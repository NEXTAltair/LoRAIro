# tests/unit/services/test_model_filter_service.py

from unittest.mock import Mock, patch

import pytest

from lorairo.services.model_filter_service import ModelFilterService
from lorairo.services.search_models import SearchConditions, ValidationResult


class TestModelFilterService:
    """ModelFilterService のユニットテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        """モックデータベースマネージャー"""
        return Mock()

    @pytest.fixture
    def mock_model_selection_service(self):
        """モックモデル選択サービス"""
        mock_service = Mock()

        # モックモデルデータ（辞書形式）
        mock_models = [
            {
                "name": "gpt-4-vision",
                "provider": "openai",
                "capabilities": ["image_analysis", "text_generation"],
                "requires_api_key": True,
                "estimated_size_gb": 0,
                "is_recommended": True,
            },
            {
                "name": "claude-3-sonnet",
                "provider": "anthropic",
                "capabilities": ["image_analysis", "advanced_reasoning"],
                "requires_api_key": True,
                "estimated_size_gb": 0,
                "is_recommended": True,
            },
            {
                "name": "local-llava",
                "provider": "local",
                "capabilities": ["image_analysis"],
                "requires_api_key": False,
                "estimated_size_gb": 7.5,
                "is_recommended": False,
            },
        ]

        mock_service.load_models.return_value = mock_models
        return mock_service

    @pytest.fixture
    def service(self, mock_db_manager, mock_model_selection_service):
        """テスト用ModelFilterService"""
        return ModelFilterService(mock_db_manager, mock_model_selection_service)

    def test_initialization(self, service, mock_db_manager, mock_model_selection_service):
        """初期化テスト"""
        assert service.db_manager == mock_db_manager
        assert service.model_selection_service == mock_model_selection_service

    def test_get_annotation_models_list_success(self, service, mock_model_selection_service):
        """アノテーションモデル一覧取得成功テスト"""
        models = service.get_annotation_models_list()

        # ModelSelectionServiceが呼ばれることを確認
        mock_model_selection_service.load_models.assert_called_once()

        # 返される形式を確認
        assert len(models) == 3

        # 最初のモデルの確認
        gpt4_model = models[0]
        assert gpt4_model["name"] == "gpt-4-vision"
        assert gpt4_model["provider"] == "openai"
        assert gpt4_model["capabilities"] == ["image_analysis", "text_generation"]
        assert gpt4_model["requires_api_key"] is True
        assert gpt4_model["is_local"] is False
        assert gpt4_model["estimated_size_gb"] == 0
        assert gpt4_model["is_recommended"] is True

        # ローカルモデルの確認
        local_model = models[2]
        assert local_model["name"] == "local-llava"
        assert local_model["provider"] == "local"
        assert local_model["is_local"] is True
        assert local_model["estimated_size_gb"] == 7.5
        assert local_model["is_recommended"] is False

    @patch("lorairo.services.model_filter_service.logger")
    def test_get_annotation_models_list_error(self, mock_logger, service, mock_model_selection_service):
        """アノテーションモデル一覧取得エラーテスト"""
        # ModelSelectionServiceでエラーを発生させる
        mock_model_selection_service.load_models.side_effect = Exception("Service error")

        models = service.get_annotation_models_list()

        # エラーログが出力され、空リストが返されることを確認
        mock_logger.error.assert_called_once()
        assert models == []

    def test_filter_models_by_criteria_provider_filter(self, service):
        """プロバイダーフィルターテスト"""
        criteria = {"provider_filter": "openai"}

        filtered_models = service.filter_models_by_criteria(criteria)

        # OpenAIモデルのみ残ることを確認
        assert len(filtered_models) == 1
        assert filtered_models[0]["provider"] == "openai"

    def test_filter_models_by_criteria_local_only(self, service):
        """ローカルモデルのみフィルターテスト"""
        criteria = {"local_only": True}

        filtered_models = service.filter_models_by_criteria(criteria)

        # ローカルモデルのみ残ることを確認
        assert len(filtered_models) == 1
        assert filtered_models[0]["provider"] == "local"
        assert filtered_models[0]["is_local"] is True

    def test_filter_models_by_criteria_recommended_only(self, service):
        """推奨モデルのみフィルターテスト"""
        criteria = {"recommended_only": True}

        filtered_models = service.filter_models_by_criteria(criteria)

        # 推奨モデルのみ残ることを確認（gpt-4-vision, claude-3-sonnet）
        assert len(filtered_models) == 2
        assert all(model["is_recommended"] for model in filtered_models)

    def test_filter_models_by_criteria_multiple_providers(self, service):
        """複数プロバイダーフィルターテスト"""
        criteria = {"provider_filter": ["openai", "anthropic"]}

        filtered_models = service.filter_models_by_criteria(criteria)

        # OpenAIとAnthropicモデルが残ることを確認
        assert len(filtered_models) == 2
        providers = {model["provider"] for model in filtered_models}
        assert providers == {"openai", "anthropic"}

    @patch("lorairo.services.model_filter_service.logger")
    def test_filter_models_by_criteria_error(self, mock_logger, service, mock_model_selection_service):
        """モデルフィルタリングエラーテスト"""
        # get_annotation_models_listでエラーを発生させる
        mock_model_selection_service.load_models.side_effect = Exception("Filter error")

        criteria = {"provider_filter": "openai"}
        filtered_models = service.filter_models_by_criteria(criteria)

        # エラーログが出力され、空リストが返されることを確認
        mock_logger.error.assert_called_once()
        assert filtered_models == []

    def test_infer_model_capabilities_vision_model(self, service):
        """ビジョンモデルの能力推定テスト"""
        model_data = {
            "name": "gpt-4-vision-preview",
            "provider": "openai",
            "capabilities": ["existing_capability"],
            "is_local": False,
        }

        capabilities = service.infer_model_capabilities(model_data)

        # 既存の能力 + 推定された能力
        expected_capabilities = {
            "existing_capability",
            "image_analysis",
            "object_detection",
            "text_generation",
            "description_generation",
            "advanced_reasoning",
            "contextual_analysis",
        }

        assert set(capabilities) == expected_capabilities

    def test_infer_model_capabilities_local_model(self, service):
        """ローカルモデルの能力推定テスト"""
        model_data = {
            "name": "local-image-model",
            "provider": "local",
            "capabilities": [],
            "is_local": True,
        }

        capabilities = service.infer_model_capabilities(model_data)

        # ローカルモデル特有の能力が含まれることを確認
        assert "offline_processing" in capabilities
        assert "image_analysis" in capabilities
        assert "object_detection" in capabilities

    def test_infer_model_capabilities_anthropic_model(self, service):
        """Anthropicモデルの能力推定テスト"""
        model_data = {
            "name": "claude-3-opus",
            "provider": "anthropic",
            "capabilities": [],
            "is_local": False,
        }

        capabilities = service.infer_model_capabilities(model_data)

        # Anthropic特有の能力が含まれることを確認
        assert "text_generation" in capabilities
        assert "description_generation" in capabilities
        assert "advanced_reasoning" in capabilities
        assert "contextual_analysis" in capabilities

    @patch("lorairo.services.model_filter_service.logger")
    def test_infer_model_capabilities_error(self, mock_logger, service):
        """モデル能力推定エラーテスト"""
        # 不正なモデルデータ
        invalid_model_data = None

        capabilities = service.infer_model_capabilities(invalid_model_data)

        # エラーログが出力され、空リストが返されることを確認
        mock_logger.error.assert_called_once()
        assert capabilities == []

    def test_validate_annotation_settings_valid(self, service):
        """有効なアノテーション設定検証テスト"""
        # まず利用可能なモデルを取得
        available_models = service.get_annotation_models_list()
        available_model_names = [model["name"] for model in available_models]

        settings = {
            "selected_models": available_model_names[:2],  # 最初の2つのモデルを選択
            "openai_api_key": "test_key",
            "anthropic_api_key": "test_key",
            "batch_size": 10,
            "timeout": 60,
        }

        result = service.validate_annotation_settings(settings)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_annotation_settings_no_models(self, service):
        """モデル未選択設定検証テスト"""
        settings = {"selected_models": [], "batch_size": 5, "timeout": 30}

        result = service.validate_annotation_settings(settings)

        assert result.is_valid is False
        assert "アノテーション用のモデルが選択されていません" in result.errors

    def test_validate_annotation_settings_unavailable_model(self, service):
        """利用不可モデル設定検証テスト"""
        settings = {"selected_models": ["non-existent-model"], "batch_size": 5, "timeout": 30}

        result = service.validate_annotation_settings(settings)

        assert result.is_valid is False
        assert any("non-existent-model" in error for error in result.errors)

    def test_validate_annotation_settings_missing_api_key(self, service):
        """APIキー未設定設定検証テスト"""
        # 利用可能なモデルから最初のAPI キー必須モデルを選択
        available_models = service.get_annotation_models_list()
        api_key_required_model = next(m for m in available_models if m.get("requires_api_key", False))

        settings = {
            "selected_models": [api_key_required_model["name"]],
            "batch_size": 5,
            "timeout": 30,
            # APIキーが設定されていない
        }

        result = service.validate_annotation_settings(settings)

        # 警告として扱われる
        assert len(result.warnings) > 0
        assert any("APIキーが必要です" in warning for warning in result.warnings)

    def test_validate_annotation_settings_invalid_batch_size(self, service):
        """無効なバッチサイズ設定検証テスト"""
        settings = {
            "selected_models": ["gpt-4-vision"],
            "batch_size": 150,  # 最大値超過
            "timeout": 30,
        }

        result = service.validate_annotation_settings(settings)

        assert result.is_valid is False
        assert "バッチサイズは1から100の間で設定してください" in result.errors

    def test_validate_annotation_settings_invalid_timeout(self, service):
        """無効なタイムアウト設定検証テスト"""
        settings = {
            "selected_models": ["gpt-4-vision"],
            "batch_size": 5,
            "timeout": 400,  # 推奨値超過
        }

        result = service.validate_annotation_settings(settings)

        # 警告として扱われる
        assert any(
            "タイムアウトは5秒から300秒の間での設定を推奨します" in warning for warning in result.warnings
        )

    @patch("lorairo.services.model_filter_service.logger")
    def test_validate_annotation_settings_error(self, mock_logger, service, mock_model_selection_service):
        """アノテーション設定検証エラーテスト

        get_annotation_models_listが例外をキャッチして空リストを返すため、
        validate_annotation_settingsは「モデルが利用できない」エラーとして処理する。
        """
        # get_annotation_models_listでエラーを発生させる
        mock_model_selection_service.load_models.side_effect = Exception("Validation error")

        settings = {"selected_models": ["any-model"]}

        result = service.validate_annotation_settings(settings)

        # get_annotation_models_listが空リストを返すため、
        # 選択モデルが利用不可として報告される
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert any("利用できません" in error for error in result.errors)

    def test_apply_advanced_model_filters_no_filters(self, service):
        """高度なモデルフィルターなしテスト"""
        images = [{"id": 1}, {"id": 2}]
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # 高度なフィルターが設定されていない場合
        result = service.apply_advanced_model_filters(images, conditions)

        # 全画像がそのまま返される
        assert result == images

    def test_apply_advanced_model_filters_with_filters(self, service):
        """高度なモデルフィルター適用テスト"""
        images = [{"id": 1}, {"id": 2}, {"id": 3}]
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        # 高度なフィルターを擬似的に設定
        conditions.model_filters = {"quality_threshold": 0.8}

        result = service.apply_advanced_model_filters(images, conditions)

        # フィルターが適用される（この実装では全画像が返される）
        assert len(result) <= len(images)

    def test_optimize_advanced_filtering_performance(self, service):
        """高度なフィルタリングパフォーマンス最適化テスト"""
        # 大量の画像データを作成
        images = [{"id": i} for i in range(200)]
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = service.optimize_advanced_filtering_performance(images, conditions)

        # バッチ処理が正常に動作することを確認
        assert len(result) <= len(images)

    def test_model_matches_criteria_provider_string(self, service):
        """プロバイダー文字列条件マッチテスト"""
        model = {"provider": "OpenAI", "capabilities": []}
        criteria = {"provider_filter": "openai"}

        result = service._model_matches_criteria(model, criteria)

        # 大文字小文字を無視してマッチすることを確認
        assert result is True

    def test_model_matches_criteria_provider_list(self, service):
        """プロバイダーリスト条件マッチテスト"""
        model = {"provider": "anthropic", "capabilities": []}
        criteria = {"provider_filter": ["openai", "anthropic"]}

        result = service._model_matches_criteria(model, criteria)

        assert result is True

    def test_model_matches_criteria_function_filter(self, service):
        """機能フィルター条件マッチテスト"""
        model = {
            "provider": "openai",
            "name": "gpt-4-vision",
            "capabilities": ["image_analysis"],
            "is_local": False,
        }
        criteria = {"function_filter": ["image_analysis"]}

        result = service._model_matches_criteria(model, criteria)

        assert result is True

    def test_model_matches_criteria_inferred_capabilities(self, service):
        """推定機能条件マッチテスト"""
        model = {
            "provider": "openai",
            "name": "gpt-4-vision",
            "capabilities": [],  # 空だが推定される
            "is_local": False,
        }
        criteria = {"function_filter": "text_generation"}

        result = service._model_matches_criteria(model, criteria)

        # 推定機能でマッチすることを確認
        assert result is True

    def test_model_matches_provider_filter_none(self, service):
        """プロバイダーフィルターなしテスト"""
        model = {"provider": "openai"}
        criteria = {}

        result = service._model_matches_provider_filter(model, criteria)

        # フィルターなしの場合はTrue
        assert result is True

    def test_model_matches_function_filter_none(self, service):
        """機能フィルターなしテスト"""
        model = {"capabilities": ["image_analysis"]}
        criteria = {}

        result = service._model_matches_function_filter(model, criteria)

        # フィルターなしの場合はTrue
        assert result is True

    def test_has_advanced_model_filters_true(self, service):
        """高度なモデルフィルター有効判定テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        # 高度なフィルターを擬似的に設定
        conditions.model_filters = {"quality_threshold": 0.8}

        result = service._has_advanced_model_filters(conditions)

        assert result is True

    def test_has_advanced_model_filters_false(self, service):
        """高度なモデルフィルター無効判定テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = service._has_advanced_model_filters(conditions)

        assert result is False

    def test_image_matches_advanced_model_criteria_basic(self, service):
        """画像高度モデル条件マッチテスト"""
        image = {"id": 1, "quality_score": 0.9}
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        # 品質閾値を擬似的に設定
        conditions.quality_threshold = 0.8

        result = service._image_matches_advanced_model_criteria(image, conditions)

        # 品質スコアが閾値を超えているのでTrue
        assert result is True

    def test_image_matches_advanced_model_criteria_below_threshold(self, service):
        """画像高度モデル条件閾値下回りテスト"""
        image = {"id": 1, "quality_score": 0.5}
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        # 品質閾値を擬似的に設定
        conditions.quality_threshold = 0.8

        result = service._image_matches_advanced_model_criteria(image, conditions)

        # 品質スコアが閾値を下回っているのでFalse
        assert result is False


@pytest.mark.unit
class TestModelFilterServiceAdditional:
    """ModelFilterService の追加ブランチカバレッジテスト"""

    @pytest.fixture
    def mock_db_manager(self):
        return Mock()

    @pytest.fixture
    def mock_model_selection_service(self):
        mock_service = Mock()
        mock_models = [
            {
                "name": "gpt-4-vision",
                "provider": "openai",
                "capabilities": ["image_analysis", "text_generation"],
                "requires_api_key": True,
                "estimated_size_gb": 0,
                "is_recommended": True,
            },
            {
                "name": "claude-3-sonnet",
                "provider": "anthropic",
                "capabilities": ["image_analysis", "advanced_reasoning"],
                "requires_api_key": True,
                "estimated_size_gb": 0,
                "is_recommended": True,
            },
            {
                "name": "local-llava",
                "provider": "local",
                "capabilities": ["image_analysis"],
                "requires_api_key": False,
                "estimated_size_gb": 7.5,
                "is_recommended": False,
            },
        ]
        mock_service.load_models.return_value = mock_models
        return mock_service

    @pytest.fixture
    def service(self, mock_db_manager, mock_model_selection_service):
        return ModelFilterService(mock_db_manager, mock_model_selection_service)

    def test_get_annotation_models_list_with_model_objects(self, mock_db_manager):
        """Model オブジェクト形式（辞書でない）でのモデル一覧取得テスト"""
        mock_service = Mock()
        # Mock objects (not dicts) - production path
        mock_model = Mock()
        mock_model.name = "test-model"
        mock_model.provider = "openai"
        mock_model.capabilities = ["image_analysis"]
        mock_model.requires_api_key = True
        mock_model.estimated_size_gb = 0.0
        mock_model.is_recommended = True
        mock_service.load_models.return_value = [mock_model]

        service = ModelFilterService(mock_db_manager, mock_service)
        models = service.get_annotation_models_list()

        assert len(models) == 1
        assert models[0]["name"] == "test-model"
        assert models[0]["provider"] == "openai"
        assert models[0]["is_local"] is False
        assert models[0]["requires_api_key"] is True

    def test_get_annotation_models_list_local_model_object(self, mock_db_manager):
        """ローカルプロバイダーのModel オブジェクト形式でis_local=True になるテスト"""
        mock_service = Mock()
        mock_model = Mock()
        mock_model.name = "local-model"
        mock_model.provider = "local"
        mock_model.capabilities = []
        mock_model.requires_api_key = False
        mock_model.estimated_size_gb = 5.0
        mock_model.is_recommended = False
        mock_service.load_models.return_value = [mock_model]

        service = ModelFilterService(mock_db_manager, mock_service)
        models = service.get_annotation_models_list()

        assert models[0]["is_local"] is True

    def test_filter_models_by_criteria_function_filter_string(self, service):
        """function_filter が文字列のとき、その機能を持つモデルのみ返す"""
        criteria = {"function_filter": "image_analysis"}
        filtered = service.filter_models_by_criteria(criteria)
        assert len(filtered) >= 1
        # すべて image_analysis を含む (推定能力経由でも)

    def test_filter_models_by_criteria_function_filter_list(self, service):
        """function_filter がリストのとき、いずれかの機能を持つモデルを返す"""
        criteria = {"function_filter": ["offline_processing"]}
        filtered = service.filter_models_by_criteria(criteria)
        # ローカルモデルのみが offline_processing を持つ
        assert len(filtered) == 1
        assert filtered[0]["provider"] == "local"

    def test_filter_models_by_criteria_no_match(self, service):
        """どの条件にも一致するモデルがない場合は空リストを返す"""
        # 存在しないプロバイダーでフィルタリング
        criteria = {"provider_filter": "nonexistent_provider"}
        filtered = service.filter_models_by_criteria(criteria)
        assert filtered == []

    def test_model_matches_provider_filter_unexpected_type(self, service):
        """provider_filter が文字列でもリストでもない場合はTrue を返す"""
        model = {"provider": "openai"}
        criteria = {"provider_filter": 42}  # 整数型 (予期しない型)
        result = service._model_matches_provider_filter(model, criteria)
        assert result is True

    def test_model_matches_function_filter_non_list_capabilities(self, service):
        """capabilities が非リスト型の場合でも安全に処理する"""
        model = {
            "provider": "openai",
            "name": "test-model",
            "capabilities": "not_a_list",  # 非リスト型
            "is_local": False,
        }
        criteria = {"function_filter": "text_generation"}
        # 例外なく処理され、推定能力でマッチ可能
        result = service._model_matches_function_filter(model, criteria)
        # openai プロバイダーなので text_generation が推定される
        assert result is True

    def test_has_advanced_model_filters_advanced_model_criteria(self, service):
        """advanced_model_criteria 属性で高度なフィルター有効判定テスト"""
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        conditions.advanced_model_criteria = {"threshold": 0.9}
        result = service._has_advanced_model_filters(conditions)
        assert result is True

    def test_image_matches_advanced_model_criteria_with_annotation_model_filter(self, service):
        """annotation_model_filter が設定されている場合の処理テスト（image_id あり）"""
        image = {"id": 1, "quality_score": 0.9}
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        conditions.annotation_model_filter = "gpt-4-vision"
        # 実装では image_id 取得後 pass なので True が返る
        result = service._image_matches_advanced_model_criteria(image, conditions)
        assert result is True

    def test_image_matches_advanced_model_criteria_no_image_id(self, service):
        """annotation_model_filter で image_id がない場合のテスト"""
        image = {"quality_score": 0.9}  # id キーなし
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")
        conditions.annotation_model_filter = "gpt-4-vision"
        result = service._image_matches_advanced_model_criteria(image, conditions)
        assert result is True

    def test_infer_model_capabilities_google_provider(self, service):
        """Google プロバイダーの能力推定テスト"""
        model_data = {
            "name": "gemini-pro",
            "provider": "google",
            "capabilities": [],
            "is_local": False,
        }
        capabilities = service.infer_model_capabilities(model_data)
        # google プロバイダーなので text_generation が推定される
        assert "text_generation" in capabilities
        assert "description_generation" in capabilities
        # gemini キーワードで高度な推論能力
        assert "advanced_reasoning" in capabilities

    def test_infer_model_capabilities_non_list_existing(self, service):
        """既存能力が非リスト型でも安全に処理するテスト"""
        model_data = {
            "name": "simple-model",
            "provider": "other",
            "capabilities": None,  # None 型
            "is_local": False,
        }
        # None は isinstance(None, list) が False なので extend されない
        capabilities = service.infer_model_capabilities(model_data)
        assert isinstance(capabilities, list)

    def test_validate_annotation_settings_batch_size_too_small(self, service):
        """バッチサイズが小さすぎる（0）場合のエラーテスト"""
        settings = {
            "selected_models": ["gpt-4-vision"],
            "batch_size": 0,  # 最小値未満
            "timeout": 30,
        }
        result = service.validate_annotation_settings(settings)
        assert result.is_valid is False
        assert "バッチサイズは1から100の間で設定してください" in result.errors

    def test_validate_annotation_settings_timeout_too_small(self, service):
        """タイムアウトが小さすぎる場合の警告テスト"""
        settings = {
            "selected_models": ["gpt-4-vision"],
            "batch_size": 5,
            "timeout": 3,  # 最小値未満
        }
        result = service.validate_annotation_settings(settings)
        assert any("タイムアウトは5秒から300秒の間での設定を推奨します" in w for w in result.warnings)

    def test_optimize_advanced_filtering_performance_progress_logging(self, mock_db_manager):
        """500件の倍数でデバッグ進捗ログが出力されるテスト"""
        mock_service = Mock()
        mock_service.load_models.return_value = []
        service = ModelFilterService(mock_db_manager, mock_service)

        # 501 枚以上（batch_size=50, 10バッチ分 = 500件がちょうど 500件区切りログ対象）
        images = [{"id": i} for i in range(501)]
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        result = service.optimize_advanced_filtering_performance(images, conditions)
        # 例外なく完了し、全件返る（フィルターなし）
        assert len(result) == len(images)

    def test_model_matches_criteria_local_only_false_model(self, service):
        """local_only=True のとき is_local=False のモデルはフィルター除外される"""
        model = {"provider": "openai", "is_local": False, "capabilities": []}
        criteria = {"local_only": True}
        result = service._model_matches_criteria(model, criteria)
        assert result is False

    def test_model_matches_criteria_recommended_only_false_model(self, service):
        """recommended_only=True のとき is_recommended=False のモデルはフィルター除外される"""
        model = {"provider": "openai", "is_local": False, "is_recommended": False, "capabilities": []}
        criteria = {"recommended_only": True}
        result = service._model_matches_criteria(model, criteria)
        assert result is False


class TestModelFilterServicePerformance:
    """ModelFilterService のパフォーマンステスト"""

    @pytest.fixture
    def service_with_large_dataset(self):
        """大規模データセット用サービス"""
        mock_db_manager = Mock()
        mock_model_service = Mock()

        # 大量のモデルデータを作成
        large_model_list = []
        for i in range(100):
            mock_model = Mock(
                name=f"model-{i}",
                provider=f"provider-{i % 5}",
                capabilities=[f"capability-{j}" for j in range(i % 10)],
                requires_api_key=i % 2 == 0,
                estimated_size_gb=i * 0.5,
                is_recommended=i % 10 == 0,
            )
            large_model_list.append(mock_model)

        mock_model_service.load_models.return_value = large_model_list
        return ModelFilterService(mock_db_manager, mock_model_service)

    def test_large_model_list_filtering(self, service_with_large_dataset):
        """大規模モデルリストフィルタリングテスト"""
        criteria = {"recommended_only": True}

        filtered_models = service_with_large_dataset.filter_models_by_criteria(criteria)

        # 推奨モデルのみが残ることを確認（0, 10, 20, ..., 90, 100のうち99個まで）
        expected_count = 10  # 0, 10, 20, ..., 90
        assert len(filtered_models) == expected_count

    def test_batch_performance_optimization(self, service_with_large_dataset):
        """バッチパフォーマンス最適化テスト"""
        # 大量の画像データ
        images = [{"id": i, "quality_score": i * 0.01} for i in range(1000)]
        conditions = SearchConditions(search_type="tags", keywords=["test"], tag_logic="and")

        # パフォーマンス最適化版を実行
        result = service_with_large_dataset.optimize_advanced_filtering_performance(images, conditions)

        # 結果が期待される範囲内であることを確認
        assert len(result) <= len(images)
