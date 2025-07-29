"""ModelInfoManager テスト"""

from unittest.mock import Mock, patch

import pytest

from lorairo.database.db_repository import ImageRepository
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.model_info_manager import ModelFilterCriteria, ModelInfoManager
from lorairo.services.model_sync_service import ModelSyncService


class TestModelInfoManager:
    """ModelInfoManager単体テスト"""

    @pytest.fixture
    def mock_db_repository(self):
        """モックDBリポジトリ"""
        mock = Mock(spec=ImageRepository)
        mock._get_model_id = Mock(return_value=None)
        return mock

    @pytest.fixture
    def mock_config_service(self):
        """モック設定サービス"""
        mock = Mock(spec=ConfigurationService)
        mock.get_config = Mock(
            return_value={
                "api": {"openai_key": "test_key", "claude_key": "", "google_key": "another_test_key"}
            }
        )
        return mock

    @pytest.fixture
    def mock_model_sync_service(self):
        """モックModelSyncService"""
        mock = Mock(spec=ModelSyncService)

        # テスト用モデルメタデータ
        test_models = [
            {
                "name": "gpt-4o",
                "provider": "openai",
                "model_type": "multimodal",
                "requires_api_key": True,
                "api_model_id": "gpt-4o",
                "estimated_size_gb": None,
                "discontinued_at": None,
            },
            {
                "name": "wd-v1-4-tagger",
                "provider": None,
                "model_type": "tagger",
                "requires_api_key": False,
                "api_model_id": None,
                "estimated_size_gb": 1.2,
                "discontinued_at": None,
            },
            {
                "name": "claude-3-5-sonnet",
                "provider": "anthropic",
                "model_type": "multimodal",
                "requires_api_key": True,
                "api_model_id": "claude-3-5-sonnet-20241022",
                "estimated_size_gb": None,
                "discontinued_at": None,
            },
        ]

        mock.get_model_metadata_from_library = Mock(return_value=test_models)
        return mock

    @pytest.fixture
    def model_info_manager(self, mock_db_repository, mock_config_service, mock_model_sync_service):
        """ModelInfoManager インスタンス"""
        return ModelInfoManager(
            db_repository=mock_db_repository,
            config_service=mock_config_service,
            model_sync_service=mock_model_sync_service,
        )

    def test_initialization(self, model_info_manager):
        """初期化テスト"""
        assert model_info_manager.db_repository is not None
        assert model_info_manager.config_service is not None
        assert model_info_manager.model_sync_service is not None

    def test_get_available_models_basic(self, model_info_manager):
        """基本的な利用可能モデル取得テスト"""
        models = model_info_manager.get_available_models()

        # 基本検証
        assert isinstance(models, list)
        assert len(models) >= 2  # テスト用モデルが含まれている

        # ModelInfo構造の検証
        for model in models:
            assert isinstance(model, dict)
            assert "name" in model
            assert "provider" in model
            assert "model_type" in model
            assert "requires_api_key" in model
            assert "available" in model

    def test_model_availability_check(self, model_info_manager):
        """モデル利用可能性チェックテスト"""
        models = model_info_manager.get_available_models()

        # APIキー設定されたプロバイダーのモデルは利用可能
        openai_models = [m for m in models if m["provider"] == "openai"]
        assert len(openai_models) > 0
        assert all(m["available"] for m in openai_models)

        # APIキー未設定のプロバイダーのモデルは利用不可
        anthropic_models = [m for m in models if m["provider"] == "anthropic"]
        if anthropic_models:
            assert all(not m["available"] for m in anthropic_models)

        # ローカルモデル（APIキー不要）は利用可能
        local_models = [m for m in models if not m["requires_api_key"]]
        assert len(local_models) > 0
        assert all(m["available"] for m in local_models)

    def test_get_models_by_type(self, model_info_manager):
        """タイプ別モデル取得テスト"""
        # Vision モデル取得
        vision_models = model_info_manager.get_models_by_type("multimodal")
        assert all(m["model_type"] == "multimodal" for m in vision_models)

        # Tagger モデル取得
        tagger_models = model_info_manager.get_models_by_type("tagger")
        assert all(m["model_type"] == "tagger" for m in tagger_models)

    def test_filter_criteria_application(self, model_info_manager):
        """フィルタリング条件適用テスト"""
        # プロバイダーフィルター
        openai_filter = ModelFilterCriteria(providers=["openai"])
        openai_models = model_info_manager.get_available_models(openai_filter)
        assert all(m["provider"] == "openai" for m in openai_models)

        # モデルタイプフィルター
        vision_filter = ModelFilterCriteria(model_types=["multimodal"])
        vision_models = model_info_manager.get_available_models(vision_filter)
        assert all(m["model_type"] == "multimodal" for m in vision_models)

        # APIキー要件フィルター
        api_key_filter = ModelFilterCriteria(requires_api_key=True)
        api_models = model_info_manager.get_available_models(api_key_filter)
        assert all(m["requires_api_key"] for m in api_models)

    def test_get_providers_list(self, model_info_manager):
        """プロバイダー一覧取得テスト"""
        providers = model_info_manager.get_providers_list()

        assert isinstance(providers, list)
        assert "openai" in providers
        assert "local" in providers  # None -> "local" に変換される
        assert providers == sorted(providers)  # ソート済み

    def test_get_model_types_list(self, model_info_manager):
        """モデルタイプ一覧取得テスト"""
        model_types = model_info_manager.get_model_types_list()

        assert isinstance(model_types, list)
        assert "multimodal" in model_types
        assert "tagger" in model_types
        assert model_types == sorted(model_types)  # ソート済み

    def test_check_model_availability(self, model_info_manager):
        """個別モデル利用可能性チェックテスト"""
        # 利用可能モデル
        assert model_info_manager.check_model_availability("gpt-4o") is True
        assert model_info_manager.check_model_availability("wd-v1-4-tagger") is True

        # 利用不可モデル（APIキー未設定）
        assert model_info_manager.check_model_availability("claude-3-5-sonnet") is False

        # 存在しないモデル
        assert model_info_manager.check_model_availability("nonexistent-model") is False

    def test_get_model_summary_stats(self, model_info_manager):
        """モデル統計情報取得テスト"""
        stats = model_info_manager.get_model_summary_stats()

        # 基本統計
        assert "total_models" in stats
        assert "available_models" in stats
        assert "providers" in stats
        assert "model_types" in stats
        assert "api_key_required" in stats
        assert "local_models" in stats

        # 数値検証
        assert stats["total_models"] >= 2
        assert stats["available_models"] <= stats["total_models"]
        assert isinstance(stats["providers"], dict)
        assert isinstance(stats["model_types"], dict)

    def test_error_handling(self, mock_db_repository, mock_config_service):
        """エラーハンドリングテスト"""
        # ModelSyncServiceでエラーが発生する場合
        mock_model_sync_service = Mock()
        mock_model_sync_service.get_model_metadata_from_library.side_effect = Exception("API Error")

        manager = ModelInfoManager(
            db_repository=mock_db_repository,
            config_service=mock_config_service,
            model_sync_service=mock_model_sync_service,
        )

        # エラーが発生しても空リストを返す
        models = manager.get_available_models()
        assert models == []

    def test_convert_to_model_info_list(self, model_info_manager):
        """モデル情報変換テスト"""
        # 直接変換メソッドをテスト
        test_library_models = [
            {
                "name": "test-model",
                "provider": "test-provider",
                "model_type": "multimodal",
                "requires_api_key": False,
                "api_model_id": "test-id",
                "estimated_size_gb": 2.5,
                "discontinued_at": None,
            }
        ]

        model_infos = model_info_manager._convert_to_model_info_list(test_library_models)

        assert len(model_infos) == 1
        model_info = model_infos[0]

        assert model_info["name"] == "test-model"
        assert model_info["provider"] == "test-provider"
        assert model_info["model_type"] == "multimodal"
        assert model_info["requires_api_key"] is False
        assert model_info["api_model_id"] == "test-id"
        assert model_info["estimated_size_gb"] == 2.5
        assert model_info["available"] is True  # APIキー不要なので利用可能


class TestModelFilterCriteria:
    """ModelFilterCriteria テスト"""

    def test_model_filter_criteria_initialization(self):
        """ModelFilterCriteria初期化テスト"""
        # デフォルト値
        criteria = ModelFilterCriteria()
        assert criteria.model_types is None
        assert criteria.providers is None
        assert criteria.requires_api_key is None
        assert criteria.only_available is True

        # カスタム値
        custom_criteria = ModelFilterCriteria(
            model_types=["multimodal", "tagger"],
            providers=["openai"],
            requires_api_key=True,
            only_available=False,
        )
        assert custom_criteria.model_types == ["multimodal", "tagger"]
        assert custom_criteria.providers == ["openai"]
        assert custom_criteria.requires_api_key is True
        assert custom_criteria.only_available is False

    def test_filter_application_logic(self):
        """フィルター適用ロジックテスト"""
        # 複数条件組み合わせ
        criteria = ModelFilterCriteria(
            model_types=["multimodal"],
            providers=["openai", "google"],
            requires_api_key=True,
            only_available=True,
        )

        # 設定値確認
        assert "multimodal" in criteria.model_types
        assert "openai" in criteria.providers
        assert criteria.requires_api_key is True
        assert criteria.only_available is True


class TestModelInfoManagerIntegration:
    """ModelInfoManager統合テスト"""

    def test_integration_with_real_config_service(self, mock_db_repository):
        """実際のConfigurationServiceとの統合テスト"""
        # 実際の設定サービスインスタンス作成をモック
        with patch("src.lorairo.services.model_info_manager.ModelSyncService") as mock_sync_service_class:
            mock_sync_instance = Mock()
            mock_sync_instance.get_model_metadata_from_library.return_value = []
            mock_sync_service_class.return_value = mock_sync_instance

            # 実際の設定サービス（モック）
            config_service = Mock()
            config_service.get_config.return_value = {"api": {}}

            manager = ModelInfoManager(db_repository=mock_db_repository, config_service=config_service)

            # ModelSyncServiceが正しく初期化される
            assert manager.model_sync_service is mock_sync_instance
            mock_sync_service_class.assert_called_once()

    def test_dependency_injection_patterns(self, mock_db_repository, mock_config_service):
        """依存性注入パターンテスト"""
        # 外部からModelSyncServiceを注入
        external_sync_service = Mock()

        manager = ModelInfoManager(
            db_repository=mock_db_repository,
            config_service=mock_config_service,
            model_sync_service=external_sync_service,
        )

        # 注入されたサービスが使用される
        assert manager.model_sync_service is external_sync_service

        # AnnotatorLibraryも注入可能
        external_annotator_lib = Mock()

        manager2 = ModelInfoManager(
            db_repository=mock_db_repository,
            config_service=mock_config_service,
            annotator_library=external_annotator_lib,
        )

        # ModelSyncServiceに渡される
        assert manager2.model_sync_service is not None
