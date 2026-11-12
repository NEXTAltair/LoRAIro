"""crop_detect_provider のユニットテスト (Issue #1340 / ADR 0110)。

検出器は fake に差し替え、実 SQLite + 実ファイルシステムで「親画像 → 検出 → 候補」の
変換 (クラス → 検出器、閾値、余白のクランプ、最小長辺、既存クロップとの IoU、0 件、
EXIF 回転済み画像の座標系、画像を開けない場合) と一括処理への配線を検証する。
"""

import importlib.util
import random
import sys
import types
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from PIL import Image

from lorairo.database.db_core import resolve_stored_path
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.domain.crop_rect_provider import CropRectCandidate, CropRectNotice
from lorairo.domain.crop_request import CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.services.crop_batch_service import run_crop_batch
from lorairo.services.crop_detect_provider import (
    DETECTOR_CLASSES,
    DetectedBox,
    DetectionSettings,
    DetectorCropRectProvider,
    LibObjectDetector,
    ObjectDetectionError,
    padded_rect,
    rect_iou,
)

pytestmark = pytest.mark.unit

PERSON = DETECTOR_CLASSES["person"]


@dataclass
class _Call:
    size: tuple[int, int]
    detector: str
    class_name: str
    min_score: float
    nms_iou: float
    pixel: tuple[int, ...]


@dataclass
class _FakeDetector:
    """呼び出しを記録し、画像 ID 順に用意した結果 (または例外) を返す fake 検出器。"""

    results: list[Sequence[DetectedBox] | ObjectDetectionError]
    calls: list[_Call] = field(default_factory=list)

    def detect(
        self, image: Image.Image, *, detector: str, class_name: str, min_score: float, nms_iou: float
    ) -> Sequence[DetectedBox]:
        self.calls.append(
            _Call(image.size, detector, class_name, min_score, nms_iou, tuple(image.getpixel((5, 5))))
        )
        result = self.results[len(self.calls) - 1]
        if isinstance(result, ObjectDetectionError):
            raise result
        return result


def _register(db: ImageDatabaseManager, fsm: FileSystemManager, path: Path) -> int:
    registered = db.register_original_image(path, fsm)
    assert registered is not None
    return registered[0]


@pytest.fixture
def parent_id(test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager, tmp_path: Path) -> int:
    """ノイズ画像 (400x300) を親として登録する。"""
    source = tmp_path / "noise_parent.png"
    Image.frombytes("RGB", (400, 300), random.Random(1488).randbytes(400 * 300 * 3)).save(source)
    return _register(test_db_manager, fs_manager, source)


def _provider(
    db: ImageDatabaseManager, detector: _FakeDetector, **settings: float
) -> DetectorCropRectProvider:
    params: dict[str, float] = {"min_score": PERSON.default_min_score, "min_long_edge": 1, **settings}
    return DetectorCropRectProvider(
        PERSON,
        DetectionSettings(
            min_score=params["min_score"],
            padding=params.get("padding", 0.0),
            nms_iou=params.get("nms_iou", 0.5),
            min_long_edge=int(params["min_long_edge"]),
            existing_iou=params.get("existing_iou", 0.7),
        ),
        db_manager=db,
        detector=detector,
    )


def test_class_maps_to_detector_and_lib_receives_report_floor_and_nms(
    parent_id: int, test_db_manager: ImageDatabaseManager
) -> None:
    detector = _FakeDetector([[DetectedBox(0.9, (10.0, 20.0, 110.0, 220.0))]])

    items = _provider(test_db_manager, detector, nms_iou=0.45).candidates_for(parent_id)

    call = detector.calls[0]
    assert (call.detector, call.class_name, call.size) == ("person_detect_v1.3_s", "person", (400, 300))
    assert call.min_score == pytest.approx(0.162)
    assert call.nms_iou == 0.45
    assert items == [
        CropRectCandidate(rect=CropRect(10, 20, 100, 200), origin="person_detect_v1.3_s", score=0.9)
    ]


def test_padding_expands_each_side_and_clamps_to_image_edges(
    parent_id: int, test_db_manager: ImageDatabaseManager
) -> None:
    detector = _FakeDetector(
        [
            [
                DetectedBox(0.9, (10.4, 20.6, 110.2, 220.5)),
                DetectedBox(0.8, (350.0, 250.0, 400.0, 300.0)),
                DetectedBox(0.7, (150.0, 100.0, 250.0, 150.0)),
            ]
        ]
    )

    items = _provider(test_db_manager, detector, padding=0.2).candidates_for(parent_id)

    # 1: w=99.8 -> pad 19.96 / h=199.9 -> pad 39.98。左上は 0 にクランプ、右下は切り上げ
    # 2: 右下端の矩形は画像端 (400, 300) でクランプ
    # 3: 内側の矩形は 4 辺とも 20%/10px ずつ広がる
    assert [item.rect for item in items if isinstance(item, CropRectCandidate)] == [
        CropRect(0, 0, 131, 261),
        CropRect(340, 240, 60, 60),
        CropRect(130, 90, 140, 70),
    ]


@pytest.mark.parametrize(
    ("bbox", "padding", "size", "expected"),
    [
        ((0.0, 0.0, 10.0, 10.0), 0.0, (10, 10), CropRect(0, 0, 10, 10)),
        ((2.5, 3.5, 7.5, 8.5), 0.0, (10, 10), CropRect(2, 3, 6, 6)),
        ((2.0, 2.0, 8.0, 8.0), 1.0, (10, 10), CropRect(0, 0, 10, 10)),
        ((4.0, 4.0, 6.0, 6.0), 0.5, (10, 10), CropRect(3, 3, 4, 4)),
    ],
)
def test_padded_rect_contains_box_and_stays_in_image(
    bbox: tuple[float, float, float, float], padding: float, size: tuple[int, int], expected: CropRect
) -> None:
    assert padded_rect(bbox, padding, size) == expected


def test_rect_iou_values() -> None:
    a = CropRect(0, 0, 10, 10)
    assert rect_iou(a, a) == 1.0
    assert rect_iou(a, CropRect(5, 0, 10, 10)) == pytest.approx(50 / 150)
    assert rect_iou(a, CropRect(10, 0, 10, 10)) == 0.0


def test_below_min_score_and_min_long_edge_are_skipped_with_reasons(
    parent_id: int, test_db_manager: ImageDatabaseManager
) -> None:
    detector = _FakeDetector(
        [
            [
                DetectedBox(0.9, (0.0, 0.0, 200.0, 100.0)),
                DetectedBox(0.39, (200.0, 0.0, 400.0, 100.0)),
                DetectedBox(0.8, (0.0, 200.0, 99.0, 250.0)),
                DetectedBox(0.8, (200.0, 150.0, 300.0, 300.0)),
            ]
        ]
    )

    items = _provider(test_db_manager, detector, min_score=0.4, min_long_edge=100).candidates_for(parent_id)

    assert detector.calls[0].min_score == pytest.approx(0.2)
    reasons = [(item.skip_reason, item.score) for item in items if isinstance(item, CropRectCandidate)]
    assert reasons == [
        (None, 0.9),
        ("below_min_score", 0.39),
        ("below_min_long_edge", 0.8),
        (None, 0.8),
    ]
    skipped = [item for item in items if isinstance(item, CropRectCandidate) and item.skip_reason]
    assert skipped[0].skip_message == "score 0.390 is below min_score 0.400"
    assert skipped[1].skip_message == "long edge 99px is below min_long_edge 100px"


def test_overlap_with_existing_crop_is_skipped_but_same_rect_and_origin_passes_through(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    from lorairo.domain.crop_request import CropCreateRequest
    from lorairo.services.crop_service import create_crop_image

    for rect, origin in (
        (CropRect(0, 0, 100, 100), "manual"),
        (CropRect(200, 0, 100, 100), "person_detect_v1.3_s"),
    ):
        create_crop_image(
            CropCreateRequest(parent_image_id=parent_id, rect=rect, origin=origin),
            db_manager=test_db_manager,
            fsm=fs_manager,
        )
    detector = _FakeDetector(
        [
            [
                # 既存 manual (0,0,100,100) と IoU = 90*100 / (100*100 + 90*100 - 90*100) = 0.9
                DetectedBox(0.9, (0.0, 0.0, 90.0, 100.0)),
                # 既存の同じ矩形・同じ由来は一括処理が already_exists にするので素通し
                DetectedBox(0.8, (200.0, 0.0, 300.0, 100.0)),
                # 既存 manual と IoU = 75*100 / (100*100 + 100*100 - 75*100) = 0.6 (< 0.7) は作成対象
                DetectedBox(0.7, (0.0, 25.0, 100.0, 125.0)),
            ]
        ]
    )

    items = _provider(test_db_manager, detector).candidates_for(parent_id)

    assert [item.skip_reason for item in items if isinstance(item, CropRectCandidate)] == [
        "overlaps_existing_crop",
        None,
        None,
    ]
    first = items[0]
    assert isinstance(first, CropRectCandidate)
    assert first.skip_message == "IoU 0.900 with an existing crop (manual) is at least 0.700"


def test_no_detection_is_a_skipped_notice(parent_id: int, test_db_manager: ImageDatabaseManager) -> None:
    items = _provider(test_db_manager, _FakeDetector([[]])).candidates_for(parent_id)

    assert items == [
        CropRectNotice(
            status="skipped",
            reason="no_detection",
            message="No person detected (score >= 0.162)",
            origin="person_detect_v1.3_s",
        )
    ]


def test_exif_rotated_parent_is_detected_in_display_orientation(
    test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager, tmp_path: Path
) -> None:
    """EXIF orientation=6 (90 度回転) の画像は表示向き (縦長) の画素で検出器に渡す。"""
    raw = Image.new("RGB", (300, 200), (0, 0, 255))
    raw.paste((255, 0, 0), (0, 0, 150, 200))  # 保存画素の左半分が赤
    exif = Image.Exif()
    exif[0x0112] = 6
    path = tmp_path / "rotated.jpg"
    raw.save(path, format="JPEG", quality=100, subsampling=0, exif=exif.tobytes())
    image_id = _register(test_db_manager, fs_manager, path)
    detector = _FakeDetector([[DetectedBox(0.9, (150.0, 250.0, 200.0, 300.0))]])

    items = _provider(test_db_manager, detector, padding=0.5).candidates_for(image_id)

    call = detector.calls[0]
    # 表示向きは 200x300。orientation 6 は時計回り 90 度なので、保存画素の左 (赤) が上に来る
    assert call.size == (200, 300)
    assert call.pixel[0] > 200 and call.pixel[2] < 50
    assert items == [
        CropRectCandidate(rect=CropRect(125, 225, 75, 75), origin="person_detect_v1.3_s", score=0.9)
    ]


def test_unreadable_or_unregistered_parent_is_a_failed_notice(
    parent_id: int, test_db_manager: ImageDatabaseManager
) -> None:
    metadata = test_db_manager.get_image_metadata(parent_id)
    assert metadata is not None
    resolve_stored_path(str(metadata["stored_image_path"])).write_bytes(b"not an image")
    detector = _FakeDetector([])
    provider = _provider(test_db_manager, detector)

    unreadable = provider.candidates_for(parent_id)
    missing = provider.candidates_for(987654)

    assert [(n.status, n.reason) for n in unreadable if isinstance(n, CropRectNotice)] == [
        ("failed", "io_error")
    ]
    assert [(n.status, n.reason) for n in missing if isinstance(n, CropRectNotice)] == [
        ("failed", "parent_not_found")
    ]
    assert detector.calls == []


def test_detector_unavailable_is_not_retried_but_detection_failure_is_per_image(
    parent_id: int, test_db_manager: ImageDatabaseManager
) -> None:
    failing = _FakeDetector([ObjectDetectionError("detection_failed", "boom"), []])
    provider = _provider(test_db_manager, failing)
    assert [n.reason for n in provider.candidates_for(parent_id) if isinstance(n, CropRectNotice)] == [
        "detection_failed"
    ]
    assert [n.reason for n in provider.candidates_for(parent_id) if isinstance(n, CropRectNotice)] == [
        "no_detection"
    ]

    unavailable = _FakeDetector([ObjectDetectionError("detector_unavailable", "no network")])
    provider = _provider(test_db_manager, unavailable)
    first = provider.candidates_for(parent_id)
    second = provider.candidates_for(parent_id)

    assert (
        first
        == second
        == [
            CropRectNotice(
                status="failed",
                reason="detector_unavailable",
                message="no network",
                origin="person_detect_v1.3_s",
            )
        ]
    )
    assert len(unavailable.calls) == 1


def test_run_crop_batch_reports_every_box_and_rerun_is_idempotent(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    boxes = [
        DetectedBox(0.9, (0.0, 0.0, 120.0, 120.0)),
        DetectedBox(0.2, (200.0, 0.0, 320.0, 120.0)),
        DetectedBox(0.8, (300.0, 200.0, 310.0, 210.0)),
    ]
    detector = _FakeDetector([boxes, boxes, []])
    provider = _provider(test_db_manager, detector, min_long_edge=50)

    first = run_crop_batch(provider, [parent_id], db_manager=test_db_manager, fsm=fs_manager)
    second = run_crop_batch(provider, [parent_id], db_manager=test_db_manager, fsm=fs_manager)
    empty = run_crop_batch(provider, [parent_id], db_manager=test_db_manager, fsm=fs_manager)

    assert [(o.status, o.reason) for o in first] == [
        ("created", None),
        ("skipped", "below_min_score"),
        ("skipped", "below_min_long_edge"),
    ]
    assert [(o.status, o.reason) for o in second] == [
        ("skipped", "already_exists"),
        ("skipped", "below_min_score"),
        ("skipped", "below_min_long_edge"),
    ]
    assert second[0].child_image_id == first[0].child_image_id
    assert [(o.status, o.reason, o.candidate, o.origin) for o in empty] == [
        ("skipped", "no_detection", None, "person_detect_v1.3_s")
    ]
    children = test_db_manager.get_crop_children(parent_id)
    assert [(c.x, c.y, c.width, c.height, c.origin) for c in children] == [
        (0, 0, 120, 120, "person_detect_v1.3_s")
    ]


class _AnnotatorError(Exception):
    pass


class _ModelLoadError(_AnnotatorError):
    pass


class _ModelNotFoundError(_AnnotatorError):
    pass


class _OutOfMemoryError(_AnnotatorError):
    pass


class _ModelExecutionError(_AnnotatorError):
    pass


@dataclass
class _LibDetection:
    class_name: str
    score: float
    bbox: tuple[float, float, float, float]


@dataclass
class _LibImageDetections:
    detections: tuple[_LibDetection, ...]


@pytest.fixture
def fake_lib(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """conftest の image_annotator_lib mock に detect_objects / release_detectors と例外型を差し込む。"""
    state: dict[str, object] = {"raise": None, "released": None, "kwargs": None}
    errors = types.ModuleType("image_annotator_lib.exceptions.errors")
    for name, cls in (
        ("AnnotatorError", _AnnotatorError),
        ("ModelLoadError", _ModelLoadError),
        ("ModelNotFoundError", _ModelNotFoundError),
        ("OutOfMemoryError", _OutOfMemoryError),
    ):
        setattr(errors, name, cls)
    monkeypatch.setitem(sys.modules, "image_annotator_lib.exceptions.errors", errors)

    def detect_objects(
        images: Sequence[Image.Image], detector: str, **kwargs: float | list[str]
    ) -> list[_LibImageDetections]:
        state["kwargs"] = {"count": len(images), "detector": detector, **kwargs}
        error = state["raise"]
        if isinstance(error, Exception):
            raise error
        return [_LibImageDetections((_LibDetection("person", 0.5, (1.0, 2.0, 3.0, 4.0)),))]

    def release_detectors(names: list[str]) -> int:
        state["released"] = names
        return len(names)

    lib = sys.modules["image_annotator_lib"]
    monkeypatch.setattr(lib, "detect_objects", detect_objects, raising=False)
    monkeypatch.setattr(lib, "release_detectors", release_detectors, raising=False)
    return state


def test_lib_detector_passes_parameters_and_releases_used_sessions(fake_lib: dict[str, object]) -> None:
    detector = LibObjectDetector()
    detector.release()
    assert fake_lib["released"] is None  # 未使用なら lib を呼ばない

    boxes = detector.detect(
        Image.new("RGB", (8, 8)),
        detector="face_detect_v1.4_s",
        class_name="face",
        min_score=0.1,
        nms_iou=0.4,
    )
    detector.release()

    assert boxes == [DetectedBox(0.5, (1.0, 2.0, 3.0, 4.0))]
    assert fake_lib["kwargs"] == {
        "count": 1,
        "detector": "face_detect_v1.4_s",
        "classes": ["face"],
        "min_score": 0.1,
        "nms_iou": 0.4,
    }
    assert fake_lib["released"] == ["face_detect_v1.4_s"]


@pytest.mark.parametrize(
    ("error", "reason", "message"),
    [
        (
            _ModelLoadError("download failed at /secret/path"),
            "detector_unavailable",
            "Detector 'person_detect_v1.3_s' could not be loaded. The model is downloaded from "
            "Hugging Face Hub on first use; check network access and retry.",
        ),
        (_ModelNotFoundError("x"), "detector_unavailable", None),
        (
            _OutOfMemoryError("oom"),
            "detection_failed",
            "Detector 'person_detect_v1.3_s' ran out of memory.",
        ),
        (
            _ModelExecutionError("/secret/path"),
            "detection_failed",
            "Detector 'person_detect_v1.3_s' failed (_ModelExecutionError).",
        ),
    ],
)
def test_lib_errors_become_detection_errors_without_internal_details(
    fake_lib: dict[str, object], error: Exception, reason: str, message: str | None
) -> None:
    fake_lib["raise"] = error

    with pytest.raises(ObjectDetectionError) as raised:
        LibObjectDetector().detect(
            Image.new("RGB", (8, 8)),
            detector="person_detect_v1.3_s",
            class_name="person",
            min_score=0.1,
            nms_iou=0.5,
        )

    assert raised.value.reason == reason
    if message is not None:
        assert raised.value.message == message
    assert "/secret/path" not in raised.value.message


def test_detector_table_matches_lib_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """LoRAIro 側の対応表 (クラス → 検出器・既定閾値) が lib の BUILTIN_DETECTORS と一致する。

    conftest が image_annotator_lib を mock しているため、純粋な dataclass だけの
    detection/types.py と catalog.py をファイルから直接読む。
    """
    root = Path(__file__).resolve().parents[3]
    detection_dir = root / "local_packages/image-annotator-lib/src/image_annotator_lib/detection"
    if not (detection_dir / "catalog.py").exists():
        pytest.skip("image-annotator-lib submodule is not checked out")
    package = types.ModuleType("image_annotator_lib.detection")
    package.__path__ = [str(detection_dir)]
    monkeypatch.setitem(sys.modules, "image_annotator_lib.detection", package)
    loaded: dict[str, types.ModuleType] = {}
    for name in ("types", "catalog"):
        spec = importlib.util.spec_from_file_location(
            f"image_annotator_lib.detection.{name}", detection_dir / f"{name}.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        loaded[name] = module

    catalog = loaded["catalog"].BUILTIN_DETECTORS
    for spec_row in DETECTOR_CLASSES.values():
        info = catalog[spec_row.detector]
        assert info.classes == (spec_row.class_name,)
        assert info.default_min_score == spec_row.default_min_score
        assert info.license == "MIT"
    assert set(catalog) == {row.detector for row in DETECTOR_CLASSES.values()}
