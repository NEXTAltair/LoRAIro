"""LoRAIro Public API Facade層。

CLI・GUI・外部ツールから使用されるパブリック API。
既存 Service を統一的にラップし、型安全で使いやすいインターフェースを提供する。

使用例:
    >>> from lorairo.api import create_project, list_projects
    >>> from lorairo.api.types import ProjectCreateRequest
    >>>
    >>> # プロジェクト作成
    >>> project = create_project(ProjectCreateRequest(name="my_project"))
    >>>
    >>> # プロジェクト一覧
    >>> projects = list_projects()
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# エクスポート: 例外クラス（ServiceContainer非依存、即時インポート安全）
from lorairo.api.exceptions import (
    AnnotationError,
    AnnotationFailedError,
    APIKeyNotConfiguredError,
    DatabaseConnectionError,
    DatabaseError,
    DuplicateImageError,
    ExportError,
    ExportFailedError,
    ImageError,
    ImageNotFoundError,
    ImageRegistrationError,
    InvalidFormatError,
    InvalidInputError,
    InvalidPathError,
    LoRAIroException,
    ProjectAlreadyExistsError,
    ProjectError,
    ProjectNotFoundError,
    ProjectOperationError,
    TagError,
    TagNotFoundError,
    TagRegistrationError,
    ValidationError,
)

# エクスポート: データ型（ServiceContainer非依存、即時インポート安全）
from lorairo.api.types import (
    AnnotationResult,
    DuplicateInfo,
    ErrorResponse,
    ExportCriteria,
    ExportResult,
    ImageMetadata,
    ModelInfo,
    PagedResult,
    PaginationInfo,
    ProjectCreateRequest,
    ProjectInfo,
    RegistrationResult,
    StatusResponse,
    TagInfo,
    TagSearchResult,
)

if TYPE_CHECKING:
    pass

# API関数は遅延ロード（ServiceContainer依存のため循環インポート回避）
_API_FUNCTION_MODULES: dict[str, tuple[str, str]] = {
    "annotate_images": ("lorairo.api.annotations", "annotate_images"),
    "export_dataset": ("lorairo.api.export", "export_dataset"),
    "register_images": ("lorairo.api.images", "register_images"),
    "detect_duplicate_images": ("lorairo.api.images", "detect_duplicate_images"),
    "create_project": ("lorairo.api.project", "create_project"),
    "delete_project": ("lorairo.api.project", "delete_project"),
    "get_project": ("lorairo.api.project", "get_project"),
    "list_projects": ("lorairo.api.project", "list_projects"),
    "update_project": ("lorairo.api.project", "update_project"),
    "get_available_types": ("lorairo.api.tags", "get_available_types"),
    "get_unknown_tags": ("lorairo.api.tags", "get_unknown_tags"),
}


def __getattr__(name: str) -> object:
    """API関数の遅延ロード。

    ServiceContainer に依存するAPI関数はモジュール初期化時ではなく、
    実際にアクセスされた時点でインポートする（循環インポート回避）。
    """
    if name in _API_FUNCTION_MODULES:
        import importlib

        module_path, attr_name = _API_FUNCTION_MODULES[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "APIKeyNotConfiguredError",
    "AnnotationError",
    "AnnotationFailedError",
    "AnnotationResult",
    "DatabaseConnectionError",
    "DatabaseError",
    "DuplicateImageError",
    "DuplicateInfo",
    "ErrorResponse",
    "ExportCriteria",
    "ExportError",
    "ExportFailedError",
    "ExportResult",
    "ImageError",
    "ImageMetadata",
    "ImageNotFoundError",
    "ImageRegistrationError",
    "InvalidFormatError",
    "InvalidInputError",
    "InvalidPathError",
    "LoRAIroException",
    "ModelInfo",
    "PagedResult",
    "PaginationInfo",
    "ProjectAlreadyExistsError",
    "ProjectCreateRequest",
    "ProjectError",
    "ProjectInfo",
    "ProjectNotFoundError",
    "ProjectOperationError",
    "RegistrationResult",
    "StatusResponse",
    "TagError",
    "TagInfo",
    "TagNotFoundError",
    "TagRegistrationError",
    "TagSearchResult",
    "ValidationError",
    "annotate_images",
    "create_project",
    "delete_project",
    "detect_duplicate_images",
    "export_dataset",
    "get_available_types",
    "get_project",
    "get_unknown_tags",
    "list_projects",
    "register_images",
    "update_project",
]
