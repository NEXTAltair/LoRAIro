# tests/unit/gui/services/test_model_selection_service.py

from unittest.mock import Mock

import pytest

from lorairo.gui.services.model_selection_service import (
    ModelInfo,
    ModelSelectionCriteria,
    ModelSelectionService,
)
from lorairo.services.model_registry_protocol import ModelInfo as RegistryModelInfo


class TestModelInfo:
    """ModelInfo データクラスのテスト"""

    def test_model_info_creation(self):
        """ModelInfo の基本作成テスト"""
        model = ModelInfo(
            name="gpt-4o",
            provider="openai",
            capabilities=["caption", "tags"],
            api_model_id="gpt-4o-2024",
            requires_api_key=True,
            estimated_size_gb=None,
            is_recommended=True,
        )

        assert model.name == "gpt-4o"
        assert model.provider == "openai"
        assert model.capabilities == ["caption", "tags"]
        assert model.api_model_id == "gpt-4o-2024"
        assert model.requires_api_key is True
        assert model.estimated_size_gb is None
        assert model.is_recommended is True

    def test_model_info_defaults(self):
        """ModelInfo のデフォルト値テスト"""
        model = ModelInfo(
            name="test-model",
            provider="test",
            capabilities=["caption"],
            api_model_id=None,
            requires_api_key=False,
            estimated_size_gb=1.5,
        )

        assert model.is_recommended is False  # デフォルト値


class TestModelSelectionService:
    """ModelSelectionService のユニットテスト（現代化版）"""

    @pytest.fixture
    def mock_model_registry(self):
        """モック ModelRegistryServiceProtocol"""
        mock = Mock()
        mock.get_available_models.return_value = [
            RegistryModelInfo(
                name="gpt-4o",
                provider="openai",
                capabilities=["caption", "tags"],
                api_model_id="gpt-4o-2024",
                requires_api_key=True,
                estimated_size_gb=None,
            ),
            RegistryModelInfo(
                name="claude-3-5-sonnet",
                provider="anthropic",
                capabilities=["caption", "tags"],
                api_model_id="claude-3-5-sonnet-20241022",
                requires_api_key=True,
                estimated_size_gb=None,
            ),
            RegistryModelInfo(
                name="wd-v1-4",
                provider="local",
                capabilities=["tags"],
                api_model_id=None,
                requires_api_key=False,
                estimated_size_gb=2.5,
            ),
            RegistryModelInfo(
                name="clip-aesthetic",
                provider="local",
                capabilities=["scores"],
                api_model_id=None,
                requires_api_key=False,
                estimated_size_gb=1.2,
            ),
        ]
        return mock

    @pytest.fixture
    def service(self, mock_model_registry):
        """現代化されたModelSelectionService"""
        return ModelSelectionService(model_registry=mock_model_registry)

    @pytest.fixture
    def empty_service(self):
        """ModelRegistryなしのサービス（NullModelRegistry使用）"""
        return ModelSelectionService()

    def test_initialization(self, mock_model_registry):
        """現代化された初期化テスト"""
        service = ModelSelectionService(model_registry=mock_model_registry)
        assert service.model_registry == mock_model_registry
        assert service._all_models == []
        assert service._cached_models is None

    def test_initialization_without_registry(self):
        """ModelRegistryなし初期化テスト"""
        service = ModelSelectionService()
        # NullModelRegistryが設定されることを確認
        assert service.model_registry is not None
        assert service._all_models == []

    def test_create_class_method(self, mock_model_registry):
        """create()クラスメソッドテスト"""
        service = ModelSelectionService.create(model_registry=mock_model_registry)
        assert service.model_registry == mock_model_registry
        assert service._all_models == []

    def test_load_models_success(self, service, mock_model_registry):
        """モデル読み込み成功テスト（Protocol-based）"""
        models = service.load_models()

        # ModelRegistryが呼ばれたことを確認
        mock_model_registry.get_available_models.assert_called_once()

        # 返されたモデル数を確認
        assert len(models) == 4

        # ModelInfoオブジェクトが正しく作成されたことを確認
        gpt_model = models[0]
        assert isinstance(gpt_model, ModelInfo)
        assert gpt_model.name == "gpt-4o"
        assert gpt_model.provider == "openai"
        assert gpt_model.capabilities == ["caption", "tags"]
        assert gpt_model.requires_api_key is True
        assert gpt_model.is_recommended is True  # gpt-4o は推奨モデル

    def test_load_models_empty_registry(self, empty_service):
        """空のModelRegistryでのモデル読み込みテスト"""
        models = empty_service.load_models()
        # NullModelRegistryは空リストを返す
        assert models == []

    def test_load_models_exception_handling(self, mock_model_registry):
        """モデル読み込み例外処理テスト"""
        # ModelRegistryが例外を投げるよう設定
        mock_model_registry.get_available_models.side_effect = Exception("Test error")

        service = ModelSelectionService(model_registry=mock_model_registry)
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

        # 機能でフィルタ
        criteria = ModelSelectionCriteria(capabilities=["tags"])
        tag_models = service.filter_models(criteria)
        tag_names = [m.name for m in tag_models]
        assert "gpt-4o" in tag_names
        assert "claude-3-5-sonnet" in tag_names
        assert "wd-v1-4" in tag_names

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

        # プロバイダーと機能の組み合わせ
        criteria = ModelSelectionCriteria(provider="local", capabilities=["scores"])
        local_score_models = service.filter_models(criteria)
        assert len(local_score_models) == 1
        assert local_score_models[0].name == "clip-aesthetic"

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

    def test_create_model_tooltip(self, service):
        """モデルツールチップ作成テスト"""
        service.load_models()
        models = service.get_all_models()

        gpt_model = next(m for m in models if m.name == "gpt-4o")
        tooltip = service.create_model_tooltip(gpt_model)

        assert "プロバイダー: openai" in tooltip
        assert "機能: caption, tags" in tooltip
        assert "API ID: gpt-4o-2024" in tooltip
        assert "APIキー必要: Yes" in tooltip

    def test_create_model_display_name(self, service):
        """モデル表示名作成テスト"""
        service.load_models()
        models = service.get_all_models()

        # API必要モデル
        gpt_model = next(m for m in models if m.name == "gpt-4o")
        display_name = service.create_model_display_name(gpt_model)
        assert display_name == "gpt-4o (API)"

        # ローカルモデル（サイズ情報あり）
        wd_model = next(m for m in models if m.name == "wd-v1-4")
        display_name = service.create_model_display_name(wd_model)
        assert display_name == "wd-v1-4 (2.5GB)"

    def test_is_recommended_model(self, service):
        """推奨モデル判定テスト"""
        # 推奨キャプションモデル
        assert service._is_recommended_model("gpt-4o") is True
        assert service._is_recommended_model("claude-3-5-sonnet") is True
        assert service._is_recommended_model("gemini-pro") is True

        # 推奨タグモデル
        assert service._is_recommended_model("wd-v1-4") is True
        assert service._is_recommended_model("wd-tagger") is True
        assert service._is_recommended_model("deepdanbooru") is True

        # 推奨スコアモデル
        assert service._is_recommended_model("clip-aesthetic") is True
        assert service._is_recommended_model("musiq") is True

        # 非推奨モデル
        assert service._is_recommended_model("unknown-model") is False
        assert service._is_recommended_model("test-model") is False

    def test_case_insensitive_recommendation(self, service):
        """大文字小文字を区別しない推奨判定テスト"""
        assert service._is_recommended_model("GPT-4O") is True
        assert service._is_recommended_model("Claude-3-5-Sonnet") is True
        assert service._is_recommended_model("WD-V1-4") is True

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
