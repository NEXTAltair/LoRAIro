"""StagingTagPanel の pytest-qt テストスイート（Issue #947）。

テストカバレッジ:
- 初期化・UI コンポーネント検証
- load_tags によるタグ集計表示
- タグ行クリック → filter_tag_changed emit
- リセットボタン → filter_tag_changed(None) emit
- ソート切替（件数順 / 名前順 / 手動のみ）
- インクリメンタル検索フィルタ
- ⊘ 出力除外 → overlay_exclude_requested emit
- ✎ reject(DB) → db_reject_everywhere_requested emit
- ⇄ 置換 → overlay_replace_requested emit
- 置換先タグ空・同値ガード
- service 委譲（薄い widget）の確認
- 手動タグの ✎ 表示
- アクションバーの可視性制御
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lorairo.gui.widgets.staging_tag_panel import (
    _SORT_COUNT,
    _SORT_MANUAL_ONLY,
    _SORT_NAME,
    StagingTagPanel,
)
from lorairo.services.staging_tag_aggregation import StagingTagAggregationService, TagCount

# ------------------------------------------------------------------
# ヘルパー
# ------------------------------------------------------------------


def _make_service(tags: list[TagCount] | None = None) -> MagicMock:
    """StagingTagAggregationService をモックして返す。

    Args:
        tags: aggregate() が返す TagCount リスト。None なら空リスト。

    Returns:
        service のモックオブジェクト。
    """
    service = MagicMock(spec=StagingTagAggregationService)
    service.aggregate.return_value = tags if tags is not None else []
    return service


def _sample_tags() -> list[TagCount]:
    """テスト用 TagCount リスト（件数降順・タグ名昇順）。"""
    return [
        TagCount(tag="long_hair", count=10, manual=False),
        TagCount(tag="smile", count=7, manual=True),
        TagCount(tag="blush", count=5, manual=False),
        TagCount(tag="1girl", count=3, manual=False),
    ]


@pytest.fixture
def service() -> MagicMock:
    """デフォルトのモックサービス（サンプルタグを返す）。"""
    return _make_service(_sample_tags())


@pytest.fixture
def panel(qtbot, service: MagicMock) -> StagingTagPanel:
    """StagingTagPanel フィクスチャ（サービスをモック注入済み）。"""
    w = StagingTagPanel(service=service)
    qtbot.addWidget(w)
    return w


@pytest.fixture
def loaded_panel(qtbot, service: MagicMock) -> StagingTagPanel:
    """タグをロード済みの StagingTagPanel フィクスチャ。"""
    w = StagingTagPanel(service=service)
    qtbot.addWidget(w)
    w.load_tags([1, 2, 3])
    return w


# ------------------------------------------------------------------
# 初期化テスト
# ------------------------------------------------------------------


class TestInitialization:
    """初期化・UI コンポーネント検証。"""

    @pytest.mark.gui
    def test_widget_creates_without_error(self, panel: StagingTagPanel) -> None:
        """ウィジェットが例外なく生成されること。"""
        assert panel is not None

    @pytest.mark.gui
    def test_ui_components_present(self, panel: StagingTagPanel) -> None:
        """必要な UI コンポーネントが存在すること。"""
        assert panel._search_edit is not None
        assert panel._sort_combo is not None
        assert panel._list_widget is not None
        assert panel._reset_btn is not None
        assert panel._action_bar is not None
        assert panel._exclude_btn is not None
        assert panel._db_reject_btn is not None
        assert panel._replace_btn is not None
        assert panel._replace_to_edit is not None

    @pytest.mark.gui
    def test_action_bar_hidden_initially(self, panel: StagingTagPanel) -> None:
        """初期状態でアクションバーが hidden 状態であること。"""
        assert panel._action_bar.isHidden()

    @pytest.mark.gui
    def test_initial_image_ids_empty(self, panel: StagingTagPanel) -> None:
        """初期状態で image_ids が空であること。"""
        assert panel.get_image_ids() == []

    @pytest.mark.gui
    def test_sort_combo_initial_index(self, panel: StagingTagPanel) -> None:
        """ソートコンボボックスの初期値が件数順であること。"""
        assert panel._sort_combo.currentIndex() == _SORT_COUNT


# ------------------------------------------------------------------
# load_tags テスト
# ------------------------------------------------------------------


class TestLoadTags:
    """load_tags によるタグ集計表示テスト。"""

    @pytest.mark.gui
    def test_load_tags_calls_service_aggregate(self, panel: StagingTagPanel, service: MagicMock) -> None:
        """load_tags が service.aggregate を呼び出すこと（service 委譲）。"""
        panel.load_tags([1, 2, 3])
        service.aggregate.assert_called_once_with([1, 2, 3])

    @pytest.mark.gui
    def test_load_tags_populates_list(self, loaded_panel: StagingTagPanel) -> None:
        """load_tags 後にリストにタグが表示されること。"""
        assert loaded_panel._list_widget.count() == 4

    @pytest.mark.gui
    def test_load_tags_empty_image_ids(self, qtbot, service: MagicMock) -> None:
        """空の image_ids を渡した場合、空リストでサービスを呼ぶこと。"""
        service.aggregate.return_value = []
        panel = StagingTagPanel(service=service)
        qtbot.addWidget(panel)
        panel.load_tags([])
        service.aggregate.assert_called_once_with([])
        assert panel._list_widget.count() == 0

    @pytest.mark.gui
    def test_load_tags_updates_image_ids(self, loaded_panel: StagingTagPanel) -> None:
        """load_tags 後に get_image_ids が正しい値を返すこと。"""
        assert loaded_panel.get_image_ids() == [1, 2, 3]

    @pytest.mark.gui
    def test_load_tags_updates_reset_btn_text(self, loaded_panel: StagingTagPanel) -> None:
        """load_tags 後にリセットボタンのテキストが更新されること。"""
        assert "3" in loaded_panel._reset_btn.text()

    @pytest.mark.gui
    def test_load_tags_shows_manual_mark(self, loaded_panel: StagingTagPanel) -> None:
        """手動タグに ✎ マークが表示されること。"""
        # smile が manual=True
        items = [loaded_panel._list_widget.item(i).text() for i in range(loaded_panel._list_widget.count())]
        smile_items = [t for t in items if "smile" in t]
        assert len(smile_items) == 1
        assert "✎" in smile_items[0]

    @pytest.mark.gui
    def test_load_tags_no_manual_mark_for_ai_tag(self, loaded_panel: StagingTagPanel) -> None:
        """AI タグ（manual=False）に ✎ マークが表示されないこと。"""
        items = [loaded_panel._list_widget.item(i).text() for i in range(loaded_panel._list_widget.count())]
        long_hair_items = [t for t in items if "long_hair" in t]
        assert len(long_hair_items) == 1
        assert "✎" not in long_hair_items[0]

    @pytest.mark.gui
    def test_load_tags_updates_summary_label(self, loaded_panel: StagingTagPanel) -> None:
        """load_tags 後にサマリラベルにタグ数と画像数が表示されること。"""
        text = loaded_panel._summary_label.text()
        assert "4" in text  # 4 タグ
        assert "3" in text  # 3 枚

    @pytest.mark.gui
    def test_get_displayed_tags_returns_current(self, loaded_panel: StagingTagPanel) -> None:
        """get_displayed_tags が現在表示中の TagCount リストを返すこと。"""
        displayed = loaded_panel.get_displayed_tags()
        assert len(displayed) == 4
        assert all(isinstance(t, TagCount) for t in displayed)


# ------------------------------------------------------------------
# シグナル: filter_tag_changed
# ------------------------------------------------------------------


class TestFilterTagChangedSignal:
    """タグ行クリックとリセットの filter_tag_changed emit テスト。"""

    @pytest.mark.gui
    def test_item_click_emits_filter_tag_changed(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """タグ行クリックで filter_tag_changed(str) が emit されること。"""
        with qtbot.waitSignal(loaded_panel.filter_tag_changed, timeout=1000) as blocker:
            loaded_panel._list_widget.item(0).setSelected(True)
            loaded_panel._list_widget.itemClicked.emit(loaded_panel._list_widget.item(0))

        assert isinstance(blocker.args[0], str)
        assert blocker.args[0] == "long_hair"

    @pytest.mark.gui
    def test_reset_btn_emits_filter_tag_changed_none(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """リセットボタンクリックで filter_tag_changed(None) が emit されること。"""
        with qtbot.waitSignal(loaded_panel.filter_tag_changed, timeout=1000) as blocker:
            loaded_panel._reset_btn.click()

        assert blocker.args[0] is None

    @pytest.mark.gui
    def test_item_click_second_tag(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """2番目のタグ行クリックで正しいタグ文字列が emit されること。"""
        with qtbot.waitSignal(loaded_panel.filter_tag_changed, timeout=1000) as blocker:
            loaded_panel._list_widget.item(1).setSelected(True)
            loaded_panel._list_widget.itemClicked.emit(loaded_panel._list_widget.item(1))

        assert blocker.args[0] == "smile"

    @pytest.mark.gui
    def test_load_tags_emits_none_when_active_filter_cleared(
        self, qtbot, loaded_panel: StagingTagPanel
    ) -> None:
        """アクティブフィルタ中に load_tags すると filter_tag_changed(None) が emit されること。

        接続先サムネペインが古いタグで絞り込まれたまま取り残されるのを防ぐ。
        """
        # まずタグ行をクリックしてフィルタをアクティブにする
        loaded_panel._list_widget.itemClicked.emit(loaded_panel._list_widget.item(0))
        assert loaded_panel._active_filter_tag == "long_hair"

        with qtbot.waitSignal(loaded_panel.filter_tag_changed, timeout=1000) as blocker:
            loaded_panel.load_tags([1, 2, 3])

        assert blocker.args[0] is None
        assert loaded_panel._active_filter_tag is None

    @pytest.mark.gui
    def test_load_tags_no_emit_when_no_active_filter(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """フィルタ未適用なら load_tags は filter_tag_changed を emit しないこと。"""
        received: list[object] = []
        loaded_panel.filter_tag_changed.connect(received.append)

        loaded_panel.load_tags([1, 2, 3])

        assert received == []


# ------------------------------------------------------------------
# シグナル: overlay_exclude_requested
# ------------------------------------------------------------------


class TestOverlayExcludeSignal:
    """⊘ 出力除外ボタンの overlay_exclude_requested emit テスト。"""

    @pytest.mark.gui
    def test_exclude_btn_emits_signal(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """除外ボタンクリックで overlay_exclude_requested が emit されること。"""
        # タグを選択してからボタンをクリック
        loaded_panel._list_widget.setCurrentRow(0)

        with qtbot.waitSignal(loaded_panel.overlay_exclude_requested, timeout=1000) as blocker:
            loaded_panel._exclude_btn.click()

        assert blocker.args[0] == "long_hair"

    @pytest.mark.gui
    def test_exclude_btn_no_signal_without_selection(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """選択なし状態でボタンクリックしてもシグナルが emit されないこと。"""
        loaded_panel._list_widget.clearSelection()
        received: list[str] = []
        loaded_panel.overlay_exclude_requested.connect(received.append)

        loaded_panel._exclude_btn.click()

        assert received == []


# ------------------------------------------------------------------
# シグナル: db_reject_everywhere_requested
# ------------------------------------------------------------------


class TestDbRejectSignal:
    """✎ reject(DB) ボタンの db_reject_everywhere_requested emit テスト。"""

    @pytest.mark.gui
    def test_db_reject_btn_emits_signal(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """reject(DB) ボタンクリックで db_reject_everywhere_requested が emit されること。"""
        loaded_panel._list_widget.setCurrentRow(0)

        with qtbot.waitSignal(loaded_panel.db_reject_everywhere_requested, timeout=1000) as blocker:
            loaded_panel._db_reject_btn.click()

        assert blocker.args[0] == "long_hair"

    @pytest.mark.gui
    def test_db_reject_btn_no_signal_without_selection(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """選択なし状態でボタンクリックしてもシグナルが emit されないこと。"""
        loaded_panel._list_widget.clearSelection()
        received: list[str] = []
        loaded_panel.db_reject_everywhere_requested.connect(received.append)

        loaded_panel._db_reject_btn.click()

        assert received == []


# ------------------------------------------------------------------
# シグナル: overlay_replace_requested
# ------------------------------------------------------------------


class TestOverlayReplaceSignal:
    """⇄ 置換ボタンの overlay_replace_requested emit テスト。"""

    @pytest.mark.gui
    def test_replace_btn_emits_signal(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """置換先タグを入力してボタンクリックすると overlay_replace_requested が emit されること。

        置換先はアンダースコア除去・空白整形で正規化される（new_tag → new tag）。
        """
        loaded_panel._list_widget.setCurrentRow(0)
        loaded_panel._replace_to_edit.setText("new_tag")

        with qtbot.waitSignal(loaded_panel.overlay_replace_requested, timeout=1000) as blocker:
            loaded_panel._replace_btn.click()

        assert blocker.args == ["long_hair", "new tag"]

    @pytest.mark.gui
    def test_replace_btn_no_signal_when_to_empty(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """置換先タグが空のときシグナルが emit されないこと。"""
        loaded_panel._list_widget.setCurrentRow(0)
        loaded_panel._replace_to_edit.setText("")
        received: list[tuple[str, str]] = []
        loaded_panel.overlay_replace_requested.connect(lambda f, t: received.append((f, t)))

        loaded_panel._replace_btn.click()

        assert received == []

    @pytest.mark.gui
    def test_replace_btn_no_signal_when_same_tag(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """置換先が選択タグと正規化後に等価ならシグナルが emit されないこと。

        long_hair を long_hair（正規化で long hair）に置換しようとしても、
        選択タグ long_hair の正規化形 long hair と一致するため no-op になる。
        """
        loaded_panel._list_widget.setCurrentRow(0)
        loaded_panel._replace_to_edit.setText("long_hair")
        received: list[tuple[str, str]] = []
        loaded_panel.overlay_replace_requested.connect(lambda f, t: received.append((f, t)))

        loaded_panel._replace_btn.click()

        assert received == []

    @pytest.mark.gui
    def test_replace_btn_no_signal_without_selection(self, qtbot, loaded_panel: StagingTagPanel) -> None:
        """選択なし状態でボタンクリックしてもシグナルが emit されないこと。"""
        loaded_panel._list_widget.clearSelection()
        loaded_panel._replace_to_edit.setText("new_tag")
        received: list[tuple[str, str]] = []
        loaded_panel.overlay_replace_requested.connect(lambda f, t: received.append((f, t)))

        loaded_panel._replace_btn.click()

        assert received == []

    @pytest.mark.gui
    def test_replace_normalizes_underscore_and_whitespace(
        self, qtbot, loaded_panel: StagingTagPanel
    ) -> None:
        """置換先タグの前後空白がトリムされ、アンダースコアが除去されること。"""
        loaded_panel._list_widget.setCurrentRow(0)
        loaded_panel._replace_to_edit.setText("  trimmed_tag  ")

        with qtbot.waitSignal(loaded_panel.overlay_replace_requested, timeout=1000) as blocker:
            loaded_panel._replace_btn.click()

        assert blocker.args[1] == "trimmed tag"

    @pytest.mark.gui
    def test_replace_btn_no_signal_when_to_contains_comma(
        self, qtbot, loaded_panel: StagingTagPanel
    ) -> None:
        """置換先にカンマが含まれるとシグナルが emit されないこと。

        apply_overlay は to_tag を convert 前タグとして扱い DatasetExportService が
        カンマ連結するため、カンマ混入は余分なタグを生む。これを未然に弾く。
        """
        loaded_panel._list_widget.setCurrentRow(0)
        loaded_panel._replace_to_edit.setText("foo, bar")
        received: list[tuple[str, str]] = []
        loaded_panel.overlay_replace_requested.connect(lambda f, t: received.append((f, t)))

        loaded_panel._replace_btn.click()

        assert received == []


# ------------------------------------------------------------------
# ソートテスト
# ------------------------------------------------------------------


class TestSortBehavior:
    """ソート切替テスト。"""

    @pytest.mark.gui
    def test_sort_by_count_default(self, loaded_panel: StagingTagPanel) -> None:
        """デフォルト（件数順）でタグが件数降順で表示されること。"""
        assert loaded_panel._sort_combo.currentIndex() == _SORT_COUNT
        displayed = loaded_panel.get_displayed_tags()
        counts = [t.count for t in displayed]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.gui
    def test_sort_by_name(self, loaded_panel: StagingTagPanel) -> None:
        """名前順ソートでタグが名前昇順で表示されること。"""
        loaded_panel._sort_combo.setCurrentIndex(_SORT_NAME)
        displayed = loaded_panel.get_displayed_tags()
        tags = [t.tag for t in displayed]
        assert tags == sorted(tags)

    @pytest.mark.gui
    def test_sort_manual_only(self, loaded_panel: StagingTagPanel) -> None:
        """手動のみフィルタで manual=True のタグだけ表示されること。"""
        loaded_panel._sort_combo.setCurrentIndex(_SORT_MANUAL_ONLY)
        displayed = loaded_panel.get_displayed_tags()
        assert all(t.manual for t in displayed)
        # sample_tags で manual=True は smile のみ
        assert len(displayed) == 1
        assert displayed[0].tag == "smile"

    @pytest.mark.gui
    def test_sort_by_name_list_count(self, loaded_panel: StagingTagPanel) -> None:
        """名前順ソートでリストの件数が変わらないこと。"""
        loaded_panel._sort_combo.setCurrentIndex(_SORT_NAME)
        assert loaded_panel._list_widget.count() == 4


# ------------------------------------------------------------------
# 検索フィルタテスト
# ------------------------------------------------------------------


class TestSearchFilter:
    """インクリメンタル検索フィルタテスト。"""

    @pytest.mark.gui
    def test_search_filters_tags(self, loaded_panel: StagingTagPanel) -> None:
        """検索テキスト入力で一致するタグのみ表示されること。"""
        loaded_panel._search_edit.setText("hair")
        displayed = loaded_panel.get_displayed_tags()
        assert len(displayed) == 1
        assert displayed[0].tag == "long_hair"

    @pytest.mark.gui
    def test_search_is_case_insensitive(self, loaded_panel: StagingTagPanel) -> None:
        """検索が大文字小文字を区別しないこと。"""
        loaded_panel._search_edit.setText("HAIR")
        displayed = loaded_panel.get_displayed_tags()
        assert len(displayed) == 1
        assert displayed[0].tag == "long_hair"

    @pytest.mark.gui
    def test_search_empty_shows_all(self, loaded_panel: StagingTagPanel) -> None:
        """空の検索テキストで全タグが表示されること。"""
        loaded_panel._search_edit.setText("hair")
        loaded_panel._search_edit.setText("")
        assert loaded_panel._list_widget.count() == 4

    @pytest.mark.gui
    def test_search_no_match_shows_empty(self, loaded_panel: StagingTagPanel) -> None:
        """一致なしの検索でリストが空になること。"""
        loaded_panel._search_edit.setText("zzz_no_match_zzz")
        assert loaded_panel._list_widget.count() == 0

    @pytest.mark.gui
    def test_search_partial_match(self, loaded_panel: StagingTagPanel) -> None:
        """部分一致で複数タグが表示されること（"irl" を含む 1girl のみ）。"""
        loaded_panel._search_edit.setText("irl")
        displayed = loaded_panel.get_displayed_tags()
        tags = {t.tag for t in displayed}
        # "irl" を含むのは 1girl のみ
        assert "1girl" in tags
        assert "long_hair" not in tags
        assert "smile" not in tags
        assert "blush" not in tags

    @pytest.mark.gui
    def test_summary_shows_filter_note_when_filtered(self, loaded_panel: StagingTagPanel) -> None:
        """検索フィルタ中にサマリに「絞り込み中」と表示されること。"""
        loaded_panel._search_edit.setText("hair")
        text = loaded_panel._summary_label.text()
        assert "絞り込み中" in text

    @pytest.mark.gui
    def test_summary_no_filter_note_when_all_shown(self, loaded_panel: StagingTagPanel) -> None:
        """全タグ表示時にサマリに「絞り込み中」が表示されないこと。"""
        loaded_panel._search_edit.setText("")
        text = loaded_panel._summary_label.text()
        assert "絞り込み中" not in text


# ------------------------------------------------------------------
# アクションバー可視性テスト
# ------------------------------------------------------------------


class TestActionBarVisibility:
    """アクションバーの可視性制御テスト。"""

    @pytest.mark.gui
    def test_action_bar_shown_on_selection(self, loaded_panel: StagingTagPanel) -> None:
        """タグ行選択でアクションバーが非 hidden 状態になること。

        isVisible() は親ウィジェットが show() されていない場合に False になるため、
        明示的な hide 状態を示す isHidden() で検証する。
        """
        loaded_panel._list_widget.setCurrentRow(0)
        # setVisible(True) が呼ばれ isHidden() == False になること
        assert not loaded_panel._action_bar.isHidden()

    @pytest.mark.gui
    def test_action_bar_hidden_after_clear_selection(self, loaded_panel: StagingTagPanel) -> None:
        """選択解除でアクションバーが hidden 状態になること。

        clearSelection() は currentItem() を維持するため setCurrentRow(-1) を使用する。
        """
        loaded_panel._list_widget.setCurrentRow(0)
        assert not loaded_panel._action_bar.isHidden()

        # setCurrentRow(-1) で current item と selection を両方クリアする
        loaded_panel._list_widget.setCurrentRow(-1)
        loaded_panel._update_action_bar_visibility()
        assert loaded_panel._action_bar.isHidden()

    @pytest.mark.gui
    def test_action_tag_label_shows_selected_tag(self, loaded_panel: StagingTagPanel) -> None:
        """アクションバーに選択タグ名が表示されること。"""
        loaded_panel._list_widget.setCurrentRow(0)
        label_text = loaded_panel._action_tag_label.text()
        assert "long_hair" in label_text

    @pytest.mark.gui
    def test_replace_edit_cleared_on_selection_change(self, loaded_panel: StagingTagPanel) -> None:
        """タグ行を切り替えたとき置換入力欄がクリアされること。"""
        loaded_panel._list_widget.setCurrentRow(0)
        loaded_panel._replace_to_edit.setText("some_text")

        # 別の行に切り替え
        loaded_panel._list_widget.setCurrentRow(1)
        assert loaded_panel._replace_to_edit.text() == ""


# ------------------------------------------------------------------
# service 委譲の確認
# ------------------------------------------------------------------


class TestServiceDelegation:
    """ロジックが service に委譲されていることの確認。"""

    @pytest.mark.gui
    def test_aggregate_called_with_correct_ids(self, qtbot) -> None:
        """load_tags の呼び出しで service.aggregate に正確な image_ids が渡されること。"""
        service = _make_service([])
        panel = StagingTagPanel(service=service)
        qtbot.addWidget(panel)

        panel.load_tags([10, 20, 30])

        service.aggregate.assert_called_once_with([10, 20, 30])

    @pytest.mark.gui
    def test_widget_does_not_compute_aggregation(self, qtbot) -> None:
        """ウィジェット自体は集計を行わず service に全て委譲すること（service がモック）。"""
        custom_tags = [
            TagCount(tag="custom_tag", count=99, manual=False),
        ]
        service = _make_service(custom_tags)
        panel = StagingTagPanel(service=service)
        qtbot.addWidget(panel)

        panel.load_tags([1])

        # service が返す結果がそのまま表示されること
        assert panel._list_widget.count() == 1
        item = panel._list_widget.item(0)
        assert "custom_tag" in item.text()
        assert "99" in item.text()
