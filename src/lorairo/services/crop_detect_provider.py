"""物体検出器で矩形を決める CropRectProvider 実装 (Issue #1340 / ADR 0110)。

親画像を EXIF 適用後の表示向き (ADR 0092 §5) で開き、image-annotator-lib の検出器で
人物・顔・頭部を検出して、余白を足した矩形を候補として返す。作成対象外と判定した矩形は
理由コード付きの候補 (``skip_reason``) として、検出 0 件・画像を開けない・検出器を使えない
場合は矩形を伴わない :class:`CropRectNotice` として返し、一括処理 (``run_crop_batch``) が
1 矩形 = 1 結果の契約のまま報告する。

image-annotator-lib (onnxruntime / huggingface_hub) は検出を実行するときに初めて import する。
``lorairo-cli --help`` や ``describe`` はこのモジュールを読んでも重い依存を引き込まない。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from loguru import logger
from PIL import Image, ImageOps

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.domain.crop_rect_provider import CropRectCandidate, CropRectNotice
from lorairo.domain.crop_request import CropRect
from lorairo.services.crop_service import get_crop_source_info


@dataclass(frozen=True, slots=True)
class DetectorClassSpec:
    """``--class`` の値と検出器の対応。

    Attributes:
        class_name: 検出するクラス名 (``--class`` の値)。
        detector: image-annotator-lib の検出器名。``crop_relations.origin`` にも使う。
        default_min_score: 検出器提供元の推奨 score 閾値 (lib の ``DetectorInfo.default_min_score``)。
    """

    class_name: str
    detector: str
    default_min_score: float


# NOTE: lib の detection/catalog.py (BUILTIN_DETECTORS) と同じ値。CLI の --help / describe が
# lib を import せずに選択肢と既定値を示せるよう、LoRAIro 側の対応表はここ 1 箇所に置く。
# lib との一致はユニットテストで検証する。
DETECTOR_CLASSES: dict[str, DetectorClassSpec] = {
    spec.class_name: spec
    for spec in (
        DetectorClassSpec("person", "person_detect_v1.3_s", 0.324),
        DetectorClassSpec("face", "face_detect_v1.4_s", 0.307),
        DetectorClassSpec("head", "head_detect_v2.0_s", 0.413),
    )
}

UNSUPPORTED_DETECTOR_CLASSES: dict[str, str] = {
    "halfbody": (
        "halfbody is not supported: its detector is distributed under an OpenRAIL-style license "
        "whose use restrictions have not been reviewed (ADR 0110)."
    ),
}
"""``--class`` で受け付けるが未対応のクラスと、その理由。"""

DEFAULT_PADDING = 0.1
"""検出矩形の幅・高さそれぞれに掛ける片側の余白比率。"""

DEFAULT_NMS_IOU = 0.5
"""同一画像内の NMS の IoU 閾値。"""

DEFAULT_MIN_LONG_EDGE = 256
"""余白を足した後の矩形の長辺がこの値 (px) 未満なら ``below_min_long_edge``。"""

DEFAULT_EXISTING_IOU = 0.7
"""同じ親の既存クロップとの IoU がこの値以上なら ``overlaps_existing_crop``。"""

BELOW_SCORE_REPORT_RATIO = 0.5
"""``min_score`` x この比率以上・``min_score`` 未満の検出を ``below_min_score`` として報告する。"""

BoundingBox = tuple[float, float, float, float]
"""ピクセル座標の矩形 ``(x1, y1, x2, y2)``。x2/y2 は排他的な右下端。"""

DetectionFailureReason = Literal["detector_unavailable", "detection_failed"]


@dataclass(frozen=True, slots=True)
class DetectedBox:
    """検出器が返した 1 件の矩形。

    Attributes:
        score: 信頼度 (0.0 から 1.0)。
        bbox: 入力画像のピクセル座標 ``(x1, y1, x2, y2)``。
    """

    score: float
    bbox: BoundingBox


class ObjectDetectionError(Exception):
    """検出を実行できなかったことを表す。

    Attributes:
        reason: ``detector_unavailable`` (モデル取得・ロード失敗) または ``detection_failed``。
        message: 利用者向けの説明。内部パスやスタックは含めない。
    """

    def __init__(self, reason: DetectionFailureReason, message: str) -> None:
        super().__init__(message)
        self.reason: DetectionFailureReason = reason
        self.message = message


class ObjectDetector(Protocol):
    """1 枚の画像から矩形を検出する境界。テストでは fake に差し替える。"""

    def detect(
        self, image: Image.Image, *, detector: str, class_name: str, min_score: float, nms_iou: float
    ) -> Sequence[DetectedBox]:
        """``min_score`` 以上の検出を score 降順で返す。

        Raises:
            ObjectDetectionError: 検出器を使えない・推論に失敗した場合。
        """
        ...


class LibObjectDetector:
    """image-annotator-lib の ``detect_objects`` を呼ぶ :class:`ObjectDetector` 実装。"""

    def __init__(self) -> None:
        self._used: set[str] = set()

    def detect(
        self, image: Image.Image, *, detector: str, class_name: str, min_score: float, nms_iou: float
    ) -> Sequence[DetectedBox]:
        """lib の検出器で 1 枚を検出し、lib の例外を :class:`ObjectDetectionError` に変換する。"""
        # 重い依存 (onnxruntime / huggingface_hub) は検出の実行時まで読まない
        from image_annotator_lib import detect_objects
        from image_annotator_lib.exceptions.errors import (
            AnnotatorError,
            ModelLoadError,
            ModelNotFoundError,
            OutOfMemoryError,
        )

        self._used.add(detector)
        try:
            results = detect_objects(
                [image], detector, classes=[class_name], min_score=min_score, nms_iou=nms_iou
            )
        except (ModelLoadError, ModelNotFoundError) as error:
            logger.opt(exception=error).error("検出器のロードに失敗: detector={}", detector)
            raise ObjectDetectionError(
                "detector_unavailable",
                f"Detector '{detector}' could not be loaded. The model is downloaded from "
                "Hugging Face Hub on first use; check network access and retry.",
            ) from error
        except OutOfMemoryError as error:
            logger.opt(exception=error).error("検出中にメモリ不足: detector={}", detector)
            raise ObjectDetectionError(
                "detection_failed", f"Detector '{detector}' ran out of memory."
            ) from error
        except AnnotatorError as error:
            logger.opt(exception=error).error("検出に失敗: detector={}", detector)
            raise ObjectDetectionError(
                "detection_failed", f"Detector '{detector}' failed ({type(error).__name__})."
            ) from error
        return [
            DetectedBox(score=float(item.score), bbox=item.bbox)
            for result in results
            for item in result.detections
        ]

    def release(self) -> None:
        """この実行で使った検出器のセッションを破棄する (lib ADR 0014: 解放は呼び出し側の責務)。"""
        if not self._used:
            return
        from image_annotator_lib import release_detectors

        release_detectors(sorted(self._used))
        self._used.clear()


@dataclass(frozen=True, slots=True)
class DetectionSettings:
    """検出 provider のパラメータ。

    Attributes:
        min_score: 作成対象にする最小 score。
        padding: 検出矩形の幅・高さそれぞれに掛ける片側の余白比率 (画像端でクランプ)。
        nms_iou: 同一画像内の NMS の IoU 閾値。
        min_long_edge: 余白適用後の矩形の最小長辺 (px)。
        existing_iou: 同じ親の既存クロップとの IoU がこれ以上なら skipped。
    """

    min_score: float
    padding: float = DEFAULT_PADDING
    nms_iou: float = DEFAULT_NMS_IOU
    min_long_edge: int = DEFAULT_MIN_LONG_EDGE
    existing_iou: float = DEFAULT_EXISTING_IOU

    @property
    def report_floor(self) -> float:
        """``below_min_score`` として報告する検出の下限 score。"""
        return self.min_score * BELOW_SCORE_REPORT_RATIO


class DetectorCropRectProvider:
    """物体検出器の結果を親画像ごとの矩形候補として返す provider。"""

    def __init__(
        self,
        spec: DetectorClassSpec,
        settings: DetectionSettings,
        *,
        db_manager: ImageDatabaseManager,
        detector: ObjectDetector,
    ) -> None:
        self._spec = spec
        self._settings = settings
        self._db_manager = db_manager
        self._detector = detector
        self._unavailable: ObjectDetectionError | None = None

    @property
    def origin(self) -> str:
        """``crop_relations.origin`` に保存する由来 (検出器名)。"""
        return self._spec.detector

    def candidates_for(self, parent_image_id: int) -> list[CropRectCandidate | CropRectNotice]:
        """親画像 1 枚を検出し、作成対象・skipped の候補、または notice を返す。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元へ伝播させる。
        """
        if self._unavailable is not None:
            # モデルを取得・ロードできなかった場合は画像ごとに再試行しない
            return [self._notice("failed", self._unavailable.reason, self._unavailable.message)]
        loaded = self._load_image(parent_image_id)
        if isinstance(loaded, CropRectNotice):
            return [loaded]
        image_size = loaded.size
        try:
            boxes = self._detector.detect(
                loaded,
                detector=self._spec.detector,
                class_name=self._spec.class_name,
                min_score=self._settings.report_floor,
                nms_iou=self._settings.nms_iou,
            )
        except ObjectDetectionError as error:
            if error.reason == "detector_unavailable":
                self._unavailable = error
            return [self._notice("failed", error.reason, error.message)]
        finally:
            loaded.close()
        if not boxes:
            return [
                self._notice(
                    "skipped",
                    "no_detection",
                    f"No {self._spec.class_name} detected (score >= {self._settings.report_floor:.3f})",
                )
            ]
        existing = self._existing_rects(parent_image_id)
        return [self._candidate(box, image_size, existing) for box in boxes]

    def _load_image(self, parent_image_id: int) -> Image.Image | CropRectNotice:
        """親画像を EXIF 適用後の表示向きで開く。開けなければ notice を返す。"""
        try:
            source = get_crop_source_info(parent_image_id, db_manager=self._db_manager)
        except ValueError as exc:
            return self._notice("failed", "parent_not_found", str(exc))
        except OSError as exc:
            return self._notice("failed", "io_error", f"Cannot read parent image: {exc.strerror or exc}")
        try:
            with Image.open(source.image_path) as opened:
                oriented = ImageOps.exif_transpose(opened)
                image = oriented.convert("RGB")
        except OSError as exc:
            return self._notice("failed", "io_error", f"Cannot read parent image: {exc.strerror or exc}")
        return image

    def _existing_rects(self, parent_image_id: int) -> list[tuple[CropRect, str]]:
        return [
            (CropRect(rel.x, rel.y, rel.width, rel.height), rel.origin)
            for rel in self._db_manager.get_crop_children(parent_image_id)
        ]

    def _candidate(
        self, box: DetectedBox, image_size: tuple[int, int], existing: list[tuple[CropRect, str]]
    ) -> CropRectCandidate:
        """検出 1 件を候補にする。作成対象外なら理由コードを付ける。"""
        settings = self._settings
        rect = padded_rect(box.bbox, settings.padding, image_size)
        candidate = CropRectCandidate(rect=rect, origin=self.origin, score=box.score)
        if box.score < settings.min_score:
            return _skip(
                candidate,
                "below_min_score",
                f"score {box.score:.3f} is below min_score {settings.min_score:.3f}",
            )
        if rect.long_edge < settings.min_long_edge:
            return _skip(
                candidate,
                "below_min_long_edge",
                f"long edge {rect.long_edge}px is below min_long_edge {settings.min_long_edge}px",
            )
        for other, other_origin in existing:
            # 同じ矩形・由来は一括処理が already_exists として報告する (再実行の冪等性)
            if other == rect and other_origin == self.origin:
                continue
            overlap = rect_iou(rect, other)
            if overlap >= settings.existing_iou:
                return _skip(
                    candidate,
                    "overlaps_existing_crop",
                    f"IoU {overlap:.3f} with an existing crop ({other_origin}) is at least "
                    f"{settings.existing_iou:.3f}",
                )
        return candidate

    def _notice(
        self,
        status: Literal["skipped", "failed"],
        reason: Literal[
            "no_detection", "parent_not_found", "io_error", "detector_unavailable", "detection_failed"
        ],
        message: str,
    ) -> CropRectNotice:
        return CropRectNotice(status=status, reason=reason, message=message, origin=self.origin)


def _skip(
    candidate: CropRectCandidate,
    reason: Literal["below_min_score", "below_min_long_edge", "overlaps_existing_crop"],
    message: str,
) -> CropRectCandidate:
    return CropRectCandidate(
        rect=candidate.rect,
        origin=candidate.origin,
        score=candidate.score,
        skip_reason=reason,
        skip_message=message,
    )


def padded_rect(bbox: BoundingBox, padding: float, image_size: tuple[int, int]) -> CropRect:
    """検出矩形に余白を足し、画像端でクランプした整数矩形を返す。

    幅・高さそれぞれに ``padding`` を掛けた量を左右・上下に足す。左上は切り捨て、右下は
    切り上げで整数化し、検出矩形を必ず含むようにする。

    Args:
        bbox: ``(x1, y1, x2, y2)`` のピクセル座標 (float)。
        padding: 片側の余白比率 (0 以上)。
        image_size: 画像の ``(width, height)``。

    Returns:
        画像範囲内の矩形。
    """
    width, height = image_size
    x1, y1, x2, y2 = bbox
    pad_x = (x2 - x1) * padding
    pad_y = (y2 - y1) * padding
    left = max(0, math.floor(x1 - pad_x))
    top = max(0, math.floor(y1 - pad_y))
    right = min(width, math.ceil(x2 + pad_x))
    bottom = min(height, math.ceil(y2 + pad_y))
    return CropRect(x=left, y=top, width=right - left, height=bottom - top)


def rect_iou(a: CropRect, b: CropRect) -> float:
    """2 つの矩形の IoU (0.0 から 1.0) を返す。"""
    inter_w = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    inter_h = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    intersection = inter_w * inter_h
    union = a.width * a.height + b.width * b.height - intersection
    return intersection / union if union > 0 else 0.0
