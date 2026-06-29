"""SelectedImageDetailsWidget の個別タグ編集が DatasetStateManager キャッシュへ反映されるか検証する (#949)。

検索タブのプレビュー詳細ペインでタグを soft-reject / 復活 / 手動追加すると、DB は更新されるが
``DatasetStateManager._all_images`` の遅延ロード済みアノテーションが古いままになる回帰を再現する。
再選択時に編集前タグが復活し「DB に反映されていない」ように見える症状の防止。
"""

from __future__ import annotations

from typing import Any

import pytest

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget

pytestmark = pytest.mark.gui


class _FakeImageRepo:
    """DB の代わりに soft-reject 状態を保持し、現在状態のメタデータを返す fake。"""

    def __init__(self) -> None:
        self._all_tags = ["flower", "rose"]
        self.rejected: set[str] = set()
        self.added: list[str] = []

    def _live_tags(self) -> list[dict[str, Any]]:
        tags = [t for t in self._all_tags if t not in self.rejected] + self.added
        return [
            {
                "id": i,
                "tag": t,
                "tag_id": None,
                "model_id": None,
                "model_name": "Unknown",
                "source": "AI",
                "existing": False,
                "is_edited_manually": False,
                "confidence_score": None,
                "created_at": None,
                "updated_at": None,
            }
            for i, t in enumerate(tags)
        ]

    def _metadata(self, image_id: int) -> dict[str, Any]:
        return {
            "id": image_id,
            "stored_image_path": "/tmp/x.png",
            "width": 100,
            "height": 100,
            "tags": self._live_tags(),
            "tags_text": ", ".join(t["tag"] for t in self._live_tags()),
            "captions": [],
            "scores": [],
            "score_labels": [],
            "ratings": [],
        }

    # DatasetStateManager._ensure_annotations_loaded が呼ぶ遅延ロード経路
    def get_image_annotation_metadata(self, image_id: int) -> dict[str, Any]:
        return {
            "tags": self._live_tags(),
            "captions": [],
            "scores": [],
            "score_labels": [],
            "ratings": [],
        }

    # refresh_image / _reload_current_image が呼ぶ完全メタデータ取得経路
    def get_image_metadata(self, image_id: int) -> dict[str, Any]:
        return self._metadata(image_id)


class _FakeDbManager:
    """SelectedImageDetailsWidget / DatasetStateManager が触る最小 Manager fake。"""

    def __init__(self) -> None:
        self.image_repo = _FakeImageRepo()

    def soft_reject_tag(self, image_id: int, tag: str) -> bool:
        self.image_repo.rejected.add(tag)
        return True

    def restore_tag(self, image_id: int, tag: str) -> bool:
        self.image_repo.rejected.discard(tag)
        return True

    def add_manual_tag(self, image_id: int, tag: str) -> bool:
        self.image_repo.added.append(tag)
        return True

    def get_rejected_tags(self, image_id: int) -> list[dict[str, Any]]:
        return [{"tag": t, "tag_id": None, "is_edited_manually": False} for t in self.image_repo.rejected]


def _cached_tag_names(dsm: DatasetStateManager, image_id: int) -> set[str]:
    data = dsm.get_image_by_id(image_id)
    assert data is not None
    return {t["tag"] for t in data.get("tags", [])}


def _wire(qtbot) -> tuple[SelectedImageDetailsWidget, DatasetStateManager, _FakeDbManager]:
    db = _FakeDbManager()
    dsm = DatasetStateManager()
    dsm.set_db_manager(db)
    # 検索フェーズ: アノテーション無しでキャッシュ投入 (Issue #965 の遅延ロード前提)
    dsm.update_from_search_results([{"id": 1, "stored_image_path": "/tmp/x.png"}])
    # 選択でアノテーションを遅延ロード → キャッシュ dict に tags がマージされる
    dsm.set_current_image(1)
    assert _cached_tag_names(dsm, 1) == {"flower", "rose"}

    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    widget.set_db_manager(db)
    widget.connect_to_dataset_state_manager(dsm)
    widget.current_image_id = 1
    return widget, dsm, db


def test_reject_updates_dataset_state_cache(qtbot) -> None:
    """soft-reject 後、DSM キャッシュからも該当タグが消える (再選択で復活しない)。"""
    widget, dsm, _db = _wire(qtbot)

    widget._on_tag_reject("flower")

    assert "flower" not in _cached_tag_names(dsm, 1)
    assert _cached_tag_names(dsm, 1) == {"rose"}


def test_add_updates_dataset_state_cache(qtbot) -> None:
    """手動タグ追加後、DSM キャッシュに新タグが反映される。"""
    widget, dsm, _db = _wire(qtbot)

    widget._on_tag_add("blue_sky")

    assert "blue_sky" in _cached_tag_names(dsm, 1)


def test_restore_updates_dataset_state_cache(qtbot) -> None:
    """復活後、DSM キャッシュに該当タグが戻る。"""
    widget, dsm, db = _wire(qtbot)
    db.image_repo.rejected.add("rose")
    dsm.refresh_image(1)
    assert "rose" not in _cached_tag_names(dsm, 1)

    widget._on_tag_restore("rose")

    assert "rose" in _cached_tag_names(dsm, 1)
