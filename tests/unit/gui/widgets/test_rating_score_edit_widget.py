# tests/unit/gui/widgets/test_rating_score_edit_widget.py

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QLabel

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
        """未設定 (手動値なし) のテスト (Issue #825)。

        手動 rating / score が無い場合は未設定表示にする:
        rating は "----"、score は slider 中立位置 (500) かつラベルは "--"。
        """
        image_data = {"id": 111}

        widget.populate_from_image_data(image_data)

        assert widget.ui.comboBoxRating.currentText() == "----"
        assert widget.ui.sliderScore.value() == 500
        # 手動スコア未設定は "--" (旧仕様の "5.00" デフォルトから変更)
        assert widget.ui.labelScoreValue.text() == "--"

    def test_save_unrated_image_does_not_emit_rating(self, widget, qtbot):
        """未設定画像の保存ではrating_changedを発行しない（scoreのみ発行）"""
        # rating 未設定の画像 → コンボボックスは "----"
        widget.populate_from_image_data({"id": 555, "score_value": 6.0})
        assert widget.ui.comboBoxRating.currentText() == "----"

        rating_emitted = False

        def on_rating_signal(*args):
            nonlocal rating_emitted
            rating_emitted = True

        widget.rating_changed.connect(on_rating_signal)

        # score_changed は発行される
        with qtbot.waitSignal(widget.score_changed, timeout=1000) as score_blocker:
            widget.ui.pushButtonSave.click()

        assert rating_emitted is False
        assert score_blocker.args == [555, 600]

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


class TestRatingScoreEditWidgetAiSection:
    """RatingScoreEditWidget AI 併記セクションのテスト (Issue #812)"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用RatingScoreEditWidget"""
        widget = RatingScoreEditWidget()
        qtbot.addWidget(widget)
        return widget

    def test_ai_section_widgets_exist(self, widget):
        """AI セクションのウィジェットが構築されていること"""
        assert set(widget._ai_rating_chips.keys()) == {"PG", "PG-13", "R", "X", "XXX"}
        assert hasattr(widget, "_ai_score_bar")
        assert hasattr(widget, "_ai_score_value")
        assert hasattr(widget, "_rating_segmented")
        assert hasattr(widget, "_manual_edit_chip")
        assert hasattr(widget, "_delta_label")

    def test_card_labels_do_not_expose_developer_notes(self, widget):
        """ユーザー向けカードに ADR 番号や DB カラム名を表示しない。"""
        visible_text = "\n".join(
            label.text() for label in widget.findChildren(QLabel) if label.text() and not label.isHidden()
        )

        for developer_term in ("ADR", "quality_score", "source 分離", "is_edited_manually", "MANUAL_EDIT"):
            assert developer_term not in visible_text
        assert "AI 評価と手動補正" in visible_text

    def test_ai_section_renders_ai_values(self, widget):
        """ai_rating / ai_score_value が AI セクションに描画される"""
        widget.populate_from_image_data(
            {"id": 1, "rating": "R", "score_value": 7.0, "ai_rating": "R", "ai_score_value": 7.0}
        )
        assert widget._ai_rating == "R"
        assert widget._ai_score_ui == 700
        assert widget._ai_score_value.text() == "7.00"
        assert widget._ai_score_bar.value() == 700

    def test_ai_section_falls_back_to_manual_source(self, widget):
        """ai_* キー未指定時は rating / score_value にフォールバックする"""
        widget.populate_from_image_data({"id": 2, "rating": "PG-13", "score_value": 4.0})
        assert widget._ai_rating == "PG-13"
        assert widget._ai_score_ui == 400
        assert widget._ai_score_value.text() == "4.00"

    def test_ai_section_unset_shows_placeholder(self, widget):
        """AI 値が無い場合はスコアバーが 0、数値は '--'"""
        widget.populate_from_image_data({"id": 3, "rating": "----", "ai_rating": "----"})
        assert widget._ai_rating is None
        assert widget._ai_score_value.text() == "--"

    def test_segmented_control_syncs_with_combo_on_populate(self, widget):
        """populate 時に SegmentedControl が comboBoxRating と同期する"""
        widget.populate_from_image_data({"id": 4, "rating": "X", "score_value": 5.0})
        assert widget._rating_segmented._buttons["X"].isChecked() is True
        assert all(
            not button.isChecked()
            for rating, button in widget._rating_segmented._buttons.items()
            if rating != "X"
        )

    def test_segmented_click_updates_combo(self, widget):
        """SegmentedControl クリックで comboBoxRating (SSoT) が更新される"""
        widget.populate_from_image_data({"id": 5, "rating": "PG", "score_value": 5.0})
        widget._rating_segmented._buttons["XXX"].click()
        assert widget.ui.comboBoxRating.currentText() == "XXX"

    def test_segmented_click_highlights_chip(self, widget):
        """#829: クリックしたチップが選択ハイライト (active QSS) される。

        #1105: QSS は DsSegmentedControl (base サイズ) が供給する。
        """
        from lorairo.gui.widgets.ds_segmented_control import _segment_button_qss

        widget.populate_from_image_data({"id": 9, "rating": "----", "score_value": None})
        btn = widget._rating_segmented._buttons["R"]
        btn.click()
        assert btn.isChecked() is True
        assert btn.styleSheet() == _segment_button_qss(True)
        # 他のチップは非選択スタイルのまま
        other = widget._rating_segmented._buttons["PG"]
        assert other.styleSheet() == _segment_button_qss(False)

    def test_segmented_deselects_all_when_no_rating(self, widget):
        """#1105: rating 未設定 (----) では全セグメントが非選択に戻る。"""
        # 一度 R を選択してから未設定データで再描画する
        widget.populate_from_image_data({"id": 3, "rating": "R", "score_value": 5.0})
        assert widget._rating_segmented._buttons["R"].isChecked() is True

        widget.populate_from_image_data({"id": 4, "rating": "----", "score_value": None})
        assert all(not button.isChecked() for button in widget._rating_segmented._buttons.values())

    def test_manual_edit_chip_hidden_when_equal_to_ai(self, widget):
        """手動値が AI と一致する初期状態では手動補正 chip は非表示"""
        widget.populate_from_image_data(
            {"id": 6, "rating": "R", "score_value": 6.0, "ai_rating": "R", "ai_score_value": 6.0}
        )
        assert widget._manual_edit_chip.isVisibleTo(widget) is False
        assert widget._delta_label.isVisibleTo(widget) is False

    def test_manual_edit_chip_shown_when_score_differs(self, widget):
        """手動スコアを AI から変更すると手動補正 chip と Δ が表示される"""
        widget.populate_from_image_data(
            {"id": 7, "rating": "R", "score_value": 6.0, "ai_rating": "R", "ai_score_value": 6.0}
        )
        widget.ui.sliderScore.setValue(650)
        assert widget._manual_edit_chip.isVisibleTo(widget) is True
        assert widget._manual_edit_chip.text() == "手動補正あり"
        assert widget._delta_label.isVisibleTo(widget) is True
        assert widget._delta_label.text() == "Δ +0.50 vs AI"

    def test_manual_edit_chip_shown_when_rating_differs(self, widget):
        """手動レーティングを AI から変更すると手動補正 chip が表示される"""
        widget.populate_from_image_data(
            {"id": 8, "rating": "R", "score_value": 6.0, "ai_rating": "R", "ai_score_value": 6.0}
        )
        widget._rating_segmented._buttons["X"].click()
        assert widget._manual_edit_chip.isVisibleTo(widget) is True
        assert widget._manual_edit_chip.text() == "手動補正あり"

    def test_combo_box_hidden_in_two_tier_card(self, widget):
        """comboBoxRating は SegmentedControl の裏で非表示の SSoT として保持される"""
        assert widget.ui.comboBoxRating.isVisibleTo(widget) is False


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
        mock_db_manager.image_repo.get_image_metadata.side_effect = [
            {"rating": "R", "score_value": 5.0},
            {"rating": "R", "score_value": 7.0},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget._is_batch_mode is True
        assert widget._selected_image_ids == [1, 2]
        assert widget.ui.comboBoxRating.currentText() == "R"

    def test_populate_from_selection_different_ratings(self, widget, mock_db_manager):
        """異なるRatingの場合、デフォルトが表示される"""
        mock_db_manager.image_repo.get_image_metadata.side_effect = [
            {"rating": "PG", "score_value": 5.0},
            {"rating": "X", "score_value": 5.0},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget._is_batch_mode is True
        # デフォルト: 未設定（----）
        assert widget.ui.comboBoxRating.currentText() == "----"

    def test_populate_from_selection_common_score(self, widget, mock_db_manager):
        """全画像が同じScoreの場合、共通値が表示される"""
        mock_db_manager.image_repo.get_image_metadata.side_effect = [
            {"rating": "PG", "score_value": 8.5},
            {"rating": "R", "score_value": 8.5},
        ]

        widget.populate_from_selection([1, 2], mock_db_manager)

        assert widget.ui.sliderScore.value() == 850
        assert widget.ui.labelScoreValue.text() == "8.50"

    def test_populate_from_selection_different_scores(self, widget, mock_db_manager):
        """異なるScoreの場合、デフォルト値が表示される"""
        mock_db_manager.image_repo.get_image_metadata.side_effect = [
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
        mock_db_manager.image_repo.get_image_metadata.side_effect = [
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

    def test_batch_save_placeholder_rating_does_not_emit_rating(self, widget, mock_db_manager, qtbot):
        """mixed Rating選択時の保存ではbatch_rating_changedを発行しない（scoreのみ発行）"""
        mock_db_manager.image_repo.get_image_metadata.side_effect = [
            {"rating": "PG", "score_value": 5.0},
            {"rating": "X", "score_value": 5.0},
        ]

        widget.populate_from_selection([10, 20], mock_db_manager)
        # mixed Rating → プレースホルダ表示
        assert widget.ui.comboBoxRating.currentText() == "----"

        rating_emitted = False

        def on_rating_signal(*args):
            nonlocal rating_emitted
            rating_emitted = True

        widget.batch_rating_changed.connect(on_rating_signal)

        with qtbot.waitSignal(widget.batch_score_changed, timeout=1000) as score_blocker:
            widget.ui.pushButtonSave.click()

        assert rating_emitted is False
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


class TestAiManualSeparation:
    """Issue #825: AI セクションと人間セクションの値分離。"""

    @pytest.fixture
    def widget(self, qtbot):
        widget = RatingScoreEditWidget()
        qtbot.addWidget(widget)
        return widget

    def test_ai_section_uses_ai_values_not_manual(self, widget):
        """AI セクションは AI 値を、人間セクションは手動値を独立して表示する。"""
        widget.populate_from_image_data(
            {
                "id": 1,
                "rating": "R",  # 手動 rating
                "score_value": 8.0,  # 手動 score
                "ai_rating": "PG",  # AI rating (手動と別)
                "ai_score_value": 3.0,  # AI score (手動と別)
            }
        )

        # 人間 (編集可能) セクション = 手動値
        assert widget.ui.comboBoxRating.currentText() == "R"
        assert widget.ui.sliderScore.value() == 800
        # AI (read-only) セクション = AI 値
        assert widget._ai_rating == "PG"
        assert widget._ai_score_ui == 300

    def test_manual_unset_with_ai_present_shows_unset_and_no_delta(self, widget):
        """手動値が無く AI のみある場合、人間側は未設定で Δ/MANUAL_EDIT を出さない。"""
        widget.populate_from_image_data(
            {
                "id": 2,
                "rating": "----",  # 手動 rating 未設定
                "score_value": None,  # 手動 score 未設定
                "ai_rating": "X",
                "ai_score_value": 6.0,
            }
        )

        # 人間側は未設定表示
        assert widget.ui.comboBoxRating.currentText() == "----"
        assert widget.ui.labelScoreValue.text() == "--"
        assert widget._manual_score_set is False
        # AI 側は AI 値
        assert widget._ai_rating == "X"
        assert widget._ai_score_ui == 600
        # 手動未編集なので差分表示・MANUAL_EDIT chip は出さない
        assert widget._delta_label.isVisible() is False
        assert widget._manual_edit_chip.isVisible() is False

    def test_ai_unset_shows_placeholder(self, widget):
        """AI 値が無い場合 AI セクションは未設定 (--) 表示。"""
        widget.populate_from_image_data(
            {
                "id": 3,
                "rating": "PG",
                "score_value": 5.0,
                "ai_rating": "----",
                "ai_score_value": None,
            }
        )

        assert widget._ai_rating is None
        assert widget._ai_score_ui is None
        assert widget._ai_score_value.text() == "--"

    def test_dragging_slider_marks_manual_set(self, widget, qtbot):
        """未設定からスライダーを動かすと手動スコアが設定済みになる。"""
        widget.populate_from_image_data({"id": 4, "score_value": None, "ai_score_value": 6.0})
        assert widget._manual_score_set is False

        widget.ui.sliderScore.setValue(700)
        assert widget._manual_score_set is True
        assert widget.ui.labelScoreValue.text() == "7.00"
