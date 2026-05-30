"""OpenAI moderation preflight for WebAPI annotation sends."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.exc import IntegrityError

from lorairo.database.repository.error_record import ErrorRecordRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.model import ModelRepository
from lorairo.services.annotation_save_service import AnnotationSaveResult, AnnotationSaveService
from lorairo.services.configuration_service import ConfigurationService
from lorairo.utils.log import logger

MODERATION_LITELLM_MODEL_ID = "openai/omni-moderation-latest"
MODERATION_PROVIDER = "openai"
MODERATION_ERROR_TYPE_MISSING_KEY = "moderation_preflight_missing_openai_key"
MODERATION_ERROR_TYPE_FAILED = "moderation_preflight_failed"
MODERATION_ERROR_TYPE_NO_RATING = "moderation_preflight_no_rating"
MODERATION_ERROR_TYPE_BLOCKED = "moderation_preflight_blocked"


class ModerationRunner(Protocol):
    """Callable boundary for running a single moderation model over image paths."""

    def __call__(
        self,
        *,
        image_paths: list[str],
        litellm_model_ids: list[str],
        phash_list: list[str] | None = None,
    ) -> Any: ...


@dataclass(frozen=True)
class ModerationPreflightSkip:
    """Per-image moderation preflight skip reason."""

    image_path: str
    image_id: int | None
    reason: str
    message: str


@dataclass(frozen=True)
class ModerationPreflightResult:
    """Summary of filtering candidates before WebAPI annotation."""

    allowed_paths: list[str]
    skipped: list[ModerationPreflightSkip] = field(default_factory=list)
    moderated_count: int = 0
    existing_rating_allowed_count: int = 0
    existing_rating_blocked_count: int = 0
    unknown_path_count: int = 0
    failure_count: int = 0

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


class ModerationPreflightService:
    """Run moderation for unrated images before WebAPI annotation."""

    _ALLOW_RATINGS = frozenset({"PG", "PG-13", "R"})
    _BLOCK_RATINGS = frozenset({"X", "XXX"})

    def __init__(
        self,
        *,
        image_repo: ImageRepository,
        model_repo: ModelRepository,
        error_record_repo: ErrorRecordRepository,
        annotation_save_service: AnnotationSaveService,
        config_service: ConfigurationService,
        moderation_runner: ModerationRunner,
    ) -> None:
        self._image_repo = image_repo
        self._model_repo = model_repo
        self._error_record_repo = error_record_repo
        self._annotation_save_service = annotation_save_service
        self._config_service = config_service
        self._moderation_runner = moderation_runner

    def apply(self, image_paths: list[str]) -> ModerationPreflightResult:
        """Return image paths that may proceed to WebAPI annotation."""
        if not image_paths:
            return ModerationPreflightResult(allowed_paths=[])

        path_to_image_id = self._image_repo.get_image_ids_by_filepaths(image_paths)
        known_ids = [image_id for image_id in set(path_to_image_id.values()) if image_id is not None]
        latest_rating_map = (
            self._image_repo.get_latest_normalized_ratings_by_image_ids(known_ids) if known_ids else {}
        )

        allowed_paths: list[str] = []
        preflight_paths: list[str] = []
        skipped: list[ModerationPreflightSkip] = []
        existing_allowed = 0
        existing_blocked = 0
        unknown_paths = 0

        for image_path in image_paths:
            image_id = path_to_image_id.get(image_path)
            if image_id is None:
                allowed_paths.append(image_path)
                unknown_paths += 1
                continue

            normalized = self._normalize_rating(latest_rating_map.get(image_id))
            if normalized in self._BLOCK_RATINGS:
                skipped.append(
                    self._record_skip(
                        image_path=image_path,
                        image_id=image_id,
                        reason=MODERATION_ERROR_TYPE_BLOCKED,
                        message=f"latest rating blocks WebAPI annotation: {normalized}",
                    )
                )
                existing_blocked += 1
            elif normalized in self._ALLOW_RATINGS:
                allowed_paths.append(image_path)
                existing_allowed += 1
            else:
                preflight_paths.append(image_path)

        if preflight_paths:
            preflight_result = self._moderate_unrated_paths(preflight_paths, path_to_image_id)
            preflight_allowed = set(preflight_result.allowed_paths)
            allowed_paths.extend(path for path in preflight_paths if path in preflight_allowed)
            skipped.extend(preflight_result.skipped)
            moderated_count = preflight_result.moderated_count
            failure_count = preflight_result.failure_count
        else:
            moderated_count = 0
            failure_count = 0

        if skipped:
            logger.info(
                f"moderation preflight: allowed={len(allowed_paths)} skipped={len(skipped)} "
                f"moderated={moderated_count}"
            )

        return ModerationPreflightResult(
            allowed_paths=allowed_paths,
            skipped=skipped,
            moderated_count=moderated_count,
            existing_rating_allowed_count=existing_allowed,
            existing_rating_blocked_count=existing_blocked,
            unknown_path_count=unknown_paths,
            failure_count=failure_count,
        )

    @staticmethod
    def _normalize_rating(value: str | None) -> str | None:
        return value.strip().upper() if isinstance(value, str) and value.strip() else None

    def _moderate_unrated_paths(
        self,
        image_paths: list[str],
        path_to_image_id: Mapping[str, int | None],
    ) -> ModerationPreflightResult:
        missing_key = self._missing_openai_key()
        if missing_key is not None:
            skipped = [
                self._record_skip(
                    image_path=path,
                    image_id=path_to_image_id.get(path),
                    reason=MODERATION_ERROR_TYPE_MISSING_KEY,
                    message=missing_key,
                )
                for path in image_paths
            ]
            return ModerationPreflightResult(
                allowed_paths=[],
                skipped=skipped,
                failure_count=len(skipped),
            )

        try:
            model_id = self._ensure_moderation_model_id()
            phash_list = self._build_phash_list(image_paths)
        except Exception as exc:
            message = f"moderation preflight setup failed: {exc}"
            logger.warning(message, exc_info=True)
            skipped = [
                self._record_skip(
                    image_path=path,
                    image_id=path_to_image_id.get(path),
                    reason=MODERATION_ERROR_TYPE_FAILED,
                    message=message,
                )
                for path in image_paths
            ]
            return ModerationPreflightResult(
                allowed_paths=[],
                skipped=skipped,
                failure_count=len(skipped),
            )
        if phash_list is None:
            skipped = [
                self._record_skip(
                    image_path=path,
                    image_id=path_to_image_id.get(path),
                    reason=MODERATION_ERROR_TYPE_FAILED,
                    message="moderation preflight could not resolve registered pHash",
                )
                for path in image_paths
            ]
            return ModerationPreflightResult(
                allowed_paths=[],
                skipped=skipped,
                failure_count=len(skipped),
            )

        try:
            results = self._moderation_runner(
                image_paths=image_paths,
                litellm_model_ids=[MODERATION_LITELLM_MODEL_ID],
                phash_list=phash_list,
            )
            save_result = self._annotation_save_service.save_annotation_results(results)
        except Exception as exc:
            logger.warning(
                f"moderation preflight batch failed; retrying per image: {exc}",
                exc_info=True,
            )
            return self._moderate_unrated_paths_individually(
                image_paths=image_paths,
                path_to_image_id=path_to_image_id,
                phash_list=phash_list,
            )

        logger.debug(
            f"moderation preflight saved ratings with model_id={model_id}: "
            f"success={save_result.success_count} skip={save_result.skip_count} error={save_result.error_count}"
        )
        return self._decide_after_moderation(
            image_paths=image_paths,
            path_to_image_id=path_to_image_id,
            save_result=save_result,
        )

    def _moderate_unrated_paths_individually(
        self,
        *,
        image_paths: list[str],
        path_to_image_id: Mapping[str, int | None],
        phash_list: list[str],
    ) -> ModerationPreflightResult:
        allowed_paths: list[str] = []
        skipped: list[ModerationPreflightSkip] = []
        failure_count = 0

        for image_path, phash in zip(image_paths, phash_list, strict=True):
            try:
                results = self._moderation_runner(
                    image_paths=[image_path],
                    litellm_model_ids=[MODERATION_LITELLM_MODEL_ID],
                    phash_list=[phash],
                )
                save_result = self._annotation_save_service.save_annotation_results(results)
                decision = self._decide_after_moderation(
                    image_paths=[image_path],
                    path_to_image_id=path_to_image_id,
                    save_result=save_result,
                )
            except Exception as exc:
                message = f"moderation preflight failed: {exc}"
                logger.warning(message, exc_info=True)
                skipped.append(
                    self._record_skip(
                        image_path=image_path,
                        image_id=path_to_image_id.get(image_path),
                        reason=MODERATION_ERROR_TYPE_FAILED,
                        message=message,
                    )
                )
                failure_count += 1
                continue

            allowed_paths.extend(decision.allowed_paths)
            skipped.extend(decision.skipped)
            failure_count += decision.failure_count

        return ModerationPreflightResult(
            allowed_paths=allowed_paths,
            skipped=skipped,
            moderated_count=len(image_paths),
            failure_count=failure_count,
        )

    def _missing_openai_key(self) -> str | None:
        try:
            key = self._config_service.get_setting("api", "openai_key", "")
        except Exception as exc:
            return f"OpenAI API key lookup failed for moderation preflight: {exc}"
        if isinstance(key, str) and key.strip():
            return None
        return "OpenAI API key is required for moderation preflight"

    def _ensure_moderation_model_id(self) -> int:
        existing = self._model_repo.get_model_by_litellm_id(MODERATION_LITELLM_MODEL_ID)
        if existing is not None:
            return int(existing.id)

        try:
            return self._model_repo.insert_model(
                name=MODERATION_LITELLM_MODEL_ID,
                provider=MODERATION_PROVIDER,
                model_types=["ratings"],
                litellm_model_id=MODERATION_LITELLM_MODEL_ID,
                requires_api_key=True,
            )
        except IntegrityError:
            existing = self._model_repo.get_model_by_litellm_id(MODERATION_LITELLM_MODEL_ID)
            if existing is not None:
                return int(existing.id)
            raise

    def _build_phash_list(self, image_paths: list[str]) -> list[str] | None:
        path_to_phash = self._image_repo.get_phashes_by_filepaths(image_paths)
        phashes = [path_to_phash.get(path) for path in image_paths]
        if any(phash is None for phash in phashes):
            return None
        return [str(phash) for phash in phashes]

    def _decide_after_moderation(
        self,
        *,
        image_paths: list[str],
        path_to_image_id: Mapping[str, int | None],
        save_result: AnnotationSaveResult,
    ) -> ModerationPreflightResult:
        image_ids = [image_id for image_id in path_to_image_id.values() if image_id is not None]
        latest = self._image_repo.get_latest_normalized_ratings_by_image_ids(list(set(image_ids)))

        allowed_paths: list[str] = []
        skipped: list[ModerationPreflightSkip] = []
        for image_path in image_paths:
            image_id = path_to_image_id.get(image_path)
            normalized = self._normalize_rating(latest.get(image_id)) if image_id is not None else None
            if normalized in self._BLOCK_RATINGS:
                skipped.append(
                    self._record_skip(
                        image_path=image_path,
                        image_id=image_id,
                        reason=MODERATION_ERROR_TYPE_BLOCKED,
                        message=f"moderation rating blocks WebAPI annotation: {normalized}",
                    )
                )
            elif normalized in self._ALLOW_RATINGS:
                allowed_paths.append(image_path)
            else:
                skipped.append(
                    self._record_skip(
                        image_path=image_path,
                        image_id=image_id,
                        reason=MODERATION_ERROR_TYPE_NO_RATING,
                        message="moderation preflight did not produce a usable saved rating",
                    )
                )

        failure_count = save_result.error_count + sum(
            1 for skip in skipped if skip.reason == MODERATION_ERROR_TYPE_NO_RATING
        )
        return ModerationPreflightResult(
            allowed_paths=allowed_paths,
            skipped=skipped,
            moderated_count=len(image_paths),
            failure_count=failure_count,
        )

    def _record_skip(
        self,
        *,
        image_path: str,
        image_id: int | None,
        reason: str,
        message: str,
    ) -> ModerationPreflightSkip:
        try:
            self._error_record_repo.save_error_record(
                operation_type="annotation",
                error_type=reason,
                error_message=message,
                image_id=image_id,
                file_path=image_path,
                model_name=MODERATION_LITELLM_MODEL_ID,
            )
        except Exception:
            logger.warning(
                f"moderation preflight skip reason could not be saved: path={image_path}",
                exc_info=True,
            )
        return ModerationPreflightSkip(
            image_path=image_path,
            image_id=image_id,
            reason=reason,
            message=message,
        )


def build_annotation_logic_runner(execute_annotation: Callable[..., Any]) -> ModerationRunner:
    """Adapt `AnnotationLogic.execute_annotation` to the moderation runner protocol."""

    def _run(
        *,
        image_paths: list[str],
        litellm_model_ids: list[str],
        phash_list: list[str] | None = None,
    ) -> Any:
        return execute_annotation(
            image_paths=image_paths,
            litellm_model_ids=litellm_model_ids,
            phash_list=phash_list,
        )

    return _run
