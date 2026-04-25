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

    try:
        # フィルタ条件を ImageFilterCriteria に変換して export_with_criteria に委譲
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

        result_path = service.export_with_criteria(
            output_path=output_dir,
            format_type=criteria.format_type,
            resolution=criteria.resolution,
            criteria=filter_criteria,
        )

        # 零件マッチ時はサービス側でディレクトリを作成しない場合があるため確保する
        result_path.mkdir(parents=True, exist_ok=True)

        # エクスポート結果の集計
        file_count = sum(1 for _ in result_path.iterdir())
        total_size = sum(f.stat().st_size for f in result_path.rglob("*") if f.is_file())

        return ExportResult(
            output_path=result_path,
            file_count=file_count,
            total_size=total_size,
            format_type=criteria.format_type,
            resolution=criteria.resolution,
        )

    except Exception as e:
        raise ExportFailedError(criteria.format_type, str(e)) from e
