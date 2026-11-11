"""エラータブの専用ウィジェット (Epic #867 / #871)。

同一原因グルーピング + クロスフィルタ + resolve アクションを持つ
`ErrorsTriageWidget` をホストし、固有の振る舞い (再計算・resolve) を所有する。
statusBar の通知バッジ (`ErrorNotificationWidget`) は MainWindow が所有する横断
コンポーネントのため、resolve 時は `errors_resolved` シグナルを上へ emit して
MainWindow 側でバッジ更新する (glue)。
"""

from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ...database.db_manager import ImageDatabaseManager
from ...database.schema import ErrorRecord
from ...services.error_triage_service import ErrorRow, ErrorTriageService
from ...utils.log import logger
from ..state.staging_state import StagingStateManager
from ..widgets.errors_triage_widget import ErrorsTriageWidget

_ERROR_RECORDS_LIMIT = 500


class ErrorsTabWidget(QWidget):
    """エラータブのルートウィジェット (Wireframes v11 Frame 4 · Errors)。

    DB のエラーレコードをトリアージ表示し、resolve 操作で resolved 状態を更新する。

    Signals:
        errors_resolved: エラーを resolve したとき。MainWindow が statusBar の
            通知バッジ件数を更新するために購読する。
        image_link_clicked: 影響画像リンクが押されたとき (image_id)。
        restage_images_requested: 影響画像のステージング追加が要求されたとき (list[int])。
    """

    errors_resolved = Signal()
    image_link_clicked = Signal(int)
    restage_images_requested = Signal(list)

    def __init__(
        self,
        *,
        db_manager: ImageDatabaseManager | None,
        staging_state_manager: Any = None,
        parent: QWidget | None = None,
    ) -> None:
        """エラータブを初期化する。

        Args:
            db_manager: エラーレコードの取得と resolve 更新に使う。
            staging_state_manager: ステージング状態マネージャ (任意)。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._db_manager = db_manager
        self._staging_state_manager = staging_state_manager
        self._triage_service = ErrorTriageService()

        self._triage_widget = ErrorsTriageWidget(parent=self)
        self._triage_widget.resolve_requested.connect(self._on_resolve)
        self._triage_widget.resolve_group_requested.connect(self._on_resolve_group)
        self._triage_widget.filter_changed.connect(self.refresh)
        self._triage_widget.image_link_clicked.connect(self._on_image_link_clicked)
        self._triage_widget.restage_images_requested.connect(self._on_restage_images_requested)

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
            self._triage_widget.display(
                self._triage_service.summarize([]),
                [],
                [],
                is_truncated=False,
            )
            return

        # 全エラー (resolved/unresolved 両方) を取得して ErrorRow へ変換する。
        records = self._db_manager.error_record_repo.get_error_records(
            resolved=None, limit=_ERROR_RECORDS_LIMIT
        )
        all_rows = [self._error_record_to_row(record) for record in records]

        operation_types = sorted({r.operation_type for r in all_rows})
        error_types = sorted({r.error_type for r in all_rows})
        model_names = sorted({r.model_name for r in all_rows if r.model_name})
        # フィルタ選択肢更新時にも既存の combo 選択値は保持される (#1536)
        self._triage_widget.set_filter_options(operation_types, error_types, model_names)

        summary = self._triage_service.summarize(all_rows)
        error_filter = self._triage_widget.get_filter()
        filtered = self._triage_service.apply_filter(all_rows, error_filter)
        groups = self._triage_service.group_errors(filtered)
        self._triage_widget.display(
            summary,
            groups,
            filtered,
            is_truncated=len(records) >= _ERROR_RECORDS_LIMIT,
        )

    @staticmethod
    def _error_record_to_row(record: ErrorRecord) -> ErrorRow:
        """ErrorRecord ORM を ORM 非依存の ErrorRow に変換する。"""
        raw_file_path = getattr(record, "file_path", None)
        raw_stack = getattr(record, "stack_trace", None)
        return ErrorRow(
            error_id=record.id,
            image_id=record.image_id,
            operation_type=record.operation_type,
            error_type=record.error_type,
            error_message=record.error_message,
            model_name=record.model_name,
            resolved=record.resolved_at is not None,
            created_at=record.created_at,
            file_path=str(raw_file_path) if isinstance(raw_file_path, str) and raw_file_path else None,
            stack_trace=str(raw_stack) if isinstance(raw_stack, str) and raw_stack else None,
        )

    @Slot(int)
    def _on_image_link_clicked(self, image_id: int) -> None:
        """影響画像リンク押下時に Search/Review ビューへ遷移する (#1563)。"""
        self.image_link_clicked.emit(image_id)
        window = self.window()
        if hasattr(window, "_open_annotation_review_image"):
            window._open_annotation_review_image(image_id)

    @staticmethod
    def _cache_metadata_in_dataset_state(dataset_state: Any, meta: dict[str, Any]) -> None:
        if hasattr(dataset_state, "cache_external_image_metadata"):
            dataset_state.cache_external_image_metadata(meta)
        elif hasattr(dataset_state, "add_image"):
            dataset_state.add_image(meta)

    @classmethod
    def _batch_resolve_missing_images(
        cls, db_mgr: Any, dataset_state: Any, missing_ids: list[int]
    ) -> set[int]:
        resolved_ids: set[int] = set()
        batch_getter = getattr(db_mgr, "get_images_metadata_batch", None)
        if not callable(batch_getter):
            return resolved_ids
        try:
            batch_rows = batch_getter(missing_ids, include_annotations=False)
            if isinstance(batch_rows, list):
                for meta in batch_rows:
                    if isinstance(meta, dict) and meta.get("id") is not None:
                        cls._cache_metadata_in_dataset_state(dataset_state, meta)
                        resolved_ids.add(int(meta["id"]))
        except Exception as e:
            logger.warning(f"Failed to batch resolve metadata for images {missing_ids}: {e}")
        return resolved_ids

    def _resolve_and_cache_missing_images(self, manager: Any, image_ids: list[int]) -> None:
        """ステージング未登録の画像を DB から解決して dataset_state の補助キャッシュへ追加する (#1563, Codex P2)。"""
        dataset_state = getattr(manager, "_dataset_state_manager", None)
        db_mgr = self._db_manager or getattr(self.window(), "db_manager", None)
        if db_mgr is None and dataset_state is not None:
            db_mgr = getattr(dataset_state, "_db_manager", None)

        if db_mgr is None or dataset_state is None:
            return

        missing_ids = [iid for iid in image_ids if dataset_state.get_image_by_id(iid) is None]
        if not missing_ids:
            return

        resolved_ids = self._batch_resolve_missing_images(db_mgr, dataset_state, missing_ids)
        for iid in missing_ids:
            if iid in resolved_ids:
                continue
            try:
                meta = db_mgr.get_image_metadata(iid)
                if isinstance(meta, dict) and meta:
                    self._cache_metadata_in_dataset_state(dataset_state, meta)
            except Exception as e:
                logger.warning(f"Failed to resolve metadata for image {iid}: {e}")

    @Slot(list)
    def _on_restage_images_requested(self, image_ids: list[int]) -> None:
        """未解決エラーの影響画像をステージングへ追加する (#1563, Codex P2 #4531614949)。"""
        if not image_ids:
            return
        self.restage_images_requested.emit(list(image_ids))
        manager = self._staging_state_manager or getattr(self.window(), "staging_state_manager", None)
        if manager is None:
            return

        self._resolve_and_cache_missing_images(manager, image_ids)

        if isinstance(manager, StagingStateManager):
            manager.add_image_ids(image_ids)
        elif hasattr(manager, "add_images"):
            manager.add_images(image_ids)
        elif hasattr(manager, "add_image_ids"):
            manager.add_image_ids(image_ids)

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
