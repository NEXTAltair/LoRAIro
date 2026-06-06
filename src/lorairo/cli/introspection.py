"""CLI command introspection registry and emitters (ADR 0059).

The wire format intentionally reuses ADR 0057 ``item`` / ``result`` rows.
Payload ``type`` differentiates tools, compact models, and JSON Schema rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from lorairo.api.types import (
    BatchImportResultResponse,
    ExportResult,
    ProjectCreateRequest,
    ProjectInfo,
    RegistrationResult,
    StatusResponse,
)
from lorairo.cli._emit import emit_item, emit_result

SideEffect = Literal["db_read", "db_write", "file_read", "file_write", "network"]
SchemaMode = Literal["compact", "json_schema"]


class ImageFilterCriteriaSchema(BaseModel):
    """Public JSON Schema mirror for ImageFilterCriteria.

    ImageFilterCriteria is a dataclass used by the DB/repository layer. This
    Pydantic mirror is the public, curated search contract exposed by CLI
    introspection; it is not a raw DB schema.
    """

    tags: list[str] | None = Field(default=None, description="Tags to include in image search.")
    caption: str | None = Field(default=None, description="Caption text filter.")
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
    """JSONL item payload emitted by ``images list --json``."""

    id: int | None = None
    filename: str
    tags: int
    annotated: bool

    model_config = ConfigDict(title="ImagesListItem")


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


def _input(name: str, fields: tuple[FieldSpec, ...], description: str = "") -> ModelSpec:
    return ModelSpec(name=name, role="input", fields=fields, description=description)


def _output(
    name: str, fields: tuple[FieldSpec, ...], description: str = "", schema: type[BaseModel] | None = None
) -> ModelSpec:
    return ModelSpec(name=name, role="output", fields=fields, description=description, schema_model=schema)


def _search_input(name: str, fields: tuple[FieldSpec, ...], description: str = "") -> tuple[ModelSpec, ...]:
    return (
        _input(name, fields, description),
        ModelSpec(
            name="ImageFilterCriteria",
            role="input",
            description="Public search filter contract shared by search-driven commands.",
            fields=(
                _f("tags", "list[str]?"),
                _f("caption", "str?"),
                _f("excluded_tags", "list[str]?"),
                _f("ratings", "manual_rating_filter | ai_rating_filter"),
                _f("scores", "score_min/score_max"),
                _f("image_ids", "list[int]?<=500"),
            ),
            schema_model=ImageFilterCriteriaSchema,
        ),
    )


TOOL_SPECS: dict[str, ToolSpec] = {
    "project create": ToolSpec(
        name="project create",
        path="project create",
        summary="Create a project.",
        read_only=False,
        side_effects=("file_write", "db_write"),
        inputs=(
            _input("ProjectCreateInput", (_f("name", "str", required=True), _f("description", "str?"))),
        ),
        outputs=(_output("ProjectInfo", (_f("name", "str"), _f("path", "path")), schema=ProjectInfo),),
        errors=(ERROR_MODEL,),
    ),
    "project list": ToolSpec(
        name="project list",
        path="project list",
        summary="List projects.",
        read_only=True,
        side_effects=("file_read", "db_read"),
        inputs=(_input("ProjectListInput", (_f("format", "table|json", default="table"),)),),
        outputs=(
            _output(
                "ProjectInfo",
                (_f("name", "str"), _f("created", "datetime"), _f("path", "path")),
                schema=ProjectInfo,
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
                "ProjectDeleteInput", (_f("name", "str", required=True), _f("force", "bool", default=False))
            ),
        ),
        outputs=(_output("StatusResponse", (_f("name", "str"),), schema=StatusResponse),),
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
                "RegistrationResult",
                (_f("total", "int"), _f("registered", "int"), _f("skipped", "int"), _f("errors", "int")),
                schema=RegistrationResult,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "images list": ToolSpec(
        name="images list",
        path="images list",
        summary="List images in a project.",
        read_only=True,
        side_effects=("db_read", "file_read"),
        inputs=(
            _input(
                "ImagesListInput",
                (
                    _f("project", "str", required=True),
                    _f("limit", "int>=1?"),
                    _f("unrated", "bool", default=False),
                ),
            ),
        ),
        outputs=(
            _output(
                "ImagesListItem",
                (_f("id", "int"), _f("filename", "str"), _f("tags", "int"), _f("annotated", "bool")),
                schema=ImagesListItem,
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
                "StatusResponse",
                (
                    _f("project", "str"),
                    _f("target_images", "int"),
                    _f("tags", "list[str]"),
                    _f("added", "int"),
                ),
                schema=StatusResponse,
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
        inputs=_search_input(
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
        outputs=(),
        errors=(ERROR_MODEL,),
        search_schema=ImageFilterCriteriaSchema,
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
                "BatchImportResultResponse",
                (_f("total_records", "int"), _f("saved", "int"), _f("save_errors", "int")),
                schema=BatchImportResultResponse,
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "export create": ToolSpec(
        name="export create",
        path="export create",
        summary="Export a filtered dataset from a project.",
        read_only=False,
        side_effects=("db_read", "file_read", "file_write"),
        inputs=_search_input(
            "ExportCreateInput",
            (
                _f("project", "str", required=True),
                _f("output", "path", required=True),
                _f("format", "txt|json", default="txt"),
                _f("resolution", "int", default=512),
                _f("tags", "csv[str]?"),
                _f("excluded_tags", "csv[str]?"),
                _f("caption", "str?"),
                _f("manual_rating", "rating?"),
                _f("ai_rating", "rating?"),
                _f("include_nsfw", "bool", default=False),
                _f("score_min", "float[0,10]?"),
                _f("score_max", "float[0,10]?"),
            ),
        ),
        outputs=(
            _output(
                "ExportResult",
                (
                    _f("output_path", "path"),
                    _f("total_images", "int"),
                    _f("format", "str"),
                    _f("resolution", "int"),
                ),
                schema=ExportResult,
            ),
        ),
        errors=(ERROR_MODEL,),
        search_schema=ImageFilterCriteriaSchema,
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
                "StatusResponse", (_f("discovered", "int"), _f("summary", "str")), schema=StatusResponse
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
                    _f("image_id", "list[int]", required=True),
                    _f("provider", "openai|anthropic?"),
                    _f("endpoint", "str?"),
                    _f("prompt_profile", "str", default="default"),
                    _f("description", "str?"),
                    _f("task_type", "annotation|rating_preflight", default="annotation"),
                ),
            ),
        ),
        outputs=(
            _output("StatusResponse", (_f("job_id", "int"), _f("job", "dict?")), schema=StatusResponse),
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
                (_f("id", "int"), _f("provider", "str"), _f("status", "str"), _f("request_count", "int")),
            ),
        ),
        errors=(ERROR_MODEL,),
    ),
    "batch status": ToolSpec(
        name="batch status",
        path="batch status",
        summary="Show provider batch job status.",
        read_only=False,
        side_effects=("db_read", "db_write", "network"),
        inputs=(
            _input(
                "BatchStatusInput",
                (
                    _f("job_id", "int", required=True),
                    _f("project", "str", required=True),
                    _f("refresh", "bool", default=True),
                ),
            ),
        ),
        outputs=(_output("ProviderBatchJob", (_f("job", "dict"),)),),
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
            _output("StatusResponse", (_f("job_id", "int"), _f("job", "dict?")), schema=StatusResponse),
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
                "StatusResponse",
                (
                    _f("job_id", "int"),
                    _f("items", "int"),
                    _f("succeeded", "int"),
                    _f("failed", "int"),
                    _f("artifacts", "list[dict]"),
                ),
                schema=StatusResponse,
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
                "StatusResponse",
                (_f("imported", "int"), _f("skipped", "int"), _f("errors", "int"), _f("total", "int")),
                schema=StatusResponse,
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
