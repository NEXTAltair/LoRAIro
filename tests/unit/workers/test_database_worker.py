# tests/unit/workers/test_database_worker.py
"""
DatabaseWorkerの改善されたユニットテスト
- 過度なMockを避け、実際のオブジェクトを使用
- 外部依存（ファイルシステム）のみMock化
- API名やインポートパスの問題を検出可能
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.gui.workers.database_worker import (
    DatabaseRegistrationResult,
    DatabaseRegistrationWorker,
    SearchWorker,
)
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager


class TestDatabaseRegistrationWorker:
    """DatabaseRegistrationWorker の改善されたユニットテスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_image_files(self, temp_dir):
        """モック画像ファイル（実際のファイルを作成）"""
        image_files = []
        for i in range(3):
            image_file = temp_dir / f"test_image_{i}.jpg"
            image_file.write_bytes(b"fake_image_data")
            image_files.append(image_file)
        return image_files

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationService（Mockしない）"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepository（Mockしない）"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManager（Mockしない）"""
        return ImageDatabaseManager(real_repository, real_config_service)

    @pytest.fixture
    def mock_fsm(self, mock_image_files):
        """ファイルシステムのみMock化（外部依存）"""
        mock = Mock(spec=FileSystemManager)
        mock.get_image_files.return_value = mock_image_files
        return mock

    def test_api_method_names_are_correct(self, temp_dir, real_db_manager, mock_fsm):
        """
        APIメソッド名が正しいことをテスト
        - このテストは実際のregister_image → register_original_imageエラーを検出できる
        """
        DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        # 実際のDatabaseManagerのメソッドが存在することを確認
        assert hasattr(real_db_manager, "detect_duplicate_image")
        assert hasattr(real_db_manager, "register_original_image")  # register_imageではない！
        assert hasattr(real_db_manager, "get_image_metadata")  # get_image_by_idではない！

        # メソッドが呼び出し可能であることを確認
        assert callable(real_db_manager.detect_duplicate_image)
        assert callable(real_db_manager.register_original_image)
        assert callable(real_db_manager.get_image_metadata)

    def test_import_paths_are_correct(self):
        """
        インポートパスが正しいことをテスト
        - このテストは実際の...database.db_coreインポートエラーを検出できる
        """
        # DatabaseWorkerがインポート可能であることを確認
        # 依存するモジュールがインポート可能であることを確認
        from lorairo.database.db_core import resolve_stored_path  # インポートエラーを検出
        from lorairo.database.db_repository import CaptionAnnotationData, TagAnnotationData
        from lorairo.gui.workers.database_worker import DatabaseRegistrationWorker

        # クラスが正しく定義されていることを確認
        assert DatabaseRegistrationWorker is not None
        assert resolve_stored_path is not None

    def test_worker_execution_with_real_objects(self, temp_dir, real_db_manager, mock_fsm):
        """
        実際のオブジェクトを使用したワーカー実行テスト
        - Mock以外の実際の連携をテスト
        """
        # 重複検出とDB登録をMock化（データベース書き込みを避けるため）
        with (
            patch.object(real_db_manager, "detect_duplicate_image") as mock_detect,
            patch.object(real_db_manager, "register_original_image") as mock_register,
        ):
            mock_detect.return_value = None  # 重複なし
            mock_register.return_value = (1, {"id": 1, "path": "test"})  # 成功

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 結果の検証
            assert isinstance(result, DatabaseRegistrationResult)
            assert result.registered_count == 3  # 3つのファイル
            assert result.skipped_count == 0
            assert result.error_count == 0

            # 実際のAPIが呼ばれたことを確認
            assert mock_detect.call_count == 3
            assert mock_register.call_count == 3

    def test_associated_files_processing_integration(self, temp_dir, real_db_manager, mock_fsm):
        """
        関連ファイル処理の統合テスト
        - タグファイル・キャプションファイル処理の実際の連携をテスト
        """
        # テスト用ファイル作成
        image_file = temp_dir / "test.jpg"
        tag_file = temp_dir / "test.txt"
        caption_file = temp_dir / "test.caption"

        image_file.write_bytes(b"fake_image")
        tag_file.write_text("tag1, tag2, tag3", encoding="utf-8")
        caption_file.write_text("test caption", encoding="utf-8")

        mock_fsm.get_image_files.return_value = [image_file]

        # DB操作をMock化
        with (
            patch.object(real_db_manager, "detect_duplicate_image") as mock_detect,
            patch.object(real_db_manager, "register_original_image") as mock_register,
            patch.object(real_db_manager, "save_tags") as mock_save_tags,
            patch.object(real_db_manager, "save_captions") as mock_save_captions,
        ):
            mock_detect.return_value = None
            mock_register.return_value = (1, {"id": 1})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            worker.execute()

            # 関連ファイル処理が呼ばれたことを確認
            mock_save_tags.assert_called_once()
            mock_save_captions.assert_called_once()

            # タグデータの構造確認
            tag_call_args = mock_save_tags.call_args
            assert tag_call_args[0][0] == 1  # image_id
            tag_data = tag_call_args[0][1]  # tags_data
            assert len(tag_data) == 3
            assert tag_data[0]["tag"] == "tag1"

    def test_cancellation_behavior(self, temp_dir, real_db_manager, mock_fsm):
        """キャンセル動作テスト"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        worker.cancel()

        with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
            worker.execute()

    def test_empty_directory_handling(self, temp_dir, real_db_manager):
        """空ディレクトリ処理テスト"""
        mock_fsm = Mock(spec=FileSystemManager)
        mock_fsm.get_image_files.return_value = []

        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        result = worker.execute()

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0


class TestSearchWorker:
    """SearchWorker の改善されたユニットテスト"""

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationServiceを使用"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepositoryを使用"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManagerを使用"""
        return ImageDatabaseManager(real_repository, real_config_service)

    @pytest.fixture
    def search_conditions(self):
        """テスト用検索条件"""
        return {
            "tags": ["test", "sample"],
            "caption": "test image",
            "resolution": "1024x768",
            "use_and": True,
            "date_range": (None, None),
            "include_untagged": False,
        }

    def test_search_worker_api_method_names(self, real_db_manager, search_conditions):
        """
        SearchWorkerのAPIメソッド名が正しいことをテスト
        - get_images_by_filterメソッドが存在することを確認
        """
        worker = SearchWorker(real_db_manager, search_conditions)

        # 実際のDB ManagerのAPIが存在することを確認
        assert hasattr(real_db_manager, "get_images_by_filter")
        assert callable(real_db_manager.get_images_by_filter)

        # Workerが正しく初期化されることを確認
        assert worker.db_manager is real_db_manager
        assert worker.filter_conditions == search_conditions

    def test_search_with_real_objects(self, real_db_manager, search_conditions):
        """
        実際のオブジェクトを使用した検索テスト
        - データベースアクセスのみMock化
        """
        # DB検索結果をMock化（実際のDBアクセスを避ける）
        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = (
                [
                    {"id": 1, "stored_image_path": "/test/image1.jpg"},
                    {"id": 2, "stored_image_path": "/test/image2.jpg"},
                ],
                2,
            )

            worker = SearchWorker(real_db_manager, search_conditions)
            result = worker.execute()

            # 結果の検証
            assert result.total_count == 2
            assert len(result.image_metadata) == 2
            assert result.filter_conditions == search_conditions
            assert result.search_time > 0

            # 実際のAPIに正しいパラメータが渡されたことを確認
            mock_search.assert_called_once_with(
                tags=["test", "sample"],
                caption="test image",
                resolution="1024x768",
                use_and=True,
                start_date=None,
                end_date=None,
                include_untagged=False,
            )

    def test_search_conditions_processing(self, real_db_manager):
        """
        検索条件の処理が正しいことをテスト
        - 日付範囲やinclude_untaggedの処理を確認
        """
        conditions = {
            "tags": [],
            "caption": "",
            "resolution": "",
            "use_and": True,
            "date_range": ("2023-01-01", "2023-12-31"),
            "include_untagged": True,
        }

        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = ([], 0)

            worker = SearchWorker(real_db_manager, conditions)
            worker.execute()

            # 日付範囲が正しく処理されることを確認
            mock_search.assert_called_once_with(
                tags=[],
                caption="",
                resolution="",
                use_and=True,
                start_date="2023-01-01",
                end_date="2023-12-31",
                include_untagged=True,
            )

    def test_cancellation_behavior(self, real_db_manager, search_conditions):
        """キャンセル動作テスト"""
        worker = SearchWorker(real_db_manager, search_conditions)
        worker.cancel()

        with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
            worker.execute()

    def test_empty_search_result_handling(self, real_db_manager, search_conditions):
        """空の検索結果処理テスト"""
        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = ([], 0)

            worker = SearchWorker(real_db_manager, search_conditions)
            result = worker.execute()

            assert result.total_count == 0
            assert len(result.image_metadata) == 0
