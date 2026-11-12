"""AnnotationExecutionPolicy (ADR 0109) の受付判定・待機のユニットテスト。

空きメモリ取得・時計・sleep をすべて fake にして決定論的に検証する。
"""

import sys
from types import SimpleNamespace

import pytest

from lorairo.services import annotation_execution_policy as policy_module
from lorairo.services.annotation_execution_policy import (
    REASON_LOW_RAM,
    REASON_LOW_VRAM,
    AnnotationExecutionPolicy,
    AnnotationExecutionSettings,
    MemorySnapshot,
    is_memory_error_code,
)
from lorairo.services.configuration_service import ConfigurationService

# autouse fixture で差し替えられる前の実関数 (collection 時点で束縛)
_REAL_PROBE = policy_module.probe_system_memory

GIB = 1024**3


class FakeClock:
    """sleep で進む fake の単調時計。"""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class SequenceProbe:
    """呼ばれるたびに次の空きメモリ (GB) を返す fake。最後の値を繰り返す。"""

    def __init__(self, ram_gb: list[float], vram_gb: list[float | None] | None = None) -> None:
        self._ram = ram_gb
        self._vram = vram_gb or [None]
        self.calls = 0

    def __call__(self) -> MemorySnapshot:
        ram = self._ram[min(self.calls, len(self._ram) - 1)]
        vram = self._vram[min(self.calls, len(self._vram) - 1)]
        self.calls += 1
        return MemorySnapshot(
            available_ram_bytes=int(ram * GIB),
            available_vram_bytes=None if vram is None else int(vram * GIB),
        )


def _policy(probe: SequenceProbe, clock: FakeClock, **overrides: object) -> AnnotationExecutionPolicy:
    settings = AnnotationExecutionSettings(
        ram_safety_margin_gb=4.0,
        vram_safety_margin_gb=1.0,
        wait_poll_interval_sec=5.0,
        wait_timeout_sec=20.0,
    )
    if overrides:
        settings = AnnotationExecutionSettings(**{**settings.__dict__, **overrides})
    return AnnotationExecutionPolicy(settings, memory_probe=probe, clock=clock, sleep=clock.sleep)


@pytest.mark.unit
class TestEvaluate:
    def test_plenty_of_memory_is_admitted(self) -> None:
        policy = _policy(SequenceProbe([16.0]), FakeClock())

        decision = policy.evaluate()

        assert decision.admitted is True
        assert decision.reason_code is None
        assert decision.shortage_text() == ""

    def test_low_ram_is_not_admitted_with_reason(self) -> None:
        policy = _policy(SequenceProbe([2.5]), FakeClock())

        decision = policy.evaluate()

        assert decision.admitted is False
        assert decision.reason_code == REASON_LOW_RAM
        assert decision.shortage_text() == "空きメモリ 2.5GB (必要 4.0GB)"

    def test_low_vram_is_not_admitted_when_vram_is_known(self) -> None:
        policy = _policy(SequenceProbe([16.0], [0.5]), FakeClock())

        decision = policy.evaluate()

        assert decision.admitted is False
        assert decision.reason_code == REASON_LOW_VRAM
        assert "空きビデオメモリ 0.5GB" in decision.shortage_text()

    def test_unknown_memory_values_skip_the_check(self) -> None:
        policy = AnnotationExecutionPolicy(
            AnnotationExecutionSettings(),
            memory_probe=lambda: MemorySnapshot(available_ram_bytes=None, available_vram_bytes=None),
        )

        assert policy.evaluate().admitted is True

    def test_disabled_check_never_probes(self) -> None:
        probe = SequenceProbe([0.1])
        policy = _policy(probe, FakeClock(), admission_check_enabled=False)

        assert policy.evaluate().admitted is True
        assert probe.calls == 0


@pytest.mark.unit
class TestWaitForAdmission:
    def test_normal_memory_returns_immediately_without_wait(self) -> None:
        clock = FakeClock()
        waits: list[float] = []
        policy = _policy(SequenceProbe([16.0]), clock)

        decision = policy.wait_for_admission(
            check_cancel=lambda: None, on_wait=lambda _d, r: waits.append(r)
        )

        assert decision.admitted is True
        assert decision.waited_sec == 0.0
        assert waits == []
        assert clock.sleeps == []

    def test_low_memory_waits_then_runs_after_recovery(self) -> None:
        clock = FakeClock()
        waits: list[float] = []
        # 初回 2GB → 5 秒後 3GB → 10 秒後 8GB で回復
        policy = _policy(SequenceProbe([2.0, 3.0, 8.0]), clock)

        decision = policy.wait_for_admission(
            check_cancel=lambda: None, on_wait=lambda _d, r: waits.append(r)
        )

        assert decision.admitted is True
        assert decision.waited_sec == pytest.approx(10.0)
        assert waits == [pytest.approx(20.0), pytest.approx(15.0)]
        # 中止確認のため 0.5 秒刻みで待つ
        assert max(clock.sleeps) <= 0.5

    def test_low_memory_until_timeout_is_skipped_with_reason(self) -> None:
        clock = FakeClock()
        policy = _policy(SequenceProbe([2.0]), clock)

        decision = policy.wait_for_admission(check_cancel=lambda: None)

        assert decision.admitted is False
        assert decision.reason_code == REASON_LOW_RAM
        assert decision.waited_sec == pytest.approx(20.0)

    def test_memory_consumed_by_other_process_during_wait_keeps_waiting(self) -> None:
        """待機中に他プロセスが空きを減らしても、回復するまで受け付けない。"""
        clock = FakeClock()
        probe = SequenceProbe([3.5, 3.9, 1.0, 1.0, 6.0])
        policy = _policy(probe, clock, wait_timeout_sec=60.0)

        decision = policy.wait_for_admission(check_cancel=lambda: None)

        assert decision.admitted is True
        assert probe.calls == 5
        assert decision.waited_sec == pytest.approx(20.0)

    def test_cancel_during_wait_raises_and_stops_probing(self) -> None:
        clock = FakeClock()
        probe = SequenceProbe([1.0])
        policy = _policy(probe, clock)

        class Canceled(Exception):
            pass

        def check_cancel() -> None:
            if clock.now >= 2.0:
                raise Canceled

        with pytest.raises(Canceled):
            policy.wait_for_admission(check_cancel=check_cancel)

        assert clock.now == pytest.approx(2.0)
        assert probe.calls == 1

    def test_zero_timeout_skips_without_waiting(self) -> None:
        clock = FakeClock()
        policy = _policy(SequenceProbe([1.0]), clock, wait_timeout_sec=0.0)

        decision = policy.wait_for_admission(check_cancel=lambda: None)

        assert decision.admitted is False
        assert clock.sleeps == []


@pytest.mark.unit
class TestSettings:
    def test_defaults_are_conservative_and_match_default_config(self) -> None:
        from lorairo.utils.config import DEFAULT_CONFIG

        settings = AnnotationExecutionSettings()
        section = DEFAULT_CONFIG["annotation_execution"]
        assert isinstance(section, dict)
        assert section == {
            "admission_check_enabled": settings.admission_check_enabled,
            "ram_safety_margin_gb": settings.ram_safety_margin_gb,
            "vram_safety_margin_gb": settings.vram_safety_margin_gb,
            "wait_poll_interval_sec": settings.wait_poll_interval_sec,
            "wait_timeout_sec": settings.wait_timeout_sec,
            "skip_completed_on_rerun": settings.skip_completed_on_rerun,
        }
        assert settings.admission_check_enabled is True
        assert settings.skip_completed_on_rerun is False

    def test_from_config_reads_section(self) -> None:
        config = ConfigurationService(
            shared_config={
                "annotation_execution": {
                    "admission_check_enabled": False,
                    "ram_safety_margin_gb": 8,
                    "vram_safety_margin_gb": 2.5,
                    "wait_poll_interval_sec": 1.0,
                    "wait_timeout_sec": 30,
                    "skip_completed_on_rerun": True,
                }
            }
        )

        settings = AnnotationExecutionSettings.from_config(config)

        assert settings == AnnotationExecutionSettings(
            admission_check_enabled=False,
            ram_safety_margin_gb=8.0,
            vram_safety_margin_gb=2.5,
            wait_poll_interval_sec=1.0,
            wait_timeout_sec=30.0,
            skip_completed_on_rerun=True,
        )

    def test_from_config_falls_back_on_invalid_values(self) -> None:
        config = ConfigurationService(
            shared_config={
                "annotation_execution": {
                    "admission_check_enabled": "yes",
                    "ram_safety_margin_gb": -1,
                    "wait_timeout_sec": "long",
                    "vram_safety_margin_gb": True,
                }
            }
        )

        assert AnnotationExecutionSettings.from_config(config) == AnnotationExecutionSettings()

    def test_from_config_without_service_uses_defaults(self) -> None:
        assert AnnotationExecutionSettings.from_config(None) == AnnotationExecutionSettings()


@pytest.mark.unit
class TestMemoryProbe:
    def test_real_probe_reports_available_ram(self) -> None:
        snapshot = _REAL_PROBE()

        assert snapshot.available_ram_bytes is None or snapshot.available_ram_bytes > 0

    def test_vram_is_none_without_imported_torch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delitem(sys.modules, "torch", raising=False)

        assert policy_module._probe_cuda_free_vram() is None

    def test_vram_is_none_when_cuda_not_initialized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mem_get_info_calls: list[bool] = []
        fake_cuda = SimpleNamespace(
            is_available=lambda: True,
            is_initialized=lambda: False,
            mem_get_info=lambda: mem_get_info_calls.append(True) or (1, 2),
        )
        monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))

        assert policy_module._probe_cuda_free_vram() is None
        # CUDA コンテキストを新たに作らない
        assert mem_get_info_calls == []

    def test_vram_from_initialized_cuda(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_cuda = SimpleNamespace(
            is_available=lambda: True,
            is_initialized=lambda: True,
            mem_get_info=lambda: (3 * GIB, 8 * GIB),
        )
        monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))

        assert policy_module._probe_cuda_free_vram() == 3 * GIB

    def test_vram_probe_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def broken() -> tuple[int, int]:
            raise RuntimeError("CUDA error")

        fake_cuda = SimpleNamespace(
            is_available=lambda: True, is_initialized=lambda: True, mem_get_info=broken
        )
        monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=fake_cuda))

        assert policy_module._probe_cuda_free_vram() is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("OUT_OF_MEMORY", True),
        ("INSUFFICIENT_MEMORY", True),
        (SimpleNamespace(value="OUT_OF_MEMORY"), True),
        ("SAFETY_REFUSAL", False),
        (None, False),
        (1, False),
    ],
)
def test_is_memory_error_code(code: object, expected: bool) -> None:
    assert is_memory_error_code(code) is expected
