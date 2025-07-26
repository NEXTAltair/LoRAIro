"""Performance Tests

Phase 4実装のパフォーマンス要件をテスト
DB登録性能（1000画像/5分）、バッチ処理性能（100画像）等の要件確認
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from lorairo.services.annotation_batch_processor import BatchProcessor
from lorairo.services.annotator_lib_adapter import MockAnnotatorLibAdapter
from lorairo.services.model_sync_service import ModelSyncService
from lorairo.services.service_container import ServiceContainer


@pytest.mark.slow
class TestPerformanceRequirements:
    """パフォーマンス要件テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_database_registration_performance(self):
        """DB登録性能テスト（要件: 1000画像/5分）"""
        mock_config = Mock()
        mock_db_repository = Mock()

        # DB操作の高速化をシミュレート
        mock_db_repository.get_model_by_name.return_value = None

        sync_service = ModelSyncService(mock_db_repository, mock_config)

        # 大量モデルデータ準備
        large_model_list = []
        for i in range(100):  # 100モデルでテスト（1000の縮小版）
            large_model_list.append(
                {
                    "name": f"test-model-{i}",
                    "class": "TestAnnotator",
                    "provider": "test",
                    "model_type": "vision",
                    "requires_api_key": True,
                    "estimated_size_gb": None,
                    "api_model_id": f"test-{i}",
                    "discontinued_at": None,
                }
            )

        # 性能測定
        start_time = time.time()
        count = sync_service.register_new_models_to_db(large_model_list)
        elapsed_time = time.time() - start_time

        # 性能要件確認（100モデル/30秒以内 = 1000モデル/5分相当）
        assert elapsed_time < 30.0, f"DB登録が遅すぎます: {elapsed_time:.2f}秒"
        assert count >= 0

        # スループット計算
        throughput = len(large_model_list) / elapsed_time
        expected_min_throughput = 100 / 30  # モデル/秒
        assert throughput >= expected_min_throughput, f"スループット不足: {throughput:.2f} models/sec"

    def test_batch_processing_performance(self):
        """バッチ処理性能テスト（要件: 100画像バッチ処理）"""
        mock_config = Mock()
        mock_adapter = Mock()

        # 高速モックレスポンス設定
        mock_results = {}
        for i in range(100):
            mock_results[f"phash_{i}"] = {
                "gpt-4o": {"formatted_output": {"captions": [f"Image {i}"]}, "error": None}
            }
        mock_adapter.call_annotate.return_value = mock_results

        processor = BatchProcessor(mock_adapter, mock_config)

        # 100画像パス準備（実際のファイルは作らない）
        with tempfile.TemporaryDirectory() as temp_dir:
            image_paths = []
            for i in range(100):
                image_path = Path(temp_dir) / f"test_image_{i}.jpg"
                # 実際の画像ファイル作成（最小サイズ）
                test_image = Image.new("RGB", (50, 50), "red")
                test_image.save(image_path, "JPEG")
                image_paths.append(image_path)

            # バッチ処理性能測定
            start_time = time.time()
            result = processor.execute_batch_annotation(image_paths, ["gpt-4o"], batch_size=50)
            elapsed_time = time.time() - start_time

            # 性能要件確認（100画像/60秒以内）
            assert elapsed_time < 60.0, f"バッチ処理が遅すぎます: {elapsed_time:.2f}秒"
            assert result.total_images == 100
            assert result.processed_images == 100

            # スループット計算
            throughput = result.processed_images / elapsed_time
            expected_min_throughput = 100 / 60  # 画像/秒
            assert throughput >= expected_min_throughput, (
                f"処理スループット不足: {throughput:.2f} images/sec"
            )

    def test_model_sync_performance(self):
        """モデル同期性能テスト"""
        mock_config = Mock()
        mock_db_repository = Mock()
        mock_library = Mock()

        # 大量モデルメタデータ準備
        large_metadata = []
        for i in range(50):
            large_metadata.append(
                {
                    "name": f"sync-model-{i}",
                    "class": "SyncAnnotator",
                    "provider": "sync-provider",
                    "model_type": "vision",
                    "requires_api_key": True,
                }
            )

        mock_library.get_available_models_with_metadata.return_value = large_metadata
        mock_db_repository.get_model_by_name.return_value = None

        sync_service = ModelSyncService(mock_db_repository, mock_config, annotator_library=mock_library)

        # 同期性能測定
        start_time = time.time()
        result = sync_service.sync_available_models()
        elapsed_time = time.time() - start_time

        # 性能要件確認（50モデル/10秒以内）
        assert elapsed_time < 10.0, f"モデル同期が遅すぎます: {elapsed_time:.2f}秒"
        assert result.success is True
        assert result.total_library_models == 50

    def test_annotator_adapter_performance(self):
        """アノテーターアダプター性能テスト"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # 大量画像準備
        large_image_set = []
        for i in range(20):  # 20画像（性能テスト用）
            large_image_set.append(Image.new("RGB", (100, 100), "blue"))

        # 複数モデルでの処理
        test_models = ["gpt-4o", "claude-3-5-sonnet", "gemini-flash"]

        # アノテーション性能測定
        start_time = time.time()
        results = adapter.call_annotate(images=large_image_set, models=test_models)
        elapsed_time = time.time() - start_time

        # 性能要件確認（20画像×3モデル/30秒以内）
        total_annotations = len(large_image_set) * len(test_models)
        assert elapsed_time < 30.0, f"アノテーション処理が遅すぎます: {elapsed_time:.2f}秒"
        assert isinstance(results, dict)

        # スループット計算
        throughput = total_annotations / elapsed_time
        expected_min_throughput = 2.0  # アノテーション/秒
        assert throughput >= expected_min_throughput, (
            f"アノテーションスループット不足: {throughput:.2f} annotations/sec"
        )

    def test_service_container_initialization_performance(self):
        """ServiceContainer初期化性能テスト"""
        # 初期化性能測定
        start_time = time.time()

        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.FileSystemManager") as mock_fs_class,
            patch("lorairo.services.service_container.ImageRepository") as mock_repo_class,
        ):
            mock_config_class.return_value = Mock()
            mock_fs_class.return_value = Mock()
            mock_repo_class.return_value = Mock()

            container = ServiceContainer()

            # 全サービス初期化
            _ = container.config_service
            _ = container.file_system_manager
            _ = container.image_repository
            _ = container.annotator_lib_adapter

        elapsed_time = time.time() - start_time

        # 初期化性能要件（5秒以内）
        assert elapsed_time < 5.0, f"ServiceContainer初期化が遅すぎます: {elapsed_time:.2f}秒"

    def test_memory_usage_performance(self):
        """メモリ使用量性能テスト"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # 大量データ処理
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # 大量画像セット
        many_images = []
        for i in range(100):
            many_images.append(Image.new("RGB", (200, 200), "green"))

        # 処理実行
        results = adapter.call_annotate(images=many_images, models=["gpt-4o"])

        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # メモリ使用量要件（500MB増加以内）
        assert memory_increase < 500, f"メモリ使用量が多すぎます: {memory_increase:.2f}MB増加"
        assert isinstance(results, dict)


@pytest.mark.slow
class TestScalabilityRequirements:
    """スケーラビリティ要件テスト"""

    def test_concurrent_annotation_performance(self):
        """並行アノテーション性能テスト"""
        import concurrent.futures
        import threading

        mock_config = Mock()

        def annotation_task(task_id):
            """アノテーションタスク"""
            adapter = MockAnnotatorLibAdapter(mock_config)
            test_images = [Image.new("RGB", (50, 50), f"color_{task_id}")]

            start_time = time.time()
            results = adapter.call_annotate(images=test_images, models=["gpt-4o"])
            elapsed_time = time.time() - start_time

            return {
                "task_id": task_id,
                "elapsed_time": elapsed_time,
                "success": isinstance(results, dict) and len(results) > 0,
            }

        # 10並行タスク実行
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(annotation_task, i) for i in range(10)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        total_elapsed = time.time() - start_time

        # 並行処理性能要件（10タスク/20秒以内）
        assert total_elapsed < 20.0, f"並行処理が遅すぎます: {total_elapsed:.2f}秒"

        # 全タスク成功確認
        success_count = sum(1 for r in results if r["success"])
        assert success_count == 10, f"タスク失敗: {success_count}/10成功"

    def test_large_batch_scalability(self):
        """大規模バッチスケーラビリティテスト"""
        mock_config = Mock()
        mock_adapter = Mock()

        # 非常に大きなレスポンス準備
        huge_results = {}
        for i in range(1000):  # 1000画像分
            huge_results[f"phash_{i}"] = {
                "gpt-4o": {"formatted_output": {"captions": [f"Large batch image {i}"]}, "error": None}
            }
        mock_adapter.call_annotate.return_value = huge_results

        processor = BatchProcessor(mock_adapter, mock_config)

        # 大規模バッチリクエスト作成
        large_paths = [Path(f"/test/large_image_{i}.jpg") for i in range(1000)]

        start_time = time.time()
        request = processor.create_batch_request(large_paths, "gpt-4o")
        elapsed_time = time.time() - start_time

        # スケーラビリティ要件（1000画像リクエスト/5秒以内）
        assert elapsed_time < 5.0, f"大規模バッチリクエスト作成が遅すぎます: {elapsed_time:.2f}秒"
        assert request["total_images"] == 1000

    def test_model_metadata_scalability(self):
        """モデルメタデータスケーラビリティテスト"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # メタデータ取得性能測定
        start_time = time.time()
        models = adapter.get_available_models_with_metadata()
        elapsed_time = time.time() - start_time

        # メタデータ取得性能要件（1秒以内）
        assert elapsed_time < 1.0, f"モデルメタデータ取得が遅すぎます: {elapsed_time:.2f}秒"
        assert isinstance(models, list)
        assert len(models) > 0


@pytest.mark.slow
class TestResourceUtilizationPerformance:
    """リソース使用効率性能テスト"""

    def test_cpu_utilization_efficiency(self):
        """CPU使用効率テスト"""
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_cpu_times = process.cpu_times()

        # CPU集約的処理
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # 多数の小さな画像処理
        small_images = []
        for i in range(50):
            small_images.append(Image.new("RGB", (100, 100), "red"))

        start_time = time.time()
        results = adapter.call_annotate(images=small_images, models=["gpt-4o", "claude-3-5-sonnet"])
        elapsed_time = time.time() - start_time

        final_cpu_times = process.cpu_times()
        cpu_time_used = (final_cpu_times.user + final_cpu_times.system) - (
            initial_cpu_times.user + initial_cpu_times.system
        )

        # CPU効率要件（CPU時間/実時間 < 2.0）
        cpu_efficiency = cpu_time_used / elapsed_time if elapsed_time > 0 else 0
        assert cpu_efficiency < 2.0, f"CPU使用効率が悪すぎます: {cpu_efficiency:.2f}"
        assert isinstance(results, dict)

    def test_file_io_performance(self):
        """ファイルI/O性能テスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 大量小ファイル作成・読み込み性能
            file_paths = []
            create_start = time.time()

            for i in range(100):
                file_path = Path(temp_dir) / f"test_file_{i}.txt"
                file_path.write_text(f"Test content for file {i}", encoding="utf-8")
                file_paths.append(file_path)

            create_elapsed = time.time() - create_start

            # 読み込み性能測定
            read_start = time.time()
            total_content = ""
            for file_path in file_paths:
                total_content += file_path.read_text(encoding="utf-8")
            read_elapsed = time.time() - read_start

            # I/O性能要件
            assert create_elapsed < 10.0, f"ファイル作成が遅すぎます: {create_elapsed:.2f}秒"
            assert read_elapsed < 5.0, f"ファイル読み込みが遅すぎます: {read_elapsed:.2f}秒"
            assert len(total_content) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "slow"])
