"""`KohyaVersionExportDialog` の GUI テスト (Issue #1456)。

一時 DB に版を作り、版の一覧 → 選択 → 詳細表示 → 書き出しを worker 経由で通す。
QMessageBox / message_box は tests/unit/gui/conftest.py の autouse で抑止される。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox
from pytestqt.qtbot import QtBot
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_core import create_db_engine
from lorairo.database.repository.dataset import (
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
    TrainingConfigSpec,
)
from lorairo.database.schema import Base, Image
from lorairo.gui.widgets import kohya_version_export_dialog as dialog_module
from lorairo.gui.widgets.kohya_version_export_dialog import KohyaVersionExportDialog

pytestmark = [pytest.mark.unit, pytest.mark.gui]

_TIMEOUT_MS = 10000


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = create_db_engine(f"sqlite:///{tmp_path / 'dialog.db'}")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def repo(session_factory: Callable[[], Session]) -> DatasetRepository:
    return DatasetRepository(session_factory=session_factory)


def _make_image(session_factory: Callable[[], Session], tmp_path: Path, uuid: str) -> int:
    path = tmp_path / "stored" / f"{uuid}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"png-" + uuid.encode())
    with session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=str(path),
            stored_image_path=str(path),
            width=64,
            height=64,
            format="PNG",
            extension=".png",
            filename=path.name,
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


def _config(unmapped: dict[str, object]) -> TrainingConfigSpec:
    return TrainingConfigSpec(
        source_kind="kohya_gui_json",
        source_file_name="config.json",
        raw_content="{}",
        normalized_json=json.dumps({"learning_rate": 0.0001}),
        unmapped_json=json.dumps(unmapped),
    )


@pytest.fixture
def version_id(repo: DatasetRepository, session_factory: Callable[[], Session], tmp_path: Path) -> int:
    image_id = _make_image(session_factory, tmp_path, "img-a")
    dataset_id = repo.ensure_dataset("kariginu")
    vid = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        vid,
        FolderSpec(
            dir_name="10_kariginu", name="kariginu", num_repeats=10, trigger_word="Kari", position=0
        ),
        [
            FolderImageSpec(
                image_id=image_id,
                file_stem="a",
                texts=[
                    LearningTextSpec(extension=".txt", raw_text="Kari, smile", elements=["Kari", "smile"])
                ],
            )
        ],
    )
    repo.add_training_config(dataset_id, vid, _config({"LoRA_type": "LyCORIS/BOFT"}))
    return vid


def _open(qtbot: QtBot, repo: DatasetRepository) -> KohyaVersionExportDialog:
    dialog = KohyaVersionExportDialog(repo)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.version_table.rowCount() > 0, timeout=_TIMEOUT_MS)
    return dialog


def _select_first_version(qtbot: QtBot, dialog: KohyaVersionExportDialog) -> None:
    dialog.version_table.selectRow(0)
    qtbot.waitUntil(lambda: dialog.folder_table.rowCount() > 0, timeout=_TIMEOUT_MS)


def test_lists_versions_and_shows_folders(qtbot: QtBot, repo: DatasetRepository, version_id: int) -> None:
    dialog = _open(qtbot, repo)

    row = [dialog.version_table.item(0, column).text() for column in range(5)]
    assert row == ["kariginu", "v01", str(version_id), "-", "1"]
    assert dialog.version_table.item(0, 5).text() == "1"

    _select_first_version(qtbot, dialog)

    folder_row = [dialog.folder_table.item(0, column).text() for column in range(4)]
    assert folder_row == ["10_kariginu", "10", "1", "Kari"]
    # 「書き出さない」+ 学習設定 1 件
    assert dialog.config_combo.count() == 2
    assert dialog.export_button.isEnabled() is False


def test_unmapped_keys_are_shown_for_selected_config(
    qtbot: QtBot, repo: DatasetRepository, version_id: int
) -> None:
    dialog = _open(qtbot, repo)
    _select_first_version(qtbot, dialog)

    assert dialog.unmapped_label.isHidden()
    dialog.config_combo.setCurrentIndex(1)

    assert not dialog.unmapped_label.isHidden()
    assert "LoRA_type" in dialog.unmapped_label.text()


def test_export_writes_kohya_layout_and_reports(
    qtbot: QtBot,
    repo: DatasetRepository,
    version_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infos: list[str] = []
    monkeypatch.setattr(dialog_module, "show_information", lambda _p, _t, text, *a: infos.append(text))
    dialog = _open(qtbot, repo)
    _select_first_version(qtbot, dialog)
    out_dir = tmp_path / "out"
    dialog.output_dir_edit.setText(str(out_dir))
    assert dialog.export_button.isEnabled()

    dialog.export_button.click()
    qtbot.waitUntil(lambda: bool(infos), timeout=_TIMEOUT_MS)

    assert (out_dir / "10_kariginu" / "a.txt").read_text(encoding="utf-8") == "Kari, smile"
    assert (out_dir / "10_kariginu" / "a.png").is_file()
    assert (out_dir / "dataset_config.toml").is_file()
    assert not (out_dir / "training_config.toml").exists()
    assert "画像数: 1" in infos[0]
    assert dialog.close_button.isEnabled()


def test_export_with_unmapped_config_asks_and_can_be_declined(
    qtbot: QtBot,
    repo: DatasetRepository,
    version_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def decline(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        asked.append(str(args[2]))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    dialog = _open(qtbot, repo)
    _select_first_version(qtbot, dialog)
    dialog.config_combo.setCurrentIndex(1)
    out_dir = tmp_path / "out"
    dialog.output_dir_edit.setText(str(out_dir))

    dialog.export_button.click()

    assert asked and "未変換" in asked[0]
    assert not out_dir.exists()


def test_export_with_config_writes_training_toml(
    qtbot: QtBot,
    repo: DatasetRepository,
    version_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infos: list[str] = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(dialog_module, "show_information", lambda _p, _t, text, *a: infos.append(text))
    dialog = _open(qtbot, repo)
    _select_first_version(qtbot, dialog)
    dialog.config_combo.setCurrentIndex(1)
    out_dir = tmp_path / "out"
    dialog.output_dir_edit.setText(str(out_dir))

    dialog.export_button.click()
    qtbot.waitUntil(lambda: bool(infos), timeout=_TIMEOUT_MS)

    assert (out_dir / "training_config.toml").is_file()


def test_export_to_non_empty_dir_is_rejected_before_worker(
    qtbot: QtBot,
    repo: DatasetRepository,
    version_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(dialog_module, "show_warning", lambda _p, _t, text, *a: warnings.append(text))
    dialog = _open(qtbot, repo)
    _select_first_version(qtbot, dialog)
    out_dir = tmp_path / "busy"
    out_dir.mkdir()
    (out_dir / "keep.txt").write_text("x", encoding="utf-8")
    dialog.output_dir_edit.setText(str(out_dir))

    dialog.export_button.click()

    assert warnings and "空のディレクトリではありません" in warnings[0]
    assert sorted(p.name for p in out_dir.iterdir()) == ["keep.txt"]


def test_export_error_is_reported(
    qtbot: QtBot,
    repo: DatasetRepository,
    version_id: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """保存済み画像が無いなど service が失敗したら、警告を出して再び操作できる。"""
    warnings: list[str] = []
    monkeypatch.setattr(dialog_module, "show_warning", lambda _p, _t, text, *a: warnings.append(text))
    for stored in (tmp_path / "stored").iterdir():
        stored.unlink()
    dialog = _open(qtbot, repo)
    _select_first_version(qtbot, dialog)
    dialog.output_dir_edit.setText(str(tmp_path / "out"))

    dialog.export_button.click()
    qtbot.waitUntil(lambda: bool(warnings), timeout=_TIMEOUT_MS)

    assert dialog.export_button.isEnabled()
    assert dialog.close_button.isEnabled()


def test_empty_database_shows_message(qtbot: QtBot, repo: DatasetRepository) -> None:
    dialog = KohyaVersionExportDialog(repo)
    qtbot.addWidget(dialog)

    qtbot.waitUntil(lambda: "ありません" in dialog.status_label.text(), timeout=_TIMEOUT_MS)
    assert dialog.version_table.rowCount() == 0
