"""StagingWidget の縦 QSplitter ペイン高さクランプの runtime 検証 (Issue #1097 再オープン)。

enable_content_height (sizeHint 縮小) だけでは、パネル実高さを決める縦 QSplitter が
子の sizeHint 変化を反映せず空白が残った。実際に縦 splitter を組んで staged 画像を
0/3/10 枚に変え、「サムネイル下の空白がしきい値以下」を実測する。
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget

from lorairo.gui.widgets.staging_widget import StagingWidget

pytestmark = [pytest.mark.unit, pytest.mark.gui]

_WHITESPACE_TOLERANCE = 8  # px (AA / 端数)


def _build_vertical_splitter(qtbot) -> tuple[QSplitter, QWidget, QLabel, StagingWidget]:
    """縦 splitter [staging を含む上ペイン, 下ペイン] を組んで過剰配分した状態で返す。"""
    splitter = QSplitter(Qt.Orientation.Vertical)
    top = QWidget()
    top_layout = QVBoxLayout(top)
    top_layout.setContentsMargins(0, 0, 0, 0)
    staging = StagingWidget()
    dsm = Mock()
    dsm.get_image_by_id.side_effect = lambda image_id: {"stored_image_path": f"/x/{image_id}.png"}
    staging.set_dataset_state_manager(dsm)
    top_layout.addWidget(staging)
    bottom = QLabel("bottom")
    bottom.setMinimumHeight(60)
    splitter.addWidget(top)
    splitter.addWidget(bottom)
    qtbot.addWidget(splitter)
    splitter.resize(420, 820)
    splitter.setSizes([700, 120])  # 上ペインを過剰配分 (= 空白の元)
    splitter.show()
    qtbot.waitExposed(splitter)
    return splitter, top, bottom, staging


class TestStagingSplitterFit:
    @pytest.mark.parametrize("count", [0, 3, 10])
    def test_no_whitespace_below_thumbnails(self, qtbot, count):
        _splitter, top, _bottom, staging = _build_vertical_splitter(qtbot)
        if count:
            staging.add_image_ids(list(range(1, count + 1)))
        qtbot.waitUntil(lambda: staging.count() == count, timeout=2000)
        # 上ペインの高さがステージング内容 (sizeHint) を大きく超えない = 空白が無い
        whitespace = top.height() - staging.sizeHint().height()
        assert whitespace <= _WHITESPACE_TOLERANCE, f"count={count} whitespace={whitespace}"

    def test_excess_height_goes_to_adjacent_pane(self, qtbot):
        _splitter, top, bottom, staging = _build_vertical_splitter(qtbot)
        staging.add_image_ids([1, 2, 3])
        qtbot.waitUntil(lambda: staging.count() == 3, timeout=2000)
        # 上ペインがクランプされ、余剰が下ペインへ回る (過剰配分 700 → 大幅縮小)
        assert top.height() < 400
        assert bottom.height() > 400

    def test_more_rows_raises_clamp(self, qtbot):
        _splitter, top, _bottom, staging = _build_vertical_splitter(qtbot)
        staging.add_image_ids([1, 2, 3])
        qtbot.waitUntil(lambda: staging.count() == 3, timeout=2000)
        small = top.maximumHeight()
        staging.add_image_ids(list(range(4, 16)))  # 3 行を超える
        qtbot.waitUntil(lambda: staging.count() == 15, timeout=2000)
        # 行数が増えたぶんクランプ上限は上がる (ただし最大3行で頭打ち)
        assert top.maximumHeight() > small

    def test_manual_shrink_still_allowed(self, qtbot):
        # クランプは上限のみ。多行 (max > min) のときハンドルで縮める操作は維持される。
        _splitter, top, _bottom, staging = _build_vertical_splitter(qtbot)
        staging.add_image_ids(list(range(1, 16)))  # 3 行相当 → max > min で縮小余地あり
        qtbot.waitUntil(lambda: staging.count() == 15, timeout=2000)
        clamp = top.maximumHeight()
        floor = top.minimumSizeHint().height()
        assert clamp > floor, "多行では上限が最小より大きい (縮小余地がある)"
        target = (clamp + floor) // 2
        _splitter.setSizes([target, 820 - target])
        qtbot.waitUntil(lambda: top.height() < clamp, timeout=2000)
        assert top.height() < clamp  # 上限より小さくできる


class TestStagingSplitterFitSafety:
    def test_no_vertical_splitter_ancestor_is_noop(self, qtbot):
        # 縦 splitter 祖先が無い文脈ではクランプしない (他画面の StagingWidget を壊さない)。
        host = QWidget()
        layout = QVBoxLayout(host)
        staging = StagingWidget()
        layout.addWidget(staging)
        qtbot.addWidget(host)
        host.show()
        qtbot.waitExposed(host)
        staging.add_image_ids([1, 2, 3])
        # maximumHeight は既定 (無制限) のまま
        assert staging.maximumHeight() >= 16777215 - 1


def _build_nested_splitter(
    qtbot, *, window_width: int = 900, sibling_min_height: int = 60
) -> tuple[QSplitter, QWidget, StagingWidget, QLabel]:
    """実ツリー相当: 縦 splitter → ペイン(margins) → 横 splitter[staging, tag入力] → 下ペイン。

    staging は横 splitter に入れ子で、ペイン widget は staging ではなくその祖先。
    tag 入力の高さ (sibling_min_height) がクランプ計算に含まれるかを検証できる。
    """
    vsplit = QSplitter(Qt.Orientation.Vertical)
    pane = QWidget()
    pane_layout = QVBoxLayout(pane)
    pane_layout.setContentsMargins(6, 6, 6, 6)
    hsplit = QSplitter(Qt.Orientation.Horizontal)
    staging = StagingWidget()
    dsm = Mock()
    dsm.get_image_by_id.side_effect = lambda image_id: {"stored_image_path": f"/x/{image_id}.png"}
    staging.set_dataset_state_manager(dsm)
    tag_input = QLabel("tag input")
    tag_input.setMinimumHeight(sibling_min_height)
    hsplit.addWidget(staging)
    hsplit.addWidget(tag_input)
    pane_layout.addWidget(hsplit)
    bottom = QLabel("bottom")
    bottom.setMinimumHeight(60)
    vsplit.addWidget(pane)
    vsplit.addWidget(bottom)
    qtbot.addWidget(vsplit)
    vsplit.resize(window_width, 820)
    vsplit.setSizes([700, 120])
    vsplit.show()
    qtbot.waitExposed(vsplit)
    return vsplit, pane, staging, tag_input


class TestStagingSplitterFitCodexRegressions:
    """#1097 Codex P2×3: 幅変化再クランプ / ラッパー chrome / 行数増でペイン拡大。"""

    def test_grows_when_staging_needs_more_rows(self, qtbot):
        # P2-3: 少数 (1 行) → 多数 (複数行) で実際にペインが広がる
        # (max 緩和だけでは QSplitter が広げないため setSizes 再配分が要る)。
        _vsplit, pane, staging, _tag = _build_nested_splitter(qtbot, sibling_min_height=60)
        staging.add_image_ids([1])
        qtbot.waitUntil(lambda: staging.count() == 1, timeout=2000)
        one_row_height = pane.height()
        staging.add_image_ids(list(range(2, 13)))
        qtbot.waitUntil(lambda: staging.count() == 12, timeout=2000)
        assert pane.height() > one_row_height + 40, (
            f"ペインが広がっていない ({one_row_height} -> {pane.height()})"
        )

    def test_recomputes_clamp_on_width_change(self, qtbot):
        # P2-1: 幅変化で列数=行数が変わったとき cap を再計算する。
        vsplit, pane, staging, _tag = _build_nested_splitter(
            qtbot, window_width=1600, sibling_min_height=50
        )
        staging.add_image_ids(list(range(1, 7)))
        qtbot.waitUntil(lambda: staging.count() == 6, timeout=2000)
        wide_cap = pane.maximumHeight()
        vsplit.resize(360, 820)  # 狭幅 → 行数増
        qtbot.waitUntil(lambda: pane.maximumHeight() > wide_cap + 40, timeout=2000)
        assert pane.maximumHeight() > wide_cap

    def test_pane_chrome_not_clipping_thumbnails(self, qtbot):
        # P2-2: ペインは staging ではなく祖先。兄弟 (tag入力) が高くてもサムネが切れない。
        _vsplit, pane, staging, _tag = _build_nested_splitter(qtbot, sibling_min_height=320)
        staging.add_image_ids([1, 2, 3])
        qtbot.waitUntil(lambda: staging.count() == 3, timeout=2000)
        thumb = staging._staging_thumbnail_widget
        # サムネ枠の実高さが推奨コンテンツ高さ以上 = 切れていない
        assert thumb.height() >= thumb._recommended_content_height()
        # ペインは兄弟 (320) を収める高さになっている
        assert pane.height() >= 320
