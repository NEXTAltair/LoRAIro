"""tests/ 配下の test ファイル basename 重複を検出する。

tests/ には __init__.py が無いため、同名 basename のテストが unit と bdd 等に
存在すると、同一 pytest セッションで ``import file mismatch`` の collection error になる。
"""

from collections import defaultdict
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_test_file_basenames_are_unique() -> None:
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in TESTS_ROOT.rglob("test_*.py"):
        by_name[path.name].append(str(path.relative_to(TESTS_ROOT)))

    duplicates = {name: sorted(paths) for name, paths in by_name.items() if len(paths) > 1}
    assert not duplicates, f"tests/ 配下で test ファイルの basename が重複: {duplicates}"
