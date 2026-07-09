"""TagPanelWidget 単体テスト (ADR 0083 / Issue #987)。

DB / service 非依存の生成、chip 描画、soft-reject 一本のタグ操作モデル
(単クリック無効化トグル / ✕ で外す / Ctrl+クリック選択コピー)、手動タグ追加、
refinement ignore の Signal 配線を検証する。
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QPushButton, QToolButton

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
    """#1056/#1233/#1241: character→copyright→artist→meta→general のグループ順
    (Issue #1233/#1241 デザイン確定 SSoT) + グループ内 canonical アルファベット順。
    """
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
        "absurdres",  # meta
        "1girl",  # general (アルファベット順)
        "zzz effect",  # general
    ]


def test_set_tags_unknown_type_goes_to_trailing_group(panel):
    """#1056: type が引けないタグ (tagdb 未登録等) は末尾グループに寄せる (ユーザー決定)。

    #1233/#1241 で meta→general の順に統一したため、meta は general より先に並ぶ。
    """
    tags = [
        {"tag": "aaa unknown", "tag_id": None, "model_name": "wd", "source": "AI"},
        {"tag": "zzz meta", "tag_id": 5, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    tag_types = {"1girl": "general", "zzz meta": "meta"}

    panel.set_tags(tags, tag_types=tag_types)

    assert [c.canonical for c in panel._tag_chips] == ["zzz meta", "1girl", "aaa unknown"]


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

    received: list[tuple[str, str, bool]] = []
    panel.refinement_ignored.connect(lambda c, r, s: received.append((c, r, s)))
    # chip の「無視」(スコープ付き #1053) を発火 → パネル signal へ中継されること
    chip.refinement_ignore_requested.emit("1girl", "broad_single_word", False)
    assert received == [("1girl", "broad_single_word", False)]


# refinement 適用の重複排除 (#1221) --------------------------------------------


def _broad_rec(tag: str):
    """needs_refinement=True の最小 RefinementRecommendation を作る (#1221)。"""
    from genai_tag_db_tools.models import RefinementReason, RefinementRecommendation

    return RefinementRecommendation(
        source_tag=tag,
        normalized_tag=tag,
        needs_refinement=True,
        score=0.7,
        reasons=[RefinementReason(code="broad_single_word", message="broad")],  # type: ignore[arg-type]
        suggestions=[],
        proposals=[],
    )


def test_selection_burst_skips_empty_refinement_reapply(panel, sample_tags, monkeypatch):
    """refinement 未確定の選択バーストでは chip への適用ループを走らせない (#1221)。

    親は 1 選択で set_tags / set_rejected_tags / set_tag_metadata_pending を順に呼び、
    各々が chip を再生成する。refinement が未確定 (空) の間は「印なし」を無印 chip へ
    適用するだけの no-op なので、1 回も set_refinement しないことを検証する。
    """
    calls: list[str] = []
    original = SelectableTagChip.set_refinement

    def spy(self, recommendation, candidate_counts=None):
        calls.append(self.canonical)
        original(self, recommendation, candidate_counts)

    monkeypatch.setattr(SelectableTagChip, "set_refinement", spy)

    panel.set_tags(sample_tags)
    panel.set_rejected_tags([])
    panel.set_tag_metadata_pending(True)

    assert calls == []


def test_refinement_confirmed_applies_once_and_survives_rerender(panel, sample_tags, monkeypatch):
    """refinement 確定時は 1 回だけ全 chip へ適用し、再描画後も ⚠ が保持される (#1221)。"""
    panel.set_tags(sample_tags)
    panel.set_tag_metadata_pending(True)  # 未確定バースト (適用は走らない)

    calls: list[str] = []
    original = SelectableTagChip.set_refinement

    def spy(self, recommendation, candidate_counts=None):
        calls.append(self.canonical)
        original(self, recommendation, candidate_counts)

    monkeypatch.setattr(SelectableTagChip, "set_refinement", spy)

    panel.apply_refinements({"1girl": _broad_rec("1girl")})
    # 確定した refinements を全 chip へ 1 巡だけ適用する。
    assert calls == ["1girl", "flower", "solo"]

    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert chip.text().startswith("⚠")

    # chip を再生成する経路 (metadata 反映) でも fresh chip へ ⚠ が復元される。
    panel.apply_tag_metadata({}, {}, {})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert chip.text().startswith("⚠")


def test_clearing_refinements_removes_marker(panel, sample_tags):
    """確定済み ⚠ を空 refinements で消す再適用は従来どおり実行される (#1221)。"""
    panel.set_tags(sample_tags)
    panel.apply_refinements({"1girl": _broad_rec("1girl")})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert chip.text().startswith("⚠")

    panel.apply_refinements({})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert not chip.text().startswith("⚠")


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


# 翻訳キャッシュ + 解決中表示 (#1191) ----------------------------------------


def test_translations_survive_image_switch_phase1(panel, sample_tags):
    """phase 1 (translations 未解決) の画像切替でも既出タグの訳を保持する (#1191)。"""
    translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
    panel.set_tags(sample_tags, translations, ["japanese"], image_id=1)
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")

    # 別画像の phase 1: translations 未解決 (None) で set_tags されても英語へ巻き戻らない
    panel.set_tags(sample_tags, None, ["japanese"], image_id=2)

    assert [c.text() for c in panel._tag_chips] == ["1人の女の子", "花", "solo"]


def test_apply_tag_metadata_removes_stale_translation_for_current_tags(panel, sample_tags):
    """worker 結果に無い表示中 tag_id の訳はキャッシュから退避する (#1191)。"""
    panel.set_tags(sample_tags, {10: {"japanese": "1人の女の子"}}, ["japanese"], image_id=1)
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")

    panel.apply_tag_metadata({20: {"japanese": "花"}}, {}, {})

    assert 10 not in panel._translations
    assert panel._translations[20] == {"japanese": "花"}


def test_pending_untranslated_chip_shows_resolving_not_missing(panel, sample_tags):
    """解決中は未訳 chip を「翻訳なし」(点線) でなく「解決中」として表示する (#1191)。"""
    panel.set_tags(sample_tags, None, ["japanese"], image_id=1)
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")
    panel.set_tag_metadata_pending(True)

    chip = panel._tag_chips[0]
    assert not getattr(chip, "untranslated", False)
    assert "翻訳解決中" in chip.toolTip()
    assert "翻訳解決中" in panel._tags_translation_note.text()

    # worker 完了 (訳なし確定) で通常の「翻訳なし」点線表示へ戻る
    panel.apply_tag_metadata({}, {}, {})
    chip = panel._tag_chips[0]
    assert getattr(chip, "untranslated", False)
    assert "翻訳なし" in chip.toolTip()
    assert "点線 = 翻訳なし" in panel._tags_translation_note.text()


def test_pending_false_on_failure_restores_missing_style(panel, sample_tags):
    """失敗/キャンセル終端の pending 解除で「翻訳なし」確定表示へ戻す (#1191)。"""
    panel.set_tags(sample_tags, None, ["japanese"], image_id=1)
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentText("japanese")
    panel.set_tag_metadata_pending(True)
    panel.set_tag_metadata_pending(False)

    chip = panel._tag_chips[0]
    assert getattr(chip, "untranslated", False)
    assert "翻訳なし" in chip.toolTip()


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


def test_chip_right_click_does_not_emit_clicked(qtbot, monkeypatch):
    """右クリックは clicked / ctrl_clicked を emit しない (#1223 バグA 回帰防止)。

    chip の左クリック = 無効化トグル (soft-reject 誘発)。右クリックが誤って clicked を
    出すと「コンテキストメニュー狙いの右クリックでタグが消える」データ破壊的誤操作になる。
    従来テストは chip.clicked.emit() の直接呼び出し / contextMenuEvent の直接呼び出しのみで、
    実クリック経由の button 振り分け配線 (mousePressEvent が LeftButton のみ clicked を出す)
    の regression を検出できなかった。menu.exec() のネストループはテストをブロックするため
    monkeypatch で無効化する。
    """
    monkeypatch.setattr(QMenu, "exec", lambda self, *a, **k: None)
    chip = SelectableTagChip("display", "canonical")
    qtbot.addWidget(chip)
    fired: list[str] = []
    chip.clicked.connect(lambda: fired.append("clicked"))
    chip.ctrl_clicked.connect(lambda: fired.append("ctrl"))

    qtbot.mouseClick(chip, Qt.MouseButton.RightButton)

    assert fired == []


def test_chip_left_click_emits_clicked(qtbot):
    """左クリックは clicked を emit する (右クリックとの対比、#1223 バグA)。"""
    chip = SelectableTagChip("display", "canonical")
    qtbot.addWidget(chip)
    fired: list[str] = []
    chip.clicked.connect(lambda: fired.append("clicked"))

    qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)

    assert fired == ["clicked"]


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


def test_translation_manage_dialog_lists_candidates_and_marks_preferred(qtbot):
    """候補訳をラジオ表示し、現在の主訳を選択済み + 「(主訳)」で明示する (#1084)。"""
    dialog = TranslationAddDialog("blue_eyes", lambda language: (["青い目", "青目"], "青目"))
    qtbot.addWidget(dialog)
    assert dialog.current_preferred() == "青目"
    assert dialog.selected_candidate() == "青目"
    labels = [radio.text() for radio in dialog._radio_values]
    assert "青目（主訳）" in labels
    assert "青い目" in labels


def test_translation_manage_dialog_includes_preferred_outside_candidates(qtbot):
    """主訳が候補一覧に無くても選択肢へ含め、選択済みにする (#1084)。"""
    dialog = TranslationAddDialog("tag", lambda language: (["a"], "b"))
    qtbot.addWidget(dialog)
    assert "b" in dialog._radio_values.values()
    assert dialog.selected_candidate() == "b"


def test_translation_manage_dialog_reloads_on_language_change(qtbot):
    """言語切替で provider を引き直し候補・主訳を作り直す (#1084)。"""
    calls: list[str] = []

    def provider(language: str) -> tuple[list[str], str | None]:
        calls.append(language)
        return {"ja": (["日本語訳"], "日本語訳"), "en": (["english_tr"], None)}[language]

    dialog = TranslationAddDialog("tag", provider)
    qtbot.addWidget(dialog)
    assert dialog.current_preferred() == "日本語訳"
    dialog._language_combo.setCurrentIndex(1)  # English
    assert dialog.language() == "en"
    assert dialog.current_preferred() is None
    assert calls == ["ja", "en"]


def test_translation_manage_dialog_no_provider_shows_no_candidates(qtbot):
    """provider 未注入なら候補なしで開ける (#1084)。"""
    dialog = TranslationAddDialog("tag")
    qtbot.addWidget(dialog)
    assert dialog._radio_values == {}
    assert dialog.selected_candidate() is None


def test_translation_manage_dialog_async_provider_loads_without_blocking(qtbot):
    """#1232: 非同期 provider があると構築時に同期呼びせず、完了 callback で候補が埋まる。"""
    pending: dict[str, object] = {}

    def async_provider(language, on_result):
        # 即座に候補を返さず callback を保持 = 構築時にブロックしない (読み込み中状態)。
        pending["language"] = language
        pending["cb"] = on_result

    dialog = TranslationAddDialog("blue_eyes", None, async_candidates_provider=async_provider)
    qtbot.addWidget(dialog)
    # 完了前は候補ラジオ未生成 (読み込み中プレースホルダのみ)。
    assert dialog._radio_values == {}
    assert pending["language"] == "ja"

    # worker 完了を模して callback を呼ぶと候補が反映される。
    pending["cb"](["青い目", "青目"], "青目")
    assert dialog.selected_candidate() == "青目"
    labels = [radio.text() for radio in dialog._radio_values]
    assert "青目（主訳）" in labels
    assert "青い目" in labels


def test_translation_manage_dialog_async_takes_precedence_over_sync(qtbot):
    """#1232: 非同期 provider があれば同期 provider は呼ばれない。"""
    sync_calls: list[str] = []

    def sync_provider(language):
        sync_calls.append(language)
        return (["sync"], "sync")

    def async_provider(language, on_result):
        on_result(["async"], "async")  # 即時完了を模す

    dialog = TranslationAddDialog("tag", sync_provider, async_candidates_provider=async_provider)
    qtbot.addWidget(dialog)
    assert sync_calls == []
    assert dialog.selected_candidate() == "async"


def test_translation_manage_dialog_async_stale_result_ignored(qtbot):
    """#1232: 言語切替で世代が進むと、古い非同期結果は反映しない (single-flight)。"""
    captured: list[tuple[str, object]] = []

    def async_provider(language, on_result):
        captured.append((language, on_result))

    dialog = TranslationAddDialog("tag", None, async_candidates_provider=async_provider)
    qtbot.addWidget(dialog)
    _, first_cb = captured[0]

    dialog._language_combo.setCurrentIndex(1)  # 言語切替で新しい取得 (世代 +1)

    # 古い取得の結果が後から来ても無視される。
    first_cb(["stale"], "stale")
    assert dialog.selected_candidate() is None

    # 新しい取得の結果は反映される。
    _, second_cb = captured[1]
    second_cb(["新訳"], "新訳")
    assert dialog.selected_candidate() == "新訳"


def test_translation_preferred_emitted_on_radio_change(panel, sample_tags, qtbot, monkeypatch):
    """新規入力なし + ラジオ選択が現主訳と異なる → translation_preferred_requested (#1084)。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.set_translation_candidates_provider(lambda canonical, language: (["青い目", "青目"], "青目"))

    def choose(dialog):
        for radio, value in dialog._radio_values.items():
            if value == "青い目":
                radio.setChecked(True)

    _accept_dialog(monkeypatch, "TranslationAddDialog", choose)
    with qtbot.waitSignal(panel.translation_preferred_requested, timeout=1000) as blocker:
        panel._open_translation_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "青い目"]


def test_translation_manage_no_op_when_radio_unchanged(panel, sample_tags, monkeypatch):
    """主訳を変えず新規入力もなければ何も emit しない (#1084)。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.set_translation_candidates_provider(lambda canonical, language: (["青い目", "青目"], "青目"))
    _accept_dialog(monkeypatch, "TranslationAddDialog", lambda dialog: None)  # 現主訳のまま
    received: list = []
    panel.translation_preferred_requested.connect(lambda *a: received.append(("pref", *a)))
    panel.translation_add_requested.connect(lambda *a: received.append(("add", *a)))
    panel._open_translation_dialog("1girl")
    assert received == []


def test_translation_add_takes_priority_over_radio(panel, sample_tags, qtbot, monkeypatch):
    """新規入力があれば主訳選択より優先して translation_add_requested を出す (#1084)。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.set_translation_candidates_provider(lambda canonical, language: (["青い目"], "青い目"))

    def fill(dialog):
        dialog._translation_input.setText("新訳")

    _accept_dialog(monkeypatch, "TranslationAddDialog", fill)
    with qtbot.waitSignal(panel.translation_add_requested, timeout=1000) as blocker:
        panel._open_translation_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "新訳"]


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


def test_type_edit_unchanged_type_skips_emit(panel, sample_tags, monkeypatch):
    """現在 type を初期選択したまま無変更確定しても emit しない (#1255 バグ1 回帰防止)。

    バグ1 修正で current_type を初期選択するようにしたため、無変更確定でも emit すると
    冗長な userdb 書き込み + refinement 再実行が走る (Codex P2)。値が変わらなければ skip。
    """
    panel.set_tags(sample_tags, image_id=10)
    panel._tag_types["1girl"] = "character"

    # field_setter なし = 初期選択 (current_type="character") のまま Accepted。
    _accept_dialog(monkeypatch, "TagTypeEditDialog", lambda dialog: None)
    received: list = []
    panel.tag_metadata_edit_requested.connect(lambda *a: received.append(a))
    panel._open_type_edit_dialog("1girl")
    assert received == []


def test_type_edit_changed_type_emits(panel, sample_tags, qtbot, monkeypatch):
    """現在 type から別 type に変更して確定すれば emit する (#1255 バグ1)。"""
    panel.set_tags(sample_tags, image_id=10)
    panel._tag_types["1girl"] = "character"

    def fill(dialog):
        dialog._type_combo.setCurrentText("copyright")

    _accept_dialog(monkeypatch, "TagTypeEditDialog", fill)
    with qtbot.waitSignal(panel.tag_metadata_edit_requested, timeout=1000) as blocker:
        panel._open_type_edit_dialog("1girl")
    assert blocker.args == ["1girl", "copyright"]


def test_type_edit_dialog_receives_current_type(panel, sample_tags, monkeypatch):
    """既存タグの type 補正時、現在の type が current_type として渡る (#1255 バグ1)。

    以前は _open_type_edit_dialog が current_type を渡さず常にプレースホルダ表示となり、
    既存タグの現在の種別が絶対に見えなかった。self._tag_types から引いて渡すことを検証する。
    """
    panel.set_tags(sample_tags, image_id=10)
    panel._tag_types["1girl"] = "character"

    captured: dict[str, str | None] = {}
    original = tpw.TagTypeEditDialog

    class _CapturingDialog(original):
        def __init__(self, *args, current_type=None, **kwargs):
            captured["current_type"] = current_type
            super().__init__(*args, current_type=current_type, **kwargs)

        def exec(self):
            return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(tpw, "TagTypeEditDialog", _CapturingDialog)
    panel._open_type_edit_dialog("1girl")
    assert captured["current_type"] == "character"


def test_type_edit_dialog_current_type_none_when_unknown(panel, sample_tags, monkeypatch):
    """_tag_types に無い canonical は current_type=None で渡る (#1255 バグ1)。"""
    panel.set_tags(sample_tags, image_id=10)

    captured: dict[str, str | None] = {}
    original = tpw.TagTypeEditDialog

    class _CapturingDialog(original):
        def __init__(self, *args, current_type=None, **kwargs):
            captured["current_type"] = current_type
            super().__init__(*args, current_type=current_type, **kwargs)

        def exec(self):
            return int(QDialog.DialogCode.Rejected)

    monkeypatch.setattr(tpw, "TagTypeEditDialog", _CapturingDialog)
    panel._open_type_edit_dialog("1girl")
    assert captured["current_type"] is None


def test_translation_dialog_returns_inputs(qtbot):
    """TranslationAddDialog が言語・翻訳の入力値を返す。"""
    dialog = TranslationAddDialog("1girl")
    qtbot.addWidget(dialog)
    dialog._language_combo.setCurrentText("日本語")
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


def test_type_dialog_accepts_custom_type(qtbot):
    """#1234: combo は editable で、danbooru 標準 5 種以外の独自 type も入力できる。"""
    dialog = TagTypeEditDialog("1girl")
    qtbot.addWidget(dialog)
    assert dialog._type_combo.isEditable()

    dialog._type_combo.setCurrentText("my_custom_type")
    assert dialog.selected_type() == "my_custom_type"
    ok_button = dialog._buttons.button(dialog._buttons.StandardButton.Ok)
    assert ok_button.isEnabled()


def test_type_dialog_custom_type_whitespace_is_rejected(qtbot):
    """#1234: 空白のみの入力は未選択扱いで OK 無効・selected_type 空文字。"""
    dialog = TagTypeEditDialog("1girl")
    qtbot.addWidget(dialog)
    dialog._type_combo.setCurrentText("   ")
    assert dialog.selected_type() == ""
    ok_button = dialog._buttons.button(dialog._buttons.StandardButton.Ok)
    assert not ok_button.isEnabled()


def test_type_dialog_preselects_existing_custom_type(qtbot):
    """#1234: 既存の独自 type (5 種外) を current_type に渡すとサジェスト+初期選択される。"""
    dialog = TagTypeEditDialog("1girl", current_type="my_custom_type")
    qtbot.addWidget(dialog)
    assert dialog.selected_type() == "my_custom_type"
    choices = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
    assert "my_custom_type" in choices
    # プレースホルダは付かない (current_type があるため)。
    assert TagTypeEditDialog._PLACEHOLDER not in choices


def test_type_edit_dialog_emits_custom_type(panel, sample_tags, qtbot, monkeypatch):
    """#1234: 独自 type 入力で確定すると tag_metadata_edit_requested(canonical, custom) を出す。"""
    panel.set_tags(sample_tags, image_id=10)

    def fill(dialog):
        dialog._type_combo.setCurrentText("my_custom_type")

    _accept_dialog(monkeypatch, "TagTypeEditDialog", fill)
    with qtbot.waitSignal(panel.tag_metadata_edit_requested, timeout=1000) as blocker:
        panel._open_type_edit_dialog("1girl")
    assert blocker.args == ["1girl", "my_custom_type"]


# #1242 検索付き + 既存型グルーピング + 新規作成抑制 --------------------------


def test_type_dialog_groups_tagdb_and_custom_types(qtbot):
    """カスタム type 注入時、From tagdb / Your types の 2 グループで提示する (#1242)。"""
    dialog = TagTypeEditDialog("1girl", custom_type_names=["circle", "series"])
    qtbot.addWidget(dialog)
    choices = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
    assert choices == [
        TagTypeEditDialog._PLACEHOLDER,
        TagTypeEditDialog._FROM_TAGDB_HEADER,
        *TagTypeEditDialog.TYPE_CHOICES,
        TagTypeEditDialog._CUSTOM_HEADER,
        "circle",
        "series",
    ]
    # 見出し行は選択不可 (グループヘッダとして機能する)。
    model = dialog._type_combo.model()
    header_index = choices.index(TagTypeEditDialog._FROM_TAGDB_HEADER)
    header_item = model.item(header_index)
    assert not (header_item.flags() & Qt.ItemFlag.ItemIsSelectable)
    # custom type 行はバッジ描画用の role が立っている。
    custom_index = choices.index("circle")
    assert bool(model.item(custom_index).data(TagTypeEditDialog._CUSTOM_TYPE_ROLE))
    # tagdb 標準行はバッジ role が立たない。
    tagdb_index = choices.index("character")
    assert not bool(model.item(tagdb_index).data(TagTypeEditDialog._CUSTOM_TYPE_ROLE))


def test_type_dialog_no_custom_types_has_no_group_headers(qtbot):
    """カスタム type 未注入時は見出し無しの単一リストのまま (#1234 以前と同じ並び)。"""
    dialog = TagTypeEditDialog("1girl", custom_type_names=[])
    qtbot.addWidget(dialog)
    choices = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
    assert TagTypeEditDialog._FROM_TAGDB_HEADER not in choices
    assert TagTypeEditDialog._CUSTOM_HEADER not in choices
    assert choices == [TagTypeEditDialog._PLACEHOLDER, *TagTypeEditDialog.TYPE_CHOICES]


def test_type_dialog_custom_types_dedup_against_tagdb_case_insensitive(qtbot):
    """tagdb 標準と大小文字違いで重複するカスタム type は Your types に出さない (#1242)。"""
    dialog = TagTypeEditDialog("1girl", custom_type_names=["General", "circle", "circle"])
    qtbot.addWidget(dialog)
    choices = [dialog._type_combo.itemText(i) for i in range(dialog._type_combo.count())]
    # "General" (tagdb の "general" と case-insensitive 一致) は除外され、"circle" は1回だけ。
    assert choices.count("General") == 0
    assert choices.count("circle") == 1


def test_type_dialog_new_type_hint_shown_only_for_unknown_input(qtbot):
    """一致する既存 type が無い入力のときだけ新規作成ヒントを表示する (#1242)。"""
    dialog = TagTypeEditDialog("1girl", custom_type_names=["circle"])
    qtbot.addWidget(dialog)

    # 既知の tagdb 標準 type → ヒント非表示。
    dialog._type_combo.setCurrentText("character")
    assert not dialog._new_type_hint.isVisibleTo(dialog)

    # 既知のカスタム type → ヒント非表示。
    dialog._type_combo.setCurrentText("circle")
    assert not dialog._new_type_hint.isVisibleTo(dialog)

    # 大小文字違いでも既存一致とみなしヒント非表示 (case-insensitive)。
    dialog._type_combo.setCurrentText("Circle")
    assert not dialog._new_type_hint.isVisibleTo(dialog)

    # 未知の type → ヒント表示 + 対象 type 名を含む。
    dialog._type_combo.setCurrentText("brand_new_type")
    assert dialog._new_type_hint.isVisibleTo(dialog)
    assert "brand_new_type" in dialog._new_type_hint.text()

    # 空入力 (プレースホルダに戻す) → ヒント非表示。
    dialog._type_combo.setCurrentText(TagTypeEditDialog._PLACEHOLDER)
    assert not dialog._new_type_hint.isVisibleTo(dialog)


def test_type_dialog_completer_uses_contains_match_over_tagdb_and_custom(qtbot):
    """検索補完 (QCompleter) は tagdb 標準 + カスタム type から contains マッチする (#1242)。"""
    dialog = TagTypeEditDialog("1girl", custom_type_names=["circle"])
    qtbot.addWidget(dialog)
    completer = dialog._type_combo.completer()
    assert completer is not None
    assert completer.filterMode() == Qt.MatchFlag.MatchContains
    assert completer.caseSensitivity() == Qt.CaseSensitivity.CaseInsensitive
    completer.setCompletionPrefix("irc")
    completions = [
        completer.completionModel().data(completer.completionModel().index(i, 0))
        for i in range(completer.completionCount())
    ]
    assert "circle" in completions


def test_type_dialog_no_db_dependency(qtbot):
    """ダイアログは DB / service_container を一切持たない (ADR 0083 / #1242)。"""
    dialog = TagTypeEditDialog("1girl", custom_type_names=["circle"])
    qtbot.addWidget(dialog)
    assert not hasattr(dialog, "_reader")
    assert not hasattr(dialog, "_repo")
    assert not hasattr(dialog, "_service")
    assert not hasattr(dialog, "_db_manager")
    assert not hasattr(dialog, "_service_container")


def test_panel_type_choices_provider_injects_custom_types_into_dialog(panel, sample_tags, monkeypatch):
    """set_type_choices_provider で注入した候補が dialog の Your types へ反映される (#1242)。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.set_type_choices_provider(lambda: ["circle", "series"])

    captured: list[TagTypeEditDialog] = []

    def fill(dialog):
        captured.append(dialog)

    monkeypatch.setattr(tpw.TagTypeEditDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected))
    original_init = tpw.TagTypeEditDialog.__init__

    def capturing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        captured.append(self)

    monkeypatch.setattr(tpw.TagTypeEditDialog, "__init__", capturing_init)
    panel._open_type_edit_dialog("1girl")
    assert len(captured) == 1
    choices = [captured[0]._type_combo.itemText(i) for i in range(captured[0]._type_combo.count())]
    assert "circle" in choices
    assert "series" in choices


def test_panel_type_choices_provider_unset_opens_without_custom_types(panel, sample_tags, monkeypatch):
    """provider 未注入時は tagdb 標準のみ (Your types グループなし) で開く (#1242)。"""
    panel.set_tags(sample_tags, image_id=10)
    monkeypatch.setattr(tpw.TagTypeEditDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected))
    captured: list[TagTypeEditDialog] = []
    original_init = tpw.TagTypeEditDialog.__init__

    def capturing_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        captured.append(self)

    monkeypatch.setattr(tpw.TagTypeEditDialog, "__init__", capturing_init)
    panel._open_type_edit_dialog("1girl")
    assert len(captured) == 1
    choices = [captured[0]._type_combo.itemText(i) for i in range(captured[0]._type_combo.count())]
    assert TagTypeEditDialog._CUSTOM_HEADER not in choices


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


def test_edit_menu_actions_emit_replace_and_move_to_caption(
    panel, sample_tags, capture_menu, monkeypatch, qtbot
):
    """編集モード時、任意置換とキャプション移動の右クリック操作を出す (#1240)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    monkeypatch.setattr(tpw.QInputDialog, "getText", lambda *args, **kwargs: ("1boy", True))
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert "別のタグに置換…" in actions
    assert "キャプションに移動" in actions

    menu = capture_menu.instances[-1]
    replace_action = next(a for a in menu.actions() if a.text() == "別のタグに置換…")
    with qtbot.waitSignal(panel.tag_replace_requested, timeout=1000) as blocker:
        replace_action.trigger()
    assert blocker.args == ["1girl", "1boy"]

    move_action = next(a for a in menu.actions() if a.text() == "キャプションに移動")
    with qtbot.waitSignal(chip.tag_move_to_caption_requested, timeout=1000) as blocker:
        move_action.trigger()
    assert blocker.args == ["1girl"]


def test_apply_menu_absent_when_edit_disabled(panel, sample_tags, capture_menu):
    """read-only モードでは「修正候補を適用」をメニューに出さない (image DB 書き込みのため)。"""
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_refinements({"1girl": _make_recommendation("1girl", ["1boy"], ["correction_candidate"])})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert not any(a.startswith("修正候補を適用") for a in actions)
    assert "別のタグに置換…" not in actions
    assert "キャプションに移動" not in actions
    # ignore 等の既存メニューは出続ける (#1053 でスコープ別 2 アクション化)
    assert any(a.startswith("この画像でのみ無視") for a in actions)
    assert any(a.startswith("全画像で無視") for a in actions)


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


def test_panel_opens_arbitrary_replace_dialog(panel, sample_tags, monkeypatch, qtbot):
    """右クリックの任意置換入力を既存 tag_replace_requested(from, to) へ流す (#1240)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    monkeypatch.setattr(tpw.QInputDialog, "getText", lambda *args, **kwargs: ("1boy", True))

    with qtbot.waitSignal(panel.tag_replace_requested, timeout=1000) as blocker:
        panel._open_tag_replace_dialog("1girl")
    assert blocker.args == ["1girl", "1boy"]


def test_panel_relays_move_to_caption_requested(panel, sample_tags, qtbot):
    """chip の caption 移動要求が panel の signal として再公開される (#1240)。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=1)
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    with qtbot.waitSignal(panel.tag_move_to_caption_requested, timeout=1000) as blocker:
        chip.tag_move_to_caption_requested.emit("1girl")
    assert blocker.args == ["1girl"]


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


# #1052: refinement 候補にサイト別使用カウント併記 ----------------------------


def test_format_count_short():
    from lorairo.gui.widgets.tag_panel_widget import _format_count_short

    assert _format_count_short(1_200_000) == "1.2M"
    assert _format_count_short(1_000_000) == "1M"
    assert _format_count_short(800_000) == "800k"
    assert _format_count_short(1_500) == "1.5k"
    assert _format_count_short(300) == "300"


def test_format_candidate_label_with_and_without_counts():
    from lorairo.gui.widgets.tag_panel_widget import _format_candidate_label

    # counts は大きい順で併記
    assert (
        _format_candidate_label("cat", {"e621": 800_000, "danbooru": 1_200_000})
        == "cat (danbooru 1.2M / e621 800k)"
    )
    # 取得できない候補は名前のみ (欠損で表示を壊さない)
    assert _format_candidate_label("feline", None) == "feline"
    assert _format_candidate_label("feline", {}) == "feline"


def _make_refinement(canonical: str, candidates: list[str]):
    from genai_tag_db_tools.models import (
        RefinementReason,
        RefinementRecommendation,
        RefinementSuggestion,
    )

    return RefinementRecommendation(
        source_tag=canonical,
        normalized_tag=canonical,
        needs_refinement=True,
        score=0.9,
        reasons=[RefinementReason(code="alias_tag", message="alias です")],
        suggestions=[RefinementSuggestion(kind="correction_candidate", tag=tag) for tag in candidates],
    )


def test_refinement_tooltip_includes_candidate_counts(panel, sample_tags):
    """#1052: ⚠ ツールチップの「提案:」行に候補の使用カウントを併記する。"""
    panel.set_tags(sample_tags, image_id=10)
    rec = _make_refinement("1girl", ["cat", "feline"])

    panel.apply_refinements(
        {"1girl": rec},
        candidate_counts={"cat": {"danbooru": 1_200_000, "e621": 800_000}},
    )

    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    tooltip = chip.toolTip()
    assert "提案: cat (danbooru 1.2M / e621 800k), feline" in tooltip


def test_refinement_menu_label_includes_counts_but_emits_raw_tag(panel, sample_tags, qtbot):
    """#1052: 置換メニューのラベルに counts を併記しつつ、emit 値は raw タグのまま。"""
    panel.set_tag_edit_enabled(True)
    panel.set_tags(sample_tags, image_id=10)
    rec = _make_refinement("1girl", ["cat"])
    panel.apply_refinements({"1girl": rec}, candidate_counts={"cat": {"danbooru": 500}})

    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    # メニューを実表示せずラベル整形だけ検証する
    assert chip.replacement_candidates() == ["cat"]
    from lorairo.gui.widgets.tag_panel_widget import _format_candidate_label

    assert _format_candidate_label("cat", chip._candidate_counts.get("cat")) == "cat (danbooru 500)"

    with qtbot.waitSignal(chip.refinement_apply_requested, timeout=1000) as blocker:
        chip.refinement_apply_requested.emit("1girl", "cat")
    assert blocker.args == ["1girl", "cat"]


# #1050: 翻訳登録ダイアログの言語選択は固定ドロップダウン --------------------


def test_translation_dialog_language_choices_are_fixed(qtbot):
    """自由入力は廃止し、候補は 日本語/English の固定2択 (Issue #1050)。"""
    dialog = TranslationAddDialog("1girl")
    qtbot.addWidget(dialog)

    assert dialog._language_combo.isEditable() is False
    labels = [dialog._language_combo.itemText(i) for i in range(dialog._language_combo.count())]
    assert labels == ["日本語", "English"]


def test_translation_dialog_language_returns_normalized_code(qtbot):
    """表示は人間向けラベル、保存値は ja / en に正規化される (Issue #1050)。"""
    dialog = TranslationAddDialog("1girl")
    qtbot.addWidget(dialog)

    dialog._language_combo.setCurrentIndex(0)
    assert dialog.language() == "ja"

    dialog._language_combo.setCurrentIndex(1)
    assert dialog.language() == "en"


def test_translation_lookup_bridges_ja_and_japanese_keys(panel, sample_tags):
    """#1050 Codex P2: 正規化キー "ja" で保存した翻訳は legacy "japanese" 表示でも見える。"""
    panel.set_tags(
        sample_tags,
        translations={10: {"ja": "1人の女の子"}},
        available_languages=["japanese"],
        image_id=10,
    )

    panel._refresh_tags_for_language("japanese")

    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert chip.text().strip("⚠ ").strip() == "1人の女の子"


def test_update_language_selector_preserves_selection_and_adds_new_language(panel, sample_tags):
    """#1050 Codex P2: 新言語追加後の selector 更新は現在の選択を巻き戻さない。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.initialize_language_selector(["japanese"])
    panel._lang_combo.setCurrentIndex(panel._lang_combo.findText("japanese"))

    # 新言語 ko を追加 (#1235: en/english 族は sentinel と重複するため combo に出さない
    # ので、追加検証には別族の言語を使う)。
    panel.update_language_selector(["japanese", "ko"])

    labels = [panel._lang_combo.itemText(i) for i in range(panel._lang_combo.count())]
    assert labels == ["english", "japanese", "ko"]
    # 選択は japanese のまま (english へ巻き戻らない)
    assert panel._lang_combo.currentText() == "japanese"


def test_update_language_selector_switches_from_original_view_to_saved_language(panel, sample_tags):
    """#1050 Codex P2: 原文 (english) 表示中に登録した言語へ自動切替して即可視化する。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.initialize_language_selector(["japanese"])
    assert panel._current_language() == "english"

    # 原文 (english) 表示中に登録した ko へ自動切替 (#1235: en 族は sentinel に畳むため
    # 自動切替の検証には別族の言語を使う)。
    panel.update_language_selector(["japanese", "ko"], prefer="ko")

    assert panel._lang_combo.currentText() == "ko"


def test_language_selector_dedupes_alias_families(panel, sample_tags):
    """#1235: en/english 族は sentinel と重複、ja/japanese 族は 1 項目へ畳む。"""
    panel.set_tags(sample_tags, image_id=10)
    # DB 由来の distinct 値に en (english と衝突) と ja/japanese の混在があるケース。
    panel.initialize_language_selector(["en", "ja", "japanese", "ko"])

    labels = [panel._lang_combo.itemText(i) for i in range(panel._lang_combo.count())]
    # english sentinel + ja (japanese 族の代表短形) + ko。en は sentinel に畳む。
    assert labels == ["english", "ja", "ko"]


def test_language_selector_dedupes_via_update(panel, sample_tags):
    """#1235: update_language_selector 経路でも alias 族を畳む。"""
    panel.set_tags(sample_tags, image_id=10)
    panel.update_language_selector(["english", "en", "japanese"])

    labels = [panel._lang_combo.itemText(i) for i in range(panel._lang_combo.count())]
    assert labels == ["english", "japanese"]


def test_refinement_ignore_menu_emits_scope(panel, sample_tags, qtbot):
    """#1053: ⚠ メニューは「この画像でのみ無視」(True) と「全画像で無視」(False) を区別して emit する。"""
    panel.set_tags(sample_tags, image_id=10)
    rec = _make_refinement("1girl", [])
    panel.apply_refinements({"1girl": rec})
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    received: list = []
    panel.refinement_ignored.connect(lambda *a: received.append(a))

    chip.refinement_ignore_requested.emit("1girl", "alias_tag", True)
    chip.refinement_ignore_requested.emit("1girl", "alias_tag", False)

    assert received == [("1girl", "alias_tag", True), ("1girl", "alias_tag", False)]


# ⑯ 誤翻訳の修正導線 (#1054) ----------------------------------------------------


def _make_translation_reason_rec(canonical: str, codes: list[str]):
    from genai_tag_db_tools.models import RefinementReason, RefinementRecommendation

    return RefinementRecommendation(
        source_tag=canonical,
        normalized_tag=canonical,
        needs_refinement=True,
        score=0.5,
        reasons=[RefinementReason(code=code, message=code) for code in codes],
        suggestions=[],
        proposals=[],
    )


def test_translation_fix_dialog_lists_and_prefills(qtbot):
    """既存翻訳を一覧表示し、行選択で修正入力欄へプリフィルする。"""
    dialog = tpw.TranslationFixDialog("dress", {"ja": "连衣裙", "en": "dress"})
    qtbot.addWidget(dialog)

    assert dialog._table.rowCount() == 2
    dialog._table.selectRow(0)

    assert dialog.language() == "ja"
    assert dialog._translation_input.text() == "连衣裙"


def test_translation_fix_dialog_dedupes_alias_family_rows(panel, sample_tags, qtbot, monkeypatch):
    """#1236: 主訳 fan-out で ja/japanese 両キーに入った翻訳を 1 行へ畳んで表示する。

    _open_translation_fix_dialog は _translations dict を dedupe してから
    TranslationFixDialog へ渡すため、実データに無い 'japanese' の幻の行が出ない。
    """
    panel.set_tags(sample_tags, image_id=10)
    tag_id = sample_tags[0]["tag_id"]
    # fan-out された ja/japanese 両キー (同値) + en を投入。
    panel._translations = {tag_id: {"en": "dress", "ja": "ドレス", "japanese": "ドレス"}}

    captured: dict[str, list[str]] = {}

    class _StubDialog:
        def __init__(self, canonical, translations, parent=None):
            captured["languages"] = list(translations.keys())

        def exec(self):
            from PySide6.QtWidgets import QDialog

            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(tpw, "TranslationFixDialog", _StubDialog)
    panel._open_translation_fix_dialog(sample_tags[0]["tag"])

    # japanese は ja へ畳まれ、en/ja の 2 行のみ。
    assert captured["languages"] == ["en", "ja"]


def test_translation_fix_dialog_ok_requires_selection_and_text(qtbot):
    """OK は行選択 + 修正テキスト非空のときだけ有効。"""
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = tpw.TranslationFixDialog("dress", {"ja": "连衣裙"})
    qtbot.addWidget(dialog)
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)

    assert not ok.isEnabled()  # 未選択
    dialog._table.selectRow(0)
    assert ok.isEnabled()  # プリフィル済みで非空
    dialog._translation_input.setText("  ")
    assert not ok.isEnabled()  # 空白のみ
    dialog._translation_input.setText("ドレス")
    assert ok.isEnabled()


def test_translation_fix_menu_action_emits(capture_menu, qtbot):
    """右クリックメニュー「翻訳を修正…」で translation_fix_menu_requested(canonical) を出す。

    panel 経由の chip は signal が実ダイアログを開く slot に接続済みのため、
    単体 chip で trigger する (modal exec のハング防止)。
    """
    chip = SelectableTagChip("1girl", "1girl")
    qtbot.addWidget(chip)

    actions = _context_menu_actions(chip)
    assert "翻訳を修正…" in actions

    menu = capture_menu.instances[-1]
    fix_action = next(a for a in menu.actions() if a.text() == "翻訳を修正…")
    with qtbot.waitSignal(chip.translation_fix_menu_requested, timeout=1000) as blocker:
        fix_action.trigger()
    assert blocker.args == ["1girl"]


def test_translation_fix_menu_emphasized_on_translation_quality_reason(panel, sample_tags, capture_menu):
    """⚠ 翻訳品質 reason 付き chip では「翻訳を修正…」を ⚠ 付きラベルで直行導線にする。"""
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_refinements(
        {"1girl": _make_translation_reason_rec("1girl", ["wrong_language_translation"])}
    )
    chip = next(c for c in panel._tag_chips if c.canonical == "1girl")

    actions = _context_menu_actions(chip)
    assert "翻訳を修正 (⚠ 翻訳品質)…" in actions
    assert "翻訳を修正…" not in actions


def test_translation_fix_dialog_emits_translation_add_requested(panel, sample_tags, qtbot, monkeypatch):
    """修正確定で選択行と同一言語キーの translation_add_requested を出す (上書き登録)。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "连衣裙"}}, available_languages=["ja"], image_id=1)

    def fill(dialog):
        dialog._table.selectRow(0)
        dialog._translation_input.setText("ドレス")

    _accept_dialog(monkeypatch, "TranslationFixDialog", fill)
    with qtbot.waitSignal(panel.translation_add_requested, timeout=1000) as blocker:
        panel._open_translation_fix_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "ドレス"]


def test_translation_fix_without_existing_falls_back_to_add_dialog(panel, sample_tags, qtbot, monkeypatch):
    """既存翻訳が無いタグの修正要求は翻訳追加ダイアログへフォールバックする。"""
    panel.set_tags(sample_tags, image_id=1)

    def fill(dialog):
        dialog._language_combo.setCurrentIndex(0)  # 日本語 (保存値 ja)
        dialog._translation_input.setText("少女")

    _accept_dialog(monkeypatch, "TranslationAddDialog", fill)
    with qtbot.waitSignal(panel.translation_add_requested, timeout=1000) as blocker:
        panel._open_translation_fix_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "少女"]


def test_translation_fix_dialog_cancel_emits_nothing(panel, sample_tags, monkeypatch):
    """修正ダイアログのキャンセルでは Signal を出さない。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "连衣裙"}}, available_languages=["ja"], image_id=1)
    monkeypatch.setattr(tpw.TranslationFixDialog, "exec", lambda self: int(QDialog.DialogCode.Rejected))
    received: list = []
    panel.translation_add_requested.connect(lambda *a: received.append(a))
    panel._open_translation_fix_dialog("1girl")
    assert received == []


def test_translation_fix_dialog_delete_button_requires_selection(qtbot):
    """「この翻訳を削除」ボタンは行選択済みのときだけ有効。"""
    dialog = tpw.TranslationFixDialog("dress", {"ja": "连衣裙", "en": "dress"})
    qtbot.addWidget(dialog)

    assert not dialog._delete_button.isEnabled()  # 未選択
    dialog._table.selectRow(0)
    assert dialog._delete_button.isEnabled()


def test_translation_fix_dialog_delete_click_sets_delete_action(qtbot):
    """削除ボタン押下で action()="delete" になり、選択行の元翻訳を返す。"""
    dialog = tpw.TranslationFixDialog("dress", {"ja": "连衣裙", "en": "dress"})
    qtbot.addWidget(dialog)
    dialog._table.selectRow(0)

    dialog._on_delete_clicked()

    assert dialog.action() == "delete"
    assert dialog.language() == "ja"
    assert dialog.original_translation() == "连衣裙"


def test_translation_fix_dialog_emits_translation_delete_requested(panel, sample_tags, qtbot, monkeypatch):
    """削除確定 (確認ダイアログ Yes) で translation_delete_requested(canonical, lang, tr) を出す。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "连衣裙"}}, available_languages=["ja"], image_id=1)

    def fill(dialog):
        dialog._table.selectRow(0)
        dialog._on_delete_clicked()

    _accept_dialog(monkeypatch, "TranslationFixDialog", fill)
    monkeypatch.setattr(tpw.QMessageBox, "question", lambda *a, **k: tpw.QMessageBox.StandardButton.Yes)
    with qtbot.waitSignal(panel.translation_delete_requested, timeout=1000) as blocker:
        panel._open_translation_fix_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "连衣裙"]


def test_translation_fix_dialog_delete_confirmation_declined_emits_nothing(panel, sample_tags, monkeypatch):
    """削除確認ダイアログで No を選ぶと translation_delete_requested を出さない。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "连衣裙"}}, available_languages=["ja"], image_id=1)

    def fill(dialog):
        dialog._table.selectRow(0)
        dialog._on_delete_clicked()

    _accept_dialog(monkeypatch, "TranslationFixDialog", fill)
    monkeypatch.setattr(tpw.QMessageBox, "question", lambda *a, **k: tpw.QMessageBox.StandardButton.No)
    received: list = []
    panel.translation_delete_requested.connect(lambda *a: received.append(a))
    panel._open_translation_fix_dialog("1girl")
    assert received == []


def test_translation_fix_dialog_suppress_button_requires_selection(qtbot):
    """「表示から隠す (抑制)」ボタンは行選択済みのときだけ有効。"""
    dialog = tpw.TranslationFixDialog("dress", {"ja": "连衣裙", "en": "dress"})
    qtbot.addWidget(dialog)

    assert not dialog._suppress_button.isEnabled()  # 未選択
    dialog._table.selectRow(0)
    assert dialog._suppress_button.isEnabled()


def test_translation_fix_dialog_suppress_click_sets_suppress_action(qtbot):
    """抑制ボタン押下で action()="suppress" になり、選択行の元翻訳を返す。"""
    dialog = tpw.TranslationFixDialog("dress", {"ja": "连衣裙", "en": "dress"})
    qtbot.addWidget(dialog)
    dialog._table.selectRow(0)

    dialog._on_suppress_clicked()

    assert dialog.action() == "suppress"
    assert dialog.language() == "ja"
    assert dialog.original_translation() == "连衣裙"


def test_translation_fix_dialog_emits_translation_suppress_requested(
    panel, sample_tags, qtbot, monkeypatch
):
    """抑制確定 (確認ダイアログ Yes) で translation_suppress_requested(canonical, lang, tr) を出す。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "连衣裙"}}, available_languages=["ja"], image_id=1)

    def fill(dialog):
        dialog._table.selectRow(0)
        dialog._on_suppress_clicked()

    _accept_dialog(monkeypatch, "TranslationFixDialog", fill)
    monkeypatch.setattr(tpw.QMessageBox, "question", lambda *a, **k: tpw.QMessageBox.StandardButton.Yes)
    with qtbot.waitSignal(panel.translation_suppress_requested, timeout=1000) as blocker:
        panel._open_translation_fix_dialog("1girl")
    assert blocker.args == ["1girl", "ja", "连衣裙"]


def test_translation_fix_dialog_suppress_confirmation_declined_emits_nothing(
    panel, sample_tags, monkeypatch
):
    """抑制確認ダイアログで No を選ぶと translation_suppress_requested を出さない。"""
    panel.set_tags(sample_tags, translations={10: {"ja": "连衣裙"}}, available_languages=["ja"], image_id=1)

    def fill(dialog):
        dialog._table.selectRow(0)
        dialog._on_suppress_clicked()

    _accept_dialog(monkeypatch, "TranslationFixDialog", fill)
    monkeypatch.setattr(tpw.QMessageBox, "question", lambda *a, **k: tpw.QMessageBox.StandardButton.No)
    received: list = []
    panel.translation_suppress_requested.connect(lambda *a: received.append(a))
    panel._open_translation_fix_dialog("1girl")
    assert received == []


def test_translation_fix_pending_metadata_blocks_add_fallback(panel, sample_tags, monkeypatch):
    """メタデータ解決中は空翻訳を「翻訳なし」と誤認せず追加ダイアログへ落とさない (Codex P2)。

    読み込み中に追加ダイアログへ落ちると正規化キー "ja" で書いてしまい、legacy
    "japanese" キーの誤訳を上書きできない。apply_tag_metadata の反映で解禁される。
    """
    panel.set_tags(sample_tags, image_id=1)
    panel.set_tag_metadata_pending(True)
    infos: list = []
    monkeypatch.setattr(tpw.QMessageBox, "information", lambda *a, **k: infos.append(a))
    opened: list = []
    monkeypatch.setattr(panel, "_open_translation_dialog", lambda c: opened.append(c))

    panel._open_translation_fix_dialog("1girl")

    assert opened == []
    assert len(infos) == 1

    # メタデータ反映後は通常の追加フォールバックが効く
    panel.apply_tag_metadata({}, {}, {})
    panel._open_translation_fix_dialog("1girl")
    assert opened == ["1girl"]


# usage counts のセッション内キャッシュ (#1083) ---------------------------------


def test_metric_bar_survives_image_switch_during_phase1(panel, sample_tags):
    """画像切替の phase 1 (usage 空) で metric バーが消えない (#1083)。

    #1046 の2段階描画では選択直後の set_tags が usage_counts={} を渡すため、
    従来はキャッシュがクリアされ metadata worker 完了までバーが消えていた。
    """
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_tag_metadata({}, {10: {"danbooru": 1234}, 20: {"danbooru": 800}}, {})
    assert panel._metric_bar.isVisibleTo(panel)

    # 画像2へ切替: 既出 tag_id を含むタグ集合、usage は phase 1 なので空
    image2_tags = [
        {"tag": "1girl", "tag_id": 10, "model_name": "wd", "source": "AI", "confidence_score": 0.9},
        {"tag": "smile", "tag_id": 99, "model_name": "wd", "source": "AI", "confidence_score": 0.8},
    ]
    panel.set_tags(image2_tags, image_id=2, usage_counts={})

    assert panel._metric_bar.isVisibleTo(panel)  # 既出 tag_id=10 の count で表示継続
    assert panel._counts_by_canonical.get("1girl") == {"danbooru": 1234}


def test_metric_selection_preserved_across_image_switch(panel, sample_tags):
    """metric の選択 (danbooru 等) が画像切替をまたいで維持される (#1083)。"""
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_tag_metadata({}, {10: {"danbooru": 1234}}, {})
    index = panel._metric_combo.findText("danbooru")
    panel._metric_combo.setCurrentIndex(index)
    assert panel._metric_source == "danbooru"

    panel.set_tags(sample_tags, image_id=2, usage_counts={})

    assert panel._metric_source == "danbooru"


def test_apply_tag_metadata_merges_usage_counts(panel, sample_tags):
    """apply_tag_metadata は他画像で貯めた counts を消さず merge する (#1083)。

    表示中タグ (tag_id 10, 20) の counts は今回の解決結果が正 (無ければ退避、
    Codex P2) だが、表示外の tag_id (別画像で貯めた 999) は保持される。
    """
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_tag_metadata({}, {999: {"danbooru": 5}}, {})  # 別画像分のキャッシュ相当
    panel.apply_tag_metadata({}, {10: {"danbooru": 1234}, 20: {"danbooru": 800}}, {})

    assert panel._usage_counts == {
        999: {"danbooru": 5},
        10: {"danbooru": 1234},
        20: {"danbooru": 800},
    }


def test_clear_keeps_usage_cache_but_hides_metric_bar(panel, sample_tags):
    """clear() はキャッシュを保持しつつ、タグ無しなので metric バーは隠れる (#1083)。"""
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_tag_metadata({}, {10: {"danbooru": 1234}}, {})

    panel.clear()

    assert not panel._metric_bar.isVisibleTo(panel)  # タグが無いので非表示
    assert panel._usage_counts == {10: {"danbooru": 1234}}  # キャッシュは残る

    # 再選択で即座に復活する
    panel.set_tags(sample_tags, image_id=3, usage_counts={})
    assert panel._metric_bar.isVisibleTo(panel)


def test_apply_tag_metadata_evicts_stale_counts_for_current_tags(panel, sample_tags):
    """表示中タグで解決結果に無い tag_id の stale キャッシュは退避する (Codex P2)。

    セッション中に usage 行が削除された / tag DB が差し替えられたタグの古い count を
    phase 2 以降も表示し続けないこと。他画像で貯めた無関係な tag_id は保持する。
    """
    panel.set_tags(sample_tags, image_id=1)  # tag_id 10, 20 を含む
    panel.apply_tag_metadata({}, {10: {"danbooru": 1234}, 999: {"danbooru": 5}}, {})

    # 2回目の解決で tag_id=10 の count が消えた (usage 行削除相当)
    panel.apply_tag_metadata({}, {20: {"danbooru": 800}}, {})

    assert 10 not in panel._usage_counts  # 表示中タグの stale は退避
    assert panel._usage_counts.get(20) == {"danbooru": 800}
    assert panel._usage_counts.get(999) == {"danbooru": 5}  # 他画像分は保持


def test_set_tags_explicit_counts_evict_missing_current_tags(panel, sample_tags):
    """set_tags の明示的な非空 usage_counts は表示中タグ分の正として扱う (Codex P2)。

    map に無い表示中 tag_id の古いキャッシュは退避し、phase 1 の空 map では保持する。
    """
    panel.set_tags(sample_tags, image_id=1)
    panel.apply_tag_metadata({}, {10: {"danbooru": 1234}, 999: {"danbooru": 5}}, {})

    # tag_id 10, 20 を含むタグ集合へ、20 だけの明示 counts を渡す
    panel.set_tags(sample_tags, image_id=2, usage_counts={20: {"danbooru": 800}})

    assert 10 not in panel._usage_counts  # 表示中で map に無い分は退避
    assert panel._usage_counts.get(20) == {"danbooru": 800}
    assert panel._usage_counts.get(999) == {"danbooru": 5}  # 表示外は保持


def test_update_language_selector_prefer_resolves_legacy_alias(panel):
    """prefer が正規化キー ("ja") で候補が legacy キー ("japanese") だけでも切り替わる (Codex P2)。

    主訳は ja/en 正規化で保存されるため、既存 DB の候補が "japanese" しか無い場合に
    prefer="ja" が不一致で english のまま残ると、主訳変更が「何も起きない」ように見える。
    """
    panel.update_language_selector(["japanese"], prefer=None)
    assert panel._current_language() == "english"

    panel.update_language_selector(["japanese"], prefer="ja")

    assert panel._current_language() == "japanese"


def test_update_language_selector_force_prefer_switches_from_non_english(panel):
    """force_prefer=True なら非英語表示中でも prefer の言語へ切り替える (Codex P2)。"""
    panel.update_language_selector(["japanese", "ko"], prefer="japanese", force_prefer=True)
    assert panel._current_language() == "japanese"

    # 非英語 (japanese) 表示中に ko の主訳を変更した想定 (#1235: en 族は sentinel に
    # 畳むため force_prefer 検証には別族の言語を使う)
    panel.update_language_selector(["japanese", "ko"], prefer="ko", force_prefer=True)

    assert panel._current_language() == "ko"


# 翻訳再取得ボタン (言語バー右端、#1210 案A) ---------------------------------


def test_translation_refresh_button_lives_in_lang_bar(panel):
    """翻訳再取得ボタンは言語バー右端に配置され、既定では無効 (#1210)。"""
    button = panel._translation_refresh_button
    assert button.parent() is panel._lang_bar
    assert not button.isEnabled()


def test_translation_refresh_button_emits_signal(panel, qtbot):
    """ボタン押下で translation_refresh_requested が emit される (#1210)。"""
    panel.set_translation_refresh_enabled(True)
    assert panel._translation_refresh_button.isEnabled()
    with qtbot.waitSignal(panel.translation_refresh_requested, timeout=1000):
        panel._translation_refresh_button.click()


def test_set_translation_refresh_enabled_toggles(panel):
    panel.set_translation_refresh_enabled(True)
    assert panel._translation_refresh_button.isEnabled()
    panel.set_translation_refresh_enabled(False)
    assert not panel._translation_refresh_button.isEnabled()


def test_refresh_button_stays_visible_when_no_languages(panel):
    """翻訳言語 0 件でも再取得ボタンは残る (Codex #1224 P2)。

    未翻訳画像で言語コンボが隠れても、CLI で最初の翻訳を追加した直後に
    画像再選択なしで取得できるよう、ボタンとバーは可視を保つ
    (ヘッドレス親非表示のため isHidden() で明示可視フラグを検証)。
    """
    panel.initialize_language_selector([])  # 言語なし → コンボ非表示
    panel.set_translation_refresh_enabled(True)

    assert panel._lang_combo.isHidden()  # 言語コンボは隠れる
    assert not panel._translation_refresh_button.isHidden()  # ボタンは残る
    assert not panel._lang_bar.isHidden()  # バーも残る


def test_lang_bar_hidden_when_no_languages_and_refresh_disabled(panel):
    """言語 0 件かつ再取得ボタン無効ならバー全体を隠す (既存挙動を維持)。"""
    panel.initialize_language_selector([])
    panel.set_translation_refresh_enabled(False)

    assert panel._lang_bar.isHidden()


def test_lang_combo_shown_when_languages_present(panel):
    """翻訳言語ありなら言語コンボとバーを表示する。"""
    panel.initialize_language_selector(["japanese"])

    assert not panel._lang_bar.isHidden()
    assert not panel._lang_combo.isHidden()
    assert panel._lang_combo.count() > 1


def test_reinit_with_no_languages_clears_stale_combo(panel):
    """言語ありの後に空リストで再初期化すると古い言語が残らない (Codex #1224 P2)。

    clear しないと combo に古い言語が残り、可視性判定が count()>1 で誤って
    表示継続する (set_merged_reader(None) 相当の回帰)。
    """
    panel.initialize_language_selector(["japanese", "en"])
    assert panel._lang_combo.count() > 1

    panel.initialize_language_selector([])  # リーダー消失 / 言語なしリーダー再注入

    assert panel._lang_combo.count() == 0
    assert panel._lang_combo.isHidden()
    assert panel._lang_bar.isHidden()  # 再取得も無効なのでバーごと隠れる


def test_action_buttons_use_text_only_style(panel):
    """グリフ文字ボタンは TextOnly スタイルでラベルを表示する (Codex #1224 P2)。"""
    from PySide6.QtCore import Qt

    assert panel._translation_refresh_button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextOnly


def test_current_language_is_english_when_combo_empty(panel):
    """言語 0 件で bar が (再取得ボタンのため) 表示されても english 判定 (Codex #1224 P2)。"""
    panel.initialize_language_selector([])
    panel.set_translation_refresh_enabled(True)  # bar 表示・combo 空
    assert panel._current_language() == "english"


# ⑰ 種別インジケータ (グリフ + ストライプ + 色分け) と「種別で分ける」トグル (#1233 / #1241) --


def test_chip_shows_glyph_for_known_type_and_blank_for_general(panel):
    """既知種別 (character 等) はグリフ付き、general は無印 (ノイズを増やさない)。"""
    tags = [
        {"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    tag_types = {"hatsune miku": "character", "1girl": "general"}

    panel.set_tags(tags, tag_types=tag_types)

    miku = next(c for c in panel._tag_chips if c.canonical == "hatsune miku")
    girl = next(c for c in panel._tag_chips if c.canonical == "1girl")
    assert miku.type_glyph == "C"
    assert miku.text().startswith("C ")
    assert girl.type_glyph == ""
    assert girl.text() == "1girl"


def test_chip_stripe_color_matches_type_palette(panel):
    """種別ストライプ色は theme.TAG_TYPE_PALETTE の色と一致し、QSS にも反映される (#1241)。"""
    tags = [{"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"}]
    panel.set_tags(tags, tag_types={"hatsune miku": "character"})

    chip = panel._tag_chips[0]
    _bg, fg, _border = theme.TAG_TYPE_PALETTE["character"]
    assert chip.stripe_color == fg
    assert f"border-left: 4px solid {fg}" in chip.styleSheet()


def test_chip_recolors_by_type_palette_when_active(panel):
    """アクティブ (翻訳解決済み・非無効化) chip の背景色が種別パレットで recolor される (#1233)。"""
    tags = [{"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"}]
    panel.set_tags(tags, tag_types={"hatsune miku": "character"})

    chip = panel._tag_chips[0]
    assert chip.base_qss == theme.tag_type_chip_qss("character")
    assert chip.base_qss != theme.chip_qss("accent")


def test_chip_general_and_unknown_type_keep_accent(panel):
    """general / 型不明は現行の accent chip (無色分け) を据え置く (#1233)。"""
    tags = [
        {"tag": "1girl", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "unregistered", "tag_id": None, "model_name": "wd", "source": "AI"},
    ]
    panel.set_tags(tags, tag_types={"1girl": "general"})

    girl = next(c for c in panel._tag_chips if c.canonical == "1girl")
    unknown = next(c for c in panel._tag_chips if c.canonical == "unregistered")
    assert girl.base_qss == theme.chip_qss("accent")
    assert unknown.base_qss == theme.chip_qss("accent")
    assert girl.stripe_color is None
    assert unknown.stripe_color is None


def test_group_by_type_toggle_disabled_with_single_type(panel):
    """種別が 1 つしかない画像ではトグルを無効化する (#1241)。"""
    tags = [
        {"tag": "1girl", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "solo", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    panel.set_tags(tags, tag_types={"1girl": "general", "solo": "general"})

    assert panel._group_by_type_checkbox.isEnabled() is False


def test_group_by_type_toggle_enabled_with_multiple_types(panel):
    """2 種別以上あればトグルを有効化する (#1241)。"""
    tags = [
        {"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    panel.set_tags(tags, tag_types={"hatsune miku": "character", "1girl": "general"})

    assert panel._group_by_type_checkbox.isEnabled() is True


def test_group_by_type_toggle_on_creates_sections_with_headers(panel):
    """トグル ON でヘッダ (グリフ+ラベル+件数) 付きセクションへ分割する (#1241)。"""
    tags = [
        {"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "vocaloid", "tag_id": 2, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 3, "model_name": "wd", "source": "AI"},
    ]
    tag_types = {"hatsune miku": "character", "vocaloid": "copyright", "1girl": "general"}
    panel.set_tags(tags, tag_types=tag_types)

    panel._group_by_type_checkbox.setChecked(True)

    # 3 種別 (character/copyright/general) それぞれヘッダ + FlowLayout の 2 要素 = 6 セクション
    sections = panel._tags_chip_sections_layout
    assert sections.count() == 6
    headers = [
        sections.itemAt(i).widget()
        for i in range(sections.count())
        if isinstance(sections.itemAt(i).widget(), QLabel)
    ]
    header_texts = [h.text() for h in headers]
    assert any("キャラクター" in t for t in header_texts)
    assert any("版権" in t for t in header_texts)
    assert any("一般" in t for t in header_texts)
    # chip 自体は変わらず全件描画される (グループ化は表示上の分割のみ)
    assert len(panel._tag_chips) == 3


def test_group_by_type_with_rejected_tags_no_duplicate_headers(panel):
    """soft-rejected タグが複数種別に跨っても種別ヘッダが重複しない (Codex P1 回帰)。

    rejected 分は type ソート対象外で末尾追記されるため、隣接判定だけだと同一 type が
    非連続になり重複ヘッダ + 誤った件数が出る。_render_grouped_chips が type グループ順に
    stable-sort してから区切ることで、active/rejected を問わず 1 種別 1 セクションになる。
    """
    tags = [
        {"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "vocaloid", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    panel.set_tags(tags, tag_types={"hatsune miku": "character", "vocaloid": "copyright"})
    panel.set_rejected_tags(
        [
            {"tag": "old_meta_tag", "reject_reason": "not_needed"},
            {"tag": "old_character_tag", "reject_reason": "not_needed"},
        ]
    )
    # rejected タグの type を注入 (character が active の character と非隣接になる並び)
    panel._tag_types["old_meta_tag"] = "meta"
    panel._tag_types["old_character_tag"] = "character"
    panel._refresh_tags_for_language(panel._current_language())

    panel._group_by_type_checkbox.setChecked(True)

    sections = panel._tags_chip_sections_layout
    headers = [
        sections.itemAt(i).widget().text()
        for i in range(sections.count())
        if isinstance(sections.itemAt(i).widget(), QLabel)
    ]
    # 各種別ヘッダは 1 回だけ (重複しない)
    assert sum("キャラクター" in t for t in headers) == 1
    assert sum("版権" in t for t in headers) == 1
    assert sum("メタ" in t for t in headers) == 1
    # character セクションは active miku + rejected old_character_tag の 2 件
    character_header = next(t for t in headers if "キャラクター" in t)
    assert "(2)" in character_header


def test_group_by_type_toggle_off_is_flat(panel):
    """トグル OFF (既定) はフラット表示 (単一セクション) を維持する (#1241)。"""
    tags = [
        {"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    panel.set_tags(tags, tag_types={"hatsune miku": "character", "1girl": "general"})

    assert panel._tags_chip_sections_layout.count() == 1
    assert len(panel._tag_chips) == 2


def test_group_by_type_toggle_back_off_restores_flat(panel):
    """トグルを ON→OFF に戻すとフラット表示へ戻る (#1241)。"""
    tags = [
        {"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"},
        {"tag": "1girl", "tag_id": 2, "model_name": "wd", "source": "AI"},
    ]
    panel.set_tags(tags, tag_types={"hatsune miku": "character", "1girl": "general"})
    panel._group_by_type_checkbox.setChecked(True)
    assert panel._tags_chip_sections_layout.count() > 1

    panel._group_by_type_checkbox.setChecked(False)
    assert panel._tags_chip_sections_layout.count() == 1
    assert len(panel._tag_chips) == 2


def test_click_model_unaffected_by_type_indicator(panel, qtbot):
    """無効化⇄復活 / Ctrl+コピーの既存クリックモデルは種別インジケータ付きでも非回帰 (#1233/#1241)。"""
    tags = [{"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"}]
    panel.set_tag_edit_enabled(True)
    panel.set_tags(tags, tag_types={"hatsune miku": "character"})
    chip = panel._tag_chips[0]

    with qtbot.waitSignal(panel.tag_disable_requested, timeout=1000) as blocker:
        chip.clicked.emit()
    assert blocker.args == ["hatsune miku"]
    # 破線 (無効化) スタイルでも種別ストライプは維持される (状態と独立、#1233/#1241)
    assert "border-left: 4px solid" in chip.styleSheet()

    with qtbot.waitSignal(panel.tag_restore_requested, timeout=1000) as blocker:
        chip.clicked.emit()
    assert blocker.args == ["hatsune miku"]

    chip.ctrl_clicked.emit()
    assert chip.selected is True
    assert "border-left: 4px solid" in chip.styleSheet()


def test_remove_button_still_hides_chip_with_type_indicator(panel, qtbot):
    """✕ (除外) の既存挙動は種別インジケータ付きでも非回帰 (#1233/#1241)。"""
    tags = [{"tag": "hatsune miku", "tag_id": 1, "model_name": "wd", "source": "AI"}]
    panel.set_tag_edit_enabled(True)
    panel.set_tags(tags, tag_types={"hatsune miku": "character"})
    buttons = panel.findChildren(QToolButton, "tagRejectButton")
    assert len(buttons) == 1

    with qtbot.waitSignal(panel.tag_exclude_requested, timeout=1000) as blocker:
        buttons[0].click()
    assert blocker.args == ["hatsune miku"]
    assert "hatsune miku" in panel._hidden
    assert panel._tag_chips == []
