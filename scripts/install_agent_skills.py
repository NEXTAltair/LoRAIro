#!/usr/bin/env python3
"""skills-lock.json を SSoT として外部ソース由来の agent skills を復元する。

外部ソース (sourceType: "github") の skill は git 追跡しない (.gitignore 参照) ため、
fresh clone / まっさらな devcontainer では .agents/skills/ に実体が存在しない。
このスクリプトが skills-lock.json を読み、欠落している skill だけを
`npx skills add` で再導入する。導入済みの skill には触れない。

呼び出し元: `make setup` (devcontainer postCreateCommand.sh も make setup 経由で実行)。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    lock_path = PROJECT_ROOT / "skills-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))

    missing: list[tuple[str, str]] = []
    for name, entry in sorted(lock["skills"].items()):
        if entry.get("sourceType") != "github":
            continue  # local ソースは git 追跡済みなので対象外
        if (PROJECT_ROOT / ".agents" / "skills" / name / "SKILL.md").exists():
            continue
        missing.append((name, entry["source"]))

    if not missing:
        print("OK: 外部ソース skill はすべて導入済み")
        return 0

    if shutil.which("npx") is None:
        # devcontainer 以外 (Node 無しホスト) では skill 復元をスキップして続行する
        print(
            f"WARNING: npx が見つからないため外部 skill {len(missing)} 件を復元できません: "
            + ", ".join(name for name, _ in missing),
            file=sys.stderr,
        )
        return 0

    failed: list[str] = []
    for name, source in missing:
        print(f"install: {name} <- github:{source}")
        result = subprocess.run(
            ["npx", "--yes", "skills", "add", f"github:{source}", "--skill", name, "-y"],
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            failed.append(name)

    if failed:
        print(f"FAILED: 復元に失敗した skill: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"OK: 外部ソース skill を {len(missing)} 件復元")
    return 0


if __name__ == "__main__":
    sys.exit(main())
