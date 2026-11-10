"""TagCloudWidget / NetworkGraphView の GUI テスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QLabel, QWidget

from lorairo.gui.widgets.tag_cloud_widget import (
    FlowLayout,
    NetworkGraphView,
    TagCloudWidget,
    _ramp_color,
    _TagCloudLabel,
)
from lorairo.services.tag_cloud_service import GraphEdge, GraphNode, GraphResult


def _sample_graph() -> GraphResult:
    return GraphResult(
        nodes=[
            GraphNode(tag="long_hair", count=10, weight=1.0),
            GraphNode(tag="smile", count=5, weight=0.5),
            GraphNode(tag="blush", count=2, weight=0.0),
        ],
        edges=[GraphEdge(a=0, b=1, weight=3, norm=1.0)],
        adjacency=[{1}, {0}, set()],
        matched_images=8,
        total_images=20,
        tag_count=5,
        excluded_tags=[],
    )


def _empty_graph() -> GraphResult:
    return GraphResult(nodes=[], edges=[], adjacency=[], matched_images=0, total_images=20, tag_count=0)


def _make_widget(qtbot: pytest.FixtureRequest, result: GraphResult) -> TagCloudWidget:
    """build_graph をスタブした TagCloudWidget を生成（同期パス）。"""
    widget = TagCloudWidget(db_manager=MagicMock())
    qtbot.addWidget(widget)
    widget._service = MagicMock()
    widget._service.build_graph = MagicMock(return_value=result)
    widget._loaded_once = True
    return widget


@pytest.mark.unit
@pytest.mark.gui
class TestHelpers:
    def test_ramp_color_returns_qcolor(self) -> None:
        assert isinstance(_ramp_color(0.0), QColor)

    def test_ramp_low_and_high_differ(self) -> None:
        assert _ramp_color(0.0).name() != _ramp_color(1.0).name()

    def test_flowlayout_add_count_take(self, qtbot: pytest.FixtureRequest) -> None:
        container = QWidget()
        qtbot.addWidget(container)
        layout = FlowLayout(container)
        layout.addWidget(QLabel("a"))
        layout.addWidget(QLabel("b"))
        assert layout.count() == 2
        assert layout.takeAt(0) is not None
        assert layout.count() == 1
        assert layout.takeAt(5) is None


@pytest.mark.unit
@pytest.mark.gui
class TestNetworkGraphView:
    def test_set_graph_populates_particles(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.set_graph(_sample_graph())
        assert len(view._particles) == 3

    def test_empty_graph_has_no_particles(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.set_graph(_empty_graph())
        assert view._particles == []

    def test_node_click_emits_tag(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.resize(400, 400)
        view.set_graph(_sample_graph())
        # 1つ目の粒子を既知座標へ移動してクリック
        view._particles[0].x = 100.0
        view._particles[0].y = 100.0
        view._particles[0].r = 20.0
        with qtbot.waitSignal(view.node_clicked, timeout=1000) as blocker:
            view._click_at(100.0, 100.0)
        assert blocker.args == ["long_hair"]

    def test_node_at_detects_node(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.resize(400, 400)
        view.set_graph(_sample_graph())
        view._particles[1].x = 200.0
        view._particles[1].y = 200.0
        view._particles[1].r = 15.0
        assert view._node_at(200.0, 200.0) == 1
        assert view._node_at(5.0, 5.0) == -1

    def test_label_collision_skips_overlapping_lower_weight(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.resize(400, 400)
        view.set_graph(_sample_graph())
        # Place node 0 (weight 1.0) and node 1 (weight 0.5) at identical coordinates
        for p in view._particles:
            p.x = 200.0
            p.y = 200.0
            p.r = 15.0
        image = QImage(400, 400, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        view._draw_labels(painter)
        painter.end()
        assert "long_hair" in view._last_drawn_labels
        assert "smile" not in view._last_drawn_labels
        assert "blush" not in view._last_drawn_labels

    def test_hovered_node_label_prioritized_over_higher_weight(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.resize(400, 400)
        view.set_graph(_sample_graph())
        for p in view._particles:
            p.x = 200.0
            p.y = 200.0
            p.r = 15.0
        # Hover node 1 (weight 0.5, neighbor of node 0 with weight 1.0)
        view._hover = 1
        image = QImage(400, 400, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        view._draw_labels(painter)
        painter.end()
        assert view._last_drawn_labels == ["smile"]

    def test_wheel_zoom_and_screen_to_world_hit_testing(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.resize(400, 400)
        view.set_graph(_sample_graph())
        view._particles[0].x = 150.0
        view._particles[0].y = 150.0
        view._particles[0].r = 15.0
        # Zoom in via wheelEvent anchored at (150, 150)
        wheel = QWheelEvent(
            QPointF(150.0, 150.0),
            QPointF(150.0, 150.0),
            QPoint(0, 0),
            QPoint(0, 120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
        view.wheelEvent(wheel)
        assert view._zoom == pytest.approx(1.15)
        sx, sy = view._world_to_screen(150.0, 150.0)
        assert view._node_at(sx, sy) == 0
        # Pan via empty background drag
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10.0, 10.0),
            QPointF(10.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(50.0, 60.0),
            QPointF(50.0, 60.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(50.0, 60.0),
            QPointF(50.0, 60.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mousePressEvent(press)
        view.mouseMoveEvent(move)
        view.mouseReleaseEvent(release)
        sx_after, sy_after = view._world_to_screen(150.0, 150.0)
        assert view._node_at(sx_after, sy_after) == 0
        # Reset view restores zoom=1, pan=(0,0)
        view.reset_view()
        assert view._zoom == 1.0
        assert view._pan_x == 0.0
        assert view._pan_y == 0.0

    def test_node_drag_pins_particle_and_suppresses_click(self, qtbot: pytest.FixtureRequest) -> None:
        view = NetworkGraphView()
        qtbot.addWidget(view)
        view.resize(400, 400)
        view.set_graph(_sample_graph())
        view.stop()
        view._particles[0].x = 100.0
        view._particles[0].y = 100.0
        view._particles[0].r = 20.0
        clicked_tags: list[str] = []
        view.node_clicked.connect(clicked_tags.append)

        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(100.0, 100.0),
            QPointF(100.0, 100.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        move = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(180.0, 190.0),
            QPointF(180.0, 190.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(180.0, 190.0),
            QPointF(180.0, 190.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        view.mousePressEvent(press)
        view.mouseMoveEvent(move)
        view.mouseReleaseEvent(release)

        assert view._particles[0].pinned is True
        assert view._particles[0].x == pytest.approx(180.0)
        assert view._particles[0].y == pytest.approx(190.0)
        assert clicked_tags == []

        # Simulation step keeps pinned node fixed
        view._step()
        assert view._particles[0].x == pytest.approx(180.0)
        assert view._particles[0].y == pytest.approx(190.0)


@pytest.mark.unit
@pytest.mark.gui
class TestTagCloudWidget:
    def test_initial_state_shows_placeholder(self, qtbot: pytest.FixtureRequest) -> None:
        widget = TagCloudWidget(db_manager=MagicMock())
        qtbot.addWidget(widget)
        assert widget._stack.currentIndex() == TagCloudWidget._PAGE_MESSAGE
        assert widget._status_label.text() == ""
        assert widget._selected_tags == []

    def test_keyword_builds_network(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._recompute()
        assert widget._stack.currentIndex() == TagCloudWidget._PAGE_NETWORK
        assert len(widget._network_view._particles) == 3
        assert "該当 8枚" in widget._status_label.text()
        assert "3ノード" in widget._status_label.text()

    def test_empty_result_shows_message(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _empty_graph())
        widget._keyword = "zzz"
        widget._recompute()
        assert widget._stack.currentIndex() == TagCloudWidget._PAGE_MESSAGE
        assert "該当する画像がありません" in widget._message_label.text()

    def test_empty_keyword_recompute_shows_placeholder(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "   "
        widget._recompute()
        assert widget._stack.currentIndex() == TagCloudWidget._PAGE_MESSAGE
        widget._service.build_graph.assert_not_called()

    def test_toggle_to_cloud_shows_cloud_page(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._recompute()
        widget._on_view_changed("cloud")
        assert widget._stack.currentIndex() == TagCloudWidget._PAGE_CLOUD
        labels = [widget._cloud_layout.itemAt(i).widget() for i in range(widget._cloud_layout.count())]
        assert all(isinstance(label, _TagCloudLabel) for label in labels)
        assert len(labels) == 3

    def test_tag_click_adds_chip_and_recomputes(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._recompute()
        widget._on_tag_clicked("smile")
        assert widget._selected_tags == ["smile"]
        widget._service.build_graph.assert_called_with("hair", ["smile"], max_nodes=34, min_edge_weight=2)

    def test_duplicate_tag_click_ignored(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._on_tag_clicked("smile")
        widget._on_tag_clicked("smile")
        assert widget._selected_tags == ["smile"]

    def test_chip_removed_recomputes(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._selected_tags = ["smile", "blush"]
        widget._on_chip_removed("smile")
        assert widget._selected_tags == ["blush"]

    def test_reset_clears_state(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword_edit.setText("hair")
        widget._selected_tags = ["smile"]
        widget._max_nodes_combo.setCurrentIndex(0)  # 15
        widget._min_edge_spin.setValue(5)
        widget._network_view._zoom = 2.0
        widget._network_view._pan_x = 40.0
        widget._on_reset()
        assert widget._keyword == ""
        assert widget._selected_tags == []
        assert widget._keyword_edit.text() == ""
        assert widget._max_nodes_combo.currentData() == 34
        assert widget._min_edge_spin.value() == 2
        assert widget._network_view._zoom == 1.0
        assert widget._network_view._pan_x == 0.0
        assert widget._stack.currentIndex() == TagCloudWidget._PAGE_MESSAGE

    def test_filter_controls_trigger_recompute(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._max_nodes_combo.setCurrentIndex(0)  # 15
        widget._service.build_graph.assert_called_with("hair", [], max_nodes=15, min_edge_weight=2)
        widget._min_edge_spin.setValue(4)
        widget._service.build_graph.assert_called_with("hair", [], max_nodes=15, min_edge_weight=4)

    def test_reload_refreshes_service(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._keyword = "hair"
        widget._on_reload()
        widget._service.refresh.assert_called_once()

    def test_keyword_change_resets_drilldown(self, qtbot: pytest.FixtureRequest) -> None:
        widget = _make_widget(qtbot, _sample_graph())
        widget._selected_tags = ["smile"]
        widget._on_keyword_changed("eyes")
        assert widget._keyword == "eyes"
        assert widget._selected_tags == []
