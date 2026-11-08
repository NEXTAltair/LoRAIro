"""クロップ矩形の供給元 (provider) の差し替え境界 (Issue #1340 / ADR 0103)。

矩形を「どこから得るか」(外部ツールが書いた JSONL、将来の物体検出器など) を
一括クロップの処理本体から切り離すための Protocol と候補型。
Qt / DB / service を import しない plain な Python 型に留める。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lorairo.domain.crop_request import CropRect


@dataclass(frozen=True, slots=True)
class CropRectCandidate:
    """provider が返す 1 件の切り出し矩形候補。

    Attributes:
        rect: 親画像基準 (EXIF orientation 適用後の表示向き、ADR 0092 §5) の矩形。
        origin: ``crop_relations.origin`` に保存する切り出し由来。
        score: 検出信頼度などの任意スコア。保存はせず結果出力にだけ載せる。
        line: 入力ファイル由来の候補なら 1 始まりの行番号。検出器由来なら None。
    """

    rect: CropRect
    origin: str
    score: float | None = None
    line: int | None = None


@runtime_checkable
class CropRectProvider(Protocol):
    """親画像 ID から切り出し矩形の候補を返す差し替え可能な境界。

    画像ファイルを必要とする実装 (物体検出器など) は、パス解決手段をコンストラクタで
    受け取る。候補の妥当性 (範囲内か等) は呼び出し側の一括処理が検証する。
    """

    def candidates_for(self, parent_image_id: int) -> Sequence[CropRectCandidate]:
        """親画像 1 枚分の矩形候補を返す。候補が無ければ空のシーケンス。"""
        ...
