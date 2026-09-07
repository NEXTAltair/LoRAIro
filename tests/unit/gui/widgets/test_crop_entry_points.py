"""クロップ導線の入口 (一覧右クリック / プレビューボタン) の GUI テスト (#1346)。

どちらの入口も ``crop_requested(image_id)`` を上げるだけで、ダイアログ生成には関与しない。
1 枚選択時のみ有効になること・配線したタブだけに表示されること・現在画像 ID を正しく
乗せることを検証する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from PySide6.QtCore import QPoint, Qt

from lorairo.gui.state.dataset_state import DatasetStateManager
from lorairo.gui.widgets.image_preview import ImagePreviewWidget
from lorairo.gui.widgets.thumbnail_selector_widget import ThumbnailSelectorWidget

CROP_MENU_TEXT = "クロップして学習素材を作成…"
_MENU_SYMBOL = "lorairo.gui.widgets.thumbnail_selector_widget.QMenu"


class _StubThumbnail:
    """`thumbnail_items` の可視 ID 収集と再描画通知だけを満たす軽量スタブ。"""

    def __init__(self, image_id: int) -> None:
        self.image_id = image_id

    def update(self) -> None:
        """選択変更時の再描画トリガー (スタブでは何もしない)。"""


class _RecordingWorkerService:
    """``start_thumbnail_page_load`` の引数だけを記録する WorkerService スタブ。

    ``cancel_thumbnail_load`` は実装しない (ウィジェット側が hasattr で分岐するため、
    未完了要求のキャンセル経路には入らない)。
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def start_thumbnail_page_load(
        self,
        search_result: Any,
        thumbnail_size: Any,
        image_ids: list[int],
        page_num: int,
        request_id: str,
        cancel_previous: bool = True,
    ) -> str:
        self.calls.append(
            {
                "search_result": search_result,
                "image_ids": list(image_ids),
                "page_num": page_num,
                "request_id": request_id,
            }
        )
        return f"worker-{len(self.calls)}"


class _FakeAction:
    """QAction の text / 活性のみを模した項目スタブ。"""

    def __init__(self, text: str) -> None:
        self._text = text
        self._enabled = True

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def isEnabled(self) -> bool:
        return self._enabled

    def text(self) -> str:
        return self._text


def _patch_menu(monkeypatch: pytest.MonkeyPatch, choose: str | None) -> dict[str, object]:
    """右クリックメニューを組み立て専用のフェイクへ差し替える。

    実 ``QMenu.exec`` はヘッドレスでも入力待ちでブロックするため、ウィジェットが参照する
    ``QMenu`` シンボル自体を差し替えて「組み立てた項目」と「選択結果」を制御する。

    Args:
        monkeypatch: 差し替え用 fixture。
        choose: 選択させる項目テキスト。None なら「何も選ばず閉じる」。

    Returns:
        キー "actions" に組み立てられた項目リストが入る辞書。
    """
    created: dict[str, object] = {}

    class FakeMenu:
        def __init__(self, parent: object | None = None) -> None:
            self.entries: list[_FakeAction] = []
            created["actions"] = self.entries

        def addAction(self, text: str) -> _FakeAction:
            action = _FakeAction(text)
            self.entries.append(action)
            return action

        def addSeparator(self) -> None:
            return None

        def exec(self, position: object) -> _FakeAction | None:
            if choose is None:
                return None
            return next((a for a in self.entries if a.text() == choose), None)

    monkeypatch.setattr(_MENU_SYMBOL, FakeMenu)
    return created


def _action_map(captured: dict[str, object]) -> dict[str, _FakeAction]:
    """捕捉した項目リストをテキスト → 項目の辞書にする。"""
    actions = captured["actions"]
    assert isinstance(actions, list)
    return {action.text(): action for action in actions}


@pytest.fixture
def thumbnail_widget(qtbot) -> ThumbnailSelectorWidget:
    """dataset_state 付きのサムネイル一覧 (可視サムネ 2 枚)。"""
    widget = ThumbnailSelectorWidget(dataset_state=DatasetStateManager())
    qtbot.addWidget(widget)
    widget.thumbnail_items.extend([_StubThumbnail(11), _StubThumbnail(12)])
    return widget


@pytest.mark.gui
def test_crop_menu_absent_until_enabled(
    thumbnail_widget: ThumbnailSelectorWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    """既定 (opt-in 未設定) では右クリックメニューにクロップ項目が出ない。"""
    assert thumbnail_widget.dataset_state is not None
    thumbnail_widget.dataset_state.set_selected_images([11])
    captured = _patch_menu(monkeypatch, None)

    thumbnail_widget._on_context_menu_requested(QPoint(0, 0))

    assert CROP_MENU_TEXT not in _action_map(captured)


@pytest.mark.gui
def test_crop_menu_enabled_only_for_single_selection(
    thumbnail_widget: ThumbnailSelectorWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1 枚選択時のみクロップ項目が有効、複数選択・未選択では無効。"""
    thumbnail_widget.set_crop_action_enabled(True)
    assert thumbnail_widget.dataset_state is not None

    for selection, expected_enabled in (([11], True), ([11, 12], False), ([], False)):
        thumbnail_widget.dataset_state.set_selected_images(selection)
        captured = _patch_menu(monkeypatch, None)

        thumbnail_widget._on_context_menu_requested(QPoint(0, 0))

        actions = _action_map(captured)
        assert CROP_MENU_TEXT in actions
        assert actions[CROP_MENU_TEXT].isEnabled() is expected_enabled


@pytest.mark.gui
def test_crop_menu_emits_selected_image_id(
    qtbot, thumbnail_widget: ThumbnailSelectorWidget, monkeypatch: pytest.MonkeyPatch
) -> None:
    """クロップ項目を選ぶと選択中の 1 枚の image_id が crop_requested に乗る。"""
    thumbnail_widget.set_crop_action_enabled(True)
    assert thumbnail_widget.dataset_state is not None
    thumbnail_widget.dataset_state.set_selected_images([12])
    _patch_menu(monkeypatch, CROP_MENU_TEXT)

    with qtbot.waitSignal(thumbnail_widget.crop_requested, timeout=1000) as blocker:
        thumbnail_widget._on_context_menu_requested(QPoint(0, 0))

    assert blocker.args == [12]


@pytest.fixture
def preview_image(tmp_path: Path) -> Path:
    """プレビュー表示に使う小さな実画像。"""
    path = tmp_path / "preview.png"
    Image.new("RGB", (64, 48), (10, 120, 200)).save(path)
    return path


@pytest.mark.gui
def test_preview_crop_button_hidden_by_default(qtbot) -> None:
    """プレビューのクロップボタンは既定で非表示 (配線したタブだけが表示する)。"""
    widget = ImagePreviewWidget()
    qtbot.addWidget(widget)

    assert widget._crop_action_bar.isHidden() is True
    assert widget.current_image_id() is None


@pytest.mark.gui
def test_preview_crop_button_emits_current_image_id(qtbot, preview_image: Path) -> None:
    """現在画像を受け取るとボタンが有効になり、押下で crop_requested を emit する。"""
    widget = ImagePreviewWidget()
    qtbot.addWidget(widget)
    widget.set_crop_action_visible(True)
    assert widget._crop_button.isEnabled() is False

    widget._on_image_data_received({"id": 42, "stored_image_path": str(preview_image)})

    assert widget.current_image_id() == 42
    assert widget._crop_button.isEnabled() is True

    with qtbot.waitSignal(widget.crop_requested, timeout=1000) as blocker:
        qtbot.mouseClick(widget._crop_button, Qt.MouseButton.LeftButton)

    assert blocker.args == [42]


@pytest.mark.gui
def test_preview_crop_button_disabled_on_empty_selection(qtbot, preview_image: Path) -> None:
    """選択解除 (空データ) でボタンは再び無効になり、現在画像 ID もクリアされる。"""
    widget = ImagePreviewWidget()
    qtbot.addWidget(widget)
    widget.set_crop_action_visible(True)
    widget._on_image_data_received({"id": 42, "stored_image_path": str(preview_image)})

    widget._on_image_data_received({})

    assert widget.current_image_id() is None
    assert widget._crop_button.isEnabled() is False


@pytest.mark.gui
def test_refresh_current_page_is_noop_without_pagination(qtbot) -> None:
    """dataset_state 未注入 (ページネーション未初期化) の一覧再読込は安全に no-op (#1346)。"""
    widget = ThumbnailSelectorWidget(dataset_state=None)
    qtbot.addWidget(widget)
    assert widget.pagination_state is None

    widget.refresh_current_page()

    assert widget.pagination_state is None


@pytest.mark.gui
def test_refresh_current_page_drops_stale_page_cache(
    thumbnail_widget: ThumbnailSelectorWidget,
) -> None:
    """一覧の画像集合が変わった後の再読込でページキャッシュを捨てる (#1346)。

    ページキャッシュはページ番号でしか引けないため、集合が変わったまま再利用すると
    追加した画像が描画されない。
    """
    assert thumbnail_widget.pagination_state is not None
    thumbnail_widget.page_cache.set_page(1, [])
    assert thumbnail_widget.cache_usage_info()["page_cache_count"] == 1

    thumbnail_widget.refresh_current_page()

    assert thumbnail_widget.cache_usage_info()["page_cache_count"] == 0


@pytest.mark.gui
def test_refresh_current_page_requests_added_image_from_dataset_state(
    thumbnail_widget: ThumbnailSelectorWidget,
) -> None:
    """再読込は dataset_state (SSoT) のメタデータで追加画像を要求する (Codex P2)。

    ``ThumbnailWorker`` は要求 ID のメタデータを渡された ``SearchResult`` からしか
    解決しないため、検索結果のままだと追加画像が省かれて灰色プレースホルダになる。
    """
    worker_service = _RecordingWorkerService()
    thumbnail_widget.set_worker_service(worker_service)
    dataset_state = thumbnail_widget.dataset_state
    assert dataset_state is not None
    dataset_state.set_dataset_images([{"id": 11, "stored_image_path": "/test/a.jpg"}])

    dataset_state.add_image({"id": 99, "stored_image_path": "/test/crop.jpg"})
    thumbnail_widget.refresh_current_page()

    call = worker_service.calls[-1]
    assert 99 in call["image_ids"]
    requested = {item["id"]: item for item in call["search_result"].image_metadata}
    assert requested[99]["stored_image_path"] == "/test/crop.jpg"


@pytest.mark.gui
def test_refresh_current_page_requests_page_without_prior_search(
    thumbnail_widget: ThumbnailSelectorWidget,
) -> None:
    """検索未実行 (一覧が空) から追加しても、その 1 件のページを要求する (Codex P2)。

    旧実装は検索結果が無いとサムネイルを要求できず、ローディング表示が残っていた。
    """
    worker_service = _RecordingWorkerService()
    thumbnail_widget.set_worker_service(worker_service)
    dataset_state = thumbnail_widget.dataset_state
    assert dataset_state is not None
    assert dataset_state.filtered_images == []

    dataset_state.add_image({"id": 77, "stored_image_path": "/test/crop.jpg"})
    thumbnail_widget.refresh_current_page()

    call = worker_service.calls[-1]
    assert call["page_num"] == 1
    assert call["image_ids"] == [77]
    assert [item["id"] for item in call["search_result"].image_metadata] == [77]


@pytest.mark.gui
def test_refresh_current_page_shows_added_image_on_displayed_page(
    thumbnail_widget: ThumbnailSelectorWidget,
) -> None:
    """100 件超の一覧で 2 ページ目表示中に追加しても、表示ページに追加画像が載る (Codex P2)。"""
    worker_service = _RecordingWorkerService()
    thumbnail_widget.set_worker_service(worker_service)
    dataset_state = thumbnail_widget.dataset_state
    assert dataset_state is not None
    dataset_state.set_dataset_images(
        [{"id": image_id, "stored_image_path": f"/test/{image_id}.jpg"} for image_id in range(1, 151)]
    )
    assert thumbnail_widget.pagination_state is not None
    thumbnail_widget.pagination_state.set_page(2)

    dataset_state.add_image({"id": 999, "stored_image_path": "/test/crop.jpg"})
    thumbnail_widget.refresh_current_page()

    call = worker_service.calls[-1]
    assert call["page_num"] == 1
    assert call["image_ids"][0] == 999
    assert 999 in {item["id"] for item in call["search_result"].image_metadata}
