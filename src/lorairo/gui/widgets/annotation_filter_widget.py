"""
Annotation Filter Widget - アノテーションフィルターウィジェット

ローカルモデル対応機能（Caption/Tag/Score/Rating）と実行環境（Web API/ローカル）の
フィルタリングUIを提供する。ModelSelectionWidget と連携してモデル一覧を
動的にフィルタリングする。

使用パターン:
    annotation_filter = AnnotationFilterWidget()
    annotation_filter.filter_changed.connect(
        lambda filters: model_selection.apply_filters(
            provider="local" if filters.get("environment") == "local" else None,
            capabilities=filters.get("capabilities", [])
        )
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from ...utils.log import logger
from ..designer.AnnotationFilterWidget_ui import Ui_AnnotationFilterWidget

if TYPE_CHECKING:
    from PySide6.QtWidgets import QCheckBox

# センチネル値: 引数が明示的に渡されたかどうかを判断するため
_UNSET: object = object()


class AnnotationFilterWidget(QWidget, Ui_AnnotationFilterWidget):
    """
    アノテーションフィルターウィジェット

    ローカルモデル対応機能と実行環境（Web API、ローカルモデル）の
    チェックボックスによるフィルタリングUIを提供。

    Signals:
        filter_changed: フィルター状態が変更されたときに emit
            dict: {"capabilities": list[str], "environment": str | None}

    使用例:
        >>> filter_widget = AnnotationFilterWidget()
        >>> filter_widget.filter_changed.connect(on_filter_changed)
        >>> filters = filter_widget.get_current_filters()
        >>> # {"capabilities": ["caption", "tags"], "environment": "local"}
    """

    # Signal: フィルター変更時に emit
    filter_changed = Signal(dict)  # {capabilities: list[str], environment: str | None}

    # UI elements type hints (from Ui_AnnotationFilterWidget via multi-inheritance)
    if TYPE_CHECKING:
        checkBoxCaption: QCheckBox
        checkBoxTags: QCheckBox
        checkBoxScore: QCheckBox
        checkBoxRating: QCheckBox
        checkBoxWebAPI: QCheckBox
        checkBoxLocal: QCheckBox

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        AnnotationFilterWidget 初期化

        Args:
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.setupUi(self)

        self._connect_signals()
        self._update_capability_controls()
        logger.debug("AnnotationFilterWidget initialized")

    def _connect_signals(self) -> None:
        """チェックボックスのシグナルを接続"""
        # 機能タイプチェックボックス
        self.checkBoxCaption.stateChanged.connect(self._on_filter_changed)
        self.checkBoxTags.stateChanged.connect(self._on_filter_changed)
        self.checkBoxScore.stateChanged.connect(self._on_filter_changed)
        self.checkBoxRating.stateChanged.connect(self._on_filter_changed)

        # 実行環境チェックボックス
        self.checkBoxWebAPI.stateChanged.connect(self._on_filter_changed)
        self.checkBoxLocal.stateChanged.connect(self._on_filter_changed)

    def _on_filter_changed(self, _state: int) -> None:
        """
        フィルター変更ハンドラ

        Args:
            _state: チェックボックスの状態（未使用、シグナル接続用）
        """
        self._update_capability_controls()
        filters = self.get_current_filters()
        logger.debug(f"Filter changed: {filters}")
        self.filter_changed.emit(filters)

    def _is_local_only_environment(self) -> bool:
        """Capability filter is meaningful only when the environment is local-only."""
        return self.checkBoxLocal.isChecked() and not self.checkBoxWebAPI.isChecked()

    def _update_capability_controls(self) -> None:
        """ローカル専用時だけ capability control を有効化する。"""
        enabled = self._is_local_only_environment()
        self.groupBoxFunctionType.setEnabled(enabled)
        for checkbox in (
            self.checkBoxTags,
            self.checkBoxCaption,
            self.checkBoxScore,
            self.checkBoxRating,
        ):
            checkbox.setEnabled(enabled)

    def get_current_filters(self) -> dict[str, Any]:
        """
        現在のフィルター状態を取得

        Returns:
            dict: フィルター状態
                - capabilities: list[str] - 選択された対応機能 ('caption', 'tags', 'scores', 'ratings')
                - environment: str | None - 実行環境 ('local', 'api', None)
        """
        # 実行環境
        environment: str | None = None
        web_api = self.checkBoxWebAPI.isChecked()
        local = self.checkBoxLocal.isChecked()

        if local and not web_api:
            environment = "local"
        elif web_api and not local:
            environment = "api"
        # 両方チェックまたは両方未チェック → None (フィルターなし)

        # ローカルモデル対応機能: DB ModelType.name 値と一致させる。
        capabilities: list[str] = []
        if environment == "local":
            if self.checkBoxTags.isChecked():
                capabilities.append("tags")
            if self.checkBoxCaption.isChecked():
                capabilities.append("caption")
            if self.checkBoxScore.isChecked():
                capabilities.append("scores")
            if self.checkBoxRating.isChecked():
                capabilities.append("ratings")

        return {"capabilities": capabilities, "environment": environment}

    def set_filters(
        self,
        capabilities: list[str] | None | object = _UNSET,
        environment: str | None | object = _UNSET,
    ) -> None:
        """
        フィルター状態を設定

        Args:
            capabilities: 対応機能リスト ('caption', 'tags', 'scores', 'ratings')、None でクリア
            environment: 実行環境 ('local', 'api')、None でクリア

        Note:
            引数を省略した場合は現状維持、明示的に None を渡した場合はクリア
        """
        # シグナル発火を一時的にブロック
        self.blockSignals(True)

        try:
            # 機能タイプ設定 (DB ModelType.name 値と一致)
            if capabilities is not _UNSET:
                caps = cast("list[str]", capabilities if capabilities is not None else [])
                self.checkBoxCaption.setChecked("caption" in caps)
                self.checkBoxTags.setChecked("tags" in caps)
                self.checkBoxScore.setChecked("scores" in caps)
                self.checkBoxRating.setChecked("ratings" in caps)

            # 実行環境設定
            if environment is not _UNSET:
                if environment is None:
                    # 明示的に None を渡した場合はクリア
                    self.checkBoxWebAPI.setChecked(False)
                    self.checkBoxLocal.setChecked(False)
                else:
                    self.checkBoxWebAPI.setChecked(environment == "api")
                    self.checkBoxLocal.setChecked(environment == "local")

        finally:
            self.blockSignals(False)

        self._update_capability_controls()
        # 設定後にシグナルを発火
        self.filter_changed.emit(self.get_current_filters())

    def clear_filters(self) -> None:
        """全フィルターをクリア"""
        self.blockSignals(True)

        try:
            self.checkBoxCaption.setChecked(False)
            self.checkBoxTags.setChecked(False)
            self.checkBoxScore.setChecked(False)
            self.checkBoxRating.setChecked(False)
            self.checkBoxWebAPI.setChecked(False)
            self.checkBoxLocal.setChecked(False)

        finally:
            self.blockSignals(False)

        self._update_capability_controls()
        self.filter_changed.emit(self.get_current_filters())
        logger.debug("All filters cleared")
