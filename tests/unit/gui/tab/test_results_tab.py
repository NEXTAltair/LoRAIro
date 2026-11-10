"""ResultsTabWidget の GUI テスト (Epic #867 / #870)。"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea

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
def test_results_tab_forwards_background_status_and_saved_result_notifications(qtbot, staging) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)
    widget.hide()

    with qtbot.waitSignal(widget.running_status_changed) as emission:
        widget.annotation_review_widget.running_status_changed.emit("チェック中 1 / 2 枚")
    assert emission.args == ["チェック中 1 / 2 枚"]
    with qtbot.waitSignal(widget.review_result_saved) as emission:
        widget.annotation_review_widget.review_result_saved.emit(42)
    assert emission.args == [42]
    with qtbot.waitSignal(widget.running_status_changed) as emission:
        widget.annotation_review_widget.running_status_changed.emit("")
    assert emission.args == [""]


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
    db.mark_images_reviewed_batch.return_value = 3
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging)
    qtbot.addWidget(widget)

    widget.results_widget.accept_clean_requested.emit([1, 2, 3])

    db.mark_images_reviewed_batch.assert_called_once_with([1, 2, 3], reviewed=True)
    db.mark_image_reviewed.assert_not_called()


@pytest.mark.gui
def test_accept_clean_falls_back_to_per_item_when_batch_unavailable(
    qtbot, staging: StagingStateManager
) -> None:
    db = MagicMock()
    db.mark_images_reviewed_batch = None
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


@pytest.mark.gui
def test_accept_updates_in_place_without_requerying_db_or_resetting_scroll(qtbot) -> None:
    """単一 accept は DB 再クエリ・全行破棄・スクロール先頭戻し・CLEAN 再抽選を起こさない (#1545)。"""
    ids = list(range(1, 31))
    staging_mock = MagicMock()
    staging_mock.get_staged_items.return_value = OrderedDict(
        (i, (f"img_{i:02d}.png", f"/p/img_{i:02d}.png")) for i in ids
    )
    db = MagicMock()
    db.get_images_metadata_batch.return_value = [
        {
            "id": i,
            "uuid": f"uuid{i:04d}",
            "width": 512,
            "height": 512,
            "reviewed_at": None,
            "filename": f"img_{i:02d}.png",
            "stored_image_path": f"/p/img_{i:02d}.png",
        }
        for i in ids
    ]
    # #1 は issue あり (タグ無し)、#2..#30 は clean (タグ・スコアあり)
    db.get_image_annotations_batch.return_value = {
        i: {
            "tags": []
            if i == 1
            else [{"tag": "cat", "confidence_score": 0.9, "model_id": 1, "rejected_at": None}],
            "captions": [],
            "scores": [{"score": 0.8}],
            "score_labels": [],
            "ratings": [],
            "quality_summary": {},
        }
        for i in ids
    }
    db.get_low_res_image_paths_batch.return_value = {}
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging_mock)
    qtbot.addWidget(widget)
    widget.resize(600, 300)
    widget.show()

    widget.refresh()
    qtbot.waitUntil(lambda: widget.results_widget.findChild(object, "resultsRow_15") is not None)

    row_1_before = widget.results_widget.findChild(object, "resultsRow_1")
    row_2_before = widget.results_widget.findChild(object, "resultsRow_2")
    sample_before = list(widget.results_widget._clean_plan.sample_image_ids)
    scroll = widget.results_widget.findChild(QScrollArea)
    assert scroll is not None
    scroll.verticalScrollBar().setMaximum(500)
    scroll.verticalScrollBar().setValue(180)

    db.get_images_metadata_batch.reset_mock()
    db.get_image_annotations_batch.reset_mock()

    widget.results_widget.accept_requested.emit(1)

    db.mark_image_reviewed.assert_called_once_with(1, reviewed=True)
    # 1 件 accept で全件の metadata / annotations を再取得しない
    db.get_images_metadata_batch.assert_not_called()
    db.get_image_annotations_batch.assert_not_called()
    # 行ウィジェットは破棄されず同一インスタンスのままボタンと状態だけ更新される
    assert widget.results_widget.findChild(object, "resultsRow_1") is row_1_before
    assert widget.results_widget.findChild(object, "resultsRow_2") is row_2_before
    assert widget.results_widget.findChild(object, "resultsUnacceptButton_1") is not None
    assert widget.results_widget.findChild(object, "resultsAcceptButton_1") is None
    # スクロール位置と CLEAN 監査の抽出サンプルが維持される
    assert scroll.verticalScrollBar().value() == 180
    assert list(widget.results_widget._clean_plan.sample_image_ids) == sample_before


@pytest.mark.gui
def test_refresh_displays_filename_and_supports_keyboard_accept(qtbot) -> None:
    """行ヘッダにファイル名を表示し、上下キー + Enter で選択行を accept できる (#1545)。"""
    ids = [10, 20]
    staging_mock = MagicMock()
    staging_mock.get_staged_items.return_value = OrderedDict(
        [(10, ("hero.png", "/imgs/hero.png")), (20, ("villain.png", "/imgs/villain.png"))]
    )
    db = MagicMock()
    db.get_images_metadata_batch.return_value = [
        {
            "id": 10,
            "uuid": "aaaa1111",
            "width": 640,
            "height": 480,
            "reviewed_at": None,
            "filename": "hero.png",
            "stored_image_path": "/imgs/hero.png",
        },
        {
            "id": 20,
            "uuid": "bbbb2222",
            "width": 800,
            "height": 600,
            "reviewed_at": None,
            "filename": "villain.png",
            "stored_image_path": "/imgs/villain.png",
        },
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
    db.get_low_res_image_paths_batch.return_value = {}
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging_mock)
    qtbot.addWidget(widget)

    widget.refresh()

    ident_10 = widget.results_widget.findChild(QLabel, "resultsRowIdent_10")
    ident_20 = widget.results_widget.findChild(QLabel, "resultsRowIdent_20")
    assert ident_10 is not None and "hero.png" in ident_10.text()
    assert ident_20 is not None and "villain.png" in ident_20.text()

    # 初期フォーカスは先頭行 (#10)、Down キーで 2 行目 (#20) へ移動し Enter で accept
    assert widget.results_widget.focused_image_id == 10
    qtbot.keyClick(widget, Qt.Key.Key_Down)
    assert widget.results_widget.focused_image_id == 20
    qtbot.keyClick(widget, Qt.Key.Key_Return)
    db.mark_image_reviewed.assert_called_once_with(20, reviewed=True)
    assert widget.results_widget.findChild(object, "resultsUnacceptButton_20") is not None


def test_keyboard_navigation_does_not_forward_when_focus_in_review_batch_widget(qtbot):
    """フォーカスが _review_batch_widget 内にある時はキー入力を ResultsWidget へ転送しない (#1545 Codex P2)。"""
    ids = [10, 20]
    staging_mock = MagicMock()
    staging_mock.get_staged_items.return_value = OrderedDict(
        [(10, ("hero.png", "/imgs/hero.png")), (20, ("villain.png", "/imgs/villain.png"))]
    )
    staging_mock.get_all_staged_ids.return_value = ids
    db = MagicMock()
    db.get_images_metadata_batch.return_value = [
        {
            "id": 10,
            "uuid": "u10",
            "width": 800,
            "height": 600,
            "reviewed_at": None,
            "stored_image_path": "/imgs/hero.png",
        },
        {
            "id": 20,
            "uuid": "u20",
            "width": 800,
            "height": 600,
            "reviewed_at": None,
            "stored_image_path": "/imgs/villain.png",
        },
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
    db.get_low_res_image_paths_batch.return_value = {}
    widget = ResultsTabWidget(db_manager=db, staging_state_manager=staging_mock)
    qtbot.addWidget(widget)
    widget.refresh()

    widget._annotation_review_widget.setFocus()
    assert widget.results_widget.focused_image_id == 10
    qtbot.keyClick(widget, Qt.Key.Key_Down)
    # フォーカス行は 10 のまま変わらない
    assert widget.results_widget.focused_image_id == 10
