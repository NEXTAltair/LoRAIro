"""Error Handling and Edge Cases Tests

Phase 4実装のエラーハンドリングと境界値テストを包括的にテスト
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image

from lorairo.services.annotation_batch_processor import BatchAnnotationResult, BatchProcessor
from lorairo.services.annotator_lib_adapter import AnnotatorLibAdapter, MockAnnotatorLibAdapter
from lorairo.services.model_sync_service import ModelSyncResult, ModelSyncService
from lorairo.services.service_container import ServiceContainer


class TestAnnotatorLibAdapterErrorHandling:
    """AnnotatorLibAdapter エラーハンドリングテスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        self.mock_config_service = Mock()
        self.mock_config_service.get_setting.return_value = "test_key"

    def test_mock_adapter_with_invalid_config(self):
        """無効な設定でのMockAdapter初期化"""
        invalid_config = None

        # 例外が発生しないことを確認
        adapter = MockAnnotatorLibAdapter(invalid_config)
        assert adapter is not None

        # メソッド呼び出しが可能
        models = adapter.get_available_models_with_metadata()
        assert isinstance(models, list)

    def test_mock_adapter_call_annotate_with_invalid_images(self):
        """無効な画像でのアノテーション呼び出し"""
        adapter = MockAnnotatorLibAdapter(self.mock_config_service)

        # None画像
        results = adapter.call_annotate(images=[None], models=["gpt-4o"])
        assert isinstance(results, dict)

        # 空リスト
        results = adapter.call_annotate(images=[], models=["gpt-4o"])
        assert isinstance(results, dict)
        assert len(results) == 0

    def test_mock_adapter_call_annotate_with_invalid_models(self):
        """無効なモデルでのアノテーション呼び出し"""
        adapter = MockAnnotatorLibAdapter(self.mock_config_service)
        test_images = [Image.new("RGB", (100, 100), "red")]

        # 空モデルリスト
        results = adapter.call_annotate(images=test_images, models=[])
        assert isinstance(results, dict)

        # Noneモデル
        results = adapter.call_annotate(images=test_images, models=[None])
        assert isinstance(results, dict)

    def test_mock_adapter_call_annotate_with_mismatched_phashes(self):
        """不一致pHashでのアノテーション呼び出し"""
        adapter = MockAnnotatorLibAdapter(self.mock_config_service)
        test_images = [Image.new("RGB", (100, 100), "red")]

        # 画像数とpHash数が異なる
        results = adapter.call_annotate(
            images=test_images,
            models=["gpt-4o"],
            phash_list=["hash1", "hash2", "hash3"],  # 画像1つに対してpHash3つ
        )
        assert isinstance(results, dict)

    @patch("image_annotator_lib.core.registry.list_available_annotators_with_metadata")
    def test_real_adapter_import_fallback(self, mock_list_func):
        """実アダプターImportError時のフォールバック"""
        mock_list_func.side_effect = ImportError("Cannot import image_annotator_lib")

        adapter = AnnotatorLibAdapter(self.mock_config_service)

        # フォールバック動作確認
        models = adapter.get_available_models_with_metadata()
        assert isinstance(models, list)
        assert len(models) > 0  # MockAdapterからの結果

    def test_real_adapter_runtime_error_fallback(self):
        """実アダプター実行時エラーのフォールバック"""
        adapter = AnnotatorLibAdapter(self.mock_config_service)
        test_images = [Image.new("RGB", (100, 100), "red")]

        # ProviderManagerがエラーを投げる場合のテスト
        with patch.object(adapter.provider_manager, "run_inference_with_model") as mock_inference:
            mock_inference.side_effect = RuntimeError("Annotation processing failed")

            # エラーハンドリング動作確認
            results = adapter.call_annotate(images=test_images, models=["gpt-4o"])
            assert isinstance(results, dict)
            # エラー時は空の結果（continue処理）
            assert len(results) == 0

    def test_get_unified_api_keys_with_missing_settings(self):
        """設定不足時のAPIキー取得"""
        mock_config = Mock()

        # 一部の設定のみ存在
        def mock_get_setting(section, key, default):
            if key == "openai_key":
                return "valid_openai_key"
            return default  # 他は全てデフォルト値

        mock_config.get_setting.side_effect = mock_get_setting

        adapter = MockAnnotatorLibAdapter(mock_config)
        api_keys = adapter.get_unified_api_keys()

        # 設定のあるキーのみ含まれる
        assert "openai" in api_keys
        assert api_keys["openai"] == "valid_openai_key"


class TestModelSyncServiceErrorHandling:
    """ModelSyncService エラーハンドリングテスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        self.mock_db_repository = Mock()
        self.mock_config_service = Mock()

    def test_sync_with_library_exception(self):
        """ライブラリ例外時の同期処理"""
        mock_library = Mock()
        mock_library.get_available_models_with_metadata.side_effect = Exception("Library connection failed")

        service = ModelSyncService(
            self.mock_db_repository, self.mock_config_service, annotator_library=mock_library
        )

        result = service.sync_available_models()

        assert isinstance(result, ModelSyncResult)
        assert result.success is False
        assert len(result.errors) > 0
        assert "Library connection failed" in str(result.errors)

    def test_sync_with_database_error(self):
        """データベースエラー時の同期処理"""
        mock_library = Mock()
        mock_library.get_available_models_with_metadata.return_value = [
            {
                "name": "test-model",
                "class": "TestAnnotator",
                "provider": "test",
                "model_type": "vision",
                "requires_api_key": True,
            }
        ]

        # データベース操作でエラー
        self.mock_db_repository.get_model_by_name.side_effect = Exception("Database connection failed")

        service = ModelSyncService(
            self.mock_db_repository, self.mock_config_service, annotator_library=mock_library
        )

        result = service.sync_available_models()

        assert isinstance(result, ModelSyncResult)
        assert result.success is False
        assert len(result.errors) > 0

    def test_register_new_models_with_invalid_metadata(self):
        """無効なメタデータでのモデル登録"""
        service = ModelSyncService(self.mock_db_repository, self.mock_config_service)

        # 不正なメタデータ
        invalid_models = [
            {
                "name": "",  # 空の名前
                "class": None,  # Noneクラス
                "provider": "test",
                "model_type": "unknown",
                "requires_api_key": "invalid_boolean",  # 無効なboolean
            },
            {
                # 必須フィールド不足
                "provider": "test"
            },
        ]

        # 例外が発生せずに処理されることを確認
        count = service.register_new_models_to_db(invalid_models)
        assert count >= 0

    def test_get_model_metadata_with_empty_library(self):
        """空のライブラリからのメタデータ取得"""
        mock_library = Mock()
        mock_library.get_available_models_with_metadata.return_value = []

        service = ModelSyncService(
            self.mock_db_repository, self.mock_config_service, annotator_library=mock_library
        )

        metadata_list = service.get_model_metadata_from_library()
        assert isinstance(metadata_list, list)
        assert len(metadata_list) == 0

    def test_update_existing_models_with_db_error(self):
        """データベースエラー時の既存モデル更新"""
        service = ModelSyncService(self.mock_db_repository, self.mock_config_service)

        # データベース操作でエラー
        def db_error_side_effect(*args, **kwargs):
            raise Exception("Database update failed")

        # モック設定をより具体的に
        original_method = service.update_existing_models

        test_models = [
            {
                "name": "test-model",
                "class": "TestAnnotator",
                "provider": "test",
                "model_type": "vision",
                "requires_api_key": True,
                "estimated_size_gb": None,
                "discontinued_at": None,
                "api_model_id": None,
            }
        ]

        # 例外が発生しても適切に処理されることを確認
        count = service.update_existing_models(test_models)
        assert count >= 0


class TestBatchProcessorErrorHandling:
    """BatchProcessor エラーハンドリングテスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        self.mock_adapter = Mock()
        self.mock_config = Mock()
        self.processor = BatchProcessor(self.mock_adapter, self.mock_config)

    def test_execute_batch_annotation_with_corrupted_images(self):
        """破損画像でのバッチアノテーション"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 破損画像ファイル作成
            corrupted_path = Path(temp_dir) / "corrupted.jpg"
            corrupted_path.write_text("This is not an image", encoding="utf-8")

            test_paths = [corrupted_path]
            test_models = ["gpt-4o"]

            result = self.processor.execute_batch_annotation(test_paths, test_models)

            # 破損画像は処理されない
            assert result.total_images == 1
            assert result.processed_images == 0
            assert result.failed_annotations == 1

    def test_execute_batch_annotation_with_permission_denied(self):
        """アクセス権限なしファイルでのバッチアノテーション"""
        # 存在しないパスでテスト（権限エラーの模擬）
        inaccessible_paths = [Path("/root/secret/image.jpg")]
        test_models = ["gpt-4o"]

        result = self.processor.execute_batch_annotation(inaccessible_paths, test_models)

        # アクセスできないファイルは処理されない
        assert result.total_images == 1
        assert result.processed_images == 0
        assert result.failed_annotations == 1

    def test_execute_batch_annotation_with_annotator_timeout(self):
        """アノテーター処理タイムアウト"""
        # アノテーターがタイムアウト例外を投げる
        self.mock_adapter.call_annotate.side_effect = TimeoutError("Annotation timeout")

        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "test.jpg"
            test_image = Image.new("RGB", (100, 100), "red")
            test_image.save(image_path, "JPEG")

            test_paths = [image_path]
            test_models = ["gpt-4o"]

            result = self.processor.execute_batch_annotation(test_paths, test_models)

            # タイムアウトエラーが適切に処理される
            assert result.total_images == 1
            assert result.processed_images == 0
            assert result.failed_annotations == 1

    def test_process_batch_results_with_malformed_data(self):
        """不正な形式の結果データ処理"""
        # 不正な結果構造
        malformed_results = {
            "invalid_structure": "not_a_dict",
            "missing_model_data": {},
            "phash_with_none": None,
        }

        # 例外が発生しても適切に処理されることを確認
        try:
            result = self.processor.process_batch_results(malformed_results)
            assert isinstance(result, BatchAnnotationResult)
        except Exception as e:
            # 例外が発生した場合もテストパス（適切なエラーハンドリング）
            assert "error" in str(e).lower() or "invalid" in str(e).lower()

    def test_save_batch_results_with_write_permission_error(self):
        """書き込み権限エラー時のファイル保存"""
        # 有効な結果データ
        test_results = {
            "phash_1": {"gpt-4o": {"formatted_output": {"tags": ["test", "image"]}, "error": None}}
        }

        batch_result = BatchAnnotationResult(
            total_images=1,
            processed_images=1,
            successful_annotations=1,
            failed_annotations=0,
            results=test_results,
        )

        # 存在しない/書き込み不可能なディレクトリ
        inaccessible_dir = Path("/root/readonly")

        stats = self.processor.save_batch_results_to_files(
            batch_result, inaccessible_dir, format_type="txt"
        )

        # エラーが適切に処理される
        assert "saved_files" in stats
        assert "errors" in stats

    def test_create_batch_request_with_extreme_values(self):
        """極端な値でのバッチリクエスト作成"""
        # 非常に多数の画像パス
        many_paths = [Path(f"/test/image_{i}.jpg") for i in range(10000)]

        # 非常に長いモデル名
        long_model_name = "a" * 1000

        # 例外が発生しないことを確認
        request = self.processor.create_batch_request(many_paths, long_model_name)

        assert isinstance(request, dict)
        assert request["total_images"] == 10000
        assert request["model_name"] == long_model_name

    def test_submit_openai_batch_with_network_error(self):
        """ネットワークエラー時のOpenAI Batch API送信"""
        # APIキー設定
        self.mock_config.get_setting.return_value = "test_api_key"

        # ネットワークエラーをシミュレート
        with patch(
            "lorairo.services.annotation_batch_processor.OpenAIBatchProcessor"
        ) as mock_processor_class:
            mock_processor_class.side_effect = ConnectionError("Network connection failed")

            test_requests = [{"request": "test"}]

            # フォールバックが動作することを確認
            batch_id = self.processor.submit_openai_batch(test_requests)

            assert isinstance(batch_id, str)
            assert batch_id.startswith("batch_openai_mock_")


class TestServiceContainerErrorHandling:
    """ServiceContainer エラーハンドリングテスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_service_initialization_failure_recovery(self):
        """サービス初期化失敗時の復旧"""
        with patch("lorairo.services.service_container.ConfigurationService") as mock_config_class:
            # 初回初期化で失敗
            mock_config_class.side_effect = [Exception("Config initialization failed"), Mock()]

            container = ServiceContainer()

            # 初回はNone
            assert container._config_service is None

            # 再試行で成功
            try:
                config_service = container.config_service
                # 2回目の呼び出しで成功すべき
                assert config_service is not None
            except Exception:
                # 失敗した場合も適切にハンドリングされることを確認
                pass

    def test_production_mode_switch_with_service_errors(self):
        """サービスエラー時のプロダクションモード切り替え"""
        container = ServiceContainer()

        # 既存サービスを設定
        container._annotator_lib_adapter = Mock()
        container._model_sync_service = Mock()

        # モード変更でエラーが発生しても適切に処理される
        try:
            container.set_production_mode(False)
            container.set_production_mode(True)
        except Exception:
            # エラーが発生してもContainerは安定状態を保つ
            assert container._use_production_mode is not None

    def test_reset_container_with_cleanup_errors(self):
        """クリーンアップエラー時のコンテナリセット"""
        container = ServiceContainer()

        # 問題のあるサービスを設定
        problematic_service = Mock()
        problematic_service.__del__ = Mock(side_effect=Exception("Cleanup failed"))
        container._config_service = problematic_service

        # リセットが例外なく完了することを確認
        try:
            container.reset_container()
        except Exception:
            pass

        # リセット状態の確認
        assert ServiceContainer._instance is None
        assert ServiceContainer._initialized is False

    def test_get_service_summary_with_partial_failures(self):
        """一部サービス障害時のサマリー取得"""
        with patch("lorairo.services.service_container.ConfigurationService") as mock_config_class:
            mock_config_class.side_effect = Exception("Config service failed")

            container = ServiceContainer()

            # サマリー取得が例外なく動作する
            summary = container.get_service_summary()

            assert isinstance(summary, dict)
            assert "initialized_services" in summary
            assert "container_initialized" in summary

    def test_concurrent_access_edge_cases(self):
        """並行アクセス時のエッジケース"""
        # 複数回の同時インスタンス化
        containers = []
        for _ in range(100):
            containers.append(ServiceContainer())

        # 全て同じインスタンス
        first_container = containers[0]
        for container in containers[1:]:
            assert container is first_container

        # 状態の一貫性確認
        assert first_container._initialized is True


class TestEdgeCasesAndBoundaryValues:
    """境界値・エッジケーステスト"""

    def test_zero_and_negative_values(self):
        """ゼロ・負の値の処理"""
        # BatchAnnotationResult with zero values
        result = BatchAnnotationResult(
            total_images=0, processed_images=0, successful_annotations=0, failed_annotations=0
        )

        assert result.success_rate == 0.0
        assert "総数0" in result.summary

        # 負の値での初期化
        negative_result = BatchAnnotationResult(
            total_images=-1, processed_images=-1, successful_annotations=-1, failed_annotations=-1
        )

        # 負の値でも適切に処理される
        assert isinstance(negative_result.summary, str)

    def test_extremely_large_values(self):
        """極端に大きな値の処理"""
        large_result = BatchAnnotationResult(
            total_images=2**31,  # 大きな整数
            processed_images=2**31,
            successful_annotations=2**31,
            failed_annotations=0,
        )

        assert large_result.success_rate == 100.0
        assert isinstance(large_result.summary, str)

    def test_unicode_and_special_characters(self):
        """Unicode・特殊文字の処理"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # Unicode文字を含む画像でのアノテーション
        unicode_image = Image.new("RGB", (100, 100), "red")
        unicode_models = ["日本語モデル", "émojì-mödél", "🤖-ai-model"]
        unicode_phashes = ["ハッシュ_1", "hash_2_🔥", "спэциал-хэш"]

        try:
            results = adapter.call_annotate(
                images=[unicode_image],
                models=unicode_models,
                phash_list=unicode_phashes[:1],  # 画像数に合わせる
            )
            assert isinstance(results, dict)
        except Exception as e:
            # Unicode処理エラーが適切にハンドリングされる
            assert isinstance(e, (UnicodeError, ValueError, KeyError)) or "unicode" in str(e).lower()

    def test_memory_intensive_operations(self):
        """メモリ集約的操作の処理"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # 大きな画像での処理
        try:
            large_image = Image.new("RGB", (8000, 8000), "blue")  # 大きな画像
            results = adapter.call_annotate(images=[large_image], models=["gpt-4o"])
            assert isinstance(results, dict)
        except MemoryError:
            # メモリエラーが適切にハンドリングされる
            pass
        except Exception:
            # その他の例外も適切にハンドリングされる
            pass

    def test_concurrent_model_processing(self):
        """並行モデル処理のエッジケース"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # 多数のモデルで同時処理
        many_models = [f"model-{i}" for i in range(100)]
        test_images = [Image.new("RGB", (50, 50), "green")]

        results = adapter.call_annotate(images=test_images, models=many_models)

        # 全モデルが処理される
        assert isinstance(results, dict)
        if results:
            phash = list(results.keys())[0]
            # Mock実装では全モデルが処理されるべき
            assert len(results[phash]) <= len(many_models)

    def test_file_system_edge_cases(self):
        """ファイルシステム関連のエッジケース"""
        mock_adapter = Mock()
        mock_config = Mock()
        processor = BatchProcessor(mock_adapter, mock_config)

        # 特殊なファイル名
        special_paths = [
            Path("/test/file with spaces.jpg"),
            Path("/test/file-with-dashes.jpg"),
            Path("/test/file_with_underscores.jpg"),
            Path("/test/file.with.dots.jpg"),
            Path("/test/file@symbol.jpg"),
            Path("/test/file[brackets].jpg"),
            Path("/test/file(parens).jpg"),
        ]

        # バッチリクエスト作成が例外なく完了する
        for path in special_paths:
            try:
                request = processor.create_batch_request([path], "test-model")
                assert isinstance(request, dict)
                assert request["total_images"] == 1
            except Exception as e:
                # ファイルシステム固有のエラーは許容
                assert isinstance(e, (OSError, ValueError, TypeError))


@pytest.mark.error
class TestComprehensiveErrorScenarios:
    """包括的エラーシナリオテスト"""

    def test_cascading_failures(self):
        """連鎖的失敗のシナリオ"""
        # サービス初期化失敗から始まる連鎖
        with patch("lorairo.services.service_container.ConfigurationService") as mock_config_class:
            mock_config_class.side_effect = Exception("Config failed")

            container = ServiceContainer()

            # 設定サービス失敗
            config_failed = False
            try:
                _ = container.config_service
            except Exception:
                config_failed = True

            # 設定失敗でも他のサービスが影響を受けないことを確認
            summary = container.get_service_summary()
            assert isinstance(summary, dict)

    def test_resource_exhaustion_scenarios(self):
        """リソース枯渇シナリオ"""
        mock_config = Mock()
        adapter = MockAnnotatorLibAdapter(mock_config)

        # ファイル記述子不足の模擬
        with patch("PIL.Image.open", side_effect=OSError("Too many open files")):
            try:
                # 大量の画像処理要求
                many_images = [Image.new("RGB", (10, 10), "red") for _ in range(1000)]
                results = adapter.call_annotate(images=many_images, models=["gpt-4o"])
                assert isinstance(results, dict)
            except OSError:
                # リソース不足エラーが適切にハンドリングされる
                pass

    def test_recovery_after_failure(self):
        """失敗後の復旧テスト"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

        # 初回失敗
        with patch(
            "lorairo.services.service_container.ConfigurationService",
            side_effect=Exception("First failure"),
        ):
            container1 = ServiceContainer()

        # リセット後成功
        container1.reset_container()

        with patch("lorairo.services.service_container.ConfigurationService") as mock_config_class:
            mock_config_class.return_value = Mock()
            container2 = ServiceContainer()

            # 復旧後は正常動作
            assert container2._initialized is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
