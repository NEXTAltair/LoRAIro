"""CLI タブの専用ウィジェット (Epic #867)。

agent-friendly CLI 契約 (ADR 0057-0060) を図解する読み取り専用リファレンス
`CliReferenceWidget` をホストする。DB 接続不要のため依存注入はない。
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..widgets.cli_reference_widget import CliReferenceWidget


class CliTabWidget(QWidget):
    """CLI タブのルートウィジェット。

    読み取り専用の `CliReferenceWidget` を内包する。コンテンツは
    `CliReferenceWidget` 側で初回表示時に遅延生成される。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """CLI タブを初期化する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._reference = CliReferenceWidget(parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._reference)

    @property
    def reference(self) -> CliReferenceWidget:
        """内包する `CliReferenceWidget` を返す (テスト用)。"""
        return self._reference
