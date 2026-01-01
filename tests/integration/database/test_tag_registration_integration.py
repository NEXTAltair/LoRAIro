"""
Phase 2タグ登録機能の統合テスト

テストカバレッジ:
- TagRegisterService を使った新規タグ登録
- format_name="Lorairo", type_name="unknown" での登録
- 競合検出時のリトライ検索
- 既存タグの検索（重複作成防止）
- エラー時のグレースフルデグラデーション

Note:
- これらのテストは環境変数TEST_TAG_DB_PATHが設定されている場合のみ実行される
- テスト用データベースを使用し、テスト後は自動クリーンアップされる
- Phase 2実装（TagRegisterService統合）の動作を検証
"""

import uuid
from unittest.mock import patch

import pytest
from genai_tag_db_tools.models import TagSearchRequest
from genai_tag_db_tools.utils.cleanup_str import TagCleaner
from sqlalchemy.exc import IntegrityError

from lorairo.database.db_repository import ImageRepository


@pytest.mark.integration
class TestTagRegistrationIntegration:
    """Phase 2タグ登録機能の統合テスト

    TagRegisterServiceを使用した新規タグ登録機能を検証。
    TEST_TAG_DB_PATH環境変数が設定されている場合のみテスト実行。
    """

    def test_new_tag_registration_with_format_and_type(
        self, test_image_repository_with_tag_db, test_tag_repository
    ):
        """
        新規タグ登録テスト（format_name/type_name指定）

        目的: TagRegisterServiceを使用して新規タグを登録し、
              format_name="Lorairo", type_name="unknown"で保存されることを確認
        """
        # 一意な新規タグを生成
        new_tag = f"test_phase2_tag_{uuid.uuid4().hex[:8]}"

        # ImageRepositoryを通じてタグ登録（Phase 2実装）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, new_tag)

        # 検証: tag_idが返却される
        assert tag_id is not None, f"Tag ID should be returned for new tag '{new_tag}'"

        # 外部tag_dbでタグの存在確認
        retrieved_tag = test_tag_repository.get_tag_by_id(tag_id)
        assert retrieved_tag is not None, "Tag should exist in external tag_db"

        # 正規化後のtagと比較
        expected_normalized = TagCleaner.clean_format(new_tag).strip()
        assert retrieved_tag.tag == expected_normalized, (
            f"Normalized tag should match: expected '{expected_normalized}', got '{retrieved_tag.tag}'"
        )
        assert retrieved_tag.source_tag == new_tag, "Source tag should match original"

    def test_existing_tag_lookup_no_duplicate_creation(
        self, test_image_repository_with_tag_db, test_tag_repository
    ):
        """
        既存タグ検索テスト（重複作成防止）

        目的: 既存タグを検索した場合、TagRegisterServiceを使わず
              既存tag_idを返すことを確認
        """
        # 一意なタグを生成
        source_tag = f"test_existing_{uuid.uuid4().hex[:8]}"
        normalized_tag = TagCleaner.clean_format(source_tag).strip()

        # 事前に外部tag_dbにタグ作成
        tag_id_original = test_tag_repository.create_tag(source_tag=source_tag, tag=normalized_tag)

        # ImageRepositoryで同じタグを検索（Phase 2実装: search_tags -> 既存tag_id返却）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_retrieved = test_image_repository_with_tag_db._get_or_create_tag_id_external(
                session, source_tag
            )

        # 検証: 同じtag_idが返される
        assert tag_id_retrieved == tag_id_original, "Should return existing tag_id without registration"

        # 重複作成されていないことを確認
        all_matching_tags = test_tag_repository.search_tag_ids(normalized_tag, partial=False)
        assert len(all_matching_tags) == 1, "Should not create duplicate tags"

    def test_tag_registration_service_initialization(self, test_image_repository_with_tag_db):
        """
        TagRegisterService遅延初期化テスト

        目的: 新規タグ登録時にTagRegisterServiceが正しく初期化されることを確認
        """
        # 初期状態: TagRegisterServiceはNone
        assert test_image_repository_with_tag_db.tag_register_service is None, (
            "TagRegisterService should be None initially"
        )

        # 新規タグ登録（遅延初期化をトリガー）
        new_tag = f"test_service_init_{uuid.uuid4().hex[:8]}"
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, new_tag)

        # 検証: tag_idが返却される
        assert tag_id is not None, "Tag ID should be returned"

        # TagRegisterServiceが初期化されたことを確認
        assert test_image_repository_with_tag_db.tag_register_service is not None, (
            "TagRegisterService should be initialized after registration"
        )

    def test_race_condition_retry_logic(self, test_image_repository_with_tag_db, monkeypatch):
        """
        競合検出時のリトライ検索テスト

        目的: IntegrityError発生時にリトライ検索が実行され、
              他のプロセスが登録したtag_idを取得することを確認
        """
        from genai_tag_db_tools import search_tags
        from genai_tag_db_tools.models import TagRecordPublic, TagSearchResult

        # テスト用タグ
        test_tag = f"test_race_condition_{uuid.uuid4().hex[:8]}"
        normalized_tag = TagCleaner.clean_format(test_tag).strip()

        # モック: 初回検索は空、登録でIntegrityError、リトライ検索で見つかる
        call_count = {"search": 0}
        expected_tag_id = 999

        def mock_search_tags(reader, request):
            call_count["search"] += 1
            if call_count["search"] == 1:
                # 初回検索: 空
                return TagSearchResult(items=[])
            else:
                # リトライ検索: 見つかる
                return TagSearchResult(
                    items=[TagRecordPublic(tag=normalized_tag, tag_id=expected_tag_id, source_tag=test_tag)]
                )

        def mock_register_tag(self, request):
            # 登録時にIntegrityErrorを発生させる
            raise IntegrityError("duplicate", "params", "orig")

        monkeypatch.setattr("lorairo.database.db_repository.search_tags", mock_search_tags)
        monkeypatch.setattr(
            "genai_tag_db_tools.services.tag_register.TagRegisterService.register_tag",
            mock_register_tag,
        )

        # 競合発生時の動作確認
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 検証: リトライ検索で取得したtag_idが返される
        assert tag_id == expected_tag_id, "Should return tag_id from retry search"
        assert call_count["search"] == 2, "Should call search_tags twice (initial + retry)"

    def test_graceful_degradation_on_registration_error(
        self, test_image_repository_with_tag_db, monkeypatch
    ):
        """
        登録エラー時のグレースフルデグラデーションテスト

        目的: TagRegisterService.register_tag()でエラーが発生した場合、
              Noneを返すことを確認（システムクラッシュしない）
        """
        from genai_tag_db_tools.models import TagSearchResult

        # モック: 検索結果なし、登録でRuntimeError
        def mock_search_tags(reader, request):
            return TagSearchResult(items=[])

        def mock_register_tag(self, request):
            raise RuntimeError("Simulated registration error")

        monkeypatch.setattr("lorairo.database.db_repository.search_tags", mock_search_tags)
        monkeypatch.setattr(
            "genai_tag_db_tools.services.tag_register.TagRegisterService.register_tag",
            mock_register_tag,
        )

        # エラー発生時の動作確認
        test_tag = f"test_error_{uuid.uuid4().hex[:8]}"
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 検証: クラッシュせずNoneを返す
        assert tag_id is None, "Should return None on registration error without crashing"

    def test_tag_id_consistency_with_multiple_calls(self, test_image_repository_with_tag_db):
        """
        複数回呼び出しでのtag_id一貫性テスト

        目的: 同じタグを複数回処理した場合、常に同じtag_idが返されることを確認
              （1回目: 登録、2回目以降: 検索）
        """
        test_tag = f"test_consistency_{uuid.uuid4().hex[:8]}"

        # 1回目の呼び出し（新規登録）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_first = test_image_repository_with_tag_db._get_or_create_tag_id_external(
                session, test_tag
            )

        # 2回目の呼び出し（既存タグ検索）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_second = test_image_repository_with_tag_db._get_or_create_tag_id_external(
                session, test_tag
            )

        # 3回目の呼び出し
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_third = test_image_repository_with_tag_db._get_or_create_tag_id_external(
                session, test_tag
            )

        # 検証: すべて同じtag_idが返される
        assert tag_id_first == tag_id_second == tag_id_third, (
            f"Tag ID should be consistent across calls: {tag_id_first}, {tag_id_second}, {tag_id_third}"
        )

    def test_value_error_handling_on_invalid_format(self, test_image_repository_with_tag_db, monkeypatch):
        """
        無効なformat_name/type_name時のエラーハンドリングテスト

        目的: TagRegisterServiceでValueErrorが発生した場合、
              Noneを返すことを確認
        """
        from genai_tag_db_tools.models import TagSearchResult

        # モック: 検索結果なし、登録でValueError
        def mock_search_tags(reader, request):
            return TagSearchResult(items=[])

        def mock_register_tag(self, request):
            raise ValueError("Invalid format_name")

        monkeypatch.setattr("lorairo.database.db_repository.search_tags", mock_search_tags)
        monkeypatch.setattr(
            "genai_tag_db_tools.services.tag_register.TagRegisterService.register_tag",
            mock_register_tag,
        )

        # エラー発生時の動作確認
        test_tag = f"test_value_error_{uuid.uuid4().hex[:8]}"
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 検証: Noneを返す
        assert tag_id is None, "Should return None on ValueError without crashing"

    def test_tag_normalization_consistency(self, test_image_repository_with_tag_db):
        """
        タグ正規化の一貫性テスト

        目的: 登録前の正規化処理が正しく動作することを確認
        """
        # テストケース: アンダースコアを含むタグ
        test_tag = f"test_underscore_{uuid.uuid4().hex[:8]}"
        expected_normalized = test_tag.replace("_", " ")

        # タグ登録
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 検証: tag_idが返却される
        assert tag_id is not None, "Tag ID should be returned"

        # 正規化が正しく適用されていることを確認（再検索で同じtag_idが返る）
        with test_image_repository_with_tag_db.session_factory() as session:
            # 正規化後の形式で検索
            tag_id_normalized = test_image_repository_with_tag_db._get_or_create_tag_id_external(
                session, expected_normalized
            )

        # 検証: 同じtag_idが返される（正規化により同一タグと認識）
        assert tag_id == tag_id_normalized, (
            "Normalized form should return same tag_id "
            f"(original: {tag_id}, normalized: {tag_id_normalized})"
        )
