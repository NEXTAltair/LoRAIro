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

from PySide6.QtCore import QObject, QRect, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QPainter, QPaintEvent, QPixmap
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
    """元画像の選択範囲を、縦横比を保って表示するプレビュー用ラベル。

    元画像と選択矩形をそのまま保持し、``paintEvent`` で表示サイズの矩形へ直接
    描画する。ドラッグ中の毎フレームでフル解像度の切り出しコピー
    (``QPixmap.copy``) を作らないため、4K/8K の選択でも確保するメモリは
    ラベル寸法ぶんだけで済む。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """プレビューラベルを構築する。

        Args:
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._source: QPixmap | None = None
        self._crop: CropRect | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(200, 150)
        self.setStyleSheet(
            f"background-color: {theme.PAPER_SHADE};"
            f" border: {theme.BORDER_WIDTH}px solid {theme.LINE};"
            f" color: {theme.INK_FAINT};"
        )
        self.setText(_NO_SELECTION_TEXT)

    def set_preview(self, source: QPixmap | None, crop: CropRect | None) -> None:
        """表示する元画像と切り出し範囲を差し替える。

        Args:
            source: 切り出し元の QPixmap (コピーせず参照だけ保持する)。
            crop: 切り出し範囲。None / 無効な矩形なら「選択範囲なし」表示に戻す。
        """
        self._source = source
        self._crop = crop
        if self._source_rect() is None:
            self.setText(_NO_SELECTION_TEXT)
        else:
            # 文字列を消して背景と枠だけを基底クラスに描かせ、その上に自前描画する
            self.setText("")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """背景・枠を基底クラスに描かせたうえで、選択範囲を表示サイズへ直接描く。"""
        super().paintEvent(event)
        source_rect = self._source_rect()
        target_rect = self._target_rect(source_rect)
        if self._source is None or source_rect is None or target_rect is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(target_rect, self._source, source_rect)
        painter.end()

    def _source_rect(self) -> QRect | None:
        """元画像から切り出す矩形 (画像範囲内へクリップ済み)。描けないなら None。"""
        if self._source is None or self._source.isNull():
            return None
        if self._crop is None or not self._crop.has_positive_size():
            return None
        clipped = QRect(self._crop.x, self._crop.y, self._crop.width, self._crop.height).intersected(
            self._source.rect()
        )
        return clipped if not clipped.isEmpty() else None

    def _target_rect(self, source_rect: QRect | None) -> QRect | None:
        """切り出し範囲を縦横比を保って中央配置したときの描画先矩形。"""
        if source_rect is None:
            return None
        area = self.contentsRect()
        if area.isEmpty():
            return None
        scaled = source_rect.size().scaled(area.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(
            area.x() + (area.width() - scaled.width()) // 2,
            area.y() + (area.height() - scaled.height()) // 2,
            scaled.width(),
            scaled.height(),
        )


class _CropSaveWorker(QObject):
    """保存 callback を GUI スレッド外で実行するワーカー。

    Signals:
        succeeded (int): 保存に成功した際、生成された子画像 ID を emit する。
        failed (object): 保存に失敗した際、送出された例外オブジェクトを emit する。
    """

    succeeded = Signal(int)
    failed = Signal(object)

    def __init__(self, callback: Callable[[CropCreateRequest], int], request: CropCreateRequest) -> None:
        """ワーカーを構築する。

        Args:
            callback: 保存要求を受け取り子画像 ID を返す callback。
            request: 実行する保存要求。

        Note:
            ``moveToThread`` するため親は持たせない (所有権はダイアログ側の属性で保持する)。
        """
        super().__init__()
        self._callback = callback
        self._request = request

    @Slot()
    def run(self) -> None:
        """保存 callback を実行し、結果または例外を Signal で返す。"""
        try:
            child_image_id = self._callback(self._request)
        except Exception as exc:
            # save_callback は呼び出し側 (service / DB 層) の任意の例外を投げうる。
            # ワーカースレッドで例外を落とすとアプリごと終了しうるため、ここだけ広く受けて
            # GUI スレッドへ渡す (提示と後始末はダイアログの責務)。
            self.failed.emit(exc)
            return
        self.succeeded.emit(int(child_image_id))


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
        # 実行中に GC されると emit 先が消えてクラッシュするため、thread / worker の
        # 両方を属性で保持する (docs/lessons-learned.md の PySide6 節)
        self._save_thread: QThread | None = None
        self._save_worker: _CropSaveWorker | None = None
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
        """保存 callback をワーカースレッドで実行する (完了は Signal で受ける)。"""
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

        thread = QThread(self)
        worker = _CropSaveWorker(self._save_callback, request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # worker は別スレッドにいるので、既定の AutoConnection で GUI スレッドへ queued 配送される
        worker.succeeded.connect(self._on_save_succeeded)
        worker.failed.connect(self._on_save_failed)
        self._save_thread = thread
        self._save_worker = worker
        thread.start()

    @Slot(int)
    def _on_save_succeeded(self, child_image_id: int) -> None:
        """保存成功をダイアログへ反映し、閉じる。"""
        self._finish_save()
        self._child_image_id = int(child_image_id)
        self._saved = True
        logger.info(
            f"クロップ画像を保存しました: parent={self._parent_image_id} child={self._child_image_id}"
        )
        self.saved.emit(self._child_image_id)
        self.accept()

    @Slot(object)
    def _on_save_failed(self, error: object) -> None:
        """保存失敗をログとエラーラベルへ反映し、ダイアログは閉じずに残す。"""
        self._finish_save()
        exc = error if isinstance(error, BaseException) else RuntimeError(str(error))
        logger.opt(exception=exc).error(
            f"クロップ画像の保存に失敗しました (parent={self._parent_image_id}): {exc}"
        )
        self._show_error(f"保存に失敗しました: {exc}")

    def _finish_save(self) -> None:
        """保存スレッドを止めて参照を解放し、保存中フラグを下ろす。"""
        thread = self._save_thread
        if thread is not None:
            thread.quit()
            thread.wait()
        self._save_thread = None
        self._save_worker = None
        self._save_in_progress = False
        self._update_save_enabled()

    # ------------------------------------------------------------------
    # 閉じる際の破棄確認
    # ------------------------------------------------------------------

    def reject(self) -> None:
        """未保存の変更があれば破棄確認を挟んでから閉じる (保存中は閉じない)。"""
        if self._save_in_progress:
            return
        if self._close_confirmed or self._confirm_discard():
            self._close_confirmed = False
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        """ウィンドウを閉じる操作にも破棄確認を挟む (保存中は閉じない)。"""
        if self._save_in_progress:
            event.ignore()
            return
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
        self._preview.set_preview(self._selector.source_pixmap(), crop)
        if crop is None:
            self._size_label.setText(_NO_SELECTION_TEXT)
        else:
            self._size_label.setText(f"{crop.width} x {crop.height} px")
        show_warning = (
            crop is not None and crop.has_positive_size() and crop.long_edge < CROP_LONG_EDGE_WARNING_PX
        )
        self._warning_label.setHidden(not show_warning)
        self._update_save_enabled()

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
