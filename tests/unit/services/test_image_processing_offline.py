"""Real offline resize/filesystem behavior with isolated registered-image boundaries."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from lorairo.filesystem import FileSystemManager
from lorairo.services.image_processing_service import ImageProcessingService


@pytest.fixture
def offline_service(tmp_path, monkeypatch):
    fsm = FileSystemManager()
    fsm.initialize(tmp_path / "project")
    originals = {}
    for image_id in (1, 2):
        source = tmp_path / f"original-{image_id}.png"
        Image.new("RGB", (96, 64), color=(image_id * 50, 90, 130)).save(source)
        originals[image_id] = {
            "id": image_id,
            "stored_image_path": str(source),
            "has_alpha": False,
            "mode": "RGB",
        }
    db = MagicMock()
    db.get_image_metadata.side_effect = originals.get
    records = {}
    db.image_repo.get_processed_image.side_effect = lambda image_id, **kwargs: [
        row for (parent_id, _resolution), row in records.items() if parent_id == image_id
    ]

    def register(image_id, path, metadata):
        row = {**metadata, "id": 100 + image_id, "stored_image_path": str(path)}
        records[image_id, max(row["width"], row["height"])] = row
        return row["id"]

    db.register_processed_image.side_effect = register
    config = MagicMock()
    config.get_image_processing_config.return_value = {
        "upscaler": "MUST-NOT-RUN",
        "target_resolution": 1024,
    }
    monkeypatch.setattr("lorairo.database.db_core.resolve_stored_path", Path)
    monkeypatch.setattr(
        "lorairo.image_transforms.upscaler.Upscaler.upscale_image",
        MagicMock(side_effect=AssertionError("upscaler invoked")),
    )
    service = ImageProcessingService(config, fsm, db)
    return service, originals, records


def test_offline_exact_ids_resolution_and_original_preservation(offline_service):
    service, originals, records = offline_service
    original_bytes = {
        image_id: Path(data["stored_image_path"]).read_bytes() for image_id, data in originals.items()
    }
    outcomes = service.process_image_ids_offline([1], 256)
    assert outcomes[0].status == "success"
    assert max(Image.open(outcomes[0].output_path).size) == 256
    assert (2, 256) not in records
    assert all(
        Path(originals[image_id]["stored_image_path"]).read_bytes() == data
        for image_id, data in original_bytes.items()
    )
    service.idm.register_original_image.assert_not_called()
    service.idm.detect_duplicate_image.assert_not_called()


def test_offline_skip_repair_and_explicit_rebuild(offline_service):
    service, _originals, records = offline_service
    first = service.process_image_ids_offline([1], 256)[0]
    output = Path(first.output_path)
    before = output.stat().st_mtime_ns
    second = service.process_image_ids_offline([1], 256)[0]
    assert second.status == "skipped"
    assert output.stat().st_mtime_ns == before
    output.write_bytes(b"corrupt")
    repaired = service.process_image_ids_offline([1], 256)[0]
    assert repaired.status == "success"
    assert repaired.processed_image_id == first.processed_image_id
    with Image.open(output) as image:
        image.verify()
    output.unlink()
    assert service.process_image_ids_offline([1], 256)[0].status == "success"
    assert service.process_image_ids_offline([1], 256, rebuild=True)[0].status == "success"
    assert len(records) == 1
    assert service.idm.register_processed_image.call_count == 1


def test_offline_partial_failure_and_missing_id(offline_service):
    service, originals, _records = offline_service
    Path(originals[2]["stored_image_path"]).unlink()
    outcomes = service.process_image_ids_offline([1, 2, 999], 256)
    assert [item.status for item in outcomes] == ["success", "failed", "failed"]
    assert "original_file_missing" in outcomes[1].reason
    assert "image_not_found" in outcomes[2].reason


def test_offline_empty_and_invalid_parameters(offline_service):
    service, _originals, _records = offline_service
    assert service.process_image_ids_offline([], 256) == []
    with pytest.raises(ValueError):
        service.process_image_ids_offline([0], 256)
    with pytest.raises(ValueError):
        service.process_image_ids_offline([1], 17)


def test_offline_does_not_skip_nearby_resolution(offline_service):
    service, _originals, _records = offline_service
    first = service.process_image_ids_offline([1], 256)[0]
    second = service.process_image_ids_offline([1], 288)[0]
    assert second.status == "success"
    assert second.output_path != first.output_path
    assert max(Image.open(second.output_path).size) == 288


def test_offline_refuses_original_as_processed_output(offline_service):
    service, originals, records = offline_service
    original = Path(originals[1]["stored_image_path"])
    before = original.read_bytes()
    records[1, 256] = {"id": 5, "width": 256, "height": 256, "stored_image_path": str(original)}
    outcome = service.process_image_ids_offline([1], 256, rebuild=True)[0]
    assert outcome.status == "failed"
    assert "unsafe_processed_path" in outcome.reason
    assert original.read_bytes() == before


def test_offline_failed_registration_is_not_success(offline_service):
    service, _originals, _records = offline_service
    service.idm.register_processed_image.side_effect = None
    service.idm.register_processed_image.return_value = None
    outcome = service.process_image_ids_offline([1], 256)[0]
    assert outcome.status == "failed"
    assert "unlinked output remains" in outcome.reason


def test_offline_refuses_inconsistent_rebuild_dimensions(offline_service):
    service, _originals, records = offline_service
    first = service.process_image_ids_offline([1], 256)[0]
    output = Path(first.output_path)
    before = output.read_bytes()
    records[1, 256]["height"] = 32
    outcome = service.process_image_ids_offline([1], 256, rebuild=True)[0]
    assert outcome.status == "failed"
    assert "processed_metadata_mismatch" in outcome.reason
    assert output.read_bytes() == before


def test_offline_duplicate_ids_are_processed_once(offline_service):
    service, _originals, _records = offline_service
    outcomes = service.process_image_ids_offline([1, 1], 256)
    assert len(outcomes) == 1
    assert service.idm.register_processed_image.call_count == 1


@pytest.mark.parametrize("size", [(64, 96), (160, 64), (128, 128)])
def test_offline_aspect_ratios_obey_long_side(offline_service, size):
    service, originals, _records = offline_service
    source = Path(originals[1]["stored_image_path"])
    Image.new("RGB", size, color=(20, 80, 140)).save(source)
    outcome = service.process_image_ids_offline([1], 288)[0]
    assert outcome.status == "success"
    with Image.open(outcome.output_path) as output:
        assert max(output.size) == 288
        assert all(dimension > 0 and dimension % 32 == 0 for dimension in output.size)


def test_offline_same_basename_distinct_ids_do_not_overwrite(offline_service, tmp_path):
    service, originals, _records = offline_service
    for image_id in (1, 2):
        path = tmp_path / str(image_id) / "same-parent" / "same.png"
        path.parent.mkdir(parents=True)
        Image.new("RGB", (96, 64), color=(image_id * 80, 20, 30)).save(path)
        originals[image_id]["stored_image_path"] = str(path)
    outcomes = service.process_image_ids_offline([1, 2], 256)
    assert [outcome.status for outcome in outcomes] == ["success", "success"]
    assert outcomes[0].output_path != outcomes[1].output_path
    first_bytes = Path(outcomes[0].output_path).read_bytes()
    assert service.process_image_ids_offline([2], 256, rebuild=True)[0].status == "success"
    assert Path(outcomes[0].output_path).read_bytes() == first_bytes


def test_offline_prefers_valid_exact_row_after_broken_exact_row(offline_service):
    service, _originals, records = offline_service
    first = service.process_image_ids_offline([1], 256)[0]
    valid = records[1, 256]
    broken = {
        **valid,
        "id": 999,
        "stored_image_path": str(Path(first.output_path).with_name("missing.webp")),
    }
    service.idm.image_repo.get_processed_image.side_effect = None
    service.idm.image_repo.get_processed_image.return_value = [broken, valid]
    outcome = service.process_image_ids_offline([1], 256)[0]
    assert outcome.status == "skipped"
    assert outcome.processed_image_id == first.processed_image_id
    assert service.idm.register_processed_image.call_count == 1


def test_offline_checks_new_destination_before_save(offline_service, tmp_path, monkeypatch):
    service, _originals, _records = offline_service
    monkeypatch.setattr(service.fsm, "get_resolution_dir", lambda resolution: tmp_path / "outside")
    save = MagicMock()
    monkeypatch.setattr(service.fsm, "save_processed_image", save)
    outcome = service.process_image_ids_offline([1], 256)[0]
    assert outcome.status == "failed"
    assert "unsafe_processed_path" in outcome.reason
    save.assert_not_called()


def test_offline_rejects_wrong_generated_size(offline_service, monkeypatch):
    service, _originals, _records = offline_service
    monkeypatch.setattr(
        "lorairo.image_transforms.image_processor.ImageProcessingManager.process_image",
        lambda *args, **kwargs: (Image.new("RGB", (32, 32)), {}),
    )
    outcome = service.process_image_ids_offline([1], 256)[0]
    assert outcome.status == "failed"
    assert "resize_resolution_mismatch" in outcome.reason
    service.idm.register_processed_image.assert_not_called()


@pytest.mark.parametrize(
    "changed", [{"upscaler_used": "RealESRGAN"}, {"mode": "RGBA"}, {"has_alpha": True}]
)
def test_offline_rebuild_preserves_incompatible_provenance(offline_service, changed):
    service, _originals, records = offline_service
    first = service.process_image_ids_offline([1], 256)[0]
    output = Path(first.output_path)
    before = output.read_bytes()
    records[1, 256].update(changed)
    row_before = dict(records[1, 256])
    outcome = service.process_image_ids_offline([1], 256, rebuild=True)[0]
    assert outcome.status == "failed"
    assert "processed_provenance_mismatch" in outcome.reason
    assert "choose another resolution" in outcome.reason
    assert output.read_bytes() == before
    assert records[1, 256] == row_before


def test_offline_valid_upscaled_file_can_be_skipped(offline_service):
    service, _originals, records = offline_service
    service.process_image_ids_offline([1], 256)
    records[1, 256]["upscaler_used"] = "RealESRGAN"
    assert service.process_image_ids_offline([1], 256)[0].status == "skipped"
