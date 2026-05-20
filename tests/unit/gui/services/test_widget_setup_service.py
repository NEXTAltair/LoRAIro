"""WidgetSetupService の単体テスト"""

from __future__ import annotations

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
        }

    def test_missing_capabilities_defaults_to_empty_list(self) -> None:
        """capabilitiesキー欠落時も絞り込みなしとして扱う"""
        filters = WidgetSetupService._build_model_selection_filters({"environment": None})

        assert filters == {
            "provider": None,
            "capabilities": [],
            "exclude_local": False,
            "execution_env": None,
        }

    def test_batch_model_selection_hides_internal_execution_env_combo(self) -> None:
        """Batch annotationではModelSelectionWidget側の環境Comboを操作面にしない"""
        model_widget = Mock()

        WidgetSetupService._configure_batch_model_selection_widget(model_widget)

        model_widget.executionEnvCombo.setVisible.assert_called_once_with(False)
