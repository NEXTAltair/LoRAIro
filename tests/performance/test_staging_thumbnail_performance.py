"""Real-image staging measurements for issue #1385.

This deliberately runs on both the synchronous baseline and the asynchronous
implementation. Image creation and checksum verification happen outside every
measurement. All scenarios share 500 distinct, deterministic 768 x 640 files
(250 JPEG and 250 WEBP), and completion is observed through displayed pixmaps.
No thumbnail decoder or staging state is mocked.

Set STAGING_PERF_INPUT_DIR to reuse the exact files between checkouts, and
STAGING_PERF_OUTPUT_DIR / STAGING_PERF_LABEL to preserve JSON and screenshots.
Optional STAGING_PERF_MAX_GUI_GAP_MS and STAGING_PERF_REQUIRE_INPUT_DURING_LOAD=1
turn measurements into local acceptance gates; leave them unset for a baseline.
Linux offscreen results describe a synthetic comparison, not Windows runtime.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import platform
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, Qt, QTimer, qVersion
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget
from pytestqt.qtbot import QtBot

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.staging_widget import StagingWidget
from lorairo.gui.widgets.thumbnail_selector_widget import ThumbnailSelectorWidget

pytestmark = [pytest.mark.slow, pytest.mark.gui_show]

IMAGE_COUNT = 500
IMAGE_SIZE = (768, 640)
DATASET_VERSION = 1
HEARTBEAT_INTERVAL_MS = 10


@dataclass(frozen=True)
class ImageDataset:
    metadata: list[dict[str, Any]]
    manifest_sha256: str


@pytest.fixture(scope="module")
def staging_images(tmp_path_factory: pytest.TempPathFactory) -> ImageDataset:
    """Generate/verify the shared source files before starting a GUI timer."""
    configured = os.environ.get("STAGING_PERF_INPUT_DIR")
    image_dir = Path(configured) if configured else tmp_path_factory.mktemp("staging_perf_images")
    image_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = image_dir / "manifest.json"
    manifest: dict[str, Any] = {"version": DATASET_VERSION, "images": []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["version"] == DATASET_VERSION, "Use a new directory for a new dataset version"
        assert len(manifest["images"]) == IMAGE_COUNT
    else:
        rng = np.random.default_rng(1385)
        for image_id in range(1, IMAGE_COUNT + 1):
            # Dense real pixel data makes decoding measurable. A colored corner
            # ensures a loaded image cannot be mistaken for a gray placeholder.
            pixels = rng.integers(0, 256, size=(IMAGE_SIZE[1], IMAGE_SIZE[0], 3), dtype=np.uint8)
            pixels[:64, :64] = (16 + image_id % 192, 32 + image_id % 160, 240)
            suffix = ".webp" if image_id % 2 else ".jpg"
            path = image_dir / f"staging_{image_id:04d}{suffix}"
            image = Image.fromarray(pixels)
            image.save(path, quality=82)
            image.close()
            manifest["images"].append(
                {
                    "id": image_id,
                    "filename": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                    "width": IMAGE_SIZE[0],
                    "height": IMAGE_SIZE[1],
                }
            )
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    metadata = []
    for entry in manifest["images"]:
        path = image_dir / entry["filename"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        with Image.open(path) as image:
            assert image.size == IMAGE_SIZE
        metadata.append(
            {
                "id": entry["id"],
                "stored_image_path": str(path.resolve()),
                "width": entry["width"],
                "height": entry["height"],
            }
        )
    assert len({entry["sha256"] for entry in manifest["images"]}) == IMAGE_COUNT
    manifest_digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return ImageDataset(metadata, manifest_digest)


@dataclass
class StagingHarness:
    host: QWidget
    staging: StagingWidget
    thumbnails: ThumbnailSelectorWidget
    dataset_state: DatasetStateManager
    input_widget: QLineEdit


@pytest.fixture
def staging_harness(qtbot: QtBot, staging_images: ImageDataset) -> StagingHarness:
    """Use the actual DatasetStateManager -> StagingWidget -> thumbnail path."""
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    staging = StagingWidget(host)
    input_widget = QLineEdit(host)
    input_widget.setPlaceholderText("Input responsiveness probe")
    layout.addWidget(staging)
    layout.addWidget(input_widget)
    state = DatasetStateManager(host)
    state.set_dataset_images(staging_images.metadata)
    staging.set_dataset_state_manager(state)
    thumbnails = staging.findChild(ThumbnailSelectorWidget, "stagingThumbnailWidget")
    assert thumbnails is not None
    host.resize(1024, 540)
    host.show()
    input_widget.setFocus()
    # Let the initial 250 ms resize debounce expire before measuring an add.
    qtbot.wait(350)
    return StagingHarness(host, staging, thumbnails, state, input_widget)


def _completed_image_count(harness: StagingHarness) -> int:
    """Read displayed content, not private asynchronous task/cache fields."""
    placeholder_colors = {QColor(Qt.GlobalColor.gray).rgb(), QColor(Qt.GlobalColor.lightGray).rgb()}
    count = 0
    for item in harness.thumbnails.thumbnail_items:
        if not item.pixmap.isNull() and item.pixmap.toImage().pixel(0, 0) not in placeholder_colors:
            count += 1
    return count


def _assert_complete(harness: StagingHarness, expected_ids: list[int]) -> bool:
    assert harness.staging.get_image_ids() == expected_ids
    items = harness.thumbnails.thumbnail_items
    if [item.image_id for item in items] != expected_ids:
        return False
    for item in items:
        metadata = harness.dataset_state.get_image_by_id(item.image_id)
        assert metadata is not None
        assert item.image_path == Path(metadata["stored_image_path"])
    return _completed_image_count(harness) == len(expected_ids)


def _measure(
    qtbot: QtBot,
    harness: StagingHarness,
    name: str,
    action: Callable[[], None],
    expected_ids: list[int],
    *,
    operate_while_loading: bool = False,
    layout_ready: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Capture blocking calls, actual event gaps, and actual queued key input."""
    harness.input_widget.clear()
    input_events: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    gaps: list[float] = []
    started = time.perf_counter()
    previous_tick = started

    def heartbeat() -> None:
        nonlocal previous_tick
        now = time.perf_counter()
        gaps.append((now - previous_tick) * 1000)
        previous_tick = now

    def input_processed(text: str) -> None:
        input_events.append(
            {
                "text": text,
                "delay_ms": (time.perf_counter() - started) * 1000,
                "completed_images": _completed_image_count(harness),
            }
        )

    def operate() -> None:
        scroll_bar = harness.thumbnails.graphics_view.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())
        harness.host.resize(720, 540)
        operations.append(
            {
                "delay_ms": (time.perf_counter() - started) * 1000,
                "completed_images": _completed_image_count(harness),
                "scroll_value": scroll_bar.value(),
                "width": harness.host.width(),
            }
        )

    timer = QTimer(harness.host)
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(HEARTBEAT_INTERVAL_MS)
    timer.timeout.connect(heartbeat)
    operation_timer = QTimer(harness.host)
    operation_timer.setSingleShot(True)
    operation_timer.timeout.connect(operate)
    harness.input_widget.textChanged.connect(input_processed)
    timer.start()
    if operate_while_loading:
        operation_timer.start(20)
    # Posted QKeyEvents are handled by the real QLineEdit only when the GUI
    # event loop gets control. Direct qtbot.keyClick would hide GUI starvation.
    for event_type in (QKeyEvent.Type.KeyPress, QKeyEvent.Type.KeyRelease):
        QCoreApplication.postEvent(
            harness.input_widget,
            QKeyEvent(event_type, Qt.Key.Key_X, Qt.KeyboardModifier.NoModifier, "x"),
        )
    try:
        call_started = time.perf_counter()
        action()
        call_ms = (time.perf_counter() - call_started) * 1000
        qtbot.waitUntil(
            lambda: _assert_complete(harness, expected_ids) and (layout_ready is None or layout_ready()),
            timeout=120_000,
        )
        complete_ms = (time.perf_counter() - started) * 1000
        qtbot.waitUntil(lambda: harness.input_widget.text() == "x", timeout=10_000)
        # Width changes use a 250 ms debounce. Include its work and the
        # following heartbeat so a synchronous resize decode cannot be missed.
        qtbot.wait(350)
        qtbot.waitUntil(lambda: _assert_complete(harness, expected_ids), timeout=120_000)
        qtbot.wait(30)
        assert len(input_events) == 1
        assert input_events[0]["text"] == "x"
        if operate_while_loading:
            assert len(operations) == 1
            assert operations[0]["width"] == 720
            assert operations[0]["scroll_value"] > 0
        assert harness.staging.count() == len(expected_ids)
        assert harness.staging.ui.labelStagingCount.text() == f"{len(expected_ids)} / 500 枚"
        return {
            "scenario": name,
            "expected_images": len(expected_ids),
            "completed_images": _completed_image_count(harness),
            "call_ms": call_ms,
            "complete_ms": complete_ms,
            "settled_ms": (time.perf_counter() - started) * 1000,
            "max_gui_gap_ms": max(gaps),
            "heartbeat_samples": len(gaps),
            "heartbeat_interval_ms": HEARTBEAT_INTERVAL_MS,
            "queued_input": input_events[0],
            "operations": operations,
        }
    finally:
        timer.stop()
        operation_timer.stop()
        harness.input_widget.textChanged.disconnect(input_processed)
        timer.deleteLater()
        operation_timer.deleteLater()


def _save_result(
    tmp_path: Path,
    harness: StagingHarness,
    images: ImageDataset,
    scenario: str,
    measurements: list[dict[str, Any]],
) -> None:
    output_dir = Path(os.environ.get("STAGING_PERF_OUTPUT_DIR", str(tmp_path)))
    output_dir.mkdir(parents=True, exist_ok=True)
    label = os.environ.get("STAGING_PERF_LABEL", "measurement")
    basename = f"{label}-{scenario}"
    sources = {}
    for widget_type in (StagingWidget, ThumbnailSelectorWidget):
        source_path = Path(inspect.getfile(widget_type)).resolve()
        sources[widget_type.__name__] = {
            "path": str(source_path),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        }
    result = {
        "label": label,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "qt_version": qVersion(),
        "qt_platform": os.environ.get("QT_QPA_PLATFORM", "default"),
        "scope": "synthetic real-image staging; Linux offscreen is not a Windows production measurement",
        "image_count": IMAGE_COUNT,
        "image_size": list(IMAGE_SIZE),
        "formats": {"JPEG": IMAGE_COUNT // 2, "WEBP": IMAGE_COUNT // 2},
        "image_generation_is_timed": False,
        "manifest_sha256": images.manifest_sha256,
        "sources": sources,
        "measurements": measurements,
    }
    (output_dir / f"{basename}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert harness.host.grab().save(str(output_dir / f"{basename}.png"))
    print(json.dumps(result, sort_keys=True))

    max_gap = os.environ.get("STAGING_PERF_MAX_GUI_GAP_MS")
    if max_gap is not None:
        assert all(item["max_gui_gap_ms"] <= float(max_gap) for item in measurements), measurements
    if os.environ.get("STAGING_PERF_REQUIRE_INPUT_DURING_LOAD") == "1":
        for item in measurements:
            if item["scenario"].startswith(("add_", "initial_")):
                assert item["queued_input"]["completed_images"] < item["expected_images"], item
                for operation in item["operations"]:
                    assert operation["completed_images"] < item["expected_images"], item


def test_staging_add_100_images_until_500(
    qtbot: QtBot,
    staging_harness: StagingHarness,
    staging_images: ImageDataset,
    tmp_path: Path,
) -> None:
    """Measure each real selection -> staging add without clearing prior items."""
    measurements = []
    for total in range(100, IMAGE_COUNT + 1, 100):
        staging_harness.dataset_state.set_selected_images(list(range(total - 99, total + 1)))
        measurements.append(
            _measure(
                qtbot,
                staging_harness,
                f"add_100_to_{total}",
                staging_harness.staging.add_selected_images,
                list(range(1, total + 1)),
            )
        )
    _save_result(tmp_path, staging_harness, staging_images, "increments", measurements)


def test_staging_initial_500_and_width_change(
    qtbot: QtBot,
    staging_harness: StagingHarness,
    staging_images: ImageDataset,
    tmp_path: Path,
) -> None:
    """Measure a fresh 500-image add and an actual debounced width change."""
    expected_ids = list(range(1, IMAGE_COUNT + 1))
    staging_harness.dataset_state.set_selected_images(expected_ids)
    measurements = [
        _measure(
            qtbot,
            staging_harness,
            "initial_500",
            staging_harness.staging.add_selected_images,
            expected_ids,
        )
    ]
    previous_last_position = staging_harness.thumbnails.thumbnail_items[-1].pos()
    measurements.append(
        _measure(
            qtbot,
            staging_harness,
            "width_change_500",
            lambda: staging_harness.host.resize(720, 540),
            expected_ids,
            layout_ready=lambda: (
                staging_harness.thumbnails.thumbnail_items[-1].pos() != previous_last_position
            ),
        )
    )
    _save_result(tmp_path, staging_harness, staging_images, "initial-and-resize", measurements)


def test_staging_input_scroll_and_resize_during_add(
    qtbot: QtBot,
    staging_harness: StagingHarness,
    staging_images: ImageDataset,
    tmp_path: Path,
) -> None:
    """Verify real queued input/scroll/resize, recording whether loading continued."""
    expected_ids = list(range(1, IMAGE_COUNT + 1))
    staging_harness.dataset_state.set_selected_images(expected_ids)
    measurement = _measure(
        qtbot,
        staging_harness,
        "initial_500_with_input_scroll_resize",
        staging_harness.staging.add_selected_images,
        expected_ids,
        operate_while_loading=True,
    )
    _save_result(tmp_path, staging_harness, staging_images, "interaction", [measurement])
