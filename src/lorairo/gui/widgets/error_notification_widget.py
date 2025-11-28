"""エラー通知Widget（StatusBar用）

未解決エラー件数を表示し、クリックでエラーログダイアログを開きます。
"""

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ...database.db_manager import ImageDatabaseManager


class ErrorNotificationWidget(QLabel):
    """エラー通知Widget（StatusBar用）

    未解決エラー件数を表示し、クリックでエラーログ表示をトリガーします。

    Signals:
        clicked: ウィジェットがクリックされたとき
    """

    clicked = Signal()

    def __init__(self, db_manager: ImageDatabaseManager | None = None, parent: QWidget | None = None):
        """ErrorNotificationWidgetを初期化します

        Args:
            db_manager: ImageDatabaseManagerインスタンス（後で設定可能）
            parent: 親Widget
        """
        super().__init__(parent)

        self.db_manager = db_manager
        self.unresolved_count = 0

        # Widget設定
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("クリックでエラーログを表示")

        # 初期表示
        self.update_error_count()

    def set_db_manager(self, db_manager: ImageDatabaseManager) -> None:
        """ImageDatabaseManagerを設定します

        Args:
            db_manager: ImageDatabaseManagerインスタンス
        """
        self.db_manager = db_manager
        self.update_error_count()

    def update_error_count(self) -> None:
        """未解決エラー件数を更新します"""
        if not self.db_manager:
            self.setText("エラー: -- 件")
            self.setStyleSheet("")
            return

        try:
            count = self.db_manager.repository.get_error_count_unresolved()
            self.unresolved_count = count

            # 表示とスタイル更新
            if count == 0:
                self.setText("エラー: 0 件")
                self.setStyleSheet("QLabel { color: green; }")
            elif count < 10:
                self.setText(f"⚠️ エラー: {count} 件")
                self.setStyleSheet("QLabel { color: orange; font-weight: bold; }")
            else:
                self.setText(f"❌ エラー: {count} 件")
                self.setStyleSheet("QLabel { color: red; font-weight: bold; }")

            logger.debug(f"Error notification updated: {count} unresolved errors")

        except Exception as e:
            logger.error(f"Failed to update error count: {e}", exc_info=True)
            self.setText("エラー: 取得失敗")
            self.setStyleSheet("QLabel { color: gray; }")

    def mousePressEvent(self, event) -> None:
        """マウスクリックイベント"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
