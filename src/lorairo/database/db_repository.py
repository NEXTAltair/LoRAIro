"""DBリポジトリ"""

import datetime
from collections.abc import Callable, Mapping
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
from .repository.annotation_record import AnnotationRepository
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
        # ADR 0035 段階 5 (#423): Annotation 書き込み + 外部 tag_db 統合は
        # `repository/annotation_record.py` の `AnnotationRepository` に移設。
        # 既存呼び出し (`image_repository.save_annotations()` 等) との互換性のため、
        # 本 facade は内部で AnnotationRepository への delegating wrapper を保持する。
        # 段階 6 で `manager.annotation_repo` 経由の直接参照に切り替わったあと、
        # 本 facade は legacy 互換のみ残し、最終的に削除可能。
        self._annotation_repo = AnnotationRepository(session_factory=session_factory)
        logger.info("ImageRepository initialized.")

        # ADR 0035 段階 5 (#423): tag_db 統合属性 (`merged_reader` /
        # `tag_register_service`) は AnnotationRepository が初期化を担当。
        # facade からの参照・書き換えは下記 `merged_reader` / `tag_register_service`
        # property で `_annotation_repo` への透過 delegation を行うため、
        # `__init__` 内で追加代入は不要 (warning ログは AnnotationRepository 側で出る)。

    @property
    def merged_reader(self) -> MergedTagReader | None:
        """``AnnotationRepository.merged_reader`` への透過参照 (ADR 0035 段階 5)。

        facade 経由で `merged_reader` を読み書きすると `_annotation_repo` 側の
        attribute を直接操作する。test fixture が `repo.merged_reader = mock`
        で外部 tag_db を差し替えるケースを drift なくサポートする。
        """
        return self._annotation_repo.merged_reader

    @merged_reader.setter
    def merged_reader(self, value: MergedTagReader | None) -> None:
        self._annotation_repo.merged_reader = value

    @property
    def tag_register_service(self) -> TagRegisterService | None:
        """``AnnotationRepository.tag_register_service`` への透過参照 (ADR 0035 段階 5)。

        `merged_reader` と同じく、test fixture が lazy-init を強制的に
        差し替えるケース (`repo.tag_register_service = None` 等) に対応する。
        """
        return self._annotation_repo.tag_register_service

    @tag_register_service.setter
    def tag_register_service(self, value: TagRegisterService | None) -> None:
        self._annotation_repo.tag_register_service = value

    # ADR 0035 段階 4 (#423, PR #488 Codex review P2 / P3):
    # `session_factory` および `BATCH_CHUNK_SIZE` をテストやランタイムで facade に
    # 書き戻すケース (例: `repository.session_factory = MagicMock(...)`) で、内部
    # delegating repos (`_image_repo` 等) の同名属性が古い snapshot のまま drift
    # しないように propagate する。__init__ 内で先に `_*_repo` が生成されている
    # 必要があるため、`__init__` の組み立て順 (session_factory → _model_repo →
    # _project_repo → _error_record_repo → _image_repo → _annotation_repo) を保つこと。
    _DELEGATED_REPO_ATTRS: ClassVar[tuple[str, ...]] = (
        "_model_repo",
        "_project_repo",
        "_error_record_repo",
        "_image_repo",
        "_annotation_repo",
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
        """``AnnotationRepository._initialize_merged_reader`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._initialize_merged_reader()

    def _initialize_tag_register_service(self) -> TagRegisterService | None:
        """``AnnotationRepository._initialize_tag_register_service`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._initialize_tag_register_service()

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
        """``AnnotationRepository.save_annotations`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.save_annotations(
            image_id=image_id,
            annotations=annotations,
            skip_existence_check=skip_existence_check,
            tag_id_cache=tag_id_cache,
        )

    @staticmethod
    def _build_existing_tags_map(session: Session, image_ids: list[int]) -> dict[int, set[str]]:
        """``AnnotationRepository._build_existing_tags_map`` への delegate (ADR 0035 段階 5)。"""
        return AnnotationRepository._build_existing_tags_map(session=session, image_ids=image_ids)

    def add_tag_to_images_batch(
        self,
        image_ids: list[int],
        tag: str,
        model_id: int | None,
    ) -> tuple[bool, int]:
        """``AnnotationRepository.add_tag_to_images_batch`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.add_tag_to_images_batch(
            image_ids=image_ids, tag=tag, model_id=model_id
        )

    def _get_or_create_tag_id_external(self, session: Session, tag_string: str) -> int | None:
        """``AnnotationRepository._get_or_create_tag_id_external`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._get_or_create_tag_id_external(session=session, tag_string=tag_string)

    def _register_new_tag(
        self,
        normalized_tag: str,
        source_tag: str,
        search_request: "TagSearchRequest",
    ) -> int | None:
        """``AnnotationRepository._register_new_tag`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._register_new_tag(
            normalized_tag=normalized_tag, source_tag=source_tag, search_request=search_request
        )

    def batch_resolve_tag_ids(self, normalized_tags: set[str]) -> dict[str, int | None]:
        """``AnnotationRepository.batch_resolve_tag_ids`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.batch_resolve_tag_ids(normalized_tags=normalized_tags)

    def _register_missing_tags(self, missing_tags: set[str], result: dict[str, int | None]) -> None:
        """``AnnotationRepository._register_missing_tags`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._register_missing_tags(missing_tags=missing_tags, result=result)

    def _register_single_tag(self, tag_str: str) -> int | None:
        """``AnnotationRepository._register_single_tag`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._register_single_tag(tag_str=tag_str)

    def _retry_tag_search(self, tag_str: str) -> int | None:
        """``AnnotationRepository._retry_tag_search`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._retry_tag_search(tag_str=tag_str)

    def _save_tags(
        self,
        session: Session,
        image_id: int,
        tags_data: list[TagAnnotationData],
        *,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """``AnnotationRepository._save_tags`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._save_tags(
            session=session, image_id=image_id, tags_data=tags_data, tag_id_cache=tag_id_cache
        )

    def _save_captions(
        self,
        session: Session,
        image_id: int,
        captions_data: list[CaptionAnnotationData],
    ) -> None:
        """``AnnotationRepository._save_captions`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._save_captions(
            session=session, image_id=image_id, captions_data=captions_data
        )

    def _save_scores(self, session: Session, image_id: int, scores_data: list[ScoreAnnotationData]) -> None:
        """``AnnotationRepository._save_scores`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._save_scores(
            session=session, image_id=image_id, scores_data=scores_data
        )

    def _save_score_labels(
        self,
        session: Session,
        image_id: int,
        score_labels_data: list[ScoreLabelAnnotationData],
    ) -> None:
        """``AnnotationRepository._save_score_labels`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._save_score_labels(
            session=session, image_id=image_id, score_labels_data=score_labels_data
        )

    def _save_ratings(
        self,
        session: Session,
        image_id: int,
        ratings_data: list[RatingAnnotationData],
    ) -> None:
        """``AnnotationRepository._save_ratings`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo._save_ratings(
            session=session, image_id=image_id, ratings_data=ratings_data
        )

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
        """``AnnotationRepository.update_manual_rating`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.update_manual_rating(image_id=image_id, rating=rating)

    def update_annotation_manual_edit_flag(
        self,
        annotation_type: str,
        annotation_id: int,
        is_edited: bool,
    ) -> bool:
        """``AnnotationRepository.update_annotation_manual_edit_flag`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.update_annotation_manual_edit_flag(
            annotation_type=annotation_type, annotation_id=annotation_id, is_edited=is_edited
        )

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
                        selectinload(ProviderBatchJob.model),
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

    def update_provider_batch_items_by_custom_id(
        self,
        job_id: int,
        updates_by_custom_id: Mapping[str, Mapping[str, Any]],
    ) -> set[str]:
        """job_id + custom_id ごとの Provider Batch API job item 更新を 1 transaction で反映する。"""
        for updates in updates_by_custom_id.values():
            invalid_fields = set(updates) - self.PROVIDER_BATCH_ITEM_UPDATE_FIELDS
            if invalid_fields:
                raise ValueError(f"更新できない provider batch item フィールド: {sorted(invalid_fields)}")
        if not updates_by_custom_id:
            return set()

        with self.session_factory() as session:
            try:
                updated_custom_ids: set[str] = set()
                for custom_id, updates in updates_by_custom_id.items():
                    if not updates:
                        continue
                    stmt = (
                        update(ProviderBatchItem)
                        .where(
                            ProviderBatchItem.job_id == job_id,
                            ProviderBatchItem.custom_id == custom_id,
                        )
                        .values(**dict(updates), updated_at=func.now())
                    )
                    result = cast(CursorResult[Any], session.execute(stmt))
                    if result.rowcount:
                        updated_custom_ids.add(custom_id)
                session.commit()
                return updated_custom_ids
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"Provider batch item 一括更新中にエラーが発生しました: {e}", exc_info=True)
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
        """``AnnotationRepository.update_rating_batch`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.update_rating_batch(
            image_ids=image_ids, rating=rating, model_id=model_id
        )

    def update_score_batch(
        self,
        image_ids: list[int],
        score: float,
        model_id: int | None,
    ) -> tuple[bool, int]:
        """``AnnotationRepository.update_score_batch`` への delegate (ADR 0035 段階 5)。"""
        return self._annotation_repo.update_score_batch(image_ids=image_ids, score=score, model_id=model_id)
