"""crop_service が Qt に依存しないことをサブプロセスで検証する (Issue #1344)。

同一プロセス内では他テストが先に ``PySide6`` を import している可能性があるため、
クリーンなインタプリタを起こして ``sys.modules`` を確認する。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
_PROBE = "import sys, lorairo.services.crop_service; print('PySide6' in sys.modules)"


def test_importing_crop_service_does_not_load_pyside6() -> None:
    """crop_service を import しても PySide6 がロードされない。"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(_SRC_ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False", completed.stdout
