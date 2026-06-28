"""ExportOverlayBar の pytest-qt テストスイート（Issue #948）。

テストカバレッジ:
- trigger 追加 → overlay_changed emit + プレビュー先頭反映
- 出力除外 → プレビューから消える
- 漢字 trigger のリテラルプレビュー表示
- scope 切替 → scope_changed emit
- chip の追加・削除
- 公開メソッド add_overlay_exclude / add_overlay_replace
- validate/export ボタン → シグナル emit
- in-memory スタブ vocab での動作（vocab 未注入）
"""

from __future__ import annotations

from datetime import datetime

import pytest

from lorairo.gui.widgets.export_overlay_bar import ExportOverlayBar
from lorairo.services.export_overlay import ExportTagOverlay
from lorairo.services.trigger_vocab import VocabEntry

pytestmark = pytest.mark.gui


@pytest.fixture
def bar(qtbot) -> ExportOverlayBar:
    """reader=None（convert スキップ）の ExportOverlayBar フィクスチャ。"""
    w = ExportOverlayBar(reader=None)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def loaded_bar(qtbot) -> ExportOverlayBar:
    """選択画像を設定済みの ExportOverlayBar フィクスチャ。"""
    w = ExportOverlayBar(reader=None)
    qtbot.addWidget(w)
    w.set_selected_image(1, ["1girl", "smile"])
    return w


# ------------------------------------------------------------------
# trigger 追加
# ------------------------------------------------------------------


class TestTriggerAdd:
    """trigger 追加の overlay_changed emit とプレビュー反映テスト。"""

    def test_add_trigger_emits_overlay_changed(self, qtbot, loaded_bar: ExportOverlayBar) -> None:
        """trigger 追加で overlay_changed が ExportTagOverlay を emit すること。"""
        loaded_bar._trigger_edit.setText("magic")

        with qtbot.waitSignal(loaded_bar.overlay_changed, timeout=1000) as blocker:
            loaded_bar._add_trigger_btn.click()

        overlay = blocker.args[0]
        assert isinstance(overlay, ExportTagOverlay)
        assert overlay.add == ["magic"]

    def test_add_trigger_prepends_to_preview(self, loaded_bar: ExportOverlayBar) -> None:
        """trigger がプレビュー先頭に literal prepend されること。"""
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar._preview.toPlainText() == "magic, 1girl, smile"

    def test_add_kanji_trigger_literal_in_preview(self, loaded_bar: ExportOverlayBar) -> None:
        """漢字 trigger がプレビューにリテラルのまま先頭表示されること。"""
        loaded_bar._trigger_edit.setText("魔法少女")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar._preview.toPlainText() == "魔法少女, 1girl, smile"

    def test_add_trigger_clears_input(self, loaded_bar: ExportOverlayBar) -> None:
        """trigger 追加後に入力欄がクリアされること。"""
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar._trigger_edit.text() == ""

    def test_add_duplicate_trigger_ignored(self, loaded_bar: ExportOverlayBar) -> None:
        """同一 trigger の重複追加は無視されること。"""
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar.current_overlay().add == ["magic"]

    def test_empty_trigger_not_added(self, loaded_bar: ExportOverlayBar) -> None:
        """空入力の追加は overlay を変更しないこと。"""
        loaded_bar._trigger_edit.setText("   ")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar.current_overlay().add == []

    def test_comma_trigger_rejected(self, loaded_bar: ExportOverlayBar) -> None:
        """カンマを含む trigger は追加しないこと（複数タグ化けを防止）。"""
        loaded_bar._trigger_edit.setText("foo, bar")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar.current_overlay().add == []
        assert loaded_bar._preview.toPlainText() == "1girl, smile"


# ------------------------------------------------------------------
# 出力除外 / 置換（公開メソッド）
# ------------------------------------------------------------------


class TestExcludeAndReplace:
    """add_overlay_exclude / add_overlay_replace の overlay 反映テスト。"""

    def test_exclude_removes_from_preview(self, loaded_bar: ExportOverlayBar) -> None:
        """exclude するとプレビューから当該タグが消えること。"""
        loaded_bar.add_overlay_exclude("smile")

        assert loaded_bar._preview.toPlainText() == "1girl"

    def test_exclude_emits_overlay_changed(self, qtbot, loaded_bar: ExportOverlayBar) -> None:
        """exclude で overlay_changed が emit されること。"""
        with qtbot.waitSignal(loaded_bar.overlay_changed, timeout=1000) as blocker:
            loaded_bar.add_overlay_exclude("smile")

        assert blocker.args[0].exclude == {"smile"}

    def test_duplicate_exclude_ignored(self, loaded_bar: ExportOverlayBar) -> None:
        """同一タグの重複 exclude は無視されること。"""
        loaded_bar.add_overlay_exclude("smile")
        loaded_bar.add_overlay_exclude("smile")

        assert loaded_bar.current_overlay().exclude == {"smile"}

    def test_replace_applies_to_preview(self, loaded_bar: ExportOverlayBar) -> None:
        """replace するとプレビューのタグが置換されること。"""
        loaded_bar.add_overlay_replace("smile", "grin")

        assert loaded_bar._preview.toPlainText() == "1girl, grin"

    def test_replace_same_tag_ignored(self, loaded_bar: ExportOverlayBar) -> None:
        """from == to の replace は無視されること。"""
        loaded_bar.add_overlay_replace("smile", "smile")

        assert loaded_bar.current_overlay().replace == {}


# ------------------------------------------------------------------
# chip 描画・削除
# ------------------------------------------------------------------


class TestChips:
    """overlay chip の追加・削除テスト。"""

    def test_trigger_chip_added(self, loaded_bar: ExportOverlayBar) -> None:
        """trigger 追加で chip が1つ増えること。"""
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()

        assert loaded_bar._chip_layout.count() == 1

    def test_remove_trigger_updates_overlay_and_preview(self, loaded_bar: ExportOverlayBar) -> None:
        """trigger を内部削除すると overlay とプレビューが更新されること。"""
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()

        loaded_bar._remove_trigger("magic")

        assert loaded_bar.current_overlay().add == []
        assert loaded_bar._preview.toPlainText() == "1girl, smile"

    def test_chips_for_all_overlay_kinds(self, loaded_bar: ExportOverlayBar) -> None:
        """trigger/exclude/replace の3種すべてが chip 表示されること。"""
        loaded_bar._trigger_edit.setText("magic")
        loaded_bar._add_trigger_btn.click()
        loaded_bar.add_overlay_exclude("smile")
        loaded_bar.add_overlay_replace("1girl", "1woman")

        assert loaded_bar._chip_layout.count() == 3


# ------------------------------------------------------------------
# scope
# ------------------------------------------------------------------


class TestScope:
    """適用先スコープ切替テスト。"""

    def test_scope_change_emits_filtered(self, qtbot, bar: ExportOverlayBar) -> None:
        """絞込ボタンで scope_changed('filtered') が emit されること。"""
        with qtbot.waitSignal(bar.scope_changed, timeout=1000) as blocker:
            bar._filtered_btn.click()

        assert blocker.args[0] == "filtered"

    def test_scope_change_back_to_all(self, qtbot, bar: ExportOverlayBar) -> None:
        """全ボタンで scope_changed('all') が emit されること。"""
        bar._filtered_btn.click()

        with qtbot.waitSignal(bar.scope_changed, timeout=1000) as blocker:
            bar._all_btn.click()

        assert blocker.args[0] == "all"

    def test_same_scope_click_no_emit(self, qtbot, bar: ExportOverlayBar) -> None:
        """既に選択中のスコープを再クリックしても emit しないこと。"""
        received: list[str] = []
        bar.scope_changed.connect(received.append)

        bar._all_btn.click()  # 既定で all 選択済み

        assert received == []

    def test_set_scope_counts_updates_labels(self, bar: ExportOverlayBar) -> None:
        """set_scope_counts でセグメントの件数表示が更新されること。"""
        bar.set_scope_counts(all_count=10, filtered_count=3)

        assert "10" in bar._all_btn.text()
        assert "3" in bar._filtered_btn.text()


# ------------------------------------------------------------------
# プレビュー / 選択画像
# ------------------------------------------------------------------


class TestPreview:
    """ライブプレビュー更新テスト。"""

    def test_preview_empty_without_selection(self, bar: ExportOverlayBar) -> None:
        """選択画像なしのときプレビューは空であること。"""
        assert bar._preview.toPlainText() == ""

    def test_preview_updates_on_selection_change(self, bar: ExportOverlayBar) -> None:
        """set_selected_image でプレビューが更新されること。"""
        bar.set_selected_image(2, ["cat", "dog"])

        assert bar._preview.toPlainText() == "cat, dog"

    def test_preview_clears_when_selection_none(self, loaded_bar: ExportOverlayBar) -> None:
        """選択画像を None にするとプレビューが空になること。"""
        loaded_bar.set_selected_image(None, [])

        assert loaded_bar._preview.toPlainText() == ""


# ------------------------------------------------------------------
# エクスポート操作
# ------------------------------------------------------------------


class TestExportActions:
    """検証/エクスポートボタンと選択値テスト。"""

    def test_validate_button_emits(self, qtbot, bar: ExportOverlayBar) -> None:
        """検証ボタンで validate_requested が emit されること。"""
        with qtbot.waitSignal(bar.validate_requested, timeout=1000):
            bar._validate_btn.click()

    def test_export_button_emits(self, qtbot, bar: ExportOverlayBar) -> None:
        """エクスポートボタンで export_requested が emit されること。"""
        with qtbot.waitSignal(bar.export_requested, timeout=1000):
            bar._export_btn.click()

    def test_selected_resolution_and_format(self, bar: ExportOverlayBar) -> None:
        """解像度・形式の選択値（canonical 値）が取得できること。"""
        assert bar.selected_resolution() == 512
        assert bar.selected_format() == "txt_separate"

    def test_resolution_includes_1536(self, bar: ExportOverlayBar) -> None:
        """高解像度 1536px が選択肢に含まれること（既存 UI と同等）。"""
        options = [bar._resolution_combo.itemText(i) for i in range(bar._resolution_combo.count())]
        assert "1536" in options
        bar._resolution_combo.setCurrentText("1536")
        assert bar.selected_resolution() == 1536

    def test_format_includes_txt_merged(self, bar: ExportOverlayBar) -> None:
        """キャプション統合形式 txt_merged が選択可能であること（既存 UI と同等）。"""
        values = [bar._format_combo.itemData(i) for i in range(bar._format_combo.count())]
        assert "txt_merged" in values
        idx = values.index("txt_merged")
        bar._format_combo.setCurrentIndex(idx)
        assert bar.selected_format() == "txt_merged"

    def test_changed_since_filter_defaults_disabled(self, bar: ExportOverlayBar) -> None:
        """changed-since フィルタは既定で無効であること。"""
        assert bar.changed_since_enabled() is False

    def test_changed_since_filter_can_be_enabled(self, bar: ExportOverlayBar) -> None:
        """changed-since フィルタの cutoff 日時を取得できること。"""
        cutoff = datetime(2026, 6, 28, 10, 30)
        bar._changed_since_filter.set_filter(True, cutoff)

        assert bar.changed_since_enabled() is True
        assert bar.changed_since() == cutoff


# ------------------------------------------------------------------
# in-memory スタブ vocab
# ------------------------------------------------------------------


class TestVocabStub:
    """vocab 未注入時の in-memory スタブ動作テスト。"""

    def test_registered_trigger_appears_in_suggestions(self, bar: ExportOverlayBar) -> None:
        """追加した trigger が以降の補完候補に出ること（in-memory スタブ）。"""
        bar._trigger_edit.setText("magic")
        bar._add_trigger_btn.click()

        # 新たに "mag" と打つと補完候補に "magic" が出る
        bar._trigger_edit.setText("mag")

        suggestions = [bar._suggest_combo.itemText(i) for i in range(bar._suggest_combo.count())]
        assert "magic" in suggestions

    def test_injected_vocab_used_for_suggestions(self, qtbot) -> None:
        """注入した vocab の search が補完候補に使われること。"""

        class FakeVocab:
            def search(self, prefix: str) -> list[VocabEntry]:
                return [VocabEntry(word="魔法少女", freq=3)]

            def register(self, word: str) -> None:
                pass

        bar = ExportOverlayBar(vocab=FakeVocab(), reader=None)
        qtbot.addWidget(bar)

        bar._trigger_edit.setText("魔")

        suggestions = [bar._suggest_combo.itemText(i) for i in range(bar._suggest_combo.count())]
        assert suggestions == ["魔法少女"]
