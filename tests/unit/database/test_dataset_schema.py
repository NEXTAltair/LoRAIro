"""データセット関連テーブル (Issue #1404 / #1412) のスキーマと Alembic migration のテスト。"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.orm import Session

from lorairo.database.db_core import create_db_engine
from lorairo.database.schema import (
    Base,
    Dataset,
    DatasetFolder,
    DatasetFolderImage,
    DatasetLearningText,
    DatasetVersion,
    Image,
    TrainingConfig,
)

pytestmark = pytest.mark.unit

PREVIOUS_REVISION = "d4e5f6a7b8c9"

DATASET_TABLES = {
    "datasets",
    "dataset_versions",
    "dataset_folders",
    "dataset_folder_images",
    "dataset_learning_texts",
    "training_configs",
}


def _make_alembic_config(db_path: Path) -> Config:
    project_root = Path(__file__).resolve().parents[3]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "src/lorairo/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _seed_pre_dataset_db(db_path: Path) -> None:
    """データセット追加前 (revision d4e5f6a7b8c9) の最小 DB を用意する。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE images (id INTEGER NOT NULL PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": PREVIOUS_REVISION},
        )
    engine.dispose()


ForeignKeyShape = tuple[tuple[str, ...], str, tuple[str, ...], str | None]


class TableShape(NamedTuple):
    """比較用に正規化したテーブル構造。"""

    columns: dict[str, tuple[str, bool]]
    foreign_keys: list[ForeignKeyShape]
    uniques: list[tuple[str, ...]]
    indexes: list[tuple[str | None, tuple[str, ...], bool]]


def _describe_tables(engine: Engine) -> dict[str, TableShape]:
    """比較用に、データセット関連テーブルの列・FK・UNIQUE・index を正規化して返す。"""
    inspector = inspect(engine)
    described: dict[str, TableShape] = {}
    for table in sorted(DATASET_TABLES):
        columns = {c["name"]: (str(c["type"]), bool(c["nullable"])) for c in inspector.get_columns(table)}
        foreign_keys: list[ForeignKeyShape] = sorted(
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
                (fk.get("options") or {}).get("ondelete"),
            )
            for fk in inspector.get_foreign_keys(table)
        )
        uniques = sorted(tuple(u["column_names"]) for u in inspector.get_unique_constraints(table))
        indexes = sorted(
            (
                (i["name"], tuple(str(c) for c in i["column_names"]), bool(i["unique"]))
                for i in inspector.get_indexes(table)
            ),
            key=lambda shape: (shape[0] or "", shape[1]),
        )
        described[table] = TableShape(columns, foreign_keys, uniques, indexes)
    return described


def test_create_all_creates_dataset_tables(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'create_all.db'}")
    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    engine.dispose()

    assert DATASET_TABLES <= table_names


def test_alembic_upgrade_head_creates_dataset_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "upgrade.db"
    _seed_pre_dataset_db(db_path)

    command.upgrade(_make_alembic_config(db_path), "head")

    engine = create_engine(f"sqlite:///{db_path}")
    table_names = set(inspect(engine).get_table_names())
    engine.dispose()

    assert DATASET_TABLES <= table_names


def test_alembic_and_create_all_produce_same_dataset_tables(tmp_path: Path) -> None:
    """列・FK (ondelete 含む)・UNIQUE・index が create_all と migration で一致する。"""
    migrated_path = tmp_path / "migrated.db"
    _seed_pre_dataset_db(migrated_path)
    command.upgrade(_make_alembic_config(migrated_path), "head")
    migrated_engine = create_engine(f"sqlite:///{migrated_path}")
    migrated = _describe_tables(migrated_engine)
    migrated_engine.dispose()

    created_engine = create_engine(f"sqlite:///{tmp_path / 'created.db'}")
    Base.metadata.create_all(created_engine)
    created = _describe_tables(created_engine)
    created_engine.dispose()

    assert migrated == created


def test_dataset_tables_have_expected_constraints(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'constraints.db'}")
    Base.metadata.create_all(engine)
    described = _describe_tables(engine)
    engine.dispose()

    assert ("ix_datasets_name", ("name",), True) in described["datasets"].indexes
    assert ("ix_dataset_folder_images_image_id", ("image_id",), False) in described[
        "dataset_folder_images"
    ].indexes
    assert described["dataset_versions"].uniques == [("dataset_id", "name")]
    assert described["dataset_folders"].uniques == [("version_id", "dir_name")]
    assert described["dataset_folder_images"].uniques == [("folder_id", "file_stem")]
    assert described["dataset_learning_texts"].uniques == [("folder_image_id", "extension")]
    assert described["dataset_versions"].foreign_keys == [
        (("dataset_id",), "datasets", ("id",), "CASCADE"),
        (("parent_version_id",), "dataset_versions", ("id",), "SET NULL"),
    ]
    assert described["dataset_folder_images"].foreign_keys == [
        (("folder_id",), "dataset_folders", ("id",), "CASCADE"),
        (("image_id",), "images", ("id",), "CASCADE"),
    ]
    assert described["training_configs"].foreign_keys == [
        (("dataset_id",), "datasets", ("id",), "CASCADE"),
        (("version_id",), "dataset_versions", ("id",), "SET NULL"),
    ]


def test_alembic_has_single_head(tmp_path: Path) -> None:
    script = ScriptDirectory.from_config(_make_alembic_config(tmp_path / "heads.db"))

    heads = script.get_heads()

    assert len(heads) == 1
    # データセットの migration (e5f6a7b8c9d0) は d4e5f6a7b8c9 の直後にあり、head までの系列に含まれる
    dataset_revision = script.get_revision("e5f6a7b8c9d0")
    assert dataset_revision is not None
    assert dataset_revision.down_revision == PREVIOUS_REVISION
    assert "e5f6a7b8c9d0" in {rev.revision for rev in script.iterate_revisions(heads[0], "base")}


def test_alembic_downgrade_drops_dataset_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "downgrade.db"
    _seed_pre_dataset_db(db_path)
    cfg = _make_alembic_config(db_path)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, PREVIOUS_REVISION)

    engine = create_engine(f"sqlite:///{db_path}")
    table_names = set(inspect(engine).get_table_names())
    engine.dispose()

    assert not (DATASET_TABLES & table_names)
    assert "images" in table_names


def _make_image(session: Session) -> Image:
    image = Image(
        uuid="uuid-1",
        phash="phash-1",
        original_image_path="/src/a.png",
        stored_image_path="image_dataset/a.png",
        width=64,
        height=64,
        format="PNG",
        extension=".png",
    )
    session.add(image)
    session.flush()
    return image


def test_deleting_version_cascades_to_folders_texts(tmp_path: Path) -> None:
    # 実運用と同じ接続設定 (PRAGMA foreign_keys=ON) のエンジンを使う
    engine = create_db_engine(f"sqlite:///{tmp_path / 'cascade.db'}")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            image = _make_image(session)
            dataset = Dataset(name="kariginu")
            session.add(dataset)
            session.flush()
            version = DatasetVersion(dataset_id=dataset.id, name="v01")
            session.add(version)
            session.flush()
            child_version = DatasetVersion(dataset_id=dataset.id, name="v02", parent_version_id=version.id)
            folder = DatasetFolder(
                version_id=version.id,
                dir_name="10_kariginu",
                name="kariginu",
                num_repeats=10,
                trigger_word="Kariginu",
                position=0,
            )
            session.add_all([child_version, folder])
            session.flush()
            folder_image = DatasetFolderImage(folder_id=folder.id, image_id=image.id, file_stem="a")
            session.add(folder_image)
            session.flush()
            learning_text = DatasetLearningText(
                folder_image_id=folder_image.id,
                extension=".txt",
                raw_text="Kariginu, long_sleeves",
                elements_json='["Kariginu", "long_sleeves"]',
            )
            config = TrainingConfig(
                dataset_id=dataset.id,
                version_id=version.id,
                source_kind="kohya_gui_json",
                source_file_name="config.json",
                raw_content="{}",
                normalized_json="{}",
                unmapped_json="{}",
            )
            session.add_all([learning_text, config])
            session.commit()
            assert learning_text.is_edited is False
            version_id = version.id
            child_version_id = child_version.id
            config_id = config.id

        # ORM の cascade ではなく DB の ON DELETE を検証するため Core で削除する
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM dataset_versions WHERE id = :id"), {"id": version_id})

        with Session(engine) as session:
            assert session.scalars(select(DatasetFolder)).all() == []
            assert session.scalars(select(DatasetFolderImage)).all() == []
            assert session.scalars(select(DatasetLearningText)).all() == []
            # 画像本体は消えない
            assert len(session.scalars(select(Image)).all()) == 1
            # 自己参照・training_configs の版参照は SET NULL
            child = session.get(DatasetVersion, child_version_id)
            assert child is not None
            assert child.parent_version_id is None
            remaining_config = session.get(TrainingConfig, config_id)
            assert remaining_config is not None
            assert remaining_config.version_id is None
    finally:
        engine.dispose()
