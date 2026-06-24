# Annotate dispatch mode 土台 実装計画 (#884 Phase 2a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Annotate 実行系に「送信方式 (dispatch mode) = 同期 / async Batch API」の選択を導入する土台を作る。`RunOptions.dispatch_mode` フィールド・RunSettingsDialog の選択行・`start_annotation` の dispatch 分岐を追加する。本 Phase では async 経路は射影 service (Phase 2b) / worker 配線 (Phase 2c) が未実装のため guard で止め、同期実行は behavior 不変に保つ。

**Architecture:** ADR 0076 §1「Annotate に明示的な dispatch mode (同期 / async Batch API) を設けるのが Jobs submit 撤去の前提条件」を最小単位で満たす。dispatch mode の選択 UI は既存 `RunSettingsDialog` (Wireframes v12 Frame 3) に DsSegmentedControl 1 行を追加する。`RunSettingsDialog` の方針「バックエンド未実装の操作は disabled で見せかけ操作を作らない」(同 dialog docstring) に従い、Batch API 配線が無い本 Phase では dispatch mode 行を **disabled + tooltip** で出し、default は `"sync"` 固定。`RunOptions.dispatch_mode` フィールドと `start_annotation` の分岐 (batch_api → guard) はユニットテストで検証できる形で入れ、UI enable は Phase 2c に回す。

**Tech Stack:** PySide6 (QtWidgets QDialog / QtCore), pytest-qt, Loguru。

## Global Constraints

- ADR 0076 が本 Phase の SSoT。Phase 2a は「dispatch mode の土台」のみ。射影 (route 分割 / batch-capable フィルタ / moderation preflight 合成) は Phase 2b、worker thread 配線 + INFERENCE LEDGER プレビューは Phase 2c。
- **非 batch-capable 混在時の方針は (a) 拒否** (ユーザー確定, 2026-06-24)。実装は Phase 2b の射影 service で行う。本 2a では dispatch mode の選択肢を作るだけ。
- 同期 (`dispatch_mode == "sync"`) 実行は **behavior 完全不変**。既存の `annotation_workflow_controller.start_annotation_workflow(...)` 経路・引数を一切変えない。
- 型ヒント必須・modern Python 構文 (`list[str]` / `X | None`)・Google-style docstring・実装コメントは日本語 (`.claude/rules/coding-style.md`)。
- 行長 108 / Ruff format / `# type: ignore` `# noqa` 禁止。
- INFO ログはバッチサマリーのみ。per-item は DEBUG/TRACE (`.claude/rules/logging.md`)。
- 実装作業は worktree から (`.claude/rules/git-workflow.md`)。branch `feat/issue-884-phase2a-dispatch-mode` (作成済み)。
- 検証は CI-equivalent filter: `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` (`.claude/rules/testing.md`)。MainWindow 改修を含むため `tests/unit/gui/window/test_main_window_coverage.py` も含める ([[feedback_tab_extraction_check_window_coverage]])。
- QMessageBox は必ず monkeypatch でモックする (`.claude/rules/testing.md` / MEMORY.md)。

---

## Epic ロードマップ (ADR 0076 全体 / #884)

- **Phase 1 (完了, PR #898 merge 済み)**: `ModelSelectionStateManager` hoist。Annotate を購読 view 化。
- **Phase 2 (3 サブPR に分割, ユーザー確定 2026-06-24)**:
  - **Phase 2a (本計画)**: dispatch mode の土台。`RunOptions.dispatch_mode` + RunSettingsDialog 選択行 (disabled) + `start_annotation` 分岐 (async は guard)。同期不変。
  - **Phase 2b**: Qt-free dispatch 射影 service。選択モデル集合を route 分割し batch-capable モデル1台 = 1 `provider_batch_jobs` 行へ射影。`provider_batch_capability` helper + `list_batch_capable_models()` discovery を再利用。**非 batch-capable 混在は (a) 拒否**。model_id / prompt_profile / processed パス (ADR 0064) / moderation preflight (ADR 0070, omni-moderation 自前解決) を射影出力契約に含める。純ロジック + ユニットテスト。GUI 配線なし。
  - **Phase 2c**: async dispatch_mode → 射影 service → worker thread (ADR 0044, 再入/busy ガード) を配線。INFERENCE LEDGER に async batch プレビュー。RunSettingsDialog の dispatch mode 行を enable。async が end-to-end で動く。
- **Phase 3**: Jobs (`provider_batch_job_widget.py`) submit パネル丸ごと撤去 (picker / staging / rating_preflight combo)。Jobs を純粋監視台帳に。**ユーザー可視のバグ (Annotate↔Jobs 反映) はここで構造解消**。
- **Phase 4**: wireframe v12 反映 (Annotate route バッジ / async batch レーン / Jobs 監視専用)。

---

## File Structure

- `src/lorairo/gui/widgets/run_settings_dialog.py` (改修): `RunOptions` に `dispatch_mode: str = "sync"` 追加。`RunSettingsDialog` に dispatch mode 選択行 (disabled) を追加し `run_options()` に反映。
- `src/lorairo/gui/window/main_window.py` (改修): `start_annotation` に dispatch mode 分岐を追加。`batch_api` は guard (QMessageBox + return)、`sync` は既存経路を不変で実行。
- `tests/unit/gui/widgets/test_run_settings_dialog.py` (改修): dispatch_mode default / disabled / run_options 反映の検証。
- `tests/unit/gui/window/test_main_window_coverage.py` (改修): start_annotation の sync/batch_api 分岐の coverage。

---

### Task 1: RunOptions.dispatch_mode + RunSettingsDialog 選択行 (disabled)

**Files:**
- Modify: `src/lorairo/gui/widgets/run_settings_dialog.py`
- Modify: `tests/unit/gui/widgets/test_run_settings_dialog.py`

**Interfaces:**
- Consumes: 既存 `DsSegmentedControl(options: list[tuple[str, str]], value: str, parent=...)` (`.value() -> str` / `.setEnabled(bool)` / `.setToolTip(str)`)。
- Produces:
  - `RunOptions.dispatch_mode: str` (default `"sync"`。`"sync"` または `"batch_api"`)。
  - `RunSettingsDialog._dispatch_mode: DsSegmentedControl` (disabled)。
  - `RunSettingsDialog.run_options()` が `dispatch_mode` を載せて返す。

- [ ] **Step 1: Write the failing tests**

`tests/unit/gui/widgets/test_run_settings_dialog.py` に追記する。既存 `TestRunSettingsDialogDefaults.test_default_run_options_match_ds` の期待値に `dispatch_mode="sync"` を追加し、新規テストクラスを足す。

既存テストの修正 (`test_default_run_options_match_ds` の assert を置換):

```python
    def test_default_run_options_match_ds(self, dialog):
        opts = dialog.run_options()
        assert opts == RunOptions(
            concurrency=4,
            retries=2,
            on_fail="skip",
            rating_gate=True,
            overwrite=False,
            dedupe=True,
            dry_run=False,
            dispatch_mode="sync",
        )
```

新規追記:

```python
class TestRunSettingsDialogDispatchMode:
    def test_dispatch_mode_defaults_to_sync(self, dialog):
        assert dialog.run_options().dispatch_mode == "sync"

    def test_dispatch_mode_control_is_disabled_pending_phase2c(self, dialog):
        # Batch API 配線 (Phase 2c) まで disabled。見せかけ操作を作らない方針。
        assert not dialog._dispatch_mode.isEnabled()
        assert dialog._dispatch_mode.toolTip() != ""

    def test_dispatch_mode_value_reflected_in_run_options(self, dialog):
        # control を直接操作すれば run_options に載る (Phase 2c で enable する前提の配線確認)。
        dialog._dispatch_mode.set_value("batch_api")
        assert dialog.run_options().dispatch_mode == "batch_api"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/gui/widgets/test_run_settings_dialog.py -v`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'dispatch_mode'` および `AttributeError: '_dispatch_mode'`)。

- [ ] **Step 3: Add dispatch_mode to RunOptions**

`src/lorairo/gui/widgets/run_settings_dialog.py` の `RunOptions` dataclass に field を追加する。docstring の Attributes にも 1 行足す。

`Attributes:` ブロック末尾 (`dry_run:` 行の後) に追加:

```python
        dry_run: 実推論せずジョブ件数・推定のみ検証するか。
        dispatch_mode: 送信方式 ("sync" = 同期実行 / "batch_api" = async Provider Batch API)。
```

field 定義 (`dry_run: bool = False` の後) に追加:

```python
    dry_run: bool = False
    dispatch_mode: str = "sync"
```

- [ ] **Step 4: Add dispatch mode row to RunSettingsDialog**

module 定数 (`_DEDUPE_TOOLTIP` の後) に tooltip を追加:

```python
_DISPATCH_MODE_TOOLTIP = "Batch API への async 送信は後続フェーズ (#884 Phase 2c) で配線予定。現在は同期実行のみ。"
```

`__init__` 内、dry-run チェックボックスを追加する直前 (`# dry-run (実装済 → 操作可)` コメントの直前) に dispatch mode 行を追加する:

```python
        # 送信方式 dispatch mode (Batch API 配線は Phase 2c → 現状 disabled)
        self._dispatch_mode = self._add_segment_row(
            layout,
            "送信方式 dispatch mode",
            "同期 = その場で推論。Batch API = Provider の非同期バッチへ送信 (大量・低コスト)。",
            [("sync", "同期"), ("batch_api", "Batch API")],
            "sync",
            enabled=False,
            tooltip=_DISPATCH_MODE_TOOLTIP,
        )
```

`run_options()` の返却に `dispatch_mode` を追加:

```python
    def run_options(self) -> RunOptions:
        """ダイアログの現在値を :class:`RunOptions` として返す。"""
        return RunOptions(
            concurrency=int(self._concurrency.value()),
            retries=int(self._retries.value()),
            on_fail=self._on_fail.value(),
            rating_gate=self._rating_gate.value() == "on",
            overwrite=self._overwrite.value() == "on",
            dedupe=self._dedupe.value() == "on",
            dry_run=self._dry_run.isChecked(),
            dispatch_mode=self._dispatch_mode.value(),
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/gui/widgets/test_run_settings_dialog.py -v`
Expected: PASS (既存 + 新規 3 件)。

- [ ] **Step 6: Format + commit**

```bash
uv run ruff format src/lorairo/gui/widgets/run_settings_dialog.py tests/unit/gui/widgets/test_run_settings_dialog.py
uv run ruff check src/lorairo/gui/widgets/run_settings_dialog.py tests/unit/gui/widgets/test_run_settings_dialog.py --fix
git add src/lorairo/gui/widgets/run_settings_dialog.py tests/unit/gui/widgets/test_run_settings_dialog.py
git commit -m "feat(gui): RunOptions に dispatch_mode を追加・RunSettingsDialog に送信方式行 (disabled) (#884)"
```

---

### Task 2: start_annotation の dispatch mode 分岐 (async は guard)

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/unit/gui/window/test_main_window_coverage.py`

**Interfaces:**
- Consumes: Task 1 の `RunOptions.dispatch_mode`。`AnnotateTabWidget.run_options() -> RunOptions` (既存, annotate_tab.py:459)。
- Produces: `start_annotation` が `dispatch_mode == "batch_api"` のとき QMessageBox.information を出して return する分岐 (Phase 2c で実配線に置換)。`"sync"` は既存経路を不変で実行。

**設計メモ:** `start_annotation` (main_window.py:1429) は現状 `run_options()` を読んでいない。本 Task では dispatch mode 判定のみ追加し、`sync` 経路は既存 `start_annotation_workflow(...)` 呼び出しを一切変えない。`RunOptions` の import は不要 (`self.annotate_tab.run_options()` 経由で読むため)。判定は controller 未初期化ガードの直後・選択モデル取得より前に置く (early-return で sync 経路に影響させない)。

- [ ] **Step 1: Write the failing tests**

`tests/unit/gui/window/test_main_window_coverage.py` の現行 `main_window` fixture 名・生成方法を grep で確認してから流用する。QMessageBox は monkeypatch でモックする。`annotation_workflow_controller` と `annotate_tab` は Mock で差し替える。

```python
# tests/unit/gui/window/test_main_window_coverage.py に追記
from unittest.mock import MagicMock

from lorairo.gui.widgets.run_settings_dialog import RunOptions


def test_start_annotation_batch_api_mode_shows_guard_and_skips_workflow(
    main_window, monkeypatch
):
    """dispatch_mode=batch_api は guard を出し同期 workflow を起動しない (#884 Phase 2a)。"""
    from PySide6.QtWidgets import QMessageBox

    info_calls: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "information", lambda *args, **kwargs: info_calls.append(args[1])
    )
    main_window.annotation_workflow_controller = MagicMock()
    main_window.annotate_tab = MagicMock()
    main_window.annotate_tab.run_options.return_value = RunOptions(dispatch_mode="batch_api")

    main_window.start_annotation()

    assert len(info_calls) == 1
    main_window.annotation_workflow_controller.start_annotation_workflow.assert_not_called()


def test_start_annotation_sync_mode_runs_workflow(main_window, monkeypatch):
    """dispatch_mode=sync は従来どおり同期 workflow を起動する (#884 Phase 2a)。"""
    main_window.annotation_workflow_controller = MagicMock()
    main_window.annotate_tab = MagicMock()
    main_window.annotate_tab.run_options.return_value = RunOptions(dispatch_mode="sync")
    main_window.annotate_tab.selected_litellm_model_ids.return_value = ["openai/gpt-4o"]
    # ステージング画像取得をスタブ (tabBatchTag 経路を回避し workflow 起動だけ確認)
    monkeypatch.setattr(
        main_window, "_get_staged_image_paths_for_annotation", lambda: ["/tmp/a.png"]
    )
    monkeypatch.setattr(
        main_window.tabWidgetMainMode, "currentWidget", lambda: main_window.tabBatchTag
    )

    main_window.start_annotation()

    main_window.annotation_workflow_controller.start_annotation_workflow.assert_called_once()
```

> 注: `main_window` fixture が DB / tab を実生成する場合、`annotate_tab` / `annotation_workflow_controller` の Mock 差し替えで十分。fixture 名・生成手順は現行 test_main_window_coverage.py の他テストに合わせる。sync テストの `currentWidget` / staging スタブは fixture の実装状況に応じて調整 (workflow が呼ばれることの確認が目的)。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/gui/window/test_main_window_coverage.py -v -k start_annotation`
Expected: FAIL (batch_api guard 未実装のため workflow が呼ばれてしまう / info_calls が空)。

- [ ] **Step 3: Add dispatch mode branch to start_annotation**

`src/lorairo/gui/window/main_window.py` の `start_annotation` 内、controller 未初期化ガード (`if not self.annotation_workflow_controller:` ブロック) の直後に dispatch mode 判定を追加する:

```python
        # 送信方式 (dispatch mode) 判定 (#884 Phase 2a, ADR 0076 §1)
        # batch_api (async) は射影 service (Phase 2b) / worker 配線 (Phase 2c) が未実装のため guard。
        if (
            self.annotate_tab is not None
            and self.annotate_tab.run_options().dispatch_mode == "batch_api"
        ):
            QMessageBox.information(
                self,
                "Batch API 送信",
                "Batch API への async 送信は後続フェーズ (#884 Phase 2c) で配線予定です。\n"
                "現在は同期実行のみ利用できます。",
            )
            return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/gui/window/test_main_window_coverage.py -v -k start_annotation`
Expected: PASS (新規 2 件)。

- [ ] **Step 5: Run full CI-equivalent filter**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"
```
Expected: 全 PASS (回帰なし)。

- [ ] **Step 6: Format + mypy + commit**

```bash
uv run ruff format src/lorairo/gui/window/main_window.py tests/unit/gui/window/test_main_window_coverage.py
uv run ruff check src/lorairo/gui/window/main_window.py tests/unit/gui/window/test_main_window_coverage.py --fix
uv run mypy -p lorairo
git add src/lorairo/gui/window/main_window.py tests/unit/gui/window/test_main_window_coverage.py
git commit -m "feat(gui): start_annotation に dispatch mode 分岐を追加・async は Phase 2c guard (#884)"
```

---

## Self-Review

**Spec coverage (ADR 0076 §1 / #884 Phase 2a):**
- 「Annotate に dispatch mode (同期 / async Batch API) を設ける」→ Task 1 (RunOptions.dispatch_mode + UI 行) + Task 2 (start_annotation 分岐)。✓
- 「RunOptions への async 経路」→ `dispatch_mode` field 導入。実配線は Phase 2c。✓
- 「同期実行は behavior 不変」→ Task 2 は sync 経路の既存呼び出しを変えない (early-return 分岐のみ追加)。✓
- 射影 / batch-capable フィルタ / moderation preflight / worker 配線 → **Phase 2b-2c へ繰り延べ** (ロードマップ記載)。✓
- 非 batch-capable 混在 = (a) 拒否 → Phase 2b の射影 service で実装 (本 2a は選択肢を作るだけ)。✓

**Placeholder scan:** 全 step に実コード/実コマンド記載済み。fixture 名は「現行を grep で確認」と明示 (既存テスト構造依存)。

**Type consistency:** `RunOptions.dispatch_mode: str` を Task 1 で定義し Task 2 で `run_options().dispatch_mode` として参照。`DsSegmentedControl.value()/set_value()/setEnabled()/setToolTip()` は既存 API (確認済み, ds_segmented_control.py:213/221, run_settings_dialog.py:194-200)。`AnnotateTabWidget.run_options()` は既存 (annotate_tab.py:459)。✓
