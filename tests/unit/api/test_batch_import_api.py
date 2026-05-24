"""バッチインポートAPI テスト。

lorairo.api.batch_import モジュールのユニットテスト。
ServiceContainer と BatchImportService のラッパー関数を検証する。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.api.batch_import import import_batch_annotations
from lorairo.api.exceptions import BatchImportError, ProjectNotFoundError
from lorairo.services.batch_import_service import BatchImportResult


@pytest.mark.unit
class TestImportBatchAnnotations:
    """import_batch_annotations() のユニットテスト。"""

    def _make_result(self, **kwargs) -> BatchImportResult:
        """テスト用 BatchImportResult を生成するヘルパー。"""
        defaults = {
            "total_records": 0,
            "parsed_ok": 0,
            "parse_errors": 0,
            "matched": 0,
            "unmatched": 0,
            "saved": 0,
            "save_errors": 0,
            "model_name": "test-model",
            "unmatched_ids": [],
            "error_details": [],
        }
        defaults.update(kwargs)
        return BatchImportResult(**defaults)

    def test_raises_project_not_found_when_project_is_none(self, tmp_path: Path) -> None:
        """プロジェクトが存在しない場合 ProjectNotFoundError を送出する。"""
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = None

        with patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()

            with pytest.raises(ProjectNotFoundError) as exc_info:
                import_batch_annotations(tmp_path, "nonexistent_project")

        assert "nonexistent_project" in exc_info.value.project_name

    def test_raises_project_not_found_with_correct_project_name(self, tmp_path: Path) -> None:
        """ProjectNotFoundError に正しいプロジェクト名が設定される。"""
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = None

        with patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls:
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()

            with pytest.raises(ProjectNotFoundError) as exc_info:
                import_batch_annotations(tmp_path, "my_project")

        assert exc_info.value.project_name == "my_project"

    def test_wraps_file_not_found_error_as_batch_import_error(self, tmp_path: Path) -> None:
        """BatchImportService が FileNotFoundError を送出した場合 BatchImportError にラップする。"""
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.side_effect = FileNotFoundError("dir not found")

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()
            mock_service_cls.return_value = mock_batch_service

            with pytest.raises(BatchImportError):
                import_batch_annotations(tmp_path, "my_project")

    def test_wraps_value_error_as_batch_import_error(self, tmp_path: Path) -> None:
        """BatchImportService が ValueError を送出した場合 BatchImportError にラップする。"""
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.side_effect = ValueError("no jsonl files")

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()
            mock_service_cls.return_value = mock_batch_service

            with pytest.raises(BatchImportError):
                import_batch_annotations(tmp_path, "my_project")

    def test_returns_batch_import_result_on_success(self, tmp_path: Path) -> None:
        """インポートが成功した場合 BatchImportResult を返す。"""
        expected_result = self._make_result(total_records=5, parsed_ok=5, matched=5, saved=5)

        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.return_value = expected_result

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()
            mock_service_cls.return_value = mock_batch_service

            result = import_batch_annotations(tmp_path, "my_project")

        assert result is expected_result
        assert result.total_records == 5
        assert result.saved == 5

    def test_passes_dry_run_flag_to_service(self, tmp_path: Path) -> None:
        """dry_run フラグが BatchImportService に正しく渡される。"""
        expected_result = self._make_result()
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.return_value = expected_result

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()
            mock_service_cls.return_value = mock_batch_service

            import_batch_annotations(tmp_path, "my_project", dry_run=True)

        mock_batch_service.import_from_directory.assert_called_once_with(
            tmp_path, dry_run=True, model_name_override=None
        )

    def test_passes_model_name_override_to_service(self, tmp_path: Path) -> None:
        """model_name_override が BatchImportService に正しく渡される。"""
        expected_result = self._make_result()
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.return_value = expected_result

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()
            mock_service_cls.return_value = mock_batch_service

            import_batch_annotations(tmp_path, "my_project", model_name_override="gpt-4o")

        mock_batch_service.import_from_directory.assert_called_once_with(
            tmp_path, dry_run=False, model_name_override="gpt-4o"
        )

    def test_creates_batch_import_service_with_repository(self, tmp_path: Path) -> None:
        """BatchImportService は image_repository を受け取って生成される。"""
        expected_result = self._make_result()
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()
        mock_repository = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.return_value = expected_result

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = mock_repository
            mock_service_cls.return_value = mock_batch_service

            import_batch_annotations(tmp_path, "my_project")

        mock_service_cls.assert_called_once_with(mock_repository)

    def test_batch_import_error_preserves_original_exception(self, tmp_path: Path) -> None:
        """BatchImportError の cause は元の例外。"""
        original_error = FileNotFoundError("original message")
        mock_project_service = MagicMock()
        mock_project_service.get_project.return_value = MagicMock()

        mock_batch_service = MagicMock()
        mock_batch_service.import_from_directory.side_effect = original_error

        with (
            patch("lorairo.api.batch_import.ServiceContainer") as mock_container_cls,
            patch("lorairo.api.batch_import.BatchImportService") as mock_service_cls,
        ):
            mock_container_cls.return_value.project_management_service = mock_project_service
            mock_container_cls.return_value.image_repository = MagicMock()
            mock_service_cls.return_value = mock_batch_service

            with pytest.raises(BatchImportError) as exc_info:
                import_batch_annotations(tmp_path, "my_project")

        assert exc_info.value.__cause__ is original_error
