"""ResultsTabWidget の GUI テスト (Epic #867 / #870)。"""

from __future__ import annotations

from collections import OrderedDict
from unittest.mock import MagicMock

import pytest

from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.results_tab import ResultsTabWidget
from lorairo.gui.widgets.results_widget import ResultsWidget


@pytest.fixture
def staging() -> StagingStateManager:
    return StagingStateManager()


@pytest.mark.gui
def test_results_tab_hosts_results_widget(qtbot, staging: StagingStateManager) -> None:
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    assert isinstance(widget.results_widget, ResultsWidget)
    assert widget.results_widget.parent() is widget


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
def test_resolve_thumbnail_path_prefers_low_res(qtbot, staging: StagingStateManager) -> None:
    """低解像度処理済み画像パスがあればそれを優先する (Issue #1104 / #1140 バッチ化)。"""
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    assert widget._resolve_thumbnail_path({"stored_image_path": "/orig.png"}, "/low.png") == "/low.png"


@pytest.mark.gui
def test_resolve_thumbnail_path_falls_back_to_stored(qtbot, staging: StagingStateManager) -> None:
    """低解像度画像が無ければオリジナルの stored path にフォールバックする (Issue #1104)。"""
    widget = ResultsTabWidget(db_manager=MagicMock(), staging_state_manager=staging)
    qtbot.addWidget(widget)

    assert widget._resolve_thumbnail_path({"stored_image_path": "/orig.png"}, None) == "/orig.png"


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
