"""Frame 4 · Errors トリアージ表示ウィジェット。

``ErrorTriageService`` が算出した ``ErrorTriageSummary`` / ``ErrorGroup`` /
``ErrorRow`` を受け取り、サマリ band・フィルタ bar・グループ/個別行表示を
描画する。集約ロジックは持たず表示に専念する (MVC の View)。
アクションは resolve / bulk resolve のみ。
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lorairo.services.error_triage_service import (
    ErrorFilter,
    ErrorGroup,
    ErrorRow,
    ErrorTriageSummary,
)


class ErrorsTriageWidget(QWidget):
    """Frame 4 · Errors トリアージ表示。objectName = "errorsTriageWidget"。"""

    resolve_requested = Signal(int)  # error_id (単一 resolve)
    resolve_group_requested = Signal(list)  # list[int] error_ids (グループ一括 resolve)
    filter_changed = Signal()  # フィルタ/表示モード変更 → controller が再取得
    image_link_clicked = Signal(int)  # image_id (将来 Search 連携用)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorsTriageWidget")
        self._root = QVBoxLayout(self)

    def display(
        self,
        summary: ErrorTriageSummary,
        groups: list[ErrorGroup],
        rows: list[ErrorRow],
    ) -> None:
        """サマリ band + (グループ表示 or 個別行表示) を再描画する。"""

    def get_filter(self) -> ErrorFilter:
        """フィルタ UI の現在の選択状態を返す。"""
        return ErrorFilter()

    def is_grouped(self) -> bool:
        """グループ表示モードなら True、個別行モードなら False。"""
        return True

    def set_filter_options(
        self, operation_types: list[str], error_types: list[str], model_names: list[str]
    ) -> None:
        """フィルタ combo の選択肢を設定する。"""
