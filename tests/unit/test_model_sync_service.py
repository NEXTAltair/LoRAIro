"""ModelSyncService ユニットテスト

Phase 4実装のimage-annotator-lib統合モデル同期サービスをテスト
実DB統合版: temp_db_repository fixtureを使用した実際のDB操作テスト
"""

import datetime
from unittest.mock import Mock

import pytest

from lorairo.services.model_sync_service import (
    AnnotatorLibraryProtocol,
    MockAnnotatorLibrary,
    ModelMetadata,
    ModelSyncResult,
    ModelSyncService,
)


class TestModelMetadata:
    """ModelMetadata型定義テスト"""

    def test_model_metadata_structure(self):
        """ModelMetadata型構造確認（model_types追加版）"""
        metadata: ModelMetadata = {
            "name": "gpt-4o",
            "provider": "openai",
            "class_name": "PydanticAIWebAPIAnnotator",
            "api_model_id": "gpt-4o",
            "model_type": "vision",
            "model_types": ["llm", "captioner"],  # 追加: マッピング後のタイプ
            "estimated_size_gb": None,
            "requires_api_key": True,
            "discontinued_at": None,
        }

        assert metadata["name"] == "gpt-4o"
        assert metadata["provider"] == "openai"
        assert metadata["model_type"] == "vision"
        assert metadata["model_types"] == ["llm", "captioner"]
        assert metadata["requires_api_key"] is True


class TestModelSyncResult:
    """ModelSyncResult データクラステスト"""

    def test_successful_sync_result(self):
        """成功時の同期結果"""
        result = ModelSyncResult(
            total_library_models=10, new_models_registered=5, existing_models_updated=3, errors=[]
        )

        assert result.success is True
        assert result.total_library_models == 10
        assert result.new_models_registered == 5
        assert result.existing_models_updated == 3
        assert len(result.errors) == 0

        expected_summary = "同期完了: ライブラリモデル 10件, 新規登録 5件, 更新 3件, エラー 0件"
        assert result.summary == expected_summary

    def test_failed_sync_result(self):
        """エラー発生時の同期結果"""
        result = ModelSyncResult(
            total_library_models=0,
            new_models_registered=0,
            existing_models_updated=0,
            errors=["Connection failed", "Invalid API key"],
        )

        assert result.success is False
        assert len(result.errors) == 2
        assert "Connection failed" in result.errors


class TestMockAnnotatorLibrary:
    """MockAnnotatorLibrary テスト"""

    def test_get_available_models_with_metadata(self):
        """モックのメタデータ付きモデル一覧取得"""
        mock_lib = MockAnnotatorLibrary()
        models = mock_lib.get_available_models_with_metadata()

        # リスト形式で返却される
        assert isinstance(models, list)
        assert len(models) > 0

        # 各モデルに必要なフィールドが含まれる
        for model in models:
            assert "name" in model
            assert "class" in model
            assert "model_type" in model
            assert "requires_api_key" in model

        # 特定のモデルが含まれることを確認
        model_names = [m["name"] for m in models]
        assert "gpt-4o" in model_names
        assert "claude-3-5-sonnet" in model_names
        assert "wd-v1-4-swinv2-tagger" in model_names

    def test_mock_model_types(self):
        """モックモデルの種類確認"""
        mock_lib = MockAnnotatorLibrary()
        models = mock_lib.get_available_models_with_metadata()

        model_types = [m["model_type"] for m in models]
        assert "vision" in model_types
        assert "tagger" in model_types
        assert "score" in model_types


class TestModelTypeMapping:
    """ModelTypeマッピングロジックテスト"""

    @pytest.fixture
    def service_with_mock(self, temp_db_repository, mock_config_service):
        """マッピングテスト用サービス"""
        return ModelSyncService(
            db_repository=temp_db_repository, config_service=mock_config_service, annotator_library=Mock()
        )

    def test_map_vision_to_llm_captioner_for_pydanticai(self, service_with_mock):
        """visionタイプのPydanticAIモデルをllm+captionerにマッピング"""
        result = service_with_mock._map_library_model_type_to_db(
            "vision", "gpt-4o", "PydanticAIWebAPIAnnotator"
        )
        assert result == ["llm", "captioner"]

    def test_map_vision_to_llm_captioner_for_webapi(self, service_with_mock):
        """visionタイプのWebAPIモデルをllm+captionerにマッピング"""
        result = service_with_mock._map_library_model_type_to_db("vision", "claude", "WebAPIAnnotator")
        assert result == ["llm", "captioner"]

    def test_map_vision_to_llm_for_llm_model(self, service_with_mock):
        """visionタイプのLLMモデルをllmにマッピング"""
        result = service_with_mock._map_library_model_type_to_db("vision", "llm-model", "LLMAnnotator")
        assert result == ["llm"]

    def test_map_vision_to_captioner_default(self, service_with_mock):
        """visionタイプのその他モデルをcaptionerにマッピング"""
        result = service_with_mock._map_library_model_type_to_db(
            "vision", "other-vision", "VisionAnnotator"
        )
        assert result == ["captioner"]

    def test_map_score_to_score(self, service_with_mock):
        """scoreタイプをscoreにマッピング"""
        result = service_with_mock._map_library_model_type_to_db("score", "aesthetic", "AestheticPredictor")
        assert result == ["score"]

    def test_map_tagger_to_tagger(self, service_with_mock):
        """taggerタイプをtaggerにマッピング"""
        result = service_with_mock._map_library_model_type_to_db("tagger", "wd-tagger", "WDTagger")
        assert result == ["tagger"]

    def test_map_unknown_type_to_captioner(self, service_with_mock):
        """未知のタイプをcaptionerにマッピング（警告ログ付き）"""
        result = service_with_mock._map_library_model_type_to_db("unknown_type", "test", "TestAnnotator")
        assert result == ["captioner"]


class TestModelSyncServiceWithRealDB:
    """ModelSyncService 実DB統合テスト"""

    @pytest.fixture
    def model_sync_service(self, temp_db_repository, mock_config_service):
        """ModelSyncService インスタンス（実DB使用）"""
        return ModelSyncService(db_repository=temp_db_repository, config_service=mock_config_service)

    def test_initialization_with_mock(self, model_sync_service):
        """Mock使用時の初期化"""
        assert model_sync_service.db_repository is not None
        assert model_sync_service.config_service is not None
        assert isinstance(model_sync_service.annotator_library, MockAnnotatorLibrary)

    def test_get_model_metadata_from_library_success(self, model_sync_service):
        """ライブラリからのメタデータ取得成功（model_types含む）"""
        metadata_list = model_sync_service.get_model_metadata_from_library()

        assert isinstance(metadata_list, list)
        assert len(metadata_list) > 0

        # 最初のメタデータ構造確認
        first_model = metadata_list[0]
        assert "name" in first_model
        assert "provider" in first_model
        assert "class_name" in first_model
        assert "model_type" in first_model
        assert "model_types" in first_model
        assert "discontinued_at" in first_model

        # PydanticAI WebAPIモデル（gpt-4o）のマッピング確認
        gpt4o_model = next((m for m in metadata_list if m["name"] == "gpt-4o"), None)
        assert gpt4o_model is not None
        assert gpt4o_model["model_types"] == ["llm", "captioner"]

    def test_register_new_models_to_db_success(self, model_sync_service, temp_db_repository):
        """新規モデルDB登録成功（実DB操作）"""
        test_models: list[ModelMetadata] = [
            {
                "name": "test-model-new-1",
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": "test-1",
                "model_type": "vision",
                "model_types": ["llm", "captioner"],
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            },
            {
                "name": "test-model-new-2",
                "provider": None,
                "class_name": "LocalTagger",
                "api_model_id": None,
                "model_type": "tagger",
                "model_types": ["tagger"],
                "estimated_size_gb": 1.5,
                "requires_api_key": False,
                "discontinued_at": None,
            },
        ]

        count = model_sync_service.register_new_models_to_db(test_models)

        # 2つのモデルが実際に登録される
        assert count == 2

        # DB確認
        registered_model_1 = temp_db_repository.get_model_by_name("test-model-new-1")
        assert registered_model_1 is not None
        assert registered_model_1.provider == "openai"
        assert len(registered_model_1.model_types) == 2
        assert set(mt.name for mt in registered_model_1.model_types) == {"llm", "captioner"}

        registered_model_2 = temp_db_repository.get_model_by_name("test-model-new-2")
        assert registered_model_2 is not None
        assert registered_model_2.estimated_size_gb == 1.5
        assert len(registered_model_2.model_types) == 1
        assert registered_model_2.model_types[0].name == "tagger"

    def test_register_new_models_to_db_with_discontinued_at(self, model_sync_service, temp_db_repository):
        """discontinued_atフィールド付き新規モデル登録（Issue #5対応）"""
        discontinued_date = datetime.datetime(2024, 12, 31, tzinfo=datetime.UTC)
        test_models: list[ModelMetadata] = [
            {
                "name": "discontinued-model",
                "provider": "openai",
                "class_name": "DiscontinuedAnnotator",
                "api_model_id": "discontinued-1",
                "model_type": "vision",
                "model_types": ["captioner"],
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": discontinued_date,
            }
        ]

        count = model_sync_service.register_new_models_to_db(test_models)
        assert count == 1

        # DB確認: discontinued_atが正しく保存されている
        registered_model = temp_db_repository.get_model_by_name("discontinued-model")
        assert registered_model is not None
        assert registered_model.discontinued_at is not None
        # SQLiteはnaive datetimeとして保存するため、timezone情報を削除して比較
        assert registered_model.discontinued_at == discontinued_date.replace(tzinfo=None)

    def test_register_new_models_existing_models_skip(self, model_sync_service, temp_db_repository):
        """既存モデル存在時のDB登録スキップ"""
        # 事前に1つ目のモデルを登録
        temp_db_repository.insert_model(
            name="existing-model-test", provider="openai", model_types=["llm"], requires_api_key=True
        )

        test_models: list[ModelMetadata] = [
            {
                "name": "existing-model-test",
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": "existing",
                "model_type": "vision",
                "model_types": ["llm"],
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        count = model_sync_service.register_new_models_to_db(test_models)

        # 既存モデルなので新規登録は0
        assert count == 0

    def test_update_existing_models_success(self, model_sync_service, temp_db_repository):
        """既存モデル更新処理（実DB操作）"""
        # 事前にモデルを登録
        model_id = temp_db_repository.insert_model(
            name="update-test-model", provider="openai", model_types=["captioner"], estimated_size_gb=1.0
        )

        # 更新データ（サイズとタイプ変更）
        test_models: list[ModelMetadata] = [
            {
                "name": "update-test-model",
                "provider": "openai",
                "class_name": "UpdatedAnnotator",
                "api_model_id": "updated",
                "model_type": "vision",
                "model_types": ["llm", "captioner"],  # タイプ追加
                "estimated_size_gb": 2.5,  # サイズ変更
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        count = model_sync_service.update_existing_models(test_models)

        # 1つのモデルが更新される
        assert count == 1

        # DB確認: 実際に更新されている
        updated_model = temp_db_repository.get_model_by_name("update-test-model")
        assert updated_model is not None
        assert updated_model.estimated_size_gb == 2.5
        assert len(updated_model.model_types) == 2
        assert set(mt.name for mt in updated_model.model_types) == {"llm", "captioner"}

    def test_update_existing_models_no_changes(self, model_sync_service, temp_db_repository):
        """既存モデル更新処理（変更なし）"""
        # 事前にモデルを登録
        temp_db_repository.insert_model(
            name="no-change-model", provider="openai", model_types=["llm"], estimated_size_gb=1.0
        )

        # 同じデータで更新
        test_models: list[ModelMetadata] = [
            {
                "name": "no-change-model",
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": None,
                "model_type": "vision",
                "model_types": ["llm"],
                "estimated_size_gb": 1.0,
                "requires_api_key": False,
                "discontinued_at": None,
            }
        ]

        count = model_sync_service.update_existing_models(test_models)

        # 変更がないので更新数は0
        assert count == 0

    def test_update_existing_models_with_discontinued_at(self, model_sync_service, temp_db_repository):
        """既存モデルのdiscontinued_at更新（Issue #5対応）"""
        # 事前にモデルを登録（discontinued_at=None）
        temp_db_repository.insert_model(
            name="to-be-discontinued", provider="openai", model_types=["captioner"], discontinued_at=None
        )

        # discontinued_atを設定して更新
        discontinued_date = datetime.datetime(2025, 6, 30, tzinfo=datetime.UTC)
        test_models: list[ModelMetadata] = [
            {
                "name": "to-be-discontinued",
                "provider": "openai",
                "class_name": "DiscontinuedAnnotator",
                "api_model_id": "discontinued",
                "model_type": "vision",
                "model_types": ["captioner"],
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": discontinued_date,
            }
        ]

        count = model_sync_service.update_existing_models(test_models)
        assert count == 1

        # DB確認: discontinued_atが更新されている
        updated_model = temp_db_repository.get_model_by_name("to-be-discontinued")
        assert updated_model is not None
        # SQLiteはnaive datetimeとして保存するため、timezone情報を削除して比較
        assert updated_model.discontinued_at == discontinued_date.replace(tzinfo=None)

    def test_sync_available_models_success(self, model_sync_service):
        """モデル同期処理成功（実DB操作）"""
        result = model_sync_service.sync_available_models()

        assert isinstance(result, ModelSyncResult)
        assert result.success is True
        assert result.total_library_models > 0
        assert result.new_models_registered >= 0
        assert len(result.errors) == 0

    def test_sync_available_models_with_error(self, temp_db_repository, mock_config_service):
        """モデル同期処理エラー発生"""
        error_lib = Mock(spec=AnnotatorLibraryProtocol)
        error_lib.get_available_models_with_metadata.side_effect = Exception("Sync error")

        service = ModelSyncService(
            db_repository=temp_db_repository,
            config_service=mock_config_service,
            annotator_library=error_lib,
        )

        result = service.sync_available_models()

        assert isinstance(result, ModelSyncResult)
        assert result.success is False
        assert result.total_library_models == 0
        assert len(result.errors) == 1
        assert "Sync error" in result.errors[0]

    def test_get_library_models_summary(self, model_sync_service):
        """ライブラリモデルサマリー取得"""
        summary = model_sync_service.get_library_models_summary()

        assert isinstance(summary, dict)
        assert "total_models" in summary
        assert "providers" in summary
        assert "model_types" in summary
        assert "api_key_required" in summary
        assert "local_models" in summary

    def test_validate_annotation_model_type(self, model_sync_service):
        """アノテーションモデルタイプの妥当性検証"""
        assert model_sync_service.validate_annotation_model_type("vision") is True
        assert model_sync_service.validate_annotation_model_type("score") is True
        assert model_sync_service.validate_annotation_model_type("tagger") is True
        assert model_sync_service.validate_annotation_model_type("upscaler") is False
        assert model_sync_service.validate_annotation_model_type("unknown") is False


class TestModelSyncServiceEdgeCases:
    """ModelSyncService 境界値・エッジケーステスト"""

    @pytest.fixture
    def model_sync_service(self, temp_db_repository, mock_config_service):
        """ModelSyncService インスタンス（実DB使用）"""
        return ModelSyncService(db_repository=temp_db_repository, config_service=mock_config_service)

    def test_empty_model_list_sync(self, temp_db_repository, mock_config_service):
        """空のモデルリスト同期"""
        empty_lib = Mock(spec=AnnotatorLibraryProtocol)
        empty_lib.get_available_models_with_metadata.return_value = []

        service = ModelSyncService(
            db_repository=temp_db_repository,
            config_service=mock_config_service,
            annotator_library=empty_lib,
        )

        result = service.sync_available_models()

        assert result.success is True
        assert result.total_library_models == 0
        assert result.new_models_registered == 0

    def test_invalid_model_metadata_handling(self, model_sync_service):
        """不正なモデルメタデータの処理"""
        # 不正なメタデータを含むテスト
        invalid_models: list[ModelMetadata] = [
            {
                "name": "",  # 空の名前
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": None,
                "model_type": "unknown",  # 不明な型
                "model_types": ["captioner"],  # マッピング結果
                "estimated_size_gb": -1.0,  # 負の値
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        # 例外が発生せずに処理されることを確認
        count = model_sync_service.register_new_models_to_db(invalid_models)
        assert count >= 0
