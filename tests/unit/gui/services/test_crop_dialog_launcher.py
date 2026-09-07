"""CropDialogLauncher の GUI テスト (#1346)。

実 SQLite + 実ファイルシステムで「一覧の要求 → ダイアログ生成 → サービス保存 →
crop_saved 中継」まで通し、再クロップ (親 → 子 → 孫) と保存失敗時の振る舞いを固定する。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

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

TRANSLATED_TAGS = {"blue hair": 101, "smile": 202}
"""翻訳解決テスト用の親タグ (タグ名 -> tag_id)。"""

TAG_TRANSLATIONS: dict[int, dict[str, str]] = {
    101: {"ja": "青い髪", "zh": "蓝发"},
    202: {"ja": "笑顔"},
}
"""FakeMergedTagReader が返す翻訳 (tag_id -> {language: translation})。"""


class _FakeTranslationRow:
    """``get_translations_batch`` が返す行のスタブ。"""

    def __init__(self, language: str, translation: str) -> None:
        self.language = language
        self.translation = translation


class FakeMergedTagReader:
    """TagMetadataWorker が呼ぶ範囲だけを実装した MergedTagReader スタブ。

    ``gate`` を渡すと ``get_translations_batch`` がそれを待ってから返すため、
    「翻訳解決の完了前にダイアログが閉じる」順序をテストから制御できる。
    """

    def __init__(self, translations: dict[int, dict[str, str]], gate: threading.Event | None = None):
        self._translations = translations
        self._gate = gate

    def get_translations_batch(self, tag_ids: list[int]) -> dict[int, list[_FakeTranslationRow]]:
        if self._gate is not None:
            assert self._gate.wait(timeout=15), "gate が解放されませんでした"
        return {
            tag_id: [
                _FakeTranslationRow(language, text) for language, text in self._translations[tag_id].items()
            ]
            for tag_id in tag_ids
            if tag_id in self._translations
        }

    def get_preferred_translations_batch(self, tag_ids: list[int]) -> dict[int, dict[str, str]]:
        return {}

    def get_format_map(self) -> dict[int, str]:
        return {}

    def get_usage_counts_batch(self, tag_ids: list[int]) -> dict[int, dict[int, int]]:
        return {}

    def get_tag_languages(self) -> list[str]:
        return sorted({language for values in self._translations.values() for language in values})

    def search_tags_bulk_all(self, queries: list[str], **kwargs: Any) -> dict[str, list[Any]]:
        return {}


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


def test_open_initializes_uninitialized_fsm_from_project_root(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    parent_image_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未初期化の FileSystemManager でも、開く時点で現在のプロジェクトルートで初期化される。"""
    from lorairo.database import db_core

    project_root = tmp_path / "gui_project"
    project_root.mkdir()
    monkeypatch.setattr(db_core, "IMG_DB_PATH", project_root / "image_database.db")
    fresh_fsm = FileSystemManager()
    assert fresh_fsm.original_images_dir is None
    launcher = CropDialogLauncher(db_manager=crop_db_manager, fsm=fresh_fsm)

    dialog = launcher.open_for_image(parent_image_id)

    assert dialog is not None
    qtbot.addWidget(dialog)
    assert fresh_fsm.original_images_dir is not None
    assert fresh_fsm.original_images_dir.is_relative_to(project_root / "image_dataset")


def test_finished_dialog_is_destroyed_not_only_forgotten(
    qtbot,
    launcher: CropDialogLauncher,
    parent_image_id: int,
) -> None:
    """閉じたダイアログは参照解放だけでなく Qt 側でも破棄され、親の子ツリーに残らない。"""
    from PySide6.QtWidgets import QWidget

    from lorairo.gui.widgets.crop_dialog import CropDialog

    host = QWidget()
    qtbot.addWidget(host)
    dialog = launcher.open_for_image(parent_image_id, parent=host)
    assert dialog is not None
    assert host.findChildren(CropDialog) == [dialog]

    dialog.reject()

    qtbot.waitUntil(lambda: host.findChildren(CropDialog) == [], timeout=5000)
    assert launcher._open_dialogs == []


@pytest.fixture
def translated_parent_image_id(
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    tmp_path: Path,
) -> int:
    """tag_id を持つタグと、tag_id 無しの手動タグを併せ持つ親画像 (#1355)。"""
    source = tmp_path / "translated_parent.png"
    Image.new("RGB", (PARENT_WIDTH, PARENT_HEIGHT), (90, 60, 30)).save(source)
    registered = crop_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    parent_id: int = registered[0]
    crop_db_manager.save_tags(
        parent_id,
        [
            {
                "tag": tag,
                "tag_id": tag_id,
                "model_id": None,
                "existing": True,
                "is_edited_manually": False,
                "confidence_score": None,
            }
            for tag, tag_id in TRANSLATED_TAGS.items()
        ]
        + [
            {
                "tag": "手動タグ",
                "tag_id": None,
                "model_id": None,
                "existing": True,
                "is_edited_manually": True,
                "confidence_score": None,
            }
        ],
    )
    return parent_id


def _translating_launcher(
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    gate: threading.Event | None = None,
) -> CropDialogLauncher:
    """翻訳を返す fake reader を注入したランチャー。"""
    return CropDialogLauncher(
        db_manager=crop_db_manager,
        fsm=fs_manager,
        merged_reader=FakeMergedTagReader(TAG_TRANSLATIONS, gate),
    )


@pytest.mark.gui
def test_translations_reach_dialog_after_open(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    translated_parent_image_id: int,
) -> None:
    """ダイアログを開いた後、非同期に解決された翻訳が候補タグへ反映される (#1355)。"""
    launcher = _translating_launcher(crop_db_manager, fs_manager)

    dialog = launcher.open_for_image(translated_parent_image_id)

    assert dialog is not None
    qtbot.addWidget(dialog)
    # 開いた直後は原文のみ (翻訳待ちで表示をブロックしない)
    assert dialog.is_language_selector_visible() is False
    qtbot.waitUntil(dialog.is_language_selector_visible, timeout=15000)
    assert dialog.current_language() == "ja"
    assert dialog.candidate_labels() == ["blue hair / 青い髪", "smile / 笑顔", "手動タグ"]
    # tag_id を持たない手動タグは原文のまま、原文タグ側は変わらない
    assert dialog.candidate_tags() == ["blue hair", "smile", "手動タグ"]


@pytest.mark.gui
def test_language_can_be_switched_after_translations_arrive(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    translated_parent_image_id: int,
) -> None:
    """解決済みの言語だけがセレクタに並び、切り替えると表示が変わる。"""
    launcher = _translating_launcher(crop_db_manager, fs_manager)
    dialog = launcher.open_for_image(translated_parent_image_id)
    assert dialog is not None
    qtbot.addWidget(dialog)
    qtbot.waitUntil(dialog.is_language_selector_visible, timeout=15000)

    dialog._language_combo.setCurrentText("zh")

    assert dialog.candidate_labels() == ["blue hair / 蓝发", "smile", "手動タグ"]


@pytest.mark.gui
def test_dialog_opens_without_reader(
    qtbot, launcher: CropDialogLauncher, translated_parent_image_id: int
) -> None:
    """MergedTagReader 未注入でもダイアログは開き、原文表示のまま動く。"""
    dialog = launcher.open_for_image(translated_parent_image_id)

    assert dialog is not None
    qtbot.addWidget(dialog)
    assert dialog.is_language_selector_visible() is False
    assert dialog.candidate_labels() == ["blue hair", "smile", "手動タグ"]


@pytest.mark.gui
def test_translations_are_discarded_for_closed_dialog(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    translated_parent_image_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """解決完了より先に閉じられたダイアログへは翻訳を適用しない (破棄済み参照を触らない)。"""
    gate = threading.Event()
    launcher = _translating_launcher(crop_db_manager, fs_manager, gate)
    # 閉じたダイアログは deleteLater で破棄されるため、qtbot の close 対象にはしない
    # (teardown で破棄済み C++ オブジェクトに触れて RuntimeError になる)。
    dialog = launcher.open_for_image(translated_parent_image_id)
    assert dialog is not None
    applied: list[object] = []
    monkeypatch.setattr(dialog, "set_tag_translations", lambda *args, **kwargs: applied.append(args))

    dialog.reject()
    gate.set()

    manager = launcher._tag_metadata_manager
    assert manager is not None
    qtbot.waitUntil(lambda: not manager.active_workers, timeout=15000)
    assert applied == []
    assert launcher._tag_metadata_targets == {}


def test_closing_dialog_requests_cancel_of_its_translation_worker(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    translated_parent_image_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """解決中にダイアログを閉じたら、その worker に協調キャンセルを要求する。"""
    gate = threading.Event()
    launcher = _translating_launcher(crop_db_manager, fs_manager, gate)
    dialog = launcher.open_for_image(translated_parent_image_id)
    assert dialog is not None
    manager = launcher._tag_metadata_manager
    assert manager is not None
    requested: list[str] = []
    original_request = manager.request_cancel_worker

    def _record(worker_id: str, *args: object, **kwargs: object) -> bool:
        requested.append(worker_id)
        return original_request(worker_id, *args, **kwargs)

    monkeypatch.setattr(manager, "request_cancel_worker", _record)
    active_ids = list(manager.active_workers)
    assert len(active_ids) == 1

    dialog.reject()
    gate.set()

    assert requested == active_ids
    qtbot.waitUntil(lambda: not manager.active_workers, timeout=15000)
    assert launcher._tag_metadata_targets == {}


def test_shutdown_cancels_workers_and_blocks_new_ones(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    translated_parent_image_id: int,
) -> None:
    """shutdown は実行中の翻訳 worker を止め、以降はダイアログを開いても worker を起動しない。"""
    gate = threading.Event()
    launcher = _translating_launcher(crop_db_manager, fs_manager, gate)
    first = launcher.open_for_image(translated_parent_image_id)
    assert first is not None
    qtbot.addWidget(first)
    manager = launcher._tag_metadata_manager
    assert manager is not None
    assert manager.active_workers

    gate.set()
    launcher.shutdown()

    qtbot.waitUntil(lambda: not manager.active_workers, timeout=15000)
    assert launcher._tag_metadata_targets == {}
    second = launcher.open_for_image(translated_parent_image_id)
    assert second is not None
    qtbot.addWidget(second)
    assert not manager.active_workers


def test_translations_are_applied_on_gui_thread(
    qtbot,
    crop_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    translated_parent_image_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker の完了は launcher の Signal 経由で queued 配送され、翻訳適用は GUI スレッドで行われる。"""
    from PySide6.QtCore import QCoreApplication, QThread

    launcher = _translating_launcher(crop_db_manager, fs_manager)
    dialog = launcher.open_for_image(translated_parent_image_id)
    assert dialog is not None
    qtbot.addWidget(dialog)
    seen_threads: list[QThread] = []
    original = dialog.set_tag_translations

    def _record(*args: object, **kwargs: object) -> None:
        seen_threads.append(QThread.currentThread())
        original(*args, **kwargs)

    monkeypatch.setattr(dialog, "set_tag_translations", _record)

    qtbot.waitUntil(lambda: bool(seen_threads), timeout=15000)

    app = QCoreApplication.instance()
    assert app is not None
    assert seen_threads == [app.thread()]
