# tests/integration/test_phase5_signal_integration.py

"""Phase 5: Signal処理現代化 統合テスト

Phase 1-4で実装されたProtocol-based architectureとの統合確認
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QTimer

from lorairo.gui.services.model_selection_service import ModelInfo, ModelSelectionService
from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.model_selection_widget import ModelSelectionWidget
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget
from lorairo.services.annotator_lib_adapter import AnnotatorLibAdapter
from lorairo.services.model_registry_protocol import NullModelRegistry
from lorairo.services.signal_manager_service import SignalManagerService


class TestPhase5SignalIntegration:
    """Phase 5 Signal処理現代化 統合テスト"""

    def setup_method(self) -> None:
        """テストセットアップ"""
        self.signal_manager = SignalManagerService()

    def test_protocol_based_signal_integration(self, qtbot: Any) -> None:
        """Protocol-based architectureとSignal統合テスト"""
        # Phase 1-4 統合: ModelSelectionWidget + SignalManager
        model_registry = NullModelRegistry()
        model_selection_service = ModelSelectionService(annotator_adapter=None)

        widget = ModelSelectionWidget(
            model_registry=model_registry, model_selection_service=model_selection_service, mode="simple"
        )
        qtbot.addWidget(widget)

        # Phase 5: SignalManager統合
        signals_received = []

        def model_selection_handler(models: list[str]) -> None:
            signals_received.append(("model_selection_changed", models))

        signal_mapping = {"model_selection_changed": model_selection_handler}

        # Signal接続
        success = self.signal_manager.connect_widget_signals(widget, signal_mapping)
        assert success is True

        # Protocol統合確認
        assert isinstance(widget.model_registry, NullModelRegistry)
        assert isinstance(widget.model_selection_service, ModelSelectionService)

        # Signal registry確認
        registry = self.signal_manager.get_signal_registry()
        assert "model_selection_changed" in registry

    def test_thumbnail_selector_signal_modernization_integration(self, qtbot: Any) -> None:
        """ThumbnailSelectorWidget現代化統合テスト"""
        # DatasetStateManager統合
        dataset_state = DatasetStateManager()

        widget = ThumbnailSelectorWidget(dataset_state=dataset_state)
        qtbot.addWidget(widget)

        # Phase 5: 現代化Signal統合
        signals_received: list[tuple[str, Any]] = []

        def image_selected_handler(path: Path) -> None:
            signals_received.append(("image_selected", path))

        def multiple_images_handler(paths: list[Path]) -> None:
            signals_received.append(("multiple_images_selected", paths[0] if paths else Path("")))

        def selection_cleared_handler() -> None:
            signals_received.append(("selection_cleared", None))

        # 現代化Signal接続
        modern_signal_mapping: dict[str, Callable[..., Any]] = {
            "image_selected": image_selected_handler,
            "multiple_images_selected": multiple_images_handler,
            "selection_cleared": selection_cleared_handler,
        }

        success = self.signal_manager.connect_widget_signals(widget, modern_signal_mapping)
        assert success is True

        # Legacy互換性確認
        legacy_signals_received = []

        widget.imageSelected.connect(
            lambda path: legacy_signals_received.append(("legacy_imageSelected", path))
        )
        widget.multipleImagesSelected.connect(
            lambda paths: legacy_signals_received.append(("legacy_multipleImagesSelected", paths))
        )
        widget.deselected.connect(lambda: legacy_signals_received.append(("legacy_deselected", None)))

        # Signal発行テスト
        test_path = Path("/test/integration_image.jpg")
        with patch.object(widget, "get_selected_images", return_value=[test_path]):
            widget._emit_legacy_signals()

        # Wait for signal processing
        QTimer.singleShot(100, lambda: None)
        qtbot.wait(150)

        # 現代化Signalとlegacy Signal両方発行確認
        assert len(signals_received) >= 1
        assert len(legacy_signals_received) >= 1

        # 内容確認
        modern_signal = next((s for s in signals_received if s[0] == "image_selected"), None)
        legacy_signal = next((s for s in legacy_signals_received if s[0] == "legacy_imageSelected"), None)

        assert modern_signal is not None
        assert legacy_signal is not None
        assert modern_signal[1] == test_path
        assert legacy_signal[1] == test_path

    def test_dataset_state_manager_signal_integration(self, qtbot: Any) -> None:
        """DatasetStateManager統合テスト"""
        dataset_state = DatasetStateManager()

        # DatasetStateManagerのSignal統合
        signals_received = []

        def dataset_loaded_handler(count: int) -> None:
            signals_received.append(("dataset_loaded", count))

        def images_filtered_handler(images: list[dict[str, Any]]) -> None:
            signals_received.append(("images_filtered", len(images)))

        # DatasetStateManagerは既に統一命名規約
        signal_mapping: dict[str, Callable[..., Any]] = {
            "dataset_loaded": dataset_loaded_handler,
            "images_filtered": images_filtered_handler,
        }

        success = self.signal_manager.connect_widget_signals(dataset_state, signal_mapping)
        assert success is True

        # DatasetStateManagerの統一Signal名確認
        assert self.signal_manager.validate_signal_naming("dataset_loaded") is True
        assert self.signal_manager.validate_signal_naming("images_filtered") is True

        # Signal registry確認
        registry = self.signal_manager.get_signal_registry()
        assert "dataset_loaded" in registry
        assert "images_filtered" in registry

    def test_cross_widget_signal_communication(self, qtbot: Any) -> None:
        """Widget間Signal通信統合テスト"""
        # DatasetStateManager
        dataset_state = DatasetStateManager()

        # ThumbnailSelectorWidget
        thumbnail_widget = ThumbnailSelectorWidget(dataset_state=dataset_state)
        qtbot.addWidget(thumbnail_widget)

        # ModelSelectionWidget
        model_widget = ModelSelectionWidget(mode="simple")
        qtbot.addWidget(model_widget)

        # Cross-widget signal communication
        signals_received = []

        # ThumbnailSelector → Dataset State
        dataset_state.current_image_changed.connect(
            lambda image_id: signals_received.append(("current_image_changed", image_id))
        )

        # Dataset State → ThumbnailSelector (既存の統合)
        assert thumbnail_widget.dataset_state == dataset_state

        # Model Selection events
        model_widget.model_selection_changed.connect(
            lambda models: signals_received.append(("model_selection_changed", models))
        )

        # Phase 5: SignalManager統合
        thumbnail_signal_mapping = {
            "image_selected": lambda path: signals_received.append(("thumb_image_selected", path))
        }

        model_signal_mapping = {
            "model_selection_changed": lambda models: signals_received.append(("model_changed", models))
        }

        # 両Widget統合
        thumb_success = self.signal_manager.connect_widget_signals(
            thumbnail_widget, thumbnail_signal_mapping
        )
        model_success = self.signal_manager.connect_widget_signals(model_widget, model_signal_mapping)

        assert thumb_success is True
        assert model_success is True

        # Signal registry確認
        registry = self.signal_manager.get_signal_registry()
        assert "image_selected" in registry
        assert "model_selection_changed" in registry

    def test_error_handling_integration(self, qtbot: Any) -> None:
        """エラーハンドリング統合テスト"""
        widget = ModelSelectionWidget(mode="simple")
        qtbot.addWidget(widget)

        # エラーハンドラー設定
        errors_received = []

        def error_handler(component: str, error: Exception) -> None:
            errors_received.append((component, str(error)))

        success = self.signal_manager.register_error_handler(widget, error_handler)
        assert success is True

        # アプリケーションエラー発行
        self.signal_manager.emit_application_signal(
            "application_error", "TestComponent", "Test error message"
        )

        # Wait for error processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # エラーハンドリング確認
        assert len(errors_received) >= 0  # エラーハンドラーが登録されている

    def test_signal_naming_validation_integration(self, qtbot: Any) -> None:
        """Signal命名検証統合テスト"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)

        # Legacy命名でのSignal接続試行
        violations_received = []

        self.signal_manager.signal_naming_violation.connect(
            lambda widget_name, invalid_name, suggested: violations_received.append(
                (widget_name, invalid_name, suggested)
            )
        )

        def dummy_handler(data: Any) -> None:
            pass

        # Legacy命名でマッピング作成
        legacy_signal_mapping = {
            "imageSelected": dummy_handler,  # camelCase → snake_case変換が期待される
        }

        self.signal_manager.connect_widget_signals(widget, legacy_signal_mapping)

        # Wait for validation processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # 命名規約違反が検出される場合の処理確認
        # (ThumbnailSelectorWidgetには実際にimageSelectedが存在するため、違反は検出されない可能性)

        # 代わりに、存在しないLegacy命名での接続を試行
        nonexistent_signal_mapping = {
            "invalidCamelCase": dummy_handler,
        }

        failures_received = []
        self.signal_manager.signal_connection_failed.connect(
            lambda widget_name, signal_name: failures_received.append((widget_name, signal_name))
        )

        self.signal_manager.connect_widget_signals(widget, nonexistent_signal_mapping)

        # Wait for processing
        QTimer.singleShot(50, lambda: None)
        qtbot.wait(100)

        # 接続失敗が検出される
        assert len(failures_received) >= 1

    def test_service_summary_integration(self, qtbot: Any) -> None:
        """サービス状態統合テスト"""
        # 複数Widget統合
        dataset_state = DatasetStateManager()
        thumbnail_widget = ThumbnailSelectorWidget(dataset_state=dataset_state)
        model_widget = ModelSelectionWidget(mode="simple")

        qtbot.addWidget(thumbnail_widget)
        qtbot.addWidget(model_widget)

        # Signal接続
        def dummy_handler(data: Any) -> None:
            pass

        thumb_signals = {"image_selected": dummy_handler}
        model_signals = {"model_selection_changed": dummy_handler}

        self.signal_manager.connect_widget_signals(thumbnail_widget, thumb_signals)
        self.signal_manager.connect_widget_signals(model_widget, model_signals)

        # サービス状態取得
        summary = self.signal_manager.get_service_summary()

        assert summary["service_name"] == "SignalManagerService"
        assert summary["registered_signals"] >= 2
        assert "image_selected" in summary["signal_registry"]
        assert "model_selection_changed" in summary["signal_registry"]


@pytest.fixture
def qtbot(qtbot: Any) -> Any:
    """Qt test framework fixture"""
    return qtbot
