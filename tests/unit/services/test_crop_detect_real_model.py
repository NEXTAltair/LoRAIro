"""実検出モデルでの ``LibObjectDetector`` の確認 (Issue #1340 / ADR 0110)。

Hugging Face Hub からモデルを取得して CPU 推論するため ``downloads_and_runs_model`` を付け、
CI の必須ゲートから外す。conftest が image_annotator_lib を mock するため、実ライブラリは
fresh interpreter (subprocess) で読む。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_IMAGE = Path(__file__).resolve().parents[2] / "resources" / "img" / "1_img" / "file01.webp"

_PROBE = """
import json, sys
from PIL import Image, ImageOps
from lorairo.services.crop_detect_provider import DETECTOR_CLASSES, LibObjectDetector

spec = DETECTOR_CLASSES[sys.argv[2]]
with Image.open(sys.argv[1]) as opened:
    image = ImageOps.exif_transpose(opened).convert("RGB")
detector = LibObjectDetector()
boxes = detector.detect(
    image, detector=spec.detector, class_name=spec.class_name, min_score=0.1, nms_iou=0.5
)
detector.release()
print(json.dumps({"size": image.size, "boxes": [[b.score, *b.bbox] for b in boxes]}))
"""


@pytest.mark.downloads_and_runs_model
@pytest.mark.parametrize("class_name", ["person", "face", "head"])
def test_real_detector_returns_boxes_inside_the_image(class_name: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(_IMAGE), class_name],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert result.returncode == 0, result.stderr[-2000:]
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    width, height = payload["size"]
    for score, x1, y1, x2, y2 in payload["boxes"]:
        assert 0.1 <= score <= 1.0
        assert 0.0 <= x1 <= x2 <= width
        assert 0.0 <= y1 <= y2 <= height
    scores = [box[0] for box in payload["boxes"]]
    assert scores == sorted(scores, reverse=True)
