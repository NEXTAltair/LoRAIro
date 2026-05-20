"""WidgetSetupService の単体テスト"""

from __future__ import annotations

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
            "exclude_local": True,
        }

    def test_local_environment_keeps_empty_capabilities(self) -> None:
        """ローカル環境のみ指定時、空capabilitiesは全件表示として保持する"""
        filters = WidgetSetupService._build_model_selection_filters(
            {"capabilities": [], "environment": "local"}
        )

        assert filters == {
            "provider": "local",
            "capabilities": [],
            "exclude_local": False,
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
        }

    def test_missing_capabilities_defaults_to_empty_list(self) -> None:
        """capabilitiesキー欠落時も絞り込みなしとして扱う"""
        filters = WidgetSetupService._build_model_selection_filters({"environment": None})

        assert filters == {
            "provider": None,
            "capabilities": [],
            "exclude_local": False,
        }
