# Development Workflow

LoRAIro の開発プロセスと標準的な作業パターン。

## Standard Workflow

```
/check-existing → Plan Mode → /implement → /test → /save-session
```

1. **Analysis**: `/check-existing` — 既存機能・実装パターンの調査
2. **Planning**: Plan Mode (Claude Code ネイティブ) — 実装方針の策定
3. **Implementation**: `/implement` — コード開発
4. **Validation**: `/test` — 品質保証・テスト実行
5. **Session Save**: `/save-session` — 設計意図を OpenClaw LTM に保存

**Process Rules:**
- 関連コードを必ず読んでから変更する
- LoRAIro の確立されたアーキテクチャパターンに従う
- コード変更時は関連 docs を更新する

## Plan Mode vs /planning Command

**Plan Mode** (Quick Task Planning):
- **用途**: 単一機能の実装、即座の実行タスク
- **所要時間**: 5-10分
- **出力**: `.claude/plans/` → `docs/plans/` に自動コピー

**/planning Command** (Comprehensive Design):
- **用途**: 複雑なアーキテクチャ決定、複数フェーズ機能
- **所要時間**: 20-40分
- **出力**: Notion LTM（設計/意図）+ `docs/plans/`

**選択ガイドライン**:
- シンプルな機能追加 → **Plan Mode**
- アーキテクチャ変更を伴う実装 → **/planning**
- 過去に似た実装がある → まず `/check-existing`、その後 Plan Mode

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

`.github/skills/` に LoRAIro 開発パターンが定義されています。

**LoRAIro Development Skills:**
- `lorairo-repository-pattern` — SQLAlchemy リポジトリパターン実装ガイド
- `interface-design` — UI デザイン原則（技術実装前のデザイン決定）
- `lorairo-qt-widget` — PySide6 ウィジェット技術実装（Signal/Slot、Qt Designer）
- `lorairo-test-generator` — pytest+pytest-qt テスト生成（75%+ カバレッジ）

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
