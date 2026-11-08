"""比較画面の左右の注釈とプレビューを読み込む worker (Issue #1399 / #1484)。

1 回の比較要求 (左右の画像 ID の組) ごとに 1 本起動し、左右のスナップショット・
プレビュー画像・差分を 1 つの結果として返す。画像と注釈を同じ結果に入れるため、
受け取り側で左右の対応がずれない。受け取り側は ``generation`` で古い結果を捨てる。

プレビューは表示中の 2 枚だけを、上限サイズへ縮小してデコードする。QPixmap は
GUI スレッド専用なので、ここではスレッドセーフな QImage を返す。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader

from ...database.db_core import resolve_stored_path
from ...services.image_comparison import (
    ComparisonResult,
    ComparisonSnapshot,
    ImageComparisonService,
    compare_snapshots,
)
from ...utils.log import logger
from .base import LoRAIroWorkerBase


@dataclass(frozen=True)
class LoadedComparisonSide:
    """片側の読み込み結果。``preview`` は読めなければ None。"""

    snapshot: ComparisonSnapshot
    preview: QImage | None


@dataclass(frozen=True)
class ImageComparisonLoadResult:
    """1 回の比較要求の結果。"""

    generation: int
    left: LoadedComparisonSide
    right: LoadedComparisonSide
    comparison: ComparisonResult


def decode_preview_image(image_path: Path, max_edge: int) -> QImage | None:
    """画像を最大辺 ``max_edge`` に収まるよう縮小デコードする (EXIF の向きを反映)。

    Args:
        image_path: 画像ファイルのパス。
        max_edge: 最大辺 (px)。

    Returns:
        デコードした QImage。読めなければ None。
    """
    if not image_path.is_file():
        return None
    reader = QImageReader(str(image_path))
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and (size.width() > max_edge or size.height() > max_edge):
        reader.setScaledSize(size.scaled(max_edge, max_edge, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        logger.debug(f"比較プレビューのデコードに失敗: {image_path.name}: {reader.errorString()}")
        return None
    return image


class ImageComparisonWorker(LoRAIroWorkerBase[ImageComparisonLoadResult]):
    """左右の画像の注釈とプレビューを読み、差分を計算する。"""

    _OPERATION_TYPE = "image_comparison"
    PREVIEW_MAX_EDGE = 1600

    def __init__(
        self,
        service: ImageComparisonService,
        *,
        generation: int,
        left_id: int,
        right_id: int,
        cached: dict[int, LoadedComparisonSide] | None = None,
    ) -> None:
        """要求を受け取る。

        Args:
            service: 読み取り専用の比較サービス。
            generation: 要求の世代番号 (受け取り側で古い結果を捨てる)。
            left_id: 左の画像 ID。
            right_id: 右の画像 ID。
            cached: 読み込み済みの片側 (入れ替えや片側固定で再読込しないため)。
        """
        super().__init__()
        self._service = service
        self._generation = generation
        self._left_id = left_id
        self._right_id = right_id
        self._cached = dict(cached or {})

    def _load_side(self, image_id: int) -> LoadedComparisonSide:
        cached = self._cached.get(image_id)
        if cached is not None:
            return cached
        snapshot = self._service.load_snapshot(image_id)
        self._check_cancellation()
        preview = None
        if snapshot.stored_image_path:
            preview = decode_preview_image(
                resolve_stored_path(snapshot.stored_image_path), self.PREVIEW_MAX_EDGE
            )
        return LoadedComparisonSide(snapshot=snapshot, preview=preview)

    def execute(self) -> ImageComparisonLoadResult:
        """左右を読み、差分を計算する。"""
        left = self._load_side(self._left_id)
        self._check_cancellation()
        right = self._load_side(self._right_id)
        self._check_cancellation()
        comparison = compare_snapshots(left.snapshot, right.snapshot)
        return ImageComparisonLoadResult(
            generation=self._generation, left=left, right=right, comparison=comparison
        )
