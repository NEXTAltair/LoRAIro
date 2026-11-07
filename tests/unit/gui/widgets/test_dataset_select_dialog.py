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


# --- サブフォルダ共通タグ (Issue #1409) ---


def _make_tree(root: Path) -> None:
    from PIL import Image as PILImage

    for relative in ("root.png", "chara_a/1.png", "chara_a/2.jpg", "style/b/3.webp", "style/notes.txt"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".txt":
            path.write_text("x")
        else:
            PILImage.new("RGB", (8, 8)).save(path)


def test_refresh_subfolders_lists_folders_with_direct_images(dialog, tmp_path):
    _make_tree(tmp_path)
    dialog.directory_edit.setText(str(tmp_path))
    dialog.refresh_subfolders()
    rows = [
        (dialog.folder_table.item(r, 0).text(), dialog.folder_table.item(r, 1).text())
        for r in range(dialog.folder_table.rowCount())
    ]
    # 直下画像のない "style" と選択ディレクトリ直下は行にしない
    assert rows == [("chara_a", "2"), ("style/b", "1")]
    assert dialog.folder_table.isEnabled()


def test_folder_tags_are_parsed_verbatim_into_selection(dialog, tmp_path):
    _make_tree(tmp_path)
    dialog.directory_edit.setText(str(tmp_path))
    dialog.refresh_subfolders()
    assert dialog.set_folder_tags_text(Path("chara_a"), " Chara A , blue_sky,, Chara A ")
    assert not dialog.set_folder_tags_text(Path("missing"), "x")
    selection = dialog.selection()
    assert selection is not None
    # 空欄のフォルダは含めない。表記は書き換えず、重複だけ除く
    assert selection.folder_tags == {Path("chara_a"): ("Chara A", "blue_sky")}


def test_refresh_same_directory_keeps_entered_tags(dialog, tmp_path):
    _make_tree(tmp_path)
    dialog.directory_edit.setText(str(tmp_path))
    dialog.refresh_subfolders()
    dialog.set_folder_tags_text(Path("chara_a"), "kept")
    dialog.refresh_subfolders()
    assert dialog.selection().folder_tags == {Path("chara_a"): ("kept",)}


def test_folder_tags_dropped_when_directory_changed_without_rescan(dialog, tmp_path):
    _make_tree(tmp_path)
    dialog.directory_edit.setText(str(tmp_path))
    dialog.refresh_subfolders()
    dialog.set_folder_tags_text(Path("chara_a"), "tag")
    dialog.directory_edit.setText(str(tmp_path / "chara_a"))
    assert dialog.selection().folder_tags == {}


def test_folder_tags_disabled_and_ignored_for_kohya_import(dialog, tmp_path):
    _make_tree(tmp_path)
    dialog.directory_edit.setText(str(tmp_path))
    dialog.refresh_subfolders()
    dialog.set_folder_tags_text(Path("chara_a"), "tag")
    dialog.add_config_file(Path("/cfg/a.json"))
    assert not dialog.folder_table.isEnabled()
    assert dialog.selection().folder_tags == {}


def test_browse_scans_picked_directory(dialog, tmp_path, monkeypatch):
    _make_tree(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(tmp_path))
    dialog.browse_button.click()
    assert dialog.folder_table.rowCount() == 2


def test_nonexistent_directory_has_no_subfolder_rows(dialog):
    dialog.directory_edit.setText("/nonexistent/path/for/test")
    dialog.refresh_subfolders()
    assert dialog.folder_table.rowCount() == 0
    assert dialog.selection().folder_tags == {}
