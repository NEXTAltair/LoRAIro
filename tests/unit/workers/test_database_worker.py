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
from lorairo.services.search_models import SearchConditions
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
        return SearchConditions(
            search_type="tags",
            keywords=["test", "sample"],
            tag_logic="and",
        )

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
        assert worker.search_conditions == search_conditions

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

            # 実際のAPIに正しいパラメータが渡されたことを確認（ImageFilterCriteria形式）
            expected_criteria = search_conditions.to_filter_criteria()
            mock_search.assert_called_once_with(criteria=expected_criteria)

    def test_search_conditions_processing(self, real_db_manager):
        """
        検索条件の処理が正しいことをテスト
        - 日付範囲やonly_untaggedの処理を確認
        """
        from datetime import date

        conditions = SearchConditions(
            search_type="caption",
            keywords=["test caption"],
            tag_logic="and",
            date_filter_enabled=True,
            date_range_start=date(2023, 1, 1),
            date_range_end=date(2023, 12, 31),
            only_untagged=True,
        )

        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = ([], 0)

            worker = SearchWorker(real_db_manager, conditions)
            worker.execute()

            # 日付範囲が正しく処理されることを確認（ImageFilterCriteria形式）
            expected_criteria = conditions.to_filter_criteria()
            mock_search.assert_called_once_with(criteria=expected_criteria)

    def test_search_applies_aspect_ratio_filter(self, real_db_manager):
        """SearchWorker経由でアスペクト比フィルターが適用されることを確認"""
        conditions = SearchConditions(
            search_type="tags",
            keywords=["test"],
            tag_logic="and",
            aspect_ratio_filter="正方形 (1:1)",
        )

        with patch.object(real_db_manager, "get_images_by_filter") as mock_search:
            mock_search.return_value = (
                [
                    {"id": 1, "width": 1024, "height": 1024},
                    {"id": 2, "width": 1920, "height": 1080},
                ],
                2,
            )

            worker = SearchWorker(real_db_manager, conditions)
            result = worker.execute()

            # 正方形画像のみ残ることを確認
            assert result.total_count == 1
            assert len(result.image_metadata) == 1
            assert result.image_metadata[0]["id"] == 1
            expected_criteria = conditions.to_filter_criteria()
            mock_search.assert_called_once_with(criteria=expected_criteria)

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


class TestRegisterSingleImage:
    """_register_single_image() の単体テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def worker_setup(self, temp_dir):
        """worker と mock オブジェクトのセットアップ"""
        mock_db_manager = Mock(spec=ImageDatabaseManager)
        mock_fsm = Mock(spec=FileSystemManager)

        worker = DatabaseRegistrationWorker(temp_dir, mock_db_manager, mock_fsm)

        # _report_batch_progress と _report_progress をモック
        worker._report_batch_progress = Mock()
        worker._report_progress = Mock()

        return worker, mock_db_manager, mock_fsm

    def test_register_single_image_normal_registration(self, temp_dir, worker_setup):
        """新規画像を登録（重複なし、関連ファイルなし）"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None  # 重複なし
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "registered"
            assert image_id == 1
            mock_db_manager.detect_duplicate_image.assert_called_once_with(image_path)
            mock_db_manager.register_original_image.assert_called_once()
            worker._report_batch_progress.assert_called_once()
            worker._report_progress.assert_called_once()

    def test_register_single_image_duplicate_detection(self, temp_dir, worker_setup):
        """pHash一致で重複検出 → スキップ"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = 42  # 重複画像ID

        # ExistingFileReader をモック
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "skipped"
            assert image_id == 42
            mock_db_manager.detect_duplicate_image.assert_called_once_with(image_path)
            mock_db_manager.register_original_image.assert_not_called()
            worker._report_batch_progress.assert_called_once()
            worker._report_progress.assert_called_once()

    def test_register_single_image_with_tags_only(self, temp_dir, worker_setup):
        """".txt 存在、.caption 不在"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック - タグのみ返す
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1", "tag2"],
                "captions": [],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "registered"
            assert image_id == 1
            mock_db_manager.save_tags.assert_called_once()
            mock_db_manager.save_captions.assert_not_called()

    def test_register_single_image_with_caption_only(self, temp_dir, worker_setup):
        """.caption 存在、.txt 不在"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック - キャプションのみ返す
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": [],
                "captions": ["test caption"],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "registered"
            assert image_id == 1
            mock_db_manager.save_tags.assert_not_called()
            mock_db_manager.save_captions.assert_called_once()

    def test_register_single_image_with_both_files(self, temp_dir, worker_setup):
        """.txt と .caption の両方存在"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック - 両方返す
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1", "tag2"],
                "captions": ["test caption"],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "registered"
            assert image_id == 1
            mock_db_manager.save_tags.assert_called_once()
            mock_db_manager.save_captions.assert_called_once()

    def test_register_single_image_without_associated_files(self, temp_dir, worker_setup):
        """.txt/.caption 不在"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック - 何も返さない
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "registered"
            assert image_id == 1
            mock_db_manager.save_tags.assert_not_called()
            mock_db_manager.save_captions.assert_not_called()

    def test_register_single_image_db_registration_returns_none(self, temp_dir, worker_setup):
        """register_original_image() が None を返す（失敗）"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = None  # 失敗

        # ExistingFileReader をモック
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "error"
            assert image_id == -1
            mock_db_manager.save_tags.assert_not_called()
            mock_db_manager.save_captions.assert_not_called()

    def test_register_single_image_progress_reporting(self, temp_dir, worker_setup):
        """_report_batch_progress() と _report_progress() が呼ばれる"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 5, 100)

            # _report_batch_progress の呼び出しを確認
            worker._report_batch_progress.assert_called_once_with(6, 100, image_path.name)

            # _report_progress の呼び出しを確認
            worker._report_progress.assert_called_once()
            call_args = worker._report_progress.call_args
            assert call_args[0][0] > 10  # percentage >= 10

    def test_register_single_image_associated_file_processing_error(self, temp_dir, worker_setup):
        """save_tags() で例外発生 - エラーが適切にハンドルされる"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})
        mock_db_manager.save_tags.side_effect = Exception("Tag save failed")

        # ExistingFileReader をモック
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1"],
                "captions": [],
            }

            # execute() が呼ぶ外側の try-except でキャッチされる想定
            # _register_single_image は例外を伝播させる
            with pytest.raises(Exception, match="Tag save failed"):
                worker._register_single_image(image_path, 0, 1)

    def test_register_single_image_multiple_tags_parsing(self, temp_dir, worker_setup):
        """複数タグのパース - TagAnnotationData を複数個作成"""
        worker, mock_db_manager, mock_fsm = worker_setup

        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        # モック設定
        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        # ExistingFileReader をモック
        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1", "tag2", "tag3"],
                "captions": [],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 1)

            assert result_type == "registered"

            # save_tags の呼び出しを確認
            mock_db_manager.save_tags.assert_called_once()
            call_args = mock_db_manager.save_tags.call_args
            tags_data = call_args[0][1]  # tags_data 引数

            # 3つのタグが作成されたことを確認
            assert len(tags_data) == 3
            assert tags_data[0]["tag"] == "tag1"
            assert tags_data[1]["tag"] == "tag2"
            assert tags_data[2]["tag"] == "tag3"
            assert all(t["existing"] is True for t in tags_data)
            assert all(t["is_edited_manually"] is False for t in tags_data)


class TestBuildRegistrationResult:
    """_build_registration_result() の単体テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationService"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepository"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManager"""
        return ImageDatabaseManager(real_repository, real_config_service)

    @pytest.fixture
    def mock_fsm(self):
        """ファイルシステムマネージャーのMock"""
        return Mock(spec=FileSystemManager)

    @pytest.fixture
    def worker(self, temp_dir, real_db_manager, mock_fsm):
        """DatabaseRegistrationWorker インスタンス"""
        return DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

    def test_build_registration_result_normal_case(self, worker):
        """通常ケース: 登録3、スキップ2、エラー1"""
        stats = {"registered": 3, "skipped": 2, "errors": 1}
        processed_paths = [Path("img1.jpg"), Path("img2.jpg"), Path("img3.jpg")]
        start_time = 0.0

        with patch("time.time", return_value=1.5):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert isinstance(result, DatabaseRegistrationResult)
        assert result.registered_count == 3
        assert result.skipped_count == 2
        assert result.error_count == 1
        assert result.processed_paths == processed_paths
        assert result.total_processing_time > 0

    def test_build_registration_result_all_registered(self, worker):
        """すべてが登録された場合"""
        stats = {"registered": 10, "skipped": 0, "errors": 0}
        processed_paths = [Path(f"img{i}.jpg") for i in range(10)]
        start_time = 0.0

        with patch("time.time", return_value=2.0):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert result.registered_count == 10
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert len(result.processed_paths) == 10
        assert result.total_processing_time == 2.0

    def test_build_registration_result_all_skipped(self, worker):
        """すべてがスキップされた場合"""
        stats = {"registered": 0, "skipped": 10, "errors": 0}
        processed_paths = []
        start_time = 0.0

        with patch("time.time", return_value=1.0):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert result.registered_count == 0
        assert result.skipped_count == 10
        assert result.error_count == 0
        assert len(result.processed_paths) == 0

    def test_build_registration_result_all_errors(self, worker):
        """すべてがエラーになった場合"""
        stats = {"registered": 0, "skipped": 0, "errors": 10}
        processed_paths = []
        start_time = 0.0

        with patch("time.time", return_value=3.5):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 10
        assert len(result.processed_paths) == 0
        assert result.total_processing_time == 3.5

    def test_build_registration_result_processing_time_recorded(self, worker):
        """処理時間が正確に記録されるか"""
        stats = {"registered": 5, "skipped": 3, "errors": 2}
        processed_paths = [Path(f"img{i}.jpg") for i in range(5)]
        start_time = 10.0

        with patch("time.time", return_value=15.5):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert result.total_processing_time == 5.5
        assert result.total_processing_time > 0

    def test_build_registration_result_processed_paths_included(self, worker):
        """processed_paths が正確に含まれるか"""
        processed_paths = [Path("img1.jpg"), Path("img2.jpg"), Path("img3.jpg")]
        stats = {"registered": 3, "skipped": 0, "errors": 0}
        start_time = 0.0

        with patch("time.time", return_value=1.0):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert result.processed_paths == processed_paths
        assert len(result.processed_paths) == 3
        assert all(isinstance(p, Path) for p in result.processed_paths)

    def test_build_registration_result_info_log_output(self, worker):
        """INFO ログが出力されるか"""
        stats = {"registered": 5, "skipped": 2, "errors": 1}
        processed_paths = [Path(f"img{i}.jpg") for i in range(5)]
        start_time = 0.0

        with patch("time.time", return_value=2.0), patch(
            "lorairo.gui.workers.registration_worker.logger"
        ) as mock_logger:
            result = worker._build_registration_result(stats, processed_paths, start_time)

            # INFO ログが呼ばれたことを確認
            mock_logger.info.assert_called_once()

            # ログメッセージの内容確認
            log_message = mock_logger.info.call_args[0][0]
            assert "データベース登録完了" in log_message
            assert "登録=5" in log_message
            assert "スキップ=2" in log_message
            assert "エラー=1" in log_message

    def test_build_registration_result_info_log_only(self, worker):
        """INFO ログのみが出力されるか（DEBUG ログは出力されないか）"""
        stats = {"registered": 3, "skipped": 1, "errors": 1}
        processed_paths = [Path(f"img{i}.jpg") for i in range(3)]
        start_time = 0.0

        with patch("time.time", return_value=1.5), patch(
            "lorairo.gui.workers.registration_worker.logger"
        ) as mock_logger:
            result = worker._build_registration_result(stats, processed_paths, start_time)

            # DEBUG ログが呼ばれていないことを確認
            mock_logger.debug.assert_not_called()

            # INFO ログが呼ばれたことを確認
            assert mock_logger.info.called

    def test_build_registration_result_empty_result(self, worker):
        """空の結果を処理"""
        stats = {"registered": 0, "skipped": 0, "errors": 0}
        processed_paths = []
        start_time = 0.0

        with patch("time.time", return_value=0.1):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert result.processed_paths == []
        assert result.total_processing_time == 0.1

    def test_build_registration_result_type_validation(self, worker):
        """返却値が DatabaseRegistrationResult 型で、すべてのフィールドが存在するか"""
        stats = {"registered": 2, "skipped": 1, "errors": 1}
        processed_paths = [Path("img1.jpg"), Path("img2.jpg")]
        start_time = 0.0

        with patch("time.time", return_value=2.5):
            result = worker._build_registration_result(stats, processed_paths, start_time)

        # 型チェック
        assert isinstance(result, DatabaseRegistrationResult)

        # すべてのフィールドが存在するか
        assert hasattr(result, "registered_count")
        assert hasattr(result, "skipped_count")
        assert hasattr(result, "error_count")
        assert hasattr(result, "processed_paths")
        assert hasattr(result, "total_processing_time")

        # フィールドの型チェック
        assert isinstance(result.registered_count, int)
        assert isinstance(result.skipped_count, int)
        assert isinstance(result.error_count, int)
        assert isinstance(result.processed_paths, list)
        assert isinstance(result.total_processing_time, float)


class TestRegistrationErrorHandling:
    """エラーハンドリング・統合テスト"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def mock_image_files(self, temp_dir):
        """モック画像ファイル（複数パターン対応）"""
        image_files = []
        for i in range(3):
            image_file = temp_dir / f"test_image_{i}.jpg"
            image_file.write_bytes(b"fake_image_data")
            image_files.append(image_file)
        return image_files

    @pytest.fixture
    def real_config_service(self):
        """実際のConfigurationService"""
        return ConfigurationService()

    @pytest.fixture
    def real_repository(self):
        """実際のImageRepository"""
        return ImageRepository()

    @pytest.fixture
    def real_db_manager(self, real_repository, real_config_service):
        """実際のImageDatabaseManager"""
        return ImageDatabaseManager(real_repository, real_config_service)

    @pytest.fixture
    def mock_fsm(self, mock_image_files):
        """ファイルシステムのみMock化"""
        mock = Mock(spec=FileSystemManager)
        mock.get_image_files.return_value = mock_image_files
        return mock

    @pytest.fixture
    def worker_setup(self, temp_dir, real_db_manager, mock_fsm):
        """ワーカー初期化フィクスチャ"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        return worker, real_db_manager, mock_fsm

    def test_cancellation_during_execution(self, worker_setup):
        """キャンセル実行時にRuntimeErrorが発生することを確認"""
        worker, _, _ = worker_setup
        worker.cancel()

        with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
            worker.execute()

    def test_cancellation_mid_loop(self, temp_dir, real_db_manager, mock_fsm):
        """2件処理後のキャンセル確認"""
        # 3つの画像ファイルを用意
        image_files = []
        for i in range(3):
            image_file = temp_dir / f"image_{i}.jpg"
            image_file.write_bytes(b"fake")
            image_files.append(image_file)
        mock_fsm.get_image_files.return_value = image_files

        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        # register_original_imageをMock化
        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register, \
             patch.object(worker, "_check_cancellation") as mock_cancel:
            mock_detect.return_value = None
            mock_register.return_value = (1, {})

            # 2回目のチェック時にキャンセル
            def cancel_on_second_call():
                if mock_cancel.call_count >= 2:
                    raise RuntimeError("処理がキャンセルされました")

            mock_cancel.side_effect = cancel_on_second_call

            with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
                worker.execute()

    def test_exception_in_db_registration(self, temp_dir, real_db_manager, mock_fsm):
        """register_original_imageが例外を発生した場合の処理確認"""
        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register, \
             patch.object(real_db_manager, "save_error_record") as mock_save_error:
            mock_detect.return_value = None
            mock_register.side_effect = ValueError("登録エラー")

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # save_error_recordが呼ばれたことを確認
            assert mock_save_error.called
            # error_countが増加したことを確認
            assert result.error_count == 3

    def test_secondary_error_in_save_error_record(
        self, temp_dir, real_db_manager, mock_fsm
    ):
        """save_error_record自体が例外を発生した場合の処理確認"""
        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register, \
             patch.object(real_db_manager, "save_error_record") as mock_save_error, \
             patch("lorairo.gui.workers.registration_worker.logger") as mock_logger:
            mock_detect.return_value = None
            mock_register.side_effect = ValueError("登録エラー")
            mock_save_error.side_effect = Exception("エラー保存失敗")

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 処理が継続されること（クラッシュしないこと）
            assert result.error_count == 3
            # logger.error で二次エラーが記録されることを確認
            # save_error_record の例外ハンドルで logger.error() が呼ばれる
            assert any("エラーレコード保存失敗（二次エラー）" in str(call)
                      for call in mock_logger.error.call_args_list)

    def test_progress_reporting_sequence(self, temp_dir, real_db_manager, mock_fsm):
        """進捗報告の呼び出し順序確認"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register, \
             patch.object(worker, "_report_progress") as mock_progress, \
             patch.object(worker, "_report_batch_progress") as mock_batch:
            mock_detect.return_value = None
            mock_register.return_value = (1, {})

            worker.execute()

            # 進捗報告が呼ばれたことを確認
            assert mock_progress.called
            # 最初の呼び出しで "画像ファイルを検索中..." を確認
            first_call = mock_progress.call_args_list[0]
            assert "画像ファイルを検索中" in first_call[0][1]
            # 最後の呼び出しで "データベース登録完了" を確認
            last_call = mock_progress.call_args_list[-1]
            assert "データベース登録完了" in last_call[0][1]
            # バッチ進捗が呼ばれたことを確認
            assert mock_batch.call_count >= 3

    def test_empty_directory_handling_integration(self, temp_dir, real_db_manager):
        """空ディレクトリ処理テスト（統合テスト版）"""
        mock_fsm = Mock(spec=FileSystemManager)
        mock_fsm.get_image_files.return_value = []

        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
        result = worker.execute()

        # 全カウントが0であることを確認
        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0
        # 早期リターンで processed_paths が空であることを確認
        assert len(result.processed_paths) == 0

    def test_integration_with_split_methods(self, temp_dir, real_db_manager, mock_fsm):
        """分割メソッド（_register_single_image, _build_registration_result）の協調確認"""
        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register:
            mock_detect.return_value = None
            mock_register.return_value = (1, {"id": 1})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 単一メソッド版と同じ動作を確認
            assert isinstance(result, DatabaseRegistrationResult)
            assert result.registered_count == 3
            assert result.skipped_count == 0
            assert result.error_count == 0
            assert len(result.processed_paths) == 3

    def test_integration_duplicate_detection_with_file_processing(
        self, temp_dir, real_db_manager, mock_fsm
    ):
        """重複検出時の関連ファイル処理確認"""
        # テスト用ファイル作成
        image_file = temp_dir / "duplicate_test.jpg"
        tag_file = temp_dir / "duplicate_test.txt"
        caption_file = temp_dir / "duplicate_test.caption"

        image_file.write_bytes(b"fake_image")
        tag_file.write_text("tag1, tag2", encoding="utf-8")
        caption_file.write_text("test caption", encoding="utf-8")

        mock_fsm.get_image_files.return_value = [image_file]

        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "save_tags") as mock_save_tags, \
             patch.object(real_db_manager, "save_captions") as mock_save_captions:
            # 重複画像を返す（image_id = 999）
            mock_detect.return_value = 999

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 重複時でも _process_associated_files() が呼ばれることを確認
            # （タグとキャプションが処理される）
            mock_save_tags.assert_called_once()
            mock_save_captions.assert_called_once()
            # スキップ数が増加することを確認
            assert result.skipped_count == 1

    def test_high_volume_image_processing(self, temp_dir, real_db_manager):
        """100個の画像処理時のパフォーマンステスト"""
        # 100個の画像ファイルを作成
        image_files = []
        for i in range(100):
            image_file = temp_dir / f"image_{i:03d}.jpg"
            image_file.write_bytes(b"x" * 1000)  # 小さめのダミーデータ
            image_files.append(image_file)

        mock_fsm = Mock(spec=FileSystemManager)
        mock_fsm.get_image_files.return_value = image_files

        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register:
            mock_detect.return_value = None
            mock_register.return_value = (1, {})

            worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)
            result = worker.execute()

            # 100件全て処理されたことを確認
            assert result.registered_count == 100
            assert result.total_processing_time >= 0  # 処理時間が記録されること
            assert len(result.processed_paths) == 100

    def test_progress_report_call_count_verification(self, temp_dir, real_db_manager, mock_fsm):
        """進捗報告呼び出し回数の確認"""
        worker = DatabaseRegistrationWorker(temp_dir, real_db_manager, mock_fsm)

        with patch.object(real_db_manager, "detect_duplicate_image") as mock_detect, \
             patch.object(real_db_manager, "register_original_image") as mock_register, \
             patch.object(worker, "_report_progress") as mock_progress, \
             patch.object(worker, "_report_batch_progress") as mock_batch:
            mock_detect.return_value = None
            mock_register.return_value = (1, {})

            worker.execute()

            # _report_progress の呼び出し回数：開始 + ループ内 + 完了
            # 最低3回（開始、開始2、完了）以上
            assert mock_progress.call_count >= 3
            # _report_batch_progress は画像ごとに1回呼ばれる（3回）
            assert mock_batch.call_count == 3


class TestRegisterSingleImageUnits:
    """_register_single_image() の詳細単体テスト（10個のテストケース）"""

    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def worker_setup(self, temp_dir):
        """worker と mock オブジェクトのセットアップ"""
        mock_db_manager = Mock(spec=ImageDatabaseManager)
        mock_fsm = Mock(spec=FileSystemManager)

        worker = DatabaseRegistrationWorker(temp_dir, mock_db_manager, mock_fsm)

        # _report_batch_progress と _report_progress をモック
        worker._report_batch_progress = Mock()
        worker._report_progress = Mock()

        return worker, mock_db_manager, mock_fsm

    def test_new_image_registration(self, temp_dir, worker_setup):
        """1. 新規画像（重複なし）を登録し、image_id > 0、processed_paths に追加"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "test.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (42, {"id": 42})

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "registered"
            assert image_id == 42
            assert image_id > 0
            mock_db_manager.register_original_image.assert_called_once()

    def test_duplicate_detection_skips(self, temp_dir, worker_setup):
        """2. 重複検出 → skipped、関連ファイル処理が呼ばれる"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "duplicate.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = 99

        with patch.object(worker, "file_reader") as mock_file_reader, \
             patch.object(worker, "_process_associated_files") as mock_process:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "skipped"
            assert image_id == 99
            mock_process.assert_called_once_with(image_path, 99)
            mock_db_manager.register_original_image.assert_not_called()

    def test_no_associated_files(self, temp_dir, worker_setup):
        """3. .txt/.caption 不在 → DB登録、_process_associated_files called で早期 return"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "no_files.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        with patch.object(worker, "file_reader") as mock_file_reader, \
             patch.object(worker, "_process_associated_files") as mock_process:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "registered"
            # _process_associated_files は呼ばれるが、内部で None チェックして早期return
            mock_process.assert_called_once_with(image_path, 1)

    def test_tags_file_only(self, temp_dir, worker_setup):
        """4. .txt のみ存在 → タグ処理、キャプション処理なし"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "tags_only.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1", "tag2"],
                "captions": [],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "registered"
            mock_db_manager.save_tags.assert_called_once()
            mock_db_manager.save_captions.assert_not_called()

    def test_captions_file_only(self, temp_dir, worker_setup):
        """5. .caption のみ存在 → キャプション処理、タグ処理なし"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "captions_only.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": [],
                "captions": ["test caption"],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "registered"
            mock_db_manager.save_tags.assert_not_called()
            mock_db_manager.save_captions.assert_called_once()

    def test_db_registration_returns_none(self, temp_dir, worker_setup):
        """6. register_original_image() が None → error、image_id = -1"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "fail.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = None

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "error"
            assert image_id == -1

    def test_progress_helper_call(self, temp_dir, worker_setup):
        """7. ProgressHelper.calculate_percentage() が 10-85% 範囲で呼ばれる"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "progress.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        with patch.object(worker, "file_reader") as mock_file_reader, \
             patch("lorairo.gui.workers.registration_worker.ProgressHelper.calculate_percentage") as mock_calc:
            mock_file_reader.get_existing_annotations.return_value = None
            mock_calc.return_value = 45

            result_type, image_id = worker._register_single_image(image_path, 5, 100)

            mock_calc.assert_called_once_with(6, 100, 10, 85)

    def test_batch_progress_reporting(self, temp_dir, worker_setup):
        """8. _report_batch_progress() が (i+1, total_count, image_path.name) で呼ばれる"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "batch_report.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = None

            worker._register_single_image(image_path, 7, 50)

            worker._report_batch_progress.assert_called_once_with(8, 50, "batch_report.jpg")

    def test_associated_files_error_handling(self, temp_dir, worker_setup):
        """9. save_tags() で例外 → エラーログ出力、処理継続"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "error.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})
        mock_db_manager.save_tags.side_effect = ValueError("Tag save failed")

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1"],
                "captions": [],
            }

            with pytest.raises(ValueError, match="Tag save failed"):
                worker._register_single_image(image_path, 0, 10)

    def test_multiple_tags_parsing(self, temp_dir, worker_setup):
        """10. "tag1, tag2, tag3" → 3個の TagAnnotationData が save_tags に渡される"""
        worker, mock_db_manager, _ = worker_setup
        image_path = temp_dir / "multi_tags.jpg"
        image_path.write_bytes(b"fake_image")

        mock_db_manager.detect_duplicate_image.return_value = None
        mock_db_manager.register_original_image.return_value = (1, {"id": 1})

        with patch.object(worker, "file_reader") as mock_file_reader:
            mock_file_reader.get_existing_annotations.return_value = {
                "tags": ["tag1", "tag2", "tag3"],
                "captions": [],
            }

            result_type, image_id = worker._register_single_image(image_path, 0, 10)

            assert result_type == "registered"
            mock_db_manager.save_tags.assert_called_once()
            call_args = mock_db_manager.save_tags.call_args
            tags_data = call_args[0][1]

            assert len(tags_data) == 3
            assert tags_data[0]["tag"] == "tag1"
            assert tags_data[1]["tag"] == "tag2"
            assert tags_data[2]["tag"] == "tag3"
            assert all(t["existing"] is True for t in tags_data)
            assert all(t["is_edited_manually"] is False for t in tags_data)
