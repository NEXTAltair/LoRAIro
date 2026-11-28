"""プロジェクト横断コピーの確認ダイアログ・由来の表示・worker の単体テスト (Issue #1661)。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.gui.widgets.cross_project_search_dialog import CrossProjectCopyConfirmDialog
from lorairo.gui.widgets.image_origin_widget import ImageOriginEntry, ImageOriginWidget, format_origins
from lorairo.gui.workers.cross_project_workers import (
    TOO_MANY_RESULTS_REASON,
    CopyFailure,
    CrossProjectCopyOutcome,
    CrossProjectCopyWorker,
    CrossProjectSearchWorker,
)
from lorairo.public_api.exceptions import ResultSetTooLargeError
from lorairo.services.project_transfer_service import (
    ImageTransferItem,
    ImageTransferResult,
    ProjectSearchResult,
    SourceProject,
)

pytestmark = pytest.mark.unit


def _result(name: str, actions: list[str], *, dry_run: bool = True) -> ImageTransferResult:
    items = [
        ImageTransferItem(i + 1, f"u{i}", action, None if action == "copy" else 100 + i, 0)
        for i, action in enumerate(actions)
    ]
    return ImageTransferResult(name, None, items, dry_run=dry_run)


@pytest.mark.gui
def test_confirm_dialog_shows_plan_counts(qtbot) -> None:
    """確認ダイアログは複製・由来の追加・記録済みの件数を DsSummaryStat で出す。"""
    outcome = CrossProjectCopyOutcome(
        [_result("a", ["copy", "copy", "link"]), _result("b", ["already_linked"])],
        [CopyFailure("c", "schema")],
        dry_run=True,
    )
    dialog = CrossProjectCopyConfirmDialog(outcome, "target")
    qtbot.addWidget(dialog)

    assert (dialog.copy_stat.value(), dialog.link_stat.value(), dialog.already_stat.value()) == (
        "2",
        "1",
        "1",
    )
    assert dialog.confirm_button.isEnabled()


@pytest.mark.gui
def test_confirm_dialog_cannot_confirm_empty_plan(qtbot) -> None:
    """計画を作れたコピー元が無ければ確定できない。"""
    dialog = CrossProjectCopyConfirmDialog(CrossProjectCopyOutcome([], [CopyFailure("a", "x")]), "t")
    qtbot.addWidget(dialog)
    assert dialog.confirm_button.isEnabled() is False


def test_outcome_target_ids_skip_planned_new_images() -> None:
    """取り込み先の画像 ID は、決まっている分だけを重複なしで返す。"""
    outcome = CrossProjectCopyOutcome([_result("a", ["copy", "link", "link"])])
    assert outcome.target_image_ids() == [101, 102]


def test_copy_worker_keeps_going_after_one_source_fails() -> None:
    """コピー元 1 つが失敗しても、残りを続けて失敗として報告する。"""
    service = Mock()
    service.copy_images.side_effect = [LookupError("missing"), _result("b", ["copy"], dry_run=False)]
    sources = [SourceProject("a", Path("/a")), SourceProject("b", Path("/b"))]

    outcome = CrossProjectCopyWorker(
        service, [(sources[0], [1]), (sources[1], [2])], dry_run=False
    ).execute()

    assert [r.source_project_name for r in outcome.results] == ["b"]
    assert outcome.failures == [CopyFailure("a", "missing")]
    assert service.copy_images.call_args_list[1].kwargs == {"dry_run": False}


def test_search_worker_marks_project_with_too_many_results() -> None:
    """一致件数が上限を超えたプロジェクトは理由付きの空の結果にし、残りを続ける。"""
    service = Mock()
    ok = ProjectSearchResult("b", 1, [])
    service.search.side_effect = [ResultSetTooLargeError(matched=900, limit=500), [ok]]
    criteria = ImageFilterCriteria()
    sources = [SourceProject("a", Path("/a")), SourceProject("b", Path("/b"))]

    results = CrossProjectSearchWorker(sources, lambda: criteria, service=service).execute()

    assert results == [ProjectSearchResult("a", 900, [], unavailable_reason=TOO_MANY_RESULTS_REASON), ok]
    assert service.search.call_args.kwargs["skip_unavailable"] is True


@pytest.mark.gui
def test_origin_widget_formats_entries(qtbot) -> None:
    """由来はコピー元のプロジェクト名と画像 ID で示し、無ければコピー元なしと出す。"""
    widget = ImageOriginWidget()
    qtbot.addWidget(widget)
    assert widget.text() == "このプロジェクトで登録した画像 (コピー元なし)"
    widget.set_entries([ImageOriginEntry("a", 3), ImageOriginEntry("b", 9)])
    assert widget.text() == "a の画像 #3 からコピー\nb の画像 #9 からコピー"
    assert format_origins(widget.entries()) == "a #3, b #9"
    assert format_origins([]) == "-"
