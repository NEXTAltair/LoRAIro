"""images rate コマンドおよび update_manual_rating_batch のユニットテスト (Issue #1504)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from lorairo.cli._output_mode import set_json_mode
from lorairo.cli.main import app
from lorairo.database.repository.annotation_record import (
    AnnotationRepository,
    ManualRatingBatchResult,
)
from lorairo.database.schema import Base, Image, Model, Rating

runner = CliRunner()


def _jsonl(stdout: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip().startswith("{")]


@pytest.fixture(autouse=True)
def _reset_json_mode() -> None:
    set_json_mode(False)
    yield
    set_json_mode(False)


@pytest.fixture
def mock_rate_context(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    container = MagicMock()
    container.db_manager.image_repo.get_images_by_filter.side_effect = lambda criteria: (
        [{"id": i} for i in (criteria.image_ids or [])],
        len(criteria.image_ids or []),
    )
    container.db_manager.annotation_repo.update_manual_rating_batch.side_effect = (
        lambda image_ids, rating, *, dry_run=False: ManualRatingBatchResult(
            target_count=len(image_ids),
            updated_count=len(image_ids),
            unchanged_count=0,
            cleared_count=len(image_ids) if rating is None else 0,
            dry_run=dry_run,
            rating=rating,
            per_image_status=dict.fromkeys(image_ids, "cleared" if rating is None else "updated"),
        )
    )
    monkeypatch.setattr("lorairo.cli.commands.images.api_get_project", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        "lorairo.cli.commands.images.get_service_container",
        MagicMock(return_value=container),
    )
    return container


@pytest.mark.unit
class TestImagesRateCommand:
    @pytest.mark.parametrize(
        "input_rating,expected_rating",
        [
            ("PG", "PG"),
            ("pg-13", "PG-13"),
            ("r", "R"),
            ("x", "X"),
            ("xxx", "XXX"),
            ("none", None),
            ("NONE", None),
        ],
    )
    def test_rate_canonicalizes_rating_and_defaults_to_dry_run(
        self,
        mock_rate_context: MagicMock,
        input_rating: str,
        expected_rating: str | None,
    ) -> None:
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "rate",
                "--project",
                "proj",
                "--rating",
                input_rating,
                "--image-ids",
                "1,2",
            ],
        )
        assert result.exit_code == 0, result.output
        rows = _jsonl(result.stdout)
        items = [r for r in rows if r.get("kind") == "item"]
        summary = next(r for r in rows if r.get("kind") == "result")

        assert len(items) == 2
        assert [i["image_id"] for i in items] == [1, 2]
        assert all(i["status"] == "dry_run" for i in items)
        assert all(i["rating"] == expected_rating for i in items)

        assert summary["ok"] is True
        assert summary["status"] == "success"
        assert summary["dry_run"] is True
        assert summary["rating"] == expected_rating
        assert summary["target_count"] == 2
        assert summary["target_images"] == 2
        assert summary["updated_count"] == 2
        assert summary["unchanged_count"] == 0
        assert summary["failed_chunks"] == 0

        mock_rate_context.db_manager.annotation_repo.update_manual_rating_batch.assert_called_once_with(
            [1, 2],
            expected_rating,
            dry_run=True,
        )

    def test_rate_apply_writes_and_emits_updated_status(self, mock_rate_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "rate",
                "--project",
                "proj",
                "--rating",
                "R",
                "--image-ids",
                "10,20",
                "--apply",
            ],
        )
        assert result.exit_code == 0, result.output
        rows = _jsonl(result.stdout)
        items = [r for r in rows if r.get("kind") == "item"]
        summary = next(r for r in rows if r.get("kind") == "result")

        assert [i["status"] for i in items] == ["updated", "updated"]
        assert summary["dry_run"] is False
        assert summary["rating"] == "R"
        assert summary["updated_count"] == 2
        mock_rate_context.db_manager.annotation_repo.update_manual_rating_batch.assert_called_once_with(
            [10, 20],
            "R",
            dry_run=False,
        )

    def test_rate_invalid_rating_returns_exit2(self, mock_rate_context: MagicMock) -> None:
        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "rate",
                "--project",
                "proj",
                "--rating",
                "INVALID",
                "--image-ids",
                "1",
            ],
        )
        assert result.exit_code == 2
        rows = _jsonl(result.stdout)
        assert rows[-1]["kind"] == "error"
        assert rows[-1]["code"] == "INVALID_INPUT"
        mock_rate_context.db_manager.annotation_repo.update_manual_rating_batch.assert_not_called()

    def test_rate_bulk_file_chunks_and_partial_failure_returns_exit3(
        self,
        mock_rate_context: MagicMock,
        tmp_path: Path,
    ) -> None:
        ids_file = tmp_path / "ids.txt"
        ids_file.write_text("\n".join(str(i) for i in range(1, 601)), encoding="utf-8")

        call_count = 0

        def side_effect(
            image_ids: list[int], rating: str | None, *, dry_run: bool = False
        ) -> ManualRatingBatchResult:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("chunk 2 db failure")
            return ManualRatingBatchResult(
                target_count=len(image_ids),
                updated_count=len(image_ids),
                unchanged_count=0,
                cleared_count=0,
                dry_run=dry_run,
                rating=rating,
                per_image_status=dict.fromkeys(image_ids, "updated"),
            )

        mock_rate_context.db_manager.annotation_repo.update_manual_rating_batch.side_effect = side_effect

        result = runner.invoke(
            app,
            [
                "--json",
                "images",
                "rate",
                "--project",
                "proj",
                "--rating",
                "PG",
                "--image-ids-file",
                str(ids_file),
                "--apply",
            ],
        )
        assert result.exit_code == 3, result.output
        rows = _jsonl(result.stdout)
        items = [r for r in rows if r.get("kind") == "item"]
        summary = next(r for r in rows if r.get("kind") == "result")

        assert len(items) == 2
        assert items[0]["status"] == "updated"
        assert items[0]["chunk_images"] == 500
        assert items[1]["status"] == "failed"
        assert summary["ok"] is False
        assert summary["status"] == "partial_success"
        assert summary["target_count"] == 600
        assert summary["updated_count"] == 500
        assert summary["failed_chunks"] == 1


@pytest.mark.unit
class TestUpdateManualRatingBatchRepository:
    def test_update_manual_rating_batch_scopes_to_manual_edit_and_preserves_ai_ratings(
        self,
    ) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)

        with session_factory() as session:
            ai_model = Model(
                name="omni-moderation",
                provider="openai",
                litellm_model_id="openai/omni-moderation-latest",
            )
            session.add(ai_model)
            for idx in (1, 2, 3):
                session.add(
                    Image(
                        id=idx,
                        uuid=f"uuid-{idx}",
                        phash=f"{idx:016x}",
                        original_image_path=f"/src/{idx}.jpg",
                        stored_image_path=f"image_dataset/original_images/{idx}.jpg",
                        width=512,
                        height=512,
                        format="JPEG",
                        mode="RGB",
                        has_alpha=False,
                        filename=f"{idx}",
                        extension="jpg",
                    )
                )
            session.flush()
            session.add(
                Rating(
                    image_id=1,
                    model_id=ai_model.id,
                    raw_rating_value="PG",
                    normalized_rating="PG",
                    confidence_score=0.95,
                )
            )
            session.commit()
            ai_model_id = ai_model.id

        repo = AnnotationRepository(session_factory)

        # 1. Dry-run before MANUAL_EDIT model exists: no DB writes, accurate preview
        preview = repo.update_manual_rating_batch([1, 2], "R", dry_run=True)
        assert preview.target_count == 2
        assert preview.updated_count == 2
        assert preview.unchanged_count == 0
        assert preview.dry_run is True

        # 2. Apply manual rating R to images 1 and 2
        applied = repo.update_manual_rating_batch([1, 2], "R", dry_run=False)
        assert applied.updated_count == 2
        assert applied.unchanged_count == 0
        assert applied.rating == "R"

        # 3. Re-applying same rating is idempotent (unchanged_count == 2)
        reapplied = repo.update_manual_rating_batch([1, 2], "r", dry_run=False)
        assert reapplied.updated_count == 0
        assert reapplied.unchanged_count == 2

        # 4. AI rating row on image 1 is untouched
        with session_factory() as session:
            ai_rows = session.execute(select(Rating).where(Rating.model_id == ai_model_id)).scalars().all()
            assert len(ai_rows) == 1
            assert ai_rows[0].image_id == 1
            assert ai_rows[0].normalized_rating == "PG"

        # 5. Clear manual rating on images 1, 2, 3 (image 3 had none -> unchanged)
        cleared = repo.update_manual_rating_batch([1, 2, 3], None, dry_run=False)
        assert cleared.target_count == 3
        assert cleared.updated_count == 2
        assert cleared.cleared_count == 2
        assert cleared.unchanged_count == 1

        # Verify AI rating on image 1 still exists and manual ratings are gone
        with session_factory() as session:
            all_ratings = session.execute(select(Rating)).scalars().all()
            assert len(all_ratings) == 1
            assert all_ratings[0].model_id == ai_model_id
            assert all_ratings[0].normalized_rating == "PG"
