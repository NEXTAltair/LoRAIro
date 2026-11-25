# ModelSelectionStateManager Hoist 実装計画(#884 Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** モデル選択(選択 `litellm_model_id` 集合)の信頼源(SSoT)を `ModelSelectionWidget` のチェックボックス状態から `gui/state/` の QObject 状態マネージャへ引き上げ(hoist)、Annotate タブを購読ビューへ降格する。

**Architecture:** ADR 0074 の `StagingStateManager` の前例に倣い、`gui/state/model_selection_state.py` に `ModelSelectionStateManager(QObject)` を新設する。`MainWindow` がこれを所有・DI し、`AnnotateTabWidget` 内で `ModelSelectionWidget`(ビュー)とマネージャ(SSoT)をループガード付きで双方向同期する。本 Phase は振る舞いを変えないリファクタリングであり、後続 Phase(dispatch 射影および Jobs submit 撤去)の土台を作る。

**Tech Stack:** PySide6(QtCore QObject / Signal)、pytest-qt、Loguru

## 全体制約

- ADR 0076 を本 Phase の信頼源(SSoT)とする。SSoT は選択モデル集合(ADR 0075)であり、その所在を `gui/state/` へ移す改定である(#884 hoist)。
- 型ヒントを必須とし、モダンな Python 構文(`list[str]`、`X | None`)、Google スタイルの docstring、日本語の実装コメントを用いる(`.claude/rules/coding-style.md`)。
- 最大行長は 108 文字とし、Ruff フォーマットを適用する。`# type: ignore` および `# noqa` は禁止する。
- INFO ログはバッチサマリーのみとし、個別項目は DEBUG または TRACE とする(`.claude/rules/logging.md`)。粒度は `StagingStateManager` に揃える。
- 実装作業はワークツリーから開始する(`.claude/rules/git-workflow.md`)。ブランチ名は `refactor/issue-884-model-selection-state` とする。
- 検証には CI 相当フィルタ `uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` を用いる(`.claude/rules/testing.md`)。タブ抽出系の回帰確認には `tests/unit/gui/window/test_main_window_coverage.py` も含める([[feedback_tab_extraction_check_window_coverage]])。
- Qt 非依存は QObject の排除を意味しない。状態マネージャは QObject を維持するのが正解である([[feedback_qt_free_not_qobject_exclusion]])。

---

## Epic ロードマップ(ADR 0076 全体)

本計画の対象は **Phase 1 のみ**である。後続は別計画(別 PR)として起票する。

- **Phase 1(本計画):** `ModelSelectionStateManager` の引き上げと Annotate の購読ビュー化。振る舞い不変の土台を作る。
- **Phase 2:** Annotate に dispatch mode(同期/非同期 Batch API)を追加し、Qt 非依存の dispatch 射影サービスを実装する(`provider_batch_capability` と `list_batch_capable_models` を再利用、ワーカースレッド、ADR 0044)。
- **Phase 3:** Jobs(`provider_batch_job_widget.py`)の submit パネル(ピッカー、ステージング、`rating_preflight` コンボ)を丸ごと撤去し、Jobs を純粋な監視台帳にする。
- **Phase 4:** wireframe v12 を反映する(Annotate の route バッジ、async batch レーン、Jobs の監視専用化)。

Phase 1 単体で「選択状態が 1 箇所に集約される」ことを達成し、ユニットテスト可能にする。ユーザー可視のバグ解消(Annotate と Jobs 間の反映)は Phase 3 まで保留する(ADR 0076 の方針により、Jobs は購読せずピッカー撤去で解消する)。

---

## ファイル構成

- `src/lorairo/gui/state/model_selection_state.py`(新規): `ModelSelectionStateManager(QObject)`。選択 `litellm_model_id` 集合の SSoT。
- `src/lorairo/gui/window/main_window.py`(改修): マネージャの生成・所有、および `AnnotateTab` への DI。
- `src/lorairo/gui/tab/annotate_tab.py`(改修): マネージャを DI で受け取り、`ModelSelectionWidget` と双方向同期する。`selected_litellm_model_ids()` をマネージャ起点へ変更する。
- `tests/unit/gui/state/test_model_selection_state.py`(新規): マネージャのユニットテスト。
- `tests/unit/gui/tab/test_annotate_tab.py`(改修): DI 引数の追加と同期検証。
- `tests/unit/gui/window/test_main_window_coverage.py`(改修): マネージャ初期化と DI 委譲のカバレッジ追加。

---

### Task 1: `ModelSelectionStateManager`(`gui/state/` の QObject SSoT)

**Files:**
- Create: `src/lorairo/gui/state/model_selection_state.py`
- Test: `tests/unit/gui/state/test_model_selection_state.py`

**Interfaces:**
- 依存(Consumes): なし(PySide6 の QtCore のみ)。
- 提供(Produces):
  - `class ModelSelectionStateManager(QObject)`
  - シグナル `selection_changed = Signal(list)`(現在の選択 `list[str]` を載せる)
  - `get_selected() -> list[str]`(選択順を保持する)
  - `set_selected(litellm_model_ids: list[str]) -> None`(集合を置換し、変化時のみ発行する)
  - `set_model_selected(litellm_model_id: str, selected: bool) -> None`(1 件を ON/OFF し、変化時のみ発行する)
  - `clear() -> None`(空にし、元が非空のときのみ発行する)
  - `count() -> int`
  - `is_selected(litellm_model_id: str) -> bool`

- [ ] **Step 1: 失敗するテストを書く**

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

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/gui/state/test_model_selection_state.py -v`
期待結果: `ModuleNotFoundError: lorairo.gui.state.model_selection_state` で失敗する。

- [ ] **Step 3: 最小限の実装を書く**

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

- [ ] **Step 4: テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/gui/state/test_model_selection_state.py -v`
期待結果: 7 件すべて通る。

- [ ] **Step 5: フォーマットしてコミットする**

```bash
uv run ruff format src/lorairo/gui/state/model_selection_state.py tests/unit/gui/state/test_model_selection_state.py
uv run ruff check src/lorairo/gui/state/model_selection_state.py tests/unit/gui/state/test_model_selection_state.py --fix
git add src/lorairo/gui/state/model_selection_state.py tests/unit/gui/state/test_model_selection_state.py
git commit -m "feat(gui): 選択モデル集合の SSoT ModelSelectionStateManager を新設 (#884)"
```

---

### Task 2: Annotate タブの購読ビュー化と `MainWindow` 配線

**Files:**
- Modify: `src/lorairo/gui/window/main_window.py`(状態マネージャの生成と DI)
- Modify: `src/lorairo/gui/tab/annotate_tab.py`(DI 受け取りと双方向同期)
- Modify: `tests/unit/gui/tab/test_annotate_tab.py`(DI 引数の追加と同期検証)
- Modify: `tests/unit/gui/window/test_main_window_coverage.py`(初期化カバレッジ)

**Interfaces:**
- 依存(Consumes): Task 1 の `ModelSelectionStateManager`(`get_selected`、`set_selected`、`set_model_selected`、`selection_changed`)。
- 提供(Produces):
  - `AnnotateTabWidget.__init__` へのキーワード引数 `model_selection_state_manager: ModelSelectionStateManager | None` の追加(凍結契約の拡張)。
  - `MainWindow.model_selection_state_manager: ModelSelectionStateManager | None` 属性。

**設計メモ(ループガード):**
`ModelSelectionWidget.model_selection_changed(list)` からマネージャの `set_selected` へ、マネージャの `selection_changed` からウィジェットの `set_selected_models` へ双方向同期を行う。再帰を防ぐため、`self._syncing_model_selection` フラグでガードする。`set_selected_models` はシグナルを抑制するセッターだが、安全のためガードを通す。また、`selected_litellm_model_ids()` ゲッターはマネージャを SSoT として参照する。

- [ ] **Step 1: 失敗するテストを書く(`annotate_tab`)**

`tests/unit/gui/tab/test_annotate_tab.py` の `AnnotateTabWidget` 生成フィクスチャ(105 行目および 143 行目付近の 2 箇所)に `model_selection_state_manager=` 引数を追加し、同期テストを追記する。

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

新規フィクスチャを既存フィクスチャ群の近くに追加する(既存の生成パターンを流用し、`model_selection_state_manager` を渡す)。

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

> **注:** `mock_service_container` と `mock_db_manager` は、`test_annotate_tab.py` の現行フィクスチャを grep で確認して既存名に合わせる。`selected_litellm_model_ids()` がマネージャ起点で値を返すことを検証するため、チェックボックス未生成でもゲッターがマネージャを読む実装にする。

- [ ] **Step 2: テストを実行して失敗を確認する**

実行コマンド: `uv run pytest tests/unit/gui/tab/test_annotate_tab.py -v`
期待結果: `TypeError: unexpected keyword argument 'model_selection_state_manager'` で失敗する。

- [ ] **Step 3: `AnnotateTabWidget` の DI と双方向同期を実装する**

`annotate_tab.py` のインポートに以下を追加する。

```python
from ..state.model_selection_state import ModelSelectionStateManager
```

`__init__` シグネチャに引数を追加し、凍結契約の docstring も更新する。

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

`__init__` 本体(`self._dataset_state_manager = dataset_state_manager` の直後)に以下を追加する。

```python
        self._model_selection_state_manager = model_selection_state_manager
        # widget ↔ state manager 双方向同期の再帰ガード
        self._syncing_model_selection = False
```

`_build_pipeline_composition_panel` のシグナル配線部(`self._batch_model_selection.model_selection_changed.connect(self._on_pipeline_models_changed)` の直後)に状態同期の配線を追加する。

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

同期ハンドラを追加し、`selected_litellm_model_ids` の定義を以下へ置換する。

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

- [ ] **Step 4: `MainWindow` の配線を実装する**

`main_window.py` のインポート(39 行目の staging インポート付近)に以下を追加する。

```python
from ..state.model_selection_state import ModelSelectionStateManager
```

属性宣言(77 行目の `staging_state_manager` 宣言付近)に以下を追加する。

```python
    model_selection_state_manager: ModelSelectionStateManager | None
```

`_initialize_staging_state_manager()` 呼び出し(228 行目付近)の直後に初期化呼び出しを追加し、初期化メソッドを新設する。

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

`AnnotateTabWidget` の生成箇所(731 行目付近)に DI 引数を追加する。

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

> **注:** 731 行目の既存 `AnnotateTabWidget(` 呼び出しの実引数構成を事前に読み込んで確認し、`model_selection_state_manager=` を 1 行追加するだけにとどめる(他引数と `parent` は現状を維持する)。

- [ ] **Step 5: `annotate_tab` テストを実行して通ることを確認する**

実行コマンド: `uv run pytest tests/unit/gui/tab/test_annotate_tab.py -v`
期待結果: 既存テストおよび新規 2 件がすべて通る。

- [ ] **Step 6: `MainWindow` のカバレッジテストを追加する**

`tests/unit/gui/window/test_main_window_coverage.py` に以下を追記する(既存の `MainWindow` フィクスチャを流用する)。

```python
def test_model_selection_state_manager_initialized(main_window):
    """MainWindow が ModelSelectionStateManager を初期化し AnnotateTab へ DI する (#884)。"""
    from lorairo.gui.state.model_selection_state import ModelSelectionStateManager

    assert isinstance(main_window.model_selection_state_manager, ModelSelectionStateManager)
```

> **注:** `main_window` フィクスチャ名と生成方法は `test_main_window_coverage.py` の現行フィクスチャを grep で確認して流用する。DB 初期化を伴うフィクスチャであれば既存パターンに従う。

- [ ] **Step 7: カバレッジテストと CI 相当フィルタを実行する**

```bash
uv run pytest tests/unit/gui/window/test_main_window_coverage.py -v
uv run pytest -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"
```

期待結果: すべて通り、回帰がない。

- [ ] **Step 8: フォーマット、mypy、コミットを実行する**

```bash
uv run ruff format src/lorairo/gui/state/model_selection_state.py src/lorairo/gui/tab/annotate_tab.py src/lorairo/gui/window/main_window.py
uv run ruff check src/ tests/ --fix
uv run mypy -p lorairo
git add -A
git commit -m "refactor(gui): モデル選択 state を ModelSelectionStateManager へ hoist・Annotate を購読 view 化 (#884)"
```

---

## セルフレビュー

**仕様カバレッジ(ADR 0076 §3 / #884 step 2):**
- 「モデル選択 state を `gui/state/` へ hoist」: Task 1(マネージャ新設)と Task 2(Annotate の購読ビュー化)でカバーしている。✓
- 「canonical = 選択モデル集合」: Task 1 の SSoT セマンティクスでカバーしている。✓
- 「Annotate はこれを購読する唯一の view」: Task 2 の双方向同期でカバーしている。✓
- 「Jobs は購読しない(監視のみ)」: 本 Phase では Jobs を一切触らず、Phase 3 でピッカーを撤去する。✓
- batch-capable フィルタ、射影、Jobs submit 撤去: Phase 2–3 へ繰り延べた(ロードマップに記載済み、Phase 1 のスコープ外)。✓

**プレースホルダ確認:**
全ステップに実コードと実コマンドを記載済みである。フィクスチャ名は既存テスト構造に依存するため、「現行を grep で確認」と明示した。

**型整合性:**
`get_selected`、`set_selected`、`set_model_selected`、`selection_changed(list)` を Task 1 で定義し、Task 2 で同名使用している。`ModelSelectionWidget.model_selection_changed(list)`、`set_selected_models(list[str])`、`get_selected_models()` は既存 API であることを確認済みである(行 104 / 771 / 704)。✓
