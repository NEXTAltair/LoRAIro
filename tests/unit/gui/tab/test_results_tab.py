"""ResultsTabWidget の GUI テスト (Epic #867 / #870)。"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.results_tab import ResultsTabWidget
from lorairo.gui.widgets.results_widget import ResultsWidget
from lorairo.gui.workers.annotation_review_results_loader import AnnotationReviewResultsLoader


@pytest.fixture
def staging() -> StagingStateManager:
    return StagingStateManager()


@pytest.mark.gui
def test_results_tab_hosts_results_widget(qtbot, staging: StagingStateManager) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    assert isinstance(widget.results_widget, ResultsWidget)
    assert widget.results_widget.parent() is widget
    assert widget.annotation_review_widget.isHidden()


@pytest.mark.gui
def test_results_tab_forwards_manual_review_for_saved_image(qtbot, staging: StagingStateManager) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.manual_review_requested) as emission:
        widget.annotation_review_widget.manual_review_requested.emit(42)

    assert emission.args == [42]


@pytest.mark.gui
def test_review_target_controls_forward_navigation_without_running_review(qtbot, staging) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)
    review = widget.annotation_review_widget

    with qtbot.waitSignal(widget.review_target_selection_requested):
        review.select_targets_button.click()

    state = MagicMock()
    state.get_image_by_id.return_value = {"stored_image_path": "/images/portrait.jpg"}
    staging.set_dataset_state_manager(state)
    staging.add_image_ids([42])
    assert "portrait.jpg" in review.target_names_label.text()
    with qtbot.waitSignal(widget.review_target_list_requested):
        review.target_list_button.click()

    assert not review.start_button.isEnabled()
    assert review._inflight_id is None


@pytest.mark.gui
def test_results_tab_updates_next_review_scope_when_staging_changes(qtbot, staging) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)
    staging.staged_images_changed.emit([4, 9])

    assert widget.annotation_review_widget._image_ids == (4, 9)
    assert not widget.annotation_review_widget.start_button.isEnabled()


@pytest.mark.gui
@pytest.mark.parametrize("visible", [False, True])
def test_saved_reviews_load_when_results_are_opened(qtbot, staging, visible: bool) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)
    service, store, manager = MagicMock(), MagicMock(), MagicMock()
    store.get_current_results.return_value = {}
    if visible:
        widget.show()

    widget.set_annotation_review_services(service, store, manager)

    if not visible:
        manager.start_worker.assert_not_called()
        store.get_current_results.assert_not_called()
        widget.show()
        widget.refresh()

    manager.start_worker.assert_called_once()
    loader = manager.start_worker.call_args.args[1]
    assert isinstance(loader, AnnotationReviewResultsLoader)
    loader.execute()
    store.get_current_results.assert_called_once_with(service, limit=500)
    service.review.assert_not_called()
    widget.shutdown()


@pytest.mark.gui
def test_accept_marks_image_reviewed(qtbot, staging: StagingStateManager) -> None:
    db = MagicMock()
    db.mark_image_reviewed.return_value = True
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging)
    qtbot.addWidget(widget)

    widget.results_widget.accept_requested.emit(42)

    db.mark_image_reviewed.assert_called_once_with(42, reviewed=True)


@pytest.mark.gui
def test_accept_clean_marks_all(qtbot, staging: StagingStateManager) -> None:
    db = MagicMock()
    db.mark_image_reviewed.return_value = True
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging)
    qtbot.addWidget(widget)

    widget.results_widget.accept_clean_requested.emit([1, 2, 3])

    assert db.mark_image_reviewed.call_count == 3


@pytest.mark.gui
def test_refresh_without_staging_items_clears(qtbot, staging: StagingStateManager) -> None:
    # 空のステージング集合では例外なく clear される
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    widget.refresh()  # 例外なし
    assert staging.count() == 0


@pytest.mark.gui
def test_resolve_thumbnail_path_prefers_low_res(
    qtbot, staging: StagingStateManager, tmp_path: Path
) -> None:
    """低解像度処理済み画像パスがあればそれを優先する (Issue #1104 / #1140 バッチ化)。"""
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    original = tmp_path / "orig.png"
    low_res = tmp_path / "low.png"
    assert widget._resolve_thumbnail_path({"stored_image_path": str(original)}, str(low_res)) == str(
        low_res
    )


@pytest.mark.gui
def test_resolve_thumbnail_path_falls_back_to_stored(
    qtbot, staging: StagingStateManager, tmp_path: Path
) -> None:
    """低解像度画像が無ければオリジナルの stored path にフォールバックする (Issue #1104)。"""
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    original = tmp_path / "orig.png"
    assert widget._resolve_thumbnail_path({"stored_image_path": str(original)}, None) == str(original)


@pytest.mark.gui
def test_resolve_thumbnail_path_none_when_absent(qtbot, staging: StagingStateManager) -> None:
    """低解像度も stored path も無ければ None を返す (Issue #1104)。"""
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    assert widget._resolve_thumbnail_path({}, None) is None


@pytest.mark.gui
def test_refresh_uses_batch_queries_not_per_image(qtbot) -> None:
    """refresh は per-image ループでなくバッチ DB クエリを使う (Issue #1140 N+1 解消)。

    DB 呼び出し回数が画像数に比例せず O(バッチ) であることを assert する。
    """
    ids = list(range(1, 101))
    # staging は get_staged_items() だけ使うため mock で 100 件を直接返す。
    staging_mock = MagicMock()
    staging_mock.get_staged_items.return_value = OrderedDict((i, (f"f{i}", f"/p{i}.png")) for i in ids)
    db = MagicMock()
    db.get_images_metadata_batch.return_value = [
        {
            "id": i,
            "uuid": f"u{i}",
            "width": 100,
            "height": 100,
            "reviewed_at": None,
            "stored_image_path": f"/p{i}.png",
        }
        for i in ids
    ]
    db.get_image_annotations_batch.return_value = {
        i: {
            "tags": [],
            "captions": [],
            "scores": [],
            "score_labels": [],
            "ratings": [],
            "quality_summary": {},
        }
        for i in ids
    }
    db.get_low_res_image_paths_batch.return_value = {i: f"/low{i}.png" for i in ids}
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging_mock)
    qtbot.addWidget(widget)

    widget.refresh()

    # バッチ API は画像数 100 に対しても各 1 回だけ。
    assert db.get_images_metadata_batch.call_count == 1
    assert db.get_image_annotations_batch.call_count == 1
    assert db.get_low_res_image_paths_batch.call_count == 1
    # metadata バッチはアノテーションを二重取得しない (Codex #1143 P2-1)。
    db.get_images_metadata_batch.assert_called_once_with(ids, include_annotations=False)
    # 旧 per-image API は使わない (N+1 の温床)。
    db.get_image_metadata.assert_not_called()
    db.get_image_annotations.assert_not_called()
    db.get_low_res_image_path.assert_not_called()


@pytest.mark.gui
def test_refresh_degrade_skips_low_res_batch(qtbot) -> None:
    """500件以上の degrade 時は低解像度パスの一括取得をスキップする (Codex #1143 P2-3)。"""
    from lorairo.gui.widgets.results_widget import _VIRTUALIZE_THRESHOLD

    ids = list(range(1, _VIRTUALIZE_THRESHOLD + 1))
    staging_mock = MagicMock()
    staging_mock.get_staged_items.return_value = OrderedDict((i, (f"f{i}", f"/p{i}.png")) for i in ids)
    db = MagicMock()
    db.get_images_metadata_batch.return_value = [
        {
            "id": i,
            "uuid": f"u{i}",
            "width": 100,
            "height": 100,
            "reviewed_at": None,
            "stored_image_path": f"/p{i}.png",
        }
        for i in ids
    ]
    db.get_image_annotations_batch.return_value = {
        i: {
            "tags": [],
            "captions": [],
            "scores": [],
            "score_labels": [],
            "ratings": [],
            "quality_summary": {},
        }
        for i in ids
    }
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging_mock)
    qtbot.addWidget(widget)

    widget.refresh()

    # degrade 域では低解像度パスの一括クエリを走らせない (行を描かないため無駄)。
    db.get_low_res_image_paths_batch.assert_not_called()
