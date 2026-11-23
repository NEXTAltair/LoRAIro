"""タグ DB 境界の縮退処理がキャンセル由来の SQL 中断を握りつぶさないことの単体テスト (#1621)。

progress handler が実行中 SQL を打ち切ると ``OperationalError("interrupted")`` が上がる。
これは worker スレッドへのキャンセル要求でしか起きないため、縮退保存 (tag_id=None)・
個別検索へのフォールバック・競合 retry へ進まず、そのまま呼び出し元へ伝播させる。
"""

from unittest.mock import Mock, patch

import pytest
from genai_tag_db_tools.models import TagSearchResult
from sqlalchemy.exc import IntegrityError, OperationalError

from lorairo.database.repository.annotation_record import AnnotationRepository

_SEARCH = "lorairo.database.repository.annotation_record.search_tags"


def _interrupted() -> OperationalError:
    return OperationalError("SELECT ...", {}, Exception("interrupted"))


def _wrapped_interrupt() -> ValueError:
    """genai-tag-db-tools が登録時の DB 失敗を ValueError に包んだ形。"""
    try:
        raise _interrupted()
    except OperationalError as error:
        try:
            raise ValueError("データベース操作に失敗しました: interrupted") from error
        except ValueError as wrapped:
            return wrapped


@pytest.fixture
def repository() -> AnnotationRepository:
    repo = AnnotationRepository()
    repo.merged_reader = Mock()
    repo.tag_register_service = Mock()
    return repo


@pytest.mark.unit
def test_single_search_interrupt_propagates_without_registration(repository):
    with patch(_SEARCH, side_effect=_interrupted()) as search:
        with pytest.raises(OperationalError, match="interrupted"):
            repository._get_or_create_tag_id_external(Mock(), "cat")
    assert search.call_count == 1
    repository.tag_register_service.register_tag.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("error_factory", [_interrupted, _wrapped_interrupt])
def test_registration_interrupt_propagates_without_retry_search(repository, error_factory):
    repository.tag_register_service.register_tag.side_effect = error_factory()
    with patch(_SEARCH, return_value=TagSearchResult(items=[])) as search:
        with pytest.raises((OperationalError, ValueError)):
            repository._get_or_create_tag_id_external(Mock(), "new tag")
    # 初回検索の 1 回だけ。競合 retry の再検索へ進まない
    assert search.call_count == 1


@pytest.mark.unit
def test_retry_search_interrupt_propagates(repository):
    repository.tag_register_service.register_tag.side_effect = IntegrityError("i", {}, Exception("dup"))
    with patch(_SEARCH, side_effect=[TagSearchResult(items=[]), _interrupted()]):
        with pytest.raises(OperationalError, match="interrupted"):
            repository._get_or_create_tag_id_external(Mock(), "new tag")


@pytest.mark.unit
def test_bulk_resolution_interrupt_propagates_without_individual_registration(repository):
    repository.merged_reader.search_tags_bulk.side_effect = _interrupted()
    with pytest.raises(OperationalError, match="interrupted"):
        repository.batch_resolve_tag_ids({"cat", "new tag"})
    repository.tag_register_service.register_tag.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize("error_factory", [_interrupted, _wrapped_interrupt])
def test_missing_tag_registration_interrupt_stops_remaining_tags(repository, error_factory):
    repository.merged_reader.search_tags_bulk.return_value = {}
    repository.tag_register_service.register_tag.side_effect = error_factory()
    with patch(_SEARCH) as search:
        with pytest.raises((OperationalError, ValueError)):
            repository.batch_resolve_tag_ids({"new a", "new b", "new c"})
    # 1 件目で止まり、残りのタグの登録や retry 検索へ進まない
    assert repository.tag_register_service.register_tag.call_count == 1
    search.assert_not_called()


@pytest.mark.unit
def test_retry_tag_search_interrupt_propagates(repository):
    repository.merged_reader.search_tags_bulk.return_value = {}
    repository.tag_register_service.register_tag.side_effect = IntegrityError("i", {}, Exception("dup"))
    with patch(_SEARCH, side_effect=_interrupted()):
        with pytest.raises(OperationalError, match="interrupted"):
            repository.batch_resolve_tag_ids({"new a"})


@pytest.mark.unit
def test_canonical_resolution_interrupt_propagates(repository):
    repository.merged_reader.search_tags_bulk.side_effect = _interrupted()
    with pytest.raises(OperationalError, match="interrupted"):
        repository._resolve_danbooru_canonical({"cat"})


@pytest.mark.unit
def test_reader_initialization_interrupt_propagates_and_retries_later():
    """初期化中の中断で tag DB を「利用不可」と確定させない (次回の呼び出しで再初期化する)。"""
    repo = AnnotationRepository()
    with patch(
        "lorairo.database.repository.annotation_record.ensure_tag_db_initialized",
        side_effect=_interrupted(),
    ):
        with pytest.raises(OperationalError, match="interrupted"):
            repo.get_merged_reader()
    assert repo._merged_reader_initialized is False


@pytest.mark.unit
def test_non_interrupt_errors_keep_degrading(repository):
    """中断以外の OperationalError は従来どおり縮退する (回帰防止)。"""
    repository.merged_reader.search_tags_bulk.side_effect = OperationalError(
        "SELECT ...", {}, Exception("no such table")
    )
    assert repository.batch_resolve_tag_ids({"cat"}) == {"cat": None}
    assert repository._resolve_danbooru_canonical({"cat"}) == {}
