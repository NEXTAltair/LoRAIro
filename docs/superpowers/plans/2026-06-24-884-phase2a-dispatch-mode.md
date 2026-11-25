# Annotate dispatch mode 土台 実装計画(#884 Phase 2a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Annotate 実行系に送信方式(dispatch mode:同期/async Batch API)の選択を導入するための土台を作る。`RunOptions.dispatch_mode` フィールド、`RunSettingsDialog` の選択行、`start_annotation` の dispatch 分岐を追加する。本 Phase では射影サービス(Phase 2b)とワーカー配線(Phase 2c)が未実装のため、async 経路はガードで止め、同期実行の振る舞いは不変に保つ。

**Architecture:** ADR 0076 §1 の「Annotate に明示的な dispatch mode(同期/async Batch API)を設けるのが Jobs submit 撤去の前提条件」を最小単位で満たす。選択 UI は既存の `RunSettingsDialog`(Wireframes v12 Frame 3)に `DsSegmentedControl` を 1 行追加する。同ダイアログの docstring にある「バックエンド未実装の操作は disabled で見せかけ操作を作らない」方針に従い、本 Phase では dispatch mode 行を **disabled とツールチップ付き**で表示し、デフォルト値を `"sync"` に固定する。`RunOptions.dispatch_mode` と `start_annotation` の分岐(`batch_api` 時のガード)はユニットテストで検証可能な形で組み込み、UI の有効化は Phase 2c へ回す。

**Tech Stack:** PySide6(QtWidgets QDialog / QtCore)、pytest-qt、Loguru

## 全体制約

- ADR 0076 を本 Phase の信頼源(SSoT)とする。Phase 2a は dispatch mode の土台のみを扱う。射影(route 分割、batch-capable フィルタ、moderation preflight 合成)は Phase 2b、ワーカースレッド配線と INFERENCE LEDGER プレビューは Phase 2c で実装する。
- **非 batch-capable 混在時の方針は (a) 拒否**とする(ユーザー確定 2026-06-24)。実装は Phase 2b の射影サービスで行い、Phase 2a では dispatch mode の選択肢のみを設ける。
- 同期実行(`dispatch_mode == "sync"`)は**振る舞いを完全に維持する**。既存の `annotation_workflow_controller.start_annotation_workflow(...)` の経路と引数は一切変更しない。
- 型ヒントを必須とし、モダンな Python 構文(`list[str]`、`X | None`)、Google スタイルの docstring、日本語の実装コメントを用いる(`.claude/rules/coding-style.md`)。
- 最大行長は 108 文字とし、Ruff フォーマットを適用する。`# type: ignore` および `# noqa` は禁止する。
- INFO ログはバッチサマリーのみとし、個別項目は DEBUG または TRACE とする(`.claude/rules/logging.md`)。
- 実装作業はワークツリーから開始する(`.claude/rules/git-workflow.md`)。ブランチは `feat/issue-884-phase2a-dispatch-mode`(作成済み)を使用する。
- 検証には CI 相当フィルタ `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` を用いる(`.claude/rules/testing.md`)。`MainWindow` 改修を含むため `tests/unit/gui/window/test_main_window_coverage.py` も含める([[feedback_tab_extraction_check_window_coverage]])。
- `QMessageBox` は必ず `monkeypatch` でモック化する(`.claude/rules/testing.md` / MEMORY.md)。

---

## Epic ロードマップ(ADR 0076 全体 / #884)

- **Phase 1(完了、PR #898 マージ済み):** `ModelSelectionStateManager` の引き上げと Annotate の購読ビュー化。
- **Phase 2(3 サブ PR に分割、ユーザー確定 2026-06-24):**
  - **Phase 2a(本計画):** dispatch mode の土台を作る。`RunOptions.dispatch_mode`、`RunSettingsDialog` の選択行(disabled)、`start_annotation` の分岐(async はガード)を追加し、同期経路は不変とする。
  - **Phase 2b:** Qt 非依存の dispatch 射影サービスを実装する。選択モデル集合を route 分割し、batch-capable モデル 1 台を 1 `provider_batch_jobs` 行へ射影する。`provider_batch_capability` ヘルパーと `list_batch_capable_models()` の discovery を再利用し、**非 batch-capable 混在時は (a) 拒否**とする。射影出力契約には `model_id`、`prompt_profile`、processed パス(ADR 0064)、moderation preflight(ADR 0070、omni-moderation 自前解決)を含める。純ロジックとユニットテストのみで、GUI 配線は行わない。
  - **Phase 2c:** async の `dispatch_mode` から射影サービスを経てワーカースレッド(ADR 0044、再入・busy ガード付き)へ配線する。INFERENCE LEDGER に async batch プレビューを表示し、`RunSettingsDialog` の dispatch mode 行を有効化する。この段階で async がエンドツーエンドで動作する。
- **Phase 3:** Jobs(`provider_batch_job_widget.py`)の submit パネル(ピッカー、ステージング、`rating_preflight` コンボ)を丸ごと撤去し、Jobs を純粋な監視台帳にする。**ユーザー可視のバグ(Annotate と Jobs 間の反映)はここで構造的に解消される**。
- **Phase 4:** wireframe v12 を反映する(Annotate の route バッジ、async batch レーン、Jobs の監視専用化)。

---

## ファイル構成

- `src/lorairo/gui/widgets/run_settings_dialog.py`(改修): `RunOptions` に `dispatch_mode: str = "sync"` を追加する。`RunSettingsDialog` に dispatch mode 選択行(disabled)を追加し、`run_options()` に反映する。
- `src/lorairo/gui/window/main_window.py`(改修): `start_annotation` に dispatch mode 分岐を追加する。`batch_api` はガード(`QMessageBox` 表示後に return)とし、`sync` は既存経路を不変で実行する。
- `tests/unit/gui/widgets/test_run_settings_dialog.py`(改修): `dispatch_mode` のデフォルト値、disabled 状態、`run_options` への反映を検証する。
- `tests/unit/gui/window/test_main_window_coverage.py`(改修): `start_annotation` の `sync`/`batch_api` 分岐のカバレッジを追加する。

---

### Task 1: `RunOptions.dispatch_mode` と `RunSettingsDialog` の選択行(disabled)

**Files:**
- Modify: `src/lorairo/gui/widgets/run_settings_dialog.py`
- Modify: `tests/unit/gui/widgets/test_run_settings_dialog.py`

**Interfaces:**
- 依存(Consumes): 既存の `DsSegmentedControl(options: list[tuple[str, str]], value: str, parent=...)`(`.value() -> str`、`.setEnabled(bool)`、`.setToolTip(str)`)。
- 提供(Produces):
  - `RunOptions.dispatch_mode: str`(デフォルト `"sync"`。値は `"sync"` または `"batch_api"`)。
  - `RunSettingsDialog._dispatch_mode: DsSegmentedControl`(disabled)。
  - `RunSettingsDialog.run_options()` が `dispatch_mode` を含めて返す。

- [ ] **Step 1: 失敗するテストを書く**

`tests/unit/gui/widgets/test_run_settings_dialog.py` に以下を追記する。既存の `TestRunSettingsDialogDefaults.test_default_run_options_match_ds` の期待値に `dispatch_mode="sync"` を追加し、新規テストクラスを追加する。

既存テストの修正(`test_default_run_options_match_ds` の assert を置換):

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

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/gui/widgets/test_run_settings_dialog.py -v`
期待結果: `TypeError: __init__() got an unexpected keyword argument 'dispatch_mode'` および `AttributeError: '_dispatch_mode'` で失敗する。

- [ ] **Step 3: `RunOptions` に `dispatch_mode` を追加する**

`src/lorairo/gui/widgets/run_settings_dialog.py` の `RunOptions` dataclass にフィールドを追加し、docstring の `Attributes:` にも 1 行追記する。

`Attributes:` ブロック末尾(`dry_run:` 行の後)に追加:

```python
        dry_run: 実推論せずジョブ件数・推定のみ検証するか。
        dispatch_mode: 送信方式 ("sync" = 同期実行 / "batch_api" = async Provider Batch API)。
```

フィールド定義(`dry_run: bool = False` の後)に追加:

```python
    dry_run: bool = False
    dispatch_mode: str = "sync"
```

- [ ] **Step 4: `RunSettingsDialog` に dispatch mode 行を追加する**

モジュール定数(`_DEDUPE_TOOLTIP` の後)にツールチップ文字列を追加する。

```python
_DISPATCH_MODE_TOOLTIP = "Batch API への async 送信は後続フェーズ (#884 Phase 2c) で配線予定。現在は同期実行のみ。"
```

`__init__` 内で dry-run チェックボックスを追加する直前(`# dry-run (実装済 → 操作可)` コメントの直前)に dispatch mode 行を追加する。

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

`run_options()` の返却値に `dispatch_mode` を追加する。

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

- [ ] **Step 5: テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/gui/widgets/test_run_settings_dialog.py -v`
期待結果: 既存テストおよび新規 3 件がすべて通る。

- [ ] **Step 6: フォーマットしてコミットする**

```bash
uv run ruff format src/lorairo/gui/widgets/run_settings_dialog.py tests/unit/gui/widgets/test_run_settings_dialog.py
uv run ruff check src/lorairo/gui/widgets/run_settings_dialog.py tests/unit/gui/widgets/test_run_settings_dialog.py --fix
git add src/lorairo/gui/widgets/run_settings_dialog.py tests/unit/gui/widgets/test_run_settings_dialog.py
git commit -m "feat(gui): RunOptions に dispatch_mode を追加・RunSettingsDialog に送信方式行 (disabled) (#884)"
```

---

### Task 2: `start_annotation` の dispatch mode 分岐(async はガード)

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`
- Modify: `tests/unit/gui/window/test_main_window_coverage.py`

**Interfaces:**
- 依存(Consumes): Task 1 の `RunOptions.dispatch_mode`、および既存の `AnnotateTabWidget.run_options() -> RunOptions`(`annotate_tab.py:459`)。
- 提供(Produces): `start_annotation` で `dispatch_mode == "batch_api"` の場合に `QMessageBox.information` を表示して return する分岐(Phase 2c で実配線へ置換する)。`"sync"` の場合は既存経路を不変で実行する。

**設計メモ:**
`start_annotation`(`main_window.py:1429`)は現状 `run_options()` を読んでいない。本タスクでは dispatch mode の判定のみを追加し、`sync` 経路の `start_annotation_workflow(...)` 呼び出しは一切変えない。`self.annotate_tab.run_options()` 経由で参照するため、`RunOptions` のインポートは不要である。判定はコントローラ未初期化ガードの直後、かつ選択モデル取得より前に配置し、early-return で同期経路へ影響させない。

- [ ] **Step 1: 失敗するテストを書く**

`tests/unit/gui/window/test_main_window_coverage.py` の現行 `main_window` フィクスチャ名と生成方法を grep で確認して流用する。`QMessageBox` は `monkeypatch` でモック化し、`annotation_workflow_controller` と `annotate_tab` は `Mock` で差し替える。

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

> **注:** `main_window` フィクスチャが DB やタブを実生成する場合でも、`annotate_tab` と `annotation_workflow_controller` を `Mock` で差し替えれば十分である。フィクスチャ名と生成手順は現行 `test_main_window_coverage.py` の他テストに合わせる。同期テストの `currentWidget` やステージングのスタブは、ワークフローが呼ばれることを確認する目的に沿ってフィクスチャの実装状況に応じ調整する。

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/gui/window/test_main_window_coverage.py -v -k start_annotation`
期待結果: `batch_api` ガードが未実装のためワークフローが呼ばれてしまい、`info_calls` が空になって失敗する。

- [ ] **Step 3: `start_annotation` に dispatch mode 分岐を追加する**

`src/lorairo/gui/window/main_window.py` の `start_annotation` 内で、コントローラ未初期化ガード(`if not self.annotation_workflow_controller:` ブロック)の直後に dispatch mode 判定を追加する。

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

- [ ] **Step 4: テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/gui/window/test_main_window_coverage.py -v -k start_annotation`
期待結果: 新規 2 件が通る。

- [ ] **Step 5: CI 相当フィルタで全体を実行する**

```bash
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"
```

期待結果: すべて通り、回帰がない。

- [ ] **Step 6: フォーマット、mypy、コミットを実行する**

```bash
uv run ruff format src/lorairo/gui/window/main_window.py tests/unit/gui/window/test_main_window_coverage.py
uv run ruff check src/lorairo/gui/window/main_window.py tests/unit/gui/window/test_main_window_coverage.py --fix
uv run mypy -p lorairo
git add src/lorairo/gui/window/main_window.py tests/unit/gui/window/test_main_window_coverage.py
git commit -m "feat(gui): start_annotation に dispatch mode 分岐を追加・async は Phase 2c guard (#884)"
```

---

## セルフレビュー

**仕様カバレッジ(ADR 0076 §1 / #884 Phase 2a):**
- 「Annotate に dispatch mode(同期/async Batch API)を設ける」: Task 1(`RunOptions.dispatch_mode` と UI 行)および Task 2(`start_annotation` 分岐)でカバーしている。✓
- 「`RunOptions` への async 経路」: `dispatch_mode` フィールドを導入済みであり、実配線は Phase 2c で行う。✓
- 「同期実行は behavior 不変」: Task 2 では early-return 分岐のみを追加し、同期経路の既存呼び出しを変更していない。✓
- 射影、batch-capable フィルタ、moderation preflight、ワーカー配線: Phase 2b–2c へ繰り延べた(ロードマップに記載済み)。✓
- 非 batch-capable 混在時の (a) 拒否: Phase 2b の射影サービスで実装する(本 Phase 2a は選択肢のみ作成)。✓

**プレースホルダ確認:**
全ステップに実コードと実コマンドを記載済みである。フィクスチャ名は既存テスト構造に依存するため、「現行を grep で確認」と明示した。

**型整合性:**
`RunOptions.dispatch_mode: str` を Task 1 で定義し、Task 2 で `run_options().dispatch_mode` として参照している。`DsSegmentedControl` の `value()`、`set_value()`、`setEnabled()`、`setToolTip()` は既存 API であることを確認済みである(`ds_segmented_control.py:213/221`、`run_settings_dialog.py:194-200`)。`AnnotateTabWidget.run_options()` も既存である(`annotate_tab.py:459`)。✓
