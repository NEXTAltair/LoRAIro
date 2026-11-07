"""Kohya-ss データセット取り込み用ワーカー。

バックグラウンドスレッドで DatasetImportService を実行し、GUI をブロックしない。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ...database.repository.dataset import DatasetRepository
from ...services.dataset_import_service import DatasetImportResult, DatasetImportService
from ...utils.log import logger
from .base import LoRAIroWorkerBase

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...filesystem import FileSystemManager


class DatasetImportWorker(LoRAIroWorkerBase[DatasetImportResult]):
    """Kohya-ss データセット取り込みワーカー。"""

    _OPERATION_TYPE: ClassVar[str] = "dataset_import"

    def __init__(
        self,
        root: Path,
        dataset_name: str,
        version_name: str,
        config_files: list[Path],
        db_manager: ImageDatabaseManager,
        fsm: FileSystemManager,
    ) -> None:
        """ワーカー初期化。

        Args:
            root: Kohya 形式のルートディレクトリ。
            dataset_name: データセット名。
            version_name: 版名。空なら service が候補を作る。
            config_files: 版に紐づける設定 JSON (自動検出結果を置き換える)。
            db_manager: 画像登録に使う DB マネージャ (image_repo の session_factory も共有する)。
            fsm: 初期化済み FileSystemManager。
        """
        super().__init__(db_manager=db_manager)
        self._root = root
        self._dataset_name = dataset_name
        self._version_name = version_name
        self._config_files = config_files
        self._fsm = fsm

    def execute(self) -> DatasetImportResult:
        """取り込みを実行する。

        Returns:
            取り込み結果。

        Raises:
            DatasetConflictError: 同名の版が既にある場合など。
            ValueError: 計画や設定 JSON が不正な場合。
            OSError: 設定 JSON を読めない場合。
        """
        assert self._db_manager is not None
        self._report_progress(5, "取り込み計画を作成中...")
        # 他の worker と同様、DB マネージャの session_factory を共有し短命セッションで使う
        repository = DatasetRepository(session_factory=self._db_manager.image_repo.session_factory)
        service = DatasetImportService(self._db_manager, repository, self._fsm)

        # JSON は画像ディレクトリの外にあるため、選択されたものだけを使う。
        # 版名の候補 (output_name) も選択された JSON から作る
        config_files = [path.resolve() for path in self._config_files]
        plan = service.propose_plan(self._root, self._dataset_name, self._version_name, config_files)

        self._check_cancellation()
        self._report_progress(10, "データセットを取り込み中...")
        result = service.import_directory(self._root, plan)
        self._report_progress(100, "データセット取り込み完了")
        logger.info(
            f"データセット取り込みワーカー完了: version_id={result.version_id}, "
            f"images={result.image_count}, skipped={result.skipped_images}"
        )
        return result
