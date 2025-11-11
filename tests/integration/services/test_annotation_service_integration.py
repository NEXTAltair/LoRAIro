"""AnnotationService統合テスト

ServiceContainer実態との統合動作を検証
"""

import pytest

from lorairo.services.annotation_service import AnnotationService


@pytest.mark.integration
class TestAnnotationServiceIntegration:
    """AnnotationService統合テスト"""

    def test_service_initialization_with_container(self):
        """ServiceContainerとの統合初期化テスト"""
        service = AnnotationService()

        assert service.container is not None
        assert hasattr(service, "annotationFinished")
        assert hasattr(service, "annotationError")
        assert hasattr(service, "modelSyncCompleted")

    def test_get_service_status_integration(self):
        """サービス状況取得の統合テスト"""
        service = AnnotationService()

        status = service.get_service_status()

        assert "service_name" in status
        assert "phase" in status
        assert "container_summary" in status
        assert "last_results" in status
