"""ADR の陳腐化(drift)候補を検出するオンデマンドツール。

ADR は「書いた時点の決定スナップショット」で、下流(コード/ワイヤー/他 ADR)が動いても
自動追従しない。本ツールは ADR 0029 を陳腐化させた2つのサインを機械検出する:

1. REFERENCE-DRIFT — その ADR を参照しているファイルが、ADR 本体より新しく更新されている
   (世界が動いたのに ADR が据え置き)。
2. ADDITIVE-DRIFT — ADR 本文に「追補 / amendment / addendum」的な後付け節があるのに、
   Status 行に "Revised" が無い(主従が変わったサインを付録で吸収している)。

意味的 currency(決定がまだ妥当か)は判定しない。あくまで「見直すべき候補」を出すだけ。

使い方:
    uv run python scripts/check_adr_drift.py            # 既定 30 日閾値で markdown レポート
    uv run python scripts/check_adr_drift.py --days 60  # 参照が 60 日以上新しいものだけ
    make adr-drift
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "decisions"

# 参照を逆引きする対象 = 決定を「実際に動かす」面に限定する。
# ADR 同士の相互参照 (docs/decisions) や narrative docs (architecture/lessons) は
# 多数の ADR に言及してノイズになるため対象外。enactment surface = 実装 + ワイヤー。
_REFERENCE_PREFIXES = ("src/", "tests/", "scripts/")
# 追加で(tracked でなくても)走査するディレクトリ。ワイヤーのローカルコピー等。
_EXTRA_SCAN_DIRS = ("docs/design",)
# 参照集計から除外するファイル (索引・ADR 本体自身は別途除外)。
_EXCLUDE_FILES = ("docs/decisions/README.md",)
# 追補サインの語。
_ADDENDUM_MARKERS = ("追補", "amendment", "addendum")
# テキストとして走査する拡張子。
_TEXT_SUFFIXES = {".md", ".py", ".html", ".toml", ".txt", ".json", ".jsx", ".ts", ".tsx", ".cfg", ".ini"}


@dataclass
class AdrInfo:
    """1 ADR の検査結果。"""

    number: int
    path: Path
    last_commit: datetime | None
    has_addendum: bool
    status_has_revised: bool
    # (参照ファイル, その最終更新日時) のうち ADR より新しいもの。
    newer_refs: list[tuple[str, datetime]] = field(default_factory=list)


def _git_commit_dates() -> dict[str, datetime]:
    """全 tracked file の最終コミット日時を **1 回の git log** で取得する (相対パス→日時)。

    `git log --name-only` を新しい順に走査し、各ファイルの初出コミット = 最終コミットとする。
    ファイルごとに `git log` を起動しないことで O(ファイル数) の subprocess を回避する。
    """
    # pathspec で対象配下のコミットだけ走査し、全履歴 walk を避ける。
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "log",
                "--name-only",
                "--format=__COMMIT__%cI",
                "--",
                "src",
                "tests",
                "scripts",
                "docs/decisions",
                "docs/design",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    dates: dict[str, datetime] = {}
    current: datetime | None = None
    for line in out.splitlines():
        if line.startswith("__COMMIT__"):
            current = datetime.fromisoformat(line[len("__COMMIT__") :].strip())
        elif line and current is not None and line not in dates:
            dates[line] = current  # 履歴は新しい順 → 初出が最終コミット
    return dates


def _resolve_date(path: Path, git_dates: dict[str, datetime]) -> datetime | None:
    """git 最終コミット日時、無ければ filesystem mtime を返す。"""
    rel = path.relative_to(ROOT).as_posix()
    if rel in git_dates:
        return git_dates[rel]
    if path.exists():
        return datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    return None


_ADR_REF_RE = re.compile(r"ADR[\s_-]*(\d{4})\b|\b(\d{4})-")


def _referenced_numbers(text: str) -> set[int]:
    """テキストが参照する ADR 番号 (4 桁) の集合を返す (ADR NNNN / NNNN- 形式)。"""
    return {int(m.group(1) or m.group(2)) for m in _ADR_REF_RE.finditer(text)}


def _scan_files() -> list[Path]:
    """参照逆引き対象ファイル一覧 (tracked 接頭辞 + 追加走査ディレクトリ) を返す。"""
    paths: set[Path] = set()
    try:
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", *_REFERENCE_PREFIXES],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        tracked = []
    for rel in tracked:
        if rel and rel not in _EXCLUDE_FILES:
            paths.add(ROOT / rel)
    for extra in _EXTRA_SCAN_DIRS:
        d = ROOT / extra
        if d.is_dir():
            paths.update(p for p in d.rglob("*") if p.is_file())
    return [p for p in paths if p.suffix.lower() in _TEXT_SUFFIXES]


def _adr_files() -> list[Path]:
    """docs/decisions/NNNN-*.md を番号順で返す。"""
    files = [p for p in ADR_DIR.glob("*.md") if re.match(r"\d{4}-", p.name)]
    return sorted(files, key=lambda p: p.name)


def analyze(days: int) -> list[AdrInfo]:
    """全 ADR を検査して drift 候補情報を返す。

    各参照ファイルは **1 回だけ**読み、(ADR 番号 → [(ファイル, 日時)]) の逆引きを作る。
    日時は `_git_commit_dates()` の単一 git log 結果を共有する (subprocess は 1 回)。
    """
    git_dates = _git_commit_dates()
    scan_files = _scan_files()

    # 参照ファイルを 1 回ずつ読み、参照 ADR 番号 → [(file, date)] の逆引きを構築する。
    inverted: dict[int, list[tuple[str, datetime]]] = {}
    for ref_path in scan_files:
        date = _resolve_date(ref_path, git_dates)
        if date is None:
            continue
        try:
            text = ref_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = ref_path.relative_to(ROOT).as_posix()
        for num in _referenced_numbers(text):
            inverted.setdefault(num, []).append((rel, date))

    results: list[AdrInfo] = []
    for adr_path in _adr_files():
        number = int(adr_path.name[:4])
        text = adr_path.read_text(encoding="utf-8")
        status_line = next((ln for ln in text.splitlines() if "ステータス" in ln or "Status" in ln), "")
        adr_date = _resolve_date(adr_path, git_dates)
        info = AdrInfo(
            number=number,
            path=adr_path,
            last_commit=adr_date,
            has_addendum=any(m in text for m in _ADDENDUM_MARKERS),
            status_has_revised="Revised" in status_line,
        )
        if adr_date is not None:
            adr_rel = adr_path.relative_to(ROOT).as_posix()
            for rel, d in inverted.get(number, []):
                if rel != adr_rel and (d - adr_date).days >= days:
                    info.newer_refs.append((rel, d))
            info.newer_refs.sort(key=lambda t: t[1], reverse=True)
        results.append(info)
    return results


def render(results: list[AdrInfo], days: int) -> str:
    """検査結果を markdown レポートに整形する。"""
    ref_drift = [r for r in results if r.newer_refs]
    add_drift = [r for r in results if r.has_addendum and not r.status_has_revised]

    lines = ["# ADR drift レポート", ""]
    lines.append(f"- 検査 ADR: {len(results)} 件 / 参照しきい値: {days} 日")
    lines.append(f"- REFERENCE-DRIFT: {len(ref_drift)} 件 / ADDITIVE-DRIFT: {len(add_drift)} 件")
    lines.append("")

    lines.append("## REFERENCE-DRIFT (参照ファイルが ADR より新しい)")
    if not ref_drift:
        lines.append("- なし")
    for r in ref_drift:
        adr_date = r.last_commit.date().isoformat() if r.last_commit else "?"
        lines.append(f"- **ADR {r.number:04d}** ({r.path.name}, 最終 {adr_date})")
        for rel, d in r.newer_refs[:5]:
            lines.append(f"    - {d.date().isoformat()}  {rel}")
        if len(r.newer_refs) > 5:
            lines.append(f"    - … 他 {len(r.newer_refs) - 5} 件")
    lines.append("")

    lines.append("## ADDITIVE-DRIFT (追補があるが Status に Revised 無し)")
    if not add_drift:
        lines.append("- なし")
    for r in add_drift:
        lines.append(f"- **ADR {r.number:04d}** ({r.path.name}) — 追補節あり / Status 未 Revised")
    lines.append("")

    lines.append("> 注: これは「見直すべき候補」。決定がまだ妥当かは人が判断する。")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR の陳腐化候補を検出する。")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="参照ファイルが ADR より何日以上新しければ drift 候補とするか (既定: 30)。",
    )
    args = parser.parse_args()
    results = analyze(args.days)
    print(render(results, args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
