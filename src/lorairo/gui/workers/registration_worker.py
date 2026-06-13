"""データベース登録専用ワーカー"""

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ...annotations.existing_file_reader import ExistingFileReader
from ...database.db_manager import RegistrationOutcome
from ...utils.log import logger
from .base import LoRAIroWorkerBase
from .progress_helper import ProgressHelper

if TYPE_CHECKING:
    from ...database.db_manager import ImageDatabaseManager
    from ...storage.file_system import FileSystemManager


@dataclass(frozen=True)
class RegistrationDetailItem:
    """登録結果の1ファイル分の内訳。

    Wireframes v11 Frame 1「登録完了サマリ」の詳細行・「既存#N を表示」リンク用。

    Attributes:
        filename: 登録対象ファイル名 (``Path.name``)。
        outcome: pHash 分類結果 (新規 / 別版 / 重複 / 失敗)。
        image_id: 関連付けられた画像 ID。DUPLICATE は既存 ID、VARIANT / REGISTERED は
            新規 ID。失敗時は ``None``。
    """

    filename: str
    outcome: RegistrationOutcome
    image_id: int | None


@dataclass
class DatabaseRegistrationResult:
    """データベース登録結果。

    ADR 0061 §4 (#633): pHash 分類結果を全経路統一の統計値に対応させる。
    ``variant_count`` は同一 pHash でも属性差で別版として新規登録された件数。
    ``directory`` / ``detail`` は Wireframes v11 Frame 1「登録完了サマリ」用。
    """

    registered_count: int
    skipped_count: int
    error_count: int
    processed_paths: list[Path]
    total_processing_time: float
    variant_count: int = 0
    directory: Path | None = None
    detail: list[RegistrationDetailItem] = field(default_factory=list)


class DatabaseRegistrationWorker(LoRAIroWorkerBase[DatabaseRegistrationResult]):
    """データベース登録専用ワーカー"""

    _OPERATION_TYPE = "registration"

    # #633: 登録 outcome → 統計キーの対応。重複は skipped、別版は variant に集計する。
    _OUTCOME_TO_STAT_KEY: ClassVar[dict[RegistrationOutcome, str]] = {
        RegistrationOutcome.REGISTERED: "registered",
        RegistrationOutcome.VARIANT: "variant",
        RegistrationOutcome.DUPLICATE: "skipped",
        RegistrationOutcome.FAILED: "errors",
    }

    def __init__(
        self, directory: Path, db_manager: "ImageDatabaseManager", fsm: "FileSystemManager"
    ) -> None:
        super().__init__(db_manager=db_manager)
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
            CancellationError: 処理がキャンセルされた場合
        """
        import time

        start_time = time.time()

        # 画像ファイル一覧取得
        self._report_progress(5, "画像ファイルを検索中...")
        image_files = list(self.fsm.get_image_files(self.directory))
        total_count = len(image_files)

        if total_count == 0:
            logger.warning(f"画像ファイルが見つかりません: {self.directory}")
            return DatabaseRegistrationResult(
                0, 0, 0, [], 0.0, variant_count=0, directory=self.directory, detail=[]
            )

        logger.info(f"登録対象画像: {total_count}件")

        # 関連ファイル(.txt/.caption)を事前読み込みし、タグIDを一括解決（N+1回避）
        self._report_progress(8, "関連アノテーションを解析中...")
        annotations_by_path = self._preload_associated_annotations(image_files)
        tag_id_cache = self._build_tag_id_cache(annotations_by_path)

        # 統計情報初期化 (#633: variant を追加し全経路統一)
        stats = {"registered": 0, "variant": 0, "skipped": 0, "errors": 0}
        processed_paths: list[Path] = []
        detail: list[RegistrationDetailItem] = []

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
                detail,
                annotations=annotations_by_path.get(image_path),
                tag_id_cache=tag_id_cache,
            )

        # 完了処理
        self._report_progress(100, "データベース登録完了")
        return self._build_registration_result(stats, processed_paths, detail, start_time)

    def _process_single_image_in_batch(
        self,
        image_path: Path,
        i: int,
        total_count: int,
        stats: dict[str, int],
        processed_paths: list[Path],
        detail: list[RegistrationDetailItem],
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
            detail: 1ファイル分の内訳を格納するリスト（in-place更新、登録完了サマリ用）。
            annotations: 事前読み込み済みのアノテーション。Noneの場合はその場で読み込む。
            tag_id_cache: 正規化済みタグ→tag_idのキャッシュ。
        """
        try:
            # 単一画像の登録処理 (統一エントリ経由で副作用は db_manager 側で適用)
            outcome, image_id = self._register_single_image(
                image_path, i, total_count, annotations=annotations, tag_id_cache=tag_id_cache
            )

            # 統計情報更新 (#633: outcome → 統計キーの対応を全経路で揃える)
            stat_key = self._OUTCOME_TO_STAT_KEY[outcome]
            stats[stat_key] += 1
            # 新規 / 別版はどちらも新規行を作るので processed として記録する
            if outcome in (RegistrationOutcome.REGISTERED, RegistrationOutcome.VARIANT):
                processed_paths.append(image_path)
            # 登録完了サマリ用に内訳を記録 (DUPLICATE=既存ID, VARIANT/REGISTERED=新規ID)
            resolved_id = image_id if image_id is not None and image_id >= 0 else None
            detail.append(RegistrationDetailItem(image_path.name, outcome, resolved_id))

        except Exception as e:
            stats["errors"] += 1
            detail.append(RegistrationDetailItem(image_path.name, RegistrationOutcome.FAILED, None))
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
    ) -> tuple[RegistrationOutcome, int]:
        """単一画像を統一登録エントリ経由で登録する (ADR 0061 §4, #633)。

        分類 (重複 / 別版 / 新規)・保存・関連ファイル取り込み・filename alias 登録は
        ``db_manager.register_image_with_side_effects`` が分類結果駆動で一元的に行う。
        ワーカーは進捗報告と outcome の返却のみを担当する。

        Args:
            image_path: 登録対象の画像ファイルパス
            i: 現在の処理インデックス（0始まり）
            total_count: 処理対象の総画像数
            annotations: 事前読み込み済みのアノテーション。
            tag_id_cache: 正規化済みタグ→tag_idのキャッシュ。

        Returns:
            tuple[RegistrationOutcome, int]: (outcome, image_id)。
                失敗時の image_id は -1。
        """
        force_progress_emit = i == 0 or i + 1 == total_count

        # バッチ進捗報告
        self._report_batch_progress_throttled(
            i + 1, total_count, image_path.name, force_emit=force_progress_emit
        )

        # 統一登録エントリ: 分類・保存・関連ファイル・alias を一元適用
        side_effect_result = self.db_manager.register_image_with_side_effects(
            image_path,
            self.fsm,
            associated_annotations=annotations,
            tag_id_cache=tag_id_cache,
        )
        outcome = side_effect_result.outcome
        image_id = side_effect_result.image_id if side_effect_result.image_id is not None else -1
        logger.debug(f"登録 outcome={outcome.value}: {image_path}")

        # 進捗報告（ProgressHelper使用）
        percentage = ProgressHelper.calculate_percentage(i + 1, total_count, 10, 85)  # 10-95%
        self._report_progress_throttled(
            percentage,
            f"登録中: {image_path.name}",
            current_item=str(image_path),
            processed_count=i + 1,
            total_count=total_count,
            force_emit=force_progress_emit,
        )

        return outcome, image_id

    def _build_registration_result(
        self,
        stats: dict[str, int],
        processed_paths: list[Path],
        detail: list[RegistrationDetailItem],
        start_time: float,
    ) -> DatabaseRegistrationResult:
        """登録結果オブジェクトを構築

        処理統計情報と経過時間から最終的な登録結果を構築し、
        サマリーログを出力する。

        Args:
            stats: 処理統計情報（registered, skipped, errors）
            processed_paths: 登録成功した画像パスのリスト
            detail: 1ファイル分の内訳のリスト（登録完了サマリ用）
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
            variant_count=stats["variant"],
            directory=self.directory,
            detail=detail,
        )

        # バッチサマリーログ（INFOレベル）
        logger.info(
            f"データベース登録完了: 登録={stats['registered']}, 別版={stats['variant']}, "
            f"スキップ={stats['skipped']}, エラー={stats['errors']}, 処理時間={processing_time:.2f}秒"
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
            cache = self.db_manager.annotation_repo.batch_resolve_tag_ids(all_tags)
            logger.info(
                f"タグID一括解決完了: {sum(1 for v in cache.values() if v is not None)}/"
                f"{len(all_tags)}件解決"
            )
            return cache
        except Exception as e:
            logger.warning(f"タグID一括解決に失敗、個別解決へフォールバック: {e}")
            return {}
