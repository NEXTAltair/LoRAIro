"""Model registry commands."""

from __future__ import annotations

from enum import StrEnum

import typer
from rich.console import Console
from rich.table import Table

from lorairo.services.model_route_service import (
    build_available_providers,
    canonical_key,
    detect_route,
    required_provider_for,
)
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

app = typer.Typer(help="Model registry commands")
console = Console()


class ModelTypeFilter(StrEnum):
    """`models list` の `--type` フィルタ値。"""

    all = "all"
    webapi = "webapi"
    local = "local"


class ModelCategoryFilter(StrEnum):
    """`models list` の `--category` フィルタ値 (AnnotatorInfo.model_type に対応)。"""

    all = "all"
    tagger = "tagger"
    scorer = "scorer"
    captioner = "captioner"
    vision = "vision"


class RouteFilter(StrEnum):
    """`models list` の `--route` フィルタ値 (Issue #241)。"""

    auto = "auto"
    direct = "direct"
    openrouter = "openrouter"
    all = "all"


@app.command("refresh")
def refresh(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Project to sync model metadata into. Uses default DB when omitted.",
    ),
) -> None:
    """Refresh available WebAPI models."""
    try:
        container = get_service_container()
        if project is not None:
            container.set_active_project(project)
        console.print("[cyan]Refreshing model registry...[/cyan]")
        models = container.annotator_library.refresh_available_models()
        sync_result = container.model_sync_service.sync_available_models()

        if sync_result.errors:
            console.print("[red]Error:[/red] Model registry refreshed but DB sync failed.")
            console.print(sync_result.summary)
            for error in sync_result.errors:
                console.print(f"[red]Sync error:[/red] {error}")
            raise typer.Exit(code=1)

        console.print(f"[green]Model registry refreshed.[/green] {len(models)} model(s) discovered.")
        console.print(sync_result.summary)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to refresh models: {e}")
        logger.error(f"Model refresh command failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


@app.command("list")
def list_models(
    include_deprecated: bool = typer.Option(
        False,
        "--include-deprecated",
        help="Include deprecated WebAPI models",
    ),
    type_filter: ModelTypeFilter = typer.Option(
        ModelTypeFilter.all,
        "--type",
        case_sensitive=False,
        help="Filter by execution type (all / webapi / local)",
    ),
    category: ModelCategoryFilter = typer.Option(
        ModelCategoryFilter.all,
        "--category",
        case_sensitive=False,
        help="Filter by model category (all / tagger / scorer / captioner / vision)",
    ),
    route: RouteFilter = typer.Option(
        RouteFilter.auto,
        "--route",
        case_sensitive=False,
        help=(
            "Route preference (Issue #241). "
            "auto: API key 設定済み provider に応じて direct を優先 / "
            "direct: 直接プロバイダー経路のみ / "
            "openrouter: OpenRouter 経由のみ / "
            "all: 同一モデルの全 route を 1 行ずつ表示"
        ),
    ),
) -> None:
    """List available annotator models (WebAPI + local).

    Issue #241: 同一モデルが direct / openrouter 経路で 2 行並ぶ重複を畳み込み、
    API key 設定済み provider を優先 route として 1 行にまとめる。
    ``--route all`` を指定した場合のみ全 candidate を 1 行ずつ表示する。
    """
    try:
        container = get_service_container()
        annotator = container.annotator_library
        infos = annotator.list_annotator_info()

        config = container.config_service
        api_keys = {
            "openai": config.get_setting("api", "openai_key", ""),
            "anthropic": config.get_setting("api", "claude_key", ""),
            "google": config.get_setting("api", "google_key", ""),
            "openrouter": config.get_setting("api", "openrouter_key", ""),
        }
        available_providers = build_available_providers(api_keys)

        rows: list[dict[str, str | bool]] = []
        for info in infos:
            if type_filter is ModelTypeFilter.webapi and not info.is_api:
                continue
            if type_filter is ModelTypeFilter.local and not info.is_local:
                continue
            if category is not ModelCategoryFilter.all and info.model_type != category.value:
                continue

            try:
                deprecated = annotator.is_model_deprecated(info.name)
            except Exception as e:
                logger.warning(f"Deprecated check failed for {info.name}: {e}")
                deprecated = False

            if deprecated and not include_deprecated:
                continue

            type_label = "webapi" if info.is_api else "local"
            # Issue #245: Provider と Litellm ID を表示し、route の区別を可能にする。
            provider_label = info.provider or ("local" if info.is_local else "unknown")
            litellm_id = info.litellm_model_id or info.name
            row_route = detect_route(litellm_id)
            row_required = required_provider_for(litellm_id, info.provider)
            rows.append(
                {
                    "name": info.name,
                    "provider": provider_label,
                    "litellm_id": litellm_id,
                    "type_label": type_label,
                    "category": info.model_type,
                    "deprecated": deprecated,
                    "route": row_route,
                    "required_provider": row_required,
                }
            )

        # Issue #241: canonical_key で grouping し、--route preference に従って絞り込む。
        display_rows = _apply_route_filter(rows, route, available_providers)

        # 長いモデル名 (例: "vercel_ai_gateway/openai/o1") で固定幅未指定のままだと
        # Rich Table が Type/Category/Status を 0 幅に collapse させて Issue #220 の
        # 主要機能 (Type 列で local/webapi 区別) が視認できなくなる。各カラムに
        # min_width を指定し、Model/Provider/Litellm ID カラムは折返し許容で長さに対応する。
        # Issue #245: Provider/Litellm ID 列を追加。
        # Issue #241: Route 列を追加 (direct / openrouter)。
        table = Table(title="Available Models")
        table.add_column("Model", style="cyan", overflow="fold", min_width=10)
        table.add_column("Provider", style="bright_magenta", overflow="fold", min_width=8)
        table.add_column("Litellm ID", style="bright_cyan", overflow="fold", min_width=10)
        table.add_column("Route", style="bright_blue", min_width=8, no_wrap=True)
        table.add_column("Type", style="magenta", min_width=6, no_wrap=True)
        table.add_column("Category", style="blue", min_width=8, no_wrap=True)
        table.add_column("Status", style="green", min_width=10, no_wrap=True)

        for row in display_rows:
            table.add_row(
                str(row["name"]),
                str(row["provider"]),
                str(row["litellm_id"]),
                str(row["route"]),
                str(row["type_label"]),
                str(row["category"]),
                "[yellow]deprecated[/yellow]" if row["deprecated"] else "active",
            )

        console.print(table)
        console.print(f"[dim]{len(display_rows)} model(s) (preference={route.value})[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to list models: {e}")
        logger.error(f"Model list command failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


def _apply_route_filter(
    rows: list[dict[str, str | bool]],
    route: RouteFilter,
    available_providers: set[str],
) -> list[dict[str, str | bool]]:
    """Issue #241: AnnotatorInfo 由来の row リストに canonical_key 畳み込みと route 選択を適用。

    Args:
        rows: ``list_models()`` で構築した row dict 群。各 row には
            ``litellm_id``, ``route``, ``required_provider`` が含まれる前提。
        route: ``--route`` Typer Option の値。
        available_providers: API key 設定済み provider 集合。

    Returns:
        表示用 row のリスト。``route="all"`` の場合は元 row を全件、それ以外は
        canonical_key 単位で preferred row を 1 件ずつ返す。
    """
    grouped, order = _group_rows_by_canonical_key(rows)

    if route is RouteFilter.all:
        return [row for ckey in order for row in grouped[ckey]]

    result: list[dict[str, str | bool]] = []
    for ckey in order:
        chosen = _pick_row_for_route(grouped[ckey], route, available_providers)
        if chosen is not None:
            result.append(chosen)
    return result


def _group_rows_by_canonical_key(
    rows: list[dict[str, str | bool]],
) -> tuple[dict[str, list[dict[str, str | bool]]], list[str]]:
    """canonical_key で row を grouping し、入力順を保持した key リストも返す。"""
    grouped: dict[str, list[dict[str, str | bool]]] = {}
    order: list[str] = []
    for row in rows:
        litellm_id = str(row["litellm_id"])
        ckey = canonical_key(litellm_id)
        if ckey not in grouped:
            grouped[ckey] = []
            order.append(ckey)
        grouped[ckey].append(row)
    return grouped, order


def _pick_row_for_route(
    group_rows: list[dict[str, str | bool]],
    route: RouteFilter,
    available_providers: set[str],
) -> dict[str, str | bool] | None:
    """同一 canonical_key の row 群から ``--route`` 値に応じて 1 件選ぶ。

    auto モードは direct を優先しつつ ``available_providers`` を考慮し、
    どちらも未設定の場合は direct (なければ openrouter) を disabled 表示用に返す。
    """
    by_route: dict[str, dict[str, str | bool]] = {str(r["route"]): r for r in group_rows}
    direct = by_route.get("direct")
    openrouter = by_route.get("openrouter")

    if route is RouteFilter.direct:
        return direct
    if route is RouteFilter.openrouter:
        return openrouter

    # auto
    if direct is not None and str(direct["required_provider"]) in available_providers:
        return direct
    if openrouter is not None and str(openrouter["required_provider"]) in available_providers:
        return openrouter
    return direct or openrouter
