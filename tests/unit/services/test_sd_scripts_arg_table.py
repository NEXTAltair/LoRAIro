"""sd-scripts 引数表のテスト。"""

import pytest

from lorairo.services.sd_scripts_arg_table import SD_SCRIPTS_ARG_TYPES


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("learning_rate", "float"),
        ("network_dim", "int"),
        ("gradient_checkpointing", "bool"),
        ("optimizer_type", "str"),
        ("log_with", "str"),
    ],
)
def test_table_contains_known_args(name: str, expected: str) -> None:
    assert SD_SCRIPTS_ARG_TYPES[name] == expected


@pytest.mark.unit
@pytest.mark.parametrize("name", ["num_cpu_threads_per_process", "LoRA_type", "sdxl"])
def test_table_excludes_launcher_and_gui_only_keys(name: str) -> None:
    assert name not in SD_SCRIPTS_ARG_TYPES
