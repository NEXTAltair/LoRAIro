"""tags コマンド群のユニットテスト。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app

runner = CliRunner()


def _make_container(*, image_exists: bool = True) -> MagicMock:
    container = MagicMock()
    mock_records = [{"id": 1}, {"id": 2}] if image_exists else []
    container.db_manager.image_repo.get_images_by_filter.return_value = (mock_records, len(mock_records))
    container.db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, 2)
    container.db_manager.annotation_repo.remove_tag_from_images_batch.return_value = (
        True,
        [(1, "changed"), (2, "changed")],
    )
    container.db_manager.annotation_repo.replace_tag_for_images_batch.return_value = (
        True,
        [(1, "changed"), (2, "skipped")],
    )
    return container


@pytest.fixture
def mock_project_and_container(monkeypatch):
    container = _make_container()
    monkeypatch.setattr("lorairo.cli.commands.tags.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.tags.get_service_container", MagicMock(return_value=container)
    )
    return container


@pytest.mark.unit
class TestTagsAdd:
    def test_add_dry_run_default_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_not_called()

    def test_add_apply_writes_to_db(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "add", "--project", "proj", "--image-ids", "1,2", "--tags", "cat", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.add_tag_to_images_batch.assert_called()

    def test_add_json_output_has_result_row(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "add",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--tags",
                "cat",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert result_row["ok"] is True
        assert result_row["dry_run"] is False


@pytest.mark.unit
class TestTagsRemove:
    def test_remove_dry_run_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_not_called()

    def test_remove_apply_writes(self, mock_project_and_container):
        result = runner.invoke(
            app,
            ["tags", "remove", "--project", "proj", "--image-ids", "1,2", "--tags", "bad_tag", "--apply"],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.remove_tag_from_images_batch.assert_called()


@pytest.mark.unit
class TestTagsReplace:
    def test_replace_dry_run_does_not_write(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "tags",
                "replace",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--from",
                "bad",
                "--to",
                "good",
            ],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.replace_tag_for_images_batch.assert_not_called()

    def test_replace_apply_writes(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "tags",
                "replace",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--from",
                "bad",
                "--to",
                "good",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        mock_project_and_container.db_manager.annotation_repo.replace_tag_for_images_batch.assert_called()

    def test_replace_json_item_rows(self, mock_project_and_container):
        result = runner.invoke(
            app,
            [
                "--json",
                "tags",
                "replace",
                "--project",
                "proj",
                "--image-ids",
                "1,2",
                "--from",
                "bad",
                "--to",
                "good",
                "--apply",
            ],
        )
        assert result.exit_code == 0
        lines = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
        items = [r for r in lines if r.get("kind") == "item"]
        result_row = next(r for r in lines if r.get("kind") == "result")
        assert len(items) == 2
        assert result_row["ok"] is True
        assert result_row["dry_run"] is False
