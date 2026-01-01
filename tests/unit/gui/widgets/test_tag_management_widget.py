"""TagManagementWidget の単体テスト"""

from unittest.mock import Mock, patch

import pytest
from genai_tag_db_tools.models import TagRecordPublic
from PySide6.QtWidgets import QCheckBox, QComboBox

from lorairo.gui.widgets.tag_management_widget import TagManagementWidget
from lorairo.services.tag_management_service import TagManagementService


@pytest.mark.unit
class TestTagManagementWidget:
    """TagManagementWidget のテストクラス"""

    @pytest.fixture
    def mock_service(self) -> Mock:
        """Mock TagManagementService を提供"""
        service = Mock(spec=TagManagementService)
        service.get_unknown_tags.return_value = []
        service.get_all_available_types.return_value = ["character", "general", "meta"]
        return service

    @pytest.fixture
    def widget(self, qtbot, mock_service) -> TagManagementWidget:
        """TagManagementWidget インスタンスを提供"""
        widget = TagManagementWidget()
        widget.set_tag_service(mock_service)
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, widget: TagManagementWidget) -> None:
        """初期化時のUI状態確認"""
        assert widget.tag_service is not None
        assert widget.unknown_tags == []
        assert widget.available_types == []
        assert widget.tableWidgetTags.rowCount() == 0
        assert not widget.buttonUpdate.isEnabled()

    def test_load_unknown_tags_empty(self, widget: TagManagementWidget, qtbot, mock_service: Mock) -> None:
        """unknown type タグが0件の場合"""
        mock_service.get_unknown_tags.return_value = []
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        # テーブル更新を待機
        qtbot.waitUntil(lambda: widget.tableWidgetTags.rowCount() == 0, timeout=1000)

        assert len(widget.unknown_tags) == 0
        assert "0 unknown type tags found" in widget.labelStatus.text()

    def test_load_unknown_tags_with_data(
        self, widget: TagManagementWidget, qtbot, mock_service: Mock
    ) -> None:
        """unknown type タグが複数ある場合"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag_1",
                tag_id=1,
                source_tag="test_tag_1",
                type_name="unknown",
                format_name="Lorairo",
            ),
            TagRecordPublic(
                tag="test_tag_2",
                tag_id=2,
                source_tag="test_tag_2",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general", "meta"]

        widget.load_unknown_tags()

        # テーブルが2行になるまで待機
        qtbot.waitUntil(lambda: widget.tableWidgetTags.rowCount() == 2, timeout=1000)

        assert len(widget.unknown_tags) == 2
        assert "2 unknown type tags found" in widget.labelStatus.text()

        # 各行のUI要素確認
        for row in range(2):
            # Column 0: Checkbox
            checkbox = widget.tableWidgetTags.cellWidget(row, 0)
            assert isinstance(checkbox, QCheckBox)
            assert not checkbox.isChecked()

            # Column 4: ComboBox
            combobox = widget.tableWidgetTags.cellWidget(row, 4)
            assert isinstance(combobox, QComboBox)
            assert combobox.count() == 4  # "(選択してください)" + 3 types

    def test_checkbox_enables_button(self, widget: TagManagementWidget, qtbot, mock_service: Mock) -> None:
        """Checkbox選択でボタン有効化"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        # 初期状態: ボタン無効
        assert not widget.buttonUpdate.isEnabled()

        # UI要素取得
        checkbox = widget.tableWidgetTags.cellWidget(0, 0)
        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(checkbox, QCheckBox)
        assert isinstance(combobox, QComboBox)

        # UI操作をエミュレート
        combobox.setCurrentIndex(1)  # "character" を選択
        checkbox.setChecked(True)

        # ボタンが有効化されるまで待機
        qtbot.waitUntil(lambda: widget.buttonUpdate.isEnabled(), timeout=1000)

    def test_update_completed_signal(self, widget: TagManagementWidget, qtbot, monkeypatch) -> None:
        """update_completed Signal 発火確認"""
        # QMessageBoxをmockしてモーダルブロックを回避
        mock_msgbox = Mock(return_value=None)
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.QMessageBox.information", mock_msgbox
        )

        # waitSignalでシグナル発火を待機（timeout付き）
        with qtbot.waitSignal(widget.update_completed, timeout=2000):
            widget.update_completed.emit()

    def test_update_failed_signal(self, widget: TagManagementWidget, qtbot, monkeypatch) -> None:
        """update_failed Signal 発火確認"""
        # QMessageBoxをmockしてモーダルブロックを回避
        mock_msgbox = Mock(return_value=None)
        monkeypatch.setattr("lorairo.gui.widgets.tag_management_widget.QMessageBox.critical", mock_msgbox)

        # waitSignalでシグナル発火を待機（引数検証も可能）
        with qtbot.waitSignal(widget.update_failed, timeout=2000):
            widget.update_failed.emit("Test error")

    def test_type_selection_tracking(self, widget: TagManagementWidget, mock_service: Mock) -> None:
        """Type選択が内部で追跡されること"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(combobox, QComboBox)

        # type選択
        combobox.setCurrentIndex(1)  # "character"

        assert 1 in widget._type_selections
        assert widget._type_selections[1] == "character"
