"""プロジェクト管理API。

ProjectManagementService をラップし、統一的なインターフェースを提供。
"""

from lorairo.api.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
)
from lorairo.api.types import ProjectCreateRequest, ProjectInfo
from lorairo.services.service_container import ServiceContainer


def create_project(request: ProjectCreateRequest) -> ProjectInfo:
    """プロジェクトを作成。

    Args:
        request: プロジェクト作成リクエスト。

    Returns:
        ProjectInfo: 作成されたプロジェクト情報。

    Raises:
        ProjectAlreadyExistsError: 同名プロジェクトが既に存在。
        ProjectOperationError: プロジェクト作成に失敗。
    """
    container = ServiceContainer()
    service = container.project_management_service
    return service.create_project(request.name, request.description or "")


def list_projects() -> list[ProjectInfo]:
    """プロジェクト一覧を取得。

    Returns:
        list[ProjectInfo]: プロジェクト情報のリスト。
    """
    container = ServiceContainer()
    service = container.project_management_service
    return service.list_projects()


def get_project(name: str) -> ProjectInfo:
    """プロジェクト情報を取得。

    Args:
        name: プロジェクト名。

    Returns:
        ProjectInfo: プロジェクト情報。

    Raises:
        ProjectNotFoundError: プロジェクトが見つからない。
    """
    container = ServiceContainer()
    service = container.project_management_service
    return service.get_project(name)


def delete_project(name: str) -> None:
    """プロジェクトを削除。

    警告: この操作は取り消せません。

    Args:
        name: プロジェクト名。

    Raises:
        ProjectNotFoundError: プロジェクトが見つからない。
        ProjectOperationError: 削除に失敗。
    """
    container = ServiceContainer()
    service = container.project_management_service
    service.delete_project(name)


def update_project(name: str, description: str) -> ProjectInfo:
    """プロジェクト情報を更新。

    Args:
        name: プロジェクト名。
        description: 新しい説明文。

    Returns:
        ProjectInfo: 更新されたプロジェクト情報。

    Raises:
        ProjectNotFoundError: プロジェクトが見つからない。
        ProjectOperationError: 更新に失敗。
    """
    container = ServiceContainer()
    service = container.project_management_service
    return service.update_project(name, description)
