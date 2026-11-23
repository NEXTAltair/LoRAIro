"""CLI 統合テスト用の共有 fixture。

`-p PROJECT` 付きの CLI 呼び出しは毎回 `db_core._prepare_project_database` を通り、
既に Alembic head の DB にも `alembic command.upgrade` を実行する。upgrade 自体は no-op だが、
migration スクリプト群の読み込みに 1 回 1 秒以上かかる。ここではその読み込みを、
DB が既に head にあるときだけ省く。head でない DB は本物の upgrade を通す。

Alembic の実経路 (新規 DB の stamp と既存 DB の upgrade) は、これらの fixture を使わない
`test_cli_workflow.py` が引き続き検証する。
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest

from lorairo.database import db_core


def _alembic_revisions(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as conn:
        return {row[0] for row in conn.execute("SELECT version_num FROM alembic_version")}


@pytest.fixture(scope="session")
def prepared_project_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """本物の `_prepare_project_database` で作った、Alembic head の空プロジェクト DB。

    テストはこのファイルを直接開かず、`shutil.copyfile` した複製を使う。
    """
    template = tmp_path_factory.mktemp("project_db_template") / "image_database.db"
    engine = db_core._prepare_project_database(template)
    engine.dispose()
    # WAL の内容を本体に書き戻してから複製元にする (最後の接続を閉じると -wal は消える)
    with closing(sqlite3.connect(template)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    assert not template.with_name(template.name + "-wal").exists()
    return template


@pytest.fixture
def skip_alembic_upgrade_at_head(
    prepared_project_db_template: Path, monkeypatch: pytest.MonkeyPatch
) -> Callable[[Path], None]:
    """DB が既に head なら `_upgrade_alembic_head` の migration 読み込みを省く。

    head の revision は、本物の stamp を通した template DB から読む。head でない DB では
    元の `_upgrade_alembic_head` をそのまま呼ぶ。
    """
    head = _alembic_revisions(prepared_project_db_template)
    assert head, "template DB が Alembic head に stamp されていない"
    original = db_core._upgrade_alembic_head

    def upgrade_unless_at_head(project_db_path: Path) -> None:
        if _alembic_revisions(project_db_path) == head:
            return
        original(project_db_path)

    monkeypatch.setattr(db_core, "_upgrade_alembic_head", upgrade_unless_at_head)
    return upgrade_unless_at_head


@pytest.fixture
def copy_prepared_project_db(
    prepared_project_db_template: Path,
) -> Callable[[Path], None]:
    """`project create` 直後の空 DB を、準備済み template の複製で置き換える関数を返す。"""

    def copy_into(project_dir: Path) -> None:
        db_file = project_dir / "image_database.db"
        assert db_file.is_file() and db_file.stat().st_size == 0, "project create 直後の空 DB を想定"
        shutil.copyfile(prepared_project_db_template, db_file)

    return copy_into
