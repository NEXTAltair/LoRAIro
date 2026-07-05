#!/usr/bin/env python3
"""skills-lock.json を SSoT として外部ソース由来の agent skills を復元する。

外部ソース (sourceType: "github") の skill は git 追跡しない (.gitignore 参照) ため、
fresh clone / まっさらな devcontainer では .agents/skills/ に実体が存在しない。
このスクリプトが skills-lock.json を読み、欠落 or lock 更新で stale になった skill を
`npx skills add` で再導入する。

再導入の判定は skill dir 内のマーカーファイル (.installed-lock-hash) と lock の
computedHash の照合で行う。マーカーが無い既存導入分は「lock 記録時の内容のまま」
とみなしてマーカーを付与する (lock hash は導入時に CLI が計算するため、この時点では
両者は一致している)。以後 pull で lock が更新されるとマーカー不一致 → 再導入になる。

`npx skills add` は upstream の現行 default branch を取得するため、lock 記録時から
upstream が変わっていると異なる内容が入りうる。復元後に lock の computedHash が
書き換わっていないかを照合し、drift を検出したら exit 1 で明示的に失敗させる
(黙って別内容を「lock どおり」として受け入れない)。drift 時は CLI が書き換えた
skills-lock.json が git diff に残るので、取り込むか戻すかを判断して解消する。

また、`.claude/skills/<name>` symlink は復元分だけでなく全 skill (LoRAIro 固有の
local skill 含む) について保証する。CLI 任せだと復元した skill の symlink だけが
作られ、validate_harness.py の「全 shared skill に symlink があること」チェックが
fresh make setup 後に落ちるため。

呼び出し元: `make setup` (devcontainer postCreateCommand.sh も make setup 経由で実行)。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / ".agents" / "skills"
CLAUDE_SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"
MARKER_NAME = ".installed-lock-hash"


def read_marker(skill_dir: Path) -> str | None:
    marker = skill_dir / MARKER_NAME
    if not marker.exists():
        return None
    return marker.read_text(encoding="utf-8").strip()


def write_marker(skill_dir: Path, lock_hash: str) -> None:
    (skill_dir / MARKER_NAME).write_text(lock_hash + "\n", encoding="utf-8")


def collect_targets(lock: dict) -> list[tuple[str, str, str]]:
    """再導入が必要な (name, source, reason) を列挙し、健全な既存導入にはマーカーを付与する。"""
    targets: list[tuple[str, str, str]] = []
    for name, entry in sorted(lock["skills"].items()):
        if entry.get("sourceType") != "github":
            continue  # local ソースは git 追跡済みなので対象外
        skill_dir = SKILLS_DIR / name
        lock_hash = entry.get("computedHash", "")
        if not (skill_dir / "SKILL.md").exists():
            targets.append((name, entry["source"], "missing"))
            continue
        marker = read_marker(skill_dir)
        if marker is None:
            # 既存導入分: 導入時に CLI が lock hash を計算しているため一致している前提で付与
            write_marker(skill_dir, lock_hash)
        elif marker != lock_hash:
            targets.append((name, entry["source"], "lock-updated"))
    return targets


def ensure_claude_symlinks() -> None:
    """全 shared skill (.agents/skills/*) の .claude/skills symlink を保証する。"""
    if not SKILLS_DIR.exists():
        return
    CLAUDE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not (skill_dir / "SKILL.md").exists():
            continue
        link = CLAUDE_SKILLS_DIR / skill_dir.name
        if link.is_symlink() or link.exists():
            continue
        link.symlink_to(Path("..") / ".." / ".agents" / "skills" / skill_dir.name)


def main() -> int:
    lock_path = PROJECT_ROOT / "skills-lock.json"
    lock_before = json.loads(lock_path.read_text(encoding="utf-8"))

    targets = collect_targets(lock_before)

    if not targets:
        ensure_claude_symlinks()
        print("OK: 外部ソース skill はすべて lock と同期済み")
        return 0

    if shutil.which("npx") is None:
        # devcontainer 以外 (Node 無しホスト) では skill 復元をスキップして続行する
        ensure_claude_symlinks()
        print(
            f"WARNING: npx が見つからないため外部 skill {len(targets)} 件を復元できません: "
            + ", ".join(name for name, _, _ in targets),
            file=sys.stderr,
        )
        return 0

    failed: list[str] = []
    for name, source, reason in targets:
        print(f"install: {name} <- github:{source} ({reason})")
        skill_dir = SKILLS_DIR / name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)  # lock 更新で stale になった旧実体を除去してから再導入
        result = subprocess.run(
            ["npx", "--yes", "skills", "add", f"github:{source}", "--skill", name, "-y"],
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            failed.append(name)

    ensure_claude_symlinks()

    if failed:
        print(f"FAILED: 復元に失敗した skill: {', '.join(failed)}", file=sys.stderr)
        return 1

    # 復元内容が lock 記録時と同一かを computedHash で照合する。`npx skills add` は
    # 取得内容の hash を lock に書き戻すため、hash が変わった = upstream drift。
    lock_after = json.loads(lock_path.read_text(encoding="utf-8"))
    drifted: list[str] = []
    for name, _, _ in targets:
        expected = lock_before["skills"][name].get("computedHash")
        actual = lock_after["skills"].get(name, {}).get("computedHash")
        if actual != expected:
            drifted.append(name)
        else:
            write_marker(SKILLS_DIR / name, expected or "")

    if drifted:
        print(
            "ERROR: 復元した skill が lock 記録時と異なる内容 (upstream drift): "
            + ", ".join(drifted)
            + "\n  取り込む場合: skills-lock.json の diff を確認して commit する"
            + "\n  固定する場合: 該当 skill を lock 記録時の revision へ戻す",
            file=sys.stderr,
        )
        return 1

    print(f"OK: 外部ソース skill を {len(targets)} 件復元 (lock hash 一致)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
