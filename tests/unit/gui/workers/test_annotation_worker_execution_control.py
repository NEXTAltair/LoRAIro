"""AnnotationWorker のアプリ側実行制御 (ADR 0109) のテスト。

受付判定・待機・メモリ不足後の継続判定・モデル単位の即時保存・中止を、実際の
``_run_annotation`` / ``execute`` 経路で検証する。空きメモリ取得・時計・sleep は fake。
"""

from collections.abc import Callable
from unittest.mock import Mock

import pytest

from lorairo.gui.workers.annotation_worker import MEMORY_SKIP_ERROR_TYPE, AnnotationWorker
from lorairo.gui.workers.base import CancellationError
from lorairo.services.annotation_execution_policy import (
    AnnotationExecutionPolicy,
    AnnotationExecutionSettings,
    MemorySnapshot,
)
from lorairo.services.annotation_progress import AnnotationPhase
from lorairo.services.model_registry_protocol import ModelInfo

GIB = 1024**3
IMAGE_PATHS = ["/images/a.jpg", "/images/b.jpg"]
PATH_TO_PHASH = {"/images/a.jpg": "phash-a", "/images/b.jpg": "phash-b"}
PATH_TO_ID = {"/images/a.jpg": 1, "/images/b.jpg": 2}


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ScriptedProbe:
    """呼び出しごとの空き RAM (GB) を返す fake。最後の値を繰り返す。"""

    def __init__(self, ram_gb: list[float]) -> None:
        self.ram_gb = ram_gb
        self.calls = 0

    def __call__(self) -> MemorySnapshot:
        value = self.ram_gb[min(self.calls, len(self.ram_gb) - 1)]
        self.calls += 1
        return MemorySnapshot(available_ram_bytes=int(value * GIB))


def _policy(
    probe: Callable[[], MemorySnapshot], clock: FakeClock, **overrides: object
) -> AnnotationExecutionPolicy:
    base = {
        "ram_safety_margin_gb": 4.0,
        "wait_poll_interval_sec": 5.0,
        "wait_timeout_sec": 20.0,
    }
    settings = AnnotationExecutionSettings(**{**base, **overrides})
    return AnnotationExecutionPolicy(settings, memory_probe=probe, clock=clock, sleep=clock.sleep)


def _model_info(name: str, *, requires_api_key: bool) -> ModelInfo:
    return ModelInfo(
        name=name,
        provider="openai" if requires_api_key else "local",
        capabilities=["tags"],
        litellm_model_id=name,
        requires_api_key=requires_api_key,
        estimated_size_gb=None,
    )


def _registry(*infos: ModelInfo) -> Mock:
    registry = Mock()
    registry.get_available_models.return_value = list(infos)
    return registry


def _db_manager() -> Mock:
    db = Mock()
    db.image_repo.get_phashes_by_filepaths.return_value = dict(PATH_TO_PHASH)
    db.image_repo.find_image_ids_by_phashes.return_value = {"phash-a": 1, "phash-b": 2}
    db.image_repo.find_image_ids_by_phashes_multi.return_value = {"phash-a": [1], "phash-b": [2]}
    db.image_repo.get_image_ids_by_filepaths.return_value = dict(PATH_TO_ID)
    db.model_repo.get_models_by_litellm_ids.return_value = {
        name: Mock(id=i) for i, name in enumerate(["local-a", "local-b", "local-c", "api-x"], start=1)
    }
    return db


def _ok(model: str, *, device: str | None = None) -> dict[str, dict[str, dict[str, object]]]:
    return {
        phash: {model: {"tags": [f"{model}-tag"], "error": None, "execution_device": device}}
        for phash in ("phash-a", "phash-b")
    }


def _oom(model: str) -> dict[str, dict[str, dict[str, object]]]:
    return {
        "phash-a": {model: {"tags": ["partial"], "error": None}},
        "phash-b": {
            model: {
                "tags": None,
                "error": "メモリ不足で推論できませんでした",
                "error_code": "OUT_OF_MEMORY",
            }
        },
    }


class RecordingRunner:
    """モデル単位で呼ばれた順序を記録する fake AnnotationRunner。"""

    def __init__(self, behaviors: dict[str, object], device: str | None = None) -> None:
        self.behaviors = behaviors
        self.calls: list[tuple[list[str], list[str], list[str] | None]] = []
        self.device = device
        self.after_call: Callable[[str], None] | None = None

    def execute_annotation(
        self, image_paths: list[str], litellm_model_ids: list[str], phash_list: list[str] | None = None
    ) -> object:
        self.calls.append((list(image_paths), list(litellm_model_ids), phash_list))
        model = litellm_model_ids[0]
        behavior = self.behaviors[model]
        if self.after_call is not None:
            self.after_call(model)
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    def get_execution_device(self, _litellm_model_id: str) -> str | None:
        return self.device

    @property
    def called_models(self) -> list[str]:
        return [models[0] for _paths, models, _phashes in self.calls]


def _worker(
    runner: RecordingRunner,
    models: list[str],
    registry: Mock,
    policy: AnnotationExecutionPolicy,
    db: Mock | None = None,
) -> AnnotationWorker:
    return AnnotationWorker(
        annotation_runner=runner,
        image_paths=list(IMAGE_PATHS),
        litellm_model_ids=models,
        db_manager=db or _db_manager(),
        model_registry=registry,
        execution_policy=policy,
    )


def _memory_error_records(db: Mock) -> list[dict[str, object]]:
    return [
        call.kwargs
        for call in db.save_error_record.call_args_list
        if call.kwargs.get("error_type") == MEMORY_SKIP_ERROR_TYPE
    ]


@pytest.mark.unit
class TestAdmission:
    def test_normal_memory_runs_models_in_selected_order(self) -> None:
        runner = RecordingRunner({"local-a": _ok("local-a"), "local-b": _ok("local-b")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("local-b", requires_api_key=False)
        )
        worker = _worker(
            runner, ["local-a", "local-b"], registry, _policy(ScriptedProbe([16.0]), FakeClock())
        )
        phases: list[AnnotationPhase] = []
        worker.progress_updated.connect(lambda p: phases.append(p.annotation_progress.phase))

        result = worker.execute()

        assert runner.called_models == ["local-a", "local-b"]
        assert all(paths == IMAGE_PATHS for paths, _m, _p in runner.calls)
        assert AnnotationPhase.WAITING_FOR_MEMORY not in phases
        assert set(result.results["phash-a"]) == {"local-a", "local-b"}
        assert result.model_errors == []

    def test_low_memory_waits_then_runs_after_recovery(self) -> None:
        clock = FakeClock()
        runner = RecordingRunner({"local-a": _ok("local-a")})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([2.0, 2.0, 6.0]), clock),
        )
        notes: list[tuple[AnnotationPhase, str]] = []
        worker.progress_updated.connect(
            lambda p: notes.append((p.annotation_progress.phase, p.annotation_progress.detail_text()))
        )

        result = worker.execute()

        assert runner.called_models == ["local-a"]
        waiting = [text for phase, text in notes if phase is AnnotationPhase.WAITING_FOR_MEMORY]
        assert waiting, "待機中の進捗が出ること"
        assert "local-a: 空きメモリ 2.0GB (必要 4.0GB)" in waiting[0]
        assert "残り 20秒" in waiting[0]
        # 待機の後は実行中表示へ戻る
        last_wait = max(
            i for i, (phase, _) in enumerate(notes) if phase is AnnotationPhase.WAITING_FOR_MEMORY
        )
        assert any(phase is AnnotationPhase.RUNNING for phase, _ in notes[last_wait + 1 :])
        assert clock.now == pytest.approx(10.0)
        assert result.model_errors == []

    def test_low_memory_until_timeout_skips_model_and_records_reason(self) -> None:
        db = _db_manager()
        runner = RecordingRunner({"local-a": _ok("local-a"), "api-x": _ok("api-x")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("api-x", requires_api_key=True)
        )
        worker = _worker(
            runner, ["local-a", "api-x"], registry, _policy(ScriptedProbe([1.0]), FakeClock()), db
        )

        result = worker.execute()

        # ローカルモデルは見送り、WebAPI モデルは受付判定の対象外で実行される
        assert runner.called_models == ["api-x"]
        records = _memory_error_records(db)
        assert [(r["model_name"], r["file_path"], r["image_id"]) for r in records] == [
            ("local-a", "/images/a.jpg", 1),
            ("local-a", "/images/b.jpg", 2),
        ]
        assert "空きメモリが回復しなかったため実行を見送りました" in str(records[0]["error_message"])
        assert "20秒待機" in str(records[0]["error_message"])
        skipped = [e for e in result.model_errors if e.model_name == "local-a"]
        assert len(skipped) == 2
        assert all(e.error_code == MEMORY_SKIP_ERROR_TYPE for e in skipped)
        assert any("local-a" in note and "見送り" in note for note in result.execution_notes)
        assert "api-x" in result.results["phash-a"]

    def test_other_process_consumes_memory_between_models(self) -> None:
        """1 つ目のモデルの後に他プロセスが空きを減らすと、2 つ目は待機の後に見送る。完了分は保存済み。"""
        db = _db_manager()
        probe = ScriptedProbe([16.0, 1.5])
        runner = RecordingRunner({"local-a": _ok("local-a"), "local-b": _ok("local-b")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("local-b", requires_api_key=False)
        )
        worker = _worker(runner, ["local-a", "local-b"], registry, _policy(probe, FakeClock()), db)

        result = worker.execute()

        assert runner.called_models == ["local-a"]
        assert ("phash-a", "local-a") in worker._persisted_keys
        assert {r["model_name"] for r in _memory_error_records(db)} == {"local-b"}
        assert "local-a" in result.results["phash-a"]

    def test_unknown_model_is_treated_as_local(self) -> None:
        runner = RecordingRunner({"mystery": _ok("mystery")})
        worker = _worker(runner, ["mystery"], _registry(), _policy(ScriptedProbe([1.0]), FakeClock()))

        worker.execute()

        assert runner.called_models == []

    def test_disabled_admission_runs_without_probing(self) -> None:
        probe = ScriptedProbe([0.1])
        runner = RecordingRunner({"local-a": _ok("local-a")})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(probe, FakeClock(), admission_check_enabled=False),
        )

        worker.execute()

        assert runner.called_models == ["local-a"]
        assert probe.calls == 0


@pytest.mark.unit
class TestAfterOutOfMemory:
    def test_oom_without_recovery_skips_remaining_local_models_and_keeps_completed(self) -> None:
        db = _db_manager()
        # local-a 受付 (16GB) → OOM 後は 1GB のまま回復しない
        probe = ScriptedProbe([16.0, 1.0])
        runner = RecordingRunner(
            {
                "local-a": _oom("local-a"),
                "local-b": _ok("local-b"),
                "api-x": _ok("api-x"),
                "local-c": _ok("local-c"),
            }
        )
        registry = _registry(
            _model_info("local-a", requires_api_key=False),
            _model_info("local-b", requires_api_key=False),
            _model_info("api-x", requires_api_key=True),
            _model_info("local-c", requires_api_key=False),
        )
        worker = _worker(
            runner, ["local-a", "local-b", "api-x", "local-c"], registry, _policy(probe, FakeClock()), db
        )

        result = worker.execute()

        assert runner.called_models == ["local-a", "api-x"]
        # 残りのローカルモデルは 1 回の判定だけで待たずに見送る
        assert probe.calls == 1 + 5
        assert {r["model_name"] for r in _memory_error_records(db)} == {"local-b", "local-c"}
        # OOM を返す前に完了した画像の結果は保存済み
        assert ("phash-a", "local-a") in worker._persisted_keys
        oom_errors = [e for e in result.model_errors if e.model_name == "local-a"]
        assert [e.error_code for e in oom_errors] == ["OUT_OF_MEMORY"]
        assert any("残りのローカルモデルを見送りました" in note for note in result.execution_notes)

    def test_oom_with_recovery_continues_remaining_models(self) -> None:
        probe = ScriptedProbe([16.0, 2.0, 8.0])
        runner = RecordingRunner({"local-a": _oom("local-a"), "local-b": _ok("local-b")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("local-b", requires_api_key=False)
        )
        worker = _worker(runner, ["local-a", "local-b"], registry, _policy(probe, FakeClock()))

        result = worker.execute()

        assert runner.called_models == ["local-a", "local-b"]
        assert "local-b" in result.results["phash-b"]

    def test_oom_on_last_local_model_does_not_wait(self) -> None:
        probe = ScriptedProbe([16.0, 1.0])
        runner = RecordingRunner({"local-a": _oom("local-a"), "api-x": _ok("api-x")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("api-x", requires_api_key=True)
        )
        worker = _worker(runner, ["local-a", "api-x"], registry, _policy(probe, FakeClock()))

        worker.execute()

        assert runner.called_models == ["local-a", "api-x"]
        assert probe.calls == 1


@pytest.mark.unit
class TestPerModelPersistenceAndCancel:
    def test_cancel_after_first_model_keeps_its_saved_results(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """実経路: 1 モデル完了 → 中止。完了モデルは中止前に保存され、次のモデルは呼ばれない。"""
        db = _db_manager()
        runner = RecordingRunner({"local-a": _ok("local-a"), "local-b": _ok("local-b")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("local-b", requires_api_key=False)
        )
        worker = _worker(
            runner, ["local-a", "local-b"], registry, _policy(ScriptedProbe([16.0]), FakeClock()), db
        )
        save_calls_at_cancel: list[int] = []

        def cancel_after_first(model: str) -> None:
            if model == "local-a":
                worker.cancel()

        runner.after_call = cancel_after_first
        original_persist = worker._persist_incremental_results

        def spy_persist(chunk: dict[str, object], **kwargs: object) -> tuple[int, int]:
            outcome = original_persist(chunk, **kwargs)
            save_calls_at_cancel.append(len(chunk))
            return outcome

        monkeypatch.setattr(worker, "_persist_incremental_results", spy_persist)
        persisted_signals: list[set[str]] = []
        worker.partial_results_persisted.connect(persisted_signals.append)
        summaries: list[str] = []
        worker.progress_updated.connect(lambda p: summaries.append(p.annotation_progress.detail_text()))

        with pytest.raises(CancellationError):
            worker.execute()

        assert runner.called_models == ["local-a"]
        # local-a の結果はモデル完了時点で保存されている
        assert save_calls_at_cancel and save_calls_at_cancel[0] == 2
        assert {("phash-a", "local-a"), ("phash-b", "local-a")} <= worker._persisted_keys
        assert (
            db.annotation_repo.save_annotations_batch.called or db.annotation_repo.save_annotations.called
        )
        assert persisted_signals and {"phash-a", "phash-b"} <= persisted_signals[-1]
        assert "完了した 1モデルの結果は保存済み" in summaries[-1]

    def test_cancel_during_memory_wait_stops_without_running(self) -> None:
        clock = FakeClock()
        runner = RecordingRunner({"local-a": _ok("local-a")})
        workers: list[AnnotationWorker] = []

        def sleep_then_cancel(seconds: float) -> None:
            clock.sleep(seconds)
            if clock.now >= 3.0:
                workers[0].cancel()

        policy = AnnotationExecutionPolicy(
            AnnotationExecutionSettings(wait_timeout_sec=600.0),
            memory_probe=ScriptedProbe([1.0]),
            clock=clock,
            sleep=sleep_then_cancel,
        )
        worker = _worker(
            runner, ["local-a"], _registry(_model_info("local-a", requires_api_key=False)), policy
        )
        workers.append(worker)

        with pytest.raises(CancellationError):
            worker.execute()

        assert runner.called_models == []
        assert clock.now < 5.0


@pytest.mark.unit
class TestExecutionDeviceAndRerunSkip:
    def test_cpu_execution_is_reported_from_result(self) -> None:
        runner = RecordingRunner({"local-a": _ok("local-a", device="cpu")})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([16.0]), FakeClock()),
        )
        details: list[str] = []
        worker.progress_updated.connect(lambda p: details.append(p.annotation_progress.detail_text()))

        result = worker.execute()

        assert "local-a: CPU で実行しました" in result.execution_notes
        assert "local-a: CPU で実行しました" in details

    def test_cpu_execution_is_reported_from_runtime_info(self) -> None:
        runner = RecordingRunner({"local-a": _ok("local-a")}, device="cpu")
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([16.0]), FakeClock()),
        )

        assert worker.execute().execution_notes == ["local-a: CPU で実行しました"]

    def test_gpu_or_unknown_device_adds_no_note(self) -> None:
        runner = RecordingRunner({"local-a": _ok("local-a", device="cuda:0")}, device=None)
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([16.0]), FakeClock()),
        )

        assert worker.execute().execution_notes == []

    def test_rerun_skips_images_that_already_have_model_results(self) -> None:
        db = _db_manager()
        db.image_repo.get_image_ids_with_model_annotations.side_effect = lambda ids, model: (
            {1} if model == "local-a" else {1, 2}
        )
        runner = RecordingRunner({"local-a": _ok("local-a"), "local-b": _ok("local-b")})
        registry = _registry(
            _model_info("local-a", requires_api_key=False), _model_info("local-b", requires_api_key=False)
        )
        worker = _worker(
            runner,
            ["local-a", "local-b"],
            registry,
            _policy(ScriptedProbe([16.0]), FakeClock(), skip_completed_on_rerun=True),
            db,
        )

        result = worker.execute()

        # local-a は未完了の b だけ (pHash も同じ位置で揃える)、local-b は全画像完了済みで呼ばない
        assert runner.calls == [(["/images/b.jpg"], ["local-a"], ["phash-b"])]
        assert "local-b: 全画像に結果があるため実行を省略しました" in result.execution_notes

    def test_rerun_skip_disabled_by_default(self) -> None:
        db = _db_manager()
        runner = RecordingRunner({"local-a": _ok("local-a")})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([16.0]), FakeClock()),
            db,
        )

        worker.execute()

        db.image_repo.get_image_ids_with_model_annotations.assert_not_called()
        assert runner.calls[0][0] == IMAGE_PATHS


@pytest.mark.unit
def test_default_policy_is_built_from_config_service() -> None:
    from lorairo.services.configuration_service import ConfigurationService

    db = _db_manager()
    db.config_service = ConfigurationService(
        shared_config={"annotation_execution": {"wait_timeout_sec": 7, "ram_safety_margin_gb": 1.5}}
    )
    worker = AnnotationWorker(
        annotation_runner=Mock(),
        image_paths=list(IMAGE_PATHS),
        litellm_model_ids=["local-a"],
        db_manager=db,
        model_registry=_registry(),
    )

    settings = worker._execution_policy.settings
    assert settings.wait_timeout_sec == 7.0
    assert settings.ram_safety_margin_gb == 1.5


@pytest.mark.unit
class TestRerunSkipScope:
    """skip_completed_on_rerun の完了済み判定と保存範囲 (Codex P2 on PR #1612)。"""

    @staticmethod
    def _spy_persist(worker: AnnotationWorker, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
        calls: list[dict[str, object]] = []
        original = worker._persist_incremental_results

        def spy(chunk: dict[str, object], **kwargs: object) -> tuple[int, int]:
            calls.append({"models": {m for a in chunk.values() for m in a}, **kwargs})
            return original(chunk, **kwargs)

        monkeypatch.setattr(worker, "_persist_incremental_results", spy)
        return calls

    def test_fully_completed_model_is_skipped_before_memory_admission(self) -> None:
        db = _db_manager()
        db.image_repo.get_image_ids_with_model_annotations.return_value = {1, 2}
        probe = ScriptedProbe([0.5])
        runner = RecordingRunner({"local-a": _ok("local-a")})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(probe, FakeClock(), skip_completed_on_rerun=True),
            db,
        )

        result = worker.execute()

        assert runner.calls == []
        assert probe.calls == 0
        assert _memory_error_records(db) == []
        assert result.model_errors == []
        assert result.execution_notes == ["local-a: 全画像に結果があるため実行を省略しました"]

    def test_memory_skip_records_only_remaining_targets(self) -> None:
        db = _db_manager()
        db.image_repo.get_image_ids_with_model_annotations.return_value = {1}
        runner = RecordingRunner({"local-a": _ok("local-a")})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([0.5]), FakeClock(), skip_completed_on_rerun=True),
            db,
        )

        result = worker.execute()

        assert [r["file_path"] for r in _memory_error_records(db)] == ["/images/b.jpg"]
        assert [e.raw_image_path for e in result.model_errors] == ["/images/b.jpg"]

    def test_saves_are_scoped_to_inferred_images_when_phash_is_shared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同じ pHash の完了済み画像へ結果を fan-out しない。"""
        db = _db_manager()
        db.image_repo.get_phashes_by_filepaths.return_value = {
            "/images/a.jpg": "phash-a",
            "/images/b.jpg": "phash-a",
        }
        db.image_repo.find_image_ids_by_phashes.return_value = {"phash-a": 1}
        db.image_repo.find_image_ids_by_phashes_multi.return_value = {"phash-a": [1, 2]}
        db.image_repo.get_image_ids_by_filepaths.return_value = {"/images/a.jpg": 1, "/images/b.jpg": 2}
        db.image_repo.get_image_ids_with_model_annotations.return_value = {1}
        runner = RecordingRunner({"local-a": {"phash-a": {"local-a": {"tags": ["x"], "error": None}}}})
        worker = _worker(
            runner,
            ["local-a"],
            _registry(_model_info("local-a", requires_api_key=False)),
            _policy(ScriptedProbe([16.0]), FakeClock(), skip_completed_on_rerun=True),
            db,
        )
        calls = self._spy_persist(worker, monkeypatch)

        worker.execute()

        assert runner.calls[0][0] == ["/images/b.jpg"]
        assert calls[0]["allowed_image_ids"] == {2}
        assert calls[0]["resolved_allowed_ids"] is True

    def test_final_save_retry_keeps_model_scope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _db_manager()
        runner = RecordingRunner({})
        worker = _worker(
            runner,
            ["local-a", "api-x"],
            _registry(),
            _policy(ScriptedProbe([16.0]), FakeClock()),
            db,
        )
        worker._model_save_scopes = {"local-a": {2}}
        calls = self._spy_persist(worker, monkeypatch)
        results = {
            "phash-a": {
                "local-a": {"tags": ["x"], "error": None},
                "api-x": {"tags": ["y"], "error": None},
            }
        }

        worker._save_results_to_database(results)

        scoped = [c for c in calls if c["models"] == {"local-a"}]
        unscoped = [c for c in calls if c["models"] == {"api-x"}]
        assert scoped and scoped[0]["allowed_image_ids"] == {2}
        assert unscoped and unscoped[0]["allowed_image_ids"] == {1, 2}
