# ADR 0014: Agent Teams Integration

- **日付**: 2026-04-09
- **ステータス**: Accepted

## Context

Claude Code v2.1.32+ の実験的機能 **Agent Teams** を LoRAIro 開発ハーネスに統合する。
Agent Teams は複数の Claude Code インスタンスが「チームリード + チームメート」として協調動作し、
並列レビュー・デバッグ・独立モジュール実装の効率化を目的とする。

統合調査の過程で、既存エージェント8件の frontmatter に非標準フィールド（`allowed-tools`）が
使われており、ツール制限が実質無効化されていることも判明した。

## Decision

1. **環境変数**: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` を `.claude/settings.json` の `env` と
   `.devcontainer/devcontainer.json` の `remoteEnv` に追加した。

2. **frontmatter 修正**: 既存エージェント8件の非標準フィールドを公式仕様に修正した。
   - `allowed-tools` → `tools`（公式フィールド名）
   - `context: fork/main` 削除（skill 用フィールド、agent 定義では無意味）
   - `parallel-safe: true/false` 削除（非標準、効果なし）

3. **新エージェント**: `test-runner`（テスト実行専門）と `db-schema-reviewer`（スキーマ検査専門）を追加した。

4. **フック**: TeammateIdle・TaskCreated・TaskCompleted の3イベントを **1つの統合スクリプト**
   `hook_teammate_monitor.py` で処理する。軽量化の方針（13個→3個）に準拠。

5. **品質ゲート**: TaskCompleted フックで `git diff` の変更ファイルのみ ruff check を実行。
   全体スキャンは重すぎるため変更ファイル限定とした。デフォルトは警告のみ（差し戻しなし）。

## Rationale

- **frontmatter 修正を同一 Issue に含めた理由**: Agent Teams 導入前に修正しないと、ツール制限が
  無効なままチームメートが全ツールにアクセスできる状態になる。修正は純粋なフィールド名の変更であり、
  Agent Teams 統合の前提条件として適切。

- **フック統合スクリプト採用の理由**: 直近の hooks 整理（13個→3個）の方針に従い、同一関心事
  （チームメート監視）に属する3イベントを1ファイルに統合した。`hook_event_name` フィールドで
  ルーティングすることで保守性を確保。

- **in-process モード採用の理由**: devcontainer 環境に tmux が未インストールのため。
  in-process モードはどのターミナルでも動作し、追加セットアップ不要。

- **TaskCompleted の変更ファイル限定 ruff の理由**: 全体 ruff は数十秒かかり、チームメートの
  レスポンスを著しく遅延させる。変更ファイル限定であれば数秒以内に完了する。

## Consequences

- Agent Teams 機能が devcontainer 再ビルド時から自動的に有効になる
- 既存エージェントのツール制限が正しく機能するようになる（security-reviewer は Read/Grep/Glob のみに制限）
- チームメートのアイドル・タスク作成・完了に対して品質ゲートが自動実行される
- トークン消費がチームメート数に比例して増加するため、単純作業には subagent を継続使用する
- 実験的機能のため、仕様変更時は env var を削除するだけで無効化可能
