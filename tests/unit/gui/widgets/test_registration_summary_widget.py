"""RegistrationSummaryWidget 単体テスト。

Wireframes v11 Frame 1「登録完了サマリ」。worker の
``DatabaseRegistrationResult`` を渡して View の描画・詳細行・シグナル発火・
✕ dismiss を検証する。QT_QPA_PLATFORM=offscreen ヘッドレス。
"""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from lorairo.database.db_manager import RegistrationOutcome
from lorairo.gui.widgets.registration_summary_widget import RegistrationSummaryWidget
from lorairo.gui.workers.registration_worker import (
    DatabaseRegistrationResult,
    RegistrationDetailItem,
)


@pytest.fixture
def result() -> DatabaseRegistrationResult:
    """新規4 / 別版1 / 重複2 / エラー0 の登録結果。"""
    return DatabaseRegistrationResult(
        registered_count=4,
        skipped_count=2,
        error_count=0,
        processed_paths=[],
        total_processing_time=18.2,
        variant_count=1,
        directory=Path("/data/uploads/shiba_batch_07"),
        detail=[
            RegistrationDetailItem("shiba_a.jpg", RegistrationOutcome.REGISTERED, 12480),
            RegistrationDetailItem("shiba_close_v2.jpg", RegistrationOutcome.VARIANT, 12481),
            RegistrationDetailItem("shiba_007_copy.jpg", RegistrationOutcome.DUPLICATE, 4412),
            RegistrationDetailItem("shiba_012.png", RegistrationOutcome.DUPLICATE, 2871),
        ],
    )


def test_show_result_displays_directory_and_counts(qtbot, result):
    """show_result でヘッダにディレクトリ名と件数を表示し、パネルが可視になる。"""
    widget = RegistrationSummaryWidget()
    qtbot.addWidget(widget)

    widget.show_result(result)

    assert not widget.isHidden()
    header = widget.findChild(QLabel, "registrationSummaryHeader")
    counts = widget.findChild(QLabel, "registrationSummaryCounts")
    assert "shiba_batch_07" in header.text()
    counts_text = counts.text()
    assert "4" in counts_text  # 新規
    assert "1" in counts_text  # 別版
    assert "2" in counts_text  # skip


def test_dismiss_hides_widget(qtbot, result):
    """✕ クリックでパネルが非表示になる。"""
    widget = RegistrationSummaryWidget()
    qtbot.addWidget(widget)
    widget.show_result(result)
    assert not widget.isHidden()

    dismiss = widget.findChild(QPushButton, "registrationSummaryDismiss")
    dismiss.click()

    assert widget.isHidden()


def test_detail_rows_only_for_duplicate_and_variant(qtbot, result):
    """詳細リンクは DUPLICATE / VARIANT のみ生成される（REGISTERED は出さない）。"""
    widget = RegistrationSummaryWidget()
    qtbot.addWidget(widget)

    widget.show_result(result)

    links = [
        b
        for b in widget.findChildren(QPushButton)
        if b.objectName().startswith("registrationSummaryImageLink_")
    ]
    linked_ids = {b.objectName().rsplit("_", 1)[1] for b in links}
    # VARIANT 12481, DUPLICATE 4412 / 2871 の3件。REGISTERED 12480 は含めない。
    assert linked_ids == {"12481", "4412", "2871"}


def test_link_click_emits_view_image_requested(qtbot, result):
    """詳細行リンクのクリックで view_image_requested(image_id) が発火する。"""
    widget = RegistrationSummaryWidget()
    qtbot.addWidget(widget)
    widget.show_result(result)

    link = widget.findChild(QPushButton, "registrationSummaryImageLink_4412")
    with qtbot.waitSignal(widget.view_image_requested, timeout=1000) as blocker:
        link.click()

    assert blocker.args == [4412]


def test_toggle_shows_and_hides_detail(qtbot, result):
    """詳細は既定で折りたたまれ、トグルで開閉する。"""
    widget = RegistrationSummaryWidget()
    qtbot.addWidget(widget)
    widget.show_result(result)

    toggle = widget.findChild(QPushButton, "registrationSummaryToggle")
    container = widget.findChild(QWidget, "registrationSummaryDetail")

    assert container.isHidden()
    toggle.click()
    assert not container.isHidden()
    toggle.click()
    assert container.isHidden()
