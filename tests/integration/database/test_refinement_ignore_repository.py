"""RefinementIgnoreRepository の統合テスト (#931)。

テスト DB (db_session_factory fixture) を使い、tag + reason_code 単位の
ignore 永続化・冪等性・一覧取得・解除を検証する。
"""

from __future__ import annotations

import pytest

from lorairo.database.repository.refinement_ignore import RefinementIgnoreRepository

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
