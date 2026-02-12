"""AnnotationWorkerユニットテスト

Phase 7で再設計された3層アーキテクチャに対応:
- AnnotationLogic依存注入
- image_paths/modelsインターフェース
- 進捗報告・キャンセル処理
- AnnotationExecutionResult サマリー付き戻り値
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lorairo.gui.workers.annotation_worker import (
    AnnotationExecutionResult,
    AnnotationWorker,
    ModelErrorDetail,
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


class TestAnnotationWorkerInitialization:
    """AnnotationWorker初期化テスト"""

    def test_initialization_with_annotation_logic(self, mock_annotation_logic):
        """正常な初期化テスト"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini"]
        mock_db_manager = Mock()

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
        )

        assert worker.annotation_logic is mock_annotation_logic
        assert worker.image_paths == image_paths
        assert worker.models == models
        assert worker.db_manager is mock_db_manager


class TestAnnotationWorkerExecute:
    """AnnotationWorker execute()テスト"""

    def test_execute_success_single_model(self, mock_annotation_logic):
        """単一モデルでの正常実行"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o-mini"]

        # DB manager モック（バッチAPI対応）
        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"test_phash": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {"gpt-4o-mini": Mock(id=1)}
        mock_db_manager.repository.save_annotations = Mock()

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
        )

        result = worker.execute()

        # AnnotationLogic.execute_annotation()が呼ばれたことを確認
        mock_annotation_logic.execute_annotation.assert_called_once_with(
            image_paths=image_paths,
            model_names=["gpt-4o-mini"],
            phash_list=None,
        )

        # AnnotationExecutionResult が返されることを確認
        assert isinstance(result, AnnotationExecutionResult)
        assert "test_phash" in result.results
        assert "gpt-4o-mini" in result.results["test_phash"]
        assert result.total_images == 2
        assert result.models_used == ["gpt-4o-mini"]
        assert result.db_save_success == 1
        assert result.model_errors == []

    def test_execute_success_multiple_models(self, mock_annotation_logic):
        """複数モデルでの正常実行（結果マージ確認）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        # DB manager モック（バッチAPI対応）
        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"phash1": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {
            "gpt-4o-mini": Mock(id=1),
            "claude-3-haiku-20240307": Mock(id=2),
        }
        mock_db_manager.repository.save_annotations = Mock()

        # モデルごとの戻り値
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
        )

        result = worker.execute()

        # execute_annotation()が2回（モデル数）呼ばれたことを確認
        assert mock_annotation_logic.execute_annotation.call_count == 2

        # 結果がマージされていることを確認
        assert isinstance(result, AnnotationExecutionResult)
        assert "phash1" in result.results
        assert "gpt-4o-mini" in result.results["phash1"]
        assert "claude-3-haiku-20240307" in result.results["phash1"]
        assert result.total_images == 1
        assert result.models_used == ["gpt-4o-mini", "claude-3-haiku-20240307"]

    def test_execute_model_error_partial_success(self, mock_annotation_logic):
        """モデルエラー時の部分的成功"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307", "gemini-1.5-flash-latest"]

        # DB manager モック（バッチAPI対応）
        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {"phash1": 1}
        mock_db_manager.repository.get_models_by_names.return_value = {
            "gpt-4o-mini": Mock(id=1),
            "gemini-1.5-flash-latest": Mock(id=3),
        }
        mock_db_manager.repository.save_annotations = Mock()
        mock_db_manager.get_image_id_by_filepath.return_value = 1

        # 2番目のモデルでエラー
        mock_annotation_logic.execute_annotation.side_effect = [
            {"phash1": {"gpt-4o-mini": {"tags": ["cat"], "formatted_output": {}, "error": None}}},
            RuntimeError("API Error"),  # 2番目はエラー
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
        )

        # エラーでも処理継続（部分的成功を許容）
        result = worker.execute()

        # 3回呼ばれたことを確認
        assert mock_annotation_logic.execute_annotation.call_count == 3

        # 成功したモデルの結果のみ含まれる
        assert isinstance(result, AnnotationExecutionResult)
        assert "phash1" in result.results
        assert "gpt-4o-mini" in result.results["phash1"]
        assert "claude-3-haiku-20240307" not in result.results["phash1"]  # エラーで除外
        assert "gemini-1.5-flash-latest" in result.results["phash1"]

        # モデルエラーが記録されている
        assert len(result.model_errors) == 1  # 1画像 x 1エラーモデル
        assert result.model_errors[0].model_name == "claude-3-haiku-20240307"
        assert "API Error" in result.model_errors[0].error_message

    def test_execute_all_models_fail(self, mock_annotation_logic):
        """全モデルエラー時（空結果）"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o-mini", "claude-3-haiku-20240307"]

        # DB manager モック（バッチAPI対応）
        mock_db_manager = Mock()
        mock_db_manager.repository.find_image_ids_by_phashes.return_value = {}
        mock_db_manager.repository.get_models_by_names.return_value = {}
        mock_db_manager.repository.save_annotations = Mock()
        mock_db_manager.get_image_id_by_filepath.return_value = 1

        # 全てエラー
        mock_annotation_logic.execute_annotation.side_effect = [
            RuntimeError("API Error 1"),
            RuntimeError("API Error 2"),
        ]

        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=image_paths,
            models=models,
            db_manager=mock_db_manager,
        )

        # エラーでも例外は発生しない（空結果を返す）
        result = worker.execute()

        # 空の結果が返される
        assert isinstance(result, AnnotationExecutionResult)
        assert result.results == {}
        assert result.total_images == 1
        assert result.db_save_success == 0

        # 全モデルのエラーが記録されている
        assert len(result.model_errors) == 2  # 1画像 x 2エラーモデル

    def test_save_uses_batch_queries(self, mock_annotation_logic):
        """DB保存がバッチクエリを使用すること"""
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
        )

        worker.execute()

        # バッチメソッドが各1回だけ呼ばれること
        mock_db_manager.repository.find_image_ids_by_phashes.assert_called_once()
        mock_db_manager.repository.get_models_by_names.assert_called_once()
        # 旧個別メソッドは呼ばれないこと
        mock_db_manager.repository.find_duplicate_image_by_phash.assert_not_called()
        mock_db_manager.repository.get_model_by_name.assert_not_called()


# ==============================================================================
# Test _extract_field
# ==============================================================================


class TestExtractField:
    """_extract_fieldの辞書/Pydanticモデル両対応テスト"""

    def test_extract_field_from_dict(self, mock_annotation_logic):
        """辞書からフィールドを取得できる。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
        )
        data = {"tags": ["cat", "dog"], "error": None}
        assert worker._extract_field(data, "tags") == ["cat", "dog"]
        assert worker._extract_field(data, "error") is None
        assert worker._extract_field(data, "nonexistent") is None

    def test_extract_field_from_object(self, mock_annotation_logic):
        """オブジェクトからフィールドを取得できる。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
        )
        obj = SimpleNamespace(tags=["cat"], scores={"aesthetic": 0.9}, error=None)
        assert worker._extract_field(obj, "tags") == ["cat"]
        assert worker._extract_field(obj, "scores") == {"aesthetic": 0.9}
        assert worker._extract_field(obj, "nonexistent") is None


# ==============================================================================
# Test _extract_scores_from_formatted_output
# ==============================================================================


class TestExtractScoresFromFormattedOutput:
    """_extract_scores_from_formatted_outputのスコア抽出テスト"""

    def test_none_returns_none(self):
        """Noneの場合はNoneを返す。"""
        assert AnnotationWorker._extract_scores_from_formatted_output(None) is None

    def test_unified_result_with_scores(self):
        """scores属性を持つオブジェクトからスコア辞書を抽出できる。"""
        obj = SimpleNamespace(scores={"aesthetic": 5.2})
        result = AnnotationWorker._extract_scores_from_formatted_output(obj)
        assert result == {"aesthetic": 5.2}

    def test_dict_with_hq_key(self):
        """AestheticShadow形式のdict（hqキー）からaestheticスコアを抽出できる。"""
        data = {"hq": 0.85, "lq": 0.15}
        result = AnnotationWorker._extract_scores_from_formatted_output(data)
        assert result == {"aesthetic": 0.85}

    def test_float_value(self):
        """CafePredictor形式の単一float値からaestheticスコアを抽出できる。"""
        result = AnnotationWorker._extract_scores_from_formatted_output(0.67)
        assert result == {"aesthetic": 0.67}

    def test_int_value(self):
        """int値からaestheticスコアを抽出できる。"""
        result = AnnotationWorker._extract_scores_from_formatted_output(7)
        assert result == {"aesthetic": 7.0}

    def test_object_with_scores_none(self):
        """scores属性がNoneのオブジェクトはNoneを返す。"""
        obj = SimpleNamespace(scores=None)
        assert AnnotationWorker._extract_scores_from_formatted_output(obj) is None

    def test_unrelated_dict(self):
        """スコア関連キーを含まないdictはNoneを返す。"""
        data = {"tags": ["cat", "dog"]}
        assert AnnotationWorker._extract_scores_from_formatted_output(data) is None

    def test_string_returns_none(self):
        """文字列はNoneを返す。"""
        assert AnnotationWorker._extract_scores_from_formatted_output("some caption") is None


# ==============================================================================
# Test _convert_to_annotations_dict scorer fallback
# ==============================================================================


class TestConvertToAnnotationsDictScorerFallback:
    """_convert_to_annotations_dictのformatted_outputフォールバック動作テスト"""

    def test_scores_field_preferred_over_formatted_output(self, mock_annotation_logic):
        """scoresフィールドが存在する場合はformatted_outputより優先される。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
        )
        model = SimpleNamespace(id=1)
        annotations = {
            "test-model": {
                "scores": {"quality": 8.0},
                "formatted_output": SimpleNamespace(scores={"aesthetic": 5.0}),
                "tags": None,
                "captions": None,
                "ratings": None,
                "error": None,
            }
        }
        result = worker._convert_to_annotations_dict(annotations, {"test-model": model})
        assert len(result["scores"]) == 1
        assert result["scores"][0]["score"] == 8.0

    def test_formatted_output_fallback_for_pipeline_dict(self, mock_annotation_logic):
        """scoresがNoneの場合、formatted_outputのAestheticShadow形式dictからスコアを抽出する。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
        )
        model = SimpleNamespace(id=2)
        annotations = {
            "aesthetic-shadow": {
                "scores": None,
                "formatted_output": {"hq": 0.9, "lq": 0.1},
                "tags": None,
                "captions": None,
                "ratings": None,
                "error": None,
            }
        }
        result = worker._convert_to_annotations_dict(annotations, {"aesthetic-shadow": model})
        assert len(result["scores"]) == 1
        assert result["scores"][0]["model_id"] == 2
        assert result["scores"][0]["score"] == pytest.approx(0.9)

    def test_formatted_output_fallback_for_float(self, mock_annotation_logic):
        """scoresがNoneの場合、formatted_outputの単一float値からスコアを抽出する。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
        )
        model = SimpleNamespace(id=3)
        annotations = {
            "cafe-predictor": {
                "scores": None,
                "formatted_output": 0.67,
                "tags": None,
                "captions": None,
                "ratings": None,
                "error": None,
            }
        }
        result = worker._convert_to_annotations_dict(annotations, {"cafe-predictor": model})
        assert len(result["scores"]) == 1
        assert result["scores"][0]["model_id"] == 3
        assert result["scores"][0]["score"] == pytest.approx(0.67)

    def test_no_scores_no_formatted_output(self, mock_annotation_logic):
        """scoresもformatted_outputも無い場合はスコアが追加されない。"""
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=Mock(),
        )
        model = SimpleNamespace(id=4)
        annotations = {
            "tagger-model": {
                "scores": None,
                "formatted_output": None,
                "tags": ["cat", "dog"],
                "captions": None,
                "ratings": None,
                "error": None,
            }
        }
        result = worker._convert_to_annotations_dict(annotations, {"tagger-model": model})
        assert len(result["scores"]) == 0


# ==============================================================================
# Test _save_error_records
# ==============================================================================


class TestSaveErrorRecords:
    """_save_error_recordsのエッジケーステスト"""

    def test_save_error_records_empty_paths(self, mock_annotation_logic):
        """空のimage_pathsでは何も保存されない。"""
        mock_db = Mock()
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=[],
            models=[],
            db_manager=mock_db,
        )
        worker._save_error_records(Exception("test"), [], model_name="test-model")
        mock_db.save_error_record.assert_not_called()

    def test_save_error_records_with_none_image_id(self, mock_annotation_logic):
        """image_idがNoneでもエラーレコードは保存される。"""
        mock_db = Mock()
        mock_db.get_image_id_by_filepath.return_value = None
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=["/test/img.jpg"],
            models=[],
            db_manager=mock_db,
        )
        worker._save_error_records(ValueError("err"), ["/test/img.jpg"], model_name="m1")
        mock_db.save_error_record.assert_called_once()
        call_kwargs = mock_db.save_error_record.call_args.kwargs
        assert call_kwargs["image_id"] is None
        assert call_kwargs["model_name"] == "m1"
        assert call_kwargs["error_type"] == "ValueError"

    def test_save_error_records_secondary_error_continues(self, mock_annotation_logic):
        """二次エラーが発生しても残りのパスの処理が続行される。"""
        mock_db = Mock()
        mock_db.get_image_id_by_filepath.side_effect = [RuntimeError("db error"), 42]
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=["/img1.jpg", "/img2.jpg"],
            models=[],
            db_manager=mock_db,
        )
        # 例外が発生しないことを確認
        worker._save_error_records(Exception("test"), ["/img1.jpg", "/img2.jpg"])
        # 2回目のパスではsave_error_recordが呼ばれる
        assert mock_db.save_error_record.call_count == 1

    def test_save_error_records_model_name_none_for_overall_error(self, mock_annotation_logic):
        """全体エラー時にmodel_name=Noneで保存される。"""
        mock_db = Mock()
        mock_db.get_image_id_by_filepath.return_value = 1
        worker = AnnotationWorker(
            annotation_logic=mock_annotation_logic,
            image_paths=["/test/img.jpg"],
            models=[],
            db_manager=mock_db,
        )
        worker._save_error_records(Exception("overall"), ["/test/img.jpg"], model_name=None)
        call_kwargs = mock_db.save_error_record.call_args.kwargs
        assert call_kwargs["model_name"] is None
