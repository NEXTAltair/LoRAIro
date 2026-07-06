"""CLI command introspection registry and emitters (ADR 0059).

The wire format intentionally reuses ADR 0057 ``item`` / ``result`` rows.
Payload ``type`` differentiates tools, compact models, and JSON Schema rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli.commands.images import ImageSearchQuery
from lorairo.public_api.types import ProjectCreateRequest

SideEffect = Literal["db_read", "db_write", "file_read", "file_write", "network"]
SchemaMode = Literal["compact", "json_schema"]


class ImageFilterCriteriaSchema(BaseModel):
    """Public JSON Schema mirror for ImageFilterCriteria.

    ImageFilterCriteria is a dataclass used by the DB/repository layer. This
    Pydantic mirror is the public, curated search contract exposed by CLI
    introspection; it is not a raw DB schema.
    """

    tags: list[str] | None = Field(default=None, description="Tags to include in image search.")
    caption: list[str] | None = Field(
        default=None, description="Caption keyword filters (all keywords targeted)."
    )
    excluded_tags: list[str] | None = Field(default=None, description="Tags to exclude.")
    resolution: int = Field(default=0, ge=0, description="Target long-edge resolution; 0 means original.")
    use_and: bool = Field(default=True, description="Use AND semantics for multiple tags.")
    start_date: str | None = Field(default=None, description="Inclusive start date/time in ISO 8601 form.")
    end_date: str | None = Field(default=None, description="Inclusive end date/time in ISO 8601 form.")
    include_untagged: bool = Field(default=False, description="Search only images without tags.")
    include_nsfw: bool = Field(default=False, description="Include NSFW images in results.")
    include_unrated: bool = Field(default=True, description="Include images without any rating rows.")
    only_unrated: bool = Field(default=False, description="Search only images without ratings.")
    missing_model_litellm_id: str | None = Field(
        default=None,
        description="Search images missing annotation rows for this LiteLLM model ID.",
    )
    manual_rating_filter: str | None = Field(default=None, description="Manual rating filter.")
    ai_rating_filter: str | None = Field(default=None, description="AI rating filter.")
    manual_edit_filter: bool | None = Field(
        default=None,
        description="Filter by whether annotations were manually edited.",
    )
    score_min: float | None = Field(default=None, ge=0.0, le=10.0, description="Minimum score.")
    score_max: float | None = Field(default=None, ge=0.0, le=10.0, description="Maximum score.")
    project_name: str | None = Field(default=None, description="Project name scope.")
    project_id: int | None = Field(default=None, description="Project ID scope.")
    limit: int | None = Field(default=None, ge=1, description="Maximum result count.")
    offset: int = Field(default=0, ge=0, description="Rows to skip.")
    image_ids: list[int] | None = Field(
        default=None,
        max_length=500,
        description="Exact image ID selector. When present, other filter dimensions are bypassed.",
    )

    model_config = ConfigDict(title="ImageFilterCriteria")


class CliErrorResponse(BaseModel):
    """Public JSONL error contract emitted by the CLI boundary."""

    kind: Literal["error"] = "error"
    ok: Literal[False] = False
    code: str
    message: str
    retryable: bool
    user_action_required: bool
    hint: str | None = None
    details: dict[str, Any] | None = None

    model_config = ConfigDict(title="CliErrorResponse")


class ImagesListItem(BaseModel):
    """JSONL item payload emitted by ``images list --json --fetch``.

    Rows are only emitted when ``--fetch`` is set. The default count-first path
    (#655 bounded pagination) emits no items, only an ``ImagesListResult`` row.
    """

    image_id: int | None = None
    file_path: str | None = None

    model_config = ConfigDict(title="ImagesListItem")


class ImagesListResult(BaseModel):
    """JSONL result payload emitted by ``images list --json``.

    ``count`` / ``total`` の語義は両モードで一貫する (#664): ``count`` は **この応答で
    出力した item 行数**、``total`` は **総ヒット数**。count-first 既定は item を
    出さないため ``count=0`` + ``total=N``。``--fetch`` は ``count=len(page)`` +
    ``total=N`` + ページングメタ (``limit`` / ``offset`` / ``has_more``)。
    """

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    count: int = Field(description="Number of item rows emitted in this response (0 in count-first mode).")
    total: int | None = Field(default=None, description="Total number of matching images.")
    limit: int | None = None
    offset: int | None = None
    has_more: bool | None = None

    model_config = ConfigDict(title="ImagesListResult")


class ModelsListItem(BaseModel):
    """JSONL item payload emitted by ``models list --json``."""

    provider: str
    route: str
    litellm_id: str
    type: Literal["webapi", "local"]
    category: str
    available: bool
    deprecated: bool

    model_config = ConfigDict(title="ModelsListItem")


class ProjectListItem(BaseModel):
    """JSONL item payload emitted by ``project list --json``."""

    name: str
    created: str
    path: str

    model_config = ConfigDict(title="ProjectListItem")


class ProjectCreateResult(BaseModel):
    """JSONL result payload emitted by ``project create --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    name: str
    path: str

    model_config = ConfigDict(title="ProjectCreateResult")


class ProjectDeleteResult(BaseModel):
    """JSONL result payload emitted by ``project delete --json``.

    JSON mode は ``--force`` 必須 (Issue #659) のため対話キャンセル経路を持たず、
    成功時は常に ``name`` を伴う result 行を 1 つだけ emit する。
    """

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    name: str | None = None

    model_config = ConfigDict(title="ProjectDeleteResult")


class VersionResult(BaseModel):
    """JSONL result payload emitted by ``version --json`` (Issue #662)."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    name: str
    version: str
    description: str

    model_config = ConfigDict(title="VersionResult")


class StatusResult(BaseModel):
    """JSONL result payload emitted by ``status --json`` (Issue #662).

    CLI 経路は ``api_keys``、GUI 経路は ``initialized_services`` を伴う
    (実行環境によりどちらか一方のみが存在する)。
    """

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    environment: str
    phase: str
    config_found: bool
    api_keys: dict[str, bool] | None = None
    initialized_services: dict[str, bool] | None = None

    model_config = ConfigDict(title="StatusResult")


class ImagesRegisterResult(BaseModel):
    """JSONL result payload emitted by ``images register --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    total: int
    registered: int
    skipped: int
    errors: int
    error_details: list[str] = Field(default_factory=list)

    model_config = ConfigDict(title="ImagesRegisterResult")


class ImagesUpdateResult(BaseModel):
    """JSONL result payload emitted by ``images update --json``.

    A project with no images returns a success row containing only ``count=0``
    (no-target path); a normal update populates the remaining fields instead.
    """

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    project: str | None = None
    target_images: int | None = None
    tags: list[str] | None = None
    added: int | None = None
    failed_tags: list[str] | None = None
    count: int | None = None

    model_config = ConfigDict(title="ImagesUpdateResult")


class ImagesShowInputSchema(BaseModel):
    """Implemented options surface accepted by ``images show``."""

    project: str
    image_ids: str = Field(
        description="Comma-separated image IDs, max 500. Positional form `images show 42 57` also works."
    )
    include_rejected: bool = False

    model_config = ConfigDict(title="ImagesShowInput")


class ImagesShowItem(BaseModel):
    """JSONL item payload emitted per image by ``images show --json``."""

    image_id: int
    metadata: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Image file metadata for cross-checking annotations against the actual file "
            "(Issue #1215): stored_image_path / original_image_path / width / height / "
            "format / filename / extension / phash / uuid. Null when the metadata row "
            "is unavailable."
        ),
    )
    tags: list[dict[str, Any]]
    captions: list[dict[str, Any]]
    scores: list[dict[str, Any]]
    score_labels: list[dict[str, Any]]
    ratings: list[dict[str, Any]]
    quality_summary: dict[str, Any]

    model_config = ConfigDict(title="ImagesShowItem")


class ImagesShowResult(BaseModel):
    """JSONL result payload emitted by ``images show --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    target_images: int

    model_config = ConfigDict(title="ImagesShowResult")


class ExportCreateInputSchema(BaseModel):
    """Implemented options surface accepted by ``export create``.

    export create requires --image-ids (comma-separated IDs).
    Use ``images search`` to resolve IDs, then pass them here.
    """

    project: str
    image_ids: str = Field(description="Comma-separated image IDs to export, e.g. '1,2,3'.")
    output: str
    resolution: int = 512

    model_config = ConfigDict(title="ExportCreateInput")


class ExportCreateResult(BaseModel):
    """JSONL result payload emitted by ``export create --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    output_path: str | None = None
    total_images: int | None = None
    resolution: int | None = None
    count: int | None = None

    model_config = ConfigDict(title="ExportCreateResult")


class TagsEditItem(BaseModel):
    """JSONL item payload emitted per image by ``tags add/remove/replace --json``."""

    image_id: int
    action: Literal["add", "remove", "replace"]
    tags: list[str] | None = Field(default=None, description="Tags operated on (add/remove commands).")
    from_tag: str | None = Field(
        default=None,
        alias="from",
        description="Source tag (replace command only). Wire key is 'from'.",
    )
    to_tag: str | None = Field(
        default=None,
        alias="to",
        description="Destination tag (replace command only). Wire key is 'to'.",
    )
    status: str
    reason: str | None = None

    model_config = ConfigDict(title="TagsEditItem", populate_by_name=True)


class TagResolutionEntry(BaseModel):
    """Per-tag classification entry surfaced by ``tags add --json`` (Issue #1174)."""

    tag: str
    classification: Literal["exact", "alias_resolved", "typo_candidate", "ambiguous", "unregistered"]
    canonical_tag: str
    tag_id: int | None
    candidates: list[str]

    model_config = ConfigDict(title="TagResolutionEntry")


class TagsAddResult(BaseModel):
    """JSONL result payload emitted by ``tags add --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    target_images: int
    tags: list[str]
    added: int
    dry_run: bool
    tag_resolutions: list[TagResolutionEntry]
    skipped_invalid_tags: list[str]
    unresolved_tag_count: int | None
    would_add: int | None = Field(
        default=None,
        description=(
            "Estimated additions if --apply were run (dry-run only, Issue #1217). "
            "Accounts for existing-duplicate skips. Absent on apply runs."
        ),
    )

    model_config = ConfigDict(title="TagsAddResult")


class TagsRemoveResult(BaseModel):
    """JSONL result payload emitted by ``tags remove --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    target_images: int
    tags: list[str]
    removed: int
    dry_run: bool
    mode: Literal["soft_reject"] = Field(
        default="soft_reject",
        description=(
            "Removal mode (Issue #1217). soft_reject marks rejected_at and is reversible "
            "via tags restore / re-add."
        ),
    )
    would_remove: int | None = Field(
        default=None,
        description=(
            "Estimated soft-reject count if --apply were run (dry-run only, Issue #1217). "
            "Absent on apply runs."
        ),
    )

    model_config = ConfigDict(title="TagsRemoveResult")


class TagsReplaceResult(BaseModel):
    """JSONL result payload emitted by ``tags replace --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    target_images: int
    changed: int
    skipped: int
    errors: int
    dry_run: bool

    model_config = ConfigDict(title="TagsReplaceResult")


class TagsAddInputSchema(BaseModel):
    """Implemented options surface accepted by ``tags add``."""

    project: str
    image_ids: str = Field(description="Comma-separated image IDs, max 500.")
    tags: str = Field(description="Comma-separated tags to add.")
    apply: bool = False

    model_config = ConfigDict(title="TagsAddInput")


class TagsRemoveInputSchema(BaseModel):
    """Implemented options surface accepted by ``tags remove``."""

    project: str
    image_ids: str = Field(description="Comma-separated image IDs, max 500.")
    tags: str = Field(description="Comma-separated tags to remove.")
    apply: bool = False

    model_config = ConfigDict(title="TagsRemoveInput")


class TagsReplaceInputSchema(BaseModel):
    """Implemented options surface accepted by ``tags replace``."""

    project: str
    image_ids: str = Field(description="Comma-separated image IDs, max 500.")
    from_tag: str = Field(description="Tag to replace.")
    to_tag: str = Field(description="Replacement tag.")
    apply: bool = False

    model_config = ConfigDict(title="TagsReplaceInput")


class ModelsRefreshResult(BaseModel):
    """JSONL result payload emitted by ``models refresh --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    discovered: int
    summary: str

    model_config = ConfigDict(title="ModelsRefreshResult")


class BatchJobResult(BaseModel):
    """JSONL result payload for batch commands returning a job."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    job_id: int | None = None
    job: dict[str, Any] | None = None

    model_config = ConfigDict(title="BatchJobResult")


class BatchFetchResult(BaseModel):
    """JSONL result payload emitted by ``batch fetch --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    job_id: int
    provider_status: str | None = None
    items: int
    succeeded: int
    failed: int
    artifacts: list[dict[str, Any]]

    model_config = ConfigDict(title="BatchFetchResult")


class BatchImportResult(BaseModel):
    """JSONL result payload emitted by ``batch import --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    job_id: int | None = None
    imported: int
    skipped: int
    errors: int
    total: int
    job_imported: bool

    model_config = ConfigDict(title="BatchImportResult")


class ProviderBatchJob(BaseModel):
    """JSONL payload describing a persisted provider batch job (``_job_dict``).

    Emitted as an item row by ``batch list --json`` and embedded as the ``job``
    field of the ``batch status`` result. Timestamp fields are ISO-8601 strings
    (the CLI emitter serializes ``datetime`` via ``default=str``).
    """

    id: int
    provider: str
    provider_job_id: str | None = None
    status: str
    provider_status: str | None = None
    endpoint: str | None = None
    model_id: int | None = None
    request_count: int
    succeeded_count: int
    failed_count: int
    canceled_count: int
    expired_count: int
    submitted_at: str | None = None
    completed_at: str | None = None
    canceled_at: str | None = None
    expires_at: str | None = None
    imported_at: str | None = None

    model_config = ConfigDict(title="ProviderBatchJob")


class ProviderBatchItemRecord(BaseModel):
    """JSONL item payload for a provider batch item (``batch status --items --json``).

    ``--items`` を付けた ``batch status --json`` で、job 配下の per-image item ごとに
    1 行ずつ emit される。rating_preflight の重複 submit 確認・audit に使用できる。
    """

    id: int
    job_id: int
    custom_id: str
    image_id: int | None = None
    model_id: int | None = None
    task_type: str | None = None
    status: str
    error_type: str | None = None
    error_message: str | None = None

    model_config = ConfigDict(title="ProviderBatchItemRecord")


class BatchStatusResult(BaseModel):
    """JSONL result payload emitted by ``batch status --json``.

    ``--items`` が指定された場合、result 行の前に ``ProviderBatchItemRecord`` item 行が
    emit される。``items_count`` / ``items_limit`` / ``items_offset`` / ``items_has_more``
    はいずれも ``--items`` 指定時のみ非 null になる。
    """

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    job: ProviderBatchJob | None = None
    items_count: int | None = Field(
        default=None,
        description="Number of item rows emitted (only when --items is set).",
    )
    items_limit: int | None = Field(default=None, description="Page size used for items query.")
    items_offset: int | None = Field(default=None, description="Rows skipped in items query.")
    items_has_more: bool | None = Field(
        default=None,
        description="True when len(items) >= limit, indicating further pages may exist.",
    )

    model_config = ConfigDict(title="BatchStatusResult")


class AnnotateRunModelResult(BaseModel):
    """Per-model annotation entry inside an ``annotate run`` item row."""

    model: str
    tags: list[str]
    score: float | int | None = None
    error: str | None = None

    model_config = ConfigDict(title="AnnotateRunModelResult")


class AnnotateRunItem(BaseModel):
    """JSONL item payload emitted per annotated image by ``annotate run --json``."""

    type: Literal["annotation"] = "annotation"
    image_id: int | None = None
    phash: str
    file_path: str | None = None
    models: list[AnnotateRunModelResult]

    model_config = ConfigDict(title="AnnotateRunItem")


class AnnotateRunResult(BaseModel):
    """JSONL terminal result payload emitted by ``annotate run --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    annotated: int
    skipped: int
    errors: int
    loaded: int
    results: int
    models: list[str]

    model_config = ConfigDict(title="AnnotateRunResult")


class AnnotateImportBatchResult(BaseModel):
    """JSONL result payload emitted by ``annotate import-batch --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    total_records: int
    parsed_ok: int
    parse_errors: int
    matched: int
    unmatched: int
    saved: int
    save_errors: int
    model_name: str | None = None
    dry_run: bool

    model_config = ConfigDict(title="AnnotateImportBatchResult")


class ErrorRecordItem(BaseModel):
    """JSONL item payload emitted by ``errors list --json``."""

    kind: Literal["item"] = "item"
    id: int
    operation_type: str
    error_type: str
    error_message: str
    model_name: str | None = None
    resolved_at: str | None = None
    created_at: str | None = None

    model_config = ConfigDict(title="ErrorRecordItem")


class ErrorListResult(BaseModel):
    """JSONL result payload emitted by ``errors list --json``."""

    kind: Literal["result"] = "result"
    ok: Literal[True] = True
    message: str
    count: int

    model_config = ConfigDict(title="ErrorListResult")


class ErrorsResolveResult(BaseModel):
    """JSONL result payload emitted by ``errors resolve --json``."""

    kind: Literal["result"] = "result"
    ok: bool
    message: str
    resolved: int
    dry_run: bool

    model_config = ConfigDict(title="ErrorsResolveResult")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool = False
    default: Any = None
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "required": self.required,
        }
        if self.default is not None:
            data["default"] = self.default
        if self.description:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class ModelSpec:
    name: str
    role: Literal["input", "output", "error"]
    fields: tuple[FieldSpec, ...] = ()
    description: str = ""
    schema_model: type[BaseModel] | None = None

    def compact_payload(self, command: str) -> dict[str, Any]:
        return {
            "type": "model",
            "command": command,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "fields": [field.to_dict() for field in self.fields],
        }

    def schema_payload(self, command: str) -> dict[str, Any] | None:
        if self.schema_model is None:
            return None
        return {
            "type": "schema",
            "command": command,
            "name": self.name,
            "role": self.role,
            "schema": self.schema_model.model_json_schema(),
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    path: str
    summary: str
    read_only: bool
    side_effects: tuple[SideEffect, ...]
    inputs: tuple[ModelSpec, ...]
    outputs: tuple[ModelSpec, ...]
    errors: tuple[ModelSpec, ...] = field(default_factory=tuple)
    search_schema: type[BaseModel] | None = None

    def tool_payload(self) -> dict[str, Any]:
        return {
            "type": "tool",
            "name": self.name,
            "path": self.path,
            "summary": self.summary,
            "read_only": self.read_only,
            "side_effects": list(self.side_effects),
        }


def _f(
    name: str,
    type_: str,
    *,
    required: bool = False,
    default: Any = None,
    description: str = "",
) -> FieldSpec:
    return FieldSpec(name=name, type=type_, required=required, default=default, description=description)


ERROR_MODEL = ModelSpec(
    name="CliErrorResponse",
    role="error",
    description="Structured error payload emitted as kind=error by the CLI boundary.",
    fields=(
        _f("kind", "error", required=True),
        _f("ok", "false", required=True),
        _f("code", "str", required=True),
        _f("message", "str", required=True),
        _f("retryable", "bool", required=True),
        _f("user_action_required", "bool", required=True),
        _f("hint", "str?"),
        _f("details", "dict?"),
    ),
    schema_model=CliErrorResponse,
)


def _input(
    name: str,
    fields: tuple[FieldSpec, ...],
    description: str = "",
    schema: type[BaseModel] | None = None,
) -> ModelSpec:
    return ModelSpec(name=name, role="input", fields=fields, description=description, schema_model=schema)


def _output(
    name: str, fields: tuple[FieldSpec, ...], description: str = "", schema: type[BaseModel] | None = None
) -> ModelSpec:
    return ModelSpec(name=name, role="output", fields=fields, description=description, schema_model=schema)


TOOL_SPECS: dict[str, ToolSpec] = {
    "version": ToolSpec(
        name="version",
        path="version",
        summary="Show version information.",
        read_only=True,
        side_effects=(),
        inputs=(),
        outputs=(
            _output(
                "VersionResult",
                (_f("name", "str"), _f("version", "str"), _f("description", "str")),
                schema=VersionResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "status": ToolSpec(
        name="status",
        path="status",
        summary="Show system status (config file and API key availability).",
        read_only=True,
        side_effects=("file_read",),
        inputs=(),
        outputs=(
            _output(
                "StatusResult",
                (
                    _f("environment", "str"),
                    _f("phase", "str"),
                    _f("config_found", "bool"),
                    _f("api_keys", "dict[str,bool]?"),
                    _f("initialized_services", "dict[str,bool]?"),
                ),
                schema=StatusResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "project create": ToolSpec(
        name="project create",
        path="project create",
        summary="Create a project.",
        read_only=False,
        side_effects=("file_write", "db_write"),
        inputs=(
            _input(
                "ProjectCreateInput",
                (_f("name", "str", required=True), _f("description", "str?")),
                schema=ProjectCreateRequest,
            ),
        ),
        outputs=(
            _output(
                "ProjectCreateResult",
                (_f("name", "str"), _f("path", "path")),
                schema=ProjectCreateResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "project list": ToolSpec(
        name="project list",
        path="project list",
        summary="List projects.",
        read_only=True,
        side_effects=("file_read", "db_read"),
        inputs=(
            _input(
                "ProjectListInput",
                (
                    # `--format table` は人間向け既定 (ADR 0058)。機械可読出力は
                    # グローバル --json (JSONL)。legacy `--format json` は非推奨。
                    _f("format", "table", default="table"),
                ),
            ),
        ),
        outputs=(
            _output(
                "ProjectListItem",
                (_f("name", "str"), _f("created", "str"), _f("path", "path")),
                schema=ProjectListItem,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "project delete": ToolSpec(
        name="project delete",
        path="project delete",
        summary="Delete a project.",
        read_only=False,
        side_effects=("file_write", "db_write"),
        inputs=(
            _input(
                "ProjectDeleteInput",
                (
                    _f("name", "str", required=True),
                    # JSON mode は対話 confirm を stdout に書けないため --force 必須
                    # (Issue #659)。introspection 契約上も agent に必須要件を明示する。
                    _f(
                        "force",
                        "bool",
                        default=False,
                        description="Required in JSON mode (--json): omitting it yields INVALID_INPUT "
                        "since interactive confirmation cannot be driven over stdout.",
                    ),
                ),
            ),
        ),
        outputs=(_output("ProjectDeleteResult", (_f("name", "str"),), schema=ProjectDeleteResult),),
        errors=(ERROR_MODEL,),
    ),
    "images register": ToolSpec(
        name="images register",
        path="images register",
        summary="Register images from a file or directory into a project.",
        read_only=False,
        side_effects=("file_read", "file_write", "db_read", "db_write"),
        inputs=(
            _input(
                "ImagesRegisterInput",
                (
                    _f("path", "path", required=True),
                    _f("project", "str", required=True),
                    _f("skip_duplicates", "bool", default=True),
                ),
            ),
        ),
        outputs=(
            _output(
                "ImagesRegisterResult",
                (_f("total", "int"), _f("registered", "int"), _f("skipped", "int"), _f("errors", "int")),
                schema=ImagesRegisterResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "images list": ToolSpec(
        name="images list",
        path="images list",
        summary=(
            "List images in a project. Count-first (ADR 0060): default returns only the matching "
            "count; --fetch returns id+path rows but only when the total is <= 500."
        ),
        read_only=True,
        side_effects=("db_read", "file_read"),
        inputs=(
            _input(
                "ImagesListInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "fetch",
                        "bool",
                        default=False,
                        description="Fetch id+path rows instead of only the count. Succeeds only when "
                        "total matches are <= 500; a larger result yields RESULT_SET_TOO_LARGE "
                        "(narrow the filter). Omitted (default) returns the count only.",
                    ),
                    _f(
                        "limit",
                        "int[1,500]",
                        default=500,
                        description="Page size within a <= 500 match set (ADR 0060). Does NOT bypass the "
                        "count-first gate: a total over 500 is rejected regardless of limit.",
                    ),
                    _f(
                        "offset",
                        "int>=0",
                        default=0,
                        description="Rows to skip within a <= 500 match set. Pagination is bounded to the "
                        "working set; it is not a way to page through a result larger than 500.",
                    ),
                    _f("unrated", "bool", default=False),
                ),
            ),
        ),
        outputs=(
            _output(
                "ImagesListItem",
                (_f("image_id", "int?"), _f("file_path", "str?")),
                schema=ImagesListItem,
            ),
            _output(
                "ImagesListResult",
                (
                    _f(
                        "count",
                        "int",
                        description="Item rows emitted in this response (0 in count-first mode). "
                        "Use total for the match count.",
                    ),
                    _f("total", "int?", description="Total number of matching images."),
                    _f("limit", "int?"),
                    _f("offset", "int?"),
                    _f("has_more", "bool?"),
                ),
                schema=ImagesListResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "images update": ToolSpec(
        name="images update",
        path="images update",
        summary="Add tags to images in a project.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "ImagesUpdateInput",
                (
                    _f("project", "str", required=True),
                    _f("tags", "csv[str]", required=True),
                    _f("image_id", "int?"),
                ),
            ),
        ),
        outputs=(
            _output(
                "ImagesUpdateResult",
                (
                    _f("project", "str?"),
                    _f("target_images", "int?"),
                    _f("tags", "list[str]?"),
                    _f("added", "int?"),
                    _f("failed_tags", "list[str]?"),
                    _f("count", "int?", description="Set to 0 on the no-image (no-target) success path."),
                ),
                schema=ImagesUpdateResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "annotate run": ToolSpec(
        name="annotate run",
        path="annotate run",
        summary="Run annotation for selected project images.",
        read_only=False,
        side_effects=("db_read", "db_write", "file_read", "network"),
        inputs=(
            _input(
                "AnnotateRunInput",
                (
                    _f("project", "str", required=True),
                    _f("model", "list[str]", required=True),
                    _f("limit", "int>=1?"),
                    _f("offset", "int>=0", default=0),
                    _f("image_id", "list[int]?"),
                    _f("batch_size", "int>=1", default=10),
                    _f("unrated", "bool", default=False),
                    _f("missing_model", "str?"),
                ),
            ),
        ),
        outputs=(
            _output(
                "AnnotateRunItem",
                (
                    _f("type", "annotation"),
                    _f("image_id", "int?"),
                    _f("phash", "str"),
                    _f("file_path", "str?"),
                    _f("models", "list[AnnotateRunModelResult]"),
                ),
                schema=AnnotateRunItem,
            ),
            _output(
                "AnnotateRunResult",
                (
                    _f("annotated", "int"),
                    _f("skipped", "int"),
                    _f("errors", "int"),
                    _f("loaded", "int"),
                    _f("results", "int"),
                    _f("models", "list[str]"),
                ),
                schema=AnnotateRunResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "annotate import-batch": ToolSpec(
        name="annotate import-batch",
        path="annotate import-batch",
        summary="Import provider batch annotation JSONL results.",
        read_only=False,
        side_effects=("file_read", "db_read", "db_write"),
        inputs=(
            _input(
                "AnnotateImportBatchInput",
                (
                    _f("project", "str", required=True),
                    _f("jsonl_dir", "path", required=True),
                    _f("dry_run", "bool", default=False),
                    _f("model_name", "str?"),
                ),
            ),
        ),
        outputs=(
            _output(
                "AnnotateImportBatchResult",
                (
                    _f("total_records", "int"),
                    _f("parsed_ok", "int"),
                    _f("parse_errors", "int"),
                    _f("matched", "int"),
                    _f("unmatched", "int"),
                    _f("saved", "int"),
                    _f("save_errors", "int"),
                    _f("model_name", "str?"),
                    _f("dry_run", "bool"),
                ),
                schema=AnnotateImportBatchResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "export create": ToolSpec(
        name="export create",
        path="export create",
        summary="Export a dataset from a list of image IDs. Use 'images search' to resolve IDs first.",
        read_only=False,
        side_effects=("db_read", "file_read", "file_write"),
        inputs=(
            _input(
                "ExportCreateInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description="Comma-separated image IDs, e.g. '1,2,3'. Use images search to resolve IDs.",
                    ),
                    _f("output", "path", required=True),
                    _f("resolution", "int", default=512),
                ),
                schema=ExportCreateInputSchema,
            ),
        ),
        outputs=(
            _output(
                "ExportCreateResult",
                (
                    _f("output_path", "path?"),
                    _f("total_images", "int?"),
                    _f("resolution", "int?"),
                    _f("count", "int?"),
                ),
                schema=ExportCreateResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "images search": ToolSpec(
        name="images search",
        path="images search",
        summary="Search images by JSON query. Returns image_ids for use with export create or tags commands.",
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "ImagesSearchInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "query",
                        "json|'-'",
                        description="JSON search schema string, or '-' to read from stdin.",
                    ),
                    _f(
                        "query_file",
                        "path?",
                        description="Path to a JSON file containing the search schema.",
                    ),
                ),
                description="Pass exactly one of --query or --query-file.",
            ),
            ModelSpec(
                name="ImageSearchQuery",
                role="input",
                description="JSON body schema passed via --query or --query-file.",
                fields=(
                    _f("image_ids", "list[int]?"),
                    _f("tags", "list[str]?"),
                    _f("excluded_tags", "list[str]?"),
                    _f("caption", "str?"),
                    _f("manual_rating", "str?"),
                    _f("ai_rating", "str?"),
                    _f("score_min", "float?"),
                    _f("score_max", "float?"),
                    _f("only_unrated", "bool", default=False),
                    _f("missing_model", "str?"),
                    _f("include_nsfw", "bool", default=False),
                    _f("limit", "int[1,500]", default=500),
                    _f("offset", "int>=0", default=0),
                ),
                schema_model=ImageSearchQuery,
            ),
        ),
        outputs=(
            _output(
                "ImagesListItem",
                (_f("image_id", "int?"), _f("file_path", "str?")),
                schema=ImagesListItem,
            ),
            _output(
                "ImagesListResult",
                (
                    _f("count", "int"),
                    _f("total", "int?"),
                    _f("limit", "int?"),
                    _f("offset", "int?"),
                    _f("has_more", "bool?"),
                ),
                schema=ImagesListResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "images show": ToolSpec(
        name="images show",
        path="images show",
        summary=(
            "Show current tags, captions, scores, and ratings for images (read-only). "
            "Use as judgment material before tags add/remove/replace."
        ),
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "ImagesShowInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description=(
                            "Comma-separated image IDs, max 500. "
                            "Positional form `images show 42 57` also works."
                        ),
                    ),
                    _f(
                        "include_rejected",
                        "bool",
                        default=False,
                        description="Include soft-rejected tags/captions in the output.",
                    ),
                ),
                schema=ImagesShowInputSchema,
            ),
        ),
        outputs=(
            _output(
                "ImagesShowItem",
                (
                    _f("image_id", "int"),
                    _f(
                        "metadata",
                        "dict | None",
                        description=(
                            "Image file metadata (stored_image_path/original_image_path/width/"
                            "height/format/filename/extension/phash/uuid). Null when unavailable."
                        ),
                    ),
                    _f("tags", "list[dict]"),
                    _f("captions", "list[dict]"),
                    _f("scores", "list[dict]"),
                    _f("score_labels", "list[dict]"),
                    _f("ratings", "list[dict]"),
                    _f("quality_summary", "dict"),
                ),
                schema=ImagesShowItem,
            ),
            _output(
                "ImagesShowResult",
                (_f("target_images", "int"),),
                schema=ImagesShowResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "tags add": ToolSpec(
        name="tags add",
        path="tags add",
        summary="Add tags to images. Default dry-run; use --apply to write.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "TagsAddInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description="Comma-separated image IDs, max 500.",
                    ),
                    _f("tags", "csv[str]", required=True, description="Comma-separated tags to add."),
                    _f("apply", "bool", default=False, description="Write to DB. Default is dry-run."),
                ),
                schema=TagsAddInputSchema,
            ),
        ),
        outputs=(
            _output(
                "TagsEditItem",
                (
                    _f("image_id", "int"),
                    _f("action", "add"),
                    _f("tags", "list[str]"),
                    _f("status", "str"),
                ),
                schema=TagsEditItem,
            ),
            _output(
                "TagsAddResult",
                (
                    _f("target_images", "int"),
                    _f("tags", "list[str]"),
                    _f("added", "int"),
                    _f("dry_run", "bool"),
                    _f(
                        "tag_resolutions",
                        "list[dict]",
                        description=(
                            "Per-tag classification (Issue #1174): `tag` / `classification` "
                            "(`exact` | `alias_resolved` | `typo_candidate` | `ambiguous` | "
                            "`unregistered`) / `canonical_tag` / `tag_id` (null = unresolved) / "
                            "`candidates` (typo/ambiguous suggestions, never auto-applied)."
                        ),
                    ),
                    _f(
                        "skipped_invalid_tags",
                        "list[str]",
                        description="Tags that normalized to empty (not added, not registered).",
                    ),
                    _f(
                        "unresolved_tag_count",
                        "int?",
                        description="Count of applied tags left with `tag_id=null` (apply mode only).",
                    ),
                    _f(
                        "would_add",
                        "int?",
                        description=(
                            "Estimated additions if --apply were run (dry-run only, Issue #1217). "
                            "Accounts for existing-duplicate skips."
                        ),
                    ),
                ),
                schema=TagsAddResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "tags remove": ToolSpec(
        name="tags remove",
        path="tags remove",
        summary="Remove tags from images. Default dry-run; use --apply to write.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "TagsRemoveInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description="Comma-separated image IDs, max 500.",
                    ),
                    _f("tags", "csv[str]", required=True, description="Comma-separated tags to remove."),
                    _f("apply", "bool", default=False, description="Write to DB. Default is dry-run."),
                ),
                schema=TagsRemoveInputSchema,
            ),
        ),
        outputs=(
            _output(
                "TagsEditItem",
                (
                    _f("image_id", "int"),
                    _f("action", "remove"),
                    _f("tags", "list[str]"),
                    _f("status", "str"),
                ),
                schema=TagsEditItem,
            ),
            _output(
                "TagsRemoveResult",
                (
                    _f("target_images", "int"),
                    _f("tags", "list[str]"),
                    _f("removed", "int"),
                    _f("dry_run", "bool"),
                    _f(
                        "mode",
                        "str",
                        description=(
                            "Removal mode (Issue #1217): `soft_reject` marks rejected_at and is "
                            "reversible via tags restore / re-add."
                        ),
                    ),
                    _f(
                        "would_remove",
                        "int?",
                        description=(
                            "Estimated soft-reject count if --apply were run (dry-run only, Issue #1217)."
                        ),
                    ),
                ),
                schema=TagsRemoveResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "tags replace": ToolSpec(
        name="tags replace",
        path="tags replace",
        summary="Replace a tag with another across images. Default dry-run; use --apply to write.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "TagsReplaceInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description="Comma-separated image IDs, max 500.",
                    ),
                    _f("from_tag", "str", required=True, description="Tag to replace."),
                    _f("to_tag", "str", required=True, description="Replacement tag."),
                    _f("apply", "bool", default=False, description="Write to DB. Default is dry-run."),
                ),
                schema=TagsReplaceInputSchema,
            ),
        ),
        outputs=(
            _output(
                "TagsEditItem",
                (
                    _f("image_id", "int"),
                    _f("action", "replace"),
                    _f("from", "str"),
                    _f("to", "str"),
                    _f("status", "str"),
                ),
                schema=TagsEditItem,
            ),
            _output(
                "TagsReplaceResult",
                (
                    _f("target_images", "int"),
                    _f("changed", "int"),
                    _f("skipped", "int"),
                    _f("errors", "int"),
                    _f("dry_run", "bool"),
                ),
                schema=TagsReplaceResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "tags translations show": ToolSpec(
        name="tags translations show",
        path="tags translations show",
        summary="Show ja/en translation status for tags (read-only). Issue #1173 / ADR 0085.",
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "TagsTranslationsShowInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        description=(
                            "Show translation status of these images' tags. Mutually exclusive with --tags."
                        ),
                    ),
                    _f(
                        "tags",
                        "csv[str]",
                        description="Tags to inspect, max 100. Mutually exclusive with --image-ids.",
                    ),
                    _f(
                        "missing_only",
                        "bool",
                        default=False,
                        description=(
                            "未翻訳 (tag, lang) ペアだけを 1 行 1 件で出力する (Issue #1211)。"
                            "出力行は text を埋めるだけで `translations add --file` に渡せる。"
                        ),
                    ),
                ),
            ),
        ),
        outputs=(
            _output(
                "MissingTranslationPairItem",
                (
                    _f("tag", "str"),
                    _f("tag_id", "int?"),
                    _f("lang", "ja | en"),
                    _f("text", "str", description="常に空文字。翻訳を埋めて add --file へ渡す。"),
                    _f("image_id", "int?", description="--image-ids 指定時のみ。"),
                ),
                description="--missing-only 指定時の item 行 (未翻訳ペア単位、Issue #1211)。",
            ),
            _output(
                "TagTranslationStatusItem",
                (
                    _f("tag", "str"),
                    _f("tag_id", "int?", description="null = 未解決 (tag DB 未登録)。"),
                    _f(
                        "translations",
                        "dict",
                        description=(
                            "`{ja,en: {candidates, preferred}}`。読みは ja/japanese・en/english を集約。"
                        ),
                    ),
                    _f("missing", "list[str]", description="訳が無い言語。"),
                ),
                description="--tags 指定時の item 行 (tag 単位)。",
            ),
            _output(
                "ImageTagTranslationStatusItem",
                (
                    _f("image_id", "int"),
                    _f(
                        "tags",
                        "list[dict]",
                        description="その画像のタグごとの TagTranslationStatusItem と同形式の配列。",
                    ),
                ),
                description="--image-ids 指定時の item 行 (画像単位のラッパー)。",
            ),
            _output(
                "TagsTranslationsShowResult",
                (
                    _f("target_tags", "int", description="対象タグ数。"),
                    _f("target_images", "int?", description="--image-ids 指定時のみ: 対象画像数。"),
                    _f(
                        "missing_pairs",
                        "int?",
                        description="--missing-only 指定時のみ: 未翻訳 (tag, lang) ペア数。",
                    ),
                ),
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "tags translations add": ToolSpec(
        name="tags translations add",
        path="tags translations add",
        summary="Add translations to tags (user DB overlay). Dry-run by default; --apply to write.",
        read_only=False,
        side_effects=("db_read", "db_write", "file_read"),
        inputs=(
            _input(
                "TagsTranslationsAddInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "tag",
                        "str",
                        description=(
                            "Target tag (--file と排他、単発時は --lang/--text と3点セット必須)。"
                            "tag_id 解決は tags add (Issue #1174) と同経路: "
                            "exact/alias は解決、真の新タグは --apply 時に user DB 登録、"
                            "typo/曖昧候補は候補提示でエラー (先に tags alias で確定)。"
                        ),
                    ),
                    _f("lang", "ja | en", description="書き込みは ja/en の一貫形。"),
                    _f("text", "str"),
                    _f(
                        "file",
                        "path",
                        description=(
                            "JSONL バッチ入力 (Issue #1211): 1 行 = "
                            '{"tag", "lang", "text"[, "preferred"]}。最大 100 行。'
                            "`translations show --missing-only` の出力行に text を埋めた形を受ける。"
                            "typo/曖昧・既存訳・登録失敗は per-item status で報告して続行する。"
                        ),
                    ),
                    _f("preferred", "bool", default=False, description="その言語の主訳にする。"),
                    _f("apply", "bool", default=False, description="Write to DB. Default is dry-run."),
                ),
            ),
        ),
        outputs=(
            _output(
                "TagsTranslationsAddItem",
                (
                    _f("tag", "str"),
                    _f("canonical_tag", "str?"),
                    _f("classification", "str"),
                    _f("tag_id", "int?"),
                    _f("language", "str"),
                    _f("translation", "str"),
                    _f("preferred", "bool"),
                    _f("registered_new_tag", "bool"),
                    _f(
                        "status",
                        "dry_run | changed | skipped_existing | skipped_candidates | skipped_invalid | error",
                        description=(
                            "skipped_* / error は --file バッチのみ (Issue #1211)。"
                            "skipped_existing = 同一訳が既に存在 (再実行が冪等)。"
                        ),
                    ),
                    _f("candidates", "list[str]?", description="skipped_candidates 時のみ: 類似候補。"),
                    _f("error", "str?", description="error 時のみ: 失敗理由。"),
                ),
                description="書き込みは user DB overlay のみ (base DB は不変)。タグ登録失敗 (tagdb #124 edge) は単発は DB_ERROR、バッチは per-item error で明示。",
            ),
            _output(
                "TagsTranslationsAddResult",
                (
                    _f("dry_run", "bool"),
                    _f("tag_id", "int?", description="単発 --tag 時のみ。"),
                    _f("language", "str?", description="単発 --tag 時のみ。"),
                    _f("total", "int?", description="--file バッチ時のみ: 入力行数。"),
                    _f("changed", "int?", description="--file バッチ時のみ: 書き込み件数。"),
                    _f(
                        "would_add",
                        "int?",
                        description="--file バッチ dry-run 時のみ: 書き込み見込み件数。",
                    ),
                    _f("skipped_existing", "int?", description="--file バッチ時のみ。"),
                    _f("skipped_candidates", "int?", description="--file バッチ時のみ。"),
                    _f("errors", "int?", description="--file バッチ時のみ。"),
                ),
                description="終端 result 行。既定は dry-run (dry_run=true) で書き込みなし。",
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "tags alias": ToolSpec(
        name="tags alias",
        path="tags alias",
        summary="Record a typo → preferred-tag alias in the user DB. Dry-run by default.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "TagsAliasInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "from",
                        "str",
                        required=True,
                        description=(
                            "Alias source (typo 等)。既存タグの付け替えは拒否。"
                            "既に同じ preferred へ解決される場合は no-op。"
                        ),
                    ),
                    _f(
                        "to",
                        "str",
                        required=True,
                        description="解決先 preferred タグ (tag DB に存在必須)。",
                    ),
                    _f("apply", "bool", default=False, description="Write to DB. Default is dry-run."),
                ),
            ),
        ),
        outputs=(
            _output(
                "TagsAliasResult",
                (
                    _f("dry_run", "bool", description="既定は dry-run (true) で書き込みなし。"),
                    _f("from_tag", "str"),
                    _f("to_tag", "str"),
                    _f("alias_tag_id", "int?"),
                    _f("status", "dry_run | changed | noop"),
                ),
                description="書き込みは user DB overlay のみ。no-op 経路 (既に同じ preferred へ解決) も同形。",
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "models refresh": ToolSpec(
        name="models refresh",
        path="models refresh",
        summary="Refresh available WebAPI model metadata and sync it into the DB.",
        read_only=False,
        side_effects=("network", "db_write", "db_read"),
        inputs=(_input("ModelsRefreshInput", (_f("project", "str?"),)),),
        outputs=(
            _output(
                "ModelsRefreshResult",
                (_f("discovered", "int"), _f("summary", "str")),
                schema=ModelsRefreshResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "models list": ToolSpec(
        name="models list",
        path="models list",
        summary="List available annotator models.",
        read_only=True,
        side_effects=("db_read", "file_read"),
        inputs=(
            _input(
                "ModelsListInput",
                (
                    _f("include_deprecated", "bool", default=False),
                    _f("type", "all|webapi|local", default="all"),
                    _f("category", "all|tagger|scorer|captioner|vision|rating", default="all"),
                    _f("route", "auto|direct|openrouter|all?"),
                    _f("show_unavailable", "bool", default=False),
                ),
            ),
        ),
        outputs=(
            _output(
                "ModelsListItem",
                (
                    _f("provider", "str"),
                    _f("route", "str"),
                    _f("litellm_id", "str"),
                    _f("type", "webapi|local"),
                    _f("category", "str"),
                    _f("available", "bool"),
                    _f("deprecated", "bool"),
                ),
                schema=ModelsListItem,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch submit": ToolSpec(
        name="batch submit",
        path="batch submit",
        summary="Submit registered images to a provider batch job.",
        read_only=False,
        side_effects=("db_read", "db_write", "network"),
        inputs=(
            _input(
                "BatchSubmitInput",
                (
                    _f("project", "str", required=True),
                    _f("model", "str", required=True),
                    _f(
                        "image_ids",
                        "csv[int]",
                        required=True,
                        description="Comma-separated image IDs, e.g. 2,7,11.",
                    ),
                    _f("provider", "openai|anthropic?"),
                    _f("endpoint", "str?"),
                    _f("prompt_profile", "str", default="default"),
                    _f("description", "str?"),
                    _f("task_type", "annotation|rating_preflight", default="annotation"),
                ),
            ),
        ),
        outputs=(
            _output("BatchJobResult", (_f("job_id", "int"), _f("job", "dict?")), schema=BatchJobResult),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch list": ToolSpec(
        name="batch list",
        path="batch list",
        summary="List persisted provider batch jobs.",
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "BatchListInput",
                (
                    _f("project", "str", required=True),
                    _f("provider", "str?"),
                    _f("status", "str?"),
                    _f("limit", "int[1,1000]", default=100),
                    _f("offset", "int>=0", default=0),
                ),
            ),
        ),
        outputs=(
            _output(
                "ProviderBatchJob",
                (
                    _f("id", "int"),
                    _f("provider", "str"),
                    _f("provider_job_id", "str?"),
                    _f("status", "str"),
                    _f("provider_status", "str?"),
                    _f("endpoint", "str?"),
                    _f("model_id", "int?"),
                    _f("request_count", "int"),
                    _f("succeeded_count", "int"),
                    _f("failed_count", "int"),
                    _f("canceled_count", "int"),
                    _f("expired_count", "int"),
                    _f("submitted_at", "str?"),
                    _f("completed_at", "str?"),
                    _f("canceled_at", "str?"),
                    _f("expires_at", "str?"),
                    _f("imported_at", "str?"),
                ),
                schema=ProviderBatchJob,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch status": ToolSpec(
        name="batch status",
        path="batch status",
        summary=(
            "Show provider batch job status. Pass --items to list per-image items "
            "(custom_id, image_id, model_id, task_type, status, error_type); "
            "useful for auditing duplicate rating_preflight submissions."
        ),
        read_only=False,
        side_effects=("db_read", "db_write", "network"),
        inputs=(
            _input(
                "BatchStatusInput",
                (
                    _f("job_id", "int", required=True),
                    _f("project", "str", required=True),
                    _f("refresh", "bool", default=True),
                    _f(
                        "items",
                        "bool",
                        default=False,
                        description=(
                            "Emit ProviderBatchItemRecord item rows before the result. "
                            "Use to inspect per-image item state or detect duplicate submissions."
                        ),
                    ),
                    _f(
                        "limit",
                        "int[1,500]",
                        default=500,
                        description="Page size for items query (only when --items is set).",
                    ),
                    _f(
                        "offset",
                        "int>=0",
                        default=0,
                        description="Rows to skip in items query (only when --items is set).",
                    ),
                    _f(
                        "item_status",
                        "str?",
                        description="Filter items by status when --items is set (e.g. succeeded, failed).",
                    ),
                ),
            ),
        ),
        outputs=(
            _output(
                "ProviderBatchItemRecord",
                (
                    _f("id", "int"),
                    _f("job_id", "int"),
                    _f("custom_id", "str"),
                    _f("image_id", "int?"),
                    _f("model_id", "int?"),
                    _f("task_type", "str?"),
                    _f("status", "str"),
                    _f("error_type", "str?"),
                    _f("error_message", "str?"),
                ),
                description="Emitted per item when --items is set. Precedes the BatchStatusResult row.",
                schema=ProviderBatchItemRecord,
            ),
            _output(
                "BatchStatusResult",
                (
                    _f("job", "ProviderBatchJob"),
                    _f(
                        "items_count",
                        "int?",
                        description="Number of item rows emitted (null when --items is not set).",
                    ),
                    _f("items_limit", "int?"),
                    _f("items_offset", "int?"),
                    _f("items_has_more", "bool?"),
                ),
                schema=BatchStatusResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch cancel": ToolSpec(
        name="batch cancel",
        path="batch cancel",
        summary="Cancel a provider batch job.",
        read_only=False,
        side_effects=("db_read", "db_write", "network"),
        inputs=(
            _input(
                "BatchCancelInput",
                (_f("job_id", "int", required=True), _f("project", "str", required=True)),
            ),
        ),
        outputs=(
            _output("BatchJobResult", (_f("job_id", "int"), _f("job", "dict?")), schema=BatchJobResult),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch fetch": ToolSpec(
        name="batch fetch",
        path="batch fetch",
        summary="Fetch normalized provider batch results and artifacts.",
        read_only=False,
        side_effects=("db_read", "db_write", "file_write", "network"),
        inputs=(
            _input(
                "BatchFetchInput",
                (
                    _f("job_id", "int", required=True),
                    _f("project", "str", required=True),
                    _f("output_dir", "path?"),
                ),
            ),
        ),
        outputs=(
            _output(
                "BatchFetchResult",
                (
                    _f("job_id", "int"),
                    _f("provider_status", "str?"),
                    _f("items", "int"),
                    _f("succeeded", "int"),
                    _f("failed", "int"),
                    _f("artifacts", "list[dict]"),
                ),
                schema=BatchFetchResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch import": ToolSpec(
        name="batch import",
        path="batch import",
        summary="Fetch and import provider batch results into annotations.",
        read_only=False,
        side_effects=("db_read", "db_write", "file_write", "network"),
        inputs=(
            _input(
                "BatchImportInput",
                (
                    _f("job_id", "int", required=True),
                    _f("project", "str", required=True),
                    _f("output_dir", "path?"),
                ),
            ),
        ),
        outputs=(
            _output(
                "BatchImportResult",
                (
                    _f("job_id", "int?"),
                    _f("imported", "int"),
                    _f("skipped", "int"),
                    _f("errors", "int"),
                    _f("total", "int"),
                    _f("job_imported", "bool"),
                ),
                schema=BatchImportResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "errors list": ToolSpec(
        name="errors list",
        path="errors list",
        summary="List error records. Default: unresolved only.",
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "ErrorsListInput",
                (
                    _f("project", "str", required=True),
                    _f(
                        "operation",
                        "str?",
                        description="Filter by operation_type (search/registration/annotation)",
                    ),
                    _f("error_type", "str?", description="Filter by error_type"),
                    _f("message_contains", "str?", description="Partial match on error_message"),
                    _f("all", "bool", default=False, description="Include resolved records"),
                    _f("limit", "int", default=50, description="Max records (max 500)"),
                    _f("offset", "int", default=0),
                ),
            ),
        ),
        outputs=(
            _output(
                "ErrorRecordItem",
                (
                    _f("id", "int"),
                    _f("operation_type", "str"),
                    _f("error_type", "str"),
                    _f("error_message", "str"),
                    _f("model_name", "str?"),
                    _f("resolved_at", "str?"),
                    _f("created_at", "str?"),
                ),
                schema=ErrorRecordItem,
            ),
            _output(
                "ErrorListResult",
                (_f("count", "int"),),
                schema=ErrorListResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "errors get": ToolSpec(
        name="errors get",
        path="errors get",
        summary=(
            "Get a single error record by ID (full detail). "
            "`list` は error_message を切り詰め stack_trace / file_path / image_id を省くため、"
            "1 件の全容を確認するには本コマンドを使う。"
        ),
        read_only=True,
        side_effects=("db_read",),
        inputs=(
            _input(
                "ErrorsGetInput",
                (
                    _f(
                        "error_id",
                        "int",
                        required=True,
                        description="Error record ID to retrieve (positional).",
                    ),
                    _f("project", "str", required=True),
                ),
            ),
        ),
        outputs=(
            _output(
                "ErrorRecordDetailItem",
                (
                    _f("id", "int"),
                    _f("image_id", "int?"),
                    _f("operation_type", "str"),
                    _f("error_type", "str"),
                    _f("error_message", "str"),
                    _f("stack_trace", "str?"),
                    _f("file_path", "str?"),
                    _f("model_name", "str?"),
                    _f("resolved_at", "str?"),
                    _f("created_at", "str?"),
                ),
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "errors resolve": ToolSpec(
        name="errors resolve",
        path="errors resolve",
        summary="Mark error records as resolved. Use --dry-run to preview.",
        read_only=False,
        side_effects=("db_read", "db_write"),
        inputs=(
            _input(
                "ErrorsResolveInput",
                (
                    _f("project", "str", required=True),
                    _f("ids", "csv[int]?", description="Comma-separated error record IDs"),
                    _f("operation", "str?", description="Bulk-resolve by operation_type"),
                    _f("error_type", "str?", description="Bulk-resolve by error_type"),
                    _f(
                        "message_contains",
                        "str?",
                        description="Bulk-resolve by partial message match",
                    ),
                    _f("dry_run", "bool", default=False, description="Preview count without writing"),
                ),
            ),
        ),
        outputs=(
            _output(
                "ErrorsResolveResult",
                (
                    _f("ok", "bool"),
                    _f("resolved", "int"),
                    _f("dry_run", "bool"),
                ),
                schema=ErrorsResolveResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
}


def iter_tool_specs() -> tuple[ToolSpec, ...]:
    """Return all command specs in stable path order."""
    return tuple(TOOL_SPECS[path] for path in sorted(TOOL_SPECS))


def get_tool_spec(path: str) -> ToolSpec:
    """Resolve a space-separated command path."""
    normalized = " ".join(path.split())
    try:
        return TOOL_SPECS[normalized]
    except KeyError as exc:
        known = ", ".join(sorted(TOOL_SPECS))
        raise ValueError(f"Unknown command path: {path!r}. Known commands: {known}") from exc


def emit_list_commands() -> None:
    """Emit one ``item(type=tool)`` row per command and a terminal result row."""
    specs = iter_tool_specs()
    for spec in specs:
        emit_item(spec.tool_payload())
    emit_result(f"{len(specs)} command(s)", count=len(specs))


def emit_describe(command: str, schema: SchemaMode = "compact") -> None:
    """Emit command metadata in compact or JSON Schema mode."""
    spec = get_tool_spec(command)
    emit_item(spec.tool_payload())

    item_count = 1
    if schema == "json_schema":
        seen: set[str] = set()
        for model in (*spec.inputs, *spec.outputs, *spec.errors):
            payload = model.schema_payload(spec.path)
            if payload is None or payload["name"] in seen:
                continue
            seen.add(payload["name"])
            emit_item(payload)
            item_count += 1
    else:
        for model in (*spec.inputs, *spec.outputs, *spec.errors):
            emit_item(model.compact_payload(spec.path))
            item_count += 1

    emit_result(f"Description for {spec.path}", command=spec.path, count=item_count, schema=schema)
