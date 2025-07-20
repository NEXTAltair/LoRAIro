# tests/unit/gui/workers/test_search_worker.py

import time
from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QApplication

from lorairo.gui.workers.search import SearchResult, SearchWorker

# Ensure QApplication exists for Qt tests
if not QApplication.instance():
    app = QApplication([])


class TestSearchResult:
    """SearchResult データクラスのテスト"""

    def test_basic_creation(self):
        """基本的な作成テスト"""
        image_metadata = [{"id": 1, "path": "/test/image1.jpg"}]
        filter_conditions = {"tags": ["test"]}

        result = SearchResult(
            image_metadata=image_metadata,
            total_count=1,
            search_time=0.5,
            filter_conditions=filter_conditions,
        )

        assert result.image_metadata == image_metadata
        assert result.total_count == 1
        assert result.search_time == 0.5
        assert result.filter_conditions == filter_conditions

    def test_empty_result(self):
        """空結果作成テスト"""
        result = SearchResult(
            image_metadata=[],
            total_count=0,
            search_time=0.0,
            filter_conditions={},
        )

        assert result.image_metadata == []
        assert result.total_count == 0
        assert result.search_time == 0.0
        assert result.filter_conditions == {}


class TestSearchWorker:
    """SearchWorker のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        mock = Mock()
        mock.get_images_by_filter.return_value = (
            [
                {"id": 1, "stored_image_path": "/test/image1.jpg", "width": 1024, "height": 768},
                {"id": 2, "stored_image_path": "/test/image2.jpg", "width": 800, "height": 600},
                {"id": 3, "stored_image_path": "/test/image3.jpg", "width": 1200, "height": 900},
            ],
            3,
        )
        return mock

    @pytest.fixture
    def basic_filter_conditions(self):
        """基本フィルター条件"""
        return {
            "tags": ["test", "sample"],
            "caption": "test image",
            "resolution": 1024,
            "use_and": True,
            "date_range": (None, None),
            "include_untagged": False,
        }

    @pytest.fixture
    def search_worker(self, mock_db_manager, basic_filter_conditions):
        """テスト用SearchWorker"""
        return SearchWorker(mock_db_manager, basic_filter_conditions)

    def test_initialization(self, search_worker, mock_db_manager, basic_filter_conditions):
        """初期化テスト"""
        assert search_worker.db_manager == mock_db_manager
        assert search_worker.filter_conditions == basic_filter_conditions

    def test_successful_search(self, search_worker, mock_db_manager, basic_filter_conditions):
        """正常検索テスト"""
        # 進捗シグナル受信用モック
        progress_signals = []
        
        def capture_progress(progress):
            progress_signals.append({
                'percentage': progress.percentage,
                'message': progress.status_message,
                'processed': progress.processed_count,
                'total': progress.total_count
            })
        
        search_worker.progress_updated.connect(capture_progress)

        # 実行
        result = search_worker.execute()

        # 結果検証
        assert isinstance(result, SearchResult)
        assert len(result.image_metadata) == 3
        assert result.total_count == 3
        assert result.search_time > 0
        assert result.filter_conditions == basic_filter_conditions

        # 画像メタデータ内容確認
        assert result.image_metadata[0]["id"] == 1
        assert result.image_metadata[1]["id"] == 2
        assert result.image_metadata[2]["id"] == 3

        # DB呼び出し確認
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=["test", "sample"],
            caption="test image",
            resolution=1024,
            use_and=True,
            start_date=None,
            end_date=None,
            include_untagged=False,
        )

        # 進捗シグナル確認
        assert len(progress_signals) >= 3  # 開始、解析、実行、完了
        
        # 進捗の順序確認
        percentages = [sig['percentage'] for sig in progress_signals]
        assert 10 in percentages  # 開始
        assert 30 in percentages  # 解析中
        assert 60 in percentages  # 実行中
        assert 100 in percentages  # 完了

        # 最終進捗の詳細確認
        final_progress = next(sig for sig in progress_signals if sig['percentage'] == 100)
        assert "検索完了" in final_progress['message']
        assert "3件" in final_progress['message']
        assert final_progress['processed'] == 3
        assert final_progress['total'] == 3

    def test_search_with_date_range(self, mock_db_manager):
        """日付範囲付き検索テスト"""
        filter_conditions = {
            "tags": ["anime"],
            "caption": "",
            "resolution": 0,
            "use_and": False,
            "date_range": ("2023-01-01", "2023-12-31"),
            "include_untagged": True,
        }

        worker = SearchWorker(mock_db_manager, filter_conditions)
        result = worker.execute()

        # DB呼び出し確認（日付範囲が正しく渡されることを確認）
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=["anime"],
            caption="",
            resolution=0,
            use_and=False,
            start_date="2023-01-01",
            end_date="2023-12-31",
            include_untagged=True,
        )

        assert result.filter_conditions == filter_conditions

    def test_search_with_resolution_filter(self, mock_db_manager):
        """解像度フィルター付き検索テスト"""
        filter_conditions = {
            "tags": [],
            "caption": "",
            "resolution": 2048,
            "use_and": True,
            "date_range": (None, None),
            "include_untagged": False,
        }

        worker = SearchWorker(mock_db_manager, filter_conditions)
        worker.execute()

        # 解像度フィルターが正しく渡されることを確認
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=[],
            caption="",
            resolution=2048,
            use_and=True,
            start_date=None,
            end_date=None,
            include_untagged=False,
        )

    def test_search_empty_result(self, mock_db_manager, basic_filter_conditions):
        """空検索結果テスト"""
        # 空結果を返すように設定
        mock_db_manager.get_images_by_filter.return_value = ([], 0)

        worker = SearchWorker(mock_db_manager, basic_filter_conditions)
        result = worker.execute()

        # 空結果確認
        assert result.total_count == 0
        assert len(result.image_metadata) == 0
        assert result.search_time >= 0

    def test_search_cancellation(self, mock_db_manager, basic_filter_conditions):
        """検索キャンセルテスト"""
        worker = SearchWorker(mock_db_manager, basic_filter_conditions)

        # キャンセル実行（execute前）
        worker.cancel()

        # 実行
        result = worker.execute()

        # キャンセル結果確認
        assert result.total_count == 0
        assert len(result.image_metadata) == 0
        assert result.search_time == 0.0
        assert result.filter_conditions == basic_filter_conditions

        # DB呼び出しが実行されないことを確認
        mock_db_manager.get_images_by_filter.assert_not_called()

    def test_search_database_error(self, mock_db_manager, basic_filter_conditions):
        """データベースエラーテスト"""
        # DB エラーを発生させる
        mock_db_manager.get_images_by_filter.side_effect = RuntimeError("データベース接続エラー")

        worker = SearchWorker(mock_db_manager, basic_filter_conditions)

        # エラーが再発生することを確認
        with pytest.raises(RuntimeError, match="データベース接続エラー"):
            worker.execute()

    def test_filter_condition_parsing(self, mock_db_manager):
        """フィルター条件解析テスト"""
        # 様々な条件を含むフィルター
        filter_conditions = {
            "tags": ["tag1", "tag2", "tag3"],
            "caption": "beautiful landscape",
            "resolution": 1920,
            "use_and": False,
            "date_range": ("2022-06-01", "2022-06-30"),
            "include_untagged": True,
        }

        worker = SearchWorker(mock_db_manager, filter_conditions)
        worker.execute()

        # 全ての条件が正しく解析・渡されることを確認
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=["tag1", "tag2", "tag3"],
            caption="beautiful landscape",
            resolution=1920,
            use_and=False,
            start_date="2022-06-01",
            end_date="2022-06-30",
            include_untagged=True,
        )

    def test_missing_filter_keys(self, mock_db_manager):
        """フィルターキー不足テスト"""
        # 一部のキーが欠落したフィルター条件
        incomplete_conditions = {
            "tags": ["test"],
            # caption, resolution, use_and, date_range, include_untagged が欠落
        }

        worker = SearchWorker(mock_db_manager, incomplete_conditions)
        worker.execute()

        # デフォルト値が使用されることを確認
        mock_db_manager.get_images_by_filter.assert_called_once_with(
            tags=["test"],
            caption="",  # デフォルト
            resolution=0,  # デフォルト
            use_and=True,  # デフォルト
            start_date=None,  # デフォルト
            end_date=None,  # デフォルト
            include_untagged=False,  # デフォルト
        )

    def test_search_timing(self, mock_db_manager, basic_filter_conditions):
        """検索時間測定テスト"""
        # DB呼び出しに遅延を追加
        def slow_search(*args, **kwargs):
            time.sleep(0.1)  # 100ms の遅延
            return ([{"id": 1, "path": "/test.jpg"}], 1)

        mock_db_manager.get_images_by_filter.side_effect = slow_search

        worker = SearchWorker(mock_db_manager, basic_filter_conditions)
        result = worker.execute()

        # 測定された時間が遅延を反映していることを確認
        assert result.search_time >= 0.1
        assert result.search_time < 1.0  # 過度に長くないことも確認

    def test_progress_signal_emission(self, mock_db_manager, basic_filter_conditions):
        """進捗シグナル発行テスト"""
        worker = SearchWorker(mock_db_manager, basic_filter_conditions)

        # シグナル発行回数をカウント
        signal_count = 0
        
        def count_signals(progress):
            nonlocal signal_count
            signal_count += 1

        worker.progress_updated.connect(count_signals)

        # 実行
        worker.execute()

        # 適切な回数のシグナルが発行されたことを確認
        assert signal_count >= 3  # 最低限の進捗報告（開始、解析、実行、完了）