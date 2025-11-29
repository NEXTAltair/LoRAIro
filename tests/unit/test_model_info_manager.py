"""ModelInfoManager ユニットテスト

アノテーション用モデル情報管理サービスのテスト
"""

from unittest.mock import Mock

import pytest

from lorairo.services.model_info_manager import ModelFilterCriteria, ModelInfo, ModelInfoManager
from lorairo.services.model_sync_service import MockAnnotatorLibrary, ModelSyncService


class TestModelInfoManager:
    """ModelInfoManager基本機能テスト"""

    @pytest.fixture
    def model_info_manager(self, temp_db_repository, mock_config_service):
        """ModelInfoManagerインスタンス"""
        return ModelInfoManager(
            db_repository=temp_db_repository,
            config_service=mock_config_service,
        )

    def test_initialization(self, model_info_manager):
        """初期化テスト"""
        assert model_info_manager.db_repository is not None
        assert model_info_manager.config_service is not None
        assert model_info_manager.model_sync_service is not None

    def test_get_available_models(self, model_info_manager):
        """利用可能なモデル一覧取得"""
        models = model_info_manager.get_available_models()

        assert isinstance(models, list)
        # MockAnnotatorLibraryのモデルが取得される
        assert len(models) > 0

        # 各モデルの構造確認
        for model in models:
            assert "id" in model
            assert "name" in model
            assert "provider" in model
            assert "model_type" in model
            assert "requires_api_key" in model
            assert "available" in model

    def test_get_available_models_with_filter(self, model_info_manager):
        """フィルタリング付きモデル一覧取得"""
        filter_criteria = ModelFilterCriteria(model_types=["vision"], only_available=True)
        models = model_info_manager.get_available_models(filter_criteria)

        assert isinstance(models, list)
        # visionタイプのみが返される
        for model in models:
            assert model["model_type"] == "vision"

    def test_get_models_by_type(self, model_info_manager):
        """指定タイプのモデル一覧取得"""
        vision_models = model_info_manager.get_models_by_type("vision")

        assert isinstance(vision_models, list)
        for model in vision_models:
            assert model["model_type"] == "vision"

    def test_get_providers_list(self, model_info_manager):
        """プロバイダー一覧取得"""
        providers = model_info_manager.get_providers_list()

        assert isinstance(providers, list)
        assert len(providers) > 0
        # MockAnnotatorLibraryのプロバイダーが含まれる
        assert "openai" in providers or "local" in providers

    def test_get_model_types_list(self, model_info_manager):
        """モデルタイプ一覧取得"""
        model_types = model_info_manager.get_model_types_list()

        assert isinstance(model_types, list)
        assert len(model_types) > 0
        # アノテーション専用タイプのみが返される
        for model_type in model_types:
            assert model_type in ["vision", "score", "tagger"]

    def test_check_model_availability(self, model_info_manager):
        """モデル利用可能性チェック"""
        # MockAnnotatorLibraryの既知のモデル
        is_available = model_info_manager.check_model_availability("wd-v1-4-swinv2-tagger")

        # ローカルモデルなのでAPIキー不要で利用可能
        assert is_available is True

    def test_check_model_availability_nonexistent(self, model_info_manager):
        """存在しないモデルの利用可能性チェック"""
        is_available = model_info_manager.check_model_availability("nonexistent-model")

        assert is_available is False

    def test_get_model_summary_stats(self, model_info_manager):
        """モデル統計情報取得"""
        stats = model_info_manager.get_model_summary_stats()

        assert isinstance(stats, dict)
        assert "total_models" in stats
        assert "available_models" in stats
        assert "providers" in stats
        assert "model_types" in stats
        assert "api_key_required" in stats
        assert "local_models" in stats

        # 統計値が妥当であることを確認
        assert stats["total_models"] >= 0
        assert stats["available_models"] >= 0
        assert stats["available_models"] <= stats["total_models"]

    def test_get_db_model_id_integration(self, model_info_manager, temp_db_repository):
        """_get_db_model_id()のget_model_by_name()統合テスト"""
        # 事前にモデルを登録
        model_id = temp_db_repository.insert_model(
            name="test-integration-model",
            provider="test",
            model_types=["captioner"],
        )

        # ModelInfoManagerの内部メソッドを間接的にテスト
        result_id = model_info_manager._get_db_model_id("test-integration-model")

        assert result_id is not None
        assert result_id == model_id

    def test_get_db_model_id_not_found(self, model_info_manager):
        """_get_db_model_id()でモデルが見つからない場合"""
        result_id = model_info_manager._get_db_model_id("nonexistent-model")

        assert result_id is None


class TestModelFilterCriteria:
    """ModelFilterCriteria フィルタリングテスト"""

    @pytest.fixture
    def model_info_manager(self, temp_db_repository, mock_config_service):
        """ModelInfoManagerインスタンス"""
        return ModelInfoManager(
            db_repository=temp_db_repository,
            config_service=mock_config_service,
        )

    def test_filter_by_model_types(self, model_info_manager):
        """モデルタイプでフィルタリング"""
        filter_criteria = ModelFilterCriteria(model_types=["tagger", "score"], only_available=False)
        models = model_info_manager.get_available_models(filter_criteria)

        for model in models:
            assert model["model_type"] in ["tagger", "score"]

    def test_filter_by_requires_api_key(self, model_info_manager):
        """APIキー要件でフィルタリング"""
        filter_criteria = ModelFilterCriteria(requires_api_key=False, only_available=False)
        models = model_info_manager.get_available_models(filter_criteria)

        for model in models:
            assert model["requires_api_key"] is False

    def test_filter_only_available(self, model_info_manager):
        """利用可能なモデルのみフィルタリング"""
        filter_criteria = ModelFilterCriteria(only_available=True)
        models = model_info_manager.get_available_models(filter_criteria)

        for model in models:
            assert model["available"] is True
