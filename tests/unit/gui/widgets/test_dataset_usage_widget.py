"""「学習に使ったデータセット」表と、タグ欄の由来の印・絞り込み・強調の GUI テスト (#1647)。

`DatasetUsageWidget` は DB 非依存の表示専用ウィジェットで、行の選択で強調する要素を
Signal で上げる。詳細カラムは取得手段を配線したときだけ表を出し、行の選択をタグ欄
(`TagPanelWidget`) の強調へつなぐ。タグ欄は KOHYA_DATASET 由来 (source == "Dataset") の
chip に印を付け、由来で絞り込める。
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from lorairo.gui.widgets.dataset_usage_widget import DatasetUsageEntry, DatasetUsageWidget
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.gui.widgets.tag_panel_widget import TagPanelWidget

pytestmark = pytest.mark.gui

ENTRIES = [
    DatasetUsageEntry("raikou", "v06ps", "10_raikou", 10, ("1boy", "armor", "otogi")),
    DatasetUsageEntry("raikou", "v06ps", "10_raikousyouzoku1", 10, ("1boy", "japanese armor")),
    DatasetUsageEntry("raikou", "v01", "10_raikou", 10, ("1boy", "rating:safe")),
]

# 同一 canonical "1boy" は AI 行とデータセット行の 2 行を持つ (畳む前の行で由来を判定する)
TAG_ROWS = [
    {"tag": "1boy", "tag_id": None, "model_name": "wd", "source": "AI"},
    {"tag": "1boy", "tag_id": None, "model_name": "KOHYA_DATASET", "source": "Dataset"},
    {"tag": "armor", "tag_id": None, "model_name": "KOHYA_DATASET", "source": "Dataset"},
    {"tag": "japanese armor", "tag_id": None, "model_name": "KOHYA_DATASET", "source": "Dataset"},
    {"tag": "solo", "tag_id": None, "model_name": "wd", "source": "AI"},
    {"tag": "my note", "tag_id": None, "model_name": "MANUAL_EDIT", "source": "Manual"},
]


def _chip_states(panel: TagPanelWidget) -> dict[str, tuple[bool, str | None]]:
    return {chip.canonical: (chip.from_dataset, chip.highlight_state) for chip in panel._tag_chips}


@pytest.fixture
def usage(qtbot) -> DatasetUsageWidget:
    widget = DatasetUsageWidget()
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def panel(qtbot) -> TagPanelWidget:
    widget = TagPanelWidget()
    qtbot.addWidget(widget)
    widget.set_tags(TAG_ROWS, image_id=1)
    return widget


# --- DatasetUsageWidget ----------------------------------------------------


def test_usage_table_lists_dataset_version_folder_and_repeats(usage: DatasetUsageWidget) -> None:
    usage.set_entries(ENTRIES)

    table = usage._table
    rows = [
        tuple(table.item(row, column).text() for column in range(table.columnCount()))
        for row in range(table.rowCount())
    ]
    assert rows == [
        ("raikou", "v06ps", "10_raikou", "10"),
        ("raikou", "v06ps", "10_raikousyouzoku1", "10"),
        ("raikou", "v01", "10_raikou", "10"),
    ]
    assert usage._empty_label.isHidden() is True


def test_usage_empty_shows_none(usage: DatasetUsageWidget) -> None:
    usage.set_entries([])

    assert usage._table.isHidden() is True
    assert usage._empty_label.isHidden() is False


def test_usage_row_selection_emits_elements_and_clear_emits_none(qtbot, usage: DatasetUsageWidget) -> None:
    usage.set_entries(ENTRIES)

    with qtbot.waitSignal(usage.highlight_changed, timeout=1000) as selected:
        usage.select_row(2)
    assert selected.args == [{"1boy", "rating:safe"}]
    assert usage._clear_button.isEnabled() is True

    with qtbot.waitSignal(usage.highlight_changed, timeout=1000) as cleared:
        usage._clear_button.click()
    assert cleared.args == [None]
    assert usage.selected_row() is None


# --- TagPanelWidget: 由来の印・絞り込み・強調 ------------------------------


def test_dataset_origin_mark_uses_all_rows_before_folding(panel: TagPanelWidget) -> None:
    """同一 canonical に AI とデータセットの行があれば、畳んだ chip にデータセットの印を付ける。"""
    states = _chip_states(panel)
    assert {tag for tag, (from_dataset, _) in states.items() if from_dataset} == {
        "1boy",
        "armor",
        "japanese armor",
    }
    chip = next(c for c in panel._tag_chips if c.canonical == "armor")
    assert chip.text().startswith("▣ ")
    assert "由来: 学習データセット" in chip.toolTip()
    assert panel._origin_filter_bar.isHidden() is False


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("all", {"1boy", "armor", "japanese armor", "solo", "my note"}),
        ("dataset", {"1boy", "armor", "japanese armor"}),
        ("ai", {"1boy", "solo"}),
        ("manual", {"my note"}),
    ],
)
def test_origin_filter_narrows_chips(panel: TagPanelWidget, origin: str, expected: set[str]) -> None:
    panel._origin_filter_control._buttons[origin].click()

    assert panel.origin_filter() == origin
    assert {chip.canonical for chip in panel._tag_chips} == expected


@pytest.mark.parametrize(
    ("origin", "expected_rejected"),
    [
        ("all", {"old dataset tag", "old ai tag"}),
        ("dataset", {"old dataset tag"}),
        ("ai", {"old ai tag"}),
        ("manual", set()),
    ],
)
def test_origin_filter_keeps_rejected_chip_of_matching_origin(
    panel: TagPanelWidget, origin: str, expected_rejected: set[str]
) -> None:
    """Codex P2 (PR #1655): 無効化 (soft-reject) したタグも由来で絞り込み、破線 chip を残す。"""
    panel.set_rejected_tags(
        [
            {"tag": "old dataset tag", "reject_reason": "not_needed", "source": "Dataset"},
            {"tag": "old ai tag", "reject_reason": "not_needed", "source": "AI"},
        ]
    )

    panel._origin_filter_control._buttons[origin].click()

    shown = {chip.canonical for chip in panel._tag_chips}
    assert shown & {"old dataset tag", "old ai tag"} == expected_rejected


def test_highlight_marks_hits_and_dims_others_then_clears(panel: TagPanelWidget) -> None:
    panel.set_highlight_tags({"1boy", "armor", "otogi"})

    states = _chip_states(panel)
    assert {tag: state for tag, (_, state) in states.items()} == {
        "1boy": "hit",
        "armor": "hit",
        "japanese armor": "dim",
        "solo": "dim",
        "my note": "dim",
    }

    panel.set_highlight_tags(None)
    assert all(state is None for _, state in _chip_states(panel).values())


def test_highlight_is_reset_when_another_image_is_shown(panel: TagPanelWidget) -> None:
    panel.set_highlight_tags({"armor"})

    panel.set_tags(TAG_ROWS, image_id=2)

    assert all(state is None for _, state in _chip_states(panel).values())


# --- SelectedImageDetailsWidget との結合 ----------------------------------


class TestSelectedImageDetailsDatasetUsage:
    @pytest.fixture
    def details(self, qtbot) -> SelectedImageDetailsWidget:
        widget = SelectedImageDetailsWidget()
        qtbot.addWidget(widget)
        return widget

    def test_section_hidden_until_provider_injected(self, details: SelectedImageDetailsWidget) -> None:
        assert details._dataset_usage_widget.isHidden() is True

    def test_selecting_row_changes_tag_highlight(self, details: SelectedImageDetailsWidget) -> None:
        provider = Mock(return_value=ENTRIES)
        details.set_dataset_usage_provider(provider)

        details._on_image_data_received({"id": 55, "stored_image_path": "dummy.png", "tags": TAG_ROWS})

        provider.assert_called_with(55)
        usage = details._dataset_usage_widget
        assert usage.isHidden() is False
        assert len(usage.entries()) == 3
        tag_panel = details.annotation_display._tag_panel

        usage.select_row(1)
        assert {c.canonical for c in tag_panel._tag_chips if c.highlight_state == "hit"} == {
            "1boy",
            "japanese armor",
        }

        usage.select_row(0)
        assert {c.canonical for c in tag_panel._tag_chips if c.highlight_state == "hit"} == {
            "1boy",
            "armor",
        }

        usage.clear_selection()
        assert all(c.highlight_state is None for c in tag_panel._tag_chips)

    def test_provider_error_leaves_table_empty(self, details: SelectedImageDetailsWidget) -> None:
        details.set_dataset_usage_provider(Mock(side_effect=SQLAlchemyError("boom")))

        details._on_image_data_received({"id": 55, "stored_image_path": "dummy.png"})

        assert details._dataset_usage_widget.entries() == []


def test_search_tab_wires_usage_rows_with_txt_elements(monkeypatch: pytest.MonkeyPatch) -> None:
    """検索タブの配線は版の利用行を表の行に変え、強調には .txt の要素だけを使う。"""
    from types import SimpleNamespace

    from lorairo.database.repository.dataset import ImageDatasetUsage, LearningTextSnapshot
    from lorairo.gui.tab import search_tab

    usage_row = ImageDatasetUsage(
        image_id=5,
        dataset_id=1,
        dataset_name="raikou",
        version_name="v06ps",
        version_id=3,
        parent_version_id=None,
        folder_id=9,
        dir_name="10_raikou",
        folder_name="raikou",
        num_repeats=10,
        trigger_word=None,
        file_stem="a",
        texts=[
            LearningTextSnapshot(1, ".txt", "1boy, armor", ["1boy", "armor"], False),
            LearningTextSnapshot(2, ".caption", "a knight", ["a knight"], False),
        ],
    )
    repository = Mock()
    repository.list_image_usage.return_value = [usage_row]
    monkeypatch.setattr(search_tab, "DatasetRepository", Mock(return_value=repository))
    details = Mock()
    fake_tab = SimpleNamespace(
        _db_manager=SimpleNamespace(image_repo=SimpleNamespace(session_factory=object())),
        _selected_image_details_widget=details,
    )

    search_tab.SearchTabWidget._wire_dataset_usage(fake_tab)

    (provider,) = details.set_dataset_usage_provider.call_args.args
    assert provider(5) == [DatasetUsageEntry("raikou", "v06ps", "10_raikou", 10, ("1boy", "armor"))]
    repository.list_image_usage.assert_called_once_with(5)
