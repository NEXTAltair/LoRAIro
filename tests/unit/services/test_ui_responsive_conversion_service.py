"""UIResponsiveConversionService のユニットテスト

getparent() バグ（lxml専用APIを標準xml.etree.ElementTreeで呼び出していた）の
リグレッション防止テスト。
"""

import xml.etree.ElementTree as ET
from unittest.mock import Mock

import pytest

from lorairo.services.ui_responsive_conversion_service import UIResponsiveConversionService


@pytest.mark.unit
class TestCalculateLayoutNestingLevel:
    """_calculate_layout_nesting_level のリグレッションテスト"""

    @pytest.fixture
    def service(self) -> UIResponsiveConversionService:
        """ConfigurationService をモックしたサービスインスタンス"""
        return UIResponsiveConversionService(Mock())

    def test_nesting_level_zero_for_root_direct_child(self, service: UIResponsiveConversionService) -> None:
        """root直下のレイアウトはネストレベル0を返す"""
        root = ET.fromstring("<ui><qhboxlayout/></ui>")
        layout = root.find("qhboxlayout")
        assert layout is not None

        result = service._calculate_layout_nesting_level(layout, root)

        assert result == 0

    def test_nesting_level_two_for_doubly_nested_layout(
        self, service: UIResponsiveConversionService
    ) -> None:
        """2段ネストのレイアウトはネストレベル2を返す"""
        root = ET.fromstring(
            "<ui><qvboxlayout><qhboxlayout><qgridlayout/></qhboxlayout></qvboxlayout></ui>"
        )
        inner_layout = root.find(".//qgridlayout")
        assert inner_layout is not None

        result = service._calculate_layout_nesting_level(inner_layout, root)

        assert result == 2
