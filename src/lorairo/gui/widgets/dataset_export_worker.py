"""Dataset export worker for LoRA training compatible dataset export.

Provides an async worker that runs DatasetExportService in a QThread with
progress reporting. GUI 側の起動・監視は export_tab.py が担う。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from PySide6.QtCore import QObject, Signal

from ...database.filter_criteria import ImageFilterCriteria
from ...services.dataset_export_service import ExportResult

if TYPE_CHECKING:
    from ...services.export_overlay import ExportOverlayPlan


class DatasetExportWorker(QObject):
    """Worker for async dataset export processing."""

    # Signals
    progress = Signal(int, str)  # (progress_percent, message)
    finished = Signal(str)  # export_path
    cancelled = Signal()
    error = Signal(str)  # error_message

    def __init__(
        self,
        export_service: Any,
        image_ids: list[int],
        output_path: Path,
        resolution: int,
        export_format: str,
        merge_caption: bool = False,
        overlay_plan: ExportOverlayPlan | None = None,
    ) -> None:
        """Initialize export worker.

        Args:
            export_service: DatasetExportService instance
            image_ids: List of image IDs to export
            output_path: Output directory path
            resolution: Image resolution (512, 768, 1024, 1536)
            export_format: Export format ("txt_separate", "txt_merged", "json")
            merge_caption: Whether to merge captions with tags
            overlay_plan: 出力オーバーレイプラン (ADR 0080)。None で従来挙動を維持する。
        """
        super().__init__()
        self.export_service = export_service
        self.image_ids = image_ids
        self.output_path = output_path
        self.resolution = resolution
        self.export_format = export_format
        self.merge_caption = merge_caption
        self.overlay_plan = overlay_plan
        self._cancelled = False
        self.report = ExportResult(image_ids)

    @property
    def is_cancelled(self) -> bool:
        """Return whether cancellation has been requested."""
        return self._cancelled

    def cancel(self) -> None:
        """Request cooperative cancellation of the running export."""
        self._cancelled = True

    def run(self) -> None:
        """Execute export processing with progress reporting."""
        try:
            if self._cancelled:
                logger.info("Dataset export cancelled before start")
                self.cancelled.emit()
                return

            self.report = ExportResult(self.image_ids)
            total = len(self.image_ids)
            logger.info(
                f"Starting dataset export: {total} images, {self.resolution}px, format={self.export_format}"
            )

            self.progress.emit(0, f"エクスポート処理を開始しています... (0/{total})")

            def _on_progress(completed_count: int, total_count: int, _image_id: int) -> None:
                percent = int(completed_count * 100 / total_count) if total_count > 0 else 100
                self.progress.emit(percent, f"エクスポート中... ({completed_count}/{total_count})")

            # ADR 0055: 明示 ID は exact-set selector の criteria 経由で渡す
            # (非推奨の image_ids 直渡しを排除。他フィルタを bypass し NSFW 等も落とさない)。
            # resolution を criteria に載せ、対象解決を「選択解像度の処理済み版を持つ画像」に
            # 揃える (対象数と実エクスポート件数を一致させる, #612)。
            criteria = ImageFilterCriteria(image_ids=self.image_ids, resolution=self.resolution)
            if self.export_format == "json":
                result_path = self.export_service.export_with_criteria(
                    output_path=self.output_path,
                    format_type="json",
                    resolution=self.resolution,
                    criteria=criteria,
                    overlay_plan=self.overlay_plan,
                    report=self.report,
                    progress_callback=_on_progress,
                    should_cancel=lambda: self._cancelled,
                )
            else:
                merge_option = self.export_format == "txt_merged" or self.merge_caption
                result_path = self.export_service.export_with_criteria(
                    output_path=self.output_path,
                    format_type="txt",
                    resolution=self.resolution,
                    criteria=criteria,
                    merge_caption=merge_option,
                    overlay_plan=self.overlay_plan,
                    report=self.report,
                    progress_callback=_on_progress,
                    should_cancel=lambda: self._cancelled,
                )

            if self._cancelled:
                logger.info("Dataset export cancelled")
                self.cancelled.emit()
                return

            if not self.report.completed and not self.report.failures:
                fmt = "json" if self.export_format == "json" else "txt"
                for image_id in self.image_ids:
                    self.report.completed.setdefault(image_id, set()).add(fmt)

            self.progress.emit(100, "エクスポート完了")
            self.finished.emit(str(result_path))
            logger.info(f"Dataset export completed: {result_path}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"エクスポート処理でエラーが発生しました: {error_msg}")
            self.error.emit(error_msg)
