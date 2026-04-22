"""BatchImportWorker ユニットテスト。"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.workers.batch_import_worker import BatchImportWorker
from lorairo.services.batch_import_service import BatchImportResult


@pytest.fixture
def mock_repository():
    return Mock()


@pytest.fixture
def sample_result():
    return BatchImportResult(
        total_records=5,
        parsed_ok=5,
        matched=5,
        saved=5,
        model_name="gpt-4o-mini",
    )


class TestBatchImportWorkerInit:
    """BatchImportWorker 初期化テスト。"""

    def test_operation_type_is_batch_import(self):
        assert BatchImportWorker._OPERATION_TYPE == "batch_import"

    def test_init_with_db_manager(self, mock_repository, tmp_path):
        from unittest.mock import Mock

        mock_db_manager = Mock()
        jsonl_file = tmp_path / "result.jsonl"
        jsonl_file.touch()
        worker = BatchImportWorker(mock_repository, [jsonl_file], db_manager=mock_db_manager)
        assert worker._db_manager is mock_db_manager

    def test_init_defaults(self, mock_repository, tmp_path):
        jsonl_file = tmp_path / "result.jsonl"
        jsonl_file.touch()
        worker = BatchImportWorker(mock_repository, [jsonl_file])
        assert worker._repository is mock_repository
        assert worker._jsonl_files == [jsonl_file]
        assert worker._dry_run is False
        assert worker._model_name_override is None
        assert worker._db_manager is None

    def test_init_with_options(self, mock_repository, tmp_path):
        jsonl_file = tmp_path / "result.jsonl"
        jsonl_file.touch()
        worker = BatchImportWorker(
            mock_repository,
            [jsonl_file],
            dry_run=True,
            model_name_override="custom-model",
        )
        assert worker._dry_run is True
        assert worker._model_name_override == "custom-model"


class TestBatchImportWorkerExecute:
    """BatchImportWorker.execute() テスト。"""

    def test_execute_empty_files(self, mock_repository):
        worker = BatchImportWorker(mock_repository, [])
        result = worker.execute()
        assert result.total_records == 0
        assert result.saved == 0

    def test_execute_single_file(self, mock_repository, tmp_path, sample_result):
        jsonl_file = tmp_path / "result.jsonl"
        jsonl_file.touch()

        with patch("lorairo.gui.workers.batch_import_worker.BatchImportService") as MockService:
            mock_service = Mock()
            mock_service.import_from_jsonl.return_value = sample_result
            MockService.return_value = mock_service

            worker = BatchImportWorker(mock_repository, [jsonl_file])
            result = worker.execute()

        assert result.saved == 5
        assert result.total_records == 5

    def test_execute_multiple_files(self, mock_repository, tmp_path):
        jsonl_file1 = tmp_path / "result1.jsonl"
        jsonl_file2 = tmp_path / "result2.jsonl"
        jsonl_file1.touch()
        jsonl_file2.touch()

        per_file_result = BatchImportResult(total_records=3, saved=3, model_name="gpt-4o")

        with patch("lorairo.gui.workers.batch_import_worker.BatchImportService") as MockService:
            mock_service = Mock()
            mock_service.import_from_jsonl.return_value = per_file_result
            MockService.return_value = mock_service

            worker = BatchImportWorker(mock_repository, [jsonl_file1, jsonl_file2])
            result = worker.execute()

        assert result.total_records == 6
        assert result.saved == 6

    def test_execute_dry_run_mode(self, mock_repository, tmp_path):
        jsonl_file = tmp_path / "result.jsonl"
        jsonl_file.touch()

        dry_run_result = BatchImportResult(total_records=2, matched=2, saved=0)

        with patch("lorairo.gui.workers.batch_import_worker.BatchImportService") as MockService:
            mock_service = Mock()
            mock_service.import_from_jsonl.return_value = dry_run_result
            MockService.return_value = mock_service

            worker = BatchImportWorker(mock_repository, [jsonl_file], dry_run=True)
            result = worker.execute()

        # dry_run=True は import_from_jsonl の引数として渡される
        mock_service.import_from_jsonl.assert_called_once_with(
            jsonl_file, dry_run=True, model_name_override=None
        )
        assert result.saved == 0


class TestAggregateResults:
    """BatchImportWorker._aggregate_results() テスト。"""

    def test_aggregate_empty(self):
        result = BatchImportWorker._aggregate_results([])
        assert result.total_records == 0
        assert result.saved == 0

    def test_aggregate_single(self):
        r = BatchImportResult(total_records=5, saved=4, unmatched=1, unmatched_ids=["id1"])
        result = BatchImportWorker._aggregate_results([r])
        assert result.total_records == 5
        assert result.saved == 4
        assert result.unmatched_ids == ["id1"]

    def test_aggregate_multiple(self):
        r1 = BatchImportResult(
            total_records=3,
            parsed_ok=3,
            matched=2,
            unmatched=1,
            saved=2,
            model_name="gpt-4o",
            unmatched_ids=["a"],
        )
        r2 = BatchImportResult(
            total_records=4,
            parsed_ok=4,
            matched=4,
            unmatched=0,
            saved=4,
            model_name="gpt-4o",
            error_details=["err"],
        )
        result = BatchImportWorker._aggregate_results([r1, r2])
        assert result.total_records == 7
        assert result.saved == 6
        assert result.unmatched_ids == ["a"]
        assert result.error_details == ["err"]
        assert result.model_name == "gpt-4o"

    def test_aggregate_model_name_from_first_nonempty(self):
        r1 = BatchImportResult(model_name="")
        r2 = BatchImportResult(model_name="custom-model")
        result = BatchImportWorker._aggregate_results([r1, r2])
        assert result.model_name == "custom-model"
