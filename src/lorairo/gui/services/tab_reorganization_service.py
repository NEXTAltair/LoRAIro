# src/lorairo/gui/services/tab_reorganization_service.py

"""
TabReorganizationService - タブ構造検証ユーティリティ

MainWindow.ui で定義されたタブ構造の検証を行う静的サービス。

UI構造 (MainWindow.ui で定義):
    centralwidget
    └── tabWidgetMainMode (トップレベルタブ)
        ├── Tab 0: tabWorkspace (ワークスペース)
        │   ├── frameDatasetSelector
        │   ├── frameDbStatus
        │   ├── splitterMainWorkArea (3分割)
        │   └── frameActionToolbar
        └── Tab 1: tabBatchTag (バッチタグ)
            ├── groupBoxStagingImages (左カラム)
            └── groupBoxBatchOperations (右カラム)
                ├── batchTagWidgetPlaceholder
                ├── annotationDisplayPlaceholder
                └── groupBoxAnnotation

Note:
    プログラム的なレイアウト構築は廃止され、
    すべてのタブ構造はMainWindow.uiで宣言的に定義される。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ...utils.log import logger

if TYPE_CHECKING:
    from ..window.main_window import MainWindow


class TabReorganizationService:
    """
    タブ構造検証ユーティリティ

    MainWindow.ui で定義されたタブ構造が正しく生成されているかを検証する。
    プログラム的なレイアウト構築は廃止。
    """

    # 必須ウィジェット objectName リスト
    REQUIRED_WIDGETS: ClassVar[list[str]] = [
        "tabWidgetMainMode",
        "tabWorkspace",
        "tabBatchTag",
        "groupBoxStagingImages",
        "groupBoxBatchOperations",
        "groupBoxAnnotation",
    ]

    # widget_setup_service が期待するプレースホルダー objectName リスト
    REQUIRED_PLACEHOLDERS: ClassVar[list[str]] = [
        "batchTagWidgetPlaceholder",
        "annotationDisplayPlaceholder",
        "annotationFilterPlaceholder",
        "modelSelectionPlaceholder",
    ]

    @staticmethod
    def validate_tab_structure(main_window: MainWindow) -> bool:
        """
        タブ構造の検証

        MainWindow.ui から生成されたタブ構造が正しく存在するかを検証する。

        Args:
            main_window: 検証対象のMainWindow

        Returns:
            bool: すべての必須ウィジェットが存在すればTrue
        """
        missing_widgets: list[str] = []
        missing_placeholders: list[str] = []

        # 必須ウィジェットの存在確認
        for name in TabReorganizationService.REQUIRED_WIDGETS:
            if not main_window.findChild(object, name):
                missing_widgets.append(name)

        # プレースホルダーの存在確認
        for name in TabReorganizationService.REQUIRED_PLACEHOLDERS:
            if not main_window.findChild(object, name):
                missing_placeholders.append(name)

        # 結果ログ出力
        if missing_widgets:
            logger.error(f"Missing required widgets: {missing_widgets}")
        if missing_placeholders:
            logger.warning(f"Missing placeholders (may be replaced): {missing_placeholders}")

        is_valid = len(missing_widgets) == 0
        if is_valid:
            logger.info("Tab structure validation passed")
        else:
            logger.error("Tab structure validation failed")

        return is_valid

    @staticmethod
    def get_tab_widget_count(main_window: MainWindow) -> int:
        """
        タブウィジェットのタブ数を取得

        Args:
            main_window: MainWindow

        Returns:
            int: タブ数（tabWidgetMainMode が存在しない場合は 0）
        """
        if hasattr(main_window, "tabWidgetMainMode") and main_window.tabWidgetMainMode:
            return main_window.tabWidgetMainMode.count()
        return 0
