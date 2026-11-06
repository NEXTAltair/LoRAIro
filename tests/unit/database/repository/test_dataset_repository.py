"""`DatasetRepository` の単体テスト (Issue #1413)。

FK 制約を有効にした既存の接続設定 (`create_db_engine`) で、版・フォルダ・学習テキスト・
学習設定の永続化と、同名衝突時に中途半端な行が残らないことを検証する。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from lorairo.database.db_core import create_db_engine
from lorairo.database.repository.dataset import (
    DatasetConflictError,
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
    TrainingConfigSpec,
)
from lorairo.database.schema import (
    Base,
    DatasetFolder,
    DatasetFolderImage,
    DatasetLearningText,
    Image,
    Tag,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def fk_engine(tmp_path: Path) -> Iterator[Engine]:
    """`PRAGMA foreign_keys=ON` を設定する既存の接続設定で作ったエンジン。"""
    engine = create_db_engine(f"sqlite:///{tmp_path / 'dataset_repo.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(fk_engine: Engine) -> Callable[[], Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=fk_engine)


@pytest.fixture
def repo(session_factory: Callable[[], Session]) -> DatasetRepository:
    return DatasetRepository(session_factory=session_factory)


def _insert_image(session_factory: Callable[[], Session], uuid: str = "img-1") -> int:
    """テスト用画像を 1 件作成して id を返す。"""
    with session_factory() as session:
        image = Image(
            uuid=uuid,
            phash=f"phash-{uuid}",
            original_image_path=f"/tmp/{uuid}.png",
            stored_image_path=f"/tmp/{uuid}.png",
            width=512,
            height=512,
            format="PNG",
            extension=".png",
            filename=f"{uuid}.png",
        )
        session.add(image)
        session.commit()
        image_id: int = image.id
    return image_id


def _folder(dir_name: str = "10_kariginu", position: int = 0) -> FolderSpec:
    name = dir_name.split("_", 1)[1]
    return FolderSpec(
        dir_name=dir_name, name=name, num_repeats=10, trigger_word="Kariginu", position=position
    )


def _text(raw_text: str) -> LearningTextSpec:
    return LearningTextSpec(extension=".txt", raw_text=raw_text, elements=raw_text.split(", "))


def _count(session_factory: Callable[[], Session], model: type[Base]) -> int:
    with session_factory() as session:
        count: int = session.execute(select(func.count()).select_from(model)).scalar_one()
    return count


def test_ensure_dataset_returns_same_id_for_same_name(repo: DatasetRepository) -> None:
    first = repo.ensure_dataset("kariginu", "狩衣")
    second = repo.ensure_dataset("kariginu")

    assert first == second


def test_same_image_in_two_folders_keeps_separate_texts(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")

    repo.add_folder(
        version_id,
        _folder("10_kariginu", 0),
        [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    repo.add_folder(
        version_id,
        _folder("5_style", 1),
        [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("(style:1.2), long_sleeves")])],
    )

    snapshot = repo.get_version_snapshot(version_id)
    raw_texts = [folder.images[0].texts[0].raw_text for folder in snapshot.folders]

    assert snapshot.dataset_name == "kariginu"
    assert snapshot.version_name == "v01"
    assert [folder.dir_name for folder in snapshot.folders] == ["10_kariginu", "5_style"]
    assert raw_texts == ["Kariginu, 1girl", "(style:1.2), long_sleeves"]
    assert snapshot.folders[1].images[0].texts[0].elements == ["(style:1.2)", "long_sleeves"]
    # 画像直下のタグには書かない
    assert _count(session_factory, Tag) == 0


def test_create_version_with_same_name_raises_conflict(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    repo.create_version(dataset_id, "v01")

    with pytest.raises(DatasetConflictError):
        repo.create_version(dataset_id, "v01")


def test_add_folder_with_same_dir_name_raises_conflict(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    images = [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("a")])]
    repo.add_folder(version_id, _folder(), images)

    with pytest.raises(DatasetConflictError):
        repo.add_folder(version_id, _folder(), images)

    assert _count(session_factory, DatasetFolder) == 1
    assert _count(session_factory, DatasetFolderImage) == 1
    assert _count(session_factory, DatasetLearningText) == 1


def test_add_folder_is_atomic(repo: DatasetRepository, session_factory: Callable[[], Session]) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    images = [
        FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("Kariginu")]),
        # 存在しない image_id (FK 違反)
        FolderImageSpec(image_id=image_id + 999, file_stem="b", texts=[_text("broken")]),
    ]

    with pytest.raises(DatasetConflictError):
        repo.add_folder(version_id, _folder(), images)

    assert _count(session_factory, DatasetFolder) == 0
    assert _count(session_factory, DatasetFolderImage) == 0
    assert _count(session_factory, DatasetLearningText) == 0


def test_update_learning_text_elements_keeps_raw_text(
    repo: DatasetRepository, session_factory: Callable[[], Session]
) -> None:
    image_id = _insert_image(session_factory)
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    repo.add_folder(
        version_id,
        _folder(),
        [FolderImageSpec(image_id=image_id, file_stem="a", texts=[_text("Kariginu, 1girl")])],
    )
    text = repo.get_version_snapshot(version_id).folders[0].images[0].texts[0]
    assert text.is_edited is False

    repo.update_learning_text_elements(text.id, ["Kariginu", "狩衣"])

    updated = repo.get_version_snapshot(version_id).folders[0].images[0].texts[0]
    assert updated.raw_text == "Kariginu, 1girl"
    assert updated.elements == ["Kariginu", "狩衣"]
    assert updated.is_edited is True
    with session_factory() as session:
        stored = session.get(DatasetLearningText, text.id)
        assert stored is not None
        # 日本語は ensure_ascii=False のまま保存される
        assert stored.elements_json == json.dumps(["Kariginu", "狩衣"], ensure_ascii=False)


def test_set_folder_trigger_word(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    folder_id = repo.add_folder(version_id, _folder(), [])

    repo.set_folder_trigger_word(folder_id, None)

    folder = repo.get_version_snapshot(version_id).folders[0]
    assert folder.id == folder_id
    assert folder.trigger_word is None


def test_version_parent_is_recorded(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    parent_id = repo.create_version(dataset_id, "v01")
    child_id = repo.create_version(dataset_id, "v02", parent_version_id=parent_id)

    assert repo.get_version_snapshot(child_id).parent_version_id == parent_id
    assert repo.get_version_snapshot(parent_id).parent_version_id is None


def test_get_version_snapshot_missing_raises(repo: DatasetRepository) -> None:
    with pytest.raises(LookupError):
        repo.get_version_snapshot(12345)


def test_training_config_roundtrip(repo: DatasetRepository) -> None:
    dataset_id = repo.ensure_dataset("kariginu")
    version_id = repo.create_version(dataset_id, "v01")
    spec = TrainingConfigSpec(
        source_kind="kohya_gui_json",
        source_file_name="kariginu.json",
        raw_content='{"output_name": "kariginu"}',
        normalized_json='{"output_name": "kariginu"}',
        unmapped_json="{}",
        target_script="sdxl_train_network.py",
        output_name="kariginu",
        base_model="sd_xl_base_1.0.safetensors",
        resolution="1024,1024",
        network_dim=32,
        network_alpha=16.0,
        learning_rate=0.0001,
    )

    config_id = repo.add_training_config(dataset_id, version_id, spec)
    fetched = repo.get_training_config(config_id)
    listed = repo.list_training_configs(dataset_id)

    assert fetched.id == config_id
    assert fetched.dataset_id == dataset_id
    assert fetched.version_id == version_id
    assert fetched.created_at is not None
    for field in TrainingConfigSpec.__dataclass_fields__:
        assert getattr(fetched, field) == getattr(spec, field)
    assert listed == [fetched]


def test_get_training_config_missing_raises(repo: DatasetRepository) -> None:
    with pytest.raises(LookupError):
        repo.get_training_config(999)
