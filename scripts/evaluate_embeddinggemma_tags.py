"""Evaluate image-to-tag ranking against an existing LoRAIro DB without displaying images.

The database is opened with SQLite-enforced read-only access. Images are passed only
to the local embedding model. Reports contain labels, IDs, scores and paths, never pixels.
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import random
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "google/embeddinggemma-2"
TASK_PREFIX = "task: classification | query: "
GROUPS = {
    "female_count": ["1girl", "2girls", "3girls", "4girls"],
    "male_count": ["1boy", "2boys", "3boys"],
    "hair_color": [
        "black_hair",
        "brown_hair",
        "blonde_hair",
        "white_hair",
        "grey_hair",
        "red_hair",
        "blue_hair",
        "green_hair",
        "pink_hair",
        "purple_hair",
    ],
    "eye_color": [
        "black_eyes",
        "brown_eyes",
        "blue_eyes",
        "green_eyes",
        "red_eyes",
        "yellow_eyes",
        "purple_eyes",
        "pink_eyes",
        "grey_eyes",
    ],
    "hair_length": ["short_hair", "medium_hair", "long_hair"],
    "pose": ["standing", "sitting", "lying", "kneeling"],
    "framing": ["portrait", "upper_body", "full_body"],
}
DESCRIPTIONS = {
    "1girl": "one female person",
    "2girls": "two female people",
    "3girls": "three female people",
    "4girls": "four female people",
    "1boy": "one male person",
    "2boys": "two male people",
    "3boys": "three male people",
    "upper_body": "a person shown from the waist up",
    "full_body": "a person's entire body",
    "portrait": "a close-up portrait of a person's face",
}


@dataclass
class Example:
    image_id: int
    image_path: str
    reference_tags: list[str]
    manual_tags: list[str]
    reviewed: bool
    rejected_tags: list[str]


def canonical_tag(tag: str) -> str:
    """Treat DB space/underscore variants alike without changing case or spelling."""
    return "_".join(tag.strip().split())


def resolve_image_path(db: Path, stored: str, original: str) -> Path | None:
    """Resolve legacy project prefixes against this DB, rather than global app state."""
    normalized = stored.replace("\\", "/")
    path = Path(normalized)
    candidates = [path] if path.is_absolute() else [db.parent / path]
    parts = path.parts
    for marker in (db.parent.name, "image_dataset"):
        if marker in parts:
            index = parts.index(marker) + (marker == db.parent.name)
            candidates.append(db.parent.joinpath(*parts[index:]))
    if original:
        original_path = Path(original.replace("\\", "/"))
        candidates.append(original_path if original_path.is_absolute() else db.parent / original_path)
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)


def select_labels(
    tags: list[dict[str, Any]],
    captions: set[str],
    reference: str,
    reviewed: bool,
) -> tuple[list[str], list[str], list[str]]:
    active = [row for row in tags if row["rejected_at"] is None]
    all_active = {canonical_tag(row["tag"]) for row in active}
    manual = {canonical_tag(row["tag"]) for row in active if row["is_edited_manually"]}
    selected = {
        canonical_tag(row["tag"])
        for row in active
        if reference == "all"
        or (reference == "manual" and row["is_edited_manually"])
        or (reference == "existing" and row["existing"])
        or (reference == "reviewed" and reviewed)
    }
    # Caption moves can also use reason='incorrect' (ADR 0087); exclude those strings.
    moved = {canonical_tag(caption) for caption in captions}
    rejected = (
        {
            canonical_tag(row["tag"])
            for row in tags
            if row["rejected_at"] is not None and row["reject_reason"] == "incorrect"
        }
        - all_active
        - moved
    )
    return sorted(selected - {""}), sorted(manual - {""}), sorted(rejected - {""})


def open_database(db: Path) -> Any:
    sys.path.insert(0, str(ROOT / "src"))
    from sqlalchemy.exc import SQLAlchemyError

    from lorairo.database.db_core import create_project_session_factory
    from lorairo.public_api.exceptions import ReadOnlyPreconditionError

    try:
        return create_project_session_factory(db, read_only=True)
    except (ReadOnlyPreconditionError, SQLAlchemyError) as exc:
        raise RuntimeError(str(exc)) from exc


def load_database(
    db: Path,
    limit: int,
    seed: int,
    reference: str,
    excluded_tags: set[str] | None = None,
) -> tuple[list[Example], dict[str, Any]]:
    """Use the existing protected DB factory, with no migrations or app initialization."""
    factory = open_database(db)
    from sqlalchemy import select

    from lorairo.database.schema import Caption, Image, Tag

    engine = factory.kw["bind"]
    examples: list[Example] = []
    skipped = Counter()
    excluded = {canonical_tag(tag) for tag in (excluded_tags or set())}
    try:
        with factory() as session:
            eligible = Tag.rejected_at.is_(None)
            restrictions = {"manual": Tag.is_edited_manually.is_(True), "existing": Tag.existing.is_(True)}
            if reference in restrictions:
                eligible &= restrictions[reference]
            # Materialize eligible IDs once; correlated EXISTS is expensive on large annotation DBs.
            tagged_ids = select(Tag.image_id).where(eligible)
            query = select(Image.id).where(Image.id.in_(tagged_ids)).order_by(Image.id)
            if reference == "reviewed":
                query = query.where(Image.reviewed_at.is_not(None))
            ids = list(session.scalars(query))
            random.Random(seed).shuffle(ids)
            # Fixed order and bounded batches; missing files do not silently shrink the sample.
            for offset in range(0, len(ids), 100):
                batch = ids[offset : offset + 100]
                images = {row.id: row for row in session.scalars(select(Image).where(Image.id.in_(batch)))}
                tag_rows: dict[int, list[dict[str, Any]]] = {image_id: [] for image_id in batch}
                caption_rows: dict[int, set[str]] = {image_id: set() for image_id in batch}
                for row in session.scalars(select(Tag).where(Tag.image_id.in_(batch))):
                    tag_rows[row.image_id].append(
                        {
                            "tag": row.tag,
                            "existing": row.existing,
                            "is_edited_manually": row.is_edited_manually,
                            "rejected_at": row.rejected_at,
                            "reject_reason": row.reject_reason,
                        }
                    )
                for row in session.scalars(
                    select(Caption).where(
                        Caption.image_id.in_(batch),
                        Caption.rejected_at.is_(None),
                    )
                ):
                    caption_rows[row.image_id].add(row.caption)
                for image_id in batch:
                    image = images[image_id]
                    positives, manual, rejected = select_labels(
                        tag_rows[image_id],
                        caption_rows[image_id],
                        reference,
                        image.reviewed_at is not None,
                    )
                    positives = sorted(set(positives) - excluded)
                    manual = sorted(set(manual) - excluded)
                    rejected = sorted(set(rejected) - excluded)
                    if not positives:
                        skipped["no_reference_tags"] += 1
                        continue
                    image_path = resolve_image_path(db, image.stored_image_path, image.original_image_path)
                    if image_path is None:
                        skipped["missing_image_file"] += 1
                        continue
                    examples.append(
                        Example(
                            image_id,
                            str(image_path),
                            positives,
                            manual,
                            image.reviewed_at is not None,
                            rejected,
                        )
                    )
                    if len(examples) == limit:
                        return examples, {"eligible_images": len(ids), "skipped": dict(skipped)}
            return examples, {"eligible_images": len(ids), "skipped": dict(skipped)}
    finally:
        engine.dispose()


def build_vocabulary(
    examples: list[Example], candidate_file: Path | None, excluded: list[str]
) -> list[str]:
    if candidate_file is not None:
        content = candidate_file.read_text(encoding="utf-8-sig")
        values = json.loads(content) if candidate_file.suffix.lower() == ".json" else content.splitlines()
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError("Candidate tags must be a JSON string array or one tag per line.")
        candidates = {canonical_tag(value) for value in values}
    else:
        candidates = {tag for example in examples for tag in example.reference_tags + example.rejected_tags}
        candidates.update(tag for group in GROUPS.values() for tag in group)
    return sorted(candidates - {canonical_tag(tag) for tag in excluded} - {""})


def tag_texts(vocabulary: list[str], mode: str, overrides: dict[str, str]) -> list[str]:
    if mode == "raw":
        return vocabulary.copy()
    descriptions = [DESCRIPTIONS.get(tag, tag.replace("_", " ")) for tag in vocabulary]
    if mode == "custom":
        missing = set(vocabulary) - overrides.keys()
        if missing:
            raise ValueError(
                f"Custom tag text is missing for {len(missing)} candidates; provide every candidate."
            )
        return [overrides[tag] for tag in vocabulary]
    return [f"An image containing {description}." for description in descriptions]


def rank_metrics(reference: list[str], ranking: list[str], ks: list[int]) -> dict[str, Any]:
    positives = set(reference)
    result: dict[str, Any] = {"reference_count": len(positives)}
    for k in ks:
        retrieved = ranking[:k]
        hits = len(positives.intersection(retrieved))
        result[f"hits@{k}"] = hits
        result[f"observed_recall@{k}"] = hits / len(positives) if positives else None
        result[f"observed_agreement@{k}"] = hits / len(retrieved) if retrieved else None
    return result


def rejected_pair_metrics(
    positives: list[str],
    rejected: list[str],
    scores: dict[str, float],
) -> dict[str, Any]:
    margins = [
        scores[positive] - scores[negative]
        for positive in positives
        for negative in rejected
        if positive in scores and negative in scores and positive != negative
    ]
    return {
        "pairs": len(margins),
        "wins": sum(1.0 if margin > 0 else 0.5 if margin == 0 else 0.0 for margin in margins),
        "mean_margin": sum(margins) / len(margins) if margins else None,
    }


def summarize(rows: list[dict[str, Any]], ks: list[int]) -> dict[str, Any]:
    pairs = sum(row["pairs"] for row in rows)
    summary: dict[str, Any] = {
        "images": len(rows),
        "reference_tags": sum(row["reference_count"] for row in rows),
        "rejected_pairs": pairs,
        "accepted_vs_rejected_win_rate": sum(row["wins"] for row in rows) / pairs if pairs else None,
    }
    for k in ks:
        recalls = [row[f"observed_recall@{k}"] for row in rows if row[f"observed_recall@{k}"] is not None]
        agreements = [
            row[f"observed_agreement@{k}"] for row in rows if row[f"observed_agreement@{k}"] is not None
        ]
        hits = sum(row[f"hits@{k}"] for row in rows)
        summary[f"macro_observed_recall@{k}"] = sum(recalls) / len(recalls) if recalls else None
        count = summary["reference_tags"]
        summary[f"micro_observed_recall@{k}"] = hits / count if count else None
        summary[f"observed_agreement@{k}"] = sum(agreements) / len(agreements) if agreements else None
    return summary


def evaluate_scores(
    examples: list[Example],
    vocabulary: list[str],
    matrix: Any,
    ks: list[int],
    run: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Pure label evaluation. Stable tag order breaks ranking ties; pair ties receive half credit."""
    import numpy as np

    if matrix.shape != (len(examples), len(vocabulary)) or not np.isfinite(matrix).all():
        raise ValueError("Scores have the wrong shape or contain non-finite values.")
    rows, rankings, contrasts, tag_rows = [], [], [], []
    groups = {name: [tag for tag in group if tag in vocabulary] for name, group in GROUPS.items()}
    for example, values in zip(examples, matrix, strict=True):
        order = np.argsort(-values, kind="stable")
        ranking = [vocabulary[index] for index in order]
        scores = dict(zip(vocabulary, map(float, values), strict=True))
        metrics = rank_metrics(example.reference_tags, ranking, ks)
        metrics.update(rejected_pair_metrics(example.reference_tags, example.rejected_tags, scores))
        metrics.update({"image_id": example.image_id, "reviewed": example.reviewed})
        metrics["manual_metrics"] = rank_metrics(example.manual_tags, ranking, ks)
        rows.append(metrics)
        positions = {tag: rank for rank, tag in enumerate(ranking, start=1)}
        for tag in example.reference_tags:
            tag_rows.append(
                {
                    "run": run,
                    "image_id": example.image_id,
                    "tag": tag,
                    "rank": positions.get(tag),
                    "score": scores.get(tag),
                }
            )
        for rank, tag in enumerate(ranking[: max(ks)], start=1):
            rankings.append(
                {
                    "run": run,
                    "image_id": example.image_id,
                    "rank": rank,
                    "tag": tag,
                    "score": scores[tag],
                    "in_reference": tag in example.reference_tags,
                    "explicitly_rejected": tag in example.rejected_tags,
                }
            )
        for name, group in groups.items():
            observed = set(GROUPS[name]).intersection(example.reference_tags)
            if len(observed) != 1 or len(group) < 2 or not observed.issubset(scores):
                continue
            expected = next(iter(observed))
            ordered = sorted(group, key=lambda tag: (-scores[tag], tag))
            alternative = max(scores[tag] for tag in group if tag != expected)
            contrasts.append(
                {
                    "run": run,
                    "image_id": example.image_id,
                    "group": name,
                    "reference_tag": expected,
                    "top_tag": ordered[0],
                    "matches_reference": ordered[0] == expected,
                    "reference_margin": scores[expected] - alternative,
                }
            )
    summary = summarize(rows, ks)
    summary["reviewed_images"] = summarize([row for row in rows if row["reviewed"]], ks)
    summary["unreviewed_images"] = summarize([row for row in rows if not row["reviewed"]], ks)
    summary["manual_tags"] = summarize(
        [
            row["manual_metrics"] | {"pairs": 0, "wins": 0}
            for row in rows
            if row["manual_metrics"]["reference_count"]
        ],
        ks,
    )
    summary["candidate_reference_coverage"] = (
        sum(tag in scores for example in examples for tag in example.reference_tags)
        / summary["reference_tags"]
        if summary["reference_tags"]
        else None
    )
    summary["groups"] = {
        name: {
            "images": len(items),
            "reference_match_rate": sum(item["matches_reference"] for item in items) / len(items),
        }
        for name in groups
        if (items := [row for row in contrasts if row["group"] == name])
    }
    return summary, rankings, contrasts, tag_rows


def frequency_baseline(examples: list[Example], vocabulary: list[str]) -> Any:
    """Leave this image's labels out of the frequency count used to rank its candidates."""
    import numpy as np

    counts = Counter(tag for example in examples for tag in example.reference_tags)
    return np.asarray(
        [[counts[tag] - (tag in example.reference_tags) for tag in vocabulary] for example in examples],
        dtype=np.float32,
    )


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    source = result.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", type=Path, help="Existing project image_database.db (read-only).")
    source.add_argument("--manifest", type=Path, help="Reuse a prepared sample and candidate vocabulary.")
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--limit", type=int, default=64, help="Maximum image sample (1-500; default 64).")
    result.add_argument("--seed", type=int, default=42)
    result.add_argument("--reference", choices=["all", "manual", "reviewed", "existing"], default="all")
    result.add_argument("--candidate-tags", type=Path, help="JSON array or one candidate tag per line.")
    result.add_argument(
        "--exclude-tag", action="append", default=[], help="Exclude a trigger/style tag; repeatable."
    )
    result.add_argument(
        "--prepare-only", action="store_true", help="Export metadata without decoding any image."
    )
    result.add_argument("--model", default=MODEL_ID)
    result.add_argument(
        "--revision", help="Hugging Face revision; resolved commit is recorded in the report."
    )
    result.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda"])
    result.add_argument("--batch-size", type=int, default=4)
    result.add_argument("--vision-tokens", type=int, choices=[70, 140, 280, 560, 1120], default=280)
    result.add_argument(
        "--dimensions", type=int, nargs="+", choices=[128, 256, 512, 768], default=[768, 256]
    )
    result.add_argument(
        "--prompts", nargs="+", choices=["raw", "natural", "custom"], default=["raw", "natural"]
    )
    result.add_argument(
        "--tag-texts", type=Path, help="Custom JSON tag -> description map (all candidates required)."
    )
    result.add_argument("--top-k", type=int, nargs="+", default=[5, 10, 20, 50])
    return result


def load_model(args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    from packaging.version import Version

    for package, minimum in (("sentence-transformers", "6.1.0"), ("transformers", "5.19.0")):
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"Install {package}>={minimum}; see docs/embeddinggemma-tag-evaluation.md."
            ) from exc
        if Version(installed) < Version(minimum):
            raise RuntimeError(f"{package}>={minimum} is required (installed: {installed}).")
    import torch
    from huggingface_hub import hf_hub_download
    from sentence_transformers import SentenceTransformer

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable.")
    dtype = torch.bfloat16 if device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32
    started = time.perf_counter()
    if Path(args.model).is_dir():
        resolved_revision = None
    else:
        config_path = hf_hub_download(args.model, "config.json", revision=args.revision)
        resolved_revision = Path(config_path).parent.name
    model = SentenceTransformer(
        args.model,
        revision=resolved_revision,
        device=device,
        trust_remote_code=False,
        config_kwargs={"audio_config": None},
        model_kwargs={"torch_dtype": dtype},
    )
    return model, {
        "model": args.model,
        "requested_revision": args.revision,
        "resolved_revision": resolved_revision,
        "device": device,
        "dtype": str(dtype),
        "model_load_seconds": time.perf_counter() - started,
        "versions": {
            package: importlib.metadata.version(package)
            for package in ("torch", "transformers", "sentence-transformers", "numpy", "Pillow")
        },
    }


def normalized_prefix(embeddings: Any, dimension: int) -> Any:
    import numpy as np

    values = np.asarray(embeddings, dtype=np.float32)
    if values.ndim != 2 or values.shape[1] < dimension or not np.isfinite(values).all():
        raise ValueError("Invalid embedding shape or non-finite embeddings.")
    shortened = values[:, :dimension]
    norms = np.linalg.norm(shortened, axis=1, keepdims=True)
    if (norms == 0).any():
        raise ValueError("Model returned a zero embedding.")
    return shortened / norms


def prepare(args: argparse.Namespace) -> tuple[list[Example], list[str], dict[str, Any]]:
    if args.manifest:
        if args.candidate_tags or args.exclude_tag:
            raise ValueError(
                "A manifest fixes the sample and vocabulary; do not combine it with candidate/exclude options."
            )
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        if manifest.get("schema_version") != 1:
            raise ValueError("Unsupported manifest schema version.")
        examples = [Example(**row) for row in manifest["examples"]]
        return examples, manifest["candidate_tags"], manifest
    excluded = {canonical_tag(tag) for tag in args.exclude_tag}
    examples, sampling = load_database(args.db.resolve(), args.limit, args.seed, args.reference, excluded)
    vocabulary = build_vocabulary(examples, args.candidate_tags, args.exclude_tag)
    manifest = {
        "schema_version": 1,
        "db": str(args.db.resolve()),
        "seed": args.seed,
        "reference": args.reference,
        "sampling": sampling,
        "excluded_tags": sorted(excluded),
        "candidate_tags": vocabulary,
        "examples": [asdict(example) for example in examples],
    }
    return examples, vocabulary, manifest


def validate_sample(examples: list[Example], vocabulary: list[str]) -> None:
    if not examples or not vocabulary:
        raise ValueError(
            "No evaluable images or candidates. Check reference selection, paths and exclusions."
        )
    if len(examples) > 500 or len({example.image_id for example in examples}) != len(examples):
        raise ValueError("Manifest must contain 1-500 unique image IDs.")
    if len(set(vocabulary)) != len(vocabulary) or not all(
        isinstance(tag, str) and tag for tag in vocabulary
    ):
        raise ValueError("Manifest candidates must be unique non-empty strings.")


def load_overrides(path: Path | None) -> dict[str, str]:
    overrides = {}
    if path:
        overrides = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(overrides, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value.strip()
            for key, value in overrides.items()
        ):
            raise ValueError("Custom tag texts must be a JSON object of tag -> non-empty description.")
        overrides = {canonical_tag(key): value for key, value in overrides.items()}
    return overrides


def write_report(path: Path, summary: dict[str, Any], ks: list[int]) -> None:
    lines = [
        "# EmbeddingGemma 2 tag ranking evaluation",
        "",
        f"Images: {summary['images']}; candidates: {summary['candidates']}; reference: {summary['reference']}",
        "",
        "DB-label agreement is measured here. Missing labels are unknown; cosine is not a probability.",
        "",
        "| Run | " + " | ".join(f"Recall@{k}" for k in ks) + " | Accepted/rejected wins |",
        "| --- | " + " | ".join("---:" for _ in ks) + " | ---: |",
    ]
    for name, metrics in summary["metrics"].items():
        values = [f"{metrics[f'macro_observed_recall@{k}']:.1%}" for k in ks]
        wins = metrics["accepted_vs_rejected_win_rate"]
        lines.append(
            f"| {name} | " + " | ".join(values) + f" | {wins:.1%} |"
            if wins is not None
            else f"| {name} | " + " | ".join(values) + " | n/a |"
        )
    lines += [
        "",
        "## Attribute groups",
        "",
        "| Run | Group | Images | Reference match |",
        "| --- | --- | ---: | ---: |",
    ]
    for name, metrics in summary["metrics"].items():
        for group, result in metrics["groups"].items():
            lines.append(
                f"| {name} | {group} | {result['images']} | {result['reference_match_rate']:.1%} |"
            )
    lines += ["", "## Interpretation", ""] + [f"- {item}" for item in summary["interpretation"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    if not 1 <= args.limit <= 500 or args.batch_size < 1 or any(k < 1 for k in args.top_k):
        raise ValueError("limit must be 1-500; batch-size and top-k must be positive.")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError(
            "Output directory must be empty; choose a new directory to preserve previous results."
        )
    examples, vocabulary, manifest = prepare(args)
    validate_sample(examples, vocabulary)
    overrides = load_overrides(args.tag_texts)
    prompt_inputs = {mode: tag_texts(vocabulary, mode, overrides) for mode in dict.fromkeys(args.prompts)}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "manifest.json", manifest)
    print(f"Prepared {len(examples)} images and {len(vocabulary)} candidate tags. No images displayed.")
    if args.prepare_only:
        return
    import numpy as np

    ks = sorted(set(args.top_k))
    summaries, rankings, contrasts, tag_rows = {}, [], [], []

    def record(name: str, matrix: Any) -> None:
        summary, ranked, grouped, per_tag = evaluate_scores(examples, vocabulary, matrix, ks, name)
        summaries[name] = summary
        rankings.extend(ranked)
        contrasts.extend(grouped)
        tag_rows.extend(per_tag)
        print(
            f"{name}: observed recall@{ks[0]}={summary[f'macro_observed_recall@{ks[0]}']:.4f}, "
            f"accepted/rejected win rate={summary['accepted_vs_rejected_win_rate']}"
        )

    record("frequency_leave_one_out", frequency_baseline(examples, vocabulary))
    model, runtime = load_model(args)
    started = time.perf_counter()
    image_vectors = model.encode(
        [{"image": example.image_path} for example in examples],
        batch_size=args.batch_size,
        show_progress_bar=True,
        prompt="",
        normalize_embeddings=True,
        convert_to_numpy=True,
        processing_kwargs={"image": {"max_soft_tokens": args.vision_tokens}},
    )
    runtime["image_encode_seconds"] = time.perf_counter() - started
    artifacts: dict[str, Any] = {
        "image_ids": np.asarray([example.image_id for example in examples]),
        "image_embeddings": image_vectors,
        "candidate_tags": np.asarray(vocabulary),
    }
    prompt_timings = {}
    for mode, texts in prompt_inputs.items():
        started = time.perf_counter()
        text_vectors = model.encode(
            texts,
            prompt=TASK_PREFIX,
            batch_size=max(args.batch_size, 16),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )
        prompt_timings[mode] = time.perf_counter() - started
        artifacts[f"{mode}_texts"] = np.asarray(texts)
        artifacts[f"{mode}_embeddings"] = text_vectors
        for dimension in dict.fromkeys(args.dimensions):
            matrix = (
                normalized_prefix(image_vectors, dimension) @ normalized_prefix(text_vectors, dimension).T
            )
            record(f"{mode}_{dimension}d", matrix)
    np.savez_compressed(args.output_dir / "embeddings.npz", **artifacts)
    summary = {
        "schema_version": 1,
        "images": len(examples),
        "candidates": len(vocabulary),
        "reference": manifest["reference"],
        "seed": manifest["seed"],
        "runtime": runtime,
        "text_encode_seconds": prompt_timings,
        "vision_tokens": args.vision_tokens,
        "text_task_prefix": TASK_PREFIX,
        "metrics": summaries,
        "interpretation": [
            "DB tags are reference labels, not independently verified visual ground truth.",
            "Absent annotations are unknown; observed_agreement is not true precision.",
            "Cosine scores are not probabilities of tag presence.",
            "incorrect rejections can include caption moves; matching active caption strings are excluded.",
            "Group matches assume exactly one observed group member; missing annotations may affect results.",
            "Candidate vocabulary is fixed across runs; reference recall includes out-of-vocabulary labels.",
        ],
    }
    write_json(args.output_dir / "summary.json", summary)
    write_report(args.output_dir / "report.md", summary, ks)
    write_csv(
        args.output_dir / "rankings.csv",
        rankings,
        ["run", "image_id", "rank", "tag", "score", "in_reference", "explicitly_rejected"],
    )
    write_csv(args.output_dir / "tag_ranks.csv", tag_rows, ["run", "image_id", "tag", "rank", "score"])
    write_csv(
        args.output_dir / "attribute_groups.csv",
        contrasts,
        ["run", "image_id", "group", "reference_tag", "top_tag", "matches_reference", "reference_margin"],
    )
    print(f"Reports saved to {args.output_dir.resolve()}")


def main() -> int:
    args = parser().parse_args()
    try:
        run(args)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
