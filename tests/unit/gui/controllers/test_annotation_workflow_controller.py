"""AnnotationWorkflowControllerの単体テスト

Phase 2.3で作成されたAnnotationWorkflowControllerのテスト。
DatasetControllerパターンに従ったアノテーションワークフロー制御を検証。
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from lorairo.gui.controllers.annotation_workflow_controller import (
    AnnotationWorkflowController,
)


@pytest.fixture
def mock_worker_service():
    """WorkerServiceのモック"""
    service = Mock()
    service.start_enhanced_batch_annotation = Mock(return_value="test_worker_id")
    return service


@pytest.fixture
def mock_selection_state_service():
    """SelectionStateServiceのモック"""
    service = Mock()
    service.get_selected_image_paths.return_value = [
        "/path/to/image1.jpg",
        "/path/to/image2.jpg",
    ]
    return service


@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモック"""
    service = Mock()
    service.get_api_keys.return_value = {
        "openai_key": "test-openai-key",
        "claude_key": "test-claude-key",
    }
    service.get_available_annotation_models.return_value = [
        "gpt-4o-mini",
        "gpt-4o",
        "claude-3-haiku-20240307",
        "claude-3-sonnet-20240229",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
    ]
    return service


@pytest.fixture
def mock_parent():
    """親ウィジェットのモック"""
    parent = Mock()
    return parent


@pytest.fixture
def controller(
    mock_worker_service,
    mock_selection_state_service,
    mock_config_service,
    mock_parent,
):
    """AnnotationWorkflowControllerインスタンス"""
    return AnnotationWorkflowController(
        worker_service=mock_worker_service,
        selection_state_service=mock_selection_state_service,
        config_service=mock_config_service,
        parent=mock_parent,
    )


class TestAnnotationWorkflowControllerInit:
    """初期化テスト"""

    def test_init(
        self,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
        mock_parent,
    ):
        """正常な初期化"""
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=mock_parent,
        )

        assert controller.worker_service is mock_worker_service
        assert controller.selection_state_service is mock_selection_state_service
        assert controller.config_service is mock_config_service
        assert controller.parent is mock_parent

    def test_init_without_parent(
        self, mock_worker_service, mock_selection_state_service, mock_config_service
    ):
        """親なしの初期化"""
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )

        assert controller.parent is None


class TestStartAnnotationWorkflow:
    """start_annotation_workflow()テスト"""

    def test_start_annotation_workflow_success(
        self,
        controller,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
    ):
        """正常なアノテーション開始"""

        # Setup - モデル選択callback
        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - SelectionStateService呼び出し確認
        mock_selection_state_service.get_selected_image_paths.assert_called_once()

        # Assert - WorkerService呼び出し確認
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()
        call_args = mock_worker_service.start_enhanced_batch_annotation.call_args
        assert call_args[1]["image_paths"] == [
            "/path/to/image1.jpg",
            "/path/to/image2.jpg",
        ]
        assert call_args[1]["models"] == ["gpt-4o-mini"]

    def test_start_annotation_workflow_no_images_selected(
        self,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
    ):
        """画像未選択エラー"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )
        mock_selection_state_service.get_selected_image_paths.side_effect = ValueError(
            "画像が選択されていません"
        )

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute & Assert
        # ValueError should be caught and handled gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - WorkerServiceは呼ばれない
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_model_selection_cancelled(self, controller, mock_worker_service):
        """モデル選択キャンセル"""

        # Setup - callback returns None (cancelled)
        def model_selection_callback(available_models: list[str]) -> str | None:
            return None

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - WorkerServiceは呼ばれない
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_no_api_keys(
        self, controller, mock_config_service, mock_worker_service
    ):
        """APIキー未設定の場合でもデフォルトモデルで実行"""
        # Setup
        mock_config_service.get_api_keys.return_value = {}

        def model_selection_callback(available_models: list[str]) -> str:
            # デフォルトモデルリストが渡される
            assert "gpt-4o-mini" in available_models
            return "gpt-4o-mini"

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - デフォルトモデルで実行される
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()

    def test_start_annotation_workflow_worker_service_failure(
        self,
        mock_worker_service,
        mock_selection_state_service,
        mock_config_service,
    ):
        """WorkerService実行失敗"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )
        mock_worker_service.start_enhanced_batch_annotation.side_effect = RuntimeError("Annotation failed")

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute - Should handle exception gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - Exception was caught
        mock_worker_service.start_enhanced_batch_annotation.assert_called_once()

    def test_start_annotation_workflow_no_worker_service(
        self, mock_selection_state_service, mock_config_service
    ):
        """WorkerServiceがNoneの場合"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=None,
            selection_state_service=mock_selection_state_service,
            config_service=mock_config_service,
            parent=None,
        )

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute & Assert - Should handle gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

    def test_start_annotation_workflow_no_selection_service(
        self, mock_worker_service, mock_config_service
    ):
        """SelectionStateServiceがNoneの場合"""
        # Setup - parent=None to avoid QMessageBox calls in tests
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=None,
            config_service=mock_config_service,
            parent=None,
        )

        def model_selection_callback(available_models: list[str]) -> str:
            return "gpt-4o-mini"

        # Execute & Assert - Should handle gracefully
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_no_config_service(
        self, mock_worker_service, mock_selection_state_service
    ):
        """ConfigurationServiceがNoneの場合（空のモデルリスト）"""
        # Setup - parent=None for consistency
        controller = AnnotationWorkflowController(
            worker_service=mock_worker_service,
            selection_state_service=mock_selection_state_service,
            config_service=None,
            parent=None,
        )

        callback_called = False

        def model_selection_callback(available_models: list[str]) -> str | None:
            nonlocal callback_called
            callback_called = True
            # ConfigurationServiceがNoneの場合、空リストが渡される
            assert available_models == []
            # 空リストの場合、Noneを返す（キャンセル扱い）
            return None

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - callbackは呼ばれるが、start_enhanced_batch_annotationは呼ばれない
        assert callback_called
        mock_worker_service.start_enhanced_batch_annotation.assert_not_called()

    def test_start_annotation_workflow_with_available_providers(self, controller, mock_config_service):
        """利用可能なプロバイダーに基づくモデル選択"""
        # Setup
        mock_config_service.get_api_keys.return_value = {
            "openai_key": "test-key",
            "claude_key": "test-key",
            "google_key": "test-key",
        }

        available_models_captured = []

        def model_selection_callback(available_models: list[str]) -> str:
            available_models_captured.extend(available_models)
            return available_models[0]

        # Execute
        controller.start_annotation_workflow(model_selection_callback=model_selection_callback)

        # Assert - 全プロバイダーのモデルが利用可能
        assert len(available_models_captured) >= 3  # OpenAI, Anthropic, Google models
