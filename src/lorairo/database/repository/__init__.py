"""Aggregate 単位 Repository (ADR 0035)。

`db_repository.py` god class を Aggregate 境界で分割した Repository 群。
段階的に entity ごとに移行する (移行戦略は ADR 0035 §6 参照)。

段階 1 (#423): `ModelRepository`
段階 2 (#423): `ProjectRepository`
段階 3 以降: `ErrorRecordRepository`, `ImageRepository`, `AnnotationRepository`
"""

from .base import BaseRepository
from .model import ModelRepository
from .project import ProjectRepository

__all__ = [
    "BaseRepository",
    "ModelRepository",
    "ProjectRepository",
]
