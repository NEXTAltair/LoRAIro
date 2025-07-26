"""ServiceContainer ユニットテスト

Phase 4実装の依存関係注入コンテナをテスト
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.services.service_container import (
    ServiceContainer,
    get_annotator_lib_adapter,
    get_batch_processor,
    get_config_service,
    get_model_sync_service,
    get_service_container,
)


class TestServiceContainerSingleton:
    """ServiceContainer シングルトンパターンテスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        # シングルトンインスタンスリセット
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        # シングルトンインスタンスリセット
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_singleton_instance_creation(self):
        """シングルトンインスタンス作成"""
        container1 = ServiceContainer()
        container2 = ServiceContainer()

        # 同一インスタンス確認
        assert container1 is container2
        assert ServiceContainer._instance is container1
        assert ServiceContainer._initialized is True

    def test_singleton_initialization_once(self):
        """シングルトン初期化は一度のみ実行"""
        container = ServiceContainer()
        original_config = container._config_service

        # 再初期化を試行
        container.__init__()

        # 状態が変わらないことを確認
        assert container._config_service is original_config
        assert ServiceContainer._initialized is True

    def test_get_service_container_function(self):
        """get_service_container()便利関数"""
        container1 = get_service_container()
        container2 = get_service_container()

        assert container1 is container2
        assert isinstance(container1, ServiceContainer)


class TestServiceContainerLazyInitialization:
    """ServiceContainer 遅延初期化テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    @patch("lorairo.services.service_container.ConfigurationService")
    def test_config_service_lazy_initialization(self, mock_config_class):
        """ConfigurationService遅延初期化"""
        mock_config_instance = Mock()
        mock_config_class.return_value = mock_config_instance

        container = ServiceContainer()

        # 初期状態では未初期化
        assert container._config_service is None

        # プロパティアクセスで初期化
        config_service = container.config_service

        assert config_service is mock_config_instance
        assert container._config_service is mock_config_instance
        mock_config_class.assert_called_once()

    @patch("lorairo.services.service_container.FileSystemManager")
    def test_file_system_manager_lazy_initialization(self, mock_fs_class):
        """FileSystemManager遅延初期化"""
        mock_fs_instance = Mock()
        mock_fs_class.return_value = mock_fs_instance

        container = ServiceContainer()

        # 初期状態では未初期化
        assert container._file_system_manager is None

        # プロパティアクセスで初期化
        fs_manager = container.file_system_manager

        assert fs_manager is mock_fs_instance
        assert container._file_system_manager is mock_fs_instance
        mock_fs_class.assert_called_once()

    @patch("lorairo.services.service_container.ImageRepository")
    @patch("lorairo.services.service_container.DefaultSessionLocal")
    def test_image_repository_lazy_initialization(self, mock_session, mock_repo_class):
        """ImageRepository遅延初期化"""
        mock_repo_instance = Mock()
        mock_repo_class.return_value = mock_repo_instance

        container = ServiceContainer()

        # 初期状態では未初期化
        assert container._image_repository is None

        # プロパティアクセスで初期化
        image_repo = container.image_repository

        assert image_repo is mock_repo_instance
        assert container._image_repository is mock_repo_instance
        mock_repo_class.assert_called_once_with(session_factory=mock_session)

    @patch("lorairo.services.service_container.ImageDatabaseManager")
    def test_db_manager_lazy_initialization(self, mock_db_class):
        """ImageDatabaseManager遅延初期化"""
        mock_db_instance = Mock()
        mock_db_class.return_value = mock_db_instance

        container = ServiceContainer()

        # 依存関係をモック化
        with (
            patch.object(container, "image_repository") as mock_image_repo,
            patch.object(container, "config_service") as mock_config,
            patch.object(container, "file_system_manager") as mock_fs,
        ):
            # 初期状態では未初期化
            assert container._db_manager is None

            # プロパティアクセスで初期化
            db_manager = container.db_manager

            assert db_manager is mock_db_instance
            assert container._db_manager is mock_db_instance
            mock_db_class.assert_called_once_with(mock_image_repo, mock_config, mock_fs)

    @patch("lorairo.services.service_container.ImageProcessingService")
    def test_image_processing_service_lazy_initialization(self, mock_service_class):
        """ImageProcessingService遅延初期化"""
        mock_service_instance = Mock()
        mock_service_class.return_value = mock_service_instance

        container = ServiceContainer()

        # 依存関係をモック化
        with (
            patch.object(container, "config_service") as mock_config,
            patch.object(container, "file_system_manager") as mock_fs,
        ):
            # 初期状態では未初期化
            assert container._image_processing_service is None

            # プロパティアクセスで初期化
            processing_service = container.image_processing_service

            assert processing_service is mock_service_instance
            assert container._image_processing_service is mock_service_instance
            mock_service_class.assert_called_once_with(mock_config, mock_fs)

    @patch("lorairo.services.service_container.ModelSyncService")
    def test_model_sync_service_lazy_initialization(self, mock_sync_class):
        """ModelSyncService遅延初期化"""
        mock_sync_instance = Mock()
        mock_sync_class.return_value = mock_sync_instance

        container = ServiceContainer()

        # 依存関係をモック化
        with (
            patch.object(container, "image_repository") as mock_repo,
            patch.object(container, "config_service") as mock_config,
            patch.object(container, "annotator_lib_adapter") as mock_adapter,
        ):
            # 初期状態では未初期化
            assert container._model_sync_service is None

            # プロパティアクセスで初期化
            sync_service = container.model_sync_service

            assert sync_service is mock_sync_instance
            assert container._model_sync_service is mock_sync_instance
            mock_sync_class.assert_called_once_with(mock_repo, mock_config, annotator_library=mock_adapter)


class TestServiceContainerProductionMode:
    """ServiceContainer プロダクション/Mockモード切り替えテスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    @patch("lorairo.services.service_container.AnnotatorLibAdapter")
    def test_annotator_lib_adapter_production_mode_success(self, mock_adapter_class):
        """AnnotatorLibAdapter プロダクションモード成功"""
        mock_adapter_instance = Mock()
        mock_adapter_class.return_value = mock_adapter_instance

        container = ServiceContainer()
        container.set_production_mode(True)

        # 依存関係をモック化
        with patch.object(container, "config_service") as mock_config:
            adapter = container.annotator_lib_adapter

            assert adapter is mock_adapter_instance
            assert container._annotator_lib_adapter is mock_adapter_instance
            mock_adapter_class.assert_called_once_with(mock_config)

    @patch("lorairo.services.service_container.AnnotatorLibAdapter")
    @patch("lorairo.services.service_container.MockAnnotatorLibAdapter")
    def test_annotator_lib_adapter_production_mode_fallback(self, mock_mock_class, mock_adapter_class):
        """AnnotatorLibAdapter プロダクションモード失敗時のフォールバック"""
        mock_mock_instance = Mock()
        mock_mock_class.return_value = mock_mock_instance
        mock_adapter_class.side_effect = Exception("Production adapter failed")

        container = ServiceContainer()
        container.set_production_mode(True)

        # 依存関係をモック化
        with patch.object(container, "config_service") as mock_config:
            adapter = container.annotator_lib_adapter

            # フォールバックでMockが使用される
            assert adapter is mock_mock_instance
            assert container._annotator_lib_adapter is mock_mock_instance
            mock_adapter_class.assert_called_once_with(mock_config)
            mock_mock_class.assert_called_once_with(mock_config)

    @patch("lorairo.services.service_container.MockAnnotatorLibAdapter")
    def test_annotator_lib_adapter_mock_mode(self, mock_mock_class):
        """AnnotatorLibAdapter Mockモード"""
        mock_mock_instance = Mock()
        mock_mock_class.return_value = mock_mock_instance

        container = ServiceContainer()
        container.set_production_mode(False)

        # 依存関係をモック化
        with patch.object(container, "config_service") as mock_config:
            adapter = container.annotator_lib_adapter

            assert adapter is mock_mock_instance
            assert container._annotator_lib_adapter is mock_mock_instance
            mock_mock_class.assert_called_once_with(mock_config)

    @patch("lorairo.services.service_container.BatchProcessor")
    def test_batch_processor_lazy_initialization(self, mock_batch_class):
        """BatchProcessor遅延初期化"""
        mock_batch_instance = Mock()
        mock_batch_class.return_value = mock_batch_instance

        container = ServiceContainer()

        # 依存関係をモック化
        with (
            patch.object(container, "annotator_lib_adapter") as mock_adapter,
            patch.object(container, "config_service") as mock_config,
        ):
            # 初期状態では未初期化
            assert container._batch_processor is None

            # プロパティアクセスで初期化
            batch_processor = container.batch_processor

            assert batch_processor is mock_batch_instance
            assert container._batch_processor is mock_batch_instance
            mock_batch_class.assert_called_once_with(mock_adapter, mock_config)


class TestServiceContainerModeManagement:
    """ServiceContainer モード管理テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_default_production_mode(self):
        """デフォルトでプロダクションモード"""
        container = ServiceContainer()
        assert container.is_production_mode() is True
        assert container._use_production_mode is True

    def test_set_production_mode_change(self):
        """プロダクションモード変更"""
        container = ServiceContainer()

        # 初期状態
        assert container.is_production_mode() is True

        # Mockモードに変更
        container.set_production_mode(False)
        assert container.is_production_mode() is False

        # プロダクションモードに戻す
        container.set_production_mode(True)
        assert container.is_production_mode() is True

    def test_mode_change_resets_related_services(self):
        """モード変更時の関連サービスリセット"""
        container = ServiceContainer()

        # サービスを初期化
        with patch.object(container, "config_service"):
            # Mock初期化
            mock_adapter = Mock()
            mock_model_sync = Mock()
            mock_batch_processor = Mock()

            container._annotator_lib_adapter = mock_adapter
            container._model_sync_service = mock_model_sync
            container._batch_processor = mock_batch_processor

            # モード変更実行
            container.set_production_mode(False)

            # 関連サービスがリセットされることを確認
            assert container._annotator_lib_adapter is None
            assert container._model_sync_service is None
            assert container._batch_processor is None

    def test_mode_change_same_mode_no_reset(self):
        """同じモードに変更時はリセットしない"""
        container = ServiceContainer()

        # サービス初期化
        mock_adapter = Mock()
        container._annotator_lib_adapter = mock_adapter

        # 同じモードに変更
        container.set_production_mode(True)

        # サービスがリセットされないことを確認
        assert container._annotator_lib_adapter is mock_adapter


class TestServiceContainerUtilities:
    """ServiceContainer ユーティリティ機能テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_get_service_summary_initial_state(self):
        """初期状態でのサービスサマリー取得"""
        container = ServiceContainer()
        summary = container.get_service_summary()

        assert isinstance(summary, dict)
        assert "initialized_services" in summary
        assert "container_initialized" in summary
        assert "phase" in summary

        # 初期状態では全サービスが未初期化
        services = summary["initialized_services"]
        assert all(not initialized for initialized in services.values())
        assert summary["container_initialized"] is True
        assert "Phase 4 (Production Integration)" in summary["phase"]

    def test_get_service_summary_with_initialized_services(self):
        """サービス初期化後のサマリー取得"""
        container = ServiceContainer()

        # いくつかのサービスを初期化
        with patch.object(container, "config_service") as mock_config:
            _ = mock_config  # サービス初期化

            summary = container.get_service_summary()
            services = summary["initialized_services"]

            # 初期化されたサービスの状態確認
            assert services["config_service"] is True
            # 他のサービスは未初期化
            assert services["file_system_manager"] is False

    def test_get_service_summary_mock_mode(self):
        """Mockモードでのサマリー"""
        container = ServiceContainer()
        container.set_production_mode(False)

        summary = container.get_service_summary()
        assert "Mock Implementation" in summary["phase"]

    def test_reset_container(self):
        """コンテナリセット機能"""
        container = ServiceContainer()

        # サービス初期化
        mock_config = Mock()
        container._config_service = mock_config

        # リセット実行
        container.reset_container()

        # 全サービスがクリアされることを確認
        assert container._config_service is None
        assert container._file_system_manager is None
        assert container._image_repository is None
        assert container._db_manager is None
        assert container._image_processing_service is None
        assert container._model_sync_service is None
        assert container._annotator_lib_adapter is None
        assert container._batch_processor is None

        # クラスレベルリセット確認
        assert ServiceContainer._instance is None
        assert ServiceContainer._initialized is False


class TestServiceContainerConvenienceFunctions:
    """ServiceContainer 便利関数テスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_get_config_service_function(self):
        """get_config_service()便利関数"""
        with patch.object(ServiceContainer, "config_service", new_callable=lambda: Mock()) as mock_prop:
            config_service = get_config_service()
            assert config_service is mock_prop

    def test_get_model_sync_service_function(self):
        """get_model_sync_service()便利関数"""
        with patch.object(ServiceContainer, "model_sync_service", new_callable=lambda: Mock()) as mock_prop:
            model_sync_service = get_model_sync_service()
            assert model_sync_service is mock_prop

    def test_get_annotator_lib_adapter_function(self):
        """get_annotator_lib_adapter()便利関数"""
        with patch.object(
            ServiceContainer, "annotator_lib_adapter", new_callable=lambda: Mock()
        ) as mock_prop:
            adapter = get_annotator_lib_adapter()
            assert adapter is mock_prop

    def test_get_batch_processor_function(self):
        """get_batch_processor()便利関数"""
        with patch.object(ServiceContainer, "batch_processor", new_callable=lambda: Mock()) as mock_prop:
            batch_processor = get_batch_processor()
            assert batch_processor is mock_prop


# 境界値・エッジケーステスト
class TestServiceContainerEdgeCases:
    """ServiceContainer 境界値・エッジケーステスト"""

    def setup_method(self):
        """各テスト前の初期化"""
        ServiceContainer._instance = None
        ServiceContainer._initialized = False

    def teardown_method(self):
        """各テスト後のクリーンアップ"""
        if ServiceContainer._instance:
            ServiceContainer._instance.reset_container()

    def test_multiple_reset_calls(self):
        """複数回のリセット呼び出し"""
        container = ServiceContainer()

        # 複数回リセット実行（例外が発生しないことを確認）
        container.reset_container()
        container.reset_container()
        container.reset_container()

        # 最終状態確認
        assert ServiceContainer._instance is None
        assert ServiceContainer._initialized is False

    def test_service_access_after_reset(self):
        """リセット後のサービスアクセス"""
        container = ServiceContainer()
        container.reset_container()

        # リセット後に新しいコンテナが作成される
        new_container = ServiceContainer()
        assert new_container is not None
        assert new_container._initialized is True

    def test_concurrent_singleton_creation(self):
        """並行シングルトン作成（基本テスト）"""
        container1 = ServiceContainer()
        container2 = ServiceContainer()
        container3 = ServiceContainer()

        # 全て同一インスタンス
        assert container1 is container2 is container3


@pytest.mark.integration
class TestServiceContainerIntegration:
    """ServiceContainer 統合テスト"""

    def test_full_service_integration(self):
        """完全なサービス統合テست"""
        # 実際の依存関係を使用した統合テスト
        # 本テストは統合テストファイルで実装
        pass
