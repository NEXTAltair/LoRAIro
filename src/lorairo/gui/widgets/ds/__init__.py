"""DS 部品ライブラリ (claude.ai/design のデザインシステムを鏡写しした再利用 Qt ウィジェット)。

各画面はここの部品を組み合わせて構成し、React (claude.ai/design) と Qt (実機) を
同じ部品ボキャブラリで揃えることで design↔code の drift を防ぐ (Issue #852 / #843)。
すべて :mod:`lorairo.gui.theme` のトークン駆動。
"""

from .ds_card import DsCard
from .ds_chip import DsChip
from .ds_segmented_control import DsSegmentedControl, SegmentOption
from .ds_summary_stat import DsSummaryStat

__all__ = [
    "DsCard",
    "DsChip",
    "DsSegmentedControl",
    "DsSummaryStat",
    "SegmentOption",
]
