#!/usr/bin/env python3
"""skills-lock.json を SSoT として外部ソース由来の agent skills を復元する。

外部ソース (sourceType: "github") の skill は git 追跡しない (.gitignore 参照) ため、
fresh clone / まっさらな devcontainer では .agents/skills/ に実体が存在しない。
このスクリプトが skills-lock.json を読み、欠落 or lock 更新で stale になった skill を
`npx skills add` で再導入し、lock から削除された外部 skill の実体を除去する。

再導入の判定は skill dir 内のマーカーファイル (.installed-lock-hash) と lock の
computedHash の照合で行う。マーカーが無い既存導入分は「lock 記録時の内容のまま」
とみなしてマーカーを付与する (lock hash は導入時に CLI が計算するため、この時点では
両者は一致している)。以後 pull で lock が更新されるとマーカー不一致 → 再導入になる。

`npx skills add` は upstream の現行 default branch を取得するため、lock 記録時から
upstream が変わっていると異なる内容が入りうる。復元後に lock の computedHash が
書き換わっていないかを照合し、drift を検出したら該当 skill の実体を除去し
skills-lock.json を実行前の内容へ戻して exit 1 で失敗させる (導入を受け入れない)。
再実行しても欠落 → 再導入 → drift 再検出で決定的に失敗し続けるため、マーカー無し
分岐で汚れた lock hash が黙って正当化されることはない。取り込む場合は手動で
`npx skills add` を実行し、lock diff を確認して commit する。

また、`.claude/skills/<name>` symlink は復元分だけでなく全 skill (LoRAIro 固有の
local skill 含む) について保証し、実体を失った broken symlink は除去する。
CLI 任せだと復元した skill の symlink だけが作られ、validate_harness.py の
「全 shared skill に symlink があること」チェックが fresh make setup 後に落ちるため。

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
        skill_dir = SKILLS_DIR / name
        if entry.get("sourceType") != "github":
            # local ソースは git 追跡済みなので対象外。ソース切替等で残った stray マーカーは掃除する
            stray = skill_dir / MARKER_NAME
            if stray.exists():
                stray.unlink()
            continue
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


def prune_removed_skills(lock: dict) -> list[str]:
    """lock から削除された外部 skill の実体を除去する。

    マーカーファイルを持つ dir (= このスクリプト管理下で導入された外部 skill) のうち、
    lock に名前が全く存在しないものだけを対象にする。lock にエントリがある dir
    (sourceType を問わない) とマーカーの無い dir (git 追跡の local skill 等) には触れない。
    """
    if not SKILLS_DIR.exists():
        return []
    pruned: list[str] = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / MARKER_NAME).exists():
            continue
        if skill_dir.name in lock["skills"]:
            continue
        shutil.rmtree(skill_dir)
        pruned.append(skill_dir.name)
    return pruned


def ensure_claude_symlinks() -> None:
    """全 shared skill の .claude/skills symlink を保証し、broken symlink を除去する。"""
    if not SKILLS_DIR.exists():
        return
    CLAUDE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for link in sorted(CLAUDE_SKILLS_DIR.iterdir()):
        if link.is_symlink() and not link.resolve().exists():
            link.unlink()  # prune 済み skill などの実体を失ったリンクを掃除
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not (skill_dir / "SKILL.md").exists():
            continue
        link = CLAUDE_SKILLS_DIR / skill_dir.name
        if link.is_symlink() or link.exists():
            continue
        link.symlink_to(Path("..") / ".." / ".agents" / "skills" / skill_dir.name)


def main() -> int:
    lock_path = PROJECT_ROOT / "skills-lock.json"
    lock_text_before = lock_path.read_text(encoding="utf-8")
    lock_before = json.loads(lock_text_before)

    targets = collect_targets(lock_before)
    pruned = prune_removed_skills(lock_before)
    if pruned:
        print(f"prune: lock から削除された外部 skill を除去: {', '.join(pruned)}")

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

    if failed:
        ensure_claude_symlinks()
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
        # 導入を受け入れない: drift した実体を除去し、lock を実行前の内容へ戻す。
        # マーカーも書かないため、再実行しても必ず再検出されて失敗し続ける
        for name in drifted:
            skill_dir = SKILLS_DIR / name
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
        lock_path.write_text(lock_text_before, encoding="utf-8")
        ensure_claude_symlinks()
        print(
            "ERROR: 復元した skill が lock 記録時と異なる内容 (upstream drift) のため除去しました: "
            + ", ".join(drifted)
            + "\n  取り込む場合: `npx skills add github:<source> --skill <name> -y` を手動実行し、"
            + "skills-lock.json の diff を確認して commit する"
            + "\n  固定する場合: upstream を lock 記録時の revision へ戻す",
            file=sys.stderr,
        )
        return 1

    ensure_claude_symlinks()
    print(f"OK: 外部ソース skill を {len(targets)} 件復元 (lock hash 一致)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
