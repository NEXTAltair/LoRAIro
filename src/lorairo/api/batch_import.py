"""OpenAI Batch API JSONL インポートAPI。

BatchImportServiceをラップし、プロジェクト解決を含む
高レベルインポート機能を提供する。
"""

from pathlib import Path

from lorairo.api.exceptions import BatchImportError, ProjectNotFoundError
from lorairo.services.batch_import_service import BatchImportResult, BatchImportService
from lorairo.services.service_container import ServiceContainer


def import_batch_annotations(
    jsonl_dir: Path,
    project_name: str,
    *,
    dry_run: bool = False,
    model_name_override: str | None = None,
) -> BatchImportResult:
    """ディレクトリ内のOpenAI Batch API結果をプロジェクトDBにインポートする。

    Args:
        jsonl_dir: JSONLファイルが格納されたディレクトリ。
        project_name: インポート先プロジェクト名。
        dry_run: Trueの場合、DB書き込みを行わず照合結果のみ返す。
        model_name_override: モデル名を上書きする場合に指定。

    Returns:
        インポート結果。

    Raises:
        ProjectNotFoundError: プロジェクトが見つからない場合。
        BatchImportError: インポート処理に失敗した場合。
    """
    container = ServiceContainer()
    project_info = container.project_management_service.get_project(project_name)
    if project_info is None:
        raise ProjectNotFoundError(project_name)

    repository = container.image_repository
    service = BatchImportService(repository)

    try:
        return service.import_from_directory(
            jsonl_dir, dry_run=dry_run, model_name_override=model_name_override
        )
    except (FileNotFoundError, ValueError) as e:
        raise BatchImportError(str(e)) from e
