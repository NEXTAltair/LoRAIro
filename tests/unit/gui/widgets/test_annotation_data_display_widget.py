# tests/unit/gui/widgets/test_annotation_data_display_widget.py

import pytest

from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, AnnotationDataDisplayWidget


class TestAnnotationDataDisplayWidget:
    """AnnotationDataDisplayWidget単体テスト（言語切り替え機能含む）"""

    @pytest.fixture
    def widget(self, qtbot):
        """テスト用AnnotationDataDisplayWidget"""
        w = AnnotationDataDisplayWidget()
        qtbot.addWidget(w)
        return w

    @pytest.fixture
    def sample_tags(self):
        """テスト用タグリスト（tag_id付き）"""
        return [
            {
                "tag": "1girl",
                "tag_id": 10,
                "model_name": "wd",
                "source": "AI",
                "confidence_score": 0.9,
                "is_edited_manually": False,
            },
            {
                "tag": "flower",
                "tag_id": 20,
                "model_name": "wd",
                "source": "AI",
                "confidence_score": 0.8,
                "is_edited_manually": False,
            },
            {
                "tag": "solo",
                "tag_id": None,
                "model_name": "wd",
                "source": "AI",
                "confidence_score": 0.7,
                "is_edited_manually": False,
            },
        ]

    # ─── initialize_language_selector ───────────────────────────────────

    def test_language_bar_hidden_by_default(self, widget):
        """デフォルト状態では言語バーが非表示であること"""
        # isHidden()はisVisible()と異なり親ウィジェットの表示状態に依存しない
        assert widget._lang_bar.isHidden()

    def test_language_bar_hidden_when_empty_list(self, widget):
        """空リスト渡しで言語バーが非表示になること"""
        widget.initialize_language_selector([])
        assert widget._lang_bar.isHidden()

    def test_language_bar_visible_when_languages_provided(self, widget):
        """言語リスト渡しで言語バーが表示されること"""
        widget.initialize_language_selector(["japanese", "chinese"])
        assert not widget._lang_bar.isHidden()

    def test_combo_includes_english_as_first_item(self, widget):
        """コンボボックスの先頭は常にenglishであること"""
        widget.initialize_language_selector(["japanese", "chinese"])
        assert widget._lang_combo.itemText(0) == "english"

    def test_combo_total_count_includes_english(self, widget):
        """コンボボックスのアイテム数は言語数+1（english）"""
        widget.initialize_language_selector(["japanese", "chinese"])
        assert widget._lang_combo.count() == 3  # english + japanese + chinese

    def test_combo_excludes_english_from_additional_items(self, widget):
        """english を含む言語リストでも english が重複しないこと"""
        widget.initialize_language_selector(["english", "japanese"])
        # english は先頭の1つだけ
        texts = [widget._lang_combo.itemText(i) for i in range(widget._lang_combo.count())]
        assert texts.count("english") == 1

    # ─── _refresh_tags_for_language ──────────────────────────────────────

    def test_compact_label_shows_english_by_default(self, widget, sample_tags):
        """初期表示は英語タグ名のコンパクトラベルであること"""
        data = AnnotationData(tags=sample_tags)
        widget.update_data(data)
        assert "1girl" in widget._tags_compact_label.text()
        assert "flower" in widget._tags_compact_label.text()

    def test_compact_label_switches_to_japanese(self, widget, sample_tags):
        """japanese選択でラベルが翻訳テキストに切り替わること"""
        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])

        widget._lang_combo.setCurrentText("japanese")

        assert "1人の女の子" in widget._tags_compact_label.text()
        assert "花" in widget._tags_compact_label.text()

    def test_fallback_to_english_when_no_translation(self, widget, sample_tags):
        """翻訳がないタグは英語原文でフォールバックすること"""
        # 翻訳データなし（空dict）
        data = AnnotationData(
            tags=sample_tags,
            tag_translations={},
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])

        widget._lang_combo.setCurrentText("japanese")

        # 翻訳なしなので英語のまま
        assert "1girl" in widget._tags_compact_label.text()
        assert "flower" in widget._tags_compact_label.text()

    def test_tag_without_tag_id_shows_english(self, widget, sample_tags):
        """tag_id=Noneのタグは言語切り替えに関わらず英語原文を表示すること"""
        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])

        widget._lang_combo.setCurrentText("japanese")

        label_text = widget._tags_compact_label.text()
        # tag_id=Noneの"solo"は英語原文のまま
        assert "solo" in label_text

    def test_switch_back_to_english_restores_original(self, widget, sample_tags):
        """englishに戻すと英語タグ名が復元されること"""
        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])

        widget._lang_combo.setCurrentText("japanese")
        widget._lang_combo.setCurrentText("english")

        label_text = widget._tags_compact_label.text()
        assert "1girl" in label_text
        assert "flower" in label_text

    def test_table_tag_column_updates_on_language_change(self, widget, sample_tags):
        """言語切り替え時にテーブルTag列（列0）も更新されること"""
        translations = {10: {"japanese": "1人の女の子"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)

        # テーブルを表示状態にして確認
        widget.tableWidgetTags.setVisible(True)
        widget.initialize_language_selector(["japanese"])
        widget._lang_combo.setCurrentText("japanese")

        # 行0（1girl / tag_id=10）のTag列が翻訳テキストに更新されていること
        item = widget.tableWidgetTags.item(0, 0)
        assert item is not None
        assert item.text() == "1人の女の子"

    # ─── update_data との統合 ───────────────────────────────────────────

    def test_update_data_with_translations_applies_current_language(self, widget, sample_tags):
        """update_data呼び出し時に選択中言語が適用されること"""
        widget.initialize_language_selector(["japanese"])
        widget._lang_combo.setCurrentText("japanese")

        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)

        assert "1人の女の子" in widget._tags_compact_label.text()
