# tests/unit/database/test_tag_database_duplicate_handling.py

from unittest.mock import MagicMock, Mock, patch

import pytest
from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from lorairo.database.db_repository import ImageRepository


class TestTagDatabaseDuplicateHandling:
    """タグデータベース重複処理テスト"""

    @pytest.fixture
    def mock_session_factory(self):
        """モックセッションファクトリ"""
        return Mock()

    @pytest.fixture
    def repository(self, mock_session_factory):
        """テスト用ImageRepository"""
        return ImageRepository(mock_session_factory)

    @pytest.fixture
    def mock_session(self):
        """モックセッション"""
        session = Mock()
        # session.execute() の戻り値をモック化
        session.execute.return_value = Mock()
        return session

    def test_get_or_create_tag_id_external_single_result(self, repository, mock_session):
        """正常ケース: タグが1つ見つかる場合"""
        # テストデータ
        tag_string = "test_tag"
        expected_tag_id = 12345

        # モック設定：1つの結果が返される
        mock_result = Mock()
        mock_result.__getitem__ = Mock(return_value=expected_tag_id)  # result[0]
        mock_session.execute.return_value.first.return_value = mock_result
        mock_session.execute.return_value.scalar.return_value = 1  # COUNT = 1

        # テスト実行
        result = repository._get_or_create_tag_id_external(mock_session, tag_string)

        # 結果検証
        assert result == expected_tag_id

        # SQLクエリが正しく呼び出されたか確認
        assert mock_session.execute.call_count == 2  # SELECT + COUNT

        # 最初のクエリ（SELECT）
        first_call_args = mock_session.execute.call_args_list[0]
        stmt = first_call_args[0][0]
        params = first_call_args[0][1]
        assert "SELECT tag_id FROM tag_db.TAGS WHERE tag = :tag_name" in str(stmt)
        assert params["tag_name"] == tag_string

    def test_get_or_create_tag_id_external_duplicate_results(self, repository, mock_session):
        """重複ケース: 同じタグが複数見つかる場合（警告ログ出力）"""
        # テストデータ
        tag_string = ":d"  # 実際に問題となったタグ
        expected_tag_id = 100
        duplicate_count = 3

        # モック設定：重複結果
        mock_result = Mock()
        mock_result.__getitem__ = Mock(return_value=expected_tag_id)
        mock_session.execute.return_value.first.return_value = mock_result
        mock_session.execute.return_value.scalar.return_value = duplicate_count

        # ログキャプチャ用のモック
        with patch("lorairo.database.db_repository.logger") as mock_logger:
            # テスト実行
            result = repository._get_or_create_tag_id_external(mock_session, tag_string)

            # 結果検証
            assert result == expected_tag_id

            # 警告ログが呼び出されたか確認
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Multiple entries" in warning_call
            assert f"({duplicate_count})" in warning_call
            assert tag_string in warning_call

    def test_get_or_create_tag_id_external_no_result(self, repository, mock_session):
        """見つからないケース: タグが存在しない場合"""
        # テストデータ
        tag_string = "nonexistent_tag"

        # モック設定：結果なし
        mock_session.execute.return_value.first.return_value = None

        # テスト実行
        result = repository._get_or_create_tag_id_external(mock_session, tag_string)

        # 結果検証
        assert result is None

        # COUNT クエリは実行されない
        assert mock_session.execute.call_count == 1

    def test_get_or_create_tag_id_external_database_error(self, repository, mock_session):
        """エラーケース: データベースエラーが発生した場合"""
        # テストデータ
        tag_string = "error_tag"

        # モック設定：SQLAlchemyErrorを発生
        mock_session.execute.side_effect = SQLAlchemyError("Database connection failed")

        # ログキャプチャ用のモック
        with patch("lorairo.database.db_repository.logger") as mock_logger:
            # テスト実行
            result = repository._get_or_create_tag_id_external(mock_session, tag_string)

            # 結果検証：Noneが返される（例外は再発生しない）
            assert result is None

            # エラーログが呼び出されたか確認
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args[0][0]
            assert "Error searching tag_id in tag_db" in error_call
            assert tag_string in error_call

    def test_get_or_create_tag_id_external_edge_cases(self, repository, mock_session):
        """エッジケース: 特殊文字を含むタグ"""
        special_tags = [
            ":d",  # 実際の問題タグ
            "tag:with:colons",
            "tag with spaces",
            "tag_with_underscore",
            "tag-with-dash",
            "日本語タグ",
            "",  # 空文字列
        ]

        for tag_string in special_tags:
            # モック設定：正常結果
            mock_result = Mock()
            mock_result.__getitem__ = Mock(return_value=999)
            mock_session.execute.return_value.first.return_value = mock_result
            mock_session.execute.return_value.scalar.return_value = 1

            # テスト実行
            result = repository._get_or_create_tag_id_external(mock_session, tag_string)

            # 結果検証
            assert result == 999

            # パラメータが正しく渡されているか確認
            params = mock_session.execute.call_args_list[-2][0][1]  # 最後から2番目（SELECT）
            assert params["tag_name"] == tag_string


class TestTagDatabaseIntegration:
    """タグデータベース統合テスト（実際のDB接続が必要な場合用）"""

    @pytest.mark.integration
    def test_tag_duplicate_handling_with_real_db(self):
        """
        実際のDB接続でのテスト
        注意: このテストは実際のtag_dbが必要
        """
        # TODO: 実際のDB接続が必要な統合テスト
        # CI/CD環境では実行されない可能性がある
        pytest.skip("Requires actual tag database connection")

    @pytest.mark.integration
    def test_dataset_registration_flow_with_duplicates(self):
        """
        データセット登録フロー全体での重複処理テスト
        """
        # TODO: 実際のデータセット登録フローでのテスト
        pytest.skip("Requires full dataset registration setup")
