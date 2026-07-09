"""export create コマンドのユニットテスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _make_export_container(tmp_path: Path) -> MagicMock:
    """export テスト用 ServiceContainer モックを生成する。"""
    container = MagicMock()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    container.dataset_export_service.export_dataset_txt_format.return_value = out_dir
    container.dataset_export_service.export_dataset_json_format.return_value = out_dir
    return container


@pytest.fixture
def mock_export_context(tmp_path, monkeypatch):
    """project 確認と ServiceContainer をモック。"""
    container = _make_export_container(tmp_path)
    monkeypatch.setattr("lorairo.cli.commands.export.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.export.get_service_container", MagicMock(return_value=container)
    )
    return container, tmp_path


@pytest.mark.unit
class TestExportCreate:
    def test_create_with_image_ids_calls_both_exporters(self, mock_export_context, tmp_path):
        """--image-ids 指定時に txt と json 両エクスポーターが呼ばれる。"""
        container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1,2,3",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        container.dataset_export_service.export_dataset_txt_format.assert_called_once()
        container.dataset_export_service.export_dataset_json_format.assert_called_once()

    def test_create_without_image_ids_fails(self, mock_export_context, tmp_path):
        """--image-ids なしは exit 2 (INVALID_INPUT)。"""
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2

    def test_create_json_output_has_result_row(self, mock_export_context, tmp_path):
        """--json 出力に kind=result 行が含まれる。"""
        _container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "--json",
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1,2,3",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        json_lines = []
        for line in result.output.strip().splitlines():
            if not line.strip():
                continue
            try:
                json_lines.append(json.loads(line))
            except json.JSONDecodeError:
                pass  # loguru やその他の非 JSON 行はスキップ
        result_row = next(r for r in json_lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        assert result_row["total_images"] == 3

    def test_create_invalid_image_ids_fails(self, mock_export_context, tmp_path):
        """非整数の --image-ids は exit 2 (INVALID_INPUT)。"""
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "abc,def",
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2

    def test_create_resolution_passed_to_exporters(self, mock_export_context, tmp_path):
        """--resolution が両エクスポーターに渡される。"""
        container, _ = mock_export_context
        runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1",
                "--output",
                str(tmp_path / "out"),
                "--resolution",
                "1024",
            ],
        )
        call_args_txt = container.dataset_export_service.export_dataset_txt_format.call_args
        call_args_json = container.dataset_export_service.export_dataset_json_format.call_args
        assert call_args_txt is not None
        assert call_args_json is not None
        # resolution は第3引数 (positional) または keyword "resolution" で渡される
        txt_args = call_args_txt[0]
        json_args = call_args_json[0]
        assert 1024 in txt_args or call_args_txt[1].get("resolution") == 1024
        assert 1024 in json_args or call_args_json[1].get("resolution") == 1024

    def test_create_tag_languages_passed_to_exporters(self, mock_export_context, tmp_path):
        """--tag-language の複数指定が両エクスポーターに渡される。"""
        container, _ = mock_export_context
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1",
                "--output",
                str(tmp_path / "out"),
                "--tag-language",
                "canonical",
                "--tag-language",
                "ja",
            ],
        )
        assert result.exit_code == 0
        txt_kwargs = container.dataset_export_service.export_dataset_txt_format.call_args.kwargs
        json_kwargs = container.dataset_export_service.export_dataset_json_format.call_args.kwargs
        assert txt_kwargs["tag_languages"] == ["canonical", "ja"]
        assert json_kwargs["tag_languages"] == ["canonical", "ja"]


@pytest.mark.unit
class TestExportCreateImageIdsFile:
    """export create の --image-ids-file 入力 (Issue #1216)。"""

    def test_create_with_image_ids_file(self, mock_export_context, tmp_path):
        container, _ = mock_export_context
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("1\n2, 3\n")
        result = runner.invoke(
            app,
            [
                "--json",
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids-file",
                str(ids_file),
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        called_ids = container.dataset_export_service.export_dataset_txt_format.call_args.args[0]
        assert called_ids == [1, 2, 3]

    def test_create_both_ids_inputs_rejected(self, mock_export_context, tmp_path):
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("1")
        result = runner.invoke(
            app,
            [
                "export",
                "create",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--image-ids-file",
                str(ids_file),
                "--output",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 2
