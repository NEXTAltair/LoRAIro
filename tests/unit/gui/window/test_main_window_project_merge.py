"""MainWindow のメニュー「プロジェクトを統合…」の配線テスト (Issue #1660)。"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar
from unittest.mock import Mock, patch

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMenu

from lorairo.gui.widgets import project_merge_dialog
from lorairo.gui.window import main_window as main_window_module
from lorairo.gui.window.main_window import MainWindow

pytestmark = [pytest.mark.unit, pytest.mark.gui]


class _FakeDialog:
    """ダイアログの代わり。exec で統合先を確定したことにする。"""

    instances: ClassVar[list[_FakeDialog]] = []
    merged_root: ClassVar[Path | None] = None

    def __init__(
        self, project_service: object, *, current_project_root: Path | None, parent: object
    ) -> None:
        self.project_service = project_service
        self.current_project_root = current_project_root
        self.merged_target_root: Path | None = None
        self.executed = False
        _FakeDialog.instances.append(self)

    def exec(self) -> int:
        self.executed = True
        self.merged_target_root = _FakeDialog.merged_root
        return 1

    def deleteLater(self) -> None:
        pass


@pytest.fixture
def window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mock:
    _FakeDialog.instances = []
    _FakeDialog.merged_root = None
    monkeypatch.setattr(project_merge_dialog, "ProjectMergeDialog", _FakeDialog)
    monkeypatch.setattr(main_window_module, "get_current_project_root", lambda: tmp_path / "current")
    refresh = Mock()
    monkeypatch.setattr(MainWindow, "_refresh_active_tab", refresh)
    fake = Mock()
    fake.refresh = refresh
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


def test_merge_into_current_project_refreshes_view(
    window: Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(MainWindow, "_project_switch_block_reason", lambda self: None)
    _FakeDialog.merged_root = (tmp_path / "current").resolve()

    MainWindow._open_project_merge_dialog(window)

    (dialog,) = _FakeDialog.instances
    assert dialog.executed
    assert dialog.current_project_root == (tmp_path / "current").resolve()
    window.refresh.assert_called_once_with(window)


def test_merge_into_other_project_does_not_refresh(
    window: Mock, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(MainWindow, "_project_switch_block_reason", lambda self: None)
    _FakeDialog.merged_root = (tmp_path / "other").resolve()

    MainWindow._open_project_merge_dialog(window)

    assert len(_FakeDialog.instances) == 1
    window.refresh.assert_not_called()
