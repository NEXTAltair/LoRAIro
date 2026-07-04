"""loguru 移行ガード: src/lorairo/ に std-logging の `exc_info=` が混入しないことを検証する (#1153)。

loguru は std logging の `exc_info=` をサポートしない。kwargs として渡ると traceback が
記録されず (silent)、さらにメッセージに波括弧が含まれると `.format()` が走って KeyError で
ログ呼び出し自体がクラッシュする。except 節では `logger.opt(exception=True).<level>(msg)` を使う。
本テストは `exc_info=` の再混入を機械的に防ぐ。

除外:
- ``database/migrations/``: Alembic の std logging (``logging.getLogger``) を使うため
  ``exc_info=True`` は正当。恒久的除外。
- provider_batch 3 ファイル: teammate-annotate が #1150 / #1152 で並行修正中のため一時除外。
  #1152 merge 後にこの除外を解除する (TODO #1152)。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lorairo"

# path の部分文字列で除外判定する
_EXCLUDE_SUBSTR: tuple[str, ...] = (
    "database/migrations/",
    # TODO(#1152): provider_batch 3 ファイルは teammate-annotate 修正待ち。merge 後に除外解除する。
    "gui/widgets/provider_batch_job_widget.py",
    "services/provider_batch_workflow_service.py",
    "services/provider_batch_service.py",
)

_EXC_INFO_RE = re.compile(r"\bexc_info\s*=")


@pytest.mark.unit
def test_no_loguru_exc_info_in_src() -> None:
    """src/lorairo/ (除外を除く) に `exc_info=` が 1 件も無いことを保証する。"""
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        posix = path.as_posix()
        if any(sub in posix for sub in _EXCLUDE_SUBSTR):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _EXC_INFO_RE.search(line):
                rel = path.relative_to(_SRC_ROOT).as_posix()
                offenders.append(f"{rel}:{lineno}: {line.strip()}")

    assert not offenders, (
        "loguru では exc_info= を使わず logger.opt(exception=True).<level>(msg) を使うこと (#1153):\n"
        + "\n".join(offenders)
    )
