"""
サムネイル選択時の画像詳細表示アノテーション統合テスト
"""

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.services.worker_service import WorkerService
from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget


@pytest.mark.gui
class TestThumbnailDetailsAnnotationIntegration:
    """サムネイル選択→画像詳細表示でのアノテーション統合テスト"""

    @pytest.fixture
    def app(self, qapp):
        """Qt アプリケーション"""
        return qapp

    @pytest.fixture
    def mock_worker_service(self):
        """MockのWorkerService"""
        return Mock(spec=WorkerService)

    @pytest.fixture
    def mock_state_manager(self):
        """MockのDatasetStateManager"""
        return Mock(spec=DatasetStateManager)

    @pytest.fixture
    def thumbnail_widget(self, app, mock_worker_service, mock_state_manager):
        """ThumbnailSelectorWidget インスタンス"""
        widget = ThumbnailSelectorWidget()
        # 必要なサービスを設定
        widget.worker_service = mock_worker_service
        widget.state_manager = mock_state_manager
        return widget

    @pytest.fixture
    def details_widget(self, app):
        """SelectedImageDetailsWidget インスタンス"""
        return SelectedImageDetailsWidget()

    @pytest.fixture
    def sample_metadata_with_annotations(self):
        """アノテーション情報を含むサンプルメタデータ"""
        return {
            "id": 1,
            "filename": "test_image.jpg",
            "original_image_path": "/path/to/test_image.jpg",
            "stored_image_path": "/path/to/stored/test_image.jpg",
            "width": 1024,
            "height": 768,
            "format": "JPEG",
            "tags": [
                {
                    "id": 1,
                    "tag": "landscape",
                    "tag_id": 100,
                    "model_id": "test_model",
                    "existing": True,
                    "is_edited_manually": False,
                    "confidence_score": 0.95,
                    "created_at": datetime(2025, 9, 27, 10, 0, 0),
                    "updated_at": datetime(2025, 9, 27, 10, 0, 0),
                },
                {
                    "id": 2,
                    "tag": "nature",
                    "tag_id": 101,
                    "model_id": "test_model",
                    "existing": False,
                    "is_edited_manually": True,
                    "confidence_score": 0.88,
                    "created_at": datetime(2025, 9, 27, 10, 1, 0),
                    "updated_at": datetime(2025, 9, 27, 10, 1, 0),
                },
            ],
            "captions": [
                {
                    "id": 1,
                    "caption": "A beautiful landscape with mountains and trees",
                    "model_id": "test_model",
                    "existing": True,
                    "is_edited_manually": False,
                    "created_at": datetime(2025, 9, 27, 10, 0, 0),
                    "updated_at": datetime(2025, 9, 27, 10, 0, 0),
                },
            ],
            "scores": [
                {
                    "id": 1,
                    "score": 0.85,
                    "model_id": "test_model",
                    "is_edited_manually": False,
                    "created_at": datetime(2025, 9, 27, 10, 0, 0),
                    "updated_at": datetime(2025, 9, 27, 10, 0, 0),
                },
            ],
            "ratings": [
                {
                    "id": 1,
                    "raw_rating_value": "5",
                    "normalized_rating": 1.0,
                    "model_id": "test_model",
                    "confidence_score": 0.90,
                    "created_at": datetime(2025, 9, 27, 10, 0, 0),
                    "updated_at": datetime(2025, 9, 27, 10, 0, 0),
                },
            ],
        }

    def test_direct_widget_connection_setup(self, thumbnail_widget, details_widget):
        """直接ウィジェット接続のセットアップテスト"""
        # 接続を確立
        details_widget.connect_to_thumbnail_widget(thumbnail_widget)

        # シグナル接続が正しく設定されているかを確認
        assert thumbnail_widget.image_metadata_selected.isSignalConnected(
            details_widget, "_on_direct_metadata_received"
        )

    def test_annotation_signal_emission(self, thumbnail_widget, sample_metadata_with_annotations):
        """アノテーション付きメタデータのシグナル発信テスト"""
        signal_received = False
        received_metadata = None

        def capture_signal(metadata):
            nonlocal signal_received, received_metadata
            signal_received = True
            received_metadata = metadata

        # シグナルを接続
        thumbnail_widget.image_metadata_selected.connect(capture_signal)

        # メタデータをキャッシュに設定
        thumbnail_widget.image_metadata = {1: sample_metadata_with_annotations}

        # サムネイル選択をシミュレート
        thumbnail_widget._on_image_selected(1)

        # シグナルが発信されたことを確認
        assert signal_received is True
        assert received_metadata is not None
        assert received_metadata["id"] == 1
        assert "tags" in received_metadata
        assert "captions" in received_metadata
        assert len(received_metadata["tags"]) == 2
        assert len(received_metadata["captions"]) == 1

    def test_details_widget_annotation_processing(self, details_widget, sample_metadata_with_annotations):
        """SelectedImageDetailsWidgetでのアノテーション処理テスト"""
        # 既存の_build_image_details_from_metadata をモック
        with patch.object(details_widget, "_build_image_details_from_metadata") as mock_build:
            mock_build.return_value = "Mock HTML content with annotations"

            # メタデータを直接受信
            details_widget._on_direct_metadata_received(sample_metadata_with_annotations)

            # _build_image_details_from_metadata が呼ばれたことを確認
            mock_build.assert_called_once()
            call_args = mock_build.call_args[0][0]

            # メタデータにアノテーション情報が含まれていることを確認
            assert "tags" in call_args
            assert "captions" in call_args
            assert "scores" in call_args
            assert "ratings" in call_args
            assert len(call_args["tags"]) == 2
            assert call_args["tags"][0]["tag"] == "landscape"
            assert call_args["tags"][1]["tag"] == "nature"

    def test_end_to_end_annotation_display(
        self, thumbnail_widget, details_widget, sample_metadata_with_annotations, app
    ):
        """エンドツーエンドでのアノテーション表示テスト"""
        # 直接接続を確立
        details_widget.connect_to_thumbnail_widget(thumbnail_widget)

        # メタデータをキャッシュに設定
        thumbnail_widget.image_metadata = {1: sample_metadata_with_annotations}

        # _build_image_details_from_metadata をモックして、アノテーション処理を確認
        with patch.object(details_widget, "_build_image_details_from_metadata") as mock_build:
            mock_build.return_value = "Mock HTML with annotations"

            # サムネイル選択をシミュレート
            thumbnail_widget._on_image_selected(1)

            # Qt イベントループを処理
            app.processEvents()

            # アノテーション情報が正しく処理されたことを確認
            mock_build.assert_called_once()
            processed_metadata = mock_build.call_args[0][0]

            assert processed_metadata["id"] == 1
            assert len(processed_metadata["tags"]) == 2
            assert processed_metadata["tags"][0]["confidence_score"] == 0.95
            assert (
                processed_metadata["captions"][0]["caption"]
                == "A beautiful landscape with mountains and trees"
            )

    def test_empty_annotation_handling(self, thumbnail_widget, details_widget):
        """アノテーションが空の場合の処理テスト"""
        metadata_without_annotations = {
            "id": 1,
            "filename": "test_image.jpg",
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        # 直接接続を確立
        details_widget.connect_to_thumbnail_widget(thumbnail_widget)

        # メタデータをキャッシュに設定
        thumbnail_widget.image_metadata = {1: metadata_without_annotations}

        with patch.object(details_widget, "_build_image_details_from_metadata") as mock_build:
            mock_build.return_value = "Mock HTML without annotations"

            # サムネイル選択をシミュレート
            thumbnail_widget._on_image_selected(1)

            # アノテーション情報が空でも正しく処理されることを確認
            mock_build.assert_called_once()
            processed_metadata = mock_build.call_args[0][0]

            assert processed_metadata["id"] == 1
            assert processed_metadata["tags"] == []
            assert processed_metadata["captions"] == []
            assert processed_metadata["scores"] == []
            assert processed_metadata["ratings"] == []

    def test_multiple_annotation_types_display(
        self, thumbnail_widget, details_widget, sample_metadata_with_annotations
    ):
        """複数種類のアノテーション表示テスト"""
        # 直接接続を確立
        details_widget.connect_to_thumbnail_widget(thumbnail_widget)

        # メタデータをキャッシュに設定
        thumbnail_widget.image_metadata = {1: sample_metadata_with_annotations}

        with patch.object(details_widget, "_build_image_details_from_metadata") as mock_build:
            mock_build.return_value = "Mock HTML with all annotation types"

            # サムネイル選択をシミュレート
            thumbnail_widget._on_image_selected(1)

            # すべてのアノテーション類型が含まれていることを確認
            mock_build.assert_called_once()
            processed_metadata = mock_build.call_args[0][0]

            # Tags
            assert len(processed_metadata["tags"]) == 2
            assert processed_metadata["tags"][0]["tag"] == "landscape"
            assert processed_metadata["tags"][0]["confidence_score"] == 0.95

            # Captions
            assert len(processed_metadata["captions"]) == 1
            assert "beautiful landscape" in processed_metadata["captions"][0]["caption"]

            # Scores
            assert len(processed_metadata["scores"]) == 1
            assert processed_metadata["scores"][0]["score"] == 0.85

            # Ratings
            assert len(processed_metadata["ratings"]) == 1
            assert processed_metadata["ratings"][0]["normalized_rating"] == 1.0

    def test_signal_disconnection_on_reconnection(self, thumbnail_widget, details_widget):
        """再接続時の適切なシグナル切断テスト"""
        # 初回接続
        details_widget.connect_to_thumbnail_widget(thumbnail_widget)

        # 別のサムネイルウィジェットを作成
        thumbnail_widget2 = ThumbnailSelectorWidget()

        # 再接続
        details_widget.connect_to_thumbnail_widget(thumbnail_widget2)

        # 最初のウィジェットとの接続が切断されていることを確認
        # （実装によってはassertionの詳細が変わる可能性があります）
        assert not thumbnail_widget.image_metadata_selected.isSignalConnected(
            details_widget, "_on_direct_metadata_received"
        )

        # 新しいウィジェットとの接続が確立されていることを確認
        assert thumbnail_widget2.image_metadata_selected.isSignalConnected(
            details_widget, "_on_direct_metadata_received"
        )
