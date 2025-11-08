"""AnnotationServiceユニットテスト

Phase 4-3: start_single_annotation()実装のテスト
ServiceContainer統合とAnnotatorLibraryAdapter呼び出しを検証
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QObject

from lorairo.services.annotation_service import AnnotationService


@pytest.fixture
def mock_container():
    """ServiceContainerのモックフィクスチャ"""
    container = MagicMock()

    # annotator_libraryモック
    mock_annotator = MagicMock()
    mock_annotator.annotate.return_value = {
        "test_phash": {
            "gpt-4o": {
                "tags": ["cat", "animal"],
                "formatted_output": {"captions": ["A cat sitting"]},
                "error": None,
            }
        }
    }
    container.annotator_library = mock_annotator

    # model_registryモック
    mock_registry = MagicMock()
    mock_model = MagicMock()
    mock_model.name = "gpt-4o"
    mock_model.provider = "openai"
    mock_model.capabilities = ["tagging"]
    mock_model.api_model_id = "gpt-4o"
    mock_model.requires_api_key = True
    mock_model.estimated_size_gb = 0.0
    mock_registry.get_available_models.return_value = [mock_model]
    container.model_registry = mock_registry

    # model_sync_serviceモック
    mock_sync_service = MagicMock()
    mock_sync_service.get_library_models_summary.return_value = {}
    mock_sync_service.sync_available_models.return_value = MagicMock(
        success=True, summary="Test sync", errors=[]
    )
    container.model_sync_service = mock_sync_service

    # batch_processorモック
    mock_batch_processor = MagicMock()
    container.batch_processor = mock_batch_processor

    container.get_service_summary.return_value = {"test": "summary"}

    return container


@pytest.fixture
def annotation_service(mock_container):
    """AnnotationServiceフィクスチャ"""
    with patch("lorairo.services.annotation_service.get_service_container", return_value=mock_container):
        service = AnnotationService()
        return service


class TestAnnotationService:
    """AnnotationServiceユニットテスト"""

    def test_initialization(self, annotation_service, mock_container):
        """初期化テスト"""
        assert annotation_service.container == mock_container
        assert annotation_service._last_annotation_result is None
        assert annotation_service._last_batch_result is None

    def test_start_single_annotation_success(self, annotation_service, mock_container):
        """単発アノテーション成功テスト"""
        # テストデータ準備
        test_image = Image.new("RGB", (100, 100))
        images = [test_image]
        phash_list = ["test_phash"]
        models = ["gpt-4o"]

        # シグナルスパイ
        signal_results = []

        def capture_signal(result):
            signal_results.append(result)

        annotation_service.annotationFinished.connect(capture_signal)

        # 実行
        annotation_service.start_single_annotation(images, phash_list, models)

        # 検証
        mock_container.annotator_library.annotate.assert_called_once_with(
            images=images,
            model_names=models,
            phash_list=phash_list,
        )

        # シグナル発火確認
        assert len(signal_results) == 1
        assert "test_phash" in signal_results[0]

        # 最終結果保存確認
        assert annotation_service.get_last_annotation_result() is not None

    def test_start_single_annotation_no_images(self, annotation_service):
        """画像なしエラーテスト"""
        error_messages = []

        def capture_error(msg):
            error_messages.append(msg)

        annotation_service.annotationError.connect(capture_error)

        # 実行
        annotation_service.start_single_annotation([], [], ["gpt-4o"])

        # 検証
        assert len(error_messages) == 1
        assert "入力画像がありません" in error_messages[0]

    def test_start_single_annotation_no_models(self, annotation_service):
        """モデルなしエラーテスト"""
        error_messages = []

        def capture_error(msg):
            error_messages.append(msg)

        annotation_service.annotationError.connect(capture_error)

        # 実行
        test_image = Image.new("RGB", (100, 100))
        annotation_service.start_single_annotation([test_image], ["phash"], [])

        # 検証
        assert len(error_messages) == 1
        assert "モデルが選択されていません" in error_messages[0]

    def test_start_single_annotation_phash_mismatch(self, annotation_service):
        """pHash数不一致エラーテスト"""
        error_messages = []

        def capture_error(msg):
            error_messages.append(msg)

        annotation_service.annotationError.connect(capture_error)

        # 実行
        test_image = Image.new("RGB", (100, 100))
        annotation_service.start_single_annotation(
            [test_image],
            ["phash1", "phash2"],
            ["gpt-4o"],  # 画像1枚、phash 2個
        )

        # 検証
        assert len(error_messages) == 1
        assert "画像とpHashの数が一致しません" in error_messages[0]

    def test_start_single_annotation_adapter_error(self, annotation_service, mock_container):
        """AnnotatorLibraryAdapterエラーテスト"""
        # モックでエラー発生
        mock_container.annotator_library.annotate.side_effect = Exception("Annotation error")

        error_messages = []

        def capture_error(msg):
            error_messages.append(msg)

        annotation_service.annotationError.connect(capture_error)

        # 実行
        test_image = Image.new("RGB", (100, 100))
        annotation_service.start_single_annotation([test_image], ["phash"], ["gpt-4o"])

        # 検証
        assert len(error_messages) == 1
        assert "Annotation error" in error_messages[0]

    def test_get_available_models(self, annotation_service, mock_container):
        """利用可能モデル取得テスト"""
        models = annotation_service.get_available_models()

        assert len(models) == 1
        assert models[0]["name"] == "gpt-4o"
        assert models[0]["provider"] == "openai"
        assert models[0]["requires_api_key"] is True

    def test_fetch_available_annotators(self, annotation_service):
        """利用可能アノテーター取得テスト（互換性メソッド）"""
        signal_results = []

        def capture_signal(result):
            signal_results.append(result)

        annotation_service.availableAnnotatorsFetched.connect(capture_signal)

        # 実行
        annotation_service.fetch_available_annotators()

        # 検証
        assert len(signal_results) == 1
        assert "gpt-4o" in signal_results[0]

    def test_sync_available_models_success(self, annotation_service, mock_container):
        """モデル同期成功テスト"""
        signal_results = []

        def capture_signal(result):
            signal_results.append(result)

        annotation_service.modelSyncCompleted.connect(capture_signal)

        # 実行
        annotation_service.sync_available_models()

        # 検証
        mock_container.model_sync_service.sync_available_models.assert_called_once()
        assert len(signal_results) == 1
        assert signal_results[0].success is True

    def test_sync_available_models_error(self, annotation_service, mock_container):
        """モデル同期エラーテスト"""
        # モックで失敗結果
        mock_container.model_sync_service.sync_available_models.return_value = MagicMock(
            success=False, summary="Failed", errors=["Test error"]
        )

        error_messages = []

        def capture_error(msg):
            error_messages.append(msg)

        annotation_service.annotationError.connect(capture_error)

        # 実行
        annotation_service.sync_available_models()

        # 検証
        assert len(error_messages) == 1
        assert "Test error" in error_messages[0]

    def test_get_service_status(self, annotation_service):
        """サービス状況取得テスト"""
        status = annotation_service.get_service_status()

        assert status["service_name"] == "AnnotationService"
        assert "Phase 2" in status["phase"]
        assert "container_summary" in status
        assert status["last_results"]["has_annotation_result"] is False
        assert status["last_results"]["has_batch_result"] is False
