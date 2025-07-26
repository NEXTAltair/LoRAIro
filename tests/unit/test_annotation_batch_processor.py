"""BatchProcessor (AnnotationBatchProcessor) ユニットテスト

Phase 4実装のアノテーション専用バッチプロセッサーをテスト
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image

from lorairo.services.annotation_batch_processor import BatchAnnotationResult, BatchProcessor


class TestBatchAnnotationResult:
    """BatchAnnotationResult データクラステスト"""

    def test_batch_annotation_result_initialization(self):
        """BatchAnnotationResult初期化テスト"""
        result = BatchAnnotationResult(
            total_images=100,
            processed_images=95,
            successful_annotations=85,
            failed_annotations=10,
            batch_id="test_batch_001",
            results={"test": "data"},
        )

        assert result.total_images == 100
        assert result.processed_images == 95
        assert result.successful_annotations == 85
        assert result.failed_annotations == 10
        assert result.batch_id == "test_batch_001"
        assert result.results == {"test": "data"}

    def test_batch_annotation_result_default_values(self):
        """BatchAnnotationResult デフォルト値テスト"""
        result = BatchAnnotationResult(
            total_images=50, processed_images=45, successful_annotations=40, failed_annotations=5
        )

        assert result.batch_id is None
        assert result.results == {}

    def test_success_rate_calculation(self):
        """成功率計算テスト"""
        result = BatchAnnotationResult(
            total_images=100, processed_images=100, successful_annotations=85, failed_annotations=15
        )

        assert result.success_rate == 85.0

    def test_success_rate_zero_total(self):
        """総数ゼロ時の成功率計算"""
        result = BatchAnnotationResult(
            total_images=0, processed_images=0, successful_annotations=0, failed_annotations=0
        )

        assert result.success_rate == 0.0

    def test_summary_generation(self):
        """サマリー生成テスト"""
        result = BatchAnnotationResult(
            total_images=200, processed_images=180, successful_annotations=150, failed_annotations=30
        )

        summary = result.summary
        assert "総数200" in summary
        assert "処理済み180" in summary
        assert "成功150" in summary
        assert "失敗30" in summary
        assert "成功率75.0%" in summary


class TestBatchProcessorInitialization:
    """BatchProcessor 初期化テスト"""

    def test_initialization_success(self):
        """正常な初期化テスト"""
        mock_adapter = Mock()
        mock_config = Mock()

        processor = BatchProcessor(mock_adapter, mock_config)

        assert processor.annotator_adapter is mock_adapter
        assert processor.config_service is mock_config

    def test_initialization_with_real_components(self):
        """実際のコンポーネントでの初期化"""
        # 実際のコンポーネントのモック
        from lorairo.services.annotator_lib_adapter import MockAnnotatorLibAdapter
        from lorairo.services.configuration_service import ConfigurationService

        with patch.object(ConfigurationService, "__init__", return_value=None):
            mock_config = Mock(spec=ConfigurationService)
            mock_adapter = Mock(spec=MockAnnotatorLibAdapter)

            processor = BatchProcessor(mock_adapter, mock_config)

            assert processor.annotator_adapter is mock_adapter
            assert processor.config_service is mock_config


class TestBatchProcessorRequestGeneration:
    """BatchProcessor バッチリクエスト生成テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_create_batch_request_success(self, batch_processor):
        """バッチリクエスト生成成功"""
        test_paths = [Path("/test/image1.jpg"), Path("/test/image2.jpg")]
        test_model = "gpt-4o"

        request = batch_processor.create_batch_request(test_paths, test_model)

        assert isinstance(request, dict)
        assert "batch_id" in request
        assert request["model_name"] == test_model
        assert request["total_images"] == len(test_paths)
        assert request["image_paths"] == [str(p) for p in test_paths]
        assert request["status"] == "created"
        assert "created_at" in request

    def test_create_batch_request_empty_paths(self, batch_processor):
        """空パスリストでのバッチリクエスト生成"""
        test_paths = []
        test_model = "gpt-4o"

        request = batch_processor.create_batch_request(test_paths, test_model)

        assert request["total_images"] == 0
        assert request["image_paths"] == []

    def test_create_batch_request_many_images(self, batch_processor):
        """多数画像でのバッチリクエスト生成"""
        test_paths = [Path(f"/test/image{i}.jpg") for i in range(500)]
        test_model = "claude-3-5-sonnet"

        request = batch_processor.create_batch_request(test_paths, test_model)

        assert request["total_images"] == 500
        assert len(request["image_paths"]) == 500
        assert request["model_name"] == test_model

    def test_create_batch_request_batch_id_uniqueness(self, batch_processor):
        """バッチIDの一意性確認"""
        test_paths1 = [Path("/test/image1.jpg")]
        test_paths2 = [Path("/test/image2.jpg")]
        test_model = "gpt-4o"

        request1 = batch_processor.create_batch_request(test_paths1, test_model)
        request2 = batch_processor.create_batch_request(test_paths2, test_model)

        assert request1["batch_id"] != request2["batch_id"]


class TestBatchProcessorResultProcessing:
    """BatchProcessor 結果処理テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_process_batch_results_success(self, batch_processor):
        """バッチ結果処理成功"""
        test_results = {
            "phash_1": {
                "gpt-4o": {"formatted_output": {"captions": ["A red car"]}, "error": None},
                "claude-3-5-sonnet": {"formatted_output": {"captions": ["Red vehicle"]}, "error": None},
            },
            "phash_2": {
                "gpt-4o": {"error": "Processing failed"},
                "claude-3-5-sonnet": {"formatted_output": {"captions": ["Blue sky"]}, "error": None},
            },
        }

        result = batch_processor.process_batch_results(test_results)

        assert isinstance(result, BatchAnnotationResult)
        assert result.total_images == 2
        assert result.processed_images == 2
        assert result.successful_annotations == 3  # 成功した3つのアノテーション
        assert result.failed_annotations == 1  # 失敗した1つのアノテーション
        assert result.results == test_results

    def test_process_batch_results_empty(self, batch_processor):
        """空の結果処理"""
        test_results = {}

        result = batch_processor.process_batch_results(test_results)

        assert result.total_images == 0
        assert result.processed_images == 0
        assert result.successful_annotations == 0
        assert result.failed_annotations == 0

    def test_process_batch_results_all_failures(self, batch_processor):
        """全失敗結果処理"""
        test_results = {
            "phash_1": {
                "gpt-4o": {"error": "API error"},
                "claude-3-5-sonnet": {"error": "Rate limit exceeded"},
            }
        }

        result = batch_processor.process_batch_results(test_results)

        assert result.total_images == 1
        assert result.successful_annotations == 0
        assert result.failed_annotations == 2
        assert result.success_rate == 0.0

    def test_process_batch_results_all_successes(self, batch_processor):
        """全成功結果処理"""
        test_results = {
            "phash_1": {"gpt-4o": {"formatted_output": {"captions": ["Success 1"]}, "error": None}},
            "phash_2": {"gpt-4o": {"formatted_output": {"captions": ["Success 2"]}, "error": None}},
        }

        result = batch_processor.process_batch_results(test_results)

        assert result.total_images == 2
        assert result.successful_annotations == 2
        assert result.failed_annotations == 0
        assert result.success_rate == 100.0


class TestBatchProcessorOpenAIBatch:
    """BatchProcessor OpenAI Batch API テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_submit_openai_batch_no_api_key(self, batch_processor):
        """OpenAI APIキーなしでの送信（モックフォールバック）"""
        # APIキーなしの設定
        batch_processor.config_service.get_setting.return_value = ""

        test_requests = [{"request": "test1"}, {"request": "test2"}]

        with patch.object(batch_processor, "_submit_openai_batch_mock") as mock_fallback:
            mock_fallback.return_value = "mock_batch_id"

            batch_id = batch_processor.submit_openai_batch(test_requests)

            assert batch_id == "mock_batch_id"
            mock_fallback.assert_called_once_with(test_requests)

    def test_submit_openai_batch_with_api_key_success(self, batch_processor):
        """OpenAI APIキーありでの送信成功"""
        # APIキー設定
        batch_processor.config_service.get_setting.return_value = "test_api_key"

        test_requests = [{"request": "test1"}]

        with patch(
            "lorairo.services.annotation_batch_processor.OpenAIBatchProcessor"
        ) as mock_processor_class:
            mock_processor = Mock()
            mock_processor.start_batch_processing.return_value = "real_batch_id"
            mock_processor_class.return_value = mock_processor

            with patch.object(batch_processor, "_create_jsonl_file") as mock_create_jsonl:
                mock_create_jsonl.return_value = Path("/tmp/test.jsonl")

                batch_id = batch_processor.submit_openai_batch(test_requests)

                assert batch_id == "real_batch_id"
                mock_processor_class.assert_called_once_with("test_api_key")
                mock_processor.start_batch_processing.assert_called_once_with(Path("/tmp/test.jsonl"))

    def test_submit_openai_batch_import_error_fallback(self, batch_processor):
        """OpenAIBatchProcessor ImportError時のフォールバック"""
        batch_processor.config_service.get_setting.return_value = "test_api_key"

        test_requests = [{"request": "test1"}]

        with patch(
            "lorairo.services.annotation_batch_processor.OpenAIBatchProcessor", side_effect=ImportError
        ):
            with patch.object(batch_processor, "_submit_openai_batch_mock") as mock_fallback:
                mock_fallback.return_value = "fallback_batch_id"

                batch_id = batch_processor.submit_openai_batch(test_requests)

                assert batch_id == "fallback_batch_id"
                mock_fallback.assert_called_once_with(test_requests)

    def test_submit_openai_batch_exception_fallback(self, batch_processor):
        """OpenAI Batch API例外時のフォールバック"""
        batch_processor.config_service.get_setting.return_value = "test_api_key"

        test_requests = [{"request": "test1"}]

        with patch(
            "lorairo.services.annotation_batch_processor.OpenAIBatchProcessor"
        ) as mock_processor_class:
            mock_processor_class.side_effect = Exception("API Error")

            with patch.object(batch_processor, "_submit_openai_batch_mock") as mock_fallback:
                mock_fallback.return_value = "error_fallback_batch_id"

                batch_id = batch_processor.submit_openai_batch(test_requests)

                assert batch_id == "error_fallback_batch_id"
                mock_fallback.assert_called_once_with(test_requests)

    def test_submit_openai_batch_mock(self, batch_processor):
        """OpenAI Batch APIモック実装テスト"""
        test_requests = [{"request": "test1"}, {"request": "test2"}]

        batch_id = batch_processor._submit_openai_batch_mock(test_requests)

        assert isinstance(batch_id, str)
        assert batch_id.startswith("batch_openai_mock_")
        assert "2" in batch_id  # リクエスト数が含まれる


class TestBatchProcessorJSONLFile:
    """BatchProcessor JSONLファイル作成テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_create_jsonl_file_success(self, batch_processor):
        """JSONLファイル作成成功"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 設定でディレクトリ指定
            batch_processor.config_service.get_setting.return_value = temp_dir

            test_requests = [
                {"request_id": "req1", "data": "test1"},
                {"request_id": "req2", "data": "test2"},
            ]

            jsonl_path = batch_processor._create_jsonl_file(test_requests)

            # ファイルが作成されることを確認
            assert jsonl_path.exists()
            assert jsonl_path.suffix == ".jsonl"
            assert jsonl_path.parent == Path(temp_dir)

            # ファイル内容確認
            with open(jsonl_path, encoding="utf-8") as f:
                lines = f.readlines()

            assert len(lines) == 2
            assert json.loads(lines[0].strip()) == test_requests[0]
            assert json.loads(lines[1].strip()) == test_requests[1]

    def test_create_jsonl_file_no_config_directory(self, batch_processor):
        """設定ディレクトリなしでのJSONLファイル作成"""
        # 設定ディレクトリなし
        batch_processor.config_service.get_setting.return_value = ""

        test_requests = [{"request_id": "req1"}]

        with patch("pathlib.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/mock/current")

            jsonl_path = batch_processor._create_jsonl_file(test_requests)

            # デフォルトディレクトリが使用される
            assert str(jsonl_path.parent).endswith("batch_results")

    def test_create_jsonl_file_empty_requests(self, batch_processor):
        """空リクエストでのJSONLファイル作成"""
        with tempfile.TemporaryDirectory() as temp_dir:
            batch_processor.config_service.get_setting.return_value = temp_dir

            test_requests = []

            jsonl_path = batch_processor._create_jsonl_file(test_requests)

            assert jsonl_path.exists()
            # ファイルは空
            assert jsonl_path.stat().st_size == 0


class TestBatchProcessorExecuteBatchAnnotation:
    """BatchProcessor バッチアノテーション実行テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_execute_batch_annotation_success(self, batch_processor):
        """バッチアノテーション実行成功"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # テスト画像作成
            image_path1 = Path(temp_dir) / "test1.jpg"
            image_path2 = Path(temp_dir) / "test2.jpg"

            test_image = Image.new("RGB", (100, 100), "red")
            test_image.save(image_path1, "JPEG")
            test_image.save(image_path2, "JPEG")

            test_paths = [image_path1, image_path2]
            test_models = ["gpt-4o", "claude-3-5-sonnet"]

            # モックアノテーション結果
            mock_annotation_results = {
                "phash_1": {
                    "gpt-4o": {"formatted_output": {"captions": ["Red image"]}, "error": None},
                    "claude-3-5-sonnet": {"formatted_output": {"captions": ["Test image"]}, "error": None},
                },
                "phash_2": {
                    "gpt-4o": {"formatted_output": {"captions": ["Another red image"]}, "error": None},
                    "claude-3-5-sonnet": {"formatted_output": {"captions": ["Second test"]}, "error": None},
                },
            }
            batch_processor.annotator_adapter.call_annotate.return_value = mock_annotation_results

            # バッチアノテーション実行
            result = batch_processor.execute_batch_annotation(test_paths, test_models, batch_size=50)

            # 検証
            assert isinstance(result, BatchAnnotationResult)
            assert result.total_images == 2
            assert result.successful_annotations == 4  # 2画像 × 2モデル
            assert result.failed_annotations == 0

            # アノテーター呼び出し確認
            batch_processor.annotator_adapter.call_annotate.assert_called_once()
            call_args = batch_processor.annotator_adapter.call_annotate.call_args
            assert len(call_args[1]["images"]) == 2
            assert call_args[1]["models"] == test_models

    def test_execute_batch_annotation_nonexistent_files(self, batch_processor):
        """存在しないファイルでのバッチアノテーション"""
        nonexistent_paths = [Path("/nonexistent/image1.jpg"), Path("/nonexistent/image2.jpg")]
        test_models = ["gpt-4o"]

        result = batch_processor.execute_batch_annotation(nonexistent_paths, test_models)

        # 有効な画像がないため失敗結果
        assert result.total_images == 2
        assert result.processed_images == 0
        assert result.successful_annotations == 0
        assert result.failed_annotations == 2

        # アノテーターは呼ばれない
        batch_processor.annotator_adapter.call_annotate.assert_not_called()

    def test_execute_batch_annotation_empty_paths(self, batch_processor):
        """空パスリストでのバッチアノテーション"""
        test_paths = []
        test_models = ["gpt-4o"]

        result = batch_processor.execute_batch_annotation(test_paths, test_models)

        assert result.total_images == 0
        assert result.processed_images == 0
        assert result.successful_annotations == 0
        assert result.failed_annotations == 0

    def test_execute_batch_annotation_annotator_exception(self, batch_processor):
        """アノテーター例外でのバッチアノテーション"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # テスト画像作成
            image_path = Path(temp_dir) / "test.jpg"
            test_image = Image.new("RGB", (100, 100), "red")
            test_image.save(image_path, "JPEG")

            test_paths = [image_path]
            test_models = ["gpt-4o"]

            # アノテーター例外設定
            batch_processor.annotator_adapter.call_annotate.side_effect = Exception("Annotation failed")

            result = batch_processor.execute_batch_annotation(test_paths, test_models)

            # エラー結果が返される
            assert result.total_images == 1
            assert result.processed_images == 0
            assert result.successful_annotations == 0
            assert result.failed_annotations == 1


class TestBatchProcessorFileSaving:
    """BatchProcessor ファイル保存テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    @pytest.fixture
    def sample_batch_result(self):
        """サンプルバッチ結果"""
        results = {
            "phash_1": {
                "gpt-4o": {
                    "formatted_output": {
                        "captions": ["A red car driving on the road"],
                        "tags": ["car", "red", "road", "vehicle"],
                    },
                    "error": None,
                }
            },
            "phash_2": {
                "claude-3-5-sonnet": {
                    "formatted_output": {
                        "captions": ["Blue sky with white clouds"],
                        "tags": ["sky", "blue", "clouds", "weather"],
                    },
                    "error": None,
                }
            },
            "phash_3": {"gpt-4o": {"error": "Processing failed"}},
        }

        return BatchAnnotationResult(
            total_images=3,
            processed_images=3,
            successful_annotations=2,
            failed_annotations=1,
            results=results,
        )

    def test_save_batch_results_txt_format(self, batch_processor, sample_batch_result):
        """TXT形式でのバッチ結果保存"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            stats = batch_processor.save_batch_results_to_files(
                sample_batch_result, output_dir, format_type="txt"
            )

            # 統計確認
            assert stats["saved_files"] == 2  # 成功した2つのアノテーション
            assert stats["errors"] == 0

            # ファイル存在確認
            txt_file1 = output_dir / "phash_1_gpt-4o.txt"
            txt_file2 = output_dir / "phash_2_claude-3-5-sonnet.txt"

            assert txt_file1.exists()
            assert txt_file2.exists()

            # ファイル内容確認
            assert "car, red, road, vehicle" in txt_file1.read_text(encoding="utf-8")
            assert "sky, blue, clouds, weather" in txt_file2.read_text(encoding="utf-8")

    def test_save_batch_results_caption_format(self, batch_processor, sample_batch_result):
        """Caption形式でのバッチ結果保存"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            stats = batch_processor.save_batch_results_to_files(
                sample_batch_result, output_dir, format_type="caption"
            )

            # 統計確認
            assert stats["saved_files"] == 2
            assert stats["errors"] == 0

            # ファイル存在確認
            caption_file1 = output_dir / "phash_1_gpt-4o.caption"
            caption_file2 = output_dir / "phash_2_claude-3-5-sonnet.caption"

            assert caption_file1.exists()
            assert caption_file2.exists()

            # ファイル内容確認
            assert "A red car driving on the road" in caption_file1.read_text(encoding="utf-8")
            assert "Blue sky with white clouds" in caption_file2.read_text(encoding="utf-8")

    def test_save_batch_results_json_format(self, batch_processor, sample_batch_result):
        """JSON形式でのバッチ結果保存"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            stats = batch_processor.save_batch_results_to_files(
                sample_batch_result, output_dir, format_type="json"
            )

            # 統計確認
            assert stats["saved_files"] == 2
            assert stats["errors"] == 0

            # ファイル存在確認
            json_file1 = output_dir / "phash_1_gpt-4o.json"
            json_file2 = output_dir / "phash_2_claude-3-5-sonnet.json"

            assert json_file1.exists()
            assert json_file2.exists()

            # JSON内容確認
            json_data1 = json.loads(json_file1.read_text(encoding="utf-8"))
            assert "formatted_output" in json_data1
            assert json_data1["error"] is None

    def test_save_batch_results_nonexistent_directory(self, batch_processor, sample_batch_result):
        """存在しないディレクトリへの保存"""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "nonexistent" / "nested"

            stats = batch_processor.save_batch_results_to_files(
                sample_batch_result, output_dir, format_type="txt"
            )

            # ディレクトリが作成されて保存成功
            assert output_dir.exists()
            assert stats["saved_files"] == 2
            assert stats["errors"] == 0

    def test_save_batch_results_empty_results(self, batch_processor):
        """空結果の保存"""
        empty_result = BatchAnnotationResult(
            total_images=0, processed_images=0, successful_annotations=0, failed_annotations=0, results={}
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            stats = batch_processor.save_batch_results_to_files(empty_result, output_dir, format_type="txt")

            assert stats["saved_files"] == 0
            assert stats["errors"] == 0


class TestBatchProcessorCapabilities:
    """BatchProcessor 機能情報テスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_get_batch_processing_capabilities(self, batch_processor):
        """バッチ処理能力情報取得"""
        capabilities = batch_processor.get_batch_processing_capabilities()

        assert isinstance(capabilities, dict)
        assert "supported_providers" in capabilities
        assert "openai" in capabilities["supported_providers"]
        assert "anthropic" in capabilities["supported_providers"]
        assert "google" in capabilities["supported_providers"]

        assert capabilities["max_batch_size"] == 1000
        assert capabilities["supported_formats"] == ["txt", "caption", "json"]
        assert capabilities["concurrent_models"] is True
        assert capabilities["openai_batch_api"] is True
        assert "Phase" in capabilities["phase"]


# 境界値・エッジケーステスト
class TestBatchProcessorEdgeCases:
    """BatchProcessor 境界値・エッジケーステスト"""

    @pytest.fixture
    def batch_processor(self):
        """BatchProcessorインスタンス"""
        mock_adapter = Mock()
        mock_config = Mock()
        return BatchProcessor(mock_adapter, mock_config)

    def test_large_batch_processing(self, batch_processor):
        """大量バッチ処理テスト"""
        # 大量のパス（ただし実際のファイルは作らない）
        large_paths = [Path(f"/mock/image_{i}.jpg") for i in range(1000)]
        test_models = ["gpt-4o"]

        # 全て存在しないファイルなので空結果が返される
        result = batch_processor.execute_batch_annotation(large_paths, test_models)

        assert result.total_images == 1000
        assert result.processed_images == 0
        assert result.failed_annotations == 1000

    def test_unicode_file_paths(self, batch_processor):
        """Unicode文字含むファイルパスの処理"""
        unicode_paths = [
            Path("/test/画像_テスト_1.jpg"),
            Path("/test/テスト画像_２.jpg"),
            Path("/test/日本語ファイル名.jpg"),
        ]
        test_models = ["gpt-4o"]

        # パス自体の処理で例外が発生しないことを確認
        result = batch_processor.execute_batch_annotation(unicode_paths, test_models)

        # ファイルが存在しないので失敗結果
        assert result.total_images == 3
        assert result.processed_images == 0

    def test_very_long_model_names(self, batch_processor):
        """非常に長いモデル名の処理"""
        test_paths = []
        very_long_model = "a" * 500  # 500文字のモデル名

        result = batch_processor.execute_batch_annotation(test_paths, [very_long_model])

        # 空パスなので空結果
        assert result.total_images == 0


@pytest.mark.integration
class TestBatchProcessorIntegration:
    """BatchProcessor 統合テスト"""

    def test_full_batch_workflow(self):
        """完全なバッチワークフロー"""
        # 実際のアノテーターライブラリとの統合テスト
        # 本テストは統合テストファイルで実装
        pass
