"""Frame 5 · Results 読み取り専用トリアージ表示ウィジェット。

``QualityIssueDetectionService`` が算出した ``BatchTriageSummary`` /
``ImageTriageResult`` を受け取り、サマリ band・issue カード・per-image 行を
描画する。検出ロジックは持たず表示に専念する (MVC の View)。
"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from lorairo.services.quality_issue_detection_service import (
    BatchTriageSummary,
    ImageTriageResult,
)


class ResultsWidget(QWidget):
    """Frame 5 · Results 読み取り専用トリアージ表示。objectName = "resultsWidget"。"""

    review_requested = Signal(int)  # image_id (Annotate へ遷移要求。Phase 2b で接続)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultsWidget")
        self._root = QVBoxLayout(self)

    def display(self, summary: BatchTriageSummary, results: list[ImageTriageResult]) -> None:
        """サマリ band・issue カード・per-image 行を再描画する。"""

    def clear(self) -> None:
        """空状態 (ステージング 0 件) を表示する。"""
