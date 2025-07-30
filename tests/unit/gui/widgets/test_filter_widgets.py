# tests/unit/gui/widgets/test_filter_widgets.py

from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import QDate, QDateTime, Qt, QTime, QTimeZone
from PySide6.QtWidgets import QWidget

from lorairo.gui.widgets.filter import CustomRangeSlider, FilterSearchPanel


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
        """スケール変換の境界値テスト"""
        # 最小値 (0)
        assert range_slider.scale_to_value(0) == 100

        # 最大値 (100)
        assert range_slider.scale_to_value(100) == 10000

        # 中間値テスト（対数スケール）
        mid_value = range_slider.scale_to_value(50)
        assert 100 < mid_value < 10000

    def test_get_range(self, range_slider):
        """範囲取得テスト"""
        # スライダーの値を設定
        range_slider.slider.setValue((25, 75))
        min_val, max_val = range_slider.get_range()

        assert isinstance(min_val, int)
        assert isinstance(max_val, int)
        assert min_val >= range_slider.min_value
        assert max_val <= range_slider.max_value
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
    @patch("lorairo.gui.widgets.filter.FilterSearchPanel.setupUi")
    @patch("lorairo.gui.widgets.filter.FilterSearchPanel.setup_date_range_slider")
    @patch("lorairo.gui.widgets.filter.FilterSearchPanel.setup_connections")
    def filter_panel(self, mock_connections, mock_date_slider, mock_setup_ui, parent_widget, qtbot):
        """テスト用FilterSearchPanel（UI初期化をモック）"""
        panel = FilterSearchPanel(parent_widget)
        qtbot.addWidget(panel)

        # UI要素をモック
        panel.lineEditSearch = Mock()
        panel.radioTags = Mock()
        panel.radioCaption = Mock()
        panel.radioAnd = Mock()
        panel.radioOr = Mock()
        panel.comboResolution = Mock()
        panel.comboAspectRatio = Mock()
        panel.lineEditWidth = Mock()
        panel.lineEditHeight = Mock()
        panel.frameCustomResolution = Mock()
        panel.checkboxDateFilter = Mock()
        panel.frameDateRange = Mock()
        panel.checkboxOnlyUntagged = Mock()
        panel.checkboxOnlyUncaptioned = Mock()
        panel.checkboxExcludeDuplicates = Mock()
        panel.checkboxIncludeNSFW = Mock()
        panel.textEditPreview = Mock()
        panel.buttonApply = Mock()
        panel.buttonClear = Mock()
        panel.dateRangeSliderPlaceholder = Mock()

        # DateRangeSlider モック
        panel.date_range_slider = Mock()
        panel.date_range_slider.get_range.return_value = (
            1640995200,
            1703980800,
        )  # 2022-01-01 to 2023-12-30

        return panel

    def test_initialization(self, filter_panel):
        """初期化テスト"""
        assert hasattr(filter_panel, "lineEditSearch")
        assert hasattr(filter_panel, "date_range_slider")
        assert hasattr(filter_panel, "filterApplied")

    def test_toggle_custom_resolution_show(self, filter_panel):
        """カスタム解像度フレーム表示テスト"""
        filter_panel.toggle_custom_resolution("カスタム...")
        filter_panel.frameCustomResolution.setVisible.assert_called_with(True)

    def test_toggle_custom_resolution_hide(self, filter_panel):
        """カスタム解像度フレーム非表示テスト"""
        filter_panel.toggle_custom_resolution("1024x1024")
        filter_panel.frameCustomResolution.setVisible.assert_called_with(False)

    def test_get_filter_conditions_basic_search(self, filter_panel):
        """基本検索条件取得テスト"""
        # UI状態設定
        filter_panel.lineEditSearch.text.return_value = "test search"
        filter_panel.radioTags.isChecked.return_value = True
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

        conditions = filter_panel.get_filter_conditions()

        assert conditions["search_text"] == "test search"
        assert conditions["search_type"] == "tags"
        assert conditions["search_mode"] == "and"
        assert conditions["resolution"] is None
        assert conditions["aspect_ratio"] is None
        assert conditions["date_range"] is None
        assert conditions["only_untagged"] is False
        assert conditions["only_uncaptioned"] is False
        assert conditions["exclude_duplicates"] is False
        assert conditions["include_nsfw"] is False

    def test_get_filter_conditions_caption_search(self, filter_panel):
        """キャプション検索条件テスト"""
        # UI状態設定（キャプション検索）
        filter_panel.lineEditSearch.text.return_value = "beautiful landscape"
        filter_panel.radioTags.isChecked.return_value = False
        filter_panel.radioCaption.isChecked.return_value = True
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

        conditions = filter_panel.get_filter_conditions()

        assert conditions["search_text"] == "beautiful landscape"
        assert conditions["search_type"] == "caption"
        assert conditions["search_mode"] == "or"

    def test_get_filter_conditions_custom_resolution(self, filter_panel):
        """カスタム解像度条件テスト"""
        # UI状態設定（カスタム解像度）
        filter_panel.lineEditSearch.text.return_value = ""
        filter_panel.radioTags.isChecked.return_value = True
        filter_panel.radioAnd.isChecked.return_value = True
        filter_panel.comboResolution.currentText.return_value = "カスタム..."
        filter_panel.comboResolution.currentIndex.return_value = -1
        filter_panel.lineEditWidth.text.return_value = "1920"
        filter_panel.lineEditHeight.text.return_value = "1080"
        filter_panel.comboAspectRatio.currentText.return_value = "風景 (16:9)"
        filter_panel.comboAspectRatio.currentIndex.return_value = 2
        filter_panel.checkboxDateFilter.isChecked.return_value = False
        filter_panel.checkboxOnlyUntagged.isChecked.return_value = False
        filter_panel.checkboxOnlyUncaptioned.isChecked.return_value = False
        filter_panel.checkboxExcludeDuplicates.isChecked.return_value = False
        filter_panel.checkboxIncludeNSFW.isChecked.return_value = False

        conditions = filter_panel.get_filter_conditions()

        assert conditions["resolution"] == "1920x1080"
        assert conditions["aspect_ratio"] == "風景 (16:9)"

    def test_get_filter_conditions_date_range(self, filter_panel):
        """日付範囲条件テスト"""
        # UI状態設定（日付フィルター有効）
        filter_panel.lineEditSearch.text.return_value = ""
        filter_panel.radioTags.isChecked.return_value = True
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

        conditions = filter_panel.get_filter_conditions()

        assert conditions["date_range"] is not None
        assert isinstance(conditions["date_range"], tuple)
        assert len(conditions["date_range"]) == 2

    def test_get_filter_conditions_all_options(self, filter_panel):
        """全オプション有効時の条件テスト"""
        # UI状態設定（全オプション有効）
        filter_panel.lineEditSearch.text.return_value = "test"
        filter_panel.radioTags.isChecked.return_value = True
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

        conditions = filter_panel.get_filter_conditions()

        assert conditions["search_text"] == "test"
        assert conditions["resolution"] == "1024x1024"
        assert conditions["aspect_ratio"] == "正方形 (1:1)"
        assert conditions["date_range"] is not None
        assert conditions["only_untagged"] is True
        assert conditions["only_uncaptioned"] is True
        assert conditions["exclude_duplicates"] is True
        assert conditions["include_nsfw"] is True

    def test_on_clear_filter(self, filter_panel):
        """フィルタークリアテスト"""
        filter_panel.on_clear_filter()

        # 各UI要素がクリアされたことを確認
        filter_panel.lineEditSearch.clear.assert_called_once()
        filter_panel.radioTags.setChecked.assert_called_with(True)
        filter_panel.radioAnd.setChecked.assert_called_with(True)
        filter_panel.comboResolution.setCurrentIndex.assert_called_with(0)
        filter_panel.comboAspectRatio.setCurrentIndex.assert_called_with(0)
        filter_panel.checkboxDateFilter.setChecked.assert_called_with(False)
        filter_panel.checkboxOnlyUntagged.setChecked.assert_called_with(False)
        filter_panel.checkboxOnlyUncaptioned.setChecked.assert_called_with(False)
        filter_panel.checkboxExcludeDuplicates.setChecked.assert_called_with(False)
        filter_panel.checkboxIncludeNSFW.setChecked.assert_called_with(False)
        filter_panel.textEditPreview.clear.assert_called_once()

    def test_on_apply_filter_signal(self, filter_panel, qtbot):
        """フィルター適用シグナルテスト"""
        # UI状態をセットアップ
        filter_panel.lineEditSearch.text.return_value = "test"
        filter_panel.radioTags.isChecked.return_value = True
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

        # filterAppliedシグナルをモック
        signal_mock = Mock()
        filter_panel.filterApplied = signal_mock

        filter_panel.on_apply_filter()

        # シグナルが発行されたことを確認
        signal_mock.emit.assert_called_once()
        emitted_conditions = signal_mock.emit.call_args[0][0]
        assert emitted_conditions["search_text"] == "test"


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
