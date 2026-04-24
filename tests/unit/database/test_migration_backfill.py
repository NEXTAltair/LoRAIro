"""マイグレーション f5a6b7c8d9e0 のバックフィルロジックのテスト。

_backfill_project() がディレクトリ名ではなく .lorairo-project メタデータの
logical name を projects.name に使うことを検証する。
"""

import json
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text


def _setup_db(db_path: Path) -> sa.engine.Engine:
    """テスト用 SQLite エンジン作成（projects / images テーブル付き）。"""
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE TABLE projects"
                " (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,"
                "  path TEXT NOT NULL, description TEXT, created_at TIMESTAMP)"
            )
        )
        conn.execute(text("CREATE TABLE images (id INTEGER PRIMARY KEY, project_id INTEGER)"))
        conn.execute(text("INSERT INTO images (id) VALUES (1), (2)"))
        conn.commit()
    return engine


@pytest.mark.unit
class TestBackfillProjectName:
    """_backfill_project() のプロジェクト名取得ロジックのテスト。"""

    def test_uses_metadata_name_when_lorairo_project_exists(self, tmp_path: Path) -> None:
        """.lorairo-project が存在する場合、metadata の name をプロジェクト名として使う。

        ディレクトリ名は 'my_project_20260424_142530' だが、metadata には 'my_project' と
        記録されている。export_dataset() は logical name ('my_project') でフィルタするため、
        backfill も同じ値を projects.name に格納しなければならない。
        """
        from lorairo.database.migrations.versions.f5a6b7c8d9e0_add_projects_table_and_image_project_fk import (
            _backfill_project,
        )

        db_dir = tmp_path / "my_project_20260424_142530"
        db_dir.mkdir()
        (db_dir / ".lorairo-project").write_text(
            json.dumps({"name": "my_project", "created": "20260424_142530"})
        )

        db_path = db_dir / "image_database.db"
        engine = _setup_db(db_path)

        with engine.connect() as conn:
            _backfill_project(conn)
            project_name = conn.execute(text("SELECT name FROM projects")).scalar()

        assert project_name == "my_project"

    def test_falls_back_to_directory_name_when_no_metadata(self, tmp_path: Path) -> None:
        """.lorairo-project が存在しない場合、ディレクトリ名をフォールバックとして使う。"""
        from lorairo.database.migrations.versions.f5a6b7c8d9e0_add_projects_table_and_image_project_fk import (
            _backfill_project,
        )

        db_dir = tmp_path / "fallback_project"
        db_dir.mkdir()

        db_path = db_dir / "image_database.db"
        engine = _setup_db(db_path)

        with engine.connect() as conn:
            _backfill_project(conn)
            project_name = conn.execute(text("SELECT name FROM projects")).scalar()

        assert project_name == "fallback_project"

    def test_images_assigned_to_project(self, tmp_path: Path) -> None:
        """バックフィル後に全 images.project_id が設定される。"""
        from lorairo.database.migrations.versions.f5a6b7c8d9e0_add_projects_table_and_image_project_fk import (
            _backfill_project,
        )

        db_dir = tmp_path / "test_project_20260101_000000"
        db_dir.mkdir()
        (db_dir / ".lorairo-project").write_text(json.dumps({"name": "test_project"}))

        db_path = db_dir / "image_database.db"
        engine = _setup_db(db_path)

        with engine.connect() as conn:
            _backfill_project(conn)
            null_count = conn.execute(text("SELECT COUNT(*) FROM images WHERE project_id IS NULL")).scalar()

        assert null_count == 0
