"""エラー詳細表示Dialog

このモジュールはエラーレコードの詳細情報を表示するモーダルダイアログを提供します。
"""

from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QMessageBox

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import ErrorRecord
from ..designer.ErrorDetailDialog_ui import Ui_ErrorDetailDialog


class ErrorDetailDialog(QDialog, Ui_ErrorDetailDialog):
    """エラー詳細表示Dialog

    エラーレコードの詳細情報（スタックトレース、画像プレビュー等）を表示し、
    解決済みマーク機能を提供します。

    Attributes:
        was_resolved (bool): Dialogで解決済みマークが実行されたかどうか
    """

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        error_id: int,
        parent: QDialog | None = None,
    ):
        """ErrorDetailDialogを初期化します

        Args:
            db_manager: ImageDatabaseManagerインスタンス
            error_id: 表示するエラーレコードID
            parent: 親Dialog
        """
        super().__init__(parent)
        self.setupUi(self)  # type: ignore  # Justification: Qt Designer generated method signature

        self.db_manager = db_manager
        self.error_id = error_id
        self.error_record: ErrorRecord | None = None
        self.was_resolved: bool = False

        # エラー詳細読み込み
        self._load_error_detail()

        # Signal接続
        self._connect_signals()

        logger.info(f"ErrorDetailDialog initialized for error_id={error_id}")

    def _connect_signals(self) -> None:
        """Signalを接続します"""
        self.buttonMarkResolved.clicked.connect(self._on_mark_resolved_clicked)
        # buttonClose の clicked シグナルは .ui ファイルで accept() に接続済み

    def _load_error_detail(self) -> None:
        """エラー詳細を読み込みます

        Repository APIを呼び出してエラーレコードを取得し、UIに表示します。
        """
        try:
            # Repository API呼び出し
            # Note: get_error_records()にID指定フィルタがないため、
            # 全レコード取得してPython側でフィルタ
            all_records = self.db_manager.repository.get_error_records(limit=10000, offset=0)

            # error_idでフィルタ
            matching_records = [r for r in all_records if r.id == self.error_id]

            if not matching_records:
                logger.error(f"Error record not found: error_id={self.error_id}")
                QMessageBox.critical(
                    self, "エラー", f"エラーレコード（ID: {self.error_id}）が見つかりません"
                )
                self.reject()
                return

            self.error_record = matching_records[0]

            # UI更新
            self._update_ui()

        except Exception as e:
            logger.error(f"エラー詳細読み込みエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"エラー詳細の読み込みに失敗しました:\n{e}")
            self.reject()

    def _update_ui(self) -> None:
        """UIを更新します

        読み込んだエラーレコードの情報をUIに反映します。
        """
        if not self.error_record:
            return

        record = self.error_record

        # 基本情報
        self.lineEditOperationType.setText(record.operation_type)
        self.lineEditErrorType.setText(record.error_type)
        self.textEditErrorMessage.setPlainText(record.error_message)
        self.lineEditFilePath.setText(record.file_path if record.file_path else "N/A")
        self.lineEditModelName.setText(record.model_name if record.model_name else "N/A")
        self.lineEditCreatedAt.setText(record.created_at.strftime("%Y-%m-%d %H:%M:%S"))
        self.lineEditRetryCount.setText(str(record.retry_count))

        # 解決日時
        if record.resolved_at:
            self.lineEditResolvedAt.setText(record.resolved_at.strftime("%Y-%m-%d %H:%M:%S"))
            # 解決済みの場合はボタン無効化
            self.buttonMarkResolved.setEnabled(False)
        else:
            self.lineEditResolvedAt.setText("未解決")

        # スタックトレース
        if record.stack_trace:
            self.textEditStackTrace.setPlainText(record.stack_trace)
        else:
            self.textEditStackTrace.setPlainText("スタックトレースなし")

        # 画像プレビュー
        self._load_image_preview()

    def _load_image_preview(self) -> None:
        """画像プレビューを読み込みます"""
        if not self.error_record or not self.error_record.file_path:
            self.labelImagePreview.setText("画像パスが設定されていません")
            return

        file_path = Path(self.error_record.file_path)

        if not file_path.exists():
            self.labelImagePreview.setText(f"画像ファイルが見つかりません:\n{file_path.name}")
            return

        try:
            # QPixmap読み込み
            pixmap = QPixmap(str(file_path))

            if pixmap.isNull():
                self.labelImagePreview.setText(f"画像の読み込みに失敗しました:\n{file_path.name}")
                return

            # スケール表示（アスペクト比維持）
            scaled_pixmap = pixmap.scaled(
                400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.labelImagePreview.setPixmap(scaled_pixmap)

            logger.debug(f"Image preview loaded: {file_path.name}")

        except Exception as e:
            logger.error(f"画像プレビュー読み込みエラー: {e}", exc_info=True)
            self.labelImagePreview.setText(f"画像プレビューエラー:\n{e}")

    def _on_mark_resolved_clicked(self) -> None:
        """解決済みマークボタンクリック処理"""
        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "確認",
            "このエラーを解決済みにマークしますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Repository API呼び出し
                self.db_manager.repository.mark_error_resolved(self.error_id)
                self.was_resolved = True

                QMessageBox.information(self, "成功", "エラーを解決済みにマークしました")

                logger.info(f"Error marked as resolved: error_id={self.error_id}")

                # Dialogを閉じる
                self.accept()

            except Exception as e:
                logger.error(f"解決マーク失敗: {e}", exc_info=True)
                QMessageBox.critical(self, "エラー", f"解決マークに失敗しました:\n{e}")
