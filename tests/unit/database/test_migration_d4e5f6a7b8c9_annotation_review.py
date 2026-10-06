"""Upgrade / rollback for retained annotation review results."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_core import create_db_engine
from lorairo.database.repository.annotation_review import AnnotationReviewRepository
from lorairo.database.schema import AnnotationReviewRecord

pytestmark = pytest.mark.unit

PREVIOUS_REVISION = "d3e4f5a6b7c8"
REVISION = "d4e5f6a7b8c9"


def _config(db_path: Path) -> Config:
    root = Path(__file__).resolve().parents[3]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "src/lorairo/database/migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


def _prepare_previous_database(db_path: Path) -> None:
    engine = create_db_engine(f"sqlite:///{db_path}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE images (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO images (id) VALUES (1), (2)"))
            connection.execute(text("CREATE TABLE tags (id INTEGER PRIMARY KEY, tag VARCHAR NOT NULL)"))
            connection.execute(text("INSERT INTO tags (id, tag) VALUES (1, 'cat')"))
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
            connection.execute(
                text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                {"revision": PREVIOUS_REVISION},
            )
    finally:
        engine.dispose()


def test_revision_links_to_previous_schema(tmp_path: Path) -> None:
    scripts = ScriptDirectory.from_config(_config(tmp_path / "unused.db"))
    revision = scripts.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION


def test_upgrade_creates_schema_matching_orm_and_preserves_existing_data(tmp_path: Path) -> None:
    db_path = tmp_path / "upgrade.db"
    _prepare_previous_database(db_path)
    command.upgrade(_config(db_path), REVISION)
    engine = create_db_engine(f"sqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("annotation_review_results")}
        expected = AnnotationReviewRecord.__table__
        assert set(columns) == {column.name for column in expected.columns}
        for column in expected.columns:
            assert columns[column.name]["nullable"] == column.nullable
        assert inspector.get_pk_constraint("annotation_review_results")["constrained_columns"] == [
            "image_id"
        ]
        foreign_key = inspector.get_foreign_keys("annotation_review_results")[0]
        assert foreign_key["constrained_columns"] == ["image_id"]
        assert foreign_key["referred_table"] == "images"
        assert foreign_key["options"]["ondelete"] == "CASCADE"
        indexes = inspector.get_indexes("annotation_review_results")
        assert any(
            index["name"] == "ix_annotation_review_results_checked_at"
            and index["column_names"] == ["checked_at"]
            for index in indexes
        )
        with engine.connect() as connection:
            assert connection.execute(text("SELECT id FROM images ORDER BY id")).scalars().all() == [1, 2]
            assert connection.execute(text("SELECT tag FROM tags")).scalar_one() == "cat"
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == REVISION
            )
    finally:
        engine.dispose()


def test_migrated_database_supports_repository_reload_and_image_cascade(tmp_path: Path) -> None:
    db_path = tmp_path / "repository.db"
    _prepare_previous_database(db_path)
    command.upgrade(_config(db_path), REVISION)
    engine = create_db_engine(f"sqlite:///{db_path}")
    try:
        factory = sessionmaker(bind=engine)
        repository = AnnotationReviewRepository(factory)
        repository.save_result(
            image_id=1,
            fingerprint="saved-fingerprint",
            model_name="clef-flash",
            warning_threshold=0.2,
            status="complete",
            items_json='[{"candidate_id":"tag_1","probability":0.1}]',
            error=None,
        )
        stored = AnnotationReviewRepository(factory).get_results()[1]
        assert stored.fingerprint == "saved-fingerprint"
        assert stored.checked_at.tzinfo is not None
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM images WHERE id = 1"))
        assert repository.get_results() == {}
    finally:
        engine.dispose()


def test_downgrade_removes_only_review_results_and_can_upgrade_again(tmp_path: Path) -> None:
    db_path = tmp_path / "rollback.db"
    _prepare_previous_database(db_path)
    config = _config(db_path)
    command.upgrade(config, REVISION)
    command.downgrade(config, PREVIOUS_REVISION)
    engine = create_db_engine(f"sqlite:///{db_path}")
    try:
        assert "annotation_review_results" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT tag FROM tags")).scalar_one() == "cat"
            assert connection.execute(text("SELECT id FROM images ORDER BY id")).scalars().all() == [1, 2]
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == PREVIOUS_REVISION
            )
    finally:
        engine.dispose()
    command.upgrade(config, REVISION)
    engine = create_db_engine(f"sqlite:///{db_path}")
    try:
        assert "annotation_review_results" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
