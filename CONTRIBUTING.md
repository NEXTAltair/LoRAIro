# LoRAIro への貢献ガイド

LoRAIro の開発に参加するための案内です。詳細な規約や手順は各ドキュメントに集約しています。

## 開発環境セットアップ

```bash
make setup     # サブモジュール(local_packages/*)の取得と開発依存のインストール(uv sync --dev)
```

仮想環境のルールや開発コマンドの詳細は [CLAUDE.md](CLAUDE.md) を参照してください。

## ブランチ・PR 運用

- ブランチ命名とワークツリー運用については [.claude/rules/git-workflow.md](.claude/rules/git-workflow.md) を参照してください。
- アプリコード(`src/`、`tests/`、スキーマやマイグレーション)は `main` ブランチで直接作業せず、Issue やタスクごとに専用ブランチを切ってください。
- ドキュメントや開発ツール周りの作業に関する例外規定は、[.claude/rules/git-workflow.md](.claude/rules/git-workflow.md) の「worktree + PR を要さない例外」を参照してください。

## コーディング規約

型ヒント、docstring、命名規則などの詳細は [.claude/rules/coding-style.md](.claude/rules/coding-style.md) を参照してください。

## テスト

テスト戦略、実行方法、CI と同等のテストフィルタについては [docs/testing.md](docs/testing.md) を参照してください。

## リリース手順

リリース前には、[docs/release-checklist.md](docs/release-checklist.md) の手動チェックリストをすべて確認してください。

## その他の資料

- 開発ワークフロー全体: [docs/development-workflow.md](docs/development-workflow.md)
- 設計判断(ADR): [docs/decisions/](docs/decisions/)
