# Plan: Issue #531 `annotate run` 本番スケール OOM 修正 (Agent Teams 並列実装)

- **対象 Issue**: [#531](https://github.com/NEXTAltair/LoRAIro/issues/531) (epic) / サブ [#536](https://github.com/NEXTAltair/LoRAIro/issues/536) [#537](https://github.com/NEXTAltair/LoRAIro/issues/537) [#538](https://github.com/NEXTAltair/LoRAIro/issues/538)
- **作成日**: 2026-05-29
- **対象ファイル**: `src/lorairo/cli/commands/annotate.py` (`run()` / `_load_images_from_db()`)
- **戦略**: Contract-first 2-track 並列 + CLI レベル slice (ユーザー承認済み)

---

## 1. 要件・成功基準

### 問題
`lorairo-cli annotate run` が `_load_images_from_db()` で対象画像レコード**全件**を `PIL.Image.Image` として decode し `pil_images` に一括保持してから annotation に渡す。21,192 件規模で annotation 開始前に `[Errno 12] Cannot allocate memory` (OOM 相当) に到達。`--batch-size` は CLI option として存在するが load にも `annotator.annotate(...)` にも渡されておらず**実質未使用**。さらに `Cannot allocate memory` が通常の破損画像 warning と同じ `except Exception` に握り込まれ、致命的失敗が分かりにくい。

### 成功基準
1. **#536**: `--batch-size` が同時保持する decoded PIL 画像数を実質的に制限する。データセット > batch_size で `annotator.annotate()` が複数回呼ばれる。各チャンクの画像はチャンク処理後に close/release される。チャンクごとに DB 保存しサマリーを集計。
2. **#537**: `MemoryError` / `OSError(errno.ENOMEM)` を通常のファイル単位失敗と区別し、致命的失敗時に **non-zero exit**。通常の破損画像はスキップ継続を維持。exit code 挙動をテストで明文化。
3. **#538**: `--limit N` / `--offset N` / `--image-id ID` (repeatable) で部分実行・sharding を可能にする。無効 ID / 空選択は明確な non-zero。
4. 既存の model 解決・API key 検証・deprecated warning・結果検証・DB 保存サマリーの挙動を維持。
5. 既存 24 件の `test_commands_annotate.py` が回帰なし。

### 制約
- `src/lorairo/cli/commands/annotate.py` 1 ファイルに 3 Issue が集中 → `run()` で git conflict リスク（後述の contract で localize）。
- `get_images_by_filter()` は **ページング非対応**（全 ID 取得 → メタデータ化）。#538 は CLI レベル slice で対応（DB 層変更なし、db-schema-reviewer 不要）。
- submodule (`local_packages/*`) 変更なし → pre-PR submodule hook 非該当。

---

## 2. 現状・ギャップ分析

| 項目 | 現状 (`origin/main`) | ギャップ |
|---|---|---|
| 画像ロード | `_load_images_from_db()` が全件 decode → `list` 保持 | チャンク化されていない |
| `--batch-size` | option 定義のみ、未使用 | load/annotate に伝播していない |
| エラー分類 | `except Exception` で全 load 失敗を warning 化 | MemoryError/ENOMEM が致命扱いされない |
| exit code | 致命時 1/2 だが OOM が warning 化で素通り | 観測上 exit 0 (#537 で要追加調査) |
| 選択 | `ImageFilterCriteria(include_nsfw=True)` 全件 | limit/offset/image-id なし |
| annotate 呼び出し | `annotator.annotate(pil_images, litellm_model_ids=...)` 1 回 | チャンク反復なし |
| 保存 | `save_annotation_results(results)` 1 回 → `AnnotationSaveResult` | チャンク集計なし |

---

## 3. 検討アプローチとトレードオフ

| 案 | 並列性 | conflict | 新規ファイル | 採否 |
|---|---|---|---|---|
| Contract-first 2-track | 高（A=#536+#537 / B=#538） | run() 上部に局所化、lead が手動 wiring | なし | **採用** |
| Refactor-first 3-track (新 pipeline モジュール) | 最大 | seam で完全分離 | `annotate_pipeline.py` 新設（CLAUDE.md「不要ファイル回避」とトレードオフ）+ Phase0 ブロッキング | 不採用 |
| 順次実装 | なし | なし | なし | 不採用（並列の利点なし） |

**#538 の slice 実装場所**: CLI レベル slice を採用。メタデータは dict なので 21k 件でもメモリ問題なし（画像 decode は #536 のチャンクで制御）。DB 層非変更で Track B が完全独立。

---

## 4. 凍結する契約 (Contract — 並列開始前に固定)

並列開始前にこのセクションのシグネチャを**凍結**する。両 Track はこの契約に対して実装し、`run()` 内の seam 変数 **`records_to_process: list[dict[str, Any]]`** を介して合流する。

### Track B (#538) が提供
```python
def _select_image_records(
    image_records: list[dict[str, Any]],
    *,
    limit: int | None,
    offset: int,
    image_ids: list[int] | None,
) -> list[dict[str, Any]]:
    """フィルタ済みレコードに image-id 選択 → offset → limit を適用。

    - image_ids 指定時: record["id"] でフィルタ。要求 ID のうち未存在のものは
      warning。フィルタ結果が空なら呼び出し側が non-zero exit。
    - offset/limit: image_ids 適用後のリストに対し records[offset:offset+limit]。
    """
```
- `run()` への追加 option: `--limit`(int|None, default None) / `--offset`(int, default 0) / `--image-id`(list[int], `-i`, repeatable, default [])。
- `run()` 内で `image_records` 取得後に
  `records_to_process = _select_image_records(image_records, limit=limit, offset=offset, image_ids=image_id)` を生成。
- 空選択時のエラーメッセージと `typer.Exit(code=1)`。

### Track A (#537) が提供 — エラー分類
```python
import errno
from enum import Enum

class LoadFailureAction(Enum):
    SKIP = "skip"      # 破損/欠損ファイル → warning して継続
    FATAL = "fatal"    # MemoryError / ENOMEM → 致命

class ImageLoadMemoryError(RuntimeError):
    """メモリ/リソース枯渇による致命的ロード失敗。"""

def _classify_load_failure(exc: BaseException) -> LoadFailureAction:
    """MemoryError と errno.ENOMEM 相当の OSError を FATAL、他を SKIP に分類。"""
```

### Track A (#536) が提供 — ストリーミング
```python
from collections.abc import Iterator

def _iter_record_batches(
    records: list[dict[str, Any]], batch_size: int
) -> Iterator[list[dict[str, Any]]]:
    """records を batch_size 単位の chunk に分割。"""

def _load_batch_images(
    records_chunk: list[dict[str, Any]],
) -> tuple[list[Image.Image], int, int]:
    """chunk 内の画像のみ open/load。例外は _classify_load_failure で分岐。
    FATAL → ImageLoadMemoryError を raise(呼び出し側で non-zero exit)。
    SKIP  → warning + failed_count++。
    Returns: (images, loaded, failed)。
    """
```
- `run()` 内 driver (Track A 所有):
```python
total_loaded = total_failed = 0
agg_success = agg_skip = agg_error = 0
all_results_empty = True
try:
    for chunk in _iter_record_batches(records_to_process, batch_size):
        images, loaded, failed = _load_batch_images(chunk)   # FATAL は raise
        total_loaded += loaded; total_failed += failed
        if not images:
            continue
        try:
            results = annotator.annotate(images, litellm_model_ids=resolved_litellm_ids)
            if results:
                all_results_empty = False
                _accumulate_chunk_errors(results, ...)        # 全失敗判定は run 全体で集計
                sr = container.annotation_save_service.save_annotation_results(results)
                agg_success += sr.success_count; agg_skip += sr.skip_count; agg_error += sr.error_count
        finally:
            for img in images:
                img.close()
except ImageLoadMemoryError as e:
    console.print(f"[red]Error:[/red] Memory/resource exhaustion during image load: {e}")
    raise typer.Exit(code=1) from e
```
- **全失敗判定の互換性**: 既存 `_handle_annotation_results` は「結果空 or 全モデル失敗で Exit(1)」。ストリーミングでは「**全チャンク通算**で 1 件も成功しなければ Exit(1)」へ意味を保ちつつ変更。1 チャンクの失敗で全体を中断しない。Track A が `_check_annotation_errors` を再利用し通算集計するヘルパーへ整理。
- サマリーは通算カウンタ (`total_loaded` / `agg_success` / `agg_skip` / `agg_error`) で表示。

### 合流規約 (lead が integration で wiring)
- seam 変数名は **`records_to_process`** で固定。
- Track A は driver を `records_to_process` 消費前提で実装（Track B 未完でも `records_to_process = image_records` の暫定行でローカル開発可）。
- Track B は option + `_select_image_records` + seam 生成行のみ担当、driver には触れない。
- lead は merge 時に「B の option/seam 生成行」+「A の driver/loader/classify」を `run()` に結合。conflict は option params と seam 生成行の数行に局所化。

---

## 5. チーム編成と担当 (Agent Teams)

推奨サイズ 3（コア）+ 2（統合フェーズのレビュー）。worktree は `/tmp/worktrees/` 配下、`UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv` 共有（worktree 専用 `.venv` を作らない）。

| ロール | 担当 | 主タスク | ファイル所有 |
|---|---|---|---|
| **Team Lead** (orchestrator) | 契約凍結・wiring・CI-equiv・PR | 後述 | `run()` 最終結合のみ |
| **Track A** (claude, worktree `wt-531a`) | #536 + #537 | loader/streaming/classify + driver | `annotate.py` のヘルパー群 + driver、`tests/unit/cli/test_annotate_streaming.py`(#536)、`tests/unit/cli/test_annotate_load_failure.py`(#537) |
| **Track B** (claude, worktree `wt-531b`) | #538 | `_select_image_records` + CLI option | `annotate.py` の option/seam、`tests/unit/cli/test_annotate_selection.py`(#538) |
| **test-runner** (統合時) | CI-equiv filter 実行・回帰検証 | 統合ブランチ検証 | (read/test only) |
| **code-reviewer** (統合時) | コード品質・規約準拠レビュー | PR 前レビュー | (read only) |

> ファイル競合回避: 両 Track は**別 worktree** + **別テストファイル**。`annotate.py` 本体は契約で関数単位に分割所有し、`run()` のみ lead が最終結合。

---

## 6. 実装計画 (フェーズ分割)

### Phase 0 — 契約凍結 (Lead, ブロッキング, 短時間)
- 本計画 §4 の契約をレビュー → 凍結。
- 2 つの worktree を作成:
  ```bash
  git worktree add /tmp/worktrees/wt-531a -b feat/issue-536-537-streaming
  git worktree add /tmp/worktrees/wt-531b -b feat/issue-538-selection
  ```
- 各 Track へ契約 §4 とテスト要件を伝達。

### Phase 1 — 並列実装 (Track A / Track B 同時)

**Track A (#536 + #537)** — branch `feat/issue-536-537-streaming`
1. `_classify_load_failure` + `LoadFailureAction` + `ImageLoadMemoryError` 追加 (#537)。
2. `_iter_record_batches` 追加 (#536)。
3. `_load_batch_images` 追加: per-image load + 分類分岐 (FATAL raise / SKIP warn) (#536+#537)。
4. `run()` の driver をチャンクストリーミングへ書き換え。`_load_images_from_db` は削除 or `_load_batch_images` へ吸収。通算サマリー集計。`ImageLoadMemoryError` → Exit(1)。
5. 全失敗判定を「通算 0 成功で Exit(1)」へ整理（既存 `_handle_annotation_results`/`_check_annotation_errors` 再利用）。
6. テスト:
   - `test_annotate_streaming.py` (#536): dataset > batch_size で `annotate()` が複数回呼ばれる / chunk 後に `img.close()` 呼ばれる / 単一バッチ小規模互換。
   - `test_annotate_load_failure.py` (#537): `MemoryError` で non-zero / `OSError(errno.ENOMEM)` で non-zero / 通常破損はスキップ継続 / exit code 明文化。

**Track B (#538)** — branch `feat/issue-538-selection`
1. `_select_image_records` 実装 (image-id フィルタ → offset → limit、未存在 ID 警告)。
2. `run()` に `--limit` / `--offset` / `--image-id` option 追加 + seam 生成行
   `records_to_process = _select_image_records(...)`（暫定 driver は既存 `_load_images_from_db(records_to_process)` 呼び出しでローカル green を維持）。
3. 空選択 → `typer.Exit(code=1)` + メッセージ。
4. テスト `test_annotate_selection.py` (#538): `--limit N` で最大 N / `--offset N --limit M` で deterministic 継続 / `--image-id` で指定 ID のみ / 無効 ID・空選択で non-zero。

> 各 worktree で `UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run pytest tests/unit/cli/<own_test>.py` を実行（共有 venv、並列 `uv sync` 禁止）。

### Phase 2 — 統合 (Lead)
1. 統合ブランチ `feat/issue-531-annotate-oom` を main から作成。
2. Track A → Track B の順に merge。`run()` の conflict を契約 §4「合流規約」に従い手動解決（B の option/seam + A の driver を結合、`_select_image_records` の戻り値を `records_to_process` として driver へ）。
3. 暫定 driver（B 側の `_load_images_from_db` 呼び出し）を A の streaming driver で置換。
4. 結合後の `run()` を読み直し: option → model 解決 → API key 検証 → `image_records` 取得 → `_select_image_records` → 空チェック → streaming driver。

### Phase 3 — 検証 (test-runner / Lead)
- CI-equivalent filter (LoRAIro Unit):
  ```bash
  .venv/bin/pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow" --timeout=60
  ```
- 既存 `test_commands_annotate.py` 24 件 + 新規 3 ファイルが green。
- `make format` / `make mypy`。

### Phase 4 — 投機調査 (#537 補足, 非ブロッキング)
- exit code 0 観測の追加調査（呼び出し側 wrapper / shell / プロセス終了経路）。本修正（FATAL → Exit(1)）でユーザー影響は解消されるため PR ブロックしない。判明事項は Issue #537 にコメント。

### Phase 5 — PR (Lead, code-reviewer)
- `feat/issue-531-annotate-oom` → main の PR 起票。`Closes #536 #537 #538`、`#531` を参照。
- code-reviewer レビュー → 反映 → squash merge。

---

## 7. テスト戦略

| 種別 | 内容 | コマンド |
|---|---|---|
| Unit (#536) | チャンク反復・close 呼び出し・小規模互換 | mock `annotator.annotate` で call 回数検証、`Image.close` を spy |
| Unit (#537) | `MemoryError`/`ENOMEM` → exit≠0、破損 → skip 継続、exit code 明文化 | `monkeypatch` で `Image.open`/`img.load` に例外注入 |
| Unit (#538) | limit/offset/image-id 選択・無効 ID・空選択 | `CliRunner` + mock repo |
| 回帰 | 既存 24 テスト維持 | `test_commands_annotate.py` |
| CI-equiv | フィルタ完全一致で regression なし確認 | §6 Phase 3 コマンド |

- モック方針: `annotator.annotate` / repository / `save_annotation_results` をモック。`Image.open`/`img.load` は monkeypatch で例外注入。`QMessageBox` 非該当 (CLI)。
- BDD: CLI レイヤーのため必須でない。OOM 回避の振る舞いをサービス仕様として残す価値はあるが本 Issue では unit 中心（各 Issue の Acceptance も mocked unit を指定）。

---

## 8. リスクと対策

| リスク | 影響 | 対策 |
|---|---|---|
| `run()` での merge conflict | 統合遅延 | 契約で seam 変数 `records_to_process` 固定、関数単位所有、lead が一括 wiring |
| 全失敗判定の意味変更 | 既存テスト破壊 | 「通算 0 成功で Exit(1)」へ整理、既存ヘルパー再利用、回帰テスト必須 |
| 並列 `uv sync` で venv 破損 (#222) | 環境全損 | worktree で `UV_PROJECT_ENVIRONMENT` 共有・`uv sync` 直列、`--active` 禁止 |
| `_load_batch_images` の close 漏れ | メモリ未解放で OOM 再発 | `finally` で close、テストで spy 検証 |
| #538 image-id と offset/limit の適用順序曖昧 | 期待外の選択 | 契約で「image-id → offset → limit」順を固定・テストで明示 |
| exit 0 の真因未解明 | 再発懸念 | Phase 4 で調査、ただし FATAL→Exit(1) で影響解消、非ブロッキング |

---

## 9. 次ステップ (implement への引き継ぎ)

1. 本計画承認後、Lead が Phase 0 (契約凍結 + worktree 作成)。
2. Track A / Track B を Agent Teams のチームメートとして spawn（`isolation: "worktree"`、別ブランチ・別テストファイル）。
3. 並列実装 → Lead 統合 → CI-equiv 検証 → PR。
4. 重要設計判断（CLI streaming annotation の契約・全失敗判定の通算化）は必要に応じて ADR 追記を検討（ADR 0033/0034 の worker batch 契約と整合）。

---

## 参照
- ADR 0014 (Agent Teams Integration) / ADR 0024 (pytest 責務分離) / ADR 0033-0034 (annotation worker batch 契約)
- `.claude/rules/testing.md` (CI-equivalent filter) / `.claude/rules/parallel-execution.md` (worktree venv) / `.claude/rules/git-workflow.md`
- `src/lorairo/cli/commands/annotate.py` / `src/lorairo/annotations/annotator_adapter.py` / `src/lorairo/services/annotation_save_service.py` / `src/lorairo/database/repository/image.py`
