---
type: ADR
title: RunOptions アノテーション実行契約 — dry-run 短絡と rating ゲート / refusal filter 分離
status: Accepted
timestamp: 2026-06-27
tags: [annotation, gui, worker, run-options, dry-run, rating-gate]
---
# ADR 0077: RunOptions アノテーション実行契約 — dry-run 短絡と rating ゲート / refusal filter 分離

- **関連 Issue**: #803(`RunOptions` の配線)、#803 フォローアップ(#916: dry-run の早期短絡および rating ゲートと refusal filter の分離修正)
- **関連 ADR**: 0070(OpenAI Moderation WebAPI Preflight)、0075(アノテーションパイプライン構成ドメインモデル)、0076(Submit を Annotate の dispatch 射影へ移す)

## Context

#789 で `RunSettingsDialog` から `RunOptions` を設定するモーダルを追加した。しかし、確定した値は `main_window._pipeline_run_options` に保持されるだけで、実際のアノテーション実行フローには適用されていなかった(#803)。

その後、`RunOptions` をアノテーション実行チェーンへ通す実装(PR #915)を行ったところ、Codex レビューで次の 2 件の設計違反が指摘された(PR #916)。

1. **dry-run が課金発生点より下流でしか短絡していなかった**: `_save_results_to_database` のみをスキップし、`_apply_refusal_prefilter` と `annotation_logic.execute_annotation`(有料 WebAPI 呼び出しやローカル推論)が実行されていた。これは `RunSettingsDialog` のツールチップ契約である「実際に推論せずジョブ件数・推定コストだけを検証する」と矛盾する。
2. **`rating_gate=False` が refusal filter まで無効化していた**: rating ゲートと refusal filter は別個の概念であるにもかかわらず、同一フラグによってまとめてスキップされていた。

## Decision

### 1. dry-run は推論の実行前に短絡する

`AnnotationWorker.execute()` の冒頭で `_dry_run` を検査する。`True` であれば、推論、外部送信、DB 保存を一切行わず、対象件数のみを算出して処理を終了する。

```python
# AnnotationWorker.execute() の冒頭
if self._dry_run:
    self.completed.emit(WorkerResult(total=len(image_ids), dry_run=True))
    return
```

dry-run 時の挙動は次のとおりとする。

- `_apply_refusal_prefilter`(WebAPI 呼び出しを伴う処理)を実行しない。
- `annotation_logic.execute_annotation`(有料推論)を実行しない。
- `_save_results_to_database`(DB 書き込み)を実行しない。
- 対象件数(`image_ids` の長さ)のみを算出し、`WorkerResult` をシグナルで送出する。

これに伴い、`_save_results_to_database` 内の dry-run 分岐は到達不能になるため削除する。

### 2. rating ゲートと refusal filter を独立した 2 概念として分離する

| 概念 | 制御フラグ | 目的 | 適用タイミング |
|---|---|---|---|
| **rating ゲート** | `rating_gate: bool` | X・XXX レーティング画像を送信前に除外する。OpenAI Moderation preflight(ADR 0070)を含む | `rating_gate=True` の場合のみ適用 |
| **refusal filter** | (常時有効) | 過去に `SAFETY_REFUSAL` や `EMPTY_ANNOTATION` で拒否された画像の再送と API 浪費を防ぐ | `rating_gate` の値に関わらず常時適用 |

`_apply_refusal_prefilter()` は「refusal filter」と「rating ゲートおよびモデレーション事前検査」の 2 ブロックで構成し、`rating_gate` フラグは後者のブロックのみを制御する。

```python
def _apply_refusal_prefilter(self, image_paths: list[Path]) -> list[Path]:
    # refusal filter は常時適用 (SAFETY_REFUSAL / EMPTY_ANNOTATION 再送防止)
    filtered = self._filter_refused_image_paths(image_paths)
    # rating ゲートは run_options.rating_gate で制御
    if self._rating_gate:
        filtered = self._apply_rating_and_moderation_gate(filtered)
    return filtered
```

### 3. RunOptions の伝搬チェーン

`RunOptions` は次の呼び出しチェーンを任意引数(省略可能)として伝搬する。省略時は従来の挙動(`dry_run=False`、`rating_gate=True`)を維持する。

```
start_annotation (controller)
  → start_annotation_workflow
  → _start_batch_annotation
  → worker_service.start_enhanced_batch_annotation(run_options=...)
  → AnnotationWorker(run_options=...)
```

`start_annotation` は `annotate_tab.run_options()` を読み取り、同期アノテーションフローへ引き渡す。

## Consequences

- **dry-run 時に課金や事前検査の副作用が発生しない**: ダイアログのツールチップ契約と実装が一致する。
- **`rating_gate` を無効化しても refusal filter が機能する**: 既存の API 浪費防止機能が誤って無効化されない。
- **既存の呼び出し箇所に対して後方互換性を維持する**: `run_options` を省略(`None`)した場合は従来の挙動をそのまま保持する。
- **到達不能コードを残さない**: `_save_results_to_database` 内の不要になった dry-run 分岐を削除する。
