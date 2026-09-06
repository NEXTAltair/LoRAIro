"""Wire models for command outputs that have no public API response DTO."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ResultRow(BaseModel):
    kind: Literal["result"] = "result"
    ok: bool = True
    message: str


class CountResult(ResultRow):
    count: int


class ProjectListResult(CountResult):
    pass


class BatchListResult(CountResult):
    pass


class ErrorsGetResult(CountResult):
    pass


class ModelsListResult(CountResult):
    preference: str
    preference_source: str
    unavailable: int


class ErrorRecordDetailItem(BaseModel):
    kind: Literal["item"] = "item"
    id: int
    image_id: int | None
    operation_type: str
    error_type: str
    error_message: str
    stack_trace: str | None
    file_path: str | None
    model_name: str | None
    resolved_at: str | None
    created_at: str | None


class MissingTranslationPairItem(BaseModel):
    kind: Literal["item"] = "item"
    tag: str
    tag_id: int | None
    lang: Literal["ja", "en"]
    text: str
    image_id: int | None = None


class TranslationCandidates(BaseModel):
    candidates: list[str]
    preferred: str | None


class TagTranslationStatusItem(BaseModel):
    tag: str
    tag_id: int | None
    translations: dict[str, TranslationCandidates]
    missing: list[str]


class ImageTagTranslationStatusItem(BaseModel):
    kind: Literal["item"] = "item"
    image_id: int
    tags: list[TagTranslationStatusItem]


class TagsTranslationsShowResult(ResultRow):
    target_tags: int
    target_images: int | None = None
    missing_pairs: int | None = None
    truncated: bool | None = None


class TagsTranslationsAddItem(BaseModel):
    kind: Literal["item"] = "item"
    tag: str
    canonical_tag: str
    classification: str
    tag_id: int | None
    language: str
    translation: str
    preferred: bool
    registered_new_tag: bool
    status: Literal[
        "dry_run", "changed", "skipped_existing", "skipped_candidates", "skipped_invalid", "error"
    ]
    candidates: list[str] | None = None
    error: str | None = None


class TagsTranslationsAddResult(ResultRow):
    dry_run: bool
    tag_id: int | None = None
    language: str | None = None
    total: int | None = None
    changed: int | None = None
    would_add: int | None = None
    skipped_existing: int | None = None
    skipped_candidates: int | None = None
    errors: int | None = None


class TranslationMutationItem(BaseModel):
    kind: Literal["item"] = "item"
    tag: str
    tag_id: int
    language: str
    translation: str
    status: Literal["dry_run", "changed", "not_found"]


class TagsTranslationsDeleteItem(TranslationMutationItem):
    pass


class TagsTranslationsSuppressItem(TranslationMutationItem):
    status: Literal["dry_run", "changed"]


class TagsTranslationsUnsuppressItem(TranslationMutationItem):
    pass


class TranslationMutationResult(ResultRow):
    dry_run: bool
    tag_id: int
    language: str


class TagsTranslationsDeleteResult(TranslationMutationResult):
    deleted: bool


class TagsTranslationsSuppressResult(TranslationMutationResult):
    pass


class TagsTranslationsUnsuppressResult(TranslationMutationResult):
    removed: bool


class TagsAliasResult(ResultRow):
    dry_run: bool
    from_tag: str
    to_tag: str
    alias_tag_id: int | None = None
    status: Literal["dry_run", "changed", "noop"]


# Keep registry lookup explicit and limited to wire models; no arbitrary import by name.
OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        ProjectListResult,
        BatchListResult,
        ModelsListResult,
        ErrorsGetResult,
        ErrorRecordDetailItem,
        MissingTranslationPairItem,
        TagTranslationStatusItem,
        ImageTagTranslationStatusItem,
        TagsTranslationsShowResult,
        TagsTranslationsAddItem,
        TagsTranslationsAddResult,
        TagsTranslationsDeleteItem,
        TagsTranslationsDeleteResult,
        TagsTranslationsSuppressItem,
        TagsTranslationsSuppressResult,
        TagsTranslationsUnsuppressItem,
        TagsTranslationsUnsuppressResult,
        TagsAliasResult,
    )
}
