"""annotate import-batch コマンドのユニットテスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.services.batch_import_service import BatchImportResult

runner = CliRunner()


def _make_batch_result(**overrides: object) -> BatchImportResult:
    """テスト用BatchImportResultを生成する。"""
    defaults = {
        "total_records": 100,
        "parsed_ok": 98,
        "parse_errors": 2,
        "matched": 90,
        "unmatched": 8,
        "saved": 90,
        "save_errors": 0,
        "model_name": "gpt-4-turbo-2024-04-09",
        "unmatched_ids": ["unknown_001", "unknown_002"],
        "error_details": [],
    }
    defaults.update(overrides)
    return BatchImportResult(**defaults)  # type: ignore[arg-type]


class TestImportBatchCommand:
    """import-batch CLIコマンドのテスト。"""

    @pytest.fixture(autouse=True)
    def mock_set_active_project(self) -> MagicMock:
        """set_active_project をモックして DB 接続切り替えをスキップする。"""
        with patch("lorairo.cli.commands.annotate.get_service_container") as mock_container_factory:
            mock_container = MagicMock()
            mock_container_factory.return_value = mock_container
            yield mock_container

    @patch("lorairo.cli.commands.annotate.import_batch_annotations")
    def test_normal_invocation(self, mock_import: MagicMock, tmp_path: Path) -> None:
        """正常呼び出しで結果テーブルが表示される。"""
        # JSONLファイルを用意（typerのexists=True検証用）
        jsonl_dir = tmp_path / "jsonl"
        jsonl_dir.mkdir()
        (jsonl_dir / "test.jsonl").write_text("{}", encoding="utf-8")

        mock_import.return_value = _make_batch_result()

        result = runner.invoke(app, ["annotate", "import-batch", str(jsonl_dir), "-p", "test_project"])

        assert result.exit_code == 0
        assert "Batch Import Summary" in result.output
        assert "90" in result.output  # saved count
        mock_import.assert_called_once()

    @patch("lorairo.cli.commands.annotate.import_batch_annotations")
    def test_dry_run_flag(self, mock_import: MagicMock, tmp_path: Path) -> None:
        """--dry-runフラグが伝播される。"""
        jsonl_dir = tmp_path / "jsonl"
        jsonl_dir.mkdir()
        (jsonl_dir / "test.jsonl").write_text("{}", encoding="utf-8")

        mock_import.return_value = _make_batch_result(saved=0)

        result = runner.invoke(
            app,
            ["annotate", "import-batch", str(jsonl_dir), "-p", "test_project", "--dry-run"],
        )

        assert result.exit_code == 0
        assert "DRY-RUN" in result.output
        call_kwargs = mock_import.call_args
        assert call_kwargs.kwargs["dry_run"] is True

    @patch("lorairo.cli.commands.annotate.import_batch_annotations")
    def test_model_name_override(self, mock_import: MagicMock, tmp_path: Path) -> None:
        """--model-nameオプションが伝播される。"""
        jsonl_dir = tmp_path / "jsonl"
        jsonl_dir.mkdir()
        (jsonl_dir / "test.jsonl").write_text("{}", encoding="utf-8")

        mock_import.return_value = _make_batch_result(model_name="custom-model")

        result = runner.invoke(
            app,
            [
                "annotate",
                "import-batch",
                str(jsonl_dir),
                "-p",
                "test_project",
                "--model-name",
                "custom-model",
            ],
        )

        assert result.exit_code == 0
        call_kwargs = mock_import.call_args
        assert call_kwargs.kwargs["model_name_override"] == "custom-model"

    def test_nonexistent_directory(self) -> None:
        """存在しないディレクトリでエラー。"""
        result = runner.invoke(
            app,
            ["annotate", "import-batch", "/nonexistent/path", "-p", "test_project"],
        )
        # typerのexists=Trueバリデーションによりエラー
        assert result.exit_code != 0

    @patch("lorairo.cli.commands.annotate.import_batch_annotations")
    def test_project_not_found(self, mock_import: MagicMock, tmp_path: Path) -> None:
        """存在しないプロジェクトでエラー。"""
        from lorairo.api.exceptions import ProjectNotFoundError

        jsonl_dir = tmp_path / "jsonl"
        jsonl_dir.mkdir()
        (jsonl_dir / "test.jsonl").write_text("{}", encoding="utf-8")

        mock_import.side_effect = ProjectNotFoundError("nonexistent")

        result = runner.invoke(
            app,
            ["annotate", "import-batch", str(jsonl_dir), "-p", "nonexistent"],
        )

        assert result.exit_code == 1
        assert "nonexistent" in result.output

    @patch("lorairo.cli.commands.annotate.import_batch_annotations")
    def test_unmatched_ids_displayed(self, mock_import: MagicMock, tmp_path: Path) -> None:
        """アンマッチIDが表示される。"""
        jsonl_dir = tmp_path / "jsonl"
        jsonl_dir.mkdir()
        (jsonl_dir / "test.jsonl").write_text("{}", encoding="utf-8")

        mock_import.return_value = _make_batch_result(unmatched_ids=["id_a", "id_b", "id_c"])

        result = runner.invoke(app, ["annotate", "import-batch", str(jsonl_dir), "-p", "test_project"])

        assert result.exit_code == 0
        assert "照合失敗" in result.output
        assert "id_a" in result.output
