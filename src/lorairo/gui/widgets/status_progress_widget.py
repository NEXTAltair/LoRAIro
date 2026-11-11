"""ステータスバー常設の進捗表示部品。

`QStatusBar.showMessage` の一時メッセージは操作結果の通知専用とし、進捗は
`addPermanentWidget` で載せた本部品へ表示する。常設部品は一時メッセージで隠れない。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

_LABEL_MAX_WIDTH = 360
_BAR_WIDTH = 160


class StatusProgressWidget(QWidget):
    """工程名ラベルと進捗バーからなるステータスバー常設の進捗部品。

    進捗が無いときは非表示。``set_progress`` で表示し、``clear`` で隠す。
    件数が分からない工程 (``total`` 未指定または 0 以下) は不定進捗で表示する。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """部品を初期化する。初期状態は非表示。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._text = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.label = QLabel(self)
        self.label.setObjectName("statusProgressLabel")
        self.label.setMaximumWidth(_LABEL_MAX_WIDTH)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName("statusProgressBar")
        self.progress_bar.setFixedWidth(_BAR_WIDTH)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        self.setVisible(False)

    def set_progress(self, text: str, current: int | None = None, total: int | None = None) -> None:
        """工程名と進捗状態を設定して表示する。

        Args:
            text: 工程名 (表示テキスト)。長い場合は省略表示し、全文はツールチップに出す。
            current: 処理済み件数。``total`` が有効なときだけ使う。
            total: 総件数。``None`` または 0 以下なら不定進捗にする。
        """
        self._text = text
        metrics = self.label.fontMetrics()
        self.label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, _LABEL_MAX_WIDTH))
        self.label.setToolTip(text)
        if total is None or total <= 0:
            # 件数不明: 不定進捗 (range 0..0 で Qt がビジー表示する)
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(min(max(current or 0, 0), total))
        self.setVisible(True)

    def clear(self) -> None:
        """進捗を消して部品を隠す。"""
        self._text = ""
        self.label.clear()
        self.label.setToolTip("")
        # 不定進捗のアニメーションを止めるため確定レンジへ戻す
        self.progress_bar.setRange(0, 100)
        self.progress_bar.reset()
        self.setVisible(False)

    def text(self) -> str:
        """現在の工程名 (省略前の全文) を返す。"""
        return self._text

    def is_indeterminate(self) -> bool:
        """不定進捗で表示中なら True。"""
        return self.progress_bar.minimum() == 0 and self.progress_bar.maximum() == 0
