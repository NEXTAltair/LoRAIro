"""DirectoryPickerWidget 単体テスト

QFileDialog は conftest.py の auto_mock_qfiledialog により自動モック済み
（getExistingDirectory は空文字列を返す）。
"""

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

    def test_validate_and_emit_dedupes_return_pressed_and_editing_finished(
        self, widget, tmp_path, monkeypatch
    ):
        """returnPressed 直後の editingFinished で同一パスを二重検証・二重 emit しない (#1546)。"""
        (tmp_path / "test.jpg").write_bytes(b"")
        widget.set_path(str(tmp_path))

        validate_calls: list[str] = []
        orig_validate = widget._validate_dataset_directory

        def spy_validate(path: str) -> bool:
            validate_calls.append(path)
            return orig_validate(path)

        monkeypatch.setattr(widget, "_validate_dataset_directory", spy_validate)
        received: list[str] = []
        widget.validDirectorySelected.connect(received.append)

        widget.DirectoryPicker.lineEditPicker.returnPressed.emit()
        widget.DirectoryPicker.lineEditPicker.editingFinished.emit()

        assert validate_calls == [str(tmp_path)]
        assert received == [str(tmp_path)]

    def test_validate_dataset_directory_prunes_beyond_max_depth(self, widget, tmp_path):
        """os.walk の枝刈りにより max_depth (3階層) より深いファイルは走査しない (#1546)。"""
        deep_dir = tmp_path / "d1" / "d2" / "d3"
        deep_dir.mkdir(parents=True)
        # 深さ 4 (d1/d2/d3/deep.jpg) のみに画像がある場合は検出されない
        (deep_dir / "deep.jpg").write_bytes(b"")
        assert widget._validate_dataset_directory(str(tmp_path)) is False

        # 深さ 3 (d1/d2/ok.jpg) に画像があれば有効と判定される
        (tmp_path / "d1" / "d2" / "ok.jpg").write_bytes(b"")
        assert widget._validate_dataset_directory(str(tmp_path)) is True

    def test_set_require_images_false_allows_empty_directory(self, widget, tmp_path):
        """Issue #1566: set_require_images(False) 時は画像が無い有効ディレクトリでも発信する"""
        widget.set_require_images(False)
        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.set_path(str(tmp_path))
        widget._validate_and_emit()
        assert received == [str(tmp_path)]

    def test_set_require_images_false_rejects_nonexistent_directory(self, widget):
        """Issue #1566: set_require_images(False) でも存在しないパスは発信しない"""
        widget.set_require_images(False)
        received = []
        widget.validDirectorySelected.connect(lambda p: received.append(p))
        widget.set_path("/nonexistent/path/to/directory")
        widget._validate_and_emit()
        assert received == []
