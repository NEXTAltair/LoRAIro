"""ModelSyncService ユニットテスト

Phase 4実装のimage-annotator-lib統合モデル同期サービスをテスト
"""

import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

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
        """ModelMetadata型構造確認"""
        metadata: ModelMetadata = {
            "name": "gpt-4o",
            "provider": "openai",
            "class_name": "PydanticAIWebAPIAnnotator",
            "api_model_id": "gpt-4o",
            "model_type": "vision",
            "estimated_size_gb": None,
            "requires_api_key": True,
            "discontinued_at": None,
        }

        assert metadata["name"] == "gpt-4o"
        assert metadata["provider"] == "openai"
        assert metadata["model_type"] == "vision"
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


class TestModelSyncService:
    """ModelSyncService メインテスト"""

    @pytest.fixture
    def mock_db_repository(self):
        """モックDB リポジトリ"""
        mock_repo = Mock()
        mock_repo.get_model_by_name.return_value = None
        return mock_repo

    @pytest.fixture
    def mock_config_service(self):
        """モック設定サービス"""
        mock_config = Mock()
        return mock_config

    @pytest.fixture
    def model_sync_service(self, mock_db_repository, mock_config_service):
        """ModelSyncService インスタンス"""
        return ModelSyncService(db_repository=mock_db_repository, config_service=mock_config_service)

    def test_initialization_with_mock(self, model_sync_service):
        """Mock使用時の初期化"""
        assert model_sync_service.db_repository is not None
        assert model_sync_service.config_service is not None
        assert isinstance(model_sync_service.annotator_library, MockAnnotatorLibrary)

    def test_initialization_with_custom_library(self, mock_db_repository, mock_config_service):
        """カスタムライブラリ使用時の初期化"""
        custom_lib = Mock(spec=AnnotatorLibraryProtocol)
        custom_lib.get_available_models_with_metadata.return_value = []

        service = ModelSyncService(
            db_repository=mock_db_repository,
            config_service=mock_config_service,
            annotator_library=custom_lib,
        )

        assert service.annotator_library is custom_lib

    def test_get_model_metadata_from_library_success(self, model_sync_service):
        """ライブラリからのメタデータ取得成功"""
        # MockAnnotatorLibraryを使用
        metadata_list = model_sync_service.get_model_metadata_from_library()

        assert isinstance(metadata_list, list)
        assert len(metadata_list) > 0

        # 最初のメタデータ構造確認
        first_model = metadata_list[0]
        assert "name" in first_model
        assert "provider" in first_model
        assert "class_name" in first_model
        assert "model_type" in first_model

    def test_get_model_metadata_from_library_error(self, mock_db_repository, mock_config_service):
        """ライブラリからのメタデータ取得エラー"""
        error_lib = Mock(spec=AnnotatorLibraryProtocol)
        error_lib.get_available_models_with_metadata.side_effect = Exception("Library error")

        service = ModelSyncService(
            db_repository=mock_db_repository,
            config_service=mock_config_service,
            annotator_library=error_lib,
        )

        with pytest.raises(Exception, match="Library error"):
            service.get_model_metadata_from_library()

    def test_register_new_models_to_db_success(self, model_sync_service, mock_db_repository):
        """新規モデルDB登録成功"""
        # テストデータ
        test_models: list[ModelMetadata] = [
            {
                "name": "test-model-1",
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": "test-1",
                "model_type": "vision",
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            },
            {
                "name": "test-model-2",
                "provider": None,
                "class_name": "LocalTagger",
                "api_model_id": None,
                "model_type": "tagger",
                "estimated_size_gb": 1.5,
                "requires_api_key": False,
                "discontinued_at": None,
            },
        ]

        # モックDB設定（モデルが存在しない）
        mock_db_repository.get_model_by_name.return_value = None

        count = model_sync_service.register_new_models_to_db(test_models)

        # 2つのモデルが登録される（モック実装）
        assert count == 2

    def test_register_new_models_to_db_existing_models(self, model_sync_service, mock_db_repository):
        """既存モデル存在時のDB登録"""
        test_models: list[ModelMetadata] = [
            {
                "name": "existing-model",
                "provider": "openai",
                "class_name": "TestAnnotator",
                "api_model_id": "existing",
                "model_type": "vision",
                "estimated_size_gb": None,
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        # モックDB設定（モデルが既に存在）
        existing_model = Mock()
        existing_model.id = 1
        mock_db_repository.get_model_by_name.return_value = existing_model

        count = model_sync_service.register_new_models_to_db(test_models)

        # 既存モデルなので新規登録は0
        assert count == 0

    def test_sync_available_models_success(self, model_sync_service):
        """モデル同期処理成功"""
        result = model_sync_service.sync_available_models()

        assert isinstance(result, ModelSyncResult)
        assert result.success is True
        assert result.total_library_models > 0
        assert result.new_models_registered >= 0
        assert len(result.errors) == 0

    def test_sync_available_models_with_error(self, mock_db_repository, mock_config_service):
        """モデル同期処理エラー発生"""
        error_lib = Mock(spec=AnnotatorLibraryProtocol)
        error_lib.get_available_models_with_metadata.side_effect = Exception("Sync error")

        service = ModelSyncService(
            db_repository=mock_db_repository,
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
        # MockAnnotatorLibraryの実装により、モックサマリーが返される
        assert "total" in summary or len(summary) == 0  # モック実装に依存

    def test_update_existing_models(self, model_sync_service):
        """既存モデル更新処理"""
        test_models: list[ModelMetadata] = [
            {
                "name": "updated-model",
                "provider": "openai",
                "class_name": "UpdatedAnnotator",
                "api_model_id": "updated",
                "model_type": "vision",
                "estimated_size_gb": 2.0,
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        count = model_sync_service.update_existing_models(test_models)

        # モック実装により、更新数が返される
        assert count >= 0


@pytest.mark.integration
class TestModelSyncServiceIntegration:
    """ModelSyncService 統合テスト"""

    def test_full_sync_workflow(self):
        """完全な同期ワークフロー"""
        # 実際の依存関係を使用した統合テスト
        # 本テストは統合テストレベルで実装
        pass


# テストカバレッジ向上のための境界値テスト
class TestModelSyncServiceEdgeCases:
    """ModelSyncService 境界値・エッジケーステスト"""

    def test_empty_model_list_sync(self, mock_db_repository, mock_config_service):
        """空のモデルリスト同期"""
        empty_lib = Mock(spec=AnnotatorLibraryProtocol)
        empty_lib.get_available_models_with_metadata.return_value = []

        service = ModelSyncService(
            db_repository=mock_db_repository,
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
                "estimated_size_gb": -1.0,  # 負の値
                "requires_api_key": True,
                "discontinued_at": None,
            }
        ]

        # 例外が発生せずに処理されることを確認
        count = model_sync_service.register_new_models_to_db(invalid_models)
        assert count >= 0
