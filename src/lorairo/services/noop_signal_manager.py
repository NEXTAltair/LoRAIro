# src/lorairo/services/noop_signal_manager.py
"""CLI環境用 No-Operation Signal Manager実装

Signal管理が不要なCLI環境向けに、SignalManagerServiceProtocol
を実装したNoOp（No-Operation）バージョンを提供します。
"""

from collections.abc import Callable
from typing import Any

from .signal_manager_protocol import SignalManagerServiceProtocol
from ..utils.log import logger


class NoOpSignalManager:
    """CLI用 No-Operation Signal Manager

    QObject や Signal への依存なしに、SignalManagerServiceProtocol
    のインターフェースを提供します。すべての操作は正常に完了しますが、
    実際の処理は行われません（No-Operation）。

    用途:
    - CLI環境での実行
    - テスト環境でのSignal処理回避
    """

    def __init__(self) -> None:
        """NoOpSignalManagerを初期化します。"""
        logger.debug("NoOpSignalManager initialized (CLI mode)")

    def connect_widget_signals(
        self, widget: Any, signal_mapping: dict[str, Callable[..., Any]]
    ) -> bool:
        """Widget Signal接続（NoOp）

        Args:
            widget: 接続対象Widget（無視される）
            signal_mapping: Signal名→ハンドラー関数のマッピング（無視される）

        Returns:
            bool: 常にTrue（成功）

        Note:
            CLI環境ではSignalが存在しないため、実装なし。
        """
        widget_name = getattr(widget, "__class__", object).__name__ if hasattr(widget, "__class__") else "Unknown"
        logger.debug("NoOp: connect_widget_signals called (widget={})", widget_name)
        return True

    def emit_application_signal(self, signal_name: str, *args: Any) -> bool:
        """アプリケーション全体Signal発行（NoOp）

        Args:
            signal_name: 統一規約に従ったSignal名
            *args: Signalペイロード（無視される）

        Returns:
            bool: 常にTrue（成功）

        Note:
            CLI環境ではSignalが不要なため、実装なし。
        """
        logger.debug("NoOp: emit_application_signal called (signal_name={})", signal_name)
        return True

    def register_error_handler(
        self, widget: Any, error_handler: Callable[[str, Exception], None]
    ) -> bool:
        """Widget用統一エラーハンドラー登録（NoOp）

        Args:
            widget: 対象Widget（無視される）
            error_handler: エラーハンドラー関数（無視される）

        Returns:
            bool: 常にTrue（成功）

        Note:
            CLI環境ではWidget Signalが存在しないため、実装なし。
        """
        logger.debug("NoOp: register_error_handler called")
        return True

    def validate_signal_naming(self, signal_name: str) -> bool:
        """Signal命名規約検証（NoOp）

        Args:
            signal_name: 検証対象Signal名（常に有効と判定）

        Returns:
            bool: 常にTrue（有効）

        Note:
            CLI環境ではSignal検証が不要なため、常に True を返す。
        """
        logger.debug("NoOp: validate_signal_naming called (signal_name={})", signal_name)
        return True

    def get_signal_registry(self) -> dict[str, list[Any]]:
        """登録済みSignal一覧取得（NoOp）

        Returns:
            dict: 常に空の辞書（CLI環境ではSignalが登録されない）
        """
        logger.debug("NoOp: get_signal_registry called")
        return {}
