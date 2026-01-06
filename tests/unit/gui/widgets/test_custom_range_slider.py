# tests/unit/gui/widgets/test_filter_widgets.py

from unittest.mock import Mock, patch

import pytest
from PySide6.QtWidgets import QWidget

from lorairo.gui.widgets.custom_range_slider import CustomRangeSlider
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel


class TestCustomRangeSlider:
    """CustomRangeSlider のユニットテスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット (pytest-qt対応)"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    def range_slider(self, parent_widget, qtbot):
        """テスト用CustomRangeSlider"""
        slider = CustomRangeSlider(parent_widget, min_value=100, max_value=10000)
        qtbot.addWidget(slider)
        return slider

    def test_initialization_numeric_mode(self, range_slider):
        """数値モードでの初期化テスト"""
        assert range_slider.min_value == 100
        assert range_slider.max_value == 10000
        assert range_slider.is_date_mode is False
        assert hasattr(range_slider, "slider")
        assert hasattr(range_slider, "min_label")
        assert hasattr(range_slider, "max_label")

    def test_initialization_default_values(self, parent_widget, qtbot):
        """デフォルト値での初期化テスト"""
        slider = CustomRangeSlider(parent_widget)
        qtbot.addWidget(slider)

        assert slider.min_value == 0
        assert slider.max_value == 100000
        assert slider.is_date_mode is False

    def test_scale_to_value_edge_cases(self, range_slider):
        """簡素化後の直接値操作テスト（対数スケール除去）"""
        # 簡素化後は直接値を使用するため、スライダーの範囲をテスト
        assert range_slider.slider.minimum() == range_slider.min_value
        assert range_slider.slider.maximum() == range_slider.max_value

        # 初期値が正しく設定されているか確認
        min_val, max_val = range_slider.slider.value()
        assert min_val == range_slider.min_value
        assert max_val == range_slider.max_value

    def test_get_range(self, range_slider):
        """範囲取得テスト（簡素化後の直接値使用）"""
        # 範囲内の具体的な値を設定（100-10000の範囲内）
        test_min = 500
        test_max = 8000
        range_slider.slider.setValue((test_min, test_max))
        min_val, max_val = range_slider.get_range()

        assert isinstance(min_val, int)
        assert isinstance(max_val, int)
        assert min_val == test_min
        assert max_val == test_max
        assert min_val < max_val

    def test_set_range(self, range_slider):
        """範囲設定テスト"""
        new_min, new_max = 500, 50000
        range_slider.set_range(new_min, new_max)

        assert range_slider.min_value == new_min
        assert range_slider.max_value == new_max

    def test_set_date_range(self, range_slider):
        """日付範囲設定テスト"""
        range_slider.set_date_range()

        assert range_slider.is_date_mode is True
        assert range_slider.min_value > 0  # UTCタイムスタンプ
        assert range_slider.max_value > range_slider.min_value

    def test_date_mode_labels(self, range_slider):
        """日付モード時のラベル表示テスト"""
        range_slider.set_date_range()
        range_slider.slider.setValue((10, 90))
        range_slider.update_labels()

        # ラベルが日付形式 (YYYY-MM-DD) になっているかチェック
        min_text = range_slider.min_label.text()
        max_text = range_slider.max_label.text()

        assert len(min_text) == 10  # YYYY-MM-DD format
        assert min_text.count("-") == 2
        assert len(max_text) == 10
        assert max_text.count("-") == 2

    def test_numeric_mode_labels(self, range_slider):
        """数値モード時のラベル表示テスト"""
        range_slider.slider.setValue((25, 75))
        range_slider.update_labels()

        min_text = range_slider.min_label.text()
        max_text = range_slider.max_label.text()

        # 数値にカンマが含まれているかチェック（1000以上の場合）
        assert min_text.replace(",", "").isdigit()
        assert max_text.replace(",", "").isdigit()

    def test_value_changed_signal(self, range_slider, qtbot):
        """valueChangedシグナルのテスト"""
        with qtbot.waitSignal(range_slider.valueChanged, timeout=1000):
            range_slider.slider.setValue((30, 70))


class TestFilterSearchPanel:
    """FilterSearchPanel のユニットテスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット (pytest-qt対応)"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    @patch("lorairo.gui.widgets.filter_search_panel.FilterSearchPanel.setup_custom_widgets")
    @patch("lorairo.gui.widgets.filter_search_panel.FilterSearchPanel.setup_favorite_filters_ui")
    @patch("lorairo.gui.widgets.filter_search_panel.FilterSearchPanel.connect_signals")
    def filter_panel(
        self,
        mock_connect_signals,
        mock_setup_favorite_filters,
        mock_setup_custom_widgets,
        parent_widget,
        qtbot,
    ):
        """テスト用FilterSearchPanel（UI初期化をモック）"""
        panel = FilterSearchPanel(parent_widget)
        qtbot.addWidget(panel)

        # UI要素をモック（チェックボックス更新）
        panel.lineEditSearch = Mock()
        panel.checkboxTags = Mock()  # radioTags → checkboxTags
        panel.checkboxCaption = Mock()  # radioCaption → checkboxCaption
        panel.radioAnd = Mock()
        panel.radioOr = Mock()
        panel.comboResolution = Mock()
        panel.comboAspectRatio = Mock()
        panel.lineEditWidth = Mock()
        panel.lineEditHeight = Mock()
        panel.checkboxDateFilter = Mock()
        panel.frameDateRange = Mock()
        panel.checkboxOnlyUntagged = Mock()
        panel.checkboxOnlyUncaptioned = Mock()
        panel.checkboxExcludeDuplicates = Mock()
        panel.checkboxIncludeNSFW = Mock()
        # textEditPreview は削除されたため除外
        panel.buttonApply = Mock()
        panel.buttonClear = Mock()
        panel.dateRangeSliderPlaceholder = Mock()

        # DateRangeSlider モック
        panel.date_range_slider = Mock()
        panel.date_range_slider.get_range.return_value = (
            1640995200,
            1703980800,
        )  # 2022-01-01 to 2023-12-30

        # QButtonGroup モック（新機能）
        from PySide6.QtWidgets import QButtonGroup

        panel.logic_button_group = Mock(spec=QButtonGroup)

        # UI オブジェクトをモック（更新された実装と一致させる）
        panel.ui = Mock()
        panel.ui.lineEditSearch = panel.lineEditSearch
        panel.ui.checkboxTags = panel.checkboxTags  # 更新
        panel.ui.checkboxCaption = panel.checkboxCaption  # 更新
        panel.ui.radioAnd = panel.radioAnd
        panel.ui.radioOr = panel.radioOr
        panel.ui.comboResolution = panel.comboResolution
        panel.ui.comboAspectRatio = panel.comboAspectRatio
        panel.ui.lineEditWidth = panel.lineEditWidth
        panel.ui.lineEditHeight = panel.lineEditHeight
        panel.ui.checkboxDateFilter = panel.checkboxDateFilter
        panel.ui.frameDateRange = panel.frameDateRange
        panel.ui.checkboxOnlyUntagged = panel.checkboxOnlyUntagged
        panel.ui.checkboxOnlyUncaptioned = panel.checkboxOnlyUncaptioned
        panel.ui.checkboxExcludeDuplicates = panel.checkboxExcludeDuplicates
        panel.ui.checkboxIncludeNSFW = panel.checkboxIncludeNSFW
        # textEditPreview は削除

        # SearchFilterService モック
        panel.search_filter_service = Mock()

        return panel

    def test_initialization(self, filter_panel):
        """初期化テスト（リファクタリング後）"""
        assert hasattr(filter_panel, "lineEditSearch")
        assert hasattr(filter_panel, "date_range_slider")
        assert hasattr(filter_panel, "logic_button_group")  # 新機能
        assert hasattr(filter_panel, "filter_applied")

    def test_get_filter_conditions_basic_search(self, filter_panel):
        """基本検索条件取得テスト"""
        # UI状態設定（チェックボックス更新）
        filter_panel.lineEditSearch.text.return_value = "test search"
        filter_panel.checkboxTags.isChecked.return_value = True  # 更新
        filter_panel.radioAnd.isChecked.return_value = True
        filter_panel.comboResolution.currentText.return_value = "全て"
        filter_panel.comboResolution.currentIndex.return_value = 0
        filter_panel.comboAspectRatio.currentText.return_value = "全て"
        filter_panel.comboAspectRatio.currentIndex.return_value = 0
        filter_panel.checkboxDateFilter.isChecked.return_value = False
        filter_panel.checkboxOnlyUntagged.isChecked.return_value = False
        filter_panel.checkboxOnlyUncaptioned.isChecked.return_value = False
        filter_panel.checkboxExcludeDuplicates.isChecked.return_value = False
        filter_panel.checkboxIncludeNSFW.isChecked.return_value = False

        # Mock SearchFilterService to return proper SearchConditions
        from unittest.mock import Mock

        mock_search_conditions = Mock()
        mock_search_conditions.search_type = "tags"
        mock_search_conditions.keywords = ["test", "search"]
        mock_search_conditions.tag_logic = "and"
        mock_search_conditions.resolution_filter = None
        mock_search_conditions.custom_width = ""
        mock_search_conditions.custom_height = ""
        mock_search_conditions.aspect_ratio_filter = None
        mock_search_conditions.date_filter_enabled = False
        mock_search_conditions.date_range_start = None
        mock_search_conditions.date_range_end = None
        mock_search_conditions.only_untagged = False
        mock_search_conditions.only_uncaptioned = False
        mock_search_conditions.exclude_duplicates = False

        filter_panel.search_filter_service.get_current_conditions.return_value = mock_search_conditions

        conditions = filter_panel.get_current_conditions()

        assert conditions["search_type"] == "tags"
        assert conditions["keywords"] == ["test", "search"]
        assert conditions["tag_logic"] == "and"
        assert conditions["resolution_filter"] is None
        assert conditions["aspect_ratio_filter"] is None
        assert conditions["date_filter_enabled"] is False
        assert conditions["only_untagged"] is False
        assert conditions["only_uncaptioned"] is False
        assert conditions["exclude_duplicates"] is False

    def test_get_filter_conditions_caption_search(self, filter_panel):
        """キャプション検索条件テスト"""
        # UI状態設定（キャプション検索、チェックボックス更新）
        filter_panel.lineEditSearch.text.return_value = "beautiful landscape"
        filter_panel.checkboxTags.isChecked.return_value = False  # 更新
        filter_panel.checkboxCaption.isChecked.return_value = True  # 更新
        filter_panel.radioAnd.isChecked.return_value = False
        filter_panel.radioOr.isChecked.return_value = True
        filter_panel.comboResolution.currentText.return_value = "全て"
        filter_panel.comboResolution.currentIndex.return_value = 0
        filter_panel.comboAspectRatio.currentText.return_value = "全て"
        filter_panel.comboAspectRatio.currentIndex.return_value = 0
        filter_panel.checkboxDateFilter.isChecked.return_value = False
        filter_panel.checkboxOnlyUntagged.isChecked.return_value = False
        filter_panel.checkboxOnlyUncaptioned.isChecked.return_value = False
        filter_panel.checkboxExcludeDuplicates.isChecked.return_value = False
        filter_panel.checkboxIncludeNSFW.isChecked.return_value = False

        # Mock SearchFilterService for caption search
        mock_search_conditions = Mock()
        mock_search_conditions.search_type = "caption"
        mock_search_conditions.keywords = ["beautiful", "landscape"]
        mock_search_conditions.tag_logic = "or"
        mock_search_conditions.resolution_filter = None
        mock_search_conditions.custom_width = ""
        mock_search_conditions.custom_height = ""
        mock_search_conditions.aspect_ratio_filter = None
        mock_search_conditions.date_filter_enabled = False
        mock_search_conditions.date_range_start = None
        mock_search_conditions.date_range_end = None
        mock_search_conditions.only_untagged = False
        mock_search_conditions.only_uncaptioned = False
        mock_search_conditions.exclude_duplicates = False

        filter_panel.search_filter_service.get_current_conditions.return_value = mock_search_conditions

        conditions = filter_panel.get_current_conditions()

        assert conditions["keywords"] == ["beautiful", "landscape"]
        assert conditions["search_type"] == "caption"
        assert conditions["tag_logic"] == "or"

    def test_get_filter_conditions_date_range(self, filter_panel):
        """日付範囲条件テスト"""
        # UI状態設定（日付フィルター有効、チェックボックス更新）
        filter_panel.lineEditSearch.text.return_value = ""
        filter_panel.checkboxTags.isChecked.return_value = True  # 更新
        filter_panel.radioAnd.isChecked.return_value = True
        filter_panel.comboResolution.currentText.return_value = "全て"
        filter_panel.comboResolution.currentIndex.return_value = 0
        filter_panel.comboAspectRatio.currentText.return_value = "全て"
        filter_panel.comboAspectRatio.currentIndex.return_value = 0
        filter_panel.checkboxDateFilter.isChecked.return_value = True
        filter_panel.checkboxOnlyUntagged.isChecked.return_value = False
        filter_panel.checkboxOnlyUncaptioned.isChecked.return_value = False
        filter_panel.checkboxExcludeDuplicates.isChecked.return_value = False
        filter_panel.checkboxIncludeNSFW.isChecked.return_value = False

        # Mock SearchFilterService for date range
        mock_search_conditions = Mock()
        mock_search_conditions.search_type = "tags"
        mock_search_conditions.keywords = []
        mock_search_conditions.tag_logic = "and"
        mock_search_conditions.resolution_filter = None
        mock_search_conditions.custom_width = ""
        mock_search_conditions.custom_height = ""
        mock_search_conditions.aspect_ratio_filter = None
        mock_search_conditions.date_filter_enabled = True
        mock_search_conditions.date_range_start = 1640995200  # 2022-01-01
        mock_search_conditions.date_range_end = 1703980800  # 2023-12-30
        mock_search_conditions.only_untagged = False
        mock_search_conditions.only_uncaptioned = False
        mock_search_conditions.exclude_duplicates = False

        filter_panel.search_filter_service.get_current_conditions.return_value = mock_search_conditions

        conditions = filter_panel.get_current_conditions()

        assert conditions["date_filter_enabled"] is True
        assert conditions["date_range_start"] is not None
        assert conditions["date_range_end"] is not None
        assert isinstance(conditions["date_range_start"], int)
        assert isinstance(conditions["date_range_end"], int)

    def test_get_filter_conditions_all_options(self, filter_panel):
        """全オプション有効時の条件テスト"""
        # UI状態設定（全オプション有効、チェックボックス更新）
        filter_panel.lineEditSearch.text.return_value = "test"
        filter_panel.checkboxTags.isChecked.return_value = True  # 更新
        filter_panel.radioAnd.isChecked.return_value = True
        filter_panel.comboResolution.currentText.return_value = "1024x1024"
        filter_panel.comboResolution.currentIndex.return_value = 2
        filter_panel.comboAspectRatio.currentText.return_value = "正方形 (1:1)"
        filter_panel.comboAspectRatio.currentIndex.return_value = 1
        filter_panel.checkboxDateFilter.isChecked.return_value = True
        filter_panel.checkboxOnlyUntagged.isChecked.return_value = True
        filter_panel.checkboxOnlyUncaptioned.isChecked.return_value = True
        filter_panel.checkboxExcludeDuplicates.isChecked.return_value = True
        filter_panel.checkboxIncludeNSFW.isChecked.return_value = True

        # Mock SearchFilterService for all options enabled
        mock_search_conditions = Mock()
        mock_search_conditions.search_type = "tags"
        mock_search_conditions.keywords = ["test"]
        mock_search_conditions.tag_logic = "and"
        mock_search_conditions.resolution_filter = "1024x1024"
        mock_search_conditions.custom_width = ""
        mock_search_conditions.custom_height = ""
        mock_search_conditions.aspect_ratio_filter = "正方形 (1:1)"
        mock_search_conditions.date_filter_enabled = True
        mock_search_conditions.date_range_start = 1640995200
        mock_search_conditions.date_range_end = 1703980800
        mock_search_conditions.only_untagged = True
        mock_search_conditions.only_uncaptioned = True
        mock_search_conditions.exclude_duplicates = True

        filter_panel.search_filter_service.get_current_conditions.return_value = mock_search_conditions

        conditions = filter_panel.get_current_conditions()

        assert conditions["keywords"] == ["test"]
        assert conditions["resolution_filter"] == "1024x1024"
        assert conditions["aspect_ratio_filter"] == "正方形 (1:1)"
        assert conditions["date_filter_enabled"] is True
        assert conditions["only_untagged"] is True
        assert conditions["only_uncaptioned"] is True
        assert conditions["exclude_duplicates"] is True

    def test_on_clear_filter(self, filter_panel):
        """フィルタークリアテスト（実際の清理動作に合わせたテスト）"""
        filter_panel._on_clear_clicked()

        # 実際のui要素を通じてクリアされることを確認（チェックボックス更新）
        filter_panel.ui.lineEditSearch.clear.assert_called_once()
        filter_panel.ui.checkboxTags.setChecked.assert_called_with(True)  # 更新
        filter_panel.ui.checkboxCaption.setChecked.assert_called_with(False)  # 更新
        filter_panel.ui.radioAnd.setChecked.assert_called_with(True)
        filter_panel.ui.comboResolution.setCurrentIndex.assert_called_with(0)
        filter_panel.ui.comboAspectRatio.setCurrentIndex.assert_called_with(0)
        filter_panel.ui.checkboxDateFilter.setChecked.assert_called_with(False)
        filter_panel.ui.checkboxOnlyUntagged.setChecked.assert_called_with(False)
        filter_panel.ui.checkboxOnlyUncaptioned.setChecked.assert_called_with(False)
        filter_panel.ui.checkboxExcludeDuplicates.setChecked.assert_called_with(False)
        # textEditPreview は削除されたため、関連アサートを削除

    def test_dropdown_items_preserved_after_clear(self, filter_panel):
        """ドロップダウンアイテムが保持されるテスト（バグ修正確認）"""
        # ドロップダウンのアイテムが初期状態で存在することを確認
        filter_panel.ui.comboResolution.count.return_value = 7  # 解像度の選択肢数
        filter_panel.ui.comboAspectRatio.count.return_value = 6  # アスペクト比の選択肢数

        # クリアボタンを押す
        filter_panel._on_clear_clicked()

        # setCurrentIndex(0)が呼ばれることを確認（アイテムをクリアしていない）
        filter_panel.ui.comboResolution.setCurrentIndex.assert_called_with(0)
        filter_panel.ui.comboAspectRatio.setCurrentIndex.assert_called_with(0)

        # clear()は呼ばれないことを確認（これがバグ修正のポイント）
        filter_panel.ui.comboResolution.clear.assert_not_called()
        filter_panel.ui.comboAspectRatio.clear.assert_not_called()

    def test_on_apply_filter_signal(self, filter_panel, qtbot):
        """フィルター適用シグナルテスト"""
        # MockSearchFilterServiceを設定
        mock_search_service = Mock()
        mock_search_service.create_search_conditions.return_value = {
            "search_text": "test",
            "search_type": "tags",
        }
        mock_search_service.execute_search_with_filters.return_value = ([], 0)
        filter_panel.search_filter_service = mock_search_service

        # UI状態をセットアップ（直接モックされた要素を使用、チェックボックス更新）
        filter_panel.lineEditSearch.text.return_value = "test"
        filter_panel.checkboxTags.isChecked.return_value = True  # 更新
        filter_panel.radioAnd.isChecked.return_value = True
        filter_panel.comboResolution.currentText.return_value = "全て"
        filter_panel.comboAspectRatio.currentText.return_value = "全て"
        filter_panel.checkboxDateFilter.isChecked.return_value = False
        filter_panel.checkboxOnlyUntagged.isChecked.return_value = False
        filter_panel.checkboxOnlyUncaptioned.isChecked.return_value = False
        filter_panel.checkboxExcludeDuplicates.isChecked.return_value = False
        filter_panel.lineEditWidth.text.return_value = ""
        filter_panel.lineEditHeight.text.return_value = ""

        # UI オブジェクトをモックして実装と一致させる
        filter_panel.ui = Mock()
        filter_panel.ui.lineEditSearch = filter_panel.lineEditSearch
        filter_panel.ui.checkboxTags = filter_panel.checkboxTags  # 更新
        filter_panel.ui.radioAnd = filter_panel.radioAnd
        filter_panel.ui.comboResolution = filter_panel.comboResolution
        filter_panel.ui.comboAspectRatio = filter_panel.comboAspectRatio
        filter_panel.ui.checkboxDateFilter = filter_panel.checkboxDateFilter
        filter_panel.ui.checkboxOnlyUntagged = filter_panel.checkboxOnlyUntagged
        filter_panel.ui.checkboxOnlyUncaptioned = filter_panel.checkboxOnlyUncaptioned
        filter_panel.ui.checkboxExcludeDuplicates = filter_panel.checkboxExcludeDuplicates
        filter_panel.ui.lineEditWidth = filter_panel.lineEditWidth
        filter_panel.ui.lineEditHeight = filter_panel.lineEditHeight
        # textEditPreview は削除されたため除外

        # search_requestedシグナルをモック
        signal_mock = Mock()
        filter_panel.search_requested = signal_mock

        filter_panel._on_apply_clicked()

        # シグナルが発行されたことを確認
        signal_mock.emit.assert_called_once()
        emitted_data = signal_mock.emit.call_args[0][0]
        assert "results" in emitted_data
        assert "count" in emitted_data
        assert "conditions" in emitted_data

    def test_checkbox_search_types_new_functionality(self, filter_panel):
        """チェックボックス式検索タイプ選択テスト（新機能）"""
        # タグのみ選択
        filter_panel.ui.checkboxTags.isChecked.return_value = True
        filter_panel.ui.checkboxCaption.isChecked.return_value = False

        selected_types = filter_panel._get_selected_search_types()
        assert selected_types == ["tags"]

        primary_type = filter_panel._get_primary_search_type()
        assert primary_type == "tags"

    def test_checkbox_both_search_types_new_functionality(self, filter_panel):
        """両方のチェックボックス選択テスト（新機能）"""
        # 両方選択
        filter_panel.ui.checkboxTags.isChecked.return_value = True
        filter_panel.ui.checkboxCaption.isChecked.return_value = True

        selected_types = filter_panel._get_selected_search_types()
        assert "tags" in selected_types
        assert "caption" in selected_types
        assert len(selected_types) == 2

        # プライマリタイプはタグが優先
        primary_type = filter_panel._get_primary_search_type()
        assert primary_type == "tags"

    def test_checkbox_caption_only_new_functionality(self, filter_panel):
        """キャプションのみ選択テスト（新機能）"""
        # キャプションのみ選択
        filter_panel.ui.checkboxTags.isChecked.return_value = False
        filter_panel.ui.checkboxCaption.isChecked.return_value = True

        selected_types = filter_panel._get_selected_search_types()
        assert selected_types == ["caption"]

        primary_type = filter_panel._get_primary_search_type()
        assert primary_type == "caption"

    def test_checkbox_none_selected_new_functionality(self, filter_panel):
        """何も選択されていない場合のテスト（新機能）"""
        # 何も選択されていない
        filter_panel.ui.checkboxTags.isChecked.return_value = False
        filter_panel.ui.checkboxCaption.isChecked.return_value = False

        selected_types = filter_panel._get_selected_search_types()
        assert selected_types == []

        # デフォルトはタグ
        primary_type = filter_panel._get_primary_search_type()
        assert primary_type == "tags"

    def test_qbuttongroup_logic_operators_new_functionality(self, filter_panel):
        """QButtonGroup論理演算子テスト（新機能）"""
        # QButtonGroupが正しく設定されているかテスト
        assert hasattr(filter_panel, "logic_button_group")
        assert filter_panel.logic_button_group is not None

        # AND選択
        filter_panel.ui.radioAnd.isChecked.return_value = True
        filter_panel.ui.radioOr.isChecked.return_value = False

        # OR選択
        filter_panel.ui.radioAnd.isChecked.return_value = False
        filter_panel.ui.radioOr.isChecked.return_value = True

    def test_search_type_input_state_update_new_functionality(self, filter_panel):
        """検索タイプ変更時の入力状態更新テスト（新機能）"""
        # 未タグ検索有効時
        filter_panel.ui.checkboxTags.isChecked.return_value = True
        filter_panel.ui.checkboxOnlyUntagged.isChecked.return_value = True
        filter_panel.ui.checkboxCaption.isChecked.return_value = False
        filter_panel.ui.checkboxOnlyUncaptioned.isChecked.return_value = False

        filter_panel._update_search_input_state()

        # 入力が無効化されることを確認
        filter_panel.ui.lineEditSearch.setEnabled.assert_called_with(False)

    def test_search_type_input_state_normal_new_functionality(self, filter_panel):
        """検索タイプ通常時の入力状態テスト（新機能）"""
        # 通常の検索時
        filter_panel.ui.checkboxTags.isChecked.return_value = True
        filter_panel.ui.checkboxOnlyUntagged.isChecked.return_value = False
        filter_panel.ui.checkboxCaption.isChecked.return_value = False
        filter_panel.ui.checkboxOnlyUncaptioned.isChecked.return_value = False

        filter_panel._update_search_input_state()

        # 入力が有効のままであることを確認
        filter_panel.ui.lineEditSearch.setEnabled.assert_called_with(True)


class TestFilterWidgetIntegration:
    """フィルターウィジェット統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    def test_range_slider_in_filter_panel_integration(self, parent_widget, qtbot):
        """FilterSearchPanel内でのCustomRangeSlider統合テスト"""
        # CustomRangeSliderを単体で作成
        range_slider = CustomRangeSlider(parent_widget, min_value=1000, max_value=100000)
        qtbot.addWidget(range_slider)

        # 日付モードに設定
        range_slider.set_date_range()
        assert range_slider.is_date_mode is True

        # 値を変更
        range_slider.slider.setValue((20, 80))
        min_val, max_val = range_slider.get_range()

        assert min_val < max_val
        assert min_val >= range_slider.min_value
        assert max_val <= range_slider.max_value

    def test_signal_connections_mock(self, parent_widget):
        """シグナル接続のモックテスト"""
        # CustomRangeSliderのシグナル接続テスト
        range_slider = CustomRangeSlider(parent_widget)
        callback_mock = Mock()

        # シグナル接続
        range_slider.valueChanged.connect(callback_mock)

        # スライダー値変更をシミュレート
        range_slider.slider.setValue((10, 90))
        range_slider.update_labels()  # 手動でupdate_labelsを呼び出し

        # シグナルが発行されたことを確認
        assert callback_mock.call_count >= 1

    def test_qbuttongroup_integration_real(self, parent_widget, qtbot):
        """QButtonGroup統合テスト（実際のウィジェット、新機能）"""
        # QButtonGroupが正しく動作することを確認
        from PySide6.QtWidgets import QButtonGroup, QRadioButton, QVBoxLayout

        layout = QVBoxLayout(parent_widget)
        radio1 = QRadioButton("AND")
        radio2 = QRadioButton("OR")

        layout.addWidget(radio1)
        layout.addWidget(radio2)

        button_group = QButtonGroup(parent_widget)
        button_group.addButton(radio1)
        button_group.addButton(radio2)

        # 片方を選択すると、もう片方が自動的に無効になることを確認
        radio1.setChecked(True)
        assert radio1.isChecked()
        assert not radio2.isChecked()

        radio2.setChecked(True)
        assert not radio1.isChecked()
        assert radio2.isChecked()

        # デフォルト設定テスト
        radio1.setChecked(True)  # ANDをデフォルトに設定
        assert radio1.isChecked()  # ANDが選択されている
