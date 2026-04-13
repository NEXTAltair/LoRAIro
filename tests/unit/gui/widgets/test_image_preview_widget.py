# tests/unit/gui/widgets/test_image_preview_widget.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lorairo.gui.widgets.image_preview import ImagePreviewWidget


class TestImagePreviewWidget:
    """ImagePreviewWidget単体テスト（Enhanced Event-Driven Pattern対応）"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ImagePreviewWidget"""
        widget = ImagePreviewWidget()
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, widget):
        """初期化テスト"""
        assert widget.pixmap_item is None
        assert hasattr(widget, "graphics_scene")
        assert hasattr(widget, "previewGraphicsView")

    def test_adjust_view_size_skips_when_no_pixmap(self, widget):
        """Issue #52リグレッション: pixmap_item が None の場合は fitInView を呼ばない"""
        assert widget.pixmap_item is None

        with patch.object(widget.previewGraphicsView, "fitInView") as mock_fit:
            widget._adjust_view_size()

            # fitInView は呼ばれないこと（縮小バグの根本対策）
            mock_fit.assert_not_called()

    def test_adjust_view_size_calls_fit_when_pixmap_exists(self, widget):
        """pixmap_item がある場合は fitInView を呼ぶ"""
        # Mockのpixmap_itemを設定して pixmap_item != None の状態にする
        widget.pixmap_item = Mock()

        with patch.object(widget.previewGraphicsView, "fitInView") as mock_fit:
            widget._adjust_view_size()

            # fitInView が呼ばれること
            mock_fit.assert_called_once()

    def test_clear_preview(self, widget):
        """プレビュークリア・メモリ最適化テスト"""
        # テストデータ設定
        widget.pixmap_item = Mock()

        with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
            widget._clear_preview()

            # GraphicsSceneがクリアされる
            assert widget.graphics_scene.items() == []

            # PixmapItemがクリアされる
            assert widget.pixmap_item is None

            # ログ確認
            mock_logger.debug.assert_called_with("Preview cleared and memory optimized")

    def test_clear_preview_exception(self, widget):
        """プレビュークリア時の例外処理テスト"""
        widget.graphics_scene.clear = Mock(side_effect=Exception("Clear error"))

        with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
            widget._clear_preview()

            # エラーログが出力される
            mock_logger.error.assert_called_with("Error clearing preview: Clear error", exc_info=True)

    def test_connect_to_data_signals(self, widget):
        """DatasetStateManagerのシグナル接続テスト"""
        mock_state_manager = Mock()
        mock_state_manager.current_image_data_changed = Mock()
        mock_state_manager.current_image_data_changed.connect = Mock(return_value=True)

        widget.connect_to_data_signals(mock_state_manager)

        # シグナルが接続される
        mock_state_manager.current_image_data_changed.connect.assert_called_once_with(
            widget._on_image_data_received
        )

    def test_connect_to_data_signals_none_manager(self, widget):
        """DatasetStateManagerがNoneの場合のテスト"""
        with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
            widget.connect_to_data_signals(None)

            mock_logger.error.assert_called()

    def test_on_image_data_received_empty_data(self, widget):
        """空データ受信時のプレビュークリアテスト"""
        with patch.object(widget, "_clear_preview") as mock_clear:
            widget._on_image_data_received({})

            mock_clear.assert_called_once()

    def test_on_image_data_received_no_path(self, widget):
        """画像パスなしデータ受信テスト"""
        image_data = {"id": 123}

        with patch.object(widget, "_clear_preview") as mock_clear:
            widget._on_image_data_received(image_data)

            mock_clear.assert_called_once()

    def test_on_image_data_received_file_not_found(self, widget):
        """存在しないファイルパス受信テスト"""
        image_data = {
            "id": 123,
            "stored_image_path": "/nonexistent/image.jpg",
        }

        with patch("lorairo.database.db_core.resolve_stored_path") as mock_resolve:
            mock_path = Mock()
            mock_path.exists.return_value = False
            mock_resolve.return_value = mock_path

            with patch.object(widget, "_clear_preview") as mock_clear:
                widget._on_image_data_received(image_data)

                mock_clear.assert_called_once()

    def test_on_image_data_received_success(self, widget):
        """正常な画像データ受信テスト"""
        image_data = {
            "id": 123,
            "stored_image_path": "/valid/image.jpg",
        }

        with patch("lorairo.database.db_core.resolve_stored_path") as mock_resolve:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_path.name = "image.jpg"
            mock_resolve.return_value = mock_path

            with patch.object(widget, "load_image") as mock_load:
                widget._on_image_data_received(image_data)

                mock_load.assert_called_once_with(mock_path)

    def test_load_image_success(self, widget):
        """画像読み込み成功テスト"""
        from PySide6.QtCore import QRectF

        test_path = Path("/test/image.jpg")

        mock_pixmap = Mock()
        mock_pixmap.rect.return_value = QRectF(0, 0, 100, 100)

        with patch("lorairo.gui.widgets.image_preview.QPixmap", return_value=mock_pixmap):
            with patch.object(widget.graphics_scene, "addPixmap", return_value=Mock()) as mock_add:
                widget.load_image(test_path)

                # addPixmap が呼ばれる
                mock_add.assert_called_once_with(mock_pixmap)

                # pixmap_item が設定される
                assert widget.pixmap_item is not None

    def test_load_image_clears_before_loading(self, widget):
        """新しい画像読み込み前に既存をクリアするテスト"""
        test_path = Path("/test/image.jpg")

        with patch.object(widget, "_clear_preview") as mock_clear:
            with patch("lorairo.gui.widgets.image_preview.QPixmap", return_value=Mock()):
                widget.load_image(test_path)

                # クリアが呼ばれる
                mock_clear.assert_called()

    def test_load_image_exception(self, widget):
        """画像読み込み例外処理テスト"""
        test_path = Path("/test/error.jpg")

        with patch("lorairo.gui.widgets.image_preview.QPixmap", side_effect=Exception("Load error")):
            with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
                widget.load_image(test_path)

                # エラーログが出力される
                mock_logger.error.assert_called()

                # pixmap_item は None のまま
                assert widget.pixmap_item is None

    def test_resize_event_calls_adjust(self, widget):
        """resizeEvent で _adjust_view_size が呼ばれるテスト"""
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QResizeEvent

        with patch.object(widget, "_adjust_view_size") as mock_adjust:
            event = QResizeEvent(QSize(500, 400), QSize(400, 300))
            widget.resizeEvent(event)

            mock_adjust.assert_called_once()


class TestAdjustViewSizeRegressionIssue52:
    """Issue #52: 保存ボタンクリックで画像が縮小するバグのリグレッションテスト"""

    @pytest.fixture
    def widget(self, qtbot):
        widget = ImagePreviewWidget()
        qtbot.addWidget(widget)
        return widget

    def test_save_button_cycle_does_not_shrink_preview(self, widget):
        """
        保存ボタンクリックサイクルでもプレビューサイズが縮小しないことを確認。

        再現ステップ:
        1. 画像を表示（pixmap_item 設定）
        2. _clear_preview 呼び出し（保存後のリフレッシュで発生）
        3. _adjust_view_size 呼び出し（QTimer.singleShot経由）
        - 旧実装: setSizePolicy(Ignored) が復元されないため縮小が累積
        - 新実装: fitInView のみ使用、pixmap_item=None 時はスキップ
        """
        # 1. 初期画像表示
        widget.pixmap_item = Mock()

        # 2. _clear_preview（保存クリック後のリフレッシュ相当）
        widget._clear_preview()

        # _clear_preview後は pixmap_item が None
        assert widget.pixmap_item is None

        # 3. _adjust_view_size が呼ばれても fitInView は呼ばれない
        with patch.object(widget.previewGraphicsView, "fitInView") as mock_fit:
            widget._adjust_view_size()

            mock_fit.assert_not_called()

    def test_size_policy_not_modified(self, widget):
        """_adjust_view_size が setSizePolicy を呼ばないことを確認"""
        widget.pixmap_item = Mock()  # 表示中の状態

        with patch.object(widget.previewGraphicsView, "setSizePolicy") as mock_policy:
            widget._adjust_view_size()

            # setSizePolicy は呼ばれない（縮小バグの根本原因だったため）
            mock_policy.assert_not_called()
