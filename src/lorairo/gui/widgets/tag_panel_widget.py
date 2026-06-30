"""Tag Panel Widget

タグ欄の DB / service 非依存ウィジェット (ADR 0083 / Issue #987)。

`AnnotationDataDisplayWidget` からタグ表示・操作の責務を切り出した独立ウィジェット。
chip 表示 (FlowLayout) / 言語切替・翻訳表示 / chip 選択コピー (#814) /
soft-reject (無効化・✕) / 手動タグ追加 / refinement 警告・ignore (#931) を持つ。

DB / service_container は一切持たず、ユーザー操作は Signal で親へ出すだけ。保存先への
dispatch は親 (`SelectedImageDetailsWidget`) が担う。これにより保存先の混線 (#978) を
構造的に防ぐ。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QContextMenuEvent, QKeySequence, QMouseEvent, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...utils.log import logger
from .. import theme

if TYPE_CHECKING:
    from genai_tag_db_tools.models import RefinementRecommendation


class SelectableTagChip(QLabel):
    """選択トグルできるタグ chip (Issue #814 / #931 / #987)。

    1 タグ 1 chip 表示で、以下のクリックモデルを持つ (ADR 0083 §3):

    - 単クリック (修飾なし): ``clicked`` を emit (親が無効化⇄復活トグルへ割当)
    - Ctrl+クリック: ``ctrl_clicked`` を emit (コピー選択。#814 の選択をこちらへ退避)

    コピー対象は表示テキスト (翻訳後) ではなく ``canonical`` (danbooru canonical / 原文)
    を使う。タグは保存値が SSoT であり、言語切替に依らず一貫したコピー結果にする。
    """

    clicked = Signal()  # 単クリック (修飾なし): 無効化⇄復活トグル
    ctrl_clicked = Signal()  # Ctrl+クリック: コピー選択 (#814)
    # refinement リコメンドの「この理由を無視」要求 (#931): (canonical, reason_code)
    refinement_ignore_requested = Signal(str, str)
    # タグ情報メニュー要求 (#989、tagdb userdb 系)。親がダイアログを開く。
    translation_add_menu_requested = Signal(str)  # canonical — 翻訳を追加
    type_edit_menu_requested = Signal(str)  # canonical — タグ情報 (種別) を編集

    def __init__(self, display_text: str, canonical: str, parent: QWidget | None = None) -> None:
        super().__init__(display_text, parent)
        self.canonical = canonical
        self.base_qss = ""
        self.selected = False
        # 翻訳欠落 chip か (#989)。未登録なら右クリックメニューで「翻訳を追加」を強調する。
        self.untranslated = False
        # refinement 表示状態 (#931)。set_refinement で更新する。
        self._base_text = display_text
        self._base_tooltip: str | None = None
        self.refinement: RefinementRecommendation | None = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Ctrl+C を chip フォーカス中に拾えるようクリックフォーカスを許可する。
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左クリックで clicked / Ctrl+左クリックで ctrl_clicked を emit する。"""
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.ctrl_clicked.emit()
            else:
                self.clicked.emit()
        super().mousePressEvent(event)

    def set_refinement(self, recommendation: RefinementRecommendation | None) -> None:
        """refinement リコメンドを反映する (#931)。

        needs_refinement かつ reason があれば ⚠ マーカーを表示テキストに前置し
        (高さは1行で不変)、ツールチップに reason message と suggestion を出す。
        リコメンドが無ければ元の表示・ツールチップへ戻す。

        Args:
            recommendation: 当該タグのリコメンド。無ければ None。
        """
        # 初回呼び出し時に元ツールチップ (翻訳脚注等) を退避する。
        if self._base_tooltip is None:
            self._base_tooltip = self.toolTip()
        self.refinement = recommendation
        if recommendation is not None and recommendation.needs_refinement and recommendation.reasons:
            self.setText(f"⚠ {self._base_text}")
            lines = [r.message for r in recommendation.reasons]
            suggestions = [s.tag for s in recommendation.suggestions if s.tag]
            if suggestions:
                lines.append("提案: " + ", ".join(suggestions))
            self.setToolTip("\n".join(lines))
        else:
            self.setText(self._base_text)
            self.setToolTip(self._base_tooltip)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """chip の右クリックで「タグ情報」メニューを出す (ADR 0083 §3 / #989)。

        tagdb userdb 系 (canonical 主キー・全画像反映) の「翻訳を追加」「タグ情報を編集」を
        常に提示し、refinement リコメンドがあれば reason 単位の「この理由を無視」(#931) を
        続けて並べる。未翻訳 chip では「翻訳を追加」を強調表示する (#989)。
        """
        menu = QMenu(self)

        translation_label = "翻訳を追加 (未登録)…" if self.untranslated else "翻訳を追加…"
        translation_action = menu.addAction(translation_label)
        translation_action.triggered.connect(
            lambda _checked=False: self.translation_add_menu_requested.emit(self.canonical)
        )
        type_action = menu.addAction("タグ情報を編集…")
        type_action.triggered.connect(
            lambda _checked=False: self.type_edit_menu_requested.emit(self.canonical)
        )

        rec = self.refinement
        if rec is not None and rec.needs_refinement and rec.reasons:
            menu.addSeparator()
            for reason in rec.reasons:
                action = menu.addAction(f"この理由を無視: {reason.code}")
                action.triggered.connect(
                    lambda _checked=False, code=reason.code: self.refinement_ignore_requested.emit(
                        self.canonical, code
                    )
                )
        menu.exec(event.globalPos())
        event.accept()


# tagdb userdb 系ダイアログのティール「タグ情報」見出し QSS (ADR 0083 §2 / #989)。
# image DB 系 (青) と保存先を視覚的に分けるため UDB トークンで縁取る。
_UDB_HEADER_QSS = (
    f"QLabel#udbHeader {{ background-color: {theme.UDB_SOFT}; color: {theme.UDB};"
    f" border: 1px solid {theme.UDB_BORDER}; border-radius: {theme.RADIUS_CHIP}px;"
    f" padding: 4px 8px; font-weight: 600; }}"
)


class TranslationAddDialog(QDialog):
    """canonical タグへ言語別翻訳を追加する入力ダイアログ (ADR 0083 §2 / #989)。

    DB は知らない。OK 確定で (language, translation) を返すだけで、保存は親が dispatch する。
    保存先が「タグ情報 (全画像に反映)」であることをティール見出しで明示する。
    """

    def __init__(self, canonical: str, languages: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("翻訳を追加")
        self._canonical = canonical

        layout = QVBoxLayout(self)
        header = QLabel("タグ情報を編集 · 全画像に反映されます", self)
        header.setObjectName("udbHeader")
        header.setStyleSheet(_UDB_HEADER_QSS)
        layout.addWidget(header)

        form = QFormLayout()
        form.addRow("タグ (canonical):", QLabel(canonical, self))
        self._language_combo = QComboBox(self)
        # 既知言語があれば候補に、無ければ ja を既定にする。編集可で任意の言語コードも入力可。
        for lang in languages:
            self._language_combo.addItem(lang)
        if self._language_combo.count() == 0:
            self._language_combo.addItem("ja")
        self._language_combo.setEditable(True)
        form.addRow("言語:", self._language_combo)
        self._translation_input = QLineEdit(self)
        self._translation_input.setPlaceholderText("翻訳テキスト")
        form.addRow("翻訳:", self._translation_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def language(self) -> str:
        """入力された言語コードを返す。"""
        return self._language_combo.currentText().strip()

    def translation(self) -> str:
        """入力された翻訳テキストを返す。"""
        return self._translation_input.text().strip()


class TagTypeEditDialog(QDialog):
    """canonical タグの種別 (type) を補正するダイアログ (ADR 0083 §2 / #989)。

    DB は知らない。OK 確定で選択 type 名を返すだけで、保存は親が dispatch する。
    refinement の TYPE_MISMATCH 警告があればヒントを表示する。
    """

    # 補正候補の type 名 (ADR 0083 §2 / Issue #989)。
    TYPE_CHOICES = ("general", "character", "copyright", "meta", "artist")

    # 既知 type を渡せないとき先頭に置く非選択プレースホルダ。誤って general で確定して
    # 既存 type を上書きする no-op 事故を防ぐ (Codex #995 P2)。
    _PLACEHOLDER = "（タグ種別を選択）"

    def __init__(
        self,
        canonical: str,
        type_mismatch_hint: str | None = None,
        current_type: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("タグ情報を編集")
        self._canonical = canonical

        layout = QVBoxLayout(self)
        header = QLabel("タグ情報を編集 · 全画像に反映されます", self)
        header.setObjectName("udbHeader")
        header.setStyleSheet(_UDB_HEADER_QSS)
        layout.addWidget(header)

        if type_mismatch_hint:
            hint = QLabel(f"⚠ {type_mismatch_hint}", self)
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {theme.WARN};")
            layout.addWidget(hint)

        form = QFormLayout()
        form.addRow("タグ (canonical):", QLabel(canonical, self))
        self._type_combo = QComboBox(self)
        # 現在の type が分かるならそれを初期選択する (無変更確定は同じ type なので無害)。
        # 不明ならプレースホルダを先頭に置き、ユーザーに明示選択を強制する。
        self._has_placeholder = current_type not in self.TYPE_CHOICES
        if self._has_placeholder:
            self._type_combo.addItem(self._PLACEHOLDER)
        for type_name in self.TYPE_CHOICES:
            self._type_combo.addItem(type_name)
        if not self._has_placeholder:
            self._type_combo.setCurrentText(current_type)  # type: ignore[arg-type]
        form.addRow("タグ種別:", self._type_combo)
        layout.addLayout(form)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        # プレースホルダ選択中は OK を無効化し、明示選択を要求する。
        if self._has_placeholder:
            self._type_combo.currentTextChanged.connect(self._update_ok_enabled)
            self._update_ok_enabled(self._type_combo.currentText())

    @Slot(str)
    def _update_ok_enabled(self, text: str) -> None:
        """プレースホルダ以外の type が選ばれているときのみ OK を有効化する。"""
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(text in self.TYPE_CHOICES)

    def selected_type(self) -> str:
        """選択された type 名を返す。プレースホルダ選択時は空文字を返す。"""
        text = self._type_combo.currentText()
        return text if text in self.TYPE_CHOICES else ""


class TagPanelWidget(QWidget):
    """タグ表示・操作の DB 非依存ウィジェット (ADR 0083 / Issue #987)。

    タグ chip 表示、言語切替・翻訳、選択コピー (#814)、soft-reject 一本のタグ操作
    (無効化 / ✕ / 復活)、手動タグ追加、refinement 警告・ignore (#931) を担う。
    操作要求は Signal で親へ出すだけで、DB / service への dispatch は親が行う。

    タグ操作モデル (ADR 0083 §3、soft-reject 一本):

    - 単クリック = 無効化⇄復活トグル (破線 chip でインライン表示継続)
    - ✕ ボタン = この画像から外す (パネルから当該セッションのみ非表示)
    - Ctrl+クリック = コピー選択 (#814)
    - 右クリック = タグ情報メニュー (翻訳追加 / タグ情報を編集 #989、refinement ignore #931)

    無効化 (破線表示) と ✕ (非表示) の区別は本ウィジェットの表示状態で保持し、
    永続化しない (reject 自体は親が ``rejected_at`` で永続化)。
    """

    # image DB 系 (current_image_id 必須。親が dispatch)
    tag_reject_requested = Signal(str)  # canonical — 無効化・✕ 共通で soft-reject
    tag_restore_requested = Signal(str)  # canonical — 復活
    tag_add_requested = Signal(str)  # 生入力 (親が canonical 解決)
    # tagdb userdb 系 (canonical が主キー / 画像 ID 不要)
    refinement_ignored = Signal(str, str)  # canonical, reason_code (#931)
    translation_add_requested = Signal(str, str, str)  # canonical, language, translation (#989)
    tag_metadata_edit_requested = Signal(str, str)  # canonical, type (#989)

    # タグチップ箱の高さ上限 (#835)。これを超えるタグは箱内スクロールにし、
    # パネル全体の高さがタグ数で膨張しないようにする。
    _TAGS_MAX_HEIGHT = 220

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # 表示データ (DB は知らない。親から set_tags / set_translations 経由で受ける)
        self._tags: list[dict[str, Any]] = []
        self._translations: dict[int, dict[str, str]] = {}
        self._available_languages: list[str] = []

        # 編集モード (soft-reject 導線。既定 read-only)
        self._tag_edit_enabled: bool = False

        # 操作の表示状態 (永続化しない。ADR 0083 §3)
        self._disabled_display: set[str] = set()  # 無効化 (破線でインライン表示継続)
        self._hidden: set[str] = set()  # ✕ で当該セッションのみ非表示
        self._rejected_tags: list[str] = []  # 親 (DB) から渡される soft-rejected canonical
        # 表示中画像の識別子。set_tags でこれが変わったときだけ表示状態をリセットする。
        # 同一画像の reject reload (✕ → 親が soft-reject → 同画像 reload → set_tags 呼び戻し)
        # で _hidden が消え、外したタグが破線で即再出現する回帰を防ぐ (PR #992 Codex P2)。
        self._image_id: int | None = None

        # 描画中の chip 群と refinement 保持 (#931: chip 再生成をまたいで ⚠ を復元)
        self._tag_chips: list[SelectableTagChip] = []
        self._last_refinements: dict[str, RefinementRecommendation] = {}

        self._setup_ui()

        self._lang_combo.currentTextChanged.connect(self._on_language_changed)

    def _setup_ui(self) -> None:
        """タグ欄 UI を構築する (DS chip 文法・borders-not-shadows)。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # 言語切り替えバー (コンボボックス付き)。merged_reader がなければ非表示。
        self._lang_bar = QWidget(self)
        lang_layout = QHBoxLayout(self._lang_bar)
        lang_layout.setContentsMargins(0, 0, 0, 2)
        lang_layout.addWidget(QLabel("言語:", self._lang_bar))
        self._lang_combo = QComboBox(self._lang_bar)
        self._lang_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lang_layout.addWidget(self._lang_combo)
        self._lang_bar.setVisible(False)
        root.addWidget(self._lang_bar)

        # チップ表示コンテナ。高さ上限付きスクロール箱に収める (#835)。FlowLayout の
        # minimumSizeHint は「最小幅で全チップ縦積み」の過大値を報告し、放置すると親の
        # 高さを膨張させてスコアカード下に異常な余白 + 不要スクロールを生む。
        from .tag_cloud_widget import FlowLayout

        self._tags_chip_container = QWidget(self)
        self._tags_chip_layout = FlowLayout(self._tags_chip_container, spacing=4)
        self._tags_chip_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._tags_scroll = QScrollArea(self)
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tags_scroll.setWidget(self._tags_chip_container)
        root.addWidget(self._tags_scroll)

        # 選択コピー導線 (Issue #814): Ctrl+クリックで選択、Ctrl+C / 右クリックで
        # 選択タグ (無選択なら全タグ) をカンマ区切りコピーする。
        self._tags_chip_container.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._tags_chip_container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tags_chip_container.customContextMenuRequested.connect(self._show_tags_chip_context_menu)
        self._tags_chip_copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._tags_chip_container)
        self._tags_chip_copy_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._tags_chip_copy_shortcut.activated.connect(self.copy_selected_tags_to_clipboard)

        # 翻訳脚注 (非英語選択時のみ表示)
        self._tags_translation_note = QLabel(self)
        self._tags_translation_note.setWordWrap(True)
        self._tags_translation_note.setStyleSheet(
            f"color: {theme.INK_FAINT}; font-size: {theme.FONT_SIZE_SMALL - 1}px;"
        )
        self._tags_translation_note.setVisible(False)
        root.addWidget(self._tags_translation_note)

        # 手動タグ追加入力 (編集モードのみ表示)
        self._tag_add_input = QLineEdit(self)
        self._tag_add_input.setObjectName("tagAddInput")
        self._tag_add_input.setPlaceholderText("手動タグを追加 (Enter で確定)…")
        self._tag_add_input.returnPressed.connect(self._on_tag_add_submitted)
        self._tag_add_input.setVisible(False)
        root.addWidget(self._tag_add_input)

        # コピー / アクセシビリティ用テキストバッキング (非表示)。
        # displayed_tags_text() と詳細コピーが参照する SSoT 文字列を保持する。
        self._tags_compact_label = QLabel(self)
        self._tags_compact_label.setWordWrap(True)
        self._tags_compact_label.setText("-")
        self._tags_compact_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._make_label_copyable(self._tags_compact_label)
        self._tags_compact_label.setVisible(False)
        root.addWidget(self._tags_compact_label)

        # 隠れタグテーブル (TSV コピー用バッキング、表示はしない)。
        self._setup_tags_table()
        root.addWidget(self.tableWidgetTags)

    def _setup_tags_table(self) -> None:
        """TSV コピー用の隠しタグテーブルを構築する。"""
        self.tableWidgetTags = QTableWidget(self)
        self.tableWidgetTags.setObjectName("tableWidgetTags")
        self.tableWidgetTags.setColumnCount(5)
        for column, label in enumerate(["Tag", "Model", "Source", "Confidence", "Edited"]):
            self.tableWidgetTags.setHorizontalHeaderItem(column, QTableWidgetItem(label))
        self.tableWidgetTags.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tableWidgetTags.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.tableWidgetTags.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tableWidgetTags.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tableWidgetTags.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.tableWidgetTags.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tableWidgetTags.customContextMenuRequested.connect(self._show_tags_table_context_menu)
        self.tableWidgetTags.setVisible(False)

    # ─── 公開 API ───────────────────────────────────────────────────────

    def set_tags(
        self,
        tags: list[dict[str, Any]],
        translations: dict[int, dict[str, str]] | None = None,
        available_languages: list[str] | None = None,
        image_id: int | None = None,
    ) -> None:
        """タグ集合で表示を更新する。

        ``image_id`` が前回と変わったとき (= 別画像の表示) だけ表示状態
        (無効化 / 非表示 / refinement) をリセットする。同一画像の reject reload
        では非表示などの操作状態を保持し、現在の言語選択で chip を再描画する。

        Args:
            tags: タグ詳細情報リスト (Repository 層形式)。
                ``[{"tag": "1girl", "tag_id": 10, "model_name": ..., ...}, ...]``
            translations: ``{tag_id: {language: translated_text}}``。省略時は空。
            available_languages: 利用可能言語リスト (脚注/フォールバック用)。
            image_id: 表示中画像の識別子。省略 (None) 時は常にリセットする
                (後方互換)。同一 ``image_id`` の再呼び出しは表示状態を保持する。
        """
        # ✕ で外したタグは同一画像の reject reload を跨いで非表示を維持する。
        # 親が ✕ → soft-reject → 同画像 reload → set_tags を呼び戻す経路で _hidden を
        # 消すと、外したタグが破線復活 chip として即再出現する (PR #992 Codex P2)。
        image_changed = image_id is None or image_id != self._image_id
        self._image_id = image_id
        self._tags = list(tags)
        self._translations = dict(translations) if translations else {}
        self._available_languages = list(available_languages) if available_languages else []
        if image_changed:
            # 別画像なので前画像の操作・refinement を引き継がない。
            self._disabled_display = set()
            self._hidden = set()
            self._last_refinements = {}
        self._populate_table(self._tags)
        self._refresh_tags_for_language(self._current_language())

    def set_translations(
        self, translations: dict[int, dict[str, str]], available_languages: list[str]
    ) -> None:
        """翻訳データと利用可能言語を差し替えて再描画する。"""
        self._translations = dict(translations)
        self._available_languages = list(available_languages)
        self._refresh_tags_for_language(self._current_language())

    def initialize_language_selector(self, available_languages: list[str]) -> None:
        """言語コンボボックスを初期化する。

        Args:
            available_languages: 利用可能な言語リスト。空の場合はコンボボックスを非表示にする。
        """
        if not available_languages:
            self._lang_bar.setVisible(False)
            return

        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItem("english")  # 常に先頭 (原文)
        for lang in available_languages:
            if lang != "english":
                self._lang_combo.addItem(lang)
        self._lang_combo.blockSignals(False)
        self._lang_bar.setVisible(True)

    def set_tag_edit_enabled(self, enabled: bool) -> None:
        """タグ soft-reject 編集モードを切り替える。

        Args:
            enabled: True で ✕ ボタン / 手動追加入力 / クリック無効化を有効にする。
        """
        self._tag_edit_enabled = enabled
        self._tag_add_input.setVisible(enabled)
        self._refresh_tags_for_language(self._current_language())

    def set_rejected_tags(self, rejected_tags: list[str]) -> None:
        """soft-rejected タグ一覧を設定しインライン破線 chip として再描画する。

        旧「復活」別枠は廃止し、無効化と同じく破線 chip でインライン表示する
        (ADR 0083 §3)。クリックで復活できる。

        Args:
            rejected_tags: soft-reject 済み canonical タグ文字列のリスト。
        """
        self._rejected_tags = list(rejected_tags)
        self._refresh_tags_for_language(self._current_language())

    def apply_refinements(self, recommendations: dict[str, RefinementRecommendation]) -> None:
        """各タグ chip に refinement リコメンドを反映する (#931)。

        chip の canonical をキーにマップを引き、該当があれば ⚠ + ツールチップを表示、
        無ければリコメンド表示を消す。言語切替や編集モード切替で chip が再生成されても
        ⚠ を失わないよう最後の結果を保持し、再描画末尾で自動再反映する。

        Args:
            recommendations: ``{canonical タグ: RefinementRecommendation}``。
        """
        self._last_refinements = dict(recommendations)
        self._apply_refinements_to_chips()

    def displayed_tags_text(self) -> str:
        """現在の言語選択で表示されているタグ文字列を返す。"""
        return self._tags_compact_label.text()

    @Slot()
    def copy_selected_tags_to_clipboard(self) -> bool:
        """選択中タグ (無選択なら全タグ) をカンマ区切りでクリップボードへコピーする。

        コピー値は表示テキスト (翻訳後) ではなく canonical 原文を使う (#814)。

        Returns:
            コピー対象が 1 件以上あれば True、タグが無ければ False。
        """
        selected = [chip.canonical for chip in self._tag_chips if chip.selected]
        targets = selected if selected else [chip.canonical for chip in self._tag_chips]
        targets = [tag for tag in targets if tag]
        if not targets:
            return False
        QApplication.clipboard().setText(", ".join(targets))
        return True

    @Slot()
    def copy_selected_tag_cells_to_clipboard(self) -> bool:
        """タグテーブルの選択セルを TSV としてクリップボードへコピーする。"""
        ranges = self.tableWidgetTags.selectedRanges()
        if not ranges:
            return False
        lines: list[str] = []
        for selected_range in ranges:
            for row in range(selected_range.topRow(), selected_range.bottomRow() + 1):
                values: list[str] = []
                for column in range(selected_range.leftColumn(), selected_range.rightColumn() + 1):
                    item = self.tableWidgetTags.item(row, column)
                    values.append(self._tag_table_item_clipboard_text(item, column))
                lines.append("\t".join(values))
        QApplication.clipboard().setText("\n".join(lines))
        return True

    def clear(self) -> None:
        """表示データと表示状態をクリアする。"""
        self._tags = []
        self._translations = {}
        self._disabled_display = set()
        self._hidden = set()
        self._rejected_tags = []
        self._last_refinements = {}
        self.tableWidgetTags.setRowCount(0)
        self._tags_compact_label.setText("-")
        self._render_tag_chips([], is_translated=False)
        self._adjust_tags_chip_height()

    # ─── 言語・描画 ─────────────────────────────────────────────────────

    def _current_language(self) -> str:
        """現在の表示言語を返す (言語バー非表示時は english)。"""
        return self._lang_combo.currentText() if not self._lang_bar.isHidden() else "english"

    @Slot(str)
    def _on_language_changed(self, language: str) -> None:
        """言語コンボボックス変更時にタグ表示を更新する。"""
        self._refresh_tags_for_language(language)

    def _refresh_tags_for_language(self, language: str) -> None:
        """現在のタグデータを指定言語で再描画する。

        Args:
            language: 表示言語名。"english" または available_languages の要素。
                翻訳がないタグは英語原文でフォールバックする。
        """
        use_english = language == "english" or not language

        tag_names: list[str] = []
        # チップ描画用メタ: (表示名, 原文, 翻訳ありか)
        chip_items: list[tuple[str, str, bool]] = []
        for row, tag_dict in enumerate(self._tags):
            tag_id = tag_dict.get("tag_id")
            original = tag_dict.get("tag", "")
            if use_english or tag_id is None:
                display = original
                has_translation = True  # 英語表示では翻訳欠落マークを付けない
            else:
                translated = self._translations.get(tag_id, {}).get(language)
                display = translated if translated else original
                has_translation = translated is not None
            tag_names.append(display)
            chip_items.append((display, original, has_translation))

            # 隠しテーブルの Tag 列 (列0) も更新する
            item = self.tableWidgetTags.item(row, 0)
            if item is not None:
                item.setText(display)

        self._tags_compact_label.setText(", ".join(n for n in tag_names if n) or "-")
        self._render_tag_chips(chip_items, is_translated=not use_english)

    def _render_tag_chips(self, chip_items: list[tuple[str, str, bool]], *, is_translated: bool) -> None:
        """タグチップを DS chip 文法で再描画する (borders-not-shadows)。

        ✕ で非表示にしたタグ (``_hidden``) は描画しない。soft-rejected (DB 由来) は
        破線 chip としてインライン追記する。無効化 (``_disabled_display``) と翻訳欠落は
        破線スタイルで示す。

        Args:
            chip_items: (表示名, 原文, 翻訳ありか) のタプルリスト (アクティブタグ)。
            is_translated: 非英語言語で表示中なら True。脚注と翻訳欠落の点線マークを切り替える。
        """
        self._clear_chip_layout()
        self._tag_chips = []

        # アクティブタグ (✕ 非表示は除外)
        visible_items = [
            (display, original, has_tr)
            for display, original, has_tr in chip_items
            if display and original not in self._hidden
        ]
        # DB 由来 soft-rejected のうちアクティブに含まれないものを破線 chip として追記する。
        active_canonicals = {original for _display, original, _has_tr in chip_items}
        rejected_only = [
            tag
            for tag in self._rejected_tags
            if tag and tag not in active_canonicals and tag not in self._hidden
        ]

        if not visible_items and not rejected_only:
            placeholder = QLabel("-")
            placeholder.setStyleSheet(f"color: {theme.INK_FAINT};")
            self._tags_chip_layout.addWidget(placeholder)
            self._tags_translation_note.setVisible(False)
            return

        for display, original, has_tr in visible_items:
            disabled = original in self._disabled_display or original in self._rejected_tags
            self._add_chip(
                display, original, has_translation=has_tr, is_translated=is_translated, disabled=disabled
            )

        for original in rejected_only:
            self._add_chip(original, original, has_translation=True, is_translated=False, disabled=True)

        if is_translated:
            self._tags_translation_note.setText(
                "表示のみ翻訳 · 保存値は danbooru canonical 固定 · 点線 = 翻訳なし"
            )
            self._tags_translation_note.setVisible(True)
        else:
            self._tags_translation_note.setVisible(False)

        # chip 再生成後、保持中の refinement 結果を再反映する (#931)。
        self._apply_refinements_to_chips()
        self._adjust_tags_chip_height()

    def _add_chip(
        self,
        display: str,
        original: str,
        *,
        has_translation: bool,
        is_translated: bool,
        disabled: bool,
    ) -> None:
        """1 タグ分の chip (編集モードでは ✕ 付き) を生成して配置する。"""
        chip = SelectableTagChip(display, original)
        if is_translated and not has_translation:
            chip.untranslated = True
            chip.base_qss = theme.tag_chip_untranslated_qss()
            chip.setToolTip(f"{original} — 翻訳なし · 右クリックで翻訳を追加")
        else:
            chip.base_qss = theme.chip_qss("accent")
            if is_translated and display != original:
                chip.setToolTip(f"{original} → {display}")
        # 無効化 (破線) 表示の場合は disabled スタイルを適用する。
        chip.setStyleSheet(self._disabled_chip_qss() if disabled else chip.base_qss)
        chip.clicked.connect(lambda c=chip: self._on_chip_clicked(c))
        chip.ctrl_clicked.connect(lambda c=chip: self._on_chip_ctrl_clicked(c))
        # refinement「この理由を無視」を上位へ中継 (#931)
        chip.refinement_ignore_requested.connect(self.refinement_ignored)
        # タグ情報メニュー (#989): chip 右クリック → 親がダイアログを開く。
        chip.translation_add_menu_requested.connect(self._open_translation_dialog)
        chip.type_edit_menu_requested.connect(self._open_type_edit_dialog)
        self._tag_chips.append(chip)
        self._tags_chip_layout.addWidget(self._wrap_editable_chip(chip, original))

    def _clear_chip_layout(self) -> None:
        """chip レイアウトの既存ウィジェットを破棄する。"""
        while self._tags_chip_layout.count():
            child = self._tags_chip_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _wrap_editable_chip(self, chip: SelectableTagChip, original: str) -> QWidget:
        """編集モード時にチップを ✕ ボタン付きコンテナで包む (この画像から外す)。

        read-only モードでは chip をそのまま返す。

        Args:
            chip: タグチップ。
            original: canonical タグ文字列 (soft-reject 対象)。

        Returns:
            編集モードなら ✕ 付きコンテナ、そうでなければ chip。
        """
        if not self._tag_edit_enabled:
            return chip
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(chip)
        remove = QToolButton(container)
        remove.setObjectName("tagRejectButton")
        remove.setText("×")
        remove.setAutoRaise(True)
        remove.setToolTip(f"{original} をこの画像から外す (soft-reject、行は残す)")
        remove.clicked.connect(lambda _checked=False, tag=original: self._on_chip_removed(tag))
        layout.addWidget(remove)
        return container

    @staticmethod
    def _disabled_chip_qss() -> str:
        """無効化 (soft-reject インライン) chip 用の破線 QSS を返す。"""
        return theme.tag_chip_untranslated_qss()

    @staticmethod
    def _selected_chip_qss() -> str:
        """選択中タグ chip 用の強調 QSS を theme トークンで生成する (Issue #814)。"""
        return (
            f"QLabel {{ background-color: {theme.ACCENT}; color: {theme.TEXT_ON_ACCENT};"
            f" border: {theme.BORDER_WIDTH_ACCENT}px solid {theme.ACCENT};"
            f" border-radius: {theme.RADIUS_CHIP}px; padding: 1px 9px;"
            f" font-size: {theme.FONT_SIZE_SMALL}px; font-weight: 600; }}"
        )

    # ─── chip 操作ハンドラ ──────────────────────────────────────────────

    def _on_chip_clicked(self, chip: SelectableTagChip) -> None:
        """単クリック: 無効化⇄復活トグル (ADR 0083 §3、編集モードのみ)。"""
        if not self._tag_edit_enabled:
            return
        canonical = chip.canonical
        if canonical in self._disabled_display or canonical in self._rejected_tags:
            # 破線 chip クリック = 復活
            self._disabled_display.discard(canonical)
            chip.setStyleSheet(chip.base_qss)
            self.tag_restore_requested.emit(canonical)
        else:
            # アクティブ chip クリック = 無効化 (破線でインライン継続)
            self._disabled_display.add(canonical)
            chip.setStyleSheet(self._disabled_chip_qss())
            self.tag_reject_requested.emit(canonical)

    def _on_chip_ctrl_clicked(self, chip: SelectableTagChip) -> None:
        """Ctrl+クリック: コピー選択トグル (#814)。"""
        chip.selected = not chip.selected
        chip.setStyleSheet(self._selected_chip_qss() if chip.selected else chip.base_qss)

    def _on_chip_removed(self, canonical: str) -> None:
        """✕ ボタン: この画像から外す (soft-reject + 当該セッション非表示)。"""
        self._hidden.add(canonical)
        self.tag_reject_requested.emit(canonical)
        self._refresh_tags_for_language(self._current_language())

    def _on_tag_add_submitted(self) -> None:
        """手動タグ追加入力の Enter ハンドラ。生入力のまま親へ出す (親が canonical 解決)。"""
        text = self._tag_add_input.text().strip()
        if not text:
            return
        self._tag_add_input.clear()
        self.tag_add_requested.emit(text)

    # ─── タグ情報メニュー (#989、tagdb userdb 系) ───────────────────────

    @Slot(str)
    def _open_translation_dialog(self, canonical: str) -> None:
        """翻訳追加ダイアログを開き、確定で translation_add_requested を出す (#989)。

        DB は知らない。ダイアログ確定で (canonical, language, translation) を親へ出すだけ。

        Args:
            canonical: 翻訳を付与する canonical タグ文字列。
        """
        dialog = TranslationAddDialog(canonical, list(self._available_languages), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        language = dialog.language()
        translation = dialog.translation()
        if not language or not translation:
            logger.debug(f"翻訳追加をスキップ (空入力): canonical='{canonical}'")
            return
        self.translation_add_requested.emit(canonical, language, translation)

    @Slot(str)
    def _open_type_edit_dialog(self, canonical: str) -> None:
        """タグ種別補正ダイアログを開き、確定で tag_metadata_edit_requested を出す (#989)。

        当該タグに refinement の TYPE_MISMATCH 警告があればヒントとして渡す。

        Args:
            canonical: 種別を補正する canonical タグ文字列。
        """
        dialog = TagTypeEditDialog(canonical, self._type_mismatch_hint(canonical), parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        type_name = dialog.selected_type()
        if not type_name:
            # プレースホルダのまま確定 (明示選択なし) → 既存 type を上書きしない (#995 P2)。
            logger.debug(f"type 補正をスキップ (種別未選択): canonical='{canonical}'")
            return
        self.tag_metadata_edit_requested.emit(canonical, type_name)

    def _type_mismatch_hint(self, canonical: str) -> str | None:
        """canonical タグの TYPE_MISMATCH refinement reason メッセージを返す (#989)。

        保持中の refinement (``_last_refinements``) から code に "TYPE_MISMATCH" を含む
        reason を探してメッセージを返す。無ければ None。

        Args:
            canonical: 対象 canonical タグ。

        Returns:
            TYPE_MISMATCH reason のメッセージ。該当が無ければ None。
        """
        rec = self._last_refinements.get(canonical)
        if rec is None or not rec.reasons:
            return None
        for reason in rec.reasons:
            if "TYPE_MISMATCH" in reason.code.upper():
                return str(reason.message)
        return None

    # ─── refinement (#931) ──────────────────────────────────────────────

    def _apply_refinements_to_chips(self) -> None:
        """保持中のリコメンド (_last_refinements) を現在の chip 群へ反映する (#931)。"""
        applied = 0
        for chip in self._tag_chips:
            rec = self._last_refinements.get(chip.canonical)
            chip.set_refinement(rec)
            if rec is not None:
                applied += 1
        logger.debug(f"refinement 反映: chip={len(self._tag_chips)}, 印付き={applied}")

    # ─── テーブル (TSV コピーバッキング) ────────────────────────────────

    def _populate_table(self, tags: list[dict[str, Any]]) -> None:
        """隠しタグテーブルにタグ詳細を投入する (TSV コピー用)。"""
        self.tableWidgetTags.setSortingEnabled(False)
        self.tableWidgetTags.setRowCount(len(tags))
        for row, tag_dict in enumerate(tags):
            self.tableWidgetTags.setItem(row, 0, QTableWidgetItem(tag_dict.get("tag", "")))
            self.tableWidgetTags.setItem(row, 1, QTableWidgetItem(tag_dict.get("model_name", "-")))
            self.tableWidgetTags.setItem(row, 2, QTableWidgetItem(tag_dict.get("source", "AI")))
            confidence = tag_dict.get("confidence_score")
            confidence_text = f"{confidence:.2f}" if confidence is not None else "-"
            confidence_item = QTableWidgetItem(confidence_text)
            confidence_item.setData(Qt.ItemDataRole.UserRole, confidence if confidence else -1)
            self.tableWidgetTags.setItem(row, 3, confidence_item)
            edited = tag_dict.get("is_edited_manually", False)
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.CheckState.Checked if edited else Qt.CheckState.Unchecked)
            checkbox_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tableWidgetTags.setItem(row, 4, checkbox_item)
        self.tableWidgetTags.setSortingEnabled(True)
        self.tableWidgetTags.resizeColumnsToContents()

    @staticmethod
    def _tag_table_item_clipboard_text(item: QTableWidgetItem | None, column: int) -> str:
        """タグテーブルセルのコピー用文字列を返す。"""
        if item is None:
            return ""
        if column == 4:
            return "true" if item.checkState() == Qt.CheckState.Checked else "false"
        return item.text()

    # ─── コンテキストメニュー ──────────────────────────────────────────

    @Slot(QPoint)
    def _show_tags_chip_context_menu(self, position: QPoint) -> None:
        """タグ chip コンテナの右クリックメニュー (選択タグのカンマ区切りコピー)。"""
        menu = QMenu(self._tags_chip_container)
        copy_action = menu.addAction("選択タグをコピー")
        copy_action.setEnabled(bool(self._tag_chips))
        copy_action.triggered.connect(self.copy_selected_tags_to_clipboard)
        menu.exec(self._tags_chip_container.mapToGlobal(position))

    @Slot(QPoint)
    def _show_tags_table_context_menu(self, position: QPoint) -> None:
        menu = QMenu(self.tableWidgetTags)
        copy_action = menu.addAction("選択範囲をコピー")
        copy_action.setEnabled(bool(self.tableWidgetTags.selectedRanges()))
        copy_action.triggered.connect(self.copy_selected_tag_cells_to_clipboard)
        menu.exec(self.tableWidgetTags.viewport().mapToGlobal(position))

    def _make_label_copyable(self, label: QLabel) -> None:
        """読み取り専用 QLabel を選択・コピー可能にする。"""
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        label.customContextMenuRequested.connect(
            lambda position, target=label: self._show_label_context_menu(target, position)
        )

    def _show_label_context_menu(self, label: QLabel, position: QPoint) -> None:
        menu = QMenu(label)
        copy_action = menu.addAction("コピー")
        text = label.selectedText() or label.text()
        copy_action.setEnabled(bool(text))
        copy_action.triggered.connect(
            lambda: QApplication.clipboard().setText(label.selectedText() or label.text())
        )
        menu.exec(label.mapToGlobal(position))

    # ─── サイジング (#835) ──────────────────────────────────────────────

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # 幅変化でタグチップの折り返し行数が変わるため箱の高さを追従させる (#835)
        self._adjust_tags_chip_height()

    def _adjust_tags_chip_height(self) -> None:
        """タグチップ箱の高さを min(実幅での必要高さ, 上限) に収める (#835)。

        FlowLayout の minimumSizeHint (最小幅での全チップ縦積み) が親へ伝播して
        スクロール領域を膨張させるのを防ぐため、箱の高さを実寸ベースで明示する。
        """
        if not self._tags_scroll.isVisible():
            return
        width = self._tags_scroll.viewport().width()
        if width <= 0:
            return
        # 収まるときに内側スクロールバーが出ないよう僅かな余裕を足す。
        needed = self._tags_chip_layout.heightForWidth(width) + 8
        self._tags_scroll.setFixedHeight(min(needed, self._TAGS_MAX_HEIGHT))
