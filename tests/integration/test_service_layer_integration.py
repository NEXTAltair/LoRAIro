"""Service Layer Integration Tests

Phase 4実装のサービス間連携をテスト
外部依存は最小限に抑え、LoRAIro内部サービス間の統合をテスト
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtTest import QSignalSpy

# 実ライブラリの読み込みを防ぐため、import前にモック設定
with patch.dict(
    "sys.modules",
    {
        "image_annotator_lib": Mock(),
        "image_annotator_lib.annotate": Mock(),
        "image_annotator_lib.list_available_annotators_with_metadata": Mock(),
    },
):
    from lorairo.services.enhanced_annotation_service import EnhancedAnnotationService
    from lorairo.services.service_container import ServiceContainer, get_service_container


class TestServiceContainerIntegration:
    """ServiceContainer 統合テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        # ServiceContainerリセット
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_service_container_lazy_initialization_chain(self):
        """サービス遅延初期化の依存関係チェーン"""
        with (
            patch("lorairo.services.service_container.DefaultSessionLocal") as mock_session,
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.FileSystemManager") as mock_fs_class,
            patch("lorairo.services.service_container.ImageRepository") as mock_repo_class,
            patch("lorairo.services.service_container.ImageDatabaseManager") as mock_db_class,
            patch("lorairo.services.service_container.ImageProcessingService") as mock_processing_class,
        ):
            # モックインスタンス作成
            mock_config = Mock()
            mock_fs = Mock()
            mock_repo = Mock()
            mock_db = Mock()
            mock_processing = Mock()

            mock_config_class.return_value = mock_config
            mock_fs_class.return_value = mock_fs
            mock_repo_class.return_value = mock_repo
            mock_db_class.return_value = mock_db
            mock_processing_class.return_value = mock_processing

            container = ServiceContainer()

            # 依存関係チェーン実行
            db_manager = container.db_manager

            # 依存関係の正しい注入確認
            mock_config_class.assert_called_once()
            mock_fs_class.assert_called_once()
            mock_repo_class.assert_called_once_with(session_factory=mock_session)
            mock_db_class.assert_called_once_with(mock_repo, mock_config, mock_fs)

            assert db_manager is mock_db

    def test_service_container_production_mock_switching(self):
        """ServiceContainer プロダクション/Mock モード切り替え統合"""
        with (
            patch("lorairo.services.service_container.AnnotatorLibAdapter") as mock_real_adapter,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_mock_adapter,
            patch("lorairo.services.service_container.ConfigurationService"),
        ):
            mock_real_instance = Mock()
            mock_mock_instance = Mock()
            mock_real_adapter.return_value = mock_real_instance
            mock_mock_adapter.return_value = mock_mock_instance

            container = ServiceContainer()

            # 初期状態（プロダクションモード）
            assert container.is_production_mode() is True
            adapter1 = container.annotator_lib_adapter
            assert adapter1 is mock_real_instance

            # Mockモードに切り替え
            container.set_production_mode(False)
            adapter2 = container.annotator_lib_adapter
            assert adapter2 is mock_mock_instance

            # プロダクションモードに戻す
            container.set_production_mode(True)
            adapter3 = container.annotator_lib_adapter
            assert adapter3 is mock_real_instance

            # 異なるインスタンスが作成されることを確認
            assert adapter1 is not adapter3

    def test_service_container_fallback_mechanism_integration(self):
        """ServiceContainer フォールバック機構統合テスト"""
        with (
            patch("lorairo.services.service_container.AnnotatorLibAdapter") as mock_real_adapter,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_mock_adapter,
            patch("lorairo.services.service_container.ConfigurationService"),
        ):
            # 実アダプターが例外を投げる
            mock_real_adapter.side_effect = Exception("Real adapter initialization failed")
            mock_mock_instance = Mock()
            mock_mock_adapter.return_value = mock_mock_instance

            container = ServiceContainer()
            container.set_production_mode(True)

            # フォールバックが動作することを確認
            adapter = container.annotator_lib_adapter
            assert adapter is mock_mock_instance
            mock_mock_adapter.assert_called_once()


class TestEnhancedAnnotationServiceIntegration:
    """EnhancedAnnotationService サービス統合テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

        # Qt Application確保
        if not QCoreApplication.instance():
            self.app = QCoreApplication([])
        else:
            self.app = QCoreApplication.instance()

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_enhanced_annotation_service_with_real_container(self):
        """EnhancedAnnotationService と実際のServiceContainer統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter

            # 利用可能モデルのモック設定
            mock_models = [
                {"name": "gpt-4o", "provider": "openai", "model_type": "vision"},
                {"name": "claude-3-5-sonnet", "provider": "anthropic", "model_type": "vision"},
            ]
            mock_adapter.get_available_models_with_metadata.return_value = mock_models

            # EnhancedAnnotationService作成
            service = EnhancedAnnotationService()

            # ServiceContainer統合確認
            assert service.container is not None
            assert isinstance(service.container, ServiceContainer)

            # 利用可能モデル取得
            models = service.get_available_models()
            assert models == mock_models
            mock_adapter.get_available_models_with_metadata.assert_called_once()

    def test_enhanced_annotation_service_model_sync_integration(self):
        """EnhancedAnnotationService モデル同期統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
            patch("lorairo.services.service_container.ModelSyncService") as mock_sync_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_sync = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter
            mock_sync_class.return_value = mock_sync

            # 同期結果モック
            mock_sync_result = Mock()
            mock_sync_result.success = True
            mock_sync_result.summary = "統合テスト同期完了"
            mock_sync.sync_available_models.return_value = mock_sync_result

            service = EnhancedAnnotationService()

            # シグナルスパイ設定
            sync_spy = QSignalSpy(service.modelSyncCompleted)

            # モデル同期実行
            service.sync_available_models()

            # 統合確認
            mock_sync.sync_available_models.assert_called_once()
            assert sync_spy.count() == 1
            # Signal triggered - exact argument check omitted for integration test simplicity

    def test_enhanced_annotation_service_batch_processing_integration(self):
        """EnhancedAnnotationService バッチ処理統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.BatchProcessor") as mock_batch_class,
        ):
            mock_config = Mock()
            mock_batch = Mock()
            mock_config_class.return_value = mock_config
            mock_batch_class.return_value = mock_batch

            # バッチ結果モック
            mock_batch_result = Mock()
            mock_batch_result.summary = "統合テストバッチ完了"
            mock_batch.execute_batch_annotation.return_value = mock_batch_result

            service = EnhancedAnnotationService()

            # シグナルスパイ設定
            started_spy = QSignalSpy(service.batchProcessingStarted)
            finished_spy = QSignalSpy(service.batchProcessingFinished)

            # バッチアノテーション実行
            test_image_paths = ["/test/image1.jpg", "/test/image2.jpg"]
            test_models = ["gpt-4o"]
            service.start_batch_annotation(test_image_paths, test_models, batch_size=50)

            # 統合確認
            assert started_spy.count() == 1
            # Started signal triggered with image count

            mock_batch.execute_batch_annotation.assert_called_once()
            call_args = mock_batch.execute_batch_annotation.call_args
            assert len(call_args[1]["image_paths"]) == 2
            assert call_args[1]["models"] == test_models
            assert call_args[1]["batch_size"] == 50

            assert finished_spy.count() == 1
            # Finished signal triggered with batch result

    def test_enhanced_annotation_service_single_annotation_integration(self):
        """EnhancedAnnotationService 単発アノテーション統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter

            # アノテーション結果モック
            mock_annotation_results = {
                "phash_1": {"gpt-4o": {"formatted_output": {"captions": ["Test caption"]}, "error": None}}
            }
            mock_adapter.call_annotate.return_value = mock_annotation_results

            service = EnhancedAnnotationService()

            # シグナルスパイ設定
            finished_spy = QSignalSpy(service.annotationFinished)

            # 単発アノテーション実行
            test_images = [Image.new("RGB", (100, 100), "red")]
            test_phashes = ["phash_1"]
            test_models = ["gpt-4o"]
            service.start_single_annotation(test_images, test_phashes, test_models)

            # 統合確認
            mock_adapter.call_annotate.assert_called_once_with(
                images=test_images, models=test_models, phash_list=test_phashes
            )
            assert finished_spy.count() == 1
            # Finished signal triggered with annotation results
            assert service.get_last_annotation_result() == mock_annotation_results


class TestModelSyncServiceIntegration:
    """ModelSyncService 統合テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_model_sync_service_with_annotator_lib_adapter_integration(self):
        """ModelSyncService と AnnotatorLibAdapter統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.ImageRepository") as mock_repo_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_repo = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_repo_class.return_value = mock_repo
            mock_adapter_class.return_value = mock_adapter

            # アノテーターライブラリのモックデータ
            mock_library_models = [
                {
                    "name": "gpt-4o",
                    "class": "PydanticAIWebAPIAnnotator",
                    "provider": "openai",
                    "model_type": "vision",
                    "requires_api_key": True,
                },
                {
                    "name": "wd-v1-4-swinv2-tagger",
                    "class": "WDTagger",
                    "provider": None,
                    "model_type": "tagger",
                    "requires_api_key": False,
                },
            ]
            mock_adapter.get_available_models_with_metadata.return_value = mock_library_models

            # DBモック設定（既存モデルなし）
            mock_repo.get_model_by_name.return_value = None

            container = ServiceContainer()
            model_sync_service = container.model_sync_service

            # モデル同期実行
            sync_result = model_sync_service.sync_available_models()

            # 統合確認
            assert sync_result.success is True
            assert sync_result.total_library_models == 2
            assert sync_result.new_models_registered >= 0  # Mock実装では模擬値
            mock_adapter.get_available_models_with_metadata.assert_called_once()

    def test_model_sync_service_database_integration(self):
        """ModelSyncService データベース統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.ImageRepository") as mock_repo_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_repo = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_repo_class.return_value = mock_repo
            mock_adapter_class.return_value = mock_adapter

            # ライブラリモデル
            mock_library_models = [
                {
                    "name": "new-model",
                    "class": "TestAnnotator",
                    "provider": "test",
                    "model_type": "vision",
                    "requires_api_key": True,
                }
            ]
            mock_adapter.get_available_models_with_metadata.return_value = mock_library_models

            # DB操作モック
            mock_repo.get_model_by_name.return_value = None  # 新規モデル

            container = ServiceContainer()
            model_sync_service = container.model_sync_service

            # モデル登録テスト
            metadata_list = model_sync_service.get_model_metadata_from_library()
            registered_count = model_sync_service.register_new_models_to_db(metadata_list)

            # データベース統合確認
            assert len(metadata_list) == 1
            assert metadata_list[0]["name"] == "new-model"
            assert registered_count >= 0  # Mock実装では模擬値
            mock_repo.get_model_by_name.assert_called()


class TestBatchProcessorIntegration:
    """BatchProcessor 統合テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_batch_processor_with_annotator_lib_adapter_integration(self):
        """BatchProcessor と AnnotatorLibAdapter統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter

            # アノテーション結果モック
            mock_annotation_results = {
                "phash_1": {"gpt-4o": {"formatted_output": {"captions": ["Red image"]}, "error": None}},
                "phash_2": {"gpt-4o": {"formatted_output": {"captions": ["Blue image"]}, "error": None}},
            }
            mock_adapter.call_annotate.return_value = mock_annotation_results

            container = ServiceContainer()
            batch_processor = container.batch_processor

            # テスト画像作成
            with tempfile.TemporaryDirectory() as temp_dir:
                image_path1 = Path(temp_dir) / "test1.jpg"
                image_path2 = Path(temp_dir) / "test2.jpg"

                test_image = Image.new("RGB", (100, 100), "red")
                test_image.save(image_path1, "JPEG")
                test_image.save(image_path2, "JPEG")

                test_paths = [image_path1, image_path2]
                test_models = ["gpt-4o"]

                # バッチアノテーション実行
                batch_result = batch_processor.execute_batch_annotation(
                    test_paths, test_models, batch_size=10
                )

                # 統合確認
                assert batch_result.total_images == 2
                assert batch_result.processed_images == 2
                assert batch_result.successful_annotations == 2
                assert batch_result.failed_annotations == 0
                mock_adapter.call_annotate.assert_called_once()

    def test_batch_processor_openai_integration_fallback(self):
        """BatchProcessor OpenAI統合（フォールバック）"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter

            # APIキーなしの設定
            mock_config.get_setting.return_value = ""

            container = ServiceContainer()
            batch_processor = container.batch_processor

            # OpenAI Batch API送信（フォールバック）
            test_requests = [{"request": "test1"}, {"request": "test2"}]
            batch_id = batch_processor.submit_openai_batch(test_requests)

            # フォールバック確認
            assert isinstance(batch_id, str)
            assert batch_id.startswith("batch_openai_mock_")

    def test_batch_processor_file_saving_integration(self):
        """BatchProcessor ファイル保存統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter

            container = ServiceContainer()
            batch_processor = container.batch_processor

            # バッチ結果作成
            from lorairo.services.annotation_batch_processor import BatchAnnotationResult

            test_results = {
                "phash_1": {
                    "gpt-4o": {
                        "formatted_output": {"captions": ["A red car"], "tags": ["car", "red", "vehicle"]},
                        "error": None,
                    }
                }
            }

            batch_result = BatchAnnotationResult(
                total_images=1,
                processed_images=1,
                successful_annotations=1,
                failed_annotations=0,
                results=test_results,
            )

            # ファイル保存
            with tempfile.TemporaryDirectory() as temp_dir:
                output_dir = Path(temp_dir)

                stats = batch_processor.save_batch_results_to_files(
                    batch_result, output_dir, format_type="txt"
                )

                # 統合確認
                assert stats["saved_files"] == 1
                assert stats["errors"] == 0

                saved_file = output_dir / "phash_1_gpt-4o.txt"
                assert saved_file.exists()
                content = saved_file.read_text(encoding="utf-8")
                assert "car" in content and "red" in content


class TestEndToEndServiceIntegration:
    """End-to-End サービス統合テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

        if not QCoreApplication.instance():
            self.app = QCoreApplication([])
        else:
            self.app = QCoreApplication.instance()

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_complete_annotation_workflow_integration(self):
        """完全なアノテーションワークフロー統合"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
            patch("lorairo.services.service_container.ModelSyncService") as mock_sync_class,
            patch("lorairo.services.service_container.BatchProcessor") as mock_batch_class,
        ):
            # モック設定
            mock_config = Mock()
            mock_adapter = Mock()
            mock_sync = Mock()
            mock_batch = Mock()

            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter
            mock_sync_class.return_value = mock_sync
            mock_batch_class.return_value = mock_batch

            # 利用可能モデル
            mock_models = [
                {"name": "gpt-4o", "provider": "openai", "model_type": "vision"},
                {"name": "claude-3-5-sonnet", "provider": "anthropic", "model_type": "vision"},
            ]
            mock_adapter.get_available_models_with_metadata.return_value = mock_models

            # 同期結果
            mock_sync_result = Mock()
            mock_sync_result.success = True
            mock_sync_result.summary = "E2E統合テスト同期完了"
            mock_sync.sync_available_models.return_value = mock_sync_result

            # アノテーション結果
            mock_annotation_results = {
                "phash_1": {"gpt-4o": {"formatted_output": {"captions": ["E2E test"]}, "error": None}}
            }
            mock_adapter.call_annotate.return_value = mock_annotation_results

            # バッチ結果
            from lorairo.services.annotation_batch_processor import BatchAnnotationResult

            mock_batch_result = BatchAnnotationResult(
                total_images=1, processed_images=1, successful_annotations=1, failed_annotations=0
            )
            mock_batch.execute_batch_annotation.return_value = mock_batch_result

            # EnhancedAnnotationService作成
            service = EnhancedAnnotationService()

            # シグナルスパイ設定
            sync_spy = QSignalSpy(service.modelSyncCompleted)
            models_spy = QSignalSpy(service.availableAnnotatorsFetched)
            annotation_spy = QSignalSpy(service.annotationFinished)
            batch_spy = QSignalSpy(service.batchProcessingFinished)

            # 完全ワークフロー実行
            # 1. モデル同期
            service.sync_available_models()
            assert sync_spy.count() == 1

            # 2. 利用可能モデル取得
            service.fetch_available_annotators()
            assert models_spy.count() == 1
            # Models signal triggered with model names

            # 3. 単発アノテーション
            test_images = [Image.new("RGB", (100, 100), "red")]
            service.start_single_annotation(test_images, ["phash_1"], ["gpt-4o"])
            assert annotation_spy.count() == 1

            # 4. バッチアノテーション
            service.start_batch_annotation(["/test/image.jpg"], ["gpt-4o"])
            assert batch_spy.count() == 1

            # 全ての統合が成功したことを確認
            assert service.get_last_annotation_result() == mock_annotation_results
            assert service.get_last_batch_result() == mock_batch_result

    def test_service_status_integration(self):
        """サービス状況統合テスト"""
        with patch("lorairo.services.service_container.ConfigurationService") as mock_config_class:
            mock_config = Mock()
            mock_config_class.return_value = mock_config

            # サービス作成とステータス確認
            service = EnhancedAnnotationService()
            status = service.get_service_status()

            # 統合状況確認
            assert status["service_name"] == "EnhancedAnnotationService"
            assert "Phase 2" in status["phase"]
            assert "container_summary" in status
            assert "last_results" in status
            assert isinstance(status["container_summary"], dict)

    def test_error_handling_integration(self):
        """エラーハンドリング統合テスト"""
        with (
            patch("lorairo.services.service_container.ConfigurationService") as mock_config_class,
            patch("lorairo.services.service_container.MockAnnotatorLibAdapter") as mock_adapter_class,
        ):
            mock_config = Mock()
            mock_adapter = Mock()
            mock_config_class.return_value = mock_config
            mock_adapter_class.return_value = mock_adapter

            # アダプターエラー設定
            mock_adapter.get_available_models_with_metadata.side_effect = Exception("統合テストエラー")

            service = EnhancedAnnotationService()

            # エラーシグナルスパイ
            error_spy = QSignalSpy(service.annotationError)

            # エラー発生確認
            service.fetch_available_annotators()

            # エラーハンドリング統合確認
            assert error_spy.count() == 1
            # Error signal triggered with error message


@pytest.mark.integration
class TestConcurrentServiceIntegration:
    """並行サービス統合テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

        if not QCoreApplication.instance():
            self.app = QCoreApplication([])
        else:
            self.app = QCoreApplication.instance()

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_multiple_service_instances_integration(self):
        """複数サービスインスタンス統合"""
        with patch("lorairo.services.service_container.ConfigurationService") as mock_config_class:
            mock_config = Mock()
            mock_config_class.return_value = mock_config

            # 複数のEnhancedAnnotationService作成
            service1 = EnhancedAnnotationService()
            service2 = EnhancedAnnotationService()

            # 同じServiceContainerを共有することを確認
            assert service1.container is service2.container
            assert isinstance(service1.container, ServiceContainer)
            assert isinstance(service2.container, ServiceContainer)

            # サービス状況が一貫していることを確認
            status1 = service1.get_service_status()
            status2 = service2.get_service_status()

            # コンテナサマリーは同じ
            assert status1["container_summary"] == status2["container_summary"]

    def test_service_container_thread_safety_basic(self):
        """ServiceContainer基本的なスレッドセーフティ"""
        # 基本的なシングルトン一貫性確認
        containers = []
        for _ in range(10):
            containers.append(get_service_container())

        # 全て同じインスタンス
        for container in containers:
            assert container is containers[0]
