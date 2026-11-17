"""Derive public argument schemas from the registered Click/Typer interface."""

from __future__ import annotations

import re
from enum import Enum
from types import GenericAlias
from typing import Any, Literal, cast, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, create_model
from typer.core import TyperArgument, TyperCommand, TyperGroup, TyperOption


def command_tree() -> tuple[TyperCommand | TyperGroup, dict[str, TyperCommand]]:
    """Inspect registration without invoking callbacks or initializing a project."""
    from typer.main import get_command

    from lorairo.cli.main import app

    root = get_command(app)
    leaves: dict[str, TyperCommand] = {}

    def walk(command: TyperCommand | TyperGroup, path: str) -> None:
        if isinstance(command, TyperGroup):
            for name, child in command.commands.items():
                if not isinstance(child, (TyperCommand, TyperGroup)):
                    raise TypeError(f"未対応の CLI コマンド型: {type(child).__name__}")
                walk(child, f"{path} {name}".strip())
        else:
            leaves[path] = command

    walk(root, "")
    return root, leaves


def parameter_name(parameter: TyperArgument | TyperOption, names: set[str]) -> str:
    """Preserve published names while exposing actual flags/destinations separately."""
    candidates = [parameter.name or ""]
    candidates.extend(option[2:].replace("-", "_") for option in parameter.opts if option.startswith("--"))
    candidates.append((parameter.name or "").removesuffix("_csv"))
    if parameter.name == "image_ids_positional":
        candidates.append("image_ids")
    return next((name for name in candidates if name in names), candidates[0])


def _choice_type(values: tuple[Any, ...], *, case_sensitive: bool) -> tuple[Any, dict[str, Any]]:
    choices = tuple(value.value if isinstance(value, Enum) else value for value in values)
    if case_sensitive:
        return Literal[choices], {}
    pattern = (
        "^(?:"
        + "|".join(
            "".join(
                f"[{char.lower()}{char.upper()}]" if char.isalpha() else re.escape(char)
                for char in str(value)
            )
            for value in choices
        )
        + ")$"
    )
    return str, {"pattern": pattern}


def _parameter_type(
    parameter: TyperArgument | TyperOption, path: str, public_name: str
) -> tuple[Any, dict[str, Any]]:
    # Typer 0.29 は Click の ParamType ではなく登録時の型情報を保持する。
    descriptor = parameter.type_descriptor
    annotation = descriptor.annotation
    if get_origin(annotation) is list:
        annotation = get_args(annotation)[0]
    if annotation not in (bool, int, float):
        annotation = str
    constraints: dict[str, Any] = {}
    info = descriptor.parameter_info
    if info.min is not None:
        constraints["ge"] = info.min
    if info.max is not None:
        constraints["le"] = info.max
    if descriptor.choices is not None:
        annotation, choice_constraints = _choice_type(
            descriptor.choices, case_sensitive=info.case_sensitive
        )
        constraints.update(choice_constraints)
    constraints.update(_runtime_constraints(path, public_name))
    if "gt" in constraints:
        constraints.pop("ge", None)
    return annotation, constraints


def _runtime_constraints(path: str, name: str) -> dict[str, Any]:
    if path == "errors list" and name in {"limit", "offset"}:
        from lorairo.cli.commands.errors import MAX_LIST_LIMIT

        return {"ge": 0, "le": MAX_LIST_LIMIT} if name == "limit" else {"ge": 0}
    if path == "images process" and name == "resolution":
        return {"multiple_of": 32}
    if path == "images crop-detect" and name in {"nms_iou", "existing_iou"}:
        return {"gt": 0.0, "le": 1.0}
    return {}


def input_model(
    name: str, command: TyperCommand, descriptions: dict[str, str], *, path: str
) -> type[BaseModel]:
    """Generate types, aliases, bounds and defaults from the parser's parameters.

    Runtime-only checks remain documented explicitly. The narrow bounds below are
    implemented in command bodies, so Click alone cannot expose them.
    """
    definitions: dict[str, Any] = {}
    metadata_by_name: dict[str, dict[str, Any]] = {}
    for parameter in command.params:
        if not isinstance(parameter, (TyperArgument, TyperOption)):
            raise TypeError(f"未対応の CLI 引数型: {type(parameter).__name__}")
        if parameter.is_eager:
            continue
        public_name = parameter_name(parameter, set(descriptions))
        aliases = [*parameter.opts, *getattr(parameter, "secondary_opts", [])]
        if public_name in definitions:
            metadata_by_name[public_name]["x-cli-options"].extend(aliases)
            metadata_by_name[public_name]["x-cli-destinations"].append(parameter.name)
            metadata_by_name[public_name]["x-cli-locations"].append(
                "argument" if isinstance(parameter, TyperArgument) else "option"
            )
            continue
        annotation, constraints = _parameter_type(parameter, path, public_name)
        default: Any = parameter.default
        if isinstance(default, Enum):
            default = default.value
        if getattr(parameter, "multiple", False):
            annotation = GenericAlias(list, annotation)
            default = list(default) if default is not None else None
        if path == "annotate run" and public_name == "output":
            annotation = type(None)
        required = parameter.required or (path == "images show" and public_name == "image_ids")
        if not required and default is None:
            annotation = annotation | None
        metadata: dict[str, Any] = {
            "x-cli-options": aliases,
            "x-cli-destinations": [parameter.name],
            "x-cli-locations": ["argument" if isinstance(parameter, TyperArgument) else "option"],
        }
        if path == "annotate run" and public_name == "output":
            metadata["deprecated"] = True
        metadata_by_name[public_name] = metadata
        definitions[public_name] = (
            annotation,
            Field(
                default=cast(Any, ... if required else default),
                description=descriptions.get(public_name) or getattr(parameter, "help", None) or "",
                json_schema_extra=metadata,
                **constraints,
            ),
        )
    return create_model(name, __config__=ConfigDict(title=name), **definitions)


def compact_type(schema: dict[str, Any]) -> str:
    """Render the same JSON Schema type/constraints in the compact vocabulary."""
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    if "anyOf" in schema:
        choices = schema["anyOf"]
        nonnull = [item for item in choices if item.get("type") != "null"]
        if len(nonnull) == 1 and len(choices) == 2:
            return compact_type(nonnull[0]) + "?"
        return " | ".join(compact_type(item) for item in choices)
    if "const" in schema:
        return str(schema["const"]).lower() if isinstance(schema["const"], bool) else str(schema["const"])
    if "enum" in schema:
        return " | ".join(str(value) for value in schema["enum"])
    kind = schema.get("type")
    if kind == "array":
        result = f"list[{compact_type(schema.get('items', {}))}]"
    elif kind == "object":
        result = "dict"
    else:
        result = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "null": "None",
        }.get(str(kind), "Any")
    return result + _compact_constraints(schema)


def _compact_constraints(schema: dict[str, Any]) -> str:
    result = ""
    lower, upper = schema.get("minimum"), schema.get("maximum")
    if lower is not None and upper is not None:
        result += f"[{lower},{upper}]"
    elif lower is not None:
        result += f">={lower}"
    elif upper is not None:
        result += f"<={upper}"
    for keyword, symbol in (("exclusiveMinimum", ">"), ("exclusiveMaximum", "<")):
        if keyword in schema:
            result += f"{symbol}{schema[keyword]}"
    return result
