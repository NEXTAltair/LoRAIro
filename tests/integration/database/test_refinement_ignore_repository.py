"""RefinementIgnoreRepository の統合テスト (#931)。

テスト DB (db_session_factory fixture) を使い、tag + reason_code 単位の
ignore 永続化・冪等性・一覧取得・解除を検証する。
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from lorairo.database.repository.refinement_ignore import RefinementIgnoreRepository
from lorairo.database.schema import Base

pytestmark = pytest.mark.integration


@pytest.fixture
def ignore_repo(db_session_factory) -> RefinementIgnoreRepository:
    return RefinementIgnoreRepository(session_factory=db_session_factory)


def test_add_and_is_ignored(ignore_repo: RefinementIgnoreRepository) -> None:
    assert ignore_repo.is_ignored("blue__eyes", "normalization_changes_tag") is False
    ignore_repo.add_ignore("blue__eyes", "normalization_changes_tag")
    assert ignore_repo.is_ignored("blue__eyes", "normalization_changes_tag") is True


def test_add_ignore_is_idempotent(ignore_repo: RefinementIgnoreRepository) -> None:
    """同一 (tag, reason_code) を二重登録しても例外にならず1件のまま。"""
    ignore_repo.add_ignore("flower", "broad_single_word")
    ignore_repo.add_ignore("flower", "broad_single_word")
    assert ignore_repo.list_ignored() == {("flower", "broad_single_word")}


def test_same_tag_different_reason_codes_coexist(ignore_repo: RefinementIgnoreRepository) -> None:
    """同一タグでも reason_code が違えば別レコードとして共存する。"""
    ignore_repo.add_ignore("flower", "broad_single_word")
    ignore_repo.add_ignore("flower", "normalization_changes_tag")
    assert ignore_repo.list_ignored() == {
        ("flower", "broad_single_word"),
        ("flower", "normalization_changes_tag"),
    }


def test_remove_ignore(ignore_repo: RefinementIgnoreRepository) -> None:
    ignore_repo.add_ignore("bad_id", "training_unsuitable")
    ignore_repo.remove_ignore("bad_id", "training_unsuitable")
    assert ignore_repo.is_ignored("bad_id", "training_unsuitable") is False


def test_remove_ignore_missing_is_noop(ignore_repo: RefinementIgnoreRepository) -> None:
    """未登録の解除は例外にならない (冪等)。"""
    ignore_repo.remove_ignore("nonexistent", "broad_single_word")
    assert ignore_repo.list_ignored() == set()


# #1053: 画像スコープ ---------------------------------------------------------


def test_image_scoped_ignore_is_isolated(ignore_repo):
    """画像限定スコープは他画像の評価に効かない。"""
    ignore_repo.add_ignore("heart", "alias_tag", image_id=None)  # 全画像
    ignore_repo.add_ignore("star", "alias_tag", image_id=7)  # 画像7限定

    assert ignore_repo.list_ignored() == {("heart", "alias_tag")}
    assert ignore_repo.list_ignored(7) == {("heart", "alias_tag"), ("star", "alias_tag")}
    assert ignore_repo.list_ignored(8) == {("heart", "alias_tag")}


def test_scoped_add_is_idempotent_per_scope(ignore_repo):
    """同一スコープの再登録は冪等、別スコープは共存する。"""
    ignore_repo.add_ignore("heart", "alias_tag", image_id=7)
    ignore_repo.add_ignore("heart", "alias_tag", image_id=7)
    ignore_repo.add_ignore("heart", "alias_tag", image_id=None)
    ignore_repo.add_ignore("heart", "alias_tag", image_id=None)

    entries = ignore_repo.list_ignored_entries()
    scopes = sorted((e["image_id"] for e in entries), key=lambda v: (v is not None, v))
    assert scopes == [None, 7]


def test_remove_ignore_respects_scope(ignore_repo):
    """解除は指定スコープの行だけ消す。"""
    ignore_repo.add_ignore("heart", "alias_tag", image_id=None)
    ignore_repo.add_ignore("heart", "alias_tag", image_id=7)

    ignore_repo.remove_ignore("heart", "alias_tag", image_id=7)

    assert ignore_repo.is_ignored("heart", "alias_tag", image_id=None) is True
    assert ignore_repo.is_ignored("heart", "alias_tag", image_id=7) is False


def test_list_ignored_entries_returns_scope(ignore_repo):
    """管理 UI 向け列挙はスコープ (image_id) を含む。"""
    ignore_repo.add_ignore("heart", "alias_tag", image_id=7)

    entries = ignore_repo.list_ignored_entries()

    assert len(entries) == 1
    assert entries[0]["tag"] == "heart"
    assert entries[0]["reason_code"] == "alias_tag"
    assert entries[0]["image_id"] == 7


def test_add_ignore_propagates_fk_violation(tmp_path):
    """存在しない画像への image_id 登録は FK 違反として伝播する (PR #1082 Codex P2)。

    重複 (UNIQUE 違反) だけが冪等の正常系で、FK 違反まで握ると「保存されていないのに
    UI が成功として進む」ため IntegrityError を伝播させる。共通 fixture は
    PRAGMA foreign_keys を有効化しないため、専用エンジンで検証する。
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'fk_ignore.db'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection: sqlite3.Connection, _record: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    repo = RefinementIgnoreRepository(
        session_factory=sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )

    with pytest.raises(IntegrityError):
        repo.add_ignore("heart", "alias_tag", image_id=999)

    assert repo.list_ignored_entries() == []
    engine.dispose()
