"""TagPanelWidget 単体テスト (ADR 0083 / Issue #987)。

DB / service 非依存の生成、chip 描画、soft-reject 一本のタグ操作モデル
(単クリック無効化トグル / ✕ で外す / Ctrl+クリック選択コピー)、手動タグ追加、
refinement ignore の Signal 配線を検証する。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QToolButton

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


# ③ 単クリックで reject 発火 + 破線化 ----------------------------------------


def test_single_click_emits_reject_and_dashes_chip(panel, sample_tags, qtbot):
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    chip = panel._tag_chips[0]

    with qtbot.waitSignal(panel.tag_reject_requested, timeout=1000) as blocker:
        chip.clicked.emit()
    assert blocker.args == ["1girl"]
    # 当該 chip は破線スタイル (無効化インライン表示) になる
    assert chip.styleSheet() == theme.tag_chip_untranslated_qss()
    assert "1girl" in panel._disabled_display


def test_single_click_noop_when_edit_disabled(panel, sample_tags):
    """編集モード無効時は単クリックで reject を出さない (read-only)。"""
    panel.set_tags(sample_tags)
    received: list[str] = []
    panel.tag_reject_requested.connect(received.append)
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


def test_remove_button_emits_reject_and_hides_chip(panel, sample_tags, qtbot):
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags)
    buttons = panel.findChildren(QToolButton, "tagRejectButton")
    assert len(buttons) == 3

    with qtbot.waitSignal(panel.tag_reject_requested, timeout=1000) as blocker:
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
    panel.tag_reject_requested.connect(rejected.append)

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


def test_set_rejected_tags_renders_inline_dashed_restore_chip(panel, qtbot):
    """soft-rejected はインライン破線 chip で表示し、クリックで復活する。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags([{"tag": "1girl", "tag_id": 10}])
    panel.set_rejected_tags(["bad_tag"])

    rejected_chip = next((c for c in panel._tag_chips if c.canonical == "bad_tag"), None)
    assert rejected_chip is not None
    assert rejected_chip.styleSheet() == theme.tag_chip_untranslated_qss()
    with qtbot.waitSignal(panel.tag_restore_requested, timeout=1000) as blocker:
        rejected_chip.clicked.emit()
    assert blocker.args == ["bad_tag"]


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
    """✕ で外したタグは同一画像の reject reload 後も非表示を維持する (PR #992 Codex P2)。

    ✕ → tag_reject_requested が同期で親へ届き、親が同一画像を reload して
    set_tags / set_rejected_tags を呼び戻す。この同一画像 reload で _hidden が
    クリアされると、外したタグが破線復活 chip として即座に再出現してしまう。
    image_id が変わらない限り非表示状態を保持すること。
    """
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=10)
    panel._on_chip_removed("1girl")
    assert "1girl" in panel._hidden

    # 同一画像の reject reload: 1girl は active から消え rejected へ移る
    remaining = [t for t in sample_tags if t["tag"] != "1girl"]
    panel.set_tags(remaining, image_id=10)
    panel.set_rejected_tags(["1girl"])

    assert "1girl" in panel._hidden
    assert "1girl" not in [chip.canonical for chip in panel._tag_chips]


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
        dialog._language_combo.setCurrentText("ja")
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
        dialog._language_combo.setCurrentText("ja")
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
