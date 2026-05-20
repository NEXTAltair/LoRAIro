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
