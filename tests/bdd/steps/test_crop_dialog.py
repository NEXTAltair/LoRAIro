"""クロップ作成ダイアログの BDD ステップ定義 (#1345)。

CropDialog を DB / サービスなしで組み立て、解像度警告の境界・無効範囲での保存禁止・
タグの候補↔採用移動・レーティング初期値・破棄確認・保存の成否をユーザーフローとして検証する。
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.domain.crop_request import CropCreateRequest, CropRect
from lorairo.gui.widgets.crop_dialog import CropDialog
from lorairo.gui.widgets.crop_tag_list_widget import ClickableTagListWidget

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "crop_dialog.feature"
scenarios(str(_FEATURE_FILE))

CHILD_IMAGE_ID = 555


class _SaveRecorder:
    """保存 callback のスタブ (呼び出し記録 + 任意で例外送出)。"""

    def __init__(self) -> None:
        self.calls: list[CropCreateRequest] = []
        self.error: Exception | None = None

    def __call__(self, request: CropCreateRequest) -> int:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return CHILD_IMAGE_ID


@pytest.fixture(autouse=True)
def auto_mock_qmessagebox(monkeypatch: pytest.MonkeyPatch) -> None:
    """QMessageBox.question を既定で「はい」に固定する。

    tests/bdd には tests/unit/gui/conftest.py のような autouse mock が無い。
    pytest-qt は teardown で登録ウィジェットを close() するため、未保存変更が残った
    ダイアログで実 QMessageBox が開き、テストがブロックする。個別ステップはこの上から
    さらに monkeypatch して回答と呼び出し回数を制御する。
    """
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)


def _click_tag(qtbot, tag_list: ClickableTagListWidget, tag: str) -> None:
    """タグリストの該当行を実際にクリックする。"""
    for row in range(tag_list.count()):
        item = tag_list.item(row)
        if item is not None and item.text() == tag:
            qtbot.mouseClick(
                tag_list.viewport(),
                Qt.MouseButton.LeftButton,
                pos=tag_list.visualItemRect(item).center(),
            )
            return
    raise AssertionError(f"タグ {tag!r} が見つかりません: {tag_list.tags()}")


def _split_tags(text: str) -> list[str]:
    """カンマ区切りのタグ列をリストへ変換する。"""
    return [part.strip() for part in text.split(",") if part.strip()]


# ---------------------------------------------------------------------------
# 前提
# ---------------------------------------------------------------------------


@given(parsers.parse("{width:d}x{height:d} の親画像がある"), target_fixture="crop_image_path")
def given_parent_image(tmp_path: Path, width: int, height: int) -> Path:
    path = tmp_path / "parent.png"
    Image.new("RGB", (width, height), (180, 170, 160)).save(path)
    return path


@given(
    parsers.parse('候補タグ "{tags}" と親レーティング "{rating}" でクロップダイアログを開いている'),
    target_fixture="ctx",
)
def given_crop_dialog(qtbot, crop_image_path: Path, tags: str, rating: str) -> dict[str, Any]:
    recorder = _SaveRecorder()
    dialog = CropDialog(
        image_path=crop_image_path,
        parent_image_id=42,
        candidate_tags=_split_tags(tags),
        parent_rating=rating,
        save_callback=recorder,
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return {"dialog": dialog, "recorder": recorder, "questions": []}


@given("保存 callback が失敗する")
def given_save_fails(ctx: dict[str, Any]) -> None:
    ctx["recorder"].error = RuntimeError("保存サービスが失敗しました")


# ---------------------------------------------------------------------------
# もし
# ---------------------------------------------------------------------------


@when(parsers.parse("幅 {width:d} 高さ {height:d} の範囲を選択する"))
def when_select_rect(ctx: dict[str, Any], width: int, height: int) -> None:
    ctx["dialog"].set_rect(CropRect(x=0, y=0, width=width, height=height))


@when(parsers.parse('候補タグ "{tag}" をクリックする'))
def when_click_candidate(qtbot, ctx: dict[str, Any], tag: str) -> None:
    _click_tag(qtbot, ctx["dialog"]._candidate_list, tag)


@when(parsers.parse('採用タグ "{tag}" をクリックする'))
def when_click_adopted(qtbot, ctx: dict[str, Any], tag: str) -> None:
    _click_tag(qtbot, ctx["dialog"]._adopted_list, tag)


@when(parsers.parse('レーティング "{value}" を選ぶ'))
def when_select_rating(ctx: dict[str, Any], value: str) -> None:
    ctx["dialog"]._rating_control._buttons[value].click()


@when(parsers.parse('破棄確認で "{answer}" を選んで閉じる'))
def when_close_with_answer(monkeypatch: pytest.MonkeyPatch, ctx: dict[str, Any], answer: str) -> None:
    button = QMessageBox.StandardButton.Yes if answer == "はい" else QMessageBox.StandardButton.No

    def fake_question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        ctx["questions"].append(answer)
        return button

    monkeypatch.setattr(QMessageBox, "question", fake_question)
    ctx["dialog"].close()


@when("保存ボタンを押す")
def when_click_save(ctx: dict[str, Any]) -> None:
    ctx["dialog"]._save_button.click()


# ---------------------------------------------------------------------------
# ならば
# ---------------------------------------------------------------------------


@then("解像度の警告が表示される")
def then_warning_shown(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].is_resolution_warning_visible() is True


@then("解像度の警告は表示されない")
def then_warning_hidden(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].is_resolution_warning_visible() is False


@then("保存ボタンは有効である")
def then_save_enabled(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].can_save() is True


@then("保存ボタンは無効である")
def then_save_disabled(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].can_save() is False


@then(parsers.parse('採用タグは "{tags}" である'))
def then_adopted_tags(ctx: dict[str, Any], tags: str) -> None:
    assert ctx["dialog"].adopted_tags() == _split_tags(tags)


@then("採用タグは空である")
def then_adopted_empty(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].adopted_tags() == []


@then(parsers.parse('候補タグは "{tags}" である'))
def then_candidate_tags(ctx: dict[str, Any], tags: str) -> None:
    assert ctx["dialog"].candidate_tags() == _split_tags(tags)


@then(parsers.parse('レーティングは "{value}" である'))
def then_rating_is(ctx: dict[str, Any], value: str) -> None:
    assert ctx["dialog"].rating() == value


@then("破棄確認が表示される")
def then_question_shown(ctx: dict[str, Any]) -> None:
    assert ctx["questions"] != []


@then("破棄確認は表示されない")
def then_question_not_shown(ctx: dict[str, Any]) -> None:
    assert ctx["questions"] == []


@then("ダイアログは開いたままである")
def then_dialog_open(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].isVisible() is True


@then("ダイアログは閉じている")
def then_dialog_closed(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].isVisible() is False


@then(parsers.parse("保存 callback が {count:d} 回呼ばれる"))
def then_callback_called(ctx: dict[str, Any], count: int) -> None:
    assert len(ctx["recorder"].calls) == count


@then("エラーが表示される")
def then_error_shown(ctx: dict[str, Any]) -> None:
    assert ctx["dialog"].error_message() != ""
