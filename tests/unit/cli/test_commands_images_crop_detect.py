"""``images crop-detect`` コマンドのユニットテスト (Issue #1340 / ADR 0110)。

実 SQLite の ImageDatabaseManager と実 FileSystemManager を container 経由で注入し、
検出器だけ fake に差し替えて「親画像 ID → 検出 → 一括作成 → JSONL 出力 / 終了コード」の
配線を検証する。
"""

import json
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from PIL import Image
from typer.testing import CliRunner

from lorairo.cli.main import app
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.filesystem import FileSystemManager
from lorairo.services.crop_detect_provider import DetectedBox, ObjectDetectionError

runner = CliRunner()

pytestmark = pytest.mark.unit


class _FakeLibDetector:
    """LibObjectDetector の代わりに CLI へ差し込む fake。"""

    boxes: Sequence[DetectedBox] = ()
    error: ObjectDetectionError | None = None
    calls: ClassVar[list[dict[str, Any]]] = []
    released: ClassVar[list[bool]] = []

    def detect(
        self, image: Image.Image, *, detector: str, class_name: str, min_score: float, nms_iou: float
    ) -> Sequence[DetectedBox]:
        type(self).calls.append(
            {
                "size": image.size,
                "detector": detector,
                "class_name": class_name,
                "min_score": min_score,
                "nms_iou": nms_iou,
            }
        )
        if self.error is not None:
            raise self.error
        return self.boxes

    def release(self) -> None:
        type(self).released.append(True)


@pytest.fixture
def fake_detector(monkeypatch: pytest.MonkeyPatch) -> type[_FakeLibDetector]:
    detector_cls = type("FakeDetector", (_FakeLibDetector,), {"calls": [], "released": []})
    monkeypatch.setattr("lorairo.cli.commands.images.LibObjectDetector", detector_cls)
    return detector_cls


@pytest.fixture
def parent_id(
    monkeypatch: pytest.MonkeyPatch,
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """ノイズ画像 (400x300) を親として登録し、CLI の container を実オブジェクトへ差し替える。"""
    source = tmp_path / "noise_parent.png"
    Image.frombytes("RGB", (400, 300), random.Random(1488).randbytes(400 * 300 * 3)).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None

    container = MagicMock()
    container.db_manager = test_db_manager
    container.file_system_manager = fs_manager
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container", MagicMock(return_value=container)
    )
    return registered[0]


def _jsonl(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _invoke(*extra: str, json_mode: bool = True) -> Any:
    args = ["--json"] if json_mode else ["--no-json"]
    return runner.invoke(app, [*args, "images", "crop-detect", "--project", "proj", *extra])


def test_creates_crops_with_detector_origin_and_reports_skips(
    parent_id: int, fake_detector: type[_FakeLibDetector], test_db_manager: ImageDatabaseManager
) -> None:
    fake_detector.boxes = (
        DetectedBox(0.9, (100.0, 50.0, 300.0, 250.0)),
        DetectedBox(0.2, (0.0, 0.0, 300.0, 300.0)),
        DetectedBox(0.8, (380.0, 280.0, 400.0, 300.0)),
    )

    result = _invoke("--class", "face", "--image-ids", str(parent_id), "--min-long-edge", "100")

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    items = [row for row in rows if row["kind"] == "item"]
    # padding 0.1: (100,50,300,250) -> (80,30,320,270)
    assert [
        (i["status"], i["reason"], i["x"], i["y"], i["width"], i["height"], i["origin"], i["score"])
        for i in items
    ] == [
        ("created", None, 80, 30, 240, 240, "face_detect_v1.4_s", 0.9),
        ("skipped", "below_min_score", 0, 0, 330, 300, "face_detect_v1.4_s", 0.2),
        ("skipped", "below_min_long_edge", 378, 278, 22, 22, "face_detect_v1.4_s", 0.8),
    ]
    assert all(i["line"] is None for i in items)
    call = fake_detector.calls[0]
    assert (call["detector"], call["class_name"], call["nms_iou"]) == ("face_detect_v1.4_s", "face", 0.5)
    assert call["min_score"] == pytest.approx(0.307 * 0.5)
    terminal = rows[-1]
    assert (terminal["ok"], terminal["status"], terminal["created"], terminal["skipped"]) == (
        True,
        "success",
        1,
        2,
    )
    assert terminal["created_ids"] == [items[0]["child_image_id"]]
    assert terminal["failed_lines"] == []
    children = test_db_manager.get_crop_children(parent_id)
    assert [(c.x, c.y, c.width, c.height, c.origin) for c in children] == [
        (80, 30, 240, 240, "face_detect_v1.4_s")
    ]
    assert fake_detector.released == [True]


def test_rerun_reports_already_exists(
    parent_id: int, fake_detector: type[_FakeLibDetector], test_db_manager: ImageDatabaseManager
) -> None:
    fake_detector.boxes = (DetectedBox(0.9, (50.0, 20.0, 350.0, 280.0)),)
    assert _invoke("--class", "person", "--image-ids", str(parent_id)).exit_code == 0

    result = _invoke("--class", "person", "--image-ids", str(parent_id))

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    assert (rows[0]["status"], rows[0]["reason"], rows[0]["origin"]) == (
        "skipped",
        "already_exists",
        "person_detect_v1.3_s",
    )
    assert len(test_db_manager.get_crop_children(parent_id)) == 1


def test_no_detection_is_skipped_with_null_rectangle(
    parent_id: int, fake_detector: type[_FakeLibDetector]
) -> None:
    result = _invoke("--class", "head", "--image-ids", str(parent_id))

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    assert rows[0]["status"] == "skipped"
    assert rows[0]["reason"] == "no_detection"
    assert (rows[0]["x"], rows[0]["origin"], rows[0]["parent_image_id"]) == (
        None,
        "head_detect_v2.0_s",
        parent_id,
    )
    assert (rows[-1]["ok"], rows[-1]["skipped"], rows[-1]["total"]) == (True, 1, 1)


def test_partial_success_exits_3_when_a_parent_is_missing(
    parent_id: int, fake_detector: type[_FakeLibDetector]
) -> None:
    fake_detector.boxes = (DetectedBox(0.9, (50.0, 20.0, 350.0, 280.0)),)

    result = _invoke("--class", "person", "--image-ids", f"{parent_id},987654")

    assert result.exit_code == 3, result.output
    rows = _jsonl(result.stdout)
    items = [row for row in rows if row["kind"] == "item"]
    assert [(i["parent_image_id"], i["status"], i["reason"]) for i in items] == [
        (parent_id, "created", None),
        (987654, "failed", "parent_not_found"),
    ]
    assert (rows[-1]["ok"], rows[-1]["status"]) == (False, "partial_success")


def test_detector_unavailable_fails_every_parent_and_exits_1(
    parent_id: int, fake_detector: type[_FakeLibDetector]
) -> None:
    fake_detector.error = ObjectDetectionError("detector_unavailable", "Detector could not be loaded.")

    result = _invoke("--class", "person", "--image-ids", f"{parent_id}", json_mode=False)

    assert result.exit_code == 1, result.output
    assert "detector_unavailable" in result.stdout
    assert "Detector could not be loaded." in result.stdout
    assert "line=" not in result.stdout


def test_dry_run_writes_nothing_and_opens_project_read_only(
    parent_id: int, fake_detector: type[_FakeLibDetector], test_db_manager: ImageDatabaseManager
) -> None:
    from lorairo.cli.commands import images
    from lorairo.database.access_policy import is_read_only

    container = images.get_service_container()
    observed: list[bool] = []
    container.set_active_project.side_effect = lambda _project: observed.append(is_read_only())
    fake_detector.boxes = (DetectedBox(0.9, (50.0, 20.0, 350.0, 280.0)),)

    result = _invoke("--class", "person", "--image-ids", str(parent_id), "--dry-run")

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    assert rows[0]["status"] == "would_create"
    assert (rows[-1]["dry_run"], rows[-1]["would_create"], rows[-1]["created_ids"]) == (True, 1, [])
    assert observed == [True]
    assert test_db_manager.get_crop_children(parent_id) == []


def test_halfbody_is_rejected_as_input_error(parent_id: int, fake_detector: type[_FakeLibDetector]) -> None:
    result = _invoke("--class", "halfbody", "--image-ids", str(parent_id))

    assert result.exit_code == 2, result.output
    error = _jsonl(result.stdout)[-1]
    assert error["code"] == "INVALID_INPUT"
    assert "license" in error["message"]
    assert fake_detector.calls == []


@pytest.mark.parametrize(
    "extra",
    [
        ("--class", "cat", "--image-ids", "1"),
        ("--class", "person"),
        ("--class", "person", "--image-ids", "1", "--nms-iou", "0"),
        ("--class", "person", "--image-ids", "1", "--min-score", "1.5"),
    ],
)
def test_invalid_arguments_exit_2(
    parent_id: int, fake_detector: type[_FakeLibDetector], extra: tuple[str, ...]
) -> None:
    result = _invoke(*extra)

    assert result.exit_code == 2, result.output
    assert fake_detector.calls == []


def test_more_than_500_parent_ids_is_rejected_before_detection(
    parent_id: int, fake_detector: type[_FakeLibDetector], tmp_path: Path
) -> None:
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("\n".join(str(i) for i in range(1, 502)), encoding="utf-8")

    result = _invoke("--class", "person", "--image-ids-file", str(ids_file))

    assert result.exit_code == 2, result.output
    error = _jsonl(result.stdout)[-1]
    assert error["code"] == "RESULT_SET_TOO_LARGE"
    assert error["details"] == {"limit": 500, "matched": 501}
    assert fake_detector.calls == []


def test_describe_exposes_choices_and_defaults() -> None:
    result = runner.invoke(app, ["--json", "describe", "images crop-detect", "--schema", "json_schema"])

    assert result.exit_code == 0, result.output
    rows = _jsonl(result.stdout)
    schema = next(
        row for row in rows if row.get("type") == "schema" and row["name"] == "ImagesCropDetectInput"
    )["schema"]
    props = schema["properties"]
    assert props["class"]["enum"] == ["person", "face", "head", "halfbody"]
    assert "person -> person_detect_v1.3_s (0.324)" in props["class"]["description"]
    assert "face -> face_detect_v1.4_s (0.307)" in props["class"]["description"]
    assert "head -> head_detect_v2.0_s (0.413)" in props["class"]["description"]
    assert (
        props["padding"]["default"],
        props["nms_iou"]["default"],
        props["min_long_edge"]["default"],
        props["existing_iou"]["default"],
    ) == (0.1, 0.5, 256, 0.7)
    assert props["nms_iou"]["exclusiveMinimum"] == 0.0
    assert set(schema["required"]) == {"project", "class"}
