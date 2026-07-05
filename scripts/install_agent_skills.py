#!/usr/bin/env python3
"""skills-lock.json を SSoT として外部ソース由来の agent skills を復元する。

外部ソース (sourceType: "github") の skill は git 追跡しない (.gitignore 参照) ため、
fresh clone / まっさらな devcontainer では .agents/skills/ に実体が存在しない。
このスクリプトが skills-lock.json を読み、欠落 or lock 更新で stale になった skill を
`npx skills add` で再導入し、lock から削除された外部 skill の実体を除去する。

再導入の判定は状態ファイル (.agents/skills/.installed-lock-hashes.json、skill 名 →
導入時 lock computedHash) と lock の照合で行う。状態ファイルは skill dir の外に置く
(skills CLI の computedHash は skill dir 内の全ファイルを再帰的に含むため、dir 内に
マーカーを置くと手動 `npx skills add` 時に hash へ混入して偽 drift の原因になる)。
状態が無い既存導入分は「lock 記録時の内容のまま」とみなして状態を記録する
(lock hash は導入時に CLI が計算するため、この時点では両者は一致している)。

`npx skills add` は lock エントリに ref があれば `source#ref` で固定し、無ければ
upstream の現行 default branch を取得する。後者は lock 記録時から upstream が変わって
いると異なる内容が入りうるため、復元後に lock の computedHash が書き換わっていないか
を照合し、drift を検出したら該当 skill の実体を除去し skills-lock.json を実行前の
内容へ戻して exit 1 で失敗させる (導入を受け入れない)。再実行しても欠落 → 再導入 →
drift 再検出で決定的に失敗し続ける。取り込む場合は手動で `npx skills add` を実行し、
lock diff を確認して commit する。drift 照合は一部の add が失敗した場合でも成功分に
対して必ず実行する (部分失敗を口実に汚れた lock を残さない)。

lock 更新による再導入では、旧実体を .agents/skills/.pending-replace/ へ退避してから
add を実行し、失敗時は旧実体を復元する (ネットワーク障害等で手元の動く copy を失わない)。

また、`.claude/skills/<name>` symlink は復元分だけでなく全 skill (LoRAIro 固有の
local skill 含む) について保証する。実体を失った broken symlink、および正規ターゲット
(.agents/skills/<name>) を指さない symlink や実体 dir 化したエントリは正規 symlink に
置き換える (validate_harness.py の要求と一致させる)。

呼び出し元: `make setup` (devcontainer postCreateCommand.sh も make setup 経由で実行)。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = PROJECT_ROOT / ".agents" / "skills"
CLAUDE_SKILLS_DIR = PROJECT_ROOT / ".claude" / "skills"
STATE_FILE = SKILLS_DIR / ".installed-lock-hashes.json"
PENDING_DIR = SKILLS_DIR / ".pending-replace"
LEGACY_MARKER_NAME = ".installed-lock-hash"


def load_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict[str, str]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def npx_env() -> dict[str, str]:
    """npx (内部で git clone) 用の環境変数。

    computedHash は取得ファイルの内容から計算されるため、ホストの git 設定
    (core.autocrlf=true 等) で checkout 内容が CRLF 化すると hash が環境依存になる
    (devcontainer で記録した lock hash が CI の LF 内容と不一致 → 偽 drift)。
    GIT_CONFIG 環境変数で autocrlf を無効化し、どの環境でも同一内容を取得させる。
    """
    env = os.environ.copy()
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "core.autocrlf"
    env["GIT_CONFIG_VALUE_0"] = "false"
    return env


def source_arg(entry: dict) -> str:
    """lock エントリから `npx skills add` の source 引数を組み立てる (ref があれば固定)。"""
    src = f"github:{entry['source']}"
    ref = entry.get("ref")
    return f"{src}#{ref}" if ref else src


def migrate_legacy_markers(state: dict[str, str]) -> None:
    """旧方式の dir 内マーカーを状態ファイルへ移行してから除去する。

    値を読まずに消すと、マーカー記録後に lock が更新されていた場合に stale な dir が
    「状態なし = lock どおり」と誤認されて lock-updated 再導入がスキップされるため、
    状態に未登録の skill はマーカー値を引き継ぐ。dir 内にマーカーを残さないのは
    CLI の computedHash 計算 (dir 内全ファイル再帰) に混入させないため。
    """
    for marker in SKILLS_DIR.glob(f"*/{LEGACY_MARKER_NAME}"):
        name = marker.parent.name
        if name not in state:
            state[name] = marker.read_text(encoding="utf-8").strip()
        marker.unlink()


def collect_targets(lock: dict, state: dict[str, str]) -> list[tuple[str, dict, str]]:
    """再導入が必要な (name, entry, reason) を列挙し、健全な既存導入は状態に記録する。"""
    targets: list[tuple[str, dict, str]] = []
    for name, entry in sorted(lock["skills"].items()):
        if entry.get("sourceType") != "github":
            state.pop(name, None)  # ソース切替等で残った stray 状態は掃除 (local は git 追跡)
            continue
        lock_hash = entry.get("computedHash", "")
        if not (SKILLS_DIR / name / "SKILL.md").exists():
            targets.append((name, entry, "missing"))
        elif name not in state:
            # 既存導入分: 導入時に CLI が lock hash を計算しているため一致している前提で記録
            state[name] = lock_hash
        elif state[name] != lock_hash:
            targets.append((name, entry, "lock-updated"))
    return targets


def prune_removed_skills(lock: dict, state: dict[str, str]) -> list[str]:
    """lock から削除された外部 skill (状態ファイルに記録があるもの) の実体を除去する。

    状態に記録の無い dir (git 追跡の local skill 等) には触れない。
    """
    pruned: list[str] = []
    for name in sorted(set(state) - set(lock["skills"])):
        skill_dir = SKILLS_DIR / name
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        state.pop(name)
        pruned.append(name)
    return pruned


def ensure_claude_symlinks() -> None:
    """全 shared skill の .claude/skills symlink を保証し、broken/非正規エントリを正規化する。"""
    if not SKILLS_DIR.exists():
        return
    CLAUDE_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for link in sorted(CLAUDE_SKILLS_DIR.iterdir()):
        # shared 実体を失ったエントリは種別 (symlink / copy 化した実 dir / ファイル) を
        # 問わず掃除する。lock から削除された skill の copy を Claude が読み続けないため
        if (SKILLS_DIR / link.name / "SKILL.md").exists():
            continue
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link)
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not (skill_dir / "SKILL.md").exists():
            continue
        link = CLAUDE_SKILLS_DIR / skill_dir.name
        expected_target = skill_dir.resolve()
        if link.is_symlink():
            if link.resolve() == expected_target:
                continue
            link.unlink()  # 別ターゲットを指す symlink は正規化する
        elif link.is_dir():
            shutil.rmtree(link)  # symlink 失敗時などに copy 化した stale dir を置換する
        elif link.exists():
            link.unlink()
        link.symlink_to(Path("..") / ".." / ".agents" / "skills" / skill_dir.name)


def backup_existing(name: str) -> Path | None:
    """lock-updated 再導入前に旧実体を退避する。add 失敗・drift 却下時に復元するため。"""
    skill_dir = SKILLS_DIR / name
    if not skill_dir.exists():
        return None
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    backup = PENDING_DIR / name
    if backup.exists():
        shutil.rmtree(backup)
    shutil.move(str(skill_dir), str(backup))
    return backup


def restore_backup(name: str, backup: Path) -> None:
    """退避しておいた旧実体を skill dir へ戻す。"""
    skill_dir = SKILLS_DIR / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)
    shutil.move(str(backup), str(skill_dir))


def main() -> int:
    lock_path = PROJECT_ROOT / "skills-lock.json"
    lock_text_before = lock_path.read_text(encoding="utf-8")
    lock_before = json.loads(lock_text_before)

    state = load_state()
    migrate_legacy_markers(state)
    targets = collect_targets(lock_before, state)
    pruned = prune_removed_skills(lock_before, state)
    if pruned:
        print(f"prune: lock から削除された外部 skill を除去: {', '.join(pruned)}")

    if not targets:
        save_state(state)
        ensure_claude_symlinks()
        print("OK: 外部ソース skill はすべて lock と同期済み")
        return 0

    if shutil.which("npx") is None:
        # 復元が必要と判定済みなのに実行できない状態を成功扱いにしない
        # (validate_harness が lock との不整合を報告し続けるため、ここで明示的に失敗させる)
        save_state(state)
        ensure_claude_symlinks()
        print(
            f"ERROR: npx が見つからないため必要な外部 skill {len(targets)} 件を復元できません: "
            + ", ".join(name for name, _, _ in targets)
            + "\n  Node.js (npx) を導入して `make skills-install` を再実行してください",
            file=sys.stderr,
        )
        return 1

    failed: list[str] = []
    succeeded: list[str] = []
    backups: dict[str, Path] = {}
    for name, entry, reason in targets:
        src = source_arg(entry)
        print(f"install: {name} <- {src} ({reason})")
        backup = backup_existing(name)
        # --agent codex で universal 配置 (.agents/skills) のみに限定する。agent 未検出の
        # ホストで -y が全 agent へ展開するのを防ぐ (実測: .codex/ 等への書き込みは無し)。
        # Claude Code 用 symlink は後段の ensure_claude_symlinks() が作る
        result = subprocess.run(
            ["npx", "--yes", "skills", "add", src, "--skill", name, "--agent", "codex", "-y"],
            cwd=PROJECT_ROOT,
            env=npx_env(),
        )
        # CLI は per-agent の書き込み失敗をログに出しつつ exit 0 で終えることがあるため、
        # returncode だけでなく実体 (SKILL.md) が書かれたことを成功条件にする
        if result.returncode == 0 and (SKILLS_DIR / name / "SKILL.md").exists():
            succeeded.append(name)
            if backup is not None:
                # バックアップの破棄は drift 照合の通過後まで遅延する
                # (add 成功でも drift 却下されると新旧両方を失うため)
                backups[name] = backup
        else:
            failed.append(name)
            if backup is not None:
                # 失敗時は手元で動いていた旧実体へ戻す (次回また lock-updated として再試行)
                restore_backup(name, backup)

    # 復元内容が lock 記録時と同一かを computedHash で照合する。`npx skills add` は
    # 取得内容の hash を lock に書き戻すため、hash が変わった = upstream drift。
    # 一部の add が失敗していても成功分の照合は必ず行う (汚れた lock を残さない)。
    lock_after = json.loads(lock_path.read_text(encoding="utf-8"))
    drifted: list[str] = []
    for name in succeeded:
        expected = lock_before["skills"][name].get("computedHash")
        actual = lock_after["skills"].get(name, {}).get("computedHash")
        if actual != expected:
            drifted.append(name)
        else:
            state[name] = expected or ""

    if drifted:
        # 導入を受け入れない: drift した実体を除去し、lock を実行前の内容へ戻す。
        # lock-updated 由来でバックアップがある場合は旧実体 (最後に動いていた copy) を復元する。
        # 状態は更新しないため、再実行しても必ず再検出されて失敗し続ける
        for name in drifted:
            skill_dir = SKILLS_DIR / name
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
            if name in backups:
                restore_backup(name, backups.pop(name))
        lock_path.write_text(lock_text_before, encoding="utf-8")

    # drift 照合を通過した分のバックアップだけをここで破棄する
    for backup in backups.values():
        shutil.rmtree(backup)
    if PENDING_DIR.exists() and not any(PENDING_DIR.iterdir()):
        PENDING_DIR.rmdir()

    save_state(state)
    ensure_claude_symlinks()

    if drifted:
        print(
            "ERROR: 復元した skill が lock 記録時と異なる内容 (upstream drift) のため除去しました"
            " (旧実体があれば復元済み): "
            + ", ".join(drifted)
            + "\n  取り込む場合: `npx skills add github:<source> --skill <name> -y` を手動実行し、"
            + "skills-lock.json の diff を確認して commit する"
            + "\n  固定する場合: upstream を lock 記録時の revision へ戻すか、lock エントリに ref を記録する",
            file=sys.stderr,
        )
    if failed:
        print(f"FAILED: 復元に失敗した skill: {', '.join(failed)}", file=sys.stderr)
    if drifted or failed:
        return 1

    print(f"OK: 外部ソース skill を {len(succeeded)} 件復元 (lock hash 一致)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
