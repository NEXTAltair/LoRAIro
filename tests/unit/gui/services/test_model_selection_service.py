# tests/unit/gui/services/test_model_selection_service.py

from unittest.mock import Mock, patch

import pytest

from lorairo.gui.services.model_selection_service import ModelInfo, ModelSelectionService


class TestModelInfo:
    """ModelInfo データクラスのテスト"""

    def test_model_info_creation(self):
        """ModelInfo の基本作成テスト"""
        model = ModelInfo(
            name="gpt-4o",
            provider="openai",
            capabilities=["caption", "tag"],
            api_model_id="gpt-4o-2024",
            requires_api_key=True,
            estimated_size_gb=None,
            is_recommended=True,
        )

        assert model.name == "gpt-4o"
        assert model.provider == "openai"
        assert model.capabilities == ["caption", "tag"]
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
    """ModelSelectionService のユニットテスト"""

    @pytest.fixture
    def mock_annotator_adapter(self):
        """モック AnnotatorLibAdapter"""
        mock = Mock()
        mock.get_available_models_with_metadata.return_value = [
            {
                "name": "gpt-4o",
                "provider": "openai",
                "model_type": "multimodal",
                "api_model_id": "gpt-4o-2024",
                "requires_api_key": True,
                "estimated_size_gb": None,
            },
            {
                "name": "claude-3-5-sonnet",
                "provider": "anthropic",
                "model_type": "multimodal",
                "api_model_id": "claude-3-5-sonnet-20241022",
                "requires_api_key": True,
                "estimated_size_gb": None,
            },
            {
                "name": "wd-v1-4",
                "provider": "local",
                "model_type": "tag",
                "api_model_id": None,
                "requires_api_key": False,
                "estimated_size_gb": 2.5,
            },
            {
                "name": "clip-aesthetic",
                "provider": "local",
                "model_type": "score",
                "api_model_id": None,
                "requires_api_key": False,
                "estimated_size_gb": 1.2,
            },
        ]
        return mock

    @pytest.fixture
    def service_with_adapter(self, mock_annotator_adapter):
        """AnnotatorLibAdapter付きのサービス"""
        return ModelSelectionService(mock_annotator_adapter)

    @pytest.fixture
    def service_without_adapter(self):
        """AnnotatorLibAdapterなしのサービス"""
        return ModelSelectionService()

    def test_initialization_with_adapter(self, mock_annotator_adapter):
        """アダプター付き初期化テスト"""
        # Windows環境での安全な初期化
        try:
            service = ModelSelectionService(mock_annotator_adapter)
            assert service.annotator_adapter == mock_annotator_adapter
            assert service._all_models == []
        except Exception as e:
            # Windows環境でのAccess Violation詳細情報
            pytest.fail(f"ModelSelectionService initialization failed: {e}")

    def test_initialization_without_adapter(self):
        """アダプターなし初期化テスト"""
        service = ModelSelectionService()
        assert service.annotator_adapter is None
        assert service._all_models == []

    def test_load_models_success(self, service_with_adapter, mock_annotator_adapter):
        """モデル読み込み成功テスト"""
        models = service_with_adapter.load_models()

        # AnnotatorLibAdapterが呼ばれたことを確認
        mock_annotator_adapter.get_available_models_with_metadata.assert_called_once()

        # 返されたモデル数を確認
        assert len(models) == 4

        # ModelInfoオブジェクトが正しく作成されたことを確認
        gpt_model = models[0]
        assert isinstance(gpt_model, ModelInfo)
        assert gpt_model.name == "gpt-4o"
        assert gpt_model.provider == "openai"
        assert gpt_model.capabilities == ["caption", "tags"]  # multimodal -> ["caption", "tags"]
        assert gpt_model.requires_api_key is True
        assert gpt_model.is_recommended is True  # gpt-4o は推奨モデル

    def test_load_models_no_adapter(self, service_without_adapter):
        """アダプターなしでのモデル読み込みテスト"""
        with patch("lorairo.gui.services.model_selection_service.logger") as mock_logger:
            models = service_without_adapter.load_models()

            # 警告ログが出力されたことを確認
            mock_logger.warning.assert_called_with("No model source available")

            # 空のリストが返されることを確認
            assert models == []

    def test_load_models_exception_handling(self, service_with_adapter, mock_annotator_adapter):
        """モデル読み込み例外処理テスト"""
        # アダプターが例外を投げるよう設定
        mock_annotator_adapter.get_available_models_with_metadata.side_effect = Exception("Test error")

        with patch("lorairo.gui.services.model_selection_service.logger") as mock_logger:
            models = service_with_adapter.load_models()

            # エラーログが出力されたことを確認
            mock_logger.error.assert_called()

            # 空のリストが返されることを確認
            assert models == []

    def test_get_all_models(self, service_with_adapter):
        """全モデル取得テスト"""
        # まずモデルを読み込み
        service_with_adapter.load_models()

        # 全モデルを取得
        all_models = service_with_adapter.get_all_models()

        assert len(all_models) == 4
        assert isinstance(all_models, list)
        # コピーが返されることを確認（元の配列と同じではない）
        assert all_models is not service_with_adapter._all_models

    def test_get_recommended_models(self, service_with_adapter):
        """推奨モデル取得テスト"""
        # まずモデルを読み込み
        service_with_adapter.load_models()

        # 推奨モデルを取得
        recommended = service_with_adapter.get_recommended_models()

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

    def test_filter_models_by_provider(self, service_with_adapter):
        """プロバイダーによるフィルタリングテスト"""
        service_with_adapter.load_models()

        # OpenAIプロバイダーでフィルタ
        openai_models = service_with_adapter.filter_models(provider="openai")
        assert len(openai_models) == 1
        assert openai_models[0].name == "gpt-4o"

        # ローカルプロバイダーでフィルタ
        local_models = service_with_adapter.filter_models(provider="local")
        assert len(local_models) == 2
        local_names = [m.name for m in local_models]
        assert "wd-v1-4" in local_names
        assert "clip-aesthetic" in local_names

    def test_filter_models_by_capabilities(self, service_with_adapter):
        """機能によるフィルタリングテスト"""
        service_with_adapter.load_models()

        # キャプション機能でフィルタ
        caption_models = service_with_adapter.filter_models(capabilities=["caption"])
        caption_names = [m.name for m in caption_models]
        assert "gpt-4o" in caption_names
        assert "claude-3-5-sonnet" in caption_names

        # タグ機能でフィルタ
        tag_models = service_with_adapter.filter_models(capabilities=["tags"])
        tag_names = [m.name for m in tag_models]
        assert "gpt-4o" in tag_names  # multimodal
        assert "claude-3-5-sonnet" in tag_names  # multimodal
        assert "wd-v1-4" in tag_names  # tags専用

    def test_filter_models_combined(self, service_with_adapter):
        """プロバイダーと機能の組み合わせフィルタリングテスト"""
        service_with_adapter.load_models()

        # ローカル + スコア機能
        local_score_models = service_with_adapter.filter_models(provider="local", capabilities=["scores"])
        assert len(local_score_models) == 1
        assert local_score_models[0].name == "clip-aesthetic"

    def test_filter_models_all_provider(self, service_with_adapter):
        """「すべて」プロバイダーでのフィルタリングテスト"""
        service_with_adapter.load_models()

        # 「すべて」指定時は全モデルが返される
        all_models = service_with_adapter.filter_models(provider="すべて")
        assert len(all_models) == 4

    def test_group_models_by_provider(self, service_with_adapter):
        """プロバイダー別グループ化テスト"""
        service_with_adapter.load_models()
        all_models = service_with_adapter.get_all_models()

        grouped = service_with_adapter.group_models_by_provider(all_models)

        assert "openai" in grouped
        assert "anthropic" in grouped
        assert "local" in grouped

        assert len(grouped["openai"]) == 1
        assert len(grouped["anthropic"]) == 1
        assert len(grouped["local"]) == 2

    def test_create_model_tooltip(self, service_with_adapter):
        """モデルツールチップ作成テスト"""
        service_with_adapter.load_models()
        models = service_with_adapter.get_all_models()

        gpt_model = next(m for m in models if m.name == "gpt-4o")
        tooltip = service_with_adapter.create_model_tooltip(gpt_model)

        assert "プロバイダー: openai" in tooltip
        assert "機能: caption, tag" in tooltip
        assert "API ID: gpt-4o-2024" in tooltip
        assert "APIキー必要: Yes" in tooltip

    def test_create_model_display_name(self, service_with_adapter):
        """モデル表示名作成テスト"""
        service_with_adapter.load_models()
        models = service_with_adapter.get_all_models()

        # API必要モデル
        gpt_model = next(m for m in models if m.name == "gpt-4o")
        display_name = service_with_adapter.create_model_display_name(gpt_model)
        assert display_name == "gpt-4o (API)"

        # ローカルモデル（サイズ情報あり）
        wd_model = next(m for m in models if m.name == "wd-v1-4")
        display_name = service_with_adapter.create_model_display_name(wd_model)
        assert display_name == "wd-v1-4 (2.5GB)"

    def test_infer_capabilities(self, service_with_adapter):
        """機能推論テスト"""
        # multimodal -> ["caption", "tags"]
        capabilities = service_with_adapter._infer_capabilities({"model_type": "multimodal"})
        assert capabilities == ["caption", "tags"]

        # caption -> ["caption"]
        capabilities = service_with_adapter._infer_capabilities({"model_type": "caption"})
        assert capabilities == ["caption"]

        # tag -> ["tags"]
        capabilities = service_with_adapter._infer_capabilities({"model_type": "tag"})
        assert capabilities == ["tags"]

        # score -> ["scores"]
        capabilities = service_with_adapter._infer_capabilities({"model_type": "score"})
        assert capabilities == ["scores"]

        # 不明なタイプ -> ["caption"] (デフォルト)
        capabilities = service_with_adapter._infer_capabilities({"model_type": "unknown"})
        assert capabilities == ["caption"]

    def test_is_recommended_model(self, service_with_adapter):
        """推奨モデル判定テスト"""
        # 推奨キャプションモデル
        assert service_with_adapter._is_recommended_model("gpt-4o") is True
        assert service_with_adapter._is_recommended_model("claude-3-5-sonnet") is True
        assert service_with_adapter._is_recommended_model("gemini-pro") is True

        # 推奨タグモデル
        assert service_with_adapter._is_recommended_model("wd-v1-4") is True
        assert service_with_adapter._is_recommended_model("wd-tagger") is True
        assert service_with_adapter._is_recommended_model("deepdanbooru") is True

        # 推奨スコアモデル
        assert service_with_adapter._is_recommended_model("clip-aesthetic") is True
        assert service_with_adapter._is_recommended_model("musiq") is True

        # 非推奨モデル
        assert service_with_adapter._is_recommended_model("unknown-model") is False
        assert service_with_adapter._is_recommended_model("test-model") is False

    def test_case_insensitive_recommendation(self, service_with_adapter):
        """大文字小文字を区別しない推奨判定テスト"""
        assert service_with_adapter._is_recommended_model("GPT-4O") is True
        assert service_with_adapter._is_recommended_model("Claude-3-5-Sonnet") is True
        assert service_with_adapter._is_recommended_model("WD-V1-4") is True
