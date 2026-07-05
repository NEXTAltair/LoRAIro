# Contributing to LoRAIro

LoRAIro への貢献ガイド。詳細は各リンク先のドキュメントに集約しています。

## 開発環境セットアップ

```bash
make setup     # サブモジュール (local_packages/*) 取得 + 依存関係インストール (uv sync --dev)
```

仮想環境ルール・開発コマンドの詳細は [CLAUDE.md](CLAUDE.md) を参照。

## ブランチ・PR 運用

- ブランチ命名・ワークツリー運用: [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md)
- アプリコード（`src/`, `tests/`, schema/migration）は `main` への直接作業禁止。Issue / タスク毎に専用ブランチを切る。
  ドキュメント・開発ツール chore の例外規定は [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md) の「worktree + PR を要さない例外」を参照。

## コーディング規約

型ヒント・docstring・命名規則など: [.claude/rules/coding-style.md](.claude/rules/coding-style.md)

## テスト

テスト戦略・実行方法・CI-equivalent filter: [docs/testing.md](docs/testing.md)

## リリース手順

リリース前には手動チェックリストを完走させること:
[docs/release-checklist.md](docs/release-checklist.md)

## その他

開発ワークフロー全体は [docs/development-workflow.md](docs/development-workflow.md)、
設計判断 (ADR) は [docs/decisions/](docs/decisions/) を参照。
