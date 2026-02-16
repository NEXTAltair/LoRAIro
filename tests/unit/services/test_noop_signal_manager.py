"""NoOpSignalManager の単体テスト"""

import pytest

from lorairo.services.noop_signal_manager import NoOpSignalManager


@pytest.mark.unit
class TestNoOpSignalManager:
    """NoOpSignalManager のテストクラス"""

    @pytest.fixture
    def manager(self) -> NoOpSignalManager:
        """NoOpSignalManager インスタンスを提供"""
        return NoOpSignalManager()

    def test_init(self) -> None:
        """初期化成功"""
        manager = NoOpSignalManager()
        assert manager is not None

    def test_connect_widget_signals_returns_true(self, manager: NoOpSignalManager) -> None:
        """connect_widget_signals は常に True を返す"""
        class MockWidget:
            pass

        widget = MockWidget()
        signal_mapping = {"test_signal": lambda: None}

        result = manager.connect_widget_signals(widget, signal_mapping)
        assert result is True

    def test_emit_application_signal_returns_true(self, manager: NoOpSignalManager) -> None:
        """emit_application_signal は常に True を返す"""
        result = manager.emit_application_signal("test_signal", "arg1", "arg2")
        assert result is True

    def test_register_error_handler_returns_true(self, manager: NoOpSignalManager) -> None:
        """register_error_handler は常に True を返す"""
        class MockWidget:
            pass

        widget = MockWidget()

        def error_handler(component: str, error: Exception) -> None:
            pass

        result = manager.register_error_handler(widget, error_handler)
        assert result is True

    def test_validate_signal_naming_returns_true(self, manager: NoOpSignalManager) -> None:
        """validate_signal_naming は常に True を返す"""
        result = manager.validate_signal_naming("any_signal_name")
        assert result is True

    def test_get_signal_registry_returns_empty_dict(self, manager: NoOpSignalManager) -> None:
        """get_signal_registry は空の辞書を返す"""
        result = manager.get_signal_registry()
        assert result == {}
        assert isinstance(result, dict)

    def test_multiple_operations_sequence(self, manager: NoOpSignalManager) -> None:
        """複数操作の実行シーケンス"""
        class MockWidget:
            pass

        widget = MockWidget()

        # シーケンス実行
        assert manager.validate_signal_naming("signal_1") is True
        assert manager.connect_widget_signals(widget, {"signal_1": lambda: None}) is True
        assert manager.emit_application_signal("signal_2") is True
        assert manager.register_error_handler(widget, lambda c, e: None) is True
        assert manager.get_signal_registry() == {}

    def test_noop_with_none_widget(self, manager: NoOpSignalManager) -> None:
        """None を Widget として渡す"""
        result = manager.connect_widget_signals(None, {})  # type: ignore[arg-type]
        assert result is True

    def test_noop_with_empty_mapping(self, manager: NoOpSignalManager) -> None:
        """空のシグナルマッピングを渡す"""
        class MockWidget:
            pass

        widget = MockWidget()
        result = manager.connect_widget_signals(widget, {})
        assert result is True

    def test_noop_protocol_compliance(self, manager: NoOpSignalManager) -> None:
        """SignalManagerServiceProtocol への準拠確認"""
        # Protocol で定義されたすべてのメソッドが存在し、呼び出し可能なことを確認
        assert hasattr(manager, "connect_widget_signals")
        assert hasattr(manager, "emit_application_signal")
        assert hasattr(manager, "register_error_handler")
        assert hasattr(manager, "validate_signal_naming")
        assert hasattr(manager, "get_signal_registry")

        # すべてのメソッドが callable であることを確認
        assert callable(getattr(manager, "connect_widget_signals"))
        assert callable(getattr(manager, "emit_application_signal"))
        assert callable(getattr(manager, "register_error_handler"))
        assert callable(getattr(manager, "validate_signal_naming"))
        assert callable(getattr(manager, "get_signal_registry"))
