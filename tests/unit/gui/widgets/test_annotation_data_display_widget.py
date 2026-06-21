# tests/unit/gui/widgets/test_annotation_data_display_widget.py

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange

from lorairo.gui.widgets.annotation_data_display_widget import (
    AnnotationData,
    AnnotationDataDisplayWidget,
    SelectableTagChip,
)


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

    def test_compact_labels_are_selectable(self, widget):
        """compact表示のQLabelは選択・コピー可能であること"""
        flags = (
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )

        assert widget._tags_compact_label.textInteractionFlags() & flags == flags
        assert widget._caption_compact_label.textInteractionFlags() & flags == flags
        assert widget._tags_compact_label.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert widget._caption_compact_label.focusPolicy() == Qt.FocusPolicy.StrongFocus

    def test_label_clipboard_text_prefers_selected_text(self, widget):
        """QLabelのcontext copyは選択範囲を優先すること"""
        widget._tags_compact_label.setText("1girl, flower, solo")
        widget._tags_compact_label.setSelection(7, 6)

        assert widget._label_clipboard_text(widget._tags_compact_label) == "flower"

    def test_displayed_tags_text_returns_current_compact_label(self, widget, sample_tags):
        """現在表示中のタグ文字列を取得できること"""
        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])
        widget._lang_combo.setCurrentText("japanese")

        assert widget.displayed_tags_text() == "1人の女の子, 花, solo"

    def test_copy_selected_tag_cells_to_clipboard(self, widget, sample_tags):
        """タグテーブル選択範囲をTSVとしてコピーできること"""
        widget.update_data(AnnotationData(tags=sample_tags))
        widget.tableWidgetTags.setRangeSelected(QTableWidgetSelectionRange(0, 0, 1, 1), True)

        assert widget.copy_selected_tag_cells_to_clipboard() is True
        assert QApplication.clipboard().text() == "1girl\twd\nflower\twd"

    def test_copy_selected_tag_cells_exports_edited_checkbox_state(self, widget, sample_tags):
        """Edited列はcheckbox状態をTSVへ出力すること"""
        sample_tags[0]["is_edited_manually"] = True
        sample_tags[1]["is_edited_manually"] = False
        widget.update_data(AnnotationData(tags=sample_tags))
        widget.tableWidgetTags.setRangeSelected(QTableWidgetSelectionRange(0, 4, 1, 4), True)

        assert widget.copy_selected_tag_cells_to_clipboard() is True
        assert QApplication.clipboard().text() == "true\nfalse"

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

    # ─── タグチップ表示 (Issue #785 / DS chip 文法) ──────────────────────

    def _chip_texts(self, widget):
        """チップコンテナ内の QLabel テキストを順序付きで返す。"""
        layout = widget._tags_chip_layout
        texts = []
        for i in range(layout.count()):
            item = layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is not None:
                texts.append(w.text())
        return texts

    def test_chips_render_english_tags(self, widget, sample_tags):
        """英語表示でタグ数ぶんのチップが描画されること。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        assert self._chip_texts(widget) == ["1girl", "flower", "solo"]

    def test_chips_render_translated_tags(self, widget, sample_tags):
        """言語切り替えでチップが翻訳テキストになること。"""
        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])
        widget._lang_combo.setCurrentText("japanese")

        # tag_id=None の solo は英語原文へフォールバック
        assert self._chip_texts(widget) == ["1人の女の子", "花", "solo"]

    def test_untranslated_chip_uses_dashed_style(self, widget, sample_tags):
        """翻訳のないタグのチップは点線スタイル (faint) になること。"""
        from lorairo.gui import theme

        translations = {10: {"japanese": "1人の女の子"}}  # flower(20) は翻訳なし
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])
        widget._lang_combo.setCurrentText("japanese")

        layout = widget._tags_chip_layout
        flower_chip = layout.itemAt(1).widget()  # row1 = flower (翻訳なし)
        assert flower_chip.styleSheet() == theme.tag_chip_untranslated_qss()

    def test_translation_note_visible_only_when_translated(self, widget, sample_tags):
        """脚注は非英語選択時のみ表示されること。"""
        translations = {10: {"japanese": "1人の女の子"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])

        # 英語選択中は脚注非表示
        assert widget._tags_translation_note.isHidden()

        widget._lang_combo.setCurrentText("japanese")
        assert not widget._tags_translation_note.isHidden()
        assert "canonical" in widget._tags_translation_note.text()

        # 英語へ戻すと再び非表示
        widget._lang_combo.setCurrentText("english")
        assert widget._tags_translation_note.isHidden()

    def test_clear_data_removes_chips(self, widget, sample_tags):
        """clear_data でチップが空になること。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        assert len(self._chip_texts(widget)) == 3

        widget.clear_data()
        # placeholder ("-") のみ
        assert self._chip_texts(widget) == ["-"]

    # ─── score_labels compact pill display (Issue #284 / ADR 0028) ─────

    @pytest.fixture
    def sample_score_labels(self):
        """canonical scorer の score_labels (ADR 0028 のデータ形状)"""
        return [
            {
                "label": "very aesthetic",
                "model": "aesthetic_shadow_v1",
                "model_id": 1,
                "is_edited_manually": False,
            },
            {
                "label": "aesthetic",
                "model": "cafe_aesthetic",
                "model_id": 2,
                "is_edited_manually": False,
            },
        ]

    def test_score_labels_empty_shows_placeholder(self, widget):
        """score_labels 空時、container が hidden で placeholder のみ。"""
        widget.update_data(AnnotationData(score_labels=[]))
        # placeholder は visible 設定で残る (qtbot 上は親 invisible だが isHidden() は False)
        assert not widget.labelScoreLabelsPlaceholder.isHidden()
        assert widget._score_labels_container.isHidden()

    def test_score_labels_single_pill(self, widget):
        """1 scorer で 1 pill が描画され、[model] label を含む。"""
        data = AnnotationData(
            score_labels=[
                {
                    "label": "very aesthetic",
                    "model": "aesthetic_shadow_v1",
                    "model_id": 1,
                    "is_edited_manually": False,
                }
            ]
        )
        widget.update_data(data)

        # pill (1) + stretch (1)
        assert widget._score_labels_layout.count() == 2
        pill = widget._score_labels_layout.itemAt(0).widget()
        assert pill is not None
        assert "aesthetic_shadow_v1" in pill.text()
        assert "very aesthetic" in pill.text()
        # container は visible 設定、placeholder は hidden 設定
        assert not widget._score_labels_container.isHidden()
        assert widget.labelScoreLabelsPlaceholder.isHidden()

    def test_score_labels_multi_pills(self, widget, sample_score_labels):
        """複数 scorer で複数 pill が描画される。"""
        widget.update_data(AnnotationData(score_labels=sample_score_labels))

        # 2 pill + 1 stretch
        assert widget._score_labels_layout.count() == 3
        pill_texts = [widget._score_labels_layout.itemAt(i).widget().text() for i in range(2)]
        assert any("aesthetic_shadow_v1" in t for t in pill_texts)
        assert any("cafe_aesthetic" in t for t in pill_texts)

    def test_score_labels_re_render_clears_previous(self, widget, sample_score_labels):
        """update_data 再呼出しで前 pill がクリアされて再描画される。"""
        widget.update_data(AnnotationData(score_labels=sample_score_labels))
        assert widget._score_labels_layout.count() == 3

        widget.update_data(AnnotationData(score_labels=[sample_score_labels[0]]))
        # 1 pill + 1 stretch
        assert widget._score_labels_layout.count() == 2

    def test_set_group_box_visibility_score_labels_false(self, widget):
        """score_labels=False で groupBoxScoreLabels が hidden になる。"""
        widget.set_group_box_visibility(score_labels=False)
        assert widget.groupBoxScoreLabels.isHidden()

    def test_set_group_box_visibility_backward_compatible(self, widget):
        """score_labels 省略時 (既存 caller) は default True で表示維持。"""
        widget.set_group_box_visibility(tags=False)
        # score_labels は default で visible 設定 → isHidden() は False
        assert not widget.groupBoxScoreLabels.isHidden()

    @pytest.fixture
    def sample_ratings(self):
        """Issue #334: model 別 rating record のデータ形状。"""
        return [
            {
                "model": "wd-vit-tagger-v3",
                "model_id": 42,
                "normalized_rating": "R",
                "raw_rating_value": "questionable",
                "confidence_score": 0.91,
                "source": "AI",
            },
            {
                "model": "MANUAL_EDIT",
                "model_id": 1,
                "normalized_rating": "PG",
                "raw_rating_value": "PG",
                "confidence_score": None,
                "source": "Manual",
            },
        ]

    def test_ratings_empty_shows_placeholder(self, widget):
        """ratings 空時、table が hidden で placeholder のみ。"""
        widget.update_data(AnnotationData(ratings=[]))

        assert not widget.labelRatingsPlaceholder.isHidden()
        assert widget.tableWidgetRatings.isHidden()

    def test_ratings_table_rows(self, widget, sample_ratings):
        """複数 rating record を model 別 table として表示する。"""
        widget.update_data(AnnotationData(ratings=sample_ratings))

        assert widget.tableWidgetRatings.rowCount() == 2
        assert widget.tableWidgetRatings.item(0, 0).text() == "wd-vit-tagger-v3"
        assert widget.tableWidgetRatings.item(0, 1).text() == "R"
        assert widget.tableWidgetRatings.item(0, 2).text() == "questionable"
        assert widget.tableWidgetRatings.item(0, 3).text() == "0.91"
        assert widget.tableWidgetRatings.item(0, 4).text() == "AI"
        assert widget.tableWidgetRatings.item(1, 0).text() == "MANUAL_EDIT"
        assert widget.tableWidgetRatings.item(1, 3).text() == "-"
        assert widget.tableWidgetRatings.item(1, 4).text() == "Manual"
        assert not widget.tableWidgetRatings.isHidden()
        assert widget.labelRatingsPlaceholder.isHidden()

    def test_ratings_re_render_clears_previous(self, widget, sample_ratings):
        """update_data 再呼出しで前 rating rows がクリアされる。"""
        widget.update_data(AnnotationData(ratings=sample_ratings))
        assert widget.tableWidgetRatings.rowCount() == 2

        widget.update_data(AnnotationData(ratings=[sample_ratings[0]]))

        assert widget.tableWidgetRatings.rowCount() == 1
        assert widget.tableWidgetRatings.item(0, 0).text() == "wd-vit-tagger-v3"

    def test_set_group_box_visibility_ratings_false(self, widget):
        """ratings=False で groupBoxRatings が hidden になる。"""
        widget.set_group_box_visibility(ratings=False)
        assert widget.groupBoxRatings.isHidden()

    def test_copy_selected_rating_cells_to_clipboard(self, widget, sample_ratings):
        """rating 詳細テーブルの選択セルを TSV としてコピーする。"""
        widget.update_data(AnnotationData(ratings=sample_ratings))
        widget.tableWidgetRatings.setRangeSelected(QTableWidgetSelectionRange(0, 0, 0, 2), True)

        assert widget.copy_selected_rating_cells_to_clipboard() is True
        assert QApplication.clipboard().text() == "wd-vit-tagger-v3\tR\tquestionable"


class TestAnnotationTagChipSelectionCopy:
    """タグ chip 選択コピー (Issue #814): カンマ区切りで canonical 原文を取得する。"""

    @pytest.fixture
    def widget(self, qtbot):
        w = AnnotationDataDisplayWidget()
        qtbot.addWidget(w)
        return w

    @pytest.fixture
    def sample_tags(self):
        return [
            {"tag": "1girl", "tag_id": 10, "model_name": "wd", "source": "AI"},
            {"tag": "flower", "tag_id": 20, "model_name": "wd", "source": "AI"},
            {"tag": "solo", "tag_id": None, "model_name": "wd", "source": "AI"},
        ]

    def test_chips_are_selectable_instances(self, widget, sample_tags):
        """描画される chip は SelectableTagChip インスタンスであること。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        assert len(widget._tag_chips) == 3
        assert all(isinstance(chip, SelectableTagChip) for chip in widget._tag_chips)
        assert [chip.canonical for chip in widget._tag_chips] == ["1girl", "flower", "solo"]

    def test_click_toggles_selection_and_style(self, widget, sample_tags):
        """chip クリックで選択がトグルし、選択時は base_qss と異なる強調 QSS になる。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        chip = widget._tag_chips[0]
        assert chip.selected is False
        base = chip.styleSheet()

        chip.clicked.emit()
        assert chip.selected is True
        assert chip.styleSheet() != base

        chip.clicked.emit()
        assert chip.selected is False
        assert chip.styleSheet() == chip.base_qss

    def test_copy_without_selection_copies_all_comma_separated(self, widget, sample_tags):
        """無選択時は全タグをカンマ区切りでコピーすること。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        assert widget.copy_selected_tags_to_clipboard() is True
        assert QApplication.clipboard().text() == "1girl, flower, solo"

    def test_copy_with_selection_copies_only_selected(self, widget, sample_tags):
        """選択時は選択中タグのみをカンマ区切りでコピーすること。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        widget._tag_chips[0].clicked.emit()  # 1girl を選択
        widget._tag_chips[2].clicked.emit()  # solo を選択

        assert widget.copy_selected_tags_to_clipboard() is True
        assert QApplication.clipboard().text() == "1girl, solo"

    def test_copy_uses_canonical_not_translated(self, widget, sample_tags):
        """言語切替で表示が翻訳でも、コピーは canonical 原文を使うこと。"""
        translations = {10: {"japanese": "1人の女の子"}, 20: {"japanese": "花"}}
        data = AnnotationData(
            tags=sample_tags,
            tag_translations=translations,
            available_languages=["japanese"],
        )
        widget.update_data(data)
        widget.initialize_language_selector(["japanese"])
        widget._lang_combo.setCurrentText("japanese")

        # 表示は翻訳テキストだが canonical は原文
        assert [chip.text() for chip in widget._tag_chips] == ["1人の女の子", "花", "solo"]
        assert widget.copy_selected_tags_to_clipboard() is True
        assert QApplication.clipboard().text() == "1girl, flower, solo"

    def test_copy_returns_false_when_no_tags(self, widget):
        """タグが無ければコピーは False を返すこと。"""
        widget.clear_data()
        assert widget._tag_chips == []
        assert widget.copy_selected_tags_to_clipboard() is False

    def test_selection_reset_on_re_render(self, widget, sample_tags):
        """再描画 (言語切替等) で選択状態がリセットされること。"""
        widget.update_data(AnnotationData(tags=sample_tags))
        widget._tag_chips[0].clicked.emit()
        assert widget._tag_chips[0].selected is True

        widget.update_data(AnnotationData(tags=sample_tags))
        assert all(chip.selected is False for chip in widget._tag_chips)


class TestQualityTierBadge:
    """ADR 0029: 統一品質 tier badge の表示挙動。"""

    @pytest.fixture
    def widget(self, qtbot):
        w = AnnotationDataDisplayWidget()
        qtbot.addWidget(w)
        return w

    def test_badge_hidden_initially(self, widget):
        """初期状態で badge が hidden。"""
        assert widget._quality_tier_label.isHidden()

    def test_badge_hidden_when_quality_summary_empty(self, widget):
        """quality_summary が空 dict のとき badge は hidden (旧データ互換)。"""
        widget.update_data(AnnotationData(quality_summary={}))
        assert widget._quality_tier_label.isHidden()

    def test_badge_shows_no_score_sentinel(self, widget):
        """tier='no score' のとき badge が表示され known_count=0 用の text を出す。"""
        widget.update_data(
            AnnotationData(
                quality_summary={
                    "tier": "no score",
                    "is_unanimous": False,
                    "known_count": 0,
                    "unknown_count": 0,
                    "no_score": True,
                    "votes": [],
                }
            )
        )
        assert not widget._quality_tier_label.isHidden()
        assert "no score" in widget._quality_tier_label.text()

    def test_badge_shows_unknown_sentinel(self, widget):
        """tier='unknown' のとき badge が表示される。"""
        widget.update_data(
            AnnotationData(
                quality_summary={
                    "tier": "unknown",
                    "is_unanimous": False,
                    "known_count": 0,
                    "unknown_count": 1,
                    "no_score": False,
                    "votes": [],
                }
            )
        )
        assert not widget._quality_tier_label.isHidden()
        assert "unknown" in widget._quality_tier_label.text()

    def test_badge_shows_tier_with_count(self, widget):
        """known_count >= 1 のとき '品質: <tier> (<n> scorer)' フォーマット。"""
        widget.update_data(
            AnnotationData(
                quality_summary={
                    "tier": "best quality",
                    "is_unanimous": False,
                    "known_count": 2,
                    "unknown_count": 0,
                    "no_score": False,
                    "votes": [],
                }
            )
        )
        text = widget._quality_tier_label.text()
        assert "best quality" in text
        assert "2 scorer" in text
        assert "一致" not in text

    def test_badge_shows_unanimous_suffix(self, widget):
        """is_unanimous=True で全 scorer 一致 suffix が付与される。"""
        widget.update_data(
            AnnotationData(
                quality_summary={
                    "tier": "masterpiece",
                    "is_unanimous": True,
                    "known_count": 3,
                    "unknown_count": 0,
                    "no_score": False,
                    "votes": [],
                }
            )
        )
        text = widget._quality_tier_label.text()
        assert "masterpiece" in text
        assert "3 scorer" in text
        assert "全 scorer 一致" in text

    def test_badge_clear_data_hides_badge(self, widget):
        """clear_data で badge が hidden に戻る。"""
        widget.update_data(
            AnnotationData(
                quality_summary={
                    "tier": "best quality",
                    "is_unanimous": True,
                    "known_count": 1,
                    "unknown_count": 0,
                    "no_score": False,
                    "votes": [],
                }
            )
        )
        assert not widget._quality_tier_label.isHidden()

        widget.clear_data()
        assert widget._quality_tier_label.isHidden()


class TestAnnotationDataDisplaySoftRejectEdit:
    """TagEdit soft-reject 編集モード (Issue #792)。"""

    @pytest.fixture
    def widget(self, qtbot):
        w = AnnotationDataDisplayWidget()
        qtbot.addWidget(w)
        return w

    def test_edit_mode_off_renders_plain_chip_no_reject_button(self, widget):
        from PySide6.QtWidgets import QToolButton

        widget.update_data(AnnotationData(tags=[{"tag": "1girl", "tag_id": 10}]))
        assert widget.findChildren(QToolButton, "tagRejectButton") == []

    def test_edit_mode_on_adds_reject_button_emitting_canonical_tag(self, widget, qtbot):
        from PySide6.QtWidgets import QToolButton

        widget.set_tag_edit_enabled(True)
        widget.update_data(AnnotationData(tags=[{"tag": "1girl", "tag_id": 10}]))
        buttons = widget.findChildren(QToolButton, "tagRejectButton")
        assert len(buttons) == 1
        with qtbot.waitSignal(widget.tag_reject_requested, timeout=1000) as blocker:
            buttons[0].click()
        assert blocker.args == ["1girl"]

    def test_manual_add_input_emits_tag_add_requested(self, widget, qtbot):
        widget.set_tag_edit_enabled(True)
        widget._tag_add_input.setText("new_tag")
        with qtbot.waitSignal(widget.tag_add_requested, timeout=1000) as blocker:
            widget._tag_add_input.returnPressed.emit()
        assert blocker.args == ["new_tag"]
        assert widget._tag_add_input.text() == ""

    def test_set_rejected_tags_renders_restore_chips(self, widget, qtbot):
        from PySide6.QtWidgets import QPushButton

        widget.set_tag_edit_enabled(True)
        widget.set_rejected_tags(["bad_tag"])
        chips = widget.findChildren(QPushButton, "rejectedTagChip")
        assert len(chips) == 1
        assert chips[0].text() == "bad_tag"
        with qtbot.waitSignal(widget.tag_restore_requested, timeout=1000) as blocker:
            chips[0].click()
        assert blocker.args == ["bad_tag"]

    def test_rejected_section_hidden_when_edit_off(self, widget):
        widget.set_rejected_tags(["bad_tag"])
        assert not widget._rejected_container.isVisible()


class TestMainLayoutTrailingStretch:
    """#823: 主レイアウト末尾の stretch で最下部グループの過大化を防ぐ。"""

    @pytest.fixture
    def widget(self, qtbot):
        w = AnnotationDataDisplayWidget()
        qtbot.addWidget(w)
        return w

    def test_main_layout_ends_with_stretch(self, widget):
        """verticalLayoutMain の最後尾に spacer (stretch) が存在する。

        親が本 widget を縦に展開させても、余剰高さが末尾 stretch に逃げ
        groupBoxRatings (レーティング詳細) が余白を吸収しないことを担保する。
        """
        layout = widget.verticalLayoutMain
        last_item = layout.itemAt(layout.count() - 1)
        assert last_item.spacerItem() is not None
        # 最後尾が groupBoxRatings 自体ではない (= ratings の後ろに stretch がある)
        assert last_item.widget() is None
