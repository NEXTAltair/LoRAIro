"""CropDialogLauncher の GUI テスト (#1346)。

実 SQLite + 実ファイルシステムで「一覧の要求 → ダイアログ生成 → サービス保存 →
crop_saved 中継」まで通し、再クロップ (親 → 子 → 孫) と保存失敗時の振る舞いを固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.schema import Base
from lorairo.domain.crop_request import CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.gui.services.crop_dialog_launcher import CropDialogLauncher
from lorairo.gui.widgets.crop_dialog import CropDialog

PARENT_WIDTH = 1600
PARENT_HEIGHT = 1200
PARENT_TAGS = ("solo", "outdoors")
PARENT_RATING = "PG-13"
SAVE_TIMEOUT_MS = 15000
"""保存ワーカーの完了待ち上限 (ms)。"""


@pytest.fixture
def crop_db_manager(tmp_path: Path, mock_config_service: object) -> ImageDatabaseManager:
    """ファイル実体の SQLite を使う DB マネージャー。

    #1345 で保存はワーカースレッドへ移ったため、単一スレッド前提のインメモリ SQLite
    (conftest の ``test_db_manager``) では ``check_same_thread`` に阻まれる。本番は
    ``db_core`` がファイル DB を ``check_same_thread=False`` で開くため、テストも
    ファイル DB を使って同じ前提に揃える。
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'crop_test.db'}")
    Base.metadata.create_all(engine)
    return ImageDatabaseManager(
        config_service=mock_config_service,
        session_factory=sessionmaker(autocommit=False, autoflush=False, bind=engine),
    )


@pytest.fixture
def parent_image_id(
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """タグとレーティングを持つ親画像を登録して ID を返す。"""
    source = tmp_path / "launcher_parent.png"
    Image.new("RGB", (PARENT_WIDTH, PARENT_HEIGHT), (30, 110, 190)).save(source)
    registered = crop_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    parent_id: int = registered[0]
    crop_db_manager.save_tags(
        parent_id,
        [
            {
                "tag": tag,
                "tag_id": None,
                "model_id": None,
                "existing": True,
                "is_edited_manually": False,
                "confidence_score": None,
            }
            for tag in PARENT_TAGS
        ],
    )
    crop_db_manager.annotation_repo.update_manual_rating(parent_id, PARENT_RATING)
    return parent_id


@pytest.fixture
def launcher(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
) -> CropDialogLauncher:
    """実 DB / 実 FS を注入したランチャー。"""
    return CropDialogLauncher(db_manager=crop_db_manager, fsm=fs_manager)


def _open_and_save(
    qtbot,
    launcher: CropDialogLauncher,
    image_id: int,
    rect: CropRect,
) -> tuple[CropDialog, list[tuple[int, int]]]:
    """ダイアログを開いて矩形を設定し、保存をワーカー完了まで実行する。"""
    saved: list[tuple[int, int]] = []
    launcher.crop_saved.connect(lambda parent_id, child_id: saved.append((parent_id, child_id)))
    dialog = launcher.open_for_image(image_id)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_rect(rect)
    assert dialog.can_save() is True
    # 保存は worker スレッドで走るため、完了 Signal まで待つ (#1345)
    with qtbot.waitSignal(dialog.saved, timeout=SAVE_TIMEOUT_MS):
        dialog._on_save()
    return dialog, saved


@pytest.mark.gui
def test_dialog_is_built_from_source_info(
    qtbot, launcher: CropDialogLauncher, parent_image_id: int
) -> None:
    """親画像のタグとレーティングがダイアログの初期状態に載る。"""
    dialog = launcher.open_for_image(parent_image_id)

    assert dialog is not None
    qtbot.addWidget(dialog)
    assert sorted(dialog.candidate_tags()) == sorted(PARENT_TAGS)
    assert dialog.rating() == PARENT_RATING


@pytest.mark.gui
def test_save_creates_child_and_emits_crop_saved(
    qtbot,
    launcher: CropDialogLauncher,
    parent_image_id: int,
    crop_db_manager: ImageDatabaseManager,
) -> None:
    """保存で子画像が登録され、crop_saved に (親 ID, 子 ID) が乗る。"""
    dialog, saved = _open_and_save(
        qtbot, launcher, parent_image_id, CropRect(x=100, y=100, width=640, height=480)
    )

    child_id = dialog.child_image_id()
    assert child_id is not None and child_id != parent_image_id
    assert saved == [(parent_image_id, child_id)]
    assert crop_db_manager.get_image_metadata(child_id) is not None

    relations = crop_db_manager.get_crop_children(parent_image_id)
    assert [relation.child_image_id for relation in relations] == [child_id]
    assert (relations[0].x, relations[0].y, relations[0].width, relations[0].height) == (
        100,
        100,
        640,
        480,
    )
    parent_relation = crop_db_manager.get_crop_parent(child_id)
    assert parent_relation is not None
    assert parent_relation.parent_image_id == parent_image_id


@pytest.mark.gui
def test_recrop_child_creates_grandchild(
    qtbot,
    launcher: CropDialogLauncher,
    parent_image_id: int,
    crop_db_manager: ImageDatabaseManager,
) -> None:
    """子を親として同じランチャーを使うと孫が作られる (直接の親子で連鎖)。"""
    child_dialog, _ = _open_and_save(
        qtbot, launcher, parent_image_id, CropRect(x=0, y=0, width=1024, height=768)
    )
    child_id = child_dialog.child_image_id()
    assert child_id is not None

    grandchild_dialog, _ = _open_and_save(
        qtbot, launcher, child_id, CropRect(x=10, y=10, width=256, height=256)
    )
    grandchild_id = grandchild_dialog.child_image_id()

    assert grandchild_id is not None
    assert [r.child_image_id for r in crop_db_manager.get_crop_children(child_id)] == [grandchild_id]
    grandchild_parent = crop_db_manager.get_crop_parent(grandchild_id)
    assert grandchild_parent is not None
    assert grandchild_parent.parent_image_id == child_id


@pytest.mark.gui
def test_save_failure_keeps_dialog_open_without_crop_saved(
    qtbot,
    launcher: CropDialogLauncher,
    parent_image_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存サービスが例外を投げたら crop_saved は出ず、ダイアログも閉じない。"""

    def failing_create(*args: object, **kwargs: object) -> int:
        raise RuntimeError("保存できません")

    monkeypatch.setattr("lorairo.gui.services.crop_dialog_launcher.create_crop_image", failing_create)
    saved: list[tuple[int, int]] = []
    launcher.crop_saved.connect(lambda parent_id, child_id: saved.append((parent_id, child_id)))

    dialog = launcher.open_for_image(parent_image_id)
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.set_rect(CropRect(x=0, y=0, width=512, height=512))
    dialog._on_save()
    qtbot.waitUntil(lambda: not dialog._save_in_progress, timeout=SAVE_TIMEOUT_MS)

    assert saved == []
    assert dialog.child_image_id() is None
    assert dialog.isVisible() is True
    assert "保存に失敗しました" in dialog.error_message()


@pytest.mark.gui
def test_missing_source_image_reports_error_and_returns_none(
    qtbot, launcher: CropDialogLauncher, monkeypatch: pytest.MonkeyPatch
) -> None:
    """親画像が存在しなければエラー表示のみでダイアログを開かない。"""
    shown: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: shown.append(str(args[2]) if len(args) > 2 else ""),
    )

    dialog = launcher.open_for_image(999999)

    assert dialog is None
    assert shown and "クロップを開始できません" in shown[0]
