"""MainWindow のメニュー「プロジェクトを統合…」の配線テスト (Issue #1660)。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar
from unittest.mock import Mock, call, patch

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu

from lorairo.gui.widgets import project_merge_dialog
from lorairo.gui.widgets.project_merge_dialog import ProjectMergeOutcome
from lorairo.gui.window import main_window as main_window_module
from lorairo.gui.window.main_window import MainWindow

pytestmark = [pytest.mark.unit, pytest.mark.gui]


class _FakeSignal:
    """`merge_succeeded` の代わり。connect した slot を emit で呼ぶ。"""

    def __init__(self) -> None:
        self.slots: list[Callable[[object], None]] = []

    def connect(self, slot: Callable[[object], None]) -> None:
        self.slots.append(slot)

    def emit(self, payload: object) -> None:
        for slot in self.slots:
            slot(payload)


class _FakeDialog:
    """ダイアログの代わり。exec の間に、指定した統合の成功を順に通知する。"""

    instances: ClassVar[list[_FakeDialog]] = []
    merges: ClassVar[list[ProjectMergeOutcome]] = []

    def __init__(
        self, project_service: object, *, current_project_root: Path | None, parent: object
    ) -> None:
        self.project_service = project_service
        self.current_project_root = current_project_root
        self.merge_succeeded = _FakeSignal()
        self.executed = False
        _FakeDialog.instances.append(self)

    def exec(self) -> int:
        self.executed = True
        for outcome in _FakeDialog.merges:
            self.merge_succeeded.emit(outcome)
        return 1

    def deleteLater(self) -> None:
        pass


@pytest.fixture
def window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mock:
    _FakeDialog.instances = []
    _FakeDialog.merges = []
    monkeypatch.setattr(project_merge_dialog, "ProjectMergeDialog", _FakeDialog)
    monkeypatch.setattr(main_window_module, "get_current_project_root", lambda: tmp_path / "current")
    refresh = Mock()
    monkeypatch.setattr(MainWindow, "_refresh_active_tab", refresh)
    fake = Mock()
    fake.refresh = refresh
    # Mock の window から MainWindow の slot を呼べるよう、実物の slot を割り当てる
    fake._on_project_merge_succeeded = lambda outcome: MainWindow._on_project_merge_succeeded(fake, outcome)
    return fake


def test_file_menu_has_merge_projects_action(qapp: object) -> None:
    with patch.object(MainWindow, "__init__", QMainWindow.__init__):
        window = MainWindow()
    window.menuFile = QMenu("ファイル", window)
    window.actionExit = QAction("終了", window)
    window.menuFile.addAction(window.actionExit)

    MainWindow._populate_file_menu(window)

    names = [a.objectName() for a in window.menuFile.actions() if not a.isSeparator()]
    assert "actionMergeProjects" in names
    assert window.actionMergeProjects.text() == "プロジェクトを統合…"


def test_merge_is_refused_while_jobs_are_running(window: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(
        MainWindow, "_project_switch_block_reason", lambda self: "実行中のジョブが 1 件あります。"
    )
    monkeypatch.setattr(main_window_module, "show_warning", lambda _p, title, _t: warnings.append(title))

    MainWindow._open_project_merge_dialog(window)

    assert warnings == ["プロジェクトを統合できません"]
    assert _FakeDialog.instances == []


def test_each_merge_into_current_project_refreshes_view(
    window: Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ダイアログを開いたまま 2 回続けて現在のプロジェクトへ統合したら、2 回とも読み直す。"""
    monkeypatch.setattr(MainWindow, "_project_switch_block_reason", lambda self: None)
    current = (tmp_path / "current").resolve()
    _FakeDialog.merges = [ProjectMergeOutcome(current, (3, 5)), ProjectMergeOutcome(current, (8,))]

    MainWindow._open_project_merge_dialog(window)

    (dialog,) = _FakeDialog.instances
    assert dialog.executed
    assert dialog.current_project_root == current
    # 検索タブは選択中の画像の由来・データセット利用状況まで読み直す
    assert window.search_tab.refresh_after_project_merge.call_args_list == [call([3, 5]), call([8])]
    assert window.refresh.call_count == 2


def test_merge_into_current_then_other_project_refreshes_first_merge(
    window: Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """現在のプロジェクト → 別のプロジェクトの順に統合したら、1 回目の統合の分を読み直す。"""
    monkeypatch.setattr(MainWindow, "_project_switch_block_reason", lambda self: None)
    _FakeDialog.merges = [
        ProjectMergeOutcome((tmp_path / "current").resolve(), (3, 5)),
        ProjectMergeOutcome((tmp_path / "other").resolve(), (9,)),
    ]

    MainWindow._open_project_merge_dialog(window)

    assert window.search_tab.refresh_after_project_merge.call_args_list == [call([3, 5])]
    window.refresh.assert_called_once_with(window)


def test_merge_into_other_project_does_not_refresh(
    window: Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(MainWindow, "_project_switch_block_reason", lambda self: None)
    _FakeDialog.merges = [ProjectMergeOutcome((tmp_path / "other").resolve(), (9,))]

    MainWindow._open_project_merge_dialog(window)

    assert len(_FakeDialog.instances) == 1
    window.refresh.assert_not_called()
    window.search_tab.refresh_after_project_merge.assert_not_called()
