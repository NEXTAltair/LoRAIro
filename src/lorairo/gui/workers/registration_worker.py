"""データベース登録専用ワーカー"""

import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

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

        # 関連ファイル(.txt/.caption)を事前読み込みし、タグIDを一括解決（N+1回避）
        self._report_progress(8, "関連アノテーションを解析中...")
        annotations_by_path = self._preload_associated_annotations(image_files)
        tag_id_cache = self._build_tag_id_cache(annotations_by_path)

        # 統計情報初期化
        stats = {"registered": 0, "skipped": 0, "errors": 0}
        processed_paths: list[Path] = []

        # バッチ処理開始
        self._report_progress(10, f"バッチ登録開始: {total_count}件")

        for i, image_path in enumerate(image_files):
            # キャンセルチェック
            self._check_cancellation()

            # 単一画像の登録と統計更新
            self._process_single_image_in_batch(
                image_path,
                i,
                total_count,
                stats,
                processed_paths,
                annotations=annotations_by_path.get(image_path),
                tag_id_cache=tag_id_cache,
            )

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
        *,
        annotations: dict[str, object] | None = None,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """バッチ処理内で単一画像を処理し、統計情報を更新する。

        Args:
            image_path: 処理対象の画像パス。
            i: 現在の処理インデックス（0始まり）。
            total_count: 処理対象の総画像数。
            stats: 処理統計情報を格納する辞書（in-place更新）。
            processed_paths: 登録成功した画像パスを格納するリスト（in-place更新）。
            annotations: 事前読み込み済みのアノテーション。Noneの場合はその場で読み込む。
            tag_id_cache: 正規化済みタグ→tag_idのキャッシュ。
        """
        try:
            # 単一画像の登録処理
            result_type, _ = self._register_single_image(
                image_path, i, total_count, annotations=annotations, tag_id_cache=tag_id_cache
            )

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

    def _register_single_image(
        self,
        image_path: Path,
        i: int,
        total_count: int,
        *,
        annotations: dict[str, object] | None = None,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> tuple[str, int]:
        """単一画像の登録処理を実行

        重複検出を行い、重複していない場合はデータベースに登録する。
        重複している場合でも関連ファイル（.txt/.caption）は処理される。

        Args:
            image_path: 登録対象の画像ファイルパス
            i: 現在の処理インデックス（0始まり）
            total_count: 処理対象の総画像数
            annotations: 事前読み込み済みのアノテーション。
            tag_id_cache: 正規化済みタグ→tag_idのキャッシュ。

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
            self._process_associated_files(
                image_path, duplicate_image_id, annotations=annotations, tag_id_cache=tag_id_cache
            )
            # ファイル名エイリアスを登録（バッチインポート時のマッチング用）
            # DBが未初期化の場合でも重複扱い（skipped）は変わらないため例外を握り潰す
            try:
                self.db_manager.repository.add_filename_alias(duplicate_image_id, image_path.stem)
            except SQLAlchemyError as e:
                logger.warning(f"エイリアス登録失敗（スキップ扱いは継続）: {image_path.stem}, {e}")
            logger.debug(f"スキップ (重複): {image_path} - 関連ファイルは処理")
            result_type = "skipped"
            image_id = duplicate_image_id
        else:
            # データベース登録
            result = self.db_manager.register_original_image(image_path, self.fsm)
            if result:
                image_id, _ = result
                # 関連ファイル（.txt/.caption）の処理
                self._process_associated_files(
                    image_path, image_id, annotations=annotations, tag_id_cache=tag_id_cache
                )
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

    def _preload_associated_annotations(self, image_files: list[Path]) -> dict[Path, dict[str, object]]:
        """関連アノテーション(.txt/.caption)を事前に一括読み込みする。

        Args:
            image_files: 画像ファイルパスのリスト。

        Returns:
            画像パス→アノテーション辞書のマッピング（アノテーションがある画像のみ）。
        """
        annotations_by_path: dict[Path, dict[str, object]] = {}
        for image_path in image_files:
            self._check_cancellation()
            annotations = self.file_reader.get_existing_annotations(image_path)
            if annotations:
                annotations_by_path[image_path] = annotations
        return annotations_by_path

    def _build_tag_id_cache(
        self, annotations_by_path: dict[Path, dict[str, object]]
    ) -> dict[str, int | None]:
        """事前読み込み済みアノテーションからタグを収集し、tag_idを一括解決する。

        Args:
            annotations_by_path: _preload_associated_annotations() の結果。

        Returns:
            正規化済みタグ文字列→tag_idのキャッシュ。解決失敗時は空辞書。
        """
        from genai_tag_db_tools.utils.cleanup_str import TagCleaner

        all_tags: set[str] = set()
        for annotations in annotations_by_path.values():
            raw_tags = annotations.get("tags", [])
            if not isinstance(raw_tags, list):
                continue
            for raw_tag in raw_tags:
                if not isinstance(raw_tag, str):
                    continue
                normalized = TagCleaner.clean_format(raw_tag).strip()
                if normalized:
                    all_tags.add(normalized)

        if not all_tags:
            return {}

        try:
            cache = self.db_manager.repository.batch_resolve_tag_ids(all_tags)
            logger.info(
                f"タグID一括解決完了: {sum(1 for v in cache.values() if v is not None)}/"
                f"{len(all_tags)}件解決"
            )
            return cache
        except Exception as e:
            logger.warning(f"タグID一括解決に失敗、個別解決へフォールバック: {e}")
            return {}

    def _process_associated_files(
        self,
        image_path: Path,
        image_id: int,
        *,
        annotations: dict[str, object] | None = None,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """画像ファイルに関連する.txtと.captionファイルを処理し、データベースに登録する。

        Args:
            image_path: 画像ファイルのパス。
            image_id: データベースの画像ID。
            annotations: 事前読み込み済みのアノテーション。Noneの場合はその場で読み込む。
            tag_id_cache: 正規化済みタグ→tag_idのキャッシュ。
        """
        if annotations is None:
            annotations = self.file_reader.get_existing_annotations(image_path)
        if not annotations:
            return

        raw_tags = annotations.get("tags", [])
        tags = [tag for tag in raw_tags if isinstance(tag, str)] if isinstance(raw_tags, list) else []
        if tags:
            from genai_tag_db_tools.utils.cleanup_str import TagCleaner

            from ...database.db_repository import TagAnnotationData

            tags_data: list[TagAnnotationData] = [
                {
                    "tag_id": (
                        tag_id_cache.get(TagCleaner.clean_format(tag).strip()) if tag_id_cache else None
                    ),
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

        raw_captions = annotations.get("captions", [])
        captions = [c for c in raw_captions if isinstance(c, str)] if isinstance(raw_captions, list) else []
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
