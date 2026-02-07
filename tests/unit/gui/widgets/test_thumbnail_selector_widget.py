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
from PySide6.QtGui import QImage

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.thumbnail import ThumbnailSelectorWidget
from lorairo.gui.workers.search_worker import SearchResult
from lorairo.gui.workers.thumbnail_worker import ThumbnailLoadResult
from lorairo.services.search_models import SearchConditions


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

    def test_direct_image_data_setting(self, widget):
        """画像データの直接設定"""
        test_image_data = [
            (Path("test1.jpg"), 1),
            (Path("test2.jpg"), 2),
            (Path("test3.jpg"), 3),
        ]

        widget.image_data = test_image_data

        # 画像データが正しく設定されているか
        assert len(widget.image_data) == 3
        assert widget.image_data[0] == (Path("test1.jpg"), 1)
        assert widget.image_data[1] == (Path("test2.jpg"), 2)
        assert widget.image_data[2] == (Path("test3.jpg"), 3)

    def test_direct_metadata_setting_with_custom_ids(self, widget):
        """カスタムIDつきメタデータの直接設定"""
        test_image_data = [
            (Path("image1.jpg"), 101),
            (Path("image2.jpg"), 102),
            (Path("image3.jpg"), 103),
        ]

        widget.image_data = test_image_data

        # 画像データが正しく設定されているか
        assert len(widget.image_data) == 3
        assert widget.image_data[0] == (Path("image1.jpg"), 101)
        assert widget.image_data[1] == (Path("image2.jpg"), 102)
        assert widget.image_data[2] == (Path("image3.jpg"), 103)

    def test_empty_image_data(self, widget):
        """空の画像データ設定"""
        widget.image_data = []
        assert len(widget.image_data) == 0

    @patch("lorairo.gui.widgets.thumbnail.QPixmap")
    def test_add_thumbnail_item_uses_direct_path(self, mock_pixmap_class, widget):
        """add_thumbnail_itemが渡されたパスを直接使用することをテスト"""
        # モックPixmapの設定
        mock_pixmap = Mock()
        mock_pixmap.scaled.return_value = mock_pixmap
        mock_pixmap.rect.return_value = Mock(width=lambda: 128, height=lambda: 128)
        mock_pixmap.isNull.return_value = False  # 正常なPixmapをシミュレート
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
            mock_pixmap_class.assert_called_with("test_image.jpg")
            mock_pixmap.scaled.assert_called_once_with(
                widget.thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # ThumbnailItemが作成されsceneに追加されることを確認
            mock_item_class.assert_called_once()
            mock_add_item.assert_called_once_with(mock_item)


class TestThumbnailSelectorWidgetQPixmapConversion:
    """ThumbnailSelectorWidget QImage → QPixmap変換テスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def mock_thumbnail_result(self):
        """テスト用のThumbnailLoadResult"""
        from PySide6.QtGui import QImage

        from lorairo.gui.workers.database_worker import ThumbnailLoadResult

        # テスト用のQImageを作成
        test_qimage = QImage(100, 100, QImage.Format.Format_RGB32)
        test_qimage.fill(0xFF0000)  # 赤で塗りつぶし

        loaded_thumbnails = [(1, test_qimage), (2, test_qimage), (3, test_qimage)]

        image_metadata = [
            {"id": 1, "stored_image_path": "image1.jpg"},
            {"id": 2, "stored_image_path": "image2.jpg"},
            {"id": 3, "stored_image_path": "image3.jpg"},
        ]

        return ThumbnailLoadResult(
            loaded_thumbnails=loaded_thumbnails,
            failed_count=0,
            total_count=3,
            processing_time=1.0,
            image_metadata=image_metadata,
        )

    @patch("lorairo.gui.widgets.thumbnail.QPixmap")
    def test_load_thumbnails_from_result_qimage_to_qpixmap_conversion(
        self, mock_pixmap_class, widget, mock_thumbnail_result
    ):
        """load_thumbnails_from_result でのQImage → QPixmap変換テスト"""
        # モックPixmapの設定
        mock_pixmap = Mock()
        mock_pixmap.isNull.return_value = False
        mock_pixmap_class.fromImage.return_value = mock_pixmap

        # GUI処理をモック化してテストを高速化
        with (
            patch("lorairo.gui.widgets.thumbnail.ThumbnailItem") as mock_item_class,
            patch.object(widget.scene, "addItem") as mock_add_item,
            patch.object(widget.scene, "clear") as mock_clear,
            patch.object(widget.scene, "setSceneRect") as mock_set_rect,
        ):
            mock_item = Mock()
            mock_item_class.return_value = mock_item

            # load_thumbnails_from_result実行
            widget.load_thumbnails_from_result(mock_thumbnail_result)

            # シーンがクリアされることを確認
            mock_clear.assert_called_once()

            # QPixmap.fromImage が各QImageに対して呼び出されることを確認
            assert mock_pixmap_class.fromImage.call_count == 3
            for call in mock_pixmap_class.fromImage.call_args_list:
                args, _ = call
                assert len(args) == 1
                # QImageが渡されていることを確認（モックなので型チェックのみ）
                assert hasattr(args[0], "format")  # QImageの特徴的メソッド

            # 3つのアイテムがsceneに追加されることを確認
            assert mock_add_item.call_count == 3

            # シーンレクトが設定されることを確認
            mock_set_rect.assert_called_once()

    def test_load_thumbnails_from_result_empty_result(self, widget):
        """空のThumbnailLoadResultでのテスト"""
        from lorairo.gui.workers.database_worker import ThumbnailLoadResult

        empty_result = ThumbnailLoadResult(
            loaded_thumbnails=[], failed_count=0, total_count=0, processing_time=0.0
        )

        # エラーなく処理されることを確認
        widget.load_thumbnails_from_result(empty_result)

        # アイテムが追加されていないことを確認
        assert len(widget.thumbnail_items) == 0

    @patch("lorairo.gui.widgets.thumbnail.QPixmap")
    def test_load_thumbnails_from_result_failed_qimage_conversion(
        self, mock_pixmap_class, widget, mock_thumbnail_result
    ):
        """QImage変換に失敗した場合、キャッシュには保存されずプレースホルダーで表示される"""
        # fromImageが失敗する場合をシミュレート（null pixmapを返す）
        null_pixmap = Mock()
        null_pixmap.isNull.return_value = True
        mock_pixmap_class.fromImage.return_value = null_pixmap

        # プレースホルダー用のモックPixmap
        placeholder_pixmap = Mock()
        placeholder_pixmap.fill = Mock()
        mock_pixmap_class.return_value = placeholder_pixmap

        with (
            patch("lorairo.gui.widgets.thumbnail.ThumbnailItem"),
            patch.object(widget.scene, "addItem"),
            patch.object(widget.scene, "clear"),
            patch.object(widget.scene, "setSceneRect"),
        ):
            # エラーがあっても処理が完了することを確認
            widget.load_thumbnails_from_result(mock_thumbnail_result)

            # fromImageが3回呼び出されることを確認
            assert mock_pixmap_class.fromImage.call_count == 3

            # null pixmapはキャッシュに保存されない
            cache_info = widget.cache_usage_info()
            assert cache_info["original_cache_count"] == 0


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
            test_image_data = [(Path("test.jpg"), 1)]
            widget.image_data = test_image_data
            widget.clear_thumbnails()
        except Exception as e:
            pytest.fail(f"データベース依存のないシンプルな操作でエラーが発生: {e}")

    def test_pure_display_component(self, widget):
        """純粋な表示専用コンポーネントであることを確認"""
        # 表示関連のメソッドのみ持つことを確認
        display_methods = [
            "load_thumbnails_from_result",
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
        """get_current_image_data は deprecated で空リストを返す"""
        current_data = widget.get_current_image_data()
        assert current_data == []


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
        # 1. 画像データを設定
        test_image_data = [
            (Path("test1.jpg"), 1),
            (Path("test2.jpg"), 2),
        ]
        widget.image_data = test_image_data

        # 2. サムネイルサイズ変更（直接設定 - 責任分離後）
        widget.thumbnail_size = QSize(100, 100)

        # 3. クリア
        widget.clear_thumbnails()

        # データベースアクセスなしで正常に動作することを確認
        assert len(widget.image_data) == 0
        # pytest-qtがqtbot.addWidget()を使用している場合、自動クリーンアップされる


class TestThumbnailSelectorWidgetSelectionSync:
    """ThumbnailSelectorWidget 選択状態同期テスト"""

    @pytest.fixture
    def widget_with_state(self, qtbot):
        """DatasetStateManager付きウィジェット"""
        from lorairo.gui.state.dataset_state import DatasetStateManager

        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)

        state_manager = DatasetStateManager()
        widget.dataset_state = state_manager

        return widget, state_manager

    def test_sync_selection_to_state_basic(self, widget_with_state, qtbot):
        """基本的な選択同期テスト"""
        widget, state_manager = widget_with_state

        # ThumbnailItemをモック
        from lorairo.gui.widgets.thumbnail import ThumbnailItem

        mock_item1 = Mock(spec=ThumbnailItem)
        mock_item1.image_id = 1
        mock_item2 = Mock(spec=ThumbnailItem)
        mock_item2.image_id = 2

        # scene.selectedItems() をモック
        widget.scene.selectedItems = Mock(return_value=[mock_item1, mock_item2])

        # 実行
        widget._sync_selection_to_state()

        # 検証
        assert state_manager.selected_image_ids == [1, 2]

    def test_sync_selection_to_state_empty(self, widget_with_state, qtbot):
        """空の選択状態の同期テスト"""
        widget, state_manager = widget_with_state

        # scene.selectedItems() が空リストを返す
        widget.scene.selectedItems = Mock(return_value=[])

        # 実行
        widget._sync_selection_to_state()

        # 検証
        assert state_manager.selected_image_ids == []

    def test_sync_selection_to_state_without_dataset_state(self, qtbot):
        """DatasetStateManager未設定時のテスト"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)

        # dataset_state が None の場合
        widget.dataset_state = None

        # 実行（例外が発生しないことを確認）
        widget._sync_selection_to_state()

        # 検証: 何も起こらない
        assert widget.dataset_state is None

    def test_sync_selection_to_state_signal_blocking(self, widget_with_state, qtbot):
        """シグナルブロッキング動作の確認"""
        widget, state_manager = widget_with_state

        from lorairo.gui.widgets.thumbnail import ThumbnailItem

        mock_item = Mock(spec=ThumbnailItem)
        mock_item.image_id = 5
        widget.scene.selectedItems = Mock(return_value=[mock_item])

        # blockSignals が呼ばれることを確認するためのスパイ
        with patch.object(state_manager, "blockSignals", wraps=state_manager.blockSignals) as mock_block:
            widget._sync_selection_to_state()

            # blockSignals(True) と blockSignals(False) が呼ばれたことを確認
            assert mock_block.call_count == 2
            assert mock_block.call_args_list[0][0][0] is True  # blockSignals(True)
            assert mock_block.call_args_list[1][0][0] is False  # blockSignals(False)

        # 最終的に選択状態が正しく反映されている
        assert state_manager.selected_image_ids == [5]


class TestThumbnailSelectorWidgetClickSelection:
    """クリック選択動作テスト（標準OS準拠の選択動作）"""

    @pytest.fixture
    def widget_with_items(self, qtbot):
        """DatasetStateManager + ThumbnailItemsを持つウィジェット"""
        from lorairo.gui.state.dataset_state import DatasetStateManager
        from lorairo.gui.widgets.thumbnail import ThumbnailItem

        state = DatasetStateManager()
        widget = ThumbnailSelectorWidget(dataset_state=state)
        qtbot.addWidget(widget)

        # モックThumbnailItemを5つ作成
        items = []
        for i in range(1, 6):
            mock_item = Mock(spec=ThumbnailItem)
            mock_item.image_id = i
            items.append(mock_item)
        widget.thumbnail_items = items
        return widget, state, items

    def test_normal_click_single_selection(self, widget_with_items):
        """通常クリック: 単一選択（他を解除）"""
        widget, state, items = widget_with_items

        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [1]

        # 別アイテムをクリック → 前の選択が解除される
        widget.handle_item_selection(items[2], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [3]

    def test_ctrl_click_toggle_selection(self, widget_with_items):
        """Ctrl+Click: 個別トグル選択"""
        widget, state, items = widget_with_items

        # 1つ目を通常選択
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [1]

        # Ctrlクリックで追加
        widget.handle_item_selection(items[2], Qt.KeyboardModifier.ControlModifier)
        assert sorted(state.selected_image_ids) == [1, 3]

        # 同じアイテムをCtrlクリックで解除
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.ControlModifier)
        assert state.selected_image_ids == [3]

    def test_shift_click_range_selection(self, widget_with_items):
        """Shift+Click: 範囲選択（既存選択を置換）"""
        widget, state, items = widget_with_items

        # まず1つ目を選択（last_selected_itemを設定）
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [1]

        # Shiftクリックで範囲選択（1〜4）
        widget.handle_item_selection(items[3], Qt.KeyboardModifier.ShiftModifier)
        assert state.selected_image_ids == [1, 2, 3, 4]

    def test_ctrl_shift_click_range_add_selection(self, widget_with_items):
        """Ctrl+Shift+Click: 範囲追加選択（既存選択を維持）"""
        widget, state, items = widget_with_items

        # まず1つ目を選択
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [1]

        # Ctrlクリックで3つ目を追加
        widget.handle_item_selection(items[2], Qt.KeyboardModifier.ControlModifier)
        assert sorted(state.selected_image_ids) == [1, 3]

        # Ctrl+Shiftクリックで4〜5を追加（last_selected_itemは3つ目）
        ctrl_shift = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        widget.handle_item_selection(items[4], ctrl_shift)
        assert sorted(state.selected_image_ids) == [1, 3, 4, 5]

    def test_shift_click_without_previous_selection_does_single_select(self, widget_with_items):
        """Shift+Click（前回選択なし）: 単一選択になる"""
        widget, state, items = widget_with_items

        # last_selected_item が None の状態でShiftクリック
        widget.handle_item_selection(items[2], Qt.KeyboardModifier.ShiftModifier)
        assert state.selected_image_ids == [3]

    def test_empty_space_click_clears_selection(self, widget_with_items):
        """空スペースクリック: 選択解除"""
        widget, state, items = widget_with_items

        # まず複数選択
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        widget.handle_item_selection(items[1], Qt.KeyboardModifier.ControlModifier)
        assert len(state.selected_image_ids) == 2

        # 空スペースクリック
        widget._on_empty_space_clicked()
        assert state.selected_image_ids == []

    def test_last_selected_item_tracked(self, widget_with_items):
        """last_selected_item が毎クリック後に更新される"""
        widget, _state, items = widget_with_items

        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert widget.last_selected_item is items[0]

        widget.handle_item_selection(items[3], Qt.KeyboardModifier.ControlModifier)
        assert widget.last_selected_item is items[3]

    def test_handle_item_selection_without_dataset_state(self, qtbot):
        """DatasetState未設定時はスキップされる"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        widget.dataset_state = None

        mock_item = Mock()
        mock_item.image_id = 1
        # 例外が発生しないことを確認
        widget.handle_item_selection(mock_item, Qt.KeyboardModifier.NoModifier)

    def test_sync_selection_with_ctrl_drag(self, widget_with_items):
        """Ctrl+ドラッグ: 既存選択に追加"""
        widget, state, _items = widget_with_items
        from lorairo.gui.widgets.thumbnail import ThumbnailItem

        # まず通常選択
        state.set_selected_images([1, 2])

        # ドラッグ修飾子をCtrlに設定
        widget.graphics_view._drag_modifiers = Qt.KeyboardModifier.ControlModifier

        # scene.selectedItems() をモック（ドラッグで4,5を選択）
        mock_item4 = Mock(spec=ThumbnailItem)
        mock_item4.image_id = 4
        mock_item5 = Mock(spec=ThumbnailItem)
        mock_item5.image_id = 5
        widget.scene.selectedItems = Mock(return_value=[mock_item4, mock_item5])

        widget._sync_selection_to_state()
        assert sorted(state.selected_image_ids) == [1, 2, 4, 5]

    def test_sync_selection_with_shift_drag(self, widget_with_items):
        """Shift+ドラッグ: 既存選択に追加"""
        widget, state, _items = widget_with_items
        from lorairo.gui.widgets.thumbnail import ThumbnailItem

        state.set_selected_images([1])

        widget.graphics_view._drag_modifiers = Qt.KeyboardModifier.ShiftModifier

        mock_item3 = Mock(spec=ThumbnailItem)
        mock_item3.image_id = 3
        widget.scene.selectedItems = Mock(return_value=[mock_item3])

        widget._sync_selection_to_state()
        assert sorted(state.selected_image_ids) == [1, 3]


class TestThumbnailSelectorWidgetPagination:
    """ページネーション統合テスト"""

    @pytest.fixture
    def widget_with_state(self, qtbot):
        state = DatasetStateManager()
        widget = ThumbnailSelectorWidget(dataset_state=state)
        qtbot.addWidget(widget)
        return widget, state

    @staticmethod
    def _build_search_result(image_count: int) -> SearchResult:
        metadata = [
            {"id": i, "stored_image_path": f"/tmp/image_{i}.png"} for i in range(1, image_count + 1)
        ]
        return SearchResult(
            image_metadata=metadata,
            total_count=image_count,
            search_time=0.1,
            filter_conditions=SearchConditions(search_type="tags", keywords=[], tag_logic="and"),
        )

    def test_initialize_pagination_search_requests_first_page(self, widget_with_state):
        widget, _ = widget_with_state
        worker_service = Mock()
        worker_service.start_thumbnail_page_load.return_value = "thumbnail_page_1"

        search_result = self._build_search_result(120)
        widget.initialize_pagination_search(search_result=search_result, worker_service=worker_service)

        assert widget.pagination_state is not None
        assert widget.pagination_state.total_pages == 2
        assert widget.pagination_nav is not None
        assert widget.pagination_nav.isHidden() is False
        worker_service.start_thumbnail_page_load.assert_called_once()

    def test_handle_thumbnail_page_result_displays_page(self, widget_with_state):
        widget, _ = widget_with_state
        worker_service = Mock()
        worker_service.start_thumbnail_page_load.return_value = "thumbnail_page_1"
        search_result = self._build_search_result(1)
        widget.initialize_pagination_search(search_result=search_result, worker_service=worker_service)

        request_id = widget._display_request_id
        assert request_id is not None

        qimage = QImage(64, 64, QImage.Format.Format_RGB32)
        qimage.fill(0x00FF00)
        result = ThumbnailLoadResult(
            loaded_thumbnails=[(1, qimage)],
            failed_count=0,
            total_count=1,
            processing_time=0.01,
            image_metadata=[{"id": 1, "stored_image_path": "/tmp/image_1.png"}],
            request_id=request_id,
            page_num=1,
            image_ids=[1],
        )

        widget.handle_thumbnail_page_result(result)

        assert widget.page_cache.has_page(1)
        assert len(widget.thumbnail_items) == 1
        assert widget.image_data[0][1] == 1

    def test_set_dataset_state_rebinds_pagination_state(self, widget_with_state):
        widget, _ = widget_with_state
        old_pagination_state = widget.pagination_state

        new_state = DatasetStateManager()
        widget.set_dataset_state(new_state)

        assert widget.pagination_state is not None
        assert widget.pagination_state is not old_pagination_state
        assert getattr(widget.pagination_state, "_dataset_state", None) is new_state

    def test_display_or_request_page_cancels_pending_request(self, widget_with_state):
        widget, _ = widget_with_state
        worker_service = Mock()
        worker_service.start_thumbnail_page_load.return_value = "thumbnail_req_1"

        search_result = self._build_search_result(1)
        widget.initialize_pagination_search(search_result=search_result, worker_service=worker_service)

        assert widget._display_request_id is not None
        widget.page_cache.set_page(1, [])
        widget._display_or_request_page(1, cancel_previous=True)

        worker_service.cancel_thumbnail_load.assert_called_with("thumbnail_req_1")
        assert widget._display_request_id is None
        assert widget._request_id_to_page == {}
        assert widget._request_id_to_worker_id == {}


if __name__ == "__main__":
    pytest.main([__file__])
