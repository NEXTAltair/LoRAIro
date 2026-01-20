# src/lorairo/gui/services/tab_reorganization_service.py

"""
TabReorganizationService - プログラム的タブ再構成サービス

MainWindowのcentralwidgetレイアウトをトップレベルタブ構造に再構成する。
Qt Designer .uiファイルを変更せず、プログラム的にUI構造を変更することで
安全性を確保し、既存テストへの影響を最小化する。

UI構造:
    Before (既存):
        centralwidget
        ├── frameDatasetSelector
        ├── frameDbStatus
        ├── splitterMainWorkArea (3分割)
        │   ├── frameFilterSearchPanel (左パネル)
        │   ├── frameThumbnailGrid (中央パネル)
        │   └── framePreviewDetailPanel (右パネル)
        └── frameActionToolbar

    After (再構成後):
        centralwidget
        └── tabWidgetMainMode (トップレベルタブ)
            ├── Tab 0: ワークスペース
            │   ├── frameDatasetSelector
            │   ├── frameDbStatus
            │   ├── splitterMainWorkArea (既存のまま)
            │   └── frameActionToolbar
            └── Tab 1: バッチタグ
                ├── 左カラム: ステージング画像グリッド
                └── 右カラム: 操作パネル

参考実装:
    - FilterSearchPanel.setup_favorite_filters_ui() (プログラム的UI作成)
    - SelectedImageDetailsWidget (removeWidget → setParent → addWidget パターン)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...utils.log import logger

if TYPE_CHECKING:
    from ..window.main_window import MainWindow


class TabReorganizationService:
    """
    プログラム的タブ再構成サービス

    MainWindowのUI構造をトップレベルタブに再構成する静的サービス。
    Qt Designer .uiファイルを変更せず、プログラム的にレイアウトを変更する。

    重要:
        - setup_custom_widgets()より前に呼び出す必要がある
        - 既存ウィジェットを再配置するため、MainWindow.ui生成後に実行
        - 既存サービス統合には影響しない（Phase 3以降で参照される）

    使用例:
        >>> main_window.tabWidgetMainMode = QTabWidget(main_window)
        >>> TabReorganizationService.reorganize_main_window_layout(main_window)
    """

    @staticmethod
    def create_main_tab_widget() -> QTabWidget:
        """
        トップレベルQTabWidgetを作成

        Returns:
            QTabWidget: 2タブを持つトップレベルタブウィジェット
                - Tab 0: ワークスペース
                - Tab 1: バッチタグ
        """
        tab_widget = QTabWidget()
        tab_widget.setObjectName("tabWidgetMainMode")
        logger.debug("Created main tab widget: tabWidgetMainMode")
        return tab_widget

    @staticmethod
    def extract_existing_widgets(main_window: MainWindow) -> dict[str, QWidget]:
        """
        MainWindowから必要なウィジェットを抽出

        Args:
            main_window: MainWindowインスタンス（Ui_MainWindowを多重継承しているため、
                        ウィジェットは直接self属性として存在）

        Returns:
            dict: 抽出されたウィジェットの辞書
                - "dataset_selector": frameDatasetSelector
                - "db_status": frameDbStatus
                - "splitter": splitterMainWorkArea
                - "action_toolbar": frameActionToolbar
        """
        widgets = {}

        # Qt Designerで定義されたウィジェットを取得（MainWindowの直接の属性）
        if hasattr(main_window, "frameDatasetSelector"):
            widgets["dataset_selector"] = main_window.frameDatasetSelector
            logger.debug("Extracted frameDatasetSelector")

        if hasattr(main_window, "frameDbStatus"):
            widgets["db_status"] = main_window.frameDbStatus
            logger.debug("Extracted frameDbStatus")

        if hasattr(main_window, "splitterMainWorkArea"):
            widgets["splitter"] = main_window.splitterMainWorkArea
            logger.debug("Extracted splitterMainWorkArea")

        if hasattr(main_window, "frameActionToolbar"):
            widgets["action_toolbar"] = main_window.frameActionToolbar
            logger.debug("Extracted frameActionToolbar")

        logger.info(f"Extracted {len(widgets)} existing widgets from MainWindow")
        return widgets

    @staticmethod
    def build_workspace_tab(existing_widgets: dict[str, QWidget]) -> QWidget:
        """
        ワークスペースタブを構築

        既存のウィジェット（データセット選択、DB状態、スプリッター、アクションツールバー）を
        再配置してワークスペースタブを構築する。

        Args:
            existing_widgets: extract_existing_widgets()で抽出されたウィジェット辞書

        Returns:
            QWidget: ワークスペースタブのコンテナウィジェット

        重要:
            既存ウィジェットを再配置するため、removeWidget → setParent → addWidget の
            3ステップを厳守する。
        """
        workspace_widget = QWidget()
        workspace_widget.setObjectName("tabWorkspace")
        workspace_layout = QVBoxLayout(workspace_widget)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(0)

        # 既存ウィジェットを順番に追加
        # 注意: removeWidget()は後で呼び出し元が実行する
        for key, widget_name in [
            ("dataset_selector", "frameDatasetSelector"),
            ("db_status", "frameDbStatus"),
            ("splitter", "splitterMainWorkArea"),
            ("action_toolbar", "frameActionToolbar"),
        ]:
            if key in existing_widgets:
                widget = existing_widgets[key]
                # 親を変更（Qtの所有権管理）
                widget.setParent(workspace_widget)
                # 新しいレイアウトに追加
                workspace_layout.addWidget(widget)
                logger.debug(f"Added {widget_name} to workspace tab")
            else:
                logger.warning(f"Widget {widget_name} not found in existing_widgets")

        # splitterの伸縮係数を最大化（画面の大部分を占める）
        if "splitter" in existing_widgets:
            workspace_layout.setStretch(2, 1)  # index 2 = splitter

        logger.info("Workspace tab built successfully")
        return workspace_widget

    @staticmethod
    def build_batch_tag_tab() -> QWidget:
        """
        バッチタグタブを構築

        2カラムレイアウト（ステージング画像グリッド + 操作パネル）を持つ
        バッチタグタブを構築する。

        Returns:
            QWidget: バッチタグタブのコンテナウィジェット

        Note:
            実際のウィジェット統合（BatchTagAddWidget、AnnotationDataDisplayWidget）は
            MainWindow._setup_batch_tag_tab_widgets()で行う。
            ここではレイアウト骨格のみを作成する。
        """
        batch_tag_widget = QWidget()
        batch_tag_widget.setObjectName("tabBatchTag")
        main_layout = QVBoxLayout(batch_tag_widget)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # 2カラムレイアウト作成
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(8)

        # 左カラム: ステージング画像グリッド
        left_column = QGroupBox("ステージング画像")
        left_column.setObjectName("groupBoxStagingImages")
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        # ステージング画像グリッド（プレースホルダー）
        # 実際のサムネイル表示は_setup_batch_tag_tab_widgets()で実装
        staging_grid_container = QWidget()
        staging_grid_container.setObjectName("stagingGridContainer")
        staging_grid_layout = QGridLayout(staging_grid_container)
        staging_grid_layout.setContentsMargins(0, 0, 0, 0)
        staging_grid_layout.setSpacing(6)

        # プレースホルダーラベル
        placeholder_label = QLabel("ステージング画像がありません")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_label.setObjectName("stagingPlaceholder")
        staging_grid_layout.addWidget(placeholder_label, 0, 0)

        left_layout.addWidget(staging_grid_container)

        # 右カラム: 操作パネル
        right_column = QGroupBox("操作")
        right_column.setObjectName("groupBoxBatchOperations")
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(8)

        # BatchTagAddWidget配置用プレースホルダー
        batch_tag_placeholder = QWidget()
        batch_tag_placeholder.setObjectName("batchTagWidgetPlaceholder")
        placeholder_layout = QVBoxLayout(batch_tag_placeholder)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        placeholder_layout.addWidget(QLabel("BatchTagAddWidget (配置予定)"))
        right_layout.addWidget(batch_tag_placeholder)

        # AnnotationDataDisplayWidget配置用プレースホルダー
        annotation_display_placeholder = QWidget()
        annotation_display_placeholder.setObjectName("annotationDisplayPlaceholder")
        placeholder_layout2 = QVBoxLayout(annotation_display_placeholder)
        placeholder_layout2.setContentsMargins(0, 0, 0, 0)
        placeholder_layout2.addWidget(QLabel("AnnotationDataDisplayWidget (配置予定)"))
        right_layout.addWidget(annotation_display_placeholder)

        # カラムを追加（1:1の比率）
        columns_layout.addWidget(left_column, 1)
        columns_layout.addWidget(right_column, 1)

        main_layout.addLayout(columns_layout)

        logger.info("Batch tag tab skeleton built successfully")
        return batch_tag_widget

    @staticmethod
    def reorganize_main_window_layout(main_window: MainWindow) -> None:
        """
        MainWindowのレイアウトをトップレベルタブ構造に再構成

        Args:
            main_window: 再構成対象のMainWindow

        Raises:
            RuntimeError: tabWidgetMainModeが未作成の場合

        重要:
            - main_window.tabWidgetMainModeが事前に作成されている必要がある
            - setup_custom_widgets()より前に呼び出す必要がある
            - 既存ウィジェットを移動するため、サービス統合には影響しない
        """
        if not hasattr(main_window, "tabWidgetMainMode"):
            raise RuntimeError(
                "tabWidgetMainMode must be created before calling reorganize_main_window_layout()"
            )

        central_widget = main_window.centralWidget()
        if not central_widget:
            raise RuntimeError("centralWidget not found in MainWindow")

        # 既存レイアウトを取得
        old_layout = central_widget.layout()
        if not old_layout:
            logger.warning("No layout found in centralWidget, creating new one")
            old_layout = QVBoxLayout(central_widget)

        # 既存ウィジェットを抽出
        existing_widgets = TabReorganizationService.extract_existing_widgets(main_window)

        # 既存レイアウトから既存ウィジェットを削除
        for widget in existing_widgets.values():
            old_layout.removeWidget(widget)
            logger.debug(f"Removed {widget.objectName()} from old layout")

        # ワークスペースタブ構築
        workspace_tab = TabReorganizationService.build_workspace_tab(existing_widgets)

        # バッチタグタブ構築
        batch_tag_tab = TabReorganizationService.build_batch_tag_tab()

        # タブウィジェットにタブを追加
        main_window.tabWidgetMainMode.addTab(workspace_tab, "ワークスペース")
        main_window.tabWidgetMainMode.addTab(batch_tag_tab, "バッチタグ")
        logger.info("Added 2 tabs to tabWidgetMainMode")

        # tabWidgetMainModeを親に設定
        main_window.tabWidgetMainMode.setParent(central_widget)

        # centralwidgetのレイアウトにtabWidgetMainModeを追加
        old_layout.addWidget(main_window.tabWidgetMainMode)

        logger.info("MainWindow layout reorganization completed successfully")
