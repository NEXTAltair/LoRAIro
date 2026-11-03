"""Tag evaluation uses fixed vectors and a temporary DB; no image is decoded or displayed."""

import datetime
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts" / "evaluate_embeddinggemma_tags.py"
SPEC = importlib.util.spec_from_file_location("embeddinggemma_tag_evaluation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
evaluation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = evaluation
SPEC.loader.exec_module(evaluation)


def tag(value, *, manual=False, rejected=False, reason=None, existing=False):
    return {
        "tag": value,
        "is_edited_manually": manual,
        "existing": existing,
        "rejected_at": "2026-01-01" if rejected else None,
        "reject_reason": reason,
    }


def example(image_id=1, positives=None, manual=None, rejected=None, reviewed=False):
    return evaluation.Example(
        image_id, "never-open-this.bin", positives or ["black_hair"], manual or [], reviewed, rejected or []
    )


def test_deduplicates_sources_and_excludes_rejected_caption_moves_and_conflicts():
    labels = [
        tag("black hair"),
        tag("black_hair", manual=True),
        tag("black_hair", rejected=True, reason="incorrect"),
        tag("blue_hair", rejected=True, reason="incorrect"),
        tag("a descriptive sentence", rejected=True, reason="incorrect"),
        tag("artist", rejected=True, reason="not_needed"),
        tag("old_tag", rejected=True, reason="replaced"),
    ]
    positives, manual, rejected = evaluation.select_labels(labels, {"a descriptive sentence"}, "all", False)
    assert positives == ["black_hair"]
    assert manual == ["black_hair"]
    assert rejected == ["blue_hair"]


@pytest.mark.parametrize(
    ("mode", "reviewed", "expected"),
    [
        ("manual", False, ["blue_eyes"]),
        ("existing", False, ["black_hair"]),
        ("reviewed", False, []),
        ("reviewed", True, ["black_hair", "blue_eyes", "standing"]),
    ],
)
def test_reference_provenance(mode, reviewed, expected):
    positives, _, _ = evaluation.select_labels(
        [tag("black_hair", existing=True), tag("blue_eyes", manual=True), tag("standing")],
        set(),
        mode,
        reviewed,
    )
    assert positives == expected


def test_unknown_and_out_of_vocabulary_labels_are_not_silently_counted_as_false():
    metrics = evaluation.rank_metrics(["black_hair", "unavailable_tag"], ["unknown", "black_hair"], [1, 5])
    assert metrics["observed_recall@1"] == 0
    assert metrics["observed_recall@5"] == 0.5
    assert metrics["observed_agreement@5"] == 0.5  # Actual returned length, not k.


def test_rejected_pair_ties_get_half_credit_and_no_pairs_is_distinct():
    metrics = evaluation.rejected_pair_metrics(
        ["yes"], ["no", "maybe"], {"yes": 0.5, "no": 0.1, "maybe": 0.5}
    )
    assert metrics["pairs"] == 2 and metrics["wins"] == 1.5
    assert evaluation.rejected_pair_metrics(["yes"], [], {"yes": 0.5})["mean_margin"] is None


def test_frequency_baseline_leaves_out_current_image():
    matrix = evaluation.frequency_baseline([example(1, ["a"]), example(2, ["a", "b"])], ["a", "b", "c"])
    np.testing.assert_array_equal(matrix, [[1, 1, 0], [1, 0, 0]])


def test_stratifies_reference_ranking_and_skips_ambiguous_attribute_groups():
    examples = [
        example(1, ["black_hair"], manual=["black_hair"], rejected=["blue_hair"], reviewed=True),
        example(2, ["black_hair", "blue_hair", "outside_vocabulary"]),
    ]
    summary, rankings, groups, tags = evaluation.evaluate_scores(
        examples,
        ["black_hair", "blue_hair", "unknown"],
        np.array([[0.8, 0.2, 0.9], [0.7, 0.8, 0.1]]),
        [1, 2],
        "test",
    )
    assert summary["micro_observed_recall@2"] == 3 / 4
    assert summary["candidate_reference_coverage"] == 3 / 4
    assert summary["reviewed_images"]["macro_observed_recall@1"] == 0
    assert summary["manual_tags"]["micro_observed_recall@2"] == 1
    assert summary["accepted_vs_rejected_win_rate"] == 1
    assert len(groups) == 1 and groups[0]["reference_tag"] == "black_hair"
    assert rankings[0]["tag"] == "unknown" and not rankings[0]["in_reference"]
    assert tags[-1]["rank"] is None


@pytest.mark.parametrize("positives", [["black_hair", "blue_hair"], ["blue_hair"]])
def test_group_reference_is_not_changed_by_candidate_vocabulary(positives):
    _, _, groups, _ = evaluation.evaluate_scores(
        [example(positives=positives)],
        ["black_hair", "brown_hair"],
        np.array([[0.8, 0.2]]),
        [1],
        "test",
    )
    assert not groups


def test_prepare_only_refuses_previous_results_without_overwriting(tmp_path, monkeypatch):
    old_files = ["manifest.json", "summary.json", "rankings.csv", "report.md", "embeddings.npz"]
    for name in old_files:
        (tmp_path / name).write_bytes(b"previous results")
    monkeypatch.setattr(
        evaluation, "prepare", lambda _: pytest.fail("Must reject the output before reading a DB")
    )
    args = evaluation.parser().parse_args(
        [
            "--db",
            "unused.db",
            "--output-dir",
            str(tmp_path),
            "--prepare-only",
        ]
    )
    with pytest.raises(ValueError, match="must be empty"):
        evaluation.run(args)
    assert all((tmp_path / name).read_bytes() == b"previous results" for name in old_files)


@pytest.mark.parametrize("matrix", [np.array([[float("nan")]]), np.zeros((2, 1))])
def test_rejects_bad_model_scores(matrix):
    with pytest.raises(ValueError, match=r"wrong shape|non-finite"):
        evaluation.evaluate_scores([example()], ["black_hair"], matrix, [1], "test")


def test_truncation_renormalizes_and_rejects_zero_vectors():
    np.testing.assert_allclose(evaluation.normalized_prefix(np.array([[3, 4, 100]]), 2), [[0.6, 0.8]])
    with pytest.raises(ValueError, match="zero embedding"):
        evaluation.normalized_prefix(np.zeros((1, 3)), 2)


def test_custom_descriptions_require_same_candidate_universe():
    with pytest.raises(ValueError, match="missing"):
        evaluation.tag_texts(["black_hair", "blue_hair"], "custom", {"black_hair": "黒髪"})
    assert evaluation.tag_texts(["black_hair"], "custom", {"black_hair": "黒髪"}) == ["黒髪"]
    assert evaluation.tag_texts(["1girl"], "natural", {}) == ["An image containing one female person."]


def test_resolves_legacy_project_path_without_decoding_file(tmp_path):
    stored = tmp_path / "image_dataset" / "original_images" / "example.bin"
    stored.parent.mkdir(parents=True)
    stored.write_text("not an image", encoding="utf-8")
    db = tmp_path / "image_database.db"
    assert (
        evaluation.resolve_image_path(
            db, f"lorairo_data/{tmp_path.name}/image_dataset/original_images/example.bin", ""
        )
        == stored
    )
    assert evaluation.resolve_image_path(db, "image_dataset\\original_images\\example.bin", "") == stored
    assert evaluation.resolve_image_path(db, "missing.bin", "") is None


def test_prepare_only_uses_enforced_read_only_factory_and_does_not_decode(tmp_path, monkeypatch):
    from lorairo.database import db_core
    from lorairo.database.schema import Caption, Image, Tag

    db = tmp_path / "image_database.db"
    image = tmp_path / "image.bin"
    image.write_text("invalid image bytes are intentional", encoding="utf-8")
    factory = db_core.create_project_session_factory(db)
    with factory() as session:
        session.add(
            Image(
                id=1,
                uuid="fixture-1",
                phash="fixture",
                stored_image_path="image.bin",
                original_image_path="",
                width=1,
                height=1,
                format="BIN",
                extension="bin",
            )
        )
        session.flush()
        session.add_all(
            [
                Tag(image_id=1, tag="black hair", existing=True, is_edited_manually=True),
                Tag(image_id=1, tag="black_hair", existing=False),
                Tag(
                    image_id=1,
                    tag="blue_hair",
                    existing=False,
                    rejected_at=datetime.datetime(2026, 1, 1),
                    reject_reason="incorrect",
                ),
                Tag(
                    image_id=1,
                    tag="caption text",
                    existing=False,
                    rejected_at=datetime.datetime(2026, 1, 1),
                    reject_reason="incorrect",
                ),
                Caption(image_id=1, caption="caption text", existing=True),
            ]
        )
        session.commit()
    factory.kw["bind"].dispose()
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    original_factory = db_core.create_project_session_factory

    def read_only_factory(path, *, read_only=False):
        assert read_only, "Evaluation must never use the migrating/writing factory"
        return original_factory(path, read_only=read_only)

    monkeypatch.setattr(db_core, "create_project_session_factory", read_only_factory)
    monkeypatch.setattr(
        evaluation, "load_model", lambda _: pytest.fail("prepare must not load an image model")
    )
    output = tmp_path / "result"
    args = evaluation.parser().parse_args(["--db", str(db), "--output-dir", str(output), "--prepare-only"])
    evaluation.run(args)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["examples"][0]["reference_tags"] == ["black_hair"]
    assert manifest["examples"][0]["rejected_tags"] == ["blue_hair"]
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert not (output / "summary.json").exists()


def test_explicit_candidate_vocabulary_keeps_missing_label_coverage_visible(tmp_path):
    candidates = tmp_path / "tags.json"
    candidates.write_text('["blue hair", "blue_hair", "standing"]', encoding="utf-8")
    assert evaluation.build_vocabulary([example()], candidates, ["standing"]) == ["blue_hair"]


def test_missing_db_is_reported_without_creating_it(tmp_path):
    path = tmp_path / "missing.db"
    with pytest.raises(RuntimeError, match="missing_database"):
        evaluation.load_database(path, 1, 42, "all")
    assert not path.exists()


def test_excluded_only_images_are_replaced_before_sample_limit(tmp_path):
    from lorairo.database import db_core
    from lorairo.database.schema import Image, Tag

    db = tmp_path / "image_database.db"
    factory = db_core.create_project_session_factory(db)
    with factory() as session:
        for image_id, label in [(1, "trigger"), (2, "black_hair")]:
            image_path = tmp_path / f"{image_id}.bin"
            image_path.write_text("not an image", encoding="utf-8")
            session.add(
                Image(
                    id=image_id,
                    uuid=f"fixture-{image_id}",
                    phash=str(image_id),
                    stored_image_path=image_path.name,
                    original_image_path="",
                    width=1,
                    height=1,
                    format="BIN",
                    extension="bin",
                )
            )
            session.flush()
            session.add(Tag(image_id=image_id, tag=label, existing=True))
        session.commit()
    factory.kw["bind"].dispose()
    # Seed 0 visits ID 1 first, then ID 2. The limit must apply after label exclusions.
    examples, sampling = evaluation.load_database(db, 1, 0, "all", {"trigger"})
    assert [item.image_id for item in examples] == [2]
    assert examples[0].reference_tags == ["black_hair"]
    assert sampling["skipped"]["no_reference_tags"] == 1


def test_full_run_passes_only_paths_to_image_model_and_writes_numeric_reports(tmp_path, monkeypatch):
    sample = example()
    vocabulary = ["black_hair", "blue_hair"]
    manifest = {"schema_version": 1, "reference": "all", "seed": 42}
    monkeypatch.setattr(evaluation, "prepare", lambda _: ([sample], vocabulary, manifest))

    class FixedModel:
        def encode(self, inputs, **kwargs):
            vectors = np.zeros((len(inputs), 768), dtype=np.float32)
            if isinstance(inputs[0], dict):
                assert inputs == [{"image": "never-open-this.bin"}]
                assert kwargs["prompt"] == ""
                vectors[:, 0] = 1
            else:
                assert inputs == vocabulary
                assert kwargs["prompt"] == evaluation.TASK_PREFIX
                vectors[0, 0] = vectors[1, 1] = 1
            return vectors

    monkeypatch.setattr(evaluation, "load_model", lambda _: (FixedModel(), {"model": "fixed-vectors"}))
    args = evaluation.parser().parse_args(
        [
            "--manifest",
            "ignored.json",
            "--output-dir",
            str(tmp_path),
            "--prompts",
            "raw",
            "--dimensions",
            "256",
            "--top-k",
            "1",
        ]
    )
    evaluation.run(args)
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["metrics"]["raw_256d"]["macro_observed_recall@1"] == 1
    assert summary["metrics"]["raw_256d"]["accepted_vs_rejected_win_rate"] is None
    assert (tmp_path / "report.md").is_file()
    assert {path.suffix for path in tmp_path.iterdir()} <= {".json", ".csv", ".npz", ".md"}
    with np.load(tmp_path / "embeddings.npz", allow_pickle=False) as archive:
        assert archive["image_embeddings"].shape == (1, 768)
