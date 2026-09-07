"""クロップ作成 request の共有型。

GUI (矩形選択ダイアログ) と将来の物体検出 (#1340) が同じサービス関数へ渡す
plain な Python 型。Qt / DB / service を import しない (ADR 0092)。
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CROP_ORIGIN = "manual"
"""切り出し由来の既定値。GUI の手動矩形選択。"""

CROP_LONG_EDGE_WARNING_PX = 1024
"""切り出し実寸の長辺がこの値未満なら GUI は品質警告を表示する (保存は禁止しない)。"""


@dataclass(frozen=True, slots=True)
class CropRect:
    """親画像のピクセル座標系における切り出し矩形。

    Attributes:
        x: 左上 x 座標 (親画像基準、px)。
        y: 左上 y 座標 (親画像基準、px)。
        width: 幅 (px)。
        height: 高さ (px)。
    """

    x: int
    y: int
    width: int
    height: int

    @property
    def long_edge(self) -> int:
        """長辺の長さ (px)。"""
        return max(self.width, self.height)

    def has_positive_size(self) -> bool:
        """幅・高さがともに 1px 以上か。"""
        return self.width > 0 and self.height > 0

    def fits_within(self, image_width: int, image_height: int) -> bool:
        """矩形が親画像 (image_width x image_height) の範囲内に収まるか。"""
        return (
            self.x >= 0
            and self.y >= 0
            and self.has_positive_size()
            and self.x + self.width <= image_width
            and self.y + self.height <= image_height
        )


@dataclass(frozen=True, slots=True)
class CropCreateRequest:
    """クロップ画像を 1 件作成するための request。

    Attributes:
        parent_image_id: 直接の親となる画像 ID (images.id)。
        rect: 親画像基準の切り出し矩形。
        tags: 子画像へコピーする採用タグ (正規化済みタグ文字列)。
        rating: 子画像の normalized_rating ('PG' / 'PG-13' / 'R' / 'X' / 'XXX')。None なら未設定。
        origin: 切り出し由来。手動選択は `manual`、物体検出は検出器名等 (#1340)。
    """

    parent_image_id: int
    rect: CropRect
    tags: tuple[str, ...] = ()
    rating: str | None = None
    origin: str = DEFAULT_CROP_ORIGIN
