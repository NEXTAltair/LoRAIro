"""SelectableTagChip / AnnotationDataDisplayWidget の refinement 表示テスト (#931)。

⚠ マーカー・ツールチップ・「この理由を無視」メニューの emit・apply_refinements の
chip 反映を検証する。
"""

from __future__ import annotations

import pytest
from genai_tag_db_tools.models import (
    RefinementReason,
    RefinementRecommendation,
    RefinementSuggestion,
)

from lorairo.gui.widgets.annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
)
from lorairo.gui.widgets.tag_panel_widget import SelectableTagChip

pytestmark = pytest.mark.gui


def _rec(tag: str, *, codes: list[str], suggestion: str | None = None) -> RefinementRecommendation:
    return RefinementRecommendation(
        source_tag=tag,
        normalized_tag=tag,
        needs_refinement=True,
        score=0.7,
        reasons=[RefinementReason(code=c, message=f"{c} msg") for c in codes],  # type: ignore[arg-type]
        suggestions=(
            [RefinementSuggestion(kind="correction_candidate", tag=suggestion)]
            if suggestion is not None
            else []
        ),
        proposals=[],
    )


def test_set_refinement_adds_marker_and_tooltip(qtbot) -> None:
    chip = SelectableTagChip("blue__eyes", "blue__eyes")
    qtbot.addWidget(chip)

    chip.set_refinement(_rec("blue__eyes", codes=["normalization_changes_tag"], suggestion="blue_eyes"))

    assert chip.text().startswith("⚠")
    assert "normalization_changes_tag msg" in chip.toolTip()
    assert "blue_eyes" in chip.toolTip()


def test_set_refinement_renders_translation_quality_reason(qtbot) -> None:
    """翻訳品質 reason (#976) も既存の ⚠ / tooltip / 無視メニュー経路に乗る。"""
    chip = SelectableTagChip("blue_eyes", "blue_eyes")
    qtbot.addWidget(chip)

    chip.set_refinement(_rec("blue_eyes", codes=["overlong_translation"]))

    assert chip.text().startswith("⚠")
    assert "overlong_translation msg" in chip.toolTip()

    received: list[tuple[str, str]] = []
    chip.refinement_ignore_requested.connect(lambda c, r: received.append((c, r)))
    chip.refinement_ignore_requested.emit(chip.canonical, "overlong_translation")
    assert received == [("blue_eyes", "overlong_translation")]


def test_set_refinement_none_restores_base_text(qtbot) -> None:
    chip = SelectableTagChip("flower", "flower")
    qtbot.addWidget(chip)
    chip.set_refinement(_rec("flower", codes=["broad_single_word"]))
    assert chip.text().startswith("⚠")

    chip.set_refinement(None)

    assert chip.text() == "flower"


def test_set_refinement_no_reasons_does_not_mark(qtbot) -> None:
    chip = SelectableTagChip("flower", "flower")
    qtbot.addWidget(chip)
    rec = RefinementRecommendation(
        source_tag="flower",
        normalized_tag="flower",
        needs_refinement=False,
        score=0.0,
        reasons=[],
        suggestions=[],
        proposals=[],
    )

    chip.set_refinement(rec)

    assert chip.text() == "flower"


def test_ignore_signal_emits_canonical_and_reason(qtbot) -> None:
    chip = SelectableTagChip("blue__eyes", "blue__eyes")
    qtbot.addWidget(chip)
    chip.set_refinement(_rec("blue__eyes", codes=["normalization_changes_tag"]))

    received: list[tuple[str, str]] = []
    chip.refinement_ignore_requested.connect(lambda c, r: received.append((c, r)))
    # メニュー経由ではなく Signal を直接 emit して配線を検証する
    chip.refinement_ignore_requested.emit(chip.canonical, "normalization_changes_tag")

    assert received == [("blue__eyes", "normalization_changes_tag")]


def test_refinements_survive_chip_rerender(qtbot) -> None:
    """言語切替等で chip 再生成されても ⚠ が維持される (Codex P2)。"""
    widget = AnnotationDataDisplayWidget()
    qtbot.addWidget(widget)
    widget.update_data(AnnotationData(tags=[{"tag": "flower"}]))
    widget.apply_refinements({"flower": _rec("flower", codes=["broad_single_word"])})

    # 言語切替相当: chip を再生成する (update_data は経由しない)
    widget._render_tag_chips([("flower", "flower", False)], is_translated=False)

    chips = [c for c in widget._tag_chips if c.canonical == "flower"]
    assert chips, "flower chip が再生成されていない"
    assert chips[0].text().startswith("⚠"), "再描画後に ⚠ が失われた"


def test_new_image_clears_stale_refinements(qtbot) -> None:
    """新画像 (update_data) では前画像の refinement が引き継がれない (#931)。"""
    widget = AnnotationDataDisplayWidget()
    qtbot.addWidget(widget)
    widget.update_data(AnnotationData(tags=[{"tag": "flower"}]))
    widget.apply_refinements({"flower": _rec("flower", codes=["broad_single_word"])})

    # 別画像にも "flower" タグがあるが refinement は未評価の状態で表示する
    widget.update_data(AnnotationData(tags=[{"tag": "flower"}]))

    chips = [c for c in widget._tag_chips if c.canonical == "flower"]
    assert chips and chips[0].text() == "flower", "新画像に前画像の ⚠ が漏れている"
