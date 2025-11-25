"""エラーログビューアWidget

このモジュールはエラーレコードの表示とフィルタリング機能を提供します。
"""

from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMessageBox, QTableWidgetItem, QWidget

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import ErrorRecord
from ..designer.ErrorLogViewerWidget_ui import Ui_ErrorLogViewerWidget
from .error_detail_dialog import ErrorDetailDialog


class ErrorLogViewerWidget(QWidget, Ui_ErrorLogViewerWidget):
    """エラーログビューアWidget

    Repository Patternに準拠したエラーログ表示機能を提供します。
    ImageDatabaseManager経由でエラーレコードを取得・表示します。

    Signals:
        error_selected (int): エラーレコードが選択されたときに発火（error_record_id）
        error_resolved (int): エラーが解決済みにマークされたときに発火（error_record_id）
    """

    # Signal定義
    error_selected = Signal(int)  # error_record_id
    error_resolved = Signal(int)  # error_record_id

    def __init__(self, parent: QWidget | None = None):
        """ErrorLogViewerWidgetを初期化します

        Args:
            parent: 親Widget
        """
        super().__init__(parent)
        self.setupUi(self)  # type: ignore  # Justification: Qt Designer generated method signature

        # 依存注入
        self.db_manager: ImageDatabaseManager | None = None

        # 状態管理
        self.current_page: int = 1
        self.total_pages: int = 0
        self.page_size: int = 100
        self.current_error_records: list[ErrorRecord] = []

        # UI初期化
        self._setup_table_properties()
        self._connect_signals()

        logger.info("ErrorLogViewerWidget initialized")

    def set_db_manager(self, db_manager: ImageDatabaseManager) -> None:
        """ImageDatabaseManagerを依存注入します

        Args:
            db_manager: ImageDatabaseManagerインスタンス
        """
        self.db_manager = db_manager
        logger.info("ImageDatabaseManager set for ErrorLogViewerWidget")

    def _setup_table_properties(self) -> None:
        """テーブルのプロパティを設定します"""
        # IDカラムを非表示（データ保持用）
        self.tableWidgetErrors.setColumnHidden(0, True)

        # カラム幅を設定
        self.tableWidgetErrors.setColumnWidth(1, 150)  # 作成日時
        self.tableWidgetErrors.setColumnWidth(2, 100)  # 操作種別
        self.tableWidgetErrors.setColumnWidth(3, 120)  # エラー種別
        self.tableWidgetErrors.setColumnWidth(4, 300)  # エラーメッセージ
        self.tableWidgetErrors.setColumnWidth(5, 200)  # 画像ファイル名
        self.tableWidgetErrors.setColumnWidth(6, 150)  # モデル名
        self.tableWidgetErrors.setColumnWidth(7, 80)  # 状態

    def _connect_signals(self) -> None:
        """Signalを接続します"""
        # フィルタ・更新ボタン
        self.buttonRefresh.clicked.connect(self.load_error_records)
        self.comboOperationType.currentIndexChanged.connect(self.load_error_records)
        self.checkBoxShowResolved.stateChanged.connect(self.load_error_records)

        # ページネーション
        self.buttonPreviousPage.clicked.connect(self._on_previous_page)
        self.buttonNextPage.clicked.connect(self._on_next_page)
        self.spinBoxPageSize.valueChanged.connect(self._on_page_size_changed)

        # 下部ボタン
        self.buttonViewDetails.clicked.connect(self._on_view_details_clicked)
        self.buttonMarkResolved.clicked.connect(self._on_mark_resolved_clicked)
        self.buttonExportLog.clicked.connect(self._on_export_log_clicked)

    def load_error_records(self) -> None:
        """エラーレコードを読み込みます

        Repository APIを呼び出してエラーレコードを取得し、テーブルに表示します。
        """
        if not self.db_manager:
            logger.error("ImageDatabaseManager not set")
            QMessageBox.warning(self, "エラー", "データベース接続が設定されていません。")
            return

        try:
            # フィルタ条件取得
            operation_type = self._get_selected_operation_type()
            show_resolved = self.checkBoxShowResolved.isChecked()
            resolved_filter = None if show_resolved else False

            # ページネーション計算
            self.page_size = self.spinBoxPageSize.value()
            offset = (self.current_page - 1) * self.page_size

            # Repository API呼び出し
            records = self.db_manager.repository.get_error_records(
                operation_type=operation_type,
                resolved=resolved_filter,
                limit=self.page_size,
                offset=offset,
            )

            # エラーレコードを保存
            self.current_error_records = records

            # テーブル表示更新
            self._update_table_display(records)

            # ページ情報更新
            total_count = self.db_manager.repository.get_error_count_unresolved(
                operation_type=operation_type
            )
            if show_resolved:
                # 解決済みも含む場合は別途カウント取得
                total_count = len(
                    self.db_manager.repository.get_error_records(
                        operation_type=operation_type, resolved=None, limit=10000
                    )
                )

            self.total_pages = (
                (total_count + self.page_size - 1) // self.page_size if total_count > 0 else 1
            )
            self._update_page_info()

            logger.info(
                f"Loaded {len(records)} error records (page {self.current_page}/{self.total_pages})"
            )

        except Exception as e:
            logger.error(f"エラーレコード読み込みエラー: {e}", exc_info=True)
            QMessageBox.critical(self, "エラー", f"エラーログの読み込みに失敗しました:\n{e}")

    def _get_selected_operation_type(self) -> str | None:
        """選択された操作種別を取得します

        Returns:
            str | None: 操作種別（"全て"の場合はNone）
        """
        selected_text = self.comboOperationType.currentText()
        return None if selected_text == "全て" else selected_text

    def _update_table_display(self, records: list[ErrorRecord]) -> None:
        """テーブル表示を更新します

        Args:
            records: 表示するエラーレコードのリスト
        """
        self.tableWidgetErrors.setRowCount(0)

        for row, record in enumerate(records):
            self.tableWidgetErrors.insertRow(row)

            # 0. ID（非表示、UserRole保存）
            id_item = QTableWidgetItem()
            id_item.setData(Qt.ItemDataRole.UserRole, record.id)
            self.tableWidgetErrors.setItem(row, 0, id_item)

            # 1. 作成日時
            created_at_str = record.created_at.strftime("%Y-%m-%d %H:%M:%S")
            self.tableWidgetErrors.setItem(row, 1, QTableWidgetItem(created_at_str))

            # 2. 操作種別
            self.tableWidgetErrors.setItem(row, 2, QTableWidgetItem(record.operation_type))

            # 3. エラー種別
            self.tableWidgetErrors.setItem(row, 3, QTableWidgetItem(record.error_type))

            # 4. エラーメッセージ（省略表示）
            message = record.error_message
            if len(message) > 100:
                message = message[:100] + "..."
            self.tableWidgetErrors.setItem(row, 4, QTableWidgetItem(message))

            # 5. 画像ファイル名
            if record.file_path:
                filename = Path(record.file_path).name
                self.tableWidgetErrors.setItem(row, 5, QTableWidgetItem(filename))
            else:
                self.tableWidgetErrors.setItem(row, 5, QTableWidgetItem("N/A"))

            # 6. モデル名
            model_name = record.model_name if record.model_name else "N/A"
            self.tableWidgetErrors.setItem(row, 6, QTableWidgetItem(model_name))

            # 7. 状態
            status = "解決済み" if record.resolved_at else "未解決"
            self.tableWidgetErrors.setItem(row, 7, QTableWidgetItem(status))

    def _update_page_info(self) -> None:
        """ページ情報を更新します"""
        self.labelPageInfo.setText(f"Page {self.current_page} / {self.total_pages}")
        self.buttonPreviousPage.setEnabled(self.current_page > 1)
        self.buttonNextPage.setEnabled(self.current_page < self.total_pages)

    def _on_previous_page(self) -> None:
        """前ページボタンクリック処理"""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_error_records()

    def _on_next_page(self) -> None:
        """次ページボタンクリック処理"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_error_records()

    def _on_page_size_changed(self) -> None:
        """ページサイズ変更処理"""
        self.current_page = 1  # ページサイズ変更時は1ページ目に戻る
        self.load_error_records()

    def _on_view_details_clicked(self) -> None:
        """詳細表示ボタンクリック処理"""
        selected_row = self.tableWidgetErrors.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "警告", "エラーレコードを選択してください")
            return

        # エラーレコードID取得
        error_id = self.tableWidgetErrors.item(selected_row, 0).data(Qt.ItemDataRole.UserRole)

        # Signal発火
        self.error_selected.emit(error_id)

        # DetailDialog表示
        if self.db_manager:
            dialog = ErrorDetailDialog(self.db_manager, error_id, parent=self)
            result = dialog.exec()

            # ダイアログが解決マークで閉じられた場合、リロード
            if result and dialog.was_resolved:
                self.error_resolved.emit(error_id)
                self.load_error_records()

    def _on_mark_resolved_clicked(self) -> None:
        """解決済みマークボタンクリック処理"""
        selected_row = self.tableWidgetErrors.currentRow()
        if selected_row < 0:
            QMessageBox.warning(self, "警告", "エラーレコードを選択してください")
            return

        # エラーレコードID取得
        error_id = self.tableWidgetErrors.item(selected_row, 0).data(Qt.ItemDataRole.UserRole)

        # 確認ダイアログ
        reply = QMessageBox.question(
            self,
            "確認",
            "このエラーを解決済みにマークしますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                if self.db_manager:
                    self.db_manager.repository.mark_error_resolved(error_id)
                    QMessageBox.information(self, "成功", "エラーを解決済みにマークしました")
                    self.error_resolved.emit(error_id)
                    self.load_error_records()
            except Exception as e:
                logger.error(f"解決マーク失敗: {e}", exc_info=True)
                QMessageBox.critical(self, "エラー", f"解決マークに失敗しました:\n{e}")

    def _on_export_log_clicked(self) -> None:
        """ログエクスポートボタンクリック処理

        Note:
            優先度: 低（将来拡張）
            現在は未実装メッセージを表示
        """
        QMessageBox.information(
            self,
            "未実装",
            "ログエクスポート機能は将来のバージョンで実装予定です。",
        )
