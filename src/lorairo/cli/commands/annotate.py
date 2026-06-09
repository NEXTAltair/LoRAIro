"""Annotation commands.

アノテーション実行コマンド。
API層（lorairo.api）を経由してService層を利用する。
"""

from __future__ import annotations

import errno
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import typer
from PIL import Image
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

if TYPE_CHECKING:
    from lorairo.database.repository.model import ModelRepository
    from lorairo.services.batch_import_service import BatchImportResult

from lorairo.api.batch_import import import_batch_annotations
from lorairo.api.exceptions import (
    AnnotationFailedError,
    ResultSetTooLargeError,
)
from lorairo.api.project import get_project as api_get_project
from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._image_guard import reject_original_image_records
from lorairo.cli._output_mode import is_json_mode
from lorairo.database.db_core import resolve_stored_path
from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.services.model_registry_protocol import selection_includes_webapi_model
from lorairo.services.model_route_service import validate_api_keys_for_models
from lorairo.services.moderation_preflight_service import (
    ModerationPreflightService,
    build_annotation_logic_runner,
)
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

# サブコマンドアプリ定義
app = typer.Typer(help="Annotation commands")

# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()
console_err = make_console(stderr=True)

MAX_ANNOTATE_IMAGES = 500


class LoadFailureAction(Enum):
    """画像ロード失敗時の対応方針 (Issue #537)。"""

    SKIP = "skip"  # 破損/欠損ファイル → warning して継続
    FATAL = "fatal"  # MemoryError / ENOMEM → 致命


class ImageLoadMemoryError(RuntimeError):
    """メモリ/リソース枯渇による致命的ロード失敗 (Issue #537)。"""


class AnnotationSelectionError(RuntimeError):
    """No images can be selected for annotation."""


class AnnotationRunFailedError(RuntimeError):
    """Annotation run finished without usable results."""


def _classify_load_failure(exc: BaseException) -> LoadFailureAction:
    """画像ロード時の例外を SKIP / FATAL に分類する (Issue #537)。

    メモリ・リソース枯渇 (``MemoryError`` / ``errno.ENOMEM`` 相当の ``OSError``) は
    継続不能な致命的失敗として ``FATAL`` に、破損ファイルや読み込み失敗などの
    個別エラーは ``SKIP`` に分類する。

    Args:
        exc: ロード処理で捕捉した例外。

    Returns:
        LoadFailureAction: ``FATAL`` (致命) または ``SKIP`` (継続可能)。
    """
    if isinstance(exc, MemoryError):
        return LoadFailureAction.FATAL
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.ENOMEM:
        return LoadFailureAction.FATAL
    return LoadFailureAction.SKIP


def _iter_record_batches(records: list[dict[str, Any]], batch_size: int) -> Iterator[list[dict[str, Any]]]:
    """画像レコードを ``batch_size`` 単位の chunk に分割する (Issue #536)。

    ``batch_size <= 0`` の場合は全件を 1 チャンクとして扱う。空入力は何も
    yield しない。

    Args:
        records: 処理対象の画像レコードリスト。
        batch_size: 1 チャンクあたりのレコード数。0 以下なら全件 1 チャンク。

    Yields:
        list[dict[str, Any]]: ``batch_size`` 件以下のレコード chunk。
    """
    if not records:
        return
    if batch_size <= 0:
        yield records
        return
    for start in range(0, len(records), batch_size):
        yield records[start : start + batch_size]


def _load_batch_images(
    records_chunk: list[dict[str, Any]],
) -> tuple[list[Image.Image], int, int]:
    """1 チャンク分の画像のみ open/load する (Issue #536 / #537)。

    各レコードについて ``stored_image_path`` を解決し ``Image.open`` →
    ``img.load()`` で実体をメモリに展開する。例外は ``_classify_load_failure``
    で分岐する:

    - ``FATAL`` (メモリ/リソース枯渇): 既にロード済みの画像を close してから
      ``ImageLoadMemoryError`` を raise し、呼び出し元で致命扱いさせる。
    - ``SKIP`` (破損/欠損など): warning を表示し ``failed_count`` を加算して継続。

    ``stored_image_path`` が無いレコードは ``failed_count`` を加算して skip する。

    Args:
        records_chunk: ``_iter_record_batches`` が返す 1 チャンク分のレコード。

    Returns:
        tuple: (ロード済み PIL 画像リスト, ロード成功レコードリスト, ロード成功数, ロード失敗数)。
            images[i] と loaded_records[i] は同じ画像を指す (phash_list 構築用)。

    Raises:
        ImageLoadMemoryError: メモリ/リソース枯渇による致命的ロード失敗時。
    """
    from lorairo.database.db_core import resolve_stored_path

    pil_images: list[Image.Image] = []
    loaded_records: list[dict[str, Any]] = []
    loaded_count = 0
    failed_count = 0

    for record in records_chunk:
        stored_path_str: str | None = record.get("stored_image_path")

        if not stored_path_str:
            failed_count += 1
            continue

        image_path = resolve_stored_path(stored_path_str)

        try:
            img = Image.open(image_path)
            img.load()
        except Exception as exc:
            # per-image 例外は分類のため広く捕捉し、FATAL は再 raise、SKIP は継続する。
            action = _classify_load_failure(exc)
            if action is LoadFailureAction.FATAL:
                for opened in pil_images:
                    opened.close()
                logger.error(f"Fatal image load failure on {image_path.name}: {exc}", exc_info=True)
                raise ImageLoadMemoryError(
                    f"Memory/resource exhaustion while loading {image_path.name}: {exc}"
                ) from exc
            _status_console().print(f"[yellow]Warning:[/yellow] Failed to load {image_path.name}: {exc}")
            failed_count += 1
            continue

        pil_images.append(img)
        loaded_records.append(record)
        loaded_count += 1

    return pil_images, loaded_records, loaded_count, failed_count


def _select_image_records(
    image_records: list[dict[str, Any]],
    *,
    limit: int | None,
    offset: int,
    image_ids: list[int] | None,
) -> list[dict[str, Any]]:
    """フィルタ済み画像レコードに image-id 選択 → offset → limit を順に適用する。

    適用順序は image-id フィルタ → id 昇順ソート → offset → limit で固定。
    offset/limit による sharding を決定的にするため、slice 前に必ず id 昇順で
    安定ソートする（DB クエリは ORDER BY を持たず行順が不安定なため）。

    Args:
        image_records: get_images_by_filter() が返すレコードリスト。各 record は
            "id" キー (int) を持つ。
        limit: 返す最大件数。None なら無制限。
        offset: 先頭から skip する件数（id 昇順での skip 件数）。
        image_ids: 指定時、その ID を持つレコードのみ対象。要求 ID のうち未存在の
            ものは warning を表示。空/None なら全件対象。

    Returns:
        選択後のレコードリスト（空になり得る。空時の Exit 判定は呼び出し側 run() が行う）。
    """
    records = image_records

    if image_ids:
        wanted = set(image_ids)
        records = [record for record in records if record.get("id") in wanted]

        # 要求 ID の重複除去・順序保持 (dict.fromkeys) のうち未存在のものを列挙警告
        found_ids = {record.get("id") for record in records}
        missing_ids = [image_id for image_id in dict.fromkeys(image_ids) if image_id not in found_ids]
        if missing_ids:
            missing_str = ", ".join(str(image_id) for image_id in missing_ids)
            _status_console().print(
                f"[yellow]Warning:[/yellow] Image ID(s) not found in project: {missing_str}"
            )

    # sharding 決定性: get_images_by_filter() の SQL は ORDER BY を持たず
    # (ImageRepository._build_image_filter_query は distinct() のみ)、行順は
    # クエリプラン依存で不安定。offset/limit を安定させるため id 昇順で並べてから
    # slice する (Codex review #542: shards can overlap/skip without stable order)。
    records = sorted(records, key=lambda record: record.get("id") or 0)

    # offset が 0 や範囲外でも安全に slice
    records = records[offset:]

    if limit is not None:
        records = records[:limit]

    return records


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


def _status_console() -> Any:
    """Return stderr console in JSON mode so stdout stays JSONL-only."""
    return console_err if is_json_mode() else console


@dataclass
class _StreamAnnotateSummary:
    """ストリーミングアノテーションの全チャンク通算結果 (Issue #536)。"""

    total_loaded: int = 0
    total_failed: int = 0
    total_results: int = 0
    saved: int = 0
    skipped: int = 0
    preflight_skipped: int = 0
    resolution_skipped: int = 0
    save_errors: int = 0
    any_success: bool = False
    error_models: set[str] = field(default_factory=set)


def _annotation_value(value: Any, key: str, default: Any = None) -> Any:
    """Return annotation payload value from dict-like or object-like results."""
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _annotation_tags(result: Any) -> list[str]:
    """Extract a compact tags list from an annotation result."""
    raw_tags = _annotation_value(result, "tags")
    if raw_tags is None:
        raw_tags = _annotation_value(result, "keywords")
    if raw_tags is None:
        return []
    if isinstance(raw_tags, dict):
        return [str(tag) for tag in raw_tags]
    if isinstance(raw_tags, (list, tuple, set)):
        return [str(tag) for tag in raw_tags]
    return [str(raw_tags)]


def _annotation_score(result: Any) -> float | int | None:
    """Extract a compact score/rating value from an annotation result."""
    for key in ("score", "rating_score", "aesthetic_score"):
        value = _annotation_value(result, key)
        if isinstance(value, (int, float)):
            return value
    scores = _annotation_value(result, "scores")
    if isinstance(scores, dict):
        for value in scores.values():
            if isinstance(value, (int, float)):
                return value
    if isinstance(scores, (list, tuple)):
        for value in scores:
            if isinstance(value, (int, float)):
                return value
    return None


def _emit_annotation_items(results: Any, records_chunk: list[dict[str, Any]]) -> None:
    """Emit one curated JSONL item per annotated image in the chunk."""
    if not is_json_mode() or not results:
        return

    records_by_phash: dict[str, list[dict[str, Any]]] = {}
    for record in records_chunk:
        records_by_phash.setdefault(str(record.get("phash")), []).append(record)
    for phash, model_results in results.items():
        models: list[dict[str, Any]] = []
        if isinstance(model_results, dict):
            model_items = list(model_results.items())
        else:
            model_items = []
        for model_name, model_result in model_items:
            error = _annotation_value(model_result, "error")
            models.append(
                {
                    "model": str(model_name),
                    "tags": _annotation_tags(model_result),
                    "score": _annotation_score(model_result),
                    "error": str(error) if error is not None else None,
                }
            )

        for record in records_by_phash.get(str(phash), [{}]):
            emit_item(
                {
                    "type": "annotation",
                    "image_id": record.get("id"),
                    "phash": str(phash),
                    "file_path": record.get("stored_image_path"),
                    "models": models,
                }
            )


def _stream_annotate(
    *,
    records_to_process: list[dict[str, Any]],
    batch_size: int,
    annotator: Any,
    save_service: Any,
    resolved_litellm_ids: list[str],
    moderation_preflight_service: ModerationPreflightService | None = None,
    resolution_skipped: int = 0,
) -> _StreamAnnotateSummary:
    """レコードを chunk 単位でロード→アノテーション→DB 保存する (Issue #536 / #537)。

    各チャンクで ``_load_batch_images`` により画像を open/load し、``annotator.annotate``
    を実行、結果を ``save_service.save_annotation_results`` で保存する。チャンク処理後
    は PIL 画像を必ず close してメモリを解放する。全チャンクの結果は通算カウンタに
    集約して返す。

    Args:
        records_to_process: 処理対象の画像レコードリスト (選択済み)。
        batch_size: 1 チャンクあたりのレコード数。
        annotator: ``annotate(images, litellm_model_ids=...)`` を持つアノテータ。
        save_service: ``save_annotation_results(results)`` を持つ保存サービス。
        resolved_litellm_ids: 解決済みの litellm_model_id リスト。

    Returns:
        _StreamAnnotateSummary: 全チャンク通算の集計結果。

    Raises:
        ImageLoadMemoryError: メモリ/リソース枯渇による致命的ロード失敗時。
        typer.Exit: ``annotator.annotate`` が例外を投げた場合 (code=1)。
    """
    summary = _StreamAnnotateSummary(resolution_skipped=resolution_skipped)

    progress_context: Any
    if is_json_mode():
        progress_context = _NullProgress()
    else:
        progress_context = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TimeRemainingColumn(),
            console=console,
        )

    with progress_context as active_progress:
        task = active_progress.add_task("Running annotation...", total=len(records_to_process))

        for chunk in _iter_record_batches(records_to_process, batch_size):
            original_chunk_size = len(chunk)
            if moderation_preflight_service is not None:
                chunk, skipped_count = _apply_moderation_preflight_to_records(
                    chunk,
                    moderation_preflight_service,
                )
                summary.preflight_skipped += skipped_count
                if not chunk:
                    active_progress.advance(task, advance=original_chunk_size)
                    continue

            # Issue #537: FATAL (メモリ枯渇) は ImageLoadMemoryError で送出される。
            # loaded_records は images と 1:1 対応。失敗分は除外済み (phash_list 用)。
            images, loaded_records, loaded, failed = _load_batch_images(chunk)
            summary.total_loaded += loaded
            summary.total_failed += failed

            if not images:
                active_progress.advance(task, advance=original_chunk_size)
                continue

            try:
                _annotate_and_save_chunk(
                    records_chunk=chunk,
                    loaded_records=loaded_records,
                    images=images,
                    annotator=annotator,
                    save_service=save_service,
                    resolved_litellm_ids=resolved_litellm_ids,
                    summary=summary,
                )
            finally:
                for img in images:
                    img.close()

            active_progress.advance(task, advance=original_chunk_size)

    return summary


class _NullProgress:
    """No-op context manager used to keep JSON mode stdout free of Rich progress."""

    def __enter__(self) -> _NullProgress:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def add_task(self, *_args: object, **_kwargs: object) -> None:
        return None

    def advance(self, *_args: object, **_kwargs: object) -> None:
        return None


def _apply_moderation_preflight_to_records(
    records_chunk: list[dict[str, Any]],
    moderation_preflight_service: ModerationPreflightService,
) -> tuple[list[dict[str, Any]], int]:
    """Filter a CLI annotation chunk through OpenAI moderation preflight."""
    path_to_record: dict[str, dict[str, Any]] = {}
    passthrough_records: list[dict[str, Any]] = []

    for record in records_chunk:
        stored_path = record.get("stored_image_path")
        if not stored_path:
            passthrough_records.append(record)
            continue
        path_to_record[str(resolve_stored_path(str(stored_path)))] = record

    if not path_to_record:
        return records_chunk, 0

    result = moderation_preflight_service.apply(list(path_to_record))
    allowed = [path_to_record[path] for path in result.allowed_paths if path in path_to_record]
    skipped_count = result.skipped_count
    if skipped_count:
        _status_console().print(f"[yellow]Moderation preflight skipped {skipped_count} image(s)[/yellow]")
    return passthrough_records + allowed, skipped_count


def _annotate_and_save_chunk(
    *,
    records_chunk: list[dict[str, Any]],
    loaded_records: list[dict[str, Any]],
    images: list[Image.Image],
    annotator: Any,
    save_service: Any,
    resolved_litellm_ids: list[str],
    summary: _StreamAnnotateSummary,
) -> None:
    """1 チャンク分の画像をアノテーション → DB 保存し ``summary`` を更新する。

    Args:
        records_chunk: チャンク全レコード (保存スコープ・JSON emit 用)。
        loaded_records: ロード成功レコード。images[i] と 1:1 対応 (phash_list 構築用)。
        images: ロード済み PIL 画像 (非空)。
        annotator: アノテータ。
        save_service: 保存サービス。
        resolved_litellm_ids: 解決済み litellm_model_id リスト。
        summary: 更新対象の通算集計オブジェクト。

    Raises:
        typer.Exit: ``annotator.annotate`` が例外を投げた場合 (code=1)。
    """
    try:
        # Issue #245: AnnotatorLibraryAdapter.annotate は kwarg `litellm_model_ids` を受け取る。
        # Issue #706: --resolution 時は処理済み画像から pHash を再計算すると元画像の pHash と
        # 不一致になり DB 保存が 0 件になる。loaded_records は images と 1:1 対応しているため
        # phash_list を渡して再計算を抑制し DB 上の元 pHash をキーとして使わせる。
        phash_list = [str(r["phash"]) for r in loaded_records if r.get("phash") is not None]
        results = annotator.annotate(
            images,
            litellm_model_ids=resolved_litellm_ids,
            phash_list=phash_list if phash_list else None,
        )
    except Exception as e:
        logger.error(f"Annotation error: {e}", exc_info=True)
        raise AnnotationFailedError(", ".join(resolved_litellm_ids), len(images), str(e)) from e

    if not results:
        return

    summary.total_results += len(results)
    chunk_success, chunk_error_models = _check_annotation_errors(results)
    summary.any_success = summary.any_success or chunk_success
    summary.error_models |= chunk_error_models

    selected_image_ids = {int(record["id"]) for record in records_chunk if record.get("id") is not None}
    save_result = save_service.save_annotation_results(
        results,
        allowed_image_ids=selected_image_ids or None,
    )
    summary.saved += save_result.success_count
    summary.skipped += save_result.skip_count
    summary.save_errors += save_result.error_count
    _emit_annotation_items(results, records_chunk)


def _finalize_annotation_run(summary: _StreamAnnotateSummary, resolved_litellm_ids: list[str]) -> None:
    """ストリーミング結果を検証し、サマリーを表示する (Issue #536)。

    全チャンク通算の集計に基づき、ロード不可・結果ゼロ・全モデル失敗を致命扱い
    とし、部分失敗は warning を表示する。最後に Rich Table
    で結果サマリーを出力する。

    Args:
        summary: ``_stream_annotate`` が返した通算集計。
        resolved_litellm_ids: 解決済み litellm_model_id リスト (サマリー表示用)。

    Raises:
        AnnotationRunFailedError: ロード不可・結果ゼロ・全モデル失敗の場合。
    """
    _validate_annotation_summary(summary)
    if is_json_mode():
        _emit_annotation_result(summary, resolved_litellm_ids)
        return

    console.print(f"[green]Loaded {summary.total_loaded} image(s) ({summary.total_failed} failed)[/green]")
    if summary.resolution_skipped:
        console.print(
            f"[yellow]Resolution filter skipped {summary.resolution_skipped} image(s)"
            f" (no processed image at requested resolution)[/yellow]"
        )
    if summary.preflight_skipped:
        console.print(f"[yellow]Moderation preflight skipped {summary.preflight_skipped} image(s)[/yellow]")

    if summary.total_loaded == 0 and summary.preflight_skipped > 0 and summary.total_failed == 0:
        console.print("[green]Annotation completed: all selected images were skipped by preflight[/green]")
        return
    if summary.error_models:
        console.print(
            f"[yellow]Warning:[/yellow] Some models encountered errors: "
            f"{', '.join(sorted(summary.error_models))}"
        )

    if summary.save_errors:
        console.print(
            f"[yellow]Warning:[/yellow] DB save partially failed: {summary.save_errors} item(s)\n"
            f"DB保存に一部失敗: {summary.save_errors}件"
        )

    console.print("\n[bold cyan]Annotation Summary[/bold cyan]")

    summary_table = Table()
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total Images", str(summary.total_loaded))
    summary_table.add_row("Models Used", ", ".join(resolved_litellm_ids))
    summary_table.add_row("Results", str(summary.total_results))
    summary_table.add_row("Saved to DB", str(summary.saved))
    summary_table.add_row("Skipped", str(summary.skipped))
    summary_table.add_row("Preflight Skipped", str(summary.preflight_skipped))
    if summary.resolution_skipped:
        summary_table.add_row("Resolution Skipped", str(summary.resolution_skipped))

    console.print(summary_table)

    console.print(f"\n[green]Annotation completed successfully! ({summary.saved} saved to DB)[/green]")


def _validate_annotation_summary(summary: _StreamAnnotateSummary) -> None:
    """Raise if the completed annotation stream has no usable result."""
    if summary.total_loaded == 0:
        if summary.preflight_skipped > 0 and summary.total_failed == 0:
            return
        raise AnnotationRunFailedError("No images could be loaded for annotation")
    if summary.total_results == 0:
        raise AnnotationRunFailedError("Annotation produced no results")
    if not summary.any_success and summary.error_models:
        raise AnnotationRunFailedError(
            f"All annotation models failed: {', '.join(sorted(summary.error_models))}"
        )


def _emit_annotation_result(summary: _StreamAnnotateSummary, resolved_litellm_ids: list[str]) -> None:
    """Emit the terminal JSONL result for annotate run."""
    emit_result(
        f"Annotated {summary.saved} image(s)",
        annotated=summary.saved,
        skipped=summary.skipped + summary.preflight_skipped + summary.total_failed,
        resolution_skipped=summary.resolution_skipped,
        errors=summary.save_errors + len(summary.error_models),
        loaded=summary.total_loaded,
        results=summary.total_results,
        models=resolved_litellm_ids,
    )


def _get_deprecated_models_best_effort(annotator: Any, model_names: list[str]) -> list[str]:
    """廃止モデル一覧をbest-effortで取得する。

    廃止判定は警告表示のための補助情報なので、取得に失敗しても
    アノテーション本体は継続する。
    """
    try:
        return [
            model_name for model_name in model_names if annotator.is_model_deprecated(model_name) is True
        ]
    except Exception as e:
        logger.warning(f"Deprecated model check skipped: {e}")
        _status_console().print(
            "[yellow]Warning:[/yellow] Deprecated model metadata is unavailable; continuing annotation."
        )
        return []


def _abort_if_discontinued(model: Any) -> None:
    """de-list 済 (available=False) モデルは fail-fast で abort する (Issue #589 / PR #590 review P2)。

    GUI は `Model.available` でフィルタするが CLI resolver は exact ID で素通りしていたため、
    de-list / 提供終了モデルを `annotate run --model <id>` で実行でき runtime 失敗 (404 等) を
    招いていた。GUI と同じく discontinued なモデルを候補から除外する。

    Raises:
        typer.Exit: モデルが discontinued (`available=False`) の場合 (code=1)。
    """
    if not getattr(model, "available", True):
        raise click.UsageError(
            f"Model '{model.litellm_model_id}' is discontinued / no longer "
            "provided by the annotation library and cannot be used. "
            "Run `lorairo-cli models list` to see available IDs."
        )


def _resolve_model_identifier(repository: ModelRepository, identifier: str) -> str:
    """ユーザー入力を canonical `litellm_model_id` に解決する (Issue #245)。

    解決順:
      1. `litellm_model_id` 完全一致 → そのまま返す (推奨経路)
      2. `name` 一致が単一 → その行の `litellm_model_id` を返す (convenience)
      3. `name` 一致が複数 → typer.Exit(code=1) で候補一覧を表示して中断
      4. 一致なし → typer.Exit(code=1) で `models list` を案内して中断

    ADR 0023 Phase 1.11: `Model.name` は非 UNIQUE、`Model.litellm_model_id` は
    UNIQUE NOT NULL の registry key SSoT。同一 name で route の異なる行が
    共存しうるため、曖昧マッチは silent な誤 route を生まないよう abort する。

    Args:
        repository: LoRAIro DB リポジトリ (active project に設定済み)。
        identifier: ユーザー入力文字列 (litellm_model_id または name)。

    Returns:
        str: 解決後の `litellm_model_id`。

    Raises:
        typer.Exit: 曖昧マッチまたは一致なしの場合 (code=1)。
    """
    by_litellm = repository.get_model_by_litellm_id(identifier)
    if by_litellm is not None:
        _abort_if_discontinued(by_litellm)
        return by_litellm.litellm_model_id

    by_name = repository.get_models_by_name(identifier)
    if len(by_name) == 1:
        _abort_if_discontinued(by_name[0])
        resolved = by_name[0].litellm_model_id
        logger.debug(f"--model '{identifier}' を name 経由で {resolved} に解決")
        return resolved

    if len(by_name) > 1:
        candidate_lines = "\n".join(
            f"  - {m.litellm_model_id} (provider: {m.provider or 'unknown'})" for m in by_name
        )
        raise click.UsageError(
            f"Ambiguous model '{identifier}':\n"
            f"{candidate_lines}\n"
            "Use the full LiteLLM model ID. Run `lorairo-cli models list` to see available IDs."
        )

    raise click.UsageError(
        f"Unknown model '{identifier}'. Run `lorairo-cli models list` to see available IDs."
    )


def _validate_required_api_keys(
    repository: ModelRepository,
    config: Any,
    resolved_litellm_ids: list[str],
) -> None:
    """Issue #241: 実行直前に API key 不足を検出し、不足時は ``typer.Exit(1)``。

    旧実装は「3 種類キー全部無いとき警告」だけで、片方の provider key のみ設定
    された環境で OpenRouter 経由モデルを選ぶと library 内で ``MissingApiKeyError``
    が出てから失敗していた。本 helper は registry key (litellm_model_id) の prefix
    と DB ``Model.provider`` を hint として provider 別の不足を列挙する。

    Args:
        repository: LoRAIro DB リポジトリ (Model.provider 解決用)。
        config: ``ConfigurationService`` 互換 (``get_setting`` を持つ)。
        resolved_litellm_ids: ``_resolve_model_identifier()`` で解決済みの
            ``litellm_model_id`` リスト。

    Raises:
        typer.Exit: 不足ありの場合 (code=1)。エラーメッセージに不足 provider と
            litellm_id を列挙する。
    """
    api_keys = {
        "openai": config.get_setting("api", "openai_key", ""),
        "anthropic": config.get_setting("api", "claude_key", ""),
        "google": config.get_setting("api", "google_key", ""),
        "openrouter": config.get_setting("api", "openrouter_key", ""),
    }

    provider_hints: dict[str, str] = {}
    for litellm_id in resolved_litellm_ids:
        db_model = repository.get_model_by_litellm_id(litellm_id)
        if db_model is not None and db_model.provider:
            provider_hints[litellm_id] = db_model.provider

    missing = validate_api_keys_for_models(resolved_litellm_ids, api_keys, provider_hints)
    if not missing:
        return

    missing_lines = "\n".join(
        f"  - {provider}: required for {litellm_id}" for litellm_id, provider in missing
    )
    raise click.UsageError(
        "Missing API keys for selected models:\n"
        f"{missing_lines}\n\n"
        "Configure the missing keys in config/lorairo.toml [api] section, "
        "or pick a different route (e.g. `--model openai/...` instead of "
        "`--model openrouter/openai/...`)."
    )


def _build_annotation_filter_criteria(
    model_repo: ModelRepository,
    *,
    unrated: bool,
    missing_model: str | None,
) -> tuple[ImageFilterCriteria, str | None]:
    """annotate run のCLIオプションからDB検索条件を組み立てる。"""
    missing_model_litellm_id = (
        _resolve_model_identifier(model_repo, missing_model) if missing_model is not None else None
    )
    return (
        ImageFilterCriteria(
            include_nsfw=True,
            only_unrated=unrated,
            missing_model_litellm_id=missing_model_litellm_id,
        ),
        missing_model_litellm_id,
    )


def _handle_no_image_records(
    project: str,
    *,
    filters_applied: bool,
) -> None:
    """DB検索結果0件時のCLIエラーを表示して終了する。"""
    if filters_applied:
        raise AnnotationSelectionError(f"No images matched annotation filters for project '{project}'.")

    raise AnnotationSelectionError(
        f"No registered images found in project '{project}'. Run 'lorairo-cli images register' first."
    )


def _apply_resolution_filter(
    records: list[dict[str, Any]],
    image_repo: Any,
    resolution: int,
) -> tuple[list[dict[str, Any]], int]:
    """処理済み画像パスで records を差し替え、該当なしをスキップカウントする (Issue #706)。

    Args:
        records: 処理対象レコード。
        image_repo: ImageRepository インスタンス。
        resolution: 目標解像度 (長辺ピクセル数)。

    Returns:
        (更新済みレコードリスト, スキップ件数)
    """
    record_ids = [r["id"] for r in records if r.get("id") is not None]
    proc_paths = image_repo.get_processed_image_paths_by_resolution(record_ids, resolution)
    filtered: list[dict[str, Any]] = []
    skipped = 0
    for record in records:
        image_id = record.get("id")
        if image_id in proc_paths:
            updated = dict(record)
            updated["stored_image_path"] = proc_paths[image_id]
            filtered.append(updated)
        else:
            skipped += 1
    return filtered, skipped


def _print_annotation_filter_summary(
    *,
    unrated: bool,
    missing_model_litellm_id: str | None,
) -> None:
    """適用中のannotate runフィルタを表示する。"""
    if unrated:
        _status_console().print("[cyan]Filter: unrated images only[/cyan]")
    if missing_model_litellm_id is not None:
        _status_console().print(f"[cyan]Filter: missing model {missing_model_litellm_id}[/cyan]")


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
        help=(
            "LiteLLM model ID (e.g., openrouter/openai/gpt-4o, openai/gpt-4o, "
            "wd-vit-tagger-v3). Use `lorairo-cli models list` to see available IDs. "
            "Name-only input is accepted only when it uniquely matches a single row."
        ),
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
        min=1,
        help="Batch size for processing (>=1; bounds memory per chunk)",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        help="Max number of images to annotate (>=1)",
    ),
    offset: int = typer.Option(
        0,
        "--offset",
        min=0,
        help="Skip the first N eligible images (for sharding)",
    ),
    image_id: list[int] = typer.Option(
        [],
        "--image-id",
        "-i",
        help="Target specific image ID(s); repeatable",
    ),
    unrated: bool = typer.Option(
        False,
        "--unrated",
        help="Annotate only images without any saved rating rows.",
    ),
    missing_model: str | None = typer.Option(
        None,
        "--missing-model",
        help="Annotate only images without saved annotations from the given LiteLLM model ID.",
    ),
    resolution: int | None = typer.Option(
        None,
        "--resolution",
        min=1,
        help=(
            "Use processed images at this resolution (long side in pixels). "
            "Images without a matching processed image are skipped."
        ),
    ),
) -> None:
    """Run annotation on project images.

    プロジェクトの画像に対してアノテーションを実行します。
    使用可能なモデル ID は 'lorairo-cli models list' で確認してください。

    Issue #245 / ADR 0023 Phase 1.11: `--model` には `litellm_model_id` (registry
    key SSoT) を渡すこと。display 名 (`Model.name`) は同一値で複数 route の行が
    共存しうるため、曖昧時は Error で abort し候補一覧を表示する。

    Examples:
        lorairo-cli annotate run --project myproject --model openai/gpt-4o
        lorairo-cli annotate run --project myproject --model openai/omni-moderation-latest
        lorairo-cli annotate run --project myproject \\
            --model openrouter/openai/gpt-4o --model openrouter/anthropic/claude-3-5-sonnet
    """
    with command_boundary():
        # API層経由でプロジェクト確認 & DB 接続切り替え
        api_get_project(project)

        container = get_service_container()
        container.set_active_project(project)

        # DB からプロジェクトの登録済み画像を取得
        image_repo = container.db_manager.image_repo
        model_repo = container.db_manager.model_repo

        # Issue #245: --model 入力を canonical litellm_model_id に解決
        # (曖昧マッチは Error で abort、ここで raise した typer.Exit は外側 except で素通り)
        resolved_litellm_ids = [_resolve_model_identifier(model_repo, ident) for ident in model]
        criteria, missing_model_litellm_id = _build_annotation_filter_criteria(
            model_repo,
            unrated=unrated,
            missing_model=missing_model,
        )

        image_records, total_in_db = image_repo.get_images_by_filter(criteria)

        if not image_records:
            _handle_no_image_records(
                project,
                filters_applied=unrated or missing_model_litellm_id is not None,
            )

        # Issue #538 (Track B): limit/offset/image-id によるレコード選択。
        # placeholder は全件返すが、本実装後もここで絞り込んだ集合を処理する。
        records_to_process = _select_image_records(
            image_records,
            limit=limit,
            offset=offset,
            image_ids=image_id or None,
        )

        if not records_to_process:
            raise AnnotationSelectionError("No images selected for annotation")

        resolution_skipped_count = 0
        if resolution is not None:
            records_to_process, resolution_skipped_count = _apply_resolution_filter(
                records_to_process, image_repo, resolution
            )
            if not records_to_process:
                raise AnnotationSelectionError(
                    f"No processed images found at resolution {resolution}; "
                    f"{resolution_skipped_count} image(s) skipped"
                )
        else:
            reject_original_image_records(records_to_process, command_name="annotate run")

        if len(records_to_process) > MAX_ANNOTATE_IMAGES:
            raise ResultSetTooLargeError(len(records_to_process), MAX_ANNOTATE_IMAGES)

        target_console = _status_console()
        target_console.print(f"[cyan]Found {total_in_db} image(s) in DB[/cyan]")
        target_console.print(f"[cyan]Using model(s): {', '.join(resolved_litellm_ids)}[/cyan]")
        # #543 の DB レベルフィルタ (--unrated / --missing-model) のサマリー。
        # eager な "Loaded N" 行は streaming では _finalize_annotation_run が
        # summary.total_loaded から出力するため、ここでは出さない (Issue #536)。
        _print_annotation_filter_summary(
            unrated=unrated,
            missing_model_litellm_id=missing_model_litellm_id,
        )

        annotator = container.annotator_library
        config = container.config_service

        deprecated_models = _get_deprecated_models_best_effort(annotator, resolved_litellm_ids)
        for deprecated_model in deprecated_models:
            target_console.print(f"[yellow]Warning: Model '{deprecated_model}' is deprecated[/yellow]")

        # Issue #241: 実行直前に LoRAIro 側で API key 不足を事前検出する。
        # 旧実装は「3 種類キー全部無いとき警告」だけで、片方の provider key だけ
        # 設定されていて選択モデルがもう片方を要求する場合に library 内で
        # MissingApiKeyError が出てから初めて失敗していた。
        _validate_required_api_keys(model_repo, config, resolved_litellm_ids)

        # アノテーション実行 (Issue #536: チャンクストリーミング)
        target_console.print("[cyan]Starting annotation...[/cyan]")
        try:
            should_preflight = selection_includes_webapi_model(resolved_litellm_ids, annotator)
        except Exception as e:
            logger.warning(
                f"WebAPI model detection failed; moderation preflight skipped: {e}", exc_info=True
            )
            should_preflight = False

        moderation_preflight_service = None
        if should_preflight:
            from lorairo.annotations.annotation_logic import AnnotationLogic

            moderation_logic = AnnotationLogic(annotator)
            moderation_preflight_service = ModerationPreflightService(
                image_repo=container.db_manager.image_repo,
                model_repo=container.db_manager.model_repo,
                error_record_repo=container.db_manager.error_record_repo,
                annotation_save_service=container.annotation_save_service,
                config_service=config,
                moderation_runner=build_annotation_logic_runner(moderation_logic.execute_annotation),
            )

        summary = _stream_annotate(
            records_to_process=records_to_process,
            batch_size=batch_size,
            annotator=annotator,
            save_service=container.annotation_save_service,
            resolved_litellm_ids=resolved_litellm_ids,
            moderation_preflight_service=moderation_preflight_service,
            resolution_skipped=resolution_skipped_count,
        )

        _finalize_annotation_run(summary, resolved_litellm_ids)


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
            f"\n[yellow]Unmatched ({len(result.unmatched_ids)} item(s))"
            f" - filenames from custom_id not registered in DB\n"
            f"照合失敗 ({len(result.unmatched_ids)}件) - custom_idから抽出したファイル名がDBに未登録:[/yellow]"
        )
        for uid in result.unmatched_ids[:10]:
            stem = BatchImageMatcher.extract_stem(uid)
            console.print(f"  - [bold]{stem}[/bold]  ← {uid}")
        if len(result.unmatched_ids) > 10:
            console.print(f"  ... and {len(result.unmatched_ids) - 10} more")

    # エラー詳細（5件まで表示）
    if result.error_details:
        console.print(f"\n[red]Errors ({len(result.error_details)}):[/red]")
        for detail in result.error_details[:5]:
            console.print(f"  - {detail}")
        if len(result.error_details) > 5:
            console.print(f"  ... and {len(result.error_details) - 5} more")

    if not dry_run and result.saved > 0:
        console.print(
            f"\n[green]Import completed: {result.saved} item(s) saved.\n"
            f"インポート完了: {result.saved}件保存しました[/green]"
        )


@app.command("import-batch")
def import_batch(
    jsonl_dir: Path = typer.Argument(
        ...,
        help="JSONL files directory (OpenAI Batch API results)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
    ),
    project: str = typer.Option(
        ...,
        "--project",
        "-p",
        help="Target project name / インポート先プロジェクト名",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show match results without saving to DB / DB書き込みを行わず照合結果のみ表示",
    ),
    model_name: str | None = typer.Option(
        None,
        "--model-name",
        help="Override model name (ignores model field in JSONL) / モデル名を上書き（JSONL内のmodel名を無視）",
    ),
) -> None:
    """Import OpenAI Batch API result JSONL files in bulk.
    OpenAI Batch API結果JSONLを一括インポートする。

    Reads all JSONL files in the directory, matches custom_id against
    registered image filenames in the DB, and imports annotation results.
    ディレクトリ内の全JSONLファイルを読み込み、
    custom_idとDB登録済み画像のファイル名を照合して
    アノテーション結果をインポートします。

    Examples:
        lorairo-cli annotate import-batch jsonl/ -p main_dataset_20250707_001
        lorairo-cli annotate import-batch jsonl/ -p my_project --dry-run
    """
    with command_boundary():
        get_service_container().set_active_project(project)
        result = import_batch_annotations(
            jsonl_dir,
            project,
            dry_run=dry_run,
            model_name_override=model_name,
        )
        if is_json_mode():
            emit_result(
                f"Imported {result.saved} batch annotation(s)",
                total_records=result.total_records,
                parsed_ok=result.parsed_ok,
                parse_errors=result.parse_errors,
                matched=result.matched,
                unmatched=result.unmatched,
                saved=result.saved,
                save_errors=result.save_errors,
                model_name=result.model_name,
                dry_run=dry_run,
            )
            return

        _display_batch_import_result(result, dry_run=dry_run)
