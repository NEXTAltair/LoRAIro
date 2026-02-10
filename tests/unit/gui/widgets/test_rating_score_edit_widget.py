# tests/unit/gui/widgets/test_rating_score_edit_widget.py

from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt

from lorairo.gui.widgets.rating_score_edit_widget import RatingScoreEditWidget


class TestRatingScoreEditWidget:
    """RatingScoreEditWidget単体テスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用RatingScoreEditWidget"""
        widget = RatingScoreEditWidget()
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, widget):
        """初期化テスト"""
        assert widget._current_image_id is None
        assert hasattr(widget.ui, "comboBoxRating")
        assert hasattr(widget.ui, "sliderScore")
        assert hasattr(widget.ui, "labelScoreValue")
        assert hasattr(widget.ui, "pushButtonSave")

    def test_populate_from_db_value(self, widget):
        """DB値（0.0-10.0）からの読み込みテスト"""
        # DB値を含むimage_data
        image_data = {
            "id": 123,
            "rating": "PG-13",
            "score_value": 7.5,  # DB値（0.0-10.0）
        }

        widget.populate_from_image_data(image_data)

        # 変換が正しく行われたことを確認
        assert widget._current_image_id == 123
        assert widget.ui.comboBoxRating.currentText() == "PG-13"
        assert widget.ui.sliderScore.value() == 750  # UI値（0-1000）
        assert widget.ui.labelScoreValue.text() == "7.50"

    def test_populate_from_ui_value(self, widget):
        """UI値（0-1000）からの読み込みテスト（後方互換性）"""
        # UI値を含むimage_data
        image_data = {
            "id": 456,
            "rating": "R",
            "score": 850,  # UI値（0-1000）
        }

        widget.populate_from_image_data(image_data)

        # UI値がそのまま使われることを確認
        assert widget._current_image_id == 456
        assert widget.ui.comboBoxRating.currentText() == "R"
        assert widget.ui.sliderScore.value() == 850
        assert widget.ui.labelScoreValue.text() == "8.50"

    def test_populate_with_score_value_priority(self, widget):
        """score_valueが優先されることを確認"""
        # 両方の値を持つimage_data
        image_data = {
            "id": 789,
            "rating": "X",
            "score": 1000,  # UI値
            "score_value": 3.5,  # DB値（こちらが優先）
        }

        widget.populate_from_image_data(image_data)

        # score_valueが優先されることを確認
        assert widget._current_image_id == 789
        assert widget.ui.sliderScore.value() == 350  # DB値から変換
        assert widget.ui.labelScoreValue.text() == "3.50"

    def test_save_emits_ui_value(self, widget, qtbot):
        """保存時にUI値（0-1000）が発行されることを確認"""
        # DB値からデータ読み込み
        image_data = {
            "id": 999,
            "rating": "XXX",
            "score_value": 9.25,  # DB値
        }
        widget.populate_from_image_data(image_data)

        # シグナルスパイをセットアップ
        with (
            qtbot.waitSignal(widget.rating_changed, timeout=1000) as rating_blocker,
            qtbot.waitSignal(widget.score_changed, timeout=1000) as score_blocker,
        ):
            # 保存ボタンをクリック
            widget.ui.pushButtonSave.click()

        # 発行されたシグナルを確認
        assert rating_blocker.args == [999, "XXX"]
        assert score_blocker.args == [999, 925]  # UI値（0-1000）

    def test_slider_updates_label(self, widget, qtbot):
        """スライダー変更時にラベルが更新されることを確認"""
        # スライダーを変更
        widget.ui.sliderScore.setValue(650)

        # ラベルが更新されることを確認
        qtbot.waitUntil(lambda: widget.ui.labelScoreValue.text() == "6.50", timeout=1000)
        assert widget.ui.labelScoreValue.text() == "6.50"

    def test_default_values(self, widget):
        """デフォルト値のテスト"""
        image_data = {"id": 111}

        widget.populate_from_image_data(image_data)

        # デフォルト値が適用されることを確認
        assert widget.ui.comboBoxRating.currentText() == "PG-13"
        assert widget.ui.sliderScore.value() == 500
        assert widget.ui.labelScoreValue.text() == "5.00"

    def test_edge_case_min_value(self, widget):
        """最小値（0.0）のテスト"""
        image_data = {
            "id": 222,
            "score_value": 0.0,
        }

        widget.populate_from_image_data(image_data)

        assert widget.ui.sliderScore.value() == 0
        assert widget.ui.labelScoreValue.text() == "0.00"

    def test_edge_case_max_value(self, widget):
        """最大値（10.0）のテスト"""
        image_data = {
            "id": 333,
            "score_value": 10.0,
        }

        widget.populate_from_image_data(image_data)

        assert widget.ui.sliderScore.value() == 1000
        assert widget.ui.labelScoreValue.text() == "10.00"

    def test_initialization_batch_mode_attributes(self, widget):
        """初期化時のバッチモード属性テスト"""
        assert widget._is_batch_mode is False
        assert widget._selected_image_ids == []

    def test_populate_from_image_data_resets_batch_mode(self, widget):
        """populate_from_image_data がバッチモードをリセットすること"""
        # バッチモードを手動で有効化
        widget._is_batch_mode = True
        widget._selected_image_ids = [1, 2, 3]

        # 単一画像データで populate
        widget.populate_from_image_data({"id": 100, "rating": "PG", "score_value": 5.0})

        assert widget._is_batch_mode is False
        assert widget._selected_image_ids == []
        assert widget._current_image_id == 100


class TestRatingScoreEditWidgetBatchMode:
    """RatingScoreEditWidget バッチモードテスト"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用RatingScoreEditWidget"""
        widget = RatingScoreEditWidget()
        qtbot.addWidget(widget)
        return widget

    @pytest.fixture
    def mock_db_manager(self):
        """モックImageDatabaseManager"""
        manager = Mock()
        manager.repository = Mock()
        return manager

    def test_populate_from_selection_common_rating(self, widget, mock_db_manager):
        """全画像が同じRatingの場合、共通値が表示される"""
        mock_db_manager.repository.get_image_metadata.side_effect = [
            {"rating": "R", "score_value": 5.0},
            {"rating": "R", "score_value": 7.0},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget._is_batch_mode is True
        assert widget._selected_image_ids == [1, 2]
        assert widget.ui.comboBoxRating.currentText() == "R"

    def test_populate_from_selection_different_ratings(self, widget, mock_db_manager):
        """異なるRatingの場合、デフォルトが表示される"""
        mock_db_manager.repository.get_image_metadata.side_effect = [
            {"rating": "PG", "score_value": 5.0},
            {"rating": "X", "score_value": 5.0},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget._is_batch_mode is True
        # デフォルト: PG-13（index=1）
        assert widget.ui.comboBoxRating.currentText() == "PG-13"

    def test_populate_from_selection_common_score(self, widget, mock_db_manager):
        """全画像が同じScoreの場合、共通値が表示される"""
        mock_db_manager.repository.get_image_metadata.side_effect = [
            {"rating": "PG", "score_value": 8.5},
            {"rating": "R", "score_value": 8.5},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget.ui.sliderScore.value() == 850
        assert widget.ui.labelScoreValue.text() == "8.50"

    def test_populate_from_selection_different_scores(self, widget, mock_db_manager):
        """異なるScoreの場合、デフォルト値が表示される"""
        mock_db_manager.repository.get_image_metadata.side_effect = [
            {"rating": "PG", "score_value": 3.0},
            {"rating": "PG", "score_value": 7.0},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget.ui.sliderScore.value() == 500
        assert widget.ui.labelScoreValue.text() == "5.00"

    def test_populate_from_selection_empty_list(self, widget, mock_db_manager):
        """空リストの場合、何も変更されない"""
        widget.populate_from_selection([], mock_db_manager)

        assert widget._is_batch_mode is False

    def test_batch_save_emits_batch_signals(self, widget, mock_db_manager, qtbot):
        """バッチモードでSave時にバッチシグナルが発行される"""
        mock_db_manager.repository.get_image_metadata.side_effect = [
            {"rating": "PG-13", "score_value": 5.0},
            {"rating": "PG-13", "score_value": 5.0},
        ]

        widget.populate_from_selection([10, 20], mock_db_manager)

        with (
            qtbot.waitSignal(widget.batch_rating_changed, timeout=1000) as rating_blocker,
            qtbot.waitSignal(widget.batch_score_changed, timeout=1000) as score_blocker,
        ):
            widget.ui.pushButtonSave.click()

        assert rating_blocker.args == [[10, 20], "PG-13"]
        assert score_blocker.args == [[10, 20], 500]

    def test_single_mode_save_does_not_emit_batch_signals(self, widget, qtbot):
        """単一選択モードではバッチシグナルが発行されない"""
        widget.populate_from_image_data({"id": 1, "rating": "PG", "score_value": 5.0})

        batch_emitted = False

        def on_batch_signal(*args):
            nonlocal batch_emitted
            batch_emitted = True

        widget.batch_rating_changed.connect(on_batch_signal)

        with qtbot.waitSignal(widget.rating_changed, timeout=1000):
            widget.ui.pushButtonSave.click()

        assert batch_emitted is False
