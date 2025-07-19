# tests/unit/workers/test_database_worker.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.lorairo.workers.database_worker import DatabaseRegistrationWorker, SearchWorker


class TestDatabaseRegistrationWorker:
    """DatabaseRegistrationWorker のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock = Mock()
        mock.detect_duplicate_image.return_value = False
        mock.register_image.return_value = True
        return mock

    @pytest.fixture
    def mock_fsm(self):
        """モックファイルシステムマネージャー"""
        mock = Mock()
        mock.get_image_files.return_value = [
            Path("/test/image1.jpg"),
            Path("/test/image2.jpg"),
            Path("/test/image3.jpg"),
        ]
        return mock

    @pytest.fixture
    def worker(self, mock_db_manager, mock_fsm):
        """テスト用ワーカー"""
        return DatabaseRegistrationWorker(
            directory=Path("/test/directory"),
            db_manager=mock_db_manager,
            fsm=mock_fsm,
        )

    def test_initialization(self, worker):
        """初期化テスト"""
        assert worker.directory == Path("/test/directory")
        assert worker.db_manager is not None
        assert worker.fsm is not None
        assert worker.status.value == "idle"

    def test_successful_registration(self, worker, mock_db_manager, mock_fsm):
        """正常登録テスト"""
        # 進捗シグナルの監視
        progress_signals = []
        batch_signals = []

        worker.progress_updated.connect(lambda p: progress_signals.append(p))
        worker.batch_progress.connect(lambda c, t, f: batch_signals.append((c, t, f)))

        # 実行
        result = worker.execute()

        # 結果検証
        assert result.registered_count == 3
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert len(result.processed_paths) == 3
        assert result.total_processing_time > 0

        # FSM呼び出し確認
        mock_fsm.get_image_files.assert_called_once_with(Path("/test/directory"))

        # DB登録呼び出し確認
        assert mock_db_manager.register_image.call_count == 3

        # 進捗シグナル確認
        assert len(progress_signals) > 0
        assert len(batch_signals) == 3

    def test_duplicate_handling(self, worker, mock_db_manager, mock_fsm):
        """重複処理テスト"""
        # 2番目の画像を重複として設定
        mock_db_manager.detect_duplicate_image.side_effect = [False, True, False]

        result = worker.execute()

        assert result.registered_count == 2
        assert result.skipped_count == 1
        assert result.error_count == 0

    def test_error_handling(self, worker, mock_db_manager, mock_fsm):
        """エラーハンドリングテスト"""
        # 2番目の画像でエラーを発生
        mock_db_manager.register_image.side_effect = [None, Exception("DB Error"), None]

        result = worker.execute()

        # エラーが発生しても処理が続行される
        assert result.registered_count == 2
        assert result.error_count == 1

    def test_cancellation(self, worker):
        """キャンセルテスト"""
        # キャンセル実行
        worker.cancel()

        # キャンセル後の実行でRuntimeErrorが発生することを確認
        with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
            worker.execute()

    def test_empty_directory(self, worker, mock_fsm):
        """空ディレクトリテスト"""
        mock_fsm.get_image_files.return_value = []

        result = worker.execute()

        assert result.registered_count == 0
        assert result.skipped_count == 0
        assert result.error_count == 0
        assert len(result.processed_paths) == 0


class TestSearchWorker:
    """SearchWorker のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock = Mock()
        mock.get_images_by_filter.return_value = (
            [
                {"id": 1, "stored_image_path": "/test/image1.jpg"},
                {"id": 2, "stored_image_path": "/test/image2.jpg"},
            ],
            2,
        )
        return mock

    @pytest.fixture
    def search_conditions(self):
        """検索条件"""
        return {
            "tags": ["test", "sample"],
            "caption": "test image",
            "resolution": "1024x768",
            "use_and": True,
            "date_range": (None, None),
            "include_untagged": False,
        }

    @pytest.fixture
    def worker(self, mock_db_manager, search_conditions):
        """テスト用検索ワーカー"""
        return SearchWorker(
            db_manager=mock_db_manager,
            filter_conditions=search_conditions,
        )

    def test_successful_search(self, worker, mock_db_manager, search_conditions):
        """正常検索テスト"""
        # 進捗シグナルの監視
        progress_signals = []
        worker.progress_updated.connect(lambda p: progress_signals.append(p))

        # 実行
        result = worker.execute()

        # 結果検証
        assert result.total_count == 2
        assert len(result.image_metadata) == 2
        assert result.filter_conditions == search_conditions
        assert result.search_time > 0

        # DB検索呼び出し確認
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=["test", "sample"],
            caption="test image",
            resolution="1024x768",
            use_and=True,
            start_date=None,
            end_date=None,
            include_untagged=False,
        )

        # 進捗シグナル確認
        assert len(progress_signals) > 0

    def test_cancellation(self, worker):
        """キャンセルテスト"""
        # キャンセル実行
        worker.cancel()

        # キャンセル後の実行でRuntimeErrorが発生することを確認
        with pytest.raises(RuntimeError, match="処理がキャンセルされました"):
            worker.execute()

    def test_empty_search_result(self, worker, mock_db_manager):
        """空の検索結果テスト"""
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        result = worker.execute()

        assert result.total_count == 0
        assert len(result.image_metadata) == 0

    def test_search_with_date_range(self, mock_db_manager):
        """日付範囲検索テスト"""
        conditions = {
            "tags": [],
            "caption": "",
            "resolution": "",
            "use_and": True,
            "date_range": ("2023-01-01", "2023-12-31"),
            "include_untagged": True,
        }

        worker = SearchWorker(mock_db_manager, conditions)
        worker.execute()

        # 日付範囲が正しく渡されることを確認
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=[],
            caption="",
            resolution="",
            use_and=True,
            start_date="2023-01-01",
            end_date="2023-12-31",
            include_untagged=True,
        )
