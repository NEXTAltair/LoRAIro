"""DBリポジトリ"""

import datetime
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, cast

from genai_tag_db_tools import search_tags
from genai_tag_db_tools.db.repository import MergedTagReader, get_default_reader
from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest
from genai_tag_db_tools.services.tag_register import TagRegisterService
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from sqlalchemy import Select, and_, delete, exists, func, not_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from ..domain.quality_tier import compute_quality_summary
from ..utils.log import logger
from .db_core import DefaultSessionLocal
from .filter_criteria import ImageFilterCriteria
from .repository.error_record import ErrorRecordRepository
from .repository.image import ImageRepository as _ImageRepositoryNew
from .repository.model import ModelRepository
from .repository.project import ProjectRepository
from .schema import (
    MANUAL_EDIT_LITELLM_ID,
    MANUAL_EDIT_NAME,
    Caption,
    ErrorRecord,
    Image,
    ImageFilenameAlias,
    Model,
    ProcessedImage,
    Project,
    ProviderBatchArtifact,
    ProviderBatchArtifactData,
    ProviderBatchItem,
    ProviderBatchItemData,
    ProviderBatchJob,
    ProviderBatchJobData,
    Rating,
    Score,
    ScoreLabel,
    Tag,
)
from .schema import (
    AnnotationsDict as AnnotationsDict,
)
from .schema import (
    CaptionAnnotationData as CaptionAnnotationData,
)
from .schema import (
    RatingAnnotationData as RatingAnnotationData,
)
from .schema import (
    ScoreAnnotationData as ScoreAnnotationData,
)
from .schema import (
    ScoreLabelAnnotationData as ScoreLabelAnnotationData,
)
from .schema import (
    TagAnnotationData as TagAnnotationData,
)


class ImageRepository:
    """画像関連エンティティのデータベース永続化を担当するクラス (SQLAlchemyベース)。
    CRUD操作と基本的な検索機能を提供します。
    """

    # SQLite バインド変数上限の安全マージン（32,766の約半分）
    # IN句以外にもクエリ内で変数を使うため余裕を持たせる
    BATCH_CHUNK_SIZE = 15000
    PROVIDER_BATCH_JOB_UPDATE_FIELDS: ClassVar[set[str]] = {
        "provider_job_id",
        "status",
        "provider_status",
        "endpoint",
        "model_id",
        "request_count",
        "succeeded_count",
        "failed_count",
        "canceled_count",
        "expired_count",
        "submitted_at",
        "completed_at",
        "canceled_at",
        "imported_at",
        "expires_at",
        "input_artifact_path",
        "output_artifact_path",
        "error_artifact_path",
        "raw_provider_payload",
    }
    PROVIDER_BATCH_ITEM_UPDATE_FIELDS: ClassVar[set[str]] = {
        "image_id",
        "model_id",
        "task_type",
        "status",
        "error_type",
        "error_message",
        "raw_request",
        "raw_response",
    }

    def __init__(self, session_factory: Callable[[], Session] = DefaultSessionLocal):
        """ImageRepositoryのコンストラクタ。

        Args:
            session_factory (Callable[[], Session]): SQLAlchemyセッションを生成するファクトリ関数。
                                                    デフォルトはdb_core.SessionLocalを使用。
                                                    テスト時にモック化可能。

        """
        self.session_factory = session_factory
        # ADR 0035 段階 1 (#423): Model 関連は ModelRepository に移設。
        # 既存呼び出し (`image_repository.get_models_by_litellm_ids()` 等) との互換性のため、
        # ImageRepository は内部で ModelRepository への delegating facade を保持する。
        # 段階 2 以降で各 Service / Worker が直接 ModelRepository を参照するようになれば、
        # 本 facade と _model_repo は削除可能。
        self._model_repo = ModelRepository(session_factory=session_factory)
        # ADR 0035 段階 2 (#423): Project 関連は ProjectRepository に移設。
        # 既存呼び出し (`image_repository.ensure_project()` 等) との互換性のため、
        # ImageRepository は内部で ProjectRepository への delegating facade を保持する。
        self._project_repo = ProjectRepository(session_factory=session_factory)
        # ADR 0035 段階 3 (#423): ErrorRecord 関連は ErrorRecordRepository に移設。
        # 既存呼び出し (`image_repository.save_error_record()` 等) との互換性のため、
        # ImageRepository は内部で ErrorRecordRepository への delegating facade を保持する。
        self._error_record_repo = ErrorRecordRepository(session_factory=session_factory)
        # ADR 0035 段階 4 (#423): Image / ProcessedImage / FilenameAlias は
        # `repository/image.py` の新 `ImageRepository` (`_ImageRepositoryNew`) に移設。
        # 既存呼び出し (`image_repository.add_original_image()` 等) との互換性のため、
        # 本 facade は内部で新 ImageRepository への delegating wrapper を保持する。
        # 段階 5 で `manager.image_repo` 経由の直接参照に切り替われば、本 facade は削除可能。
        self._image_repo = _ImageRepositoryNew(session_factory=session_factory)
        logger.info("ImageRepository initialized.")

        # 外部tag_db統合（公開API経由、グレースフルデグラデーション対応）
        # TagCleaner.clean_format()は静的メソッドなのでインスタンス化不要
        self.merged_reader = self._initialize_merged_reader()  # 失敗時はNoneで継続
        # TagRegisterServiceは遅延初期化（登録時のみ必要）
        self.tag_register_service: TagRegisterService | None = None

    # ADR 0035 段階 4 (#423, PR #488 Codex review P2 / P3):
    # `session_factory` および `BATCH_CHUNK_SIZE` をテストやランタイムで facade に
    # 書き戻すケース (例: `repository.session_factory = MagicMock(...)`) で、内部
    # delegating repos (`_image_repo` 等) の同名属性が古い snapshot のまま drift
    # しないように propagate する。__init__ 内で先に `_*_repo` が生成されている
    # 必要があるため、`__init__` の組み立て順 (session_factory → _model_repo →
    # _project_repo → _error_record_repo → _image_repo) を保つこと。
    _DELEGATED_REPO_ATTRS: ClassVar[tuple[str, ...]] = (
        "_model_repo",
        "_project_repo",
        "_error_record_repo",
        "_image_repo",
    )
    _PROPAGATED_ATTRS: ClassVar[frozenset[str]] = frozenset({"session_factory", "BATCH_CHUNK_SIZE"})

    def __setattr__(self, name: str, value: Any) -> None:
        """facade に書き戻された共有属性を内部 delegating repos に伝播する。

        `session_factory` / `BATCH_CHUNK_SIZE` は本クラス自身の動作 (stage 5
        領域の `save_annotations` / `update_*_batch` 等) と内部 `_image_repo`
        の両方で参照される。書き換え後の drift を防ぐため、本 `__setattr__` で
        透過的に propagate する。`_*_repo` 属性そのものを置き換える代入では
        propagate しない (循環を避ける目的)。
        """
        super().__setattr__(name, value)
        if name in self._PROPAGATED_ATTRS:
            for repo_attr in self._DELEGATED_REPO_ATTRS:
                repo = self.__dict__.get(repo_attr)
                if repo is not None:
                    object.__setattr__(repo, name, value)

    def _initialize_merged_reader(self) -> MergedTagReader | None:
        """外部タグDBリーダーを初期化（遅延初期化対応）。

        Returns:
            MergedTagReader | None: 初期化成功時はMergedTagReader、失敗時はNone。
                                   Noneの場合、外部タグDB機能は無効化され、tag_id=Noneで動作継続。

        Note:
            - 初期化失敗時はグレースフルデグラデーション（警告ログのみ、システム継続）
            - get_default_reader() はベースDBとユーザーDBの両方が無い場合にエラー
            - LoRAIroは外部タグDB無しでも動作可能（tag_id=None許容設計）

        """
        try:
            return get_default_reader()
        except Exception as e:
            logger.warning(
                f"Failed to initialize MergedTagReader (external tag DB unavailable): {e}. "
                "Tag operations will continue without external tag_id.",
            )
            return None

    def _initialize_tag_register_service(self) -> TagRegisterService | None:
        """タグ登録サービスを初期化（遅延初期化、Qt非依存）。

        Returns:
            TagRegisterService | None: 初期化成功時はTagRegisterService、失敗時はNone。
                                      Noneの場合、タグ登録機能は無効化され、検索のみ動作。

        Note:
            - MergedTagReaderが利用可能な場合のみ初期化
            - TagRegisterServiceはQt非依存で、CLI/ライブラリ/GUIで使用可能
            - 初期化失敗時はグレースフルデグラデーション（警告ログのみ、システム継続）

        """
        if self.merged_reader is None:
            logger.warning("MergedTagReader unavailable, cannot initialize TagRegisterService")
            return None

        try:
            return TagRegisterService(reader=self.merged_reader)
        except Exception as e:
            logger.warning(f"Failed to initialize TagRegisterService: {e}", exc_info=True)
            return None  # エラー時はNoneで継続

    # --- Model methods (delegating facade, ADR 0035 段階 1) ---
    # 実装は src/lorairo/database/repository/model.py の ModelRepository に移設済み。
    # 既存呼び出し (`image_repository.X()`) との互換性のため delegating wrapper を残す。
    # 段階 2 以降で各 Service / Worker が `manager.model_repo` 経由で直接 ModelRepository
    # を参照するようになれば、本 facade は削除可能。

    def _get_model_id(self, litellm_model_id: str) -> int | None:
        """ModelRepository._get_model_id への delegate (ADR 0035)。"""
        return self._model_repo._get_model_id(litellm_model_id)

    def get_model_by_litellm_id(self, litellm_model_id: str) -> Model | None:
        """ModelRepository.get_model_by_litellm_id への delegate (ADR 0035)。"""
        return self._model_repo.get_model_by_litellm_id(litellm_model_id)

    def get_models_by_name(self, name: str) -> list[Model]:
        """ModelRepository.get_models_by_name への delegate (ADR 0035)。"""
        return self._model_repo.get_models_by_name(name)

    def get_models_by_litellm_ids(self, litellm_model_ids: set[str]) -> dict[str, Model]:
        """ModelRepository.get_models_by_litellm_ids への delegate (ADR 0035)。"""
        return self._model_repo.get_models_by_litellm_ids(litellm_model_ids)

    def get_all_image_filename_index(self) -> dict[str, int]:
        """``_ImageRepositoryNew.get_all_image_filename_index`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_all_image_filename_index()

    def add_filename_alias(self, image_id: int, stem: str) -> None:
        """``_ImageRepositoryNew.add_filename_alias`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.add_filename_alias(image_id=image_id, stem=stem)

    def _get_or_create_manual_edit_model(self, session: Session) -> int:
        """ModelRepository._get_or_create_manual_edit_model への delegate (ADR 0035)。

        本メソッドは既存セッションを受け取って動作する (`session_factory` を使わない)。
        Image filter / annotation 更新など、呼び出し元が独自にセッションを管理する
        コンテキストから利用される。
        """
        return ModelRepository._get_or_create_manual_edit_model(session)

    def insert_model(
        self,
        name: str,
        provider: str | None,
        model_types: list[str],
        litellm_model_id: str,
        estimated_size_gb: float | None = None,
        requires_api_key: bool = False,
        discontinued_at: datetime.datetime | None = None,
    ) -> int:
        """ModelRepository.insert_model への delegate (ADR 0035)。"""
        return self._model_repo.insert_model(
            name=name,
            provider=provider,
            model_types=model_types,
            litellm_model_id=litellm_model_id,
            estimated_size_gb=estimated_size_gb,
            requires_api_key=requires_api_key,
            discontinued_at=discontinued_at,
        )

    @staticmethod
    def _apply_simple_field_updates(
        model: Any,
        provider: str | None,
        litellm_model_id: str | None,
        estimated_size_gb: float | None,
        requires_api_key: bool | None,
        discontinued_at: datetime.datetime | None,
    ) -> bool:
        """ModelRepository._apply_simple_field_updates への delegate (ADR 0035)。"""
        return ModelRepository._apply_simple_field_updates(
            model,
            provider,
            litellm_model_id,
            estimated_size_gb,
            requires_api_key,
            discontinued_at,
        )

    @staticmethod
    def _update_model_types(session: Session, model: Any, model_types: list[str]) -> bool:
        """ModelRepository._update_model_types への delegate (ADR 0035)。"""
        return ModelRepository._update_model_types(session, model, model_types)

    def update_model(
        self,
        model_id: int,
        provider: str | None = None,
        model_types: list[str] | None = None,
        litellm_model_id: str | None = None,
        estimated_size_gb: float | None = None,
        requires_api_key: bool | None = None,
        discontinued_at: datetime.datetime | None = None,
    ) -> bool:
        """ModelRepository.update_model への delegate (ADR 0035)。"""
        return self._model_repo.update_model(
            model_id=model_id,
            provider=provider,
            model_types=model_types,
            litellm_model_id=litellm_model_id,
            estimated_size_gb=estimated_size_gb,
            requires_api_key=requires_api_key,
            discontinued_at=discontinued_at,
        )

    def _image_exists(self, image_id: int) -> bool:
        """``_ImageRepositoryNew._image_exists`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._image_exists(image_id=image_id)

    def find_duplicate_image_by_phash(self, phash: str) -> int | None:
        """``_ImageRepositoryNew.find_duplicate_image_by_phash`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.find_duplicate_image_by_phash(phash=phash)

    def find_image_ids_by_phashes(self, phashes: set[str]) -> dict[str, int]:
        """``_ImageRepositoryNew.find_image_ids_by_phashes`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.find_image_ids_by_phashes(phashes=phashes)

    def get_annotated_image_ids(self, image_ids: list[int]) -> set[int]:
        """``_ImageRepositoryNew.get_annotated_image_ids`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_annotated_image_ids(image_ids=image_ids)

    def add_original_image(self, info: dict[str, Any]) -> int:
        """``_ImageRepositoryNew.add_original_image`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.add_original_image(info=info)

    def _find_existing_processed_image_id(
        self,
        image_id: int,
        width: int,
        height: int,
        filename: str | None,
    ) -> int | None:
        """``_ImageRepositoryNew._find_existing_processed_image_id`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._find_existing_processed_image_id(
            image_id=image_id, width=width, height=height, filename=filename
        )

    def add_processed_image(self, info: dict[str, Any]) -> int | None:
        """``_ImageRepositoryNew.add_processed_image`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.add_processed_image(info=info)

    # --- Annotation Saving Methods ---

    def save_annotations(
        self,
        image_id: int,
        annotations: AnnotationsDict,
        *,
        skip_existence_check: bool = False,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """指定された画像IDに対して、複数のアノテーションを一括で保存・更新します。

        各アノテーションタイプごとにUpsert処理を行います。

        Args:
            image_id: アノテーションを追加/更新する画像のID。
            annotations: 保存するアノテーションデータを含む辞書。
                キー: 'tags', 'captions', 'scores', 'ratings'
                値: 各アノテーションデータのリスト。
            skip_existence_check: Trueの場合、画像存在チェックをスキップする。
                バッチ処理等で事前に存在確認済みの場合に使用。
            tag_id_cache: 正規化済みタグ文字列→tag_idのキャッシュ辞書。
                バッチ処理で事前に一括解決済みのキャッシュを渡す。
                Noneの場合は従来通り個別に外部DB照会する。

        Raises:
            ValueError: 指定された image_id が存在しない場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not skip_existence_check and not self._image_exists(image_id):
            raise ValueError(f"指定された画像ID {image_id} は存在しません。")

        with self.session_factory() as session:
            try:
                # 各アノテーションタイプを処理
                if annotations.get("tags"):
                    self._save_tags(session, image_id, annotations["tags"], tag_id_cache=tag_id_cache)
                if annotations.get("captions"):
                    self._save_captions(session, image_id, annotations["captions"])
                if annotations.get("scores"):
                    self._save_scores(session, image_id, annotations["scores"])
                if annotations.get("score_labels"):
                    self._save_score_labels(session, image_id, annotations["score_labels"])
                if annotations.get("ratings"):
                    self._save_ratings(session, image_id, annotations["ratings"])

                session.commit()
                logger.debug(f"画像ID {image_id} のアノテーションを保存・更新しました。")

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"画像ID {image_id} のアノテーション保存中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    @staticmethod
    def _build_existing_tags_map(session: Session, image_ids: list[int]) -> dict[int, set[str]]:
        """画像IDごとの既存タグマップを構築する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 対象画像IDリスト。

        Returns:
            image_id -> タグ名(小文字)のセットのマッピング。

        """
        existing_tags_stmt = select(Tag).where(Tag.image_id.in_(image_ids))
        all_existing_tags = session.execute(existing_tags_stmt).scalars().all()

        existing_tags_by_image: dict[int, set[str]] = {}
        for tag_obj in all_existing_tags:
            if tag_obj.image_id is None:
                continue
            if tag_obj.image_id not in existing_tags_by_image:
                existing_tags_by_image[tag_obj.image_id] = set()
            existing_tags_by_image[tag_obj.image_id].add(tag_obj.tag.lower())
        return existing_tags_by_image

    def add_tag_to_images_batch(
        self,
        image_ids: list[int],
        tag: str,
        model_id: int | None,
    ) -> tuple[bool, int]:
        """複数画像に1つのタグを原子的に追加(既存タグに追加、重複スキップ)

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            tag: 追加するタグ(正規化済み前提: lower + strip)
            model_id: モデルID(手動編集の場合はマニュアルモデルID)

        Returns:
            (成功フラグ, 追加件数)

        Raises:
            SQLAlchemyError: データベースエラー時(ロールバック後に再送出)

        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch tag add")
            return (False, 0)

        if not tag.strip():
            logger.warning("Empty tag for batch add")
            return (False, 0)

        normalized_tag = tag.strip().lower()
        added_count = 0

        with self.session_factory() as session:
            try:
                existing_tags_by_image = self._build_existing_tags_map(session, image_ids)

                for image_id in image_ids:
                    existing_tags = existing_tags_by_image.get(image_id, set())

                    if normalized_tag in existing_tags:
                        logger.debug(
                            f"Tag '{normalized_tag}' already exists for image_id {image_id}, skipping",
                        )
                        continue

                    external_tag_id = self._get_or_create_tag_id_external(session, normalized_tag)
                    if external_tag_id is None and normalized_tag:
                        logger.warning(
                            f"Tag '{normalized_tag}' could not be linked to external tag_db. "
                            "Saving with tag_id=None.",
                        )

                    new_tag = Tag(
                        image_id=image_id,
                        model_id=model_id,
                        tag=normalized_tag,
                        tag_id=external_tag_id,
                        confidence_score=None,
                        existing=False,
                        is_edited_manually=True,
                    )
                    session.add(new_tag)
                    added_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch tag add completed: tag='{normalized_tag}', "
                    f"processed={len(image_ids)}, added={added_count}",
                )
                return (True, added_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Atomic batch tag add failed, rolled back: {e}", exc_info=True)
                raise

    def _get_or_create_tag_id_external(self, session: Session, tag_string: str) -> int | None:
        """外部 tag_db から tag 文字列に一致する tag_id を検索し、見つからない場合は新規作成する。

        Args:
            session: SQLAlchemy セッション (LoRAIro DB用、tag_db操作には未使用)。
            tag_string: 検索・登録するタグ文字列。

        Returns:
            見つかった/登録したtag_id。エラー時はNone。

        """
        # 1. タグの正規化（ExistingFileReaderと同一処理）
        normalized_tag = TagCleaner.clean_format(tag_string).strip()

        if not normalized_tag:
            logger.warning(f"Tag normalization resulted in empty string: '{tag_string}'")
            return None

        # 2. MergedTagReaderが利用可能か確認
        if self.merged_reader is None:
            logger.debug(
                f"MergedTagReader unavailable, skipping external tag search for '{normalized_tag}'",
            )
            return None

        logger.debug(f"Searching tag in external tag_db: '{tag_string}' → '{normalized_tag}'")

        # 3. 既存タグ検索（公開API search_tags()使用、完全一致）
        try:
            request = TagSearchRequest(
                query=normalized_tag,
                partial=False,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
            )
            result = search_tags(self.merged_reader, request)

            if result.items and len(result.items) > 0:
                tag_id: int = result.items[0].tag_id
                logger.debug(f"Found existing tag_id {tag_id} for '{normalized_tag}' in external tag_db")
                return tag_id

            # 検索結果なし → 新規タグ登録
            return self._register_new_tag(normalized_tag, tag_string, request)

        except Exception as e:
            logger.error(
                f"Error searching tag in external tag_db: '{normalized_tag}': {e}",
                exc_info=True,
            )
            return None  # 検索失敗時は縮退動作（tag_id=None で保存）  # その他のエラーも縮退動作

    def _register_new_tag(
        self,
        normalized_tag: str,
        source_tag: str,
        search_request: "TagSearchRequest",
    ) -> int | None:
        """外部tag_dbに新規タグを登録する。競合時はリトライ検索を行う。

        Args:
            normalized_tag: 正規化済みタグ文字列。
            source_tag: 元のタグ文字列。
            search_request: リトライ検索用のリクエストオブジェクト。

        Returns:
            登録されたtag_id。エラー時はNone。

        """
        logger.debug(f"Tag '{normalized_tag}' not found in external tag_db. Attempting registration...")

        # TagRegisterService遅延初期化
        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()
            if self.tag_register_service is None:
                logger.debug("TagRegisterService initialization failed, skipping tag registration")
                return None

        register_request = TagRegisterRequest(
            tag=normalized_tag,
            source_tag=source_tag,
            format_name="Lorairo",
            type_name="unknown",
        )

        try:
            register_result = self.tag_register_service.register_tag(register_request)
            tag_id = register_result.tag_id
            logger.debug(f"Registered new tag_id {tag_id} for '{normalized_tag}'")
            return cast("int | None", tag_id)
        except ValueError as ve:
            logger.error(f"Tag registration failed (invalid format/type): {ve}")
            return None
        except IntegrityError:
            # 競合検出（他のプロセスが同時に登録）→ リトライ
            logger.warning("Race condition detected during tag registration, retrying search...")
            try:
                retry_result = search_tags(self.merged_reader, search_request)
                if retry_result.items and len(retry_result.items) > 0:
                    tag_id = retry_result.items[0].tag_id
                    logger.debug(f"Found tag_id {tag_id} on retry for '{normalized_tag}'")
                    return cast("int | None", tag_id)
            except Exception as retry_error:
                logger.error(f"Retry search failed: {retry_error}", exc_info=True)
            return None
        except Exception as reg_error:
            logger.error(f"Unexpected error during tag registration: {reg_error}", exc_info=True)
            return None

    def batch_resolve_tag_ids(self, normalized_tags: set[str]) -> dict[str, int | None]:
        """正規化済みタグ文字列の集合に対して外部タグDBのtag_idを一括解決する。

        search_tags_bulk()で一括検索し、見つからなかったタグのみ個別登録する。
        deprecated=Trueのタグは除外し、現行の単発検索(include_deprecated=False)と同等の動作を保証する。

        Args:
            normalized_tags: TagCleaner.clean_format().strip()で正規化済みのタグ文字列セット。

        Returns:
            正規化済みタグ文字列→tag_id(またはNone)のマッピング辞書。

        """
        if not normalized_tags:
            return {}

        # MergedTagReaderが利用不可の場合は全てNone
        if self.merged_reader is None:
            logger.debug("MergedTagReader unavailable, skipping batch tag resolution")
            return dict.fromkeys(normalized_tags)

        # 一括検索
        try:
            bulk_results = self.merged_reader.search_tags_bulk(
                list(normalized_tags),
                format_name=None,
                resolve_preferred=False,
            )
        except Exception as e:
            logger.error(f"search_tags_bulk failed: {e}", exc_info=True)
            return dict.fromkeys(normalized_tags)

        # deprecated除外フィルタ適用（現行 include_deprecated=False と同等）
        result: dict[str, int | None] = {}
        for tag_str, row in bulk_results.items():
            if row.get("deprecated", False):
                logger.debug(f"Excluding deprecated tag from bulk result: '{tag_str}'")
                continue
            result[tag_str] = row["tag_id"]

        # 見つからなかったタグを個別登録
        missing_tags = normalized_tags - set(result.keys())
        if missing_tags:
            self._register_missing_tags(missing_tags, result)

        logger.info(
            f"Batch tag resolution complete: {len(result)} tags resolved, "
            f"{sum(1 for v in result.values() if v is not None)} with tag_id",
        )
        return result

    def _register_missing_tags(self, missing_tags: set[str], result: dict[str, int | None]) -> None:
        """バッチ検索で見つからなかったタグを個別登録する。

        Args:
            missing_tags: 登録が必要なタグ文字列のセット。
            result: 結果を格納する辞書（副作用で更新）。

        """
        logger.debug(f"Batch resolve: {len(missing_tags)} tags not found, attempting registration")

        # TagRegisterService遅延初期化
        if self.tag_register_service is None:
            self.tag_register_service = self._initialize_tag_register_service()

        if self.tag_register_service is None:
            # 初期化失敗 → 全てNone
            for tag_str in missing_tags:
                result[tag_str] = None
            return

        for tag_str in missing_tags:
            result[tag_str] = self._register_single_tag(tag_str)

    def _register_single_tag(self, tag_str: str) -> int | None:
        """単一タグを外部DBに登録し、tag_idを返す。

        競合検出時はリトライ検索を実行する。
        呼び出し元で self.tag_register_service is not None が保証されていること。

        Args:
            tag_str: 正規化済みタグ文字列。

        Returns:
            登録されたtag_id。失敗時はNone。

        """
        assert self.tag_register_service is not None
        try:
            register_request = TagRegisterRequest(
                tag=tag_str,
                source_tag=tag_str,
                format_name="Lorairo",
                type_name="unknown",
            )
            register_result = self.tag_register_service.register_tag(register_request)
            tag_id: int = register_result.tag_id
            logger.debug(f"Registered new tag_id {tag_id} for '{tag_str}'")
            return tag_id
        except IntegrityError:
            # 競合検出 → リトライ検索
            logger.warning(f"Race condition for '{tag_str}', retrying search...")
            return self._retry_tag_search(tag_str)
        except Exception as reg_error:
            logger.error(f"Tag registration failed for '{tag_str}': {reg_error}")
            return None

    def _retry_tag_search(self, tag_str: str) -> int | None:
        """競合検出後のリトライ検索。

        Args:
            tag_str: 検索するタグ文字列。

        Returns:
            見つかったtag_id。失敗時はNone。

        """
        try:
            retry_request = TagSearchRequest(
                query=tag_str,
                partial=False,
                resolve_preferred=False,
                include_aliases=True,
                include_deprecated=False,
            )
            retry_result = search_tags(self.merged_reader, retry_request)
            if retry_result.items:
                tag_id: int = retry_result.items[0].tag_id
                return tag_id
            return None
        except Exception as retry_error:
            logger.error(f"Retry search failed for '{tag_str}': {retry_error}")
            return None

    def _save_tags(
        self,
        session: Session,
        image_id: int,
        tags_data: list[TagAnnotationData],
        *,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """タグ情報を保存・更新 (Upsert)

        Args:
            session: SQLAlchemyセッション。
            image_id: 対象画像のID。
            tags_data: 保存するタグデータのリスト。
            tag_id_cache: 正規化済みタグ文字列→tag_idのキャッシュ。
                バッチ処理で事前解決済みの場合に渡す。キャッシュミス時は
                従来通り_get_or_create_tag_id_external()にフォールバック。

        """
        logger.debug(f"Saving/Updating {len(tags_data)} tags for image_id {image_id}")

        # 既存のタグを image_id と tag 文字列で取得 (効率化のため)
        existing_tags_stmt = select(Tag).where(Tag.image_id == image_id)
        existing_tags_result = session.execute(existing_tags_stmt).scalars().all()
        # (tag_string, model_id) をキーとする辞書を作成
        existing_tags_map = {(t.tag, t.model_id): t for t in existing_tags_result}

        for tag_info in tags_data:
            tag_string = tag_info["tag"]
            model_id = tag_info.get("model_id")  # Optional
            confidence = tag_info.get("confidence_score")  # Optional
            is_existing_tag = tag_info.get("existing", False)  # 元ファイル由来か

            # 外部DBから tag_id を取得/作成
            # 呼び出し元が設定済みの tag_id を優先し、未設定時はキャッシュ→個別照会の順
            external_tag_id: int | None = tag_info.get("tag_id")
            if external_tag_id is None:
                if tag_id_cache is not None:
                    normalized_key = TagCleaner.clean_format(tag_string).strip()
                    if normalized_key in tag_id_cache:
                        external_tag_id = tag_id_cache[normalized_key]
                    else:
                        # キャッシュミス: 従来の個別照会にフォールバック
                        external_tag_id = self._get_or_create_tag_id_external(session, tag_string)
                else:
                    external_tag_id = self._get_or_create_tag_id_external(session, tag_string)

            if external_tag_id is None and tag_string:
                logger.warning(
                    f"Tag '{tag_string}' could not be linked to external tag_db. "
                    "Saving with tag_id=None (limited taxonomy features).",
                )

            # 既存レコードを検索
            existing_record = existing_tags_map.get((tag_string, model_id))

            if existing_record:
                # 更新
                logger.debug(f"Updating existing tag: id={existing_record.id}, tag='{tag_string}'")
                existing_record.tag_id = external_tag_id
                existing_record.confidence_score = confidence
                existing_record.existing = is_existing_tag
                existing_record.is_edited_manually = tag_info.get("is_edited_manually")
            else:
                # 新規作成
                logger.debug(f"Adding new tag: tag='{tag_string}'")
                new_tag = Tag(
                    image_id=image_id,
                    model_id=model_id,
                    tag=tag_string,
                    tag_id=external_tag_id,
                    confidence_score=confidence,
                    existing=is_existing_tag,
                    is_edited_manually=tag_info.get("is_edited_manually"),
                )
                session.add(new_tag)
                existing_tags_map[(tag_string, model_id)] = new_tag

    def _save_captions(
        self,
        session: Session,
        image_id: int,
        captions_data: list[CaptionAnnotationData],
    ) -> None:
        """キャプション情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(captions_data)} captions for image_id {image_id}")

        # 既存キャプションを image_id で取得
        existing_captions_stmt = select(Caption).where(Caption.image_id == image_id)
        existing_captions_result = session.execute(existing_captions_stmt).scalars().all()
        # (caption_string, model_id) をキーとする辞書を作成
        existing_captions_map = {(c.caption, c.model_id): c for c in existing_captions_result}

        for caption_info in captions_data:
            caption_string = caption_info["caption"]
            model_id = caption_info.get("model_id")
            is_existing_caption = caption_info.get("existing", False)

            existing_record = existing_captions_map.get((caption_string, model_id))

            if existing_record:
                # 更新
                logger.debug(f"Updating existing caption: id={existing_record.id}")
                existing_record.existing = is_existing_caption
                existing_record.is_edited_manually = caption_info.get(
                    "is_edited_manually",
                )  # 渡された値を使用 (Nullable)
            else:
                # 新規作成
                logger.debug(f"Adding new caption: caption='{caption_string[:20]}...'")
                new_caption = Caption(
                    image_id=image_id,
                    model_id=model_id,
                    caption=caption_string,
                    existing=is_existing_caption,
                    is_edited_manually=caption_info.get("is_edited_manually"),
                )
                session.add(new_caption)
                existing_captions_map[(caption_string, model_id)] = new_caption

    def _save_scores(self, session: Session, image_id: int, scores_data: list[ScoreAnnotationData]) -> None:
        """スコア情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(scores_data)} scores for image_id {image_id}")

        # 既存スコアを image_id で取得
        existing_scores_stmt = select(Score).where(Score.image_id == image_id)
        existing_scores_result = session.execute(existing_scores_stmt).scalars().all()
        # model_id をキーとする辞書を作成 (同じ画像・モデルのスコアは1つのはず)
        existing_scores_map = {s.model_id: s for s in existing_scores_result}

        for score_info in scores_data:
            model_id = score_info["model_id"]
            score_value = score_info["score"]
            is_edited = score_info.get("is_edited_manually", False)

            existing_record = existing_scores_map.get(model_id)

            if existing_record:
                # 更新
                logger.debug(f"Updating existing score: id={existing_record.id}")
                existing_record.score = score_value
                existing_record.is_edited_manually = is_edited or False  # None → False
            else:
                # 新規作成
                logger.debug(f"Adding new score: model_id={model_id}, score={score_value}")
                new_score = Score(
                    image_id=image_id,
                    model_id=model_id,
                    score=score_value,
                    is_edited_manually=is_edited,  # 渡された値を使用
                )
                session.add(new_score)
                existing_scores_map[model_id] = new_score

    def _save_score_labels(
        self,
        session: Session,
        image_id: int,
        score_labels_data: list[ScoreLabelAnnotationData],
    ) -> None:
        """canonical scorer の score_label を保存・更新 (Upsert by model_id).

        ADR 0027 / iam-lib ADR 0002: aesthetic_shadow / cafe_aesthetic 等の
        canonical scorer は ``(image, model)`` 単位で単一 label を返す契約のため、
        ``_save_ratings`` と同じ ``model_id`` キーの Upsert pattern を採る。
        同一 model_id で複数 label が渡された場合は最後の値で確定する。
        """
        logger.debug(f"Saving/Updating {len(score_labels_data)} score_labels for image_id {image_id}")

        # 既存 score_label を image_id で取得
        existing_stmt = select(ScoreLabel).where(ScoreLabel.image_id == image_id)
        existing_records = session.execute(existing_stmt).scalars().all()
        existing_map: dict[int, ScoreLabel] = {r.model_id: r for r in existing_records}

        for label_info in score_labels_data:
            model_id = label_info["model_id"]
            label = label_info["label"]
            is_edited = label_info.get("is_edited_manually")

            existing_record = existing_map.get(model_id)

            if existing_record:
                logger.debug(f"Updating existing score_label: id={existing_record.id}")
                existing_record.label = label
                existing_record.is_edited_manually = is_edited
            else:
                logger.debug(f"Adding new score_label: model_id={model_id}, label='{label}'")
                new_record = ScoreLabel(
                    image_id=image_id,
                    model_id=model_id,
                    label=label,
                    is_edited_manually=is_edited,
                )
                session.add(new_record)
                existing_map[model_id] = new_record

    def _save_ratings(
        self,
        session: Session,
        image_id: int,
        ratings_data: list[RatingAnnotationData],
    ) -> None:
        """レーティング情報を保存・更新 (Upsert)"""
        logger.debug(f"Saving/Updating {len(ratings_data)} ratings for image_id {image_id}")

        # 既存レーティングを image_id で取得
        existing_ratings_stmt = select(Rating).where(Rating.image_id == image_id)
        existing_ratings_result = session.execute(existing_ratings_stmt).scalars().all()
        # model_id をキーとする辞書を作成 (同じ画像・モデルのレーティングは1つのはず)
        existing_ratings_map = {r.model_id: r for r in existing_ratings_result}

        for rating_info in ratings_data:
            model_id = rating_info["model_id"]  # 必須
            raw_value = rating_info["raw_rating_value"]
            norm_value = rating_info["normalized_rating"]
            confidence = rating_info.get("confidence_score")

            existing_record = existing_ratings_map.get(model_id)

            if existing_record:
                # 更新
                logger.debug(f"Updating existing rating: id={existing_record.id}")
                existing_record.raw_rating_value = raw_value
                existing_record.normalized_rating = norm_value
                existing_record.confidence_score = confidence
                # Rating には is_edited_manually はない
            else:
                # 新規作成
                logger.debug(f"Adding new rating: model_id={model_id}, rating={norm_value}")
                new_rating = Rating(
                    image_id=image_id,
                    model_id=model_id,
                    raw_rating_value=raw_value,
                    normalized_rating=norm_value,
                    confidence_score=confidence,
                )
                session.add(new_rating)
                existing_ratings_map[model_id] = new_rating

    # --- Data Retrieval Methods ---

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """``_ImageRepositoryNew.get_image_metadata`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_image_metadata(image_id=image_id)

    def get_images_metadata_batch(self, image_ids: list[int]) -> list[dict[str, Any]]:
        """``_ImageRepositoryNew.get_images_metadata_batch`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_images_metadata_batch(image_ids=image_ids)

    def get_batch_available_resolutions(self, image_ids: list[int]) -> dict[int, list[int]]:
        """``_ImageRepositoryNew.get_batch_available_resolutions`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_batch_available_resolutions(image_ids=image_ids)

    def get_processed_image(
        self,
        image_id: int,
        resolution: int = 0,
        all_data: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:  # 戻り値の型を調整
        """``_ImageRepositoryNew.get_processed_image`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_processed_image(
            image_id=image_id, resolution=resolution, all_data=all_data
        )

    def _filter_by_resolution(
        self,
        metadata_list: list[dict[str, Any]],
        resolution: int,
    ) -> dict[str, Any] | None:
        """``_ImageRepositoryNew._filter_by_resolution`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._filter_by_resolution(metadata_list=metadata_list, resolution=resolution)

    @staticmethod
    def _format_tag_annotation(tag: Any) -> dict[str, Any]:
        """``_ImageRepositoryNew._format_tag_annotation`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._format_tag_annotation(tag=tag)

    @staticmethod
    def _format_caption_annotation(caption: Any) -> dict[str, Any]:
        """``_ImageRepositoryNew._format_caption_annotation`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._format_caption_annotation(caption=caption)

    @staticmethod
    def _format_score_annotation(score: Any) -> dict[str, Any]:
        """``_ImageRepositoryNew._format_score_annotation`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._format_score_annotation(score=score)

    @staticmethod
    def _format_rating_annotation(rating: Any) -> dict[str, Any]:
        """``_ImageRepositoryNew._format_rating_annotation`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._format_rating_annotation(rating=rating)

    @staticmethod
    def _format_score_label_annotation(sl: Any) -> dict[str, Any]:
        """``_ImageRepositoryNew._format_score_label_annotation`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._format_score_label_annotation(sl=sl)

    def get_image_annotations(self, image_id: int) -> dict[str, Any]:
        """``_ImageRepositoryNew.get_image_annotations`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_image_annotations(image_id=image_id)

    def _parse_datetime_str(self, date_str: str | None) -> datetime.datetime | None:
        """``_ImageRepositoryNew._parse_datetime_str`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._parse_datetime_str(date_str=date_str)

    def _prepare_like_pattern(self, term: str) -> tuple[str, bool]:
        """``_ImageRepositoryNew._prepare_like_pattern`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._prepare_like_pattern(term=term)

    # --- Filtering Helper Methods ---

    def _apply_date_filter(
        self,
        query: Select[Any],
        start_dt: datetime.datetime | None,
        end_dt: datetime.datetime | None,
    ) -> Select[Any]:
        """``_ImageRepositoryNew._apply_date_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_date_filter(query=query, start_dt=start_dt, end_dt=end_dt)

    def _apply_tag_filter(
        self,
        query: Select[Any],
        tags: list[str] | None,
        excluded_tags: list[str] | None,
        use_and: bool,
        include_untagged: bool,
    ) -> Select[Any]:
        """``_ImageRepositoryNew._apply_tag_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_tag_filter(
            query=query,
            tags=tags,
            excluded_tags=excluded_tags,
            use_and=use_and,
            include_untagged=include_untagged,
        )

    def _apply_caption_filter(self, query: Select[Any], caption: str | None) -> Select[Any]:
        """``_ImageRepositoryNew._apply_caption_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_caption_filter(query=query, caption=caption)

    def _apply_ai_rating_filter(self, query: Select[Any], ai_rating_filter: str) -> Select[Any]:
        """``_ImageRepositoryNew._apply_ai_rating_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_ai_rating_filter(query=query, ai_rating_filter=ai_rating_filter)

    def _apply_unrated_filter(self, query: Select[Any], include_unrated: bool) -> Select[Any]:
        """``_ImageRepositoryNew._apply_unrated_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_unrated_filter(query=query, include_unrated=include_unrated)

    def _apply_nsfw_filter(self, query: Select[Any], include_nsfw: bool, session: Session) -> Select[Any]:
        """``_ImageRepositoryNew._apply_nsfw_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_nsfw_filter(query=query, include_nsfw=include_nsfw, session=session)

    def _apply_score_filter(
        self,
        query: Select[Any],
        score_min: float | None,
        score_max: float | None,
    ) -> Select[Any]:
        """``_ImageRepositoryNew._apply_score_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_score_filter(query=query, score_min=score_min, score_max=score_max)

    def _apply_manual_filters(
        self,
        query: Select[Any],
        manual_rating_filter: str | None,
        manual_edit_filter: bool | None,
        session: Session,
    ) -> Select[Any]:
        """``_ImageRepositoryNew._apply_manual_filters`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_manual_filters(
            query=query,
            manual_rating_filter=manual_rating_filter,
            manual_edit_filter=manual_edit_filter,
            session=session,
        )

    def _format_tags(self, image: Image, annotations: dict[str, Any]) -> None:
        """``_ImageRepositoryNew._format_tags`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._format_tags(image=image, annotations=annotations)

    def _format_captions(self, image: Image, annotations: dict[str, Any]) -> None:
        """``_ImageRepositoryNew._format_captions`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._format_captions(image=image, annotations=annotations)

    def _format_scores(self, image: Image, annotations: dict[str, Any]) -> None:
        """``_ImageRepositoryNew._format_scores`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._format_scores(image=image, annotations=annotations)

    def _format_score_labels(self, image: Image, annotations: dict[str, Any]) -> None:
        """``_ImageRepositoryNew._format_score_labels`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._format_score_labels(image=image, annotations=annotations)

    def _format_ratings(self, image: Image, annotations: dict[str, Any]) -> None:
        """``_ImageRepositoryNew._format_ratings`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._format_ratings(image=image, annotations=annotations)

    def _format_annotations_for_metadata(self, image: Image) -> dict[str, Any]:
        """``_ImageRepositoryNew._format_annotations_for_metadata`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._format_annotations_for_metadata(image=image)

    def _fetch_original_image_metadata(
        self,
        session: Session,
        image_ids: list[int],
    ) -> list[dict[str, Any]]:
        """``_ImageRepositoryNew._fetch_original_image_metadata`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._fetch_original_image_metadata(session=session, image_ids=image_ids)

    def _fetch_processed_image_metadata(
        self,
        session: Session,
        image_ids: list[int],
        resolution: int,
    ) -> list[dict[str, Any]]:
        """``_ImageRepositoryNew._fetch_processed_image_metadata`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._fetch_processed_image_metadata(
            session=session, image_ids=image_ids, resolution=resolution
        )

    def _fetch_filtered_metadata(
        self,
        session: Session,
        image_ids: list[int],
        resolution: int,
    ) -> list[dict[str, Any]]:
        """``_ImageRepositoryNew._fetch_filtered_metadata`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._fetch_filtered_metadata(
            session=session, image_ids=image_ids, resolution=resolution
        )

    def _apply_project_filter(
        self,
        query: Select[Any],
        project_name: str | None,
        project_id: int | None,
    ) -> Select[Any]:
        """``_ImageRepositoryNew._apply_project_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._apply_project_filter(
            query=query, project_name=project_name, project_id=project_id
        )

    # --- Project methods (delegating facade, ADR 0035 段階 2) ---
    # 実装は src/lorairo/database/repository/project.py の ProjectRepository に移設済み。
    # 既存呼び出し (`image_repository.ensure_project()` 等) との互換性のため delegating
    # wrapper を残す。段階 3 以降で各 Service / Worker が `manager.project_repo` 経由で
    # 直接 ProjectRepository を参照するようになれば、本 facade は削除可能。

    def ensure_project(self, name: str, path: Path, description: str = "") -> int:
        """ProjectRepository.ensure_project への delegate (ADR 0035 段階 2)。"""
        return self._project_repo.ensure_project(name, path, description)

    def get_image_ids_by_project(self, project_name: str) -> list[int]:
        """ProjectRepository.get_image_ids_by_project への delegate (ADR 0035 段階 2)。"""
        return self._project_repo.get_image_ids_by_project(project_name)

    def get_image_ids_by_project_id(self, project_id: int) -> list[int]:
        """ProjectRepository.get_image_ids_by_project_id への delegate (ADR 0035 段階 2)。"""
        return self._project_repo.get_image_ids_by_project_id(project_id)

    def assign_images_to_project(self, image_ids: list[int], project_id: int) -> int:
        """ProjectRepository.assign_images_to_project への delegate (ADR 0035 段階 2)。"""
        return self._project_repo.assign_images_to_project(image_ids, project_id)

    # --- Main Filter Method ---

    def _build_image_filter_query(
        self,
        session: Session,
        tags: list[str] | None,
        excluded_tags: list[str] | None,
        caption: str | None,
        use_and: bool,
        start_date: str | None,
        end_date: str | None,
        include_untagged: bool,
        include_nsfw: bool,
        include_unrated: bool,
        manual_rating_filter: str | None,
        ai_rating_filter: str | None,
        manual_edit_filter: bool | None,
        score_min: float | None = None,
        score_max: float | None = None,
        project_name: str | None = None,
        project_id: int | None = None,
    ) -> Select[Any]:
        """``_ImageRepositoryNew._build_image_filter_query`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._build_image_filter_query(
            session=session,
            tags=tags,
            excluded_tags=excluded_tags,
            caption=caption,
            use_and=use_and,
            start_date=start_date,
            end_date=end_date,
            include_untagged=include_untagged,
            include_nsfw=include_nsfw,
            include_unrated=include_unrated,
            manual_rating_filter=manual_rating_filter,
            ai_rating_filter=ai_rating_filter,
            manual_edit_filter=manual_edit_filter,
            score_min=score_min,
            score_max=score_max,
            project_name=project_name,
            project_id=project_id,
        )

    def get_images_by_filter(
        self,
        criteria: ImageFilterCriteria | None = None,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """``_ImageRepositoryNew.get_images_by_filter`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_images_by_filter(criteria=criteria, **kwargs)

    def get_images_count_only(
        self,
        criteria: ImageFilterCriteria | None = None,
        **kwargs: Any,
    ) -> int:
        """``_ImageRepositoryNew.get_images_count_only`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_images_count_only(criteria=criteria, **kwargs)

    # --- Model Information Retrieval (delegating facade, ADR 0035 段階 1) ---

    def get_models(self) -> list[dict[str, Any]]:
        """ModelRepository.get_models への delegate (ADR 0035)。"""
        return self._model_repo.get_models()

    def get_model_objects(self) -> list[Model]:
        """ModelRepository.get_model_objects への delegate (ADR 0035)。"""
        return self._model_repo.get_model_objects()

    def get_models_by_type(self, model_type_name: str) -> list[dict[str, Any]]:
        """ModelRepository.get_models_by_type への delegate (ADR 0035)。"""
        return self._model_repo.get_models_by_type(model_type_name)

    # --- Count Methods ---

    def get_total_image_count(self) -> int:
        """``_ImageRepositoryNew.get_total_image_count`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_total_image_count()

    # --- Update Methods (Manual Edits) ---

    def update_manual_rating(self, image_id: int, rating: str | None) -> bool:
        """指定された画像IDの手動レーティングを Rating テーブルに保存します。

        常に既存の MANUAL_EDIT レコードを削除してから INSERT する upsert 方式。
        rating=None の場合は削除のみ（解除）。手動レーティングは「現在値」のみ意味を持つため
        履歴を保持しない。詳細は ADR 0015 参照。

        Args:
            image_id (int): 更新する画像のID。
            rating (str | None): 新しいレーティング値 ('PG', 'R' など)。None で解除。

        Returns:
            bool: 更新が成功した場合はTrue、画像が見つからない場合はFalse。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        with self.session_factory() as session:
            try:
                image = session.get(Image, image_id)
                if image is None:
                    logger.warning(f"Manual rating の更新対象画像が見つかりません: image_id={image_id}")
                    return False

                manual_edit_model_id = self._get_or_create_manual_edit_model(session)

                session.execute(
                    delete(Rating).where(
                        Rating.image_id == image_id,
                        Rating.model_id == manual_edit_model_id,
                    )
                )
                if rating is not None:
                    session.add(
                        Rating(
                            image_id=image_id,
                            model_id=manual_edit_model_id,
                            raw_rating_value=rating,
                            normalized_rating=rating,
                            confidence_score=None,
                        )
                    )

                session.commit()
                logger.debug(f"画像ID {image_id} の manual_rating を '{rating}' に更新しました")
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"Manual rating の更新中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def update_annotation_manual_edit_flag(
        self,
        annotation_type: str,
        annotation_id: int,
        is_edited: bool,
    ) -> bool:
        """指定されたアノテーションの is_edited_manually フラグを更新します。

        Args:
            annotation_type (str): アノテーションのタイプ ('tags', 'captions', 'scores')。
            annotation_id (int): 更新するアノテーションのID。
            is_edited (bool): 設定する手動編集フラグの値。

        Returns:
            bool: 更新が成功した場合はTrue、アノテーションが見つからない場合はFalse。

        Raises:
            ValueError: サポートされていない annotation_type が指定された場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        model_map = {"tags": Tag, "captions": Caption, "scores": Score}
        if annotation_type not in model_map:
            raise ValueError(f"サポートされていないアノテーションタイプです: {annotation_type}")

        target_model = model_map[annotation_type]

        with self.session_factory() as session:
            try:
                stmt = (
                    update(target_model)
                    .where(target_model.__table__.c.id == annotation_id)
                    .values(is_edited_manually=is_edited)
                )
                result = cast("CursorResult[Any]", session.execute(stmt))
                if result.rowcount == 0:
                    logger.warning(
                        f"手動編集フラグの更新対象アノテーションが見つかりません: "
                        f"type={annotation_type}, id={annotation_id}",
                    )
                    return False
                session.commit()
                logger.info(
                    f"{annotation_type} ID {annotation_id} の is_edited_manually を {is_edited} に更新しました。",
                )
                return True
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"手動編集フラグの更新中にエラーが発生しました (Type: {annotation_type}, ID: {annotation_id}): {e}",
                    exc_info=True,
                )
                raise

    # --- Provider Batch Job Management Methods ---

    def create_provider_batch_job(self, data: ProviderBatchJobData) -> int:
        """Provider Batch API job を作成する。"""
        with self.session_factory() as session:
            try:
                job = ProviderBatchJob(**data)
                session.add(job)
                session.flush()
                job_id = job.id
                session.commit()
                logger.debug(
                    f"Provider batch job を作成しました: ID={job_id}, "
                    f"provider={job.provider}, status={job.status}",
                )
                return job_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch job 作成中にエラーが発生しました: {e}", exc_info=True)
                raise

    def create_provider_batch_job_with_items(
        self,
        job_data: ProviderBatchJobData,
        items_data: list[ProviderBatchItemData],
    ) -> int:
        """Provider Batch API job と item 群を単一 transaction で作成する。"""
        with self.session_factory() as session:
            try:
                job = ProviderBatchJob(**job_data)
                session.add(job)
                session.flush()
                job_id = job.id
                for item_data in items_data:
                    item_values = dict(item_data)
                    item_values["job_id"] = job_id
                    session.add(ProviderBatchItem(**item_values))
                session.commit()
                logger.debug(
                    f"Provider batch job/items を作成しました: ID={job_id}, "
                    f"provider={job.provider}, status={job.status}, items={len(items_data)}",
                )
                return job_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch job/items 作成中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_provider_batch_job(self, job_id: int) -> ProviderBatchJob | None:
        """Provider Batch API job を ID で取得する。"""
        with self.session_factory() as session:
            try:
                stmt = (
                    select(ProviderBatchJob)
                    .options(
                        selectinload(ProviderBatchJob.items),
                        selectinload(ProviderBatchJob.artifacts),
                    )
                    .where(ProviderBatchJob.id == job_id)
                )
                return session.execute(stmt).scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.error(f"Provider batch job 取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_provider_batch_job_by_provider_id(
        self,
        provider: str,
        provider_job_id: str,
    ) -> ProviderBatchJob | None:
        """provider と provider_job_id で Provider Batch API job を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = select(ProviderBatchJob).where(
                    ProviderBatchJob.provider == provider,
                    ProviderBatchJob.provider_job_id == provider_job_id,
                )
                return session.execute(stmt).scalar_one_or_none()
            except SQLAlchemyError as e:
                logger.error(
                    f"Provider batch job provider ID 取得中にエラーが発生しました: {e}", exc_info=True
                )
                raise

    def list_provider_batch_jobs(
        self,
        provider: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProviderBatchJob]:
        """Provider Batch API job 一覧を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = select(ProviderBatchJob).order_by(ProviderBatchJob.created_at.desc())
                if provider is not None:
                    stmt = stmt.where(ProviderBatchJob.provider == provider)
                if status is not None:
                    stmt = stmt.where(ProviderBatchJob.status == status)
                stmt = stmt.limit(limit).offset(offset)
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError as e:
                logger.error(f"Provider batch job 一覧取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def update_provider_batch_job(self, job_id: int, updates: dict[str, Any]) -> bool:
        """Provider Batch API job を更新する。許可フィールドのみ更新対象。"""
        invalid_fields = set(updates) - self.PROVIDER_BATCH_JOB_UPDATE_FIELDS
        if invalid_fields:
            raise ValueError(f"更新できない provider batch job フィールド: {sorted(invalid_fields)}")
        if not updates:
            return False

        with self.session_factory() as session:
            try:
                stmt = (
                    update(ProviderBatchJob)
                    .where(ProviderBatchJob.id == job_id)
                    .values(**updates, updated_at=func.now())
                )
                result = cast(CursorResult[Any], session.execute(stmt))
                session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch job 更新中にエラーが発生しました: {e}", exc_info=True)
                raise

    def delete_provider_batch_job(self, job_id: int) -> bool:
        """Provider Batch API job を削除する。items / artifacts は cascade される。"""
        with self.session_factory() as session:
            try:
                session.execute(delete(ProviderBatchArtifact).where(ProviderBatchArtifact.job_id == job_id))
                session.execute(delete(ProviderBatchItem).where(ProviderBatchItem.job_id == job_id))
                stmt = delete(ProviderBatchJob).where(ProviderBatchJob.id == job_id)
                result = cast(CursorResult[Any], session.execute(stmt))
                session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch job 削除中にエラーが発生しました: {e}", exc_info=True)
                raise

    def create_provider_batch_item(self, data: ProviderBatchItemData) -> int:
        """Provider Batch API job item を作成する。"""
        with self.session_factory() as session:
            try:
                item = ProviderBatchItem(**data)
                session.add(item)
                session.flush()
                item_id = item.id
                session.commit()
                return item_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch item 作成中にエラーが発生しました: {e}", exc_info=True)
                raise

    def list_provider_batch_items(
        self,
        job_id: int,
        status: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[ProviderBatchItem]:
        """Provider Batch API job item 一覧を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = (
                    select(ProviderBatchItem)
                    .where(ProviderBatchItem.job_id == job_id)
                    .order_by(ProviderBatchItem.id)
                )
                if status is not None:
                    stmt = stmt.where(ProviderBatchItem.status == status)
                stmt = stmt.limit(limit).offset(offset)
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError as e:
                logger.error(f"Provider batch item 一覧取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    def update_provider_batch_item_by_custom_id(
        self,
        job_id: int,
        custom_id: str,
        updates: dict[str, Any],
    ) -> bool:
        """job_id + custom_id で Provider Batch API job item を更新する。"""
        invalid_fields = set(updates) - self.PROVIDER_BATCH_ITEM_UPDATE_FIELDS
        if invalid_fields:
            raise ValueError(f"更新できない provider batch item フィールド: {sorted(invalid_fields)}")
        if not updates:
            return False

        with self.session_factory() as session:
            try:
                stmt = (
                    update(ProviderBatchItem)
                    .where(
                        ProviderBatchItem.job_id == job_id,
                        ProviderBatchItem.custom_id == custom_id,
                    )
                    .values(**updates, updated_at=func.now())
                )
                result = cast(CursorResult[Any], session.execute(stmt))
                session.commit()
                return bool(result.rowcount)
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch item 更新中にエラーが発生しました: {e}", exc_info=True)
                raise

    def create_provider_batch_artifact(self, data: ProviderBatchArtifactData) -> int:
        """Provider Batch API job artifact を作成する。"""
        with self.session_factory() as session:
            try:
                artifact = ProviderBatchArtifact(**data)
                session.add(artifact)
                session.flush()
                artifact_id = artifact.id
                session.commit()
                return artifact_id
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch artifact 作成中にエラーが発生しました: {e}", exc_info=True)
                raise

    def list_provider_batch_artifacts(
        self,
        job_id: int,
        artifact_type: str | None = None,
    ) -> list[ProviderBatchArtifact]:
        """Provider Batch API job artifact 一覧を取得する。"""
        with self.session_factory() as session:
            try:
                stmt = (
                    select(ProviderBatchArtifact)
                    .where(ProviderBatchArtifact.job_id == job_id)
                    .order_by(ProviderBatchArtifact.id)
                )
                if artifact_type is not None:
                    stmt = stmt.where(ProviderBatchArtifact.artifact_type == artifact_type)
                return list(session.execute(stmt).scalars().all())
            except SQLAlchemyError as e:
                logger.error(
                    f"Provider batch artifact 一覧取得中にエラーが発生しました: {e}", exc_info=True
                )
                raise

    # --- ErrorRecord methods (delegating facade, ADR 0035 段階 3) ---
    # 実装は src/lorairo/database/repository/error_record.py の ErrorRecordRepository に移設済み。
    # 既存呼び出し (`image_repository.save_error_record()` 等) との互換性のため delegating
    # wrapper を残す。段階 4 以降で各 Service / Worker が `manager.error_record_repo` 経由で
    # 直接 ErrorRecordRepository を参照するようになれば、本 facade は削除可能。
    #
    # NOTE: Manager 層 (`ImageDatabaseManager.save_error_record`) の二次エラー防止
    # (sentinel `-1` return) は本 facade ではなく Manager 側で維持する (PR #476)。

    def save_error_record(
        self,
        operation_type: str,
        error_type: str,
        error_message: str,
        image_id: int | None = None,
        stack_trace: str | None = None,
        file_path: str | None = None,
        model_name: str | None = None,
    ) -> int:
        """ErrorRecordRepository.save_error_record への delegate (ADR 0035 段階 3)。"""
        return self._error_record_repo.save_error_record(
            operation_type=operation_type,
            error_type=error_type,
            error_message=error_message,
            image_id=image_id,
            stack_trace=stack_trace,
            file_path=file_path,
            model_name=model_name,
        )

    def get_error_count_unresolved(self, operation_type: str | None = None) -> int:
        """ErrorRecordRepository.get_error_count_unresolved への delegate (ADR 0035 段階 3)。"""
        return self._error_record_repo.get_error_count_unresolved(operation_type)

    def get_error_image_ids(
        self,
        operation_type: str | None = None,
        resolved: bool = False,
        error_types: list[str] | None = None,
    ) -> list[int]:
        """ErrorRecordRepository.get_error_image_ids への delegate (ADR 0035 段階 3)。"""
        return self._error_record_repo.get_error_image_ids(
            operation_type=operation_type,
            resolved=resolved,
            error_types=error_types,
        )

    def get_images_by_ids(self, image_ids: list[int]) -> list[dict[str, Any]]:
        """``_ImageRepositoryNew.get_images_by_ids`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_images_by_ids(image_ids=image_ids)

    def get_error_records(
        self,
        operation_type: str | None = None,
        resolved: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ErrorRecord]:
        """ErrorRecordRepository.get_error_records への delegate (ADR 0035 段階 3)。"""
        return self._error_record_repo.get_error_records(
            operation_type=operation_type,
            resolved=resolved,
            limit=limit,
            offset=offset,
        )

    def mark_error_resolved(self, error_id: int) -> None:
        """ErrorRecordRepository.mark_error_resolved への delegate (ADR 0035 段階 3)。"""
        self._error_record_repo.mark_error_resolved(error_id)

    def mark_errors_resolved_batch(self, error_ids: list[int]) -> tuple[bool, int]:
        """ErrorRecordRepository.mark_errors_resolved_batch への delegate (ADR 0035 段階 3)。"""
        return self._error_record_repo.mark_errors_resolved_batch(error_ids)

    def get_session(self) -> Session:
        """セッションを取得（Manager層で生SQLを実行する際に使用）

        Returns:
            Session: SQLAlchemyセッション

        """
        return self.session_factory()

    def get_image_id_by_filepath(self, filepath: str) -> int | None:
        """``_ImageRepositoryNew.get_image_id_by_filepath`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_image_id_by_filepath(filepath=filepath)

    @staticmethod
    def _normalize_input_paths(filepaths: list[str]) -> tuple[dict[str, Path], set[str]]:
        """``_ImageRepositoryNew._normalize_input_paths`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._normalize_input_paths(filepaths=filepaths)

    def _build_candidates_by_filename(
        self, candidates: list[Image]
    ) -> dict[str, list[tuple[Path, int, str]]]:
        """``_ImageRepositoryNew._build_candidates_by_filename`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo._build_candidates_by_filename(candidates=candidates)

    @staticmethod
    def _safe_resolve_stored_path(image_id: int, stored_image_path: str) -> Path | None:
        """``_ImageRepositoryNew._safe_resolve_stored_path`` への delegate (ADR 0035 段階 4)。"""
        return _ImageRepositoryNew._safe_resolve_stored_path(
            image_id=image_id, stored_image_path=stored_image_path
        )

    def get_image_ids_by_filepaths(self, filepaths: list[str]) -> dict[str, int | None]:
        """``_ImageRepositoryNew.get_image_ids_by_filepaths`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_image_ids_by_filepaths(filepaths=filepaths)

    def get_phashes_by_filepaths(self, filepaths: list[str]) -> dict[str, str | None]:
        """``_ImageRepositoryNew.get_phashes_by_filepaths`` への delegate (ADR 0035 段階 4)。"""
        return self._image_repo.get_phashes_by_filepaths(filepaths=filepaths)

    def update_rating_batch(
        self,
        image_ids: list[int],
        rating: str,
        model_id: int,
    ) -> tuple[bool, int]:
        """複数画像のRatingを原子的に更新（既存レコードは更新、なければ挿入）

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            rating: Rating値（正規化済み: "PG", "PG-13", "R", "X", "XXX"）
            model_id: モデルID（手動編集の場合はマニュアルモデルID）

        Returns:
            (成功フラグ, 更新件数)

        Raises:
            SQLAlchemyError: データベースエラー時（ロールバック後に再送出）
        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch rating update")
            return (False, 0)

        if not rating.strip():
            logger.warning("Empty rating for batch update")
            return (False, 0)

        normalized_rating = rating.strip()
        updated_count = 0

        with self.session_factory() as session:
            try:
                # 既存の Rating レコードを一括取得（N+1回避）
                existing_ratings_stmt = select(Rating).where(Rating.image_id.in_(image_ids))
                existing_ratings = session.execute(existing_ratings_stmt).scalars().all()
                existing_rating_map = {r.image_id: r for r in existing_ratings}

                for image_id in image_ids:
                    if image_id in existing_rating_map:
                        # 既存レコードを UPDATE
                        existing_rating = existing_rating_map[image_id]
                        existing_rating.normalized_rating = normalized_rating
                        existing_rating.raw_rating_value = normalized_rating
                        existing_rating.model_id = model_id
                        existing_rating.confidence_score = None  # 手動編集時は信頼度なし
                        existing_rating.updated_at = func.now()
                        logger.debug(f"Updated rating for image_id {image_id}")
                    else:
                        # 新規レコードを INSERT
                        new_rating = Rating(
                            image_id=image_id,
                            model_id=model_id,
                            raw_rating_value=normalized_rating,
                            normalized_rating=normalized_rating,
                            confidence_score=None,
                        )
                        session.add(new_rating)
                        logger.debug(f"Inserted new rating for image_id {image_id}")

                    updated_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch rating update completed: rating='{normalized_rating}', "
                    f"processed={len(image_ids)}, updated={updated_count}",
                )
                return (True, updated_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"Batch rating update failed: rating='{normalized_rating}', "
                    f"image_ids={len(image_ids)}, error={e}",
                    exc_info=True,
                )
                raise

    def update_score_batch(
        self,
        image_ids: list[int],
        score: float,
        model_id: int | None,
    ) -> tuple[bool, int]:
        """複数画像のScoreを原子的に更新（既存レコードは更新、なければ挿入）

        単一トランザクションで全画像を処理。全件成功 or 全件ロールバック。

        Args:
            image_ids: 対象画像のIDリスト
            score: Score値（DB値 0.0-10.0）
            model_id: モデルID（手動編集の場合はマニュアルモデルID、Noneも許容）

        Returns:
            (成功フラグ, 更新件数)

        Raises:
            SQLAlchemyError: データベースエラー時（ロールバック後に再送出）
        """
        if not image_ids:
            logger.warning("Empty image_ids list for batch score update")
            return (False, 0)

        if not (0.0 <= score <= 10.0):
            logger.warning(f"Invalid score value for batch update: {score}")
            return (False, 0)

        updated_count = 0

        with self.session_factory() as session:
            try:
                # 既存の Score レコードを一括取得（N+1回避）
                existing_scores_stmt = select(Score).where(Score.image_id.in_(image_ids))
                existing_scores = session.execute(existing_scores_stmt).scalars().all()
                existing_score_map = {s.image_id: s for s in existing_scores}

                for image_id in image_ids:
                    if image_id in existing_score_map:
                        # 既存レコードを UPDATE
                        existing_score = existing_score_map[image_id]
                        existing_score.score = score
                        existing_score.model_id = model_id
                        existing_score.is_edited_manually = True
                        existing_score.updated_at = func.now()
                        logger.debug(f"Updated score for image_id {image_id}")
                    else:
                        # 新規レコードを INSERT
                        new_score = Score(
                            image_id=image_id,
                            model_id=model_id,
                            score=score,
                            is_edited_manually=True,
                        )
                        session.add(new_score)
                        logger.debug(f"Inserted new score for image_id {image_id}")

                    updated_count += 1

                session.commit()

                logger.info(
                    f"Atomic batch score update completed: score={score:.2f}, "
                    f"processed={len(image_ids)}, updated={updated_count}",
                )
                return (True, updated_count)

            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"Batch score update failed: score={score:.2f}, image_ids={len(image_ids)}, error={e}",
                    exc_info=True,
                )
                raise
