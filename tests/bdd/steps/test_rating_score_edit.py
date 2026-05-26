"""レーティング/スコア編集の BDD ステップ定義。

RatingScoreEditWidget のプレースホルダ挙動 (PR #328) を Gherkin で固定する。
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_bdd import given, scenarios, then, when

from lorairo.gui.widgets.rating_score_edit_widget import RatingScoreEditWidget

pytestmark = pytest.mark.gui

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "rating_score_edit.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class RatingEditContext:
    """ステップ間で受け渡すレーティング編集の状態。"""

    widget: RatingScoreEditWidget
    rating_emitted: bool = False
    score_emitted: bool = False
    batch_rating_emitted: bool = False
    batch_score_emitted: bool = False
    rating_args: list = field(default_factory=list)
    score_args: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("RatingScoreEditWidget が初期化されている", target_fixture="ctx")
def given_widget_initialized(qtbot) -> RatingEditContext:
    widget = RatingScoreEditWidget()
    qtbot.addWidget(widget)
    ctx = RatingEditContext(widget=widget)

    def on_rating(*args):
        ctx.rating_emitted = True
        ctx.rating_args = list(args)

    def on_score(*args):
        ctx.score_emitted = True
        ctx.score_args = list(args)

    def on_batch_rating(*args):
        ctx.batch_rating_emitted = True
        ctx.rating_args = list(args)

    def on_batch_score(*args):
        ctx.batch_score_emitted = True
        ctx.score_args = list(args)

    widget.rating_changed.connect(on_rating)
    widget.score_changed.connect(on_score)
    widget.batch_rating_changed.connect(on_batch_rating)
    widget.batch_score_changed.connect(on_batch_score)
    return ctx


@given("Rating 未設定の画像をロードする")
def given_load_unrated_image(ctx: RatingEditContext) -> None:
    ctx.widget.populate_from_image_data({"id": 555, "score_value": 6.0})
    assert ctx.widget.ui.comboBoxRating.currentText() == "----"


@given("Rating が混在した複数画像をバッチ選択でロードする")
def given_load_mixed_rating_selection(ctx: RatingEditContext) -> None:
    mock_db_manager = Mock()
    mock_db_manager.repository = Mock()
    mock_db_manager.image_repo.get_image_metadata.side_effect = [
        {"rating": "PG", "score_value": 5.0},
        {"rating": "X", "score_value": 5.0},
    ]
    ctx.widget.populate_from_selection([10, 20], mock_db_manager)
    # Rating 混在のためプレースホルダ表示
    assert ctx.widget.ui.comboBoxRating.currentText() == "----"


@given("有効な Rating を持つ画像をロードする")
def given_load_rated_image(ctx: RatingEditContext) -> None:
    ctx.widget.populate_from_image_data({"id": 777, "rating": "PG-13", "score_value": 7.0})
    assert ctx.widget.ui.comboBoxRating.currentText() == "PG-13"


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("保存ボタンをクリックする")
def when_click_save(ctx: RatingEditContext) -> None:
    ctx.widget.ui.pushButtonSave.click()


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("score_changed シグナルが発行される")
def then_score_emitted(ctx: RatingEditContext) -> None:
    assert ctx.score_emitted is True


@then("score_changed シグナルも発行される")
def then_score_also_emitted(ctx: RatingEditContext) -> None:
    assert ctx.score_emitted is True


@then("rating_changed シグナルは発行されない")
def then_rating_not_emitted(ctx: RatingEditContext) -> None:
    assert ctx.rating_emitted is False


@then("rating_changed シグナルが発行される")
def then_rating_emitted(ctx: RatingEditContext) -> None:
    assert ctx.rating_emitted is True


@then("batch_score_changed シグナルが発行される")
def then_batch_score_emitted(ctx: RatingEditContext) -> None:
    assert ctx.batch_score_emitted is True


@then("batch_rating_changed シグナルは発行されない")
def then_batch_rating_not_emitted(ctx: RatingEditContext) -> None:
    assert ctx.batch_rating_emitted is False
