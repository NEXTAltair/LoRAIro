"""クロップ機能の GUI 配線の BDD ステップ定義 (#1346 / ADR 0092)。

実 ``SearchTabWidget`` + ファイル実体の SQLite で、一覧 / プレビューからの起動・保存後の
一覧反映・再クロップ・再読込後の親子確認・保存失敗時の振る舞いをユーザーフローとして固定する。
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import Base, TagAnnotationData
from lorairo.domain.crop_request import CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.search_tab import SearchTabWidget
from lorairo.gui.widgets.crop_dialog import CropDialog

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "crop_wiring.feature"
scenarios(str(_FEATURE_FILE))

PARENT_WIDTH = 1600
PARENT_HEIGHT = 1200
PARENT_TAGS = ("solo", "outdoors")
PARENT_RATING = "PG-13"
SAVE_TIMEOUT_MS = 15000
"""保存ワーカーの完了待ち上限 (ms、#1345 で保存は非同期化)。"""


@dataclass
class WiringContext:
    """ステップ間で受け渡す検索タブ + DB の状態。"""

    tab: SearchTabWidget
    dataset_state: DatasetStateManager
    db_manager: ImageDatabaseManager
    db_path: Path
    parent_id: int
    dialog: CropDialog | None = None
    saved_ids: list[int] = field(default_factory=list)
    reopened: ImageDatabaseManager | None = None


@pytest.fixture(autouse=True)
def auto_mock_qmessagebox(monkeypatch: pytest.MonkeyPatch) -> None:
    """QMessageBox のネイティブダイアログを抑止する。

    tests/bdd には tests/unit/gui/conftest.py のような autouse mock が無い。pytest-qt の
    teardown が未保存のダイアログを close() する際に実ダイアログが開くとテストがブロックする。
    """
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)


def _open_file_db(db_path: Path, config_service: object) -> ImageDatabaseManager:
    """指定ファイルの SQLite を開いて Manager を返す (スキーマは必要なら作成)。"""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return ImageDatabaseManager(
        config_service=config_service,
        session_factory=sessionmaker(autocommit=False, autoflush=False, bind=engine),
    )


def _visible_dialog(ctx: WiringContext) -> CropDialog:
    """検索タブ配下で表示中のクロップダイアログを返す。"""
    dialogs = [child for child in ctx.tab.findChildren(CropDialog) if child.isVisible()]
    assert dialogs, "クロップダイアログが開かれていない"
    return dialogs[-1]


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("タグとレーティングを持つ元画像が検索タブに用意されている", target_fixture="ctx")
def given_search_tab_with_parent_image(
    qtbot,
    fs_manager: FileSystemManager,
    mock_config_service: object,
    tmp_path: Path,
) -> WiringContext:
    db_path = tmp_path / "crop_wiring.db"
    db_manager = _open_file_db(db_path, mock_config_service)

    source = tmp_path / "bdd_wiring_parent.png"
    Image.new("RGB", (PARENT_WIDTH, PARENT_HEIGHT), (32, 96, 176)).save(source)
    registered = db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    parent_id = registered[0]
    tags_data: list[TagAnnotationData] = [
        {
            "tag": tag,
            "tag_id": None,
            "model_id": None,
            "existing": True,
            "is_edited_manually": False,
            "confidence_score": None,
        }
        for tag in PARENT_TAGS
    ]
    db_manager.save_tags(parent_id, tags_data)
    db_manager.annotation_repo.update_manual_rating(parent_id, PARENT_RATING)

    container = Mock()
    container.file_system_manager = fs_manager
    container.db_manager.model_repo.get_model_objects.return_value = []
    container.favorite_filters_service.list_filters.return_value = []
    merged_reader = Mock()
    merged_reader.get_tag_languages.return_value = []
    container.db_manager.annotation_repo.get_merged_reader.return_value = merged_reader

    dataset_state = DatasetStateManager()
    dataset_state.set_db_manager(db_manager)
    tab = SearchTabWidget(
        service_container=container,
        db_manager=db_manager,
        dataset_state_manager=dataset_state,
        staging_state_manager=StagingStateManager(),
        worker_service=Mock(),
    )
    qtbot.addWidget(tab)

    ctx = WiringContext(
        tab=tab,
        dataset_state=dataset_state,
        db_manager=db_manager,
        db_path=db_path,
        parent_id=parent_id,
    )
    launcher = tab._crop_dialog_launcher
    assert launcher is not None
    launcher.crop_saved.connect(lambda _parent, child: ctx.saved_ids.append(child))
    return ctx


@given("クロップ画像の保存が失敗する")
def given_save_fails(ctx: WiringContext, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_create(*args: object, **kwargs: object) -> int:
        raise RuntimeError("保存できません")

    monkeypatch.setattr("lorairo.gui.services.crop_dialog_launcher.create_crop_image", failing_create)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("画像一覧で元画像のクロップ操作を選ぶ")
def when_crop_requested_from_list(ctx: WiringContext) -> None:
    ctx.tab.thumbnail_selector.crop_requested.emit(ctx.parent_id)
    ctx.dialog = _visible_dialog(ctx)


@when("プレビューでクロップ画像のクロップ操作を選ぶ")
def when_crop_requested_from_preview(ctx: WiringContext) -> None:
    assert ctx.saved_ids, "先にクロップ画像を作成していない"
    ctx.tab.image_preview_widget.crop_requested.emit(ctx.saved_ids[-1])
    ctx.dialog = _visible_dialog(ctx)


@when(parsers.parse("矩形 {x:d},{y:d},{width:d},{height:d} を選んで保存する"))
def when_rect_selected_and_saved(
    qtbot, ctx: WiringContext, x: int, y: int, width: int, height: int
) -> None:
    dialog = ctx.dialog
    assert dialog is not None
    dialog.set_rect(CropRect(x=x, y=y, width=width, height=height))
    dialog._on_save()
    # 保存は worker スレッドで走る (#1345)。成功 (子 ID) か失敗 (エラー表示) の終端まで待つ。
    qtbot.waitUntil(
        lambda: dialog.child_image_id() is not None or dialog.error_message() != "",
        timeout=SAVE_TIMEOUT_MS,
    )


@when("データベースを開き直す")
def when_database_reopened(ctx: WiringContext, mock_config_service: object) -> None:
    ctx.reopened = _open_file_db(ctx.db_path, mock_config_service)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("クロップダイアログが開いている")
def then_dialog_open(ctx: WiringContext) -> None:
    assert ctx.dialog is not None
    assert ctx.dialog.isVisible() is True


@then("候補タグとして元画像のタグが表示される")
def then_candidate_tags_shown(ctx: WiringContext) -> None:
    assert ctx.dialog is not None
    assert sorted(ctx.dialog.candidate_tags()) == sorted(PARENT_TAGS)


@then("クロップダイアログは閉じている")
def then_dialog_closed(ctx: WiringContext) -> None:
    assert ctx.dialog is not None
    assert ctx.dialog.isVisible() is False


@then("クロップダイアログは開いたままである")
def then_dialog_still_open(ctx: WiringContext) -> None:
    assert ctx.dialog is not None
    assert ctx.dialog.isVisible() is True
    assert ctx.dialog.child_image_id() is None


@then("一覧にクロップ画像が含まれる")
def then_list_contains_child(ctx: WiringContext) -> None:
    assert ctx.saved_ids
    image_ids = {image["id"] for image in ctx.dataset_state.filtered_images}
    assert ctx.saved_ids[-1] in image_ids


@then("一覧にクロップ画像は追加されない")
def then_list_has_no_child(ctx: WiringContext) -> None:
    assert ctx.dataset_state.filtered_images == []


@then("一覧の現在画像はクロップ画像になる")
def then_current_image_is_child(ctx: WiringContext) -> None:
    assert ctx.saved_ids
    assert ctx.dataset_state.current_image_id == ctx.saved_ids[-1]


@then("一覧の現在画像は変わらない")
def then_current_image_unchanged(ctx: WiringContext) -> None:
    assert ctx.saved_ids == []
    assert ctx.dataset_state.current_image_id is None


@then("詳細カラムの親は元画像である")
def then_details_parent_is_source(ctx: WiringContext) -> None:
    related = ctx.tab.selected_image_details_widget._related_images_widget
    parent_entry = related.parent_entry()
    assert parent_entry is not None
    assert parent_entry.image_id == ctx.parent_id


@then("孫画像の親はクロップ画像である")
def then_grandchild_parent_is_child(ctx: WiringContext) -> None:
    assert len(ctx.saved_ids) == 2
    child_id, grandchild_id = ctx.saved_ids
    relation = ctx.db_manager.get_crop_parent(grandchild_id)
    assert relation is not None
    assert relation.parent_image_id == child_id


@then("元画像の子としてクロップ画像が保存されている")
def then_reopened_children(ctx: WiringContext) -> None:
    assert ctx.reopened is not None
    children = ctx.reopened.get_crop_children(ctx.parent_id)
    assert [relation.child_image_id for relation in children] == ctx.saved_ids


@then("クロップ画像の親として元画像が保存されている")
def then_reopened_parent(ctx: WiringContext) -> None:
    assert ctx.reopened is not None
    assert ctx.saved_ids
    relation = ctx.reopened.get_crop_parent(ctx.saved_ids[-1])
    assert relation is not None
    assert relation.parent_image_id == ctx.parent_id
