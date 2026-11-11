"""DatasetSelectDialog のユニットテスト。"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog

from lorairo.gui.widgets.dataset_select_dialog import DatasetSelectDialog
from lorairo.services.dataset_import_service import FolderOverride


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
    # JSON を外しても Kohya 取り込みのまま (チェックボックスで切り替える。#1453)
    assert selection.config_files == ()
    assert selection.is_kohya_import


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


# --- Kohya 取り込み (Issue #1452 / #1453) ---


def _make_kohya_tree(root: Path) -> None:
    from PIL import Image as PILImage

    for relative in ("10_a/1.png", "10_a/2.png", "10_a/3.png", "5_b/1.png", "img_extra/x.png"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        PILImage.new("RGB", (8, 8)).save(path)
    (root / "10_a" / "1.txt").write_text("trig_a, smile", encoding="utf-8")
    (root / "10_a" / "2.txt").write_text("trig_a, red hair", encoding="utf-8")


def _kohya_dialog(dialog, root: Path) -> DatasetSelectDialog:
    dialog.directory_edit.setText(str(root))
    dialog.kohya_check.setChecked(True)
    assert dialog.wait_for_scan()
    return dialog


def test_kohya_checkbox_without_json_is_kohya_import(dialog, tmp_path):
    """設定 JSON なしでも、チェックボックスで Kohya 取り込みにできる (#1453)。"""
    _make_kohya_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)
    assert dialog.dataset_name_edit.isEnabled()
    assert _ok_enabled(dialog)
    selection = dialog.selection()
    assert selection is not None
    assert selection.is_kohya_import
    assert selection.config_files == ()
    assert selection.dataset_name == tmp_path.name
    assert selection.folder_tags == {}


def test_unchecking_kohya_returns_to_plain_registration_and_drops_json(dialog, tmp_path):
    dialog.directory_edit.setText(str(tmp_path))
    dialog.add_config_file(Path("/cfg/a.json"))
    assert dialog.kohya_check.isChecked()
    dialog.kohya_check.setChecked(False)
    selection = dialog.selection()
    assert selection is not None
    assert not selection.is_kohya_import
    assert selection.config_files == ()
    assert selection.folder_overrides is None
    assert not dialog.config_list.isEnabled()


def test_kohya_table_lists_folders_with_scan_info_and_empty_trigger(dialog, tmp_path):
    _make_kohya_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)

    table = dialog.kohya_table
    assert table.rowCount() == 2  # img_extra は <数字>_<名前> でないので出さない
    row = dialog.kohya_row("10_a")
    assert row is not None
    assert table.item(row, 3).text() == "3"  # 画像数
    assert table.item(row, 4).text() == "1"  # 学習テキストの無い画像数
    assert table.item(row, 6).text() == "trig_a (67%)"  # 候補は表示だけ
    assert table.item(row, 5).text() == ""  # 入力欄は空のまま
    assert "学習テキストの無い画像 2 枚" in dialog.kohya_summary_label.text()

    selection = dialog.selection()
    assert selection.folder_overrides == (
        FolderOverride("10_a", include=True, num_repeats=10, trigger_word=None),
        FolderOverride("5_b", include=True, num_repeats=5, trigger_word=None),
    )


def test_adopt_button_fills_trigger_and_edits_are_collected(dialog, tmp_path):
    from PySide6.QtCore import Qt

    _make_kohya_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)
    table = dialog.kohya_table
    row_a = dialog.kohya_row("10_a")
    row_b = dialog.kohya_row("5_b")

    table.cellWidget(row_a, 7).click()  # 採用
    table.cellWidget(row_a, 2).setValue(3)
    table.item(row_b, 0).setCheckState(Qt.CheckState.Unchecked)
    # 候補の無いフォルダの採用ボタンは押せない
    assert not table.cellWidget(row_b, 7).isEnabled()

    assert table.item(row_a, 5).text() == "trig_a"
    selection = dialog.selection()
    assert selection.folder_overrides == (
        FolderOverride("10_a", include=True, num_repeats=3, trigger_word="trig_a"),
        FolderOverride("5_b", include=False, num_repeats=5, trigger_word=None),
    )


def test_ok_disabled_when_no_kohya_folder_is_included(dialog, tmp_path):
    from PySide6.QtCore import Qt

    _make_kohya_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)
    for row in range(dialog.kohya_table.rowCount()):
        dialog.kohya_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
    assert not _ok_enabled(dialog)
    assert "0 / 2" in dialog.kohya_summary_label.text()


def test_ok_disabled_when_directory_has_no_kohya_folder(dialog, tmp_path):
    _make_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)
    assert dialog.kohya_table.rowCount() == 0
    assert not _ok_enabled(dialog)
    assert "フォルダがありません" in dialog.kohya_summary_label.text()


def test_kohya_rescan_same_directory_keeps_edits(dialog, tmp_path):
    _make_kohya_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)
    row = dialog.kohya_row("5_b")
    dialog.kohya_table.item(row, 5).setText("kept")
    dialog.refresh_subfolders()
    assert dialog.kohya_table.item(dialog.kohya_row("5_b"), 5).text() == "kept"


def test_kohya_overrides_dropped_when_directory_changed_without_rescan(dialog, tmp_path):
    _make_kohya_tree(tmp_path)
    _kohya_dialog(dialog, tmp_path)
    dialog.directory_edit.setText(str(tmp_path / "10_a"))
    selection = dialog.selection()
    assert selection.is_kohya_import
    assert selection.folder_overrides is None


# --- 親の版の選択 & 非同期フォルダスキャン (Issue #1478) ---


def test_parent_version_defaults_to_none_and_updates_by_dataset_name(qtbot, tmp_path):
    """外から渡したデータセット別の版一覧から親の版を選べ、データセット名変更で切り替わる (#1478)。"""
    _make_kohya_tree(tmp_path)
    dlg = DatasetSelectDialog(
        parent_versions_by_dataset={
            tmp_path.name: [(11, "v01"), (12, "v02")],
            "other_ds": [(21, "v10")],
        }
    )
    qtbot.addWidget(dlg)

    assert not dlg.parent_version_combo.isEnabled()
    assert dlg.selected_parent_version_id() is None

    _kohya_dialog(dlg, tmp_path)
    assert dlg.parent_version_combo.isEnabled()
    items = [dlg.parent_version_combo.itemText(i) for i in range(dlg.parent_version_combo.count())]
    assert items == ["なし (親の版を指定しない)", "v01 (#11)", "v02 (#12)"]
    assert dlg.selected_parent_version_id() is None
    assert dlg.selection().parent_version_id is None

    assert dlg.set_selected_parent_version_id(12)
    assert dlg.selected_parent_version_id() == 12
    assert dlg.selection().parent_version_id == 12

    # 別データセット名に変えると候補が切り替わり、選択は「なし」に戻る
    dlg.dataset_name_edit.setText("other_ds")
    other_items = [dlg.parent_version_combo.itemText(i) for i in range(dlg.parent_version_combo.count())]
    assert other_items == ["なし (親の版を指定しない)", "v10 (#21)"]
    assert dlg.selected_parent_version_id() is None

    # 未知のデータセット名では「なし」のみ
    dlg.dataset_name_edit.setText("brand_new")
    new_items = [dlg.parent_version_combo.itemText(i) for i in range(dlg.parent_version_combo.count())]
    assert new_items == ["なし (親の版を指定しない)"]
    assert dlg.selected_parent_version_id() is None


def test_parent_version_provider_and_set_available_parent_versions(qtbot, tmp_path):
    """provider や後から set_available_parent_versions で渡した候補も反映される (#1478)。"""
    _make_kohya_tree(tmp_path)
    dlg = DatasetSelectDialog(
        parent_versions_provider=lambda name: [(31, f"{name}_v1")] if name == "custom" else []
    )
    qtbot.addWidget(dlg)
    _kohya_dialog(dlg, tmp_path)
    dlg.dataset_name_edit.setText("custom")
    assert dlg.parent_version_combo.count() == 2
    dlg.parent_version_combo.setCurrentIndex(1)
    assert dlg.selected_parent_version_id() == 31
    assert dlg.selection().parent_version_id == 31

    # 通常の画像登録に戻すと選択結果に parent_version_id は載らない
    dlg.kohya_check.setChecked(False)
    assert dlg.selection().parent_version_id is None


def test_async_scan_in_flight_shows_status_and_disables_ok(qtbot, tmp_path):
    """非同期スキャン進行中はステータスメッセージを表示し OK ボタンを無効化する (#1478)。"""
    import threading

    from lorairo.services.dataset_import_service import FolderScanSummary

    _make_kohya_tree(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def slow_scanner(_directory: Path):
        started.set()
        release.wait(timeout=5.0)
        return [
            (
                "10_a",
                10,
                FolderScanSummary(
                    image_count=3,
                    images_without_text=1,
                    trigger_candidate="trig_a",
                    trigger_match_rate=2 / 3,
                ),
            ),
            (
                "5_b",
                5,
                FolderScanSummary(
                    image_count=1,
                    images_without_text=1,
                    trigger_candidate=None,
                    trigger_match_rate=0.0,
                ),
            ),
        ]

    dlg = DatasetSelectDialog(folder_scanner=slow_scanner)
    qtbot.addWidget(dlg)
    dlg.directory_edit.setText(str(tmp_path))
    dlg.kohya_check.setChecked(True)

    assert started.wait(timeout=5.0)
    # スキャン中は進行中表示が出ており、OK ボタンは無効
    assert dlg.is_scanning_kohya
    assert "スキャン中" in dlg.kohya_summary_label.text()
    assert not _ok_enabled(dlg)

    release.set()
    qtbot.waitUntil(lambda: not dlg.is_scanning_kohya, timeout=5000)

    assert dlg.kohya_table.rowCount() == 2
    assert _ok_enabled(dlg)


def test_stale_scan_result_discarded_when_root_changes_mid_scan(qtbot, tmp_path):
    """スキャン中にルートを変えた場合、世代を進め古いスキャン結果を破棄して最新だけ反映する (#1478)。"""
    import threading

    from lorairo.services.dataset_import_service import FolderScanSummary

    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    root_b.mkdir()

    started_a = threading.Event()
    release_a = threading.Event()
    finished_a = threading.Event()

    def scanner(directory: Path):
        if directory == root_a:
            started_a.set()
            release_a.wait(timeout=5.0)
            finished_a.set()
            return [
                (
                    "10_only_a",
                    10,
                    FolderScanSummary(
                        image_count=2,
                        images_without_text=0,
                        trigger_candidate="a_word",
                        trigger_match_rate=1.0,
                    ),
                )
            ]
        return [
            (
                "7_only_b",
                7,
                FolderScanSummary(
                    image_count=4,
                    images_without_text=0,
                    trigger_candidate="b_word",
                    trigger_match_rate=1.0,
                ),
            )
        ]

    dlg = DatasetSelectDialog(folder_scanner=scanner)
    qtbot.addWidget(dlg)
    dlg.directory_edit.setText(str(root_a))
    dlg.kohya_check.setChecked(True)
    assert started_a.wait(timeout=5.0)
    gen_a = dlg._scan_generation

    # スキャン中にルートを root_b へ変更して再スキャン開始
    dlg.directory_edit.setText(str(root_b))
    dlg.refresh_kohya_folders()
    assert dlg._scan_generation > gen_a

    # root_b のスキャンが先に完了するのを待つ
    qtbot.waitUntil(lambda: not dlg.is_scanning_kohya, timeout=5000)
    assert dlg.kohya_row("7_only_b") == 0
    assert dlg.kohya_row("10_only_a") is None

    # 遅れて完了した root_a (旧世代) の結果が届いても破棄され、root_b の表示が保たれる
    release_a.set()
    assert finished_a.wait(timeout=5.0)
    qtbot.waitUntil(lambda: gen_a not in dlg._scan_runners, timeout=5000)

    assert dlg.kohya_table.rowCount() == 1
    assert dlg.kohya_row("7_only_b") == 0
    assert dlg.kohya_row("10_only_a") is None
    assert dlg.selection().folder_overrides == (
        FolderOverride("7_only_b", include=True, num_repeats=7, trigger_word=None),
    )


def test_reject_stops_in_flight_scan_worker_cleanly(qtbot, tmp_path):
    """スキャン中にダイアログを閉じても worker スレッドを安全に停止し参照を解放する (#1478)。"""
    import threading

    started = threading.Event()
    release = threading.Event()

    def blocking_scanner(_directory: Path):
        started.set()
        release.wait(timeout=1.0)
        return []

    dlg = DatasetSelectDialog(folder_scanner=blocking_scanner)
    qtbot.addWidget(dlg)
    dlg.directory_edit.setText(str(tmp_path))
    dlg.kohya_check.setChecked(True)
    assert started.wait(timeout=5.0)

    release.set()
    dlg.reject()

    assert not dlg.is_scanning_kohya
    assert dlg._scan_runners == {}


def test_dialog_buttons_have_tooltips(qtbot):
    """Issue #1571: 参照・追加・削除ボタンにツールチップが設定されている。"""
    dlg = DatasetSelectDialog()
    qtbot.addWidget(dlg)
    assert dlg.browse_button.toolTip() != ""
    assert dlg.add_config_button.toolTip() != ""
    assert dlg.remove_config_button.toolTip() != ""
