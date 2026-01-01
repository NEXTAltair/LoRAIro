"""Find and optionally remove caption-like tags from image DB."""

from __future__ import annotations

import argparse
import csv
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TagScore:
    tag: str
    count: int
    score: int
    reasons: list[str]


def _word_count(text: str) -> int:
    return len([w for w in text.strip().split(" ") if w])


def _score_tag(tag: str) -> TagScore:
    lower = tag.lower()
    is_lower = tag == lower
    reasons: list[str] = []
    score = 0

    if tag.startswith(" "):
        score += 2
        reasons.append("leading_space")

    # Strong signals: articles/verb-ish tokens.
    if " is " in lower:
        score += 2
        reasons.append("contains_is")
    if " a " in lower or lower.startswith("a "):
        score += 2
        reasons.append("contains_a")
    if " an " in lower or lower.startswith("an "):
        score += 2
        reasons.append("contains_an")
    if " the " in lower or lower.startswith("the "):
        score += 2
        reasons.append("contains_the")

    # Weak signals: punctuation and length.
    comma_count = tag.count(",")
    if comma_count >= 2:
        score += 2
        reasons.append("commas_2plus")
    elif comma_count == 1:
        score += 1
        reasons.append("comma_1")

    for ch in (".", "!", "?", ":", ";"):
        if ch in tag:
            score += 1
            reasons.append(f"punct_{ch}")
            break

    if " and " in lower:
        score += 1
        reasons.append("contains_and")
    if " with " in lower:
        score += 1
        reasons.append("contains_with")

    wc = _word_count(tag)
    if wc >= 8:
        score += 2
        reasons.append("words_8plus")
    elif wc >= 4:
        score += 1
        reasons.append("words_4plus")

    length = len(tag)
    if length >= 60:
        score += 2
        reasons.append("len_60plus")
    elif length >= 40:
        score += 1
        reasons.append("len_40plus")

    # Escaped parentheses often indicate tag syntax, but long sentences can still include them.
    has_escaped_paren = "\\(" in tag or "\\)" in tag
    if has_escaped_paren:
        reasons.append("escaped_paren")
        if wc <= 4 and length <= 40 and "," not in tag and all(p not in tag for p in ".!?:;"):
            score -= 2
            reasons.append("escaped_paren_short_tag_bias")
        # Tag-style "name (title) (series)" pattern, even if long.
        paren_pattern = r"^[^,]+\\\([^,]+\\\)(?:\s*\\\([^,]+\\\))*$"
        if (
            re.match(paren_pattern, tag)
            and all(p not in tag for p in ".!?:;")
            and "," not in tag
        ):
            score -= 3
            reasons.append("escaped_paren_title_pattern")

    # Romanized title-like phrases ending with "?" (often LN titles).
    if tag.endswith("?"):
        has_strong_en = any(tok in lower for tok in (" is ", " a ", " an ", " the ", " and ", " with "))
        if (
            is_lower
            and not has_strong_en
            and "," not in tag
            and all(p not in tag for p in ".!;:")
            and re.fullmatch(r"[a-z0-9\s\\\(\)\-']+\?", tag)
            and wc >= 6
        ):
            score -= 3
            reasons.append("romanized_title_question")

    # Romanized title-like phrases ending with "!" or "?!" (often LN titles).
    if tag.endswith("!") or tag.endswith("?!") or tag.endswith("!?") or tag.endswith("!?~") or tag.endswith("?!~"):
        is_lower = tag == lower
        has_strong_en = any(tok in lower for tok in (" is ", " a ", " an ", " the ", " and ", " with "))
        if (
            is_lower
            and not has_strong_en
            and "," not in tag
            and all(p not in tag for p in ".:;")
            and re.fullmatch(r"[a-z0-9\s\\\(\)\-'\?!~]+", tag)
            and wc >= 6
        ):
            score -= 3
            reasons.append("romanized_title_exclaim_combo")

    # Romanized title-like phrases wrapped by "~...~".
    if tag.count("~") >= 2:
        if (
            is_lower
            and "," not in tag
            and all(p not in tag for p in ".:;")
            and re.fullmatch(r"[a-z0-9\s\\\(\)\-'\?!~]+", tag)
            and wc >= 6
        ):
            score -= 2
            reasons.append("romanized_title_tilde_wrap")

    # Short name with escaped paren descriptor (often character tags).
    if has_escaped_paren:
        if (
            re.fullmatch(r"[^,]+\\\([^,]+\\\)", tag)
            and wc <= 6
            and "," not in tag
        ):
            score -= 2
            reasons.append("escaped_paren_name_descriptor")

    # Title-like with colon and optional escaped parens (e.g., "the x: y (series)").
    if ":" in tag:
        if (
            re.fullmatch(r"[a-z0-9\s\\\(\)\-:'&]+\Z", tag.lower())
            and "," not in tag
            and all(p not in tag for p in "!?;.")
        ):
            score -= 2
            reasons.append("romanized_title_colon")
            if re.match(r"^the [a-z0-9\s]+: [a-z0-9\s]+$", lower):
                score -= 2
                reasons.append("romanized_title_colon_definite")

    # Franchise-style exclamation in the middle (e.g., "yu-gi-oh! the ...").
    if "!" in tag and not tag.endswith("!"):
        if (
            re.fullmatch(r"[a-z0-9\s\\\(\)\-!'&]+", lower)
            and "," not in tag
            and all(p not in tag for p in "?.:;")
        ):
            score -= 2
            reasons.append("romanized_title_mid_exclaim")

    return TagScore(tag=tag, count=0, score=score, reasons=reasons)


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _find_base_db_paths() -> list[Path]:
    cache_root = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".cache" / "huggingface" / "hub"
    if not cache_root.exists():
        return []
    return sorted(cache_root.rglob("genai-image-tag-db-*.sqlite"))


def _collect_base_tags(tags: list[str], base_paths: list[Path]) -> set[str]:
    if not base_paths:
        return set()
    base_tags: set[str] = set()
    conns = [sqlite3.connect(path) for path in base_paths]
    try:
        for chunk in _chunked(tags, 900):
            placeholders = ",".join(["?"] * len(chunk))
            for conn in conns:
                cur = conn.cursor()
                cur.execute(f"SELECT tag FROM TAGS WHERE tag IN ({placeholders})", chunk)
                base_tags.update(row[0] for row in cur.fetchall())
    finally:
        for conn in conns:
            conn.close()
    return base_tags


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect caption-like tags in image DB.")
    parser.add_argument(
        "--image-db",
        type=Path,
        default=None,
        help="Path to image_database.db (default: from db_core).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Score threshold to flag caption-like tags.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=50,
        help="Sample size to print.",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=None,
        help="Export CSV of candidates.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete caption-like tags from tags table.",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=[],
        help="Exclude specific tag text from processing (repeatable).",
    )
    parser.add_argument(
        "--move-to-captions",
        type=int,
        default=None,
        help="Move tags with score >= threshold to captions table.",
    )
    args = parser.parse_args()

    from lorairo.database import db_core  # noqa: F401

    image_db_path = args.image_db or db_core.IMG_DB_PATH
    if not image_db_path.exists():
        raise FileNotFoundError(f"image DB not found: {image_db_path}")

    conn = sqlite3.connect(image_db_path)
    cur = conn.cursor()
    cur.execute("SELECT tag, COUNT(*) FROM tags GROUP BY tag")
    rows = cur.fetchall()
    tag_list = [row[0] for row in rows if row[0]]
    tag_clean_map = {tag: tag.lstrip() for tag in tag_list}

    base_paths = _find_base_db_paths()
    base_tags = _collect_base_tags(list(tag_clean_map.values()), base_paths)
    if base_paths:
        print(f"base DBs: {len(base_paths)}")
    print(f"excluded base tags: {len(base_tags)}")

    scored: list[TagScore] = []
    excluded_explicit = {t for t in args.exclude_tag if t}
    for tag, count in rows:
        if not tag:
            continue
        if tag in excluded_explicit:
            continue
        if tag_clean_map[tag] in base_tags:
            continue
        scored_item = _score_tag(tag)
        scored_item.count = int(count)
        if scored_item.score >= args.threshold:
            scored.append(scored_item)

    scored.sort(key=lambda x: (x.score, x.count), reverse=True)

    total_candidates = len(scored)
    total_rows = sum(item.count for item in scored)
    print(f"candidates: {total_candidates} tags, {total_rows} rows")

    print("sample:")
    for item in scored[: args.sample]:
        reasons = ",".join(item.reasons)
        print(f"{item.score}\t{item.count}\t{item.tag}\t{reasons}")

    if args.export:
        with args.export.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["tag", "score", "count", "reasons"])
            for item in scored:
                writer.writerow([item.tag, item.score, item.count, ";".join(item.reasons)])
        print(f"exported: {args.export}")

    if args.move_to_captions is not None:
        tags_to_move = [item.tag for item in scored if item.score >= args.move_to_captions]
        if tags_to_move:
            if args.apply:
                moved_rows = 0
                with conn:
                    for chunk in _chunked(tags_to_move, 900):
                        placeholders = ",".join(["?"] * len(chunk))
                        cur.execute(
                            f"SELECT COUNT(*) FROM tags WHERE tag IN ({placeholders})",
                            chunk,
                        )
                        moved_rows += int(cur.fetchone()[0])
                        conn.execute(
                            f"""
                            INSERT OR IGNORE INTO captions
                                (image_id, model_id, caption, existing, is_edited_manually)
                            SELECT image_id, model_id, tag, existing, is_edited_manually
                            FROM tags
                            WHERE tag IN ({placeholders})
                            """,
                            chunk,
                        )
                        conn.execute(f"DELETE FROM tags WHERE tag IN ({placeholders})", chunk)
                print(f"moved to captions: {moved_rows} tag rows")
            else:
                total_rows = 0
                for chunk in _chunked(tags_to_move, 900):
                    placeholders = ",".join(["?"] * len(chunk))
                    cur.execute(
                        f"SELECT COUNT(*) FROM tags WHERE tag IN ({placeholders})",
                        chunk,
                    )
                    total_rows += int(cur.fetchone()[0])
                print(f"would move to captions: {total_rows} tag rows")

    if args.apply and scored and args.move_to_captions is None:
        tags_to_delete = [item.tag for item in scored]
        with conn:
            for chunk in _chunked(tags_to_delete, 900):
                placeholders = ",".join(["?"] * len(chunk))
                conn.execute(f"DELETE FROM tags WHERE tag IN ({placeholders})", chunk)
        print("deleted caption-like tags")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
