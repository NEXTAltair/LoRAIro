"""All-format export operation counts and legacy content compatibility."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lorairo.services.dataset_export_service import DatasetExportService
from lorairo.services.export_overlay import ExportOverlayPlan, ExportTagOverlay, ScopedOverlayRule

pytestmark = pytest.mark.unit


def make_service(tmp_path):
    db = MagicMock()
    db.get_image_metadata.side_effect = lambda image_id: {"id": image_id}
    db.get_image_annotations.side_effect = lambda image_id: {
        "tags": [{"tag": f"tag{image_id}"}],
        "captions": [{"caption": "synthetic caption"}] if image_id % 2 else [],
        "score_labels": [{"model": "scorer", "label": "good", "is_edited_manually": True}],
        "quality_summary": {"tier": "high", "votes": [{"model": "scorer", "label": "good"}]},
    }
    db.annotation_repo.get_merged_reader.return_value = None
    service = DatasetExportService(MagicMock(), MagicMock(), db, MagicMock())
    service._resolve_processed_image_path = MagicMock(
        side_effect=lambda image_id, resolution, **kwargs: tmp_path / f"source-{image_id}.webp"
    )
    return service


@pytest.mark.parametrize("count", [1, 500, 501, 1000, 10000])
@pytest.mark.parametrize("languages", [["canonical"], ["canonical", "ja"]])
def test_all_formats_single_pass_operation_counts(tmp_path, count, languages):
    service = make_service(tmp_path)
    service._write_export_text_files = MagicMock()
    service._build_export_tag_list = MagicMock(side_effect=lambda tags, *args: tags)
    high_water = {}

    def translate(tags, language, reader, cache):
        cache.update({tag: tag for tag in tags})
        high_water[language] = max(high_water.get(language, 0), len(cache))
        return tags

    service._translate_export_tag_list = MagicMock(side_effect=translate)
    report = service.export_dataset_all_formats(
        list(range(1, count + 1)), tmp_path / "out", tag_languages=languages
    )
    assert report.summary()["exported"] == count
    assert service.file_system_manager.copy_file.call_count == count * len(languages)
    assert service._resolve_processed_image_path.call_count == count
    assert service.db_manager.get_image_metadata.call_count == count
    assert service.db_manager.get_image_annotations.call_count == count
    assert service._build_export_tag_list.call_count == count
    assert service._translate_export_tag_list.call_count == count * len(languages)
    assert all(value <= min(count, 500) for value in high_water.values())
    print(
        json.dumps(
            {
                "images": count,
                "languages": len(languages),
                "copies": service.file_system_manager.copy_file.call_count,
                "metadata": service.db_manager.get_image_metadata.call_count,
                "annotations": service.db_manager.get_image_annotations.call_count,
                "path": service._resolve_processed_image_path.call_count,
                "canonical_tags": service._build_export_tag_list.call_count,
                "translation": service._translate_export_tag_list.call_count,
                "cache_high_water": high_water,
            },
            sort_keys=True,
        )
    )
    # These are service-call counts; no DB batch/query-count claim is made.
    assert service.db_manager.get_images_metadata_batch.call_count == 0
    assert service.db_manager.get_image_annotations_batch.call_count == 0


@pytest.mark.parametrize("languages", [["canonical"], ["canonical", "ja"]])
def test_all_formats_preserves_legacy_files_and_metadata(tmp_path, languages):
    service = make_service(tmp_path)
    for image_id in (1, 2):
        (tmp_path / f"source-{image_id}.webp").write_bytes(f"processed {image_id}".encode())
    service.file_system_manager.copy_file.side_effect = shutil.copyfile
    service._translate_export_tag_list = lambda tags, language, *args: [
        f"訳:{tag}" if language == "ja" else tag for tag in tags
    ]
    overlay = ExportOverlayPlan([ScopedOverlayRule(None, ExportTagOverlay(["trigger"], set(), {}))])
    old = tmp_path / "legacy"
    service.export_dataset_txt_format([1, 2], old, tag_languages=languages, overlay_plan=overlay)
    service.export_dataset_json_format([1, 2], old, tag_languages=languages, overlay_plan=overlay)
    assert service.file_system_manager.copy_file.call_count == 4 * len(languages)
    service.file_system_manager.copy_file.reset_mock()
    new = tmp_path / "all"
    report = service.export_dataset_all_formats([1, 2], new, tag_languages=languages, overlay_plan=overlay)
    assert report.summary()["ok"] is True
    assert service.file_system_manager.copy_file.call_count == 2 * len(languages)
    assert {path.relative_to(old) for path in old.rglob("*")} == {
        path.relative_to(new) for path in new.rglob("*")
    }
    for legacy in old.rglob("*"):
        if not legacy.is_file():
            continue
        current = new / legacy.relative_to(old)
        if legacy.name == "metadata.json":
            old_payload = {Path(key).name: value for key, value in json.loads(legacy.read_text()).items()}
            new_payload = {Path(key).name: value for key, value in json.loads(current.read_text()).items()}
            assert old_payload == new_payload
        else:
            assert legacy.read_bytes() == current.read_bytes()


def test_all_formats_empty_input_rejected(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        service.export_dataset_all_formats([], tmp_path / "out")
    service.file_system_manager.copy_file.assert_not_called()


def test_all_formats_text_failure_retains_json_result(tmp_path):
    service = make_service(tmp_path)
    service._write_export_text_files = MagicMock(side_effect=OSError("text write failed"))
    report = service.export_dataset_all_formats([1], tmp_path / "out")
    summary = report.summary()
    assert summary["ok"] is False
    assert summary["failed_ids"] == [1]
    assert summary["error_details"][0]["completed_formats"] == ["json"]
    assert len(json.loads((tmp_path / "out" / "metadata.json").read_text())) == 1
    assert service.file_system_manager.copy_file.call_count == 1


def test_public_all_formats_facade_routes_exact_ids(tmp_path, monkeypatch):
    from lorairo.public_api.export import export_images_all_formats

    service = make_service(tmp_path)
    service._write_export_text_files = MagicMock()
    container = MagicMock()
    container.dataset_export_service = service
    monkeypatch.setattr("lorairo.public_api.export.ServiceContainer", lambda: container)
    report = export_images_all_formats("synthetic", [1, 2], tmp_path / "out")
    container.set_active_project.assert_called_once_with("synthetic")
    assert report.summary()["exported_ids"] == [1, 2]
    assert service.db_manager.get_image_metadata.call_count == 2
