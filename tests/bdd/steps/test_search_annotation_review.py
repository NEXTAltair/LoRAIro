"""Real persistence, freshness and Qt rendering with a deterministic Clef transport."""

import json
import sys
from functools import partial
from pathlib import Path

import httpx
import pytest
from PIL import Image as PILImage
from PySide6.QtWidgets import QLabel
from pytest_bdd import given, scenarios, then, when

from lorairo.database.schema import Image, Tag
from lorairo.gui.widgets.annotation_data_display_widget import AnnotationData, AnnotationDataDisplayWidget
from lorairo.gui.widgets.annotation_review_widget import AnnotationReviewWidget
from lorairo.gui.workers.annotation_review_batch_worker import AnnotationReviewBatchWorker
from lorairo.services.annotation_review_service import AnnotationReviewService
from lorairo.services.annotation_review_store import AnnotationReviewStore
from lorairo.services.configuration_service import ConfigurationService

scenarios(str(Path(__file__).parent.parent / "features" / "search_annotation_review.feature"))


@pytest.fixture
def test_db_url(tmp_path):
    """File-backed SQLite shares committed results with the saved-result worker."""
    return f"sqlite:///{tmp_path / 'project.db'}"


@given("タグを持つ2枚の画像がプロジェクトに登録されている", target_fixture="review_context")
def registered_images(test_db_manager, db_session_factory, tmp_path, monkeypatch, local_clef_settings):
    package = (
        Path(__file__).resolve().parents[3] / "local_packages/image-annotator-lib/src/image_annotator_lib"
    )
    monkeypatch.setattr(sys.modules["image_annotator_lib"], "__path__", [str(package)])
    from image_annotator_lib.decisions import LocalDecisionClient

    path = tmp_path / "review.png"
    PILImage.new("RGB", (32, 32), "red").save(path)
    with db_session_factory() as session:
        for image_id in (91, 92):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"search-review-{image_id}",
                    phash=f"search-review-{image_id}",
                    original_image_path=str(path),
                    stored_image_path=str(path),
                    width=32,
                    height=32,
                    format="PNG",
                    extension=".png",
                )
            )
        session.flush()
        session.add_all(
            [Tag(image_id=image_id, tag=tag) for image_id in (91, 92) for tag in ("dog", "portrait")]
        )
        session.commit()
    requests = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        return httpx.Response(
            200,
            json={
                "model": "clef-flash",
                "answers": {
                    key: {"type": "noul", "noul": 0.03 if item["text"] == "dog" else 0.93}
                    for key, item in payload["state"]["annotations"].items()
                },
            },
        )

    config = ConfigurationService(shared_config={"annotation_review": local_clef_settings})
    service = AnnotationReviewService(
        config,
        test_db_manager,
        client_factory=partial(LocalDecisionClient, transport=httpx.MockTransport(transport)),
    )
    return {"db": test_db_manager, "service": service, "requests": requests}


@when("2枚の画像をチェックして画像ごとに保存する")
def run_selected_review(review_context):
    ctx = review_context
    result = AnnotationReviewBatchWorker(
        ctx["service"], AnnotationReviewStore(ctx["db"]), [91, 92], 1
    ).execute()
    assert len(result.reviews) == 2
    assert all(review.status == "completed" for review in result.reviews)
    assert len(ctx["requests"]) == 2


def restore_display(ctx, image_id, qtbot):
    # New store and widgets model restart: only saved-result loading is allowed.
    display = AnnotationDataDisplayWidget()
    review = AnnotationReviewWidget()
    qtbot.addWidget(display)
    qtbot.addWidget(review)
    annotations = ctx["db"].get_image_annotations(image_id)
    display.update_data(AnnotationData(tags=annotations["tags"]), image_id=image_id)
    review.result_displayed.connect(display.set_annotation_review_result)
    review.set_check_controls_visible(False)
    review.set_service(ctx["service"])
    review.set_store(AnnotationReviewStore(ctx["db"]))
    review.set_image(image_id)
    qtbot.waitUntil(lambda: review.current_result is not None, timeout=3000)
    return display, review


@then("新しい詳細表示にも再チェックせず要確認の枠とグループが復元される")
def restored_without_model(review_context, qtbot):
    for image_id in (91, 92):
        display, review = restore_display(review_context, image_id, qtbot)
        try:
            warning = next(chip for chip in display._tag_chips if chip.canonical == "dog")
            normal = next(chip for chip in display._tag_chips if chip.canonical == "portrait")
            assert warning.review_warning and "!" in warning.text()
            assert "判定値 0.030" in warning.toolTip()
            assert not normal.review_warning
            panel = display._tag_panel
            panel._group_by_type_checkbox.setChecked(True)
            assert any(label.text() == "要確認（1件）" for label in panel.findChildren(QLabel))
            assert len(display._tag_chips) == 2
            assert "チェック済み" in review.status_label.text()
            assert "保存済み" in review.model_label.text()
            assert not hasattr(review, "results_table")
            assert len(review_context["requests"]) == 2
        finally:
            review.shutdown()


@when("チェック後に1枚のタグを編集する")
def edit_tag(db_session_factory):
    from sqlalchemy import select

    with db_session_factory() as session:
        row = session.scalars(select(Tag).where(Tag.image_id == 91, Tag.tag == "dog")).one()
        row.tag = "cat"
        session.commit()


@then("編集した画像は古い判定となり要確認グループへ混ざらない")
def edited_result_is_stale(review_context, qtbot):
    display, review = restore_display(review_context, 91, qtbot)
    try:
        assert "古い判定" in review.status_label.text()
        assert all(not chip.review_warning for chip in display._tag_chips)
        display._tag_panel._group_by_type_checkbox.setChecked(True)
        assert not any("要確認" in label.text() for label in display._tag_panel.findChildren(QLabel))
        assert len(review_context["requests"]) == 2
    finally:
        review.shutdown()
