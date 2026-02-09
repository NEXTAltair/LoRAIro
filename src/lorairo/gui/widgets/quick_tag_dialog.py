# src/lorairo/gui/widgets/quick_tag_dialog.py
"""クイックタグダイアログ - サムネイル上でタグを素早く追加するためのモーダルダイアログ。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...utils.log import logger
from .batch_tag_add_widget import normalize_tag


class QuickTagDialog(QDialog):
    """クイックタグ追加ダイアログ。

    サムネイル上で右クリック時に表示され、
    選択された画像にタグを素早く追加できる。

    Signals:
        tag_add_requested: タグ追加リクエスト (image_ids: list[int], tag: str)
    """

    tag_add_requested = Signal(list, str)

    def __init__(
        self,
        image_ids: list[int],
        parent: QWidget | None = None,
    ) -> None:
        """QuickTagDialogを初期化する。

        Args:
            image_ids: タグを追加する画像IDのリスト
            parent: 親ウィジェット
        """
        super().__init__(parent)
        self._image_ids = image_ids

        self.setWindowTitle(f"クイックタグ追加 ({len(image_ids)}枚)")
        self.setWindowFlags(Qt.WindowType.Dialog)
        self.setMinimumWidth(350)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """UIをセットアップする。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 説明ラベル
        info_label = QLabel(f"選択した {len(self._image_ids)} 枚の画像にタグを追加します")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # タグ入力
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("タグを入力...")
        self._tag_input.returnPressed.connect(self._on_add_clicked)
        input_layout.addWidget(self._tag_input)

        layout.addLayout(input_layout)

        # ボタン
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self._cancel_button = QPushButton("キャンセル")
        self._cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self._cancel_button)

        self._add_button = QPushButton("追加")
        self._add_button.setDefault(True)
        self._add_button.clicked.connect(self._on_add_clicked)
        button_layout.addWidget(self._add_button)

        layout.addLayout(button_layout)

    def _on_add_clicked(self) -> None:
        """追加ボタンクリック時の処理。"""
        tag = self._tag_input.text().strip()
        if not tag:
            self._tag_input.setPlaceholderText("タグを入力してください")
            return

        # タグ正規化（BatchTagAddWidgetと同じロジック）
        normalized_tag = self._normalize_tag(tag)
        if not normalized_tag:
            logger.warning(f"Tag normalization failed for: {tag}")
            QMessageBox.warning(self, "タグエラー", f"タグ '{tag}' の正規化に失敗しました。")
            return

        logger.info(f"Quick tag add: {normalized_tag} to {len(self._image_ids)} images")
        self.tag_add_requested.emit(self._image_ids, normalized_tag)
        self.accept()

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        """タグを正規化する（モジュールレベル normalize_tag() に委譲）。

        Args:
            tag: 入力タグ文字列

        Returns:
            正規化されたタグ（TagCleaner.clean_format() + lower + strip）
        """
        return normalize_tag(tag)

    def showEvent(self, event: QShowEvent) -> None:
        """ダイアログ表示時にフォーカスを設定。"""
        super().showEvent(event)
        self._tag_input.setFocus()
        self._tag_input.selectAll()
