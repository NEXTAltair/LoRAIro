"""Aggregate 単位 Repository (ADR 0035)。

`db_repository.py` god class を Aggregate 境界で分割した Repository 群。
段階的に entity ごとに移行する (移行戦略は ADR 0035 §6 参照)。

段階 1 (#423): `ModelRepository`
段階 2 (#423): `ProjectRepository`
段階 3 (#423): `ErrorRecordRepository`
段階 4 以降: `ImageRepository`, `AnnotationRepository`
"""

from .base import BaseRepository
from .error_record import ErrorRecordRepository
from .model import ModelRepository
from .project import ProjectRepository

__all__ = [
    "BaseRepository",
    "ErrorRecordRepository",
    "ModelRepository",
    "ProjectRepository",
]
