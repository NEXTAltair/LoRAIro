# tests/unit/gui/services/test_model_selection_service.py

from unittest.mock import Mock

import pytest

from lorairo.gui.services.model_selection_service import (
    ModelSelectionCriteria,
    ModelSelectionService,
)
from lorairo.services.model_registry_protocol import ModelInfo
from lorairo.database.schema import Model


class TestModel:
    """DB Model データクラスのテスト"""

    def test_model_creation(self):
        """Model の基本作成テスト"""
        model = Model(
            name="gpt-4o",
            provider="openai",
            api_model_id="gpt-4o-2024",
            requires_api_key=True,
            estimated_size_gb=None,
        )

        assert model.name == "gpt-4o"
        assert model.provider == "openai"
        assert model.api_model_id == "gpt-4o-2024"
        assert model.requires_api_key is True
        assert model.estimated_size_gb is None
        assert model.is_recommended is True  # gpt-4o is a recommended model

    def test_model_defaults(self):
        """Model のデフォルト値テスト"""
        model = Model(
            name="test-model",
            provider="test",
            api_model_id=None,
            requires_api_key=False,
            estimated_size_gb=1.5,
        )

        assert model.is_recommended is False  # test-model is not recommended


class TestModelSelectionService:
    """ModelSelectionService のユニットテスト（DB中心アーキテクチャ）"""

    @pytest.fixture
    def mock_db_repository(self):
        """モック ImageRepository"""
        mock = Mock()
        # Create mock Model objects with only valid database fields
        mock_models = []
        
        # Create Model objects with just the DB fields
        gpt_model = Model(
            name="gpt-4o",
            provider="openai",
            api_model_id="gpt-4o-2024",
            requires_api_key=True,
            estimated_size_gb=None,
        )
        
        claude_model = Model(
            name="claude-3-5-sonnet",
            provider="anthropic", 
            api_model_id="claude-3-5-sonnet-20241022",
            requires_api_key=True,
            estimated_size_gb=None,
        )
        
        wd_model = Model(
            name="wd-v1-4",
            provider="local",
            api_model_id=None,
            requires_api_key=False,
            estimated_size_gb=2.5,
        )
        
        clip_model = Model(
            name="clip-aesthetic",
            provider="local",
            api_model_id=None,
            requires_api_key=False,
            estimated_size_gb=1.2,
        )
        
        mock_models = [gpt_model, claude_model, wd_model, clip_model]
        mock.get_model_objects.return_value = mock_models
        return mock

    @pytest.fixture
    def service(self, mock_db_repository):
        """DB中心のModelSelectionService"""
        return ModelSelectionService(db_repository=mock_db_repository)

    @pytest.fixture
    def empty_service(self):
        """空のDBリポジトリを持つサービス"""
        mock_empty_repo = Mock()
        mock_empty_repo.get_model_objects.return_value = []
        return ModelSelectionService(db_repository=mock_empty_repo)

    def test_initialization(self, mock_db_repository):
        """DB中心アーキテクチャ初期化テスト"""
        service = ModelSelectionService(db_repository=mock_db_repository)
        assert service.db_repository == mock_db_repository
        assert service._all_models == []
        assert service._cached_models is None

    def test_create_class_method(self, mock_db_repository):
        """create()クラスメソッドテスト"""
        service = ModelSelectionService.create(db_repository=mock_db_repository)
        assert service.db_repository == mock_db_repository
        assert service._all_models == []

    def test_load_models_success(self, service, mock_db_repository):
        """モデル読み込み成功テスト（DB中心）"""
        models = service.load_models()

        # DBリポジトリが呼ばれたことを確認
        mock_db_repository.get_model_objects.assert_called_once()

        # 返されたモデル数を確認
        assert len(models) == 4

        # Modelオブジェクトが正しく取得されたことを確認
        gpt_model = models[0]
        assert isinstance(gpt_model, Model)
        assert gpt_model.name == "gpt-4o"
        assert gpt_model.provider == "openai"
        assert gpt_model.requires_api_key is True
        assert gpt_model.is_recommended is True  # gpt-4o は推奨モデル
        assert gpt_model.available is True  # discontinued_at is None

    def test_load_models_empty_repository(self, empty_service):
        """空のDBリポジトリでのモデル読み込みテスト"""
        models = empty_service.load_models()
        # 空のDBリポジトリは空リストを返す
        assert models == []

    def test_load_models_exception_handling(self, mock_db_repository):
        """モデル読み込み例外処理テスト"""
        # DBリポジトリが例外を投げるよう設定
        mock_db_repository.get_model_objects.side_effect = Exception("Test error")

        service = ModelSelectionService(db_repository=mock_db_repository)
        models = service.load_models()

        # 空のリストが返されることを確認
        assert models == []

    def test_get_all_models(self, service):
        """全モデル取得テスト"""
        # まずモデルを読み込み
        service.load_models()

        # 全モデルを取得
        all_models = service.get_all_models()

        assert len(all_models) == 4
        assert isinstance(all_models, list)
        # コピーが返されることを確認（元の配列と同じではない）
        assert all_models is not service._all_models

    def test_get_recommended_models(self, service):
        """推奨モデル取得テスト"""
        # まずモデルを読み込み
        service.load_models()

        # 推奨モデルを取得
        recommended = service.get_recommended_models()

        # 推奨モデルのみが返されることを確認
        assert len(recommended) > 0
        for model in recommended:
            assert model.is_recommended is True

        # gpt-4o, claude-3-5-sonnet, wd-v1-4, clip-aesthetic が推奨モデルに含まれることを確認
        recommended_names = [m.name for m in recommended]
        assert "gpt-4o" in recommended_names
        assert "claude-3-5-sonnet" in recommended_names
        assert "wd-v1-4" in recommended_names
        assert "clip-aesthetic" in recommended_names

    def test_filter_models_by_criteria(self, service):
        """ModelSelectionCriteriaによるフィルタリングテスト"""
        service.load_models()

        # OpenAIプロバイダーでフィルタ
        criteria = ModelSelectionCriteria(provider="openai")
        openai_models = service.filter_models(criteria)
        assert len(openai_models) == 1
        assert openai_models[0].name == "gpt-4o"

        # 機能でフィルタ（注：実際のcapabilitiesはmodel_typesから取得されるため、
        # このテストでは空のcapabilitiesに対するフィルタリング動作をテスト）
        criteria = ModelSelectionCriteria(capabilities=["tags"])
        tag_models = service.filter_models(criteria)
        # model_typesが設定されていないため、フィルタに引っかからない
        assert len(tag_models) == 0

    def test_filter_models_legacy_parameters(self, service):
        """後方互換性パラメータによるフィルタリングテスト"""
        service.load_models()

        # レガシーパラメータでのフィルタ
        openai_models = service.filter_models(provider="openai")
        assert len(openai_models) == 1
        assert openai_models[0].name == "gpt-4o"

        # ローカルプロバイダーでフィルタ
        local_models = service.filter_models(provider="local")
        assert len(local_models) == 2
        local_names = [m.name for m in local_models]
        assert "wd-v1-4" in local_names
        assert "clip-aesthetic" in local_names

    def test_filter_models_combined(self, service):
        """複合条件フィルタリングテスト"""
        service.load_models()

        # プロバイダーと機能の組み合わせ（capabilitiesは空のためフィルタが厳しく動作）
        criteria = ModelSelectionCriteria(provider="local", capabilities=["scores"])
        local_score_models = service.filter_models(criteria)
        # model_typesが設定されていないため、フィルタに引っかからない
        assert len(local_score_models) == 0

    def test_filter_models_all_provider(self, service):
        """「すべて」プロバイダーでのフィルタリングテスト"""
        service.load_models()

        # 「すべて」指定時は全モデルが返される
        all_models = service.filter_models(provider="すべて")
        assert len(all_models) == 4

    def test_group_models_by_provider(self, service):
        """プロバイダー別グループ化テスト"""
        service.load_models()
        all_models = service.get_all_models()

        grouped = service.group_models_by_provider(all_models)

        assert "openai" in grouped
        assert "anthropic" in grouped
        assert "local" in grouped

        assert len(grouped["openai"]) == 1
        assert len(grouped["anthropic"]) == 1
        assert len(grouped["local"]) == 2

    # create_model_tooltip, create_model_display_name, _is_recommended_model メソッドは
    # DB中心アーキテクチャでWidgetに移動されたため、テストを削除

    def test_refresh_models(self, service):
        """モデルリフレッシュテスト"""
        # 最初にモデルを読み込み
        models1 = service.load_models()
        assert len(models1) == 4
        assert service._cached_models is not None

        # リフレッシュ
        models2 = service.refresh_models()
        assert len(models2) == 4
        assert models2 == models1
