# ADR 0008: CLAUDE.md Resilience Architecture

- **日付**: 2026-01-01
- **ステータス**: Accepted

## Context

CLAUDE.md が度重なる設計変更により陳腐化し、30+ の重大な不正確さが蓄積していた（存在しないファイルパス参照、サービス数の誤記 5件 vs 29件実在など）。

## Decision

**3層ドキュメントアーキテクチャ**を採用:

| 層 | ファイル | 更新頻度 | 内容 |
|----|---------|---------|------|
| Layer 1 | `CLAUDE.md` | 四半期 | AI エージェント指向 + ワークフロー |
| Layer 2 | `docs/*.md` | 機能完成時 | 詳細な技術仕様 |
| Layer 3 | コード | リアルタイム | 常に正確な実装詳細 |

## Rationale

- **安定要素と変動要素の分離**: アーキテクチャ原則（年次変更）vs ファイルパス・サービスリスト（月次変更）
- `docs/services.md` (29サービス), `docs/integrations.md`, `docs/testing.md` を新規作成
- CLAUDE.md はポインタのみ持ち、詳細は `docs/` に委譲

## Consequences

- CLAUDE.md の更新は四半期レビューのみで済む
- 新サービス追加時は `docs/services.md` のみ更新
- AI エージェントは CLAUDE.md → docs/ の順で参照する
- ドキュメント間の重複が減少し drift が発生しにくい
