---
type: ADR
title: Database Schema Decisions
status: Accepted
timestamp: 2025-04-16
tags: []
---
# ADR 0002: Database Schema Decisions

## Context

SQLite と SQLAlchemy ORM を用いたスキーマ設計において、外部タグ DB(`genai-tag-db-tools`)との統合方式およびアノテーション履歴の保持方針を決定する必要があった。

## Decision

1. **UNIQUE 制約を適用しない**: `tags`、`captions`、`scores`、`ratings` の各テーブルでは、`(image_id, model_id)` の組み合わせに UNIQUE 制約を設けない。
2. **`tag_id` に外部キー制約を設けない**: `tags.tag_id` は概念上、外部の `tag_db` を参照するが、外部キー制約(FK 制約)は設定せず `ATTACH DATABASE` 経由で結合する。
3. **セッション管理**: コンテキストマネージャによるメソッド単位のセッション(`with self.session_factory() as session:`)を採用する。

## Rationale

- 同一画像に対して異なる時点で生成されたアノテーション結果をすべて保存でき、履歴を保持できる。
- SQLite では別データベースファイルである `tag_db` に対して外部キー制約を直接設定できない。
- コンテキストマネージャを用いることで、トランザクションの原子性とスレッド安全性を自動的に確保できる。

## Consequences

- アノテーションの全履歴が保持される(ストレージ使用量の増加はトレードオフとなる)。
- Tag DB との結合は `ATTACH DATABASE` と `JOIN` によって実現する。
- Worker 間でセッションを共有できないため、Worker ごとに独立したセッションを使用する必要がある。

**ディレクトリ構成:**

```
src/lorairo/database/
├── schema.py       # SQLAlchemyモデル定義
├── db_repository.py
├── db_manager.py
├── db_core.py
└── migrations/
```

## Supplement: rating の upsert 方針 (2026-06-07, Issue #673)

本 ADR は「`tags`、`captions`、`scores`、`ratings` テーブルで UNIQUE 制約を設けない」と定めている。ただし、これは DB スキーマとして履歴保持を許容するという宣言であり、Repository 実装が常に履歴を保持するという意味ではない。

**`rating` は別レイヤーの判断として、`(image_id, model_id)` キーの現在値(最新値優先)で upsert する。**

- `AnnotationRepository._save_ratings()` は、同一の `image_id` と `model_id` を持つ既存行があれば `UPDATE` し、なければ `INSERT` する。複数行が蓄積される `tags` や `captions` とは異なり、`rating` は正規の現在値が SSoT として意味を持つ(ADR 0031 §6、Amendment 2026-06-07 §4)。
- この方針は UNIQUE 制約なしのスキーマと矛盾しない。UNIQUE 制約を設けないことで重複行も許容できる一方、Repository 側では最新値のみを保持する設計を選択している。
- `tags` と `captions` は引き続き複数行による履歴保持を基本方針とし、upsert 運用は `rating` のみの例外とする。

重複送信時の挙動については、ADR 0031 Amendment 2026-06-07 を参照すること。
