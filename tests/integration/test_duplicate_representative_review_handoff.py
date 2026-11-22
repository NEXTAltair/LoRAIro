"""重複クラスタの代表 ID を、無加工のまま `review run --image-ids-file` に渡せることを実 DB で確かめる (#1604)。

duplicates 側は実 service + テスト DB、review 側は実 facade と実 Clef 通信層 (HTTP だけ fake)。
代表の結果が他画像へ転記されないこと (タグ・キャプションが不変) も同じ DB で確認する。
"""

import json
import sys
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from PIL import Image as PILImage
from sqlalchemy import select
from typer.testing import CliRunner

from lorairo.cli.commands import duplicates as duplicates_command
from lorairo.cli.main import app
from lorairo.database.schema import Caption, Image, Tag
from lorairo.public_api import review as review_api
from lorairo.services import annotation_review_service
from lorairo.services.annotation_review_service import AnnotationReviewService
from lorairo.services.configuration_service import ConfigurationService
from lorairo.services.duplicate_report_service import DuplicateReportService

pytestmark = pytest.mark.integration
runner = CliRunner()

# id -> (phash, width, height)。1,2,3 と 4,5 が重複クラスタ、6 は単独画像。
IMAGES = {
    1: ("0000000000000000", 20, 20),
    2: ("0000000000000000", 40, 40),  # クラスタ A の代表 (最大)
    3: ("0000000000000000", 40, 40),  # 同点だが id が大きい
    4: ("00000000000000ff", 10, 10),
    5: ("00000000000000ff", 30, 30),  # クラスタ B の代表
    6: ("ffffffffffffffff", 99, 99),  # 単独画像 (面積最大でも代表集合に入れない)
}
EXPECTED_REPRESENTATIVES = [2, 5]


@pytest.fixture
def seeded(test_db_manager, db_session_factory, tmp_path):
    with db_session_factory() as session:
        for image_id, (phash, width, height) in IMAGES.items():
            path = tmp_path / f"{image_id}.png"
            PILImage.new("RGB", (width, height), "red").save(path)
            session.add(
                Image(
                    id=image_id,
                    uuid=f"dup-handoff-{image_id}",
                    phash=phash,
                    original_image_path=str(path),
                    stored_image_path=str(path),
                    width=width,
                    height=height,
                    format="PNG",
                    extension=".png",
                )
            )
        session.flush()
        for image_id in IMAGES:
            session.add(Tag(image_id=image_id, tag=f"tag{image_id}"))
            session.add(Caption(image_id=image_id, caption=f"caption {image_id}"))
        session.commit()
    return db_session_factory


def _annotation_snapshot(factory):
    with factory() as session:
        tags = session.execute(select(Tag.image_id, Tag.tag, Tag.is_edited_manually).order_by(Tag.id)).all()
        captions = session.execute(
            select(Caption.image_id, Caption.caption, Caption.is_edited_manually).order_by(Caption.id)
        ).all()
        images = session.execute(select(Image.id, Image.phash, Image.reviewed_at).order_by(Image.id)).all()
    return [tuple(row) for row in (*tags, *captions, *images)]


@pytest.fixture
def real_duplicates(seeded, monkeypatch):
    """実 service を実 DB に向ける。public_api の project 解決だけ差し替える。"""

    def report(project, *, max_distance, limit):
        return DuplicateReportService(seeded).report(max_distance=max_distance, limit=limit)

    monkeypatch.setattr(duplicates_command, "report_duplicates", Mock(side_effect=report))


@pytest.fixture
def real_review(seeded, test_db_manager, monkeypatch, local_clef_settings):
    """review run の実 facade と実 Clef 通信層を使い、HTTP 応答だけを fake にする。"""
    package = (
        Path(__file__).resolve().parents[2] / "local_packages/image-annotator-lib/src/image_annotator_lib"
    )
    monkeypatch.setattr(sys.modules["image_annotator_lib"], "__path__", [str(package)])
    from image_annotator_lib.decisions import LocalDecisionClient

    requests: list[dict] = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        answers = {
            question_id: {"type": "noul", "noul": 0.93} for question_id in payload["state"]["annotations"]
        }
        return httpx.Response(200, json={"model": "clef-flash", "answers": answers})

    config = ConfigurationService(shared_config={"annotation_review": local_clef_settings})
    container = SimpleNamespace(db_manager=test_db_manager, config_service=config)

    @contextmanager
    def context(project_name):
        yield container

    monkeypatch.setattr(review_api, "_project_context", context)
    monkeypatch.setattr(
        annotation_review_service,
        "AnnotationReviewService",
        partial(
            AnnotationReviewService,
            client_factory=partial(LocalDecisionClient, transport=httpx.MockTransport(transport)),
        ),
    )
    return requests


def _review(ids_file):
    return runner.invoke(
        app, ["--json", "review", "run", "--project", "p", "--image-ids-file", str(ids_file)]
    )


def _rows(result):
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_plain_representative_stdout_is_accepted_unmodified_by_review_run(
    real_duplicates, real_review, seeded, tmp_path
):
    before = _annotation_snapshot(seeded)
    listing = runner.invoke(
        app, ["images", "duplicates", "-p", "p", "--max-distance", "0", "--representatives"]
    )
    assert listing.exit_code == 0, listing.output
    assert listing.stdout.splitlines() == [str(i) for i in EXPECTED_REPRESENTATIVES]
    ids_file = tmp_path / "representatives.txt"
    ids_file.write_text(listing.stdout, encoding="utf-8")  # 加工せず保存

    result = _review(ids_file)

    assert result.exit_code == 0, result.output
    rows = _rows(result)
    outcomes = [row for row in rows if row.get("type") == "annotation_review_outcome"]
    assert [row["image_id"] for row in outcomes] == EXPECTED_REPRESENTATIVES
    assert all(row["status"] == "completed" for row in outcomes)
    assert rows[-1]["kind"] == "result" and rows[-1]["image_count"] == len(EXPECTED_REPRESENTATIVES)
    # 代表だけが Clef に送られ、同クラスタの他画像・単独画像は送られない
    assert len(real_review) == len(EXPECTED_REPRESENTATIVES)
    # 他画像への転記・自動変更なし (タグ・キャプション・画像行が不変)
    assert _annotation_snapshot(seeded) == before


def test_json_representative_rows_can_be_converted_to_an_id_file_for_review(
    real_duplicates, real_review, tmp_path
):
    listing = runner.invoke(
        app, ["--json", "images", "duplicates", "-p", "p", "--max-distance", "0", "--representatives"]
    )
    assert listing.exit_code == 0, listing.output
    ids = [row["image_id"] for row in _rows(listing) if row["kind"] == "item"]
    assert ids == EXPECTED_REPRESENTATIVES
    ids_file = tmp_path / "ids.txt"
    ids_file.write_text("\n".join(map(str, ids)), encoding="utf-8")
    assert [
        r["image_id"] for r in _rows(_review(ids_file)) if r.get("type") == "annotation_review_outcome"
    ] == ids


def test_stdout_and_stderr_are_separated(real_duplicates):
    result = runner.invoke(
        app, ["images", "duplicates", "-p", "p", "--max-distance", "0", "--representatives"]
    )
    assert all(line.isdigit() for line in result.stdout.splitlines())
    assert "reference only" in result.stderr.lower()
    assert "reference only" not in result.stdout.lower()


def test_no_duplicate_cluster_gives_an_empty_id_file_that_review_rejects_before_any_request(
    seeded, real_review, tmp_path, monkeypatch
):
    with seeded() as session:
        for image in session.scalars(select(Image)).all():
            image.phash = f"{image.id:016x}"  # 全画像の hash を相異にする = 重複クラスタなし
        session.commit()
    monkeypatch.setattr(
        duplicates_command,
        "report_duplicates",
        lambda project, *, max_distance, limit: DuplicateReportService(seeded).report(
            max_distance=max_distance, limit=limit
        ),
    )
    listing = runner.invoke(
        app, ["images", "duplicates", "-p", "p", "--max-distance", "0", "--representatives"]
    )
    assert listing.exit_code == 0 and listing.stdout == ""
    ids_file = tmp_path / "empty.txt"
    ids_file.write_text(listing.stdout, encoding="utf-8")
    result = _review(ids_file)
    assert result.exit_code == 2, result.output
    assert _rows(result)[-1]["code"] == "INVALID_INPUT"
    assert real_review == []


def test_more_than_500_representatives_are_rejected_by_review_and_split_files_pass(
    real_review, tmp_path, monkeypatch, seeded
):
    shared = tmp_path / "bulk.png"
    PILImage.new("RGB", (8, 8), "blue").save(shared)
    with seeded() as session:
        for pair in range(1, 502):
            for offset in (1, 2):
                image_id = 1000 + 2 * pair + offset
                session.add(
                    Image(
                        id=image_id,
                        uuid=f"bulk-{image_id}",
                        phash=f"aa{pair:014x}",
                        original_image_path=str(shared),
                        stored_image_path=str(shared),
                        width=10 + offset,
                        height=10,
                        format="PNG",
                        extension=".png",
                    )
                )
        session.flush()
        for image_id in session.scalars(select(Image.id).where(Image.id > 1000)).all():
            session.add(Tag(image_id=image_id, tag="bulk"))
        session.commit()
    monkeypatch.setattr(
        duplicates_command,
        "report_duplicates",
        lambda project, *, max_distance, limit: DuplicateReportService(seeded).report(
            max_distance=max_distance, limit=limit
        ),
    )
    listing = runner.invoke(
        app, ["images", "duplicates", "-p", "p", "--max-distance", "0", "--representatives"]
    )
    assert listing.exit_code == 0, listing.output
    lines = listing.stdout.splitlines()
    assert len(lines) == 501 + len(EXPECTED_REPRESENTATIVES)
    assert "split" in listing.stderr
    ids_file = tmp_path / "all.txt"
    ids_file.write_text(listing.stdout, encoding="utf-8")

    rejected = _review(ids_file)

    assert rejected.exit_code == 2, rejected.output
    error = _rows(rejected)[-1]
    assert error["code"] == "RESULT_SET_TOO_LARGE"
    assert error["details"] == {"limit": 500, "matched": len(lines)}
    assert real_review == []  # 1 件も送られない
    # 500 件ずつに分割したファイルは review run が受け付ける (件数上限だけが理由で拒否された)
    first = tmp_path / "part1.txt"
    first.write_text("\n".join(lines[:500]), encoding="utf-8")
    accepted = _review(first)
    assert accepted.exit_code == 0, accepted.output
    assert _rows(accepted)[-1]["image_count"] == 500
    assert len(real_review) == 500
    second = tmp_path / "part2.txt"
    second.write_text("\n".join(lines[500:]), encoding="utf-8")
    assert _review(second).exit_code == 0
    assert len(real_review) == len(lines)
