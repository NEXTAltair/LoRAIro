"""ImageRepository のタグ登録機能の単体テスト (Phase 2)"""

from unittest.mock import MagicMock, Mock, patch

import pytest
from genai_tag_db_tools.models import TagRecordPublic, TagRegisterResult, TagSearchResult
from sqlalchemy.exc import IntegrityError

from lorairo.database.db_repository import ImageRepository


@pytest.mark.unit
class TestImageRepositoryTagRegistration:
    """ImageRepository._get_or_create_tag_id_external() のタグ登録機能テスト"""

    @pytest.fixture
    def mock_session(self):
        """モックセッション"""
        return Mock()

    @pytest.fixture
    def repository(self):
        """ImageRepository インスタンス（MergedTagReader モック付き）"""
        with patch("lorairo.database.db_repository.get_default_reader") as mock_reader_factory:
            mock_reader = Mock()
            mock_reader_factory.return_value = mock_reader
            repo = ImageRepository()
            return repo

    def test_tag_registration_success(self, repository, mock_session):
        """新規タグ登録成功"""
        # 検索結果なし（新規タグ）
        search_result = TagSearchResult(items=[])

        # 登録成功
        register_result = TagRegisterResult(tag_id=456, created=True)

        with patch("lorairo.database.db_repository.search_tags", return_value=search_result):
            with patch.object(
                repository, "_initialize_tag_register_service"
            ) as mock_init_service:
                mock_service = Mock()
                mock_service.register_tag.return_value = register_result
                mock_init_service.return_value = mock_service
                repository.tag_register_service = None  # 強制的に遅延初期化をトリガー

                tag_id = repository._get_or_create_tag_id_external(mock_session, "new_tag")

                assert tag_id == 456
                mock_service.register_tag.assert_called_once()
                call_args = mock_service.register_tag.call_args[0][0]
                # TagCleaner.clean_format() によりアンダースコアはスペースに正規化される
                assert call_args.tag == "new tag"
                assert call_args.source_tag == "new_tag"
                assert call_args.format_name == "Lorairo"
                assert call_args.type_name == "unknown"

    def test_tag_registration_race_condition_retry_success(self, repository, mock_session):
        """競合検出後のリトライ検索成功"""
        # 検索結果なし（新規タグ）
        search_result_empty = TagSearchResult(items=[])
        # リトライ検索結果（他プロセスが登録済み）
        search_result_retry = TagSearchResult(
            items=[TagRecordPublic(tag="race_tag", tag_id=789, source_tag="race_tag")]
        )

        with patch("lorairo.database.db_repository.search_tags") as mock_search:
            mock_search.side_effect = [
                search_result_empty,  # 初回検索: なし
                search_result_retry,  # リトライ検索: 見つかる
            ]
            with patch.object(
                repository, "_initialize_tag_register_service"
            ) as mock_init_service:
                mock_service = Mock()
                mock_service.register_tag.side_effect = IntegrityError(
                    "duplicate", "params", "orig"
                )
                mock_init_service.return_value = mock_service
                repository.tag_register_service = None

                tag_id = repository._get_or_create_tag_id_external(mock_session, "race_tag")

                assert tag_id == 789
                assert mock_search.call_count == 2  # 初回 + リトライ

    def test_tag_registration_value_error_invalid_format(self, repository, mock_session):
        """無効な format_name/type_name でエラー"""
        search_result = TagSearchResult(items=[])

        with patch("lorairo.database.db_repository.search_tags", return_value=search_result):
            with patch.object(
                repository, "_initialize_tag_register_service"
            ) as mock_init_service:
                mock_service = Mock()
                mock_service.register_tag.side_effect = ValueError("Invalid format_name")
                mock_init_service.return_value = mock_service
                repository.tag_register_service = None

                tag_id = repository._get_or_create_tag_id_external(
                    mock_session, "invalid_format_tag"
                )

                assert tag_id is None

    def test_tag_registration_service_initialization_failure(self, repository, mock_session):
        """TagRegisterService 初期化失敗"""
        search_result = TagSearchResult(items=[])

        with patch("lorairo.database.db_repository.search_tags", return_value=search_result):
            with patch.object(
                repository, "_initialize_tag_register_service", return_value=None
            ):
                repository.tag_register_service = None

                tag_id = repository._get_or_create_tag_id_external(mock_session, "tag")

                assert tag_id is None

    def test_tag_registration_unexpected_error_graceful_degradation(
        self, repository, mock_session
    ):
        """予期しないエラー時のグレースフルデグラデーション"""
        search_result = TagSearchResult(items=[])

        with patch("lorairo.database.db_repository.search_tags", return_value=search_result):
            with patch.object(
                repository, "_initialize_tag_register_service"
            ) as mock_init_service:
                mock_service = Mock()
                mock_service.register_tag.side_effect = RuntimeError("Unexpected error")
                mock_init_service.return_value = mock_service
                repository.tag_register_service = None

                tag_id = repository._get_or_create_tag_id_external(mock_session, "error_tag")

                assert tag_id is None  # グレースフルデグラデーション

    def test_existing_tag_found_no_registration(self, repository, mock_session):
        """既存タグが見つかる場合は登録しない"""
        # 検索結果あり（既存タグ）
        search_result = TagSearchResult(
            items=[TagRecordPublic(tag="existing_tag", tag_id=123, source_tag="existing_tag")]
        )

        with patch("lorairo.database.db_repository.search_tags", return_value=search_result):
            with patch.object(
                repository, "_initialize_tag_register_service"
            ) as mock_init_service:
                repository.tag_register_service = None

                tag_id = repository._get_or_create_tag_id_external(mock_session, "existing_tag")

                assert tag_id == 123
                # TagRegisterService は初期化されない（検索で見つかったため）
                mock_init_service.assert_not_called()
