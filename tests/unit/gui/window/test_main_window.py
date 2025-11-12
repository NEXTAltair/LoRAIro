"""MainWindow ユニットテスト

責任分離後のMainWindowのビジネスロジックをテスト
- 最適パス決定処理の責任（Phase 2.4: DataTransformService委譲）
- データベースアクセスロジック
- エラーハンドリング

Note: これらのテストはGUIコンポーネントを実際に作成せず、
ビジネスロジックのみをテストします。

Phase 2.4 Stage 4-1: DataTransformService委譲に合わせてテストを更新。
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestMainWindowPathResolution:
    """MainWindow パス解決ロジック テスト（Phase 2.4: DataTransformService委譲パターン）"""

    def test_resolve_optimal_thumbnail_data_with_service(self) -> None:
        """DataTransformService経由でのパス解決（正常系）"""
        from lorairo.gui.window.main_window import MainWindow

        resolve_method = MainWindow._resolve_optimal_thumbnail_data
        mock_self = Mock()

        # DataTransformServiceのモック
        mock_service = Mock()
        mock_self.data_transform_service = mock_service

        # テスト用画像メタデータ
        image_metadata = [
            {"id": 101, "stored_image_path": "/original/image1.jpg"},
            {"id": 102, "stored_image_path": "/original/image2.jpg"},
        ]

        # DataTransformService.resolve_optimal_thumbnail_paths()のモック結果
        mock_service.resolve_optimal_thumbnail_paths.return_value = [
            (Path("/processed/512/image1.jpg"), 101),
            (Path("/original/image2.jpg"), 102),
        ]

        result = resolve_method(mock_self, image_metadata)

        # 結果の検証
        assert len(result) == 2
        assert result[0] == (Path("/processed/512/image1.jpg"), 101)
        assert result[1] == (Path("/original/image2.jpg"), 102)
        mock_service.resolve_optimal_thumbnail_paths.assert_called_once_with(image_metadata)

    def test_resolve_optimal_thumbnail_data_without_service(self) -> None:
        """DataTransformService未初期化時のフォールバック（元画像のみ使用）"""
        from lorairo.gui.window.main_window import MainWindow

        resolve_method = MainWindow._resolve_optimal_thumbnail_data
        mock_self = Mock()
        mock_self.data_transform_service = None

        # テスト用画像メタデータ
        image_metadata = [{"id": 201, "stored_image_path": "/original/image1.jpg"}]

        result = resolve_method(mock_self, image_metadata)

        # Service未初期化時は元画像のみ使用
        assert len(result) == 1
        assert result[0] == (Path("/original/image1.jpg"), 201)

    def test_resolve_optimal_thumbnail_data_empty_metadata(self) -> None:
        """空のメタデータの処理（Service経由）"""
        from lorairo.gui.window.main_window import MainWindow

        resolve_method = MainWindow._resolve_optimal_thumbnail_data
        mock_self = Mock()

        mock_service = Mock()
        mock_self.data_transform_service = mock_service
        mock_service.resolve_optimal_thumbnail_paths.return_value = []

        result = resolve_method(mock_self, [])

        assert result == []
        mock_service.resolve_optimal_thumbnail_paths.assert_called_once_with([])

    def test_resolve_optimal_thumbnail_data_service_delegation(self) -> None:
        """DataTransformServiceへの委譲が正しく機能することを確認"""
        from lorairo.gui.window.main_window import MainWindow

        resolve_method = MainWindow._resolve_optimal_thumbnail_data
        mock_self = Mock()

        mock_service = Mock()
        mock_self.data_transform_service = mock_service

        image_metadata = [
            {"id": 1, "stored_image_path": "/original/image1.jpg"},
            {"id": 2, "stored_image_path": "/original/image2.jpg"},
            {"id": 3, "stored_image_path": "/original/image3.jpg"},
        ]

        mock_service.resolve_optimal_thumbnail_paths.return_value = [
            (Path("/processed/512/image1.jpg"), 1),
            (Path("/original/image2.jpg"), 2),
            (Path("/original/image3.jpg"), 3),
        ]

        result = resolve_method(mock_self, image_metadata)

        # 結果の検証
        assert len(result) == 3
        assert result[0] == (Path("/processed/512/image1.jpg"), 1)
        assert result[1] == (Path("/original/image2.jpg"), 2)
        assert result[2] == (Path("/original/image3.jpg"), 3)
        mock_service.resolve_optimal_thumbnail_paths.assert_called_once_with(image_metadata)


class TestMainWindowResponsibilityBoundaries:
    """MainWindow 責任境界テスト"""

    def test_has_path_resolution_method(self) -> None:
        """パス解決メソッドが存在することを確認"""
        from lorairo.gui.window.main_window import MainWindow

        # メソッドが存在することを確認
        assert hasattr(MainWindow, "_resolve_optimal_thumbnail_data")
        assert callable(MainWindow._resolve_optimal_thumbnail_data)

    def test_path_resolution_method_signature(self) -> None:
        """パス解決メソッドのシグネチャ確認"""
        import inspect

        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._resolve_optimal_thumbnail_data
        signature = inspect.signature(method)

        # 期待するパラメータが存在することを確認
        params = list(signature.parameters.keys())
        assert "self" in params
        assert "image_metadata" in params


class TestMainWindowBusinessLogic:
    """MainWindow ビジネスロジック テスト（Phase 2.4: DataTransformService委譲）"""

    def test_delegation_pattern(self) -> None:
        """DataTransformServiceへの委譲パターンテスト"""
        from lorairo.gui.window.main_window import MainWindow

        resolve_method = MainWindow._resolve_optimal_thumbnail_data

        mock_self = Mock()
        mock_service = Mock()
        mock_self.data_transform_service = mock_service

        # 複数の画像でそれぞれ異なる最適化が適用される場合
        image_metadata = [
            {"id": 1, "stored_image_path": "/original/image1.jpg"},
            {"id": 2, "stored_image_path": "/original/image2.jpg"},
            {"id": 3, "stored_image_path": "/original/image3.jpg"},
        ]

        # DataTransformServiceが適切に処理した結果をモック
        mock_service.resolve_optimal_thumbnail_paths.return_value = [
            (Path("/processed/512/image1.jpg"), 1),  # 512px利用
            (Path("/original/image2.jpg"), 2),  # 元画像利用
            (Path("/original/image3.jpg"), 3),  # フォールバック
        ]

        result = resolve_method(mock_self, image_metadata)

        # 結果の検証
        assert len(result) == 3
        assert result[0] == (Path("/processed/512/image1.jpg"), 1)
        assert result[1] == (Path("/original/image2.jpg"), 2)
        assert result[2] == (Path("/original/image3.jpg"), 3)

        # DataTransformServiceが正しく呼ばれたことを確認
        mock_service.resolve_optimal_thumbnail_paths.assert_called_once_with(image_metadata)


class TestMainWindowPhase3Integration:
    """MainWindow Phase 3統合機能テスト（サービス統合）"""

    @pytest.fixture
    def mock_dependencies(self):
        """MainWindow依存関係のモック"""
        mocks = {
            "config_service": Mock(),
            "fsm": Mock(),
            "db_manager": Mock(),
            "worker_service": Mock(),
            "dataset_state": Mock(),
        }

        # ConfigurationServiceのモック
        mocks["config_service"].get_setting.return_value = ""
        mocks["config_service"].get_database_directory.return_value = Path("test_db")

        # ImageDatabaseManagerのモック
        mocks["db_manager"].repository = Mock()

        return mocks

    def test_setup_image_db_write_service(self, mock_dependencies):
        """ImageDBWriteService統合テスト（Phase 3.4）"""
        from lorairo.gui.window.main_window import MainWindow

        # MainWindowの_setup_image_db_write_service メソッドをテスト
        method = MainWindow._setup_image_db_write_service

        # モックオブジェクト作成
        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        mock_window.selected_image_details_widget = Mock()

        with patch("lorairo.gui.services.image_db_write_service.ImageDBWriteService") as mock_service_class:
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                mock_service_instance = Mock()
                mock_service_class.return_value = mock_service_instance

                # メソッド実行
                method(mock_window)

                # ImageDBWriteServiceが正しく初期化される
                mock_service_class.assert_called_once_with(mock_dependencies["db_manager"])

                # サービスがインスタンス変数に設定される
                assert mock_window.image_db_write_service == mock_service_instance

                # ウィジェットにサービスが注入される
                mock_window.selected_image_details_widget.set_image_db_write_service.assert_called_once_with(
                    mock_service_instance
                )

                # ログが出力される
                mock_logger.info.assert_called_with(
                    "ImageDBWriteService created and injected into SelectedImageDetailsWidget"
                )

    def test_widget_initialization_order(self, mock_dependencies):
        """ウィジェット初期化順序テスト（Phase 3.4）"""
        # setup_custom_widgets後にサービス統合が呼ばれることを確認
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        mock_window.dataset_state = mock_dependencies["dataset_state"]
        mock_window.selected_image_details_widget = Mock()
        mock_window.image_preview = Mock()

        with patch("lorairo.gui.services.image_db_write_service.ImageDBWriteService") as mock_service_class:
            mock_service_instance = Mock()
            mock_service_class.return_value = mock_service_instance

            # サービス統合メソッドを実行
            MainWindow._setup_image_db_write_service(mock_window)

            # ウィジェットが正しく設定される
            assert mock_window.image_db_write_service == mock_service_instance
            mock_window.selected_image_details_widget.set_image_db_write_service.assert_called_once()
            mock_window.image_preview.set_dataset_state_manager.assert_called_once()

    def test_service_error_handling(self, mock_dependencies):
        """サービス初期化エラーハンドリングテスト"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        mock_window.selected_image_details_widget = Mock()

        with patch("lorairo.gui.services.image_db_write_service.ImageDBWriteService") as mock_service_class:
            # サービス初期化エラーをシミュレート
            mock_service_class.side_effect = Exception("Service initialization error")

            # エラーが発生してもプログラムが停止しないことを確認
            with pytest.raises(Exception) as exc_info:
                MainWindow._setup_image_db_write_service(mock_window)

            assert "Service initialization error" in str(exc_info.value)

    def test_widget_injection_validation(self, mock_dependencies):
        """ウィジェット注入検証テスト"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]

        # selected_image_details_widgetがNoneの場合
        mock_window.selected_image_details_widget = None

        with patch("lorairo.gui.services.image_db_write_service.ImageDBWriteService") as mock_service_class:
            mock_service_instance = Mock()
            mock_service_class.return_value = mock_service_instance

            # AttributeErrorが発生する可能性
            with pytest.raises(AttributeError):
                MainWindow._setup_image_db_write_service(mock_window)

    def test_state_manager_connection_validation(self, mock_dependencies):
        """DatasetStateManager接続検証テスト"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state = mock_dependencies["dataset_state"]

        # image_previewがNoneの場合
        mock_window.image_preview = None

        with pytest.raises(AttributeError):
            MainWindow._setup_state_integration(mock_window)

    def test_complete_phase3_integration_workflow(self, mock_dependencies):
        """Phase 3完全統合ワークフローテスト"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        mock_window.dataset_state = mock_dependencies["dataset_state"]
        mock_window.selected_image_details_widget = Mock()
        mock_window.image_preview = Mock()

        with patch("lorairo.gui.services.image_db_write_service.ImageDBWriteService") as mock_service_class:
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                mock_service_instance = Mock()
                mock_service_class.return_value = mock_service_instance

                # Phase 3統合メソッドを順番に実行
                MainWindow._setup_image_db_write_service(mock_window)

                # 全ての統合が正しく実行される
                assert mock_window.image_db_write_service == mock_service_instance
                mock_window.selected_image_details_widget.set_image_db_write_service.assert_called_once()
                mock_window.image_preview.set_dataset_state_manager.assert_called_once()

                # 両方のログが出力される
                expected_calls = [
                    "ImageDBWriteService created and injected into SelectedImageDetailsWidget",
                    "DatasetStateManager connected to widgets",
                ]

                actual_calls = [call[0][0] for call in mock_logger.info.call_args_list]
                for expected_msg in expected_calls:
                    assert expected_msg in actual_calls


if __name__ == "__main__":
    pytest.main([__file__])
