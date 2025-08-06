# src/lorairo/services/signal_manager_protocol.py

"""Signal管理サービス用Protocol定義

Phase 5: Signal処理現代化の一環として、統一的なSignal管理インターフェース
を定義し、Protocol-based architectureとの統合を実現します。
"""

from abc import abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar, Protocol, runtime_checkable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget


@runtime_checkable
class SignalManagerServiceProtocol(Protocol):
    """統一Signal管理サービスProtocol

    全Widget間でのSignal処理を標準化し、以下の機能を提供：
    - 統一Signal命名規約の強制
    - エラーハンドリングSignalの標準化
    - Protocol-based依存注入対応
    - テスト容易性向上
    """

    @abstractmethod
    def connect_widget_signals(
        self, widget: QObject, signal_mapping: dict[str, Callable[..., Any]]
    ) -> bool:
        """WidgetのSignalを統一的な規約で接続

        Args:
            widget: 接続対象Widget
            signal_mapping: Signal名→ハンドラー関数のマッピング

        Returns:
            bool: 接続成功フラグ

        Note:
            signal_mappingのキーは統一命名規約（snake_case）を使用
            例: {"image_selected": handler, "images_filtered": handler}
        """
        ...

    @abstractmethod
    def emit_application_signal(self, signal_name: str, *args: Any) -> bool:
        """アプリケーション全体Signal発行

        Args:
            signal_name: 統一規約に従ったSignal名
            *args: Signalペイロード

        Returns:
            bool: 発行成功フラグ
        """
        ...

    @abstractmethod
    def register_error_handler(
        self, widget: QObject, error_handler: Callable[[str, Exception], None]
    ) -> bool:
        """Widget用統一エラーハンドラー登録

        Args:
            widget: 対象Widget
            error_handler: エラーハンドラー関数

        Returns:
            bool: 登録成功フラグ
        """
        ...

    @abstractmethod
    def validate_signal_naming(self, signal_name: str) -> bool:
        """Signal命名規約検証

        Args:
            signal_name: 検証対象Signal名

        Returns:
            bool: 命名規約準拠フラグ

        Note:
            統一規約: snake_case, 動詞_過去分詞パターン
            例: image_selected, dataset_loaded, annotation_started
        """
        ...

    @abstractmethod
    def get_signal_registry(self) -> dict[str, list[QObject]]:
        """登録済みSignal一覧取得

        Returns:
            dict: Signal名→接続元Objectリストのマッピング
        """
        ...


@runtime_checkable
class SignalNameValidatorProtocol(Protocol):
    """Signal命名検証用Protocol"""

    @abstractmethod
    def is_valid_signal_name(self, name: str) -> bool:
        """Signal名の妥当性検証

        Args:
            name: 検証対象Signal名

        Returns:
            bool: 妥当性フラグ
        """
        ...

    @abstractmethod
    def suggest_corrected_name(self, name: str) -> str:
        """Signal名修正提案

        Args:
            name: 修正対象Signal名

        Returns:
            str: 修正提案名
        """
        ...


class SignalNamingStandard:
    """Signal命名標準定義

    Phase 5現代化で統一するSignal命名規約を定義
    """

    # 標準パターン
    PATTERN_ACTION_PAST = r"^[a-z]+(_[a-z]+)*_(started|finished|completed|failed|updated|changed|cleared|selected|loaded|filtered|applied)$"
    PATTERN_ERROR = r"^[a-z]+(_[a-z]+)*_error$"
    PATTERN_STATE = r"^[a-z]+(_[a-z]+)*_(count_changed|size_changed|mode_changed)$"
    PATTERN_EVENT = r"^[a-z]+(_[a-z]+)*_(clicked|pressed|released|activated|deactivated)$"

    # 推奨Suffix
    RECOMMENDED_SUFFIXES: ClassVar[dict[str, str]] = {
        # 開始・進行・完了
        "started": "処理開始時",
        "updated": "進行状況更新時",
        "finished": "正常完了時",
        "completed": "処理完了時",
        "failed": "失敗時",
        "error": "エラー時",
        # 状態変更
        "changed": "状態変更時",
        "cleared": "クリア・リセット時",
        "loaded": "データ読み込み完了時",
        "filtered": "フィルター適用時",
        "applied": "適用時",
        "selected": "選択時",
        # UI事象
        "clicked": "クリック時",
        "activated": "アクティブ化時",
        "deactivated": "非アクティブ化時",
    }

    # Legacy → Modern マッピング
    LEGACY_TO_MODERN_MAPPING: ClassVar[dict[str, str]] = {
        # ThumbnailSelectorWidget
        "imageSelected": "image_selected",
        "multipleImagesSelected": "multiple_images_selected",
        "deselected": "selection_cleared",
        # 将来の拡張用
        "itemClicked": "item_clicked",
        "dataLoaded": "data_loaded",
        "filterApplied": "filter_applied",
    }
