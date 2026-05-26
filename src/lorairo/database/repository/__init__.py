"""Aggregate 単位 Repository (ADR 0035)。

`db_repository.py` god class を Aggregate 境界で分割した Repository 群。
段階的に entity ごとに移行する (移行戦略は ADR 0035 §6 参照)。

段階 1 (#423): `ModelRepository`
段階 2 (#423): `ProjectRepository`
段階 3 (#423): `ErrorRecordRepository`
段階 4 (#423): `ImageRepository`
段階 5 (#423): `AnnotationRepository` (annotation_record.py)
段階 6 (予定): legacy `db_repository.ImageRepository` facade を撤廃し、
              全 call site を `manager.image_repo` / `manager.annotation_repo` 等の
              直接参照に migration する。
"""

from .annotation_record import AnnotationRepository
from .base import BaseRepository
from .error_record import ErrorRecordRepository
from .image import ImageRepository
from .model import ModelRepository
from .project import ProjectRepository

__all__ = [
    "AnnotationRepository",
    "BaseRepository",
    "ErrorRecordRepository",
    "ImageRepository",
    "ModelRepository",
    "ProjectRepository",
]
