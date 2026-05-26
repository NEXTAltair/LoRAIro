"""Aggregate 単位 Repository (ADR 0035)。

`db_repository.py` god class を Aggregate 境界で分割した Repository 群。
段階 6 (#423) で legacy facade (`db_repository.ImageRepository`) を撤廃し、
全 call site は `manager.X_repo` 直接参照に移行済。

段階 1 (#423): `ModelRepository`
段階 2 (#423): `ProjectRepository`
段階 3 (#423): `ErrorRecordRepository`
段階 4 (#423): `ImageRepository`
段階 5 (#423): `AnnotationRepository` (annotation_record.py)
段階 6 (#423): `ProviderBatchRepository` + legacy facade 撤廃
"""

from .annotation_record import AnnotationRepository
from .base import BaseRepository
from .error_record import ErrorRecordRepository
from .image import ImageRepository
from .model import ModelRepository
from .project import ProjectRepository
from .provider_batch import ProviderBatchRepository

__all__ = [
    "AnnotationRepository",
    "BaseRepository",
    "ErrorRecordRepository",
    "ImageRepository",
    "ModelRepository",
    "ProjectRepository",
    "ProviderBatchRepository",
]
