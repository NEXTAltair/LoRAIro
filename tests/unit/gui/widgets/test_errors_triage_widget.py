"""ErrorsTriageWidget 単体テスト。

Track A の ``ErrorTriageService`` 実装には依存せず、hand-built の
dataclass (``ErrorTriageSummary`` / ``ErrorGroup`` / ``ErrorRow``) を渡して
View の描画・シグナル発火・フィルタ状態のみを検証する。

QT_QPA_PLATFORM=offscreen ヘッドレス。signal 検証は qtbot.waitSignal。
"""

from datetime import datetime

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from lorairo.gui.widgets.errors_triage_widget import ErrorsTriageWidget
from lorairo.services.error_triage_service import (
    ErrorGroup,
    ErrorRow,
    ErrorStatusFilter,
    ErrorTriageSummary,
)


@pytest.fixture
def summary() -> ErrorTriageSummary:
    return ErrorTriageSummary(
        total=5,
        unresolved=3,
        resolved=2,
        last_24h=1,
        by_error_type={"TimeoutError": 2, "ValueError": 1},
    )


@pytest.fixture
def groups() -> list[ErrorGroup]:
    return [
        ErrorGroup(
            operation_type="annotation",
            error_type="TimeoutError",
            model_name="gpt-4o",
            count=2,
            unresolved_count=2,
            sample_message="request timed out",
            image_ids=[10, 11],
            error_ids=[1, 2],
            unresolved_error_ids=[1, 2],
        ),
        ErrorGroup(
            operation_type="upscale",
            error_type="ValueError",
            model_name=None,
            count=1,
            unresolved_count=1,
            sample_message="invalid scale",
            image_ids=[12],
            error_ids=[3],
            unresolved_error_ids=[3],
        ),
    ]


@pytest.fixture
def rows() -> list[ErrorRow]:
    return [
        ErrorRow(
            error_id=1,
            image_id=10,
            operation_type="annotation",
            error_type="TimeoutError",
            error_message="request timed out",
            model_name="gpt-4o",
            resolved=False,
            created_at=None,
        ),
        ErrorRow(
            error_id=2,
            image_id=11,
            operation_type="annotation",
            error_type="TimeoutError",
            error_message="request timed out again",
            model_name="gpt-4o",
            resolved=True,
            created_at=None,
        ),
        ErrorRow(
            error_id=3,
            image_id=12,
            operation_type="upscale",
            error_type="ValueError",
            error_message="invalid scale",
            model_name=None,
            resolved=False,
            created_at=None,
        ),
    ]


@pytest.fixture
def widget(qtbot) -> ErrorsTriageWidget:
    w = ErrorsTriageWidget()
    qtbot.addWidget(w)
    return w


def _resolve_buttons(widget: ErrorsTriageWidget) -> list[QPushButton]:
    """objectName が errorRowResolveButton_ で始まるボタンを集める。"""
    return [
        btn
        for btn in widget.findChildren(QPushButton)
        if btn.objectName().startswith("errorRowResolveButton_")
    ]


class TestGroupDisplay:
    def test_group_mode_renders_all_groups(self, widget, summary, groups, rows):
        widget.display(summary, groups, rows)

        assert widget.is_grouped() is True
        keys = widget._group_keys()
        assert keys == [
            ("annotation", "TimeoutError", "gpt-4o"),
            ("upscale", "ValueError", None),
        ]

    def test_group_resolve_emits_unresolved_error_ids(self, widget, qtbot, summary, groups, rows):
        widget.display(summary, groups, rows)

        # 各グループカード内の resolve ボタン
        group_buttons = [
            btn for btn in widget.findChildren(QPushButton) if btn.objectName() == "errorGroupResolveButton"
        ]
        assert len(group_buttons) == 2

        with qtbot.waitSignal(widget.resolve_group_requested, timeout=1000) as blocker:
            group_buttons[0].click()
        assert blocker.args == [[1, 2]]


class TestRowDisplay:
    def test_row_mode_renders_unresolved_resolve_buttons(self, widget, summary, groups, rows):
        widget.display(summary, groups, rows)
        widget.toggle_grouped(False)
        widget.display(summary, groups, rows)

        assert widget.is_grouped() is False
        buttons = _resolve_buttons(widget)
        # resolved 済み (error_id=2) は resolve ボタンを持たない
        names = {btn.objectName() for btn in buttons}
        assert names == {"errorRowResolveButton_1", "errorRowResolveButton_3"}

    def test_single_resolve_emits_error_id(self, widget, qtbot, summary, groups, rows):
        widget.toggle_grouped(False)
        widget.display(summary, groups, rows)

        target = next(
            btn for btn in _resolve_buttons(widget) if btn.objectName() == "errorRowResolveButton_3"
        )
        with qtbot.waitSignal(widget.resolve_requested, timeout=1000) as blocker:
            target.click()
        assert blocker.args == [3]


class TestBulkResolve:
    def test_bulk_resolve_aggregates_all_unresolved_ids(
        self, widget, qtbot, monkeypatch, summary, groups, rows
    ):
        captured_defaults: list[QMessageBox.StandardButton] = []

        def _confirm(_parent, _title, _text, _buttons, default_button=QMessageBox.StandardButton.No):
            captured_defaults.append(default_button)
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", _confirm)
        widget.display(summary, groups, rows)

        bulk = next(
            btn for btn in widget.findChildren(QPushButton) if btn.objectName() == "errorsBulkResolveButton"
        )
        with qtbot.waitSignal(widget.resolve_group_requested, timeout=1000) as blocker:
            bulk.click()
        assert blocker.args == [[1, 2, 3]]
        assert captured_defaults == [QMessageBox.StandardButton.No]

    def test_bulk_resolve_canceled_does_not_emit(self, widget, monkeypatch, summary, groups, rows):
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.No,
        )
        widget.display(summary, groups, rows)
        emitted: list[list[int]] = []
        widget.resolve_group_requested.connect(emitted.append)

        widget._bulk_button.click()

        assert emitted == []


class TestRestageAndDetails:
    def test_restage_button_emits_unresolved_affected_image_ids(self, widget, qtbot, summary, groups, rows):
        widget.display(summary, groups, rows)

        restage = next(
            btn for btn in widget.findChildren(QPushButton) if btn.objectName() == "errorsRestageButton"
        )
        with qtbot.waitSignal(widget.restage_images_requested, timeout=1000) as blocker:
            restage.click()
        assert blocker.args == [[10, 12]]

    def test_restage_does_not_stage_resolved_image_when_unresolved_has_no_image(self, widget):
        resolved_row = ErrorRow(
            error_id=1,
            operation_type="annotation",
            error_type="NetError",
            model_name="m1",
            error_message="msg",
            created_at=datetime.now(),
            resolved=True,
            image_id=10,
        )
        unresolved_row = ErrorRow(
            error_id=2,
            operation_type="annotation",
            error_type="NetError",
            model_name="m1",
            error_message="msg",
            created_at=datetime.now(),
            resolved=False,
            image_id=None,
        )
        group = ErrorGroup(
            operation_type="annotation",
            error_type="NetError",
            model_name="m1",
            count=2,
            unresolved_count=1,
            sample_message="msg",
            image_ids=[10],
            unresolved_image_ids=[],
        )
        # rows supplied (authoritative even if unresolved image list is empty)
        assert widget._collect_visible_unresolved_image_ids([group], [resolved_row, unresolved_row]) == []
        # only groups supplied
        assert widget._collect_visible_unresolved_image_ids([group], []) == []

    def test_error_messages_are_selectable_by_mouse(self, widget, summary, groups, rows):
        widget.display(summary, groups, rows)
        sample_labels = [
            lbl for lbl in widget.findChildren(QLabel) if lbl.objectName() == "errorGroupSample"
        ]
        assert sample_labels
        for lbl in sample_labels:
            assert lbl.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse

    def test_row_renders_file_path_and_stack_trace_details(self, widget, summary, groups):
        detailed_row = ErrorRow(
            error_id=99,
            image_id=42,
            operation_type="annotation",
            error_type="RuntimeError",
            error_message="worker crashed",
            model_name="gpt-4o",
            resolved=False,
            file_path="/data/images/sample.png",
            stack_trace="Traceback (most recent call last):\n  RuntimeError: boom",
        )
        widget.toggle_grouped(False)
        widget.display(summary, groups, [detailed_row])

        detail = widget.findChild(QLabel, "errorRowDetail_99")
        assert detail is not None
        assert "/data/images/sample.png" in detail.text()
        assert "RuntimeError: boom" in detail.text()
        assert detail.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByMouse

    def test_truncation_notice_displayed_when_is_truncated(self, widget, summary, groups, rows):
        widget.display(summary, groups, rows, is_truncated=True)

        assert "最新500件を表示中" in widget._summary_label.text()
        assert not widget._truncation_label.isHidden()


class TestFilterChanged:
    def test_status_segment_emits_filter_changed(self, widget, qtbot, summary, groups, rows):
        widget.set_filter_options(["annotation", "upscale"], ["TimeoutError", "ValueError"], ["gpt-4o"])
        widget.display(summary, groups, rows)

        with qtbot.waitSignal(widget.filter_changed, timeout=1000):
            widget.toggle_grouped(False)

    def test_get_filter_reflects_status_selection(self, widget, summary, groups, rows):
        widget.set_filter_options(["annotation"], ["TimeoutError"], ["gpt-4o"])
        widget.display(summary, groups, rows)

        result = widget.get_filter()
        assert result.status == ErrorStatusFilter.UNRESOLVED

    def test_filter_combos_have_labels_and_tooltips(self, widget):
        """3 つのフィルタ combo に識別用ラベルとツールチップが付与される (#1536)。"""
        from PySide6.QtWidgets import QLabel

        op_label = widget.findChild(QLabel, "errorsOperationComboLabel")
        err_label = widget.findChild(QLabel, "errorsErrorTypeComboLabel")
        model_label = widget.findChild(QLabel, "errorsModelComboLabel")

        assert op_label is not None and op_label.text() == "操作種別"
        assert err_label is not None and err_label.text() == "エラー種別"
        assert model_label is not None and model_label.text() == "モデル"

        assert "操作種別" in widget._operation_combo.toolTip()
        assert "エラー種別" in widget._error_type_combo.toolTip()
        assert "モデル" in widget._model_combo.toolTip()

    def test_set_filter_options_preserves_existing_selection(self, widget):
        """set_filter_options 再実行時にも選択中の値が維持される (#1536)。"""
        widget.set_filter_options(["annotation", "upscale"], ["TimeoutError", "ValueError"], ["gpt-4o"])
        widget._operation_combo.blockSignals(True)
        widget._operation_combo.setCurrentIndex(widget._operation_combo.findData("upscale"))
        widget._operation_combo.blockSignals(False)

        emitted: list[bool] = []
        widget.filter_changed.connect(lambda: emitted.append(True))

        widget.set_filter_options(["annotation", "upscale"], ["TimeoutError", "ValueError"], ["gpt-4o"])

        assert emitted == []
        assert widget.get_filter().operation_type == "upscale"

        # 選択肢から消えた場合は「すべて」(None) にフォールバックする
        widget.set_filter_options(["annotation"], ["TimeoutError"], ["gpt-4o"])
        assert widget.get_filter().operation_type is None


class TestEmptyState:
    def test_empty_state_shown_when_no_data(self, widget):
        empty_summary = ErrorTriageSummary(total=0, unresolved=0, resolved=0, last_24h=0, by_error_type={})
        widget.display(empty_summary, [], [])

        empty = next(
            (
                child
                for child in widget.findChildren(object)
                if hasattr(child, "objectName") and child.objectName() == "errorsEmptyState"
            ),
            None,
        )
        assert empty is not None
        assert empty.isVisible() or not empty.isHidden()

    def test_buttons_have_tooltips(self, qtbot) -> None:
        """Issue #1571: フィルタ・グループ切替・一括/個別 resolve ボタンにツールチップがある。"""
        widget = ErrorsTriageWidget()
        qtbot.addWidget(widget)
        for btn in widget._status_buttons.values():
            assert btn.toolTip() != ""
        assert widget._group_toggle.toolTip() != ""
        assert widget._bulk_button.toolTip() != ""

    def test_status_segment_is_ds_segmented_control(self, qtbot) -> None:
        """Issue #1571: status 切替は DsSegmentedControl で、既定は未解決・変更で filter_changed。"""
        from lorairo.gui.widgets.ds_segmented_control import DsSegmentedControl

        widget = ErrorsTriageWidget()
        qtbot.addWidget(widget)
        assert isinstance(widget._status_control, DsSegmentedControl)
        assert widget.get_filter().status is ErrorStatusFilter.UNRESOLVED
        with qtbot.waitSignal(widget.filter_changed, timeout=2000):
            widget._status_buttons[ErrorStatusFilter.ALL].click()
        assert widget.get_filter().status is ErrorStatusFilter.ALL
        assert widget._status_buttons[ErrorStatusFilter.ALL].isChecked()
        assert not widget._status_buttons[ErrorStatusFilter.UNRESOLVED].isChecked()
