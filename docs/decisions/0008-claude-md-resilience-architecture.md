---
type: ADR
title: CLAUDE.md Resilience Architecture
status: Accepted
timestamp: 2026-01-01
tags: []
---
# ADR 0008: CLAUDE.md Resilience Architecture

## Context

度重なる設計変更により `CLAUDE.md` が陳腐化し、30 件以上の重大な不正確さが蓄積していた。存在しないファイルパスへの参照や、実在する 29 件のサービスを 5 件と誤記するなどの問題が発生していた。

## Decision

**3 層ドキュメントアーキテクチャ**を採用する。

| 層 | ファイル | 更新頻度 | 内容 |
|----|---------|---------|------|
| Layer 1 | `CLAUDE.md` | 四半期 | AI エージェント向け指針とワークフロー |
| Layer 2 | `docs/*.md` | 機能完成時 | 詳細な技術仕様 |
| Layer 3 | コード | リアルタイム | 常に正確な実装詳細 |

## Rationale

- **安定要素と変動要素の分離**: 年次でしか変わらないアーキテクチャ原則と、月次で変動するファイルパスやサービス一覧を分離する。
- 機能別の詳細仕様として、`docs/services.md`(29 サービス)、`docs/integrations.md`、`docs/testing.md` を新規作成した。
- `CLAUDE.md` には参照先へのポインタのみを記載し、詳細な仕様は `docs/` 配下に委譲する。

## Consequences

- `CLAUDE.md` の保守は四半期ごとのレビューのみで済むようになる。
- 新規サービスを追加した際は `docs/services.md` のみを更新すればよい。
- AI エージェントは `CLAUDE.md` から `docs/` の順に情報を参照する運用になる。
- ドキュメント間の重複が減り、実装との乖離が発生しにくくなる。
