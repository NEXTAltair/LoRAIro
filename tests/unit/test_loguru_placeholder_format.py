"""Loguru placeholder format regression tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

LOGURU_LEVELS = {
    "trace",
    "debug",
    "info",
    "success",
    "warning",
    "error",
    "critical",
    "exception",
}


@pytest.mark.unit
def test_src_lorairo_loguru_calls_do_not_use_stdlib_percent_placeholders() -> None:
    """Loguru accepts `{}` placeholders; stdlib `%s` placeholders are not expanded."""
    offenders: list[str] = []
    src_root = Path(__file__).resolve().parents[2] / "src" / "lorairo"

    for path in sorted(src_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in LOGURU_LEVELS:
                continue
            if not isinstance(node.func.value, ast.Name) or node.func.value.id != "logger":
                continue
            if len(node.args) < 2:
                continue
            message_node = node.args[0]
            if not isinstance(message_node, ast.Constant) or not isinstance(message_node.value, str):
                continue
            if any(placeholder in message_node.value for placeholder in ("%s", "%r", "%d")):
                rel_path = path.relative_to(src_root.parents[1])
                offenders.append(f"{rel_path}:{node.lineno}: {message_node.value!r}")

    assert offenders == []
