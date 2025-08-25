# tests/unit/gui/widgets/test_thumbnail_selector_signal_modernization.py

"""ThumbnailSelectorWidget Signal現代化テスト

Phase 5: Signal処理現代化の具体的実装テスト
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget


class TestThumbnailSelectorSignalModernization:
    """ThumbnailSelectorWidget Signal現代化テスト"""

    def setup_method(self) -> None:
        """テストセットアップ"""
        self.dataset_state = Mock(spec=DatasetStateManager)

    def test_modern_signals_exist(self, qtbot: Any) -> None:
        """統一現代化Signalの存在確認テスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        # 統一現代化Signal確認
        assert hasattr(widget, "image_selected")
        assert hasattr(widget, "multiple_images_selected")
        assert hasattr(widget, "selection_cleared")

        # Legacy Signalが削除されていることを確認
        assert not hasattr(widget, "imageSelected")
        assert not hasattr(widget, "multipleImagesSelected")
        assert not hasattr(widget, "deselected")

    def test_modern_signal_emission(self, qtbot: Any) -> None:
        """現代化Signal発行テスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        # 現代化Signal接続テスト
        signals_received = []

        widget.image_selected.connect(lambda path: signals_received.append(("image_selected", path)))
        widget.multiple_images_selected.connect(
            lambda paths: signals_received.append(("multiple_images_selected", paths))
        )
        widget.selection_cleared.connect(lambda: signals_received.append(("selection_cleared", None)))

        # Mock selected images
        test_path = Path("/test/image.jpg")
        with patch.object(widget, "get_selected_images", return_value=[test_path]):
            widget._emit_selection_signals()

        # Wait for signal processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # 現代化Signalが発行されることを確認
        assert len(signals_received) == 1
        assert signals_received[0] == ("image_selected", test_path)

    def test_multiple_images_signal_emission(self, qtbot: Any) -> None:
        """複数画像選択Signalテスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        # Signal受信記録
        signals_received = []

        widget.multiple_images_selected.connect(lambda paths: signals_received.append(("modern", paths)))

        # 複数画像選択をシミュレート
        test_paths = [Path("/test/image1.jpg"), Path("/test/image2.jpg")]
        with patch.object(widget, "get_selected_images", return_value=test_paths):
            widget._emit_selection_signals()

        # Wait for signal processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # 現代化Signalが発行されることを確認
        assert len(signals_received) == 1

        # 内容確認
        modern_signal = signals_received[0]
        assert modern_signal[0] == "modern"
        assert modern_signal[1] == test_paths

    def test_selection_cleared_signal_emission(self, qtbot: Any) -> None:
        """選択クリアSignalテスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        # Signal受信記録
        signals_received = []

        widget.selection_cleared.connect(lambda: signals_received.append("modern_cleared"))

        # 選択なしをシミュレート
        with patch.object(widget, "get_selected_images", return_value=[]):
            widget._emit_selection_signals()

        # Wait for signal processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # 現代化Signalが発行されることを確認
        assert "modern_cleared" in signals_received

    def test_signal_naming_consistency(self, qtbot: Any) -> None:
        """Signal命名一貫性テスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        # 統一現代化Signalは統一snake_case命名規約に準拠
        modern_signals = ["image_selected", "multiple_images_selected", "selection_cleared"]
        for signal_name in modern_signals:
            assert hasattr(widget, signal_name)
            signal = getattr(widget, signal_name)
            assert hasattr(signal, "emit")  # 実際にSignalオブジェクトか確認

        # Legacy Signalが削除されていることを確認
        legacy_signals = ["imageSelected", "multipleImagesSelected", "deselected"]
        for signal_name in legacy_signals:
            assert not hasattr(widget, signal_name)

    def test_dataset_state_integration_with_modern_signals(self, qtbot: Any) -> None:
        """DatasetStateManager統合と現代化Signalテスト"""
        # Mock DatasetStateManager
        mock_dataset_state = Mock(spec=DatasetStateManager)

        widget = ThumbnailSelectorWidget(dataset_state=mock_dataset_state)
        qtbot.addWidget(widget)

        # DatasetStateManagerとの統合確認
        assert widget.dataset_state == mock_dataset_state

        # 現代化Signalが適切に動作することを確認
        signals_received = []
        widget.image_selected.connect(lambda path: signals_received.append(path))

        # Mock selection and emit
        test_path = Path("/test/integrated_image.jpg")
        with patch.object(widget, "get_selected_images", return_value=[test_path]):
            widget._emit_selection_signals()

        # Wait for signal processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # Signal発行確認
        assert len(signals_received) == 1
        assert signals_received[0] == test_path

    @pytest.mark.parametrize(
        "selection_count,expected_signal",
        [
            (0, "selection_cleared"),
            (1, "image_selected"),
            (3, "multiple_images_selected"),
            (10, "multiple_images_selected"),
        ],
    )
    def test_signal_emission_by_selection_count(
        self, qtbot: Any, selection_count: int, expected_signal: str
    ) -> None:
        """選択数によるSignal発行パターンテスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        # Signal受信記録
        signals_received = []

        widget.image_selected.connect(lambda path: signals_received.append("image_selected"))
        widget.multiple_images_selected.connect(
            lambda paths: signals_received.append("multiple_images_selected")
        )
        widget.selection_cleared.connect(lambda: signals_received.append("selection_cleared"))

        # 選択状態をシミュレート
        test_paths = [Path(f"/test/image{i}.jpg") for i in range(selection_count)]
        with patch.object(widget, "get_selected_images", return_value=test_paths):
            widget._emit_selection_signals()

        # Wait for signal processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # 期待されるSignalが発行されることを確認
        assert expected_signal in signals_received

    def test_signal_thread_safety(self, qtbot: Any) -> None:
        """Signal発行のスレッドセーフティテスト"""
        widget = ThumbnailSelectorWidget(dataset_state=self.dataset_state)
        qtbot.addWidget(widget)

        signals_received = []
        widget.image_selected.connect(lambda path: signals_received.append(path))

        # 複数回の迅速なSignal発行
        test_path = Path("/test/thread_safe_image.jpg")
        with patch.object(widget, "get_selected_images", return_value=[test_path]):
            for _ in range(5):
                widget._emit_selection_signals()

        # Wait for all signals to be processed
        QTimer.singleShot(100, lambda: None)
        qtbot.wait(150)

        # すべてのSignalが適切に処理されることを確認
        assert len(signals_received) == 5
        assert all(path == test_path for path in signals_received)


@pytest.fixture
def qtbot(qtbot: Any) -> Any:
    """Qt test framework fixture"""
    return qtbot
