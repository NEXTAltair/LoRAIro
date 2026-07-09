"""Dataset export commands.

データセット エクスポート コマンド。
image_ids を受け取り、タグ txt / キャプション txt / JSON の全形式を出力する。
検索責務は ``lorairo-cli images search`` に委譲する (Issue #698)。
"""

from pathlib import Path

import typer
from rich.table import Table

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_result
from lorairo.cli._image_ids import resolve_image_ids_input
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.project import get_project as api_get_project
from lorairo.services.service_container import get_service_container

# サブコマンドアプリ定義
app = typer.Typer(help="Dataset export commands")

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()


@app.command("create")
def create(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    image_ids_csv: str | None = typer.Option(
        None,
        "--image-ids",
        help="Comma-separated image IDs to export (max 500)",
    ),
    image_ids_file: str | None = typer.Option(
        None,
        "--image-ids-file",
        help="Path to a newline/comma-separated image ID list (bulk export, Issue #1216).",
    ),
    output: str = typer.Option(
        ...,
        "--output",
        "-o",
        help="Output directory for exported dataset",
    ),
    resolution: int = typer.Option(
        512,
        "--resolution",
        "-r",
        help="Target resolution for processed images",
    ),
    tag_languages: list[str] | None = typer.Option(
        None,
        "--tag-language",
        help=(
            "Tag language to export. Use 'canonical' for existing tag output; repeat for multiple "
            "language-specific dataset directories."
        ),
    ),
) -> None:
    """Create a dataset export from a list of image IDs.

    指定した image_ids からデータセットをエクスポートします。
    タグ txt、キャプション txt、JSON の全形式を出力します。

    画像の検索には ``lorairo-cli images search`` を使用してください。

    Example:
        # まず検索で image_ids を取得

        lorairo-cli images search --project proj --json \\
          | jq -r 'select(.kind=="item")|.image_id' | paste -sd, > ids.txt

        # 取得した ids でエクスポート
        lorairo-cli export create --project proj --image-ids $(cat ids.txt) --output /tmp/out
    """
    with command_boundary():
        # API層経由でプロジェクト確認 (未存在は ProjectNotFoundError → NOT_FOUND で伝播)
        api_get_project(project)

        # image_ids パース・検証 (--image-ids / --image-ids-file 排他、Issue #1216)。
        # click.UsageError → 境界が INVALID_INPUT exit 2
        image_ids, _is_file = resolve_image_ids_input(image_ids_csv, image_ids_file)

        # ServiceContainer を取得してプロジェクト DB に切り替え
        container = get_service_container()
        container.set_active_project(project)

        export_service = container.dataset_export_service
        output_path = Path(output)
        output_path.mkdir(parents=True, exist_ok=True)

        if not is_json_mode():
            console.print(f"Exporting {len(image_ids)} image(s) to {output}")

        # タグ txt + キャプション txt
        txt_path = export_service.export_dataset_txt_format(
            image_ids, output_path, resolution, tag_languages=tag_languages
        )
        # JSON メタデータ
        export_service.export_dataset_json_format(
            image_ids, output_path, resolution, tag_languages=tag_languages
        )

        if is_json_mode():
            emit_result(
                "Export completed successfully.",
                output_path=str(txt_path),
                total_images=len(image_ids),
                resolution=resolution,
                tag_languages=tag_languages or ["canonical"],
            )
        else:
            table = Table()
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green")
            table.add_row("Total Images", str(len(image_ids)))
            table.add_row("Resolution", f"{resolution}px")
            table.add_row("Tag Languages", ", ".join(tag_languages or ["canonical"]))
            table.add_row("Output Path", str(txt_path))
            console.print(table)
            console.print("\nExport completed successfully!")
