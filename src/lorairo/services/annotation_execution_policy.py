"""アノテーション実行の受付判定 (空きメモリ確認・待機・見送り) を行う Qt 非依存サービス。

ローカル ML モデルを 1 つ実行する直前に空き RAM / VRAM を確かめ、安全余裕を下回るなら
設定の間隔で再確認しながら待機する。待機タイムアウトまでに回復しなければ、そのモデルを
見送る判断を返す (ADR 0109)。処理枚数の小分けや推論中のメモリ不足検出は
image-annotator-lib の責務で、本サービスは「実行してよいか」だけを決める。

メモリ取得関数・時計・sleep は DI でき、テストでは fake に差し替えて決定論的に検証する。
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import psutil

from lorairo.utils.log import logger

if TYPE_CHECKING:
    from lorairo.services.configuration_service import ConfigurationService

_GIB = 1024**3

CONFIG_SECTION = "annotation_execution"

# lib (ADR 0013) が推論中・推論前のメモリ不足を表す error_code。
MEMORY_ERROR_CODES: frozenset[str] = frozenset({"OUT_OF_MEMORY", "INSUFFICIENT_MEMORY"})

# 待機中に中止要求を確認する最大間隔 (秒)。再確認間隔が長くても中止はこの粒度で効く。
_CANCEL_CHECK_STEP_SEC = 0.5
# 再確認間隔の下限 (秒)。0 を設定されても空きメモリ取得を空回りさせない。
_MIN_POLL_INTERVAL_SEC = 0.1

REASON_LOW_RAM = "low_ram"
REASON_LOW_VRAM = "low_vram"


@dataclass(frozen=True)
class MemorySnapshot:
    """ある時点の空きメモリ。取得できない値は None (その項目の判定を省略する)。"""

    available_ram_bytes: int | None
    available_vram_bytes: int | None = None


MemoryProbe = Callable[[], MemorySnapshot]


def _probe_cuda_free_vram() -> int | None:
    """既に初期化済みの CUDA から空き VRAM を取得する。

    torch を新たに import したり CUDA コンテキストを作ったりしない (それ自体が VRAM を
    消費し、lib の torch 遅延 import 方針にも反するため)。torch が未 import、CUDA が
    使えない、または未初期化なら None を返して VRAM 判定を省略する。
    """
    torch_module = sys.modules.get("torch")
    if torch_module is None:
        return None
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None:
        return None
    try:
        if not cuda.is_available() or not cuda.is_initialized():
            return None
        free_bytes, _total_bytes = cuda.mem_get_info()
    except (RuntimeError, AttributeError, TypeError, ValueError):
        return None
    return int(free_bytes)


def probe_system_memory() -> MemorySnapshot:
    """現在の空き RAM (psutil) と、取得できれば空き VRAM を返す。"""
    try:
        available_ram: int | None = int(psutil.virtual_memory().available)
    except (OSError, RuntimeError):
        available_ram = None
    return MemorySnapshot(available_ram_bytes=available_ram, available_vram_bytes=_probe_cuda_free_vram())


def is_memory_error_code(error_code: object) -> bool:
    """lib の error_code (StrEnum / str) がメモリ不足系かを判定する。"""
    code = getattr(error_code, "value", error_code)
    return isinstance(code, str) and code in MEMORY_ERROR_CODES


def _read_float(config_service: ConfigurationService | None, key: str, default: float) -> float:
    if config_service is None:
        return default
    value = config_service.get_setting(CONFIG_SECTION, key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        if value != default:
            logger.warning(f"[{CONFIG_SECTION}] {key} の値が不正なため既定値 {default} を使います")
        return default
    return float(value)


def _read_bool(config_service: ConfigurationService | None, key: str, default: bool) -> bool:
    if config_service is None:
        return default
    value = config_service.get_setting(CONFIG_SECTION, key, default)
    if not isinstance(value, bool):
        logger.warning(f"[{CONFIG_SECTION}] {key} の値が不正なため既定値 {default} を使います")
        return default
    return value


@dataclass(frozen=True)
class AnnotationExecutionSettings:
    """受付判定の設定。既定値は実測前の暫定値 (ADR 0109)。

    Attributes:
        admission_check_enabled: False なら受付判定・待機を行わず常に実行する。
        ram_safety_margin_gb: ローカル ML モデル実行前に残しておく空き RAM (GB)。
        vram_safety_margin_gb: 空き VRAM が取得できる場合に残しておく空き VRAM (GB)。
        wait_poll_interval_sec: 空きが足りないときの再確認間隔 (秒)。
        wait_timeout_sec: 空きの回復を待つ上限 (秒)。超えたらそのモデルを見送る。
        skip_completed_on_rerun: True なら同じモデルの結果が既にある画像を推論から外す。
    """

    admission_check_enabled: bool = True
    ram_safety_margin_gb: float = 4.0
    vram_safety_margin_gb: float = 1.0
    wait_poll_interval_sec: float = 5.0
    wait_timeout_sec: float = 120.0
    skip_completed_on_rerun: bool = False

    @classmethod
    def from_config(cls, config_service: ConfigurationService | None) -> AnnotationExecutionSettings:
        """``[annotation_execution]`` セクションから設定を読む。不正値は既定値に戻す。"""
        defaults = cls()
        return cls(
            admission_check_enabled=_read_bool(
                config_service, "admission_check_enabled", defaults.admission_check_enabled
            ),
            ram_safety_margin_gb=_read_float(
                config_service, "ram_safety_margin_gb", defaults.ram_safety_margin_gb
            ),
            vram_safety_margin_gb=_read_float(
                config_service, "vram_safety_margin_gb", defaults.vram_safety_margin_gb
            ),
            wait_poll_interval_sec=_read_float(
                config_service, "wait_poll_interval_sec", defaults.wait_poll_interval_sec
            ),
            wait_timeout_sec=_read_float(config_service, "wait_timeout_sec", defaults.wait_timeout_sec),
            skip_completed_on_rerun=_read_bool(
                config_service, "skip_completed_on_rerun", defaults.skip_completed_on_rerun
            ),
        )


def _format_gb(value_bytes: int | None) -> str:
    if value_bytes is None:
        return "不明"
    return f"{value_bytes / _GIB:.1f}GB"


@dataclass(frozen=True)
class AdmissionDecision:
    """受付判定の結果。

    Attributes:
        admitted: 実行してよい場合 True。
        reason_code: 見送り・待機の理由 (``low_ram`` / ``low_vram``)。受付時は None。
        snapshot: 判定に使った空きメモリ。
        required_ram_bytes: 判定に使った RAM の必要空き量。
        required_vram_bytes: 判定に使った VRAM の必要空き量。
        waited_sec: 受付または見送りまでに待った秒数。
    """

    admitted: bool
    reason_code: str | None
    snapshot: MemorySnapshot
    required_ram_bytes: int = 0
    required_vram_bytes: int = 0
    waited_sec: float = 0.0

    def shortage_text(self) -> str:
        """不足の内容をユーザー向けの短い文で返す。受付時は空文字。"""
        if self.reason_code == REASON_LOW_RAM:
            return (
                f"空きメモリ {_format_gb(self.snapshot.available_ram_bytes)}"
                f" (必要 {_format_gb(self.required_ram_bytes)})"
            )
        if self.reason_code == REASON_LOW_VRAM:
            return (
                f"空きビデオメモリ {_format_gb(self.snapshot.available_vram_bytes)}"
                f" (必要 {_format_gb(self.required_vram_bytes)})"
            )
        return ""


class AnnotationExecutionPolicy:
    """ローカル ML モデル実行前の受付判定と待機を行う。

    判定基準は「空き RAM ≥ 安全余裕」かつ (VRAM が取得できれば)「空き VRAM ≥ 安全余裕」。
    モデル重みの必要量は加算しない: 重みのロード可否と待機中キャッシュの追い出しは
    lib のロード前ガード (lib ADR 0012) が担い、アプリからはキャッシュ済みかどうかが
    見えないため、加算すると同じモデルの再実行を常に二重計上してしまう (ADR 0109)。
    """

    def __init__(
        self,
        settings: AnnotationExecutionSettings,
        memory_probe: MemoryProbe | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        """初期化する。

        Args:
            settings: 受付判定の設定。
            memory_probe: 空きメモリ取得関数。省略時は ``probe_system_memory``。
            clock: 単調増加する時計。省略時は ``time.monotonic``。
            sleep: 待機関数。省略時は ``time.sleep``。
        """
        self._settings = settings
        # 省略時はモジュール属性を生成時点で解決する (テストで差し替え可能にするため)。
        self._memory_probe: MemoryProbe = memory_probe if memory_probe is not None else probe_system_memory
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._sleep: Callable[[float], None] = sleep if sleep is not None else time.sleep

    @property
    def settings(self) -> AnnotationExecutionSettings:
        return self._settings

    def evaluate(self) -> AdmissionDecision:
        """現在の空きメモリで 1 回だけ判定する (待機しない)。"""
        required_ram = int(self._settings.ram_safety_margin_gb * _GIB)
        required_vram = int(self._settings.vram_safety_margin_gb * _GIB)
        if not self._settings.admission_check_enabled:
            return AdmissionDecision(True, None, MemorySnapshot(None, None), required_ram, required_vram)

        snapshot = self._memory_probe()
        reason: str | None = None
        if snapshot.available_ram_bytes is not None and snapshot.available_ram_bytes < required_ram:
            reason = REASON_LOW_RAM
        elif snapshot.available_vram_bytes is not None and snapshot.available_vram_bytes < required_vram:
            reason = REASON_LOW_VRAM
        return AdmissionDecision(reason is None, reason, snapshot, required_ram, required_vram)

    def wait_for_admission(
        self,
        *,
        check_cancel: Callable[[], None],
        on_wait: Callable[[AdmissionDecision, float], None] | None = None,
    ) -> AdmissionDecision:
        """受け付けられるまで待機し、受付またはタイムアウト時の判定を返す。

        Args:
            check_cancel: 中止要求があれば例外を送出する関数。待機中に繰り返し呼ぶ。
            on_wait: 待機に入る/再確認するたびに (判定, 残り秒) で呼ばれる通知関数。

        Returns:
            受け付けた場合は ``admitted=True``、タイムアウトした場合は ``admitted=False``
            で最後の判定を返す。
        """
        decision = self.evaluate()
        if decision.admitted:
            return decision

        started = self._clock()
        deadline = started + self._settings.wait_timeout_sec
        poll_interval = max(self._settings.wait_poll_interval_sec, _MIN_POLL_INTERVAL_SEC)
        while True:
            now = self._clock()
            remaining = deadline - now
            if remaining <= 0:
                return replace(decision, waited_sec=now - started)
            if on_wait is not None:
                on_wait(decision, remaining)
            # 再確認まで待つ。中止は _CANCEL_CHECK_STEP_SEC ごとに確認する。
            next_probe_at = min(deadline, now + poll_interval)
            while (now := self._clock()) < next_probe_at:
                check_cancel()
                self._sleep(min(_CANCEL_CHECK_STEP_SEC, next_probe_at - now))
            check_cancel()
            decision = self.evaluate()
            if decision.admitted:
                return replace(decision, waited_sec=self._clock() - started)
