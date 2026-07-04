"""TagManagementWidget の単体テスト"""

from unittest.mock import Mock

import pytest
from genai_tag_db_tools.models import TagRecordPublic
from PySide6.QtWidgets import QCheckBox, QComboBox

from lorairo.gui.widgets.tag_management_widget import TagManagementWidget
from lorairo.services.refinement_service import RefinementService
from lorairo.services.tag_management_service import TagManagementService


@pytest.mark.unit
class TestTagManagementWidget:
    """TagManagementWidget のテストクラス"""

    @pytest.fixture
    def mock_service(self) -> Mock:
        """Mock TagManagementService を提供"""
        service = Mock(spec=TagManagementService)
        service.get_unknown_tags.return_value = []
        service.get_all_available_types.return_value = ["character", "general", "meta"]
        return service

    @pytest.fixture
    def widget(self, qtbot, mock_service) -> TagManagementWidget:
        """TagManagementWidget インスタンスを提供"""
        widget = TagManagementWidget()
        widget.set_tag_service(mock_service)
        qtbot.addWidget(widget)
        return widget

    def test_initialization(self, widget: TagManagementWidget) -> None:
        """初期化時のUI状態確認"""
        assert widget.tag_service is not None
        assert widget.unknown_tags == []
        assert widget.available_types == []
        assert widget.tableWidgetTags.rowCount() == 0
        assert not widget.buttonUpdate.isEnabled()

    def test_load_unknown_tags_empty(self, widget: TagManagementWidget, qtbot, mock_service: Mock) -> None:
        """unknown type タグが0件の場合"""
        mock_service.get_unknown_tags.return_value = []
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        # テーブル更新を待機
        qtbot.waitUntil(lambda: widget.tableWidgetTags.rowCount() == 0, timeout=1000)

        assert len(widget.unknown_tags) == 0
        assert "0 unknown type tags found" in widget.labelStatus.text()

    def test_load_unknown_tags_with_data(
        self, widget: TagManagementWidget, qtbot, mock_service: Mock
    ) -> None:
        """unknown type タグが複数ある場合"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag_1",
                tag_id=1,
                source_tag="test_tag_1",
                type_name="unknown",
                format_name="Lorairo",
            ),
            TagRecordPublic(
                tag="test_tag_2",
                tag_id=2,
                source_tag="test_tag_2",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general", "meta"]

        widget.load_unknown_tags()

        # テーブルが2行になるまで待機
        qtbot.waitUntil(lambda: widget.tableWidgetTags.rowCount() == 2, timeout=1000)

        assert len(widget.unknown_tags) == 2
        assert "2 unknown type tags found" in widget.labelStatus.text()

        # 各行のUI要素確認
        for row in range(2):
            # Column 0: Checkbox
            checkbox = widget.tableWidgetTags.cellWidget(row, 0)
            assert isinstance(checkbox, QCheckBox)
            assert not checkbox.isChecked()

            # Column 4: ComboBox
            combobox = widget.tableWidgetTags.cellWidget(row, 4)
            assert isinstance(combobox, QComboBox)
            assert combobox.count() == 4  # "(選択してください)" + 3 types

    def test_checkbox_enables_button(self, widget: TagManagementWidget, qtbot, mock_service: Mock) -> None:
        """Checkbox選択でボタン有効化"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        # 初期状態: ボタン無効
        assert not widget.buttonUpdate.isEnabled()

        # UI要素取得
        checkbox = widget.tableWidgetTags.cellWidget(0, 0)
        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(checkbox, QCheckBox)
        assert isinstance(combobox, QComboBox)

        # UI操作をエミュレート
        combobox.setCurrentIndex(1)  # "character" を選択
        checkbox.setChecked(True)

        # ボタンが有効化されるまで待機
        qtbot.waitUntil(lambda: widget.buttonUpdate.isEnabled(), timeout=1000)

    def test_update_completed_signal(self, widget: TagManagementWidget, qtbot, monkeypatch) -> None:
        """update_completed Signal 発火確認"""
        # QMessageBoxをmockしてモーダルブロックを回避
        mock_msgbox = Mock(return_value=None)
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.QMessageBox.information", mock_msgbox
        )

        # waitSignalでシグナル発火を待機（timeout付き）
        with qtbot.waitSignal(widget.update_completed, timeout=2000):
            widget.update_completed.emit()

    def test_update_failed_signal(self, widget: TagManagementWidget, qtbot, monkeypatch) -> None:
        """update_failed Signal 発火確認"""
        # QMessageBoxをmockしてモーダルブロックを回避
        mock_msgbox = Mock(return_value=None)
        monkeypatch.setattr("lorairo.gui.widgets.tag_management_widget.show_critical", mock_msgbox)

        # waitSignalでシグナル発火を待機（引数検証も可能）
        with qtbot.waitSignal(widget.update_failed, timeout=2000):
            widget.update_failed.emit("Test error")

    def test_type_selection_tracking(self, widget: TagManagementWidget, mock_service: Mock) -> None:
        """Type選択が内部で追跡されること"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(combobox, QComboBox)

        # type選択
        combobox.setCurrentIndex(1)  # "character"

        assert 1 in widget._type_selections
        assert widget._type_selections[1] == "character"

    def test_load_unknown_tags_no_service(self, qtbot, monkeypatch) -> None:
        """tag_service が未設定の場合に警告ダイアログを表示する（line 84-86）"""
        widget = TagManagementWidget()
        qtbot.addWidget(widget)
        # tag_service を設定しない
        assert widget.tag_service is None

        warning_called = []
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.show_warning",
            lambda *a: warning_called.append(True),
        )

        widget.load_unknown_tags()

        assert warning_called, "QMessageBox.warning should have been called"

    def test_load_unknown_tags_exception(
        self, widget: TagManagementWidget, mock_service: Mock, monkeypatch
    ) -> None:
        """get_unknown_tags が例外を投げた場合に critical ダイアログを表示する（line 101-103）"""
        mock_service.get_unknown_tags.side_effect = RuntimeError("DB error")

        critical_called = []
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.show_critical",
            lambda *a: critical_called.append(True),
        )

        widget.load_unknown_tags()

        assert critical_called, "QMessageBox.critical should have been called"

    def test_type_deselection_removes_from_tracking(
        self, widget: TagManagementWidget, mock_service: Mock
    ) -> None:
        """Type選択を(選択してください)に戻すと追跡から削除される（line 164）"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character", "general"]

        widget.load_unknown_tags()

        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(combobox, QComboBox)

        # まず type を選択して追跡させる
        combobox.setCurrentIndex(1)  # "character"
        assert 1 in widget._type_selections

        # "(選択してください)" に戻す (index 0, data=None)
        combobox.setCurrentIndex(0)
        assert 1 not in widget._type_selections

    def test_on_update_clicked_no_service(self, qtbot) -> None:
        """tag_service 未設定時の更新ボタンクリックは早期リターン（line 184-186）"""
        widget = TagManagementWidget()
        qtbot.addWidget(widget)
        assert widget.tag_service is None

        # クラッシュしないことを確認
        widget._on_update_clicked()

    def test_on_update_clicked_no_selections(
        self, widget: TagManagementWidget, mock_service: Mock, monkeypatch
    ) -> None:
        """選択タグがない場合に警告ダイアログを表示する（line 199-204）"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character"]
        widget.load_unknown_tags()

        warning_called = []
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.show_warning",
            lambda *a: warning_called.append(True),
        )

        # チェックボックスを未選択のままクリック
        widget._on_update_clicked()

        assert warning_called, "QMessageBox.warning should have been called when no tags selected"

    def test_on_update_clicked_confirmed_starts_thread(
        self, widget: TagManagementWidget, mock_service: Mock, monkeypatch, qtbot
    ) -> None:
        """確認ダイアログでYesを押すとスレッドが起動し update_tag_types が呼ばれる（line 206-236）"""

        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character"]
        widget.load_unknown_tags()

        # チェックボックスにチェックを入れ type を選択
        checkbox = widget.tableWidgetTags.cellWidget(0, 0)
        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(checkbox, QCheckBox)
        assert isinstance(combobox, QComboBox)
        combobox.setCurrentIndex(1)  # "character"
        checkbox.setChecked(True)

        # QMessageBox.question は conftest.py の auto_mock_qmessagebox で Yes を返す
        # update_tag_types は正常完了させる
        mock_service.update_tag_types.return_value = None

        # update_completed シグナルを waitSignal で捉える
        # (情報ダイアログも conftest.py でモック済み)
        with qtbot.waitSignal(widget.update_completed, timeout=3000):
            widget._on_update_clicked()

        # update_tag_types が呼ばれたことを確認
        mock_service.update_tag_types.assert_called_once()
        call_args = mock_service.update_tag_types.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].tag_id == 1

    def test_on_update_clicked_cancelled(
        self, widget: TagManagementWidget, mock_service: Mock, monkeypatch
    ) -> None:
        """確認ダイアログでNoを押すと更新されない（line 214-215）"""
        from PySide6.QtWidgets import QMessageBox as _QMB

        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character"]
        widget.load_unknown_tags()

        checkbox = widget.tableWidgetTags.cellWidget(0, 0)
        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(checkbox, QCheckBox)
        assert isinstance(combobox, QComboBox)
        combobox.setCurrentIndex(1)
        checkbox.setChecked(True)

        # Noを返すようにオーバーライド
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.QMessageBox.question",
            lambda *a, **kw: _QMB.StandardButton.No,
        )

        widget._on_update_clicked()

        # update_tag_types は呼ばれない
        mock_service.update_tag_types.assert_not_called()

    def test_on_update_failed_handler(self, widget: TagManagementWidget, qtbot, monkeypatch) -> None:
        """_on_update_failed がボタンを再有効化しステータスを更新する（line 251-263）"""
        critical_called = []
        monkeypatch.setattr(
            "lorairo.gui.widgets.tag_management_widget.show_critical",
            lambda *a: critical_called.append(True),
        )

        # ボタンを無効化した状態から開始
        widget.buttonUpdate.setEnabled(False)

        widget._on_update_failed("some error")

        assert critical_called
        assert widget.buttonUpdate.isEnabled()
        assert "failed" in widget.labelStatus.text().lower()

    def test_set_refinement_service_stores_instance(self, widget: TagManagementWidget) -> None:
        """set_refinement_service が RefinementService を保持する（#977）"""
        assert widget.refinement_service is None

        refinement_service = Mock(spec=RefinementService)
        refinement_service.list_ignored_entries.return_value = []
        widget.set_refinement_service(refinement_service)

        assert widget.refinement_service is refinement_service

    def test_update_completed_clears_refinement_cache(
        self, widget: TagManagementWidget, mock_service: Mock
    ) -> None:
        """tagdb 更新完了時に refinement キャッシュが無効化される（#977）"""
        refinement_service = Mock(spec=RefinementService)
        refinement_service.list_ignored_entries.return_value = []
        widget.set_refinement_service(refinement_service)

        # _on_update_completed は load_unknown_tags を呼ぶため tag_service の戻り値が必要
        mock_service.get_unknown_tags.return_value = []
        mock_service.get_all_available_types.return_value = ["character"]

        widget._on_update_completed()

        refinement_service.clear_cache.assert_called_once()

    def test_update_completed_without_refinement_service_does_not_crash(
        self, widget: TagManagementWidget, mock_service: Mock
    ) -> None:
        """RefinementService 未注入でも更新完了処理がクラッシュしない（#977）"""
        assert widget.refinement_service is None
        mock_service.get_unknown_tags.return_value = []
        mock_service.get_all_available_types.return_value = ["character"]

        # 例外を投げずに完了すること
        widget._on_update_completed()

    def test_clear_refinement_cache_degrades_on_error(self, widget: TagManagementWidget) -> None:
        """clear_cache が例外を投げても UI を巻き込まず degrade する（#977）"""
        refinement_service = Mock(spec=RefinementService)
        refinement_service.list_ignored_entries.return_value = []
        refinement_service.clear_cache.side_effect = RuntimeError("cache error")
        widget.set_refinement_service(refinement_service)

        # 例外が外へ伝播しないこと
        widget._clear_refinement_cache()

        refinement_service.clear_cache.assert_called_once()

    def test_on_update_thread_emits_failed_on_exception(
        self, widget: TagManagementWidget, mock_service: Mock, monkeypatch, qtbot
    ) -> None:
        """update_tag_types が例外を投げると update_failed シグナルが発火する（line 229-231）"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag",
                tag_id=1,
                source_tag="test_tag",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]
        mock_service.get_unknown_tags.return_value = mock_tags
        mock_service.get_all_available_types.return_value = ["character"]
        widget.load_unknown_tags()

        checkbox = widget.tableWidgetTags.cellWidget(0, 0)
        combobox = widget.tableWidgetTags.cellWidget(0, 4)
        assert isinstance(checkbox, QCheckBox)
        assert isinstance(combobox, QComboBox)
        combobox.setCurrentIndex(1)
        checkbox.setChecked(True)

        mock_service.update_tag_types.side_effect = RuntimeError("update failed")

        with qtbot.waitSignal(widget.update_failed, timeout=3000):
            widget._on_update_clicked()


class TestIgnoreManagementSection:
    """#1053: refinement 無視設定の一覧・解除セクション。"""

    def _make_widget(self, qtbot, entries):
        from lorairo.gui.widgets.tag_management_widget import TagManagementWidget
        from lorairo.services.refinement_service import RefinementService

        widget = TagManagementWidget()
        qtbot.addWidget(widget)
        service = Mock(spec=RefinementService)
        service.list_ignored_entries.return_value = entries
        widget.set_refinement_service(service)
        return widget, service

    def test_entries_listed_with_scope(self, qtbot):
        widget, _service = self._make_widget(
            qtbot,
            [
                {"tag": "heart", "reason_code": "alias_tag", "image_id": None, "created_at": None},
                {"tag": "star", "reason_code": "typo_tag", "image_id": 7, "created_at": None},
            ],
        )

        table = widget.tableIgnoredEntries
        assert table.rowCount() == 2
        assert table.item(0, 0).text() == "heart"
        assert table.item(0, 2).text() == "全画像"
        assert table.item(1, 2).text() == "画像 7 のみ"

    def test_unignore_button_removes_and_refreshes(self, qtbot):
        widget, service = self._make_widget(
            qtbot,
            [{"tag": "heart", "reason_code": "alias_tag", "image_id": 7, "created_at": None}],
        )
        # 解除後は空一覧を返す
        service.list_ignored_entries.return_value = []

        widget._on_unignore("heart", "alias_tag", 7)

        service.unignore.assert_called_once_with("heart", "alias_tag", 7)
        assert widget.tableIgnoredEntries.rowCount() == 0
