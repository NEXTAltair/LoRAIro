"""データベース登録専用ワーカー"""

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ...annotations.existing_file_reader import ExistingFileReader
from ...utils.log import logger
from .base import LoRAIroWorkerBase
from .progress_helper import ProgressHelper

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...storage.file_system import FileSystemManager


@dataclass
class DatabaseRegistrationResult:
    """データベース登録結果"""

    registered_count: int
    skipped_count: int
    error_count: int
    processed_paths: list[Path]
    total_processing_time: float


class DatabaseRegistrationWorker(LoRAIroWorkerBase[DatabaseRegistrationResult]):
    """データベース登録専用ワーカー"""

    def __init__(
        self, directory: Path, db_manager: "ImageDatabaseManager", fsm: "FileSystemManager"
    ) -> None:
        super().__init__()
        self.directory = directory
        self.db_manager = db_manager
        self.fsm = fsm
        self.file_reader = ExistingFileReader()

    def execute(self) -> DatabaseRegistrationResult:
        """データベース登録処理を実行

        指定ディレクトリ内の画像ファイルを検索し、重複チェックを行った後に
        データベースへの登録を実行する。進捗状況は定期的に報告される。

        Returns:
            DatabaseRegistrationResult: 登録結果（成功数、スキップ数、エラー数、処理時間）

        Raises:
            RuntimeError: 処理がキャンセルされた場合
        """
        import time

        start_time = time.time()

        # 画像ファイル一覧取得
        self._report_progress(5, "画像ファイルを検索中...")
        image_files = list(self.fsm.get_image_files(self.directory))
        total_count = len(image_files)

        if total_count == 0:
            logger.warning(f"画像ファイルが見つかりません: {self.directory}")
            return DatabaseRegistrationResult(0, 0, 0, [], 0.0)

        logger.info(f"登録対象画像: {total_count}件")

        # 統計情報初期化
        stats = {"registered": 0, "skipped": 0, "errors": 0}
        processed_paths: list[Path] = []

        # バッチ処理開始
        self._report_progress(10, f"バッチ登録開始: {total_count}件")

        for i, image_path in enumerate(image_files):
            # キャンセルチェック
            self._check_cancellation()

            # 単一画像の登録と統計更新
            self._process_single_image_in_batch(image_path, i, total_count, stats, processed_paths)

        # 完了処理
        self._report_progress(100, "データベース登録完了")
        return self._build_registration_result(stats, processed_paths, start_time)

    def _process_single_image_in_batch(
        self,
        image_path: Path,
        i: int,
        total_count: int,
        stats: dict[str, int],
        processed_paths: list[Path],
    ) -> None:
        """バッチ処理内で単一画像を処理し、統計情報を更新する。

        Args:
            image_path: 処理対象の画像パス。
            i: 現在の処理インデックス（0始まり）。
            total_count: 処理対象の総画像数。
            stats: 処理統計情報を格納する辞書（in-place更新）。
            processed_paths: 登録成功した画像パスを格納するリスト（in-place更新）。
        """
        try:
            # 単一画像の登録処理
            result_type, _ = self._register_single_image(image_path, i, total_count)

            # 統計情報更新
            stats[result_type] += 1
            if result_type == "registered":
                processed_paths.append(image_path)

        except Exception as e:
            stats["errors"] += 1
            logger.error(f"画像登録エラー: {image_path}, {e}")

            # エラーレコード保存（二次エラー対策付き）
            try:
                self.db_manager.save_error_record(
                    operation_type="registration",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    image_id=None,
                    stack_trace=traceback.format_exc(),
                    file_path=str(image_path),
                    model_name=None,
                )
            except Exception as save_error:
                logger.error(f"エラーレコード保存失敗（二次エラー）: {save_error}")

    def _register_single_image(self, image_path: Path, i: int, total_count: int) -> tuple[str, int]:
        """単一画像の登録処理を実行

        重複検出を行い、重複していない場合はデータベースに登録する。
        重複している場合でも関連ファイル（.txt/.caption）は処理される。

        Args:
            image_path: 登録対象の画像ファイルパス
            i: 現在の処理インデックス（0始まり）
            total_count: 処理対象の総画像数

        Returns:
            tuple[str, int]: (result_type, image_id)
                - result_type: "registered"|"skipped"|"error"
                - image_id: 登録されたID、失敗時は-1
        """
        # バッチ進捗報告
        self._report_batch_progress(i + 1, total_count, image_path.name)

        # 重複チェック
        duplicate_image_id = self.db_manager.detect_duplicate_image(image_path)
        if duplicate_image_id:
            # 重複画像でも関連ファイル（.txt/.caption）を処理
            self._process_associated_files(image_path, duplicate_image_id)
            logger.debug(f"スキップ (重複): {image_path} - 関連ファイルは処理")
            result_type = "skipped"
            image_id = duplicate_image_id
        else:
            # データベース登録
            result = self.db_manager.register_original_image(image_path, self.fsm)
            if result:
                image_id, _ = result
                # 関連ファイル（.txt/.caption）の処理
                self._process_associated_files(image_path, image_id)
                logger.debug(f"登録完了: {image_path}")
                result_type = "registered"
            else:
                logger.error(f"画像登録失敗: {image_path}")
                result_type = "error"
                image_id = -1

        # 進捗報告（ProgressHelper使用）
        percentage = ProgressHelper.calculate_percentage(i + 1, total_count, 10, 85)  # 10-95%
        self._report_progress(
            percentage,
            f"登録中: {image_path.name}",
            current_item=str(image_path),
            processed_count=i + 1,
            total_count=total_count,
        )

        return result_type, image_id

    def _build_registration_result(
        self, stats: dict[str, int], processed_paths: list[Path], start_time: float
    ) -> DatabaseRegistrationResult:
        """登録結果オブジェクトを構築

        処理統計情報と経過時間から最終的な登録結果を構築し、
        サマリーログを出力する。

        Args:
            stats: 処理統計情報（registered, skipped, errors）
            processed_paths: 登録成功した画像パスのリスト
            start_time: 処理開始時刻（time.time()）

        Returns:
            DatabaseRegistrationResult: 登録結果オブジェクト
        """
        import time

        processing_time = time.time() - start_time

        registration_result = DatabaseRegistrationResult(
            registered_count=stats["registered"],
            skipped_count=stats["skipped"],
            error_count=stats["errors"],
            processed_paths=processed_paths,
            total_processing_time=processing_time,
        )

        # バッチサマリーログ（INFOレベル）
        logger.info(
            f"データベース登録完了: 登録={stats['registered']}, スキップ={stats['skipped']}, "
            f"エラー={stats['errors']}, 処理時間={processing_time:.2f}秒"
        )

        return registration_result

    def _process_associated_files(self, image_path: Path, image_id: int) -> None:
        """画像ファイルに関連する.txtと.captionファイルを処理し、データベースに登録する。

        Args:
            image_path: 画像ファイルのパス。
            image_id: データベースの画像ID。
        """
        annotations = self.file_reader.get_existing_annotations(image_path)
        if not annotations:
            return

        tags = annotations.get("tags", [])
        if tags:
            from ...database.db_repository import TagAnnotationData

            tags_data: list[TagAnnotationData] = [
                {
                    "tag_id": None,
                    "model_id": None,
                    "tag": tag,
                    "confidence_score": None,
                    "existing": True,
                    "is_edited_manually": False,
                }
                for tag in tags
            ]
            self.db_manager.save_tags(image_id, tags_data)
            logger.debug(f"タグを追加: {image_path.name} - {len(tags)}個のタグ")

        captions = annotations.get("captions", [])
        if captions:
            from ...database.db_repository import CaptionAnnotationData

            captions_data: list[CaptionAnnotationData] = [
                {
                    "model_id": None,
                    "caption": caption,
                    "existing": False,
                    "is_edited_manually": False,
                }
                for caption in captions
            ]
            self.db_manager.save_captions(image_id, captions_data)
            logger.debug(f"キャプションを追加: {image_path.name}")
