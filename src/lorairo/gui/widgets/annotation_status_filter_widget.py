"""
Annotation Status Filter Widget

アノテーション状態によるフィルタリング機能を提供
完了/エラー状態での画像フィルタリングとカウント表示
"""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...utils.log import logger
from ..designer.AnnotationStatusFilterWidget_ui import Ui_AnnotationStatusFilterWidget
from ..services.search_filter_service import AnnotationStatusCounts, SearchFilterService


class AnnotationStatusFilterWidget(QWidget, Ui_AnnotationStatusFilterWidget):
    """
    アノテーション状態フィルタリングウィジェット

    機能:
    - 完了/エラー状態での画像フィルタリング
    - 状態統計表示とカウント更新
    - フィルター条件変更通知
    """

    # シグナル
    filter_changed = Signal(dict)  # フィルター条件変更 {completed: bool, error: bool}
    refresh_requested = Signal()  # リフレッシュ要求
    status_updated = Signal(AnnotationStatusCounts)  # 状態更新完了

    def __init__(
        self,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setupUi(self)

        # SearchFilterService（依存注入）
        self.search_filter_service: SearchFilterService | None = None

        # 状態情報
        self.current_counts: AnnotationStatusCounts = AnnotationStatusCounts()
        self.active_filters: dict[str, bool] = {"completed": False, "error": False}

        # UI初期化
        self._setup_connections()
        self._setup_widget_properties()

        logger.debug("AnnotationStatusFilterWidget initialized")

    def _setup_connections(self) -> None:
        """シグナル・スロット接続設定"""
        # チェックボックス変更イベント
        self.checkBoxCompleted.toggled.connect(self._on_completed_filter_changed)
        self.checkBoxError.toggled.connect(self._on_error_filter_changed)

        # 更新ボタン
        self.pushButtonRefresh.clicked.connect(self._on_refresh_clicked)

    def _setup_widget_properties(self) -> None:
        """ウィジェットプロパティ設定"""
        # チェックボックススタイル
        checkbox_style = """
            QCheckBox {
                font-size: 10px;
                font-weight: normal;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #ccc;
                background-color: white;
                border-radius: 2px;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #4CAF50;
                background-color: #4CAF50;
                border-radius: 2px;
            }
        """
        self.checkBoxCompleted.setStyleSheet(checkbox_style)
        self.checkBoxError.setStyleSheet(checkbox_style)

        # カウントラベルスタイル
        count_style = "font-size: 9px; color: #666; font-weight: bold;"
        self.labelCompletedCount.setStyleSheet(count_style)
        self.labelErrorCount.setStyleSheet(count_style)

        # 更新ボタンスタイル
        self.pushButtonRefresh.setStyleSheet("""
            QPushButton {
                font-size: 9px;
                padding: 4px 8px;
                border: 1px solid #2196F3;
                border-radius: 3px;
                background-color: #f0f8ff;
                color: #1976D2;
            }
            QPushButton:hover {
                background-color: #e3f2fd;
            }
            QPushButton:pressed {
                background-color: #2196F3;
                color: white;
            }
        """)

    @Slot(bool)
    def _on_completed_filter_changed(self, checked: bool) -> None:
        """完了フィルター変更時の処理"""
        self.active_filters["completed"] = checked
        self._emit_filter_changed()
        logger.debug(f"Completed filter changed: {checked}")

    @Slot(bool)
    def _on_error_filter_changed(self, checked: bool) -> None:
        """エラーフィルター変更時の処理"""
        self.active_filters["error"] = checked
        self._emit_filter_changed()
        logger.debug(f"Error filter changed: {checked}")

    @Slot()
    def _on_refresh_clicked(self) -> None:
        """更新ボタンクリック時の処理"""
        self.refresh_requested.emit()
        if self.search_filter_service:
            self.update_status_counts()
        logger.debug("Refresh requested")

    def _emit_filter_changed(self) -> None:
        """フィルター変更シグナルを送信"""
        self.filter_changed.emit(self.active_filters.copy())

    def set_search_filter_service(self, service: SearchFilterService) -> None:
        """SearchFilterServiceを設定"""
        self.search_filter_service = service
        logger.debug("SearchFilterService set for AnnotationStatusFilterWidget")

    def update_status_counts(self) -> None:
        """アノテーション状態カウントを更新"""
        if not self.search_filter_service:
            logger.warning("SearchFilterService not available for status count update")
            return

        try:
            # SearchFilterServiceから統計取得
            counts = self.search_filter_service.get_annotation_status_counts()

            # UI更新
            self._update_count_display(counts)

            # 現在の状態保存
            self.current_counts = counts

            self.status_updated.emit(counts)
            logger.debug(f"Status counts updated - completed: {counts.completed}, error: {counts.error}")

        except Exception as e:
            logger.error(f"Error updating status counts: {e}", exc_info=True)

    def _update_count_display(self, counts: AnnotationStatusCounts) -> None:
        """カウント表示を更新"""
        try:
            # 完了数表示
            self.labelCompletedCount.setText(f"({counts.completed})")

            # エラー数表示
            self.labelErrorCount.setText(f"({counts.error})")

            # ツールチップ更新
            completion_rate = counts.completion_rate
            self.checkBoxCompleted.setToolTip(f"完了: {counts.completed}件 ({completion_rate:.1f}%)")
            self.checkBoxError.setToolTip(f"エラー: {counts.error}件")

        except Exception as e:
            logger.error(f"Error updating count display: {e}")

    def get_active_filters(self) -> dict[str, bool]:
        """現在アクティブなフィルター条件を取得"""
        return self.active_filters.copy()

    def set_filter_state(self, completed: bool = False, error: bool = False) -> None:
        """フィルター状態を設定"""
        # シグナルブロックして無限ループ回避
        self.checkBoxCompleted.blockSignals(True)
        self.checkBoxError.blockSignals(True)

        try:
            self.checkBoxCompleted.setChecked(completed)
            self.checkBoxError.setChecked(error)

            self.active_filters["completed"] = completed
            self.active_filters["error"] = error

        finally:
            self.checkBoxCompleted.blockSignals(False)
            self.checkBoxError.blockSignals(False)

        logger.debug(f"Filter state set - completed: {completed}, error: {error}")

    def clear_filters(self) -> None:
        """すべてのフィルターをクリア"""
        self.set_filter_state(completed=False, error=False)
        self._emit_filter_changed()
        logger.debug("All filters cleared")

    def get_current_counts(self) -> AnnotationStatusCounts:
        """現在のカウント情報を取得"""
        return self.current_counts

    def set_enabled_state(self, enabled: bool) -> None:
        """ウィジェット全体の有効/無効状態を設定"""
        self.checkBoxCompleted.setEnabled(enabled)
        self.checkBoxError.setEnabled(enabled)
        self.pushButtonRefresh.setEnabled(enabled)

        if not enabled:
            logger.debug("AnnotationStatusFilterWidget disabled")
        else:
            logger.debug("AnnotationStatusFilterWidget enabled")
