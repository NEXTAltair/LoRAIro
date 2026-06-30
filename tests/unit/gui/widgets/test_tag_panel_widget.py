"""TagPanelWidget 単体テスト (ADR 0083 / Issue #987)。

DB / service 非依存の生成、chip 描画、soft-reject 一本のタグ操作モデル
(単クリック無効化トグル / ✕ で外す / Ctrl+クリック選択コピー)、手動タグ追加、
refinement ignore の Signal 配線を検証する。
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QToolButton

from lorairo.gui import theme
from lorairo.gui.widgets.tag_panel_widget import SelectableTagChip, TagPanelWidget

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
