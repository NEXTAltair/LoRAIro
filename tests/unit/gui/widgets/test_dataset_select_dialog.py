"""DatasetSelectDialog のユニットテスト。"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog

from lorairo.gui.widgets.dataset_select_dialog import DatasetSelectDialog


@pytest.fixture
def dialog(qtbot):
    dlg = DatasetSelectDialog()
    qtbot.addWidget(dlg)
    return dlg


def _ok_enabled(dlg: DatasetSelectDialog) -> bool:
    return dlg.button_box.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_empty_dialog_has_no_selection_and_ok_disabled(dialog):
    assert dialog.selection() is None
    assert not _ok_enabled(dialog)


def test_directory_only_is_plain_registration(dialog):
    dialog.directory_edit.setText("/data/images")
    selection = dialog.selection()
    assert selection is not None
    assert selection.directory == Path("/data/images")
    assert selection.config_files == ()
    assert not selection.is_kohya_import
    assert _ok_enabled(dialog)
    assert not dialog.dataset_name_edit.isEnabled()
    assert not dialog.version_name_edit.isEnabled()


def test_adding_json_enables_names_and_marks_kohya_import(dialog):
    dialog.directory_edit.setText("/data/my_set")
    dialog.add_config_file(Path("/cfg/a.json"))
    dialog.add_config_file(Path("/cfg/a.json"))  # 重複は無視
    dialog.add_config_file(Path("/cfg/b.json"))
    dialog.version_name_edit.setText("v1")
    assert dialog.dataset_name_edit.isEnabled()
    selection = dialog.selection()
    assert selection is not None
    assert selection.is_kohya_import
    assert selection.config_files == (Path("/cfg/a.json"), Path("/cfg/b.json"))
    assert selection.dataset_name == "my_set"
    assert selection.version_name == "v1"


def test_dataset_name_required_for_kohya_import(dialog):
    dialog.directory_edit.setText("/data/my_set")
    dialog.add_config_file(Path("/cfg/a.json"))
    dialog.dataset_name_edit.setText("")
    assert not _ok_enabled(dialog)


def test_remove_selected_config(dialog):
    dialog.directory_edit.setText("/data/x")
    dialog.add_config_file(Path("/cfg/a.json"))
    dialog.config_list.item(0).setSelected(True)
    dialog.remove_config_button.click()
    selection = dialog.selection()
    assert selection is not None
    assert not selection.is_kohya_import


def test_browse_buttons_use_file_dialogs(dialog, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: "/picked/dir")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (["/cfg/c.json"], ""))
    dialog.browse_button.click()
    dialog.add_config_button.click()
    selection = dialog.selection()
    assert selection is not None
    assert selection.directory == Path("/picked/dir")
    assert selection.config_files == (Path("/cfg/c.json"),)
