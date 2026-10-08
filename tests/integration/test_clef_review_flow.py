"""Run the real DB, Clef wire transport, persistence and manual repair boundary."""

import json
import sys
from functools import partial
from pathlib import Path

import httpx
import pytest
from PIL import Image as PILImage
from sqlalchemy import select

from lorairo.database.schema import Caption, Image, Tag
from lorairo.gui.services.image_db_write_service import ImageDBWriteService
from lorairo.gui.workers.annotation_review_batch_worker import AnnotationReviewBatchWorker
from lorairo.services.annotation_review_adoption_service import AnnotationReviewAdoptionService
from lorairo.services.annotation_review_service import AnnotationReviewService, ReviewCandidateSource
from lorairo.services.annotation_review_store import AnnotationReviewStore
from lorairo.services.configuration_service import ConfigurationService

pytestmark = pytest.mark.integration


def test_saved_warning_and_proposal_remain_correlated_through_manual_edits(
    test_db_manager, db_session_factory, tmp_path, monkeypatch
):
    package = (
        Path(__file__).resolve().parents[2] / "local_packages/image-annotator-lib/src/image_annotator_lib"
    )
    monkeypatch.setattr(sys.modules["image_annotator_lib"], "__path__", [str(package)])
    from image_annotator_lib.decisions import CloudflareDecisionClient

    path = tmp_path / "portrait.png"
    PILImage.new("RGB", (32, 32), "red").save(path)
    with db_session_factory() as session:
        for image_id in (71, 72):
            session.add(
                Image(
                    id=image_id,
                    uuid=f"clef-flow-{image_id}",
                    phash=f"clef-flow-{image_id}",
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
            [
                Tag(image_id=71, tag="portrait"),
                Tag(image_id=71, tag="dog"),
                Tag(image_id=72, tag="portrait"),
                Tag(image_id=72, tag="Long_Hair"),
            ]
        )
        caption = Caption(image_id=71, caption="A dog in a field.")
        session.add(caption)
        session.commit()
        caption_id = caption.id
    requests = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        answers = {}
        for question_id, annotation in payload["state"]["annotations"].items():
            probability = 0.04 if annotation["kind"] == "caption" or annotation["text"] == "dog" else 0.93
            answers[question_id] = {"type": "noul", "noul": probability}
        return httpx.Response(
            200, json={"success": True, "result": {"model": "clef-flash", "answers": answers}}
        )

    config = ConfigurationService(
        shared_config={"api": {"cloudflare_account_id": "account", "cloudflare_api_token": "fake-token"}}
    )
    service = AnnotationReviewService(
        config,
        test_db_manager,
        client_factory=partial(CloudflareDecisionClient, transport=httpx.MockTransport(transport)),
    )
    store = AnnotationReviewStore(test_db_manager)
    result = AnnotationReviewBatchWorker(
        service,
        store,
        [71],
        1,
        candidate_source=ReviewCandidateSource(selected_tags=("portrait",), limit=1),
    ).execute()
    assert result.reviews[0].status == "completed"
    stored = AnnotationReviewStore(test_db_manager).get_current_result(71, service)
    assert len(requests) == 1
    assert sum(item.status == "warning" for item in stored.review.items) == 2
    proposal = next(item for item in stored.review.items if item.status == "suggestion")
    assert proposal.text == "Long_Hair"
    assert any(item.candidate_id == f"caption_{caption_id}" for item in stored.review.items)
    with db_session_factory() as session:
        assert (
            session.scalars(select(Tag).where(Tag.image_id == 71, Tag.tag == "Long_Hair")).first() is None
        )
    monkeypatch.setattr(
        test_db_manager.annotation_repo,
        "_resolution_for_batch_add",
        lambda session, tag, resolved: (tag, None),
    )
    adoption = AnnotationReviewAdoptionService(test_db_manager, service, store)
    assert adoption.adopt(71, proposal.candidate_id, stored.checked_at)
    assert not adoption.adopt(71, proposal.candidate_id, stored.checked_at)
    stale = store.get_current_result(71, service)
    assert stale.review.status == "stale"
    assert all(item.probability is None for item in stale.review.items)
    assert ImageDBWriteService(test_db_manager).edit_caption(
        71, caption_id, "A person.", expected_text="A dog in a field."
    )
    with db_session_factory() as session:
        captions = session.scalars(select(Caption).where(Caption.image_id == 71)).all()
        assert len(captions) == 1 and captions[0].id == caption_id
        assert captions[0].caption == "A person." and captions[0].is_edited_manually
        manual = session.scalars(select(Tag).where(Tag.image_id == 71, Tag.tag == "Long_Hair")).one()
        assert manual.is_edited_manually and manual.confidence_score is None
        assert session.get(Image, 71).reviewed_at is None
    assert len(requests) == 1
