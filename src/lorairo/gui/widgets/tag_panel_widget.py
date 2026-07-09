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

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QRect, Qt, Signal, Slot
from PySide6.QtGui import (
    QContextMenuEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QResizeEvent,
    QShortcut,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...utils.language_keys import (
    canonical_language_key,
    dedupe_languages_by_family,
    dedupe_translations_by_family,
    language_alias_keys,
    translation_for_language,
)
from ...utils.log import logger
from .. import theme
from .ds_no_scroll_combo_box import DsNoScrollComboBox
from .tag_cloud_widget import FlowLayout

if TYPE_CHECKING:
    from genai_tag_db_tools.models import RefinementRecommendation

# 使用頻度 第2軸セレクタの「なし」選択肢ラベル (ADR 0083 §5 / #990)。
# 選択時は metric_source を空にして chip の count 補助表示を消す。
_METRIC_NONE_LABEL = "なし"

# アイコン系アクションボタンの affordance (#1210)。テキストのみだとクリック可能に
# 見えないため、hover 背景 + ボーダーでボタンらしさを付与する (palette 追従)。
ACTION_TOOL_BUTTON_QSS = """
QToolButton {
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 2px 6px;
}
QToolButton:hover {
    background: palette(midlight);
    border-color: palette(mid);
}
QToolButton:pressed {
    background: palette(mid);
}
"""

# soft-reject 種別 (schema.REJECT_REASON_* の SSoT と一致、Issue #1003)。
# 本ウィジェットは DB 非依存のため schema を import せず値のみ複製する。
# 'not_needed' のみインライン破線 chip (無効化) で残し、'incorrect'/'replaced' は非表示。
_REJECT_REASON_NOT_NEEDED = "not_needed"

# 翻訳品質系の RefinementReason.code (lib の _detect_translation_quality_reasons が返す集合、#1054)。
# これらが付いた chip は「翻訳を修正…」を ⚠ 付きラベルにして修正 UI への直行導線にする。
# missing_translation は既存翻訳が無い (修正対象なし) ため対象外で、「翻訳を追加…」が導線。
_TRANSLATION_FIX_REASON_CODES: frozenset[str] = frozenset(
    {
        "wrong_language_translation",
        "overlong_translation",
        "description_like_translation",
        "translation_mismatch",
        "low_quality_translation",
    }
)

# タグ種別の表示メタデータ (グリフ + 日本語ラベル) と表示順の SSoT (Issue #1233 / #1241
# 本文で確定)。旧 `TagPanelWidget._TYPE_GROUP_ORDER` (#1056) は character→copyright→
# artist→general→meta の順だったが、本 SSoT (meta が general より前) に統一する
# (デザイン確定が新しい SSoT)。general は無印 (グリフなし、ノイズを増やさない)。
_TYPE_ORDER: tuple[str, ...] = ("character", "copyright", "artist", "meta", "general")
_TYPE_GLYPHS: dict[str, str] = {
    "character": "C",
    "copyright": "©",
    "artist": "A",
    "meta": "M",
    "general": "",
}
_TYPE_LABELS_JA: dict[str, str] = {
    "character": "キャラクター",
    "copyright": "版権",
    "artist": "絵師",
    "meta": "メタ",
    "general": "一般",
}


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
    # canonical, reason_code, this_image_only (#1053 スコープ選択式)
    refinement_ignore_requested = Signal(str, str, bool)
    # refinement 修正候補の適用要求 (#1007、image DB 系の置換操作): (canonical, to_tag)
    refinement_apply_requested = Signal(str, str)
    # タグ情報メニュー要求 (#989、tagdb userdb 系)。親がダイアログを開く。
    translation_add_menu_requested = Signal(str)  # canonical — 翻訳を追加
    translation_fix_menu_requested = Signal(str)  # canonical — 翻訳を修正 (#1054)
    type_edit_menu_requested = Signal(str)  # canonical — タグ情報 (種別) を編集
    # 使用頻度を見るメニュー要求 (#997)。read-only で TagPanelWidget 内で完結する。
    usage_counts_menu_requested = Signal(str)  # canonical
    # image DB 系編集要求 (#1240)。親が入力/保存先 dispatch を担う。
    tag_replace_menu_requested = Signal(str)  # canonical — 任意タグへ置換
    tag_move_to_caption_requested = Signal(str)  # canonical — キャプションへ移動

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
        # 種別インジケータ (Issue #1233 / #1241)。set_type_indicator で更新される。
        # 左端ストライプ色 (None = 無印) と表示用グリフ文字を保持する。
        self.stripe_color: str | None = None
        self.type_glyph: str = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Ctrl+C を chip フォーカス中に拾えるようクリックフォーカスを許可する。
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def set_type_indicator(self, type_name: str | None) -> None:
        """タグ種別インジケータ (左端ストライプ + グリフ) を設定する (#1233 / #1241)。

        ``theme.TAG_TYPE_PALETTE`` に無い種別 (general・不明・None) はストライプ・
        グリフとも無印にする (ノイズを増やさない)。ここで設定したストライプ色は、
        以後 ``setStyleSheet`` で切り替わる翻訳解決中/翻訳なし/選択中/無効化の
        どの状態スタイルにも独立して重畳される (状態と種別表示を分離する)。

        Args:
            type_name: tagdb type 名 (小文字)。None / 未登録は無印。
        """
        palette = theme.TAG_TYPE_PALETTE.get(type_name) if type_name else None
        self.stripe_color = palette[1] if palette is not None else None
        self.type_glyph = _TYPE_GLYPHS.get(type_name, "") if type_name else ""

    def setStyleSheet(self, style_sheet: str) -> None:
        """状態スタイルに種別ストライプ (#1233 / #1241) を重ねて適用する。

        左端ストライプは翻訳解決中/翻訳なし/選択中/無効化のどの状態スタイルとも
        独立した装飾のため、呼び出し側 (``_add_chip`` / クリックハンドラ等) が渡す
        スタイルに関わらず常に維持する。
        """
        stripe_color = getattr(self, "stripe_color", None)
        if stripe_color:
            style_sheet = f"{style_sheet}\nQLabel {{ border-left: 4px solid {stripe_color}; }}"
        super().setStyleSheet(style_sheet)

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
        # 誤翻訳の修正導線 (#1054)。翻訳品質系 reason が付いた chip では ⚠ 付きラベルにして
        # 直行導線であることを明示する (reason の詳細はツールチップに出ている)。
        has_translation_reason = self.refinement is not None and any(
            reason.code in _TRANSLATION_FIX_REASON_CODES for reason in self.refinement.reasons
        )
        fix_label = "翻訳を修正 (⚠ 翻訳品質)…" if has_translation_reason else "翻訳を修正…"
        fix_action = menu.addAction(fix_label)
        fix_action.triggered.connect(
            lambda _checked=False: self.translation_fix_menu_requested.emit(self.canonical)
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
        if self.replace_enabled or apply_candidates or has_ignore:
            menu.addSeparator()
        if self.replace_enabled:
            replace_action = menu.addAction("別のタグに置換…")
            replace_action.triggered.connect(
                lambda _checked=False: self.tag_replace_menu_requested.emit(self.canonical)
            )
            move_caption_action = menu.addAction("キャプションに移動")
            move_caption_action.triggered.connect(
                lambda _checked=False: self.tag_move_to_caption_requested.emit(self.canonical)
            )
        for to_tag in apply_candidates:
            candidate_label = _format_candidate_label(to_tag, self._candidate_counts.get(to_tag))
            apply_action = menu.addAction(f"修正候補を適用: {candidate_label}")
            apply_action.triggered.connect(
                lambda _checked=False, tag=to_tag: self.refinement_apply_requested.emit(self.canonical, tag)
            )
        if rec is not None and has_ignore:
            # ワンクリック操作に対して影響 (全画像・恒久) が重すぎたため、
            # スコープを文言で明示した2アクションに分ける (#1053)
            for reason in rec.reasons:
                image_action = menu.addAction(f"この画像でのみ無視: {reason.code}")
                image_action.triggered.connect(
                    lambda _checked=False, code=reason.code: self.refinement_ignore_requested.emit(
                        self.canonical, code, True
                    )
                )
                global_action = menu.addAction(f"全画像で無視: {reason.code}")
                global_action.triggered.connect(
                    lambda _checked=False, code=reason.code: self.refinement_ignore_requested.emit(
                        self.canonical, code, False
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


# tagdb の言語キー表記ゆれ (ja/japanese, en/english) の同値解決は共有ヘルパー
# (utils.language_keys) へ集約した (#1084)。widget / worker / service で二重定義しない。
_translation_for_language = translation_for_language


# tagdb userdb 系ダイアログのティール「タグ情報」見出し QSS (ADR 0083 §2 / #989)。
# image DB 系 (青) と保存先を視覚的に分けるため UDB トークンで縁取る。
_UDB_HEADER_QSS = (
    f"QLabel#udbHeader {{ background-color: {theme.UDB_SOFT}; color: {theme.UDB};"
    f" border: 1px solid {theme.UDB_BORDER}; border-radius: {theme.RADIUS_CHIP}px;"
    f" padding: 4px 8px; font-weight: 600; }}"
)


class TranslationAddDialog(QDialog):
    """canonical タグの翻訳を管理するダイアログ (ADR 0083 §2 / #989 / #1084)。

    「翻訳を追加」から「翻訳の管理」へ拡張した (#1084)。選択言語の全候補訳をラジオ一覧で
    表示し、現在の主訳を選択済み + 「(主訳)」で明示する。ここから主訳の切り替えと新規訳の
    追加を 1 つのダイアログで行える。

    DB は知らない。候補は親から注入された ``candidates_provider`` (language を渡すと
    ``(候補訳リスト, 現在の主訳)`` を返す callback) で取得し、OK 確定の結果は親が dispatch
    する。保存先が「タグ情報 (全画像に反映)」であることをティール見出しで明示する。

    OK 確定時の解釈 (親が判定):
    - 新規入力があれば「追加」(追加した訳は親側で自動的にその言語の主訳になる、#1084)
    - 新規入力が無く、ラジオ選択が現在の主訳と異なれば「主訳変更」
    - どちらも無ければ no-op
    """

    # language を渡すと (候補訳リスト, 現在の主訳) を返す callback の型 (同期取得)。
    CandidatesProvider = Callable[[str], "tuple[list[str], str | None]"]

    # language と結果コールバックを渡すと非同期で候補を取得し、完了時に GUI スレッドで
    # ``on_result(候補訳, 主訳)`` を呼ぶ callback の型 (#1232 非同期取得)。
    AsyncCandidatesProvider = Callable[[str, "Callable[[list[str], str | None], None]"], None]

    # 登録可能な言語の固定候補 (表示ラベル, 保存値)。自由入力は廃止し、保存値を
    # ja / en に正規化する。tagdb の言語キー表記ゆれ ("japanese"/"ja" 混在、
    # #976 PR #991 Codex P1) を新規登録分で構造的に発生させない (Issue #1050)
    LANGUAGE_CHOICES: ClassVar[tuple[tuple[str, str], ...]] = (("日本語", "ja"), ("English", "en"))

    def __init__(
        self,
        canonical: str,
        candidates_provider: TranslationAddDialog.CandidatesProvider | None = None,
        parent: QWidget | None = None,
        async_candidates_provider: TranslationAddDialog.AsyncCandidatesProvider | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("翻訳の管理")
        self._canonical = canonical
        self._candidates_provider = candidates_provider
        # 非同期候補取得 (#1232)。注入されていれば同期 provider より優先し、GUI スレッドを
        # ブロックせずに候補を読み込む。未注入 (テスト等) なら従来の同期取得へフォールバック。
        self._async_candidates_provider = async_candidates_provider
        # 候補取得の世代番号。言語切替や再読込ごとに増やし、古い非同期結果を弾く。
        self._fetch_generation = 0
        # 現在の言語の主訳 (候補再読込のたびに更新)。OK 判定で「変更されたか」に使う。
        self._current_preferred: str | None = None
        # ラジオボタン -> 候補訳文字列。選択中の候補訳を引くために保持する。
        self._radio_group = QButtonGroup(self)
        self._radio_values: dict[QRadioButton, str] = {}

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
        layout.addLayout(form)

        # 候補訳ラジオ一覧 (言語切替のたび作り直す)。
        self._candidates_label = QLabel("主訳を選択:", self)
        layout.addWidget(self._candidates_label)
        self._candidates_container = QWidget(self)
        self._candidates_layout = QVBoxLayout(self._candidates_container)
        self._candidates_layout.setContentsMargins(0, 0, 0, 0)
        self._candidates_layout.setSpacing(2)
        layout.addWidget(self._candidates_container)

        add_form = QFormLayout()
        self._translation_input = QLineEdit(self)
        self._translation_input.setPlaceholderText("新しい訳を追加 (追加すると主訳になります)")
        add_form.addRow("翻訳を追加:", self._translation_input)
        layout.addLayout(add_form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # 言語切替で候補を引き直す。初期言語の候補も描画する。
        self._language_combo.currentIndexChanged.connect(self._reload_candidates)
        self._reload_candidates()

    def _clear_candidates(self) -> None:
        """候補ラジオ一覧 (ローディング表示含む) を破棄する。"""
        for radio in list(self._radio_values):
            self._radio_group.removeButton(radio)
        self._radio_values.clear()
        while self._candidates_layout.count():
            item = self._candidates_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    @Slot()
    def _reload_candidates(self) -> None:
        """選択言語の候補訳を引き直しラジオ一覧を再構築する (#1084 / 非同期化 #1232)。

        非同期 provider があれば「読み込み中…」を出して background 取得を起動し、GUI
        スレッドをブロックしない。完了時に `_on_async_candidates` が一覧を差し替える。
        言語切替のたびに世代を進め、古い取得結果を弾く (single-flight)。
        未注入なら従来どおり同期取得する。
        """
        self._clear_candidates()
        # 読み込み中は主訳未確定。OK 判定 (主訳変更) が stale 値を拾わないよう None に戻す。
        self._current_preferred = None
        self._fetch_generation += 1
        generation = self._fetch_generation
        language = self.language()

        if self._async_candidates_provider is not None:
            self._candidates_layout.addWidget(QLabel("読み込み中…", self._candidates_container))
            self._async_candidates_provider(
                language,
                lambda candidates, current: self._on_async_candidates(generation, candidates, current),
            )
            return

        candidates: list[str] = []
        current: str | None = None
        if self._candidates_provider is not None:
            candidates, current = self._candidates_provider(language)
        self._apply_candidates(candidates, current)

    def _on_async_candidates(self, generation: int, candidates: list[str], current: str | None) -> None:
        """非同期取得の完了ハンドラ。世代が最新のときだけ一覧を差し替える (#1232)。"""
        if generation != self._fetch_generation:
            # 言語切替や再読込で世代が進んでいる = stale な結果なので捨てる。
            return
        self._apply_candidates(candidates, current)

    def _apply_candidates(self, candidates: list[str], current: str | None) -> None:
        """候補訳リストからラジオ一覧を構築する (ローディング表示を置き換える)。"""
        self._clear_candidates()
        self._current_preferred = current

        # 現在の主訳が候補に無くても選択できるよう一覧へ含める (主訳は任意文字列可)。
        display_candidates = list(candidates)
        if current and current not in display_candidates:
            display_candidates.append(current)

        if not display_candidates:
            self._candidates_layout.addWidget(
                QLabel("この言語の翻訳候補はありません", self._candidates_container)
            )
            return

        for value in display_candidates:
            label = f"{value}（主訳）" if value == current else value
            radio = QRadioButton(label, self._candidates_container)
            if value == current:
                radio.setChecked(True)
            self._radio_group.addButton(radio)
            self._radio_values[radio] = value
            self._candidates_layout.addWidget(radio)

    def language(self) -> str:
        """選択された言語の正規化コード ("ja" / "en") を返す。"""
        return str(self._language_combo.currentData())

    def translation(self) -> str:
        """「翻訳を追加」入力欄のテキストを返す (新規追加用、無ければ空文字)。"""
        return self._translation_input.text().strip()

    def selected_candidate(self) -> str | None:
        """ラジオで選択中の候補訳を返す。未選択なら None。"""
        for radio, value in self._radio_values.items():
            if radio.isChecked():
                return value
        return None

    def current_preferred(self) -> str | None:
        """現在の言語の主訳を返す (候補読込時に取得済み)。未設定なら None。"""
        return self._current_preferred


class TranslationFixDialog(QDialog):
    """canonical タグの既存翻訳を上書き修正 / 削除 / 抑制するダイアログ (#1054 / #1237)。

    DB は知らない。言語別の既存翻訳一覧から1行選び、修正テキストを入力して OK 確定で
    (language, translation) を返すか、「この翻訳を削除」/「表示から隠す (抑制)」で選択行の
    (language, translation) を削除/抑制対象として返すだけで、保存は親が dispatch する。
    修正確定は選択行と同一の言語キーで user overlay へ追加され、merged reader が user
    patch を後勝ちで返すため表示上は置換になる (base DB は変更しない)。

    削除できるのは自分 (user overlay) が追加した訳のみ: merged reader は base DB 由来の
    行と user 由来の行を区別せず返すため、このダイアログ自身は行の origin を判別できない。
    base DB 由来の行を削除しようとすると親の dispatch 側で失敗が判明し、案内を出す
    (`SelectedImageDetailsWidget._on_translation_delete`)。base DB 由来の誤訳は削除でなく
    「表示から隠す (抑制)」(tombstone) で対処する。言語の付け替えは、追加した訳なら
    「削除 → 追加」、base DB 由来の訳なら「抑制 → 追加」の2ステップで表現する
    (genai-tag-db-tools#121)。
    """

    def __init__(self, canonical: str, translations: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("翻訳を修正")
        self._canonical = canonical
        # 行順 = translations の挿入順。language() は選択行の言語キーを verbatim で返す
        # ("japanese"/"ja" 等の表記ゆれをそのまま使い、同一キー上書きを保証する)。
        self._languages: list[str] = list(translations.keys())
        # 確定操作種別。既定は「修正」で、削除/抑制ボタン押下時のみ切り替わる。
        self._action: str = "fix"

        layout = QVBoxLayout(self)
        header = QLabel("タグ情報を編集 · 全画像に反映されます", self)
        header.setObjectName("udbHeader")
        header.setStyleSheet(_UDB_HEADER_QSS)
        layout.addWidget(header)
        layout.addWidget(QLabel(f"タグ (canonical): {canonical}", self))

        self._table = QTableWidget(len(self._languages), 2, self)
        self._table.setHorizontalHeaderLabels(["言語", "現在の翻訳"])
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        for row, language in enumerate(self._languages):
            self._table.setItem(row, 0, QTableWidgetItem(language))
            self._table.setItem(row, 1, QTableWidgetItem(translations[language]))
        self._table.itemSelectionChanged.connect(self._on_row_selected)
        layout.addWidget(self._table)

        form = QFormLayout()
        self._translation_input = QLineEdit(self)
        self._translation_input.setPlaceholderText("修正後の翻訳テキスト")
        self._translation_input.textChanged.connect(self._update_ok_enabled)
        form.addRow("修正後:", self._translation_input)
        layout.addLayout(form)

        note = QLabel(
            "修正はタグ情報 (user overlay) への上書き登録で、base DB は変更しません。"
            "「この翻訳を削除」で消せるのは自分で追加した訳のみです (誤登録の取り消し用、#1237)。"
            "元データベース由来の訳は削除できないため、隠したい場合は「表示から隠す (抑制)」を"
            "使ってください (元データベースの値自体は変更しません)。言語の付け替えは、"
            "追加した訳なら削除、元データベース由来の訳なら抑制のうえで、正しい言語で"
            "改めて翻訳を追加してください。",
            self,
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._delete_button = QPushButton("この翻訳を削除", self)
        self._delete_button.setEnabled(False)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        self._buttons.addButton(self._delete_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        self._suppress_button = QPushButton("表示から隠す (抑制)", self)
        self._suppress_button.setEnabled(False)
        self._suppress_button.setToolTip(
            "元データベースは変更せず、この訳を検索/表示結果から隠します (取り消し可能)。"
        )
        self._suppress_button.clicked.connect(self._on_suppress_clicked)
        self._buttons.addButton(self._suppress_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)
        self._update_ok_enabled()

    def _selected_row(self) -> int:
        """選択中の行番号を返す (未選択は -1)。"""
        indexes = self._table.selectionModel().selectedRows()
        return indexes[0].row() if indexes else -1

    def _on_row_selected(self) -> None:
        """行選択で現在の翻訳を修正入力欄へプリフィルする。"""
        row = self._selected_row()
        if row >= 0:
            item = self._table.item(row, 1)
            self._translation_input.setText(item.text() if item is not None else "")
        self._update_ok_enabled()

    def _update_ok_enabled(self) -> None:
        """OK は「行選択済み + 修正テキスト非空」、削除/抑制は「行選択済み」のときだけ有効化する。"""
        row_selected = self._selected_row() >= 0
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(row_selected and bool(self._translation_input.text().strip()))
        self._delete_button.setEnabled(row_selected)
        self._suppress_button.setEnabled(row_selected)

    def _on_delete_clicked(self) -> None:
        """「この翻訳を削除」押下: 操作種別を delete にして選択行の内容で accept する。"""
        if self._selected_row() < 0:
            return
        self._action = "delete"
        self.accept()

    def _on_suppress_clicked(self) -> None:
        """「表示から隠す (抑制)」押下: 操作種別を suppress にして選択行の内容で accept する。"""
        if self._selected_row() < 0:
            return
        self._action = "suppress"
        self.accept()

    def action(self) -> str:
        """確定した操作種別を返す ("fix": 修正/追加、"delete": 削除、"suppress": 抑制)。"""
        return self._action

    def language(self) -> str:
        """選択行の言語キーを verbatim で返す (未選択は空文字)。"""
        row = self._selected_row()
        return self._languages[row] if 0 <= row < len(self._languages) else ""

    def translation(self) -> str:
        """入力された修正後テキストを返す (action="fix" 用)。"""
        return self._translation_input.text().strip()

    def original_translation(self) -> str:
        """選択行の元の翻訳文字列を返す (action="delete"/"suppress" 用、未選択は空文字)。"""
        row = self._selected_row()
        if row < 0:
            return ""
        item = self._table.item(row, 1)
        return item.text() if item is not None else ""


class _TypeBadgeDelegate(QStyledItemDelegate):
    """type combo のカスタム type 行に "ユーザー" バッジを描画する delegate (#1242)。

    item の text (= EditRole/DisplayRole) はそのまま type 名を保つ (currentText() /
    itemText() が汚れず、選択時に combo の lineEdit へバッジ文字列が紛れ込まない)。
    バッジは ``TagTypeEditDialog._CUSTOM_TYPE_ROLE`` のデータを見て描画のみで付与する。
    """

    _BADGE_TEXT = "ユーザー"

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        super().paint(painter, option, index)
        if not bool(index.data(TagTypeEditDialog._CUSTOM_TYPE_ROLE)):
            return
        painter.save()
        metrics = painter.fontMetrics()
        badge_width = metrics.horizontalAdvance(self._BADGE_TEXT) + 8
        badge_rect = QRect(option.rect)
        badge_rect.setLeft(max(badge_rect.left(), badge_rect.right() - badge_width))
        painter.setPen(theme.UDB)
        painter.drawText(
            badge_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            self._BADGE_TEXT,
        )
        painter.restore()


class TagTypeEditDialog(QDialog):
    """canonical タグの種別 (type) を補正するダイアログ (ADR 0083 §2 / #989)。

    DB は知らない。OK 確定で選択 type 名を返すだけで、保存は親が dispatch する。
    refinement の TYPE_MISMATCH 警告があればヒントを表示する。

    combo は検索補完付き (#1242): tagdb 標準 5 種 ("From tagdb") とユーザー登録済み
    カスタム type ("Your types"、親から注入) を 2 グループで提示し、一致する既存 type
    が無い入力のときだけ新規作成ヒントを表示して同義の重複登録を抑止する。
    """

    # 補正候補の type 名 (ADR 0083 §2 / Issue #989)。combo の editable 化 (#1234) 後は
    # 候補サジェストとして機能し、ユーザーは任意の独自 type 名も入力できる。
    TYPE_CHOICES = ("general", "character", "copyright", "meta", "artist")

    # 既知 type を渡せないとき先頭に置く非選択プレースホルダ。誤って general で確定して
    # 既存 type を上書きする no-op 事故を防ぐ (Codex #995 P2)。
    _PLACEHOLDER = "（タグ種別を選択）"

    # グループ見出し (非選択アイテム、#1242)。2 グループ以上あるときのみ挿入する。
    _FROM_TAGDB_HEADER = "── From tagdb ──"
    _CUSTOM_HEADER = "── Your types ──"

    # カスタム type 行を示す item data role (#1242、_TypeBadgeDelegate が描画に使う)。
    _CUSTOM_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(
        self,
        canonical: str,
        type_mismatch_hint: str | None = None,
        current_type: str | None = None,
        custom_type_names: Sequence[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("タグ情報を編集")
        self._canonical = canonical
        # tagdb 標準 (TYPE_CHOICES) と重複 (case-insensitive) しないカスタム type のみ残す。
        self._custom_type_names = self._dedupe_custom_types(custom_type_names or ())

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
        # editable にして danbooru 標準 5 種以外の独自 type 名も入力可能にする (#1234)。
        # backend (update_tags_type_batch) は未知 type を auto-create する。TYPE_CHOICES は
        # サジェスト候補として残す。
        self._type_combo.setEditable(True)
        self._type_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._type_combo.setItemDelegate(_TypeBadgeDelegate(self._type_combo))
        # 現在の type が分かるならそれを初期選択する (無変更確定は同じ type なので無害)。
        # 不明ならプレースホルダを先頭に置き、ユーザーに明示入力を促す。
        current_is_known = bool(current_type) and self._is_known_type(current_type or "")
        self._has_placeholder = not current_type
        if self._has_placeholder:
            self._type_combo.addItem(self._PLACEHOLDER)
        # カスタム type が無ければ見出し無しの単一リスト (#1234 以前と同じ並び) のまま。
        # 2 グループ以上あるときだけ見出しでグルーピングする (#1242)。
        if self._custom_type_names:
            self._add_group_header(self._FROM_TAGDB_HEADER)
        for type_name in self.TYPE_CHOICES:
            self._type_combo.addItem(type_name)
        if self._custom_type_names:
            self._add_group_header(self._CUSTOM_HEADER)
            for type_name in self._custom_type_names:
                self._add_custom_item(type_name)
        if current_type and not current_is_known:
            # 既知 (tagdb 標準 + 注入済みカスタム) に無い既存 type はサジェスト候補に
            # 加えて初期選択する (#1234)。注入漏れのカスタム type もここで拾える。
            self._add_custom_item(current_type)
        if current_type:
            self._type_combo.setCurrentText(current_type)
        form.addRow("タグ種別:", self._type_combo)
        layout.addLayout(form)

        # 検索補完 (#1242): グループ見出しを含まないフラットな候補一覧から contains
        # マッチで補完する (前方一致のみの既定 completer より探しやすくする)。
        completion_source = [*self.TYPE_CHOICES, *self._custom_type_names]
        completer = QCompleter(completion_source, self._type_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._type_combo.setCompleter(completer)

        # 一致する既存 type が無い入力のときだけ表示する新規作成ヒント (#1242)。同音異義の
        # 重複登録 (例: 大小文字違いの別 type) を防ぐため、既存表記への意識づけを兼ねる。
        self._new_type_hint = QLabel("", self)
        self._new_type_hint.setWordWrap(True)
        self._new_type_hint.setStyleSheet(f"color: {theme.UDB};")
        self._new_type_hint.setVisible(False)
        layout.addWidget(self._new_type_hint)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        # editable では選択・打鍵の双方で currentTextChanged が飛ぶ。プレースホルダや
        # 空入力のまま OK 確定して既存 type を空文字で上書きする事故を防ぐため常時接続する
        # (旧実装は has_placeholder 時のみ接続で、editable 化後は空入力を検知できない)。
        self._type_combo.currentTextChanged.connect(self._update_ok_enabled)
        self._type_combo.currentTextChanged.connect(self._update_new_type_hint)
        self._update_ok_enabled(self._type_combo.currentText())
        self._update_new_type_hint(self._type_combo.currentText())

    @staticmethod
    def _dedupe_custom_types(names: Sequence[str]) -> list[str]:
        """TYPE_CHOICES と重複 (case-insensitive) する名前を除いた順序保持 dedupe (#1242)。"""
        known_lower = {t.lower() for t in TagTypeEditDialog.TYPE_CHOICES}
        seen: set[str] = set()
        result: list[str] = []
        for name in names:
            stripped = name.strip()
            if not stripped:
                continue
            lowered = stripped.lower()
            if lowered in known_lower or lowered in seen:
                continue
            seen.add(lowered)
            result.append(stripped)
        return result

    def _is_known_type(self, type_name: str) -> bool:
        """type_name が tagdb 標準または注入済みカスタム type に (case-insensitive) 一致するか。"""
        lowered = type_name.strip().lower()
        if not lowered:
            return False
        return any(lowered == known.lower() for known in (*self.TYPE_CHOICES, *self._custom_type_names))

    def _add_group_header(self, label: str) -> None:
        """選択不可のグループ見出し行を combo に追加する (#1242)。"""
        self._type_combo.addItem(label)
        model = self._type_combo.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(self._type_combo.count() - 1)
            if item is not None:
                item.setFlags(item.flags() & ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable))

    def _add_custom_item(self, type_name: str) -> None:
        """カスタム type 行を combo に追加し、バッジ描画用のデータを付与する (#1242)。"""
        self._type_combo.addItem(type_name)
        model = self._type_combo.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(self._type_combo.count() - 1)
            if item is not None:
                item.setData(True, self._CUSTOM_TYPE_ROLE)

    def _normalized_type(self, text: str) -> str:
        """入力を正規化する。プレースホルダ / 空白のみは空文字扱い。"""
        stripped = text.strip()
        return "" if stripped == self._PLACEHOLDER else stripped

    @Slot(str)
    def _update_ok_enabled(self, text: str) -> None:
        """非空の type 名 (プレースホルダ・空白のみを除く) のときだけ OK を有効化する。"""
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(bool(self._normalized_type(text)))

    @Slot(str)
    def _update_new_type_hint(self, text: str) -> None:
        """一致する既存 type が無い入力のときだけ新規作成ヒントを表示する (#1242)。"""
        normalized = self._normalized_type(text)
        if not normalized or self._is_known_type(normalized):
            self._new_type_hint.setVisible(False)
            self._new_type_hint.setText("")
            return
        self._new_type_hint.setText(f'+ "{normalized}" を新規作成 (ユーザーDBへ)')
        self._new_type_hint.setVisible(True)

    def selected_type(self) -> str:
        """入力された type 名を返す。プレースホルダ / 空白のみは空文字を返す。

        独自 type 名 (TYPE_CHOICES 外) もそのまま返し、backend の auto-create に委ねる (#1234)。
        """
        return self._normalized_type(self._type_combo.currentText())


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
    # タグ文字列を現在 caption へ移し、元タグを除外 soft-reject する要求 (#1240)。
    tag_move_to_caption_requested = Signal(str)  # canonical
    # tagdb userdb 系 (canonical が主キー / 画像 ID 不要)
    refinement_ignored = Signal(str, str, bool)  # canonical, reason_code, this_image_only (#931/#1053)
    translation_add_requested = Signal(str, str, str)  # canonical, language, translation (#989)
    # 主訳 (優先翻訳) 変更 (canonical, language, translation) (#1084)。既存訳から主訳を切替える。
    translation_preferred_requested = Signal(str, str, str)
    # 誤登録翻訳の削除 (canonical, language, translation) (#1237)。破壊的操作なので親側で
    # 実行前に確認ダイアログを出す想定 (TranslationFixDialog 側では確認済み)。
    translation_delete_requested = Signal(str, str, str)
    # base DB 由来の誤訳を merged 表示から隠す抑制 (tombstone) 要求 (canonical, language,
    # translation) (#1237)。削除と異なり base DB 自体は変更しない。確認は削除と同様
    # TranslationFixDialog 側で確認済み。
    translation_suppress_requested = Signal(str, str, str)
    tag_metadata_edit_requested = Signal(str, str)  # canonical, type (#989)
    # 翻訳/使用頻度/type の再取得要求 (#1210 案A)。翻訳表示 (言語バー) に対する操作
    # なので言語バー右端のアイコンボタンから emit する。DB 非依存を保つため処理は
    # 親 (SelectedImageDetailsWidget.refresh_tag_metadata) に委ねる。
    translation_refresh_requested = Signal()

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
        # 翻訳メタデータが background worker (#1046) で解決中か。読み込み中に「翻訳を修正」
        # を開くと空の _translations を「翻訳なし」と誤認して追加ダイアログへ落ち、legacy
        # 言語キー ("japanese") の誤訳を "ja" で上書きできない (PR #1086 Codex P2)。
        self._tag_metadata_pending: bool = False
        # 翻訳管理ダイアログの候補訳 provider (#1084)。language を渡すと
        # (候補訳リスト, 現在の主訳) を返す callback。DB 非依存を保つため親から注入する。
        self._translation_candidates_provider: Callable[[str, str], tuple[list[str], str | None]] | None = (
            None
        )
        # タグ種別編集ダイアログへ渡すカスタム type 一覧 provider (#1242)。呼び出す毎に
        # user DB 登録済みカスタム type 名一覧を返す callback。DB 非依存を保つため親から
        # 注入する。未注入 (None) ならダイアログは tagdb 標準 5 種のみで開く。
        self._type_choices_provider: Callable[[], list[str]] | None = None
        # 翻訳候補の非同期 provider (#1232)。(canonical, language, on_result) を渡すと
        # background で候補を取得し、完了時に GUI スレッドで on_result(候補, 主訳) を呼ぶ。
        # 注入されていれば同期 provider より優先し、ポップアップ表示のブロックを避ける。
        self._translation_candidates_async_provider: (
            Callable[[str, str, Callable[[list[str], str | None], None]], None] | None
        ) = None

        # 使用頻度 第2軸 (metric_source, ADR 0083 §5 / #990)。表示言語とは独立した軸。
        # 親が bulk 取得した {tag_id: {format_name: count}} を set_usage_counts で受け、
        # canonical → {format_name: count} へ展開して chip に補助表示する (読み取り専用)。
        self._usage_counts: dict[int, dict[str, int]] = {}
        self._counts_by_canonical: dict[str, dict[str, int]] = {}
        self._metric_source: str = ""  # 空文字 = なし (count 非表示)

        # 編集モード (soft-reject 導線。既定 read-only)
        self._tag_edit_enabled: bool = False

        # 「種別で分ける」トグル状態 (Issue #1241)。widget ローカルで非永続。
        # 2 種別以上存在するときのみチェックボックスを有効化する (_render_tag_chips)。
        self._group_by_type: bool = False

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
        # 現在の chip 群が refinement (⚠) マークを持つか (#1221)。chip 再生成 (無印) と
        # 空 refinements の組み合わせで重複 no-op 適用をスキップする判定に使う。
        self._chips_carry_refinements: bool = False

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
        self._lang_layout = QHBoxLayout(self._lang_bar)
        self._lang_layout.setContentsMargins(0, 0, 0, 2)
        self._lang_label = QLabel("言語:", self._lang_bar)
        self._lang_layout.addWidget(self._lang_label)
        # スクロール領域内のためホイール通過で値が変わらない DS 部品を使う (#1051)
        self._lang_combo = DsNoScrollComboBox(self._lang_bar)
        self._lang_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # コンボは layout stretch 1 で full-width に伸ばしボタンを右端へ押す。コンボ/ラベル
        # 非表示 (翻訳言語 0 件) 時は下の spacer stretch を 1 へ上げてボタンを右端に保つ
        # (_update_lang_bar_visibility が制御、#1210)。spacer は index 2。
        self._lang_layout.addWidget(self._lang_combo, 1)
        self._lang_layout.addStretch(0)
        # 翻訳再取得 (#1210 案A): 翻訳表示に対する操作なので言語バー右端に近接配置する。
        # 有効化は親が set_translation_refresh_enabled で行う (DB 非依存を維持)。
        self._translation_refresh_button = QToolButton(self._lang_bar)
        self._translation_refresh_button.setText("🔄")
        # QToolButton は既定でアイコンのみ表示。グリフ文字をラベルとして出すため TextOnly 必須
        # (未指定だと一部 Qt スタイルで空ボタンに見える、Codex #1224 P2)。
        self._translation_refresh_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._translation_refresh_button.setToolTip(
            "表示中画像のタグ翻訳/使用頻度/type を tag DB から再取得します (CLI で追加した翻訳の反映用)"
        )
        self._translation_refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._translation_refresh_button.setStyleSheet(ACTION_TOOL_BUTTON_QSS)
        self._translation_refresh_button.setEnabled(False)
        self._translation_refresh_button.setVisible(False)
        self._translation_refresh_button.clicked.connect(self.translation_refresh_requested)
        self._lang_layout.addWidget(self._translation_refresh_button)
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

        # 「種別で分ける」トグル (#1241)。2 種別以上存在する画像でのみ有効化する
        # (_render_tag_chips が都度再計算)。ON でヘッダ付きセクション分割、OFF で
        # 現状同様のフラット表示 (type 順ソートは #1056 のまま維持)。
        self._group_by_type_checkbox = QCheckBox("種別で分ける", self)
        self._group_by_type_checkbox.setToolTip(
            "タグ chip を種別 (キャラクター/版権/絵師/メタ/一般) ごとにグループ表示します。"
            "種別が1つしかない画像では無効化されます。"
        )
        self._group_by_type_checkbox.setEnabled(False)
        self._group_by_type_checkbox.toggled.connect(self._on_group_by_type_toggled)
        root.addWidget(self._group_by_type_checkbox)

        # チップ表示コンテナ。高さ上限付きスクロール箱に収める (#835)。FlowLayout の
        # minimumSizeHint は「最小幅で全チップ縦積み」の過大値を報告し、放置すると親の
        # 高さを膨張させてスコアカード下に異常な余白 + 不要スクロールを生む。
        # コンテナ自体は QVBoxLayout (セクション列) を持ち、フラット表示時は単一の
        # FlowLayout セクションを、種別分割時はヘッダ付き複数セクションを積む
        # (#1241: chip 再構築のたびに _render_flat_chips / _render_grouped_chips が
        # セクションを作り直す。既存の使い捨て再構築方針 (_clear_chip_layout 等) と統一)。
        self._tags_chip_container = QWidget(self)
        self._tags_chip_sections_layout = QVBoxLayout(self._tags_chip_container)
        self._tags_chip_sections_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_chip_sections_layout.setSpacing(6)
        # 縦は Preferred (ShrinkFlag あり) にする (#1025)。Minimum だと FlowLayout の
        # sizeHint (「sizeHint 幅で全チップ縦積み」した過大値、例: 40チップで996px) が
        # container の最小高さとして固定され、widgetResizable な QScrollArea が実幅の
        # 必要高さ (heightForWidth) まで縮められず、チップ下に空白スクロール領域が残る。
        self._tags_chip_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        # フラット表示時の FlowLayout (直近に生成したもの)。テスト/後方互換のため保持する。
        # 実体は _render_flat_chips / _render_grouped_chips が再構築のたびに差し替える。
        self._tags_chip_layout: FlowLayout = self._new_chip_flow_section()
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
                非空ならセッション内キャッシュへ merge、空/None ならキャッシュ保持
                (#1083: 2段階描画の phase 1 で metric バーを消さない)。
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
        # 翻訳も usage counts (#1083) と同じく tag DB 由来の画像非依存データ
        # ({tag_id: {language: text}}) なので、画像切替で破棄せずセッション内キャッシュへ
        # merge する (#1191)。2段階描画の phase 1 (即時描画) は空を渡してくるが、ここで
        # クリアすると metadata worker 完了までの数秒間、既訳タグまで「英語 + 点線
        # (翻訳なし)」へ巻き戻り、翻訳の反映失敗と誤認される (#1172 の偽陽性の原因)。
        # 空は「未解決」とみなしキャッシュを保持し、既出タグは選択直後から訳を表示する。
        if translations:
            self._merge_translations_for_current_tags(translations)
        self._available_languages = list(available_languages) if available_languages else []
        # usage counts は tag DB 由来の画像非依存データ ({tag_id: {format: count}}) なので、
        # 画像切替で破棄せずセッション内キャッシュへ merge する (#1083)。2段階描画の
        # phase 1 (即時描画) は空 dict を渡してくるが、ここでクリアすると metadata worker
        # 完了までの数秒間 metric バー (頻度ドロップダウン) が消える。空は「未解決」と
        # みなしキャッシュを保持し、既出タグは選択直後から count を表示できるようにする。
        # 非空 map は表示中タグ分の正とみなす (map に無い表示中 tag_id は退避、Codex P2)。
        if usage_counts:
            self._merge_usage_counts_for_current_tags(usage_counts)
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

    def set_translation_candidates_provider(
        self, provider: Callable[[str, str], tuple[list[str], str | None]] | None
    ) -> None:
        """翻訳管理ダイアログの候補訳 provider を注入する (#1084)。

        provider は ``(canonical, language)`` を受け、``(候補訳リスト, 現在の主訳)`` を返す。
        DB 非依存を保つため親 (`SelectedImageDetailsWidget`) が TagManagementService の
        候補列挙メソッドを渡す。未注入 (None) のときダイアログは候補なしで開く。

        Args:
            provider: 候補訳を返す callback。None で解除。
        """
        self._translation_candidates_provider = provider

    def set_type_choices_provider(self, provider: Callable[[], list[str]] | None) -> None:
        """タグ種別編集ダイアログへ渡すカスタム type 一覧 provider を注入する (#1242)。

        provider は引数なしで呼ばれ、user DB 登録済みのカスタム type 名一覧を返す。
        DB 非依存を保つため親 (`SelectedImageDetailsWidget`) が TagManagementService の
        type 列挙メソッドを渡す。未注入 (None) のときダイアログは tagdb 標準 5 種
        ("From tagdb") のみで開き、カスタム type ("Your types") のグループは表示されない。

        Args:
            provider: カスタム type 名一覧を返す callback。None で解除。
        """
        self._type_choices_provider = provider

    def set_translation_candidates_async_provider(
        self,
        provider: Callable[[str, str, Callable[[list[str], str | None], None]], None] | None,
    ) -> None:
        """翻訳候補の非同期 provider を注入する (#1232)。

        provider は ``(canonical, language, on_result)`` を受け、background で候補を取得して
        完了時に GUI スレッドで ``on_result(候補訳リスト, 現在の主訳)`` を呼ぶ。注入されて
        いれば翻訳管理ダイアログは同期 provider を使わず、候補取得でメインスレッドを
        ブロックしない (ポップアップ表示が固まる #1232 を解消)。親
        (`SelectedImageDetailsWidget`) が WorkerManager 経由の起動関数を渡す。

        Args:
            provider: 非同期候補取得の起動 callback。None で解除。
        """
        self._translation_candidates_async_provider = provider

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

    def _update_lang_bar_visibility(self) -> None:
        """言語バー内の各要素と bar 自体の可視性を state から再計算する (#1210)。

        言語コンボは翻訳言語が 1 つ以上ある (english + 1) ときだけ表示する。翻訳再取得
        ボタンは画像ロード後 (enabled) に表示する。バーは「言語あり or 再取得可能」なら表示。

        これにより、未翻訳画像 (言語 0 件で言語コンボ非表示) でも再取得ボタンが残り、
        CLI で最初の翻訳を追加した直後に画像再選択なしで取得できる (Codex #1224 P2)。
        コンボ非表示時は spacer stretch を上げてボタンを右端に保つ。
        """
        has_languages = self._lang_combo.count() > 1
        refresh_available = self._translation_refresh_button.isEnabled()
        self._lang_label.setVisible(has_languages)
        self._lang_combo.setVisible(has_languages)
        self._translation_refresh_button.setVisible(refresh_available)
        # spacer (index 2) はコンボ非表示時のみ伸ばす (可視時はコンボが full-width で押す)。
        self._lang_layout.setStretch(2, 0 if has_languages else 1)
        self._lang_bar.setVisible(has_languages or refresh_available)

    def initialize_language_selector(self, available_languages: list[str]) -> None:
        """言語コンボボックスを初期化する。

        Args:
            available_languages: 利用可能な言語リスト。空の場合はコンボボックスを非表示にする。
                (翻訳再取得ボタンが有効なら言語バー自体は残る、#1210)
        """
        if not available_languages:
            # 直前にリーダーがあり言語が入っていた場合、clear しないと combo に古い言語が
            # 残り、_update_lang_bar_visibility が count()>1 で誤って表示継続する
            # (set_merged_reader(None) / 言語なしリーダー再注入の回帰、Codex #1224 P2)。
            self._lang_combo.blockSignals(True)
            self._lang_combo.clear()
            self._lang_combo.blockSignals(False)
            self._update_lang_bar_visibility()
            return

        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItem("english")  # 常に先頭 (原文)
        for lang in dedupe_languages_by_family(available_languages):
            # ja/japanese の族重複を畳み、en/english 族は sentinel と重複するため
            # 丸ごと除外する (#1235: alias が両表記で二重に出るのを防ぐ)。
            if canonical_language_key(lang) != "en":
                self._lang_combo.addItem(lang)
        self._lang_combo.blockSignals(False)
        self._update_lang_bar_visibility()

    def update_language_selector(
        self,
        available_languages: list[str],
        *,
        prefer: str | None = None,
        force_prefer: bool = False,
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
            force_prefer: True なら現在の表示言語に関わらず prefer へ切り替える
                (Codex P2: 主訳変更は非英語表示中でも編集した言語を見せないと
                変更が可視化されない)。
        """
        current = self._current_language()
        target = prefer if (prefer and (force_prefer or current == "english")) else current
        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItem("english")  # 常に先頭 (原文)
        for lang in dedupe_languages_by_family(available_languages):
            # ja/japanese の族重複を畳み、en/english 族は sentinel と重複するため
            # 丸ごと除外する (#1235: alias が両表記で二重に出るのを防ぐ)。
            if canonical_language_key(lang) != "en":
                self._lang_combo.addItem(lang)
        index = self._lang_combo.findText(target)
        if index < 0:
            # 正規化キー ("ja") と legacy キー ("japanese") の混在に対応 (Codex P2):
            # 保存は ja/en 正規化だが、既存 DB 由来の候補は "japanese" だけのことがある。
            # エイリアスで探し、主訳変更直後の切替が「何も起きない」ように見えるのを防ぐ。
            for alias in language_alias_keys(target):
                index = self._lang_combo.findText(alias)
                if index >= 0:
                    break
        if index >= 0:
            self._lang_combo.setCurrentIndex(index)
        self._lang_combo.blockSignals(False)
        self._update_lang_bar_visibility()

    def set_tag_edit_enabled(self, enabled: bool) -> None:
        """タグ soft-reject 編集モードを切り替える。

        Args:
            enabled: True で ✕ ボタン / 手動追加入力 / クリック無効化を有効にする。
        """
        self._tag_edit_enabled = enabled
        self._tag_add_input.setVisible(enabled)
        self._refresh_tags_for_language(self._current_language())

    def set_translation_refresh_enabled(self, enabled: bool) -> None:
        """言語バー右端の翻訳再取得ボタンの有効/無効を切り替える (#1210 案A)。

        親 (画像詳細側) が画像ロード完了時に有効化する。ボタン押下は
        ``translation_refresh_requested`` Signal で親へ委譲される。

        Args:
            enabled: True で翻訳再取得ボタンをクリック可能にする。
        """
        self._translation_refresh_button.setEnabled(enabled)
        # 言語 0 件の画像でもボタンを可視に保つ (Codex #1224 P2): バーの可視性を再計算する。
        self._update_lang_bar_visibility()

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

    def set_tag_metadata_pending(self, pending: bool) -> None:
        """翻訳メタデータの background 解決中フラグを設定する (#1054)。

        親が TagMetadataWorker (#1046) を起動するとき True にする。`apply_tag_metadata`
        の反映で自動的に False へ戻る。読み込み中は「翻訳を修正」が空の `_translations`
        を「翻訳なし」と誤認して追加ダイアログへフォールバックしないようにする。

        Args:
            pending: True = 解決中 (worker 起動済みで未反映)。
        """
        if pending == self._tag_metadata_pending:
            return
        self._tag_metadata_pending = pending
        # 「解決中」と「翻訳なし」を chip / 脚注で区別するため再描画する (#1191)。
        # True: phase 1 描画直後に親が呼び、未訳 chip を「解決中」表示へ切り替える。
        # False: 失敗/キャンセル終端 (apply_tag_metadata を経ない) で「翻訳なし」確定表示へ戻す。
        self._refresh_tags_for_language(self._current_language())

    def apply_tag_metadata(
        self,
        translations: dict[int, dict[str, str]],
        usage_counts: dict[int, dict[str, int]],
        tag_types: dict[str, str],
    ) -> None:
        """worker で解決した翻訳/使用頻度/type をまとめて反映する (#1046)。

        2段階描画の後段: 原文のみの即時表示に対し、background で解決した
        メタデータを 1 回の再描画で反映する (#983 の多重再描画の罠を避ける)。
        言語選択・✕/無効化などの表示状態は保持される。

        usage counts は画像非依存のセッション内キャッシュへ merge する (#1083)。
        置換にすると別画像で貯めた既出タグの count が消え、次の画像切替の phase 1
        で metric バーが再び空白になる。ただし表示中タグの tag_id は今回の解決結果が
        正であり、結果に無い id は「count なし」が確定しているためキャッシュから
        退避する (セッション中の usage 行削除や tag DB 差し替えで stale な count を
        表示し続けない、Codex P2)。翻訳も同じ理由で merge する (#1191)。
        """
        self._merge_translations_for_current_tags(translations)
        self._merge_usage_counts_for_current_tags(usage_counts)
        self._tag_types = dict(tag_types)
        # メタデータが届いたので「翻訳を修正」の追加フォールバックを解禁する (#1054)
        self._tag_metadata_pending = False
        # type が届いたのでグループソートを適用し直す (#1056)
        self._tags = self._sort_tags_by_type(self._tags)
        self._rebuild_counts_by_canonical()
        self._refresh_metric_selector()
        self._populate_table(self._all_tag_rows)
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
        """表示データと表示状態をクリアする。

        usage counts のセッション内キャッシュ (#1083) は画像非依存の参照データなので
        破棄しない (タグが無いので metric バーは自然に隠れる)。
        """
        self._tags = []
        self._translations = {}
        self._disabled_display = set()
        self._hidden = set()
        self._rejected_tags = []
        self._last_refinements = {}
        self._last_candidate_counts = {}
        self._counts_by_canonical = {}
        self._selected_canonicals = set()
        self._refresh_metric_selector()
        self.tableWidgetTags.setRowCount(0)
        self._tags_compact_label.setText("-")
        self._render_tag_chips([], is_translated=False)
        self._adjust_tags_chip_height()

    # ─── 言語・描画 ─────────────────────────────────────────────────────

    def _current_language(self) -> str:
        """現在の表示言語を返す (言語コンボが空/未表示なら原文 english)。

        言語 0 件でも再取得ボタンのため言語バーは表示され得る (#1210)。その場合
        コンボは空なので、bar の表示状態ではなくコンボ内容で判定する (Codex #1224 P2)。
        コンボが空だと _current_language が "" を返し、翻訳追加後の
        update_language_selector(prefer=...) が english 判定にならず表示切替が効かない。
        """
        text = self._lang_combo.currentText()
        return text if text else "english"

    @Slot(str)
    def _on_language_changed(self, language: str) -> None:
        """言語コンボボックス変更時にタグ表示を更新する。"""
        self._refresh_tags_for_language(language)

    # ─── 使用頻度 第2軸 (metric_source, #990) ──────────────────────────

    def _merge_translations_for_current_tags(self, translations: dict[int, dict[str, str]]) -> None:
        """表示中タグ分を正として翻訳をセッション内キャッシュへ merge する (#1191)。

        表示中タグの tag_id は与えられた解決結果が正であり、結果に無い id は
        「翻訳なし」が確定しているため merge 前にキャッシュから退避する
        (セッション中の翻訳削除や tag DB 差し替えで stale な訳を表示し続けない)。
        表示外の tag_id (他画像で貯めた分) は保持し、再選択時に選択直後から訳を出す。

        Args:
            translations: 表示中タグ集合に対する解決結果 ``{tag_id: {language: text}}``。
        """
        current_tag_ids = {
            tag_id
            for tag_dict in self._tags
            if isinstance(tag_dict, dict) and isinstance(tag_id := tag_dict.get("tag_id"), int)
        }
        for tag_id in current_tag_ids - translations.keys():
            self._translations.pop(tag_id, None)
        self._translations.update({tag_id: dict(langs) for tag_id, langs in translations.items()})

    def _merge_usage_counts_for_current_tags(self, usage_counts: dict[int, dict[str, int]]) -> None:
        """表示中タグ分を正として usage counts をセッション内キャッシュへ merge する (#1083)。

        表示中タグの tag_id は与えられた解決結果が正であり、結果に無い id は
        「count なし」が確定しているため merge 前にキャッシュから退避する
        (セッション中の usage 行削除や tag DB 差し替えで stale な count を
        表示し続けない、Codex P2)。表示外の tag_id (他画像で貯めた分) は保持する。

        Args:
            usage_counts: 表示中タグ集合に対する解決結果 ``{tag_id: {format: count}}``。
        """
        current_tag_ids = {
            tag_id
            for tag_dict in self._tags
            if isinstance(tag_dict, dict) and isinstance(tag_id := tag_dict.get("tag_id"), int)
        }
        for tag_id in current_tag_ids - usage_counts.keys():
            self._usage_counts.pop(tag_id, None)
        self._usage_counts.update(usage_counts)

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

    # type 別グループの表示順 (#1056)。モジュール定数 _TYPE_ORDER (#1233 / #1241 の
    # デザイン確定 SSoT: character→copyright→artist→meta→general) から生成する。
    # 未知 type / type 不明は末尾グループ (ユーザー確認済み)
    _TYPE_GROUP_ORDER: ClassVar[dict[str, int]] = {name: i for i, name in enumerate(_TYPE_ORDER)}
    _UNKNOWN_TYPE_GROUP = len(_TYPE_ORDER)

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
        破線スタイルで示す。「種別で分ける」トグル (#1241) が ON かつ 2 種別以上あれば
        ヘッダ付きセクションへ分割し、それ以外は現状同様のフラット表示にする。

        Args:
            chip_items: (表示名, 原文, 翻訳ありか) のタプルリスト (アクティブタグ)。
            is_translated: 非英語言語で表示中なら True。脚注と翻訳欠落の点線マークを切り替える。
        """
        self._clear_chip_layout()
        self._tag_chips = []
        # 旧 chip を破棄した。以後 _add_chip で生成される chip は無印なので、
        # refinement 保持フラグをリセットする (#1221)。末尾の再反映で必要なら再度立つ。
        self._chips_carry_refinements = False

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
            # _clear_chip_layout() が旧セクション (FlowLayout 付きコンテナ) を丸ごと
            # deleteLater 済みのため、既存の self._tags_chip_layout は使い回せない
            # (dangling 参照)。新規セクションを作ってから追加する。
            flow = self._new_chip_flow_section()
            self._tags_chip_layout = flow
            placeholder = QLabel("-")
            placeholder.setStyleSheet(f"color: {theme.INK_FAINT};")
            flow.addWidget(placeholder)
            self._tags_translation_note.setVisible(False)
            self._group_by_type_checkbox.setEnabled(False)
            self._update_selection_bar()
            return

        # 描画対象を統一形式 (表示名, 原文, 翻訳ありか, 無効化) へまとめる。
        render_items: list[tuple[str, str, bool, bool]] = [
            (
                display,
                original,
                has_tr,
                original in self._disabled_display or original in self._rejected_tags,
            )
            for display, original, has_tr in visible_items
        ]
        render_items.extend((original, original, True, True) for original in rejected_only)

        # 「種別で分ける」トグル (#1241): 2 種別以上あるときだけ有効化する。
        distinct_types = {self._tag_types.get(original, "") for _d, original, _h, _dis in render_items}
        self._group_by_type_checkbox.setEnabled(len(distinct_types) > 1)

        if self._group_by_type and len(distinct_types) > 1:
            self._render_grouped_chips(render_items, is_translated=is_translated)
        else:
            self._render_flat_chips(render_items, is_translated=is_translated)

        if is_translated:
            # 解決中は脚注でも状態を明示する (#1191: 過渡状態を「翻訳なし」と誤認させない)
            if self._tag_metadata_pending:
                self._tags_translation_note.setText(
                    "翻訳解決中… · 表示のみ翻訳 · 保存値は danbooru canonical 固定"
                )
            else:
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

    def _on_group_by_type_toggled(self, checked: bool) -> None:
        """「種別で分ける」トグル切替: chip 表示をグループ分割⇄フラットで再描画する (#1241)。"""
        self._group_by_type = checked
        self._refresh_tags_for_language(self._current_language())

    def _render_flat_chips(
        self, render_items: list[tuple[str, str, bool, bool]], *, is_translated: bool
    ) -> None:
        """種別分割なしの現状互換フラット表示 (#1241 トグル OFF / 単一種別時)。"""
        flow = self._new_chip_flow_section()
        self._tags_chip_layout = flow
        for display, original, has_tr, disabled in render_items:
            self._add_chip(
                display,
                original,
                has_translation=has_tr,
                is_translated=is_translated,
                disabled=disabled,
                target_layout=flow,
            )

    def _render_grouped_chips(
        self, render_items: list[tuple[str, str, bool, bool]], *, is_translated: bool
    ) -> None:
        """種別ごとにヘッダ + FlowLayout のセクションへ分割する (#1241)。

        アクティブタグ分は #1056 ``_sort_tags_by_type`` 済みだが、soft-rejected 分は
        末尾に DB 行順で追記され type ソート対象外。隣接判定だけで区切ると同一 type が
        非連続になり、重複ヘッダ + 総数を各セクションに二重表示する不具合が出る
        (Codex P1)。ここで type グループ順に stable-sort し、active/rejected を問わず
        全同一 type を連続させてから変化点で区切る。
        """
        render_items = sorted(
            render_items,
            key=lambda item: self._TYPE_GROUP_ORDER.get(
                self._tag_types.get(item[1], ""), self._UNKNOWN_TYPE_GROUP
            ),
        )

        counts: dict[str, int] = {}
        for _display, original, _has_tr, _disabled in render_items:
            type_name = self._tag_types.get(original, "")
            counts[type_name] = counts.get(type_name, 0) + 1

        # render_items は呼び出し元 (_render_tag_chips) で非空を保証済み。先頭の type で
        # 最初のセクション (ヘッダ→FlowLayout の順) を開く。
        current_type = self._tag_types.get(render_items[0][1], "")
        self._add_type_section_header(current_type, counts[current_type])
        flow = self._new_chip_flow_section()
        for display, original, has_tr, disabled in render_items:
            type_name = self._tag_types.get(original, "")
            if type_name != current_type:
                current_type = type_name
                self._add_type_section_header(type_name, counts[type_name])
                flow = self._new_chip_flow_section()
            self._tags_chip_layout = flow
            self._add_chip(
                display,
                original,
                has_translation=has_tr,
                is_translated=is_translated,
                disabled=disabled,
                target_layout=flow,
            )

    def _new_chip_flow_section(self) -> FlowLayout:
        """chip 用の FlowLayout セクション (専用コンテナ付き) を新規生成して追加する。

        Returns:
            新規セクションの FlowLayout。呼び出し側が chip を addWidget していく。
        """
        container = QWidget(self._tags_chip_container)
        flow = FlowLayout(container, spacing=4)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._tags_chip_sections_layout.addWidget(container)
        return flow

    def _add_type_section_header(self, type_name: str, count: int) -> None:
        """種別グループヘッダ (グリフ + 日本語ラベル + 件数) を追加する (#1241)。"""
        label = _TYPE_LABELS_JA.get(type_name, "不明")
        glyph = _TYPE_GLYPHS.get(type_name, "")
        text = f"{glyph} {label} ({count})" if glyph else f"{label} ({count})"
        header = QLabel(text, self._tags_chip_container)
        header.setStyleSheet(theme.tag_type_badge_qss(type_name))
        self._tags_chip_sections_layout.addWidget(header)

    def _add_chip(
        self,
        display: str,
        original: str,
        *,
        has_translation: bool,
        is_translated: bool,
        disabled: bool,
        target_layout: FlowLayout,
    ) -> None:
        """1 タグ分の chip (編集モードでは ✕ 付き) を生成して配置する。"""
        # 使用頻度 metric が選択されていれば count を表示名へ付与する (#990)。
        # canonical (original) は変えずコピー結果へ影響させない。
        display = f"{display}{self._count_suffix(original)}"
        type_name = self._tag_types.get(original)
        # 種別グリフを表示名に前置する (#1241)。general/不明は無印 (ノイズを増やさない)。
        glyph = _TYPE_GLYPHS.get(type_name, "") if type_name else ""
        chip = SelectableTagChip(f"{glyph} {display}" if glyph else display, original)
        chip.set_type_indicator(type_name)
        if is_translated and not has_translation and self._tag_metadata_pending:
            # 翻訳解決中 (#1191): 「翻訳なし」の点線と区別し、反映失敗との誤認を防ぐ。
            chip.base_qss = theme.chip_qss("accent")
            chip.setToolTip(f"{original} — 翻訳解決中…")
        elif is_translated and not has_translation:
            chip.untranslated = True
            chip.base_qss = theme.tag_chip_untranslated_qss()
            chip.setToolTip(f"{original} — 翻訳なし · 右クリックで翻訳を追加")
        else:
            # type 別の色分け (#1233)。既知種別 (character/copyright/artist/meta) のみ
            # 専用パレットで recolor し、general / 不明は現行の accent を据え置く。
            chip.base_qss = theme.tag_type_chip_qss(type_name) or theme.chip_qss("accent")
            if is_translated and display != original:
                # 翻訳済み chip にも右クリックの導線を明示する (#1223 / #1225): 主訳選択
                # (翻訳管理ダイアログ) の入口が右クリックしかなく視覚的手がかりが無かった。
                chip.setToolTip(f"{original} → {display} · 右クリックで翻訳を選択/編集")
        if type_name and type_name != "general" and type_name in _TYPE_LABELS_JA:
            # 種別ラベルをツールチップへ追記する (#1241)。翻訳系ツールチップと共存させる。
            type_label = _TYPE_LABELS_JA[type_name]
            existing_tip = chip.toolTip()
            chip.setToolTip(
                f"{existing_tip}\n種別: {type_label}" if existing_tip else f"種別: {type_label}"
            )
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
        chip.tag_replace_menu_requested.connect(self._open_tag_replace_dialog)
        chip.tag_move_to_caption_requested.connect(self.tag_move_to_caption_requested)
        # タグ情報メニュー (#989): chip 右クリック → 親がダイアログを開く。
        chip.translation_add_menu_requested.connect(self._open_translation_dialog)
        chip.translation_fix_menu_requested.connect(self._open_translation_fix_dialog)
        chip.type_edit_menu_requested.connect(self._open_type_edit_dialog)
        # 使用頻度を見る (#997): read-only、TagPanelWidget 内で完結する。
        chip.usage_counts_menu_requested.connect(self._open_usage_counts_dialog)
        self._tag_chips.append(chip)
        target_layout.addWidget(self._wrap_editable_chip(chip, original))

    def _clear_chip_layout(self) -> None:
        """chip セクション群 (ヘッダ + FlowLayout コンテナ) を破棄する。"""
        while self._tags_chip_sections_layout.count():
            child = self._tags_chip_sections_layout.takeAt(0)
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

    @Slot(str)
    def _open_tag_replace_dialog(self, canonical: str) -> None:
        """任意タグへの置換先を入力し、既存の置換 Signal へ流す (#1240)。"""
        to_tag, ok = QInputDialog.getText(
            self,
            "別のタグに置換",
            "置換先タグ:",
            text=canonical,
        )
        if not ok:
            return
        replacement = to_tag.strip()
        if not replacement or replacement == canonical:
            return
        self.tag_replace_requested.emit(canonical, replacement)

    # ─── タグ情報メニュー (#989、tagdb userdb 系) ───────────────────────

    @Slot(str)
    def _open_translation_dialog(self, canonical: str) -> None:
        """翻訳管理ダイアログを開き、確定内容に応じて Signal を出す (#989 / #1084)。

        DB は知らない。候補訳は provider (親注入) から引き、確定結果を親へ dispatch する:

        - 新規入力があれば ``translation_add_requested`` (追加、親側で自動的に主訳化)。
        - 新規入力が無く、ラジオ選択が現在の主訳と異なれば ``translation_preferred_requested``
          (主訳変更)。
        - どちらでもなければ何も出さない (no-op)。

        Args:
            canonical: 翻訳を管理する canonical タグ文字列。
        """
        provider = self._dialog_candidates_provider(canonical)
        async_provider = self._dialog_async_candidates_provider(canonical)
        dialog = TranslationAddDialog(canonical, provider, self, async_candidates_provider=async_provider)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        language = dialog.language()
        if not language:
            return
        new_translation = dialog.translation()
        if new_translation:
            # 新規追加。追加した訳はその言語の主訳になる (親の add_translation が担保、#1084)。
            self.translation_add_requested.emit(canonical, language, new_translation)
            return
        selected = dialog.selected_candidate()
        current = dialog.current_preferred()
        if selected and selected != current:
            self.translation_preferred_requested.emit(canonical, language, selected)
        else:
            logger.debug(f"翻訳管理: 変更なし (no-op): canonical='{canonical}'")

    def _dialog_candidates_provider(
        self, canonical: str
    ) -> Callable[[str], tuple[list[str], str | None]] | None:
        """翻訳管理ダイアログへ渡す language→候補訳 の callback を作る (#1084)。

        親から注入された ``(canonical, language)`` provider を canonical で束ね、
        ダイアログが要求する ``language`` のみの callback にする。未注入なら None。
        """
        provider = self._translation_candidates_provider
        if provider is None:
            return None

        def bound(language: str) -> tuple[list[str], str | None]:
            return provider(canonical, language)

        return bound

    def _dialog_async_candidates_provider(
        self, canonical: str
    ) -> Callable[[str, Callable[[list[str], str | None], None]], None] | None:
        """翻訳管理ダイアログへ渡す非同期候補取得 callback を作る (#1232)。

        親注入の ``(canonical, language, on_result)`` provider を canonical で束ね、
        ダイアログが要求する ``(language, on_result)`` の callback にする。未注入なら None
        (ダイアログは同期 provider にフォールバック)。
        """
        provider = self._translation_candidates_async_provider
        if provider is None:
            return None

        def bound(language: str, on_result: Callable[[list[str], str | None], None]) -> None:
            provider(canonical, language, on_result)

        return bound

    @Slot(str)
    def _open_translation_fix_dialog(self, canonical: str) -> None:
        """翻訳修正ダイアログを開き、確定で translation_add_requested /
        translation_delete_requested / translation_suppress_requested を出す (#1054 / #1237)。

        修正は選択行と同一の言語キーで user overlay へ登録する。merged reader は user patch
        を後勝ちで返し、表示 dict が language ごとに上書きするため実質置換になる (dispatch
        経路は翻訳追加と共通)。既存翻訳が無いタグは修正対象が無いため、翻訳追加ダイアログへ
        フォールバックする。「この翻訳を削除」/「表示から隠す (抑制)」で確定した場合は破壊的
        操作のため、実行前に `QMessageBox.question` で確認を取ってから対応する Signal を出す。

        Args:
            canonical: 翻訳を修正/削除/抑制する canonical タグ文字列。
        """
        tag_id = next(
            (t.get("tag_id") for t in self._tags if t.get("tag") == canonical and t.get("tag_id")),
            None,
        )
        translations = self._translations.get(tag_id, {}) if tag_id is not None else {}
        if not translations:
            if self._tag_metadata_pending:
                # 読み込み中/取得失敗を「翻訳なし」と誤認すると追加ダイアログへ落ち、
                # legacy 言語キーの誤訳を上書きできない (PR #1086 Codex P2)
                QMessageBox.information(
                    self,
                    "翻訳を修正",
                    "翻訳情報を読み込み中です。数秒待ってからもう一度お試しください。",
                )
                return
            self._open_translation_dialog(canonical)
            return
        # 主訳 fan-out や legacy/正規表記の混在で同一言語が ja/japanese 両キーに入りうる。
        # 族ごとに 1 行へ畳んでから渡し、幻の重複行を防ぐ (#1236)。
        dialog = TranslationFixDialog(canonical, dedupe_translations_by_family(dict(translations)), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        language = dialog.language()
        action = dialog.action()
        if action in ("delete", "suppress"):
            original = dialog.original_translation()
            if not language or not original:
                logger.debug(
                    f"翻訳{'削除' if action == 'delete' else '抑制'}をスキップ (空入力): canonical='{canonical}'"
                )
                return
            if action == "delete":
                reply = QMessageBox.question(
                    self,
                    "この翻訳を削除",
                    f"'{canonical}' ({language}) の翻訳 '{original}' を削除しますか?\n"
                    "自分で追加した訳のみ削除できます。元データベース由来の訳はこの操作では"
                    "削除されません (その場合は「表示から隠す (抑制)」を使ってください)。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                self.translation_delete_requested.emit(canonical, language, original)
            else:
                reply = QMessageBox.question(
                    self,
                    "表示から隠す (抑制)",
                    f"'{canonical}' ({language}) の翻訳 '{original}' を表示/検索結果から"
                    "隠しますか?\n元データベースの値自体は変更されません。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
                self.translation_suppress_requested.emit(canonical, language, original)
            return
        translation = dialog.translation()
        if not language or not translation:
            logger.debug(f"翻訳修正をスキップ (空入力): canonical='{canonical}'")
            return
        self.translation_add_requested.emit(canonical, language, translation)

    @Slot(str)
    def _open_type_edit_dialog(self, canonical: str) -> None:
        """タグ種別補正ダイアログを開き、確定で tag_metadata_edit_requested を出す (#989)。

        当該タグに refinement の TYPE_MISMATCH 警告があればヒントとして渡す。

        Args:
            canonical: 種別を補正する canonical タグ文字列。
        """
        custom_type_names = self._type_choices_provider() if self._type_choices_provider is not None else []
        current_type = self._tag_types.get(canonical)
        dialog = TagTypeEditDialog(
            canonical,
            self._type_mismatch_hint(canonical),
            custom_type_names=custom_type_names,
            current_type=current_type,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        type_name = dialog.selected_type()
        if not type_name:
            # プレースホルダのまま確定 (明示選択なし) → 既存 type を上書きしない (#995 P2)。
            logger.debug(f"type 補正をスキップ (種別未選択): canonical='{canonical}'")
            return
        if type_name == current_type:
            # 現在 type を初期選択 (#1255 バグ1) したことで、無変更確定でも emit すると
            # 冗長な userdb 書き込み + refinement 再実行が走る。値が変わらなければ skip する。
            logger.debug(f"type 補正をスキップ (無変更): canonical='{canonical}', type='{type_name}'")
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
        """保持中のリコメンド (_last_refinements) を現在の chip 群へ反映する (#931)。

        1 回の画像選択で set_tags / set_rejected_tags / set_tag_metadata_pending 等が
        各々 chip を再生成し本メソッドを誘発する。refinement が未確定 (空) の間は、
        再生成直後の無印 chip へ「印なし」を適用するだけの no-op が選択のたびに数回
        重なり CPU を浪費する (#1221)。適用すべき refinement が無く、かつ現在の chip も
        無印なら丸ごとスキップする。refinement 確定後や、確定済み ⚠ を消す再適用は
        従来どおり実行する (⚠ 表示の正しさは不変)。
        """
        if not self._last_refinements and not self._chips_carry_refinements:
            return
        applied = 0
        for chip in self._tag_chips:
            rec = self._last_refinements.get(chip.canonical)
            chip.set_refinement(rec, candidate_counts=self._last_candidate_counts)
            if rec is not None:
                applied += 1
        self._chips_carry_refinements = applied > 0
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
        「種別で分ける」(#1241) でセクションが複数になった場合も、各セクション
        (ヘッダ QLabel または FlowLayout コンテナ) の実寸を合算して箱の高さを求める。
        """
        if not self._tags_scroll.isVisible():
            return
        width = self._tags_scroll.viewport().width()
        if width <= 0:
            return
        sections_layout = self._tags_chip_sections_layout
        needed = 0
        section_count = 0
        for i in range(sections_layout.count()):
            item = sections_layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            section_count += 1
            flow = widget.layout()
            if isinstance(flow, FlowLayout):
                # chip 再構築直後はレイアウト未 activation で新チップがまだ hidden の
                # ことがあり、QWidgetItem.sizeHint() が (0,0) を返して heightForWidth=0
                # → 箱が 8px に潰れる (#1025)。同期計測の前に hidden の chip を明示的に
                # 可視化して実寸を得る。
                for j in range(flow.count()):
                    child_item = flow.itemAt(j)
                    child_widget = child_item.widget() if child_item is not None else None
                    if child_widget is not None and child_widget.isHidden():
                        child_widget.setVisible(True)
                needed += flow.heightForWidth(width)
            else:
                # 種別ヘッダ QLabel (#1241)。プレーンな sizeHint を積み上げる。
                if widget.isHidden():
                    widget.setVisible(True)
                needed += widget.sizeHint().height()
        if section_count > 1:
            needed += sections_layout.spacing() * (section_count - 1)
        # 収まるときに内側スクロールバーが出ないよう僅かな余裕を足す。
        self._tags_scroll.setFixedHeight(min(needed + 8, self._TAGS_MAX_HEIGHT))
