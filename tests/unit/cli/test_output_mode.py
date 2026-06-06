"""CLI 出力モード解決 (``lorairo.cli._output_mode``) の test (ADR 0058 §1)。"""

from __future__ import annotations

import pytest

from lorairo.cli._output_mode import is_json_mode, resolve_output_mode, set_json_mode


@pytest.mark.unit
@pytest.mark.cli
@pytest.mark.parametrize(
    ("argv", "env", "expected"),
    [
        # 明示フラグ
        (["--json"], {}, True),
        (["--no-json"], {}, False),
        # 既定 rich
        ([], {}, False),
        # env のみ
        ([], {"LORAIRO_CLI_JSON": "1"}, True),
        ([], {"LORAIRO_CLI_JSON": "0"}, False),
        ([], {"LORAIRO_CLI_JSON": "false"}, False),
        ([], {"LORAIRO_CLI_JSON": ""}, False),
        # 明示フラグ > env
        (["--no-json"], {"LORAIRO_CLI_JSON": "1"}, False),
        (["--json"], {"LORAIRO_CLI_JSON": "0"}, True),
        # 位置非依存 (サブコマンド後でも受理)
        (["images", "list", "--json"], {}, True),
        # 後勝ち
        (["--json", "--no-json"], {}, False),
        (["--no-json", "--json"], {}, True),
        # ``--`` 以降は走査しない
        (["--", "--json"], {}, False),
    ],
)
def test_resolve_output_mode(argv: list[str], env: dict[str, str], expected: bool) -> None:
    """解決順序は「明示フラグ > env > 既定 rich」。"""
    assert resolve_output_mode(argv, env) is expected


@pytest.mark.unit
@pytest.mark.cli
def test_set_and_is_json_mode_roundtrip() -> None:
    """解決済みモードの保存/参照が往復する。"""
    set_json_mode(True)
    assert is_json_mode() is True
    set_json_mode(False)
    assert is_json_mode() is False
