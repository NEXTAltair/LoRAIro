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
from lorairo.gui.widgets.thumbnail_item import ThumbnailItem
from lorairo.gui.widgets.thumbnail_selector_widget import ThumbnailSelectorWidget
from lorairo.gui.workers.search_worker import SearchResult
from lorairo.gui.workers.terminal import CancelReason
from lorairo.gui.workers.thumbnail_worker import ThumbnailLoadResult
from lorairo.services.search_models import SearchConditions


class TestThumbnailItemOverlayTexts:
    """ThumbnailItem._overlay_texts のバッジ文字列組み立て (DS Thumbnail · #786)。"""

    def test_full_metadata(self):
        """score / rating / 解像度 すべて揃うケース。"""
        meta = {"score_value": 6.5, "rating_value": "PG-13", "width": 1024, "height": 1536}
        assert ThumbnailItem._overlay_texts(meta) == ("6.5", "PG-13", "1024×1536")

    def test_missing_values_yield_none(self):
        """欠損・ゼロ・空文字の項目は None になる。"""
        meta = {"score_value": 0, "rating_value": "", "width": 0, "height": 0}
        assert ThumbnailItem._overlay_texts(meta) == (None, None, None)

    def test_partial_metadata(self):
        """一部の項目だけ揃うケース (rating のみ)。"""
        meta = {"rating_value": "R"}
        assert ThumbnailItem._overlay_texts(meta) == (None, "R", None)


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
        assert len(widget.thumbnail_items) == 0

    def test_set_thumbnail_size(self, widget):
        """サムネイルサイズ設定テスト（責任分離後は直接設定）"""
        new_size = QSize(200, 200)
        widget.thumbnail_size = new_size  # 直接設定方式
        assert widget.thumbnail_size == new_size

    def test_clear_thumbnails(self, widget):
        """サムネイルクリアテスト"""
        # テストデータを設定
        widget._explicit_path_items = [(Path("test.jpg"), 1)]
        widget.thumbnail_items = [Mock()]

        widget.clear_thumbnails()

        assert len(widget._explicit_path_items) == 0
        assert len(widget.thumbnail_items) == 0


class TestThumbnailSelectorWidgetLoadImages:
    """ThumbnailSelectorWidget 明示パス表示テスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    def test_load_thumbnails_from_paths_tracks_explicit_paths(self, widget):
        """staging用の明示パス表示は private な明示パスリストで管理される"""
        widget.load_thumbnails_from_paths([("test1.jpg", 1), ("test2.jpg", 2), ("test3.jpg", 3)])

        assert widget._explicit_path_items == [
            (Path("test1.jpg"), 1),
            (Path("test2.jpg"), 2),
            (Path("test3.jpg"), 3),
        ]
        assert [item.image_id for item in widget.thumbnail_items] == [1, 2, 3]

    def test_empty_explicit_path_items(self, widget):
        """空の明示パス表示"""
        widget.load_thumbnails_from_paths([])
        assert widget._explicit_path_items == []
        assert widget.thumbnail_items == []

    @patch("lorairo.gui.widgets.thumbnail_selector_widget.QPixmap")
    def test_load_thumbnails_from_paths_uses_direct_path(self, mock_pixmap_class, widget):
        """staging用の明示パス表示は渡されたパスを直接使用する"""
        # モックPixmapの設定
        mock_pixmap = Mock()
        mock_pixmap.scaled.return_value = mock_pixmap
        mock_pixmap.rect.return_value = Mock(width=lambda: 128, height=lambda: 128)
        mock_pixmap.isNull.return_value = False  # 正常なPixmapをシミュレート
        mock_pixmap_class.return_value = mock_pixmap

        # GUI処理をモック化してテストを高速化
        with (
            patch("lorairo.gui.widgets.thumbnail_selector_widget.ThumbnailItem") as mock_item_class,
            patch.object(widget.scene, "addItem") as mock_add_item,
        ):
            mock_item = Mock()
            mock_item_class.return_value = mock_item

            widget.load_thumbnails_from_paths([("test_image.jpg", 123)])

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
            widget.load_thumbnails_from_paths([("test.jpg", 1)])
            widget.clear_thumbnails()
        except Exception as e:
            pytest.fail(f"データベース依存のないシンプルな操作でエラーが発生: {e}")

    def test_pure_display_component(self, widget):
        """純粋な表示専用コンポーネントであることを確認"""
        # 表示関連のメソッドのみ持つことを確認
        display_methods = [
            "load_thumbnails_from_paths",
            "clear_thumbnails",
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

    def test_deprecated_current_image_data_api_removed(self, widget):
        """ThumbnailSelectorWidget の deprecated な get_current_image_data は削除済み"""
        assert not hasattr(widget, "get_current_image_data")


class TestThumbnailSelectorWidgetLayout:
    """ThumbnailSelectorWidget レイアウトテスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用ウィジェット"""
        widget = ThumbnailSelectorWidget()
        qtbot.addWidget(widget)
        return widget

    @patch("lorairo.gui.widgets.thumbnail_selector_widget.ThumbnailItem")
    def test_update_thumbnail_layout_uses_page_cache(self, mock_item_class, qtbot):
        """検索結果のレイアウト更新はページキャッシュから再表示する"""
        state = DatasetStateManager()
        state.update_from_search_results(
            [
                {"id": 1, "stored_image_path": "image1.jpg"},
                {"id": 2, "stored_image_path": "image2.jpg"},
                {"id": 3, "stored_image_path": "image3.jpg"},
            ]
        )
        widget = ThumbnailSelectorWidget(dataset_state=state)
        qtbot.addWidget(widget)

        pixmap = Mock()
        pixmap.scaled.return_value = pixmap
        pixmap.rect.return_value = Mock(width=lambda: 128, height=lambda: 128)
        widget.page_cache.set_page(1, [(1, pixmap), (2, pixmap), (3, pixmap)])

        created_items = []

        def make_item(*_args):
            item = Mock()
            item.image_id = _args[2]
            created_items.append(item)
            return item

        mock_item_class.side_effect = make_item
        widget.scrollAreaThumbnails.resize(200, 300)
        with patch.object(widget.scene, "addItem"):
            widget.update_thumbnail_layout()

        assert mock_item_class.call_count == 3
        assert [item.image_id for item in created_items] == [1, 2, 3]


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
        widget.load_thumbnails_from_paths([("test1.jpg", 1), ("test2.jpg", 2)])

        # 2. サムネイルサイズ変更（直接設定 - 責任分離後）
        widget.thumbnail_size = QSize(100, 100)

        # 3. クリア
        widget.clear_thumbnails()

        # データベースアクセスなしで正常に動作することを確認
        assert len(widget._explicit_path_items) == 0
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
        from lorairo.gui.widgets.thumbnail_item import ThumbnailItem

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

        from lorairo.gui.widgets.thumbnail_item import ThumbnailItem

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
        from lorairo.gui.widgets.thumbnail_item import ThumbnailItem

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
        from lorairo.gui.widgets.thumbnail_item import ThumbnailItem

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
        from lorairo.gui.widgets.thumbnail_item import ThumbnailItem

        state.set_selected_images([1])

        widget.graphics_view._drag_modifiers = Qt.KeyboardModifier.ShiftModifier

        mock_item3 = Mock(spec=ThumbnailItem)
        mock_item3.image_id = 3
        widget.scene.selectedItems = Mock(return_value=[mock_item3])

        widget._sync_selection_to_state()
        assert sorted(state.selected_image_ids) == [1, 3]

    def test_right_click_preserves_selection(self, widget_with_items):
        """右クリック: 選択状態を維持（コンテキストメニュー用）"""
        widget, state, items = widget_with_items
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        # まず通常選択（ID: 1, 3を選択）
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        widget.handle_item_selection(items[2], Qt.KeyboardModifier.ControlModifier)
        assert sorted(state.selected_image_ids) == [1, 3]

        # 選択済みアイテムを右クリック（itemClickedシグナルが発火しないことを確認）
        signal_emitted = False

        def on_item_clicked(_item, _modifiers):
            nonlocal signal_emitted
            signal_emitted = True

        widget.graphics_view.itemClicked.connect(on_item_clicked)

        # 右クリックイベントを作成（itemAt()がitemsを返すようモック）
        widget.graphics_view.itemAt = Mock(return_value=items[0])
        pos = QPoint(0, 0)
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            pos,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.graphics_view.mousePressEvent(event)

        # itemClickedシグナルが発火していないことを確認
        assert signal_emitted is False

        # 選択状態が変わっていないことを確認
        assert sorted(state.selected_image_ids) == [1, 3]

    def test_right_click_on_empty_space_preserves_selection(self, widget_with_items):
        """右クリック（空スペース）: 選択状態を維持"""
        widget, state, items = widget_with_items
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtGui import QMouseEvent

        # まず選択
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [1]

        # 空スペースを右クリック（emptySpaceClickedシグナルが発火しないことを確認）
        signal_emitted = False

        def on_empty_space_clicked():
            nonlocal signal_emitted
            signal_emitted = True

        widget.graphics_view.emptySpaceClicked.connect(on_empty_space_clicked)

        # 空スペースの右クリックイベントを作成
        widget.graphics_view.itemAt = Mock(return_value=None)
        pos = QPoint(0, 0)
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            pos,
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.graphics_view.mousePressEvent(event)

        # emptySpaceClickedシグナルが発火していないことを確認
        assert signal_emitted is False

        # 選択状態が変わっていないことを確認
        assert state.selected_image_ids == [1]

    def test_select_all_items(self, widget_with_items):
        """_select_all_items: すべてのサムネイルアイテムを選択"""
        widget, state, _items = widget_with_items

        # 初期状態: 何も選択されていない
        assert state.selected_image_ids == []

        # _select_all_itemsを直接呼び出し（MainWindow.actionSelectAllから呼ばれる）
        widget._select_all_items()

        # すべてのアイテム（5つ）が選択されていることを確認
        assert sorted(state.selected_image_ids) == [1, 2, 3, 4, 5]

    def test_select_all_with_existing_selection(self, widget_with_items):
        """_select_all_items: 既存の選択状態から全選択に変更"""
        widget, state, items = widget_with_items
        from PySide6.QtCore import Qt

        # 一部を選択
        widget.handle_item_selection(items[0], Qt.KeyboardModifier.NoModifier)
        assert state.selected_image_ids == [1]

        # _select_all_itemsで全選択
        widget._select_all_items()

        # すべてのアイテム（5つ）が選択されていることを確認
        assert sorted(state.selected_image_ids) == [1, 2, 3, 4, 5]


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
        assert widget.thumbnail_items[0].image_id == 1

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

        worker_service.cancel_thumbnail_load.assert_called_with(
            "thumbnail_req_1",
            reason=CancelReason.THUMBNAIL_REPLACED,
        )
        assert widget._display_request_id is None
        assert widget._request_id_to_page == {}
        assert widget._request_id_to_worker_id == {}


if __name__ == "__main__":
    pytest.main([__file__])
