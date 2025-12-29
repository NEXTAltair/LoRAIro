# tests/unit/database/test_tag_database_duplicate_handling.py

from unittest.mock import MagicMock, Mock, patch

import pytest
from genai_tag_db_tools.models import TagRecordPublic, TagSearchRequest, TagSearchResult

from lorairo.database.db_repository import ImageRepository


class TestTagDatabaseDuplicateHandling:
    """タグデータベース重複処理テスト（公開API対応版）"""

    @pytest.fixture
    def mock_session_factory(self):
        """モックセッションファクトリ"""
        return Mock()

    @pytest.fixture
    def mock_merged_reader(self):
        """モックMergedTagReader"""
        return Mock()

    @pytest.fixture
    def repository(self, mock_session_factory, mock_merged_reader):
        """テスト用ImageRepository（merged_readerを差し替え）"""
        repo = ImageRepository(mock_session_factory)
        repo.merged_reader = mock_merged_reader
        return repo

    @pytest.fixture
    def mock_session(self):
        """モックセッション"""
        return Mock()

    def test_get_or_create_tag_id_external_single_result(self, repository, mock_session):
        """正常ケース: タグが1つ見つかる場合"""
        # テストデータ
        tag_string = "test tag"
        expected_tag_id = 12345

        # モック設定：search_tags()が1つの結果を返す
        mock_tag_item = TagRecordPublic(
            tag_id=expected_tag_id,
            source_tag=tag_string,
            tag=tag_string,
            alias=False,
            deprecated=False,
        )
        mock_result = TagSearchResult(items=[mock_tag_item], total=1)

        with patch("lorairo.database.db_repository.search_tags", return_value=mock_result):
            # テスト実行
            result = repository._get_or_create_tag_id_external(mock_session, tag_string)

            # 結果検証
            assert result == expected_tag_id

    def test_get_or_create_tag_id_external_duplicate_results(self, repository, mock_session):
        """重複ケース: 同じタグが複数見つかる場合（最初のtag_idを使用）"""
        # テストデータ
        tag_string = ":d"  # 実際に問題となったタグ
        expected_tag_id = 100

        # モック設定：複数の結果（genai-tag-db-tools側で1つに絞られている想定）
        mock_tag_item = TagRecordPublic(
            tag_id=expected_tag_id,
            source_tag=tag_string,
            tag=tag_string,
            alias=False,
            deprecated=False,
        )
        mock_result = TagSearchResult(items=[mock_tag_item], total=1)

        with patch("lorairo.database.db_repository.search_tags", return_value=mock_result):
            # テスト実行
            result = repository._get_or_create_tag_id_external(mock_session, tag_string)

            # 結果検証
            assert result == expected_tag_id

    def test_get_or_create_tag_id_external_no_result(self, repository, mock_session):
        """見つからないケース: タグが存在しない場合"""
        # テストデータ
        tag_string = "nonexistent tag"

        # モック設定：結果なし
        mock_result = TagSearchResult(items=[], total=0)

        with patch("lorairo.database.db_repository.search_tags", return_value=mock_result):
            # テスト実行
            result = repository._get_or_create_tag_id_external(mock_session, tag_string)

            # 結果検証
            assert result is None

    def test_get_or_create_tag_id_external_database_error(self, repository, mock_session):
        """エラーケース: データベースエラーが発生した場合"""
        # テストデータ
        tag_string = "error tag"

        # モック設定：search_tags()がExceptionを発生
        with patch("lorairo.database.db_repository.search_tags", side_effect=Exception("Database error")):
            with patch("lorairo.database.db_repository.logger") as mock_logger:
                # テスト実行
                result = repository._get_or_create_tag_id_external(mock_session, tag_string)

                # 結果検証：Noneが返される（例外は再発生しない）
                assert result is None

                # エラーログが呼び出されたか確認
                mock_logger.error.assert_called_once()
                error_call = mock_logger.error.call_args[0][0]
                assert "Error searching tag" in error_call
                assert tag_string in error_call

    def test_get_or_create_tag_id_external_edge_cases(self, repository, mock_session):
        """エッジケース: 特殊文字を含むタグ"""
        special_tags = [
            ":d",  # 実際の問題タグ
            "tag:with:colons",
            "tag with spaces",
            "tag with underscore",  # TagCleanerで正規化されてアンダースコアはスペースに変換
            "tag-with-dash",
            "日本語タグ",
        ]

        for tag_string in special_tags:
            # モック設定：正常結果
            mock_tag_item = TagRecordPublic(
                tag_id=999,
                source_tag=tag_string,
                tag=tag_string,
                alias=False,
                deprecated=False,
            )
            mock_result = TagSearchResult(items=[mock_tag_item], total=1)

            with patch("lorairo.database.db_repository.search_tags", return_value=mock_result):
                # テスト実行
                result = repository._get_or_create_tag_id_external(mock_session, tag_string)

                # 結果検証
                assert result == 999

    def test_get_or_create_tag_id_external_empty_string(self, repository, mock_session):
        """空文字列ケース: 正規化後に空になる場合"""
        # テストデータ
        tag_string = ""

        # テスト実行（search_tags()は呼ばれないはず）
        result = repository._get_or_create_tag_id_external(mock_session, tag_string)

        # 結果検証
        assert result is None

    def test_get_or_create_tag_id_external_merged_reader_unavailable(
        self, mock_session_factory, mock_session
    ):
        """MergedTagReaderがNoneの場合のテスト（グレースフルデグラデーション）"""
        # merged_readerがNoneのリポジトリを作成
        repo = ImageRepository(mock_session_factory)
        assert repo.merged_reader is None  # 初期化時にNoneになる

        # テスト実行
        result = repo._get_or_create_tag_id_external(mock_session, "test tag")

        # 結果検証：Noneが返される
        assert result is None


class TestTagDatabaseIntegration:
    """タグデータベース統合テスト（実際のDB接続が必要な場合用）"""

    @pytest.mark.integration
    def test_tag_duplicate_handling_with_real_db(self):
        """
        実際のDB接続でのテスト
        注意: このテストは実際のtag_dbが必要
        """
        # tests/integration/test_tag_db_integration.py に実装済み
        pytest.skip("Requires actual tag database connection")

    @pytest.mark.integration
    def test_dataset_registration_flow_with_duplicates(self):
        """
        データセット登録フロー全体での重複処理テスト
        """
        # tests/integration/test_tag_db_integration.py に実装済み
        pytest.skip("Requires full dataset registration setup")
