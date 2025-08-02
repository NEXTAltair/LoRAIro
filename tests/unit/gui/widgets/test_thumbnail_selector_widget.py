"""ThumbnailSelectorWidget ユニットテスト

責任分離後のThumbnailSelectorWidgetをテスト
- シンプルなパス受け取り専用の表示コンポーネント
- データベースアクセスなし
- 最適化ロジックなし
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QSize, Qt

from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget


class TestThumbnailSelectorWidgetBasic:
    """ThumbnailSelectorWidget 基本機能テスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, widget):
        """初期化テスト"""
        assert widget is not None
        assert widget.thumbnail_size == QSize(128, 128)  # 実際のデフォルトサイズ
        assert len(widget.image_data) == 0
        assert len(widget.thumbnail_items) == 0

    def test_set_thumbnail_size(self, widget):
        """サムネイルサイズ設定テスト（責任分離後は直接設定）"""
        new_size = QSize(200, 200)
        widget.thumbnail_size = new_size  # 直接設定方式
        assert widget.thumbnail_size == new_size

    def test_clear_thumbnails(self, widget):
        """サムネイルクリアテスト"""
        # テストデータを設定
        widget.image_data = [(Path("test.jpg"), 1)]
        widget.thumbnail_items = [Mock()]

        widget.clear_thumbnails()

        assert len(widget.image_data) == 0
        assert len(widget.thumbnail_items) == 0


class TestThumbnailSelectorWidgetLoadImages:
    """ThumbnailSelectorWidget 画像読み込みテスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_load_images_simple_paths(self, widget):
        """シンプルなパスリストでの画像読み込み"""
        test_paths = [Path("test1.jpg"), Path("test2.jpg"), Path("test3.jpg")]

        widget.load_images(test_paths)

        # 画像データが正しく設定されているか
        assert len(widget.image_data) == 3
        assert widget.image_data[0] == (Path("test1.jpg"), 0)
        assert widget.image_data[1] == (Path("test2.jpg"), 1)
        assert widget.image_data[2] == (Path("test3.jpg"), 2)

    def test_load_images_with_ids(self, widget):
        """IDつきデータでの画像読み込み"""
        test_data = [(Path("image1.jpg"), 101), (Path("image2.jpg"), 102), (Path("image3.jpg"), 103)]

        widget.load_images_with_ids(test_data)

        # 画像データが正しく設定されているか
        assert len(widget.image_data) == 3
        assert widget.image_data[0] == (Path("image1.jpg"), 101)
        assert widget.image_data[1] == (Path("image2.jpg"), 102)
        assert widget.image_data[2] == (Path("image3.jpg"), 103)

    def test_load_empty_images(self, widget):
        """空のリストでの画像読み込み"""
        widget.load_images([])
        assert len(widget.image_data) == 0

    @patch("lorairo.gui.widgets.thumbnail.QPixmap")
    def test_add_thumbnail_item_uses_direct_path(self, mock_pixmap_class, widget):
        """add_thumbnail_itemが渡されたパスを直接使用することをテスト"""
        # モックPixmapの設定
        mock_pixmap = Mock()
        mock_pixmap.scaled.return_value = mock_pixmap
        mock_pixmap.rect.return_value = Mock(width=lambda: 128, height=lambda: 128)
        mock_pixmap_class.return_value = mock_pixmap

        # GUI処理をモック化してテストを高速化
        with (
            patch("lorairo.gui.widgets.thumbnail.ThumbnailItem") as mock_item_class,
            patch.object(widget.scene, "addItem") as mock_add_item,
        ):
            mock_item = Mock()
            mock_item_class.return_value = mock_item

            widget.add_thumbnail_item(Path("test_image.jpg"), 123, 0, 3)

            # QPixmapがパスで呼び出されることを確認
            mock_pixmap_class.assert_called_once_with("test_image.jpg")
            mock_pixmap.scaled.assert_called_once_with(
                widget.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # ThumbnailItemが作成されsceneに追加されることを確認
            mock_item_class.assert_called_once()
            mock_add_item.assert_called_once_with(mock_item)


class TestThumbnailSelectorWidgetResponsibilitySeparation:
    """責任分離の確認テスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_no_database_access_methods(self, widget):
        """データベースアクセスメソッドが存在しないことを確認"""
        # _get_thumbnail_pathメソッドが削除されていることを確認
        assert not hasattr(widget, "_get_thumbnail_path")

    def test_no_database_manager_dependency(self, widget):
        """データベースマネージャーへの依存がないことを確認（シンプル版）"""
        # 通常の操作でエラーが発生しないことを確認（データベースアクセスなし）
        try:
            widget.load_images([Path("test.jpg")])
            widget.clear_thumbnails()
        except Exception as e:
            pytest.fail(f"データベース依存のないシンプルな操作でエラーが発生: {e}")

    def test_pure_display_component(self, widget):
        """純粋な表示専用コンポーネントであることを確認"""
        # 表示関連のメソッドのみ持つことを確認
        display_methods = [
            "load_images",
            "load_images_with_ids",
            "clear_thumbnails",
            "add_thumbnail_item",
            "get_selected_images",
        ]

        for method in display_methods:
            assert hasattr(widget, method), f"表示メソッド {method} が存在しません"

        # データベース関連メソッドが存在しないことを確認
        forbidden_methods = ["_get_thumbnail_path", "check_processed_image_exists", "resolve_stored_path"]

        for method in forbidden_methods:
            assert not hasattr(widget, method), f"責任外メソッド {method} が存在します"


class TestThumbnailSelectorWidgetSelection:
    """ThumbnailSelectorWidget 選択機能テスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_get_selected_images_empty(self, widget):
        """選択なしの場合の取得テスト"""
        selected = widget.get_selected_images()
        assert selected == []

    def test_get_current_image_data(self, widget):
        """現在の画像データ取得テスト（責任分離で追加されたメソッド）"""
        # メタデータを直接設定（load_images_with_idsはメタデータを設定しない）
        test_metadata = [
            {"id": 101, "stored_image_path": "image1.jpg"},
            {"id": 102, "stored_image_path": "image2.jpg"},
        ]
        widget.current_image_metadata = test_metadata

        # メタデータ形式での取得
        current_data = widget.get_current_image_data()
        assert len(current_data) == 2
        assert current_data[0]["id"] == 101
        assert current_data[1]["id"] == 102


class TestThumbnailSelectorWidgetLayout:
    """ThumbnailSelectorWidget レイアウトテスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_update_thumbnail_layout(self, widget):
        """サムネイルレイアウト更新テスト - ウィジェットサイズ変更時のレイアウト再計算"""
        # テストデータを準備
        test_data = [(Path("image1.jpg"), 1), (Path("image2.jpg"), 2), (Path("image3.jpg"), 3)]
        widget.image_data = test_data

        # add_thumbnail_itemをモック化してGUI処理をスキップ
        with patch.object(widget, "add_thumbnail_item") as mock_add_item:
            # 初期サイズでのレイアウト更新
            widget.scrollAreaThumbnails.resize(400, 300)  # 幅400px
            widget.thumbnail_size = QSize(128, 128)  # サムネイルサイズ128px
            widget.update_thumbnail_layout()

            # 幅400px ÷ 128px = 3カラムになることを確認
            initial_calls = mock_add_item.call_count
            assert initial_calls == 3  # 3つのアイテムが配置される

            mock_add_item.reset_mock()

            # ウィジェットサイズを変更（幅を狭める）
            widget.scrollAreaThumbnails.resize(200, 300)  # 幅200px
            widget.update_thumbnail_layout()

            # 幅200px ÷ 128px = 1カラムになることを確認
            assert mock_add_item.call_count == 3  # 同じ数のアイテムが再配置される

            # カラム数が1になっていることを確認（各呼び出しの4番目の引数）
            for call in mock_add_item.call_args_list:
                column_count = call[0][3]  # add_thumbnail_item(path, id, index, column_count)
                assert column_count == 1  # 1カラムレイアウト


class TestThumbnailSelectorWidgetWorkflow:
    """ThumbnailSelectorWidget ワークフローテスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_full_workflow_without_database(self, widget):
        """データベースなしでの完全ワークフロー（ユニットテスト）"""
        # 1. 画像パスを設定
        test_paths = [Path("test1.jpg"), Path("test2.jpg")]
        widget.load_images(test_paths)

        # 2. サムネイルサイズ変更（直接設定 - 責任分離後）
        widget.thumbnail_size = QSize(100, 100)

        # 3. クリア
        widget.clear_thumbnails()

        # データベースアクセスなしで正常に動作することを確認
        assert len(widget.image_data) == 0
        # pytest-qtがqtbot.addWidget()を使用している場合、自動クリーンアップされる


if __name__ == "__main__":
    pytest.main([__file__])
