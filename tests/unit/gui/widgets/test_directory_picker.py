"""DirectoryPickerWidget 単体テスト

QFileDialog は conftest.py の auto_mock_qfiledialog により自動モック済み
（getExistingDirectory は空文字列を返す）。
"""

from pathlib import Path

import pytest

from lorairo.gui.widgets.directory_picker import DirectoryPickerWidget


@pytest.fixture
def widget(qtbot):
    w = DirectoryPickerWidget()
    qtbot.addWidget(w)
    return w


class TestDirectoryPickerWidgetInit:
    def test_initialization(self, widget):
        assert widget is not None

    def test_has_valid_directory_selected_signal(self, widget):
        assert hasattr(widget, "validDirectorySelected")

    def test_initial_path_is_empty(self, widget):
        assert widget.get_selected_path() == ""


class TestDirectoryPickerWidgetSelectFolder:
    def test_select_folder_with_empty_return_does_not_crash(self, widget):
        """QFileDialogが空文字を返す場合、シグナルを発信しない"""
        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.select_folder()
        assert received == []

    def test_select_folder_with_valid_path_emits_signal(self, widget, qtbot, monkeypatch, tmp_path):
        """有効なパスが選択された場合、validDirectorySelectedシグナルを発信する"""
        # tmp_path に画像ファイルを作成して有効なディレクトリにする
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"")

        monkeypatch.setattr(
            "lorairo.gui.widgets.directory_picker.QFileDialog.getExistingDirectory",
            lambda *a, **kw: str(tmp_path),
        )

        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.select_folder()
        assert received == [str(tmp_path)]


class TestDirectoryPickerWidgetSetPath:
    def test_set_path_updates_text(self, widget, tmp_path):
        widget.set_path(str(tmp_path))
        assert widget.get_selected_path() == str(tmp_path)

    def test_set_label_text(self, widget):
        widget.set_label_text("テストラベル")


class TestDirectoryPickerWidgetValidation:
    def test_validate_and_emit_with_empty_path_does_not_crash(self, widget):
        widget.set_path("")
        widget._validate_and_emit()

    def test_validate_and_emit_with_nonexistent_path_does_not_emit(self, widget):
        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.set_path("/nonexistent/path/to/directory")
        widget._validate_and_emit()
        assert received == []

    def test_validate_and_emit_with_valid_image_dir_emits_signal(self, widget, qtbot, tmp_path):
        """画像ファイルがある有効ディレクトリでシグナルが発信される"""
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"")

        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.set_path(str(tmp_path))
        widget._validate_and_emit()
        assert received == [str(tmp_path)]

    def test_validate_and_emit_with_empty_dir_does_not_emit(self, widget, tmp_path):
        """画像ファイルがないディレクトリではシグナルを発信しない"""
        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.set_path(str(tmp_path))
        widget._validate_and_emit()
        assert received == []
