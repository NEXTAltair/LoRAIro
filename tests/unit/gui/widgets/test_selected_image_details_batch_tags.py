"""SelectedImageDetailsWidget のバッチタグ操作配線テスト (#997, ADR 0083 §3後送り分)。

複数選択のバッチ「外す」Signal (``tags_reject_requested``) と「無効化⇄復活」Signal
(``tags_toggle_requested``、reject/restore 両リストを1回でまとめて渡す) を、DB への
書き込みをループしたあと reload は1回だけ呼ぶことを fake db_manager で検証する。
単数版 (`_on_tag_reject` 等) と異なり、選択件数分の reload / refinement 再評価を
避けるための設計であること、混在選択 (reject/restore 両方発生) でも reload が
1回で済むこと (Codex #1001 P2 の指摘反映) を確認する。
"""

from __future__ import annotations

import pytest

from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget

pytestmark = pytest.mark.gui


class _FakeDbManager:
    """soft_reject_tag / restore_tag 呼び出しを記録する fake。"""

    def __init__(self) -> None:
        self.rejected: list[tuple[int, str]] = []
        self.restored: list[tuple[int, str]] = []

    def soft_reject_tag(self, image_id: int, tag: str) -> None:
        self.rejected.append((image_id, tag))

    def restore_tag(self, image_id: int, tag: str) -> None:
        self.restored.append((image_id, tag))


def _make_widget(qtbot, monkeypatch, db_manager: _FakeDbManager) -> SelectedImageDetailsWidget:
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    widget.reload_calls = 0  # type: ignore[attr-defined]

    def _track_reload():
        widget.reload_calls += 1  # type: ignore[attr-defined]

    monkeypatch.setattr(widget, "_reload_current_image", _track_reload)
    widget.set_db_manager(db_manager)
    widget.current_image_id = 42
    return widget


def test_batch_reject_writes_each_tag_and_reloads_once(qtbot, monkeypatch) -> None:
    """tags_reject_requested(list) は各タグを soft_reject_tag し reload は1回だけ。"""
    db_manager = _FakeDbManager()
    widget = _make_widget(qtbot, monkeypatch, db_manager)

    widget._on_tags_reject(["1girl", "outdoors"])

    assert db_manager.rejected == [(42, "1girl"), (42, "outdoors")]
    assert widget.reload_calls == 1  # type: ignore[attr-defined]


def test_batch_toggle_writes_restore_only_and_reloads_once(qtbot, monkeypatch) -> None:
    """tags_toggle_requested([], restore) は restore のみ書き込み reload は1回だけ。"""
    db_manager = _FakeDbManager()
    widget = _make_widget(qtbot, monkeypatch, db_manager)

    widget._on_tags_toggle([], ["blurry_background"])

    assert db_manager.restored == [(42, "blurry_background")]
    assert db_manager.rejected == []
    assert widget.reload_calls == 1  # type: ignore[attr-defined]


def test_batch_toggle_mixed_writes_both_and_reloads_once(qtbot, monkeypatch) -> None:
    """混在 (reject + restore 両方) でも reload は1回だけ (Codex #1001 P2)。"""
    db_manager = _FakeDbManager()
    widget = _make_widget(qtbot, monkeypatch, db_manager)

    widget._on_tags_toggle(["1girl"], ["flower"])

    assert db_manager.rejected == [(42, "1girl")]
    assert db_manager.restored == [(42, "flower")]
    assert widget.reload_calls == 1  # type: ignore[attr-defined]


def test_batch_reject_noop_without_current_image(qtbot, monkeypatch) -> None:
    """画像未選択では DB 書き込み・reload とも行わない。"""
    db_manager = _FakeDbManager()
    widget = _make_widget(qtbot, monkeypatch, db_manager)
    widget.current_image_id = None

    widget._on_tags_reject(["1girl"])

    assert db_manager.rejected == []
    assert widget.reload_calls == 0  # type: ignore[attr-defined]


def test_tag_panel_batch_signals_connected_after_set_db_manager(qtbot, monkeypatch) -> None:
    """set_db_manager 後に TagPanelWidget のバッチ Signal が配線されていること (#997)。"""
    db_manager = _FakeDbManager()
    widget = _make_widget(qtbot, monkeypatch, db_manager)
    widget.current_image_id = 7

    widget.annotation_display.tags_reject_requested.emit(["1girl"])

    assert db_manager.rejected == [(7, "1girl")]
