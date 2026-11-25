---
type: Guide
title: Development Workflow
status: Accepted
timestamp: 2026-06-06
tags: [process]
---
# 開発ワークフロー

LoRAIro における開発プロセスと標準的な作業手順をまとめる。

## 標準ワークフロー

```
check-existing skill → Plan Mode/brainstorming → 実装(TDD) → 検証 → 記録
```

1. **調査・分析**: `check-existing` スキルで要件を整理し、既存ライブラリや `local_packages/` の実装を調査する
2. **計画**: ネイティブの Plan Mode(`/plan`)、または superpowers の `brainstorming` から `writing-plans` を用いる
3. **実装**: superpowers の `executing-plans`・`test-driven-development` と `lorairo-*` スキルを併用して実装する
4. **検証**: `test-driven-development` と `lorairo-test-generator` スキルでテストを整備し、`make format`・`make mypy`・`uv run pytest` で確認する
5. **レビュー**: 組み込みの `/code-review` と、`code-reviewer`・`security-reviewer` エージェントで点検する
6. **記録**: 重要な判断を `docs/decisions/`(ADR)と `docs/lessons-learned.md` へ残す

> 旧 `/planning`、`/implement`、`/test`、`/build-fix`、`/code-review`、`/save-session` コマンドは廃止した。現在はネイティブ機能、superpowers、LoRAIro スキルへ統合済みである。

**プロセス原則**:
- 変更前に関連コードを必ず読む
- LoRAIro の確立されたアーキテクチャパターンに従う
- コードを変更したら関連ドキュメントもあわせて更新する

## Plan Mode と brainstorming の使い分け

タスクの規模と不確実性に応じて、以下の 2 経路を使い分ける。どちらの経路でも `rules/planning-memory.md` に従い、着手前に ADR と教訓を確認する。

| 手法 | 主な用途 | 出力先 |
|---|---|---|
| **Plan Mode**(`/plan`、軽量タスク) | 単一機能の実装、即座に着手できる作業 | `.claude/plans/`(`docs/plans/` へ自動コピー) |
| **superpowers `brainstorming` → `writing-plans`**(包括設計) | 複雑なアーキテクチャ決定、複数フェーズの機能、要件が曖昧な作業 | `docs/superpowers/specs/` の仕様書と実装計画 |

**選択の目安**:
- シンプルな機能追加には **Plan Mode** を使う
- アーキテクチャ変更や要件が曖昧な課題には **brainstorming** を使う
- 過去に似た実装がある場合は、先に `check-existing` スキルで調査してから Plan Mode へ進む

## 並列開発のための Git Worktree

複数ブランチを同時に扱う場合は Git worktree を活用する。

```bash
# 新しいブランチで worktree 作成
git worktree add ../LoRAIro-feature-name -b feature/branch-name

# 既存ブランチで worktree 使用
git worktree add ../LoRAIro-feature-name feature/existing-branch

# 一覧
git worktree list

# 削除
git worktree remove ../LoRAIro-feature-name
```

### worktree 内での実行ルール(共有 venv の保護)

worktree 専用の venv は作成せず、共有チェックアウトの `.venv` を使用する。worktree 内で素の `uv run` や `uv sync` を実行すると、暗黙の同期により共有 venv 内の `lorairo` editable インストールが worktree のパスへ再固定される。その状態で worktree を削除すると、共有チェックアウト側で `ModuleNotFoundError: No module named 'lorairo'` が発生する(#1362)。

```bash
# worktree 内: Makefile ターゲットは共有 venv を明示し sync しない (推奨)
make mypy / make lint / make test / make adr-index / make generate-ui

# 直接 uv を使う場合: 共有 venv を明示 + --no-sync + PYTHONPATH を worktree の src に向ける
# <shared-venv> は現在の OS の共有 checkout の .venv (下記)
UV_PROJECT_ENVIRONMENT=<shared-venv> PYTHONPATH=src uv run --no-sync pytest <path>

# 禁止: worktree 内での uv run (--no-sync なし) / uv sync / uv lock
```

- `<shared-venv>` のパスは OS ごとに異なる(Dev Container では Linux 側チェックアウト、Windows ではホスト側チェックアウト)。パスを直接書かず、`scripts/configure_agent_environment.py` が設定したユーザーレベルの `UV_PROJECT_ENVIRONMENT` をそのまま利用する。未設定のシェルでは、現在のチェックアウトの Git 共通ルート直下である `$(git rev-parse --path-format=absolute --git-common-dir)/../.venv` を指定する。詳細は `AGENTS.md` を参照する。
- `make install` と `make install-dev`(依存同期)は worktree からは拒否される。共有チェックアウトで実行する。
- `.ui` ファイル変更後のコード再生成も、worktree 内で `make generate-ui` を使う。
- 誤って再固定され共有チェックアウトが壊れた場合は、共有チェックアウトで `git submodule update --init --recursive` の後に `uv sync --dev` を実行して復旧する。

**運用のベストプラクティス**:
- worktree は親ディレクトリ(`../LoRAIro-feature-name`)に配置する
- ブランチ名に対応した分かりやすいディレクトリ名を付ける
- マージ後は `git worktree remove` で速やかに削除する

## Claude Skills

開発用スキルは `.agents/skills/` に配置している(`npx skills` で管理し、`.claude/skills/<name>` からシンボリックリンクを張る。導入元の SSoT は `skills-lock.json` である)。

スキルは次の 2 系統に分かれる。

- **LoRAIro 固有スキル(git 追跡対象)**: `lorairo-*` 系と `agent-pr-*` 系、および汎用スキルを LoRAIro 固有の設定(`local_packages` や `make` ターゲットなど)に特化させたスキル(`interface-design`、`sqlalchemy-query-patterns`、`okf-bundle`)。なお `okf-bundle` は Makefile の `adr-index`・`adr-okf`・`docs-okf` がスクリプトを直接呼び出すため、`make setup` 前のビルド破損を防ぐ目的で git 追跡対象として維持する。
- **外部ソーススキル(git 追跡対象外)**: [altairs-agent-dev-kit](https://github.com/NEXTAltair/altairs-agent-dev-kit) 由来(`check-existing`、`lazy-import-refactor`、`goal-prompt-crafter`、`skill-creator`、`github-ops`、`prompt-optimizer`、`qa-expert`、`claude-md-progressive-disclosurer`)と、サードパーティ由来(`wshobson/agents`、`vercel-labs/agent-skills`)。実体は `.gitignore` で除外し、`skills-lock.json` の記録をもとに `github@ref` から復元する。

### 外部スキルのインストール(altairs-agent-dev-kit を含む)

`make setup`(devcontainer の `postCreateCommand` からも呼び出される)は `scripts/install_agent_skills.py` を実行し、`skills-lock.json` に記録された外部スキルのうち不足しているものを `npx skills add` で自動導入する。新規に devcontainer を立ち上げた場合も手動操作は不要である。

手動で操作する場合は以下のコマンドを使用する。

```bash
make skills-install     # 欠落・stale な外部スキルのみ復元(要 Node.js/npx)

# devkit から新しいスキルを追加 / 既存スキルを更新する場合
npx skills add github:NEXTAltair/altairs-agent-dev-kit --skill <skill-name> -y
```

導入状態は `.agents/skills/.installed-lock-hashes.json`(git 追跡外)に記録する。このファイルが破損または消失しても手動復旧は不要である。状態の無い外部スキルは信用せず再導入する設計のため、次回の `make skills-install` または `make setup` で全外部スキルがロック情報から再導入され、状態ファイルも再構築される。

`npx skills add` を再実行すると実体が上書きされ、`skills-lock.json` のハッシュも更新される。devkit 側の更新へ追従する際は、`skills-lock.json` の差分もあわせてコミットする。

### 主な LoRAIro 開発スキル

- `check-existing` — 実装前の要件ヒアリングと既存解の調査
- `lorairo-repository-pattern` — SQLAlchemy リポジトリパターンの実装ガイド
- `interface-design` — UI デザイン原則(技術実装前のデザイン決定)
- `lorairo-qt-widget` — PySide6 ウィジェットの技術実装(Signal/Slot、Qt Designer)
- `lorairo-test-generator` — pytest と pytest-qt のテスト生成(75% 以上のカバレッジ、`test-sync` を含む)

デザイン作業は `interface-design`(デザイン意図の整理)から `lorairo-qt-widget`(技術実装)の順に進める。各スキルはタスクの文脈に応じて Claude が自動で呼び出す。

## Hook システム(自動実行)

設定ファイルは `.claude/settings.local.json` に配置する。

**セキュリティ・品質管理(PreToolUse)**:
- **Grep 拒否 Hook**: `git grep --function-context <pattern>` の使用を強制する
- **Bash 検証 Hook**: 実行前のセキュリティチェックとコマンド最適化提案を行う

**計画共有(PostToolUse)**:
- ExitPlanMode 後に `.claude/plans/{name}.md` を `docs/plans/plan_{name}_{date}.md` へ自動コピーする

**品質基準**:
- Ruff によるフォーマット(最大行長 108 文字)
- テストカバレッジ 75% 以上
- モダンな Python 型記法の使用(`typing.List`・`typing.Dict` ではなく `list`・`dict`)
