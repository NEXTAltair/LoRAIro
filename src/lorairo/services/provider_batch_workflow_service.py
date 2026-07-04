"""Provider Batch API workflow service.

GUI / API / CLI entrypoints should use this Qt-free facade when they need the
common LoRAIro-side Provider Batch lifecycle. Provider-specific request shapes,
file identifiers, and artifact formats remain behind ProviderBatchAdapter.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lorairo.database.db_core import resolve_stored_path
from lorairo.database.repository.annotation_record import AnnotationRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.repository.provider_batch import ProviderBatchRepository
from lorairo.services.annotation_save_service import AnnotationSaveResult, AnnotationSaveService
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.provider_batch_library_compat import (
    to_library_handle,
    to_library_submit_request,
    to_provider_batch_fetch_result,
    to_provider_batch_models,
    to_provider_batch_status,
    to_provider_batch_submission,
)
from lorairo.services.provider_batch_service import (
    BatchJobHandle,
    BatchSubmitItem,
    BatchSubmitRequest,
    ProviderBatchAdapter,
    ProviderBatchArtifactRef,
    ProviderBatchArtifacts,
    ProviderBatchError,
    ProviderBatchFetchResult,
    ProviderBatchJobService,
    ProviderBatchRawPayload,
    ProviderBatchResultItem,
)
from lorairo.utils.log import logger

_TASK_TYPE_ENDPOINTS = {
    "annotation": {
        "openai": "/v1/chat/completions",
        "anthropic": "/v1/messages",
    },
    "rating_preflight": {
        "openai": "/v1/moderations",
    },
}

# ADR 0041: Qt-free helper が import できるよう module-level で公開する SSoT。
# GUI/CLI 側が独自に再定義しない (annotation の anthropic 欠落バグを防ぐ)。
TASK_TYPE_ENDPOINTS: dict[str, dict[str, str]] = _TASK_TYPE_ENDPOINTS

if TYPE_CHECKING:
    from lorairo.database.schema import ProviderBatchItem, ProviderBatchJob


@dataclass(frozen=True)
class ProviderBatchResultApplyResult:
    """Summary of applying normalized batch result item state."""

    updated_count: int
    missing_count: int
    total_count: int
    missing_custom_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProviderBatchImportResult:
    """Summary of importing normalized provider batch results into annotations."""

    save_result: AnnotationSaveResult
    apply_result: ProviderBatchResultApplyResult
    imported_count: int
    skipped_count: int
    error_count: int
    total_count: int
    missing_custom_ids: tuple[str, ...] = field(default_factory=tuple)
    job_imported: bool = False


@dataclass
class _CustomIdGroup:
    """submit 時の custom_id ごとの素材グループ (ADR 0062 dedupe 単位)。"""

    representative_image_id: int
    representative_image_path: Path
    image_ids: list[int]


@dataclass(frozen=True)
class _PreparedProviderBatchImport:
    results_by_model_id: Mapping[int, Mapping[int, Any]]
    imported_custom_ids: tuple[str, ...]
    missing_custom_ids: tuple[str, ...]
    already_imported_count: int
    non_importable_count: int
    # ADR 0062: dedupe で 1 provider item が複数 image_id に fan-out されるため、
    # save 件数 (image 単位) と provider item / custom_id 単位の完了判定を区別する。
    # 各分類の image 単位件数 (fan-out 込み) を集計し、サマリを image 単位で一貫させる。
    imported_image_count: int
    already_imported_image_count: int
    non_importable_image_count: int


class ProviderBatchLibraryAdapter:
    """Adapter that forwards provider batch operations to image-annotator-lib."""

    def __init__(self, provider: str, client: Any) -> None:
        self.provider = provider
        self._client = client

    def submit_batch(self, request: BatchSubmitRequest) -> Any:
        return to_provider_batch_submission(
            self._call_client("submit_batch", to_library_submit_request(request)),
            self.provider,
        )

    def retrieve_batch(self, handle: BatchJobHandle) -> Any:
        return to_provider_batch_status(
            self._call_client("retrieve_batch", to_library_handle(handle)),
            self.provider,
        )

    def cancel_batch(self, handle: BatchJobHandle) -> Any:
        return to_provider_batch_status(
            self._call_client("cancel_batch", to_library_handle(handle)),
            self.provider,
        )

    def fetch_batch_results(self, handle: BatchJobHandle, destination_dir: Path) -> Any:
        library_handle = to_library_handle(handle)
        return to_provider_batch_fetch_result(
            self._call_fetch_batch_results(library_handle, destination_dir),
            self.provider,
            destination_dir,
            fallback_provider_job_id=handle.provider_job_id,
        )

    def list_batch_capable_models(self) -> tuple[Any, ...]:
        """Return image-annotator-lib Provider Batch model metadata."""
        return to_provider_batch_models(self._call_client("list_batch_capable_models"))

    def _call_client(self, method_name: str, *args: Any) -> Any:
        method = getattr(self._client, method_name, None)
        if method is None:
            raise ProviderBatchError(f"image-annotator-lib batch API method is unavailable: {method_name}")
        return method(*args)

    def _call_fetch_batch_results(self, handle: Any, destination_dir: Path) -> Any:
        method = getattr(self._client, "fetch_batch_results", None)
        if method is None:
            raise ProviderBatchError(
                "image-annotator-lib batch API method is unavailable: fetch_batch_results"
            )

        try:
            signature = inspect.signature(method)
            accepts_destination_dir = len(signature.parameters) >= 2
        except (TypeError, ValueError):
            try:
                return method(handle, destination_dir)
            except TypeError:
                return method(handle)
        if accepts_destination_dir:
            return method(handle, destination_dir)
        return method(handle)


class ProviderBatchWorkflowService:
    """Reusable LoRAIro-side Provider Batch workflow boundary."""

    def __init__(
        self,
        provider_batch_repo: ProviderBatchRepository,
        image_repo: ImageRepository,
        annotation_repo: AnnotationRepository,
        config_service: ConfigurationService,
        job_service: ProviderBatchJobService | None = None,
        adapters: Mapping[str, ProviderBatchAdapter] | None = None,
        annotation_save_service: AnnotationSaveService | None = None,
    ) -> None:
        # ADR 0035 段階 6 (#423): legacy facade 撤廃後、必要な Aggregate Repo を
        # 個別に inject する。Image / Annotation / ProviderBatch のクロス参照を要する。
        self._provider_batch_repo = provider_batch_repo
        self._image_repo = image_repo
        self._annotation_repo = annotation_repo
        self._config_service = config_service
        self._job_service = job_service or ProviderBatchJobService(provider_batch_repo, adapters)
        self._annotation_save_service = annotation_save_service or AnnotationSaveService(annotation_repo)
        # #1147: list_batch_capable_models() は adapter 層 (ProviderBatchLibraryAdapter) にある。
        # GUI (LEDGER preview / 自動振り分け) は facade へ呼ぶため、委譲用に adapter を保持する。
        self._model_listing_adapters: list[ProviderBatchAdapter] = list((adapters or {}).values())

    def register_adapter(self, adapter: ProviderBatchAdapter) -> None:
        """Register a provider adapter with the underlying job service."""
        self._job_service.register_adapter(adapter)
        # #1147: model listing も委譲できるよう保持集合へ追加する。
        self._model_listing_adapters.append(adapter)

    def list_batch_capable_models(self) -> tuple[Any, ...]:
        """Batch API 対応モデル情報を取得する (facade → adapter へ委譲、#1147)。

        実処理 (image-annotator-lib への問い合わせ) は adapter 層にあるが、GUI は workflow
        service に対してこのメソッドを呼ぶため facade として委譲する。provider 非依存
        (annotator_library 全体を問い合わせる) なので、対応 adapter のうち最初の 1 つへ委譲する。

        Returns:
            image-annotator-lib の Provider Batch モデルメタデータのタプル。

        Raises:
            ProviderBatchError: model listing に対応する adapter が 1 つも無い場合。
        """
        for adapter in self._model_listing_adapters:
            method = getattr(adapter, "list_batch_capable_models", None)
            if callable(method):
                models: tuple[Any, ...] = tuple(method())
                return models
        raise ProviderBatchError("Batch API 対応モデル一覧を取得できる adapter が登録されていません。")

    def build_submit_request(
        self,
        *,
        provider: str,
        endpoint: str,
        litellm_model_id: str,
        prompt_profile: str,
        image_ids: Sequence[int],
        model_id: int | None = None,
        task_type: str = "annotation",
        image_paths: Mapping[int, str | Path] | None = None,
        description: str | None = None,
        request_artifact_path: str | Path | None = None,
        raw_provider_payload: ProviderBatchRawPayload = None,
    ) -> BatchSubmitRequest:
        """Build an ADR 0038 submit request from LoRAIro image IDs."""
        if not image_ids:
            raise ProviderBatchError("Provider batch submit image_ids が空です")
        endpoint = self._validate_submit_task(
            provider=provider,
            endpoint=endpoint,
            litellm_model_id=litellm_model_id,
            task_type=task_type,
            model_id=model_id,
        )

        metadata_by_id = {
            int(row["id"]): row for row in self._image_repo.get_images_metadata_batch(list(image_ids))
        }
        missing_image_ids = [image_id for image_id in image_ids if image_id not in metadata_by_id]
        if missing_image_ids:
            raise ProviderBatchError(f"Provider batch submit 対象画像が見つかりません: {missing_image_ids}")

        # ADR 0062: pHash + 長辺解像度由来の custom_id で素材実体に寄せた突合キーを作る。
        # 同一 custom_id (= 同一素材) は batch 内で 1 リクエストに dedupe し、代表 image_id を
        # DB item に保存する。結果取り込み時に全 image_id へ反映できるよう custom_id ->
        # image_id[] 対応表を BatchSubmitItem.raw_request (LoRAIro local; library へは渡さない)
        # に埋め込む。
        path_overrides = image_paths or {}
        grouped: dict[str, _CustomIdGroup] = {}
        custom_id_order: list[str] = []
        for image_id in image_ids:
            metadata = metadata_by_id[image_id]
            custom_id = self._build_custom_id_for_image(image_id, metadata)

            image_path = path_overrides.get(image_id)
            if image_path is None:
                stored_path = metadata.get("stored_image_path")
                if not stored_path:
                    raise ProviderBatchError(
                        f"Provider batch submit 対象画像に stored_image_path がありません: image_id={image_id}"
                    )
                image_path = resolve_stored_path(str(stored_path))

            group = grouped.get(custom_id)
            if group is None:
                grouped[custom_id] = _CustomIdGroup(
                    representative_image_id=image_id,
                    representative_image_path=Path(image_path),
                    image_ids=[image_id],
                )
                custom_id_order.append(custom_id)
            else:
                # 同一素材の重複投入はまとめる。代表は最初に出現した image_id を維持する。
                if image_id not in group.image_ids:
                    group.image_ids.append(image_id)

        deduped_count = len(image_ids) - len(custom_id_order)
        if deduped_count > 0:
            logger.info(
                f"Provider batch submit dedupe: {len(image_ids)}件 -> {len(custom_id_order)}件 "
                f"(同一 pHash+長辺の重複 {deduped_count}件を統合)"
            )

        items: list[BatchSubmitItem] = []
        for custom_id in custom_id_order:
            group = grouped[custom_id]
            items.append(
                BatchSubmitItem(
                    custom_id=custom_id,
                    image_id=group.representative_image_id,
                    image_path=group.representative_image_path,
                    task_type=task_type,
                    model_id=model_id,
                    raw_request={"lorairo_image_ids": list(group.image_ids)},
                )
            )

        return BatchSubmitRequest(
            provider=provider,
            endpoint=endpoint,
            litellm_model_id=litellm_model_id,
            prompt_profile=prompt_profile,
            api_keys=self._config_service.get_api_keys(),
            items=tuple(items),
            model_id=model_id,
            description=description,
            request_artifact_path=Path(request_artifact_path)
            if request_artifact_path is not None
            else None,
            raw_provider_payload=raw_provider_payload,
        )

    @staticmethod
    def _build_custom_id_for_image(image_id: int, metadata: Mapping[str, Any]) -> str:
        """画像メタデータから ADR 0062 の custom_id を生成する。

        pHash は DB の ``Image.phash`` (NOT NULL)、長辺解像度は ``width`` / ``height``
        の大きい方を採用する。アノテーション対象素材としては original 画像の解像度を
        用いる (``get_images_metadata_batch`` は resolution=0 で original を返す)。

        Args:
            image_id: 対象画像 ID (エラーメッセージ用)。
            metadata: ``get_images_metadata_batch`` が返す画像メタデータ。

        Returns:
            ``ph:{phash}:le:{long_edge}`` 形式の custom_id。

        Raises:
            ProviderBatchError: pHash または width/height が欠落している場合。
        """
        phash = metadata.get("phash")
        if not phash:
            raise ProviderBatchError(
                f"Provider batch submit 対象画像に pHash がありません: image_id={image_id}"
            )
        width = metadata.get("width")
        height = metadata.get("height")
        if not width or not height:
            raise ProviderBatchError(
                f"Provider batch submit 対象画像に width/height がありません: image_id={image_id}"
            )
        long_edge = max(int(width), int(height))
        return ProviderBatchJobService.build_custom_id(str(phash), long_edge)

    @staticmethod
    def _validate_submit_task(
        *,
        provider: str,
        endpoint: str,
        litellm_model_id: str,
        task_type: str,
        model_id: int | None,
    ) -> str:
        normalized_provider = provider.strip().lower()
        normalized_endpoint = endpoint.strip()
        if not normalized_endpoint.startswith("/"):
            normalized_endpoint = f"/{normalized_endpoint}"
        canonical_endpoint = normalized_endpoint.rstrip("/")

        provider_endpoints = _TASK_TYPE_ENDPOINTS.get(task_type)
        expected_endpoint = provider_endpoints.get(normalized_provider) if provider_endpoints else None
        if expected_endpoint is None:
            raise ProviderBatchError(
                f"Provider batch submit は provider={normalized_provider}, task_type={task_type} に未対応です"
            )
        if canonical_endpoint != expected_endpoint:
            raise ProviderBatchError(f"Provider batch submit には endpoint={expected_endpoint} が必要です")

        if task_type != "rating_preflight":
            return expected_endpoint

        if model_id is None:
            raise ProviderBatchError("rating_preflight batch submit には model_id が必要です")
        normalized_model_id = litellm_model_id.strip().lower()
        bare_model_id = (
            normalized_model_id.removeprefix("openai/")
            if normalized_model_id.startswith("openai/")
            else normalized_model_id
        )
        if "/" in bare_model_id or not bare_model_id.startswith("omni-moderation-"):
            raise ProviderBatchError(
                "rating_preflight batch submit には openai moderation model "
                "(openai/omni-moderation-*) が必要です"
            )

        return expected_endpoint

    def submit_images(
        self,
        *,
        provider: str,
        endpoint: str,
        litellm_model_id: str,
        prompt_profile: str,
        image_ids: Sequence[int],
        model_id: int | None = None,
        task_type: str = "annotation",
        image_paths: Mapping[int, str | Path] | None = None,
        description: str | None = None,
        request_artifact_path: str | Path | None = None,
        raw_provider_payload: ProviderBatchRawPayload = None,
    ) -> int:
        """Build and submit a provider batch job for LoRAIro image IDs."""
        request = self.build_submit_request(
            provider=provider,
            endpoint=endpoint,
            litellm_model_id=litellm_model_id,
            prompt_profile=prompt_profile,
            image_ids=image_ids,
            model_id=model_id,
            task_type=task_type,
            image_paths=image_paths,
            description=description,
            request_artifact_path=request_artifact_path,
            raw_provider_payload=raw_provider_payload,
        )
        return self._job_service.submit_batch(request)

    def refresh(self, job_id: int) -> ProviderBatchJob:
        """Refresh a provider batch job using configured API keys."""
        logger.debug(f"ProviderBatch refresh: job_id={job_id}")  # #1150: 操作突合用
        return self._job_service.refresh(job_id, api_keys=self._config_service.get_api_keys())

    def cancel(self, job_id: int) -> ProviderBatchJob:
        """Cancel a provider batch job using configured API keys."""
        return self._job_service.cancel(job_id, api_keys=self._config_service.get_api_keys())

    def download_results(
        self,
        job_id: int,
        destination_dir: str | Path | None = None,
    ) -> ProviderBatchArtifacts:
        """Download provider artifacts into the configured batch results directory by default."""
        fetch_result = self.fetch_results(job_id, destination_dir)
        return ProviderBatchArtifacts(
            provider_job_id=fetch_result.provider_job_id,
            artifacts=fetch_result.artifacts,
            raw_provider_payload=fetch_result.raw_provider_payload,
        )

    def fetch_results(
        self,
        job_id: int,
        destination_dir: str | Path | None = None,
    ) -> ProviderBatchFetchResult:
        """Fetch normalized provider results and apply per-item result state."""
        logger.debug(f"ProviderBatch fetch_results: job_id={job_id}")  # #1150: 操作突合用
        resolved_destination = (
            Path(destination_dir)
            if destination_dir is not None
            else self._config_service.get_batch_results_directory()
        )
        fetch_result = self._job_service.fetch_results(
            job_id,
            resolved_destination,
            api_keys=self._config_service.get_api_keys(),
        )
        if fetch_result.items:
            self.apply_result_items(job_id, fetch_result.provider_job_id, fetch_result.items)
        return fetch_result

    def import_results(
        self,
        job_id: int,
        fetch_result: ProviderBatchFetchResult | Mapping[str, Any] | Any | None = None,
        destination_dir: str | Path | None = None,
    ) -> ProviderBatchImportResult:
        """Import normalized provider batch results using custom_id as the mapping SSoT."""
        logger.debug(f"ProviderBatch import_results: job_id={job_id}")  # #1150: 操作突合用
        job = self._require_job(job_id)
        if job.status == "imported" or job.imported_at is not None:
            raise ProviderBatchError(f"Provider batch job は import 済みです: job_id={job_id}")
        if job.provider_job_id is None:
            raise ProviderBatchError(f"provider_job_id が未設定です: job_id={job_id}")

        normalized_fetch = (
            self._coerce_fetch_result(fetch_result, job.provider_job_id)
            if fetch_result is not None
            else self.fetch_results(job_id, destination_dir)
        )
        if normalized_fetch.provider_job_id != job.provider_job_id:
            raise ProviderBatchError(
                "Provider batch import job ID mismatch: "
                f"job_id={job_id}, expected={job.provider_job_id}, actual={normalized_fetch.provider_job_id}"
            )
        self._apply_fetch_job_state(job, normalized_fetch)

        apply_result = (
            self.apply_result_items(job_id, normalized_fetch.provider_job_id, normalized_fetch.items)
            if normalized_fetch.items
            else ProviderBatchResultApplyResult(updated_count=0, missing_count=0, total_count=0)
        )

        refreshed_job = self._require_job(job_id)
        prepared = self._prepare_import_results(refreshed_job, normalized_fetch, apply_result)

        importable_count = sum(
            len(results_by_image_id) for results_by_image_id in prepared.results_by_model_id.values()
        )
        self._validate_importable_job_state(refreshed_job, importable_count)
        save_result = self._save_results_by_model(refreshed_job, prepared.results_by_model_id)

        unique_missing_custom_ids = tuple(sorted(set(prepared.missing_custom_ids)))
        import_clean = (
            save_result.error_count == 0
            and save_result.skip_count == 0
            and not unique_missing_custom_ids
            and prepared.non_importable_count == 0
        )
        # ADR 0062: 完了判定は provider item (custom_id) 単位で行う。dedupe で 1 item が
        # 複数 image に fan-out されるため、save 件数 (image 単位) ではなく custom_id 単位で
        # normalized_fetch.items との突合を取る。
        settled_custom_id_count = len(prepared.imported_custom_ids) + prepared.already_imported_count
        job_imported = (
            bool(normalized_fetch.items)
            and settled_custom_id_count == len(normalized_fetch.items)
            and import_clean
        )
        # mark は image 単位の save 成功数と fan-out 込みの想定 image 数を突合する。
        mark_imported_items = (
            save_result.success_count == prepared.imported_image_count
            and save_result.error_count == 0
            and save_result.skip_count == 0
        )
        if mark_imported_items:
            self._mark_items_imported(job_id, prepared.imported_custom_ids)
        if job_imported:
            ProviderBatchJobService.validate_transition(refreshed_job.status, "imported")
            self._provider_batch_repo.update_provider_batch_job(
                job_id,
                {"status": "imported", "imported_at": datetime.now(UTC)},
            )

        # ADR 0062 / Codex #646: imported_count / skipped_count / error_count / total_count を
        # すべて image 単位で一貫させる。dedupe fan-out で 1 provider result が複数 image に
        # 紐づくため、non-importable / already-imported も fan-out 込みの image 件数で数える
        # (2-image deduped 失敗を "1 skipped / 1 total" と過小報告しない)。missing は DB item が
        # 無く fan-out 数が不明なため 1 件として数える。
        # save 対象外の image (item 単位 → fan-out 込み image 単位へ展開) を加算する。
        not_saved_image_count = (
            len(unique_missing_custom_ids)
            + prepared.non_importable_image_count
            + prepared.already_imported_image_count
        )
        skipped_image_count = save_result.skip_count + not_saved_image_count
        # total = save 対象 image (success+skip+error) + save 対象外 image。
        image_total_count = save_result.total_count + not_saved_image_count
        return ProviderBatchImportResult(
            save_result=save_result,
            apply_result=apply_result,
            imported_count=save_result.success_count,
            skipped_count=skipped_image_count,
            error_count=save_result.error_count,
            total_count=image_total_count,
            missing_custom_ids=unique_missing_custom_ids,
            job_imported=job_imported,
        )

    @staticmethod
    def _validate_importable_job_state(job: ProviderBatchJob, importable_count: int) -> None:
        if importable_count:
            ProviderBatchJobService.validate_transition(job.status, "imported")

    def _prepare_import_results(
        self,
        job: ProviderBatchJob,
        fetch_result: ProviderBatchFetchResult,
        apply_result: ProviderBatchResultApplyResult,
    ) -> _PreparedProviderBatchImport:
        items_by_custom_id = {item.custom_id: item for item in job.items}
        results_by_model_id: dict[int, dict[int, Any]] = {}
        imported_custom_ids: list[str] = []
        missing_custom_ids: list[str] = list(apply_result.missing_custom_ids)
        already_imported_count = 0
        non_importable_count = 0
        imported_image_count = 0
        already_imported_image_count = 0
        non_importable_image_count = 0

        for raw_item in fetch_result.items:
            item = self._coerce_result_item(raw_item)
            db_item = items_by_custom_id.get(item.custom_id)
            if db_item is None or db_item.image_id is None:
                missing_custom_ids.append(item.custom_id)
                continue
            # ADR 0062 / Codex #646: dedupe で 1 provider item が複数 image に fan-out される
            # ため、skip / already-imported / non-importable も image 単位件数で集計する。
            fanned_out_image_count = len(self._image_ids_for_db_item(db_item))
            if db_item.status == "imported":
                already_imported_count += 1
                already_imported_image_count += fanned_out_image_count
                continue
            if item.status not in {"succeeded", "completed", "imported"} or item.annotation is None:
                non_importable_count += 1
                non_importable_image_count += fanned_out_image_count
                continue
            model_id = self._model_id_for_item(job, db_item)
            if model_id is None:
                raise ProviderBatchError(f"Provider batch import に model_id が必要です: job_id={job.id}")
            # ADR 0062: custom_id は素材実体キーなので、dedupe で統合された
            # 重複 image_id 群すべてに同じ annotation を反映する。
            target_image_ids = self._image_ids_for_db_item(db_item)
            model_results = results_by_model_id.setdefault(model_id, {})
            for target_image_id in target_image_ids:
                model_results[target_image_id] = item.annotation
            imported_custom_ids.append(item.custom_id)
            imported_image_count += len(target_image_ids)

        return _PreparedProviderBatchImport(
            results_by_model_id=results_by_model_id,
            imported_custom_ids=tuple(imported_custom_ids),
            missing_custom_ids=tuple(missing_custom_ids),
            already_imported_count=already_imported_count,
            non_importable_count=non_importable_count,
            imported_image_count=imported_image_count,
            already_imported_image_count=already_imported_image_count,
            non_importable_image_count=non_importable_image_count,
        )

    def _save_results_by_model(
        self,
        job: ProviderBatchJob,
        results_by_model_id: Mapping[int, Mapping[int, Any]],
    ) -> AnnotationSaveResult:
        if not results_by_model_id:
            return AnnotationSaveResult(success_count=0, skip_count=0, error_count=0, total_count=0)

        success_count = 0
        skip_count = 0
        error_count = 0
        total_count = 0
        error_details: list[str] = []
        for model_id, results_by_image_id in results_by_model_id.items():
            model_name = self._model_name_for_job(job, model_id)
            result = self._annotation_save_service.save_provider_batch_results_by_image_id(
                results_by_image_id,
                model_id=model_id,
                model_name=model_name,
            )
            success_count += result.success_count
            skip_count += result.skip_count
            error_count += result.error_count
            total_count += result.total_count
            error_details.extend(result.error_details)

        return AnnotationSaveResult(
            success_count=success_count,
            skip_count=skip_count,
            error_count=error_count,
            total_count=total_count,
            error_details=error_details,
        )

    @staticmethod
    def _model_id_for_item(job: ProviderBatchJob, item: ProviderBatchItem) -> int | None:
        return item.model_id if item.model_id is not None else job.model_id

    @staticmethod
    def _image_ids_for_db_item(item: ProviderBatchItem) -> list[int]:
        """DB item から annotation 反映対象の image_id 群を取り出す。

        ADR 0062: dedupe で統合した重複 image_id 群を ``raw_request`` の
        ``lorairo_image_ids`` (LoRAIro local) に保存している。これを読み戻して
        custom_id -> image_id[] の対応として使う。欠落時は代表 ``image_id`` のみを返す
        (旧フォーマット job との後方互換)。

        Args:
            item: 対象の ``ProviderBatchItem``。``image_id`` は非 None である前提。

        Returns:
            annotation を反映する image_id のリスト。重複は除き、代表 image_id を必ず含む。
        """
        representative = item.image_id
        if representative is None:
            return []
        mapped = ProviderBatchWorkflowService._parse_mapped_image_ids(item.raw_request)
        if not mapped:
            return [representative]
        ordered = list(dict.fromkeys([representative, *mapped]))
        return ordered

    @staticmethod
    def _parse_mapped_image_ids(raw_request: str | None) -> list[int]:
        if not raw_request:
            return []
        try:
            payload = json.loads(raw_request)
        except (json.JSONDecodeError, TypeError):
            return []
        if not isinstance(payload, Mapping):
            return []
        mapped = payload.get("lorairo_image_ids")
        if not isinstance(mapped, list):
            return []
        result: list[int] = []
        for value in mapped:
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                result.append(value)
        return result

    def _mark_items_imported(self, job_id: int, custom_ids: Sequence[str]) -> None:
        updates_by_custom_id = {custom_id: {"status": "imported"} for custom_id in custom_ids}
        if updates_by_custom_id:
            self._provider_batch_repo.update_provider_batch_items_by_custom_id(job_id, updates_by_custom_id)

    def apply_result_items(
        self,
        job_id: int,
        provider_job_id: str,
        items: Sequence[ProviderBatchResultItem | Mapping[str, Any] | Any],
    ) -> ProviderBatchResultApplyResult:
        """Apply normalized provider-neutral item statuses to DB records."""
        job = self._provider_batch_repo.get_provider_batch_job(job_id)
        if job is None:
            raise ProviderBatchError(f"Provider batch job が見つかりません: job_id={job_id}")
        if job.provider_job_id != provider_job_id:
            raise ProviderBatchError(
                "Provider batch result job ID mismatch: "
                f"job_id={job_id}, expected={job.provider_job_id}, actual={provider_job_id}"
            )

        current_items_by_custom_id = {item.custom_id: item for item in job.items}
        updates_by_custom_id: dict[str, dict[str, Any]] = {}
        for raw_item in items:
            item = self._coerce_result_item(raw_item)
            current_item = current_items_by_custom_id.get(item.custom_id)
            next_status = (
                "imported"
                if current_item is not None and current_item.status == "imported"
                else item.status
            )
            updates_by_custom_id[item.custom_id] = {
                "status": next_status,
                "error_type": item.error_type,
                "error_message": item.error_message,
                "raw_response": self._serialize_payload(item.raw_response),
            }

        updated_custom_ids = self._provider_batch_repo.update_provider_batch_items_by_custom_id(
            job_id,
            updates_by_custom_id,
        )
        missing_custom_ids = sorted(set(updates_by_custom_id) - updated_custom_ids)

        if missing_custom_ids:
            logger.warning(
                f"Provider batch result に DB item が見つからない custom_id があります: {missing_custom_ids}"
            )
        return ProviderBatchResultApplyResult(
            updated_count=len(updated_custom_ids),
            missing_count=len(missing_custom_ids),
            total_count=len(items),
            missing_custom_ids=tuple(missing_custom_ids),
        )

    def _apply_fetch_job_state(
        self,
        job: ProviderBatchJob,
        fetch_result: ProviderBatchFetchResult,
    ) -> None:
        provider_status = fetch_result.status or fetch_result.provider_status
        if not provider_status:
            return
        next_status = ProviderBatchJobService.normalize_status(job.provider, provider_status)
        should_preserve_imported = job.status == "imported" and next_status == "completed"
        if not should_preserve_imported:
            ProviderBatchJobService.validate_transition(job.status, next_status)
        updates: dict[str, Any] = {
            "provider_status": fetch_result.provider_status,
        }
        if not should_preserve_imported:
            updates["status"] = next_status
        optional_fields = {
            "request_count": fetch_result.request_count,
            "succeeded_count": fetch_result.succeeded_count,
            "failed_count": fetch_result.failed_count,
            "canceled_count": fetch_result.canceled_count,
            "expired_count": fetch_result.expired_count,
            "completed_at": fetch_result.completed_at,
            "expires_at": fetch_result.expires_at,
        }
        updates.update({key: value for key, value in optional_fields.items() if value is not None})
        self._provider_batch_repo.update_provider_batch_job(job.id, updates)

    def _require_job(self, job_id: int) -> ProviderBatchJob:
        job = self._provider_batch_repo.get_provider_batch_job(job_id)
        if job is None:
            raise ProviderBatchError(f"Provider batch job が見つかりません: job_id={job_id}")
        return job

    @classmethod
    def _coerce_fetch_result(
        cls,
        result: ProviderBatchFetchResult | ProviderBatchArtifacts | Mapping[str, Any] | Any,
        fallback_provider_job_id: str,
    ) -> ProviderBatchFetchResult:
        if isinstance(result, ProviderBatchFetchResult):
            return result
        if isinstance(result, ProviderBatchArtifacts):
            return ProviderBatchFetchResult(
                provider_job_id=result.provider_job_id,
                provider_status="",
                artifacts=result.artifacts,
                raw_provider_payload=result.raw_provider_payload,
            )
        if isinstance(result, Mapping):
            provider_status = cls._optional_str(result.get("provider_status") or result.get("status")) or ""
            return ProviderBatchFetchResult(
                provider_job_id=str(result.get("provider_job_id") or fallback_provider_job_id),
                provider_status=provider_status,
                status=cls._optional_str(result.get("status")),
                request_count=cls._optional_int(result.get("request_count")),
                succeeded_count=cls._optional_int(result.get("succeeded_count")),
                failed_count=cls._optional_int(result.get("failed_count")),
                canceled_count=cls._optional_int(result.get("canceled_count")),
                expired_count=cls._optional_int(result.get("expired_count")),
                completed_at=cls._optional_datetime(result.get("completed_at")),
                expires_at=cls._optional_datetime(result.get("expires_at")),
                artifacts=tuple(
                    cls._coerce_artifact_ref(artifact) for artifact in result.get("artifacts") or ()
                ),
                items=tuple(cls._coerce_result_item(item) for item in result.get("items") or ()),
                raw_provider_payload=result.get("raw_provider_payload"),
            )
        return ProviderBatchFetchResult(
            provider_job_id=cls._optional_str(getattr(result, "provider_job_id", None))
            or fallback_provider_job_id,
            provider_status=cls._optional_str(
                getattr(result, "provider_status", None) or getattr(result, "status", None)
            )
            or "",
            status=cls._optional_str(getattr(result, "status", None)),
            request_count=cls._optional_int(getattr(result, "request_count", None)),
            succeeded_count=cls._optional_int(getattr(result, "succeeded_count", None)),
            failed_count=cls._optional_int(getattr(result, "failed_count", None)),
            canceled_count=cls._optional_int(getattr(result, "canceled_count", None)),
            expired_count=cls._optional_int(getattr(result, "expired_count", None)),
            completed_at=cls._optional_datetime(getattr(result, "completed_at", None)),
            expires_at=cls._optional_datetime(getattr(result, "expires_at", None)),
            artifacts=tuple(
                cls._coerce_artifact_ref(artifact) for artifact in getattr(result, "artifacts", ()) or ()
            ),
            items=tuple(cls._coerce_result_item(item) for item in getattr(result, "items", ()) or ()),
            raw_provider_payload=getattr(result, "raw_provider_payload", None),
        )

    @classmethod
    def _coerce_artifact_ref(
        cls,
        artifact: ProviderBatchArtifactRef | Mapping[str, Any] | Any,
    ) -> ProviderBatchArtifactRef:
        if isinstance(artifact, ProviderBatchArtifactRef):
            return artifact
        if isinstance(artifact, Mapping):
            return ProviderBatchArtifactRef(
                artifact_type=str(artifact["artifact_type"]),
                local_path=Path(artifact["local_path"]),
                provider_file_id=cls._optional_str(artifact.get("provider_file_id")),
                sha256=cls._optional_str(artifact.get("sha256")),
            )
        return ProviderBatchArtifactRef(
            artifact_type=str(artifact.artifact_type),
            local_path=Path(artifact.local_path),
            provider_file_id=cls._optional_str(getattr(artifact, "provider_file_id", None)),
            sha256=cls._optional_str(getattr(artifact, "sha256", None)),
        )

    @staticmethod
    def _model_name_for_job(job: ProviderBatchJob, model_id: int | None) -> str:
        model = job.model
        litellm_model_id = (
            getattr(model, "litellm_model_id", None)
            if model is not None and job.model_id == model_id
            else None
        )
        if litellm_model_id:
            return str(litellm_model_id)
        if model_id is not None:
            return f"__provider_batch_model_{model_id}__"
        return "__provider_batch_model_unknown__"

    @classmethod
    def _coerce_result_item(
        cls, item: ProviderBatchResultItem | Mapping[str, Any] | Any
    ) -> ProviderBatchResultItem:
        if isinstance(item, ProviderBatchResultItem):
            return item
        if isinstance(item, Mapping):
            error = item.get("error")
            return ProviderBatchResultItem(
                custom_id=str(item["custom_id"]),
                status=str(item["status"]),
                annotation=item.get("annotation"),
                error_type=cls._optional_str(
                    item.get("error_type") or cls._extract_error_field(error, "type")
                ),
                error_message=cls._optional_str(
                    item.get("error_message")
                    or item.get("message")
                    or cls._extract_error_field(error, "message")
                ),
                raw_response=item.get("raw_response"),
            )
        error = getattr(item, "error", None)
        return ProviderBatchResultItem(
            custom_id=str(item.custom_id),
            status=str(item.status),
            annotation=getattr(item, "annotation", None),
            error_type=cls._optional_str(
                getattr(item, "error_type", None) or cls._extract_error_field(error, "type")
            ),
            error_message=cls._optional_str(
                getattr(item, "error_message", None) or cls._extract_error_field(error, "message")
            ),
            raw_response=getattr(item, "raw_response", None),
        )

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        raise ProviderBatchError(f"datetime に変換できない値です: {value!r}")

    @staticmethod
    def _serialize_payload(payload: ProviderBatchRawPayload) -> str | None:
        if payload is None:
            return None
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _extract_error_field(error: Any, field_name: str) -> Any:
        if error is None:
            return None
        if isinstance(error, Mapping):
            return error.get(field_name) or error.get(f"error_{field_name}")
        return getattr(error, field_name, None) or getattr(error, f"error_{field_name}", None)
