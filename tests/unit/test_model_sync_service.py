"""ModelSyncService ユニットテスト

Issue #225: 型安全 API (`AnnotatorLibraryProtocol` = list_annotator_info + get_model_extras) に migrate 完了。
"""

import datetime
from unittest.mock import Mock

import pytest
from image_annotator_lib import AnnotatorInfo
from image_annotator_lib.core.types import TaskCapability

from lorairo.annotations.annotator_adapter import AnnotatorExtras
from lorairo.services.model_sync_service import (
    AnnotatorLibraryProtocol,
    MockAnnotatorLibrary,
    ModelMetadata,
    ModelSyncResult,
    ModelSyncService,
)


def _info(name: str, model_type: str, *, is_api: bool, capabilities: set[TaskCapability]) -> AnnotatorInfo:
    """AnnotatorInfo 生成のショートカット (テストコード簡素化用)"""
    return AnnotatorInfo(
        name=name,
        model_type=model_type,  # type: ignore[arg-type]
        capabilities=frozenset(capabilities),
        is_local=not is_api,
        is_api=is_api,
        device=None if is_api else "cuda",
    )


class TestModelMetadata:
    """ModelMetadata型定義テスト"""

    def test_model_metadata_structure(self):
        """ModelMetadata型構造確認（class_name は Optional に変更）"""
        metadata: ModelMetadata = {
            "name": "gpt-4o",
            "provider": "openai",
            "class_name": "PydanticAIWebAPIAnnotator",
            "api_model_id": "gpt-4o",
            "model_type": "vision",
            "model_types": ["llm", "captioner"],
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
    """MockAnnotatorLibrary テスト (Issue #225 で AnnotatorInfo + extras に変更)"""

    def test_list_annotator_info_returns_annotator_info(self):
        """list_annotator_info は AnnotatorInfo のリストを返す"""
        mock_lib = MockAnnotatorLibrary()
        infos = mock_lib.list_annotator_info()

        assert isinstance(infos, list)
        assert len(infos) > 0
        assert all(isinstance(info, AnnotatorInfo) for info in infos)

        names = {info.name for info in infos}
        assert "gpt-4o" in names
        assert "claude-3-5-sonnet" in names
        assert "wd-v1-4-swinv2-tagger" in names

    def test_mock_model_types_use_post_issue_19_literals(self):
        """モックモデルの model_type は Issue #19 の Literal 値 (vision/scorer/tagger/captioner)"""
        mock_lib = MockAnnotatorLibrary()
        infos = mock_lib.list_annotator_info()

        types = {info.model_type for info in infos}
        assert "vision" in types
        assert "tagger" in types
        assert "scorer" in types  # Issue #19 P1 fix で "score" → "scorer"

    def test_get_model_extras_returns_registered_extras(self):
        """登録済みモデルは適切な extras を返す"""
        mock_lib = MockAnnotatorLibrary()

        gpt_extras = mock_lib.get_model_extras("gpt-4o")
        assert gpt_extras.provider == "openai"
        assert gpt_extras.class_name == "PydanticAIWebAPIAnnotator"
        assert gpt_extras.api_model_id == "gpt-4o"

        wd_extras = mock_lib.get_model_extras("wd-v1-4-swinv2-tagger")
        assert wd_extras.provider is None
        assert wd_extras.class_name == "WDTagger"
        assert wd_extras.estimated_size_gb == 1.2

    def test_get_model_extras_unknown_returns_all_none(self):
        """未登録モデルは全 None の AnnotatorExtras を返す"""
        mock_lib = MockAnnotatorLibrary()
        extras = mock_lib.get_model_extras("nonexistent-model")

        assert extras.provider is None
        assert extras.class_name is None
        assert extras.api_model_id is None
        assert extras.estimated_size_gb is None
        assert extras.discontinued_at is None
        assert extras.max_output_tokens is None


class TestModelTypeMapping:
    """ModelTypeマッピングロジックテスト (Issue #225 で AnnotatorInfo 引数に変更)"""

    @pytest.fixture
    def service_with_mock(self, temp_db_repository, mock_config_service):
        """マッピングテスト用サービス"""
        return ModelSyncService(
            db_repository=temp_db_repository, config_service=mock_config_service, annotator_library=Mock()
        )

    def test_vision_api_maps_to_llm_captioner(self, service_with_mock):
        """vision タイプの WebAPI モデルは ['llm', 'captioner'] にマッピングされる"""
        info = _info(
            "gpt-4o", "vision", is_api=True, capabilities={TaskCapability.TAGS, TaskCapability.CAPTIONS}
        )
        assert service_with_mock._map_library_model_type_to_db(info) == ["llm", "captioner"]

    def test_vision_local_maps_to_captioner(self, service_with_mock):
        """vision タイプのローカルモデルは ['captioner'] にマッピングされる"""
        info = _info("local-vision", "vision", is_api=False, capabilities={TaskCapability.CAPTIONS})
        assert service_with_mock._map_library_model_type_to_db(info) == ["captioner"]

    def test_captioner_maps_to_captioner(self, service_with_mock):
        """captioner タイプは ['captioner'] にマッピングされる"""
        info = _info("blip-captioner", "captioner", is_api=False, capabilities={TaskCapability.CAPTIONS})
        assert service_with_mock._map_library_model_type_to_db(info) == ["captioner"]

    def test_scorer_maps_to_score(self, service_with_mock):
        """scorer タイプは ['score'] にマッピングされる (DB 側カラム名整合)"""
        info = _info("aesthetic", "scorer", is_api=False, capabilities={TaskCapability.SCORES})
        assert service_with_mock._map_library_model_type_to_db(info) == ["score"]

    def test_tagger_maps_to_tagger(self, service_with_mock):
        """tagger タイプは ['tagger'] にマッピングされる"""
        info = _info("wd-tagger", "tagger", is_api=False, capabilities={TaskCapability.TAGS})
        assert service_with_mock._map_library_model_type_to_db(info) == ["tagger"]

    def test_unknown_type_falls_back_to_captioner(self, service_with_mock):
        """未知のタイプは ['captioner'] にフォールバック (警告ログ付き)"""
        # AnnotatorInfo の Literal を回避するため type: ignore 経由で生成
        info = AnnotatorInfo(
            name="weird",
            model_type="weird-type",  # type: ignore[arg-type]
            capabilities=frozenset({TaskCapability.TAGS}),
            is_local=True,
            is_api=False,
            device="cuda",
        )
        assert service_with_mock._map_library_model_type_to_db(info) == ["captioner"]


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
        assert gpt4o_model["provider"] == "openai"
        assert gpt4o_model["class_name"] == "PydanticAIWebAPIAnnotator"

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

        assert count == 2

        registered_model_1 = temp_db_repository.get_model_by_name("test-model-new-1")
        assert registered_model_1 is not None
        assert registered_model_1.provider == "openai"
        assert len(registered_model_1.model_types) == 2
        assert {mt.name for mt in registered_model_1.model_types} == {"llm", "captioner"}

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

        registered_model = temp_db_repository.get_model_by_name("discontinued-model")
        assert registered_model is not None
        assert registered_model.discontinued_at is not None
        assert registered_model.discontinued_at == discontinued_date.replace(tzinfo=None)

    def test_register_new_models_existing_models_skip(self, model_sync_service, temp_db_repository):
        """既存モデル存在時のDB登録スキップ"""
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
        assert count == 0

    def test_update_existing_models_success(self, model_sync_service, temp_db_repository):
        """既存モデル更新処理（実DB操作）"""
        temp_db_repository.insert_model(
            name="update-test-model", provider="openai", model_types=["captioner"], estimated_size_gb=1.0
        )

        test_models: list[ModelMetadata] = [
            {
                "name": "update-test-model",
                "provider": "openai",
                "class_name": "UpdatedAnnotator",
                "api_model_id": "updated",
                "model_type": "vision",
                "model_types": ["llm", "captioner"],
                "estimated_size_gb": 2.5,
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        count = model_sync_service.update_existing_models(test_models)
        assert count == 1

        updated_model = temp_db_repository.get_model_by_name("update-test-model")
        assert updated_model is not None
        assert updated_model.estimated_size_gb == 2.5
        assert len(updated_model.model_types) == 2
        assert {mt.name for mt in updated_model.model_types} == {"llm", "captioner"}

    def test_update_existing_models_no_changes(self, model_sync_service, temp_db_repository):
        """既存モデル更新処理（変更なし）"""
        temp_db_repository.insert_model(
            name="no-change-model", provider="openai", model_types=["llm"], estimated_size_gb=1.0
        )

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
        assert count == 0

    def test_update_existing_models_with_discontinued_at(self, model_sync_service, temp_db_repository):
        """既存モデルのdiscontinued_at更新（Issue #5対応）"""
        temp_db_repository.insert_model(
            name="to-be-discontinued", provider="openai", model_types=["captioner"], discontinued_at=None
        )

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

        updated_model = temp_db_repository.get_model_by_name("to-be-discontinued")
        assert updated_model is not None
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
        """モデル同期処理エラー発生 (新 Protocol: list_annotator_info で例外)"""
        error_lib = Mock(spec=AnnotatorLibraryProtocol)
        error_lib.list_annotator_info.side_effect = Exception("Sync error")

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
        """アノテーションモデルタイプの妥当性検証 (post Issue #19 値)"""
        assert model_sync_service.validate_annotation_model_type("vision") is True
        assert model_sync_service.validate_annotation_model_type("scorer") is True
        assert model_sync_service.validate_annotation_model_type("tagger") is True
        assert model_sync_service.validate_annotation_model_type("captioner") is True
        # 旧値 "score" は invalid (Issue #19 で "scorer" に統一)
        assert model_sync_service.validate_annotation_model_type("score") is False
        assert model_sync_service.validate_annotation_model_type("upscaler") is False
        assert model_sync_service.validate_annotation_model_type("unknown") is False


class TestModelSyncServiceEdgeCases:
    """ModelSyncService 境界値・エッジケーステスト"""

    @pytest.fixture
    def model_sync_service(self, temp_db_repository, mock_config_service):
        """ModelSyncService インスタンス（実DB使用）"""
        return ModelSyncService(db_repository=temp_db_repository, config_service=mock_config_service)

    def test_empty_model_list_sync(self, temp_db_repository, mock_config_service):
        """空のモデルリスト同期 (新 Protocol: list_annotator_info が空リスト)"""
        empty_lib = Mock(spec=AnnotatorLibraryProtocol)
        empty_lib.list_annotator_info.return_value = []
        empty_lib.get_model_extras.return_value = AnnotatorExtras(
            provider=None,
            class_name=None,
            api_model_id=None,
            estimated_size_gb=None,
            discontinued_at=None,
            max_output_tokens=None,
        )

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
        invalid_models: list[ModelMetadata] = [
            {
                "name": "",  # 空の名前
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": None,
                "model_type": "unknown",
                "model_types": ["captioner"],
                "estimated_size_gb": -1.0,
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        # 例外が発生せずに処理されることを確認
        count = model_sync_service.register_new_models_to_db(invalid_models)
        assert count >= 0
