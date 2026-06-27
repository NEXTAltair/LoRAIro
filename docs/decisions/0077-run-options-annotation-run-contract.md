---
type: ADR
title: RunOptions アノテーション実行契約 — dry-run 短絡と rating ゲート / refusal filter 分離
status: Accepted
timestamp: 2026-06-27
tags: [annotation, gui, worker, run-options, dry-run, rating-gate]
---
# ADR 0077: RunOptions アノテーション実行契約 — dry-run 短絡と rating ゲート / refusal filter 分離

- **関連 Issue**: #803 (RunOptions 配線), #803 follow-up (#916, dry-run 短絡 + rating/refusal 分離修正)
- **関連 ADR**: 0070 (OpenAI Moderation WebAPI Preflight), 0075 (アノテーションパイプライン構成ドメインモデル), 0076 (Submit を Annotate の dispatch 射影へ移す)

## Context

#789 で `RunSettingsDialog → RunOptions` モーダルを追加したが、確定値は `main_window._pipeline_run_options` に保持されるのみで実際の annotation run flow に未適用だった (#803)。

`RunOptions` を annotation チェーンに通す実装 (PR #915) ののち Codex review で 2 件の設計違反が指摘された (PR #916):

1. **dry-run が課金発生点より下流でしか短絡していなかった**: `_save_results_to_database` のみスキップし、`_apply_refusal_prefilter` と `annotation_logic.execute_annotation` (有料 WebAPI 呼び出し / ローカル推論) は実行されていた。RunSettings ダイアログの tooltip 契約「実際に推論せずジョブ件数・推定コストだけを検証する」と矛盾する。

2. **`rating_gate=False` が refusal filter まで無効化していた**: rating ゲートと refusal filter は別概念だが、同一フラグで丸ごとスキップされていた。

## Decision

### 1. dry-run は推論前に短絡

`AnnotationWorker.execute()` の冒頭で `_dry_run` を検査し、**True であれば推論・送信・DB 保存を一切行わず件数のみ算出して返す**。

```python
# AnnotationWorker.execute() の冒頭
if self._dry_run:
    self.completed.emit(WorkerResult(total=len(image_ids), dry_run=True))
    return
```

- `_apply_refusal_prefilter` (WebAPI 呼び出し) は実行しない
- `annotation_logic.execute_annotation` (有料推論) は実行しない
- `_save_results_to_database` (DB 書き込み) は実行しない
- 件数算出 (image_ids の len) のみ行い `WorkerResult` を emit する

これに伴い `_save_results_to_database` 内の dry-run 分岐は到達不能になるため撤去する。

### 2. rating ゲートと refusal filter は独立した 2 概念

| 概念 | フラグ | 目的 | 適用タイミング |
|---|---|---|---|
| **rating ゲート** | `rating_gate: bool` | X/XXX レーティング画像を送信前に弾く。OpenAI Moderation preflight (ADR 0070) を含む | `rating_gate=True` 時のみ適用 |
| **refusal filter** | （常時） | 過去に `SAFETY_REFUSAL` / `EMPTY_ANNOTATION` で拒否された画像の再送・API 浪費を防ぐ | `rating_gate` の値に関わらず常時適用 |

`_apply_refusal_prefilter()` は「refusal filter」と「rating ゲート + moderation preflight」の 2 ブロックで構成し、rating_gate フラグは後者ブロックのみを制御する:

```python
def _apply_refusal_prefilter(self, image_paths: list[Path]) -> list[Path]:
    # refusal filter は常時適用 (SAFETY_REFUSAL / EMPTY_ANNOTATION 再送防止)
    filtered = self._filter_refused_image_paths(image_paths)
    # rating ゲートは run_options.rating_gate で制御
    if self._rating_gate:
        filtered = self._apply_rating_and_moderation_gate(filtered)
    return filtered
```

### 3. RunOptions チェーン

`RunOptions` は以下のチェーンを optional 引数として流れる。省略時は従来挙動 (dry_run=False, rating_gate=True) を維持する:

```
start_annotation (controller)
  → start_annotation_workflow
  → _start_batch_annotation
  → worker_service.start_enhanced_batch_annotation(run_options=...)
  → AnnotationWorker(run_options=...)
```

`start_annotation` は `annotate_tab.run_options()` を読んで同期アノテフローへ伝搬する。

## Consequences

- **dry-run で課金・preflight 副作用が発生しない**: ダイアログ tooltip 契約と実装が一致する
- **refusal filter は rating_gate を無効化しても動く**: 既存の API 浪費防止が誤って無効化されない
- **既存呼び出しは全て non-breaking**: `run_options` 省略 = `None` の場合は従来挙動を保持
- **`_save_results_to_database` の dry-run 分岐は削除**: 到達不能コードを残さない
