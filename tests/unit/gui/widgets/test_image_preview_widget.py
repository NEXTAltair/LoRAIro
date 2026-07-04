# tests/unit/gui/widgets/test_image_preview_widget.py

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt

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
        assert widget.previewGraphicsView.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

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
        widget._current_image_path = Path("/test/image.jpg")
        widget._current_pixmap = Mock()

        with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
            mock_logger.opt.return_value = mock_logger
            widget._clear_preview()

            # GraphicsSceneがクリアされる
            assert widget.graphics_scene.items() == []

            # PixmapItemがクリアされる
            assert widget.pixmap_item is None
            assert widget._current_image_path is None
            assert widget._current_pixmap is None

            # ログ確認
            mock_logger.debug.assert_called_with("Preview cleared and memory optimized")

    def test_clear_preview_exception(self, widget):
        """プレビュークリア時の例外処理テスト"""
        widget.graphics_scene.clear = Mock(side_effect=Exception("Clear error"))

        with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
            mock_logger.opt.return_value = mock_logger  # opt(exception=True).error 経路を捕捉 (#1153)
            widget._clear_preview()

            # エラーログが出力される (loguru では opt(exception=True).error、#1153)
            mock_logger.error.assert_called_with("Error clearing preview: Clear error")

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
            mock_logger.opt.return_value = mock_logger
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
        mock_pixmap.isNull.return_value = False
        mock_pixmap.rect.return_value = QRectF(0, 0, 100, 100)

        with patch("lorairo.gui.widgets.image_preview.QPixmap", return_value=mock_pixmap):
            with patch.object(widget.graphics_scene, "addPixmap", return_value=Mock()) as mock_add:
                widget.load_image(test_path)

                # addPixmap が呼ばれる
                mock_add.assert_called_once_with(mock_pixmap)

                # pixmap_item が設定される
                assert widget.pixmap_item is not None
                assert widget._current_image_path == test_path
                assert widget._current_pixmap is mock_pixmap

    def test_load_image_clears_before_loading(self, widget):
        """新しい画像読み込み前に既存をクリアするテスト"""
        test_path = Path("/test/image.jpg")
        mock_pixmap = Mock()
        mock_pixmap.isNull.return_value = False

        with patch.object(widget, "_clear_preview") as mock_clear:
            with patch("lorairo.gui.widgets.image_preview.QPixmap", return_value=mock_pixmap):
                widget.load_image(test_path)

                # クリアが呼ばれる
                mock_clear.assert_called()

    def test_load_image_null_pixmap_keeps_copy_disabled(self, widget):
        """読み込み結果がnull pixmapならコピー可能状態にしない"""
        test_path = Path("/test/corrupt.jpg")

        mock_pixmap = Mock()
        mock_pixmap.isNull.return_value = True

        with patch("lorairo.gui.widgets.image_preview.QPixmap", return_value=mock_pixmap):
            with patch.object(widget.graphics_scene, "addPixmap") as mock_add:
                widget.load_image(test_path)

        mock_add.assert_not_called()
        assert widget.pixmap_item is None
        assert widget._current_image_path is None
        assert widget._current_pixmap is None
        assert widget._create_copy_image_action(widget).isEnabled() is False

    def test_copy_current_image_to_clipboard_no_image_noops(self, widget):
        """画像未表示時はクリップボードへコピーしない"""
        with patch("lorairo.gui.widgets.image_preview.QApplication.clipboard") as mock_clipboard:
            assert widget.copy_current_image_to_clipboard() is False

            mock_clipboard.assert_not_called()

    def test_copy_current_image_to_clipboard_prefers_loaded_original_path(self, widget):
        """表示時に保持したresolved pathから元画像をコピーする"""
        resolved_path = Mock()
        resolved_path.exists.return_value = True

        original_pixmap = Mock()
        original_pixmap.isNull.return_value = False
        displayed_pixmap = Mock()
        displayed_pixmap.isNull.return_value = False
        clipboard = Mock()

        widget._current_image_path = resolved_path
        widget._current_pixmap = displayed_pixmap

        with (
            patch(
                "lorairo.gui.widgets.image_preview.QPixmap", return_value=original_pixmap
            ) as mock_qpixmap,
            patch("lorairo.gui.widgets.image_preview.QApplication.clipboard", return_value=clipboard),
        ):
            assert widget.copy_current_image_to_clipboard() is True

        mock_qpixmap.assert_called_once_with(str(resolved_path))
        clipboard.setPixmap.assert_called_once_with(original_pixmap)

    def test_copy_current_image_to_clipboard_falls_back_to_displayed_pixmap(self, widget):
        """元画像が使えない場合は表示中のpixmapをコピーする"""
        resolved_path = Mock()
        resolved_path.exists.return_value = False

        displayed_pixmap = Mock()
        displayed_pixmap.isNull.return_value = False
        clipboard = Mock()

        widget._current_image_path = resolved_path
        widget._current_pixmap = displayed_pixmap

        with (
            patch("lorairo.gui.widgets.image_preview.QPixmap") as mock_qpixmap,
            patch("lorairo.gui.widgets.image_preview.QApplication.clipboard", return_value=clipboard),
        ):
            assert widget.copy_current_image_to_clipboard() is True

        mock_qpixmap.assert_not_called()
        clipboard.setPixmap.assert_called_once_with(displayed_pixmap)

    def test_copy_image_action_disabled_without_image(self, widget):
        """画像未表示時のコンテキストメニュー用コピー操作を無効化する"""
        action = widget._create_copy_image_action(widget)

        assert action.text() == "画像をコピー"
        assert action.isEnabled() is False

    def test_load_image_exception(self, widget):
        """画像読み込み例外処理テスト"""
        test_path = Path("/test/error.jpg")

        with patch("lorairo.gui.widgets.image_preview.QPixmap", side_effect=Exception("Load error")):
            with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
                mock_logger.opt.return_value = mock_logger
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


@pytest.mark.unit
class TestImagePreviewWidgetPilImage:
    """PIL画像読み込みのテスト（line 73-115）"""

    @pytest.fixture
    def widget(self, qtbot) -> ImagePreviewWidget:
        w = ImagePreviewWidget()
        qtbot.addWidget(w)
        return w

    def test_load_image_from_pil_success(self, widget: ImagePreviewWidget) -> None:
        """PILイメージから正常に読み込めることを確認（line 73-97）"""
        from PIL import Image as PilImage
        from PySide6.QtCore import QRectF

        pil_img = PilImage.new("RGB", (100, 100), color=(255, 0, 0))

        mock_pixmap = Mock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap.rect.return_value = QRectF(0, 0, 100, 100)

        with patch.object(widget, "_pil_to_qpixmap", return_value=mock_pixmap):
            with patch.object(widget.graphics_scene, "addPixmap", return_value=Mock()):
                widget.load_image_from_pil(pil_img, "test_image.png")

        assert widget._current_pixmap is mock_pixmap
        assert widget._current_image_path is None  # PILから読んだ場合はパス無し

    def test_load_image_from_pil_null_pixmap(self, widget: ImagePreviewWidget) -> None:
        """PIL変換失敗時（null pixmap）は pixmap_item が設定されない（line 80-82）"""
        from PIL import Image as PilImage

        pil_img = PilImage.new("RGB", (10, 10))

        mock_pixmap = Mock()
        mock_pixmap.isNull.return_value = True

        with patch.object(widget, "_pil_to_qpixmap", return_value=mock_pixmap):
            widget.load_image_from_pil(pil_img, "bad.png")

        assert widget.pixmap_item is None
        assert widget._current_pixmap is None

    def test_load_image_from_pil_exception(self, widget: ImagePreviewWidget) -> None:
        """_pil_to_qpixmap が例外を投げた場合にプレビューがクリアされる（line 95-97）"""
        from PIL import Image as PilImage

        pil_img = PilImage.new("RGB", (10, 10))

        with patch.object(widget, "_pil_to_qpixmap", side_effect=RuntimeError("conv error")):
            with patch.object(widget, "_clear_preview") as mock_clear:
                widget.load_image_from_pil(pil_img, "bad.png")

        mock_clear.assert_called()

    def test_pil_to_qpixmap_rgb_image(self, widget: ImagePreviewWidget) -> None:
        """RGB PILイメージをQPixmapに変換できる（line 99-115）"""
        from PIL import Image as PilImage

        pil_img = PilImage.new("RGB", (50, 50), color=(128, 64, 32))
        pixmap = widget._pil_to_qpixmap(pil_img)

        # 変換後は null でないこと
        assert not pixmap.isNull()

    def test_pil_to_qpixmap_rgba_image(self, widget: ImagePreviewWidget) -> None:
        """RGBA PILイメージをQPixmapに変換できる（line 102-103 スキップ）"""
        from PIL import Image as PilImage

        pil_img = PilImage.new("RGBA", (50, 50), color=(128, 64, 32, 200))
        pixmap = widget._pil_to_qpixmap(pil_img)

        assert not pixmap.isNull()

    def test_pil_to_qpixmap_converts_palette_image(self, widget: ImagePreviewWidget) -> None:
        """パレット画像 (P モード) は RGB に変換される（line 102-103）"""
        from PIL import Image as PilImage

        pil_img = PilImage.new("P", (50, 50))
        # P モードは RGB/RGBA でないので変換が走る
        pixmap = widget._pil_to_qpixmap(pil_img)

        assert not pixmap.isNull()


@pytest.mark.unit
class TestImagePreviewWidgetShowEvent:
    """showEvent とコンテキストメニューのテスト"""

    @pytest.fixture
    def widget(self, qtbot) -> ImagePreviewWidget:
        w = ImagePreviewWidget()
        qtbot.addWidget(w)
        return w

    def test_show_event_calls_adjust_view_size(self, widget: ImagePreviewWidget) -> None:
        """showEvent で _adjust_view_size が呼ばれる（line 175-176）"""
        from PySide6.QtGui import QShowEvent

        with patch.object(widget, "_adjust_view_size") as mock_adjust:
            event = QShowEvent()
            widget.showEvent(event)

        mock_adjust.assert_called_once()

    def test_show_preview_context_menu(self, widget: ImagePreviewWidget, qtbot) -> None:
        """コンテキストメニューが表示される（line 126-128）"""
        from PySide6.QtCore import QPoint

        # メニュー exec をモックして実際にウィンドウを開かない
        with patch("lorairo.gui.widgets.image_preview.QMenu") as mock_menu_cls:
            mock_menu = Mock()
            mock_menu_cls.return_value = mock_menu
            mock_action = Mock()
            mock_action.isEnabled.return_value = False

            with patch.object(widget, "_create_copy_image_action", return_value=mock_action):
                widget._show_preview_context_menu(QPoint(10, 10))

        mock_menu.addAction.assert_called_once_with(mock_action)
        mock_menu.exec.assert_called_once()

    def test_load_current_original_pixmap_null_result(self, widget: ImagePreviewWidget) -> None:
        """元画像の読み直しで null pixmap が返る場合 None を返す（line 165-166）"""
        mock_path = Mock()
        mock_path.exists.return_value = True

        widget._current_image_path = mock_path

        mock_null_pixmap = Mock()
        mock_null_pixmap.isNull.return_value = True

        with patch("lorairo.gui.widgets.image_preview.QPixmap", return_value=mock_null_pixmap):
            result = widget._load_current_original_pixmap()

        assert result is None

    def test_copy_current_image_no_valid_pixmap(self, widget: ImagePreviewWidget) -> None:
        """_load_current_original_pixmap も _current_pixmap もない場合は False（line 151-153）"""
        # _has_current_image() が True になるよう _current_pixmap を設定するが isNull=False にする
        mock_displayed_pixmap = Mock()
        mock_displayed_pixmap.isNull.return_value = False
        widget._current_pixmap = mock_displayed_pixmap

        # _load_current_original_pixmap が None を返し
        # _current_pixmap の isNull が True になるケースを作る
        mock_null_display = Mock()
        mock_null_display.isNull.return_value = True
        widget._current_pixmap = mock_null_display

        # _has_current_image は False になるので False が返る
        result = widget.copy_current_image_to_clipboard()
        assert result is False

    def test_on_image_data_received_exception(self, widget: ImagePreviewWidget) -> None:
        """_on_image_data_received で予期しない例外が発生してもクリアされる（line 257-262）"""
        image_data = {"id": 99, "stored_image_path": "/some/path.jpg"}

        with patch("lorairo.database.db_core.resolve_stored_path", side_effect=RuntimeError("oops")):
            with patch.object(widget, "_clear_preview") as mock_clear:
                widget._on_image_data_received(image_data)

        mock_clear.assert_called()

    def test_connect_to_data_signals_invalid_connection(self, widget: ImagePreviewWidget) -> None:
        """connect() が falsy を返す場合にエラーログが出る（line 204-206）"""
        mock_state_manager = Mock()
        mock_state_manager.current_image_data_changed = Mock()
        mock_state_manager.current_image_data_changed.connect = Mock(return_value=False)

        with patch("lorairo.gui.widgets.image_preview.logger") as mock_logger:
            mock_logger.opt.return_value = mock_logger
            widget.connect_to_data_signals(mock_state_manager)

        mock_logger.error.assert_called()
