"""AnnotationService ユニットテスト

Phase 4実装の拡張アノテーションサービスをテスト
Qt Signal/Slot, ServiceContainer統合, 各種アノテーション処理をテスト
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QObject
from PySide6.QtTest import QSignalSpy

from lorairo.services.annotation_service import AnnotationService


class TestAnnotationServiceInitialization:
    """AnnotationService 初期化テスト"""

    @patch("lorairo.services.enhanced_annotation_service.get_service_container")
    def test_initialization_success(self, mock_get_container):
        """正常な初期化テスト"""
        mock_container = Mock()
        mock_get_container.return_value = mock_container

        service = AnnotationService()

        assert isinstance(service, QObject)
        assert service.container is mock_container
        assert service._last_annotation_result is None
        assert service._last_batch_result is None
        mock_get_container.assert_called_once()

    @patch("lorairo.services.enhanced_annotation_service.get_service_container")
    def test_initialization_with_parent(self, mock_get_container):
        """親オブジェクト指定での初期化"""
        mock_container = Mock()
        mock_get_container.return_value = mock_container
        mock_parent = Mock(spec=QObject)

        service = AnnotationService(parent=mock_parent)

        assert service.parent() is mock_parent
        assert service.container is mock_container

    def test_signal_definitions(self):
        """シグナル定義確認"""
        with patch("lorairo.services.enhanced_annotation_service.get_service_container"):
            service = AnnotationService()

            # 各シグナルが定義されていることを確認
            assert hasattr(service, "annotationFinished")
            assert hasattr(service, "annotationError")
            assert hasattr(service, "availableAnnotatorsFetched")
            assert hasattr(service, "modelSyncCompleted")
            assert hasattr(service, "batchProcessingStarted")
            assert hasattr(service, "batchProcessingProgress")
            assert hasattr(service, "batchProcessingFinished")


class TestAnnotationServiceModelSync:
    """AnnotationService モデル同期テスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_sync_available_models_success(self, service_with_mocks):
        """モデル同期成功テスト"""
        service, mock_container = service_with_mocks

        # モックモデル同期結果
        mock_sync_result = Mock()
        mock_sync_result.success = True
        mock_sync_result.summary = "テスト同期完了"
        mock_container.model_sync_service.sync_available_models.return_value = mock_sync_result

        # シグナルスパイ設定
        sync_spy = QSignalSpy(service.modelSyncCompleted)

        # 同期実行
        service.sync_available_models()

        # 検証
        mock_container.model_sync_service.sync_available_models.assert_called_once()
        assert len(sync_spy) == 1
        assert sync_spy[0][0] is mock_sync_result

    def test_sync_available_models_failure(self, service_with_mocks):
        """モデル同期失敗テスト"""
        service, mock_container = service_with_mocks

        # モック同期失敗結果
        mock_sync_result = Mock()
        mock_sync_result.success = False
        mock_sync_result.errors = ["エラー1", "エラー2"]
        mock_container.model_sync_service.sync_available_models.return_value = mock_sync_result

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 同期実行
        service.sync_available_models()

        # 検証
        assert len(error_spy) == 1
        error_message = error_spy[0][0]
        assert "モデル同期エラー" in error_message
        assert "エラー1" in error_message
        assert "エラー2" in error_message

    def test_sync_available_models_exception(self, service_with_mocks):
        """モデル同期処理例外テスト"""
        service, mock_container = service_with_mocks

        # 例外発生をシミュレート
        mock_container.model_sync_service.sync_available_models.side_effect = Exception("同期処理エラー")

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 同期実行
        service.sync_available_models()

        # 検証
        assert len(error_spy) == 1
        error_message = error_spy[0][0]
        assert "予期しないエラー" in error_message
        assert "同期処理エラー" in error_message


class TestAnnotationServiceModelRetrieval:
    """AnnotationService モデル取得テスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_get_available_models_success(self, service_with_mocks):
        """利用可能モデル取得成功"""
        service, mock_container = service_with_mocks

        # モックモデルデータ
        mock_models = [
            {"name": "gpt-4o", "provider": "openai", "model_type": "vision"},
            {"name": "claude-3-5-sonnet", "provider": "anthropic", "model_type": "vision"},
        ]
        mock_container.annotator_lib_adapter.get_available_models_with_metadata.return_value = mock_models

        # メソッド実行
        result = service.get_available_models()

        # 検証
        assert result == mock_models
        mock_container.annotator_lib_adapter.get_available_models_with_metadata.assert_called_once()

    def test_get_available_models_exception(self, service_with_mocks):
        """利用可能モデル取得例外"""
        service, mock_container = service_with_mocks

        # 例外発生をシミュレート
        mock_container.annotator_lib_adapter.get_available_models_with_metadata.side_effect = Exception(
            "取得エラー"
        )

        # メソッド実行
        result = service.get_available_models()

        # 検証
        assert result == []

    def test_fetch_available_annotators_success(self, service_with_mocks):
        """利用可能アノテーター名取得成功（既存互換性）"""
        service, mock_container = service_with_mocks

        # モックモデルデータ
        mock_models = [
            {"name": "gpt-4o", "provider": "openai"},
            {"name": "claude-3-5-sonnet", "provider": "anthropic"},
        ]
        mock_container.annotator_lib_adapter.get_available_models_with_metadata.return_value = mock_models

        # シグナルスパイ設定
        fetched_spy = QSignalSpy(service.availableAnnotatorsFetched)

        # メソッド実行
        service.fetch_available_annotators()

        # 検証
        assert len(fetched_spy) == 1
        model_names = fetched_spy[0][0]
        assert model_names == ["gpt-4o", "claude-3-5-sonnet"]

    def test_fetch_available_annotators_exception(self, service_with_mocks):
        """利用可能アノテーター取得例外"""
        service, mock_container = service_with_mocks

        # 例外発生をシミュレート
        mock_container.annotator_lib_adapter.get_available_models_with_metadata.side_effect = Exception(
            "取得エラー"
        )

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)
        fetched_spy = QSignalSpy(service.availableAnnotatorsFetched)

        # メソッド実行
        service.fetch_available_annotators()

        # 検証
        assert len(error_spy) == 1
        assert len(fetched_spy) == 1
        assert fetched_spy[0][0] == []  # 空リストが返される


class TestAnnotationServiceSingleAnnotation:
    """AnnotationService 単発アノテーションテスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_start_single_annotation_success(self, service_with_mocks):
        """単発アノテーション成功テスト"""
        service, mock_container = service_with_mocks

        # テストデータ
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_phashes = ["phash_1"]
        test_models = ["gpt-4o"]

        # モックアノテーション結果
        mock_results = {"phash_1": {"gpt-4o": {"result": "success"}}}
        mock_container.annotator_lib_adapter.call_annotate.return_value = mock_results

        # シグナルスパイ設定
        finished_spy = QSignalSpy(service.annotationFinished)

        # アノテーション実行
        service.start_single_annotation(test_images, test_phashes, test_models)

        # 検証
        mock_container.annotator_lib_adapter.call_annotate.assert_called_once_with(
            images=test_images, models=test_models, phash_list=test_phashes
        )
        assert len(finished_spy) == 1
        assert finished_spy[0][0] == mock_results
        assert service._last_annotation_result == mock_results
        assert service.get_last_annotation_result() == mock_results

    def test_start_single_annotation_no_images(self, service_with_mocks):
        """単発アノテーション - 画像なしエラー"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 空画像リストでアノテーション実行
        service.start_single_annotation([], ["phash_1"], ["gpt-4o"])

        # 検証
        assert len(error_spy) == 1
        assert "入力画像がありません" in error_spy[0][0]
        mock_container.annotator_lib_adapter.call_annotate.assert_not_called()

    def test_start_single_annotation_no_models(self, service_with_mocks):
        """単発アノテーション - モデルなしエラー"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # モデルなしでアノテーション実行
        test_images = [Image.new("RGB", (100, 100), "red")]
        service.start_single_annotation(test_images, ["phash_1"], [])

        # 検証
        assert len(error_spy) == 1
        assert "モデルが選択されていません" in error_spy[0][0]

    def test_start_single_annotation_phash_mismatch(self, service_with_mocks):
        """単発アノテーション - 画像とpHashの数不一致エラー"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 画像とpHashの数が一致しない場合
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_phashes = ["phash_1", "phash_2"]  # 数が合わない
        service.start_single_annotation(test_images, test_phashes, ["gpt-4o"])

        # 検証
        assert len(error_spy) == 1
        assert "画像とpHashの数が一致しません" in error_spy[0][0]

    def test_start_single_annotation_exception(self, service_with_mocks):
        """単発アノテーション処理例外"""
        service, mock_container = service_with_mocks

        # 例外発生をシミュレート
        mock_container.annotator_lib_adapter.call_annotate.side_effect = Exception("アノテーションエラー")

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # アノテーション実行
        test_images = [Image.new("RGB", (100, 100), "red")]
        service.start_single_annotation(test_images, ["phash_1"], ["gpt-4o"])

        # 検証
        assert len(error_spy) == 1
        error_message = error_spy[0][0]
        assert "単発アノテーション処理エラー" in error_message
        assert "アノテーションエラー" in error_message


class TestAnnotationServiceBatchAnnotation:
    """AnnotationService バッチアノテーションテスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_start_batch_annotation_success(self, service_with_mocks):
        """バッチアノテーション成功テスト"""
        service, mock_container = service_with_mocks

        # テストデータ
        test_image_paths = ["/path/to/image1.jpg", "/path/to/image2.jpg"]
        test_models = ["gpt-4o", "claude-3-5-sonnet"]
        test_batch_size = 50

        # モックバッチ処理結果
        mock_batch_result = Mock()
        mock_batch_result.summary = "バッチ処理完了: 2画像, 2モデル"
        mock_container.batch_processor.execute_batch_annotation.return_value = mock_batch_result

        # シグナルスパイ設定
        started_spy = QSignalSpy(service.batchProcessingStarted)
        finished_spy = QSignalSpy(service.batchProcessingFinished)

        # バッチアノテーション実行
        service.start_batch_annotation(test_image_paths, test_models, test_batch_size)

        # 検証
        assert len(started_spy) == 1
        assert started_spy[0][0] == len(test_image_paths)  # 総画像数

        # execute_batch_annotationの呼び出し確認
        call_args = mock_container.batch_processor.execute_batch_annotation.call_args
        assert len(call_args[1]["image_paths"]) == len(test_image_paths)
        assert all(isinstance(p, Path) for p in call_args[1]["image_paths"])
        assert call_args[1]["models"] == test_models
        assert call_args[1]["batch_size"] == test_batch_size

        assert len(finished_spy) == 1
        assert finished_spy[0][0] is mock_batch_result
        assert service._last_batch_result is mock_batch_result
        assert service.get_last_batch_result() is mock_batch_result

    def test_start_batch_annotation_no_images(self, service_with_mocks):
        """バッチアノテーション - 画像パスなしエラー"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 空画像パスリストでバッチアノテーション実行
        service.start_batch_annotation([], ["gpt-4o"])

        # 検証
        assert len(error_spy) == 1
        assert "画像パスが指定されていません" in error_spy[0][0]
        mock_container.batch_processor.execute_batch_annotation.assert_not_called()

    def test_start_batch_annotation_no_models(self, service_with_mocks):
        """バッチアノテーション - モデルなしエラー"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # モデルなしでバッチアノテーション実行
        service.start_batch_annotation(["/path/to/image.jpg"], [])

        # 検証
        assert len(error_spy) == 1
        assert "モデルが選択されていません" in error_spy[0][0]

    def test_start_batch_annotation_exception(self, service_with_mocks):
        """バッチアノテーション処理例外"""
        service, mock_container = service_with_mocks

        # 例外発生をシミュレート
        mock_container.batch_processor.execute_batch_annotation.side_effect = Exception("バッチ処理エラー")

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # バッチアノテーション実行
        service.start_batch_annotation(["/path/to/image.jpg"], ["gpt-4o"])

        # 検証
        assert len(error_spy) == 1
        error_message = error_spy[0][0]
        assert "バッチアノテーション処理エラー" in error_message
        assert "バッチ処理エラー" in error_message


class TestAnnotationServiceUtilities:
    """AnnotationService ユーティリティ機能テスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_get_library_models_summary_success(self, service_with_mocks):
        """ライブラリモデルサマリー取得成功"""
        service, mock_container = service_with_mocks

        # モックサマリー
        mock_summary = {"total_models": 10, "vision": 5, "tagger": 3, "score": 2}
        mock_container.model_sync_service.get_library_models_summary.return_value = mock_summary

        # メソッド実行
        result = service.get_library_models_summary()

        # 検証
        assert result == mock_summary
        mock_container.model_sync_service.get_library_models_summary.assert_called_once()

    def test_get_library_models_summary_exception(self, service_with_mocks):
        """ライブラリモデルサマリー取得例外"""
        service, mock_container = service_with_mocks

        # 例外発生をシミュレート
        mock_container.model_sync_service.get_library_models_summary.side_effect = Exception(
            "サマリー取得エラー"
        )

        # メソッド実行
        result = service.get_library_models_summary()

        # 検証
        assert result == {}

    def test_cancel_annotation(self, service_with_mocks):
        """アノテーションキャンセル（Phase 2-3で実装予定）"""
        service, mock_container = service_with_mocks

        # キャンセル実行（現在は何もしない）
        service.cancel_annotation()

        # 例外が発生しないことを確認
        # Phase 2-3で実装される予定

    def test_get_service_status(self, service_with_mocks):
        """サービス状況取得"""
        service, mock_container = service_with_mocks

        # モックコンテナサマリー
        mock_container_summary = {"initialized_services": {}, "container_initialized": True}
        mock_container.get_service_summary.return_value = mock_container_summary

        # 結果を設定
        service._last_annotation_result = {"test": "result"}
        service._last_batch_result = None

        # メソッド実行
        status = service.get_service_status()

        # 検証
        assert status["service_name"] == "AnnotationService"
        assert "Phase 2" in status["phase"]
        assert status["container_summary"] == mock_container_summary
        assert status["last_results"]["has_annotation_result"] is True
        assert status["last_results"]["has_batch_result"] is False

    def test_result_accessors(self, service_with_mocks):
        """結果アクセサメソッドテスト"""
        service, mock_container = service_with_mocks

        # 初期状態
        assert service.get_last_annotation_result() is None
        assert service.get_last_batch_result() is None

        # 結果設定
        test_annotation_result = {"phash_1": {"model_1": "result_1"}}
        test_batch_result = Mock()

        service._last_annotation_result = test_annotation_result
        service._last_batch_result = test_batch_result

        # 結果取得確認
        assert service.get_last_annotation_result() == test_annotation_result
        assert service.get_last_batch_result() == test_batch_result


class TestAnnotationServiceInputValidation:
    """AnnotationService 入力検証テスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_validate_annotation_input_valid(self, service_with_mocks):
        """有効な入力検証"""
        service, mock_container = service_with_mocks

        # 有効な入力
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_phashes = ["phash_1"]
        test_models = ["gpt-4o"]

        # 検証実行
        result = service._validate_annotation_input(test_images, test_phashes, test_models)

        # 検証
        assert result is True

    def test_validate_annotation_input_no_phash(self, service_with_mocks):
        """pHashなしの有効な入力検証"""
        service, mock_container = service_with_mocks

        # pHashなしの有効な入力
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_models = ["gpt-4o"]

        # 検証実行
        result = service._validate_annotation_input(test_images, [], test_models)

        # 検証
        assert result is True

    def test_validate_annotation_input_empty_images(self, service_with_mocks):
        """空の画像リスト検証"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 検証実行
        result = service._validate_annotation_input([], ["phash_1"], ["gpt-4o"])

        # 検証
        assert result is False
        assert len(error_spy) == 1
        assert "入力画像がありません" in error_spy[0][0]

    def test_validate_annotation_input_empty_models(self, service_with_mocks):
        """空のモデルリスト検証"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 検証実行
        test_images = [Image.new("RGB", (100, 100), "red")]
        result = service._validate_annotation_input(test_images, ["phash_1"], [])

        # 検証
        assert result is False
        assert len(error_spy) == 1
        assert "モデルが選択されていません" in error_spy[0][0]

    def test_validate_annotation_input_phash_length_mismatch(self, service_with_mocks):
        """画像とpHashの数不一致検証"""
        service, mock_container = service_with_mocks

        # シグナルスパイ設定
        error_spy = QSignalSpy(service.annotationError)

        # 検証実行
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_phashes = ["phash_1", "phash_2"]  # 数が合わない
        result = service._validate_annotation_input(test_images, test_phashes, ["gpt-4o"])

        # 検証
        assert result is False
        assert len(error_spy) == 1
        assert "画像とpHashの数が一致しません" in error_spy[0][0]


# 境界値・エッジケーステスト
class TestAnnotationServiceEdgeCases:
    """AnnotationService 境界値・エッジケーステスト"""

    @pytest.fixture
    def service_with_mocks(self):
        """モック付きサービスインスタンス"""
        with patch(
            "lorairo.services.enhanced_annotation_service.get_service_container"
        ) as mock_get_container:
            mock_container = Mock()
            mock_get_container.return_value = mock_container
            service = AnnotationService()
            return service, mock_container

    def test_large_batch_annotation(self, service_with_mocks):
        """大量バッチアノテーション"""
        service, mock_container = service_with_mocks

        # 大量の画像パス
        large_image_paths = [f"/path/to/image_{i}.jpg" for i in range(1000)]
        test_models = ["gpt-4o"]

        # モックバッチ処理結果
        mock_batch_result = Mock()
        mock_batch_result.summary = "大量バッチ処理完了"
        mock_container.batch_processor.execute_batch_annotation.return_value = mock_batch_result

        # バッチアノテーション実行
        service.start_batch_annotation(large_image_paths, test_models)

        # 検証（例外が発生しないことを確認）
        mock_container.batch_processor.execute_batch_annotation.assert_called_once()

    def test_many_models_annotation(self, service_with_mocks):
        """多数モデルでのアノテーション"""
        service, mock_container = service_with_mocks

        # 多数のモデル
        many_models = [f"model-{i}" for i in range(20)]
        test_images = [Image.new("RGB", (100, 100), "red")]
        test_phashes = ["phash_1"]

        # モックアノテーション結果
        mock_results = {"phash_1": {model: {"result": "success"} for model in many_models}}
        mock_container.annotator_lib_adapter.call_annotate.return_value = mock_results

        # アノテーション実行
        service.start_single_annotation(test_images, test_phashes, many_models)

        # 検証
        mock_container.annotator_lib_adapter.call_annotate.assert_called_once_with(
            images=test_images, models=many_models, phash_list=test_phashes
        )


@pytest.mark.integration
class TestAnnotationServiceIntegration:
    """AnnotationService 統合テスト"""

    def test_full_annotation_workflow(self):
        """完全なアノテーションワークフロー"""
        # 実際のServiceContainerとの統合テスト
        # 本テストは統合テストファイルで実装
        pass
