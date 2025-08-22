# src/lorairo/services/signal_manager_service.py

"""統一Signal管理サービス実装

Phase 5: Signal処理現代化の中核実装。
既存の優れたSignalアーキテクチャを活用しつつ、Protocol-based統合を提供。
"""

import re
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

from ..utils.log import logger
from .signal_manager_protocol import (
    SignalNamingStandard,
)


class SignalNameValidator:
    """Signal命名検証実装"""

    def __init__(self) -> None:
        self.patterns = [
            re.compile(SignalNamingStandard.PATTERN_ACTION_PAST),
            re.compile(SignalNamingStandard.PATTERN_ERROR),
            re.compile(SignalNamingStandard.PATTERN_STATE),
            re.compile(SignalNamingStandard.PATTERN_EVENT),
        ]

    def is_valid_signal_name(self, name: str) -> bool:
        """Signal名妥当性検証"""
        return any(pattern.match(name) for pattern in self.patterns)

    def suggest_corrected_name(self, name: str) -> str:
        """Signal名修正提案"""
        # Legacy → Modern 変換
        if name in SignalNamingStandard.LEGACY_TO_MODERN_MAPPING:
            return SignalNamingStandard.LEGACY_TO_MODERN_MAPPING[name]

        # camelCase → snake_case 変換
        snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

        # 推奨Suffixチェック
        for suffix in SignalNamingStandard.RECOMMENDED_SUFFIXES:
            if snake_case.endswith(suffix):
                return snake_case

        # デフォルト提案
        return f"{snake_case}_changed"


class SignalManagerService(QObject):
    """統一Signal管理サービス実装

    Phase 5現代化の中核として、以下を提供：
    - 統一Signal命名規約強制
    - Protocol-based依存注入対応
    - エラーハンドリング標準化
    - 既存アーキテクチャ活用
    """

    # === アプリケーション全体Signal ===
    application_error = Signal(str, str)  # component_name, error_message
    signal_connection_failed = Signal(str, str)  # widget_name, signal_name
    signal_naming_violation = Signal(str, str, str)  # widget_name, invalid_name, suggested_name

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self.validator = SignalNameValidator()
        self.signal_registry: dict[str, list[QObject]] = {}
        self.error_handlers: dict[QObject, Callable[[str, Exception], None]] = {}

        logger.debug("SignalManagerService initialized")

    def connect_widget_signals(
        self, widget: QObject, signal_mapping: dict[str, Callable[..., Any]]
    ) -> bool:
        """WidgetのSignal統一接続"""
        try:
            widget_name = widget.__class__.__name__
            logger.debug(f"Connecting signals for {widget_name}")

            success_count = 0
            total_signals = len(signal_mapping)

            for signal_name, handler in signal_mapping.items():
                try:
                    # 命名規約検証
                    if not self.validator.is_valid_signal_name(signal_name):
                        suggested = self.validator.suggest_corrected_name(signal_name)
                        logger.warning(
                            f"Signal命名規約違反: {widget_name}.{signal_name} → 提案: {suggested}"
                        )
                        self.signal_naming_violation.emit(widget_name, signal_name, suggested)

                        # 提案名でリトライ
                        if hasattr(widget, suggested):
                            signal_name = suggested

                    # Signal接続
                    if hasattr(widget, signal_name):
                        signal = getattr(widget, signal_name)
                        signal.connect(handler)

                        # レジストリ登録
                        if signal_name not in self.signal_registry:
                            self.signal_registry[signal_name] = []
                        self.signal_registry[signal_name].append(widget)

                        success_count += 1
                        logger.debug(f"Connected: {widget_name}.{signal_name}")
                    else:
                        logger.error(f"Signal not found: {widget_name}.{signal_name}")
                        self.signal_connection_failed.emit(widget_name, signal_name)

                except Exception as e:
                    logger.error(f"Failed to connect {widget_name}.{signal_name}: {e}")
                    self.signal_connection_failed.emit(widget_name, signal_name)

            success_rate = success_count / total_signals if total_signals > 0 else 0
            logger.info(
                f"Signal接続完了 {widget_name}: {success_count}/{total_signals} ({success_rate:.1%} 成功)"
            )

            return success_count == total_signals

        except Exception as e:
            logger.error(f"Widget signal connection failed: {e}")
            self.application_error.emit(widget.__class__.__name__, str(e))
            return False

    def emit_application_signal(self, signal_name: str, *args: Any) -> bool:
        """アプリケーション全体Signal発行"""
        try:
            # 命名規約検証
            if not self.validator.is_valid_signal_name(signal_name):
                suggested = self.validator.suggest_corrected_name(signal_name)
                logger.warning(f"Signal命名規約違反: {signal_name} → 提案: {suggested}")
                return False

            # Signalが存在するかチェック
            if hasattr(self, signal_name):
                signal = getattr(self, signal_name)
                signal.emit(*args)
                logger.debug(f"Application signal emitted: {signal_name}")
                return True
            else:
                logger.error(f"Application signal not found: {signal_name}")
                return False

        except Exception as e:
            logger.error(f"Failed to emit application signal {signal_name}: {e}")
            self.application_error.emit("SignalManagerService", str(e))
            return False

    def register_error_handler(
        self, widget: QObject, error_handler: Callable[[str, Exception], None]
    ) -> bool:
        """統一エラーハンドラー登録"""
        try:
            self.error_handlers[widget] = error_handler

            # アプリケーションエラーSignalに接続
            self.application_error.connect(
                lambda component, message: error_handler(component, Exception(message))
            )

            widget_name = widget.__class__.__name__
            logger.debug(f"Error handler registered for {widget_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to register error handler: {e}")
            return False

    def validate_signal_naming(self, signal_name: str) -> bool:
        """Signal命名規約検証"""
        return self.validator.is_valid_signal_name(signal_name)

    def get_signal_registry(self) -> dict[str, list[QObject]]:
        """登録済みSignal一覧取得"""
        return self.signal_registry.copy()

    # === ユーティリティメソッド ===

    def migrate_legacy_signals(self, widget: QObject) -> dict[str, str]:
        """LegacySignal → Modern変換マッピング作成

        Args:
            widget: 対象Widget

        Returns:
            dict: legacy_name → modern_name のマッピング
        """
        migrations: dict[str, str] = {}

        for attr_name in dir(widget):
            if hasattr(widget, attr_name):
                attr = getattr(widget, attr_name)
                if isinstance(attr, Signal):
                    if attr_name in SignalNamingStandard.LEGACY_TO_MODERN_MAPPING:
                        modern_name = SignalNamingStandard.LEGACY_TO_MODERN_MAPPING[attr_name]
                        migrations[attr_name] = modern_name

                    elif not self.validator.is_valid_signal_name(attr_name):
                        suggested = self.validator.suggest_corrected_name(attr_name)
                        migrations[attr_name] = suggested

        return migrations

    def create_legacy_compatibility_wrapper(
        self, widget: QObject, legacy_name: str, modern_name: str
    ) -> bool:
        """Legacy互換性ラッパー作成

        既存コードの互換性を保ちながら、現代的Signalへの移行を支援
        """
        try:
            if hasattr(widget, modern_name) and hasattr(widget, legacy_name):
                modern_signal = getattr(widget, modern_name)
                legacy_signal = getattr(widget, legacy_name)

                # Legacy → Modern転送
                legacy_signal.connect(modern_signal.emit)

                logger.debug(f"Legacy compatibility wrapper created: {legacy_name} → {modern_name}")
                return True

        except Exception as e:
            logger.error(f"Failed to create compatibility wrapper: {e}")

        return False

    def get_service_summary(self) -> dict[str, Any]:
        """サービス状態サマリー取得"""
        return {
            "service_name": "SignalManagerService",
            "registered_signals": len(self.signal_registry),
            "registered_widgets": len(self.error_handlers),
            "signal_registry": {signal: len(objects) for signal, objects in self.signal_registry.items()},
        }
