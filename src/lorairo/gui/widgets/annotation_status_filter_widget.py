"""
Annotation Status Filter Widget

アノテーション状態によるフィルタリング機能を提供
完了/エラー状態での画像フィルタリングとカウント表示
"""

from dataclasses import dataclass

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QWidget

from ...database.db_manager import ImageDatabaseManager
from ...utils.log import logger
from ..designer.AnnotationStatusFilterWidget_ui import Ui_AnnotationStatusFilterWidget


@dataclass
class AnnotationStatusCounts:
    """アノテーション状態カウント情報"""

    total: int = 0
    completed: int = 0
    error: int = 0

    @property
    def completion_rate(self) -> float:
        """完了率を取得"""
        if self.total == 0:
            return 0.0
        return (self.completed / self.total) * 100.0


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
        db_manager: ImageDatabaseManager | None = None,
    ):
        super().__init__(parent)
        self.setupUi(self)

        # 依存関係
        self.db_manager = db_manager

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
        if self.db_manager:
            self.update_status_counts()
        logger.debug("Refresh requested")

    def _emit_filter_changed(self) -> None:
        """フィルター変更シグナルを送信"""
        self.filter_changed.emit(self.active_filters.copy())

    def set_database_manager(self, db_manager: ImageDatabaseManager) -> None:
        """データベースマネージャー設定"""
        self.db_manager = db_manager
        logger.debug("Database manager set for AnnotationStatusFilterWidget")

    def update_status_counts(self) -> None:
        """アノテーション状態カウントを更新"""
        if not self.db_manager:
            logger.warning("Database manager not available for status count update")
            return

        try:
            # データベースから統計取得
            counts = self._fetch_annotation_counts()

            # UI更新
            self._update_count_display(counts)

            # 現在の状態保存
            self.current_counts = counts

            self.status_updated.emit(counts)
            logger.debug(f"Status counts updated - completed: {counts.completed}, error: {counts.error}")

        except Exception as e:
            logger.error(f"Error updating status counts: {e}", exc_info=True)

    def _fetch_annotation_counts(self) -> AnnotationStatusCounts:
        """データベースからアノテーション状態カウントを取得"""
        try:
            # データベースクエリでアノテーション状態を集計
            # TODO: 実際のデータベーススキーマに合わせて実装
            # ここでは仮の実装
            session = self.db_manager.get_session()

            with session:
                # 総画像数取得
                total_images = session.execute("SELECT COUNT(*) FROM images").scalar() or 0

                # 完了画像数取得 (タグまたはキャプションが存在)
                completed_query = """
                    SELECT COUNT(DISTINCT i.id) FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                """
                completed_images = session.execute(completed_query).scalar() or 0

                # エラー画像数取得 (TODO: エラー記録テーブルが必要)
                # 現在はプレースホルダー
                error_images = 0

                return AnnotationStatusCounts(
                    total=total_images, completed=completed_images, error=error_images
                )

        except Exception as e:
            logger.error(f"Error fetching annotation counts: {e}")
            return AnnotationStatusCounts()

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
