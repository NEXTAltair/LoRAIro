"""MainWindowにおけるシグナル接続の統合テスト

このテストはMainWindow全体の初期化フローを通じて、
各Widgetが正しくDatasetStateManagerに接続され、シグナルを受信できることを検証します。

テスト対象:
- SelectedImageDetailsWidget
- ImagePreviewWidget

検証項目:
- DatasetStateManagerへの正規データ経路接続
- connect()戻り値がTrueであること
- シグナル発行→受信の動作確認
- データ受け渡しの正確性検証
- 複数Widget同時受信の検証
"""

from pathlib import Path

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
        MainWindow → WidgetSetupService → connect_to_dataset_state_manager() → DatasetStateManager
        """
        # DatasetStateManagerインスタンス確認
        assert main_window.dataset_state_manager is not None, "DatasetStateManagerが未初期化"

        # WidgetSetupServiceで接続されたインスタンス確認
        assert hasattr(main_window, "selected_image_details_widget"), (
            "selected_image_details_widgetが存在しない"
        )
        widget = main_window.selected_image_details_widget
        assert widget is not None, "Widgetインスタンスがない"

        # テストデータ
        test_data = {
            "id": 123,
            "file_path": "/test/path/test.jpg",
            "stored_image_path": "test.jpg",
            "file_hash": "test_hash",
            "file_size": 1024,
            "width": 800,
            "height": 600,
            "file_type": "jpg",
            "created_at": "2025-01-01T00:00:00",
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        # シグナル発行
        with qtbot.waitSignal(widget.image_details_loaded, timeout=1000) as blocker:
            main_window.dataset_state_manager.current_image_data_changed.emit(test_data)

        # 検証: シグナルが受信されたことを確認
        assert blocker.args[0].image_id == 123, "受信データが正しくない"
        assert widget.current_image_id == 123
        assert widget.current_details.file_name == "test.jpg"

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

        test_image = Path(__file__).resolve().parents[2] / "resources/img/1_img/file01.webp"

        test_data = {
            "id": 456,
            "stored_image_path": str(test_image),
        }

        # シグナル発行
        main_window.dataset_state_manager.current_image_data_changed.emit(test_data)

        # Qt イベントループを回してシグナルを処理
        qtbot.wait(100)

        # 検証: プレビューが実画像を受信して表示したことを確認
        assert widget.pixmap_item is not None, "ImagePreviewWidget経路で画像が表示されていない"

    def test_multiple_widgets_signal_broadcast(self, qtbot, main_window):
        """複数Widgetへのシグナルブロードキャストテスト

        DatasetStateManager → 複数Widgetへの同時配信を検証

        検証項目:
        - SelectedImageDetailsWidgetとImagePreviewWidget両方がシグナルを受信
        - 同一データが両Widgetに配信される
        """
        # SelectedImageDetailsWidget
        widget_details = main_window.selected_image_details_widget

        # ImagePreviewWidget
        widget_preview = main_window.imagePreviewWidget
        test_image = Path(__file__).resolve().parents[2] / "resources/img/1_img/file01.webp"

        # テストデータ
        test_data = {
            "id": 999,
            "file_path": str(test_image),
            "stored_image_path": str(test_image),
            "tags": [],
            "caption_text": "",
            "tags_text": "",
            "score_value": 0,
            "rating_value": "",
        }

        # シグナル発行（1回）
        with qtbot.waitSignal(widget_details.image_details_loaded, timeout=1000) as blocker:
            main_window.dataset_state_manager.current_image_data_changed.emit(test_data)

        # Qt イベントループを回してシグナルを処理
        qtbot.wait(100)

        # 検証: 両Widgetがシグナルを受信したか確認
        assert blocker.args[0].image_id == 999
        assert widget_preview.pixmap_item is not None, "ImagePreviewWidgetが受信していない"

        # 両Widgetに同一データが配信されたか確認
        assert widget_details.current_image_id == 999

    def test_signal_connection_with_multiple_emissions(self, qtbot, main_window):
        """複数回のシグナル発行が正しく処理されることを検証"""
        widget = main_window.selected_image_details_widget
        signal_count = []

        widget.image_details_loaded.connect(lambda details: signal_count.append(details.image_id))

        # 1回目のシグナル
        test_data1 = {"id": 111, "file_path": "/test/path/one.jpg", "tags": []}
        with qtbot.waitSignal(widget.image_details_loaded, timeout=1000):
            main_window.dataset_state_manager.current_image_data_changed.emit(test_data1)

        # 2回目のシグナル
        test_data2 = {"id": 222, "file_path": "/test/path/two.jpg", "tags": []}
        with qtbot.waitSignal(widget.image_details_loaded, timeout=1000):
            main_window.dataset_state_manager.current_image_data_changed.emit(test_data2)

        # 検証
        assert len(signal_count) == 2, f"期待2回、実際{len(signal_count)}回"
        assert signal_count[0] == 111
        assert signal_count[1] == 222

    def test_signal_connection_with_empty_data(self, qtbot, main_window):
        """空データのシグナル発行が正しく処理されることを検証"""
        widget = main_window.selected_image_details_widget
        widget.current_image_id = 123

        # 空データでシグナル発行
        main_window.dataset_state_manager.current_image_data_changed.emit({})
        qtbot.wait(100)

        # 検証: 空データで詳細表示がクリアされる
        assert widget.current_image_id is None
        assert widget.current_details is None
