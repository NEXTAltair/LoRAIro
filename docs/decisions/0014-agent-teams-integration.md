---
type: ADR
title: Agent Teams Integration
status: Accepted
timestamp: 2026-04-09
tags: []
---
# ADR 0014: Agent Teams Integration

## Context

Claude Code v2.1.32 以降の実験的機能である **Agent Teams** を LoRAIro の開発ハーネスに統合する。Agent Teams では、複数の Claude Code インスタンスが「チームリード」と「チームメート」として協調動作する。これにより、並列レビュー・デバッグ・独立モジュールの実装を効率化できる。

統合調査の過程で、既存エージェント 8 件の frontmatter に非標準フィールド(`allowed-tools`)が使われていることも判明した。この影響により、ツール制限が実質的に無効化されていた。

## Decision

1. **環境変数の設定**
   `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` を `.claude/settings.json` の `env` と `.devcontainer/devcontainer.json` の `remoteEnv` に追加する。

2. **frontmatter の修正**
   既存エージェント 8 件の非標準フィールドを公式仕様へ修正する。
   - `allowed-tools` を公式フィールド名の `tools` に変更する。
   - `context: fork/main` を削除する(スキル用フィールドであり、エージェント定義では機能しない)。
   - `parallel-safe: true/false` を削除する(非標準フィールドであり、効果がない)。

3. **新エージェントの追加**
   テスト実行専門の `test-runner` と、スキーマ検査専門の `db-schema-reviewer` を追加する。

4. **フックの統合**
   `TeammateIdle`、`TaskCreated`、`TaskCompleted` の 3 イベントを、単一の統合スクリプト `hook_teammate_monitor.py` で処理する。これはフックの軽量化方針(13 個から 3 個への集約)に沿った構成である。

5. **品質ゲートの導入**
   `TaskCompleted` フックで、`git diff` の変更ファイルのみを対象に `ruff check` を実行する。リポジトリ全体のスキャンは負荷が高いため、変更ファイルに限定する。既定の動作は警告出力のみとし、タスクの差し戻しは行わない。

## Rationale

- **frontmatter 修正を同一 Issue に含めた理由**
  Agent Teams 導入前に修正しなければ、ツール制限が無効なままチームメートが全ツールへアクセスできてしまう。修正内容は純粋なフィールド名の変更であり、統合の前提条件として同時に実施するのが適切である。

- **フック統合スクリプトを採用した理由**
  直近のフック整理方針(13 個から 3 個への集約)に従い、チームメート監視という同一関心事に属する 3 イベントを 1 ファイルにまとめた。`hook_event_name` フィールドで処理を振り分けることで、保守性を確保している。

- **in-process モードを採用した理由**
  Dev Container 環境に `tmux` が未インストールであるためである。in-process モードはどのターミナルでも動作し、追加のセットアップを必要としない。

- **`TaskCompleted` の `ruff` 実行を変更ファイル限定にした理由**
  リポジトリ全体への `ruff` 実行には数十秒かかり、チームメートの応答を大きく遅延させる。変更ファイルに限定すれば、数秒以内に完了する。

## Consequences

- Dev Container の再ビルド後から、Agent Teams 機能が自動的に有効になる。
- 既存エージェントのツール制限が正しく機能するようになる(例:`security-reviewer` は `Read`、`Grep`、`Glob` のみに制限される)。
- チームメートのアイドル時・タスク作成時・タスク完了時に、品質ゲートが自動で実行される。
- トークン消費量はチームメート数に比例して増加するため、単純な作業には引き続きサブエージェントを使う。
- 実験的機能であるため、仕様変更が発生しても環境変数を削除するだけで無効化できる。
