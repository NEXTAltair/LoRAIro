"""ResultsTabWidget の GUI テスト (Epic #867 / #870)。"""

from __future__ import annotations

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
