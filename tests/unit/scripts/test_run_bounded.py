from __future__ import annotations

import importlib.util
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run_bounded.py"
_SPEC = importlib.util.spec_from_file_location("run_bounded", _SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
run_bounded_script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(run_bounded_script)

pytestmark = pytest.mark.skipif(os.name == "nt", reason="プロセス群と RLIMIT_AS は POSIX 専用")

_GIB = 1024**3


def _spawn_grandchild_code(pid_file: Path, *, then_sleep: bool, exit_code: int = 0) -> str:
    """孫プロセス (sleep 300) を起動して PID を書き出す python ワンライナーを作る."""
    lines = [
        "import subprocess, sys, time",
        "p = subprocess.Popen(['sleep', '300'])",
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))",
    ]
    lines.append("time.sleep(300)" if then_sleep else f"sys.exit({exit_code})")
    return "\n".join(lines)


def _is_zombie(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def _wait_process_gone(pid: int, timeout: float = 5.0) -> bool:
    """PID が消えるか、親の reap 待ちのゾンビになるまでポーリングする."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        if _is_zombie(pid):
            return True
        time.sleep(0.05)
    return False


def _read_pid(pid_file: Path) -> int:
    return int(pid_file.read_text())


def test_timeout_kills_whole_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    code = _spawn_grandchild_code(pid_file, then_sleep=True)

    started = time.monotonic()
    rc = run_bounded_script.run_bounded([sys.executable, "-c", code], timeout=1.0, kill_after=1.0)

    assert rc == run_bounded_script.EXIT_TIMEOUT == 124
    assert time.monotonic() - started < 5.0
    assert _wait_process_gone(_read_pid(pid_file))


def test_normal_exit_returns_zero_and_cleans_leftover_grandchild(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    code = _spawn_grandchild_code(pid_file, then_sleep=False, exit_code=0)

    rc = run_bounded_script.run_bounded([sys.executable, "-c", code], timeout=10.0, kill_after=1.0)

    assert rc == 0
    assert _wait_process_gone(_read_pid(pid_file))


def test_pipe_success_does_not_hide_upstream_failure(capfd: pytest.CaptureFixture[str]) -> None:
    failing = [sys.executable, "-c", "import sys; print('first'); print('last', flush=True); sys.exit(7)"]

    # 関数として呼ぶ: 下流 (tail) は成功しても対象の 7 を返す
    rc = run_bounded_script.run_bounded(failing, timeout=10.0, kill_after=1.0, pipe_to="tail -n 1")
    assert rc == 7
    assert capfd.readouterr().out.strip() == "last"

    # 対象が成功して下流だけ失敗した場合は下流の終了コード
    ok = [sys.executable, "-c", "print('x')"]
    rc = run_bounded_script.run_bounded(
        ok, timeout=10.0, kill_after=1.0, pipe_to="sh -c 'cat >/dev/null; exit 3'"
    )
    assert rc == 3

    # 実際のシェルのパイプ (pipefail) でもラッパーの非ゼロが伝わる
    wrapper = shlex.join([sys.executable, str(_SCRIPT_PATH), "--timeout", "10", "--", *failing])
    result = subprocess.run(
        ["bash", "-c", f"set -o pipefail; {wrapper} | tail -n 1"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 7
    assert result.stdout.strip() == "last"


def test_memory_limit_rejects_oversized_allocation() -> None:
    limit = 1 * _GIB
    allocate = "import sys; b = bytearray({size}); sys.exit(0)"

    oversized = [sys.executable, "-c", allocate.format(size=2 * _GIB)]
    rc = run_bounded_script.run_bounded(oversized, timeout=10.0, kill_after=1.0, memory_limit_bytes=limit)
    assert rc != 0

    within = [sys.executable, "-c", allocate.format(size=64 * 1024**2)]
    rc = run_bounded_script.run_bounded(within, timeout=10.0, kill_after=1.0, memory_limit_bytes=limit)
    assert rc == 0
