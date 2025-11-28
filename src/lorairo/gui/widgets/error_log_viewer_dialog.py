"""エラーログビューアDialog

ErrorLogViewerWidgetをポップアップダイアログとして表示します。
Worker error発生時やユーザー操作によってオンデマンドで表示されます。
"""

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ...database.db_manager import ImageDatabaseManager
from .error_log_viewer_widget import ErrorLogViewerWidget


class ErrorLogViewerDialog(QDialog):
    """エラーログビューアDialog

    ErrorLogViewerWidgetをラップしてダイアログ表示を提供します。
    シングルトンパターンで再利用され、閉じても破棄されません。

    Signals:
        error_selected (int): エラーレコードが選択されたとき（widget経由）
        error_resolved (int): エラーが解決済みにマークされたとき（widget経由）
    """

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        parent: QWidget | None = None,
        auto_load: bool = True,
    ):
        """ErrorLogViewerDialogを初期化します

        Args:
            db_manager: ImageDatabaseManagerインスタンス
            parent: 親Widget（通常はMainWindow）
            auto_load: 初期化時に自動的にエラーレコードを読み込むか
        """
        super().__init__(parent)

        self.db_manager = db_manager
        self.auto_load = auto_load

        # Dialog設定
        self.setWindowTitle("エラーログビューア")
        self.resize(820, 620)  # Widget 800x600 + margin
        self.setModal(False)  # Non-modal: MainWindowと並行操作可能
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)  # 閉じても破棄しない

        # Layout作成
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ErrorLogViewerWidget埋め込み
        self.error_log_widget = ErrorLogViewerWidget(parent=self)
        self.error_log_widget.set_db_manager(db_manager)
        main_layout.addWidget(self.error_log_widget)

        # ボタンエリア
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.refresh_button = QPushButton("再読み込み")
        self.refresh_button.clicked.connect(self.error_log_widget.load_error_records)
        button_layout.addWidget(self.refresh_button)

        self.close_button = QPushButton("閉じる")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)

        main_layout.addLayout(button_layout)

        # Signal転送（property assignment for zero-overhead forwarding）
        self.error_selected = self.error_log_widget.error_selected
        self.error_resolved = self.error_log_widget.error_resolved

        # 初回ロード
        if self.auto_load:
            self.error_log_widget.load_error_records()

        logger.info("ErrorLogViewerDialog initialized")

    def showEvent(self, event) -> None:
        """Dialog表示時の処理 - 毎回最新データをリロード"""
        super().showEvent(event)
        if hasattr(self, "error_log_widget"):
            self.error_log_widget.load_error_records()
        logger.debug("ErrorLogViewerDialog shown and refreshed")

    def closeEvent(self, event) -> None:
        """Dialog閉じる処理 - 破棄せずhideする（シングルトンパターン）"""
        self.hide()
        event.accept()
        logger.debug("ErrorLogViewerDialog hidden (not destroyed)")
