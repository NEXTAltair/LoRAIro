"""タグ管理Dialog

TagManagementWidgetをポップアップダイアログとして表示します。
"""

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...services.tag_management_service import TagManagementService
from .tag_management_widget import TagManagementWidget


class TagManagementDialog(QDialog):
    """タグ管理Dialog

    TagManagementWidgetをラップしてダイアログ表示を提供します。
    シングルトンパターンで再利用され、閉じても破棄されません。

    Signals:
        update_completed: タグ更新完了時（widget経由）
        update_failed (str): タグ更新失敗時（widget経由）
    """

    def __init__(
        self,
        tag_service: TagManagementService,
        parent: QWidget | None = None,
    ):
        """TagManagementDialogを初期化します

        Args:
            tag_service: TagManagementServiceインスタンス
            parent: 親Widget（通常はMainWindow）
        """
        super().__init__(parent)

        self.tag_service = tag_service

        # Dialog設定
        self.setWindowTitle("タグタイプ管理")
        self.resize(820, 620)  # Widget 800x600 + margin
        self.setModal(False)  # Non-modal: MainWindowと並行操作可能
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # 閉じても破棄しない

        # Layout作成
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # TagManagementWidget埋め込み
        self.tag_widget = TagManagementWidget(parent=self)
        self.tag_widget.set_tag_service(tag_service)
        main_layout.addWidget(self.tag_widget)

        # ボタンエリア
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.refresh_button = QPushButton("再読み込み")
        self.refresh_button.clicked.connect(self.tag_widget.load_unknown_tags)
        button_layout.addWidget(self.refresh_button)

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)

        # Signal転送（property assignment for zero-overhead forwarding）
        self.update_completed = self.tag_widget.update_completed
        self.update_failed = self.tag_widget.update_failed

        logger.info("TagManagementDialog initialized")

    def showEvent(self, event) -> None:
        """Dialog表示時の処理 - 毎回最新データをリロード"""
        super().showEvent(event)
        if hasattr(self, "tag_widget"):
            self.tag_widget.load_unknown_tags()
        logger.debug("TagManagementDialog shown and refreshed")

    def closeEvent(self, event) -> None:
        """Dialog閉じる処理 - 破棄せずhideする（シングルトンパターン）"""
        self.hide()
        event.accept()
        logger.debug("TagManagementDialog hidden (not destroyed)")
