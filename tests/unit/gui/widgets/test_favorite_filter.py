# tests/unit/gui/widgets/test_favorite_filter.py
"""FavoriteFilterPanel の単独 qtbot テスト (ADR 0036 §5)。

QMessageBox / QInputDialog は monkeypatch でモックする
(`.claude/rules/testing.md` 参照)。
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from lorairo.gui.widgets.favorite_filter import FavoriteFilterPanel


@pytest.fixture()
def panel(qtbot) -> FavoriteFilterPanel:
    """FavoriteFilterPanel の独立インスタンスを作る。"""
    p = FavoriteFilterPanel()
    qtbot.addWidget(p)
    return p


@pytest.fixture()
def mock_service() -> MagicMock:
    """FavoriteFiltersService の mock。"""
    service = MagicMock()
    service.list_filters.return_value = []
    service.filter_exists.return_value = False
    service.save_filter.return_value = True
    service.delete_filter.return_value = True
    service.load_filter.return_value = {"some": "conditions"}
    return service


@pytest.fixture(autouse=True)
def mock_message_box(monkeypatch) -> None:
    """全 QMessageBox 呼び出しを自動 mock (テスト中のダイアログ表示防止)。"""
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)


class TestInitialState:
    """初期状態のテスト。"""

    def test_service_is_none(self, panel: FavoriteFilterPanel) -> None:
        assert panel.favorite_filters_service is None

    def test_starts_collapsed(self, panel: FavoriteFilterPanel) -> None:
        assert panel.isChecked() is False

    def test_buttons_exist(self, panel: FavoriteFilterPanel) -> None:
        assert panel.button_save_filter is not None
        assert panel.button_load_filter is not None
        assert panel.button_delete_filter is not None


class TestSetFavoriteFiltersService:
    """set_favorite_filters_service のテスト。"""

    def test_none_raises(self, panel: FavoriteFilterPanel) -> None:
        with pytest.raises(ValueError):
            panel.set_favorite_filters_service(None)

    def test_set_populates_list(self, panel: FavoriteFilterPanel) -> None:
        service = MagicMock()
        service.list_filters.return_value = ["filter_a", "filter_b"]

        panel.set_favorite_filters_service(service)

        assert panel.favorite_filters_list.count() == 2
        assert panel.favorite_filters_list.item(0).text() == "filter_a"
        assert panel.favorite_filters_list.item(1).text() == "filter_b"

    def test_set_handles_service_exception(self, panel: FavoriteFilterPanel) -> None:
        service = MagicMock()
        service.list_filters.side_effect = RuntimeError("DB error")

        # 例外はキャッチされてログのみ出力される
        panel.set_favorite_filters_service(service)

        assert panel.favorite_filters_service is service


class TestSaveFlow:
    """保存フローのテスト。"""

    def test_save_invokes_service(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
        monkeypatch,
    ) -> None:
        panel.set_favorite_filters_service(mock_service)
        conditions: dict[str, Any] = {"keywords": ["1girl"]}
        panel.set_conditions_getter(lambda: conditions)
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("my_filter", True))

        panel._on_save_clicked()

        mock_service.save_filter.assert_called_once_with("my_filter", conditions)

    def test_save_skipped_when_conditions_empty(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        panel.set_favorite_filters_service(mock_service)
        panel.set_conditions_getter(lambda: {})

        panel._on_save_clicked()

        mock_service.save_filter.assert_not_called()

    def test_save_skipped_when_user_cancels_dialog(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
        monkeypatch,
    ) -> None:
        panel.set_favorite_filters_service(mock_service)
        panel.set_conditions_getter(lambda: {"keywords": ["1girl"]})
        monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("", False))

        panel._on_save_clicked()

        mock_service.save_filter.assert_not_called()


class TestLoadFlow:
    """ロードフローのテスト。"""

    def test_load_invokes_applier(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        applier = MagicMock()
        mock_service.list_filters.return_value = ["my_filter"]
        panel.set_favorite_filters_service(mock_service)
        panel.set_conditions_applier(applier)
        panel.favorite_filters_list.setCurrentRow(0)

        panel._on_load_clicked()

        mock_service.load_filter.assert_called_once_with("my_filter")
        applier.assert_called_once_with({"some": "conditions"})

    def test_load_via_double_click(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        applier = MagicMock()
        mock_service.list_filters.return_value = ["my_filter"]
        panel.set_favorite_filters_service(mock_service)
        panel.set_conditions_applier(applier)

        item = panel.favorite_filters_list.item(0)
        panel._on_filter_double_clicked(item)

        applier.assert_called_once_with({"some": "conditions"})

    def test_load_skipped_when_nothing_selected(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        panel.set_favorite_filters_service(mock_service)

        panel._on_load_clicked()

        mock_service.load_filter.assert_not_called()


class TestDeleteFlow:
    """削除フローのテスト。"""

    def test_delete_invokes_service(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        mock_service.list_filters.return_value = ["my_filter"]
        panel.set_favorite_filters_service(mock_service)
        panel.favorite_filters_list.setCurrentRow(0)

        panel._on_delete_clicked()

        mock_service.delete_filter.assert_called_once_with("my_filter")

    def test_delete_skipped_when_user_says_no(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
        monkeypatch,
    ) -> None:
        mock_service.list_filters.return_value = ["my_filter"]
        panel.set_favorite_filters_service(mock_service)
        panel.favorite_filters_list.setCurrentRow(0)
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.No)

        panel._on_delete_clicked()

        mock_service.delete_filter.assert_not_called()


class TestChipRendering:
    """保存クエリ chip 表示のテスト (#815)。"""

    def test_chips_built_for_each_filter(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        mock_service.list_filters.return_value = ["q1", "q2"]
        mock_service.get_all_filters.return_value = {
            "q1": {"keywords": ["1girl", "solo"]},
            "q2": {"only_untagged": True},
        }

        panel.set_favorite_filters_service(mock_service)

        # checkable QGroupBox なので isVisible は親 show 依存。isHidden で明示状態を見る
        assert panel._chip_layout.count() == 2
        assert panel._chip_container.isHidden() is False
        assert panel._empty_label.isHidden() is True

    def test_empty_state_shows_placeholder(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        mock_service.list_filters.return_value = []
        mock_service.get_all_filters.return_value = {}

        panel.set_favorite_filters_service(mock_service)

        assert panel._chip_layout.count() == 0
        assert panel._empty_label.isHidden() is False

    def test_chip_click_invokes_applier(
        self,
        panel: FavoriteFilterPanel,
        mock_service: MagicMock,
    ) -> None:
        from PySide6.QtWidgets import QPushButton

        applier = MagicMock()
        mock_service.list_filters.return_value = ["q1"]
        mock_service.get_all_filters.return_value = {"q1": {"keywords": ["1girl"]}}
        panel.setChecked(True)  # 折りたたみ中は子 widget が無効化されるため展開する
        panel.set_favorite_filters_service(mock_service)
        panel.set_conditions_applier(applier)

        chip_item = panel._chip_layout.itemAt(0)
        assert chip_item is not None
        chip_button = chip_item.widget().findChild(QPushButton, "favoriteQueryChip")
        assert chip_button is not None
        chip_button.click()

        mock_service.load_filter.assert_called_once_with("q1")
        applier.assert_called_once_with({"some": "conditions"})

    def test_chip_summary_reflects_conditions(
        self,
        panel: FavoriteFilterPanel,
    ) -> None:
        summary = panel._summarize_conditions({"keywords": ["a", "b", "c"], "only_untagged": True})

        assert "a,b…" in summary
        assert "untagged" in summary

    def test_chip_summary_empty_for_none(self, panel: FavoriteFilterPanel) -> None:
        assert panel._summarize_conditions(None) == ""


class TestServiceMissingGuards:
    """service 未設定時の動作。"""

    def test_save_when_service_missing(self, panel: FavoriteFilterPanel) -> None:
        # service 未設定でも例外を投げない
        panel._on_save_clicked()

    def test_load_when_service_missing(self, panel: FavoriteFilterPanel) -> None:
        panel._on_load_clicked()

    def test_delete_when_service_missing(self, panel: FavoriteFilterPanel) -> None:
        panel._on_delete_clicked()


# 折りたたみの実挙動 (#1088) ---------------------------------------------------


class TestCollapseBehavior:
    """checkable QGroupBox の折りたたみが「グレー表示」でなく「非表示」になる (#1088)。"""

    def test_collapsed_by_default_hides_content(self, qtbot):
        """初期状態 (unchecked) では中身が非表示 (グレーの保存ボタンを見せない)。"""
        panel = FavoriteFilterPanel()
        qtbot.addWidget(panel)
        panel.show()

        assert panel.isChecked() is False
        assert not panel._content.isVisibleTo(panel)

    def test_expand_shows_content_and_enables_save(self, qtbot):
        """展開 (checked) すると中身が表示され、保存ボタンが有効になる。"""
        panel = FavoriteFilterPanel()
        qtbot.addWidget(panel)
        panel.show()

        panel.setChecked(True)

        assert panel._content.isVisibleTo(panel)
        assert panel.button_save_filter.isEnabledTo(panel)

    def test_collapse_again_hides_content(self, qtbot):
        """再度折りたたむと中身が非表示に戻る。"""
        panel = FavoriteFilterPanel()
        qtbot.addWidget(panel)
        panel.show()
        panel.setChecked(True)

        panel.setChecked(False)

        assert not panel._content.isVisibleTo(panel)
