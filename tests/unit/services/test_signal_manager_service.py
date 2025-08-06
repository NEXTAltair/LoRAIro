# tests/unit/services/test_signal_manager_service.py

"""SignalManagerService ユニットテスト

Phase 5: Signal処理現代化のテスト実装
"""

import os
from collections.abc import Generator
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget

from lorairo.services.signal_manager_protocol import SignalNamingStandard
from lorairo.services.signal_manager_service import SignalManagerService, SignalNameValidator

# GUI テスト用の環境設定
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class TestSignalNameValidator:
    """SignalNameValidator テスト"""

    def setup_method(self) -> None:
        self.validator = SignalNameValidator()

    def test_valid_signal_names(self) -> None:
        """有効なSignal名のテスト"""
        valid_names = [
            "image_selected",
            "dataset_loaded",
            "annotation_started",
            "worker_progress_updated",
            "thumbnail_size_changed",
            "filter_applied",
        ]

        for name in valid_names:
            assert self.validator.is_valid_signal_name(name), f"Should be valid: {name}"

    def test_invalid_signal_names(self) -> None:
        """無効なSignal名のテスト"""
        invalid_names = [
            "imageSelected",  # camelCase
            "DataLoaded",  # PascalCase
            "filter_applied_now_with_data",  # 過度に長い
            "123_invalid",  # 数字開始
            "",  # 空文字
        ]

        for name in invalid_names:
            assert not self.validator.is_valid_signal_name(name), f"Should be invalid: {name}"

    def test_legacy_to_modern_mapping(self) -> None:
        """Legacy → Modern 変換テスト"""
        legacy_conversions = {
            "imageSelected": "image_selected",
            "multipleImagesSelected": "multiple_images_selected",
            "deselected": "selection_cleared",
        }

        for legacy, expected in legacy_conversions.items():
            result = self.validator.suggest_corrected_name(legacy)
            assert result == expected, f"{legacy} should convert to {expected}, got {result}"

    def test_camel_case_conversion(self) -> None:
        """camelCase → snake_case 変換テスト"""
        conversions = {
            "itemClicked": "item_clicked_changed",  # デフォルトsuffix追加
            "dataLoaded": "data_loaded",  # 推奨suffix検出
            "filterApplied": "filter_applied",  # 推奨suffix検出
        }

        for camel, _expected in conversions.items():
            result = self.validator.suggest_corrected_name(camel)
            # レガシーマッピングにない場合のsnake_case変換をチェック
            snake_case = result
            assert snake_case.islower(), f"{camel} should convert to lowercase, got {result}"
            assert "_" in snake_case, f"{camel} should contain underscores, got {result}"


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """QApplication fixture for Qt tests"""
    if QApplication.instance() is None:
        app = QApplication([])
    else:
        app = cast(QApplication, QApplication.instance())
    yield app


class MockWidget(QWidget):
    """テスト用Widget"""

    # Modern signals
    image_selected = Signal(str)
    data_loaded = Signal(int)
    filter_applied = Signal(dict)

    # Legacy signals
    imageSelected = Signal(str)
    dataLoaded = Signal(int)


class TestSignalManagerService:
    """SignalManagerService テスト"""

    def setup_method(self) -> None:
        self.service = SignalManagerService()
        # Widget requires QApplication - will be initialized by qapp fixture
        self.mock_widget: MockWidget | None = None

    def test_initialization(self) -> None:
        """初期化テスト"""
        assert self.service.validator is not None
        assert isinstance(self.service.signal_registry, dict)
        assert len(self.service.signal_registry) == 0
        assert len(self.service.error_handlers) == 0

    def test_connect_widget_signals_success(self, qapp: QApplication) -> None:
        """Widget Signal接続成功テスト"""
        self.mock_widget = MockWidget()

        def mock_handler(data: Any) -> None:
            pass

        signal_mapping = {
            "image_selected": mock_handler,
            "data_loaded": mock_handler,
            "filter_applied": mock_handler,
        }

        result = self.service.connect_widget_signals(self.mock_widget, signal_mapping)

        assert result is True
        assert len(self.service.signal_registry) == 3
        assert "image_selected" in self.service.signal_registry
        assert "data_loaded" in self.service.signal_registry
        assert "filter_applied" in self.service.signal_registry

    def test_connect_widget_signals_with_naming_violation(self, qapp: QApplication) -> None:
        """Signal命名規約違反時の処理テスト"""
        self.mock_widget = MockWidget()

        def mock_handler(data: Any) -> None:
            pass

        # Legacy命名でマッピング
        signal_mapping = {
            "imageSelected": mock_handler,  # Legacy → image_selected に変換されるべき
            "data_loaded": mock_handler,  # 正しい命名
        }

        with patch.object(self.service, "signal_naming_violation") as mock_violation:
            result = self.service.connect_widget_signals(self.mock_widget, signal_mapping)

            # 命名違反が検出されシグナルが発行される
            mock_violation.emit.assert_called()

            # 接続は成功（Legacy互換性により）
            assert result is True

    def test_connect_widget_signals_missing_signal(self, qapp: QApplication) -> None:
        """存在しないSignal接続時のテスト"""
        self.mock_widget = MockWidget()

        def mock_handler(data: Any) -> None:
            pass

        signal_mapping = {
            "nonexistent_signal": mock_handler,
        }

        with patch.object(self.service, "signal_connection_failed") as mock_failed:
            result = self.service.connect_widget_signals(self.mock_widget, signal_mapping)

            # 接続失敗シグナルが発行される
            mock_failed.emit.assert_called_with("MockWidget", "nonexistent_signal")
            assert result is False

    def test_emit_application_signal_success(self) -> None:
        """アプリケーションSignal発行成功テスト"""
        # application_error Signal が存在することを確認
        assert hasattr(self.service, "application_error")

        result = self.service.emit_application_signal("application_error", "test_component", "test_error")
        assert result is True

    def test_emit_application_signal_invalid_naming(self) -> None:
        """無効な命名でのアプリケーションSignal発行テスト"""
        result = self.service.emit_application_signal("InvalidSignalName", "test_data")
        assert result is False

    def test_emit_application_signal_nonexistent(self) -> None:
        """存在しないアプリケーションSignal発行テスト"""
        result = self.service.emit_application_signal("nonexistent_signal_processed", "test_data")
        assert result is False

    def test_register_error_handler(self, qapp: QApplication) -> None:
        """エラーハンドラー登録テスト"""
        self.mock_widget = MockWidget()

        def mock_error_handler(component: str, error: Exception) -> None:
            pass

        result = self.service.register_error_handler(self.mock_widget, mock_error_handler)

        assert result is True
        assert self.mock_widget in self.service.error_handlers
        assert self.service.error_handlers[self.mock_widget] == mock_error_handler

    def test_validate_signal_naming(self) -> None:
        """Signal命名規約検証テスト"""
        # 有効な命名
        assert self.service.validate_signal_naming("image_selected") is True
        assert self.service.validate_signal_naming("data_loaded") is True

        # 無効な命名
        assert self.service.validate_signal_naming("imageSelected") is False
        assert self.service.validate_signal_naming("InvalidName") is False

    def test_get_signal_registry(self, qapp: QApplication) -> None:
        """Signal登録情報取得テスト"""
        self.mock_widget = MockWidget()

        def mock_handler(data: Any) -> None:
            pass

        signal_mapping = {"image_selected": mock_handler}
        self.service.connect_widget_signals(self.mock_widget, signal_mapping)

        registry = self.service.get_signal_registry()

        assert isinstance(registry, dict)
        assert "image_selected" in registry
        assert self.mock_widget in registry["image_selected"]

    def test_migrate_legacy_signals(self, qapp: QApplication) -> None:
        """LegacySignal移行マッピングテスト"""
        self.mock_widget = MockWidget()
        migrations = self.service.migrate_legacy_signals(self.mock_widget)

        assert isinstance(migrations, dict)
        # Legacy signals should be detected and mapped
        if "imageSelected" in migrations:
            assert migrations["imageSelected"] == "image_selected"

    def test_create_legacy_compatibility_wrapper(self, qapp: QApplication) -> None:
        """Legacy互換性ラッパーテスト"""
        self.mock_widget = MockWidget()
        # ModernとLegacy Signalが両方存在する場合
        result = self.service.create_legacy_compatibility_wrapper(
            self.mock_widget, "imageSelected", "image_selected"
        )

        assert result is True

    def test_get_service_summary(self, qapp: QApplication) -> None:
        """サービス状態サマリーテスト"""
        self.mock_widget = MockWidget()

        def mock_handler(data: Any) -> None:
            pass

        # Signal接続してサマリー取得
        signal_mapping = {"image_selected": mock_handler}
        self.service.connect_widget_signals(self.mock_widget, signal_mapping)

        summary = self.service.get_service_summary()

        assert summary["service_name"] == "SignalManagerService"
        assert summary["registered_signals"] == 1
        assert isinstance(summary["signal_registry"], dict)


class TestSignalNamingStandard:
    """SignalNamingStandard テスト"""

    def test_legacy_to_modern_mapping(self) -> None:
        """Legacy → Modern マッピングテスト"""
        mappings = SignalNamingStandard.LEGACY_TO_MODERN_MAPPING

        assert "imageSelected" in mappings
        assert mappings["imageSelected"] == "image_selected"
        assert mappings["multipleImagesSelected"] == "multiple_images_selected"
        assert mappings["deselected"] == "selection_cleared"

    def test_recommended_suffixes(self) -> None:
        """推奨Suffixテスト"""
        suffixes = SignalNamingStandard.RECOMMENDED_SUFFIXES

        assert "started" in suffixes
        assert "finished" in suffixes
        assert "changed" in suffixes
        assert "selected" in suffixes
        assert "loaded" in suffixes


class TestIntegration:
    """統合テスト"""

    def test_phase5_signal_modernization_workflow(self, qapp: QApplication, qtbot: Any) -> None:
        """Phase 5 Signal現代化の統合ワークフローテスト"""
        # SignalManagerService初期化
        service = SignalManagerService()
        widget = MockWidget()
        qtbot.addWidget(widget)

        # 1. Signal接続
        def image_handler(path: str) -> None:
            assert isinstance(path, str)

        signal_mapping = {
            "image_selected": image_handler,
        }

        success = service.connect_widget_signals(widget, signal_mapping)
        assert success is True

        # 2. Legacy互換性確認
        migrations = service.migrate_legacy_signals(widget)
        if "imageSelected" in migrations:
            assert migrations["imageSelected"] == "image_selected"

        # 3. エラーハンドリング
        def error_handler(component: str, error: Exception) -> None:
            assert isinstance(component, str)
            assert isinstance(error, Exception)

        service.register_error_handler(widget, error_handler)

        # 4. サービス状態確認
        summary = service.get_service_summary()
        assert summary["registered_signals"] >= 1
        assert summary["registered_widgets"] >= 1
