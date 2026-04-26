"""Annotation commands.

アノテーション実行コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from PIL import Image
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

if TYPE_CHECKING:
    from lorairo.services.batch_import_service import BatchImportResult

from lorairo.api.batch_import import import_batch_annotations
from lorairo.api.exceptions import (
    AnnotationFailedError,
    APIKeyNotConfiguredError,
    BatchImportError,
    ProjectNotFoundError,
)
from lorairo.api.project import get_project as api_get_project
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Annotation commands")

# Rich console（出力用）
console = Console()


def _load_images_from_db(
    image_records: list[dict[str, Any]],
) -> tuple[list[Image.Image], dict[str, int], int, int]:
    """DB の画像レコードから PIL 画像をロード。

    Args:
        image_records: ImageRepository.get_images_by_filter() が返すレコードリスト

    Returns:
        tuple: (PIL画像リスト, phash→image_id辞書, ロード成功数, ロード失敗数)
               phash→image_id は issue #168 (アノテーション結果の DB 保存) で利用する。
    """
    from lorairo.database.db_core import resolve_stored_path

    pil_images: list[Image.Image] = []
    phash_to_image_id: dict[str, int] = {}
    loaded_count = 0
    failed_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("画像ロード中...", total=len(image_records))

        for record in image_records:
            image_id: int | None = record.get("id")
            phash: str = record.get("phash", "")
            stored_path_str: str | None = record.get("stored_image_path")

            if not stored_path_str:
                failed_count += 1
                progress.advance(task)
                continue

            image_path = resolve_stored_path(stored_path_str)

            try:
                img = Image.open(image_path)
                img.load()
                pil_images.append(img)
                if image_id is not None and phash:
                    phash_to_image_id[phash] = image_id
                loaded_count += 1
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Failed to load {image_path.name}: {e}")
                failed_count += 1
            progress.advance(task)

    return pil_images, phash_to_image_id, loaded_count, failed_count


def _check_annotation_errors(
    results: Any,
) -> tuple[bool, set[str]]:
    """アノテーション結果のエラーを検出する。

    Args:
        results: PHashAnnotationResults ({phash: {model_name: UnifiedAnnotationResult}})

    Returns:
        tuple: (成功結果あり, エラーが発生したモデル名の集合)
    """
    error_detected_models: set[str] = set()
    success_detected = False

    for model_results in results.values():
        for m_name, m_result in model_results.items():
            if getattr(m_result, "error", None) is not None:
                error_detected_models.add(m_name)
            else:
                success_detected = True

    return success_detected, error_detected_models


def _handle_annotation_results(results: Any) -> None:
    """アノテーション結果を検証し、全モデルが失敗した場合は typer.Exit(code=1) を発生させる。

    Args:
        results: PHashAnnotationResults ({phash: {model_name: UnifiedAnnotationResult}})

    Raises:
        typer.Exit: 結果が空またはすべてのモデルが失敗した場合 (code=1)。
    """
    if not results:
        console.print("[red]Error:[/red] Annotation produced no results")
        raise typer.Exit(code=1)

    success_detected, error_detected_models = _check_annotation_errors(results)

    if not success_detected and error_detected_models:
        console.print(
            f"[red]Error:[/red] All annotation models failed: {', '.join(sorted(error_detected_models))}"
        )
        raise typer.Exit(code=1)
    elif error_detected_models:
        console.print(
            f"[yellow]Warning:[/yellow] Some models encountered errors: "
            f"{', '.join(sorted(error_detected_models))}"
        )


@app.command("run")
def run(
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Project name",
    ),
    model: list[str] = typer.Option(
        ...,
        "--model",
        "-m",
        help="Model name(s) to use for annotation",
    ),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for annotation results (optional)",
    ),
    batch_size: int = typer.Option(
        10,
        "--batch-size",
        "-b",
        help="Batch size for processing",
    ),
) -> None:
    """Run annotation on project images.

    プロジェクトの画像に対してアノテーションを実行します。
    """
    try:
        # API層経由でプロジェクト確認 & DB 接続切り替え
        try:
            api_get_project(project)
        except ProjectNotFoundError as e:
            console.print(f"[red]Error:[/red] Project not found: {project}")
            raise typer.Exit(code=1) from e

        container = get_service_container()
        container.set_active_project(project)

        # DB からプロジェクトの登録済み画像を取得
        repository = container.image_repository
        criteria = ImageFilterCriteria(include_nsfw=True)
        image_records, total_in_db = repository.get_images_by_filter(criteria)

        if not image_records:
            console.print(
                f"[red]Error:[/red] No registered images found in project '{project}'. "
                "Run 'lorairo-cli images register' first."
            )
            raise typer.Exit(code=1)

        # DB レコードから PIL 画像をロード
        pil_images, _phash_to_image_id, loaded_count, failed_count = _load_images_from_db(image_records)

        if not pil_images:
            console.print("[red]Error:[/red] No images could be loaded for annotation")
            raise typer.Exit(code=1)

        console.print(f"[cyan]Found {total_in_db} image(s) in DB[/cyan]")
        console.print(f"[cyan]Using model(s): {', '.join(model)}[/cyan]")
        console.print(f"[green]Loaded {loaded_count} image(s) ({failed_count} failed)[/green]")

        annotator = container.annotator_library
        config = container.config_service

        # APIキー確認
        api_keys = {
            "openai": config.get_setting("api", "openai_key", ""),
            "anthropic": config.get_setting("api", "claude_key", ""),
            "google": config.get_setting("api", "google_key", ""),
        }
        api_keys = {k: v for k, v in api_keys.items() if v and v.strip()}

        if not api_keys:
            console.print(
                "[yellow]Warning:[/yellow] No API keys configured. "
                "Consider setting API keys in config/lorairo.toml"
            )

        # アノテーション実行
        console.print("[cyan]Starting annotation...[/cyan]")

        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("アノテーション実行中...", total=len(pil_images))

                results = annotator.annotate(pil_images, model)

                progress.update(task, completed=len(pil_images))

        except Exception as e:
            console.print(f"[red]Error:[/red] Annotation failed: {e}")
            logger.error(f"Annotation error: {e}", exc_info=True)
            raise typer.Exit(code=1) from e

        # モデルエラーを検出（全失敗時は Exit(code=1)、部分失敗時は Warning 表示）
        _handle_annotation_results(results)

        # 結果サマリー表示
        console.print("\n[bold cyan]Annotation Summary[/bold cyan]")

        summary_table = Table()
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Images", str(len(pil_images)))
        summary_table.add_row("Models Used", ", ".join(model))
        summary_table.add_row("Results", str(len(results)))

        console.print(summary_table)

        console.print("\n[green]Annotation completed successfully![/green]")

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Command error: {e}", exc_info=True)
        raise typer.Exit(code=2) from e


def _display_batch_import_result(result: BatchImportResult, *, dry_run: bool) -> None:
    """バッチインポート結果をRichテーブルで表示する。

    Args:
        result: インポート結果。
        dry_run: dry-runモードかどうか。
    """
    summary_table = Table(title="Batch Import Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total Records", str(result.total_records))
    summary_table.add_row("Parsed OK", str(result.parsed_ok))
    summary_table.add_row("Parse Errors", str(result.parse_errors))
    summary_table.add_row("Matched", str(result.matched))
    summary_table.add_row("Unmatched", str(result.unmatched))
    summary_table.add_row("Saved", str(result.saved))
    summary_table.add_row("Save Errors", str(result.save_errors))
    summary_table.add_row("Model", result.model_name)
    summary_table.add_row("Mode", "[yellow]DRY-RUN[/yellow]" if dry_run else "LIVE")

    console.print(summary_table)

    # アンマッチ一覧（10件まで表示）
    if result.unmatched_ids:
        from lorairo.services.batch_image_matcher import BatchImageMatcher

        console.print(
            f"\n[yellow]照合失敗 ({len(result.unmatched_ids)}件) "
            f"- custom_idから抽出したファイル名がDBに未登録:[/yellow]"
        )
        for uid in result.unmatched_ids[:10]:
            stem = BatchImageMatcher.extract_stem(uid)
            console.print(f"  - [bold]{stem}[/bold]  ← {uid}")
        if len(result.unmatched_ids) > 10:
            console.print(f"  ... 他 {len(result.unmatched_ids) - 10} 件")

    # エラー詳細（5件まで表示）
    if result.error_details:
        console.print(f"\n[red]Errors ({len(result.error_details)}件):[/red]")
        for detail in result.error_details[:5]:
            console.print(f"  - {detail}")
        if len(result.error_details) > 5:
            console.print(f"  ... 他 {len(result.error_details) - 5} 件")

    if not dry_run and result.saved > 0:
        console.print(f"\n[green]インポート完了: {result.saved}件保存しました[/green]")


@app.command("import-batch")
def import_batch(
    jsonl_dir: Path = typer.Argument(
        ...,
        help="OpenAI Batch API結果のJSONLファイルが格納されたディレクトリ",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="インポート先プロジェクト名",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="DB書き込みを行わず照合結果のみ表示",
    ),
    model_name: str | None = typer.Option(
        None,
        "--model-name",
        help="モデル名を上書き（JSONL内のmodel名を無視）",
    ),
) -> None:
    """OpenAI Batch API結果JSONLを一括インポートする。

    ディレクトリ内の全JSONLファイルを読み込み、
    custom_idとDB登録済み画像のファイル名を照合して
    アノテーション結果をインポートします。

    使用例:
        lorairo annotate import-batch jsonl/ -p main_dataset_20250707_001
        lorairo annotate import-batch jsonl/ -p my_project --dry-run
    """
    try:
        get_service_container().set_active_project(project)
        result = import_batch_annotations(
            jsonl_dir,
            project,
            dry_run=dry_run,
            model_name_override=model_name,
        )
        _display_batch_import_result(result, dry_run=dry_run)

    except ProjectNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except BatchImportError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from e
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        logger.error(f"Batch import error: {e}", exc_info=True)
        raise typer.Exit(code=2) from e
