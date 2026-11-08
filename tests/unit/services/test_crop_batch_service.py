"""crop_batch_service のユニットテスト (実 SQLite + 実ファイルシステム、Issue #1340 / ADR 0103)。

検出器は使わず、fake provider で「provider → 一括作成」の配線と部分失敗・再実行を固定する。
"""

import random
from collections.abc import Sequence
from pathlib import Path

import pytest
from PIL import Image

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.domain.crop_rect_provider import CropRectCandidate
from lorairo.domain.crop_request import CropRect
from lorairo.filesystem import FileSystemManager
from lorairo.services.crop_batch_service import CropBatchOutcome, run_crop_batch

pytestmark = pytest.mark.unit


class _FakeProvider:
    def __init__(self, candidates: dict[int, list[CropRectCandidate]]) -> None:
        self._candidates = candidates

    def candidates_for(self, parent_image_id: int) -> Sequence[CropRectCandidate]:
        return self._candidates.get(parent_image_id, [])


def _candidate(x: int, y: int, w: int, h: int, *, line: int, origin: str = "manual") -> CropRectCandidate:
    return CropRectCandidate(rect=CropRect(x, y, w, h), origin=origin, score=0.5, line=line)


@pytest.fixture
def parent_id(test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager, tmp_path: Path) -> int:
    """切り出し位置ごとに pHash が異なるノイズ画像 (400x300) を親として登録する。"""
    data = random.Random(1340).randbytes(400 * 300 * 3)
    source = tmp_path / "noise_parent.png"
    Image.frombytes("RGB", (400, 300), data).save(source)
    registered = test_db_manager.register_original_image(source, fs_manager)
    assert registered is not None
    test_db_manager.annotation_repo.update_manual_rating(registered[0], "R")
    return registered[0]


def _run(
    provider: _FakeProvider,
    parent_ids: list[int],
    db: ImageDatabaseManager,
    fsm: FileSystemManager,
    *,
    dry_run: bool = False,
) -> list[CropBatchOutcome]:
    streamed: list[CropBatchOutcome] = []
    outcomes = run_crop_batch(
        provider, parent_ids, db_manager=db, fsm=fsm, dry_run=dry_run, on_outcome=streamed.append
    )
    assert streamed == outcomes
    return outcomes


def test_creates_every_valid_candidate_and_copies_parent_rating(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    provider = _FakeProvider(
        {
            parent_id: [
                _candidate(0, 0, 100, 100, line=1),
                _candidate(200, 100, 150, 120, line=2, origin="yolo"),
            ]
        }
    )

    outcomes = _run(provider, [parent_id], test_db_manager, fs_manager)

    assert [o.status for o in outcomes] == ["created", "created"]
    assert [o.line for o in outcomes] == [1, 2]
    children = test_db_manager.get_crop_children(parent_id)
    assert [(c.child_image_id, c.origin) for c in children] == [
        (outcomes[0].child_image_id, "manual"),
        (outcomes[1].child_image_id, "yolo"),
    ]
    child_ratings = test_db_manager.get_image_annotations(outcomes[1].child_image_id or 0)["ratings"]
    assert {row["normalized_rating"] for row in child_ratings} == {"R"}


def test_out_of_range_and_missing_parent_fail_per_candidate_and_others_continue(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    provider = _FakeProvider(
        {
            parent_id: [_candidate(350, 0, 100, 100, line=1), _candidate(0, 0, 0, 10, line=2)],
            99999: [_candidate(0, 0, 10, 10, line=3)],
        }
    )
    provider._candidates[parent_id].append(_candidate(10, 10, 50, 50, line=4))

    outcomes = _run(provider, [parent_id, 99999], test_db_manager, fs_manager)

    by_line = {o.line: o for o in outcomes}
    assert (by_line[1].status, by_line[1].reason) == ("failed", "invalid_rect")
    assert "400x300" in (by_line[1].message or "")
    assert (by_line[2].status, by_line[2].reason) == ("failed", "invalid_rect")
    assert (by_line[3].status, by_line[3].reason) == ("failed", "parent_not_found")
    assert by_line[4].status == "created"
    assert len(test_db_manager.get_crop_children(parent_id)) == 1


def test_rerun_skips_existing_relation_and_in_file_duplicates(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    first = _run(
        _FakeProvider({parent_id: [_candidate(0, 0, 100, 100, line=1)]}),
        [parent_id],
        test_db_manager,
        fs_manager,
    )
    provider = _FakeProvider(
        {parent_id: [_candidate(0, 0, 100, 100, line=1), _candidate(0, 0, 100, 100, line=2, origin="yolo")]}
    )
    provider._candidates[parent_id].append(_candidate(0, 0, 100, 100, line=3, origin="yolo"))

    second = _run(provider, [parent_id], test_db_manager, fs_manager)

    assert (second[0].status, second[0].reason) == ("skipped", "already_exists")
    assert second[0].child_image_id == first[0].child_image_id
    # 同じ矩形でも由来が違えば別の関係行として扱い、画像としては pHash 重複で skipped になる。
    assert (second[1].status, second[1].reason) == ("skipped", "duplicate_image")
    assert second[1].child_image_id == first[0].child_image_id
    assert (second[2].status, second[2].reason) == ("skipped", "duplicate_image")
    assert len(test_db_manager.get_crop_children(parent_id)) == 1


def test_dry_run_validates_without_writing(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    provider = _FakeProvider(
        {
            parent_id: [
                _candidate(0, 0, 100, 100, line=1),
                _candidate(0, 0, 100, 100, line=2),
                _candidate(0, 0, 500, 100, line=3),
            ]
        }
    )

    outcomes = _run(provider, [parent_id], test_db_manager, fs_manager, dry_run=True)

    assert [(o.status, o.reason) for o in outcomes] == [
        ("would_create", None),
        ("skipped", "already_exists"),
        ("failed", "invalid_rect"),
    ]
    assert test_db_manager.get_crop_children(parent_id) == []


def test_dry_run_reports_duplicate_image_like_real_run(
    parent_id: int, test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager
) -> None:
    """dry-run も実行時と同じく pHash 重複を skipped (duplicate_image) と報告する (PR #1480 Codex P2)。"""
    created = _run(
        _FakeProvider({parent_id: [_candidate(0, 0, 100, 100, line=1)]}),
        [parent_id],
        test_db_manager,
        fs_manager,
    )
    candidates = [
        # 作成済みの矩形を由来だけ変えたもの
        _candidate(0, 0, 100, 100, line=1, origin="yolo"),
        # 親画像と同じ画素になる全面切り出し
        _candidate(0, 0, 400, 300, line=2),
        # 同じ実行内で由来違いの同一矩形が 2 回
        _candidate(50, 50, 80, 80, line=3, origin="a"),
        _candidate(50, 50, 80, 80, line=4, origin="b"),
    ]
    provider = _FakeProvider({parent_id: candidates})

    preview = _run(provider, [parent_id], test_db_manager, fs_manager, dry_run=True)
    actual = _run(provider, [parent_id], test_db_manager, fs_manager)

    assert [(o.status, o.reason) for o in preview] == [
        ("skipped", "duplicate_image"),
        ("skipped", "duplicate_image"),
        ("would_create", None),
        ("skipped", "duplicate_image"),
    ]
    assert [(o.status, o.reason) for o in actual] == [
        ("skipped", "duplicate_image"),
        ("skipped", "duplicate_image"),
        ("created", None),
        ("skipped", "duplicate_image"),
    ]
    assert preview[0].child_image_id == created[0].child_image_id
    assert preview[1].child_image_id == parent_id
