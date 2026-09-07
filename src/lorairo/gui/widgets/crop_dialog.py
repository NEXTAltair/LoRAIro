"""クロップ (切り出し) 作成ダイアログ (#1345)。

元画像上で矩形を選び、切り出し結果・実寸・採用タグ・レーティングを確認してから
保存する専用ウィンドウ。DB / サービスには依存せず、入力は画像パス・候補タグ・親の
レーティング、出力は :class:`~lorairo.domain.crop_request.CropCreateRequest` と
コンストラクタで注入された保存 callback だけとする (#983 TagPanelWidget / ADR 0083
と同じ「見える部分を DB 非依存で先に作る」方式)。

このモジュールは ``lorairo.database`` / ``lorairo.services`` / ``lorairo.gui.services``
/ ``lorairo.gui.workers`` を import しない (受け入れ条件、テストで検査する)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...domain.crop_request import (
    CROP_LONG_EDGE_WARNING_PX,
    DEFAULT_CROP_ORIGIN,
    CropCreateRequest,
    CropRect,
)
from ...utils.log import logger
from .. import theme
from .crop_rect_selector import CropRectSelectorWidget
from .crop_tag_list_widget import ClickableTagListWidget
from .ds_segmented_control import DsSegmentedControl

# レーティングの正準順序。rating_score_edit_widget._RATING_ORDER と同じ並びだが、
# private 名を import しないためここに再掲する。
_RATING_VALUES: tuple[str, ...] = ("PG", "PG-13", "R", "X", "XXX")

_NO_SELECTION_TEXT = "選択範囲なし"
_RESOLUTION_WARNING_TEXT = (
    "長辺が1024px未満です。学習時に拡大すると、ぼけや細部不足が品質に影響する場合があります。"
)
_TAG_LIST_MAX_HEIGHT = 180


class _CropPreviewLabel(QLabel):
    """切り出し結果を縦横比を保って表示するプレビュー用ラベル。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        """プレビューラベルを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._source: QPixmap | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 150)
        self.setStyleSheet(
            f"background-color: {theme.PAPER_SHADE};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" color: {theme.INK_FAINT};"
        )
        self.setText(_NO_SELECTION_TEXT)

    def set_source_pixmap(self, pixmap: QPixmap | None) -> None:
        """表示する切り出し結果を差し替える。

        Args:
            pixmap: 切り出し済みの QPixmap。None で「選択範囲なし」表示に戻す。
        """
        self._source = pixmap
        self._rescale()

    def resizeEvent(self, event: QResizeEvent) -> None:
        """リサイズに追従してスケールし直す。"""
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        """保持している pixmap を現在のラベル寸法へ収める。"""
        if self._source is None or self._source.isNull():
            self.clear()
            self.setText(_NO_SELECTION_TEXT)
            return
        self.setPixmap(
            self._source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class CropDialog(QDialog):
    """切り出し範囲を選んで子画像を作るダイアログ。

    Signals:
        saved (int): 保存に成功した際、生成された子画像 ID を emit する。
    """

    saved = Signal(int)

    def __init__(
        self,
        *,
        image_path: Path,
        parent_image_id: int,
        candidate_tags: Sequence[str],
        parent_rating: str | None,
        save_callback: Callable[[CropCreateRequest], int],
        parent: QWidget | None = None,
    ) -> None:
        """ダイアログを構築する。

        Args:
            image_path: 切り出し元となる親画像のパス。
            parent_image_id: 親画像の images.id。
            candidate_tags: 親から引き継げる候補タグ (このリスト自体は変更しない)。
            parent_rating: 親画像のレーティング。採用タグと同じく初期値として使う。
            save_callback: 保存要求を受け取り子画像 ID を返す callback。
                失敗時は例外を送出してよい (ダイアログは閉じずにエラーを表示する)。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._image_path = image_path
        self._parent_image_id = parent_image_id
        # 呼び出し側の一覧オブジェクトを変更しないようコピーして保持する
        self._initial_candidates: list[str] = list(candidate_tags)
        self._candidate_tags: list[str] = list(candidate_tags)
        self._adopted_tags: list[str] = []
        self._initial_rating: str | None = parent_rating if parent_rating in _RATING_VALUES else None
        self._rating: str | None = self._initial_rating
        self._save_callback = save_callback
        self._save_in_progress = False
        self._saved = False
        self._child_image_id: int | None = None
        # closeEvent → QDialog::closeEvent → reject() の二重確認を防ぐフラグ
        self._close_confirmed = False

        self.setWindowTitle("切り出し範囲の指定")
        self.setObjectName("cropDialog")
        self.setModal(True)
        self.setSizeGripEnabled(True)
        # 専用ウィンドウとしてサイズ変更・最大化できるようにする
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )
        self.resize(1100, 720)

        self._build_ui()
        self._connect_signals()

        self._selector.set_image(image_path)
        self._candidate_list.set_tags(self._candidate_tags)
        self._adopted_list.set_tags(self._adopted_tags)
        self._refresh_rect_dependent(self._selector.crop_rect())

    # ------------------------------------------------------------------
    # UI 構築
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """左 (元画像 + 候補タグ) / 右 (結果 + 採用タグ + 操作) の 2 ペインを組む。"""
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(self._section_label("元画像 — ドラッグで切り出し範囲を選択"))
        self._selector = CropRectSelectorWidget(self)
        left.addWidget(self._selector, 1)
        left.addWidget(self._section_label("候補タグ — クリックで採用へ移動"))
        self._candidate_list = ClickableTagListWidget(self)
        self._candidate_list.setMaximumHeight(_TAG_LIST_MAX_HEIGHT)
        left.addWidget(self._candidate_list)

        right = QVBoxLayout()
        right.addWidget(self._section_label("切り出し結果"))
        self._preview = _CropPreviewLabel(self)
        right.addWidget(self._preview, 1)

        self._size_label = QLabel(_NO_SELECTION_TEXT, self)
        self._size_label.setObjectName("cropSizeLabel")
        self._size_label.setStyleSheet(
            f"font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_BASE}px;"
        )
        right.addWidget(self._size_label)

        self._warning_label = QLabel(_RESOLUTION_WARNING_TEXT, self)
        self._warning_label.setObjectName("cropResolutionWarning")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(
            f"color: {theme.WARN}; background-color: {theme.WARN_SOFT};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.WARN_BORDER};"
            f" border-radius: {theme.RADIUS}px; padding: 4px 6px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px;"
        )
        self._warning_label.hide()
        right.addWidget(self._warning_label)

        right.addWidget(self._section_label("採用タグ — クリックで候補へ戻す"))
        self._adopted_list = ClickableTagListWidget(self)
        self._adopted_list.setMaximumHeight(_TAG_LIST_MAX_HEIGHT)
        right.addWidget(self._adopted_list)

        right.addWidget(self._section_label("レーティング"))
        self._rating_control = DsSegmentedControl(
            [(value, value) for value in _RATING_VALUES],
            value=self._rating or "",
            size="small",
            parent=self,
        )
        right.addWidget(self._rating_control)

        self._error_label = QLabel("", self)
        self._error_label.setObjectName("cropErrorLabel")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(f"color: {theme.ERR}; font-size: {theme.FONT_SIZE_SMALL}px;")
        self._error_label.hide()
        right.addWidget(self._error_label)

        self._button_box = QDialogButtonBox(self)
        self._save_button = QPushButton("保存", self)
        self._cancel_button = QPushButton("キャンセル", self)
        self._button_box.addButton(self._save_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self._button_box.addButton(self._cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        right.addWidget(self._button_box)

        root.addLayout(left, 3)
        root.addLayout(right, 2)

    def _section_label(self, text: str) -> QLabel:
        """セクション見出し用の小さなラベルを作る。

        Args:
            text: 見出し文字列。

        Returns:
            スタイル適用済みの QLabel。
        """
        label = QLabel(text, self)
        label.setStyleSheet(
            f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;"
            f" letter-spacing: {theme.LETTER_CAPS};"
        )
        return label

    def _connect_signals(self) -> None:
        """ウィジェット間の Signal/Slot を接続する。"""
        self._selector.rect_changed.connect(self._on_rect_changed)
        self._candidate_list.tag_clicked.connect(self._on_candidate_clicked)
        self._adopted_list.tag_clicked.connect(self._on_adopted_clicked)
        self._rating_control.value_changed.connect(self._on_rating_changed)
        self._save_button.clicked.connect(self._on_save)
        self._cancel_button.clicked.connect(self.reject)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def crop_rect(self) -> CropRect | None:
        """現在の選択矩形 (親画像ピクセル座標)。未選択なら None。"""
        return self._selector.crop_rect()

    def set_rect(self, rect: CropRect | None) -> None:
        """選択矩形をプログラムから設定する (主にテスト・外部連携用)。

        Args:
            rect: 設定する矩形。None で選択解除。
        """
        self._selector.set_rect(rect)

    def candidate_tags(self) -> list[str]:
        """現在の候補タグ一覧 (表示順)。"""
        return list(self._candidate_tags)

    def adopted_tags(self) -> list[str]:
        """現在の採用タグ一覧 (採用した順)。"""
        return list(self._adopted_tags)

    def rating(self) -> str | None:
        """現在選択中のレーティング。未選択なら None。"""
        return self._rating

    def size_text(self) -> str:
        """実寸ピクセル表示の文字列。"""
        return self._size_label.text()

    def is_resolution_warning_visible(self) -> bool:
        """解像度警告が表示状態か。

        Note:
            ``isVisible()`` は親が未表示だと常に False になるため、明示的な
            hide/show を反映する ``isHidden()`` で判定する。
        """
        return not self._warning_label.isHidden()

    def error_message(self) -> str:
        """保存失敗時に表示しているエラー文言 (未発生なら空文字)。"""
        return self._error_label.text()

    def can_save(self) -> bool:
        """保存ボタンが押せる状態か (無効な矩形・保存実行中は False)。"""
        return self._save_button.isEnabled()

    def child_image_id(self) -> int | None:
        """保存に成功して生成された子画像 ID。未保存なら None。"""
        return self._child_image_id

    def build_request(self) -> CropCreateRequest:
        """現在の選択内容から保存 request を作る。

        Returns:
            保存サービスへ渡す :class:`CropCreateRequest`。

        Raises:
            ValueError: 有効な矩形が選択されていない場合。
        """
        crop = self._selector.crop_rect()
        if crop is None or not crop.has_positive_size():
            raise ValueError("有効な切り出し範囲が選択されていません")
        return CropCreateRequest(
            parent_image_id=self._parent_image_id,
            rect=crop,
            tags=tuple(self._adopted_tags),
            rating=self._rating,
            origin=DEFAULT_CROP_ORIGIN,
        )

    # ------------------------------------------------------------------
    # Slot
    # ------------------------------------------------------------------

    @Slot(object)
    def _on_rect_changed(self, rect: object) -> None:
        """矩形変更をプレビュー・実寸・警告・保存可否へ反映する。"""
        crop = rect if isinstance(rect, CropRect) else None
        self._refresh_rect_dependent(crop)

    @Slot(str)
    def _on_candidate_clicked(self, tag: str) -> None:
        """候補タグを採用側へ移す。"""
        if tag not in self._candidate_tags:
            return
        self._candidate_tags.remove(tag)
        self._adopted_tags.append(tag)
        self._refresh_tag_lists()

    @Slot(str)
    def _on_adopted_clicked(self, tag: str) -> None:
        """採用タグを候補側へ戻す (元の候補順を保つ)。"""
        if tag not in self._adopted_tags:
            return
        self._adopted_tags.remove(tag)
        self._candidate_tags.insert(self._candidate_insert_index(tag), tag)
        self._refresh_tag_lists()

    @Slot(str)
    def _on_rating_changed(self, value: str) -> None:
        """レーティング選択を保持する。"""
        self._rating = value or None

    @Slot()
    def _on_save(self) -> None:
        """保存 callback を呼び、成功なら閉じ、失敗ならエラーを表示して残る。"""
        if self._save_in_progress:
            return
        try:
            request = self.build_request()
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self._show_error("")
        self._save_in_progress = True
        self._update_save_enabled()
        try:
            child_image_id = self._save_callback(request)
        except Exception as exc:
            # save_callback は呼び出し側 (service / DB 層) の任意の例外を投げうる。
            # ダイアログを閉じずに失敗を提示する責務があるため、ここだけ広く受ける。
            logger.error(f"クロップ画像の保存に失敗しました (parent={self._parent_image_id}): {exc}")
            self._show_error(f"保存に失敗しました: {exc}")
            return
        finally:
            self._save_in_progress = False
            self._update_save_enabled()

        self._child_image_id = int(child_image_id)
        self._saved = True
        logger.info(
            f"クロップ画像を保存しました: parent={self._parent_image_id} child={self._child_image_id}"
        )
        self.saved.emit(self._child_image_id)
        self.accept()

    # ------------------------------------------------------------------
    # 閉じる際の破棄確認
    # ------------------------------------------------------------------

    def reject(self) -> None:
        """未保存の変更があれば破棄確認を挟んでから閉じる。"""
        if self._close_confirmed or self._confirm_discard():
            self._close_confirmed = False
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウを閉じる操作にも破棄確認を挟む。"""
        if not self._confirm_discard():
            event.ignore()
            return
        # QDialog::closeEvent が reject() を呼ぶため、二重確認しないよう印を立てる
        self._close_confirmed = True
        super().closeEvent(event)
        self._close_confirmed = False

    def _confirm_discard(self) -> bool:
        """閉じてよいかを判定する (未保存の変更があるときだけ確認する)。

        Returns:
            閉じてよければ True。
        """
        if not self._has_unsaved_changes():
            return True
        answer = QMessageBox.question(
            self,
            "変更を破棄しますか",
            "保存していない変更があります。破棄して閉じますか?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _has_unsaved_changes(self) -> bool:
        """矩形・採用タグ・レーティングのいずれかが初期状態から変化しているか。"""
        if self._saved:
            return False
        if self._selector.crop_rect() is not None:
            return True
        if self._adopted_tags:
            return True
        return self._rating != self._initial_rating

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _candidate_insert_index(self, tag: str) -> int:
        """採用から戻すタグを、元の候補順を保った位置へ差し込むための index を返す。

        Args:
            tag: 候補へ戻すタグ。

        Returns:
            ``self._candidate_tags`` への挿入位置。元の並びに無いタグは末尾。
        """
        if tag not in self._initial_candidates:
            return len(self._candidate_tags)
        original_index = self._initial_candidates.index(tag)
        for position, existing in enumerate(self._candidate_tags):
            if existing not in self._initial_candidates:
                continue
            if self._initial_candidates.index(existing) > original_index:
                return position
        return len(self._candidate_tags)

    def _refresh_tag_lists(self) -> None:
        """候補・採用の 2 リストを現在の状態で描き直す。"""
        self._candidate_list.set_tags(self._candidate_tags)
        self._adopted_list.set_tags(self._adopted_tags)

    def _refresh_rect_dependent(self, crop: CropRect | None) -> None:
        """矩形に連動する表示 (プレビュー / 実寸 / 警告 / 保存可否) を更新する。"""
        self._preview.set_source_pixmap(self._cropped_pixmap(crop))
        if crop is None:
            self._size_label.setText(_NO_SELECTION_TEXT)
        else:
            self._size_label.setText(f"{crop.width} x {crop.height} px")
        show_warning = (
            crop is not None and crop.has_positive_size() and crop.long_edge < CROP_LONG_EDGE_WARNING_PX
        )
        self._warning_label.setHidden(not show_warning)
        self._update_save_enabled()

    def _cropped_pixmap(self, crop: CropRect | None) -> QPixmap | None:
        """選択矩形で元画像を切り出した QPixmap を返す。無効なら None。"""
        source = self._selector.source_pixmap()
        if source is None or crop is None or not crop.has_positive_size():
            return None
        return source.copy(QRect(crop.x, crop.y, crop.width, crop.height))

    def _update_save_enabled(self) -> None:
        """矩形の妥当性と保存実行中フラグから保存ボタンの有効/無効を決める。"""
        crop = self._selector.crop_rect()
        valid = crop is not None and crop.has_positive_size()
        self._save_button.setEnabled(valid and not self._save_in_progress)

    def _show_error(self, message: str) -> None:
        """エラー表示を更新する (空文字で非表示)。

        Args:
            message: 表示するエラー文言。
        """
        self._error_label.setText(message)
        self._error_label.setHidden(not message)
