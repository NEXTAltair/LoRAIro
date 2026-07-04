"""images show コマンドのユニットテスト。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _annotations_for(image_id: int) -> dict:
    return {
        "tags": [
            {
                "id": 1,
                "tag": f"tag-{image_id}",
                "tag_id": 10,
                "model_id": 3,
                "existing": True,
                "is_edited_manually": False,
                "confidence_score": None,
                "rejected_at": None,
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        ],
        "captions": [],
        "scores": [],
        "score_labels": [],
        "ratings": [],
        "quality_summary": {},
    }


def _make_container(image_ids: list[int]) -> MagicMock:
    container = MagicMock()
    records = [{"id": i} for i in image_ids]
    container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    container.db_manager.image_repo.get_image_annotations_batch.side_effect = (
        lambda image_ids, include_rejected=False: {i: _annotations_for(i) for i in image_ids}
    )
    return container


@pytest.fixture
def mock_show_context(monkeypatch: pytest.MonkeyPatch):
    container = _make_container([42, 57])
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return container


@pytest.mark.unit
class TestImagesShow:
    def test_show_single_image_json(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 1
        assert items[0]["image_id"] == 42
        assert items[0]["tags"][0]["tag"] == "tag-42"
        assert result_row["ok"] is True
        assert result_row["target_images"] == 1

    def test_show_batch_csv(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "42,57"],
        )
        assert result.exit_code == 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        items = [r for r in lines if r.get("kind") == "item"]
        assert {row["image_id"] for row in items} == {42, 57}

    def test_show_passes_include_rejected_flag(self, mock_show_context: MagicMock) -> None:
        runner.invoke(
            app,
            [
                "--json",
                "images",
                "show",
                "--project",
                "proj",
                "--image-ids",
                "42",
                "--include-rejected",
            ],
        )
        mock_show_context.db_manager.image_repo.get_image_annotations_batch.assert_any_call(
            [42], include_rejected=True
        )

    def test_show_missing_image_id_errors(self, mock_show_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            ["--json", "images", "show", "--project", "proj", "--image-ids", "999"],
        )
        assert result.exit_code != 0
        lines = [
            json.loads(line) for line in result.output.strip().splitlines() if line.strip().startswith("{")
        ]
        error_row = next(r for r in lines if r.get("kind") == "error")
        assert error_row["code"] == "NOT_FOUND"

    def test_show_over_500_ids_rejected(self, mock_show_context: MagicMock) -> None:
        csv_ids = ",".join(str(i) for i in range(1, 502))
        result = runner.invoke(
            app,
            ["images", "show", "--project", "proj", "--image-ids", csv_ids],
        )
        assert result.exit_code != 0
