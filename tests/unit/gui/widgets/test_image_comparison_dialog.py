"""画像の比較画面と入口の GUI テスト (Issue #1399 / #1484)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.image_comparison_dialog import ImageComparisonDialog, ImageComparisonLauncher
from lorairo.gui.widgets.image_preview import ImagePreviewWidget
from lorairo.gui.widgets.staging_widget import StagingWidget
from lorairo.gui.widgets.thumbnail_selector_widget import ThumbnailSelectorWidget
from lorairo.gui.workers.image_comparison_worker import (
    ImageComparisonLoadResult,
    ImageComparisonWorker,
    LoadedComparisonSide,
    decode_preview_image,
)
from lorairo.services.image_comparison import (
    ImageComparisonService,
    Side,
    compare_snapshots,
    snapshot_from_metadata,
)

pytestmark = [pytest.mark.unit, pytest.mark.gui]

COMPARE_MENU_TEXT = "選択した画像を比較…"


class _FakeSource:
    """読み取りだけを記録する画像メタデータの取得元。書き込み API は持たない。"""

    def __init__(self, data: dict[int, dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[int] = []

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        self.calls.append(image_id)
        return self.data.get(image_id)


def _write_image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> str:
    Image.new("RGB", size, color).save(path)
    return str(path)


@pytest.fixture
def source(tmp_path: Path) -> _FakeSource:
    def meta(image_id: int, tags: list[str], caption: str | None, color: tuple[int, int, int]) -> dict:
        return {
            "id": image_id,
            "stored_image_path": _write_image(tmp_path / f"{image_id}.png", (64, 48), color),
            "original_image_path": f"/src/img_{image_id}.png",
            "width": 64,
            "height": 48,
            "tags": [{"tag": t, "model_name": "wd", "source": "AI"} for t in tags],
            "captions": [{"caption": caption, "model_name": "blip"}] if caption else [],
            "caption_text": caption or "",
        }

    return _FakeSource(
        {
            1: meta(1, ["cat", "sitting"], "a cat sitting", (255, 0, 0)),
            2: meta(2, ["dog", "sitting"], "a dog sitting", (0, 255, 0)),
            3: meta(3, [], None, (0, 0, 255)),
        }
    )


@pytest.fixture
def dialog(qtbot, source: _FakeSource) -> ImageComparisonDialog:
    widget = ImageComparisonDialog(ImageComparisonService(source))
    qtbot.addWidget(widget)
    yield widget
    widget.shutdown()


def _wait_loaded(qtbot, dialog: ImageComparisonDialog, left: int, right: int) -> ImageComparisonLoadResult:
    qtbot.waitUntil(
        lambda: (
            dialog.current_result is not None
            and (
                dialog.current_result.left.snapshot.image_id,
                dialog.current_result.right.snapshot.image_id,
            )
            == (left, right)
        ),
        timeout=5000,
    )
    result = dialog.current_result
    assert result is not None
    return result


def test_dialog_shows_both_sides_and_tag_diff(qtbot, dialog: ImageComparisonDialog) -> None:
    dialog.set_candidates([1, 2, 3])
    result = _wait_loaded(qtbot, dialog, 1, 2)

    assert result.comparison.tags.common == ("sitting",)
    assert dialog._tag_lists["left_only"].item(0).text() == "cat"
    assert dialog._tag_lists["right_only"].item(0).text() == "dog"
    assert dialog._tag_lists["common"].item(0).text() == "sitting"
    assert "画像 ID: 1" in dialog._panels[Side.LEFT].provenance_label.text()
    assert "img_1.png" in dialog._panels[Side.LEFT].provenance_label.text()
    assert "画像 ID: 2" in dialog._panels[Side.RIGHT].provenance_label.text()
    assert dialog._panels[Side.LEFT].preview.pixmap_item is not None
    # キャプション差分: 左は削除側だけ、右は追加側だけを強調し、原文を保つ
    assert dialog._caption_browsers[Side.LEFT].toPlainText() == "a cat sitting"
    assert dialog._caption_browsers[Side.RIGHT].toPlainText() == "a dog sitting"


def test_dialog_missing_side_is_not_shown_as_same(qtbot, dialog: ImageComparisonDialog) -> None:
    dialog.set_candidates([1, 3])
    _wait_loaded(qtbot, dialog, 1, 3)

    assert "右の画像にタグが無い" in dialog._tag_message.text()
    assert all(lst.count() == 0 for lst in dialog._tag_lists.values())
    assert "右の画像にキャプションが無い" in dialog._caption_message.text()
    assert dialog._caption_browsers[Side.RIGHT].toPlainText() == "(キャプションなし)"
    assert dialog._caption_browsers[Side.LEFT].toPlainText() == "a cat sitting"
    assert "同じ" not in dialog._tag_message.text()


def test_dialog_swap_keeps_image_and_annotation_together(qtbot, dialog: ImageComparisonDialog) -> None:
    dialog.set_candidates([1, 2])
    _wait_loaded(qtbot, dialog, 1, 2)
    left_pixel = dialog._panels[Side.LEFT].preview._current_pixmap.toImage().pixelColor(1, 1)

    dialog._swap_button.click()
    result = _wait_loaded(qtbot, dialog, 2, 1)

    assert result.left.snapshot.tag_names == ("dog", "sitting")
    right_pixel = dialog._panels[Side.RIGHT].preview._current_pixmap.toImage().pixelColor(1, 1)
    assert right_pixel == left_pixel  # 画像 1 (赤) が注釈と一緒に右へ移る
    assert dialog._combos[Side.LEFT].currentData() == 2


def test_dialog_pin_left_and_switch_right_candidate(qtbot, dialog: ImageComparisonDialog) -> None:
    dialog.set_candidates([1, 2, 3])
    _wait_loaded(qtbot, dialog, 1, 2)

    dialog._pin_checks[Side.LEFT].setChecked(True)
    assert not dialog._next_buttons[Side.LEFT].isEnabled()
    assert not dialog._combos[Side.LEFT].isEnabled()

    dialog._next_buttons[Side.RIGHT].click()
    _wait_loaded(qtbot, dialog, 1, 3)
    assert dialog.selection is not None and dialog.selection.left_id == 1


def test_dialog_combo_rejects_other_side_image(qtbot, dialog: ImageComparisonDialog) -> None:
    dialog.set_candidates([1, 2, 3])
    _wait_loaded(qtbot, dialog, 1, 2)
    combo = dialog._combos[Side.RIGHT]
    combo.setCurrentIndex(combo.findData(1))
    assert combo.currentData() == 2


def test_dialog_discards_stale_result(qtbot, dialog: ImageComparisonDialog, source: _FakeSource) -> None:
    dialog.set_candidates([1, 2, 3])
    _wait_loaded(qtbot, dialog, 1, 2)
    old_generation = dialog.generation

    dialog._next_buttons[Side.RIGHT].click()  # 世代が進む
    left = LoadedComparisonSide(snapshot_from_metadata(1, source.data[1]), None)
    right = LoadedComparisonSide(snapshot_from_metadata(2, source.data[2]), None)
    stale = ImageComparisonLoadResult(
        generation=old_generation,
        left=left,
        right=right,
        comparison=compare_snapshots(left.snapshot, right.snapshot),
    )
    dialog._on_worker_finished(stale)
    assert dialog.current_result is None or dialog.current_result.right.snapshot.image_id == 3

    result = _wait_loaded(qtbot, dialog, 1, 3)
    assert result.generation == dialog.generation


def test_dialog_close_stops_loading_and_discards_late_result(
    qtbot, dialog: ImageComparisonDialog, source: _FakeSource
) -> None:
    dialog.set_candidates([1, 2])
    dialog.show()
    generation = dialog.generation
    dialog.close()
    assert dialog.generation > generation
    left = LoadedComparisonSide(snapshot_from_metadata(1, source.data[1]), None)
    right = LoadedComparisonSide(snapshot_from_metadata(2, source.data[2]), None)
    dialog._on_worker_finished(
        ImageComparisonLoadResult(generation, left, right, compare_snapshots(left.snapshot, right.snapshot))
    )
    assert dialog.current_result is None


def test_dialog_reload_reads_db_again(qtbot, dialog: ImageComparisonDialog, source: _FakeSource) -> None:
    dialog.set_candidates([1, 2])
    _wait_loaded(qtbot, dialog, 1, 2)
    source.data[2]["tags"] = [{"tag": "cat", "model_name": "wd", "source": "AI"}]
    calls_before = len(source.calls)

    dialog.reload()
    result = _wait_loaded(qtbot, dialog, 1, 2)
    assert len(source.calls) == calls_before + 2  # キャッシュを捨てて左右とも読み直す
    assert result.generation == dialog.generation
    assert result.comparison.tags.right_only == ()


def test_worker_reuses_cached_side_without_reading(qtbot, source: _FakeSource) -> None:
    service = ImageComparisonService(source)
    cached = LoadedComparisonSide(snapshot_from_metadata(1, source.data[1]), QImage())
    worker = ImageComparisonWorker(service, generation=5, left_id=1, right_id=2, cached={1: cached})
    result = worker.execute()
    assert source.calls == [2]
    assert result.generation == 5
    assert result.left is cached
    assert result.right.preview is not None


def test_decode_preview_image_bounds_large_image(tmp_path: Path) -> None:
    path = Path(_write_image(tmp_path / "big.png", (4000, 1000), (1, 2, 3)))
    image = decode_preview_image(path, 1600)
    assert image is not None
    assert max(image.width(), image.height()) == 1600
    assert decode_preview_image(tmp_path / "missing.png", 1600) is None


def test_image_preview_show_decoded_image(qtbot) -> None:
    widget = ImagePreviewWidget()
    qtbot.addWidget(widget)
    image = QImage(10, 8, QImage.Format.Format_RGB32)
    image.fill(0)
    widget.show_decoded_image(image, None)
    assert widget.pixmap_item is not None
    widget.show_decoded_image(None)
    assert widget.pixmap_item is None


# --- 入口 -------------------------------------------------------------------


def test_launcher_requires_two_images_and_source(qtbot, source: _FakeSource) -> None:
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    assert ImageComparisonLauncher(None, parent).open([1, 2]) is False
    launcher = ImageComparisonLauncher(source, parent)
    assert launcher.open([1, 1]) is False
    assert launcher.open([1, 2]) is True
    assert launcher.dialog is not None and launcher.dialog.isVisible()
    launcher.shutdown()


def test_launcher_closes_dialog_on_dataset_change(qtbot, source: _FakeSource) -> None:
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    dsm = DatasetStateManager()
    launcher = ImageComparisonLauncher(source, parent, dsm)
    launcher.open([1, 2])
    assert launcher.dialog is not None
    generation = launcher.dialog.generation
    dsm.set_dataset_path(Path("/tmp/other_project"))
    assert not launcher.dialog.isVisible()
    assert launcher.dialog.generation > generation
    launcher.shutdown()


class _FakeAction:
    def __init__(self, text: str) -> None:
        self._text = text
        self._enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def isEnabled(self) -> bool:
        return self._enabled

    def text(self) -> str:
        return self._text


class _StubThumbnail:
    def __init__(self, image_id: int) -> None:
        self.image_id = image_id

    def update(self) -> None:
        """再描画通知 (何もしない)。"""


def _patch_menu(monkeypatch: pytest.MonkeyPatch, choose: str | None) -> dict[str, _FakeAction]:
    created: dict[str, _FakeAction] = {}

    class FakeMenu:
        def __init__(self, parent: object | None = None) -> None:
            pass

        def addAction(self, text: str) -> _FakeAction:
            created[text] = _FakeAction(text)
            return created[text]

        def addSeparator(self) -> None:
            return None

        def exec(self, position: object) -> _FakeAction | None:
            return created.get(choose) if choose else None

    monkeypatch.setattr("lorairo.gui.widgets.thumbnail_selector_widget.QMenu", FakeMenu)
    return created


@pytest.fixture
def thumbnail_widget(qtbot) -> ThumbnailSelectorWidget:
    widget = ThumbnailSelectorWidget(dataset_state=DatasetStateManager())
    qtbot.addWidget(widget)
    widget.thumbnail_items.extend([_StubThumbnail(11), _StubThumbnail(12)])
    return widget


def test_thumbnail_compare_menu_absent_until_enabled(
    thumbnail_widget: ThumbnailSelectorWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    """比較を配線していないタブ (エクスポート等) には項目を出さない。"""
    assert thumbnail_widget.dataset_state is not None
    thumbnail_widget.dataset_state.set_selected_images([11, 12])
    actions = _patch_menu(monkeypatch, None)
    thumbnail_widget._on_context_menu_requested(QPoint(0, 0))
    assert COMPARE_MENU_TEXT not in actions


def test_thumbnail_compare_menu_enabled_for_two_or_more(
    thumbnail_widget: ThumbnailSelectorWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    thumbnail_widget.set_compare_action_enabled(True)
    assert thumbnail_widget.dataset_state is not None
    for selection, expected in (([11], False), ([11, 12], True)):
        thumbnail_widget.dataset_state.set_selected_images(selection)
        actions = _patch_menu(monkeypatch, None)
        thumbnail_widget._on_context_menu_requested(QPoint(0, 0))
        assert actions[COMPARE_MENU_TEXT].isEnabled() is expected


def test_thumbnail_compare_menu_emits_selected_ids(
    qtbot, thumbnail_widget: ThumbnailSelectorWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    thumbnail_widget.set_compare_action_enabled(True)
    assert thumbnail_widget.dataset_state is not None
    thumbnail_widget.dataset_state.set_selected_images([12, 11])
    _patch_menu(monkeypatch, COMPARE_MENU_TEXT)
    with qtbot.waitSignal(thumbnail_widget.compare_requested, timeout=1000) as blocker:
        thumbnail_widget._on_context_menu_requested(QPoint(0, 0))
    assert sorted(blocker.args[0]) == [11, 12]


def test_staging_compare_button(qtbot) -> None:
    widget = StagingWidget()
    qtbot.addWidget(widget)
    state_manager = DatasetStateManager()
    state_manager.set_dataset_images([{"id": i, "stored_image_path": f"/x/{i}.png"} for i in (5, 6, 7)])
    widget.set_dataset_state_manager(state_manager)
    button = widget._compare_button
    assert not button.isEnabled()
    widget.add_image_ids([5])
    assert not button.isEnabled()
    widget.add_image_ids([6, 7])
    assert button.isEnabled()
    with qtbot.waitSignal(widget.compare_requested, timeout=1000) as blocker:
        button.click()
    assert blocker.args[0] == [5, 6, 7]
