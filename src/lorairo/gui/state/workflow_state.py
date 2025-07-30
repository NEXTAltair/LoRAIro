# src/lorairo/gui/state/workflow_state.py

from enum import Enum

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger


class WorkflowStep(Enum):
    """ワークフローステップ定義"""

    DATASET_SELECTION = "dataset_selection"
    DATASET_LOADING = "dataset_loading"
    OVERVIEW = "overview"
    FILTERING = "filtering"
    EDITING = "editing"
    ANNOTATION = "annotation"
    EXPORT = "export"
    COMPLETED = "completed"


class WorkflowState(Enum):
    """ワークフロー状態定義"""

    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class WorkflowStateManager(QObject):
    """
    ワークフロー進行状況とステップ管理を担当。
    UI上でのワークフロー表示、ナビゲーション、進捗追跡を支援。
    """

    # === ワークフローステップシグナル ===
    step_changed = Signal(WorkflowStep)  # current_step
    step_completed = Signal(WorkflowStep)  # completed_step
    step_started = Signal(WorkflowStep)  # started_step
    step_skipped = Signal(WorkflowStep)  # skipped_step

    # === ワークフロー状態シグナル ===
    workflow_state_changed = Signal(WorkflowState)  # current_state
    workflow_started = Signal()
    workflow_completed = Signal()
    workflow_reset = Signal()

    # === 進捗シグナル ===
    progress_updated = Signal(int, str)  # percentage, status_message
    step_progress_updated = Signal(WorkflowStep, int, str)  # step, percentage, status

    # === エラー・警告シグナル ===
    workflow_error = Signal(str)  # error_message
    step_warning = Signal(WorkflowStep, str)  # step, warning_message

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # === ワークフロー状態 ===
        self._current_step = WorkflowStep.DATASET_SELECTION
        self._workflow_state = WorkflowState.IDLE
        self._completed_steps: list[WorkflowStep] = []
        self._step_progress: dict[WorkflowStep, int] = {}
        self._step_status: dict[WorkflowStep, str] = {}

        # === ワークフロー定義 ===
        self._workflow_sequence = [
            WorkflowStep.DATASET_SELECTION,
            WorkflowStep.DATASET_LOADING,
            WorkflowStep.OVERVIEW,
            WorkflowStep.FILTERING,
            WorkflowStep.EDITING,
            WorkflowStep.ANNOTATION,
            WorkflowStep.EXPORT,
            WorkflowStep.COMPLETED,
        ]

        # === 可変ワークフロー設定 ===
        self._optional_steps = {
            WorkflowStep.FILTERING,
            WorkflowStep.EDITING,
            WorkflowStep.ANNOTATION,
        }

        logger.debug("WorkflowStateManager initialized")

    # === Properties ===

    @property
    def current_step(self) -> WorkflowStep:
        return self._current_step

    @property
    def workflow_state(self) -> WorkflowState:
        return self._workflow_state

    @property
    def completed_steps(self) -> list[WorkflowStep]:
        return self._completed_steps.copy()

    @property
    def workflow_sequence(self) -> list[WorkflowStep]:
        return self._workflow_sequence.copy()

    @property
    def is_workflow_active(self) -> bool:
        """ワークフローが実行中か"""
        return self._workflow_state in [WorkflowState.IN_PROGRESS, WorkflowState.PAUSED]

    @property
    def is_workflow_completed(self) -> bool:
        """ワークフローが完了したか"""
        return self._current_step == WorkflowStep.COMPLETED

    # === Workflow Control ===

    def start_workflow(self) -> None:
        """ワークフローを開始"""
        self._workflow_state = WorkflowState.IN_PROGRESS
        self._current_step = WorkflowStep.DATASET_SELECTION
        self._completed_steps = []
        self._step_progress = {}
        self._step_status = {}

        self.workflow_started.emit()
        self.workflow_state_changed.emit(self._workflow_state)
        self.step_started.emit(self._current_step)

        logger.info("ワークフローを開始しました")

    def reset_workflow(self) -> None:
        """ワークフローをリセット"""
        self._workflow_state = WorkflowState.IDLE
        self._current_step = WorkflowStep.DATASET_SELECTION
        self._completed_steps = []
        self._step_progress = {}
        self._step_status = {}

        self.workflow_reset.emit()
        self.workflow_state_changed.emit(self._workflow_state)

        logger.info("ワークフローをリセットしました")

    def complete_workflow(self) -> None:
        """ワークフローを完了"""
        self._workflow_state = WorkflowState.COMPLETED
        self._current_step = WorkflowStep.COMPLETED

        if WorkflowStep.COMPLETED not in self._completed_steps:
            self._completed_steps.append(WorkflowStep.COMPLETED)

        self.workflow_completed.emit()
        self.workflow_state_changed.emit(self._workflow_state)
        self.step_completed.emit(WorkflowStep.COMPLETED)

        logger.info("ワークフローが完了しました")

    def pause_workflow(self) -> None:
        """ワークフローを一時停止"""
        if self._workflow_state == WorkflowState.IN_PROGRESS:
            self._workflow_state = WorkflowState.PAUSED
            self.workflow_state_changed.emit(self._workflow_state)
            logger.info("ワークフローを一時停止しました")

    def resume_workflow(self) -> None:
        """ワークフローを再開"""
        if self._workflow_state == WorkflowState.PAUSED:
            self._workflow_state = WorkflowState.IN_PROGRESS
            self.workflow_state_changed.emit(self._workflow_state)
            logger.info("ワークフローを再開しました")

    def set_workflow_error(self, error_message: str) -> None:
        """ワークフローエラーを設定"""
        self._workflow_state = WorkflowState.ERROR
        self.workflow_state_changed.emit(self._workflow_state)
        self.workflow_error.emit(error_message)
        logger.error(f"ワークフローエラー: {error_message}")

    # === Step Management ===

    def advance_to_step(self, target_step: WorkflowStep) -> bool:
        """指定ステップに進む"""
        if not self._can_advance_to_step(target_step):
            warning_msg = f"ステップ {target_step.value} に進むことができません"
            self.step_warning.emit(target_step, warning_msg)
            return False

        # 現在のステップを完了としてマーク
        if self._current_step not in self._completed_steps:
            self._completed_steps.append(self._current_step)
            self.step_completed.emit(self._current_step)

        # 新しいステップに移行
        self._current_step = target_step
        self.step_changed.emit(self._current_step)
        self.step_started.emit(self._current_step)

        logger.info(f"ステップ変更: {target_step.value}")
        return True

    def advance_to_next_step(self) -> bool:
        """次のステップに進む"""
        next_step = self._get_next_step()
        if next_step:
            return self.advance_to_step(next_step)
        return False

    def go_back_to_step(self, target_step: WorkflowStep) -> bool:
        """指定ステップに戻る"""
        if target_step in self._completed_steps:
            self._current_step = target_step
            self.step_changed.emit(self._current_step)
            logger.info(f"ステップに戻る: {target_step.value}")
            return True
        return False

    def skip_step(self, step: WorkflowStep) -> bool:
        """ステップをスキップ"""
        if step in self._optional_steps:
            if step not in self._completed_steps:
                self._completed_steps.append(step)
            self.step_skipped.emit(step)
            logger.info(f"ステップをスキップ: {step.value}")
            return True
        return False

    def mark_step_completed(self, step: WorkflowStep) -> None:
        """ステップを完了としてマーク"""
        if step not in self._completed_steps:
            self._completed_steps.append(step)
            self.step_completed.emit(step)
            logger.debug(f"ステップ完了: {step.value}")

    def is_step_completed(self, step: WorkflowStep) -> bool:
        """ステップが完了しているかチェック"""
        return step in self._completed_steps

    def is_step_accessible(self, step: WorkflowStep) -> bool:
        """ステップにアクセス可能かチェック"""
        return self._can_advance_to_step(step)

    # === Progress Management ===

    def update_step_progress(self, step: WorkflowStep, percentage: int, status: str = "") -> None:
        """ステップ進捗を更新"""
        self._step_progress[step] = percentage
        self._step_status[step] = status

        self.step_progress_updated.emit(step, percentage, status)

        # 現在のステップの場合は全体進捗も更新
        if step == self._current_step:
            overall_progress = self._calculate_overall_progress()
            self.progress_updated.emit(overall_progress, status)

    def get_step_progress(self, step: WorkflowStep) -> int:
        """ステップ進捗を取得"""
        return self._step_progress.get(step, 0)

    def get_step_status(self, step: WorkflowStep) -> str:
        """ステップステータスを取得"""
        return self._step_status.get(step, "")

    def get_overall_progress(self) -> int:
        """全体進捗を取得"""
        return self._calculate_overall_progress()

    # === Private Methods ===

    def _can_advance_to_step(self, target_step: WorkflowStep) -> bool:
        """ステップに進むことができるかチェック"""
        if target_step not in self._workflow_sequence:
            return False

        target_index = self._workflow_sequence.index(target_step)
        current_index = self._workflow_sequence.index(self._current_step)

        # 前のステップか現在のステップの場合は常に可能
        if target_index <= current_index:
            return True

        # 次のステップの場合は、必要な前提ステップが完了しているかチェック
        required_steps = self._workflow_sequence[:target_index]
        for required_step in required_steps:
            if required_step not in self._optional_steps and not self.is_step_completed(required_step):
                return False

        return True

    def _get_next_step(self) -> WorkflowStep | None:
        """次のステップを取得"""
        try:
            current_index = self._workflow_sequence.index(self._current_step)
            if current_index < len(self._workflow_sequence) - 1:
                return self._workflow_sequence[current_index + 1]
        except ValueError:
            pass
        return None

    def _calculate_overall_progress(self) -> int:
        """全体進捗を計算"""
        if not self._workflow_sequence:
            return 0

        # 完了ステップ数ベースの進捗計算
        completed_count = len(self._completed_steps)
        total_steps = len(self._workflow_sequence)

        # 現在のステップの進捗も考慮
        current_step_progress = self._step_progress.get(self._current_step, 0)
        current_contribution = current_step_progress / 100.0

        overall_progress = ((completed_count + current_contribution) / total_steps) * 100
        return min(int(overall_progress), 100)

    # === Utility Methods ===

    def get_workflow_summary(self) -> dict[str, any]:
        """ワークフロー状態サマリーを取得"""
        return {
            "current_step": self._current_step.value,
            "workflow_state": self._workflow_state.value,
            "completed_steps": [step.value for step in self._completed_steps],
            "overall_progress": self.get_overall_progress(),
            "is_active": self.is_workflow_active,
            "is_completed": self.is_workflow_completed,
        }

    def get_available_steps(self) -> list[WorkflowStep]:
        """アクセス可能なステップリストを取得"""
        return [step for step in self._workflow_sequence if self.is_step_accessible(step)]

    def get_next_required_step(self) -> WorkflowStep | None:
        """次に完了が必要なステップを取得"""
        for step in self._workflow_sequence:
            if step not in self._optional_steps and not self.is_step_completed(step):
                return step
        return None
