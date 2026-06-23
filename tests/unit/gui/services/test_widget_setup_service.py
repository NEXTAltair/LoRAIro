"""WidgetSetupService の単体テスト"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from lorairo.gui.services.widget_setup_service import WidgetSetupService

# NOTE: AnnotationFilter → ModelSelection 変換 / batch model 選択の env combo 抑制は
# #868 で AnnotateTabWidget へ移送された。該当テストは
# tests/unit/gui/tab/test_annotate_tab.py::TestFilterToModelDelegation を参照。


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
