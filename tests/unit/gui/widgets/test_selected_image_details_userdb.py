"""SelectedImageDetailsWidget の tagdb userdb 系書き込み配線テスト (#989, ADR 0083 Phase 2)。

翻訳追加 / type 補正の Signal を canonical→tag_id 解決経由で TagManagementService へ
dispatch することを fake サービスで検証する。userdb 書き込みは canonical 主キーで
画像 ID に依存しないこと、未解決時にスキップすることを確認する。
"""

from __future__ import annotations

import pytest

from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget

pytestmark = pytest.mark.gui


class _FakeTagService:
    """TagManagementService の userdb 書き込み窓口だけを模した fake。"""

    def __init__(self, resolve_to: int | None = 42) -> None:
        self._resolve_to = resolve_to
        self.resolved: list[str] = []
        self.translations: list[tuple[int, str, str]] = []
        self.type_updates: list[tuple[int, str]] = []

    def resolve_tag_id(self, canonical: str) -> int | None:
        self.resolved.append(canonical)
        return self._resolve_to

    def add_translation(self, tag_id: int, language: str, translation: str) -> None:
        self.translations.append((tag_id, language, translation))

    def update_single_tag_type(self, tag_id: int, type_name: str) -> None:
        self.type_updates.append((tag_id, type_name))


def _make_widget(qtbot, monkeypatch, service: _FakeTagService) -> SelectedImageDetailsWidget:
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    # DB 再取得・再評価は副作用が重いので無効化し、dispatch のみ検証する。
    monkeypatch.setattr(widget, "_reload_current_image", lambda: None)
    monkeypatch.setattr(widget, "set_merged_reader", lambda reader: None)
    monkeypatch.setattr(widget, "_trigger_refinement_evaluation", lambda: None)
    widget.set_tag_management_service(service)
    return widget


def test_translation_add_dispatches_to_service(qtbot, monkeypatch) -> None:
    """translation_add_requested → resolve_tag_id → add_translation。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_translation_add("1girl", "ja", "少女")

    assert service.resolved == ["1girl"]
    assert service.translations == [(42, "ja", "少女")]


def test_type_edit_dispatches_to_service(qtbot, monkeypatch) -> None:
    """tag_metadata_edit_requested → resolve_tag_id → update_single_tag_type。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_tag_metadata_edit("1girl", "copyright")

    assert service.resolved == ["1girl"]
    assert service.type_updates == [(42, "copyright")]


def test_userdb_write_independent_of_image_id(qtbot, monkeypatch) -> None:
    """userdb 書き込みは canonical 主キーで current_image_id に依存しない (#989)。"""
    service = _FakeTagService(resolve_to=7)
    widget = _make_widget(qtbot, monkeypatch, service)
    widget.current_image_id = None  # 画像未選択でも書ける

    widget._on_translation_add("flower", "ja", "花")

    assert service.translations == [(7, "ja", "花")]


def test_translation_add_skipped_when_tag_id_unresolved(qtbot, monkeypatch) -> None:
    """canonical→tag_id が解決できなければ書き込まない。"""
    service = _FakeTagService(resolve_to=None)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_translation_add("unknown_tag", "ja", "未知")

    assert service.resolved == ["unknown_tag"]
    assert service.translations == []


def test_type_edit_skipped_without_service(qtbot, monkeypatch) -> None:
    """サービス未配線なら何もしない (graceful)。"""
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    monkeypatch.setattr(widget, "_reload_current_image", lambda: None)
    monkeypatch.setattr(widget, "_trigger_refinement_evaluation", lambda: None)
    # set_tag_management_service を呼ばない = _tag_management_service is None
    widget._on_tag_metadata_edit("1girl", "copyright")  # 例外を出さないこと
