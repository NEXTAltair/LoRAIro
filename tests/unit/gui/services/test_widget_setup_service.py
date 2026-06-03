"""WidgetSetupService の単体テスト"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from lorairo.gui.services.widget_setup_service import WidgetSetupService


class TestWidgetSetupServiceModelSelectionFilters:
    """AnnotationFilterWidget から ModelSelectionWidget へのフィルター変換テスト"""

    def test_api_environment_keeps_empty_capabilities(self) -> None:
        """API環境のみ指定時、空capabilitiesは全件表示として保持する"""
        filters = WidgetSetupService._build_model_selection_filters(
            {"capabilities": [], "environment": "api"}
        )

        assert filters == {
            "provider": None,
            "capabilities": [],
            "exclude_local": False,
            "execution_env": "APIモデルのみ",
            "annotation_only": True,
        }

    def test_local_environment_keeps_empty_capabilities(self) -> None:
        """ローカル環境のみ指定時、空capabilitiesは全件表示として保持する"""
        filters = WidgetSetupService._build_model_selection_filters(
            {"capabilities": [], "environment": "local"}
        )

        assert filters == {
            "provider": None,
            "capabilities": [],
            "exclude_local": False,
            "execution_env": "ローカルモデルのみ",
            "annotation_only": True,
        }

    def test_capabilities_are_not_replaced_with_defaults(self) -> None:
        """選択済みcapabilitiesは接続側でデフォルト上書きしない"""
        filters = WidgetSetupService._build_model_selection_filters(
            {"capabilities": ["caption"], "environment": None}
        )

        assert filters == {
            "provider": None,
            "capabilities": ["caption"],
            "exclude_local": False,
            "execution_env": None,
            "annotation_only": True,
        }

    def test_missing_capabilities_defaults_to_empty_list(self) -> None:
        """capabilitiesキー欠落時も絞り込みなしとして扱う"""
        filters = WidgetSetupService._build_model_selection_filters({"environment": None})

        assert filters == {
            "provider": None,
            "capabilities": [],
            "exclude_local": False,
            "execution_env": None,
            "annotation_only": True,
        }

    def test_batch_model_selection_hides_internal_execution_env_combo(self) -> None:
        """Batch annotationではModelSelectionWidget側の環境Comboを操作面にしない"""
        model_widget = Mock()

        WidgetSetupService._configure_batch_model_selection_widget(model_widget)

        model_widget.executionEnvCombo.setVisible.assert_called_once_with(False)
        model_widget.set_annotation_only_filtering.assert_called_once_with(True)


class TestWidgetSetupServiceSelectedImageDetails:
    """SelectedImageDetailsWidget setup integration tests."""

    def test_setup_selected_image_details_initializes_reader_for_gui(self, monkeypatch) -> None:
        """GUI setup は lazy accessor 経由で MergedTagReader を注入する。"""
        reader = Mock()
        annotation_repo = Mock()
        annotation_repo.merged_reader = None
        annotation_repo.get_merged_reader.return_value = reader
        service_container = SimpleNamespace(
            db_manager=SimpleNamespace(annotation_repo=annotation_repo),
        )

        monkeypatch.setattr("lorairo.services.get_service_container", lambda: service_container)

        widget = Mock()
        main_window = SimpleNamespace(selectedImageDetailsWidget=widget)
        dataset_state_manager = Mock()

        WidgetSetupService.setup_selected_image_details(main_window, dataset_state_manager)

        assert main_window.selected_image_details_widget is widget
        widget.connect_to_dataset_state_manager.assert_called_once_with(dataset_state_manager)
        annotation_repo.get_merged_reader.assert_called_once_with()
        widget.set_merged_reader.assert_called_once_with(reader)
