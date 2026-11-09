"""DatasetImportWorker のユニットテスト (service はモック)。"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.workers.dataset_import_worker import DatasetImportWorker
from lorairo.services.dataset_import_service import (
    DatasetImportPlan,
    DatasetImportResult,
    DatasetImportService,
    FolderImportPlan,
    FolderOverride,
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


def test_execute_applies_folder_overrides_to_plan(tmp_path, result):
    """確認画面の確定値 (取捨・繰り返し回数・トリガーワード) を計画に反映して取り込む (#1452)。"""
    plan = DatasetImportPlan(
        "ds",
        "v1",
        None,
        [
            FolderImportPlan("10_a", "a", 10, None, True),
            FolderImportPlan("5_b", "b", 5, None, True),
        ],
        [],
    )
    overrides = [
        FolderOverride("10_a", include=True, num_repeats=3, trigger_word=" trig_a "),
        FolderOverride("5_b", include=False, num_repeats=5, trigger_word=None),
    ]
    worker = DatasetImportWorker(tmp_path, "ds", "v1", [], Mock(), Mock(), overrides)
    with patch(_SERVICE) as service_cls, patch(_REPO):
        service = service_cls.return_value
        service.propose_plan.return_value = plan
        service.import_directory.return_value = result
        worker.execute()
    applied = service.import_directory.call_args.args[1]
    assert [(f.dir_name, f.include, f.num_repeats, f.trigger_word) for f in applied.folders] == [
        ("10_a", True, 3, "trig_a"),
        ("5_b", False, 5, None),
    ]


def test_execute_rejects_override_for_missing_folder(tmp_path):
    plan = DatasetImportPlan("ds", "v1", None, [FolderImportPlan("10_a", "a", 10, None, True)], [])
    overrides = [FolderOverride("9_gone", include=True, num_repeats=1, trigger_word=None)]
    worker = DatasetImportWorker(tmp_path, "ds", "v1", [], Mock(), Mock(), overrides)
    with patch(_SERVICE) as service_cls, patch(_REPO):
        service = service_cls.return_value
        service.propose_plan.return_value = plan
        with pytest.raises(ValueError, match="9_gone"):
            worker.execute()
    service.import_directory.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        [FolderOverride("10_a", True, 0, None)],
        [FolderOverride("10_a", True, 1, None), FolderOverride("10_a", False, 1, None)],
    ],
)
def test_apply_folder_overrides_rejects_invalid_values(overrides):
    from lorairo.services.dataset_import_service import apply_folder_overrides

    plan = DatasetImportPlan("ds", "v1", None, [FolderImportPlan("10_a", "a", 10, None, True)], [])
    with pytest.raises(ValueError):
        apply_folder_overrides(plan, overrides)


def test_apply_folder_overrides_excludes_folders_not_confirmed():
    """確認後に増えたフォルダ (確定値が無い) は取り込まない (Codex P2, PR #1472)。"""
    from lorairo.services.dataset_import_service import apply_folder_overrides

    plan = DatasetImportPlan(
        "ds",
        "v1",
        None,
        [FolderImportPlan("10_a", "a", 10, None, True), FolderImportPlan("3_new", "new", 3, None, True)],
        [],
    )
    applied = apply_folder_overrides(plan, [FolderOverride("10_a", True, 10, None)])
    assert [(f.dir_name, f.include) for f in applied.folders] == [("10_a", True), ("3_new", False)]


def test_execute_applies_parent_version_id_to_plan(tmp_path, result):
    """指定された parent_version_id を計画に反映して import_directory へ渡す (#1478)。"""
    worker = DatasetImportWorker(tmp_path, "ds", "v2", [], Mock(), Mock(), parent_version_id=15)
    with patch(_SERVICE) as service_cls, patch(_REPO):
        service = service_cls.return_value
        service.propose_plan.return_value = _plan()
        service.import_directory.return_value = result
        worker.execute()
    applied = service.import_directory.call_args.args[1]
    assert applied.parent_version_id == 15
