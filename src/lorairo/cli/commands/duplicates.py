"""Read-only duplicate report, registered under the images command group."""

from dataclasses import asdict

import typer

from lorairo.cli._boundary import command_boundary
from lorairo.cli._console import make_console
from lorairo.cli._emit import emit_item, emit_result
from lorairo.cli._output_mode import is_json_mode
from lorairo.public_api.duplicate_report import report_duplicates
from lorairo.public_api.review import MAX_REVIEW_IMAGES
from lorairo.services.duplicate_report_service import (
    DEFAULT_MAX_DISTANCE,
    MAX_REPORT_LIMIT,
    DuplicateReport,
)

console = make_console()
# 代表 ID を stdout に純粋な ID 一覧として出す間、要約と警告はここへ回す。
err_console = make_console(stderr=True)

DEFAULT_REPORT_LIMIT = 100
_CLUSTER_OUTPUT_KEYS = frozenset({"limit", "returned_clusters", "clusters_truncated"})

_REPRESENTATIVE_NOTE = (
    "Representatives are reference only (largest pixel count, ties by smallest image ID); "
    "do not treat a representative's result as evidence for other images in its cluster."
)


def _emit_representatives(project: str, result: DuplicateReport) -> None:
    """各クラスタの代表だけを全クラスタ分出す。単独画像は含めない。

    --limit は適用しない。切り詰めると 500 クラスタ超で残りの代表に到達できなくなるため、
    全件 (プロジェクト上限 10,000 枚から高々 5,000 件) を出し、review 側の 500 枚上限は
    review run が RESULT_SET_TOO_LARGE で明示する。
    """
    representatives = result.representatives
    over_review_limit = len(representatives) > MAX_REVIEW_IMAGES
    if is_json_mode():
        for representative in representatives:
            emit_item(asdict(representative))
        emit_result(
            "Duplicate cluster representatives complete",
            project=project,
            read_only=True,
            status="success",
            representatives_only=True,
            representative_count=len(representatives),
            review_max_images=MAX_REVIEW_IMAGES,
            exceeds_review_max_images=over_review_limit,
            reference_only=True,
            # 出力上限に関する値はクラスタ報告用で、全件出力する代表とは無関係。
            **{key: value for key, value in result.summary().items() if key not in _CLUSTER_OUTPUT_KEYS},
        )
        return
    # stdout は 1 行 1 ID のみ。そのまま `review run --image-ids-file` に渡せる。
    for representative in representatives:
        print(representative.image_id)
    err_console.print(
        f"Representatives: {len(representatives)} clusters "
        f"({result.unclustered_images} unclustered images excluded)",
        markup=False,
    )
    if over_review_limit:
        err_console.print(
            f"Warning: `review run` accepts at most {MAX_REVIEW_IMAGES} images per run; "
            f"split this list (for example `split -l {MAX_REVIEW_IMAGES}`).",
            markup=False,
        )
    err_console.print(_REPRESENTATIVE_NOTE, markup=False)


def report(
    project: str = typer.Option(..., "--project", "-p", help="Project name"),
    max_distance: int = typer.Option(
        DEFAULT_MAX_DISTANCE,
        "--max-distance",
        min=0,
        max=64,
        help="Maximum differing bits in saved 64-bit pHashes (default 4; candidate review only)",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        max=MAX_REPORT_LIMIT,
        help=(
            f"Maximum clusters and members per cluster to show (default {DEFAULT_REPORT_LIMIT}; "
            "not allowed with --representatives)"
        ),
    ),
    representatives: bool = typer.Option(
        False,
        "--representatives",
        help=(
            "Output only one representative image per duplicate cluster, for every cluster (largest "
            "pixel count, ties by smallest image ID); singletons are excluded. Plain mode prints one "
            "image ID per line for `review run --image-ids-file`. Reference only."
        ),
    ),
) -> None:
    """Report approximate duplicate candidates from saved pHashes without changing images.

    Scans the whole project, up to 10,000 images. Connected clusters can contain
    endpoints farther apart than the threshold. Missing or invalid hashes are counted.
    """
    with command_boundary():
        if representatives and limit is not None:
            raise typer.BadParameter(
                "--limit は --representatives と併用できません (代表は全クラスタ分を出力します)。"
            )
        result = report_duplicates(
            project, max_distance=max_distance, limit=DEFAULT_REPORT_LIMIT if limit is None else limit
        )
        if representatives:
            _emit_representatives(project, result)
        elif is_json_mode():
            for cluster in result.clusters:
                emit_item(asdict(cluster))
            emit_result(
                "Duplicate candidate report complete",
                project=project,
                read_only=True,
                status="success",
                **result.summary(),
            )
        else:
            console.print(
                f"Duplicate candidates: {result.cluster_count} clusters, "
                f"{result.clustered_images} of {result.total_images} images"
            )
            for cluster in result.clusters:
                console.print(str(asdict(cluster)), markup=False)
            console.print(str(result.summary()), markup=False)
            console.print("Candidates only; connected chains may exceed the threshold at their endpoints.")
