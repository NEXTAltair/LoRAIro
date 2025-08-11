from unittest.mock import Mock, patch

import pytest
from PySide6.QtCore import Qt

from lorairo.gui.widgets.model_selection_table_widget import ModelSelectionTableWidget


@pytest.fixture
def sample_models():
    return [
        {
            "name": "gpt-4-vision-preview",
            "provider": "openai",
            "capabilities": ["caption", "tags"],
            "requires_api_key": True,
            "is_local": False,
        },
        {
            "name": "claude-3-sonnet",
            "provider": "anthropic",
            "capabilities": ["caption", "tags"],
            "requires_api_key": True,
            "is_local": False,
        },
        {
            "name": "wd-v1-4-swinv2-tagger-v3",
            "provider": "local",
            "capabilities": ["tags"],
            "requires_api_key": False,
            "is_local": True,
        },
        {
            "name": "clip-aesthetic-score",
            "provider": "local",
            "capabilities": ["scores"],
            "requires_api_key": False,
            "is_local": True,
        },
    ]


@pytest.fixture
def widget(qtbot):
    w = ModelSelectionTableWidget()
    qtbot.addWidget(w)
    return w


class TestModelSelectionTableWidget:
    def test_initial_state(self, widget):
        assert widget.search_filter_service is None
        assert widget.all_models == []
        assert widget.filtered_models == []
        assert widget.tableWidgetModels.rowCount() == 0

    def test_load_models_populates_table_and_emits(self, widget, qtbot, sample_models):
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = sample_models
        mock_service.filter_models_by_criteria.return_value = sample_models

        models_loaded_spy = qtbot.waitSignal(widget.models_loaded, timeout=1000, raising=False)
        widget.set_search_filter_service(mock_service)
        widget.load_models()
        models_loaded_spy.wait()
        # イベントを捌いてテーブル状態を安定化
        qtbot.wait(0)

        assert widget.all_models == sample_models
        assert widget.filtered_models == sample_models
        assert widget.tableWidgetModels.rowCount() == len(sample_models)

        # provider 表示の確認（ローカルは「ローカル」、それ以外はTitle Case）
        providers_display = []
        for r in range(widget.tableWidgetModels.rowCount()):
            item = widget.tableWidgetModels.item(r, 2)
            if item is not None:
                providers_display.append(item.text())
        # ローカル表示が含まれ、少なくとも1つは非ローカルプロバイダー表記がある
        assert "ローカル" in providers_display
        assert any(p in providers_display for p in ("Openai", "Anthropic"))

        # capabilities 表示（カンマ結合）: ソートやイベント順の影響を避け、存在するセルから検証
        cap_texts = []
        for r in range(widget.tableWidgetModels.rowCount()):
            item = widget.tableWidgetModels.item(r, 3)
            if item is not None:
                cap_texts.append(item.text())
        assert cap_texts, "Capabilities column should have at least one populated cell"
        assert any(("," in t) or (t in ("caption", "tags", "scores")) for t in cap_texts)

    def test_apply_filters_updates_table_via_service(self, widget, sample_models):
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = sample_models
        # フィルタ結果は先頭の2件だけとする
        filtered = sample_models[:2]
        mock_service.filter_models_by_criteria.return_value = filtered

        widget.set_search_filter_service(mock_service)
        widget.load_models()

        widget.apply_filters(function_types=["caption"], providers=["openai", "anthropic"])

        mock_service.filter_models_by_criteria.assert_called_once()
        assert widget.filtered_models == filtered
        assert widget.tableWidgetModels.rowCount() == len(filtered)

    def test_selection_signals_and_get_selected_models(self, widget, qtbot, sample_models):
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = sample_models
        mock_service.filter_models_by_criteria.return_value = sample_models
        widget.set_search_filter_service(mock_service)
        widget.load_models()

        # シグナル監視
        selection_changed_calls = []
        count_changed_calls = []
        widget.model_selection_changed.connect(lambda names: selection_changed_calls.append(list(names)))
        widget.selection_count_changed.connect(
            lambda selected, total: count_changed_calls.append((selected, total))
        )

        # 並び順はソートに依存するため、名前で対象行を特定してチェックする
        def check_by_name(name: str) -> None:
            for r in range(widget.tableWidgetModels.rowCount()):
                name_item = widget.tableWidgetModels.item(r, 1)
                if name_item and name_item.text() == name:
                    cb = widget.tableWidgetModels.item(r, 0)
                    assert cb is not None
                    cb.setCheckState(Qt.CheckState.Checked)
                    return
            pytest.fail(f"Row with model name '{name}' not found")

        check_by_name(sample_models[0]["name"])  # gpt-4-vision-preview
        check_by_name(sample_models[1]["name"])  # claude-3-sonnet

        # 選択結果
        selected = widget.get_selected_models()
        assert len(selected) == 2
        assert sample_models[0]["name"] in selected and sample_models[1]["name"] in selected

        # シグナルが少なくとも1回は発火していること
        assert len(selection_changed_calls) >= 1
        assert count_changed_calls[-1][0] == 2
        assert count_changed_calls[-1][1] == len(sample_models)

    def test_set_selected_models_sets_checkboxes(self, widget, sample_models):
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = sample_models
        mock_service.filter_models_by_criteria.return_value = sample_models
        widget.set_search_filter_service(mock_service)
        widget.load_models()

        target = [sample_models[0]["name"], sample_models[2]["name"]]
        widget.set_selected_models(target)

        selected = widget.get_selected_models()
        assert sorted(selected) == sorted(target)

    def test_get_selection_info(self, widget, sample_models):
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = sample_models
        mock_service.filter_models_by_criteria.return_value = sample_models
        widget.set_search_filter_service(mock_service)
        widget.load_models()

        # 1件だけ選択（モデル名で対象行を特定）
        target_name = sample_models[0]["name"]
        for r in range(widget.tableWidgetModels.rowCount()):
            name_item = widget.tableWidgetModels.item(r, 1)
            if name_item and name_item.text() == target_name:
                cb = widget.tableWidgetModels.item(r, 0)
                assert cb is not None
                cb.setCheckState(Qt.CheckState.Checked)
                break
        else:
            pytest.fail(f"Row with model name '{target_name}' not found")

        info = widget.get_selection_info()
        assert info.total_available == len(sample_models)
        assert info.filtered_count == len(sample_models)
        assert info.selected_models == [sample_models[0]["name"]]

    def test_load_models_without_service(self, widget):
        # サービス未設定でも例外にならず、テーブルがクリアされる
        widget.load_models()
        assert widget.all_models == []
        assert widget.filtered_models == []
        assert widget.tableWidgetModels.rowCount() == 0

    def test_apply_filters_without_service_warns(self, widget, sample_models):
        # サービス未設定でフィルタしても落ちない
        with patch("lorairo.gui.widgets.model_selection_table_widget.logger") as mock_logger:
            widget.all_models = sample_models
            widget.filtered_models = sample_models.copy()
            widget.apply_filters(function_types=["caption"], providers=["openai"])
            mock_logger.warning.assert_called_with("SearchFilterService not available for filtering")
            # 変更なし
            assert widget.filtered_models == sample_models

    def test_item_changed_non_checkbox_column_does_not_emit(self, widget, sample_models):
        mock_service = Mock()
        mock_service.get_annotation_models_list.return_value = sample_models
        mock_service.filter_models_by_criteria.return_value = sample_models
        widget.set_search_filter_service(mock_service)
        widget.load_models()

        # 監視
        emitted = {"count": 0}
        widget.model_selection_changed.connect(lambda _: emitted.__setitem__("count", emitted["count"] + 1))

        # 列1（モデル名列）を書き換え（プログラム的）
        name_item = widget.tableWidgetModels.item(0, 1)
        old_text = name_item.text()
        name_item.setText(old_text + " ")  # itemChanged発火の可能性

        # チェックボックス列以外の変更では発火しないこと（寛容に==0で確認）
        assert emitted["count"] == 0
