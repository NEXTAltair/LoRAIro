"""Model registry commands."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer
from rich.table import Table

from lorairo.cli._console import make_console

if TYPE_CHECKING:
    from rich.console import Console
from lorairo.services.model_route_service import (
    build_available_providers,
    build_model_route_identity,
    parse_route_preference,
)
from lorairo.services.service_container import get_service_container
from lorairo.utils.log import logger

app = typer.Typer(help="Model registry commands")
# Rich console (Issue #254: Windows では safe_box=True で ASCII 罫線)
console = make_console()


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
    route: RouteFilter | None = typer.Option(
        None,
        "--route",
        case_sensitive=False,
        help=(
            "Route preference (Issue #241). "
            "auto: API key 設定済み provider に応じて direct を優先 / "
            "direct: 直接プロバイダー経路のみ / "
            "openrouter: OpenRouter 経由のみ / "
            "all: 同一モデルの全 route を 1 行ずつ表示。"
            "未指定時は config の [model_selection].route_preference を使う (Issue #249)。"
        ),
    ),
    show_unavailable: bool = typer.Option(
        False,
        "--show-unavailable",
        help=(
            "API key 未設定で利用不可な行も表示する (Issue #249)。"
            "default は available な行のみ。ローカル ML モデルは常に available 扱い。"
        ),
    ),
) -> None:
    """List available annotator models (WebAPI + local).

    Issue #241: 同一モデルが direct / openrouter 経路で 2 行並ぶ重複を畳み込み、
    API key 設定済み provider を優先 route として 1 行にまとめる。
    ``--route all`` を指定した場合のみ全 candidate を 1 行ずつ表示する。

    Issue #249: ``--route`` 未指定時は config の ``[model_selection].route_preference``
    を default として読み込み、``--show-unavailable`` で API key 未設定の行も表示する。
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

        # Issue #249: --route 未指定時は config 値を使う。明示指定は config 上書き。
        if route is None:
            raw_preference = config.get_setting("model_selection", "route_preference", "auto")
            route = RouteFilter(parse_route_preference(raw_preference))
            preference_source = "config"
        else:
            preference_source = "explicit"

        rows = _build_rows_from_infos(
            infos=infos,
            type_filter=type_filter,
            category=category,
            include_deprecated=include_deprecated,
            annotator=annotator,
            available_providers=available_providers,
        )

        # Issue #241: canonical_key で grouping し、--route preference に従って絞り込む。
        display_rows_pre_unavailable = _apply_route_filter(rows, route, available_providers)

        # Issue #249: --show-unavailable 未指定時は available 行のみに絞る。
        if not show_unavailable:
            display_rows = [r for r in display_rows_pre_unavailable if r.get("available", True)]
        else:
            display_rows = display_rows_pre_unavailable

        table = _build_available_models_table(
            display_rows=display_rows,
            type_filter=type_filter,
            category=category,
            show_unavailable=show_unavailable,
            include_deprecated=include_deprecated,
        )
        console.print(table)
        # Issue #249: preference の取得元と unavailable 件数も表示
        unavailable_count = sum(1 for r in display_rows if not r.get("available", True))
        unavailable_suffix = f", unavailable={unavailable_count}" if unavailable_count > 0 else ""
        console.print(
            f"[dim]{len(display_rows)} model(s) "
            f"(preference={route.value} from {preference_source}{unavailable_suffix})[/dim]"
        )

        # Issue #253: silent 0 件問題の切り分けのため DEBUG 診断を出し、
        # 0 件のときは原因に応じた hint を画面に表示する。
        _log_models_list_diagnostic(
            container=container,
            api_keys=api_keys,
            available_providers=available_providers,
            infos=infos,
            rows_count=len(rows),
            display_rows_pre_unavailable_count=len(display_rows_pre_unavailable),
            display_rows_count=len(display_rows),
            route=route,
            preference_source=preference_source,
        )
        if not display_rows:
            _emit_zero_count_hint(
                console=console,
                api_keys_configured=bool(available_providers),
                show_unavailable=show_unavailable,
            )
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to list models: {e}")
        logger.error(f"Model list command failed: {e}", exc_info=True)
        raise typer.Exit(code=1) from e


def _build_available_models_table(
    *,
    display_rows: list[dict[str, str | bool]],
    type_filter: ModelTypeFilter,
    category: ModelCategoryFilter,
    show_unavailable: bool,
    include_deprecated: bool,
) -> Table:
    """models list の表示用 Rich table を構築する。"""
    table = Table(title="Available Models")
    table.add_column("Provider", style="bright_magenta", min_width=8, no_wrap=True)
    table.add_column("Route", style="bright_blue", min_width=8, no_wrap=True)
    table.add_column("Model ID", style="bright_cyan", overflow="fold", min_width=32, ratio=1)

    show_type_column = type_filter is ModelTypeFilter.all
    show_category_column = type_filter is ModelTypeFilter.all and category is ModelCategoryFilter.all
    show_availability_column = show_unavailable or include_deprecated

    if show_type_column:
        table.add_column("Type", style="magenta", min_width=6, no_wrap=True)
    if show_category_column:
        table.add_column("Category", style="blue", min_width=8, no_wrap=True)
    if show_availability_column:
        table.add_column("Availability", style="green", min_width=12, no_wrap=True)

    for row in display_rows:
        table_row = [
            str(row["provider"]),
            str(row["route"]),
            str(row["litellm_id"]),
        ]
        if show_type_column:
            table_row.append(str(row["type_label"]))
        if show_category_column:
            table_row.append(str(row["category"]))
        if show_availability_column:
            table_row.append(_format_availability(row))
        table.add_row(*table_row)

    return table


def _format_availability(row: dict[str, str | bool]) -> str:
    """ユーザー向けの利用可否ラベルを返す。

    ``models list`` の default は利用可能な行だけを表示するため、この列は
    ``--show-unavailable`` や ``--include-deprecated`` のときだけ表示する。
    """
    if not row.get("available", True):
        return "[red]missing_key[/red]"
    if row["deprecated"]:
        return "[yellow]deprecated[/yellow]"
    return "ready"


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
        ckey = str(row["canonical_key"])
        if ckey not in grouped:
            grouped[ckey] = []
            order.append(ckey)
        grouped[ckey].append(row)
    return grouped, order


def _build_rows_from_infos(
    *,
    infos: list[Any],
    type_filter: ModelTypeFilter,
    category: ModelCategoryFilter,
    include_deprecated: bool,
    annotator: Any,
    available_providers: set[str],
) -> list[dict[str, str | bool]]:
    """AnnotatorInfo リストから表示用 row dict 群を構築する。

    Issue #249: ``list_models`` の cyclomatic complexity を下げるための切り出し。
    type/category/deprecated フィルタ + provider / route / available 判定までを担当。
    """
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
        litellm_id = info.litellm_model_id or info.name
        identity = build_model_route_identity(
            litellm_id,
            info.name,
            info.provider,
            info.is_api,
        )
        # Provider 列は LiteLLM の raw prefix ではなく、実際に必要な API key provider を表示する。
        provider_label = "local" if info.is_local else identity.required_provider
        # Issue #249: ローカル ML モデルは API key 不要のため常に available。
        # info.is_local も加味する: provider 未設定 + slash 入り bare ID のローカルモデル
        # (例: "some/local-tagger") は required_provider_for だと "some" になるため、
        # info.is_local フラグを優先して available 判定する。
        row_available = (
            info.is_local
            or identity.required_provider == "local"
            or identity.required_provider in available_providers
        )
        rows.append(
            {
                "name": info.name,
                "provider": provider_label,
                "litellm_id": litellm_id,
                "canonical_key": identity.canonical_key,
                "display_name": identity.display_name,
                "display_family": identity.display_family,
                "type_label": type_label,
                "category": info.model_type,
                "deprecated": deprecated,
                "route": identity.route,
                "required_provider": identity.required_provider,
                "available": row_available,
            }
        )
    return rows


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


def _resolve_active_config_path(container: Any) -> str:
    """Issue #253: 実際に読まれている config file の absolute path を返す。

    ``ConfigurationService.__init__`` は ``config_path`` 引数を ``self._config_path``
    に保持している。本番経路は引数なしで ``DEFAULT_CONFIG_PATH`` 固定だが、テストの
    ``MagicMock`` 等で属性が無い場合は ``DEFAULT_CONFIG_PATH`` への直 fallback で
    ``<default: ...>`` ラベル付き表示にする (実 path とは限らないことを明示する)。
    """
    config_service = container.config_service
    config_path = getattr(config_service, "_config_path", None)
    if config_path is not None:
        try:
            return str(Path(config_path).resolve())
        except (OSError, TypeError):
            pass
    try:
        from lorairo.utils.config import DEFAULT_CONFIG_PATH

        return f"<default: {DEFAULT_CONFIG_PATH.resolve()}>"
    except ImportError:
        return "<unknown>"


def _log_models_list_diagnostic(
    *,
    container: Any,
    api_keys: dict[str, str],
    available_providers: set[str],
    infos: list[Any],
    rows_count: int,
    display_rows_pre_unavailable_count: int,
    display_rows_count: int,
    route: RouteFilter,
    preference_source: str,
) -> None:
    """Issue #253: ``models list`` の切り分け用 DEBUG diagnostic を 1 行で出す。

    key 値は出さず ``*_loaded`` boolean のみ。
    ``--log-level DEBUG`` 起動時のみ表示。
    """
    config_path = _resolve_active_config_path(container)
    api_key_status = {
        "openai_key_loaded": bool(api_keys.get("openai") and api_keys["openai"].strip()),
        "claude_key_loaded": bool(api_keys.get("anthropic") and api_keys["anthropic"].strip()),
        "google_key_loaded": bool(api_keys.get("google") and api_keys["google"].strip()),
        "openrouter_key_loaded": bool(api_keys.get("openrouter") and api_keys["openrouter"].strip()),
    }
    is_api_count = sum(1 for i in infos if getattr(i, "is_api", False))
    is_local_count = sum(1 for i in infos if getattr(i, "is_local", False))
    logger.debug(
        f"models list diagnostic: "
        f"config_path={config_path}, "
        f"api_key_status={api_key_status}, "
        f"available_providers={sorted(available_providers) or 'NONE'}, "
        f"total_infos={len(infos)}, "
        f"is_api_count={is_api_count}, is_local_count={is_local_count}, "
        f"rows_after_type_filter={rows_count}, "
        f"rows_after_route_filter={display_rows_pre_unavailable_count}, "
        f"rows_after_show_unavailable_filter={display_rows_count}, "
        f"preference={route.value} from {preference_source}"
    )


def _emit_zero_count_hint(
    *,
    console: Console,
    api_keys_configured: bool,
    show_unavailable: bool,
) -> None:
    """Issue #253: 0 件表示時に原因と次の手を提示する hint。

    ADR 0020 英日併記 (英 1 行目 / 日 2 行目)。Rich ``[yellow]`` スタイル、
    exit code は 0 維持。``--log-level DEBUG`` 案内は含めず 2 行に収める。
    """
    if not api_keys_configured and not show_unavailable:
        # シナリオ A: API key が 1 つも読み込まれていない (未設定 or 読まれていない)
        console.print(
            "[yellow]Hint: No API keys were loaded from config. "
            "Either no keys are set, or the config file is not being read. "
            "Pass --show-unavailable to list all registered models regardless.[/yellow]"
        )
        console.print(
            "[yellow]ヒント: config から API キーを 1 つも読み込めませんでした。"
            "未設定か、config ファイルが読まれていない可能性があります。"
            "--show-unavailable で登録済みの全モデルを表示できます。[/yellow]"
        )
    elif not show_unavailable:
        # シナリオ B: API key は読み込めているが filter で全件消えた
        console.print(
            "[yellow]Hint: No models matched the current filters. "
            "Try --show-unavailable, --type all, or --route all.[/yellow]"
        )
        console.print(
            "[yellow]ヒント: 現在のフィルタ条件に一致するモデルがありません。"
            "--show-unavailable / --type all / --route all を試してください。[/yellow]"
        )
    else:
        # シナリオ C: --show-unavailable 付きでも 0 件 = registry 自体が空
        console.print(
            "[yellow]Hint: No entries in the registry match --type/--category. "
            "Run 'lorairo-cli models refresh' to update the model registry.[/yellow]"
        )
        console.print(
            "[yellow]ヒント: --type / --category 条件に一致するモデルが registry に"
            "ありません。'lorairo-cli models refresh' で registry を更新してください。[/yellow]"
        )
