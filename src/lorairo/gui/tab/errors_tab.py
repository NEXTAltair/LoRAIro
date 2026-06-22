"""エラータブの専用ウィジェット (Epic #867 / #871)。

同一原因グルーピング + クロスフィルタ + resolve アクションを持つ
`ErrorsTriageWidget` をホストし、固有の振る舞い (再計算・resolve) を所有する。
statusBar の通知バッジ (`ErrorNotificationWidget`) は MainWindow が所有する横断
コンポーネントのため、resolve 時は `errors_resolved` シグナルを上へ emit して
MainWindow 側でバッジ更新する (glue)。
"""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import ErrorRecord
from ...services.error_triage_service import ErrorRow, ErrorTriageService
from ...utils.log import logger
from ..widgets.errors_triage_widget import ErrorsTriageWidget


class ErrorsTabWidget(QWidget):
    """エラータブのルートウィジェット (Wireframes v11 Frame 4 · Errors)。

    DB のエラーレコードをトリアージ表示し、resolve 操作で resolved 状態を更新する。

    Signals:
        errors_resolved: エラーを resolve したとき。MainWindow が statusBar の
            通知バッジ件数を更新するために購読する。
    """

    errors_resolved = Signal()

    def __init__(
        self,
        *,
        db_manager: ImageDatabaseManager | None,
        parent: QWidget | None = None,
    ) -> None:
        """エラータブを初期化する。

        Args:
            db_manager: エラーレコードの取得と resolve 更新に使う。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._db_manager = db_manager
        self._triage_service = ErrorTriageService()

        self._triage_widget = ErrorsTriageWidget(parent=self)
        self._triage_widget.resolve_requested.connect(self._on_resolve)
        self._triage_widget.resolve_group_requested.connect(self._on_resolve_group)
        self._triage_widget.filter_changed.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._triage_widget)

    @property
    def triage_widget(self) -> ErrorsTriageWidget:
        """内包する `ErrorsTriageWidget` を返す (タブ内配線・テスト用)。"""
        return self._triage_widget

    def refresh(self) -> None:
        """タブ表示時 / フィルタ変更時にトリアージを再計算して描画する。"""
        if not self._db_manager:
            self._triage_widget.display(self._triage_service.summarize([]), [], [])
            return

        # 全エラー (resolved/unresolved 両方) を取得して ErrorRow へ変換する。
        records = self._db_manager.error_record_repo.get_error_records(resolved=None, limit=500)
        all_rows = [self._error_record_to_row(record) for record in records]

        operation_types = sorted({r.operation_type for r in all_rows})
        error_types = sorted({r.error_type for r in all_rows})
        model_names = sorted({r.model_name for r in all_rows if r.model_name})
        self._triage_widget.set_filter_options(operation_types, error_types, model_names)

        summary = self._triage_service.summarize(all_rows)
        error_filter = self._triage_widget.get_filter()
        filtered = self._triage_service.apply_filter(all_rows, error_filter)
        groups = self._triage_service.group_errors(filtered)
        self._triage_widget.display(summary, groups, filtered)

    @staticmethod
    def _error_record_to_row(record: ErrorRecord) -> ErrorRow:
        """ErrorRecord ORM を ORM 非依存の ErrorRow に変換する。"""
        return ErrorRow(
            error_id=record.id,
            image_id=record.image_id,
            operation_type=record.operation_type,
            error_type=record.error_type,
            error_message=record.error_message,
            model_name=record.model_name,
            resolved=record.resolved_at is not None,
            created_at=record.created_at,
        )

    @Slot(int)
    def _on_resolve(self, error_id: int) -> None:
        """単一エラーを resolve して再描画する。"""
        if self._db_manager:
            self._db_manager.mark_errors_resolved_batch([error_id])
            self.errors_resolved.emit()
        self.refresh()

    @Slot(list)
    def _on_resolve_group(self, error_ids: list[int]) -> None:
        """グループ / 一括の error_id 群を resolve して再描画する。"""
        if self._db_manager and error_ids:
            _, resolved = self._db_manager.mark_errors_resolved_batch(error_ids)
            logger.info(f"一括 resolve 完了: {resolved} 件")
            self.errors_resolved.emit()
        self.refresh()
