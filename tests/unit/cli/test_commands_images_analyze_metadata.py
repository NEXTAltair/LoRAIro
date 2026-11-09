"""images analyze-metadata コマンドのユニットテスト (ADR 0106, Issue #1482)。"""

import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.domain.generation_metadata import (
    AiGeneratedTagBatchResult,
    GenerationMetadataAnalysisItem,
    GenerationMetadataStatus,
)

runner = CliRunner()


@pytest.fixture
def container(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    container = MagicMock()
    records = [{"id": 42}, {"id": 57}]
    container.db_manager.image_repo.get_images_by_filter.return_value = (records, len(records))
    container.db_manager.get_unanalyzed_generation_image_ids.return_value = [7]
    container.db_manager.count_unanalyzed_generation_images.return_value = 3
    container.db_manager.analyze_generation_metadata.side_effect = lambda ids, force=False: [
        GenerationMetadataAnalysisItem(i, "analyzed", GenerationMetadataStatus.PARSED, "sd_webui")
        for i in ids
    ]
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return container


def _rows(output: str) -> list[dict]:
    return [json.loads(line) for line in output.strip().splitlines() if line.strip().startswith("{")]


@pytest.mark.unit
class TestImagesAnalyzeMetadata:
    def test_without_ids_processes_unanalyzed_images(self, container: MagicMock) -> None:
        result = runner.invoke(app, ["--json", "images", "analyze-metadata", "-p", "proj", "--limit", "10"])

        assert result.exit_code == 0, result.output
        container.db_manager.get_unanalyzed_generation_image_ids.assert_called_once_with(10, 0)
        container.db_manager.analyze_generation_metadata.assert_called_once_with([7], force=False)
        rows = _rows(result.output)
        assert [r["image_id"] for r in rows if r.get("kind") == "item"] == [7]
        summary = next(r for r in rows if r.get("kind") == "result")
        assert summary["analyzed"] == 1
        assert summary["remaining_unanalyzed"] == 3
        assert summary["next_after_id"] == 7

    def test_after_id_cursor_is_passed(self, container: MagicMock) -> None:
        result = runner.invoke(
            app, ["--json", "images", "analyze-metadata", "-p", "proj", "--after-id", "6"]
        )

        assert result.exit_code == 0, result.output
        container.db_manager.get_unanalyzed_generation_image_ids.assert_called_once_with(500, 6)

    def test_with_ids_and_force_replaces_results(self, container: MagicMock) -> None:
        result = runner.invoke(
            app, ["--json", "images", "analyze-metadata", "42", "57", "-p", "proj", "--force"]
        )

        assert result.exit_code == 0, result.output
        container.db_manager.analyze_generation_metadata.assert_called_once_with([42, 57], force=True)
        items = [r for r in _rows(result.output) if r.get("kind") == "item"]
        assert items[0] == {**items[0], "image_id": 42, "action": "analyzed", "status": "parsed"}

    def test_force_without_ids_is_rejected(self, container: MagicMock) -> None:
        result = runner.invoke(app, ["images", "analyze-metadata", "-p", "proj", "--force"])

        assert result.exit_code == 2
        container.db_manager.analyze_generation_metadata.assert_not_called()

    def test_missing_file_is_partial_failure(self, container: MagicMock) -> None:
        container.db_manager.analyze_generation_metadata.side_effect = lambda ids, force=False: [
            GenerationMetadataAnalysisItem(42, "analyzed", GenerationMetadataStatus.NO_METADATA),
            GenerationMetadataAnalysisItem(57, "file_missing"),
        ]

        result = runner.invoke(app, ["images", "analyze-metadata", "42,57", "-p", "proj"])

        assert result.exit_code == 3
        assert "file_missing" in result.output


@pytest.mark.unit
class TestImagesTagAiGenerated:
    def test_apply_across_project_and_json_output(self, container: MagicMock) -> None:
        container.db_manager.apply_ai_generated_tags_batch.return_value = AiGeneratedTagBatchResult(
            target_images=10,
            evidence_images=4,
            tags_added=3,
            tags_skipped=1,
            tags_revoked=0,
            dry_run=False,
            revoked=False,
        )

        result = runner.invoke(app, ["--json", "images", "tag-ai-generated", "-p", "proj"])

        assert result.exit_code == 0, result.output
        container.db_manager.apply_ai_generated_tags_batch.assert_called_once_with(None, dry_run=False)
        summary = next(r for r in _rows(result.output) if r.get("kind") == "result")
        assert summary == {
            "kind": "result",
            "ok": True,
            "message": "Added ai generated tag to 3 image(s)",
            "dry_run": False,
            "revoked": False,
            "target_images": 10,
            "evidence_images": 4,
            "tags_added": 3,
            "tags_skipped": 1,
            "tags_revoked": 0,
        }

    def test_dry_run_with_image_ids_validates_and_forwards(self, container: MagicMock) -> None:
        container.db_manager.apply_ai_generated_tags_batch.return_value = AiGeneratedTagBatchResult(
            target_images=2,
            evidence_images=2,
            tags_added=1,
            tags_skipped=1,
            tags_revoked=0,
            dry_run=True,
            revoked=False,
        )

        result = runner.invoke(
            app, ["images", "tag-ai-generated", "42", "--image-ids", "57", "-p", "proj", "--dry-run"]
        )

        assert result.exit_code == 0, result.output
        container.db_manager.apply_ai_generated_tags_batch.assert_called_once_with([42, 57], dry_run=True)
        assert "Would add ai generated tag to 1 image(s)" in result.output
        assert "tags_added=1" in result.output

    def test_revoke_forwards_to_revoke_batch(self, container: MagicMock) -> None:
        container.db_manager.revoke_ai_generated_tags_batch.return_value = AiGeneratedTagBatchResult(
            target_images=2,
            evidence_images=0,
            tags_added=0,
            tags_skipped=0,
            tags_revoked=2,
            dry_run=True,
            revoked=True,
        )

        result = runner.invoke(
            app, ["--json", "images", "tag-ai-generated", "42,57", "-p", "proj", "--revoke", "--dry-run"]
        )

        assert result.exit_code == 0, result.output
        container.db_manager.revoke_ai_generated_tags_batch.assert_called_once_with([42, 57], dry_run=True)
        summary = next(r for r in _rows(result.output) if r.get("kind") == "result")
        assert summary["revoked"] is True
        assert summary["dry_run"] is True
        assert summary["tags_revoked"] == 2
