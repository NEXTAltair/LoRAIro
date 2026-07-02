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

from typing import TYPE_CHECKING, Any, ClassVar

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
    QPushButton,
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
from .ds_no_scroll_combo_box import DsNoScrollComboBox

if TYPE_CHECKING:
    from genai_tag_db_tools.models import RefinementRecommendation

# 使用頻度 第2軸セレクタの「なし」選択肢ラベル (ADR 0083 §5 / #990)。
# 選択時は metric_source を空にして chip の count 補助表示を消す。
_METRIC_NONE_LABEL = "なし"

# soft-reject 種別 (schema.REJECT_REASON_* の SSoT と一致、Issue #1003)。
# 本ウィジェットは DB 非依存のため schema を import せず値のみ複製する。
# 'not_needed' のみインライン破線 chip (無効化) で残し、'incorrect'/'replaced' は非表示。
_REJECT_REASON_NOT_NEEDED = "not_needed"


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
    # refinement 修正候補の適用要求 (#1007、image DB 系の置換操作): (canonical, to_tag)
    refinement_apply_requested = Signal(str, str)
    # タグ情報メニュー要求 (#989、tagdb userdb 系)。親がダイアログを開く。
    translation_add_menu_requested = Signal(str)  # canonical — 翻訳を追加
    type_edit_menu_requested = Signal(str)  # canonical — タグ情報 (種別) を編集
    # 使用頻度を見るメニュー要求 (#997)。read-only で TagPanelWidget 内で完結する。
    usage_counts_menu_requested = Signal(str)  # canonical

    def __init__(self, display_text: str, canonical: str, parent: QWidget | None = None) -> None:
        super().__init__(display_text, parent)
        self.canonical = canonical
        self.base_qss = ""
        self.selected = False
        # 翻訳欠落 chip か (#989)。未登録なら右クリックメニューで「翻訳を追加」を強調する。
        self.untranslated = False
        # 修正候補の適用 (置換) を提示してよいか (#1007)。image DB 書き込みを伴うため
        # 編集モードかつアクティブ (非 rejected) chip のみ親 (_add_chip) が True にする。
        self.replace_enabled = False
        # refinement 表示状態 (#931)。set_refinement で更新する。
        self._base_text = display_text
        self._base_tooltip: str | None = None
        # 候補タグ -> {format: count} (#1052、set_refinement で更新)
        self._candidate_counts: dict[str, dict[str, int]] = {}
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

    def set_refinement(
        self,
        recommendation: RefinementRecommendation | None,
        candidate_counts: dict[str, dict[str, int]] | None = None,
    ) -> None:
        """refinement リコメンドを反映する (#931)。

        needs_refinement かつ reason があれば ⚠ マーカーを表示テキストに前置し
        (高さは1行で不変)、ツールチップに reason message と suggestion を出す。
        リコメンドが無ければ元の表示・ツールチップへ戻す。

        Args:
            recommendation: 当該タグのリコメンド。無ければ None。
            candidate_counts: 候補タグのサイト別使用カウント (#1052)。評価時に
                一括解決済みの値で、表示のたびに DB は叩かない。
        """
        # 初回呼び出し時に元ツールチップ (翻訳脚注等) を退避する。
        if self._base_tooltip is None:
            self._base_tooltip = self.toolTip()
        self.refinement = recommendation
        self._candidate_counts = dict(candidate_counts) if candidate_counts else {}
        if recommendation is not None and recommendation.needs_refinement and recommendation.reasons:
            self.setText(f"⚠ {self._base_text}")
            lines = [r.message for r in recommendation.reasons]
            suggestions = [
                _format_candidate_label(s.tag, self._candidate_counts.get(s.tag))
                for s in recommendation.suggestions
                if s.tag
            ]
            if suggestions:
                lines.append("提案: " + ", ".join(suggestions))
            self.setToolTip("\n".join(lines))
        else:
            self.setText(self._base_text)
            self.setToolTip(self._base_tooltip)

    def replacement_candidates(self) -> list[str]:
        """refinement の適用可能な修正候補タグを返す (#1007)。

        ``correction_candidate`` の suggestion だけを対象に、空・自分自身 (canonical と
        同一) を除外し、出現順を保って重複排除する。``review_only`` は人による確認のみ
        なので適用対象にしない。

        Returns:
            置換先候補の canonical タグ文字列リスト。無ければ空リスト。
        """
        rec = self.refinement
        if rec is None or not rec.needs_refinement:
            return []
        candidates: list[str] = []
        for suggestion in rec.suggestions:
            tag = suggestion.tag
            if suggestion.kind != "correction_candidate" or not tag or tag == self.canonical:
                continue
            if tag not in candidates:
                candidates.append(tag)
        return candidates

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """chip の右クリックで「タグ情報」メニューを出す (ADR 0083 §3 / #989)。

        tagdb userdb 系 (canonical 主キー・全画像反映) の「翻訳を追加」「タグ情報を編集」を
        常に提示し、refinement リコメンドがあれば「修正候補を適用」(#1007、編集モードのみ)
        と reason 単位の「この理由を無視」(#931) を続けて並べる。未翻訳 chip では
        「翻訳を追加」を強調表示する (#989)。
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
        freq_action = menu.addAction("使用頻度を見る…")
        freq_action.triggered.connect(
            lambda _checked=False: self.usage_counts_menu_requested.emit(self.canonical)
        )

        rec = self.refinement
        # 適用は image DB 書き込み (置換) のため replace_enabled (編集モード) 時のみ提示する。
        apply_candidates = self.replacement_candidates() if self.replace_enabled else []
        has_ignore = rec is not None and rec.needs_refinement and rec.reasons
        if apply_candidates or has_ignore:
            menu.addSeparator()
        for to_tag in apply_candidates:
            candidate_label = _format_candidate_label(to_tag, self._candidate_counts.get(to_tag))
            apply_action = menu.addAction(f"修正候補を適用: {candidate_label}")
            apply_action.triggered.connect(
                lambda _checked=False, tag=to_tag: self.refinement_apply_requested.emit(self.canonical, tag)
            )
        if rec is not None and has_ignore:
            for reason in rec.reasons:
                action = menu.addAction(f"この理由を無視: {reason.code}")
                action.triggered.connect(
                    lambda _checked=False, code=reason.code: self.refinement_ignore_requested.emit(
                        self.canonical, code
                    )
                )
        menu.exec(event.globalPos())
        event.accept()


def _format_count_short(count: int) -> str:
    """使用カウントを 1.2M / 800k 形式に略記する (#1052)。"""
    if count >= 1_000_000:
        text = f"{count / 1_000_000:.1f}M"
        return text.replace(".0M", "M")
    if count >= 1_000:
        text = f"{count / 1_000:.1f}k"
        return text.replace(".0k", "k")
    return str(count)


def _format_candidate_label(tag: str, counts: dict[str, int] | None) -> str:
    """候補タグの表示ラベルを作る (#1052)。

    counts があれば「tag (danbooru 1.2M / e621 800k)」形式で併記し、実際に使われて
    いる表記がどれか一目で分かるようにする。無い候補は名前のみ (欠損で表示を壊さない)。
    """
    if not counts:
        return tag
    parts = " / ".join(
        f"{format_name} {_format_count_short(count)}"
        for format_name, count in sorted(counts.items(), key=lambda kv: -kv[1])
    )
    return f"{tag} ({parts})"


# tagdb の言語キーは "japanese"/"ja"、"english"/"en" が混在する (#976 PR #991)。
# 新規登録は ja/en に正規化する (#1050) が、表示 lookup は両表記を同値として引く。
_LANGUAGE_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "ja": ("ja", "japanese"),
    "japanese": ("japanese", "ja"),
    "en": ("en", "english"),
    "english": ("english", "en"),
}


def _translation_for_language(translations: dict[str, str], language: str) -> str | None:
    """言語キーのエイリアス (ja/japanese, en/english) を同値として翻訳を引く (#1050)。"""
    for key in _LANGUAGE_KEY_ALIASES.get(language, (language,)):
        if key in translations:
            return translations[key]
    return None


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

    # 登録可能な言語の固定候補 (表示ラベル, 保存値)。自由入力は廃止し、保存値を
    # ja / en に正規化する。tagdb の言語キー表記ゆれ ("japanese"/"ja" 混在、
    # #976 PR #991 Codex P1) を新規登録分で構造的に発生させない (Issue #1050)
    LANGUAGE_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (("日本語", "ja"), ("English", "en"))

    def __init__(self, canonical: str, languages: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("翻訳を追加")
        self._canonical = canonical
        # languages はタグデータ由来の既知言語 (後方互換で受けるが候補には使わない。
        # 固定候補 + 正規化保存が本ダイアログの契約。Issue #1050)
        del languages

        layout = QVBoxLayout(self)
        header = QLabel("タグ情報を編集 · 全画像に反映されます", self)
        header.setObjectName("udbHeader")
        header.setStyleSheet(_UDB_HEADER_QSS)
        layout.addWidget(header)

        form = QFormLayout()
        form.addRow("タグ (canonical):", QLabel(canonical, self))
        self._language_combo = QComboBox(self)
        for label, code in self.LANGUAGE_CHOICES:
            self._language_combo.addItem(label, userData=code)
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
        """選択された言語の正規化コード ("ja" / "en") を返す。"""
        return str(self._language_combo.currentData())

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


class UsageCountsDialog(QDialog):
    """canonical タグの format 別使用頻度を一覧表示する read-only ダイアログ (#997)。

    DB へは書き込まない。表示するデータは親 (`TagPanelWidget`) が既に保持している
    ``_counts_by_canonical`` (#990 の usage_counts をキャッシュしたもの) をそのまま
    渡すだけで、追加の DB / Signal は不要。
    """

    def __init__(self, canonical: str, counts: dict[str, int], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("使用頻度を見る")

        layout = QVBoxLayout(self)
        header = QLabel("使用頻度を見る · 読み取り専用", self)
        header.setObjectName("udbHeader")
        header.setStyleSheet(_UDB_HEADER_QSS)
        layout.addWidget(header)

        form = QFormLayout()
        form.addRow("タグ (canonical):", QLabel(canonical, self))
        if counts:
            for format_name in sorted(counts):
                form.addRow(
                    f"{format_name}:", QLabel(TagPanelWidget._format_count(counts[format_name]), self)
                )
        else:
            form.addRow(QLabel("使用頻度データなし", self))
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TagPanelWidget(QWidget):
    """タグ表示・操作の DB 非依存ウィジェット (ADR 0083 / Issue #987)。

    タグ chip 表示、言語切替・翻訳、選択コピー (#814)、soft-reject 一本のタグ操作
    (無効化 / ✕ / 復活)、手動タグ追加、refinement 警告・ignore (#931)、複数選択の
    バッチ操作バーと使用頻度を見るダイアログ (#997) を担う。操作要求は Signal で
    親へ出すだけで、DB / service への dispatch は親が行う。

    タグ操作モデル (ADR 0083 §3、soft-reject 一本):

    - 単クリック = 無効化⇄復活トグル (破線 chip でインライン表示継続)
    - ✕ ボタン = この画像から外す (パネルから当該セッションのみ非表示)
    - Ctrl+クリック = コピー選択 (#814) / 選択集合が非空ならバッチ操作バーを表示 (#997)
    - 右クリック = タグ情報メニュー (翻訳追加 / タグ情報を編集 / 使用頻度を見る #989・#997、
      refinement ignore #931 / 修正候補を適用 = タグ置換 #1007)

    無効化 (破線表示) と ✕ (非表示) の区別は DB の ``reject_reason`` に永続化され
    (無効化=``not_needed`` / 除外=``incorrect`` / 置換=``replaced``、Issue #1003)、
    reload のたびに ``set_rejected_tags`` が ``_disabled_display`` / ``_hidden`` を
    DB 由来で再構築する。別画像へ往復してもメモリ state に頼らず表示が正しく戻る。
    """

    # image DB 系 (current_image_id 必須。親が dispatch)。単一操作は種別を名前で明示し、
    # 受け手の reason 文字列分岐を排除する (Issue #1003 / ADR 0083 §2)。
    tag_disable_requested = Signal(str)  # canonical — 無効化 (reason='not_needed')
    tag_exclude_requested = Signal(str)  # canonical — 除外   (reason='incorrect')
    tag_restore_requested = Signal(str)  # canonical — 復活
    tag_add_requested = Signal(str)  # 生入力 (親が canonical 解決)
    # 複数選択のバッチ操作 (#997)。親側で「ループして DB 書き込み → 最後に1回だけ reload」
    # にできるよう、単数 Signal を選択件数分ループ emit するのではなく list をまとめて渡す。
    tags_exclude_requested = Signal(list)  # list[str] canonicals — まとめて除外 (incorrect)
    # 無効化⇄復活トグルは各タグ個別の反転なので混在選択では disable/restore 両方が
    # 発生し得る。2 Signal に分けると親側で reload が2回走る (Codex #1001 P2) ため、
    # 1回の Signal で両リストをまとめて渡し、親側で reload を1回に抑える。
    # 無効化側は reason='not_needed'。
    tags_toggle_requested = Signal(list, list)  # (to_disable, to_restore) canonicals
    # refinement 修正候補の適用 = タグ置換 (#1007)。置換元は親が reject_reason='replaced'
    # で非表示化し、置換先を手動タグとして採用する (replace_tag_for_images_batch 経路)。
    tag_replace_requested = Signal(str, str)  # (from_canonical, to_tag)
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
        # 畳む前の全タグ行 (モデル別由来)。隠しテーブルの TSV コピー用 (#1055)
        self._all_tag_rows: list[dict[str, Any]] = []
        # canonical -> tagdb type 名 (小文字)。type 別グループソート用 (#1056)
        self._tag_types: dict[str, str] = {}
        self._translations: dict[int, dict[str, str]] = {}
        self._available_languages: list[str] = []

        # 使用頻度 第2軸 (metric_source, ADR 0083 §5 / #990)。表示言語とは独立した軸。
        # 親が bulk 取得した {tag_id: {format_name: count}} を set_usage_counts で受け、
        # canonical → {format_name: count} へ展開して chip に補助表示する (読み取り専用)。
        self._usage_counts: dict[int, dict[str, int]] = {}
        self._counts_by_canonical: dict[str, dict[str, int]] = {}
        self._metric_source: str = ""  # 空文字 = なし (count 非表示)

        # 編集モード (soft-reject 導線。既定 read-only)
        self._tag_edit_enabled: bool = False

        # 操作の表示状態 (Issue #1003: DB の reject_reason から reload 毎に再構築される)。
        self._disabled_display: set[str] = set()  # 無効化 (破線でインライン表示継続、not_needed)
        self._hidden: set[str] = set()  # 除外/置換 (非表示、incorrect/replaced)
        self._rejected_tags: list[str] = []  # 親 (DB) から渡される soft-rejected canonical
        # Ctrl+クリックで選択された canonical 集合 (#814 のコピー選択 + #997 のバッチ操作起点)。
        # chip は再描画のたびに新規生成されるため、選択状態はウィジェット側で持って復元する。
        self._selected_canonicals: set[str] = set()
        # 表示中画像の識別子。set_tags でこれが変わったときだけ表示状態をリセットする。
        # 同一画像の reject reload (✕ → 親が soft-reject → 同画像 reload → set_tags 呼び戻し)
        # で _hidden が消え、外したタグが破線で即再出現する回帰を防ぐ (PR #992 Codex P2)。
        self._image_id: int | None = None

        # 描画中の chip 群と refinement 保持 (#931: chip 再生成をまたいで ⚠ を復元)
        self._tag_chips: list[SelectableTagChip] = []
        self._last_refinements: dict[str, RefinementRecommendation] = {}
        # 候補タグ -> {format: count} (#1052、apply_refinements で更新)
        self._last_candidate_counts: dict[str, dict[str, int]] = {}

        self._setup_ui()

        self._lang_combo.currentTextChanged.connect(self._on_language_changed)
        self._metric_combo.currentIndexChanged.connect(self._on_metric_changed)

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
        # スクロール領域内のためホイール通過で値が変わらない DS 部品を使う (#1051)
        self._lang_combo = DsNoScrollComboBox(self._lang_bar)
        self._lang_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lang_layout.addWidget(self._lang_combo)
        self._lang_bar.setVisible(False)
        root.addWidget(self._lang_bar)

        # 使用頻度の第2軸セレクタ (metric_source, ADR 0083 §5 / #990)。表示言語と独立。
        # usage count データが無ければ非表示。「なし」選択で chip の count を消す。
        self._metric_bar = QWidget(self)
        metric_layout = QHBoxLayout(self._metric_bar)
        metric_layout.setContentsMargins(0, 0, 0, 2)
        metric_layout.addWidget(QLabel("頻度:", self._metric_bar))
        self._metric_combo = DsNoScrollComboBox(self._metric_bar)
        self._metric_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._metric_combo.addItem(_METRIC_NONE_LABEL)
        metric_layout.addWidget(self._metric_combo)
        self._metric_bar.setVisible(False)
        root.addWidget(self._metric_bar)

        # チップ表示コンテナ。高さ上限付きスクロール箱に収める (#835)。FlowLayout の
        # minimumSizeHint は「最小幅で全チップ縦積み」の過大値を報告し、放置すると親の
        # 高さを膨張させてスコアカード下に異常な余白 + 不要スクロールを生む。
        from .tag_cloud_widget import FlowLayout

        self._tags_chip_container = QWidget(self)
        self._tags_chip_layout = FlowLayout(self._tags_chip_container, spacing=4)
        # 縦は Preferred (ShrinkFlag あり) にする (#1025)。Minimum だと FlowLayout の
        # sizeHint (「sizeHint 幅で全チップ縦積み」した過大値、例: 40チップで996px) が
        # container の最小高さとして固定され、widgetResizable な QScrollArea が実幅の
        # 必要高さ (heightForWidth) まで縮められず、チップ下に空白スクロール領域が残る。
        self._tags_chip_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._tags_scroll = QScrollArea(self)
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._tags_scroll.setWidget(self._tags_chip_container)
        root.addWidget(self._tags_scroll)

        # 複数選択バッチ操作バー (#997)。選択 0件では非表示、_update_selection_bar が
        # 中身を都度作り直す (ボタン数が少ないので都度再構築で十分)。
        self._selection_bar = QWidget(self)
        self._selection_bar_layout = QHBoxLayout(self._selection_bar)
        self._selection_bar_layout.setContentsMargins(0, 2, 0, 2)
        self._selection_bar.setVisible(False)
        root.addWidget(self._selection_bar)

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
        usage_counts: dict[int, dict[str, int]] | None = None,
        tag_types: dict[str, str] | None = None,
    ) -> None:
        """タグ集合で表示を更新する。

        ``image_id`` が前回と変わったとき (= 別画像の表示) だけ表示状態
        (無効化 / 非表示 / refinement) をリセットする。同一画像の reject reload
        では非表示などの操作状態を保持し、現在の言語選択で chip を再描画する。

        Args:
            tags: タグ詳細情報リスト (Repository 層形式)。
                ``[{"tag": "1girl", "tag_id": 10, "model_name": ..., ...}, ...]``
                同一 canonical (``tag`` キー) の重複行は初出順で 1 件に畳んで表示する
                (Issue #1055)。
            translations: ``{tag_id: {language: translated_text}}``。省略時は空。
            available_languages: 利用可能言語リスト (脚注/フォールバック用)。
            image_id: 表示中画像の識別子。省略 (None) 時は常にリセットする
                (後方互換)。同一 ``image_id`` の再呼び出しは表示状態を保持する。
            usage_counts: サイト別使用頻度 ``{tag_id: {format_name: count}}`` (#990)。
                指定時は metric セレクタと chip 表示を 1 度の再描画で同時更新する
                (set_usage_counts を別途呼ぶと余分な再描画になるため統合する)。
            tag_types: ``{canonical: type名(小文字)}`` (#1056)。チップの type 別
                グループソートに使う。引けないタグは「不明」として末尾グループ。
        """
        # ✕ で外したタグは同一画像の reject reload を跨いで非表示を維持する。
        # 親が ✕ → soft-reject → 同画像 reload → set_tags を呼び戻す経路で _hidden を
        # 消すと、外したタグが破線復活 chip として即再出現する (PR #992 Codex P2)。
        image_changed = image_id is None or image_id != self._image_id
        self._image_id = image_id
        # type map はソート (_sort_tags_by_type) より先に確定させる (#1056)。
        # 別画像で type 情報が来ていない場合は前画像の map を引き継がない
        # (無関係な canonical が前画像の type でグループ化される。Codex P2)
        if tag_types is not None:
            self._tag_types = dict(tag_types)
        elif image_changed:
            self._tag_types = {}
        # 複数モデルでアノテーションした画像は同一 canonical のタグ行がモデル数ぶん
        # 重複する (heart x9 等)。チップ表示は canonical 単位で 1 つに畳む (初出順維持、
        # DB のモデル別由来行は不変。チップ操作はもともと canonical 単位で dispatch
        # されるため操作意味論は変わらない。Issue #1055 / ADR 0083 §2)。
        # 隠しテーブル (Model/Source/Confidence の TSV コピー) はモデル別由来を見せる
        # 場所なので、畳む前の全行を別途保持する (Codex P2)。
        self._all_tag_rows = list(tags)
        kept_index_by_canonical: dict[str, int] = {}
        deduped_tags: list[dict[str, Any]] = []
        for tag_dict in tags:
            canonical = str(tag_dict.get("tag", ""))
            if not canonical:
                deduped_tags.append(tag_dict)
                continue
            kept_index = kept_index_by_canonical.get(canonical)
            if kept_index is None:
                kept_index_by_canonical[canonical] = len(deduped_tags)
                deduped_tags.append(tag_dict)
            elif deduped_tags[kept_index].get("tag_id") is None and tag_dict.get("tag_id") is not None:
                # 初出行が legacy (tag_id 無し) の場合は、翻訳/使用頻度を解決できる
                # tag_id 付きの行で初出位置を差し替える (Codex P2)
                deduped_tags[kept_index] = tag_dict
        # type 別グループ + グループ内アルファベット順で表示する (#1056)。
        # 表示のみの並べ替えで DB の行順は不変。type 不明 (tagdb 未登録等) は末尾。
        self._tags = self._sort_tags_by_type(deduped_tags)
        self._translations = dict(translations) if translations else {}
        self._available_languages = list(available_languages) if available_languages else []
        if usage_counts is not None:
            self._usage_counts = dict(usage_counts)
        if image_changed:
            # 別画像なので前画像の操作・refinement・選択・reject を引き継がない。
            # 表示種別 (無効化/除外) は直後の set_rejected_tags が DB の reject_reason から
            # 再構築する (メモリ state 非依存、Issue #1003)。
            self._disabled_display = set()
            self._hidden = set()
            self._rejected_tags = []
            self._last_refinements = {}
            self._last_candidate_counts = {}
            self._selected_canonicals = set()
        self._rebuild_counts_by_canonical()
        self._refresh_metric_selector()
        self._populate_table(self._all_tag_rows)
        self._refresh_tags_for_language(self._current_language())

    def set_translations(
        self, translations: dict[int, dict[str, str]], available_languages: list[str]
    ) -> None:
        """翻訳データと利用可能言語を差し替えて再描画する。"""
        self._translations = dict(translations)
        self._available_languages = list(available_languages)
        self._refresh_tags_for_language(self._current_language())

    def set_usage_counts(self, usage_counts: dict[int, dict[str, int]]) -> None:
        """サイト別 (format 別) 使用頻度を設定し metric セレクタを更新する (#990)。

        表示言語とは独立した第2軸。``{tag_id: {format_name: count}}`` を受け取り、
        現在のタグ集合の canonical へ展開する。利用可能な metric (format 名) を
        セレクタへ反映し、データが無ければ metric バーを隠す。count は読み取り専用で
        chip への補助表示にのみ使う (DB へは書き込まない)。

        Args:
            usage_counts: ``{tag_id: {format_name: count}}``。空なら count 非表示。
        """
        self._usage_counts = dict(usage_counts)
        self._rebuild_counts_by_canonical()
        self._refresh_metric_selector()
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

    def update_language_selector(
        self, available_languages: list[str], *, prefer: str | None = None
    ) -> None:
        """言語コンボの候補を選択を保ったまま更新する (#1050)。

        新しい言語 ("en" 等) の翻訳を登録した直後に候補へ反映するために使う。
        initialize_language_selector と異なり選択を english へ巻き戻さない
        (Codex #995 P2 の巻き戻り事故を再発させない)。

        Args:
            available_languages: 利用可能な言語リスト。
            prefer: 直前に登録した翻訳の言語。原文 (english) 表示中のときだけ
                この言語へ切り替え、登録結果を即時可視化する (Codex P2)。
                非英語表示中は現在の選択を保つ。
        """
        current = self._current_language()
        target = prefer if (prefer and current == "english") else current
        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItem("english")  # 常に先頭 (原文)
        for lang in available_languages:
            if lang != "english":
                self._lang_combo.addItem(lang)
        index = self._lang_combo.findText(target)
        if index >= 0:
            self._lang_combo.setCurrentIndex(index)
        self._lang_combo.blockSignals(False)
        self._lang_bar.setVisible(self._lang_combo.count() > 1)

    def set_tag_edit_enabled(self, enabled: bool) -> None:
        """タグ soft-reject 編集モードを切り替える。

        Args:
            enabled: True で ✕ ボタン / 手動追加入力 / クリック無効化を有効にする。
        """
        self._tag_edit_enabled = enabled
        self._tag_add_input.setVisible(enabled)
        self._refresh_tags_for_language(self._current_language())

    def set_rejected_tags(self, rejected_tags: list[dict[str, Any]]) -> None:
        """soft-rejected タグを reject_reason 付きで受け、表示種別を DB から再構築する。

        現象の根治点 (Issue #1003): 無効化 (``_disabled_display``) と除外 (``_hidden``) の
        区別をメモリ state ではなく DB 由来の ``reject_reason`` から reload のたびに再構築
        する。別画像へ往復してもメモリ state に頼らず表示が正しく戻る。

        - ``reject_reason == 'not_needed'`` → 破線 chip でインライン表示 (無効化、クリックで復活)
        - ``reject_reason in ('incorrect', 'replaced')`` → 非表示

        Args:
            rejected_tags: ``{"tag": str, "reject_reason": str | None, ...}`` の dict リスト
                (``get_rejected_tags`` の戻り値)。
        """
        rows = [row for row in rejected_tags if row.get("tag")]
        self._rejected_tags = [row["tag"] for row in rows]
        # DB reject_reason から表示状態を再構築する (メモリ非依存、Issue #1003)。
        # reason 不明 (None 等) は安全側に倒し無効化 (破線で残す) 扱いにする。
        self._disabled_display = {
            row["tag"] for row in rows if row.get("reject_reason") in (None, _REJECT_REASON_NOT_NEEDED)
        }
        self._hidden = {
            row["tag"] for row in rows if row.get("reject_reason") not in (None, _REJECT_REASON_NOT_NEEDED)
        }
        self._refresh_tags_for_language(self._current_language())

    def apply_refinements(
        self,
        recommendations: dict[str, RefinementRecommendation],
        candidate_counts: dict[str, dict[str, int]] | None = None,
    ) -> None:
        """各タグ chip に refinement リコメンドを反映する (#931)。

        chip の canonical をキーにマップを引き、該当があれば ⚠ + ツールチップを表示、
        無ければリコメンド表示を消す。言語切替や編集モード切替で chip が再生成されても
        ⚠ を失わないよう最後の結果を保持し、再描画末尾で自動再反映する。

        Args:
            recommendations: ``{canonical タグ: RefinementRecommendation}``。
        """
        self._last_refinements = dict(recommendations)
        self._last_candidate_counts = dict(candidate_counts) if candidate_counts else {}
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
        self._last_candidate_counts = {}
        self._usage_counts = {}
        self._counts_by_canonical = {}
        self._selected_canonicals = set()
        self._refresh_metric_selector()
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

    # ─── 使用頻度 第2軸 (metric_source, #990) ──────────────────────────

    def _rebuild_counts_by_canonical(self) -> None:
        """``{tag_id: {format: count}}`` を canonical キーへ展開する (#990)。

        chip 描画は canonical (原文) 基準のため、現在のタグ集合の tag_id →
        usage count を canonical → ``{format: count}`` へ写し替えてキャッシュする。
        """
        counts: dict[str, dict[str, int]] = {}
        for tag_dict in self._tags:
            tag_id = tag_dict.get("tag_id")
            canonical = tag_dict.get("tag", "")
            if tag_id is None or not canonical:
                continue
            per_format = self._usage_counts.get(tag_id)
            if per_format:
                counts[canonical] = dict(per_format)
        self._counts_by_canonical = counts

    def _refresh_metric_selector(self) -> None:
        """利用可能な metric (format 名) で metric セレクタを再構築する (#990)。

        現在のタグ集合に usage count がある format 名を集約して候補にする。
        データが無ければ metric バーを隠す。可能なら現在の選択を維持する。
        """
        available = sorted({fmt for per_format in self._counts_by_canonical.values() for fmt in per_format})
        if not available:
            self._metric_bar.setVisible(False)
            self._metric_combo.blockSignals(True)
            self._metric_combo.clear()
            self._metric_combo.addItem(_METRIC_NONE_LABEL)
            self._metric_combo.blockSignals(False)
            self._metric_source = ""
            return

        previous = self._metric_source
        self._metric_combo.blockSignals(True)
        self._metric_combo.clear()
        self._metric_combo.addItem(_METRIC_NONE_LABEL)
        for fmt in available:
            self._metric_combo.addItem(fmt)
        # 直前の選択が候補に残っていれば維持、無ければ「なし」へ戻す。
        index = self._metric_combo.findText(previous) if previous else 0
        self._metric_combo.setCurrentIndex(index if index >= 0 else 0)
        self._metric_combo.blockSignals(False)
        self._metric_source = self._current_metric()
        self._metric_bar.setVisible(True)

    def _current_metric(self) -> str:
        """現在選択中の metric (format 名)。「なし」選択時は空文字を返す。"""
        text = self._metric_combo.currentText()
        return "" if text == _METRIC_NONE_LABEL else text

    @Slot(int)
    def _on_metric_changed(self, _index: int) -> None:
        """metric セレクタ変更時に chip の count 補助表示を更新する (#990)。"""
        self._metric_source = self._current_metric()
        self._refresh_tags_for_language(self._current_language())

    @staticmethod
    def _format_count(count: int) -> str:
        """使用回数を ``1.2M`` / ``842k`` 形式へ整形する (ADR 0083 §5 / #990)。"""
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M".replace(".0M", "M")
        if count >= 1_000:
            return f"{count / 1_000:.1f}k".replace(".0k", "k")
        return str(count)

    def _count_suffix(self, canonical: str) -> str:
        """現在の metric における canonical の count サフィックス ``" (1.2k)"`` を返す。

        metric=なし、または当該 format に count が無ければ空文字を返す。
        """
        if not self._metric_source:
            return ""
        count = self._counts_by_canonical.get(canonical, {}).get(self._metric_source)
        if count is None:
            return ""
        return f" ({self._format_count(count)})"

    # type 別グループの表示順 (#1056)。語彙は TagTypeEditDialog.TYPE_CHOICES と同一。
    # 未知 type / type 不明は末尾グループ (ユーザー確認済み)
    _TYPE_GROUP_ORDER: ClassVar[dict[str, int]] = {
        "character": 0,
        "copyright": 1,
        "artist": 2,
        "general": 3,
        "meta": 4,
    }
    _UNKNOWN_TYPE_GROUP = 5

    def _sort_tags_by_type(self, tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """タグ行を type 別グループ + グループ内 canonical アルファベット順に並べる (#1056)。"""

        def sort_key(tag_dict: dict[str, Any]) -> tuple[int, str]:
            canonical = str(tag_dict.get("tag", ""))
            type_name = self._tag_types.get(canonical, "")
            group = self._TYPE_GROUP_ORDER.get(type_name, self._UNKNOWN_TYPE_GROUP)
            return (group, canonical.lower())

        return sorted(tags, key=sort_key)

    def _display_text_for(
        self, tag_dict: dict[str, Any], language: str, use_english: bool
    ) -> tuple[str, bool]:
        """タグ行の表示名と翻訳有無を解決する。

        Returns:
            (表示名, 翻訳ありか)。英語表示・tag_id 無しは原文 + 翻訳欠落マーク無し。
        """
        original = str(tag_dict.get("tag", ""))
        tag_id = tag_dict.get("tag_id")
        if use_english or tag_id is None:
            return original, True
        translated = _translation_for_language(self._translations.get(tag_id, {}), language)
        return (translated if translated else original), translated is not None

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
        for tag_dict in self._tags:
            display, has_translation = self._display_text_for(tag_dict, language, use_english)
            tag_names.append(display)
            chip_items.append((display, tag_dict.get("tag", ""), has_translation))

        # 隠しテーブル (全行 = モデル別由来) の Tag 列 (列0) も更新する。
        # チップは canonical 単位で畳むためテーブルとは行数が異なる (#1055)
        for row, tag_dict in enumerate(self._all_tag_rows):
            item = self.tableWidgetTags.item(row, 0)
            if item is not None:
                display, _ = self._display_text_for(tag_dict, language, use_english)
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
            self._update_selection_bar()
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
        self._update_selection_bar()

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
        # 使用頻度 metric が選択されていれば count を表示名へ付与する (#990)。
        # canonical (original) は変えずコピー結果へ影響させない。
        display = f"{display}{self._count_suffix(original)}"
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
        # 選択集合 (#814 / #997) を再描画をまたいで復元する。disabled より優先して上書きする。
        if original in self._selected_canonicals:
            chip.selected = True
            chip.setStyleSheet(self._selected_chip_qss())
        chip.clicked.connect(lambda c=chip: self._on_chip_clicked(c))
        chip.ctrl_clicked.connect(lambda c=chip: self._on_chip_ctrl_clicked(c))
        # refinement「この理由を無視」を上位へ中継 (#931)
        chip.refinement_ignore_requested.connect(self.refinement_ignored)
        # refinement「修正候補を適用」(#1007): image DB 書き込み (置換) を伴うため編集モード
        # かつアクティブ chip のみ有効。rejected 行は置換経路の対象外 (rejected_at IS NULL
        # フィルタ) なので破線 chip では提示しない。
        chip.replace_enabled = self._tag_edit_enabled and not disabled
        chip.refinement_apply_requested.connect(self.tag_replace_requested)
        # タグ情報メニュー (#989): chip 右クリック → 親がダイアログを開く。
        chip.translation_add_menu_requested.connect(self._open_translation_dialog)
        chip.type_edit_menu_requested.connect(self._open_type_edit_dialog)
        # 使用頻度を見る (#997): read-only、TagPanelWidget 内で完結する。
        chip.usage_counts_menu_requested.connect(self._open_usage_counts_dialog)
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
            chip.replace_enabled = True
            self.tag_restore_requested.emit(canonical)
        else:
            # アクティブ chip クリック = 無効化 (破線でインライン継続、reason='not_needed')
            self._disabled_display.add(canonical)
            chip.setStyleSheet(self._disabled_chip_qss())
            # rejected 行は置換経路 (rejected_at IS NULL フィルタ) の対象外なので、
            # reload を待たず「修正候補を適用」の提示も止める (#1007)。
            chip.replace_enabled = False
            self.tag_disable_requested.emit(canonical)

    def _on_chip_ctrl_clicked(self, chip: SelectableTagChip) -> None:
        """Ctrl+クリック: コピー選択トグル (#814)。バッチ操作バーの起点にもなる (#997)。"""
        chip.selected = not chip.selected
        chip.setStyleSheet(self._selected_chip_qss() if chip.selected else chip.base_qss)
        if chip.selected:
            self._selected_canonicals.add(chip.canonical)
        else:
            self._selected_canonicals.discard(chip.canonical)
        self._update_selection_bar()

    def _on_chip_removed(self, canonical: str) -> None:
        """✕ ボタン: この画像から外す (除外 soft-reject + 当該セッション非表示)。"""
        self._hidden.add(canonical)
        self._selected_canonicals.discard(canonical)
        self.tag_exclude_requested.emit(canonical)
        self._refresh_tags_for_language(self._current_language())

    # ─── バッチ操作バー (#997) ──────────────────────────────────────────

    def _update_selection_bar(self) -> None:
        """選択集合に応じてバッチ操作バーの表示・ボタン構成を作り直す (#997)。

        選択 0件では非表示にする。ボタン数が少ないので都度作り直しで十分
        (chip の全再構築 (`_clear_chip_layout`) と同じ方針)。
        """
        while self._selection_bar_layout.count():
            child = self._selection_bar_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        selected = self._selected_canonicals
        if not selected:
            self._selection_bar.setVisible(False)
            return

        count_label = QLabel(f"{len(selected)}件選択中", self._selection_bar)
        self._selection_bar_layout.addWidget(count_label)

        # 外す/無効化⇄復活は soft-reject を伴うので単一チップ操作 (_on_chip_clicked /
        # _on_chip_removed) と同じく編集モード時のみ有効にする。
        remove_button = QPushButton("外す", self._selection_bar)
        remove_button.setEnabled(self._tag_edit_enabled)
        remove_button.clicked.connect(self._on_batch_remove)
        self._selection_bar_layout.addWidget(remove_button)

        toggle_button = QPushButton("無効化⇄復活", self._selection_bar)
        toggle_button.setEnabled(self._tag_edit_enabled)
        toggle_button.clicked.connect(self._on_batch_toggle_disable)
        self._selection_bar_layout.addWidget(toggle_button)

        single = next(iter(selected)) if len(selected) == 1 else None

        translate_button = QPushButton("翻訳", self._selection_bar)
        translate_button.setEnabled(single is not None)
        if single is not None:
            translate_button.clicked.connect(
                lambda _checked=False, c=single: self._open_translation_dialog(c)
            )
        self._selection_bar_layout.addWidget(translate_button)

        edit_button = QPushButton("編集", self._selection_bar)
        edit_button.setEnabled(single is not None)
        if single is not None:
            edit_button.clicked.connect(lambda _checked=False, c=single: self._open_type_edit_dialog(c))
        self._selection_bar_layout.addWidget(edit_button)

        freq_button = QPushButton("頻度", self._selection_bar)
        freq_button.setEnabled(single is not None)
        if single is not None:
            freq_button.clicked.connect(lambda _checked=False, c=single: self._open_usage_counts_dialog(c))
        self._selection_bar_layout.addWidget(freq_button)

        clear_button = QPushButton("選択解除", self._selection_bar)
        clear_button.clicked.connect(self._on_batch_clear_selection)
        self._selection_bar_layout.addWidget(clear_button)

        self._selection_bar.setVisible(True)

    def _on_batch_remove(self) -> None:
        """バッチ「外す」: 選択中タグをまとめて非表示にし soft-reject する (#997)。

        既存の単一チップ ✕ (`_on_chip_removed`) の複数版。
        """
        canonicals = list(self._selected_canonicals)
        if not canonicals:
            return
        self._hidden.update(canonicals)
        self._selected_canonicals.clear()
        self.tags_exclude_requested.emit(canonicals)
        self._refresh_tags_for_language(self._current_language())

    def _on_batch_toggle_disable(self) -> None:
        """バッチ「無効化⇄復活」: 選択中の各タグを個別に現在状態の反転にする (#997)。

        design の「選択全体を1方向へ揃える」方式ではなく、既存の単一チップクリック
        (`_on_chip_clicked`) と同じ判定を選択集合の各タグへ独立に適用する
        (混在選択でも各タグが個別に無効化⇄復活する)。
        """
        canonicals = list(self._selected_canonicals)
        if not canonicals:
            return
        to_disable: list[str] = []
        to_restore: list[str] = []
        for canonical in canonicals:
            if canonical in self._disabled_display or canonical in self._rejected_tags:
                self._disabled_display.discard(canonical)
                to_restore.append(canonical)
            else:
                self._disabled_display.add(canonical)
                to_disable.append(canonical)
        self._selected_canonicals.clear()
        # 混在選択でも reload が1回で済むよう、disable/restore を1回の Signal でまとめて渡す
        # (Codex #1001 P2)。無効化側は reason='not_needed' で親が dispatch する。
        self.tags_toggle_requested.emit(to_disable, to_restore)
        self._refresh_tags_for_language(self._current_language())

    def _on_batch_clear_selection(self) -> None:
        """「選択解除」ボタン: 選択集合をクリアして chip の強調表示を戻す (#997)。"""
        self._selected_canonicals.clear()
        for chip in self._tag_chips:
            if chip.selected:
                chip.selected = False
                chip.setStyleSheet(chip.base_qss)
        self._update_selection_bar()

    @Slot(str)
    def _open_usage_counts_dialog(self, canonical: str) -> None:
        """「使用頻度を見る」ダイアログを開く (#997)。read-only、Signal 発火なし。

        必要なデータ (`_counts_by_canonical`) は #990 の usage_counts で既にキャッシュ
        済みのため、追加の DB 問い合わせや親への dispatch は不要。

        Args:
            canonical: 使用頻度を表示する canonical タグ文字列。
        """
        dialog = UsageCountsDialog(canonical, self._counts_by_canonical.get(canonical, {}), self)
        dialog.exec()

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
            chip.set_refinement(rec, candidate_counts=self._last_candidate_counts)
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
        # chip 再構築直後はレイアウト未 activation で新チップがまだ hidden のことがあり、
        # QWidgetItem.sizeHint() が (0,0) を返して heightForWidth=0 → 箱が 8px に潰れる
        # (#1025)。同期計測の前に hidden の chip を明示的に可視化して実寸を得る。
        layout = self._tags_chip_layout
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is not None and widget.isHidden():
                widget.setVisible(True)
        # 収まるときに内側スクロールバーが出ないよう僅かな余裕を足す。
        needed = layout.heightForWidth(width) + 8
        self._tags_scroll.setFixedHeight(min(needed, self._TAGS_MAX_HEIGHT))
