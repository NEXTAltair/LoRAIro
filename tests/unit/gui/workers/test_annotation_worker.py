"""AnnotationWorkerユニットテスト

Phase 7で再設計された3層アーキテクチャに対応:
- AnnotationLogic依存注入
- image_paths/modelsインターフェース
- 進捗報告・キャンセル処理
- AnnotationExecutionResult サマリー付き戻り値
- Issue #225: model_registry 注入
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lorairo.gui.workers.annotation_worker import (
    AnnotationExecutionResult,
    AnnotationWorker,
)


@pytest.fixture
def mock_annotation_logic():
    """AnnotationLogicのモック"""
    logic = Mock()
    logic.execute_annotation.return_value = {
        "test_phash": {
            "gpt-4o-mini": {
                "tags": ["cat", "animal"],
                "formatted_output": {"captions": ["A cat"]},
                "error": None,
            }
        }
    }
    return logic


@pytest.fixture
def mock_model_registry():
    """ModelRegistryServiceProtocol のモック (Issue #225)"""
    registry = Mock()
    registry.get_available_models.return_value = []
    return registry


class TestAnnotationWorkerInitialization:
    """AnnotationWorker初期化テスト"""

    def test_initialization_with_annotation_logic(self, mock_annotation_logic, mock_model_registry):
        """正常な初期化テスト"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini"]
        mock_db_manager = Mock()

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
            model_registry=mock_model_registry,
        )

        assert worker.annotation_logic is mock_annotation_logic
        assert worker.image_paths == image_paths
        assert worker.models == models
        assert worker.db_manager is mock_db_manager
        assert worker.model_registry is mock_model_registry


class TestAnnotationWorkerExecute:
    """AnnotationWorker execute()テスト"""

    def test_execute_success_single_model(self, mock_annotation_logic, mock_model_registry):
        """単一モデルでの正常実行"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini"]

        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"test_phash": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {"gpt-4o-mini": Mock(id=1)}
        mock_db_manager.repository.save_annotations = Mock()

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
            model_registry=mock_model_registry,
        )

        result = worker.execute()

        mock_annotation_logic.execute_annotation.assert_called_once_with(
            image_paths=image_paths,
            model_names=["gpt-4o-mini"],
            phash_list=None,
        )

        assert isinstance(result, AnnotationExecutionResult)
        assert "test_phash" in result.results
        assert "gpt-4o-mini" in result.results["test_phash"]
        assert result.total_images == 2
        assert result.models_used == ["gpt-4o-mini"]
        assert result.db_save_success == 1
        assert result.model_errors == []

    def test_execute_success_multiple_models(self, mock_annotation_logic, mock_model_registry):
        """複数モデルでの正常実行（結果マージ確認）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"phash1": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {
            "gpt-4o-mini": Mock(id=1),
            "claude-3-haiku-20240307": Mock(id=2),
        }
        mock_db_manager.repository.save_annotations = Mock()

        mock_annotation_logic.execute_annotation.side_effect = [
            {
                "phash1": {
                    "gpt-4o-mini": {
                        "tags": ["cat"],
                        "formatted_output": {},
                        "error": None,
                    }
                }
            },
            {
                "phash1": {
                    "claude-3-haiku-20240307": {
                        "tags": ["feline"],
                        "formatted_output": {},
                        "error": None,
                    }
                }
            },
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
            model_registry=mock_model_registry,
        )

        result = worker.execute()

        assert mock_annotation_logic.execute_annotation.call_count == 2

        assert isinstance(result, AnnotationExecutionResult)
        assert "phash1" in result.results
        assert "gpt-4o-mini" in result.results["phash1"]
        assert "claude-3-haiku-20240307" in result.results["phash1"]
        assert result.total_images == 1
        assert result.models_used == ["gpt-4o-mini", "claude-3-haiku-20240307"]

    def test_execute_model_error_partial_success(self, mock_annotation_logic, mock_model_registry):
        """モデルエラー時の部分的成功"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307", "gemini-1.5-flash-latest"]

        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"phash1": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {
            "gpt-4o-mini": Mock(id=1),
            "gemini-1.5-flash-latest": Mock(id=3),
        }
        mock_db_manager.repository.save_annotations = Mock()
        mock_db_manager.get_image_id_by_filepath.return_value = 1

        mock_annotation_logic.execute_annotation.side_effect = [
            {"phash1": {"gpt-4o-mini": {"tags": ["cat"], "formatted_output": {}, "error": None}}},
            RuntimeError("API Error"),
            {
                "phash1": {
                    "gemini-1.5-flash-latest": {"tags": ["animal"], "formatted_output": {}, "error": None}
                }
            },
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
            model_registry=mock_model_registry,
        )

        result = worker.execute()

        assert mock_annotation_logic.execute_annotation.call_count == 3

        assert isinstance(result, AnnotationExecutionResult)
        assert "phash1" in result.results
        assert "gpt-4o-mini" in result.results["phash1"]
        assert "claude-3-haiku-20240307" not in result.results["phash1"]
        assert "gemini-1.5-flash-latest" in result.results["phash1"]

        assert len(result.model_errors) == 1
        assert result.model_errors[0].model_name == "claude-3-haiku-20240307"
        assert "API Error" in result.model_errors[0].error_message

    def test_execute_all_models_fail(self, mock_annotation_logic, mock_model_registry):
        """全モデルエラー時（空結果）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {}
        mock_db_manager.repository.get_models_by_names.return_value = {}
        mock_db_manager.repository.save_annotations = Mock()
        mock_db_manager.get_image_id_by_filepath.return_value = 1

        mock_annotation_logic.execute_annotation.side_effect = [
            RuntimeError("API Error 1"),
            RuntimeError("API Error 2"),
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
            model_registry=mock_model_registry,
        )

        result = worker.execute()

        assert isinstance(result, AnnotationExecutionResult)
        assert result.results == {}
        assert result.total_images == 1
        assert result.db_save_success == 0

        assert len(result.model_errors) == 2

    def test_save_uses_batch_queries(self, mock_annotation_logic, mock_model_registry):
        """DB保存がバッチクエリを使用すること（個別phashルックアップなし）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini"]

        mock_model = Mock(id=1)
        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"test_phash": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {"gpt-4o-mini": mock_model}
        mock_db_manager.repository.save_annotations = Mock()

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
            model_registry=mock_model_registry,
        )

        worker.execute()

        assert mock_db_manager.repository.find_image_ids_by_phashes.call_count == 2
        mock_db_manager.repository.get_models_by_names.assert_called_once()
        mock_db_manager.repository.find_duplicate_image_by_phash.assert_not_called()
        mock_db_manager.repository.get_model_by_name.assert_not_called()


# ==============================================================================
# Test _extract_field
# ==============================================================================


class TestExtractField:
    """_extract_fieldの辞書/Pydanticモデル両対応テスト"""

    def test_extract_field_from_dict(self, mock_annotation_logic, mock_model_registry):
        """辞書からフィールドを取得できる。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
            model_registry=mock_model_registry,
        )
        data = {"tags": ["cat", "dog"], "error": None}
        assert worker._extract_field(data, "tags") == ["cat", "dog"]
        assert worker._extract_field(data, "error") is None
        assert worker._extract_field(data, "nonexistent") is None

    def test_extract_field_from_object(self, mock_annotation_logic, mock_model_registry):
        """オブジェクトからフィールドを取得できる。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
            model_registry=mock_model_registry,
        )
        obj = SimpleNamespace(tags=["cat"], scores={"aesthetic": 0.9}, error=None)
        assert worker._extract_field(obj, "tags") == ["cat"]
        assert worker._extract_field(obj, "scores") == {"aesthetic": 0.9}
        assert worker._extract_field(obj, "nonexistent") is None


# ==============================================================================
# Test _save_error_records
# ==============================================================================


class TestSaveErrorRecords:
    """_save_error_recordsのエッジケーステスト"""

    def test_save_error_records_empty_paths(self, mock_annotation_logic, mock_model_registry):
        """空のimage_pathsでは何も保存されない。"""
        mock_db = Mock()
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=mock_db,
            model_registry=mock_model_registry,
        )
        worker._save_error_records(Exception("test"), [], model_name="test-model")
        mock_db.save_error_record.assert_not_called()

    def test_save_error_records_with_none_image_id(self, mock_annotation_logic, mock_model_registry):
        """image_idがNoneでもエラーレコードは保存される。"""
        mock_db = Mock()
        mock_db.get_image_id_by_filepath.return_value = None
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=["/test/img.jpg"],
            models=[],
            db_manager=mock_db,
            model_registry=mock_model_registry,
        )
        worker._save_error_records(ValueError("err"), ["/test/img.jpg"], model_name="m1")
        mock_db.save_error_record.assert_called_once()
        call_kwargs = mock_db.save_error_record.call_args.kwargs
        assert call_kwargs["image_id"] is None
        assert call_kwargs["model_name"] == "m1"
        assert call_kwargs["error_type"] == "ValueError"

    def test_save_error_records_secondary_error_continues(self, mock_annotation_logic, mock_model_registry):
        """二次エラーが発生しても残りのパスの処理が続行される。"""
        mock_db = Mock()
        mock_db.get_image_id_by_filepath.side_effect = [RuntimeError("db error"), 42]
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=["/img1.jpg", "/img2.jpg"],
            models=[],
            db_manager=mock_db,
            model_registry=mock_model_registry,
        )
        worker._save_error_records(Exception("test"), ["/img1.jpg", "/img2.jpg"])
        assert mock_db.save_error_record.call_count == 1

    def test_save_error_records_model_name_none_for_overall_error(
        self, mock_annotation_logic, mock_model_registry
    ):
        """全体エラー時にmodel_name=Noneで保存される。"""
        mock_db = Mock()
        mock_db.get_image_id_by_filepath.return_value = 1
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=["/test/img.jpg"],
            models=[],
            db_manager=mock_db,
            model_registry=mock_model_registry,
        )
        worker._save_error_records(Exception("overall"), ["/test/img.jpg"], model_name=None)
        call_kwargs = mock_db.save_error_record.call_args.kwargs
        assert call_kwargs["model_name"] is None
