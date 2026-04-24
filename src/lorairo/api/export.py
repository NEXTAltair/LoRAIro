"""データセットエクスポートAPI。

DatasetExportService をラップし、エクスポート機能を提供。
"""

from pathlib import Path

from lorairo.api.exceptions import (
    DatabaseConnectionError,
    ExportFailedError,
    InvalidFormatError,
    InvalidInputError,
)
from lorairo.api.types import ExportCriteria, ExportResult
from lorairo.database.db_core import get_current_project_root
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.service_container import ServiceContainer

# NOTE: LoRAIro は db_core.py でデータベースをグローバルに初期化する。
# project_name は存在確認に使うだけでは、config/lorairo.toml が別プロジェクトを
# 指している場合に全く別プロジェクトの画像を取り出してしまう。
# そのため get_current_project_root() と project_info.path を比較し、
# ミスマッチ時は明示的にエラーにする。


def export_dataset(
    project_name: str,
    output_path: str | Path,
    criteria: ExportCriteria | None = None,
) -> ExportResult:
    """プロジェクトのデータセットをエクスポート。

    Args:
        project_name: プロジェクト名。
        output_path: 出力ディレクトリパス。
        criteria: エクスポート条件。フィルタ条件（tag_filter, caption,
                 manual_rating, ai_rating, score_min, score_max のいずれか）を
                 必ず1つ以上指定すること。

    Returns:
        ExportResult: エクスポート結果。

    Raises:
        InvalidInputError: フィルタ条件が指定されていない場合。
        InvalidFormatError: サポートされていない形式が指定。
        DatabaseConnectionError: 現在接続中のDBと project_name が指すプロジェクトが異なる場合。
        ExportFailedError: エクスポート実行に失敗。

    使用例:
        >>> from lorairo.api import export_dataset
        >>> from lorairo.api.types import ExportCriteria
        >>>
        >>> criteria = ExportCriteria(
        ...     format_type="txt",
        ...     resolution=512,
        ...     tag_filter=["cat"],
        ... )
        >>> result = export_dataset("my_project", "/tmp/export", criteria)
        >>> print(f"エクスポート完了: {result.file_count}ファイル")
    """
    # プロジェクト存在確認
    container = ServiceContainer()
    project_info = container.project_management_service.get_project(project_name)

    # DB接続先とプロジェクト整合性チェック
    # LoRAIro は db_core.py でDBをグローバル初期化するため、project_name だけでは
    # クエリがスコープされない。config/lorairo.toml が別プロジェクトを指していると
    # 別プロジェクトの画像が返る事故になるので、明示的にミスマッチを検知する。
    current_db_root = get_current_project_root().resolve()
    requested_root = project_info.path.resolve()
    if current_db_root != requested_root:
        raise DatabaseConnectionError(
            project_name,
            f"DB接続先が要求プロジェクトと異なります "
            f"(要求: {requested_root}, 接続中: {current_db_root})。"
            f" config/lorairo.toml の database_dir を確認してください",
        )

    # クライテリア初期化
    if criteria is None:
        criteria = ExportCriteria()

    # フィルタ条件バリデーション
    if not criteria.has_any_filter():
        raise InvalidInputError(
            "criteria",
            "エクスポートには最低1つのフィルタ条件が必要です"
            " (tag_filter, caption, manual_rating, ai_rating, score_min, score_max のいずれか)",
        )

    # フォーマット検証
    supported_formats = ["txt", "json"]
    if criteria.format_type not in supported_formats:
        raise InvalidFormatError(criteria.format_type, supported_formats)

    output_dir = Path(output_path) if isinstance(output_path, str) else output_path

    service = container.dataset_export_service
    repository = container.image_repository

    try:
        # フィルタ条件を ImageFilterCriteria に変換してDBから画像IDを取得
        filter_criteria = ImageFilterCriteria(
            project_name=project_name,
            tags=criteria.tag_filter,
            excluded_tags=criteria.excluded_tags,
            caption=criteria.caption,
            manual_rating_filter=criteria.manual_rating,
            ai_rating_filter=criteria.ai_rating,
            include_nsfw=criteria.include_nsfw,
            score_min=criteria.score_min,
            score_max=criteria.score_max,
        )
        all_images, _ = repository.get_images_by_filter(filter_criteria)
        image_ids = [img["id"] for img in all_images] if all_images else []

        # フィルタ結果が 0 件は正常系（実行エラーではない）
        # DatasetExportService は空リストを ValueError で拒否するため事前に分岐する
        if not image_ids:
            output_dir.mkdir(parents=True, exist_ok=True)
            return ExportResult(
                output_path=output_dir,
                file_count=0,
                total_size=0,
                format_type=criteria.format_type,
                resolution=criteria.resolution,
            )

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
