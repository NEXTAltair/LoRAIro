# src/lorairo/gui/widgets/workflow_navigator.py

from typing import Dict, Optional

from PySide6.QtCore import QSize, Qt, Signal, Slot
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ...utils.log import logger
from ..state.workflow_state import WorkflowState, WorkflowStateManager, WorkflowStep


class WorkflowStepButton(QPushButton):
    """ワークフローステップを表すボタン"""

    def __init__(self, step: WorkflowStep, parent=None):
        super().__init__(parent)
        self.step = step
        self.step_name = self._get_step_display_name(step)

        # ボタン設定
        self.setText(self.step_name)
        self.setCheckable(True)
        self.setMinimumSize(QSize(80, 30))
        self.setMaximumSize(QSize(120, 30))
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        # 初期スタイル設定
        self._update_style("pending")

    def _get_step_display_name(self, step: WorkflowStep) -> str:
        """ステップの表示名を取得"""
        display_names = {
            WorkflowStep.DATASET_SELECTION: "データセット",
            WorkflowStep.DATASET_LOADING: "読み込み",
            WorkflowStep.OVERVIEW: "概要",
            WorkflowStep.FILTERING: "フィルター",
            WorkflowStep.EDITING: "編集",
            WorkflowStep.ANNOTATION: "アノテーション",
            WorkflowStep.EXPORT: "エクスポート",
            WorkflowStep.COMPLETED: "完了",
        }
        return display_names.get(step, step.value)

    def set_step_state(self, state: str, is_current: bool = False) -> None:
        """ステップ状態を設定"""
        self._update_style(state, is_current)
        self.setChecked(is_current)

    def _update_style(self, state: str, is_current: bool = False) -> None:
        """ステップ状態に応じてスタイルを更新"""
        base_style = """
            QPushButton {
                border: 2px solid %s;
                border-radius: 15px;
                padding: 4px 8px;
                font-weight: %s;
                background-color: %s;
                color: %s;
            }
            QPushButton:hover {
                background-color: %s;
            }
            QPushButton:checked {
                background-color: %s;
                color: white;
            }
        """

        if state == "completed":
            # 完了ステップ: 緑
            border_color = "#28a745"
            bg_color = "#d4edda"
            text_color = "#155724"
            hover_color = "#c3e6cb"
            checked_color = "#28a745"
            font_weight = "bold" if is_current else "normal"
        elif state == "current":
            # 現在ステップ: 青
            border_color = "#007bff"
            bg_color = "#cce5ff"
            text_color = "#004085"
            hover_color = "#b3d9ff"
            checked_color = "#007bff"
            font_weight = "bold"
        elif state == "accessible":
            # アクセス可能ステップ: 灰色
            border_color = "#6c757d"
            bg_color = "#f8f9fa"
            text_color = "#495057"
            hover_color = "#e9ecef"
            checked_color = "#6c757d"
            font_weight = "normal"
        else:
            # 未来ステップ: 薄い灰色
            border_color = "#dee2e6"
            bg_color = "#f8f9fa"
            text_color = "#6c757d"
            hover_color = "#f8f9fa"
            checked_color = "#dee2e6"
            font_weight = "normal"

        style = base_style % (border_color, font_weight, bg_color, text_color, hover_color, checked_color)
        self.setStyleSheet(style)


class WorkflowNavigatorWidget(QWidget):
    """
    ワークフローナビゲーターウィジェット。
    ワークフローの進行状況を表示し、ステップ間の移動を可能にする。
    """

    # シグナル
    step_clicked = Signal(WorkflowStep)
    step_navigation_requested = Signal(WorkflowStep)

    def __init__(self, parent=None, workflow_state: WorkflowStateManager | None = None):
        super().__init__(parent)

        # 状態管理
        self.workflow_state = workflow_state

        # UI設定
        self.setup_ui()

        # ステップボタン管理
        self.step_buttons: dict[WorkflowStep, WorkflowStepButton] = {}
        self._create_step_buttons()

        # 状態管理との連携
        if self.workflow_state:
            self._connect_workflow_state()

        logger.debug("WorkflowNavigatorWidget initialized")

    def setup_ui(self) -> None:
        """UI初期化"""
        self.setFixedHeight(40)

        # メインレイアウト
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(5)

        # ステップボタンコンテナ
        self.steps_container = QFrame(self)
        self.steps_container.setFrameShape(QFrame.Shape.NoFrame)
        self.steps_layout = QHBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(2)

        self.main_layout.addWidget(self.steps_container)

    def set_workflow_state(self, workflow_state: WorkflowStateManager) -> None:
        """ワークフロー状態管理を設定"""
        if self.workflow_state:
            self._disconnect_workflow_state()

        self.workflow_state = workflow_state
        self._connect_workflow_state()

        # 現在の状態を反映
        self._update_all_step_states()

    def _connect_workflow_state(self) -> None:
        """ワークフロー状態管理との連携を設定"""
        if not self.workflow_state:
            return

        self.workflow_state.step_changed.connect(self._on_current_step_changed)
        self.workflow_state.step_completed.connect(self._on_step_completed)
        self.workflow_state.workflow_state_changed.connect(self._on_workflow_state_changed)
        self.workflow_state.step_progress_updated.connect(self._on_step_progress_updated)

    def _disconnect_workflow_state(self) -> None:
        """ワークフロー状態管理との連携を解除"""
        if not self.workflow_state:
            return

        self.workflow_state.step_changed.disconnect(self._on_current_step_changed)
        self.workflow_state.step_completed.disconnect(self._on_step_completed)
        self.workflow_state.workflow_state_changed.disconnect(self._on_workflow_state_changed)
        self.workflow_state.step_progress_updated.disconnect(self._on_step_progress_updated)

    def _create_step_buttons(self) -> None:
        """ステップボタンを作成"""
        workflow_steps = [
            WorkflowStep.DATASET_SELECTION,
            WorkflowStep.DATASET_LOADING,
            WorkflowStep.OVERVIEW,
            WorkflowStep.FILTERING,
            WorkflowStep.EDITING,
            WorkflowStep.ANNOTATION,
            WorkflowStep.EXPORT,
            WorkflowStep.COMPLETED,
        ]

        for step in workflow_steps:
            button = WorkflowStepButton(step, self)
            button.clicked.connect(lambda checked, s=step: self._on_step_button_clicked(s))

            self.step_buttons[step] = button
            self.steps_layout.addWidget(button)

        # 初期状態設定
        self._update_all_step_states()

    def _on_step_button_clicked(self, step: WorkflowStep) -> None:
        """ステップボタンクリック処理"""
        if not self.workflow_state:
            self.step_clicked.emit(step)
            return

        # アクセス可能性チェック
        if self.workflow_state.is_step_accessible(step):
            self.step_navigation_requested.emit(step)
            logger.info(f"ステップナビゲーション要求: {step.value}")
        else:
            logger.warning(f"アクセス不可能なステップ: {step.value}")
            # ボタンの選択状態を元に戻す
            current_step = self.workflow_state.current_step
            if current_step in self.step_buttons:
                self.step_buttons[current_step].setChecked(True)

    # === State Update Handlers ===

    @Slot(object)
    def _on_current_step_changed(self, current_step: WorkflowStep) -> None:
        """現在ステップ変更処理"""
        self._update_all_step_states()
        logger.debug(f"ワークフローナビゲーター: 現在ステップ変更 -> {current_step.value}")

    @Slot(object)
    def _on_step_completed(self, completed_step: WorkflowStep) -> None:
        """ステップ完了処理"""
        if completed_step in self.step_buttons:
            button = self.step_buttons[completed_step]
            is_current = self.workflow_state and self.workflow_state.current_step == completed_step
            button.set_step_state("completed", is_current)

    @Slot(object)
    def _on_workflow_state_changed(self, workflow_state: WorkflowState) -> None:
        """ワークフロー状態変更処理"""
        # 全ボタンの有効/無効状態を更新
        enabled = workflow_state in [WorkflowState.IN_PROGRESS, WorkflowState.PAUSED]
        for button in self.step_buttons.values():
            button.setEnabled(enabled)

    @Slot(object, int, str)
    def _on_step_progress_updated(self, step: WorkflowStep, percentage: int, status: str) -> None:
        """ステップ進捗更新処理"""
        if step in self.step_buttons:
            button = self.step_buttons[step]
            # 進捗に応じてツールチップを更新
            if percentage > 0:
                button.setToolTip(f"{button.step_name}: {status} ({percentage}%)")
            else:
                button.setToolTip(button.step_name)

    def _update_all_step_states(self) -> None:
        """全ステップの状態を更新"""
        if not self.workflow_state:
            # ワークフロー状態管理がない場合はデフォルト状態
            for step, button in self.step_buttons.items():
                if step == WorkflowStep.DATASET_SELECTION:
                    button.set_step_state("current", True)
                else:
                    button.set_step_state("pending", False)
            return

        current_step = self.workflow_state.current_step
        completed_steps = self.workflow_state.completed_steps

        for step, button in self.step_buttons.items():
            is_current = step == current_step

            if step in completed_steps:
                button.set_step_state("completed", is_current)
            elif is_current:
                button.set_step_state("current", True)
            elif self.workflow_state.is_step_accessible(step):
                button.set_step_state("accessible", False)
            else:
                button.set_step_state("pending", False)

    # === Public Methods ===

    def highlight_step(self, step: WorkflowStep) -> None:
        """指定ステップをハイライト"""
        if step in self.step_buttons:
            button = self.step_buttons[step]
            button.setChecked(True)

    def get_current_step(self) -> WorkflowStep | None:
        """現在のステップを取得"""
        if self.workflow_state:
            return self.workflow_state.current_step

        # フォールバック: チェックされているボタンから判断
        for step, button in self.step_buttons.items():
            if button.isChecked():
                return step
        return None

    def set_step_enabled(self, step: WorkflowStep, enabled: bool) -> None:
        """指定ステップの有効/無効を設定"""
        if step in self.step_buttons:
            self.step_buttons[step].setEnabled(enabled)

    def update_step_tooltip(self, step: WorkflowStep, tooltip: str) -> None:
        """ステップのツールチップを更新"""
        if step in self.step_buttons:
            self.step_buttons[step].setToolTip(tooltip)

    def get_workflow_summary(self) -> dict[str, any]:
        """ワークフロー状態サマリーを取得"""
        if self.workflow_state:
            return self.workflow_state.get_workflow_summary()

        return {
            "current_step": self.get_current_step().value if self.get_current_step() else None,
            "workflow_state": "unknown",
            "completed_steps": [],
            "overall_progress": 0,
        }
