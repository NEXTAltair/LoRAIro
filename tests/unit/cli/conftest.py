"""CLI テスト共通設定。

Rich/Typer のカラー出力を無効化する autouse フィクスチャを提供する。
"""

from collections import Counter
from functools import cache

import pytest

_OBSERVED_SCHEMA_ROWS: Counter[tuple[str, str]] = Counter()


@pytest.fixture(autouse=True)
def disable_rich_color(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rich/Typer のカラー出力をテスト環境で無効化する。

    Rich は help 出力中の `--flag` パターンに ANSI エスケープ (`\\x1b[1;36m`) を挿入するため、
    CI 環境のようにカラーが強制される条件下では `assert "--project" in result.stdout` が
    `\\x1b[1;36m-\\x1b[0m\\x1b[1;36m-project\\x1b[0m` との比較になり失敗する。

    NO_COLOR と TERM=dumb を設定して Rich の自動検出を抑制する。
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")


@pytest.fixture(autouse=True)
def validate_observed_cli_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validate actual command-test wire rows against the published output schemas.

    Boundaries remain mocked by individual tests; validation observes serialized
    JSONL, including datetime/non-finite normalization, after each real invocation.
    """
    import shlex

    from typer.testing import CliRunner

    from lorairo.cli.introspection import get_tool_spec, iter_tool_specs
    from lorairo.cli.main import app

    invoke = CliRunner.invoke
    paths = sorted((spec.path for spec in iter_tool_specs()), key=lambda path: -len(path.split()))

    def checked_invoke(self, target, args=None, *positional, **kwargs):
        result = invoke(self, target, args, *positional, **kwargs)
        if target is not app:
            return result
        tokens = shlex.split(args) if isinstance(args, str) else list(args or [])
        if "describe" in tokens or "list-commands" in tokens:
            return result
        path = next(
            (
                candidate
                for candidate in paths
                if any(
                    tokens[index : index + len(candidate.split())] == candidate.split()
                    for index in range(len(tokens))
                )
            ),
            None,
        )
        if path is None:
            return result
        spec = get_tool_spec(path)
        _validate_wire_rows(path, spec, result.stdout)
        return result

    monkeypatch.setattr(CliRunner, "invoke", checked_invoke)


def _validate_wire_rows(path, spec, stdout):
    import json

    from pydantic import ValidationError

    for line in stdout.splitlines():
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(row, dict) or row.get("kind") not in {"item", "result", "error"}:
            continue
        models = spec.errors if row["kind"] == "error" else spec.outputs
        errors = []
        for model in models:
            schema = model.schema_model
            assert schema is not None
            properties = schema.model_json_schema().get("properties", {})
            missing = set(row) - set(properties) - {"kind"}
            if missing:
                errors.append(f"{model.name}: unpublished keys {sorted(missing)}")
                continue
            try:
                schema.model_validate(row)
                _json_schema_validator(schema).validate(row)
                _OBSERVED_SCHEMA_ROWS[(path, row["kind"])] += 1
                break
            except ValidationError as error:
                errors.append(f"{model.name}: {error}")
        else:
            pytest.fail(f"{path}: no published {row['kind']} schema accepts {row!r}: {errors}")


@cache
def _json_schema_validator(model):
    from jsonschema import Draft202012Validator

    schema = model.model_json_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_sep("-", "Published schema validation of observed JSONL")
    terminalreporter.write_line(
        f"{sum(_OBSERVED_SCHEMA_ROWS.values())} rows across "
        f"{len({path for path, _ in _OBSERVED_SCHEMA_ROWS})} command paths validated "
        "with Pydantic and JSON Schema."
    )

    from lorairo.cli.introspection import iter_tool_specs

    unobserved = {spec.path for spec in iter_tool_specs()} - {path for path, _ in _OBSERVED_SCHEMA_ROWS}
    terminalreporter.write_line(f"No serialized rows observed for: {sorted(unobserved)}")
