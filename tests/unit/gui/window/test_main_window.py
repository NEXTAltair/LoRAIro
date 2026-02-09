"""MainWindow ユニットテスト

責任分離後のMainWindowのビジネスロジックをテスト
- データベースアクセスロジック
- エラーハンドリング
- サービス統合

Note: これらのテストはGUIコンポーネントを実際に作成せず、
ビジネスロジックのみをテストします。
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


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
        """ImageDBWriteService統合テスト: シグナル接続パターン"""
        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._setup_image_db_write_service

        # モックオブジェクト作成（シグナル属性を持つウィジェット）
        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        mock_widget = Mock()
        mock_widget.rating_updated = Mock()
        mock_widget.score_updated = Mock()
        mock_widget.save_requested = Mock()
        mock_window.selected_image_details_widget = mock_widget

        with patch("lorairo.gui.window.main_window.ImageDBWriteService") as mock_service_class:
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                mock_service_instance = Mock()
                mock_service_class.return_value = mock_service_instance

                # メソッド実行
                method(mock_window)

                # ImageDBWriteServiceが正しく初期化される
                mock_service_class.assert_called_once_with(mock_dependencies["db_manager"])

                # サービスがインスタンス変数に設定される
                assert mock_window.image_db_write_service == mock_service_instance

                # シグナルが接続される
                mock_widget.rating_updated.connect.assert_called_once()
                mock_widget.score_updated.connect.assert_called_once()
                mock_widget.save_requested.connect.assert_called_once()

                # ログが出力される
                mock_logger.info.assert_called_with("ImageDBWriteService created and signals connected")

    def test_setup_image_db_write_service_view_only(self, mock_dependencies):
        """ImageDBWriteService: 閲覧専用ウィジェット（シグナルなし）"""
        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._setup_image_db_write_service

        mock_window = Mock()
        mock_window.db_manager = mock_dependencies["db_manager"]
        # hasattr が False を返すようにspec設定
        mock_widget = Mock(spec=[])
        mock_window.selected_image_details_widget = mock_widget

        with patch("lorairo.gui.window.main_window.ImageDBWriteService") as mock_service_class:
            with patch("lorairo.gui.window.main_window.logger") as mock_logger:
                mock_service_instance = Mock()
                mock_service_class.return_value = mock_service_instance

                method(mock_window)

                # サービスは作成される
                mock_service_class.assert_called_once_with(mock_dependencies["db_manager"])
                assert mock_window.image_db_write_service == mock_service_instance

                # シグナル接続はスキップされる
                mock_logger.info.assert_called_with(
                    "SelectedImageDetailsWidget is view-only; edit signals not connected"
                )

    def test_setup_image_db_write_service_missing_deps(self, mock_dependencies):
        """ImageDBWriteService: 依存関係なし時の警告"""
        from lorairo.gui.window.main_window import MainWindow

        method = MainWindow._setup_image_db_write_service

        mock_window = Mock()
        mock_window.db_manager = None
        mock_window.selected_image_details_widget = Mock()

        with patch("lorairo.gui.window.main_window.logger") as mock_logger:
            method(mock_window)

            mock_logger.warning.assert_called_once()

    def test_state_manager_connection_validation(self, mock_dependencies):
        """DatasetStateManager接続検証テスト"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.dataset_state = mock_dependencies["dataset_state"]

        # image_previewがNoneの場合
        mock_window.image_preview = None

        with pytest.raises(AttributeError):
            MainWindow._setup_state_integration(mock_window)


class TestMainWindowBatchRatingScore:
    """MainWindow バッチRating/Score更新テスト"""

    @pytest.fixture
    def mock_window(self):
        """バッチ処理テスト用のモックMainWindow"""
        window = Mock()
        window.image_db_write_service = Mock()
        window.dataset_state_manager = Mock()
        return window

    def test_execute_batch_rating_write_success(self, mock_window):
        """バッチRating書き込みが成功する"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window.image_db_write_service.update_rating_batch.return_value = True

        result = MainWindow._execute_batch_rating_write(mock_window, [1, 2, 3], "PG-13")

        assert result is True
        mock_window.image_db_write_service.update_rating_batch.assert_called_once_with([1, 2, 3], "PG-13")

    def test_execute_batch_rating_write_no_service(self, mock_window):
        """ImageDBWriteService 未初期化時に False を返す"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window.image_db_write_service = None

        result = MainWindow._execute_batch_rating_write(mock_window, [1, 2, 3], "R")

        assert result is False

    def test_execute_batch_score_write_success(self, mock_window):
        """バッチScore書き込みが成功する"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window.image_db_write_service.update_score_batch.return_value = True

        result = MainWindow._execute_batch_score_write(mock_window, [1, 2, 3], 750)

        assert result is True
        mock_window.image_db_write_service.update_score_batch.assert_called_once_with([1, 2, 3], 750)

    def test_execute_batch_score_write_no_service(self, mock_window):
        """ImageDBWriteService 未初期化時に False を返す"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window.image_db_write_service = None

        result = MainWindow._execute_batch_score_write(mock_window, [1, 2, 3], 500)

        assert result is False

    def test_handle_batch_rating_changed_refreshes_cache(self, mock_window):
        """バッチRating変更後にキャッシュが更新される"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window.image_db_write_service.update_rating_batch.return_value = True

        MainWindow._handle_batch_rating_changed(mock_window, [1, 2, 3], "X")

        mock_window.dataset_state_manager.refresh_images.assert_called_once_with([1, 2, 3])

    def test_handle_batch_score_changed_refreshes_cache(self, mock_window):
        """バッチScore変更後にキャッシュが更新される"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window.image_db_write_service.update_score_batch.return_value = True

        MainWindow._handle_batch_score_changed(mock_window, [1, 2, 3], 850)

        mock_window.dataset_state_manager.refresh_images.assert_called_once_with([1, 2, 3])


class TestMainWindowSelectionClear:
    """選択解除時のクリア処理テスト"""

    def test_handle_selection_changed_clears_display_on_empty(self, qtbot):
        """画像選択なし（0件）時に_clear_display()が呼ばれる"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.selectedImageDetailsWidget = Mock()

        MainWindow._handle_selection_changed_for_rating(mock_window, [])

        mock_window.selectedImageDetailsWidget._clear_display.assert_called_once()


class TestMainWindowTagAddFeedback:
    """タグ追加フィードバックテスト"""

    def test_handle_batch_tag_add_success_shows_status_bar(self, qtbot):
        """バッチタグ追加成功でstatusBarに通知"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.batchTagAddWidget = Mock()
        mock_window.statusBar = Mock(return_value=Mock())

        with patch.object(MainWindow, "_execute_batch_tag_write", return_value=True):
            MainWindow._handle_batch_tag_add(mock_window, [1, 2], "landscape")

            mock_window.statusBar().showMessage.assert_called_once()
            args = mock_window.statusBar().showMessage.call_args[0]
            assert "landscape" in args[0]
            assert "2" in args[0]

    def test_handle_batch_tag_add_failure_shows_critical(self, qtbot):
        """バッチタグ追加失敗でQMessageBox.critical表示"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window._execute_batch_tag_write = Mock(return_value=False)

        with patch("lorairo.gui.window.main_window.QMessageBox.critical") as mock_critical:
            MainWindow._handle_batch_tag_add(mock_window, [1, 2], "test")

            mock_critical.assert_called_once()
            args = mock_critical.call_args[0]
            assert "失敗" in args[1]

    def test_handle_quick_tag_add_success_shows_status_bar(self, qtbot):
        """クイックタグ追加成功でstatusBarに通知"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window.statusBar = Mock(return_value=Mock())

        with patch.object(MainWindow, "_execute_batch_tag_write", return_value=True):
            MainWindow._handle_quick_tag_add(mock_window, [1], "portrait")

            mock_window.statusBar().showMessage.assert_called_once()
            args = mock_window.statusBar().showMessage.call_args[0]
            assert "portrait" in args[0]

    def test_handle_quick_tag_add_failure_shows_critical(self, qtbot):
        """クイックタグ追加失敗でQMessageBox.critical表示"""
        from lorairo.gui.window.main_window import MainWindow

        mock_window = Mock()
        mock_window._execute_batch_tag_write = Mock(return_value=False)

        with patch("lorairo.gui.window.main_window.QMessageBox.critical") as mock_critical:
            MainWindow._handle_quick_tag_add(mock_window, [1], "test")

            mock_critical.assert_called_once()
            args = mock_critical.call_args[0]
            assert "失敗" in args[1]


if __name__ == "__main__":
    pytest.main([__file__])
