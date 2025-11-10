"""AnnotationWorkerユニットテスト

バッチアノテーション処理の新設計に対応したテスト
- api_keysパラメータ対応
- モデルループ処理
- キャンセル処理
- 直接annotate()呼び出し
"""

from unittest.mock import MagicMock, call, patch

import pytest
from PIL import Image

from lorairo.gui.workers.annotation_worker import AnnotationWorker


class TestAnnotationWorkerInitialization:
    """AnnotationWorker初期化テスト"""

    def test_initialization_single_mode_with_api_keys(self) -> None:
        """初期化テスト（単発モード + APIキー）"""
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        phash_list = ["test_phash"]
        models = ["gpt-4o"]
        api_keys = {"openai_key": "sk-test123", "claude_key": "sk-ant-test"}

        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = AnnotationWorker(
                images=images,
                phash_list=phash_list,
                models=models,
                operation_mode="single",
                api_keys=api_keys,
            )

            assert worker.operation_mode == "single"
            assert len(worker.images) == 1
            assert len(worker.phash_list) == 1
            assert len(worker.models) == 1
            assert worker.api_keys == api_keys

    def test_initialization_single_mode_without_api_keys(self) -> None:
        """初期化テスト（単発モード、APIキーなし）"""
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        phash_list = ["test_phash"]
        models = ["gpt-4o"]

        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = AnnotationWorker(
                images=images, phash_list=phash_list, models=models, operation_mode="single"
            )

            assert worker.api_keys == {}

    def test_initialization_batch_mode_with_api_keys(self):
        """初期化テスト（バッチモード + APIキー）"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o", "claude-3-haiku"]
        api_keys = {"openai_key": "sk-test", "claude_key": "sk-ant-test"}

        with patch("lorairo.gui.workers.annotation_worker.AnnotationService"):
            worker = AnnotationWorker(
                image_paths=image_paths,
                models=models,
                batch_size=50,
                operation_mode="batch",
                api_keys=api_keys,
            )

            assert worker.operation_mode == "batch"
            assert len(worker.image_paths) == 2
            assert worker.batch_size == 50
            assert len(worker.models) == 2
            assert worker.api_keys == api_keys


class TestAnnotationWorkerSingleMode:
    """AnnotationWorker単発モードテスト"""

    @patch("image_annotator_lib.annotate")
    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_execute_single_annotation_success(
        self, mock_service_class, mock_annotate
    ) -> None:
        """単発アノテーション実行成功テスト"""
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        phash_list = ["test_phash"]
        models = ["gpt-4o", "claude-3-haiku"]
        api_keys = {"openai_key": "sk-test"}

        # annotate()のモック戻り値（モデルごとに返す）
        mock_annotate.side_effect = [
            # gpt-4o の結果
            {
                "test_phash": {
                    "gpt-4o": {
                        "tags": ["cat", "animal"],
                        "formatted_output": {"captions": ["A cat"]},
                        "error": None,
                    }
                }
            },
            # claude-3-haiku の結果
            {
                "test_phash": {
                    "claude-3-haiku": {
                        "tags": ["feline", "pet"],
                        "formatted_output": {"captions": ["A feline"]},
                        "error": None,
                    }
                }
            },
        ]

        worker = AnnotationWorker(
            images=images,
            phash_list=phash_list,
            models=models,
            operation_mode="single",
            api_keys=api_keys,
        )

        # 実行
        result = worker.execute()

        # annotate()が2回（モデル数）呼ばれたことを確認
        assert mock_annotate.call_count == 2

        # 各呼び出しパラメータを確認
        calls = mock_annotate.call_args_list
        assert calls[0] == call(
            images_list=images, model_name_list=["gpt-4o"], phash_list=phash_list, api_keys=api_keys
        )
        assert calls[1] == call(
            images_list=images,
            model_name_list=["claude-3-haiku"],
            phash_list=phash_list,
            api_keys=api_keys,
        )

        # 結果がマージされていることを確認
        assert "test_phash" in result
        assert "gpt-4o" in result["test_phash"]
        assert "claude-3-haiku" in result["test_phash"]
        assert result["test_phash"]["gpt-4o"]["tags"] == ["cat", "animal"]
        assert result["test_phash"]["claude-3-haiku"]["tags"] == ["feline", "pet"]

    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_execute_single_annotation_no_images(self, mock_service_class):
        """画像なしエラーテスト"""
        worker = AnnotationWorker(images=[], models=["gpt-4o"], operation_mode="single")

        with pytest.raises(ValueError, match="単発モードで画像が指定されていません"):
            worker.execute()

    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_execute_single_annotation_no_models(self, mock_service_class):
        """モデルなしエラーテスト"""
        test_image = Image.new("RGB", (100, 100))

        worker = AnnotationWorker(images=[test_image], models=[], operation_mode="single")

        with pytest.raises(ValueError, match="モデルが選択されていません"):
            worker.execute()

    @patch("image_annotator_lib.annotate")
    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_execute_single_annotation_model_error_partial_success(
        self, mock_service_class, mock_annotate
    ):
        """モデルエラー時の部分的成功テスト"""
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        models = ["gpt-4o", "claude-3-haiku", "gemini-1.5-flash"]

        # 最初のモデルは成功、2番目は失敗、3番目は成功
        def annotate_side_effect(*args, **kwargs):
            model = kwargs["model_name_list"][0]
            if model == "claude-3-haiku":
                raise RuntimeError("API Error")
            return {
                "phash1": {
                    model: {"tags": [f"tag_{model}"], "formatted_output": {}, "error": None}
                }
            }

        mock_annotate.side_effect = annotate_side_effect

        worker = AnnotationWorker(images=images, models=models, operation_mode="single")

        # エラーでも処理継続（部分的成功を許容）
        result = worker.execute()

        # 3回呼ばれたことを確認
        assert mock_annotate.call_count == 3

        # 成功したモデルの結果のみ含まれる
        assert "phash1" in result
        assert "gpt-4o" in result["phash1"]
        assert "claude-3-haiku" not in result["phash1"]  # エラーで除外
        assert "gemini-1.5-flash" in result["phash1"]


class TestAnnotationWorkerBatchMode:
    """AnnotationWorkerバッチモードテスト"""

    @patch("image_annotator_lib.annotate")
    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    @patch("PIL.Image.open")
    def test_execute_batch_annotation_success(
        self, mock_pil_open, mock_service_class, mock_annotate
    ):
        """バッチアノテーション実行成功テスト"""
        image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        models = ["gpt-4o"]

        # PIL.Image.openのモック
        mock_image1 = MagicMock()
        mock_image2 = MagicMock()
        mock_pil_open.side_effect = [mock_image1, mock_image2]

        # annotate()のモック戻り値
        mock_annotate.return_value = {
            "phash1": {"gpt-4o": {"tags": ["cat"], "formatted_output": {}, "error": None}},
            "phash2": {"gpt-4o": {"tags": ["dog"], "formatted_output": {}, "error": None}},
        }

        worker = AnnotationWorker(image_paths=image_paths, models=models, operation_mode="batch")

        # 実行
        result = worker.execute()

        # PIL.Image.openが2回呼ばれたことを確認
        assert mock_pil_open.call_count == 2

        # annotate()が1回（モデル1つ）呼ばれたことを確認
        assert mock_annotate.call_count == 1

        # 結果確認
        assert "phash1" in result
        assert "phash2" in result

    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_execute_batch_annotation_no_paths(self, mock_service_class):
        """画像パスなしエラーテスト"""
        worker = AnnotationWorker(image_paths=[], models=["gpt-4o"], operation_mode="batch")

        with pytest.raises(ValueError, match="バッチモードで画像パスが指定されていません"):
            worker.execute()

    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    @patch("PIL.Image.open")
    def test_execute_batch_annotation_image_load_error(
        self, mock_pil_open, mock_service_class
    ):
        """画像読み込みエラーテスト"""
        image_paths = ["/path/to/bad_image.jpg"]

        # 画像読み込み失敗
        mock_pil_open.side_effect = Exception("File not found")

        worker = AnnotationWorker(image_paths=image_paths, models=["gpt-4o"], operation_mode="batch")

        # 読み込める画像がない場合はエラー
        with pytest.raises(RuntimeError, match="読み込める画像がありませんでした"):
            worker.execute()

    @patch("image_annotator_lib.annotate")
    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    @patch("PIL.Image.open")
    def test_execute_batch_annotation_multiple_models(
        self, mock_pil_open, mock_service_class, mock_annotate
    ):
        """複数モデルでのバッチアノテーションテスト"""
        image_paths = ["/path/to/image.jpg"]
        models = ["gpt-4o", "claude-3-haiku"]

        mock_image = MagicMock()
        mock_pil_open.return_value = mock_image

        # モデルごとの戻り値
        mock_annotate.side_effect = [
            {"phash1": {"gpt-4o": {"tags": ["cat"], "formatted_output": {}, "error": None}}},
            {
                "phash1": {
                    "claude-3-haiku": {"tags": ["feline"], "formatted_output": {}, "error": None}
                }
            },
        ]

        worker = AnnotationWorker(image_paths=image_paths, models=models, operation_mode="batch")

        result = worker.execute()

        # annotate()が2回呼ばれたことを確認
        assert mock_annotate.call_count == 2

        # 結果がマージされていることを確認
        assert "gpt-4o" in result["phash1"]
        assert "claude-3-haiku" in result["phash1"]


class TestAnnotationWorkerInfo:
    """AnnotationWorkerワーカー情報テスト"""

    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_get_worker_info_single_mode(self, mock_service_class):
        """ワーカー情報取得テスト（単発モード）"""
        worker = AnnotationWorker(
            images=[Image.new("RGB", (100, 100))], models=["gpt-4o"], operation_mode="single"
        )

        info = worker.get_worker_info()

        assert info["worker_type"] == "AnnotationWorker"
        assert info["operation_mode"] == "single"
        assert info["model_count"] == 1
        assert info["models"] == ["gpt-4o"]

    @patch("lorairo.gui.workers.annotation_worker.AnnotationService")
    def test_get_worker_info_batch_mode(self, mock_service_class):
        """ワーカー情報取得テスト（バッチモード）"""
        worker = AnnotationWorker(
            image_paths=["/test.jpg"], models=["gpt-4o", "claude-3-haiku"], operation_mode="batch"
        )

        info = worker.get_worker_info()

        assert info["worker_type"] == "AnnotationWorker"
        assert info["operation_mode"] == "batch"
        assert info["model_count"] == 2
        assert info["batch_size"] == 100  # デフォルト値
