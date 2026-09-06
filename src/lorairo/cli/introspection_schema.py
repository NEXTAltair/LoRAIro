"""Derive public argument schemas from the registered Click/Typer interface."""

from __future__ import annotations

import re
from enum import Enum
from types import GenericAlias
from typing import Any, Literal, cast

import click
from pydantic import BaseModel, ConfigDict, Field, create_model


def command_tree() -> tuple[click.Command, dict[str, click.Command]]:
    """Inspect registration without invoking callbacks or initializing a project."""
    from typer.main import get_command

    from lorairo.cli.main import app

    root = get_command(app)
    leaves: dict[str, click.Command] = {}

    def walk(command: click.Command, path: str) -> None:
        if isinstance(command, click.Group):
            for name, child in command.commands.items():
                walk(child, f"{path} {name}".strip())
        else:
            leaves[path] = command

    walk(root, "")
    return root, leaves


def parameter_name(parameter: click.Parameter, names: set[str]) -> str:
    """Preserve published names while exposing actual flags/destinations separately."""
    candidates = [parameter.name or ""]
    candidates.extend(option[2:].replace("-", "_") for option in parameter.opts if option.startswith("--"))
    candidates.append((parameter.name or "").removesuffix("_csv"))
    if parameter.name == "image_ids_positional":
        candidates.append("image_ids")
    return next((name for name in candidates if name in names), candidates[0])


def _choice_type(parameter_type: click.Choice[Any]) -> tuple[Any, dict[str, Any]]:
    choices = tuple(value.value if isinstance(value, Enum) else value for value in parameter_type.choices)
    if parameter_type.case_sensitive:
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
    parameter_type: click.ParamType[Any], path: str, public_name: str
) -> tuple[Any, dict[str, Any]]:
    annotation: Any
    if isinstance(parameter_type, click.types.BoolParamType):
        annotation = bool
    elif isinstance(parameter_type, click.types.IntParamType):
        annotation = int
    elif isinstance(parameter_type, click.types.FloatParamType):
        annotation = float
    else:
        annotation = str
    constraints: dict[str, Any] = {}
    if isinstance(parameter_type, (click.IntRange, click.FloatRange)):
        if parameter_type.min is not None:
            constraints["gt" if parameter_type.min_open else "ge"] = parameter_type.min
        if parameter_type.max is not None:
            constraints["lt" if parameter_type.max_open else "le"] = parameter_type.max
    if isinstance(parameter_type, click.Choice):
        annotation, choice_constraints = _choice_type(parameter_type)
        constraints.update(choice_constraints)
    constraints.update(_runtime_constraints(path, public_name))
    return annotation, constraints


def _runtime_constraints(path: str, name: str) -> dict[str, Any]:
    if path == "errors list" and name in {"limit", "offset"}:
        from lorairo.cli.commands.errors import MAX_LIST_LIMIT

        return {"ge": 0, "le": MAX_LIST_LIMIT} if name == "limit" else {"ge": 0}
    if path == "images process" and name == "resolution":
        return {"multiple_of": 32}
    return {}


def input_model(
    name: str, command: click.Command, descriptions: dict[str, str], *, path: str
) -> type[BaseModel]:
    """Generate types, aliases, bounds and defaults from the parser's parameters.

    Runtime-only checks remain documented explicitly. The narrow bounds below are
    implemented in command bodies, so Click alone cannot expose them.
    """
    definitions: dict[str, Any] = {}
    metadata_by_name: dict[str, dict[str, Any]] = {}
    for parameter in command.params:
        if parameter.is_eager:
            continue
        public_name = parameter_name(parameter, set(descriptions))
        aliases = [*parameter.opts, *getattr(parameter, "secondary_opts", [])]
        if public_name in definitions:
            metadata_by_name[public_name]["x-cli-options"].extend(aliases)
            metadata_by_name[public_name]["x-cli-destinations"].append(parameter.name)
            metadata_by_name[public_name]["x-cli-locations"].append(
                "argument" if isinstance(parameter, click.Argument) else "option"
            )
            continue
        annotation, constraints = _parameter_type(parameter.type, path, public_name)
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
            "x-cli-locations": ["argument" if isinstance(parameter, click.Argument) else "option"],
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
