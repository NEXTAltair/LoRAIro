# Development Workflow

LoRAIro の開発プロセスと標準的な作業パターン。

## Standard Workflow

```
check-existing skill → Plan Mode/brainstorming → 実装(TDD) → 検証 → 記録
```

1. **Analysis**: `check-existing` skill — 要件ヒアリング + 既存ライブラリ/local_packages 調査
2. **Planning**: ネイティブ Plan Mode (`/plan`) または superpowers `brainstorming` → `writing-plans`
3. **Implementation**: superpowers `executing-plans` / `test-driven-development` + `lorairo-*` skill
4. **Validation**: superpowers `test-driven-development` + `lorairo-test-generator` skill。クイックチェックは `make format` / `make mypy` / `uv run pytest`
5. **Review**: 組み込み `/code-review` + `code-reviewer` / `security-reviewer` agent
6. **Record**: `lorairo-mem` skill（session 保存）+ `docs/decisions/` ADR + `docs/lessons-learned.md`

> 旧 `/planning` `/implement` `/test` `/build-fix` `/code-review` `/save-session` コマンドは廃止。
> ネイティブ機能・superpowers・LoRAIro skill に統合済み。

**Process Rules:**
- 関連コードを必ず読んでから変更する
- LoRAIro の確立されたアーキテクチャパターンに従う
- コード変更時は関連 docs を更新する

## Plan Mode vs brainstorming

**Plan Mode** (`/plan`, 軽量タスク):
- **用途**: 単一機能の実装、即座の実行タスク
- **出力**: `.claude/plans/` → `docs/plans/` に自動コピー

**superpowers `brainstorming` → `writing-plans`** (包括設計):
- **用途**: 複雑なアーキテクチャ決定、複数フェーズ機能、要件が曖昧なとき
- **出力**: `docs/superpowers/specs/` の spec + 実装計画

`rules/planning-memory.md` がどちらの経路でも ADR/教訓の事前確認を強制する。

**選択ガイドライン**:
- シンプルな機能追加 → **Plan Mode**
- アーキテクチャ変更・要件が曖昧 → **brainstorming**
- 過去に似た実装がある → まず `check-existing` skill、その後 Plan Mode

## Git Worktree for Parallel Development

複数ブランチを同時に操作する場合に使用。

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

**各 worktree で必要なセットアップ:**
```bash
cd ../LoRAIro-feature-name
uv sync --dev
uv run python scripts/generate_ui.py  # .ui ファイル変更後は必須
```

**ベストプラクティス:**
- 親ディレクトリに配置 (`../LoRAIro-feature-name`)
- ブランチ名に対応した説明的なディレクトリ名を使用
- マージ後は `git worktree remove` でクリーンアップ

## Claude Skills

`.agents/skills/` に LoRAIro 開発パターンが定義されています（`npx skills` 管理、`.claude/skills/<name>` は symlink）。

**LoRAIro Development Skills:**
- `check-existing` — 実装前の要件ヒアリング + 既存解調査
- `lorairo-repository-pattern` — SQLAlchemy リポジトリパターン実装ガイド
- `interface-design` — UI デザイン原則（技術実装前のデザイン決定）
- `lorairo-qt-widget` — PySide6 ウィジェット技術実装（Signal/Slot、Qt Designer）
- `lorairo-test-generator` — pytest+pytest-qt テスト生成（75%+ カバレッジ、test-sync 含む）
- `lorairo-mem` — 長期記憶 + session 保存ワークフロー

**Design Workflow**: `interface-design`（デザイン意図）→ `lorairo-qt-widget`（技術実装）の順で使用。

Skills はタスクコンテキストに応じて Claude が自動的に呼び出します。

## Hook System（自動実行）

**設定場所**: `.claude/settings.local.json`

**セキュリティ・品質管理（PreToolUse）:**
- **Grep 拒否 Hook**: `git grep --function-context <pattern>` 強制使用
- **Bash 検証 Hook**: 実行前セキュリティチェック・コマンド最適化提案

**計画共有（PostToolUse）:**
- ExitPlanMode 後: `.claude/plans/{name}.md` → `docs/plans/plan_{name}_{date}.md` に自動コピー

**Quality Standards:**
- Ruff formatting (line length: 108)
- 75%+ test coverage
- Modern Python types (`list`/`dict` over `typing.List`/`typing.Dict`)
