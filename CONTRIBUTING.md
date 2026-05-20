# Contributing to LoRAIro

LoRAIro への貢献ガイド。詳細は各リンク先のドキュメントに集約しています。

## 開発環境セットアップ

```bash
uv sync --dev          # 依存関係をインストール (dev 含む)
./scripts/setup.sh     # サブモジュールを含むセットアップ
```

仮想環境ルール・開発コマンドの詳細は [CLAUDE.md](CLAUDE.md) を参照。

## ブランチ・PR 運用

- ブランチ命名・ワークツリー運用: [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md)
- `main` への直接作業は禁止。Issue / タスク毎に専用ブランチを切る。

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
