"""OpenAI Batch API JSONL インポート用ワーカー。

バックグラウンドスレッドでBatchImportServiceを実行し、
進捗とキャンセルをGUIに統合する。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ...database.db_repository import ImageRepository
from ...services.batch_import_service import BatchImportResult, BatchImportService
from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager


class BatchImportWorker(LoRAIroWorkerBase[BatchImportResult]):
    """OpenAI Batch API JSONL インポートワーカー。"""

    _OPERATION_TYPE: ClassVar[str] = "batch_import"

    def __init__(
        self,
        repository: ImageRepository,
        jsonl_files: list[Path],
        *,
        dry_run: bool = False,
        model_name_override: str | None = None,
        db_manager: ImageDatabaseManager | None = None,
    ) -> None:
        """ワーカー初期化。

        Args:
            repository: 画像リポジトリ。
            jsonl_files: インポート対象のJSONLファイルリスト。
            dry_run: Trueの場合、DB書き込みを行わない。
            model_name_override: モデル名上書き。
            db_manager: エラー記録用DBマネージャー。
        """
        super().__init__(db_manager=db_manager)
        self._repository = repository
        self._jsonl_files = jsonl_files
        self._dry_run = dry_run
        self._model_name_override = model_name_override

    def execute(self) -> BatchImportResult:
        """バッチインポート処理を実行する。

        Returns:
            インポート結果。
        """
        self._report_progress(5, "JSONLファイルを準備中...")

        service = BatchImportService(self._repository)
        total_files = len(self._jsonl_files)

        if total_files == 0:
            self._report_progress(100, "JSONLファイルが見つかりません")
            return BatchImportResult()

        self._report_progress(10, f"{total_files}ファイル検出、インポート開始...")

        # ファイルごとに進捗報告しながら処理
        all_results: list[BatchImportResult] = []
        for i, jsonl_path in enumerate(self._jsonl_files):
            self._check_cancellation()

            percentage = 10 + int((i / total_files) * 85)
            self._report_progress_throttled(
                percentage,
                f"処理中: {jsonl_path.name}",
                current_item=str(jsonl_path),
                processed_count=i,
                total_count=total_files,
            )
            self._report_batch_progress(i + 1, total_files, jsonl_path.name)

            result = service.import_from_jsonl(
                jsonl_path,
                dry_run=self._dry_run,
                model_name_override=self._model_name_override,
            )
            all_results.append(result)

        # 結果集約
        final = self._aggregate_results(all_results)

        mode = "DRY-RUN" if self._dry_run else "LIVE"
        self._report_progress(
            100,
            f"インポート完了 ({mode}): {final.saved}件保存",
        )

        logger.info(
            f"バッチインポートワーカー完了: "
            f"合計={final.total_records}, 保存={final.saved}, "
            f"アンマッチ={final.unmatched}, mode={mode}"
        )

        return final

    @staticmethod
    def _aggregate_results(results: list[BatchImportResult]) -> BatchImportResult:
        """複数ファイルの結果を集約する。

        Args:
            results: 各ファイルのインポート結果リスト。

        Returns:
            集約されたインポート結果。
        """
        if not results:
            return BatchImportResult()

        return BatchImportResult(
            total_records=sum(r.total_records for r in results),
            parsed_ok=sum(r.parsed_ok for r in results),
            parse_errors=sum(r.parse_errors for r in results),
            matched=sum(r.matched for r in results),
            unmatched=sum(r.unmatched for r in results),
            saved=sum(r.saved for r in results),
            save_errors=sum(r.save_errors for r in results),
            model_name=next((r.model_name for r in results if r.model_name), ""),
            unmatched_ids=[uid for r in results for uid in r.unmatched_ids],
            error_details=[d for r in results for d in r.error_details],
        )
