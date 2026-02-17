"""データセットエクスポートAPI。

DatasetExportService をラップし、エクスポート機能を提供。
"""

from pathlib import Path

from lorairo.api.exceptions import ExportFailedError, InvalidFormatError
from lorairo.api.types import ExportCriteria, ExportResult
from lorairo.services.service_container import ServiceContainer


def _resolve_project_image_ids(project_name: str) -> list[int]:
    """プロジェクトの画像IDリストを解決する。

    現段階ではDBから画像IDを取得する完全な統合は未実装のため、
    プロジェクトディレクトリの画像ファイル数に基づいたダミーIDを生成する。

    Args:
        project_name: プロジェクト名。

    Returns:
        list[int]: 画像IDリスト。

    Raises:
        ProjectNotFoundError: プロジェクトが見つからない場合。
    """
    container = ServiceContainer()
    project_service = container.project_management_service
    project_info = project_service.get_project(project_name)

    # プロジェクトの画像ディレクトリをスキャン
    images_dir = project_info.path / "image_dataset" / "original_images"
    if not images_dir.exists():
        return []

    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    image_files = [
        f for f in sorted(images_dir.iterdir())
        if f.is_file() and f.suffix.lower() in image_extensions
    ]

    # FIXME: Issue #15後続 - DBからimage_idを取得する実装に置き換え
    # 現在はファイルインデックスをIDとして使用
    return list(range(len(image_files)))


def export_dataset(
    project_name: str,
    output_path: str | Path,
    criteria: ExportCriteria | None = None,
) -> ExportResult:
    """プロジェクトのデータセットをエクスポート。

    Args:
        project_name: プロジェクト名。
        output_path: 出力ディレクトリパス。
        criteria: エクスポート条件（未指定時はデフォルト）。
                 フォーマット: 'txt' or 'json'
                 解像度: 256-2048ピクセル

    Returns:
        ExportResult: エクスポート結果。

    Raises:
        InvalidFormatError: サポートされていない形式が指定。
        ExportFailedError: エクスポート実行に失敗。

    使用例:
        >>> from lorairo.api import export_dataset
        >>> from lorairo.api.types import ExportCriteria
        >>>
        >>> criteria = ExportCriteria(
        ...     format_type="txt",
        ...     resolution=512,
        ... )
        >>> result = export_dataset("my_project", "/tmp/export", criteria)
        >>> print(f"エクスポート完了: {result.file_count}ファイル")
    """
    # クライテリア初期化
    if criteria is None:
        criteria = ExportCriteria()

    # フォーマット検証
    supported_formats = ["txt", "json"]
    if criteria.format_type not in supported_formats:
        raise InvalidFormatError(
            criteria.format_type, supported_formats
        )

    output_dir = Path(output_path) if isinstance(output_path, str) else output_path

    container = ServiceContainer()
    service = container.dataset_export_service

    try:
        # プロジェクトから画像IDを解決
        image_ids = _resolve_project_image_ids(project_name)

        # 形式に応じたエクスポート実行
        if criteria.format_type == "txt":
            result_path = service.export_dataset_txt_format(
                image_ids=image_ids,
                output_path=output_dir,
                resolution=criteria.resolution,
            )
        elif criteria.format_type == "json":
            result_path = service.export_dataset_json_format(
                image_ids=image_ids,
                output_path=output_dir,
                resolution=criteria.resolution,
            )
        else:
            raise ValueError(f"未知の形式: {criteria.format_type}")

        # エクスポート結果の集計
        file_count = sum(1 for _ in result_path.iterdir()) if result_path.exists() else 0
        total_size = (
            sum(f.stat().st_size for f in result_path.rglob("*") if f.is_file())
            if result_path.exists()
            else 0
        )

        return ExportResult(
            output_path=result_path,
            file_count=file_count,
            total_size=total_size,
            format_type=criteria.format_type,
            resolution=criteria.resolution,
        )

    except Exception as e:
        raise ExportFailedError(criteria.format_type, str(e)) from e
