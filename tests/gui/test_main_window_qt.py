# tests/gui/test_main_window_qt_standard.py

"""
MainWindow Qt テスト
pytest-qt 標準仕様に準拠した実装
"""

import os
import sys
import warnings
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QLineEdit, QProgressBar, QPushButton

from lorairo.gui.window.main_window import MainWindow


# Qt環境設定（テスト実行前）
def setup_module():
    """モジュールレベルのQt環境設定"""
    # PySide6 フォント関連警告の抑制
    warnings.filterwarnings("ignore", message=".*propagateSizeHints.*")
    warnings.filterwarnings("ignore", message=".*QFontDatabase.*")

    # プラットフォーム別フォント設定
    if os.name == "nt":  # Windows
        if os.path.exists("C:/Windows/Fonts"):
            os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
        os.environ["QT_QPA_PLATFORM"] = "windows"
    else:  # Linux/WSL
        font_dirs = ["/usr/share/fonts", "/usr/local/share/fonts"]
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                os.environ["QT_QPA_FONTDIR"] = font_dir
                break
        # ヘッドレス環境対応
        if not os.environ.get("DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "offscreen"


class TestMainWindowStandard:
    """pytest-qt標準仕様に準拠したMainWindowテスト"""

    @pytest.fixture
    def main_window(self, qtbot, qt_main_window_mock_config):
        """
        pytest-qt標準のqtbotを使用したMainWindowフィクスチャ
        """
        # 依存関係を全てパッチしてMainWindowを作成
        with (
            patch("lorairo.gui.window.main_window.ConfigurationService") as mock_config_service,
            patch("lorairo.gui.window.main_window.FileSystemManager") as mock_fsm,
            patch("lorairo.gui.window.main_window.ImageRepository"),
            patch("lorairo.gui.window.main_window.ImageDatabaseManager") as mock_db_manager,
            patch("lorairo.gui.window.main_window.WorkerService") as mock_worker_service,
            patch("lorairo.gui.window.main_window.DatasetStateManager") as mock_dataset_state,
            patch("lorairo.gui.window.main_window.FilterSearchPanel") as mock_filter_panel,
            patch("lorairo.gui.window.main_window.ThumbnailSelectorWidget") as mock_thumbnail_widget,
            patch("lorairo.gui.window.main_window.PreviewDetailPanel") as mock_preview_panel,
            patch("lorairo.gui.window.main_window.DefaultSessionLocal"),
        ):
            # モックインスタンス設定
            config_service_instance = qt_main_window_mock_config["config_service"]
            fsm_instance = qt_main_window_mock_config["fsm"]
            db_manager_instance = qt_main_window_mock_config["db_manager"]
            worker_service_instance = qt_main_window_mock_config["worker_service"]
            dataset_state_instance = qt_main_window_mock_config["dataset_state"]

            mock_config_service.return_value = config_service_instance
            mock_fsm.return_value = fsm_instance
            mock_db_manager.return_value = db_manager_instance
            mock_worker_service.return_value = worker_service_instance
            mock_dataset_state.return_value = dataset_state_instance

            # パネルのモック設定（実際のQWidget継承）
            from PySide6.QtCore import Signal as QtSignal
            from PySide6.QtWidgets import QWidget

            class MockWidget(QWidget):
                def __init__(self):
                    super().__init__()

            class MockFilterPanel(MockWidget):
                filter_applied = QtSignal(dict)
                filter_cleared = QtSignal()
                search_requested = QtSignal(dict)

            class MockThumbnailWidget(MockWidget):
                imageSelected = QtSignal(object)
                multipleImagesSelected = QtSignal(list)
                deselected = QtSignal()
                selection_changed = QtSignal(object)

            class MockPreviewPanel(MockWidget):
                pass

            mock_filter_panel.return_value = MockFilterPanel()
            mock_thumbnail_widget.return_value = MockThumbnailWidget()
            mock_preview_panel.return_value = MockPreviewPanel()

            # MainWindow作成
            window = MainWindow()

            # qtbot標準機能でウィジェット管理
            qtbot.addWidget(window)

            return window

    def test_window_creation_basic(self, qtbot, main_window):
        """基本的なウィンドウ作成テスト（qtbot使用）"""
        # ウィンドウが正常に作成されることを確認
        assert main_window is not None
        assert hasattr(main_window, "labelStatus")
        assert hasattr(main_window, "lineEditDatasetPath")
        assert hasattr(main_window, "pushButtonSelectDataset")

    def test_window_show_hide(self, qtbot, main_window):
        """ウィンドウ表示・非表示テスト"""
        # 初期状態確認
        assert not main_window.isVisible()

        # ウィンドウ表示
        main_window.show()
        with qtbot.waitExposed(main_window):  # pytest-qt推奨の待機機能
            pass
        assert main_window.isVisible()

        # ウィンドウ隠す
        main_window.hide()
        qtbot.wait(100)  # 短時間待機
        assert not main_window.isVisible()

    def test_window_basic_properties(self, qtbot, main_window):
        """ウィンドウ基本プロパティテスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # サイズ確認
        assert main_window.width() > 0
        assert main_window.height() > 0

        # タイトル確認（設定されている場合）
        window_title = main_window.windowTitle()
        assert isinstance(window_title, str)

    def test_line_edit_interaction(self, qtbot, main_window):
        """テキスト入力フィールドの相互作用テスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # lineEditDatasetPathの確認
        line_edit = main_window.lineEditDatasetPath
        assert isinstance(line_edit, QLineEdit)

        # テキスト設定・取得（ウィジェット標準メソッド使用）
        test_path = "/test/dataset/path"
        line_edit.setText(test_path)
        assert line_edit.text() == test_path

    def test_button_click_simulation(self, qtbot, main_window):
        """ボタンクリックシミュレーション"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # データセット選択ボタンの確認
        button = main_window.pushButtonSelectDataset
        assert isinstance(button, QPushButton)

        # ボタンが有効であることを確認
        assert button.isEnabled()

        # QFileDialogをモック化してダイアログ表示を回避
        with patch("lorairo.gui.window.main_window.QFileDialog") as mock_dialog:
            # ダイアログが空文字列を返すように設定（キャンセル相当）
            mock_dialog.getExistingDirectory.return_value = ""

            # qtbot標準のクリック機能を使用
            qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

            # ダイアログが呼ばれたことを確認
            mock_dialog.getExistingDirectory.assert_called_once()

        # ボタンクリック後の処理が完了するまで待機
        qtbot.wait(100)

    def test_dataset_selection_with_valid_path(self, qtbot, main_window):
        """データセット選択ボタン（有効パス選択）テスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        button = main_window.pushButtonSelectDataset

        # QFileDialogとload_datasetメソッドをモック化
        with (
            patch("lorairo.gui.window.main_window.QFileDialog") as mock_dialog,
            patch.object(main_window, "load_dataset") as mock_load_dataset,
        ):
            # 有効なパスを返すように設定
            test_path = "/test/valid/dataset/path"
            mock_dialog.getExistingDirectory.return_value = test_path

            # ボタンクリック
            qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

            # ダイアログとload_datasetが呼ばれたことを確認
            mock_dialog.getExistingDirectory.assert_called_once()
            mock_load_dataset.assert_called_once()

    def test_settings_button_click(self, qtbot, main_window):
        """設定ボタンクリックテスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # 設定ボタンがある場合のテスト
        if hasattr(main_window, "pushButtonSettings"):
            button = main_window.pushButtonSettings

            # QMessageBoxをモック化してダイアログ表示を回避
            with patch("lorairo.gui.window.main_window.QMessageBox") as mock_msgbox:
                qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
                # メッセージボックスが呼ばれたことを確認
                mock_msgbox.information.assert_called_once()

    def test_progress_bar_functionality(self, qtbot, main_window):
        """プログレスバー機能テスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # プログレスバーの確認
        progress_bar = main_window.progressBarRegistration
        assert isinstance(progress_bar, QProgressBar)

        # 値の設定・確認
        test_values = [0, 25, 50, 75, 100]
        for value in test_values:
            progress_bar.setValue(value)
            qtbot.wait(10)  # 短時間待機
            assert progress_bar.value() == value

    def test_status_label_updates(self, qtbot, main_window):
        """ステータスラベル更新テスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # ステータスラベルの確認
        status_label = main_window.labelStatus
        assert isinstance(status_label, QLabel)

        # テキスト更新テスト
        test_messages = ["準備完了", "データセット読み込み中...", "処理完了", "テストメッセージ"]

        for message in test_messages:
            status_label.setText(message)
            qtbot.wait(10)
            assert status_label.text() == message

    def test_keyboard_events(self, qtbot, main_window):
        """キーボードイベントテスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # ウィンドウにフォーカス設定
        main_window.activateWindow()
        with qtbot.waitActive(main_window):
            pass

        # キーボード入力テスト（基本的なキー）
        qtbot.keyClick(main_window, Qt.Key_Tab)
        qtbot.keyClick(main_window, Qt.Key_Escape)

    def test_resize_window(self, qtbot, main_window):
        """ウィンドウリサイズテスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # リサイズテスト
        test_sizes = [(800, 600), (1024, 768), (1200, 800)]

        for width, height in test_sizes:
            main_window.resize(width, height)
            qtbot.wait(50)  # リサイズ処理を待機

            # サイズ確認（完全一致でない場合があるため、近似確認）
            # Windows環境ではフレームサイズが大きいため、許容誤差を拡大
            actual_size = main_window.size()
            assert abs(actual_size.width() - width) <= 30
            assert abs(actual_size.height() - height) <= 30

    def test_widget_focus_management(self, qtbot, main_window):
        """ウィジェットフォーカス管理テスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # テキスト入力フィールドにフォーカス設定
        line_edit = main_window.lineEditDatasetPath
        line_edit.setFocus()
        qtbot.wait(10)

        # フォーカス確認
        assert line_edit.hasFocus()

    def test_signal_emission_basic(self, qtbot, main_window):
        """シグナル発行基本テスト"""
        # カスタムシグナルが存在することを確認
        assert hasattr(main_window, "dataset_loaded")
        assert hasattr(main_window, "database_registration_completed")

        # シグナル受信テスト
        with qtbot.waitSignal(main_window.dataset_loaded, timeout=1000) as signal_blocker:
            # シグナル発行
            test_path = "/test/dataset/path"
            main_window.dataset_loaded.emit(test_path)

        # 受信確認
        assert signal_blocker.args == [test_path]

    def test_async_operations_simulation(self, qtbot, main_window):
        """非同期操作シミュレーション"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # QTimerを使った非同期的なUI更新をシミュレート
        update_count = 0

        def update_progress():
            nonlocal update_count
            update_count += 1
            main_window.progressBarRegistration.setValue(update_count * 20)

            if update_count < 5:
                QTimer.singleShot(100, update_progress)

        # 非同期更新開始
        QTimer.singleShot(10, update_progress)

        # qtbot標準の待機機能を使用
        qtbot.waitUntil(lambda: update_count >= 5, timeout=2000)

        # 更新完了確認
        assert update_count == 5
        assert main_window.progressBarRegistration.value() == 100

    def test_mock_integration(self, qtbot, main_window, qt_main_window_mock_config):
        """モック統合テスト"""
        # モックされたサービスが正常に注入されていることを確認
        assert main_window.config_service is not None
        assert main_window.fsm is not None
        assert main_window.db_manager is not None

        # モックされたメソッドの呼び出しテスト
        mock_config = qt_main_window_mock_config["config_service"]
        result = main_window.config_service.get_setting("test_key")
        mock_config.get_setting.assert_called_with("test_key")
        assert result is None  # モックで設定した戻り値

    def test_error_handling_simulation(self, qtbot, main_window):
        """エラーハンドリングシミュレーション"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # エラー状況をシミュレート（例：無効なパス設定）
        with patch("lorairo.gui.window.main_window.QMessageBox"):
            # 何らかのエラー処理をトリガー
            main_window.labelStatus.setText("エラーが発生しました")

            # UI状態確認
            assert main_window.labelStatus.text() == "エラーが発生しました"

    def test_cleanup_on_close(self, qtbot, main_window):
        """クローズ時のクリーンアップテスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # ウィンドウクローズ
        main_window.close()
        qtbot.wait(100)

        # クローズ状態確認
        assert not main_window.isVisible()

    @pytest.mark.parametrize(
        "test_text",
        [
            "英語テキスト",
            "日本語テキスト",
            "Mixed English 日本語",
            "数字123と記号!@#",
            "",  # 空文字列
        ],
    )
    def test_internationalization_support(self, qtbot, main_window, test_text):
        """国際化サポートテスト（パラメータ化）"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # 様々な文字セットでテキスト設定
        main_window.labelStatus.setText(test_text)
        qtbot.wait(10)

        # 正しく設定されることを確認
        assert main_window.labelStatus.text() == test_text

    def test_widget_hierarchy_verification(self, qtbot, main_window):
        """ウィジェット階層検証テスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        # 子ウィジェットの存在確認
        children = main_window.findChildren(object)
        assert len(children) > 0

        # 特定のウィジェットタイプの検索
        line_edits = main_window.findChildren(QLineEdit)
        assert len(line_edits) >= 1  # 少なくとも1つは存在

        buttons = main_window.findChildren(QPushButton)
        assert len(buttons) >= 1  # 少なくとも1つは存在

    def test_performance_basic_operations(self, qtbot, main_window):
        """基本操作のパフォーマンステスト"""
        main_window.show()
        with qtbot.waitExposed(main_window):
            pass

        import time

        # 大量のUI更新のパフォーマンステスト
        start_time = time.time()

        for i in range(100):
            main_window.progressBarRegistration.setValue(i % 101)
            if i % 10 == 0:  # 10回に1回だけイベント処理
                qtbot.wait(1)

        end_time = time.time()
        execution_time = end_time - start_time

        # パフォーマンス確認（1秒以内で完了することを期待）
        assert execution_time < 1.0


class TestMainWindowAdvanced:
    """高度なQt機能のテスト"""

    @pytest.fixture
    def advanced_window(self, qtbot, qt_main_window_mock_config):
        """高度テスト用のMainWindow"""
        # 基本的なセットアップは同じだが、より詳細な設定が必要な場合に使用
        with (
            patch("lorairo.gui.window.main_window.ConfigurationService") as mock_config,
            patch("lorairo.gui.window.main_window.FileSystemManager") as mock_fsm,
            patch("lorairo.gui.window.main_window.ImageRepository"),
            patch("lorairo.gui.window.main_window.ImageDatabaseManager") as mock_db,
            patch("lorairo.gui.window.main_window.WorkerService") as mock_worker,
            patch("lorairo.gui.window.main_window.DatasetStateManager") as mock_state,
            patch("lorairo.gui.window.main_window.FilterSearchPanel") as mock_filter,
            patch("lorairo.gui.window.main_window.ThumbnailSelectorWidget") as mock_thumb,
            patch("lorairo.gui.window.main_window.PreviewDetailPanel") as mock_preview,
            patch("lorairo.gui.window.main_window.DefaultSessionLocal"),
        ):
            # より詳細なモック設定
            mock_config.return_value = qt_main_window_mock_config["config_service"]
            mock_fsm.return_value = qt_main_window_mock_config["fsm"]
            mock_db.return_value = qt_main_window_mock_config["db_manager"]
            mock_worker.return_value = qt_main_window_mock_config["worker_service"]
            mock_state.return_value = qt_main_window_mock_config["dataset_state"]

            # パネルのモック（QWidget継承）
            from PySide6.QtCore import Signal
            from PySide6.QtWidgets import QWidget

            class MockPanel(QWidget):
                test_signal = Signal()

                def __init__(self):
                    super().__init__()

            mock_filter.return_value = MockPanel()
            mock_thumb.return_value = MockPanel()
            mock_preview.return_value = MockPanel()

            window = MainWindow()
            qtbot.addWidget(window)

            return window

    def test_signal_connection_verification(self, qtbot, advanced_window):
        """シグナル接続の検証テスト"""
        # カスタムシグナルが存在し、接続可能であることを確認
        signals_to_test = ["dataset_loaded", "database_registration_completed"]

        for signal_name in signals_to_test:
            assert hasattr(advanced_window, signal_name)
            signal = getattr(advanced_window, signal_name)

            # テスト用のスロット関数
            received_args = []

            def test_slot(*args):
                received_args.extend(args)

            # シグナル接続
            signal.connect(test_slot)

            # シグナル発行テスト
            test_data = f"test_data_for_{signal_name}"
            signal.emit(test_data)
            qtbot.wait(10)

            # 受信確認
            assert test_data in received_args

    def test_exception_capture(self, qtbot, advanced_window):
        """例外キャプチャテスト"""
        advanced_window.show()
        qtbot.waitForWindowShown(advanced_window)

        # qtbot標準の例外キャプチャ機能を使用
        with qtbot.captureExceptions() as exceptions:
            # 正常操作（例外は発生しない想定）
            advanced_window.labelStatus.setText("正常操作")
            qtbot.wait(10)

        # 例外が発生しなかったことを確認
        assert len(exceptions) == 0

    def test_screenshot_capture(self, qtbot, advanced_window):
        """スクリーンショットキャプチャテスト"""
        advanced_window.show()
        qtbot.waitForWindowShown(advanced_window)

        # qtbot標準のスクリーンショット機能
        screenshot = qtbot.screenshot(advanced_window)
        assert screenshot is not None
        assert screenshot.size().width() > 0
        assert screenshot.size().height() > 0

    def test_wait_conditions(self, qtbot, advanced_window):
        """待機条件テスト"""
        advanced_window.show()
        qtbot.waitForWindowShown(advanced_window)

        # 条件待機のテスト
        progress_bar = advanced_window.progressBarRegistration

        # 非同期でプログレスバーを更新
        def update_progress():
            for i in range(0, 101, 10):
                QTimer.singleShot(i * 10, lambda value=i: progress_bar.setValue(value))

        update_progress()

        # qtbot標準の条件待機機能
        qtbot.waitUntil(lambda: progress_bar.value() >= 50, timeout=2000)
        assert progress_bar.value() >= 50

    def test_memory_usage_monitoring(self, qtbot, advanced_window):
        """メモリ使用量監視テスト"""
        import gc

        advanced_window.show()
        qtbot.waitForWindowShown(advanced_window)

        # 初期状態のメモリ使用量
        gc.collect()
        initial_refs = sys.getrefcount(advanced_window)

        # 大量の操作を実行
        for i in range(100):
            advanced_window.labelStatus.setText(f"操作 {i}")
            if i % 10 == 0:
                qtbot.wait(1)

        # ガベージコレクション実行
        gc.collect()
        final_refs = sys.getrefcount(advanced_window)

        # メモリリークがないことを確認（参照カウントが大幅に増加していない）
        ref_increase = final_refs - initial_refs
        assert ref_increase <= 5  # 許容範囲内の増加
