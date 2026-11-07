"""DatasetImportWorker のユニットテスト (service はモック)。"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.workers.dataset_import_worker import DatasetImportWorker
from lorairo.services.dataset_import_service import (
    DatasetImportPlan,
    DatasetImportResult,
    DatasetImportService,
)

_SERVICE = "lorairo.gui.workers.dataset_import_worker.DatasetImportService"
_REPO = "lorairo.gui.workers.dataset_import_worker.DatasetRepository"


@pytest.fixture
def result():
    return DatasetImportResult(
        dataset_id=1,
        version_id=7,
        folder_count=2,
        image_count=10,
        skipped_images=1,
        training_config_ids=[3],
    )


def _plan() -> DatasetImportPlan:
    return DatasetImportPlan("ds", "v1", None, [], [Path("auto.json")])


def _make_worker(tmp_path: Path, configs: list[Path]) -> DatasetImportWorker:
    return DatasetImportWorker(tmp_path, "ds", "v1", configs, Mock(), Mock())


def test_execute_passes_selected_config_files_to_plan_and_returns_result(tmp_path, result):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}")
    with patch(_SERVICE) as service_cls, patch(_REPO):
        service = service_cls.return_value
        service.propose_plan.return_value = _plan()
        service.import_directory.return_value = result
        out = _make_worker(tmp_path, [cfg]).execute()
    assert out is result
    # 版名の候補を選択した JSON から作れるよう、propose_plan に明示して渡す
    assert service.propose_plan.call_args.args[3] == [cfg.resolve()]


def test_run_emits_finished_on_success(qtbot, tmp_path, result):
    worker = _make_worker(tmp_path, [])
    with patch(_SERVICE) as service_cls, patch(_REPO):
        service = service_cls.return_value
        service.propose_plan.return_value = _plan()
        service.import_directory.return_value = result
        with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
            worker.run()
    assert blocker.args == [result]


def test_run_rejects_deleted_selected_config_before_import(qtbot, tmp_path):
    # 選択後に削除された JSON は実 service の propose_plan で拒否され、取り込みに進まない
    missing = tmp_path / "deleted.json"
    worker = _make_worker(tmp_path, [missing])
    with (
        patch(_REPO),
        patch.object(DatasetImportService, "import_directory") as import_directory,
        patch.object(worker, "_record_unhandled_error"),
    ):
        with qtbot.waitSignal(worker.error_occurred, timeout=5000) as blocker:
            worker.run()
    import_directory.assert_not_called()
    assert "deleted.json" in blocker.args[0]


def test_run_emits_error_on_failure(qtbot, tmp_path):
    worker = _make_worker(tmp_path, [])
    with patch(_SERVICE) as service_cls, patch(_REPO):
        service_cls.return_value.propose_plan.side_effect = ValueError("bad plan")
        with patch.object(worker, "_record_unhandled_error"):
            with qtbot.waitSignal(worker.error_occurred, timeout=5000) as blocker:
                worker.run()
    assert "bad plan" in blocker.args[0]
