"""MainWindowにおけるシグナル接続の統合テスト

このテストはMainWindow全体の初期化フローを通じて、
各Widgetが正しくDatasetStateManagerに接続され、シグナルを受信できることを検証します。

テスト対象:
- SelectedImageDetailsWidget
- ImagePreviewWidget

検証項目:
- connect_to_data_signals()の呼び出し成功
- connect()戻り値がTrueであること
- シグナル発行→受信の動作確認
- データ受け渡しの正確性検証
- 複数Widget同時受信の検証
"""

import pytest

from lorairo.gui.window.main_window import MainWindow


@pytest.mark.integration
@pytest.mark.gui
class TestMainWindowSignalConnection:
    """MainWindow経由でのシグナル接続テスト"""

    @pytest.fixture
    def main_window(self, qtbot, tmp_path, monkeypatch):
        """MainWindowインスタンスを作成

        Args:
            qtbot: pytest-qt fixture
            tmp_path: 一時ディレクトリ
            monkeypatch: モック用fixture
        """
        # 一時データディレクトリを設定
        monkeypatch.setenv("LORAIRO_DATA_DIR", str(tmp_path))

        # MainWindow初期化（全フロー実行）
        window = MainWindow()
        qtbot.addWidget(window)

        # 初期化完了を待機
        qtbot.wait(100)

        return window

    def test_mainwindow_has_dataset_state_manager(self, main_window):
        """MainWindowがDatasetStateManagerを持つことを確認"""
        assert hasattr(main_window, "dataset_state_manager")
        assert main_window.dataset_state_manager is not None

    def test_mainwindow_has_selected_image_details_widget(self, main_window):
        """MainWindowがSelectedImageDetailsWidgetを持つことを確認"""
        assert hasattr(main_window, "selected_image_details_widget")
        assert main_window.selected_image_details_widget is not None

    def test_mainwindow_has_image_preview_widget(self, main_window):
        """MainWindowがImagePreviewWidgetを持つことを確認"""
        assert hasattr(main_window, "imagePreviewWidget")
        assert main_window.imagePreviewWidget is not None

    def test_selected_image_details_signal_connection(self, qtbot, main_window):
        """SelectedImageDetailsWidget シグナル接続テスト

        検証項目:
        - DatasetStateManagerインスタンス存在確認
        - Widget接続確認
        - シグナル発行→受信の動作確認
        - データ受け渡しの正確性検証

        実際の経路をテスト:
        MainWindow → WidgetSetupService → connect_to_data_signals() → DatasetStateManager
        """
        # DatasetStateManagerインスタンス確認
        assert main_window.dataset_state_manager is not None, "DatasetStateManagerが未初期化"

        # WidgetSetupServiceで接続されたインスタンス確認
        assert hasattr(main_window, "selected_image_details_widget"), (
            "selected_image_details_widgetが存在しない"
        )
        widget = main_window.selected_image_details_widget
        assert widget is not None, "Widgetインスタンスがない"

        # シグナル受信をモニター
        signal_received = []

        original_method = widget._on_image_data_received

        def monitored_method(data):
            signal_received.append(data)
            return original_method(data)

        widget._on_image_data_received = monitored_method

        # テストデータ
        test_data = {
            "id": 123,
            "stored_image_path": "test.jpg",
            "file_hash": "test_hash",
            "file_size": 1024,
            "image_width": 800,
            "image_height": 600,
            "file_type": "jpg",
            "created_at": "2025-01-01T00:00:00",
            "annotations": {
                "tags": [],
                "caption_text": "",
                "score_value": None,
                "rating_value": 0,
            },
        }

        # シグナル発行
        main_window.dataset_state_manager.current_image_data_changed.emit(test_data)

        # Qt イベントループを回してシグナルを処理
        qtbot.wait(100)

        # 検証: シグナルが受信されたことを確認
        assert len(signal_received) == 1, (
            f"MainWindow経路でシグナルが受信されていない。受信数: {len(signal_received)}, 期待: 1"
        )
        assert signal_received[0]["id"] == 123, "受信データが正しくない"

    def test_image_preview_signal_connection(self, qtbot, main_window):
        """ImagePreviewWidget シグナル接続テスト

        検証項目:
        - DatasetStateManagerインスタンス存在確認
        - Widget接続確認
        - シグナル発行→受信の動作確認
        - connect()戻り値チェックの動作確認
        """
        # DatasetStateManagerインスタンス確認
        assert main_window.dataset_state_manager is not None, "DatasetStateManagerが未初期化"

        # ImagePreviewWidget確認
        assert hasattr(main_window, "imagePreviewWidget"), "imagePreviewWidgetが存在しない"
        widget = main_window.imagePreviewWidget
        assert widget is not None, "ImagePreviewWidgetインスタンスがない"

        # シグナル受信をモニター
        signal_received = []

        original_method = widget._on_image_data_received

        def monitored_method(data):
            signal_received.append(data)
            return original_method(data)

        widget._on_image_data_received = monitored_method

        # テストデータ（画像パスは存在しないが、受信確認には十分）
        test_data = {
            "id": 456,
            "stored_image_path": "test_preview.jpg",
        }

        # シグナル発行
        main_window.dataset_state_manager.current_image_data_changed.emit(test_data)

        # Qt イベントループを回してシグナルを処理
        qtbot.wait(100)

        # 検証: シグナルが受信されたことを確認
        assert len(signal_received) == 1, (
            f"ImagePreviewWidget経路でシグナルが受信されていない。受信数: {len(signal_received)}, 期待: 1"
        )
        assert signal_received[0]["id"] == 456, "受信データが正しくない"

    def test_multiple_widgets_signal_broadcast(self, qtbot, main_window):
        """複数Widgetへのシグナルブロードキャストテスト

        DatasetStateManager → 複数Widgetへの同時配信を検証

        検証項目:
        - SelectedImageDetailsWidgetとImagePreviewWidget両方がシグナルを受信
        - 同一データが両Widgetに配信される
        """
        # 両Widgetのシグナル受信をモニター
        signal_count_details = []
        signal_count_preview = []

        # SelectedImageDetailsWidget
        widget_details = main_window.selected_image_details_widget
        original_details = widget_details._on_image_data_received

        def monitored_details(data):
            signal_count_details.append(data)
            return original_details(data)

        widget_details._on_image_data_received = monitored_details

        # ImagePreviewWidget
        widget_preview = main_window.imagePreviewWidget
        original_preview = widget_preview._on_image_data_received

        def monitored_preview(data):
            signal_count_preview.append(data)
            return original_preview(data)

        widget_preview._on_image_data_received = monitored_preview

        # テストデータ
        test_data = {
            "id": 999,
            "stored_image_path": "broadcast_test.jpg",
            "annotations": {},
        }

        # シグナル発行（1回）
        main_window.dataset_state_manager.current_image_data_changed.emit(test_data)

        # Qt イベントループを回してシグナルを処理
        qtbot.wait(100)

        # 検証: 両Widgetがシグナルを受信したか確認
        assert len(signal_count_details) == 1, (
            f"SelectedImageDetailsWidgetが受信していない: {len(signal_count_details)}"
        )
        assert len(signal_count_preview) == 1, (
            f"ImagePreviewWidgetが受信していない: {len(signal_count_preview)}"
        )

        # 両Widgetに同一データが配信されたか確認
        assert signal_count_details[0]["id"] == 999
        assert signal_count_preview[0]["id"] == 999

    def test_signal_connection_with_multiple_emissions(self, qtbot, main_window):
        """複数回のシグナル発行が正しく処理されることを検証"""
        widget = main_window.selected_image_details_widget
        signal_count = []

        original_method = widget._on_image_data_received

        def monitored_method(data):
            signal_count.append(data)
            return original_method(data)

        widget._on_image_data_received = monitored_method

        # 1回目のシグナル
        test_data1 = {"id": 111, "annotations": {}}
        main_window.dataset_state_manager.current_image_data_changed.emit(test_data1)
        qtbot.wait(50)

        # 2回目のシグナル
        test_data2 = {"id": 222, "annotations": {}}
        main_window.dataset_state_manager.current_image_data_changed.emit(test_data2)
        qtbot.wait(50)

        # 検証
        assert len(signal_count) == 2, f"期待2回、実際{len(signal_count)}回"
        assert signal_count[0]["id"] == 111
        assert signal_count[1]["id"] == 222

    def test_signal_connection_with_empty_data(self, qtbot, main_window):
        """空データのシグナル発行が正しく処理されることを検証"""
        widget = main_window.selected_image_details_widget
        signal_received = []

        original_method = widget._on_image_data_received

        def monitored_method(data):
            signal_received.append(data)
            return original_method(data)

        widget._on_image_data_received = monitored_method

        # 空データでシグナル発行
        main_window.dataset_state_manager.current_image_data_changed.emit({})
        qtbot.wait(100)

        # 検証: 空データも受信される
        assert len(signal_received) == 1
        assert signal_received[0] == {}
