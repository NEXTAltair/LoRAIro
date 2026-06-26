# src/lorairo/gui/widgets/pipeline_state.py
"""Pipeline State Machine (Qt 非依存)。

検索 → サムネイル読み込み → 表示の一連の流れを 6 状態の Enum で表現する。
Qt に依存しない純粋ロジックとして実装し、unit test で完全検証可能 (ADR 0036 §6)。

呼び出し側 (FilterSearchPanel) が state 遷移を通知するハンドラを登録し、
UI 更新やシグナル発火は呼び出し側の責務とする。
"""

from collections.abc import Callable
from enum import Enum

from ...utils.log import logger


class PipelineState(Enum):
    """検索パイプラインの 6 状態。"""

    IDLE = "idle"  # 初期状態 / 操作待ち
    SEARCHING = "searching"  # 検索実行中
    LOADING_THUMBNAILS = "loading_thumbnails"  # サムネイル読み込み中
    DISPLAYING = "displaying"  # 結果表示中
    ERROR = "error"  # エラー状態
    CANCELED = "canceled"  # キャンセル状態


# 状態 → 既定メッセージのマップ (UI 表示用、UI 側で必要に応じて使う)
DEFAULT_STATE_MESSAGES: dict[PipelineState, str] = {
    PipelineState.IDLE: "操作待ち",
    PipelineState.SEARCHING: "検索中...",
    PipelineState.LOADING_THUMBNAILS: "サムネイル読み込み中...",
    PipelineState.DISPLAYING: "表示中",
    PipelineState.ERROR: "エラーが発生しました",
    PipelineState.CANCELED: "キャンセルされました",
}


StateChangeListener = Callable[[PipelineState, PipelineState], None]


class PipelineStateMachine:
    """検索 → サムネイル → 表示の状態遷移を管理する Qt 非依存クラス。

    Attributes:
        state_messages: 状態 → 既定メッセージのマップ。

    Note:
        - 状態遷移時に register_listener で登録したコールバックを呼び出す。
        - 同一状態への再遷移は無視する。
    """

    def __init__(self) -> None:
        self._current_state: PipelineState = PipelineState.IDLE
        self._listeners: list[StateChangeListener] = []
        self.state_messages: dict[PipelineState, str] = dict(DEFAULT_STATE_MESSAGES)

    @property
    def current_state(self) -> PipelineState:
        """現在の状態を取得する。"""
        return self._current_state

    def register_listener(self, listener: StateChangeListener) -> None:
        """状態遷移時に呼び出されるコールバックを登録する。

        Args:
            listener: (old_state, new_state) を受け取るコールバック。
        """
        self._listeners.append(listener)

    def transition_to(self, new_state: PipelineState) -> bool:
        """指定状態へ遷移する。

        Args:
            new_state: 遷移先の状態。

        Returns:
            遷移が実行された場合は True、同一状態で無視した場合は False。
        """
        if self._current_state == new_state:
            return False

        old_state = self._current_state
        self._current_state = new_state
        logger.info(f"Pipeline state transition: {old_state.value} → {new_state.value}")

        for listener in self._listeners:
            listener(old_state, new_state)
        return True

    def is_active(self) -> bool:
        """検索処理が進行中かどうか (SEARCHING or LOADING_THUMBNAILS)。"""
        return self._current_state in (
            PipelineState.SEARCHING,
            PipelineState.LOADING_THUMBNAILS,
        )

    def force_reset(self) -> None:
        """強制的に IDLE 状態へリセットする (緊急時用)。"""
        logger.warning("Force pipeline reset requested")
        self.transition_to(PipelineState.IDLE)

    def notify_thumbnail_loading_started(self) -> bool:
        """サムネイル読み込み開始通知。

        Returns:
            SEARCHING からの遷移が成功した場合は True、それ以外は False。
        """
        if self._current_state == PipelineState.SEARCHING:
            return self.transition_to(PipelineState.LOADING_THUMBNAILS)
        return False

    def notify_thumbnail_loading_completed(self) -> bool:
        """サムネイル読み込み完了通知。

        Returns:
            LOADING_THUMBNAILS からの遷移が成功した場合は True、それ以外は False。
        """
        if self._current_state == PipelineState.LOADING_THUMBNAILS:
            return self.transition_to(PipelineState.DISPLAYING)
        return False

    def clear_results(self) -> bool:
        """結果クリア時の状態遷移。

        - ERROR 状態の場合は IDLE へ
        - それ以外は CANCELED へ

        Returns:
            遷移が実行された場合は True。
        """
        if self._current_state == PipelineState.ERROR:
            return self.transition_to(PipelineState.IDLE)
        return self.transition_to(PipelineState.CANCELED)
