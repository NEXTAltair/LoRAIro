"""LoRAIro Services Package

Phase 2-4統合によるサービス層実装
"""

from .annotation_service import AnnotationService
from .annotator_lib_adapter import AnnotatorLibAdapter, MockAnnotatorLibAdapter
from .configuration_service import ConfigurationService
from .image_processing_service import ImageProcessingService
from .model_sync_service import ModelSyncService
from .service_container import ServiceContainer, get_service_container

# Phase 4: enhanced_annotation_service互換性
# テストファイルでの参照を維持するためのエイリアス
enhanced_annotation_service = annotation_service = __import__(
    __name__ + ".annotation_service", fromlist=[""]
)

__all__ = [
    "AnnotationService",
    "AnnotatorLibAdapter",
    "ConfigurationService",
    "ImageProcessingService",
    "MockAnnotatorLibAdapter",
    "ModelSyncService",
    "ServiceContainer",
    "annotation_service",
    "enhanced_annotation_service",
    "get_service_container",
]
