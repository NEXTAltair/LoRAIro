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
        # 主訳変更 (canonical, language, translation) の記録 (#1084)。
        self.preferred: list[tuple[str, str, str]] = []

    def resolve_tag_id(self, canonical: str) -> int | None:
        self.resolved.append(canonical)
        return self._resolve_to

    def add_translation(self, tag_id: int, language: str, translation: str) -> None:
        self.translations.append((tag_id, language, translation))

    def update_single_tag_type(self, tag_id: int, type_name: str) -> None:
        self.type_updates.append((tag_id, type_name))

    def list_translation_candidates(self, canonical: str, language: str) -> tuple[list[str], str | None]:
        return [], None

    def set_preferred_translation(self, canonical: str, language: str, translation: str) -> bool:
        self.preferred.append((canonical, language, translation))
        return self._resolve_to is not None


class _FakeRefinementService:
    """clear_cache 呼び出しを記録する fake。"""

    def __init__(self) -> None:
        self.clear_cache_calls = 0

    def clear_cache(self) -> None:
        self.clear_cache_calls += 1


def _make_widget(qtbot, monkeypatch, service: _FakeTagService) -> SelectedImageDetailsWidget:
    widget = SelectedImageDetailsWidget()
    qtbot.addWidget(widget)
    # DB 再取得・再評価は副作用が重いので無効化し、dispatch のみ検証する。
    monkeypatch.setattr(widget, "_reload_current_image", lambda: None)
    monkeypatch.setattr(widget, "_trigger_refinement_evaluation", lambda: None)
    # set_merged_reader は翻訳追加で呼ばれてはいけない (言語リセット回避、#995 P2)。
    # 呼ばれたら検知できるよう記録する。
    widget._set_merged_reader_calls = 0  # type: ignore[attr-defined]

    def _track_set_merged_reader(reader):  # type: ignore[no-untyped-def]
        widget._set_merged_reader_calls += 1  # type: ignore[attr-defined]

    monkeypatch.setattr(widget, "set_merged_reader", _track_set_merged_reader)
    widget.set_tag_management_service(service)
    return widget


def test_translation_add_dispatches_to_service(qtbot, monkeypatch) -> None:
    """translation_add_requested → resolve_tag_id → add_translation。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_translation_add("1girl", "ja", "少女")

    assert service.resolved == ["1girl"]
    assert service.translations == [(42, "ja", "少女")]


def test_translation_add_does_not_reset_language(qtbot, monkeypatch) -> None:
    """翻訳追加は set_merged_reader を呼ばない (言語セレクタを english へ戻さない、#995 P2)。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_translation_add("1girl", "ja", "少女")

    assert widget._set_merged_reader_calls == 0  # type: ignore[attr-defined]


def test_translation_preferred_dispatches_to_service(qtbot, monkeypatch) -> None:
    """translation_preferred_requested → set_preferred_translation (#1084)。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_translation_preferred("blue_eyes", "ja", "青い目")

    assert service.preferred == [("blue_eyes", "ja", "青い目")]


def test_translation_preferred_skipped_when_unresolved(qtbot, monkeypatch) -> None:
    """主訳設定が失敗 (未解決) しても例外を出さず reload しない (#1084)。"""
    service = _FakeTagService(resolve_to=None)
    widget = _make_widget(qtbot, monkeypatch, service)
    reloaded: list[int] = []
    monkeypatch.setattr(widget, "_reload_current_image", lambda: reloaded.append(1))

    widget._on_translation_preferred("unknown_tag", "ja", "未知")

    assert service.preferred == [("unknown_tag", "ja", "未知")]
    assert reloaded == []  # set_preferred_translation が False → reload しない


def test_type_edit_dispatches_to_service(qtbot, monkeypatch) -> None:
    """tag_metadata_edit_requested → resolve_tag_id → update_single_tag_type。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)

    widget._on_tag_metadata_edit("1girl", "copyright")

    assert service.resolved == ["1girl"]
    assert service.type_updates == [(42, "copyright")]


def test_type_edit_clears_refinement_cache_before_reeval(qtbot, monkeypatch) -> None:
    """type 補正後は再評価前に refinement キャッシュを無効化する (#995 P2)。"""
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)
    refinement = _FakeRefinementService()
    widget._refinement_service = refinement  # type: ignore[assignment]

    widget._on_tag_metadata_edit("1girl", "copyright")

    assert refinement.clear_cache_calls == 1


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


def test_translation_add_clears_refinement_cache_before_reeval(qtbot, monkeypatch) -> None:
    """翻訳追加/修正後は refinement キャッシュを無効化する (PR #1086 Codex P2)。

    キャッシュが残ると、⚠ → 翻訳修正で正しい値を書いても stale な翻訳品質警告が
    再表示され続ける。type 補正フローと同じ扱いにする。
    """
    service = _FakeTagService(resolve_to=42)
    widget = _make_widget(qtbot, monkeypatch, service)
    refinement = _FakeRefinementService()
    widget._refinement_service = refinement  # type: ignore[assignment]

    widget._on_translation_add("1girl", "ja", "少女")

    assert refinement.clear_cache_calls == 1

def test_preferred_en_adds_selector_entry_when_only_legacy_english(qtbot, monkeypatch) -> None:
    """en の主訳変更時、候補が legacy "english" しか無くても "en" 項目を追加する (Codex P2)。

    "english" は原文表示の sentinel なので alias fallback で寄せてはならない
    (原文表示のままになり主訳変更が見えない)。
    """
    service = _FakeTagService()
    widget = _make_widget(qtbot, monkeypatch, service)
    widget._available_languages = []
    widget._merged_reader = None  # 再取得なしで append 経路を検証

    widget._on_translation_preferred("blue_eyes", "en", "blue eyes trans")

    assert "en" in widget._available_languages


def test_preferred_ja_reuses_legacy_japanese_entry(qtbot, monkeypatch) -> None:
    """ja の主訳変更時、legacy "japanese" 候補があれば重複項目を追加しない (Codex P2)。"""
    service = _FakeTagService()
    widget = _make_widget(qtbot, monkeypatch, service)
    widget._available_languages = ["japanese"]
    widget._merged_reader = None

    widget._on_translation_preferred("blue_eyes", "ja", "青い目")

    assert widget._available_languages == ["japanese"]  # alias fallback で japanese へ切替
