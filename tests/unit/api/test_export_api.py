"""Export API テスト。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lorairo.api.export import export_dataset
from lorairo.api.types import ExportCriteria, ExportResult
from lorairo.services.service_container import ServiceContainer


@pytest.fixture
def mock_export_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    """DatasetExportService + ProjectManagementService をモック。

    Args:
        monkeypatch: pytest monkeypatch フィクスチャ
        tmp_path: 一時ディレクトリ

    Returns:
        MagicMock: モック化された DatasetExportService
    """
    mock_service = MagicMock()

    # エクスポート結果として出力ディレクトリを返す
    def mock_export(image_ids, output_path, **kwargs):
        output_path.mkdir(parents=True, exist_ok=True)
        # ダミーファイルを作成
        (output_path / "export_1.txt").write_text("test content")
        (output_path / "export_2.txt").write_text("test content 2")
        return output_path

    mock_service.export_dataset_txt_format.side_effect = mock_export
    mock_service.export_dataset_json_format.side_effect = mock_export

    # ProjectManagementService モック（_resolve_project_image_ids用）
    mock_project_service = MagicMock()
    project_images_dir = tmp_path / "project" / "image_dataset" / "original_images"
    project_images_dir.mkdir(parents=True, exist_ok=True)
    # ダミー画像ファイル作成
    (project_images_dir / "img_001.jpg").write_bytes(b"\xff\xd8\xff")
    (project_images_dir / "img_002.png").write_bytes(b"\x89PNG")

    mock_project_info = MagicMock()
    mock_project_info.path = tmp_path / "project"
    mock_project_service.get_project.return_value = mock_project_info

    container = ServiceContainer()
    monkeypatch.setattr(container, "_dataset_export_service", mock_service)
    monkeypatch.setattr(container, "_project_management_service", mock_project_service)

    return mock_service


@pytest.mark.unit
class TestExportDataset:
    """export_dataset API テスト。"""

    def test_txt_format(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """TXTフォーマットでエクスポート。"""
        output = tmp_path / "output"
        criteria = ExportCriteria(format_type="txt", resolution=512)

        result = export_dataset("test-project", output, criteria)

        assert isinstance(result, ExportResult)
        assert result.format_type == "txt"
        assert result.resolution == 512
        assert result.file_count > 0
        mock_export_service.export_dataset_txt_format.assert_called_once()

    def test_json_format(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """JSONフォーマットでエクスポート。"""
        output = tmp_path / "output"
        criteria = ExportCriteria(format_type="json", resolution=1024)

        result = export_dataset("test-project", output, criteria)

        assert result.format_type == "json"
        assert result.resolution == 1024
        mock_export_service.export_dataset_json_format.assert_called_once()

    def test_default_criteria(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """criteria未指定でデフォルト値。"""
        output = tmp_path / "output"

        result = export_dataset("test-project", output)

        assert result.format_type == "txt"
        assert result.resolution == 512

    def test_string_path(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """文字列パスでも動作。"""
        output = tmp_path / "output"

        result = export_dataset("test-project", str(output))

        assert isinstance(result, ExportResult)

    def test_invalid_format(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """無効なフォーマットでPydanticバリデーションエラー。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            ExportCriteria(format_type="xml")

        assert "format_type" in str(exc_info.value)


@pytest.mark.unit
class TestExportCriteria:
    """ExportCriteria バリデーションテスト。"""

    def test_defaults(self) -> None:
        """デフォルト値が正しい。"""
        criteria = ExportCriteria()
        assert criteria.format_type == "txt"
        assert criteria.resolution == 512

    def test_custom_values(self) -> None:
        """カスタム値を設定可能。"""
        criteria = ExportCriteria(format_type="json", resolution=1024)
        assert criteria.format_type == "json"
        assert criteria.resolution == 1024
