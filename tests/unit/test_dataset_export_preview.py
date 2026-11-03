"""Read-only export planning shares input selection and paths with actual export."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lorairo.database.access_policy import is_read_only
from lorairo.public_api.exceptions import ReadOnlyPreconditionError
from lorairo.services.dataset_export_service import DatasetExportService
from lorairo.services.export_overlay import ExportOverlayPlan, ExportTagOverlay, ScopedOverlayRule

pytestmark = pytest.mark.unit


@pytest.fixture
def preview_service(tmp_path, monkeypatch):
    paths = {}
    for image_id, name in ((1, "shared.png"), (2, "other.png"), (3, "shared.webp")):
        path = tmp_path / "sources" / str(image_id) / name
        path.parent.mkdir(parents=True)
        path.write_bytes(f"processed image {image_id}".encode())
        paths[image_id] = path
    db = MagicMock()
    db.get_image_metadata.side_effect = lambda image_id: {"id": image_id} if image_id < 99 else None
    db.check_processed_image_exists.side_effect = lambda image_id, resolution: (
        {"stored_image_path": str(paths[image_id])} if image_id in paths else None
    )
    db.get_image_annotations.side_effect = lambda image_id: {
        "tags": [{"tag": f"tag{image_id}"}],
        "captions": [{"caption": "synthetic caption"}] if image_id % 2 else [],
        "score_labels": [{"model": "scorer", "label": "good", "is_edited_manually": True}],
        "quality_summary": {},
    }
    db.annotation_repo.get_merged_reader.return_value = None
    service = DatasetExportService(MagicMock(), MagicMock(), db, MagicMock())
    service._get_export_reader = MagicMock(return_value=None)
    service.file_system_manager.copy_file.side_effect = shutil.copyfile
    service._translate_export_tag_list = MagicMock(
        side_effect=lambda tags, language, *args: [f"訳:{tag}" if language == "ja" else tag for tag in tags]
    )
    monkeypatch.setattr("lorairo.services.dataset_export_service.resolve_stored_path", Path)
    return service


def _snapshot(path):
    return {
        str(item.relative_to(path)): item.read_bytes() if item.is_file() else None
        for item in path.rglob("*")
    }


@pytest.mark.parametrize("languages", [None, ["canonical", "ja", "JA"]])
@pytest.mark.parametrize("existing_output", [False, True])
def test_preview_manifest_matches_real_export_without_writes(
    preview_service, tmp_path, languages, existing_output
):
    service = preview_service
    output = tmp_path / "out"
    if existing_output:
        output.mkdir()
        (output / "metadata.json").write_text("existing output")
    before = _snapshot(tmp_path)
    overlay = ExportOverlayPlan([ScopedOverlayRule(None, ExportTagOverlay(["trigger"], set(), {}))])
    image_ids = [1, 2, 3, 4, 99, 1]
    preview = service.preview_dataset_all_formats(
        image_ids, output, 768, tag_languages=languages, overlay_plan=overlay
    )
    assert _snapshot(tmp_path) == before
    service.file_system_manager.copy_file.assert_not_called()
    assert not is_read_only()
    planned = preview.summary()
    assert planned["dry_run"] is True
    assert planned["status"] == "partial_success"
    assert planned["requested"] == 5
    assert planned["would_export"] == 2
    assert planned["ready_ids"] == [1, 2]
    assert planned["skipped"] == 2
    assert planned["failed"] == 1
    assert planned["failed_ids"] == [3, 4, 99]
    assert "exported" not in planned and "exported_ids" not in planned
    assert all(
        "completed_formats" not in item and "output_files" not in item for item in planned["error_details"]
    )
    assert [row["image_id"] for row in preview.manifest] == [1, 2]
    assert all(
        call.args[1] == 768 for call in service.db_manager.check_processed_image_exists.call_args_list
    )

    report = service.export_dataset_all_formats(
        image_ids, output, 768, tag_languages=languages, overlay_plan=overlay
    )
    actual = report.summary()
    for field in ("requested", "skipped", "failed", "failed_ids", "status"):
        assert actual[field] == planned[field]
    assert actual["exported_ids"] == planned["ready_ids"]
    assert actual["exported"] == planned["would_export"]
    for row in preview.manifest:
        expected_artifacts = set()
        for destination in row["destinations"]:
            image = Path(destination["image_path"])
            assert image.read_bytes() == Path(row["source_path"]).read_bytes()
            expected_tags = ", ".join(
                f"訳:{tag}" if destination["language"] == "ja" else tag
                for tag in ("trigger", f"tag{row['image_id']}")
            )
            assert Path(destination["tags_path"]).read_text(encoding="utf-8") == expected_tags
            metadata = json.loads(Path(destination["metadata_path"]).read_text(encoding="utf-8"))
            assert metadata[str(image)]["tags"] == expected_tags
            assert (destination["caption_path"] is None) is (row["image_id"] == 2)
            expected_artifacts.update(
                value for key, value in destination.items() if key != "language" and value
            )
        assert set(report.artifacts[row["image_id"]]) == expected_artifacts
    assert all(Path(path).is_file() for path in planned["metadata_files"])


def test_preview_propagates_strict_preconditions_without_fallback(preview_service, tmp_path):
    error = ReadOnlyPreconditionError("prepare tags first", reason="tag_database_missing")
    preview_service._get_export_reader.side_effect = error
    with pytest.raises(ReadOnlyPreconditionError) as caught:
        preview_service.preview_dataset_all_formats([1], tmp_path / "out")
    assert caught.value is error
    assert not (tmp_path / "out").exists()
    assert not is_read_only()
    preview_service.db_manager.get_image_metadata.assert_not_called()


@pytest.mark.parametrize("image_ids,languages", [([], None), ([1], ["../invalid"])])
def test_preview_invalid_selection_never_reads_or_writes(preview_service, tmp_path, image_ids, languages):
    with pytest.raises(ValueError):
        preview_service.preview_dataset_all_formats(image_ids, tmp_path / "out", tag_languages=languages)
    preview_service.db_manager.get_image_metadata.assert_not_called()
    preview_service._get_export_reader.assert_not_called()
    preview_service.file_system_manager.copy_file.assert_not_called()
    assert not (tmp_path / "out").exists()


def test_preview_public_facade_uses_fresh_strict_scope(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from lorairo.public_api.export import preview_images_all_formats
    from lorairo.utils.config import get_runtime_configuration

    container = MagicMock()

    @contextmanager
    def scope():
        assert is_read_only()
        assert get_runtime_configuration() is not None
        yield container

    def activate(name):
        assert is_read_only()
        assert name == "synthetic"

    container.set_active_project.side_effect = activate
    monkeypatch.setattr("lorairo.services.service_container.service_container_scope", scope)
    result = preview_images_all_formats("synthetic", [1, 2], tmp_path / "out", 768, tag_languages=["ja"])
    assert result is container.dataset_export_service.preview_dataset_all_formats.return_value
    container.dataset_export_service.preview_dataset_all_formats.assert_called_once_with(
        [1, 2], tmp_path / "out", 768, tag_languages=["ja"]
    )
    assert not is_read_only()
