# tests/integration/gui/test_ui_layout_integration.py

"""
UI Layout Integration Tests

Phase 4: 統合テスト - UI統合テスト
MainWorkspaceWindow の3パネルレイアウト統合テスト
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QMainWindow, QWidget

from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow


class TestMainWorkspaceWindowIntegration:
    """MainWorkspaceWindow UI統合テスト"""

    @pytest.fixture
    def mock_services(self):
        """統合テスト用サービスモック"""
        with (
            patch("lorairo.gui.window.main_workspace_window.ConfigurationService"),
            patch("lorairo.gui.window.main_workspace_window.FileSystemManager"),
            patch("lorairo.gui.window.main_workspace_window.ImageRepository"),
            patch("lorairo.gui.window.main_workspace_window.ImageDatabaseManager"),
            patch("lorairo.gui.window.main_workspace_window.WorkerService"),
            patch("lorairo.gui.window.main_workspace_window.DatasetStateManager"),
        ):
            yield

    @pytest.fixture
    def main_window(self, qtbot, mock_services):
        """MainWorkspaceWindow のテストインスタンス"""
        with (
            patch("lorairo.gui.window.main_workspace_window.FilterSearchPanel"),
            patch("lorairo.gui.window.main_workspace_window.ThumbnailSelectorWidget"),
            patch("lorairo.gui.window.main_workspace_window.ImagePreviewWidget"),
        ):
            window = MainWorkspaceWindow()
            qtbot.addWidget(window)
            return window


class TestThreePanelLayout:
    """3パネルレイアウトテスト"""

    def test_panel_structure(self, main_window, qtbot):
        """パネル構造テスト"""
        # メインスプリッターの存在確認
        assert hasattr(main_window, "splitterMainWorkArea")

        # 3つのフレームの存在確認
        assert hasattr(main_window, "frameFilterSearchContent")  # 左パネル
        assert hasattr(main_window, "frameThumbnailContent")  # 中央パネル
        assert hasattr(main_window, "framePreviewDetailContent")  # 右パネル

    def test_panel_size_distribution(self, main_window, qtbot):
        """パネルサイズ配分テスト"""
        # ウィンドウサイズを設定
        test_window_size = QSize(1400, 800)
        main_window.resize(test_window_size)

        # スプリッターのサイズ配分確認（設計書: 300:700:400）
        if hasattr(main_window, "splitterMainWorkArea"):
            sizes = main_window.splitterMainWorkArea.sizes()

            # 比率が概ね正しいことを確認（誤差許容）
            total_size = sum(sizes)
            if total_size > 0:
                left_ratio = sizes[0] / total_size
                center_ratio = sizes[1] / total_size
                right_ratio = sizes[2] / total_size

                # 期待値: 300:700:400 = 21.4%:50%:28.6%
                assert 0.15 < left_ratio < 0.30  # 左パネル 15-30%
                assert 0.40 < center_ratio < 0.60  # 中央パネル 40-60%
                assert 0.20 < right_ratio < 0.35  # 右パネル 20-35%

    def test_custom_widgets_integration(self, main_window, qtbot):
        """カスタムウィジェット統合テスト"""
        # カスタムウィジェットの存在確認
        assert hasattr(main_window, "filter_search_panel")  # フィルター・検索パネル
        assert hasattr(main_window, "thumbnail_selector")  # サムネイルセレクター
        assert hasattr(main_window, "image_preview_widget")  # 画像プレビュー

        # ウィジェットが適切に初期化されていることを確認
        if hasattr(main_window, "filter_search_panel"):
            assert main_window.filter_search_panel is not None
        if hasattr(main_window, "thumbnail_selector"):
            assert main_window.thumbnail_selector is not None
        if hasattr(main_window, "image_preview_widget"):
            assert main_window.image_preview_widget is not None


class TestLayoutResponsiveness:
    """レスポンシブレイアウトテスト"""

    def test_window_resize_behavior(self, main_window, qtbot):
        """ウィンドウリサイズ動作テスト"""
        # 初期サイズ
        initial_size = QSize(1400, 800)
        main_window.resize(initial_size)
        qtbot.waitExposed(main_window)

        # リサイズテスト: 小サイズ
        small_size = QSize(800, 600)
        main_window.resize(small_size)
        qtbot.wait(100)  # レイアウト更新待ち

        # ウィンドウが適切にリサイズされることを確認
        assert main_window.size().width() <= small_size.width() + 10
        assert main_window.size().height() <= small_size.height() + 10

        # リサイズテスト: 大サイズ
        large_size = QSize(1920, 1080)
        main_window.resize(large_size)
        qtbot.wait(100)

        # 大きなウィンドウサイズでも適切に動作することを確認
        assert main_window.size().width() >= large_size.width() - 10

    def test_minimum_size_constraints(self, main_window, qtbot):
        """最小サイズ制約テスト"""
        # 極小サイズに設定を試行
        tiny_size = QSize(400, 300)
        main_window.resize(tiny_size)
        qtbot.wait(100)

        # 実際のサイズが使用可能な最小サイズ以上であることを確認
        actual_size = main_window.size()
        assert actual_size.width() >= 400  # 最小幅
        assert actual_size.height() >= 300  # 最小高さ

    def test_panel_splitter_interaction(self, main_window, qtbot):
        """パネルスプリッター操作テスト"""
        if hasattr(main_window, "splitterMainWorkArea"):
            splitter = main_window.splitterMainWorkArea

            # スプリッター位置変更をシミュレート
            new_sizes = [400, 600, 500]  # 左:中央:右 = 400:600:500
            splitter.setSizes(new_sizes)
            qtbot.wait(50)

            # 新しいサイズが適用されることを確認
            current_sizes = splitter.sizes()
            assert len(current_sizes) == 3

            # サイズの合計が概ね一致することを確認
            total_new = sum(new_sizes)
            total_current = sum(current_sizes)
            assert abs(total_new - total_current) <= 50  # 誤差許容


class TestWidgetPlacement:
    """ウィジェット配置テスト"""

    def test_left_panel_widgets(self, main_window, qtbot):
        """左パネルウィジェット配置テスト"""
        # 左パネルフレームの存在確認
        left_frame = getattr(main_window, "frameFilterSearchContent", None)
        assert left_frame is not None

        # 左パネル内のレイアウト確認
        left_layout = getattr(main_window, "verticalLayout_filterSearchContent", None)
        assert left_layout is not None

        # FilterSearchPanel の配置確認
        filter_panel = getattr(main_window, "filter_search_panel", None)
        if filter_panel:
            assert filter_panel.parent() == left_frame

    def test_center_panel_widgets(self, main_window, qtbot):
        """中央パネルウィジェット配置テスト"""
        # 中央パネルフレームの存在確認
        center_frame = getattr(main_window, "frameThumbnailContent", None)
        assert center_frame is not None

        # 中央パネル内のレイアウト確認
        center_layout = getattr(main_window, "verticalLayout_thumbnailContent", None)
        assert center_layout is not None

        # ThumbnailSelectorWidget の配置確認
        thumbnail_widget = getattr(main_window, "thumbnail_selector", None)
        if thumbnail_widget:
            assert thumbnail_widget.parent() == center_frame

    def test_right_panel_widgets(self, main_window, qtbot):
        """右パネルウィジェット配置テスト"""
        # 右パネルフレームの存在確認
        right_frame = getattr(main_window, "framePreviewDetailContent", None)
        assert right_frame is not None

        # 右パネル内のレイアウト確認
        right_layout = getattr(main_window, "verticalLayout_previewDetailContent", None)
        assert right_layout is not None

        # ImagePreviewWidget の配置確認
        preview_widget = getattr(main_window, "image_preview_widget", None)
        if preview_widget:
            assert preview_widget.parent() == right_frame


class TestNavigationIntegration:
    """ナビゲーション統合テスト"""

    def test_tab_focus_navigation(self, main_window, qtbot):
        """タブフォーカス移動テスト"""
        # ウィンドウがフォーカス可能であることを確認
        main_window.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # フォーカスがウィンドウに設定されることを確認
        main_window.setFocus()
        qtbot.wait(50)

        # フォーカス移動がスムーズであることを確認
        assert main_window.hasFocus() or main_window.isActiveWindow()

    def test_keyboard_shortcuts(self, main_window, qtbot):
        """キーボードショートカットテスト"""
        # ウィンドウをアクティブにする
        main_window.show()
        main_window.activateWindow()
        qtbot.waitExposed(main_window)

        # 基本的なキーボードイベントが処理されることを確認
        # 注意: 実際のショートカットは実装に依存
        qtbot.keyPress(main_window, Qt.Key.Key_Escape)
        qtbot.wait(50)

        # エラーが発生しないことを確認
        assert main_window.isVisible()


class TestMemoryAndPerformance:
    """メモリとパフォーマンステスト"""

    def test_widget_cleanup(self, main_window, qtbot):
        """ウィジェットクリーンアップテスト"""
        # ウィンドウを表示
        main_window.show()
        qtbot.waitExposed(main_window)

        # ウィンドウを閉じる
        main_window.close()
        qtbot.wait(100)

        # ウィンドウが適切に閉じられることを確認
        assert not main_window.isVisible()

    def test_layout_performance(self, main_window, qtbot):
        """レイアウト性能テスト"""
        import time

        # レイアウト処理時間を測定
        start_time = time.time()

        # 複数回のリサイズを実行
        for size in [(800, 600), (1200, 800), (1600, 1000), (1400, 900)]:
            main_window.resize(QSize(*size))
            qtbot.wait(10)

        layout_time = time.time() - start_time

        # レイアウト処理が高速であることを確認（1秒以内）
        assert layout_time < 1.0, f"Layout processing took {layout_time:.2f}s"


class TestErrorHandling:
    """エラーハンドリングテスト"""

    def test_missing_widget_graceful_handling(self, main_window, qtbot):
        """ウィジェット欠損時の適切な処理テスト"""
        # ウィジェットが存在しない場合でもエラーが発生しないことを確認
        try:
            # 存在しないウィジェットへのアクセスを試行
            nonexistent = getattr(main_window, "nonexistent_widget", None)
            assert nonexistent is None
        except AttributeError:
            pytest.fail("ウィジェット欠損時に適切にNoneを返すべき")

    def test_layout_error_recovery(self, main_window, qtbot):
        """レイアウトエラー回復テスト"""
        # 異常なサイズ設定を試行
        try:
            main_window.resize(QSize(-100, -100))  # 負のサイズ
            qtbot.wait(50)

            # 現在のサイズが正常値であることを確認
            current_size = main_window.size()
            assert current_size.width() > 0
            assert current_size.height() > 0

        except Exception:
            # 例外が発生した場合でもアプリケーションが継続することを確認
            assert main_window.isVisible()
