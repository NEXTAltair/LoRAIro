"""Run a command with a wall-clock timeout, optional memory limit and safe piping.

テストや計測を「上限付き」で実行するための標準ライブラリだけのラッパー (Issue #1632)。

- 対象コマンドを新しいセッション (プロセス群) として起動し、タイムアウト時や終了後に
  プロセス群全体へ SIGTERM → 猶予 → SIGKILL を送って孫プロセスまで後始末する。
- ``--pipe-to`` で下流コマンドへ出力をつないでも、終了コードは対象コマンドのものを返す
  (``cmd | tail`` で失敗が隠れる問題の対策)。
- ``--memory-limit-gb`` で対象コマンドの仮想メモリ (RLIMIT_AS) に上限を設ける。

Usage:
    python scripts/run_bounded.py --timeout 600 [--memory-limit-gb 16] \
        [--pipe-to "tail -n 40"] -- <command> [args...]

POSIX 専用。Windows では終了コード 2 で終了する。
"""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from types import FrameType

if sys.platform != "win32":
    import resource

EXIT_TIMEOUT = 124
EXIT_USAGE = 2
EXIT_NOT_EXECUTABLE = 126
EXIT_NOT_FOUND = 127
_POLL_INTERVAL = 0.05
_GIB = 1024**3


class _WrapperInterruptedError(Exception):
    """ラッパー自身が SIGINT / SIGTERM を受けたことを表す内部例外."""

    def __init__(self, signum: int) -> None:
        super().__init__(f"signal {signum}")
        self.signum = signum


def _log(message: str) -> None:
    """ラッパー自身の診断メッセージを stderr に出す."""
    print(f"run_bounded: {message}", file=sys.stderr, flush=True)


def _normalize_returncode(returncode: int) -> int:
    """Popen の returncode をシェル互換の終了コードへ変換する (シグナル終了は 128+signum)."""
    if returncode < 0:
        return 128 - returncode
    return returncode


def _signal_group(pgid: int, sig: int) -> bool:
    """プロセス群へシグナルを送る。群がもう存在しなければ False を返す."""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _wait_group_gone(proc: subprocess.Popen[bytes], pgid: int, deadline: float) -> bool:
    """期限までプロセス群の消滅を待つ。リーダーは reap してゾンビとして数えないようにする."""
    while True:
        proc.poll()
        if not _signal_group(pgid, 0):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(_POLL_INTERVAL)


def _terminate_group(proc: subprocess.Popen[bytes], kill_after: float) -> None:
    """プロセス群全体へ SIGTERM を送り、猶予後も残っていれば SIGKILL を送る.

    start_new_session=True で起動しているので、プロセス群 ID はリーダーの PID と等しい。
    リーダーが終了済みでも、群に残った孫プロセスはこの ID で到達できる。

    Args:
        proc: 対象コマンドの Popen (プロセス群のリーダー)。
        kill_after: SIGTERM から SIGKILL までの猶予秒数。
    """
    pgid = proc.pid
    if _signal_group(pgid, signal.SIGTERM) and not _wait_group_gone(
        proc, pgid, time.monotonic() + kill_after
    ):
        _log(f"SIGTERM 後 {kill_after} 秒経ってもプロセス群 {pgid} が残っているため SIGKILL を送ります")
        _signal_group(pgid, signal.SIGKILL)
        # SIGKILL は即時に効くが、親 (init 等) による reap 待ちのゾンビが残り得るので短く待って打ち切る
        _wait_group_gone(proc, pgid, time.monotonic() + 1.0)
    # リーダーを確実に reap する (SIGKILL 済みなので長くは待たない)
    try:
        proc.wait(timeout=max(kill_after, 1.0))
    except subprocess.TimeoutExpired:
        _log(f"プロセス {proc.pid} の終了を確認できませんでした")


def _finish_downstream(downstream: subprocess.Popen[bytes], kill_after: float) -> int:
    """下流コマンドの終了を待ち、下流のプロセス群に残ったプロセスを後始末する.

    対象側のパイプが閉じれば下流は EOF で自然に終わるので、まず猶予を与える
    (タイムアウト後も tail 等が最後の出力を表示できるようにするため)。
    その後、リーダーが終了済みでも、下流が起動した子が群に残っていれば群ごと止める。

    Args:
        downstream: 下流コマンドの Popen (独立したプロセス群のリーダー)。
        kill_after: 自然終了を待つ猶予、および SIGTERM から SIGKILL までの猶予 (秒)。

    Returns:
        下流コマンドの終了コード (シグナル終了は 128+signum)。
    """
    try:
        downstream.wait(timeout=kill_after)
    except subprocess.TimeoutExpired:
        _log("下流コマンドが終了しないため停止します")
    _terminate_group(downstream, kill_after)
    if downstream.returncode is None:
        return 128 + signal.SIGKILL
    return _normalize_returncode(downstream.returncode)


def _make_memory_limiter(limit_bytes: int) -> Callable[[], None]:
    """子プロセス側 (exec 直前) で RLIMIT_AS を設定する preexec_fn を作る.

    hard limit を超える値は設定できないため、親側で現在の hard limit に丸めておく。
    """
    _, hard = resource.getrlimit(resource.RLIMIT_AS)
    if hard != resource.RLIM_INFINITY:
        limit_bytes = min(limit_bytes, hard)

    def _apply() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

    return _apply


_SignalHandler = Callable[[int, FrameType | None], object] | int | None


def _raise_interrupted(signum: int, frame: FrameType | None) -> None:
    """シグナルハンドラ: 待機を中断して後始末に進ませる."""
    raise _WrapperInterruptedError(signum)


def _set_wrapper_signal_handlers(handler: _SignalHandler) -> dict[int, _SignalHandler]:
    """SIGINT / SIGTERM のハンドラを差し替え、元のハンドラを返す (メインスレッド以外では何もしない)."""
    previous: dict[int, _SignalHandler] = {}
    if threading.current_thread() is not threading.main_thread():
        return previous
    for sig in (signal.SIGINT, signal.SIGTERM):
        previous[sig] = signal.signal(sig, handler)
    return previous


def _restore_signal_handlers(previous: dict[int, _SignalHandler]) -> None:
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def _start_downstream(downstream_cmd: list[str]) -> subprocess.Popen[bytes] | int:
    """下流コマンドを対象とは別の独立したプロセス群として起動する。失敗時は終了コードを返す.

    独立した群にするのは、下流が起動した子まで後始末で止められるようにするため。
    対象とは別の群なので、対象を止めた後も下流は EOF まで出力を処理できる。
    """
    try:
        return subprocess.Popen(downstream_cmd, stdin=subprocess.PIPE, start_new_session=True)
    except FileNotFoundError:
        _log(f"下流コマンドが見つかりません: {downstream_cmd[0]}")
        return EXIT_NOT_FOUND
    except PermissionError:
        _log(f"下流コマンドを実行できません: {downstream_cmd[0]}")
        return EXIT_NOT_EXECUTABLE


def _start_target(
    command: Sequence[str],
    preexec: Callable[[], None] | None,
    downstream: subprocess.Popen[bytes] | None,
) -> subprocess.Popen[bytes] | int:
    """対象コマンドを新しいセッション (プロセス群) として起動する。失敗時は終了コードを返す."""
    try:
        return subprocess.Popen(
            list(command),
            start_new_session=True,
            preexec_fn=preexec,
            stdout=downstream.stdin if downstream is not None else None,
            stderr=subprocess.STDOUT if downstream is not None else None,
        )
    except FileNotFoundError:
        _log(f"コマンドが見つかりません: {command[0]}")
        return EXIT_NOT_FOUND
    except PermissionError:
        _log(f"コマンドを実行できません: {command[0]}")
        return EXIT_NOT_EXECUTABLE
    except OSError as e:
        # shebang の無いスクリプト (Exec format error) など、起動自体に失敗した場合
        _log(f"コマンドを起動できません: {command[0]} ({e.strerror})")
        return EXIT_NOT_EXECUTABLE
    except subprocess.SubprocessError as e:
        # preexec_fn (RLIMIT_AS の設定) が子プロセス側で失敗した場合
        _log(f"コマンドの起動準備に失敗しました: {command[0]} ({e})")
        return EXIT_NOT_EXECUTABLE
    finally:
        # 親側の書き込み端を閉じる。閉じないと対象が終わっても下流に EOF が届かない
        if downstream is not None and downstream.stdin is not None:
            downstream.stdin.close()


def _wait_target(proc: subprocess.Popen[bytes], timeout: float, kill_after: float) -> int:
    """対象の終了 (またはタイムアウト) を待ち、プロセス群を後始末して終了コードを返す."""
    try:
        code = _normalize_returncode(proc.wait(timeout=timeout))
    except subprocess.TimeoutExpired:
        _log(f"タイムアウト ({timeout} 秒) のためプロセス群 {proc.pid} を停止します")
        code = EXIT_TIMEOUT
    # 正常終了・失敗・タイムアウトのいずれでも、群に残ったプロセスを後始末する
    _terminate_group(proc, kill_after)
    return code


def _supervise(
    proc: subprocess.Popen[bytes] | None,
    downstream: subprocess.Popen[bytes] | None,
    timeout: float,
    kill_after: float,
) -> tuple[int, int]:
    """対象と下流の終了を待ち、両方のプロセス群を後始末する.

    ラッパーが SIGINT / SIGTERM を受けた場合も両方のプロセス群を後始末してから
    _WrapperInterruptedError を送出し直す。

    Returns:
        (対象の終了コード, 下流の終了コード)。対象や下流が無い場合は 0。
    """
    previous = _set_wrapper_signal_handlers(_raise_interrupted)
    try:
        target_code = _wait_target(proc, timeout, kill_after) if proc is not None else 0
        downstream_code = _finish_downstream(downstream, kill_after) if downstream is not None else 0
    except _WrapperInterruptedError as e:
        # 後始末の途中で再度シグナルを受けて中断されないよう、以降は無視する
        _set_wrapper_signal_handlers(signal.SIG_IGN)
        _log(f"シグナル {e.signum} を受けたため対象と下流のプロセス群を停止します")
        if proc is not None:
            _terminate_group(proc, kill_after)
        if downstream is not None:
            _finish_downstream(downstream, kill_after)
        raise
    finally:
        _restore_signal_handlers(previous)
    return target_code, downstream_code


def run_bounded(
    command: Sequence[str],
    *,
    timeout: float,
    kill_after: float = 5.0,
    memory_limit_bytes: int | None = None,
    pipe_to: str | None = None,
) -> int:
    """コマンドを上限付きで実行し、終了コードを返す.

    Args:
        command: 実行するコマンドと引数 (shell は経由しない)。
        timeout: 対象コマンドの実行時間上限 (秒)。超えたらプロセス群を停止して 124 を返す。
        kill_after: SIGTERM から SIGKILL までの猶予 (秒)。
        memory_limit_bytes: 対象コマンドの RLIMIT_AS (バイト)。None なら設定しない。
        pipe_to: 対象の stdout+stderr をつなぐ下流コマンド (shlex.split で分割)。

    Returns:
        対象コマンドの終了コード (シグナル終了は 128+signum、タイムアウトは 124)。
        対象が成功し下流だけ失敗した場合は下流の終了コード。
        ラッパーが SIGINT / SIGTERM を受けた場合は 128+signum。
    """
    if os.name != "posix":
        _log("POSIX 専用です (プロセス群の停止と RLIMIT_AS を使うため)。Windows では使えません")
        return EXIT_USAGE
    if not command:
        _log("実行するコマンドがありません")
        return EXIT_USAGE
    downstream_cmd = shlex.split(pipe_to) if pipe_to is not None else None
    if downstream_cmd is not None and not downstream_cmd:
        _log("--pipe-to のコマンドが空です")
        return EXIT_USAGE

    preexec = _make_memory_limiter(memory_limit_bytes) if memory_limit_bytes is not None else None

    # 下流を先に起動する。起動に失敗しても対象コマンドはまだ走っていないので後始末が要らない
    downstream: subprocess.Popen[bytes] | None = None
    if downstream_cmd is not None:
        started = _start_downstream(downstream_cmd)
        if isinstance(started, int):
            return started
        downstream = started

    started_target: subprocess.Popen[bytes] | int | None = None
    try:
        started_target = _start_target(command, preexec, downstream)
    finally:
        # 想定外の例外で対象の起動が中断されても、起動済みの下流を残さない
        if started_target is None and downstream is not None:
            _finish_downstream(downstream, kill_after)
    proc = None if isinstance(started_target, int) else started_target
    try:
        target_code, downstream_code = _supervise(proc, downstream, timeout, kill_after)
    except _WrapperInterruptedError as e:
        return 128 + e.signum
    if isinstance(started_target, int):
        # 対象を起動できなかった場合は起動失敗の終了コードを返す
        target_code = started_target
    # 対象の失敗を優先する。対象が成功したときだけ下流の失敗を返す
    return target_code if target_code != 0 else downstream_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="コマンドを上限付きで実行する (タイムアウト時はプロセス群ごと停止、パイプでも終了コードを保つ)",
    )
    parser.add_argument("--timeout", type=float, required=True, help="実行時間の上限 (秒)")
    parser.add_argument(
        "--kill-after", type=float, default=5.0, help="SIGTERM から SIGKILL までの猶予 (秒、既定 5)"
    )
    parser.add_argument(
        "--memory-limit-gb", type=float, default=None, help="対象の仮想メモリ上限 (GiB, RLIMIT_AS)"
    )
    parser.add_argument("--pipe-to", default=None, help='出力をつなぐ下流コマンド (例: "tail -n 40")')
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- の後に実行するコマンド")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """コマンドライン引数を解釈して run_bounded を呼ぶ."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    command: list[str] = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("-- の後に実行するコマンドを指定してください")
    if args.timeout <= 0:
        parser.error("--timeout は正の値を指定してください")
    if args.kill_after < 0:
        parser.error("--kill-after は 0 以上を指定してください")
    memory_limit_bytes: int | None = None
    if args.memory_limit_gb is not None:
        if args.memory_limit_gb <= 0:
            parser.error("--memory-limit-gb は正の値を指定してください")
        memory_limit_bytes = int(args.memory_limit_gb * _GIB)
    return run_bounded(
        command,
        timeout=args.timeout,
        kill_after=args.kill_after,
        memory_limit_bytes=memory_limit_bytes,
        pipe_to=args.pipe_to,
    )


if __name__ == "__main__":
    sys.exit(main())
