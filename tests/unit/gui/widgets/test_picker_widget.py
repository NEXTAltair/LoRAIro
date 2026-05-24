"""PickerWidget 単体テスト

QFileDialog は conftest.py の auto_mock_qfiledialog により自動モック済み。
"""

import pytest

from lorairo.gui.widgets.picker import PickerWidget


@pytest.mark.unit
class TestPickerWidgetInit:
    @pytest.fixture
    def widget(self, qtbot) -> PickerWidget:
        w = PickerWidget()
        qtbot.addWidget(w)
        return w

    def test_initialization(self, widget: PickerWidget) -> None:
        """初期状態の確認"""
        assert widget is not None
        assert widget.history == []

    def test_configure_sets_label_text(self, widget: PickerWidget) -> None:
        """configure() がラベルテキストを設定する（line 18-19）"""
        widget.configure(label_text="ファイルを選択")
        assert widget.labelPicker.text() == "ファイルを選択"

    def test_configure_default_label(self, widget: PickerWidget) -> None:
        """configure() のデフォルトラベルテキスト確認（line 18-19）"""
        widget.configure()
        assert widget.labelPicker.text() == "Select File"

    def test_set_label_text(self, widget: PickerWidget) -> None:
        """set_label_text() でラベルテキストが変わる"""
        widget.set_label_text("テスト")
        assert widget.labelPicker.text() == "テスト"

    def test_set_button_text(self, widget: PickerWidget) -> None:
        """set_button_text() でボタンテキストが変わる（line 25）"""
        widget.set_button_text("参照...")
        assert widget.pushButtonPicker.text() == "参照..."


@pytest.mark.unit
class TestPickerWidgetSelectFile:
    @pytest.fixture
    def widget(self, qtbot) -> PickerWidget:
        w = PickerWidget()
        qtbot.addWidget(w)
        return w

    def test_select_file_empty_return_does_not_add_history(self, widget: PickerWidget) -> None:
        """QFileDialog が空文字を返す場合は履歴に追加しない（line 28-33）"""
        # conftest.py の auto_mock_qfiledialog が ("", "") を返す
        widget.select_file()

        assert widget.history == []
        assert widget.lineEditPicker.text() == ""

    def test_select_file_valid_path_adds_to_history(self, widget: PickerWidget, monkeypatch) -> None:
        """有効なファイルパスが返ると lineEdit と history に追加される（line 31-33）"""
        monkeypatch.setattr(
            "lorairo.gui.widgets.picker.QFileDialog.getOpenFileName",
            lambda *a, **kw: ("/tmp/test.txt", "All Files (*)"),
        )

        widget.select_file()

        assert widget.lineEditPicker.text() == "/tmp/test.txt"
        assert "/tmp/test.txt" in widget.history


@pytest.mark.unit
class TestPickerWidgetSelectFolder:
    @pytest.fixture
    def widget(self, qtbot) -> PickerWidget:
        w = PickerWidget()
        qtbot.addWidget(w)
        return w

    def test_select_folder_empty_return_does_not_add_history(self, widget: PickerWidget) -> None:
        """QFileDialog が空文字を返す場合は履歴に追加しない（line 35-39）"""
        # conftest.py の auto_mock_qfiledialog が "" を返す
        widget.select_folder()

        assert widget.history == []

    def test_select_folder_valid_path_adds_to_history(self, widget: PickerWidget, monkeypatch) -> None:
        """有効なディレクトリパスが返ると lineEdit と history に追加される（line 37-39）"""
        monkeypatch.setattr(
            "lorairo.gui.widgets.picker.QFileDialog.getExistingDirectory",
            lambda *a, **kw: "/tmp/testdir",
        )

        widget.select_folder()

        assert widget.lineEditPicker.text() == "/tmp/testdir"
        assert "/tmp/testdir" in widget.history


@pytest.mark.unit
class TestPickerWidgetUpdateHistory:
    @pytest.fixture
    def widget(self, qtbot) -> PickerWidget:
        w = PickerWidget()
        qtbot.addWidget(w)
        return w

    def test_update_history_adds_new_path(self, widget: PickerWidget) -> None:
        """新しいパスが履歴に追加される"""
        widget.update_history("/tmp/dir1")

        assert "/tmp/dir1" in widget.history
        assert widget.lineEditPicker.text() == "/tmp/dir1"

    def test_update_history_does_not_duplicate(self, widget: PickerWidget) -> None:
        """同じパスを2回追加しても履歴は1件"""
        widget.update_history("/tmp/dir1")
        widget.update_history("/tmp/dir1")

        assert widget.history.count("/tmp/dir1") == 1

    def test_update_history_empty_string_ignored(self, widget: PickerWidget) -> None:
        """空文字列は無視される"""
        widget.update_history("")

        assert widget.history == []

    def test_update_history_overflow_truncates_oldest(self, widget: PickerWidget) -> None:
        """10件を超えると最古エントリが削除される（line 56-58）"""
        for i in range(11):
            widget.update_history(f"/tmp/dir{i}")

        # history は最大 10 件
        assert len(widget.history) == 10
        # dir0 が削除されているはず
        assert "/tmp/dir0" not in widget.history
        assert "/tmp/dir10" in widget.history


@pytest.mark.unit
class TestPickerWidgetHistorySelection:
    @pytest.fixture
    def widget(self, qtbot) -> PickerWidget:
        w = PickerWidget()
        qtbot.addWidget(w)
        return w

    def test_on_history_item_selected_updates_line_edit(self, widget: PickerWidget) -> None:
        """履歴から選択すると lineEdit が更新される（line 60-64）"""
        widget.update_history("/tmp/selected_dir")

        # comboBox の最初のアイテムを選択
        widget.comboBoxHistory.setCurrentIndex(0)
        widget.on_history_item_selected(0)

        assert widget.lineEditPicker.text() == "/tmp/selected_dir"

    def test_on_history_item_selected_none_tooltip_sets_none(self, widget: PickerWidget) -> None:
        """ツールチップが None の場合でも lineEdit に None がセットされる（line 62-63）"""
        # comboBox にアイテムを追加しないと index 0 は存在しない
        # update_history でアイテムを追加
        widget.update_history("/tmp/path_a")
        widget.update_history("/tmp/path_b")

        # index 1 を選択
        widget.on_history_item_selected(1)

        assert widget.lineEditPicker.text() == "/tmp/path_b"
