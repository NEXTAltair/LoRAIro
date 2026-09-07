"""CropDialog の単体テスト (#1345)。

長辺 1024px の警告境界・無効矩形での保存禁止・タグの候補↔採用往復・レーティング初期値・
切り出しプレビューの描画・保存 callback の成功/失敗 (ワーカースレッド実行)・未保存変更の
破棄確認を検証する。QMessageBox は monkeypatch で差し替える (tests/unit/gui/conftest.py の
autouse mock を個別に上書きする)。
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QDialog, QMessageBox

from lorairo.domain.crop_request import CropCreateRequest, CropRect
from lorairo.gui.widgets.crop_dialog import CropDialog
from lorairo.gui.widgets.crop_tag_list_widget import ClickableTagListWidget

pytestmark = [pytest.mark.unit, pytest.mark.gui]

PARENT_IMAGE_ID = 7
CANDIDATE_TAGS = ["cat", "outdoor", "sunset"]
# ワーカースレッドの完了を待つ上限 (ms)
WAIT_MS = 5000


class SaveRecorder:
    """保存 callback のスタブ (呼び出し記録 + 実行スレッド記録 + 任意で例外送出)。"""

    def __init__(self, child_image_id: int = 4242) -> None:
        self.calls: list[CropCreateRequest] = []
        self.error: Exception | None = None
        self.child_image_id = child_image_id
        self.threads: list[QThread] = []
        self.started = threading.Event()
        # set されるまで callback を保存中のまま留めるためのゲート (None なら即完了)
        self.gate: threading.Event | None = None

    def __call__(self, request: CropCreateRequest) -> int:
        self.calls.append(request)
        self.threads.append(QThread.currentThread())
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(timeout=10.0), "ゲートが解放されませんでした"
        if self.error is not None:
            raise self.error
        return self.child_image_id


def _wait_save_finished(qtbot, dialog: CropDialog) -> None:
    """保存ワーカーの完了 (成功・失敗どちらでも) を待つ。"""
    qtbot.waitUntil(lambda: not dialog._save_in_progress, timeout=WAIT_MS)


@pytest.fixture
def image_path(tmp_path: Path) -> Path:
    """1024px 境界を試せる 2000x1500 の親画像。"""
    path = tmp_path / "parent.png"
    Image.new("RGB", (2000, 1500), (200, 180, 160)).save(path)
    return path


@pytest.fixture
def recorder() -> SaveRecorder:
    return SaveRecorder()


@pytest.fixture
def candidates() -> list[str]:
    return list(CANDIDATE_TAGS)


@pytest.fixture
def dialog(qtbot, image_path: Path, recorder: SaveRecorder, candidates: list[str]) -> CropDialog:
    """表示済みの CropDialog (親レーティング R)。"""
    widget = CropDialog(
        image_path=image_path,
        parent_image_id=PARENT_IMAGE_ID,
        candidate_tags=candidates,
        parent_rating="R",
        save_callback=recorder,
    )
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _click_tag(qtbot, tag_list: ClickableTagListWidget, tag: str) -> None:
    """タグリストの該当行を実際にクリックする。"""
    for row in range(tag_list.count()):
        item = tag_list.item(row)
        if item is not None and item.text() == tag:
            qtbot.mouseClick(
                tag_list.viewport(),
                Qt.MouseButton.LeftButton,
                pos=tag_list.visualItemRect(item).center(),
            )
            return
    raise AssertionError(f"タグ {tag!r} がリストに見つかりません: {tag_list.tags()}")


class TestInitialState:
    def test_no_rect_selected(self, dialog):
        assert dialog.crop_rect() is None
        assert dialog.size_text() == "選択範囲なし"

    def test_save_disabled_without_rect(self, dialog):
        assert dialog.can_save() is False

    def test_warning_hidden_without_rect(self, dialog):
        assert dialog.is_resolution_warning_visible() is False

    def test_candidate_tags_listed(self, dialog):
        assert dialog.candidate_tags() == CANDIDATE_TAGS
        assert dialog._candidate_list.tags() == CANDIDATE_TAGS
        assert dialog.adopted_tags() == []


class TestResolutionWarningBoundary:
    def test_long_edge_below_threshold_warns_but_allows_save(self, dialog):
        dialog.set_rect(CropRect(0, 0, 1023, 500))
        assert dialog.is_resolution_warning_visible() is True
        assert dialog.can_save() is True

    def test_long_edge_exactly_threshold_has_no_warning(self, dialog):
        dialog.set_rect(CropRect(0, 0, 1024, 500))
        assert dialog.is_resolution_warning_visible() is False
        assert dialog.can_save() is True

    def test_long_edge_above_threshold_has_no_warning(self, dialog):
        dialog.set_rect(CropRect(0, 0, 500, 1500))
        assert dialog.is_resolution_warning_visible() is False
        assert dialog.can_save() is True

    def test_warning_text_matches_specification(self, dialog):
        dialog.set_rect(CropRect(0, 0, 300, 200))
        assert dialog._warning_label.text() == (
            "長辺が1024px未満です。学習時に拡大すると、ぼけや細部不足が品質に影響する場合があります。"
        )


class TestInvalidRectDisablesSave:
    def test_zero_width_disables_save(self, dialog):
        dialog.set_rect(CropRect(10, 10, 0, 500))
        assert dialog.can_save() is False

    def test_zero_height_disables_save(self, dialog):
        dialog.set_rect(CropRect(10, 10, 500, 0))
        assert dialog.can_save() is False

    def test_valid_rect_after_invalid_reenables_save(self, dialog):
        dialog.set_rect(CropRect(10, 10, 0, 500))
        dialog.set_rect(CropRect(10, 10, 500, 500))
        assert dialog.can_save() is True

    def test_build_request_rejects_invalid_rect(self, dialog):
        dialog.set_rect(CropRect(10, 10, 0, 500))
        with pytest.raises(ValueError):
            dialog.build_request()


class TestSizeDisplay:
    def test_size_text_shows_actual_pixels(self, dialog):
        dialog.set_rect(CropRect(100, 200, 640, 480))
        assert dialog.size_text() == "640 x 480 px"

    def test_size_text_resets_when_cleared(self, dialog):
        dialog.set_rect(CropRect(100, 200, 640, 480))
        dialog.set_rect(None)
        assert dialog.size_text() == "選択範囲なし"


class TestTagMovement:
    def test_candidate_click_moves_to_adopted(self, qtbot, dialog):
        _click_tag(qtbot, dialog._candidate_list, "outdoor")
        assert dialog.adopted_tags() == ["outdoor"]
        assert dialog.candidate_tags() == ["cat", "sunset"]
        assert dialog._adopted_list.tags() == ["outdoor"]

    def test_adopted_click_returns_to_candidates_in_original_order(self, qtbot, dialog):
        _click_tag(qtbot, dialog._candidate_list, "outdoor")
        _click_tag(qtbot, dialog._adopted_list, "outdoor")
        assert dialog.adopted_tags() == []
        assert dialog.candidate_tags() == CANDIDATE_TAGS

    def test_multiple_returns_keep_stable_order(self, qtbot, dialog):
        _click_tag(qtbot, dialog._candidate_list, "cat")
        _click_tag(qtbot, dialog._candidate_list, "sunset")
        _click_tag(qtbot, dialog._adopted_list, "sunset")
        _click_tag(qtbot, dialog._adopted_list, "cat")
        assert dialog.candidate_tags() == CANDIDATE_TAGS

    def test_source_candidate_list_is_not_mutated(self, qtbot, dialog, candidates):
        _click_tag(qtbot, dialog._candidate_list, "cat")
        assert candidates == CANDIDATE_TAGS

    def test_rect_change_keeps_adopted_tags(self, qtbot, dialog):
        _click_tag(qtbot, dialog._candidate_list, "cat")
        dialog.set_rect(CropRect(0, 0, 1200, 900))
        dialog.set_rect(CropRect(10, 10, 300, 300))
        assert dialog.adopted_tags() == ["cat"]


class TestRating:
    def test_parent_rating_is_initial_value(self, dialog):
        assert dialog.rating() == "R"
        assert dialog._rating_control.value() == "R"

    def test_rating_can_be_changed(self, dialog):
        dialog._rating_control._buttons["X"].click()
        assert dialog.rating() == "X"

    def test_unknown_parent_rating_is_treated_as_unset(self, qtbot, image_path, recorder):
        widget = CropDialog(
            image_path=image_path,
            parent_image_id=PARENT_IMAGE_ID,
            candidate_tags=[],
            parent_rating="UNKNOWN",
            save_callback=recorder,
        )
        qtbot.addWidget(widget)
        assert widget.rating() is None


class TestBuildRequest:
    def test_request_carries_selection(self, qtbot, dialog):
        dialog.set_rect(CropRect(100, 50, 800, 600))
        _click_tag(qtbot, dialog._candidate_list, "cat")
        request = dialog.build_request()
        assert request == CropCreateRequest(
            parent_image_id=PARENT_IMAGE_ID,
            rect=CropRect(100, 50, 800, 600),
            tags=("cat",),
            rating="R",
            origin="manual",
        )


class TestPreview:
    """プレビューはフル解像度の切り出しコピーを作らず、表示サイズへ直接描画する。"""

    def test_preview_holds_source_without_copying(self, dialog):
        dialog.set_rect(CropRect(0, 0, 1600, 1200))
        # 元画像そのものを参照で保持していれば、切り出しコピーは作られていない
        assert dialog._preview._source is dialog._selector.source_pixmap()
        assert dialog._preview._crop == CropRect(0, 0, 1600, 1200)
        # QLabel の pixmap プロパティ (= 切り出し済み画像の保持先) は使わない
        assert dialog._preview.pixmap().isNull() is True

    def test_preview_draw_target_keeps_aspect_ratio(self, dialog):
        dialog.set_rect(CropRect(0, 0, 800, 400))
        source_rect = dialog._preview._source_rect()
        target = dialog._preview._target_rect(source_rect)
        area = dialog._preview.contentsRect()
        assert target is not None
        # 2:1 の切り出しは 2:1 のまま描画される (整数丸めの 1px は許容)
        assert abs(target.width() - target.height() * 2) <= 2
        assert target.width() <= area.width()
        assert target.height() <= area.height()
        # 描画先は表示領域の中央に置かれる
        assert abs(target.center().x() - area.center().x()) <= 1
        assert abs(target.center().y() - area.center().y()) <= 1

    def test_preview_renders_selected_pixels(self, dialog):
        dialog.set_rect(CropRect(100, 100, 800, 600))
        rendered = dialog._preview.grab().toImage()
        assert rendered.size() == dialog._preview.size()
        center = rendered.pixelColor(rendered.width() // 2, rendered.height() // 2)
        # 元画像は単色 (200, 180, 160) なので、中央には元画像の色が描かれる
        assert (center.red(), center.green(), center.blue()) == (200, 180, 160)

    def test_preview_cleared_when_rect_removed(self, dialog):
        dialog.set_rect(CropRect(100, 100, 800, 600))
        dialog.set_rect(None)
        assert dialog._preview._source_rect() is None
        assert dialog._preview.text() == "選択範囲なし"

    def test_preview_cleared_for_zero_sized_rect(self, dialog):
        dialog.set_rect(CropRect(100, 100, 0, 600))
        assert dialog._preview._source_rect() is None
        assert dialog._preview.text() == "選択範囲なし"


class TestSave:
    def test_successful_save_calls_callback_once_and_accepts(self, qtbot, dialog, recorder):
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        with qtbot.waitSignal(dialog.saved, timeout=WAIT_MS) as blocker:
            dialog._save_button.click()
        assert blocker.args == [4242]
        assert len(recorder.calls) == 1
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.child_image_id() == 4242

    def test_callback_runs_off_the_gui_thread(self, qtbot, dialog, recorder):
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        with qtbot.waitSignal(dialog.saved, timeout=WAIT_MS):
            dialog._save_button.click()
        assert recorder.threads[0] is not QThread.currentThread()

    def test_save_button_disabled_while_callback_runs(self, qtbot, dialog, recorder):
        recorder.gate = threading.Event()
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog._save_button.click()
        qtbot.waitUntil(recorder.started.is_set, timeout=WAIT_MS)
        assert dialog.can_save() is False
        recorder.gate.set()
        _wait_save_finished(qtbot, dialog)

    def test_second_click_while_saving_does_not_call_again(self, qtbot, dialog, recorder):
        recorder.gate = threading.Event()
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog._save_button.click()
        qtbot.waitUntil(recorder.started.is_set, timeout=WAIT_MS)
        dialog._on_save()  # ボタンは無効なのでスロットを直接呼んで二重実行を試みる
        recorder.gate.set()
        _wait_save_finished(qtbot, dialog)
        assert len(recorder.calls) == 1

    def test_dialog_cannot_be_closed_while_saving(self, qtbot, dialog, recorder):
        recorder.gate = threading.Event()
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog._save_button.click()
        qtbot.waitUntil(recorder.started.is_set, timeout=WAIT_MS)
        dialog.close()
        dialog.reject()
        assert dialog.isVisible() is True
        recorder.gate.set()
        _wait_save_finished(qtbot, dialog)

    def test_save_failure_keeps_dialog_open_and_shows_error(self, qtbot, dialog, recorder):
        recorder.error = RuntimeError("DB 書き込みに失敗")
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog._save_button.click()
        qtbot.waitUntil(lambda: dialog.error_message() != "", timeout=WAIT_MS)
        assert len(recorder.calls) == 1
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.isVisible() is True
        assert "DB 書き込みに失敗" in dialog.error_message()
        assert dialog.child_image_id() is None

    def test_save_button_reenabled_after_failure(self, qtbot, dialog, recorder):
        recorder.error = OSError("ディスクがいっぱいです")
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog._save_button.click()
        _wait_save_finished(qtbot, dialog)
        assert dialog.can_save() is True

    def test_worker_references_released_after_save(self, qtbot, dialog, recorder):
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        with qtbot.waitSignal(dialog.saved, timeout=WAIT_MS):
            dialog._save_button.click()
        assert dialog._save_thread is None
        assert dialog._save_worker is None

    def test_retry_after_failure_succeeds(self, qtbot, dialog, recorder):
        recorder.error = ValueError("一時的な失敗")
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog._save_button.click()
        _wait_save_finished(qtbot, dialog)
        recorder.error = None
        with qtbot.waitSignal(dialog.saved, timeout=WAIT_MS):
            dialog._save_button.click()
        assert len(recorder.calls) == 2
        assert dialog.result() == QDialog.DialogCode.Accepted


class TestUnsavedChangesGuard:
    def test_reject_without_changes_does_not_ask(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: asked.append("asked") or QMessageBox.StandardButton.Yes,
        )
        dialog.reject()
        assert asked == []
        assert dialog.isVisible() is False

    def test_reject_with_changes_asks_and_no_keeps_open(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []

        def answer_no(*args, **kwargs):
            asked.append("asked")
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", answer_no)
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog.reject()
        assert asked == ["asked"]
        assert dialog.isVisible() is True

    def test_reject_with_changes_yes_closes(self, qtbot, dialog, monkeypatch):
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog.reject()
        assert dialog.isVisible() is False

    def test_adopted_tag_change_counts_as_unsaved(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []

        def answer_no(*args, **kwargs):
            asked.append("asked")
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", answer_no)
        _click_tag(qtbot, dialog._candidate_list, "cat")
        dialog.reject()
        assert asked == ["asked"]
        assert dialog.isVisible() is True

    def test_rating_change_counts_as_unsaved(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []

        def answer_no(*args, **kwargs):
            asked.append("asked")
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", answer_no)
        dialog._rating_control._buttons["X"].click()
        dialog.reject()
        assert asked == ["asked"]

    def test_close_event_asks_once_and_no_keeps_open(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []

        def answer_no(*args, **kwargs):
            asked.append("asked")
            return QMessageBox.StandardButton.No

        monkeypatch.setattr(QMessageBox, "question", answer_no)
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog.close()
        assert asked == ["asked"]
        assert dialog.isVisible() is True

    def test_close_event_yes_asks_once_and_closes(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []

        def answer_yes(*args, **kwargs):
            asked.append("asked")
            return QMessageBox.StandardButton.Yes

        monkeypatch.setattr(QMessageBox, "question", answer_yes)
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        dialog.close()
        assert asked == ["asked"]
        assert dialog.isVisible() is False

    def test_saved_dialog_does_not_ask_on_close(self, qtbot, dialog, monkeypatch):
        asked: list[str] = []
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *args, **kwargs: asked.append("asked") or QMessageBox.StandardButton.Yes,
        )
        dialog.set_rect(CropRect(0, 0, 1024, 768))
        with qtbot.waitSignal(dialog.saved, timeout=WAIT_MS):
            dialog._save_button.click()
        dialog.close()
        assert asked == []
