"""TagManagementDialog の単体テスト"""

from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt

from lorairo.gui.widgets.tag_management_dialog import TagManagementDialog
from lorairo.services.tag_management_service import TagManagementService


@pytest.mark.unit
class TestTagManagementDialog:
    """TagManagementDialog のテストクラス"""

    @pytest.fixture
    def mock_service(self) -> Mock:
        """Mock TagManagementService を提供"""
        service = Mock(spec=TagManagementService)
        service.get_unknown_tags.return_value = []
        service.get_all_available_types.return_value = ["character", "general", "meta"]
        return service

    @pytest.fixture
    def dialog(self, qtbot, mock_service) -> TagManagementDialog:
        """TagManagementDialog インスタンスを提供"""
        dialog = TagManagementDialog(mock_service)
        qtbot.addWidget(dialog)
        return dialog

    def test_initialization(self, dialog: TagManagementDialog) -> None:
        """初期化時の設定確認"""
        assert dialog.tag_service is not None
        assert dialog.windowTitle() == "タグタイプ管理"
        assert not dialog.isModal()  # Non-modal
        assert dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose) is False

    def test_widget_embedding(self, dialog: TagManagementDialog) -> None:
        """TagManagementWidget が埋め込まれていること"""
        assert hasattr(dialog, "tag_widget")
        assert dialog.tag_widget is not None
        assert dialog.tag_widget.tag_service is not None

    def test_buttons_present(self, dialog: TagManagementDialog) -> None:
        """ボタンが配置されていること"""
        assert hasattr(dialog, "refresh_button")
        assert hasattr(dialog, "close_button")
        assert dialog.refresh_button.text() == "再読み込み"
        assert dialog.close_button.text() == "閉じる"

    def test_signal_forwarding(self, dialog: TagManagementDialog) -> None:
        """Widget の Signal が Dialog に転送されること"""
        assert dialog.update_completed == dialog.tag_widget.update_completed
        assert dialog.update_failed == dialog.tag_widget.update_failed

    def test_refresh_button_triggers_load(self, dialog: TagManagementDialog, qtbot) -> None:
        """再読み込みボタンが load_unknown_tags() を呼び出すこと"""
        # Mock で呼び出しを追跡
        dialog.tag_widget.load_unknown_tags = Mock()

        # ボタンクリック
        dialog.refresh_button.click()

        # load_unknown_tags() が呼ばれたこと
        dialog.tag_widget.load_unknown_tags.assert_called_once()

    def test_close_button_hides_dialog(self, dialog: TagManagementDialog, qtbot) -> None:
        """閉じるボタンが Dialog を非表示にすること"""
        dialog.show()
        assert dialog.isVisible()

        # 閉じるボタンクリック
        dialog.close_button.click()

        # Dialog が非表示になること（破棄されない）
        assert not dialog.isVisible()

    def test_show_event_loads_tags(self, dialog: TagManagementDialog, qtbot, mock_service) -> None:
        """Dialog表示時に load_unknown_tags() が呼ばれること"""
        # Mock で呼び出しを追跡
        dialog.tag_widget.load_unknown_tags = Mock()

        # Dialog表示
        dialog.show()

        # load_unknown_tags() が呼ばれたこと
        dialog.tag_widget.load_unknown_tags.assert_called_once()
