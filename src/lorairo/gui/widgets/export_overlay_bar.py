"""エクスポート前タグ編集パネルの下部 ExportOverlayBar ウィジェット（Issue #948）。

Epic #942 の下部バー。trigger 語彙補完・overlay chip 一覧・適用先スコープ・
ライブ出力プレビュー・エクスポート操作を提供する。配線は後続 #949 が行うため、
本ウィジェットはシグナル emit と公開メソッドまで担当する。

2層色分け (ADR 0080):
    出力オーバーレイ層（橙/一時）のみを扱う。DB 編集層（青/永続）は左ペイン
    StagingTagPanel (#947) の責務。

依存:
    - apply_overlay / ExportTagOverlay（#944、ADR 0080 S1a）: ライブプレビュー生成。
    - TriggerVocabService（#946、S1c）: trigger 語彙補完。未注入なら in-memory スタブ。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import TYPE_CHECKING, Protocol

from loguru import logger
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lorairo.gui import theme
from lorairo.services.export_overlay import ExportTagOverlay, apply_overlay
from lorairo.services.trigger_vocab import VocabEntry

from .changed_since_filter_widget import ChangedSinceFilterWidget

if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader

# エクスポート解像度の選択肢（image.py の target_resolutions と一致）。
_RESOLUTION_CHOICES: list[int] = [512, 768, 1024, 1536]
# 出力形式の (値, 表示ラベル)。値は既存 DatasetExportWorker の export_format に一致させる
# （txt_separate / txt_merged / json）。実書き出しは #949 / DatasetExportWorker が担う。
_FORMAT_CHOICES: list[tuple[str, str]] = [
    ("txt_separate", "TXT（タグ分離）"),
    ("txt_merged", "TXT（キャプション統合）"),
    ("json", "JSON"),
]


class _VocabLike(Protocol):
    """TriggerVocabService の構造的インターフェイス（テスト用スタブ差し替え用）。"""

    def search(self, prefix: str) -> list[VocabEntry]: ...
    def register(self, word: str) -> None: ...


class _InMemoryTriggerVocab:
    """TriggerVocabService 未注入時のフォールバック in-memory 語彙。

    DB を持たず、本セッション中に register した trigger だけを補完候補にする。
    S1c (#946) 未配線でも ExportOverlayBar が単体で動作するための最小実装。
    """

    def __init__(self) -> None:
        self._words: list[str] = []

    def search(self, prefix: str) -> list[VocabEntry]:
        q = prefix.strip().lower()
        return [VocabEntry(word=w, freq=0) for w in self._words if q in w.lower()]

    def register(self, word: str) -> None:
        literal = word.strip()
        if literal and literal not in self._words:
            self._words.append(literal)


class ExportOverlayBar(QWidget):
    """trigger 補完・overlay 一覧・スコープ・ライブプレビュー・エクスポートの下部バー。

    overlay（trigger 追加 / 出力除外 / 置換）を保持し、変更のたびに ``overlay_changed``
    を ExportTagOverlay で emit する。選択画像の DB タグへ ``apply_overlay`` を適用した
    最終 .txt 行を等幅プレビューに表示する（overlay 変更・選択変更で即更新）。

    Signals:
        overlay_changed: overlay 変更で現在の ExportTagOverlay を emit。
        scope_changed: 適用先スコープ切替で "all" | "filtered" を emit。
        validate_requested: 検証ボタンで emit（実検証は #949 連携）。
        export_requested: エクスポートボタンで emit（実書き出しは #949 連携）。
    """

    # 公開シグナル契約（#949 が配線）
    overlay_changed = Signal(object)  # ExportTagOverlay
    scope_changed = Signal(str)  # "all" | "filtered"
    validate_requested = Signal()
    export_requested = Signal()

    def __init__(
        self,
        vocab: _VocabLike | None = None,
        reader: MergedTagReader | None = None,
        tag_format: str = "danbooru",
        parent: QWidget | None = None,
    ) -> None:
        """ExportOverlayBar を初期化する。

        Args:
            vocab: trigger 語彙サービス。None なら in-memory スタブを使う。
            reader: apply_overlay の convert に用いる MergedTagReader。None で convert スキップ。
            tag_format: convert の target format 名（プレビュー用）。
            parent: 親ウィジェット。
        """
        super().__init__(parent)
        self._vocab: _VocabLike = vocab if vocab is not None else _InMemoryTriggerVocab()
        self._reader = reader
        self._tag_format = tag_format

        # overlay の作業状態（変更のたびに ExportTagOverlay を再構築して emit する）。
        self._triggers: list[str] = []  # add（順序保持）
        self._excludes: list[str] = []  # exclude（順序保持の集合）
        self._replaces: dict[str, str] = {}  # replace X→Y

        self._scope = "all"  # "all" | "filtered"
        self._all_count = 0
        self._filtered_count = 0

        self._selected_image_id: int | None = None
        self._selected_db_tags: list[str] = []

        self._setup_ui()
        self._refresh_chips()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Public API（#949 が配線）
    # ------------------------------------------------------------------

    def current_overlay(self) -> ExportTagOverlay:
        """現在の overlay 作業状態から ExportTagOverlay を構築して返す。"""
        return ExportTagOverlay(
            add=list(self._triggers),
            exclude=set(self._excludes),
            replace=dict(self._replaces),
        )

    def set_selected_image(self, image_id: int | None, db_tags: list[str]) -> None:
        """ライブプレビュー対象の画像と DB タグ（reject 除外済み）を設定する。

        Args:
            image_id: 選択画像の DB ID。None でプレビューを空にする。
            db_tags: 選択画像の採用タグ（convert 前・soft-reject 除外済み）。
        """
        self._selected_image_id = image_id
        self._selected_db_tags = list(db_tags)
        self._refresh_preview()

    def add_overlay_exclude(self, tag: str) -> None:
        """出力除外 overlay を追加する（左ペイン StagingTagPanel からの要求受け）。

        Args:
            tag: 除外するタグ。空文字・重複は無視。
        """
        normalized = tag.strip()
        if not normalized or normalized in self._excludes:
            return
        self._excludes.append(normalized)
        self._on_overlay_mutated()

    def add_overlay_replace(self, frm: str, to: str) -> None:
        """置換 overlay を追加する（左ペイン StagingTagPanel からの要求受け）。

        Args:
            frm: 置換元タグ。
            to: 置換先タグ。frm が空、または frm == to は無視。
        """
        src = frm.strip()
        dst = to.strip()
        if not src or not dst or src == dst:
            return
        self._replaces[src] = dst
        self._on_overlay_mutated()

    def set_scope_counts(self, all_count: int, filtered_count: int) -> None:
        """スコープセグメントの件数表示を更新する（#949 が件数を供給）。

        Args:
            all_count: 全ステージング画像数。
            filtered_count: 絞り込み中の画像数。
        """
        self._all_count = all_count
        self._filtered_count = filtered_count
        self._all_btn.setText(f"全 {all_count} 枚")
        self._filtered_btn.setText(f"絞込 {filtered_count} 枚")

    def selected_resolution(self) -> int:
        """選択中のエクスポート解像度を返す。"""
        return int(self._resolution_combo.currentText())

    def selected_format(self) -> str:
        """選択中の出力形式値（"txt_separate" | "txt_merged" | "json"）を返す。

        既存 DatasetExportWorker の export_format に渡せる canonical 値を返す
        （表示ラベルではなく itemData の値）。
        """
        return str(self._format_combo.currentData())

    def changed_since_enabled(self) -> bool:
        """changed-since フィルタが有効かを返す。"""
        return self._changed_since_filter.is_enabled()

    def changed_since(self) -> datetime:
        """changed-since フィルタの cutoff 日時を返す。"""
        return self._changed_since_filter.since()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """UI コンポーネントを構築する。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(6)

        root.addLayout(self._build_trigger_row())
        root.addWidget(self._build_chip_area())
        root.addLayout(self._build_scope_row())
        root.addWidget(self._build_preview())
        root.addWidget(self._build_changed_since_filter())
        root.addLayout(self._build_export_row())

    def _build_trigger_row(self) -> QHBoxLayout:
        """trigger 入力 + 補完 + 追加ボタンの行を構築する。"""
        row = QHBoxLayout()
        row.setSpacing(6)

        label = QLabel("trigger")
        label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        row.addWidget(label)

        self._trigger_edit = QLineEdit()
        self._trigger_edit.setObjectName("triggerEdit")
        self._trigger_edit.setPlaceholderText("trigger word を入力（漢字可）…")
        self._trigger_edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 4px 6px; background: {theme.CARD}; color: {theme.INK};"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QLineEdit:focus {{ border-color: {theme.ACCENT}; }}"
        )
        self._trigger_edit.textChanged.connect(self._on_trigger_text_changed)
        self._trigger_edit.returnPressed.connect(self._on_trigger_commit)
        row.addWidget(self._trigger_edit, 1)

        # 補完候補ドロップダウン（textChanged で更新、選択で入力欄へ反映）。
        self._suggest_combo = QComboBox()
        self._suggest_combo.setObjectName("triggerSuggest")
        self._suggest_combo.setMinimumWidth(140)
        self._suggest_combo.setToolTip("登録済み trigger 語彙の補完候補")
        self._suggest_combo.activated.connect(self._on_suggest_activated)
        row.addWidget(self._suggest_combo)

        self._add_trigger_btn = QPushButton("追加")
        self._add_trigger_btn.setObjectName("addTriggerBtn")
        self._add_trigger_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_trigger_btn.setStyleSheet(self._accent_button_qss())
        self._add_trigger_btn.clicked.connect(self._on_trigger_commit)
        row.addWidget(self._add_trigger_btn)

        return row

    def _build_chip_area(self) -> QWidget:
        """overlay chip（trigger/exclude/replace）を並べる領域を構築する。"""
        from lorairo.gui.widgets.tag_cloud_widget import FlowLayout

        self._chip_container = QWidget()
        self._chip_container.setObjectName("overlayChipArea")
        self._chip_layout = FlowLayout(self._chip_container, spacing=4)
        return self._chip_container

    def _build_scope_row(self) -> QHBoxLayout:
        """適用先スコープのセグメント（全 / 絞込）を構築する。"""
        row = QHBoxLayout()
        row.setSpacing(6)

        label = QLabel("適用先")
        label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        row.addWidget(label)

        self._scope_group = QButtonGroup(self)
        self._all_btn = QPushButton(f"全 {self._all_count} 枚")
        self._all_btn.setObjectName("scopeAllBtn")
        self._all_btn.setCheckable(True)
        self._all_btn.setChecked(True)
        self._filtered_btn = QPushButton(f"絞込 {self._filtered_count} 枚")
        self._filtered_btn.setObjectName("scopeFilteredBtn")
        self._filtered_btn.setCheckable(True)
        for btn in (self._all_btn, self._filtered_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._segment_button_qss())
            self._scope_group.addButton(btn)
            row.addWidget(btn)
        self._all_btn.clicked.connect(lambda: self._on_scope_clicked("all"))
        self._filtered_btn.clicked.connect(lambda: self._on_scope_clicked("filtered"))

        row.addStretch(1)
        return row

    def _build_preview(self) -> QWidget:
        """ライブ出力プレビュー（等幅）を構築する。"""
        self._preview = QPlainTextEdit()
        self._preview.setObjectName("overlayPreview")
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(64)
        self._preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._preview.setStyleSheet(
            f"QPlainTextEdit {{ background: {theme.TERMINAL}; color: {theme.TERMINAL_FG};"
            f" border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" font-family: {theme.FONT_MONO_CSS}; font-size: {theme.FONT_SIZE_META}px;"
            f" padding: 4px 6px; }}"
        )
        return self._preview

    def _build_changed_since_filter(self) -> QWidget:
        """changed-since フィルタ行を構築する。"""
        self._changed_since_filter = ChangedSinceFilterWidget()
        return self._changed_since_filter

    def _build_export_row(self) -> QHBoxLayout:
        """解像度/形式選択 + 検証/エクスポートボタンの行を構築する。"""
        row = QHBoxLayout()
        row.setSpacing(6)

        res_label = QLabel("解像度")
        res_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        row.addWidget(res_label)
        self._resolution_combo = QComboBox()
        self._resolution_combo.setObjectName("resolutionCombo")
        for res in _RESOLUTION_CHOICES:
            self._resolution_combo.addItem(str(res))
        row.addWidget(self._resolution_combo)

        fmt_label = QLabel("形式")
        fmt_label.setStyleSheet(f"color: {theme.INK_SOFT}; font-size: {theme.FONT_SIZE_SMALL}px;")
        row.addWidget(fmt_label)
        self._format_combo = QComboBox()
        self._format_combo.setObjectName("formatCombo")
        for value, label in _FORMAT_CHOICES:
            self._format_combo.addItem(label, value)
        row.addWidget(self._format_combo)

        row.addStretch(1)

        self._validate_btn = QPushButton("検証")
        self._validate_btn.setObjectName("validateBtn")
        self._validate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._validate_btn.setStyleSheet(self._segment_button_qss())
        self._validate_btn.clicked.connect(self.validate_requested.emit)
        row.addWidget(self._validate_btn)

        self._export_btn = QPushButton("エクスポート")
        self._export_btn.setObjectName("exportBtn")
        self._export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._export_btn.setStyleSheet(self._accent_button_qss())
        self._export_btn.clicked.connect(self.export_requested.emit)
        row.addWidget(self._export_btn)

        return row

    # ------------------------------------------------------------------
    # Slots: trigger 入力
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_trigger_text_changed(self, text: str) -> None:
        """入力に応じて補完候補ドロップダウンを更新する。"""
        self._suggest_combo.clear()
        prefix = text.strip()
        if not prefix:
            return
        for entry in self._vocab.search(prefix):
            self._suggest_combo.addItem(entry.word)

    @Slot(int)
    def _on_suggest_activated(self, index: int) -> None:
        """補完候補を選んだら入力欄へ反映する。"""
        if index < 0:
            return
        self._trigger_edit.setText(self._suggest_combo.itemText(index))

    @Slot()
    def _on_trigger_commit(self) -> None:
        """入力中の trigger を overlay に追加し、語彙へ登録する。

        カンマを含む入力は拒否する: trigger は1タグのリテラルであり、
        プレビュー/出力は ", ".join するため、カンマ混入は1 trigger が複数タグに
        化けて出力ラベルを壊す（#946 register と同じ方針）。
        """
        word = self._trigger_edit.text().strip()
        if not word:
            return
        if "," in word:
            logger.debug(f"ExportOverlayBar: trigger にカンマが含まれるため追加しない: {word!r}")
            return
        if word not in self._triggers:
            self._triggers.append(word)
            self._vocab.register(word)
            self._on_overlay_mutated()
        self._trigger_edit.clear()
        self._suggest_combo.clear()

    # ------------------------------------------------------------------
    # Slots: scope
    # ------------------------------------------------------------------

    def _on_scope_clicked(self, scope: str) -> None:
        """スコープセグメント切替で scope_changed を emit しプレビューを更新する。"""
        if scope == self._scope:
            return
        self._scope = scope
        logger.debug(f"ExportOverlayBar: scope_changed emit {scope!r}")
        self.scope_changed.emit(scope)
        self._refresh_preview()

    # ------------------------------------------------------------------
    # overlay 変更の共通処理
    # ------------------------------------------------------------------

    def _on_overlay_mutated(self) -> None:
        """overlay 変更時に chip / プレビューを更新し overlay_changed を emit する。"""
        self._refresh_chips()
        self._refresh_preview()
        logger.debug(
            f"ExportOverlayBar: overlay_changed emit "
            f"triggers={len(self._triggers)} excludes={len(self._excludes)} replaces={len(self._replaces)}"
        )
        self.overlay_changed.emit(self.current_overlay())

    def _remove_trigger(self, word: str) -> None:
        if word in self._triggers:
            self._triggers.remove(word)
            self._on_overlay_mutated()

    def _remove_exclude(self, tag: str) -> None:
        if tag in self._excludes:
            self._excludes.remove(tag)
            self._on_overlay_mutated()

    def _remove_replace(self, frm: str) -> None:
        if frm in self._replaces:
            del self._replaces[frm]
            self._on_overlay_mutated()

    # ------------------------------------------------------------------
    # chip 描画
    # ------------------------------------------------------------------

    def _refresh_chips(self) -> None:
        """overlay 作業状態から chip を再描画する。"""
        # 既存 chip を全削除
        while self._chip_layout.count():
            item = self._chip_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        for trigger in self._triggers:
            self._chip_layout.addWidget(
                self._make_chip(f"⊕ {trigger}", partial(self._remove_trigger, trigger))
            )
        for tag in self._excludes:
            self._chip_layout.addWidget(self._make_chip(f"⊘ {tag}", partial(self._remove_exclude, tag)))
        for frm, to in self._replaces.items():
            self._chip_layout.addWidget(
                self._make_chip(f"⇄ {frm}→{to}", partial(self._remove_replace, frm))
            )

    def _make_chip(self, text: str, on_remove: Callable[[], None]) -> QWidget:
        """× で削除可能な overlay chip（橙系）を生成する。"""
        chip = QFrame()
        chip.setObjectName("overlayChip")
        chip.setStyleSheet(
            f"QFrame#overlayChip {{ background: {theme.ACCENT_SOFT}; border: 1px solid {theme.ACCENT_BORDER};"
            f" border-radius: {theme.RADIUS}px; }}"
        )
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(6, 2, 4, 2)
        lay.setSpacing(4)

        label = QLabel(text)
        label.setStyleSheet(
            f"color: {theme.ACCENT_HOVER}; font-size: {theme.FONT_SIZE_SMALL}px; border: none; background: transparent;"
        )
        lay.addWidget(label)

        remove_btn = QPushButton("✕")
        remove_btn.setObjectName("chipRemoveBtn")
        remove_btn.setFixedSize(16, 16)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {theme.ACCENT_HOVER};"
            f" font-size: {theme.FONT_SIZE_META}px; }}"
            f" QPushButton:hover {{ color: {theme.ERR}; }}"
        )
        remove_btn.clicked.connect(on_remove)
        lay.addWidget(remove_btn)

        return chip

    # ------------------------------------------------------------------
    # ライブプレビュー
    # ------------------------------------------------------------------

    def _refresh_preview(self) -> None:
        """選択画像の DB タグへ overlay を適用した最終 .txt 行を表示する。"""
        if self._selected_image_id is None:
            self._preview.setPlainText("")
            return

        result = apply_overlay(
            self._selected_db_tags,
            self.current_overlay(),
            self._reader,
            self._tag_format,
        )
        self._preview.setPlainText(", ".join(result))

    # ------------------------------------------------------------------
    # QSS ヘルパー
    # ------------------------------------------------------------------

    def _accent_button_qss(self) -> str:
        """主アクションボタン（橙）の QSS を返す。"""
        return (
            f"QPushButton {{ background: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
            f" border: none; border-radius: {theme.RADIUS}px; padding: 4px 12px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:hover {{ background: {theme.ACCENT_HOVER}; }}"
        )

    def _segment_button_qss(self) -> str:
        """セグメント/補助ボタンの QSS を返す。"""
        return (
            f"QPushButton {{ background: {theme.PAPER_SHADE}; color: {theme.INK_SOFT};"
            f" border: 1px solid {theme.LINE}; border-radius: {theme.RADIUS}px;"
            f" padding: 4px 10px; font-size: {theme.FONT_SIZE_SMALL}px; }}"
            f" QPushButton:checked {{ background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_HOVER};"
            f" border-color: {theme.ACCENT_BORDER}; }}"
            f" QPushButton:hover {{ background: {theme.LINE}; }}"
        )
