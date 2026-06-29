"""エクスポート前タグ編集パネルの BDD ステップ定義 (#949)。

ExportTabWidget のウィジェット間配線 (絞り込み / overlay / DB reject / スコープ) を、
実 DB / 実ファイル I/O を避けた決定的な Mock 構成でユーザーフローとして検証する。
"""

from pathlib import Path
from typing import Any
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.gui.state.staging_state import StagingStateManager
from lorairo.gui.tab.export_tab import ExportTabWidget

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "export_tag_edit_panel.feature"
scenarios(str(_FEATURE_FILE))


@given(
    parsers.parse("ステージング集合に画像が{count:d}枚あるエクスポートタブ"),
    target_fixture="ctx",
)
def given_export_tab_with_staged(qtbot, count: int) -> dict[str, Any]:
    service_container = Mock()
    service_container.dataset_export_service = Mock()
    service_container.db_manager.annotation_repo.get_merged_reader.return_value = None

    staging = StagingStateManager()
    dataset_state = Mock()
    dataset_state.get_image_by_id.side_effect = lambda image_id: {
        "stored_image_path": f"/images/{image_id}.png"
    }
    staging.set_dataset_state_manager(dataset_state)

    db_manager = Mock()
    db_manager.get_image_metadata.side_effect = lambda image_id: {
        "id": image_id,
        "stored_image_path": f"/img/{image_id}.png",
    }
    db_manager.get_rejected_tags.return_value = []
    db_manager.soft_reject_tag_batch.return_value = count

    tab = ExportTabWidget(
        service_container=service_container,
        db_manager=db_manager,
        staging_state_manager=staging,
    )
    qtbot.addWidget(tab)
    # 実 DB / 実ファイル I/O を避けるためスタブ化 (配線のみ検証)。
    tab._staging_tag_panel.load_tags = Mock()
    tab._thumbnail_selector.load_thumbnails_from_paths = Mock()
    tab._aggregation_service = Mock()

    staged_ids = list(range(1, count + 1))
    staging.add_image_ids(staged_ids)
    return {"tab": tab, "db_manager": db_manager, "staged_ids": staged_ids}


@given(parsers.parse('タグ "{tag}" を持つ画像が {n:d} 枚ある'))
def given_tag_present_in_n_images(ctx: dict[str, Any], tag: str, n: int) -> None:
    ctx["tab"]._aggregation_service.images_with_tag.return_value = ctx["staged_ids"][:n]


@when(parsers.parse('タグ "{tag}" で絞り込む'))
def when_filter_by_tag(ctx: dict[str, Any], tag: str) -> None:
    ctx["tab"]._staging_tag_panel.filter_tag_changed.emit(tag)


@when("スコープを絞り込み結果に設定する")
def when_set_scope_filtered(ctx: dict[str, Any]) -> None:
    ctx["tab"]._overlay_bar.scope_changed.emit("filtered")


@when(parsers.parse('タグ "{tag}" を出力除外する'))
def when_overlay_exclude(ctx: dict[str, Any], tag: str) -> None:
    ctx["tab"]._staging_tag_panel.overlay_exclude_requested.emit(tag)


@when(parsers.parse('タグ "{tag}" を全画像で DB reject する'))
def when_db_reject_everywhere(ctx: dict[str, Any], tag: str, monkeypatch) -> None:
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    ctx["tab"]._staging_tag_panel.db_reject_everywhere_requested.emit(tag)


@then(parsers.parse("エクスポート対象は全 staged の{n:d}枚のままになる"))
def then_export_ids_all_staged(ctx: dict[str, Any], n: int) -> None:
    # scope=filtered は overlay 適用範囲を限定するだけで、エクスポート対象は削らない (Codex P1)。
    assert len(ctx["tab"]._effective_export_ids()) == n


@then(parsers.parse('出力オーバーレイに "{tag}" の除外が含まれる'))
def then_overlay_excludes(ctx: dict[str, Any], tag: str) -> None:
    assert tag in ctx["tab"]._overlay_bar.current_overlay().exclude


@then("全 staged 画像で DB の soft-reject が呼ばれる")
def then_batch_reject_called(ctx: dict[str, Any]) -> None:
    ctx["db_manager"].soft_reject_tag_batch.assert_called_once_with(ctx["staged_ids"], "smile")
