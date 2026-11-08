"""image_comparison (Issue #1399 / #1484) の Qt 非依存ロジックのテスト。"""

from datetime import datetime
from typing import Any

import pytest

from lorairo.services.image_comparison import (
    Availability,
    ComparisonSelection,
    ComparisonSnapshot,
    DiffKind,
    ImageComparisonService,
    Side,
    compare_snapshots,
    diff_caption,
    diff_tags,
    snapshot_from_metadata,
)

pytestmark = pytest.mark.unit


# --- diff_tags -------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "availability", "common", "left_only", "right_only"),
    [
        (["a", "b", "c"], ["b", "c", "d"], Availability.BOTH, ("b", "c"), ("a",), ("d",)),
        (["a", "b"], ["a", "b"], Availability.BOTH, ("a", "b"), (), ()),
        (["a"], ["b"], Availability.BOTH, (), ("a",), ("b",)),
        # 重複は 1 つにまとめ、左右それぞれの元の並びを保つ
        (["c", "a", "c"], ["a", "x", "c"], Availability.BOTH, ("c", "a"), (), ("x",)),
        # 片側にタグが無いときは比較しない (片側だけ・共通と誤表示しない)
        ([], ["a", "b"], Availability.LEFT_MISSING, (), (), ()),
        (["a"], [], Availability.RIGHT_MISSING, (), (), ()),
        ([], [], Availability.BOTH_MISSING, (), (), ()),
        # 大文字小文字の違いは別タグとして扱う (原文のまま比較する)
        (["Cat"], ["cat"], Availability.BOTH, (), ("Cat",), ("cat",)),
    ],
)
def test_diff_tags_table(
    left: list[str],
    right: list[str],
    availability: Availability,
    common: tuple[str, ...],
    left_only: tuple[str, ...],
    right_only: tuple[str, ...],
) -> None:
    result = diff_tags(left, right)
    assert result.availability is availability
    assert result.common == common
    assert result.left_only == left_only
    assert result.right_only == right_only


def test_diff_tags_identical_flag() -> None:
    assert diff_tags(["a", "b"], ["b", "a"]).identical is True
    assert diff_tags(["a"], ["a", "b"]).identical is False
    # 両側欠落は「同じ」ではない
    assert diff_tags([], []).identical is False


# --- diff_caption ----------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "availability", "identical"),
    [
        ("a cat sitting", "a cat sitting", Availability.BOTH, True),
        ("a cat sitting", "a dog sitting", Availability.BOTH, False),
        (None, "a dog", Availability.LEFT_MISSING, False),
        ("a cat", None, Availability.RIGHT_MISSING, False),
        (None, None, Availability.BOTH_MISSING, False),
        # 空文字は「キャプション未登録」として扱い、空文字同士を同一と言わない
        ("", "", Availability.BOTH_MISSING, False),
        ("", "a", Availability.LEFT_MISSING, False),
        # 改行の違いも差分として残す (整形しない)
        ("line1\nline2", "line1 line2", Availability.BOTH, False),
    ],
)
def test_diff_caption_availability_table(
    left: str | None, right: str | None, availability: Availability, identical: bool
) -> None:
    result = diff_caption(left, right)
    assert result.availability is availability
    assert result.identical is identical
    if availability is not Availability.BOTH:
        assert result.segments == ()


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("a cat sitting on a chair", "a dog sitting on the chair."),
        ("line1\nline2\n\n  indented", "line1 line2\n  indented!"),
        ("猫が椅子に座っている", "犬が椅子に座っている。"),
        ("same", "same"),
        ("x" * 3000 + " end", "x" * 3000 + " fin"),
    ],
)
def test_diff_caption_preserves_original_text(left: str, right: str) -> None:
    """差分の左側部分を連結すると左の原文、右側部分なら右の原文に一致する。"""
    result = diff_caption(left, right)
    assert "".join(seg.left for seg in result.segments) == left
    assert "".join(seg.right for seg in result.segments) == right


def test_diff_caption_marks_word_change() -> None:
    result = diff_caption("a cat sitting", "a dog sitting")
    kinds = [(seg.kind, seg.left, seg.right) for seg in result.segments]
    assert (DiffKind.REPLACE, "cat", "dog") in kinds
    assert kinds[0] == (DiffKind.EQUAL, "a ", "a ")


def test_diff_caption_japanese_is_character_level() -> None:
    result = diff_caption("猫が座る", "犬が座る")
    assert result.segments[0].kind is DiffKind.REPLACE
    assert (result.segments[0].left, result.segments[0].right) == ("猫", "犬")


# --- snapshot_from_metadata ------------------------------------------------


def _metadata(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 7,
        "stored_image_path": "image_dataset/original_images/2026/a.webp",
        "original_image_path": "/src/a.png",
        "width": 1024,
        "height": 768,
        "tags": [
            {"tag": "cat", "model_name": "wd-tagger", "source": "AI", "is_edited_manually": False},
            {"tag": "sitting", "model_name": "Unknown", "source": "Manual", "is_edited_manually": True},
            {"tag": "cat", "model_name": "other-tagger", "source": "AI", "is_edited_manually": False},
        ],
        "captions": [
            {
                "caption": "old caption",
                "model_name": "blip",
                "is_edited_manually": False,
                "created_at": datetime(2026, 1, 1),
            },
            {
                "caption": "new caption",
                "model_name": "gpt",
                "is_edited_manually": True,
                "created_at": datetime(2026, 2, 1),
            },
        ],
        "caption_text": "new caption",
    }
    base.update(overrides)
    return base


def test_snapshot_from_metadata_collects_tags_and_origins() -> None:
    snapshot = snapshot_from_metadata(7, _metadata())
    assert snapshot.found is True
    assert snapshot.image_id == 7
    assert snapshot.tag_names == ("cat", "sitting")
    assert snapshot.tags[0].origins == ("wd-tagger (AI)", "other-tagger (AI)")
    assert snapshot.tags[1].origins == ("手動",)
    assert snapshot.caption == "new caption"
    assert snapshot.caption_origin == "gpt (手動編集)"
    assert snapshot.stored_image_path == "image_dataset/original_images/2026/a.webp"
    assert snapshot.original_file_name == "a.png"
    assert snapshot.image_size == (1024, 768)


def test_snapshot_from_metadata_missing_annotations_are_none() -> None:
    snapshot = snapshot_from_metadata(7, _metadata(tags=[], captions=[], caption_text=""))
    assert snapshot.tags == ()
    assert snapshot.caption is None
    assert snapshot.caption_origin is None


def test_snapshot_from_metadata_none_means_not_found() -> None:
    snapshot = snapshot_from_metadata(99, None)
    assert snapshot.found is False
    assert snapshot.image_id == 99
    assert snapshot.tags == ()
    assert snapshot.caption is None


def test_snapshot_provenance_lines_summarize_sources() -> None:
    lines = snapshot_from_metadata(7, _metadata()).provenance_lines()
    joined = "\n".join(lines)
    assert "画像 ID: 7" in joined
    assert "a.png" in joined
    assert "wd-tagger (AI) ×1" in joined
    assert "手動 ×1" in joined
    assert "gpt (手動編集)" in joined


def test_snapshot_provenance_lines_mark_missing() -> None:
    lines = snapshot_from_metadata(7, _metadata(tags=[], captions=[], caption_text="")).provenance_lines()
    joined = "\n".join(lines)
    assert "タグ: なし" in joined
    assert "キャプション: なし" in joined
    not_found = "\n".join(snapshot_from_metadata(5, None).provenance_lines())
    assert "見つかりません" in not_found


# --- compare_snapshots / service -------------------------------------------


def test_compare_snapshots_combines_tag_and_caption_diff() -> None:
    left = snapshot_from_metadata(1, _metadata(id=1))
    right = snapshot_from_metadata(
        2, _metadata(id=2, tags=[{"tag": "dog", "source": "AI", "model_name": "m"}], caption_text="x")
    )
    result = compare_snapshots(left, right)
    assert result.left_id == 1
    assert result.right_id == 2
    assert result.tags.left_only == ("cat", "sitting")
    assert result.tags.right_only == ("dog",)
    assert result.caption.availability is Availability.BOTH


class _FakeMetadataSource:
    def __init__(self, data: dict[int, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[int] = []

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        self.calls.append(image_id)
        return self.data.get(image_id)


def test_service_load_snapshot_reads_metadata_without_writes() -> None:
    source = _FakeMetadataSource({3: _metadata(id=3)})
    service = ImageComparisonService(source)
    snapshot = service.load_snapshot(3)
    assert isinstance(snapshot, ComparisonSnapshot)
    assert snapshot.found is True
    assert source.calls == [3]
    assert service.load_snapshot(4).found is False


# --- ComparisonSelection ---------------------------------------------------


def test_selection_initial_picks_first_two_candidates() -> None:
    selection = ComparisonSelection([5, 6, 7])
    assert (selection.left_id, selection.right_id) == (5, 6)


def test_selection_deduplicates_and_requires_two() -> None:
    with pytest.raises(ValueError):
        ComparisonSelection([5, 5])
    selection = ComparisonSelection([5, 5, 6])
    assert selection.candidates == (5, 6)


def test_selection_swap_moves_pin_with_image() -> None:
    selection = ComparisonSelection([1, 2, 3])
    selection.set_pinned(Side.LEFT, True)
    selection.swap()
    assert (selection.left_id, selection.right_id) == (2, 1)
    assert selection.is_pinned(Side.RIGHT) is True
    assert selection.is_pinned(Side.LEFT) is False


@pytest.mark.parametrize(
    ("candidates", "side", "delta", "expected"),
    [
        ([1, 2, 3, 4], Side.RIGHT, 1, (1, 3)),
        ([1, 2, 3, 4], Side.RIGHT, -1, (1, 4)),  # 2 → 1 は左と同じなので飛ばして 4
        ([1, 2, 3, 4], Side.LEFT, 1, (3, 2)),  # 1 → 2 は右と同じなので飛ばして 3
        ([1, 2], Side.RIGHT, 1, (1, 2)),  # 候補が他に無ければ変えない
    ],
)
def test_selection_step_skips_other_side(
    candidates: list[int], side: Side, delta: int, expected: tuple[int, int]
) -> None:
    selection = ComparisonSelection(candidates)
    selection.step(side, delta)
    assert (selection.left_id, selection.right_id) == expected


def test_selection_pinned_side_does_not_change() -> None:
    selection = ComparisonSelection([1, 2, 3])
    selection.set_pinned(Side.LEFT, True)
    assert selection.step(Side.LEFT, 1) is False
    assert selection.set_side(Side.LEFT, 3) is False
    assert selection.left_id == 1
    assert selection.step(Side.RIGHT, 1) is True
    assert selection.right_id == 3


def test_selection_set_side_rejects_other_side_image() -> None:
    selection = ComparisonSelection([1, 2, 3])
    assert selection.set_side(Side.RIGHT, 1) is False
    assert selection.set_side(Side.RIGHT, 9) is False
    assert selection.set_side(Side.RIGHT, 3) is True
    assert selection.right_id == 3
