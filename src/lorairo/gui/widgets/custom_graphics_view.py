# src/lorairo/gui/widgets/custom_graphics_view.py

from __future__ import annotations

from typing import Any, overload

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QWidget

from .thumbnail_item import ThumbnailItem


class CustomGraphicsView(QGraphicsView):
    """
    アイテムのクリックを処理し、信号を発行するカスタムQGraphicsView。

    標準OS準拠の選択動作:
    - Click: 単一選択
    - Ctrl+Click: トグル選択
    - Shift+Click: 範囲選択
    - Ctrl+Shift+Click: 範囲追加選択
    - ドラッグ: ラバーバンド矩形選択
    - Ctrl+ドラッグ / Shift+ドラッグ: 既存選択に矩形選択を追加

    Note: Ctrl+A全選択はMainWindowのactionSelectAllで処理
    """

    itemClicked = Signal(ThumbnailItem, Qt.KeyboardModifier)
    emptySpaceClicked = Signal()

    @overload
    def __init__(self, parent: QWidget | None = None) -> None: ...

    @overload
    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None: ...

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        CustomGraphicsViewを初期化する。

        QGraphicsViewの複数の初期化形式をサポート:
        - CustomGraphicsView(parent)
        - CustomGraphicsView(scene, parent)
        """
        super().__init__(*args, **kwargs)
        self._drag_modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier
        # キーボードフォーカスを受け取れるように設定（将来のキー操作対応のため）
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """
        マウスプレスイベントを処理する。

        左クリック時のみ選択ロジックを処理し、右クリックは無視してコンテキストメニューに委譲する。
        アイテムクリック時はitemClickedシグナルを発行し、super()を呼ばない。
        これによりQtのシーン選択が独自の選択ロジックを上書きするのを防止する。
        空スペースクリック時のみsuper()を呼び、ラバーバンドドラッグを有効にする。

        Args:
            event: マウスイベント
        """
        # 右クリックは無視（コンテキストメニューで処理）
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        item = self.itemAt(event.position().toPoint())
        if isinstance(item, ThumbnailItem):
            # アイテム上のクリック: 独自の選択ロジックで処理
            # super()を呼ばないことで、Qtのシーン選択による上書きを防止
            self.itemClicked.emit(item, event.modifiers())
        else:
            # 空スペース: ドラッグ修飾子を記録してラバーバンド開始
            self._drag_modifiers = event.modifiers()
            if not (
                event.modifiers()
                & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            ):
                # 修飾子なしの空スペースクリック → 選択解除用シグナル
                self.emptySpaceClicked.emit()
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """
        マウスリリースイベント処理。

        ラバーバンドドラッグ終了後にドラッグ修飾子をリセットする。

        Args:
            event: マウスイベント
        """
        super().mouseReleaseEvent(event)
        self._drag_modifiers = Qt.KeyboardModifier.NoModifier
