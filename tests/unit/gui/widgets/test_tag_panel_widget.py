"""TagPanelWidget 単体テスト (ADR 0083 / Issue #987)。

DB / service 非依存の生成、chip 描画、soft-reject 一本のタグ操作モデル
(単クリック無効化トグル / ✕ で外す / Ctrl+クリック選択コピー)、手動タグ追加、
refinement ignore の Signal 配線を検証する。
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QToolButton

from lorairo.gui import theme
from lorairo.gui.widgets import tag_panel_widget as tpw
from lorairo.gui.widgets.tag_panel_widget import (
    SelectableTagChip,
    TagPanelWidget,
    TagTypeEditDialog,
    TranslationAddDialog,
)

pytestmark = pytest.mark.gui


@pytest.fixture
def panel(qtbot):
    """DB / service を注入しない素の TagPanelWidget (受け入れ条件 ①)。"""
    w = TagPanelWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def sample_tags():
    return [
        {"tag": "1girl", "tag_id": 10, "model_name": "wd", "source": "AI", "confidence_score": 0.9},
        {"tag": "flower", "tag_id": 20, "model_name": "wd", "source": "AI", "confidence_score": 0.8},
        {"tag": "solo", "tag_id": None, "model_name": "wd", "source": "AI", "confidence_score": 0.7},
    ]


# ① 注入なし生成 -------------------------------------------------------------


def test_constructs_without_db_or_service(panel):
    """db_manager / service_container を持たずに生成できること (#978 整合)。"""
    assert not hasattr(panel, "_db_manager")
    assert not hasattr(panel, "_service_container")
    assert panel._tag_chips == []


# ② set_tags で canonical 順に SelectableTagChip 描画 -------------------------


def test_set_tags_renders_chips_in_canonical_order(panel, sample_tags):
    panel.set_tags(sample_tags)
    assert len(panel._tag_chips) == 3
    assert all(isinstance(c, SelectableTagChip) for c in panel._tag_chips)
    assert [c.canonical for c in panel._tag_chips] == ["1girl", "flower", "solo"]


def test_set_tags_dedupes_same_canonical_across_models(panel):
    """#1055: 複数モデル由来の同一 canonical 行は初出順で 1 チップに畳む (heart x9 対策)。"""
    rows = [{"tag": "heart", "tag_id": 30, "model_name": f"model{i}", "source": "AI"} for i in range(9)]
    tags = [
        {"tag": "1girl", "tag_id": 10, "model_name": "wd", "source": "AI"},
        *rows,
        {"tag": "solo", "tag_id": None, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 10, "model_name": "e621", "source": "AI"},
    ]

    panel.set_tags(tags)

    assert [c.canonical for c in panel._tag_chips] == ["1girl", "heart", "solo"]


def test_set_tags_keeps_all_provenance_rows_in_table(panel):
    """#1055 Codex P2: 隠しテーブル (TSV コピー) はモデル別由来の全行を保持する。"""
    tags = [{"tag": "heart", "tag_id": 30, "model_name": f"model{i}", "source": "AI"} for i in range(3)]

    panel.set_tags(tags)

    assert len(panel._tag_chips) == 1
    assert panel.tableWidgetTags.rowCount() == 3
    models = {panel.tableWidgetTags.item(row, 1).text() for row in range(3)}
    assert models == {"model0", "model1", "model2"}


def test_set_tags_sorts_by_type_group_then_alphabetical(panel):
    """#1056: character→copyright→artist→general→meta のグループ順 + グループ内アルファベット順。"""
    tags = [
        {"tag": "zzz effect", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
        {"tag": "hatsune miku", "tag_id": 3, "model_name": "wd", "source": "AI"},
        {"tag": "vocaloid", "tag_id": 4, "model_name": "wd", "source": "AI"},
        {"tag": "absurdres", "tag_id": 5, "model_name": "wd", "source": "AI"},
        {"tag": "aaa artist", "tag_id": 6, "model_name": "wd", "source": "AI"},
    ]
    tag_types = {
        "1girl": "general",
        "zzz effect": "general",
        "hatsune miku": "character",
        "vocaloid": "copyright",
        "absurdres": "meta",
        "aaa artist": "artist",
    }

    panel.set_tags(tags, tag_types=tag_types)

    assert [c.canonical for c in panel._tag_chips] == [
        "hatsune miku",  # character
        "vocaloid",  # copyright
        "aaa artist",  # artist
        "1girl",  # general (アルファベット順)
        "zzz effect",  # general
        "absurdres",  # meta
    ]


def test_set_tags_unknown_type_goes_to_trailing_group(panel):
    """#1056: type が引けないタグ (tagdb 未登録等) は末尾グループに寄せる (ユーザー決定)。"""
    tags = [
        {"tag": "aaa unknown", "tag_id": None, "model_name": "wd", "source": "AI"},
        {"tag": "zzz meta", "tag_id": 5, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    tag_types = {"1girl": "general", "zzz meta": "meta"}

    panel.set_tags(tags, tag_types=tag_types)

    assert [c.canonical for c in panel._tag_chips] == ["1girl", "zzz meta", "aaa unknown"]


def test_set_tags_without_types_sorts_alphabetically(panel):
    """#1056: type 情報が無い呼び出し元 (staging 等) でもアルファベット順で規則性を持つ。"""
    tags = [
        {"tag": "solo", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
        {"tag": "flower", "tag_id": 3, "model_name": "wd", "source": "AI"},
    ]

    panel.set_tags(tags)

    assert [c.canonical for c in panel._tag_chips] == ["1girl", "flower", "solo"]


def test_set_tags_dedupe_prefers_row_with_tag_id(panel):
    """#1055 Codex P2: 初出行が tag_id 無し (legacy) なら tag_id 付き行を採用する。"""
    tags = [
        {"tag": "heart", "tag_id": None, "model_name": "legacy", "source": "Manual"},
        {"tag": "heart", "tag_id": 30, "model_name": "wd", "source": "AI"},
    ]

    panel.set_tags(tags)

    assert len(panel._tags) == 1
    assert panel._tags[0]["tag_id"] == 30


# ③ 単クリックで reject 発火 + 破線化 ----------------------------------------


def test_single_click_emits_disable_and_dashes_chip(panel, sample_tags, qtbot):
    """単クリックは無効化 (tag_disable_requested, reason='not_needed') を出す (#1003)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    chip = panel._tag_chips[0]

    with qtbot.waitSignal(panel.tag_disable_requested, timeout=1000) as blocker:
        chip.clicked.emit()
    assert blocker.args == ["1girl"]
    # 当該 chip は破線スタイル (無効化インライン表示) になる
    assert chip.styleSheet() == theme.tag_chip_untranslated_qss()
    assert "1girl" in panel._disabled_display


def test_single_click_noop_when_edit_disabled(panel, sample_tags):
    """編集モード無効時は単クリックで disable を出さない (read-only)。"""
    panel.set_tags(sample_tags)
    received: list[str] = []
    panel.tag_disable_requested.connect(received.append)
    panel._tag_chips[0].clicked.emit()
    assert received == []


# ④ 破線 chip クリックで restore 発火 ----------------------------------------


def test_click_disabled_chip_emits_restore(panel, sample_tags, qtbot):
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    chip = panel._tag_chips[0]
    chip.clicked.emit()  # 無効化
    assert "1girl" in panel._disabled_display

    with qtbot.waitSignal(panel.tag_restore_requested, timeout=1000) as blocker:
        chip.clicked.emit()  # 復活
    assert blocker.args == ["1girl"]
    assert "1girl" not in panel._disabled_display
    assert chip.styleSheet() == chip.base_qss


# ⑤ ✕ で reject 発火 + 非表示 ------------------------------------------------


def test_remove_button_emits_exclude_and_hides_chip(panel, sample_tags, qtbot):
    """✕ は除外 (tag_exclude_requested, reason='incorrect') を出し非表示にする (#1003)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    buttons = panel.findChildren(QToolButton, "tagRejectButton")
    assert len(buttons) == 3

    with qtbot.waitSignal(panel.tag_exclude_requested, timeout=1000) as blocker:
        buttons[0].click()
    assert blocker.args == ["1girl"]
    # ✕ したタグはパネルから非表示 (当該セッションのみ)
    assert "1girl" in panel._hidden
    assert "1girl" not in [c.canonical for c in panel._tag_chips]
    assert [c.canonical for c in panel._tag_chips] == ["flower", "solo"]


# ⑥ Ctrl+クリックで選択 → canonical コピー -----------------------------------


def test_ctrl_click_selects_and_copies_canonical(panel, sample_tags):
    panel.set_tags(sample_tags)
    rejected: list[str] = []
    panel.tag_disable_requested.connect(rejected.append)
    panel.tag_exclude_requested.connect(rejected.append)

    panel._tag_chips[0].ctrl_clicked.emit()  # 1girl 選択
    panel._tag_chips[2].ctrl_clicked.emit()  # solo 選択

    # Ctrl+クリックは reject を出さない (コピー選択のみ)
    assert rejected == []
    assert panel._tag_chips[0].selected is True
    assert panel._tag_chips[2].selected is True

    assert panel.copy_selected_tags_to_clipboard() is True
    assert QApplication.clipboard().text() == "1girl, solo"


def test_copy_uses_canonical_not_translated(panel, sample_tags):
    """言語切替で表示が翻訳でもコピーは canonical 原文を使う (#814)。"""
    translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
    panel.set_tags(sample_tags, translations, ["japanese"])
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")

    assert [c.text() for c in panel._tag_chips] == ["1人の女の子", "花", "solo"]
    assert panel.copy_selected_tags_to_clipboard() is True
    assert QApplication.clipboard().text() == "1girl, flower, solo"


# ⑦ 手動タグ追加 Enter で raw 入力を出す -------------------------------------


def test_add_input_emits_raw_tag_add(panel, qtbot):
    panel.set_tag_edit_enabled(True)
    panel._tag_add_input.setText("青い 空")
    with qtbot.waitSignal(panel.tag_add_requested, timeout=1000) as blocker:
        panel._tag_add_input.returnPressed.emit()
    assert blocker.args == ["青い 空"]  # 生入力のまま (親が canonical 解決)
    assert panel._tag_add_input.text() == ""


# ⑧ refinement ignore で refinement_ignored 発火 -----------------------------


def test_refinement_ignore_relays_to_panel_signal(panel, sample_tags, qtbot):
    from genai_tag_db_tools.models import RefinementReason, RefinementRecommendation

    rec = RefinementRecommendation(
        source_tag="1girl",
        normalized_tag="1girl",
        needs_refinement=True,
        score=0.7,
        reasons=[RefinementReason(code="broad_single_word", message="broad")],  # type: ignore[arg-type]
        suggestions=[],
        proposals=[],
    )
    panel.set_tags(sample_tags)
    panel.apply_refinements({"1girl": rec})

    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert chip.text().startswith("⚠")  # 警告マーカーが付く

    received: list[tuple[str, str]] = []
    panel.refinement_ignored.connect(lambda c, r: received.append((c, r)))
    # chip の「この理由を無視」を発火 → パネル signal へ中継されること
    chip.refinement_ignore_requested.emit("1girl", "broad_single_word")
    assert received == [("1girl", "broad_single_word")]


# 言語切替・脚注・soft-rejected インライン表示 -------------------------------


def test_language_switch_renders_translated_chips(panel, sample_tags):
    translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
    panel.set_tags(sample_tags, translations, ["japanese"])
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")
    assert [c.text() for c in panel._tag_chips] == ["1人の女の子", "花", "solo"]


def test_translation_note_visible_only_when_translated(panel, sample_tags):
    translations = {10: {"japanese": "1人の女の子"}}
    panel.set_tags(sample_tags, translations, ["japanese"])
    panel.initialize_language_selector(["japanese"])
    assert panel._tags_translation_note.isHidden()
    panel._lang_combo.setCurrentText("japanese")
    assert not panel._tags_translation_note.isHidden()
    panel._lang_combo.setCurrentText("english")
    assert panel._tags_translation_note.isHidden()


def test_set_rejected_tags_not_needed_renders_inline_dashed_restore_chip(panel, qtbot):
    """reject_reason='not_needed' (無効化) はインライン破線 chip で表示し、クリックで復活する。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags([{"tag": "1girl", "tag_id": 10}])
    panel.set_rejected_tags([{"tag": "bad_tag", "reject_reason": "not_needed"}])

    rejected_chip = next((c for c in panel._tag_chips if c.canonical == "bad_tag"), None)
    assert rejected_chip is not None
    assert rejected_chip.styleSheet() == theme.tag_chip_untranslated_qss()
    with qtbot.waitSignal(panel.tag_restore_requested, timeout=1000) as blocker:
        rejected_chip.clicked.emit()
    assert blocker.args == ["bad_tag"]


def test_set_rejected_tags_incorrect_and_replaced_are_hidden(panel):
    """reject_reason='incorrect'/'replaced' (除外/置換) は非表示になる (#1003)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags([{"tag": "1girl", "tag_id": 10}])
    panel.set_rejected_tags(
        [
            {"tag": "wrong_tag", "reject_reason": "incorrect"},
            {"tag": "moved_tag", "reject_reason": "replaced"},
        ]
    )
    canonicals = [c.canonical for c in panel._tag_chips]
    assert "wrong_tag" not in canonicals
    assert "moved_tag" not in canonicals
    assert panel._hidden == {"wrong_tag", "moved_tag"}
    assert panel._disabled_display == set()


def test_set_rejected_tags_rebuilds_state_from_db_reason(panel):
    """別画像往復を模した再 set_rejected_tags で表示種別が DB reason から再構築される (#1003)。

    メモリ state ではなく DB 由来の reject_reason で毎回 _disabled_display / _hidden を
    作り直すため、逆の種別で呼び直すと表示が入れ替わる (現象の構造的根治)。
    """
    panel.set_tag_edit_enabled(True)
    panel.set_tags([{"tag": "1girl", "tag_id": 10}], image_id=10)
    # 1回目: not_needed (無効化)
    panel.set_rejected_tags([{"tag": "t", "reject_reason": "not_needed"}])
    assert panel._disabled_display == {"t"}
    assert panel._hidden == set()
    # 2回目: 同じタグが incorrect (除外) に変わったら非表示へ再構築される
    panel.set_rejected_tags([{"tag": "t", "reject_reason": "incorrect"}])
    assert panel._disabled_display == set()
    assert panel._hidden == {"t"}


def test_displayed_tags_text_returns_current_compact_label(panel, sample_tags):
    translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
    panel.set_tags(sample_tags, translations, ["japanese"])
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")
    assert panel.displayed_tags_text() == "1人の女の子, 花, solo"


def test_clear_removes_chips(panel, sample_tags):
    panel.set_tags(sample_tags)
    assert len(panel._tag_chips) == 3
    panel.clear()
    assert panel._tag_chips == []
    assert panel.displayed_tags_text() == "-"


def test_set_tags_resets_session_state(panel, sample_tags):
    """新画像 set_tags で無効化 / 非表示 / refinement がリセットされる。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    panel._tag_chips[0].clicked.emit()  # 1girl 無効化
    assert panel._disabled_display

    panel.set_tags(sample_tags)
    assert panel._disabled_display == set()
    assert panel._hidden == set()
    assert panel._last_refinements == {}


def test_x_removed_tag_stays_hidden_after_same_image_reload(panel, sample_tags):
    """✕ で外したタグは同一画像の reject reload 後も非表示を維持する (PR #992 Codex P2 / #1003)。

    ✕ → tag_exclude_requested が同期で親へ届き、親が同一画像を reload して
    set_tags / set_rejected_tags を呼び戻す。reload では set_rejected_tags が DB の
    reject_reason='incorrect' から _hidden を再構築するため、外したタグは非表示のままになる。
    """
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=10)
    panel._on_chip_removed("1girl")
    assert "1girl" in panel._hidden

    # 同一画像の reject reload: 1girl は active から消え rejected (incorrect) へ移る
    remaining = [t for t in sample_tags if t["tag"] != "1girl"]
    panel.set_tags(remaining, image_id=10)
    panel.set_rejected_tags([{"tag": "1girl", "reject_reason": "incorrect"}])

    assert "1girl" in panel._hidden
    assert "1girl" not in [chip.canonical for chip in panel._tag_chips]


def test_disabled_tag_survives_image_round_trip_via_db_reason(panel, sample_tags):
    """無効化タグは別画像往復後も DB reason から破線表示が復元される (現象の核、#1003)。

    メモリ state (別画像 set_tags でクリアされる) に頼らず、戻ってきたときの
    set_rejected_tags(reason='not_needed') で _disabled_display が再構築される。
    """
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=10)
    panel._tag_chips[0].clicked.emit()  # 1girl 無効化
    assert "1girl" in panel._disabled_display

    # 別画像へ移動 (メモリ state クリア)
    panel.set_tags([{"tag": "other", "tag_id": 99}], image_id=20)
    assert panel._disabled_display == set()

    # 元画像へ戻る: DB から not_needed で復元される
    panel.set_tags(sample_tags, image_id=10)
    panel.set_rejected_tags([{"tag": "1girl", "reject_reason": "not_needed"}])
    assert "1girl" in panel._disabled_display
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert chip.styleSheet() == theme.tag_chip_untranslated_qss()


def test_session_state_resets_on_image_change(panel, sample_tags):
    """別画像へ切り替えたら ✕ で外した非表示状態はリセットされる。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=10)
    panel._on_chip_removed("1girl")
    assert "1girl" in panel._hidden

    panel.set_tags(sample_tags, image_id=20)
    assert panel._hidden == set()
    assert "1girl" in [chip.canonical for chip in panel._tag_chips]


# ⑩ tagdb userdb 系: 翻訳追加 / type 補正 Signal (#989) -----------------------


def _accept_dialog(monkeypatch, dialog_attr, field_setter):
    """指定ダイアログクラスの exec を Accepted に固定し、入力欄を埋める。

    ダイアログは _open_*_dialog 内部で生成されるため、__init__ 直後に field_setter で
    値を流し込み、exec() は実表示せず Accepted を返すよう差し替える。
    """
    original = getattr(tpw, dialog_attr)

    class _AutoAcceptDialog(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            field_setter(self)

        def exec(self):
            return int(QDialog.DialogCode.Accepted)

    monkeypatch.setattr(tpw, dialog_attr, _AutoAcceptDialog)


def test_chip_right_click_signals_exist(panel):
    """tagdb userdb 系の panel Signal が定義されていること (ADR 0083 §2)。"""
    assert hasattr(panel, "translation_add_requested")
    assert hasattr(panel, "tag_metadata_edit_requested")


def test_untranslated_chip_flag_set(panel, sample_tags):
    """非英語表示で翻訳欠落の chip は untranslated=True になる (#989)。"""
    panel.set_tags(sample_tags, translations={}, available_languages=["ja"], image_id=10)
    panel.initialize_language_selector(["ja"])
    panel._lang_combo.setCurrentText("ja")
    assert any(chip.untranslated for chip in panel._tag_chips)


def test_translation_add_dialog_emits_signal(panel, sample_tags, qtbot, monkeypatch):
    """翻訳追加ダイアログ確定で translation_add_requested(canonical, lang, tr) を出す。"""
    panel.set_tags(sample_tags, image_id=10)

    def fill(dialog):
        dialog._language_combo.setCurrentIndex(0)  # 日本語 (保存値 ja、#1050)
        dialog._translation_input.setText("少女")

    _accept_dialog(monkeypatch, "TranslationAddDialog", fill)
    with qtbot.waitSignal(panel.translation_add_requested, timeout=1000) as blocker:
        panel._open_translation_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "少女"]


def test_translation_add_dialog_cancel_emits_nothing(panel, sample_tags, monkeypatch):
    """ダイアログをキャンセルすると Signal を出さない。"""
    panel.set_tags(sample_tags, image_id=10)
    monkeypatch.setattr(tpw.TranslationAddDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected))
    received: list = []
    panel.translation_add_requested.connect(lambda *a: received.append(a))
    panel._open_translation_dialog("1girl")
    assert received == []


def test_translation_add_empty_input_skipped(panel, sample_tags, monkeypatch):
    """空入力 (翻訳テキストなし) では Signal を出さない。"""
    panel.set_tags(sample_tags, image_id=10)

    def fill(dialog):
        dialog._language_combo.setCurrentIndex(0)  # 日本語 (保存値 ja、#1050)
        dialog._translation_input.setText("")

    _accept_dialog(monkeypatch, "TranslationAddDialog", fill)
    received: list = []
    panel.translation_add_requested.connect(lambda *a: received.append(a))
    panel._open_translation_dialog("1girl")
    assert received == []


def test_type_edit_dialog_emits_signal(panel, sample_tags, qtbot, monkeypatch):
    """type 補正ダイアログ確定で tag_metadata_edit_requested(canonical, type) を出す。"""
    panel.set_tags(sample_tags, image_id=10)

    def fill(dialog):
        dialog._type_combo.setCurrentText("copyright")

    _accept_dialog(monkeypatch, "TagTypeEditDialog", fill)
    with qtbot.waitSignal(panel.tag_metadata_edit_requested, timeout=1000) as blocker:
        panel._open_type_edit_dialog("1girl")
    assert blocker.args == ["1girl", "copyright"]


def test_type_edit_placeholder_confirm_skips_emit(panel, sample_tags, monkeypatch):
    """種別未選択 (プレースホルダのまま) で確定しても既存 type を上書きしない (#995 P2)。"""
    panel.set_tags(sample_tags, image_id=10)

    # field_setter なし = プレースホルダ選択のまま Accepted を返す。
    _accept_dialog(monkeypatch, "TagTypeEditDialog", lambda dialog: None)
    received: list = []
    panel.tag_metadata_edit_requested.connect(lambda *a: received.append(a))
    panel._open_type_edit_dialog("1girl")
    assert received == []


def test_translation_dialog_returns_inputs(qtbot):
    """TranslationAddDialog が言語・翻訳の入力値を返す。"""
    dialog = TranslationAddDialog("1girl", ["ja", "english"])
    qtbot.addWidget(dialog)
    dialog._language_combo.setCurrentText("ja")
    dialog._translation_input.setText("少女")
    assert dialog.language() == "ja"
    assert dialog.translation() == "少女"


def test_type_dialog_choices_and_hint(qtbot):
    """TagTypeEditDialog が type 候補を持ち TYPE_MISMATCH ヒントを表示する。"""
    dialog = TagTypeEditDialog("1girl", type_mismatch_hint="type が一致しません")
    qtbot.addWidget(dialog)
    choices = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
    # current_type 不明時はプレースホルダ先頭 + 全 TYPE_CHOICES
    assert choices == [TagTypeEditDialog._PLACEHOLDER, *TagTypeEditDialog.TYPE_CHOICES]
    # 既定はプレースホルダ選択 = 未選択 (空文字)、OK は無効
    assert dialog.selected_type() == ""
    ok_button = dialog._buttons.button(dialog._buttons.StandardButton.Ok)
    assert not ok_button.isEnabled()
    # 実 type を選ぶと selected_type が返り OK 有効化
    dialog._type_combo.setCurrentText("copyright")
    assert dialog.selected_type() == "copyright"
    assert ok_button.isEnabled()


def test_type_dialog_preselects_known_current_type(qtbot):
    """current_type を渡すとプレースホルダなしで初期選択され OK 有効。"""
    dialog = TagTypeEditDialog("1girl", current_type="character")
    qtbot.addWidget(dialog)
    choices = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
    assert choices == list(TagTypeEditDialog.TYPE_CHOICES)
    assert dialog.selected_type() == "character"


# ⑬ 使用頻度 第2軸 (metric_source, ADR 0083 §5 / #990) -----------------------


def test_metric_bar_hidden_without_usage_counts(panel, sample_tags):
    """usage count が無ければ metric バーは非表示 (受け入れ条件)。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({})
    assert panel._metric_bar.isHidden()


def test_metric_selector_lists_available_formats(panel, sample_tags):
    """usage count のある format 名が「なし」に続けて昇順で候補化される。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({10: {"danbooru": 1234, "e621": 42}, 20: {"danbooru": 800}})
    options = [panel._metric_combo.itemText(i) for i in range(panel._metric_combo.count())]
    assert options == [tpw._METRIC_NONE_LABEL, "danbooru", "e621"]


def test_metric_none_hides_counts(panel, sample_tags):
    """metric=なし では chip に count を表示しない (受け入れ条件)。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({10: {"danbooru": 1234}})
    # 既定は「なし」
    assert panel._metric_combo.currentText() == tpw._METRIC_NONE_LABEL
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert "(" not in chip.text()


def test_metric_selection_shows_formatted_count(panel, sample_tags):
    """metric 選択で chip にサイト別 count が 1.2k 形式で表示される (受け入れ条件)。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({10: {"danbooru": 1234}, 20: {"danbooru": 842000}})
    panel._metric_combo.setCurrentText("danbooru")
    girl = next(c for c in panel._tag_chips if c.canonical == "1girl")
    flower = next(c for c in panel._tag_chips if c.canonical == "flower")
    assert girl.text() == "1girl (1.2k)"
    assert flower.text() == "flower (842k)"
    # canonical はサフィックスを含まず、コピー結果に影響しない (#814)
    assert girl.canonical == "1girl"


def test_metric_switch_updates_count_display(panel, sample_tags):
    """metric 切替で count 表示が更新される (受け入れ条件)。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({10: {"danbooru": 1234, "e621": 5000000}})
    panel._metric_combo.setCurrentText("danbooru")
    girl = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert girl.text() == "1girl (1.2k)"
    panel._metric_combo.setCurrentText("e621")
    girl = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert girl.text() == "1girl (5M)"
    # e621 に count が無い flower はサフィックスなし
    flower = next(c for c in panel._tag_chips if c.canonical == "flower")
    assert "(" not in flower.text()


def test_metric_independent_of_language(panel, sample_tags):
    """表示言語と metric を独立に切替できる (受け入れ条件)。"""
    translations = {10: {"japanese": "少女"}}
    panel.set_tags(sample_tags, translations, ["japanese"])
    panel.initialize_language_selector(["japanese"])
    panel.set_usage_counts({10: {"danbooru": 1234}})
    panel._metric_combo.setCurrentText("danbooru")
    panel._lang_combo.setCurrentText("japanese")
    girl = next(c for c in panel._tag_chips if c.canonical == "1girl")
    # 翻訳表示 + サイト別 count が両立する
    assert girl.text() == "少女 (1.2k)"


def test_format_count_abbreviation():
    """K/M 整形: 1.2M / 842k / 小数なし整数。"""
    fmt = TagPanelWidget._format_count
    assert fmt(842) == "842"
    assert fmt(1234) == "1.2k"
    assert fmt(842000) == "842k"
    assert fmt(1200000) == "1.2M"
    assert fmt(5000000) == "5M"


def test_clear_resets_metric(panel, sample_tags):
    """clear で metric セレクタが「なし」のみへ戻り非表示になる。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({10: {"danbooru": 1234}})
    panel.clear()
    options = [panel._metric_combo.itemText(i) for i in range(panel._metric_combo.count())]
    assert options == [tpw._METRIC_NONE_LABEL]
    assert panel._metric_bar.isHidden()


# ⑪ バッチ操作バー (#997) -----------------------------------------------------


def test_selection_bar_hidden_without_selection(panel, sample_tags):
    """選択 0件ではバッチ操作バーは非表示。"""
    panel.set_tags(sample_tags)
    assert panel._selection_bar.isHidden() is True


def test_ctrl_click_shows_selection_bar_with_count(panel, sample_tags):
    """Ctrl+クリック選択でバッチ操作バーが表示され件数が反映される。"""
    panel.set_tags(sample_tags)
    panel._tag_chips[0].ctrl_clicked.emit()
    panel._tag_chips[2].ctrl_clicked.emit()

    assert panel._selection_bar.isHidden() is False
    labels = [w.text() for w in panel._selection_bar.findChildren(QLabel)]
    assert "2件選択中" in labels


def test_selection_persists_across_rerender(panel, sample_tags):
    """言語切替などで chip が再生成されても選択ハイライトは復元される (#997)。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "女の子"}}, available_languages=["ja"], image_id=1)
    panel.initialize_language_selector(["ja"])
    panel._tag_chips[0].ctrl_clicked.emit()  # 1girl 選択
    assert "1girl" in panel._selected_canonicals

    panel._lang_combo.setCurrentText("ja")  # chip 再生成が走る

    girl_chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert girl_chip.selected is True
    assert girl_chip.styleSheet() == panel._selected_chip_qss()


def test_selection_bar_tag_info_buttons_enabled_only_for_single_selection(panel, sample_tags):
    """翻訳/編集/頻度ボタンは単一選択時のみ有効 (design の disabled={!single} 踏襲)。"""
    panel.set_tags(sample_tags)
    panel._tag_chips[0].ctrl_clicked.emit()
    buttons = {b.text(): b for b in panel._selection_bar.findChildren(QPushButton)}
    assert buttons["翻訳"].isEnabled() is True
    assert buttons["編集"].isEnabled() is True
    assert buttons["頻度"].isEnabled() is True

    panel._tag_chips[1].ctrl_clicked.emit()  # 2件選択に
    buttons = {b.text(): b for b in panel._selection_bar.findChildren(QPushButton)}
    assert buttons["翻訳"].isEnabled() is False
    assert buttons["編集"].isEnabled() is False
    assert buttons["頻度"].isEnabled() is False


def test_selection_bar_batch_buttons_disabled_when_edit_disabled(panel, sample_tags):
    """外す/無効化⇄復活は編集モード無効時は無効化される。"""
    panel.set_tags(sample_tags)
    panel._tag_chips[0].ctrl_clicked.emit()
    buttons = {b.text(): b for b in panel._selection_bar.findChildren(QPushButton)}
    assert buttons["外す"].isEnabled() is False
    assert buttons["無効化⇄復活"].isEnabled() is False


def test_batch_remove_hides_selected_and_emits_list(panel, sample_tags, qtbot):
    """バッチ「外す」で選択タグがまとめて非表示になり tags_exclude_requested(list) を出す。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    panel._tag_chips[0].ctrl_clicked.emit()  # 1girl
    panel._tag_chips[2].ctrl_clicked.emit()  # solo
    remove_button = next(b for b in panel._selection_bar.findChildren(QPushButton) if b.text() == "外す")

    with qtbot.waitSignal(panel.tags_exclude_requested, timeout=1000) as blocker:
        remove_button.click()
    assert sorted(blocker.args[0]) == ["1girl", "solo"]
    assert {"1girl", "solo"} <= panel._hidden
    assert [c.canonical for c in panel._tag_chips] == ["flower"]
    assert panel._selected_canonicals == set()
    assert panel._selection_bar.isHidden() is True


def test_batch_toggle_disable_inverts_each_tag_independently(panel, sample_tags, qtbot):
    """バッチ「無効化⇄復活」は選択中の各タグを個別に現在状態の反転にする (#997)。

    混在選択 (有効な 1girl/solo + 既に無効化済みの flower) でも一方向へ揃えない:
    有効だったものは無効化、無効化済みだったものは復活へそれぞれ逆転する。
    """
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    panel._tag_chips[1].clicked.emit()  # flower を先に無効化しておく
    assert "flower" in panel._disabled_display

    panel._tag_chips[0].ctrl_clicked.emit()  # 1girl (有効)
    panel._tag_chips[1].ctrl_clicked.emit()  # flower (無効化済み)
    toggle_button = next(
        b for b in panel._selection_bar.findChildren(QPushButton) if b.text() == "無効化⇄復活"
    )

    # 混在選択でも reload が1回で済むよう、reject/restore は1回の Signal (2引数) で
    # まとめて渡す (Codex #1001 P2)。
    toggle_received: list[tuple[list[str], list[str]]] = []
    panel.tags_toggle_requested.connect(lambda reject, restore: toggle_received.append((reject, restore)))

    toggle_button.click()

    assert toggle_received == [(["1girl"], ["flower"])]
    assert "1girl" in panel._disabled_display
    assert "flower" not in panel._disabled_display
    assert panel._selected_canonicals == set()


def test_batch_clear_selection_button_resets_highlight(panel, sample_tags):
    """「選択解除」ボタンで選択集合がクリアされ chip の強調表示が戻る。"""
    panel.set_tags(sample_tags)
    panel._tag_chips[0].ctrl_clicked.emit()
    chip = panel._tag_chips[0]
    assert chip.selected is True

    clear_button = next(b for b in panel._selection_bar.findChildren(QPushButton) if b.text() == "選択解除")
    clear_button.click()

    assert panel._selected_canonicals == set()
    assert chip.selected is False
    assert chip.styleSheet() == chip.base_qss
    assert panel._selection_bar.isHidden() is True


# ⑫ 使用頻度を見るダイアログ (#997) -------------------------------------------


def test_usage_counts_menu_signal_exists(panel):
    """chip に使用頻度を見るメニュー要求 Signal があること。"""
    chip = SelectableTagChip("1girl", "1girl")
    assert hasattr(chip, "usage_counts_menu_requested")


def test_open_usage_counts_dialog_passes_cached_counts(panel, sample_tags, monkeypatch):
    """右クリック「使用頻度を見る」は #990 で既にキャッシュ済みの counts をそのまま渡す。"""
    panel.set_tags(sample_tags)
    panel.set_usage_counts({10: {"danbooru": 1234000, "e621": 500}})

    captured: dict[str, object] = {}

    class _CapturingDialog(tpw.UsageCountsDialog):
        def __init__(self, canonical, counts, parent=None):
            captured["canonical"] = canonical
            captured["counts"] = counts
            super().__init__(canonical, counts, parent)

        def exec(self):
            return None

    monkeypatch.setattr(tpw, "UsageCountsDialog", _CapturingDialog)
    panel._open_usage_counts_dialog("1girl")

    assert captured["canonical"] == "1girl"
    assert captured["counts"] == {"danbooru": 1234000, "e621": 500}


def test_usage_counts_dialog_no_data_placeholder(qtbot):
    """usage count が無い canonical では「使用頻度データなし」を表示する。"""
    dialog = tpw.UsageCountsDialog("solo", {})
    qtbot.addWidget(dialog)
    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert "使用頻度データなし" in labels


def test_usage_counts_dialog_formats_counts(qtbot):
    """format 別 count が K/M 整形されて表示される。"""
    dialog = tpw.UsageCountsDialog("1girl", {"danbooru": 1234000, "e621": 500})
    qtbot.addWidget(dialog)
    labels = [w.text() for w in dialog.findChildren(QLabel)]
    assert "1.2M" in labels
    assert "500" in labels


# ⑭ refinement 修正候補を適用 (タグ置換 / refine.suggest, #1007) ----------------


def _make_recommendation(source_tag: str, suggestion_tags: list[str | None], kinds: list[str]):
    """correction_candidate / review_only を混在させた RefinementRecommendation を作る。"""
    from genai_tag_db_tools.models import (
        RefinementReason,
        RefinementRecommendation,
        RefinementSuggestion,
    )

    return RefinementRecommendation(
        source_tag=source_tag,
        normalized_tag=source_tag,
        needs_refinement=True,
        score=0.8,
        reasons=[RefinementReason(code="alias_tag", message="alias です")],  # type: ignore[arg-type]
        suggestions=[
            RefinementSuggestion(kind=kind, tag=tag)  # type: ignore[arg-type]
            for kind, tag in zip(kinds, suggestion_tags, strict=True)
        ],
        proposals=[],
    )


class _CapturingMenu(tpw.QMenu):
    """exec をブロックせず、生成されたメニューを検査できるようにする。"""

    instances: ClassVar[list[_CapturingMenu]] = []

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        _CapturingMenu.instances.append(self)

    def exec(self, *args, **kwargs):
        return None


@pytest.fixture
def capture_menu(monkeypatch):
    _CapturingMenu.instances = []
    monkeypatch.setattr(tpw, "QMenu", _CapturingMenu)
    return _CapturingMenu


def _context_menu_actions(chip) -> list[str]:
    """chip の contextMenuEvent を発火し、生成されたメニューのアクション文言を返す。"""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent

    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(0, 0), QPoint(0, 0))
    chip.contextMenuEvent(event)
    menu = _CapturingMenu.instances[-1]
    return [action.text() for action in menu.actions() if action.text()]


def test_chip_replacement_candidates_dedup_and_exclude_self():
    """correction_candidate の tag を重複排除し、自分自身と None を除外する (#1007)。"""
    chip = SelectableTagChip("1girl", "1girl")
    rec = _make_recommendation(
        "1girl",
        ["1boy", None, "1boy", "1girl", "solo"],
        [
            "correction_candidate",
            "review_only",
            "correction_candidate",
            "correction_candidate",
            "correction_candidate",
        ],
    )
    chip.set_refinement(rec)
    assert chip.replacement_candidates() == ["1boy", "solo"]


def test_apply_menu_action_emits_refinement_apply_requested(panel, sample_tags, capture_menu, qtbot):
    """編集モード時、右クリックメニューの「修正候補を適用」で (canonical, to_tag) を出す。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_refinements({"1girl": _make_recommendation("1girl", ["1boy"], ["correction_candidate"])})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert "修正候補を適用: 1boy" in actions

    menu = capture_menu.instances[-1]
    apply_action = next(a for a in menu.actions() if a.text() == "修正候補を適用: 1boy")
    with qtbot.waitSignal(chip.refinement_apply_requested, timeout=1000) as blocker:
        apply_action.trigger()
    assert blocker.args == ["1girl", "1boy"]


def test_apply_menu_absent_when_edit_disabled(panel, sample_tags, capture_menu):
    """read-only モードでは「修正候補を適用」をメニューに出さない (image DB 書き込みのため)。"""
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_refinements({"1girl": _make_recommendation("1girl", ["1boy"], ["correction_candidate"])})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert not any(a.startswith("修正候補を適用") for a in actions)
    # ignore 等の既存メニューは出続ける
    assert any(a.startswith("この理由を無視") for a in actions)


def test_apply_menu_absent_on_disabled_chip(panel, sample_tags, capture_menu):
    """無効化 (破線) 済み chip では適用を出さない (置換経路は rejected 行を対象にしない)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    panel._tag_chips[0].clicked.emit()  # 1girl を無効化
    panel.apply_refinements({"1girl": _make_recommendation("1girl", ["1boy"], ["correction_candidate"])})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert not any(a.startswith("修正候補を適用") for a in actions)


def test_apply_menu_absent_without_correction_candidate(panel, sample_tags, capture_menu):
    """review_only のみの警告では適用メニューを出さない。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_refinements({"1girl": _make_recommendation("1girl", [None], ["review_only"])})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert not any(a.startswith("修正候補を適用") for a in actions)


def test_panel_relays_apply_to_tag_replace_requested(panel, sample_tags, qtbot):
    """chip の適用要求が panel の tag_replace_requested(from, to) へ中継される (#1007)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    with qtbot.waitSignal(panel.tag_replace_requested, timeout=1000) as blocker:
        chip.refinement_apply_requested.emit("1girl", "1boy")
    assert blocker.args == ["1girl", "1boy"]


# チップ箱サイジング (#1025) --------------------------------------------------


def _shown_panel(qtbot, width: int = 400) -> TagPanelWidget:
    """表示済み (レイアウト有効) の TagPanelWidget を返す。"""
    w = TagPanelWidget()
    qtbot.addWidget(w)
    w.resize(width, 600)
    w.show()
    qtbot.waitExposed(w)
    return w


def _many_tags(count: int) -> list[dict]:
    return [
        {"tag": f"tag_{i}_long_name_example", "tag_id": i + 1, "model_name": "wd", "source": "AI"}
        for i in range(count)
    ]


def test_chip_box_has_no_empty_scroll_region(qtbot):
    """チップ実高に箱が収まるとき空白スクロール領域が出ない (#1025)。

    従来は container の縦 SizePolicy Minimum により FlowLayout sizeHint
    (sizeHint 幅で全チップ縦積みの過大値) が最小高さとして固定され、実チップ高との
    差が空白スクロールになっていた。
    """
    panel = _shown_panel(qtbot)
    panel.set_tag_edit_enabled(True)
    panel.set_tags(_many_tags(4), image_id=1)
    panel.set_rejected_tags([{"tag": "blue flowers", "reject_reason": "not_needed"}])

    vbar = panel._tags_scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: vbar.maximum() == 0, timeout=2000)
    width = panel._tags_scroll.viewport().width()
    hfw = panel._tags_chip_layout.heightForWidth(width)
    # 箱は実必要高さ+8 (上限内)、container は箱内に収まりスクロール不要
    assert panel._tags_scroll.height() == hfw + 8
    assert vbar.maximum() == 0


def test_chip_box_not_collapsed_right_after_rerender(qtbot):
    """chip 再構築直後 (activation 前) でも箱が 8px に潰れない (#1025)。

    新チップが hidden のまま QWidgetItem.sizeHint()=(0,0) となり
    heightForWidth=0 → setFixedHeight(8) になる timing バグのリグレッション。
    """
    panel = _shown_panel(qtbot)
    panel.set_tag_edit_enabled(True)
    panel.set_tags(_many_tags(4), image_id=1)

    # set_tags 直後 (イベントループ処理前) の同期計測で潰れていないこと
    assert panel._tags_scroll.height() > 8


def test_chip_box_scroll_range_matches_actual_flowed_height(qtbot):
    """多数タグで上限 220px に収まるとき、スクロール量は実折り返し高さと一致する (#1025)。"""
    panel = _shown_panel(qtbot)
    panel.set_tag_edit_enabled(True)
    panel.set_tags(_many_tags(40), image_id=1)

    scroll = panel._tags_scroll
    qtbot.waitUntil(lambda: scroll.height() == TagPanelWidget._TAGS_MAX_HEIGHT, timeout=2000)
    width = scroll.viewport().width()
    hfw = panel._tags_chip_layout.heightForWidth(width)
    container = panel._tags_chip_container
    qtbot.waitUntil(lambda: container.height() == max(hfw, scroll.viewport().height()), timeout=2000)
    # container が sizeHint (縦積み過大値) でなく実折り返し高さになっている
    vbar = scroll.verticalScrollBar()
    assert vbar.maximum() == container.height() - scroll.viewport().height()


def test_chip_box_shrinks_when_tags_decrease(qtbot):
    """タグ数が減ったら箱の高さも追従して縮む (#1025)。"""
    panel = _shown_panel(qtbot)
    panel.set_tag_edit_enabled(True)
    panel.set_tags(_many_tags(40), image_id=1)
    qtbot.waitUntil(lambda: panel._tags_scroll.height() == TagPanelWidget._TAGS_MAX_HEIGHT, timeout=2000)

    panel.set_tags(_many_tags(2), image_id=2)

    qtbot.waitUntil(lambda: panel._tags_scroll.height() < 60, timeout=2000)
    assert panel._tags_scroll.verticalScrollBar().maximum() == 0


def test_set_tags_image_change_without_types_resets_type_map(panel):
    """#1056 Codex P2: 別画像で tag_types 省略時は前画像の type map を引き継がない。"""
    panel.set_tags(
        [{"tag": "hatsune miku", "tag_id": 3, "model_name": "wd", "source": "AI"}],
        image_id=1,
        tag_types={"hatsune miku": "character"},
    )

    # 別画像 (image_id=2) では type 情報無し → 全タグ末尾グループ = 純アルファベット順
    panel.set_tags(
        [
            {"tag": "zzz tag", "tag_id": 5, "model_name": "wd", "source": "AI"},
            {"tag": "hatsune miku", "tag_id": 3, "model_name": "wd", "source": "AI"},
        ],
        image_id=2,
    )

    assert panel._tag_types == {}
    assert [c.canonical for c in panel._tag_chips] == ["hatsune miku", "zzz tag"]


# #1050: 翻訳登録ダイアログの言語選択は固定ドロップダウン --------------------


def test_translation_dialog_language_choices_are_fixed(qtbot):
    """自由入力は廃止し、候補は 日本語/English の固定2択 (Issue #1050)。"""
    dialog = TranslationAddDialog("1girl", ["japanese", "zh", "whatever"])
    qtbot.addWidget(dialog)

    assert dialog._language_combo.isEditable() is False
    labels = [dialog._language_combo.itemText(i) for i in range(dialog._language_combo.count())]
    assert labels == ["日本語", "English"]


def test_translation_dialog_language_returns_normalized_code(qtbot):
    """表示は人間向けラベル、保存値は ja / en に正規化される (Issue #1050)。"""
    dialog = TranslationAddDialog("1girl", [])
    qtbot.addWidget(dialog)

    dialog._language_combo.setCurrentIndex(0)
    assert dialog.language() == "ja"

    dialog._language_combo.setCurrentIndex(1)
    assert dialog.language() == "en"
