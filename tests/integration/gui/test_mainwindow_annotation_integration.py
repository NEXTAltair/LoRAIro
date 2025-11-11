"""MainWindow統合テスト: アノテーション機能（Phase 5検証）

実態+モックのハイブリッド戦略:
- 実態使用: ConfigurationService, ImageDatabaseManager, FileSystemManager, DatasetStateManager
- モック使用: WorkerService, AnnotationService
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.window.main_window import MainWindow
from lorairo.services.annotation_batch_processor import BatchAnnotationResult
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def shared_test_config(tmp_path):
    """テスト用共有設定"""
    return {
        "api": {
            "openai_key": "",
            "claude_key": "",
            "google_key": "",
        },
        "directories": {
            "database_base_dir": str(tmp_path / "test_db"),
        },
    }


@pytest.fixture
def real_config_service(shared_test_config, tmp_path):
    """実態のConfigurationService"""
    config_path = tmp_path / "test_config.toml"
    return ConfigurationService(config_path, shared_test_config)


@pytest.fixture
def real_file_system_manager(tmp_path):
    """実態のFileSystemManager"""
    fsm = FileSystemManager()
    fsm.initialize(tmp_path / "lorairo_output")
    return fsm


@pytest.fixture
def real_image_repository(tmp_path):
    """実態のImageRepository（in-memory DB）"""
    db_path = ":memory:"
    return ImageRepository(db_path)


@pytest.fixture
def real_db_manager(real_image_repository, real_config_service, real_file_system_manager):
    """実態のImageDatabaseManager"""
    return ImageDatabaseManager(real_image_repository, real_config_service, real_file_system_manager)


@pytest.fixture
def real_dataset_state_manager():
    """実態のDatasetStateManager"""
    return DatasetStateManager()


@pytest.fixture
def main_window_integrated(
    qtbot,
    real_config_service,
    real_db_manager,
    real_file_system_manager,
    real_dataset_state_manager,
):
    """統合テスト用MainWindow（実態+モックのハイブリッド）"""

    # ServiceContainerモック（db_managerのみ実態）
    mock_container = Mock()
    mock_container.db_manager = real_db_manager

    with patch(
        "lorairo.services.service_container.get_service_container",
        return_value=mock_container,
    ):
        # AnnotationServiceのモック作成
        mock_annotation_service = Mock()
        mock_annotation_service.annotationFinished = Mock()
        mock_annotation_service.annotationError = Mock()
        mock_annotation_service.batchProcessingStarted = Mock()
        mock_annotation_service.batchProcessingProgress = Mock()
        mock_annotation_service.batchProcessingFinished = Mock()

        with patch(
            "lorairo.gui.window.main_window.AnnotationService", return_value=mock_annotation_service
        ):
            with patch("lorairo.gui.window.main_window.WorkerService", return_value=Mock()):
                # MainWindow作成
                window = MainWindow()
                qtbot.addWidget(window)

                # 実態サービス注入（初期化後に上書き）
                window.config_service = real_config_service
                window.db_manager = real_db_manager
                window.file_system_manager = real_file_system_manager
                window.dataset_state_manager = real_dataset_state_manager

                return window


@pytest.mark.integration
@pytest.mark.fast_integration
@pytest.mark.gui
class TestMainWindowAnnotationIntegration:
    """MainWindow統合テスト（Phase A-1）"""

    def test_mainwindow_initialization_with_real_services(self, main_window_integrated):
        """MainWindowが実態サービスで正常初期化することを検証"""
        # Assert: 実態サービスが正しく設定されていること
        assert main_window_integrated.config_service is not None
        assert isinstance(main_window_integrated.config_service, ConfigurationService)

        assert main_window_integrated.db_manager is not None
        assert isinstance(main_window_integrated.db_manager, ImageDatabaseManager)

        assert main_window_integrated.file_system_manager is not None
        assert isinstance(main_window_integrated.file_system_manager, FileSystemManager)

        assert main_window_integrated.dataset_state_manager is not None
        assert isinstance(main_window_integrated.dataset_state_manager, DatasetStateManager)

        # 初期化失敗フラグが立っていないこと
        assert not main_window_integrated._initialization_failed
        assert main_window_integrated._initialization_error is None

    def test_configuration_service_integration(self, main_window_integrated, real_config_service):
        """ConfigurationServiceとMainWindowの統合動作検証"""
        # Act: shared_config経由で設定更新
        real_config_service.update_setting("api", "openai_key", "sk-test-key-12345")

        # Assert: MainWindow経由で設定取得できること
        api_key = main_window_integrated.config_service.get_setting("api", "openai_key")
        assert api_key == "sk-test-key-12345"

        # 設定変更が即座に反映されること
        real_config_service.update_setting("api", "claude_key", "sk-ant-test-key")
        claude_key = main_window_integrated.config_service.get_setting("api", "claude_key")
        assert claude_key == "sk-ant-test-key"

    def test_batch_annotation_finished_handler(self, qtbot, main_window_integrated):
        """BatchAnnotationResult完了ハンドラーの動作検証"""
        # Arrange: 実態のBatchAnnotationResultを作成
        batch_result = BatchAnnotationResult(
            total_images=10,
            processed_images=10,
            successful_annotations=8,
            failed_annotations=2,
            batch_id="test_batch_001",
            results={
                "test_phash_001": {
                    "gpt-4o-mini": {
                        "tags": ["cat", "animal"],
                        "formatted_output": {"captions": ["A cat"]},
                        "error": None,
                    }
                },
            },
        )

        # QMessageBoxをモックしてモーダルダイアログのブロックを回避
        with patch("lorairo.gui.window.main_window.QMessageBox"):
            # Act: ハンドラー実行
            main_window_integrated._on_batch_annotation_finished(batch_result)

            # Qtイベントループ処理を待機
            qtbot.wait(200)

            # Assert: ステータスバーに結果が表示されること
            status_text = main_window_integrated.statusBar().currentMessage()
            assert "8件成功" in status_text
            assert "2件失敗" in status_text
            assert "80.0%" in status_text  # success_rate

    def test_annotation_service_signal_propagation(self, qtbot, main_window_integrated):
        """AnnotationServiceシグナルの伝播検証"""
        # Arrange: サンプルアノテーション結果
        sample_result = {
            "test_phash": {
                "gpt-4o": {
                    "tags": ["test"],
                    "formatted_output": {"captions": ["Test caption"]},
                    "error": None,
                }
            }
        }

        # Act: annotationFinishedシグナルハンドラーを直接呼び出し
        main_window_integrated._on_annotation_finished(sample_result)

        # Assert: ステータスバーが更新されたこと
        qtbot.wait(200)  # UI更新を待機
        status_text = main_window_integrated.statusBar().currentMessage()
        assert "アノテーション処理が完了しました" in status_text

    def test_batch_annotation_progress_handler(self, qtbot, main_window_integrated):
        """バッチ処理進捗シグナルの処理検証"""
        # Act: 進捗ハンドラーを複数回呼び出し
        main_window_integrated._on_batch_annotation_progress(5, 10)  # 5/10完了
        qtbot.wait(200)

        main_window_integrated._on_batch_annotation_progress(10, 10)  # 10/10完了
        qtbot.wait(200)

        # Assert: ステータスバーに進捗が表示されたこと
        status_text = main_window_integrated.statusBar().currentMessage()
        assert "10" in status_text  # 進捗数値が含まれること
        assert "100" in status_text or "10" in status_text  # 100%または10/10

    def test_annotation_error_handler(self, qtbot, main_window_integrated):
        """エラーハンドリングの検証"""
        # Arrange: テストエラーメッセージ
        test_error = "Test API Error: Invalid API key"

        # Act: エラーハンドラーを呼び出し
        main_window_integrated._on_annotation_error(test_error)

        # Assert: エラーが処理されたこと（例外が発生しないこと）
        qtbot.wait(200)  # エラー処理を待機

        # ステータスバーまたはログにエラーが記録されていることを期待
        # Note: 実装によってはQMessageBoxが表示される可能性があるが、
        # テスト環境では自動的に閉じられる
