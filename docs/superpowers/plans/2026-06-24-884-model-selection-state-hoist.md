# ModelSelectionStateManager Hoist 実装計画 (#884 Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** モデル選択 (選択 litellm_model_id 集合) の SSoT を `ModelSelectionWidget` の checkbox state から `gui/state/` の QObject 状態マネージャへ hoist し、Annotate タブを購読 view に降格する。

**Architecture:** ADR 0074 の `StagingStateManager` の前例に倣い、`gui/state/model_selection_state.py` に `ModelSelectionStateManager(QObject)` を新設する。MainWindow が所有・DI し、`AnnotateTabWidget` 内で `ModelSelectionWidget` (view) ↔ manager (SSoT) を loop guard 付きで双方向同期する。本 Phase は behavior 不変の refactor で、後続 Phase (dispatch 射影 / Jobs submit 撤去) の土台を作る。

**Tech Stack:** PySide6 (QtCore QObject/Signal), pytest-qt, Loguru。

## Global Constraints

- ADR 0076 が本 Phase の SSoT。SSoT = 選択モデル集合 (ADR 0075)、所在を gui/state/ へ移す改定 (#884 hoist)。
- 型ヒント必須・modern Python 構文 (`list[str]` / `X | None`)・Google-style docstring・実装コメントは日本語 (`.claude/rules/coding-style.md`)。
- 行長 108 / Ruff format / `# type: ignore` `# noqa` 禁止。
- INFO ログはバッチサマリーのみ。per-item は DEBUG/TRACE (`.claude/rules/logging.md`)。`StagingStateManager` と同じ粒度に揃える。
- 実装作業は worktree から (`.claude/rules/git-workflow.md`)。branch `refactor/issue-884-model-selection-state`。
- 検証は CI-equivalent filter: `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` (`.claude/rules/testing.md`)。タブ抽出系の回帰は `tests/unit/gui/window/test_main_window_coverage.py` も含める ([[feedback_tab_extraction_check_window_coverage]])。
- Qt-free ≠ QObject 排除。state manager は QObject 維持が正解 ([[feedback_qt_free_not_qobject_exclusion]])。

---

## Epic ロードマップ (ADR 0076 全体)

本計画は **Phase 1 のみ**。後続は別計画 (別 PR) として起票する:

- **Phase 1 (本計画)**: `ModelSelectionStateManager` hoist。Annotate を購読 view 化。behavior 不変の土台。
- **Phase 2**: Annotate に dispatch mode (同期 / async Batch API) を追加 + Qt-free dispatch 射影 service (`provider_batch_capability` + `list_batch_capable_models` 再利用、worker thread, ADR 0044)。
- **Phase 3**: Jobs (`provider_batch_job_widget.py`) の submit パネル丸ごと撤去 (picker / staging / rating_preflight combo)。Jobs を純粋監視台帳に。
- **Phase 4**: wireframe v12 反映 (Annotate route バッジ / async batch レーン / Jobs 監視専用)。

Phase 1 単体で「選択 state が 1 箇所に集約」を達成し、ユニットテスト可能。ユーザー可視のバグ解消 (Annotate↔Jobs 反映) は Phase 3 まで保留 (ADR 0076: Jobs は購読せず picker 撤去で解消)。

---

## File Structure

- `src/lorairo/gui/state/model_selection_state.py` (新規): `ModelSelectionStateManager(QObject)`。選択 litellm_model_id 集合の SSoT。
- `src/lorairo/gui/window/main_window.py` (改修): manager の生成・所有・AnnotateTab への DI。
- `src/lorairo/gui/tab/annotate_tab.py` (改修): manager を DI 受け取り、`ModelSelectionWidget` と双方向同期。`selected_litellm_model_ids()` を manager 起点に。
- `tests/unit/gui/state/test_model_selection_state.py` (新規): manager のユニットテスト。
- `tests/unit/gui/tab/test_annotate_tab.py` (改修): DI 引数追加・同期検証。
- `tests/unit/gui/window/test_main_window_coverage.py` (改修): manager 初期化・DI 委譲の coverage。

---

### Task 1: ModelSelectionStateManager (gui/state/ QObject SSoT)

**Files:**
- Create: `src/lorairo/gui/state/model_selection_state.py`
- Test: `tests/unit/gui/state/test_model_selection_state.py`

**Interfaces:**
- Consumes: なし (PySide6 QtCore のみ)。
- Produces:
  - `class ModelSelectionStateManager(QObject)`
  - Signal `selection_changed = Signal(list)` (現在の選択 `list[str]` を載せる)
  - `get_selected() -> list[str]` (選択順を保持)
  - `set_selected(litellm_model_ids: list[str]) -> None` (集合を置換。変化時のみ emit)
  - `set_model_selected(litellm_model_id: str, selected: bool) -> None` (1 件 ON/OFF。変化時のみ emit)
  - `clear() -> None` (空に。元が非空のときのみ emit)
  - `count() -> int`
  - `is_selected(litellm_model_id: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/gui/state/test_model_selection_state.py
"""ModelSelectionStateManager のユニットテスト (#884 Phase 1, ADR 0076)。"""

import pytest

from lorairo.gui.state.model_selection_state import ModelSelectionStateManager

pytestmark = pytest.mark.unit


@pytest.fixture
def manager(qapp) -> ModelSelectionStateManager:
    return ModelSelectionStateManager()


def test_initial_state_is_empty(manager: ModelSelectionStateManager) -> None:
    assert manager.get_selected() == []
    assert manager.count() == 0
    assert manager.is_selected("openai/gpt-4o") is False


def test_set_selected_replaces_set_and_preserves_order(manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["b", "a", "c"])
    assert manager.get_selected() == ["b", "a", "c"]
    assert manager.count() == 3
    assert manager.is_selected("a") is True


def test_set_selected_dedupes(manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a", "a", "b"])
    assert manager.get_selected() == ["a", "b"]


def test_set_selected_emits_only_on_change(qtbot, manager: ModelSelectionStateManager) -> None:
    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.set_selected(["a", "b"])
    assert blocker.args == [["a", "b"]]

    # 同一集合 (順序同一) の再設定は emit しない
    received: list[list[str]] = []
    manager.selection_changed.connect(lambda ids: received.append(ids))
    manager.set_selected(["a", "b"])
    assert received == []


def test_set_model_selected_toggles_one(qtbot, manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a"])
    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.set_model_selected("b", True)
    assert blocker.args == [["a", "b"]]

    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.set_model_selected("a", False)
    assert blocker.args == [["b"]]


def test_set_model_selected_noop_does_not_emit(manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a"])
    received: list[list[str]] = []
    manager.selection_changed.connect(lambda ids: received.append(ids))
    manager.set_model_selected("a", True)  # 既に選択
    manager.set_model_selected("z", False)  # 元々未選択
    assert received == []


def test_clear_emits_only_when_nonempty(qtbot, manager: ModelSelectionStateManager) -> None:
    manager.set_selected(["a"])
    with qtbot.waitSignal(manager.selection_changed, timeout=1000) as blocker:
        manager.clear()
    assert blocker.args == [[]]

    received: list[list[str]] = []
    manager.selection_changed.connect(lambda ids: received.append(ids))
    manager.clear()  # 既に空
    assert received == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/gui/state/test_model_selection_state.py -v`
Expected: FAIL (ModuleNotFoundError: lorairo.gui.state.model_selection_state)

- [ ] **Step 3: Write minimal implementation**

```python
# src/lorairo/gui/state/model_selection_state.py
"""選択モデル集合の状態マネージャ (Epic #867 / #884, ADR 0076)。

選択モデル集合 (アノテーション構成の SSoT, ADR 0075) を保持する単一信頼源。
従来 ``ModelSelectionWidget`` の checkbox state が事実上の SSoT だったが、本マネージャへ
hoist し、各 ``ModelSelectionWidget`` は本マネージャを購読する view へ降格する
(ADR 0076、ADR 0074 ``StagingStateManager`` の前例に倣う)。

順序保持・重複排除を担い、変更を Signal で通知する。
"""

from collections import OrderedDict

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger


class ModelSelectionStateManager(QObject):
    """選択モデル集合 (litellm_model_id) の単一信頼源 (SSoT)。

    選択された ``litellm_model_id`` を追加順に保持し、置換・単件トグル・クリアを
    提供する。複数の ``ModelSelectionWidget`` が本インスタンスを共有することで、
    タブ間のモデル選択状態を一元化する (#884)。

    Signals:
        selection_changed: 選択集合が変化したとき、現在の選択 ``list[str]`` を載せて発行。
    """

    selection_changed = Signal(list)  # list[str] - 選択 litellm_model_id (追加順)

    def __init__(self, parent: QObject | None = None) -> None:
        """選択モデル状態マネージャを初期化する。

        Args:
            parent: 親 QObject。
        """
        super().__init__(parent)
        # 順序保持 + 重複排除のため OrderedDict の key を集合として使う
        self._selected: OrderedDict[str, None] = OrderedDict()

    def get_selected(self) -> list[str]:
        """選択中の litellm_model_id を追加順で返す。"""
        return list(self._selected.keys())

    def count(self) -> int:
        """選択中のモデル数を返す。"""
        return len(self._selected)

    def is_selected(self, litellm_model_id: str) -> bool:
        """指定モデルが選択中かを返す。"""
        return litellm_model_id in self._selected

    def set_selected(self, litellm_model_ids: list[str]) -> None:
        """選択集合を置換する (重複排除・順序保持)。変化時のみ発行する。

        Args:
            litellm_model_ids: 新しい選択集合。
        """
        new_selected: OrderedDict[str, None] = OrderedDict()
        for litellm_model_id in litellm_model_ids:
            new_selected[litellm_model_id] = None
        if list(new_selected.keys()) == list(self._selected.keys()):
            return
        self._selected = new_selected
        logger.info(f"選択モデル集合を更新: {len(self._selected)} 件")
        self.selection_changed.emit(self.get_selected())

    def set_model_selected(self, litellm_model_id: str, selected: bool) -> None:
        """単一モデルの選択を ON/OFF する。変化時のみ発行する。

        Args:
            litellm_model_id: 対象モデルの litellm_model_id。
            selected: True で選択追加、False で解除。
        """
        present = litellm_model_id in self._selected
        if selected and not present:
            self._selected[litellm_model_id] = None
        elif not selected and present:
            del self._selected[litellm_model_id]
        else:
            return
        self.selection_changed.emit(self.get_selected())

    def clear(self) -> None:
        """選択集合を空にする。元が非空のときのみ発行する。"""
        if not self._selected:
            return
        self._selected.clear()
        logger.info("選択モデル集合をクリア")
        self.selection_changed.emit([])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/gui/state/test_model_selection_state.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Format + commit**

```bash
uv run ruff format src/lorairo/gui/state/model_selection_state.py tests/unit/gui/state/test_model_selection_state.py
uv run ruff check src/lorairo/gui/state/model_selection_state.py tests/unit/gui/state/test_model_selection_state.py --fix
git add src/lorairo/gui/state/model_selection_state.py tests/unit/gui/state/test_model_selection_state.py
git commit -m "feat(gui): 選択モデル集合の SSoT ModelSelectionStateManager を新設 (#884)"
```

---

### Task 2: Annotate タブを購読 view に降格 + MainWindow 配線

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py` (state manager 生成・DI)
- Modify: `src/lorairo/gui/tab/annotate_tab.py` (DI 受け取り・双方向同期)
- Modify: `tests/unit/gui/tab/test_annotate_tab.py` (DI 引数追加・同期検証)
- Modify: `tests/unit/gui/window/test_main_window_coverage.py` (初期化 coverage)

**Interfaces:**
- Consumes: Task 1 の `ModelSelectionStateManager` (`get_selected` / `set_selected` / `set_model_selected` / `selection_changed`)。
- Produces:
  - `AnnotateTabWidget.__init__` に `model_selection_state_manager: ModelSelectionStateManager | None` キーワードを追加 (凍結契約の拡張)。
  - `MainWindow.model_selection_state_manager: ModelSelectionStateManager | None` 属性。

**設計メモ (loop guard):** `ModelSelectionWidget.model_selection_changed (list)` → manager.`set_selected`、manager.`selection_changed` → widget.`set_selected_models` の双方向。再帰防止に `self._syncing_model_selection` フラグでガードする。`set_selected_models` は signal 抑制 setter なので、その後 manager は emit 済みで widget 側 emit は起きないが、安全のためガードを通す。`selected_litellm_model_ids()` getter は manager を SSoT として読む。

- [ ] **Step 1: Write the failing tests (annotate_tab)**

`tests/unit/gui/tab/test_annotate_tab.py` の AnnotateTabWidget 生成 fixture (105, 143 行付近の 2 箇所) に `model_selection_state_manager=` 引数を追加し、同期テストを追記する。

```python
# tests/unit/gui/tab/test_annotate_tab.py に追記
from lorairo.gui.state.model_selection_state import ModelSelectionStateManager


def test_widget_selection_propagates_to_state_manager(qtbot, annotate_tab_with_state):
    """ModelSelectionWidget の選択変化が state manager へ伝播する。"""
    widget, state_manager = annotate_tab_with_state
    widget.batch_model_selection.model_selection_changed.emit(["openai/gpt-4o"])
    assert state_manager.get_selected() == ["openai/gpt-4o"]


def test_state_manager_change_updates_widget_and_getter(qtbot, annotate_tab_with_state):
    """state manager の変更が widget と selected_litellm_model_ids() に反映される。"""
    widget, state_manager = annotate_tab_with_state
    # checkbox を持つモデルだけが widget へ反映されるため、getter は manager 起点で読む
    state_manager.set_selected(["openai/gpt-4o"])
    assert widget.selected_litellm_model_ids() == ["openai/gpt-4o"]
```

新規 fixture (既存 fixture 群の近くに追加。既存の生成パターンを流用し `model_selection_state_manager` を渡す):

```python
@pytest.fixture
def annotate_tab_with_state(qtbot, mock_service_container, mock_db_manager):
    state_manager = ModelSelectionStateManager()
    widget = AnnotateTabWidget(
        service_container=mock_service_container,
        db_manager=mock_db_manager,
        staging_state_manager=None,
        dataset_state_manager=None,
        model_selection_state_manager=state_manager,
    )
    qtbot.addWidget(widget)
    return widget, state_manager
```

> 注: `mock_service_container` / `mock_db_manager` は既存 fixture 名に合わせること (test_annotate_tab.py の現行 fixture を grep で確認してから流用)。`selected_litellm_model_ids()` が manager 起点で値を返す検証なので、checkbox 未生成でも getter は manager を読む実装にする。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/gui/tab/test_annotate_tab.py -v`
Expected: FAIL (TypeError: unexpected keyword argument 'model_selection_state_manager')

- [ ] **Step 3: Implement AnnotateTabWidget DI + 双方向同期**

`annotate_tab.py` の import に追加:

```python
from ..state.model_selection_state import ModelSelectionStateManager
```

`__init__` シグネチャに引数追加 (凍結契約 docstring も合わせて更新):

```python
    def __init__(
        self,
        *,
        service_container: ServiceContainer,
        db_manager: ImageDatabaseManager | None,
        staging_state_manager: StagingStateManager | None,
        dataset_state_manager: DatasetStateManager | None,
        model_selection_state_manager: ModelSelectionStateManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
```

`__init__` 本体 (`self._dataset_state_manager = dataset_state_manager` の直後) に追加:

```python
        self._model_selection_state_manager = model_selection_state_manager
        # widget ↔ state manager 双方向同期の再帰ガード
        self._syncing_model_selection = False
```

`_build_pipeline_composition_panel` の Signal 配線部 (`self._batch_model_selection.model_selection_changed.connect(self._on_pipeline_models_changed)` の直後) に state 同期配線を追加:

```python
        # モデル選択 SSoT を gui/state/ へ hoist (#884, ADR 0076)
        if self._model_selection_state_manager is not None:
            self._batch_model_selection.model_selection_changed.connect(
                self._on_widget_model_selection_changed
            )
            self._model_selection_state_manager.selection_changed.connect(
                self._on_state_model_selection_changed
            )
```

同期ハンドラと getter 改修を追加 (`selected_litellm_model_ids` の定義を置換):

```python
    def _on_widget_model_selection_changed(self, litellm_model_ids: list[str]) -> None:
        """ModelSelectionWidget の選択変化を state manager (SSoT) へ反映する (#884)。"""
        if self._syncing_model_selection or self._model_selection_state_manager is None:
            return
        self._syncing_model_selection = True
        try:
            self._model_selection_state_manager.set_selected(list(litellm_model_ids))
        finally:
            self._syncing_model_selection = False

    def _on_state_model_selection_changed(self, litellm_model_ids: list[str]) -> None:
        """state manager (SSoT) の変化を ModelSelectionWidget (view) へ反映する (#884)。"""
        if self._syncing_model_selection:
            return
        self._syncing_model_selection = True
        try:
            self._batch_model_selection.set_selected_models(list(litellm_model_ids))
            self._refresh_pipeline_panel(list(litellm_model_ids))
        finally:
            self._syncing_model_selection = False

    def selected_litellm_model_ids(self) -> list[str]:
        """選択中のモデル (litellm_model_id) を返す。

        SSoT は ``ModelSelectionStateManager`` (#884)。未注入時は従来どおり
        ``ModelSelectionWidget`` の checkbox state を読む。
        """
        if self._model_selection_state_manager is not None:
            return self._model_selection_state_manager.get_selected()
        return self._batch_model_selection.get_selected_models()
```

- [ ] **Step 4: Implement MainWindow 配線**

`main_window.py` import 追加 (39 行 staging import の近く):

```python
from ..state.model_selection_state import ModelSelectionStateManager
```

属性宣言追加 (77 行 `staging_state_manager` 宣言の近く):

```python
    model_selection_state_manager: ModelSelectionStateManager | None
```

`_initialize_staging_state_manager()` 呼び出し (228 行付近) の直後に初期化呼び出しを追加し、init メソッドを新設:

```python
        self._initialize_model_selection_state_manager()
```

```python
    def _initialize_model_selection_state_manager(self) -> None:
        """選択モデル集合の SSoT (ModelSelectionStateManager) を初期化する (#884, ADR 0076)。"""
        try:
            self.model_selection_state_manager = ModelSelectionStateManager()
            logger.info("✅ ModelSelectionStateManager初期化成功")
        except RuntimeError as e:
            logger.error(f"❌ ModelSelectionStateManager初期化失敗: {e}")
            self.model_selection_state_manager = None
```

AnnotateTabWidget 生成箇所 (731 行付近) に DI 追加:

```python
        widget = AnnotateTabWidget(
            service_container=self.service_container,
            db_manager=self.db_manager,
            staging_state_manager=self.staging_state_manager,
            dataset_state_manager=self.dataset_state_manager,
            model_selection_state_manager=self.model_selection_state_manager,
            parent=...,  # 既存の parent 引数をそのまま維持
        )
```

> 注: 731 行の既存 `AnnotateTabWidget(` 呼び出しの実引数構成を Read で確認し、`model_selection_state_manager=` を 1 行追加するだけにとどめる (他引数・parent は現状維持)。

- [ ] **Step 5: Run annotate_tab tests to verify they pass**

Run: `uv run pytest tests/unit/gui/tab/test_annotate_tab.py -v`
Expected: PASS (既存 + 新規 2 件)

- [ ] **Step 6: Add MainWindow coverage test**

`tests/unit/gui/window/test_main_window_coverage.py` に追記 (既存 MainWindow fixture を流用):

```python
def test_model_selection_state_manager_initialized(main_window):
    """MainWindow が ModelSelectionStateManager を初期化し AnnotateTab へ DI する (#884)。"""
    from lorairo.gui.state.model_selection_state import ModelSelectionStateManager

    assert isinstance(main_window.model_selection_state_manager, ModelSelectionStateManager)
```

> 注: `main_window` fixture 名・生成方法は test_main_window_coverage.py の現行 fixture を grep で確認して流用する。DB 初期化を伴う fixture の場合は既存パターンに従う。

- [ ] **Step 7: Run coverage test + full CI-equivalent filter**

```bash
uv run pytest tests/unit/gui/window/test_main_window_coverage.py -v
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"
```
Expected: 全 PASS (回帰なし)。

- [ ] **Step 8: Format + mypy + commit**

```bash
uv run ruff format src/lorairo/gui/state/model_selection_state.py src/lorairo/gui/tab/annotate_tab.py src/lorairo/gui/window/main_window.py
uv run ruff check src/ tests/ --fix
uv run mypy -p lorairo
git add -A
git commit -m "refactor(gui): モデル選択 state を ModelSelectionStateManager へ hoist・Annotate を購読 view 化 (#884)"
```

---

## Self-Review

**Spec coverage (ADR 0076 §3 / #884 step 2):**
- 「モデル選択 state を gui/state/ へ hoist」→ Task 1 (manager 新設) + Task 2 (Annotate 購読 view 化)。✓
- 「canonical = 選択モデル集合」→ Task 1 の SSoT セマンティクス。✓
- 「Annotate はこれを購読する唯一の view」→ Task 2 双方向同期。✓
- 「Jobs は購読しない (監視のみ)」→ 本 Phase は Jobs を一切触らない (Phase 3 で picker 撤去)。✓
- batch-capable フィルタ / 射影 / Jobs submit 撤去 → **Phase 2-3 へ繰り延べ** (ロードマップ記載)。Phase 1 のスコープ外。✓

**Placeholder scan:** 全 step に実コード/実コマンド記載済み。fixture 名は「現行を grep で確認」と明示 (既存テスト構造に依存するため)。

**Type consistency:** `get_selected`/`set_selected`/`set_model_selected`/`selection_changed(list)` を Task 1 で定義し Task 2 で同名使用。`ModelSelectionWidget.model_selection_changed(list)` / `set_selected_models(list[str])` / `get_selected_models()` は既存 API (確認済み, 行 104/771/704)。✓
