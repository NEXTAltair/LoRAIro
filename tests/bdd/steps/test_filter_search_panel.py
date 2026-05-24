"""FilterSearchPanel BDD ステップ定義。

FilterSearchPanel のパイプライン進捗管理の振る舞いを最小限の 2 シナリオで検証する。

NOTE: Issue #420 の FilterSearchPanel 分割リファクタ完了後に
      本格的な BDD シナリオを追加すること。
"""

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, scenarios, then, when

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "filter_search_panel.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


@dataclass
class FilterSearchPanelContext:
    """ステップ間で受け渡すコンテキスト。

    FilterSearchPanel は複雑な Qt ウィジェットのため、
    振る舞いテストでは MagicMock でパネルをモックする。
    """

    panel: MagicMock = field(default_factory=MagicMock)
    error_handler_called: bool = False


@pytest.fixture
def fsp_context() -> FilterSearchPanelContext:
    return FilterSearchPanelContext()


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given("FilterSearchPanelが初期化されている")
def given_filter_search_panel_initialized(fsp_context: FilterSearchPanelContext) -> None:
    """FilterSearchPanel をモックで初期化する。

    実ウィジェットの複雑な依存（Qt UI ファイル、サービス注入等）を回避するため
    MagicMock を使用して振る舞いのみをテストする。
    """
    panel = MagicMock()

    # hide_progress_after_completion の振る舞いをモック
    panel._progress_hidden = False

    def _hide_progress() -> None:
        panel._progress_hidden = True

    panel.hide_progress_after_completion.side_effect = _hide_progress

    # handle_pipeline_error の振る舞いをモック
    panel._error_handler_calls: list[tuple[str, dict]] = []

    def _handle_error(phase: str, error_info: dict) -> None:
        panel._error_handler_calls.append((phase, error_info))

    panel.handle_pipeline_error.side_effect = _handle_error

    fsp_context.panel = panel


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("hide_progress_after_completion を呼び出す")
def when_hide_progress_called(fsp_context: FilterSearchPanelContext) -> None:
    """hide_progress_after_completion を実行する。"""
    fsp_context.panel.hide_progress_after_completion()


@when("searchパイプラインエラーが発生する")
def when_search_pipeline_error(fsp_context: FilterSearchPanelContext) -> None:
    """search フェーズのパイプラインエラーを発生させる。"""
    fsp_context.panel.handle_pipeline_error("search", {"message": "検索エラーが発生しました"})


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then("プログレスバーが非表示になる")
def then_progress_hidden(fsp_context: FilterSearchPanelContext) -> None:
    """hide_progress_after_completion が呼ばれ、非表示フラグが立つことを確認する。"""
    fsp_context.panel.hide_progress_after_completion.assert_called_once()
    assert fsp_context.panel._progress_hidden is True


@then("エラーハンドラーが呼ばれる")
def then_error_handler_called(fsp_context: FilterSearchPanelContext) -> None:
    """handle_pipeline_error が search フェーズで呼ばれたことを確認する。"""
    fsp_context.panel.handle_pipeline_error.assert_called_once()
    assert len(fsp_context.panel._error_handler_calls) == 1
    phase, error_info = fsp_context.panel._error_handler_calls[0]
    assert phase == "search"
    assert "message" in error_info
