"""AnnotationRepository タグ削除・置換バッチ操作のユニットテスト。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lorairo.database.repository.annotation_record import AnnotationRepository


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    return session


@pytest.fixture
def repo(mock_session):
    repo = AnnotationRepository.__new__(AnnotationRepository)
    repo.session_factory = MagicMock(return_value=mock_session)
    return repo


@pytest.mark.unit
class TestRemoveTagFromImagesBatch:
    def test_removes_existing_tag_returns_per_item_results(self, repo, mock_session):
        repo._build_existing_tags_map = MagicMock(return_value={123: {"bad_tag"}, 456: {"bad_tag"}})
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.remove_tag_from_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert results == [(123, "changed"), (456, "changed")]
        mock_session.commit.assert_called_once()

    def test_skips_images_without_tag(self, repo, mock_session):
        repo._build_existing_tags_map = MagicMock(return_value={123: {"other_tag"}, 456: {"bad_tag"}})
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.remove_tag_from_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert (123, "skipped") in results
        assert (456, "changed") in results

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        ok, results = repo.remove_tag_from_images_batch([], "bad_tag")
        assert ok is False
        assert results == []

    def test_empty_tag_returns_false(self, repo, mock_session):
        ok, results = repo.remove_tag_from_images_batch([123], "")
        assert ok is False
        assert results == []

    def test_db_error_rolls_back_and_reraises(self, repo, mock_session):
        from sqlalchemy.exc import SQLAlchemyError

        repo._build_existing_tags_map = MagicMock(side_effect=SQLAlchemyError("db error"))
        with pytest.raises(SQLAlchemyError):
            repo.remove_tag_from_images_batch([123], "bad_tag")
        mock_session.rollback.assert_called_once()


@pytest.mark.unit
class TestReplaceTagForImagesBatch:
    def test_replaces_tag_changed(self, repo, mock_session):
        """変換元あり・変換先なし → changed。"""
        repo._build_existing_tags_map = MagicMock(return_value={123: {"bad_tag"}})
        repo._get_or_create_tag_id_external = MagicMock(return_value=42)
        mock_session.execute = MagicMock(return_value=MagicMock())
        mock_session.add = MagicMock()

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "changed")]
        mock_session.commit.assert_called_once()

    def test_replaces_tag_to_already_exists(self, repo, mock_session):
        """変換元あり・変換先あり → 変換元削除のみ、changed。"""
        repo._build_existing_tags_map = MagicMock(return_value={123: {"bad_tag", "good_tag"}})
        repo._get_or_create_tag_id_external = MagicMock(return_value=42)
        mock_session.execute = MagicMock(return_value=MagicMock())

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "changed")]

    def test_skips_when_from_tag_not_found(self, repo, mock_session):
        """変換元なし → skipped。"""
        repo._build_existing_tags_map = MagicMock(return_value={123: {"other_tag"}})

        ok, results = repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")

        assert ok is True
        assert results == [(123, "skipped")]

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        """空の image_ids → (False, [])。"""
        ok, results = repo.replace_tag_for_images_batch([], "bad_tag", "good_tag")
        assert ok is False
        assert results == []

    def test_empty_from_tag_returns_false(self, repo, mock_session):
        """空の from_tag → (False, [])。"""
        ok, results = repo.replace_tag_for_images_batch([123], "", "good_tag")
        assert ok is False
        assert results == []

    def test_db_error_rolls_back_and_reraises(self, repo, mock_session):
        """DB エラー時にロールバックして再送出。"""
        from sqlalchemy.exc import SQLAlchemyError

        repo._build_existing_tags_map = MagicMock(side_effect=SQLAlchemyError("db error"))
        with pytest.raises(SQLAlchemyError):
            repo.replace_tag_for_images_batch([123], "bad_tag", "good_tag")
        mock_session.rollback.assert_called_once()


@pytest.mark.unit
class TestRestoreTagForImagesBatch:
    def test_restores_rejected_tag_returns_per_item(self, repo, mock_session):
        mock_session.execute = MagicMock(return_value=MagicMock(scalars=MagicMock(return_value=[123])))

        ok, results = repo.restore_tag_for_images_batch([123, 456], "bad_tag")

        assert ok is True
        assert (123, "changed") in results
        assert (456, "skipped") in results
        mock_session.commit.assert_called_once()

    def test_empty_image_ids_returns_false(self, repo, mock_session):
        ok, results = repo.restore_tag_for_images_batch([], "bad_tag")
        assert ok is False
        assert results == []

    def test_empty_tag_returns_false(self, repo, mock_session):
        ok, results = repo.restore_tag_for_images_batch([123], "  ")
        assert ok is False
        assert results == []

    def test_db_error_rolls_back_and_reraises(self, repo, mock_session):
        from sqlalchemy.exc import SQLAlchemyError

        mock_session.execute = MagicMock(side_effect=SQLAlchemyError("db error"))
        with pytest.raises(SQLAlchemyError):
            repo.restore_tag_for_images_batch([123], "bad_tag")
        mock_session.rollback.assert_called_once()


def _search_result(items: list[SimpleNamespace]) -> SimpleNamespace:
    """search_tags 戻り値の簡易スタブ (`.items` を持つ)。"""
    return SimpleNamespace(items=items, total=len(items))


@pytest.mark.unit
class TestResolveCanonicalAndTagId:
    """`_resolve_canonical_and_tag_id` の canonical 解決動作 (#988)。"""

    def test_translation_hit_returns_canonical_string(self, repo):
        """翻訳登録済みの日本語入力 → canonical 文字列 + tag_id を返す。"""
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        item = SimpleNamespace(tag="blue_sky", tag_id=42, source_tag="青空")
        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
            return_value=_search_result([item]),
        ) as mock_search:
            canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "青空")

        assert canonical == "blue_sky"
        assert tag_id == 42
        # resolve_preferred=True で検索されること
        request = mock_search.call_args.args[1]
        assert request.resolve_preferred is True
        assert request.partial is False

    def test_search_scoped_to_danbooru_format(self, repo):
        """検索は danbooru format にスコープする (Codex P2 / PR #994)。

        genai-tag-db-tools は単一 format スコープ時のみ alias→preferred を辿るため、
        ``format_names`` 未指定では alias が canonical へ解決されない。
        """
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        item = SimpleNamespace(tag="long_hair", tag_id=7, source_tag="longhair")
        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
            return_value=_search_result([item]),
        ) as mock_search:
            repo._resolve_canonical_and_tag_id(MagicMock(), "longhair")

        request = mock_search.call_args.args[1]
        assert request.format_names == ["danbooru"]

    def test_alias_resolves_to_preferred(self, repo):
        """alias 入力 → preferred canonical へ解決される (resolve_preferred=True)。"""
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        item = SimpleNamespace(tag="long_hair", tag_id=7, source_tag="longhair")
        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
            return_value=_search_result([item]),
        ):
            canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "longhair")

        assert canonical == "long_hair"
        assert tag_id == 7

    def test_unregistered_japanese_passes_through_and_registers(self, repo):
        """翻訳未登録の日本語 → 入力をそのまま登録 (source_tag 保持)。"""
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        repo._register_new_tag = MagicMock(return_value=999)
        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
            return_value=_search_result([]),
        ):
            canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "未登録タグ")

        assert canonical == "未登録タグ"
        assert tag_id == 999
        # source_tag に生入力が保持されること
        _, source_tag, _ = repo._register_new_tag.call_args.args
        assert source_tag == "未登録タグ"

    def test_english_canonical_direct_input(self, repo):
        """英語 canonical 直接入力 → 従来どおり解決される。"""
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        item = SimpleNamespace(tag="blue_sky", tag_id=5, source_tag="blue_sky")
        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
            return_value=_search_result([item]),
        ):
            canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "blue_sky")

        assert canonical == "blue_sky"
        assert tag_id == 5

    def test_deprecated_alias_resolved_without_new_registration(self, repo):
        """deprecated alias しか無い実在タグ → preferred へ解決し新規登録しない (Issue #1212)。"""
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        repo._register_new_tag = MagicMock()
        item = SimpleNamespace(tag="sparkle", tag_id=5800, source_tag="sparkles")

        def fake_search(reader, request):
            if request.include_deprecated:
                return _search_result([item])
            return _search_result([])

        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
            side_effect=fake_search,
        ):
            canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "sparkles")

        assert canonical == "sparkle"
        assert tag_id == 5800
        repo._register_new_tag.assert_not_called()

    def test_merged_reader_unavailable_returns_normalized_none(self, repo):
        """外部 tag_db 未初期化 → 正規化入力 + tag_id=None で縮退。"""
        repo._get_merged_reader = MagicMock(return_value=None)
        canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "blue_sky")

        assert canonical == "blue_sky"
        assert tag_id is None

    def test_empty_after_normalization_returns_input_none(self, repo):
        """正規化で空文字になる入力 → 入力をそのまま返し tag_id=None (検索しない)。"""
        repo._get_merged_reader = MagicMock(return_value=MagicMock())
        with patch(
            "lorairo.database.repository.annotation_record.search_tags",
        ) as mock_search:
            canonical, tag_id = repo._resolve_canonical_and_tag_id(MagicMock(), "___")

        assert canonical == "___"
        assert tag_id is None
        mock_search.assert_not_called()


@pytest.mark.unit
class TestAddTagToImagesBatchCanonical:
    """`add_tag_to_images_batch` の canonical 解決後 dedup 動作 (#988)。"""

    def test_stores_resolved_canonical_not_raw_input(self, repo, mock_session):
        """日本語入力 → canonical 文字列で保存される。"""
        repo._resolve_canonical_and_tag_id = MagicMock(return_value=("blue_sky", 42))
        repo._build_existing_tags_map = MagicMock(return_value={})
        mock_session.add = MagicMock()

        ok, count = repo.add_tag_to_images_batch([1], "青空", model_id=None)

        assert ok is True
        assert count == 1
        added = mock_session.add.call_args.args[0]
        assert added.tag == "blue_sky"
        assert added.tag_id == 42
        assert added.is_edited_manually is True

    def test_dedup_uses_resolved_canonical(self, repo, mock_session):
        """日本語入力が既存 canonical と重複 → skip される。"""
        repo._resolve_canonical_and_tag_id = MagicMock(return_value=("blue_sky", 42))
        repo._build_existing_tags_map = MagicMock(return_value={1: {"blue_sky"}})
        mock_session.add = MagicMock()

        ok, count = repo.add_tag_to_images_batch([1], "青空", model_id=None)

        assert ok is True
        assert count == 0
        mock_session.add.assert_not_called()

    def test_resolution_runs_once_for_all_images(self, repo, mock_session):
        """canonical 解決は画像数に関わらず1回だけ実行される (dedup の前)。"""
        repo._resolve_canonical_and_tag_id = MagicMock(return_value=("blue_sky", 42))
        repo._build_existing_tags_map = MagicMock(return_value={})
        mock_session.add = MagicMock()

        ok, count = repo.add_tag_to_images_batch([1, 2, 3], "青空", model_id=None)

        assert ok is True
        assert count == 3
        assert repo._resolve_canonical_and_tag_id.call_count == 1
        for call in mock_session.add.call_args_list:
            assert call.args[0].tag == "blue_sky"

    def test_dedup_normalizes_formatting_difference(self, repo, mock_session):
        """既存行が書式違い (space/underscore) でも canonical dedup で重複を検出する。

        Codex P2 (PR #994): `_build_existing_tags_map` は DB の生値 (小文字) を返すため、
        旧行が `blue sky` で解決後が `blue_sky` のように書式だけ異なると重複を見逃して
        二重登録していた。両辺を TagCleaner.clean_format で正規化して比較する。
        """
        repo._resolve_canonical_and_tag_id = MagicMock(return_value=("blue_sky", 42))
        repo._build_existing_tags_map = MagicMock(return_value={1: {"blue sky"}})
        mock_session.add = MagicMock()

        ok, count = repo.add_tag_to_images_batch([1], "青空", model_id=None)

        assert ok is True
        assert count == 0
        mock_session.add.assert_not_called()


@pytest.mark.unit
class TestGetRejectedTags:
    def test_returns_rejected_tag_dicts(self, repo, mock_session):
        row = MagicMock(tag="bad_tag", tag_id=7, is_edited_manually=False, reject_reason="not_needed")
        mock_session.execute = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[row])))

        result = repo.get_rejected_tags(42)

        assert result == [
            {"tag": "bad_tag", "tag_id": 7, "is_edited_manually": False, "reject_reason": "not_needed"}
        ]

    def test_empty_when_no_rejected(self, repo, mock_session):
        mock_session.execute = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        assert repo.get_rejected_tags(42) == []
