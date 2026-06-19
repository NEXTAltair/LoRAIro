"""OKF バンドルの frontmatter を検証する汎用ツール (stdlib only)。

OKF SPEC v0.1 が要求する最小の構造規約を機械チェックする:

- 各概念ドキュメントに frontmatter があり、必須キー ``type`` を持つこと。
- ``timestamp`` があれば ISO 8601 (``YYYY-MM-DD`` または日時) であること。
- 予約ファイル名 (``index.md`` / ``log.md``) を概念ドキュメントに使っていないこと
  (本ツールは予約名を概念として走査しないため、混在は ``--require`` の対象外)。

プロジェクト非依存。``--bundle-root`` で対象ディレクトリを受け取り、
``--require`` で必須キーを追加できる。違反があれば終了コード 1。

使い方:
    python3 okf_validate.py --bundle-root docs/decisions
    python3 okf_validate.py --bundle-root docs/decisions --require type,title --exclude README.md
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from _okf import iter_concept_files, parse_frontmatter

# OKF SPEC §4.1: frontmatter の必須キーは type のみ。
DEFAULT_REQUIRED = ("type",)


def _is_iso8601(value: str) -> bool:
    """値が ISO 8601 の日付または日時として解釈できるか判定する。"""
    for parser in (date.fromisoformat, datetime.fromisoformat):
        try:
            parser(value.replace("Z", "+00:00") if parser is datetime.fromisoformat else value)
            return True
        except ValueError:
            continue
    return False


def validate(bundle_root: Path, required: tuple[str, ...], excludes: frozenset[str]) -> list[str]:
    """バンドルを検証し、違反メッセージのリストを返す (空なら合格)。"""
    problems: list[str] = []
    count = 0
    for path in iter_concept_files(bundle_root, extra_excludes=excludes):
        count += 1
        rel = path.relative_to(bundle_root).as_posix()
        text = path.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if not fm:
            problems.append(f"{rel}: frontmatter が無い")
            continue
        for key in required:
            if not fm.get(key):
                problems.append(f"{rel}: 必須キー '{key}' が無い")
        timestamp = fm.get("timestamp")
        if isinstance(timestamp, str) and timestamp and not _is_iso8601(timestamp):
            problems.append(f"{rel}: timestamp '{timestamp}' が ISO 8601 でない")
    if count == 0:
        problems.append(f"{bundle_root}: 概念ドキュメント (*.md) が見つからない")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="OKF バンドルの frontmatter を検証する。")
    parser.add_argument("--bundle-root", type=Path, required=True, help="バンドルのルートディレクトリ。")
    parser.add_argument(
        "--require",
        default="type",
        help="必須キーのカンマ区切り (既定: type)。",
    )
    parser.add_argument(
        "--exclude",
        default="",
        help="走査から除外するファイル名のカンマ区切り (例: README.md)。",
    )
    args = parser.parse_args()

    bundle_root: Path = args.bundle_root
    if not bundle_root.is_dir():
        print(f"エラー: バンドルが見つからない: {bundle_root}", file=sys.stderr)
        return 2

    required = tuple(k.strip() for k in args.require.split(",") if k.strip()) or DEFAULT_REQUIRED
    excludes = frozenset(k.strip() for k in args.exclude.split(",") if k.strip())

    problems = validate(bundle_root, required, excludes)
    if problems:
        print(f"OKF 検証 NG: {len(problems)} 件の違反")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OKF 検証 OK: {bundle_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
