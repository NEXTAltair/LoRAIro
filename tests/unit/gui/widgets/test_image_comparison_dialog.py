"""画像の比較画面と入口の GUI テスト (Issue #1399 / #1484 / #1494)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QWheelEvent

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.image_comparison_dialog import (
    ComparisonImageViewport,
    ImageComparisonDialog,
    ImageComparisonLauncher,
)
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

    def __init__(
        self,
        data: dict[int, dict[str, Any]],
        gen_data: dict[int, Any] | None = None,
        sources_data: dict[int, list[Any]] | None = None,
    ) -> None:
        self.data = data
        self.gen_data = gen_data or {}
        self.sources_data = sources_data or {}
        self.calls: list[int] = []

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        self.calls.append(image_id)
        return self.data.get(image_id)

    def get_generation_metadata(self, image_id: int) -> Any:
        return self.gen_data.get(image_id)

    def get_generation_metadata_sources(self, image_id: int) -> list[Any]:
        return self.sources_data.get(image_id, [])


def _write_image(path: Path, size: tuple[int, int], color: tuple[int, int, int]) -> str:
    Image.new("RGB", size, color).save(path)
    return str(path)


@pytest.fixture
def source(tmp_path: Path) -> _FakeSource:
    def meta(
        image_id: int,
        tags: list[str],
        caption: str | None,
        color: tuple[int, int, int],
        size: tuple[int, int] = (64, 48),
    ) -> dict[str, Any]:
        return {
            "id": image_id,
            "stored_image_path": _write_image(tmp_path / f"{image_id}.png", size, color),
            "original_image_path": f"/src/img_{image_id}.png",
            "width": size[0],
            "height": size[1],
            "tags": [{"tag": t, "model_name": "wd", "source": "AI"} for t in tags],
            "captions": [{"caption": caption, "model_name": "blip"}] if caption else [],
            "caption_text": caption or "",
        }

    return _FakeSource(
        {
            1: meta(1, ["cat", "sitting"], "a cat sitting", (255, 0, 0), size=(100, 80)),
            2: meta(2, ["dog", "sitting"], "a dog sitting", (0, 255, 0), size=(200, 160)),
            3: meta(3, [], None, (0, 0, 255), size=(64, 48)),
        }
    )


@pytest.fixture
def dialog(qtbot, source: _FakeSource) -> ImageComparisonDialog:
    import gc

    widget = ImageComparisonDialog(ImageComparisonService(source))
    qtbot.addWidget(widget)
    yield widget
    widget.shutdown()
    gc.collect()


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


# --- 同期ズーム / パン (#1494) ----------------------------------------------


def test_sync_zoom_and_pan_aligns_different_resolution_viewports(
    qtbot, dialog: ImageComparisonDialog
) -> None:
    """同期オン時、解像度が異なる左右画像でも同じ倍率・同じ相対位置 (rx, ry) に揃う。"""
    dialog.set_candidates([1, 2])
    _wait_loaded(qtbot, dialog, 1, 2)

    left_vp = dialog.left_viewport
    right_vp = dialog.right_viewport
    assert isinstance(left_vp, ComparisonImageViewport)
    assert isinstance(right_vp, ComparisonImageViewport)
    assert dialog.is_sync_enabled() is True

    # 左 (100x80) をズーム・パンすると、右 (200x160) も同じ zoom_factor と相対位置 (rx, ry) になる
    left_vp.set_zoom_factor(2.5)
    left_vp.set_relative_center(0.25, 0.75)

    assert right_vp.zoom_factor == pytest.approx(2.5)
    assert right_vp.get_relative_center() == pytest.approx((0.25, 0.75))
    # ピクセル座標系では各画像の解像度に応じた対応位置を指す
    assert left_vp.get_scene_center() == QPointF(25.0, 60.0)
    assert right_vp.get_scene_center() == QPointF(50.0, 120.0)

    # 右側からのホイールズームとパンも左側へ反映される
    wheel_in = QWheelEvent(
        QPointF(10.0, 10.0),
        QPointF(10.0, 10.0),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    right_vp.wheelEvent(wheel_in)
    right_vp.set_relative_center(0.6, 0.2)

    assert left_vp.zoom_factor == pytest.approx(right_vp.zoom_factor)
    assert left_vp.get_relative_center() == pytest.approx((0.6, 0.2))


def test_sync_off_keeps_viewports_independent_and_realigns_when_reenabled(
    qtbot, dialog: ImageComparisonDialog
) -> None:
    """同期オフ時は左右が独立し、再びオンにすると左の表示状態へ右が揃う。"""
    dialog.set_candidates([1, 2])
    _wait_loaded(qtbot, dialog, 1, 2)

    left_vp = dialog.left_viewport
    right_vp = dialog.right_viewport

    dialog.set_sync_enabled(False)
    assert dialog.is_sync_enabled() is False

    left_vp.set_zoom_factor(3.0)
    left_vp.set_relative_center(0.2, 0.8)

    # 右側は初期状態のまま変わらない
    assert right_vp.zoom_factor == pytest.approx(1.0)
    assert right_vp.get_relative_center() == pytest.approx((0.5, 0.5))

    right_vp.set_zoom_factor(1.5)
    right_vp.set_relative_center(0.9, 0.1)
    assert left_vp.zoom_factor == pytest.approx(3.0)
    assert left_vp.get_relative_center() == pytest.approx((0.2, 0.8))

    # 同期をオンに戻すと、左側の状態へ右側が即座に揃う
    dialog.set_sync_enabled(True)
    assert right_vp.zoom_factor == pytest.approx(3.0)
    assert right_vp.get_relative_center() == pytest.approx((0.2, 0.8))


def test_reset_zoom_button_restores_both_viewports_when_sync_on(
    qtbot, dialog: ImageComparisonDialog
) -> None:
    """同期オン時にリセットボタンを押すと両側の倍率と中心が初期値に戻る。"""
    dialog.set_candidates([1, 2])
    _wait_loaded(qtbot, dialog, 1, 2)

    left_vp = dialog.left_viewport
    right_vp = dialog.right_viewport

    dialog.btnZoomIn.click()
    left_vp.set_relative_center(0.15, 0.85)
    assert left_vp.zoom_factor > 1.0
    assert right_vp.zoom_factor == pytest.approx(left_vp.zoom_factor)
    assert right_vp.get_relative_center() == pytest.approx((0.15, 0.85))

    dialog.btnResetZoom.click()
    assert left_vp.zoom_factor == pytest.approx(1.0)
    assert right_vp.zoom_factor == pytest.approx(1.0)
    assert left_vp.get_relative_center() == pytest.approx((0.5, 0.5))
    assert right_vp.get_relative_center() == pytest.approx((0.5, 0.5))


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


# --- 生成メタデータの差分 (Issue #1485) -------------------------------------


def test_dialog_shows_generation_metadata_diff_and_raw_sources(qtbot, source: _FakeSource) -> None:
    raw_left = (
        "masterpiece, (best quality:1.2), 1girl,\nsolo, <lora:styleA:0.8>\n"
        "Negative prompt: lowres, [bad hands:0.9]\n"
        "Steps: 28, Sampler: DPM++ 2M, Schedule type: Karras, CFG scale: 7.5, Seed: 111, Model: anime_v1"
    )
    raw_right = (
        "masterpiece, (best quality:1.0), 1girl,\nsolo, <lora:styleA:0.5>\n"
        "Negative prompt: lowres, [bad hands:0.9]\n"
        "Steps: 35, Sampler: Euler a, Schedule type: Karras, CFG scale: 6, Seed: 222, Model: anime_v2"
    )
    source.gen_data[1] = {
        "status": "parsed",
        "tool": "sd_webui",
        "positive_prompt": "masterpiece, (best quality:1.2), 1girl,\nsolo, <lora:styleA:0.8>",
        "negative_prompt": "lowres, [bad hands:0.9]",
        "model_name": "anime_v1",
        "model_hash": "hash1",
        "loras": [{"name": "styleA", "weight": "0.8", "kind": "lora"}],
        "seed": "111",
        "steps": 28,
        "sampler": "DPM++ 2M",
        "cfg_scale": 7.5,
        "extra": {"Schedule type": "Karras", "Denoising strength": "0.5"},
    }
    source.gen_data[2] = {
        "status": "parsed",
        "tool": "sd_webui",
        "positive_prompt": "masterpiece, (best quality:1.0), 1girl,\nsolo, <lora:styleA:0.5>",
        "negative_prompt": "lowres, [bad hands:0.9]",
        "model_name": "anime_v2",
        "model_hash": "hash1",
        "loras": [{"name": "styleA", "weight": "0.5", "kind": "lora"}],
        "seed": "222",
        "steps": 35,
        "sampler": "Euler a",
        "cfg_scale": 6.0,
        "extra": {"Schedule type": "Karras", "Denoising strength": "0.7"},
    }
    source.sources_data[1] = [{"kind": "png_text", "key": "parameters", "raw_text": raw_left}]
    source.sources_data[2] = [{"kind": "png_text", "key": "parameters", "raw_text": raw_right}]

    widget = ImageComparisonDialog(ImageComparisonService(source))
    qtbot.addWidget(widget)
    try:
        widget.set_candidates([1, 2])
        _wait_loaded(qtbot, widget, 1, 2)

        assert "差分あり:" in widget._generation_message.text()
        assert widget.generation_field_row("tool") == ("同じ", "SD WebUI", "SD WebUI")
        assert widget.generation_field_row("model_name") == ("差分あり", "anime_v1", "anime_v2")
        assert widget.generation_field_row("model_hash") == ("同じ", "hash1", "hash1")
        assert widget.generation_field_row("loras") == ("差分あり", "styleA:0.8", "styleA:0.5")
        assert widget.generation_field_row("seed") == ("差分あり", "111", "222")
        assert widget.generation_field_row("steps") == ("差分あり", "28", "35")
        assert widget.generation_field_row("sampler") == ("差分あり", "DPM++ 2M", "Euler a")
        assert widget.generation_field_row("scheduler") == ("同じ", "Karras", "Karras")
        assert widget.generation_field_row("cfg_scale") == ("差分あり", "7.5", "6")
        assert widget.generation_field_row("denoise") == ("差分あり", "0.5", "0.7")

        # プロンプトの改行・重み表記・<lora:...> タグが壊れずに表示される
        assert widget._prompt_browsers[Side.LEFT].toPlainText() == (
            "masterpiece, (best quality:1.2), 1girl,\nsolo, <lora:styleA:0.8>"
        )
        assert widget._prompt_browsers[Side.RIGHT].toPlainText() == (
            "masterpiece, (best quality:1.0), 1girl,\nsolo, <lora:styleA:0.5>"
        )
        assert widget._negative_prompt_browsers[Side.LEFT].toPlainText() == "lowres, [bad hands:0.9]"

        # 原データの展開と確認
        assert not widget._raw_metadata_container.isVisibleTo(widget)
        widget._raw_metadata_toggle.click()
        assert widget._raw_metadata_toggle.isChecked()
        assert raw_left in widget._raw_metadata_views[Side.LEFT].toPlainText()
        assert raw_right in widget._raw_metadata_views[Side.RIGHT].toPlainText()
    finally:
        widget.shutdown()


def test_dialog_generation_metadata_missing_side_shows_nashi_not_same(qtbot, source: _FakeSource) -> None:
    source.gen_data[1] = {
        "status": "parsed",
        "tool": "sd_webui",
        "positive_prompt": "1girl",
        "model_name": "anime_v1",
        "seed": "111",
        "steps": 20,
        "sampler": "Euler a",
        "cfg_scale": 7.0,
    }
    source.gen_data[2] = {"status": "no_metadata"}
    source.gen_data[3] = None

    widget = ImageComparisonDialog(ImageComparisonService(source))
    qtbot.addWidget(widget)
    try:
        # 片側 (右) が生成メタデータなし
        widget.set_candidates([1, 2])
        _wait_loaded(qtbot, widget, 1, 2)
        assert "右の画像に生成メタデータが無いため比較できません" in widget._generation_message.text()
        assert "同じ" not in widget._generation_message.text()
        assert widget.generation_field_row("model_name") == ("左のみ", "anime_v1", "なし")
        assert widget.generation_field_row("negative_prompt") == ("なし", "なし", "なし")
        assert widget._prompt_browsers[Side.LEFT].toPlainText() == "1girl"
        assert widget._prompt_browsers[Side.RIGHT].toPlainText() == "なし"
        assert widget._raw_metadata_views[Side.RIGHT].toPlainText() == "なし"

        # 両側とも生成メタデータなし (画像と現在注釈の比較はそのまま動く)
        widget.set_candidates([2, 3])
        _wait_loaded(qtbot, widget, 2, 3)
        assert "左右どちらの画像にも生成メタデータがありません" in widget._generation_message.text()
        assert "同じ" not in widget._generation_message.text()
        for row in range(widget._generation_table.rowCount()):
            assert widget._generation_table.item(row, 1).text() == "なし"
            assert widget._generation_table.item(row, 2).text() == "なし"
            assert widget._generation_table.item(row, 3).text() == "なし"
        # タグ・キャプションの比較表示は引き続き使える
        assert widget._caption_browsers[Side.LEFT].toPlainText() == "a dog sitting"
        assert widget._caption_browsers[Side.RIGHT].toPlainText() == "(キャプションなし)"
    finally:
        widget.shutdown()
