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

    project_root = tmp_path / "project"
    mock_project_info = MagicMock()
    mock_project_info.path = project_root
    mock_project_service.get_project.return_value = mock_project_info

    # DB接続先も同プロジェクトを指していると見なす（alignment check をパスさせる）
    monkeypatch.setattr("lorairo.api.export.get_current_project_root", lambda: project_root)

    # ImageRepository モック（フィルタ条件を適用して画像IDを返す）
    mock_repository = MagicMock()
    mock_repository.get_images_by_filter.return_value = (
        [{"id": 1}, {"id": 2}],
        2,
    )

    container = ServiceContainer()
    monkeypatch.setattr(container, "_dataset_export_service", mock_service)
    monkeypatch.setattr(container, "_project_management_service", mock_project_service)
    monkeypatch.setattr(container, "_image_repository", mock_repository)

    return mock_service


@pytest.mark.unit
class TestExportDataset:
    """export_dataset API テスト。"""

    def test_txt_format(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """TXTフォーマットでエクスポート。"""
        output = tmp_path / "output"
        criteria = ExportCriteria(format_type="txt", resolution=512, tag_filter=["cat"])

        result = export_dataset("test-project", output, criteria)

        assert isinstance(result, ExportResult)
        assert result.format_type == "txt"
        assert result.resolution == 512
        assert result.file_count > 0
        mock_export_service.export_dataset_txt_format.assert_called_once()

    def test_json_format(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """JSONフォーマットでエクスポート。"""
        output = tmp_path / "output"
        criteria = ExportCriteria(format_type="json", resolution=1024, tag_filter=["cat"])

        result = export_dataset("test-project", output, criteria)

        assert result.format_type == "json"
        assert result.resolution == 1024
        mock_export_service.export_dataset_json_format.assert_called_once()

    def test_default_criteria_no_filter_raises(
        self, mock_export_service: MagicMock, tmp_path: Path
    ) -> None:
        """criteria未指定（フィルタなし）は InvalidInputError。"""
        from lorairo.api.exceptions import InvalidInputError

        output = tmp_path / "output"

        with pytest.raises(InvalidInputError):
            export_dataset("test-project", output)

    def test_string_path(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """文字列パスでも動作。"""
        output = tmp_path / "output"
        criteria = ExportCriteria(tag_filter=["cat"])

        result = export_dataset("test-project", str(output), criteria)

        assert isinstance(result, ExportResult)

    def test_invalid_format(self, mock_export_service: MagicMock, tmp_path: Path) -> None:
        """無効なフォーマットでPydanticバリデーションエラー。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            ExportCriteria(format_type="xml")

        assert "format_type" in str(exc_info.value)

    def test_db_project_mismatch_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """DB接続先と project_name が指すプロジェクトが異なる場合、
        DatabaseConnectionError を発生させる。"""
        from lorairo.api.exceptions import DatabaseConnectionError

        # ProjectManagementService モック（プロジェクトは存在するが path は別）
        mock_project_service = MagicMock()
        mock_project_info = MagicMock()
        mock_project_info.path = tmp_path / "project_requested"
        mock_project_service.get_project.return_value = mock_project_info

        # DB接続先は別のプロジェクトを指している
        other_project = tmp_path / "project_connected"
        monkeypatch.setattr("lorairo.api.export.get_current_project_root", lambda: other_project)

        container = ServiceContainer()
        monkeypatch.setattr(container, "_project_management_service", mock_project_service)

        criteria = ExportCriteria(tag_filter=["cat"])
        with pytest.raises(DatabaseConnectionError) as exc_info:
            export_dataset("test-project", tmp_path / "output", criteria)

        # エラーメッセージに要求パスと接続中パスが含まれる
        assert "project_requested" in str(exc_info.value)
        assert "project_connected" in str(exc_info.value)

    def test_rating_normalized_for_db_query(
        self, mock_export_service: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """小文字 rating が API 層で大文字化されてから DB クエリに渡される。

        _apply_manual_filters は exact match、_apply_ai_rating_filter は
        UNRATED 分岐で大文字完全一致を使うため、正規化がないと 0 件ヒットになる。
        """
        container = ServiceContainer()
        captured: dict[str, object] = {}

        def capture_filter(filter_criteria, **kwargs):
            captured["manual"] = filter_criteria.manual_rating_filter
            captured["ai"] = filter_criteria.ai_rating_filter
            return ([{"id": 1}], 1)

        monkeypatch.setattr(container.image_repository, "get_images_by_filter", capture_filter)

        criteria = ExportCriteria(manual_rating="pg", ai_rating="unrated", tag_filter=["cat"])
        export_dataset("test-project", tmp_path / "output", criteria)

        assert captured["manual"] == "PG"
        assert captured["ai"] == "UNRATED"

    def test_excluded_tags_blank_stripped_before_db_query(
        self, mock_export_service: MagicMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """空白要素を含む excluded_tags が API 層で除外されてから DB に渡る。

        _apply_tag_filter で空文字列が NOT-EXISTS 内 LIKE '%%' に化けると
        タグを持つ画像を全て除外してしまうため、事前に除去する。
        """
        container = ServiceContainer()
        captured: dict[str, object] = {}

        def capture_filter(filter_criteria, **kwargs):
            captured["excluded"] = filter_criteria.excluded_tags
            return ([{"id": 1}], 1)

        monkeypatch.setattr(container.image_repository, "get_images_by_filter", capture_filter)

        criteria = ExportCriteria(excluded_tags=["nsfw", "", "  "])
        export_dataset("test-project", tmp_path / "output", criteria)

        assert captured["excluded"] == ["nsfw"]


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
