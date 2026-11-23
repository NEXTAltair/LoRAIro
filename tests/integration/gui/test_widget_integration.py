# tests/integration/gui/test_widget_integration.py

from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QWidget

from lorairo.gui.services.search_filter_service import SearchFilterService
from lorairo.services.model_selection_service import ModelSelectionService


@pytest.mark.gui
class TestWidgetServiceIntegration:
    """ウィジェットとサービス層の統合テスト"""

    @pytest.fixture
    def parent_widget(self, qtbot):
        """テスト用親ウィジェット"""
        widget = QWidget()
        qtbot.addWidget(widget)
        yield widget

    @pytest.fixture
    def mock_model_registry(self):
        """モック ModelRegistryServiceProtocol - Protocol-basedアーキテクチャ対応"""
        from lorairo.services.model_registry_protocol import ModelInfo

        mock = Mock()
        mock.get_available_models.return_value = [
            ModelInfo(
                name="gpt-4o",
                provider="openai",
                capabilities=["caption", "tag"],
                litellm_model_id="gpt-4o",
                requires_api_key=True,
                estimated_size_gb=None,
            ),
            ModelInfo(
                name="wd-v1-4",
                provider="local",
                capabilities=["tag"],
                litellm_model_id=None,
                requires_api_key=False,
                estimated_size_gb=2.5,
            ),
        ]
        return mock

    @pytest.fixture
    def model_service(self, mock_model_registry):
        """ModelSelectionService インスタンス - Protocol-basedアーキテクチャに更新"""
        service = ModelSelectionService(mock_model_registry)
        service.load_models()
        return service

    @pytest.fixture
    def search_service(self):
        """SearchFilterService インスタンス"""
        from unittest.mock import Mock

        mock_db_manager = Mock()
        mock_model_selection_service = Mock()
        return SearchFilterService(
            db_manager=mock_db_manager,
            model_selection_service=mock_model_selection_service,
        )

    def test_search_filter_conditions_and_preview_integration(self, search_service):
        """検索条件作成とプレビュー生成の統合テスト"""
        # 複雑な検索条件を作成
        conditions = search_service.create_search_conditions(
            search_type="tags",
            keywords=["1girl", "school uniform", "smile"],
            tag_logic="and",
            resolution_filter="1920x1080",
            aspect_ratio_filter="風景 (16:9)",
            date_filter_enabled=True,
            date_range_start=None,
            date_range_end=None,
            only_untagged=False,
            only_uncaptioned=True,
            exclude_duplicates=True,
        )

        # 検索条件確認
        assert conditions.search_type == "tags"
        assert conditions.keywords == ["1girl", "school uniform", "smile"]
        assert conditions.tag_logic == "and"
        assert conditions.only_untagged is False
        assert conditions.only_uncaptioned is True
        assert conditions.resolution_filter == "1920x1080"
        assert conditions.aspect_ratio_filter == "風景 (16:9)"
        assert conditions.exclude_duplicates is True

        # プレビュー生成
        preview = search_service.create_search_preview(conditions)
        assert "1girl" in preview
        assert "school uniform" in preview
        assert "smile" in preview
        assert "解像度: 1920x1080" in preview
        assert "風景 (16:9)" in preview
        assert "重複除外" in preview
