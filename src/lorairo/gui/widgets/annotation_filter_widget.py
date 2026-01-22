"""
Annotation Filter Widget - アノテーションフィルターウィジェット

アノテーション機能タイプ（Caption/Tag/Score）と実行環境（Web API/ローカル）の
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

from typing import TYPE_CHECKING

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

    機能タイプ（Caption生成、Tag生成、品質スコア）と実行環境（Web API、ローカルモデル）の
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
        checkBoxWebAPI: QCheckBox
        checkBoxLocal: QCheckBox

    def __init__(self, parent: QWidget | None = None) -> None:
        """
        AnnotationFilterWidget 初期化

        Args:
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self.setupUi(self)  # type: ignore[no-untyped-call]

        self._connect_signals()
        logger.debug("AnnotationFilterWidget initialized")

    def _connect_signals(self) -> None:
        """チェックボックスのシグナルを接続"""
        # 機能タイプチェックボックス
        self.checkBoxCaption.stateChanged.connect(self._on_filter_changed)
        self.checkBoxTags.stateChanged.connect(self._on_filter_changed)
        self.checkBoxScore.stateChanged.connect(self._on_filter_changed)

        # 実行環境チェックボックス
        self.checkBoxWebAPI.stateChanged.connect(self._on_filter_changed)
        self.checkBoxLocal.stateChanged.connect(self._on_filter_changed)

    def _on_filter_changed(self, _state: int) -> None:
        """
        フィルター変更ハンドラ

        Args:
            _state: チェックボックスの状態（未使用、シグナル接続用）
        """
        filters = self.get_current_filters()
        logger.debug(f"Filter changed: {filters}")
        self.filter_changed.emit(filters)

    def get_current_filters(self) -> dict:
        """
        現在のフィルター状態を取得

        Returns:
            dict: フィルター状態
                - capabilities: list[str] - 選択された機能タイプ ('caption', 'tags', 'scores')
                - environment: str | None - 実行環境 ('local', 'api', None)
        """
        # 機能タイプ: DB ModelType.name 値と一致させる ('caption', 'tags', 'scores')
        capabilities: list[str] = []
        if self.checkBoxCaption.isChecked():
            capabilities.append("caption")
        if self.checkBoxTags.isChecked():
            capabilities.append("tags")
        if self.checkBoxScore.isChecked():
            capabilities.append("scores")

        # 実行環境
        environment: str | None = None
        web_api = self.checkBoxWebAPI.isChecked()
        local = self.checkBoxLocal.isChecked()

        if local and not web_api:
            environment = "local"
        elif web_api and not local:
            environment = "api"
        # 両方チェックまたは両方未チェック → None (フィルターなし)

        return {"capabilities": capabilities, "environment": environment}

    def set_filters(
        self,
        capabilities: list[str] | None | object = _UNSET,
        environment: str | None | object = _UNSET,
    ) -> None:
        """
        フィルター状態を設定

        Args:
            capabilities: 機能タイプリスト ('caption', 'tags', 'scores')、None でクリア
            environment: 実行環境 ('local', 'api')、None でクリア

        Note:
            引数を省略した場合は現状維持、明示的に None を渡した場合はクリア
        """
        # シグナル発火を一時的にブロック
        self.blockSignals(True)

        try:
            # 機能タイプ設定 (DB ModelType.name 値と一致: 'caption', 'tags', 'scores')
            if capabilities is not _UNSET:
                caps = capabilities if capabilities is not None else []
                self.checkBoxCaption.setChecked("caption" in caps)
                self.checkBoxTags.setChecked("tags" in caps)
                self.checkBoxScore.setChecked("scores" in caps)

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

        # 設定後にシグナルを発火
        self.filter_changed.emit(self.get_current_filters())

    def clear_filters(self) -> None:
        """全フィルターをクリア"""
        self.blockSignals(True)

        try:
            self.checkBoxCaption.setChecked(False)
            self.checkBoxTags.setChecked(False)
            self.checkBoxScore.setChecked(False)
            self.checkBoxWebAPI.setChecked(False)
            self.checkBoxLocal.setChecked(False)

        finally:
            self.blockSignals(False)

        self.filter_changed.emit(self.get_current_filters())
        logger.debug("All filters cleared")
