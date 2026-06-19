---
type: ADR
title: Database Schema Decisions
status: Accepted
timestamp: 2025-04-16
tags: []
---
# ADR 0002: Database Schema Decisions

## Context

SQLite + SQLAlchemy ORM でのスキーマ設計において、外部タグ DB (genai-tag-db-tools) との統合方式と、アノテーション履歴の保持方針を決定する必要があった。

## Decision

1. **UNIQUE 制約を適用しない**: `tags`, `captions`, `scores`, `ratings` テーブルで `(image_id, model_id)` の組み合わせに UNIQUE 制約を設けない。
2. **tag_id に外部キー制約なし**: `tags.tag_id` は概念的に外部 tag_db を参照するが FK 制約は設定しない（ATTACH DATABASE 経由）。
3. **セッション管理**: Context マネージャによるメソッド単位セッション (`with self.session_factory() as session:`) を採用。

## Rationale

- 同一画像への異なる時点でのアノテーション結果を全て保存できる（履歴保持）
- 外部 DB (tag_db) への FK 制約は SQLite 間で直接設定不可
- Context マネージャで原子性・スレッドセーフティを自動確保

## Consequences

- アノテーションの全履歴が保持される（ストレージ増加はトレードオフ）
- Tag DB との結合は ATTACH DATABASE + JOIN で実現
- Worker 間でセッション共有不可（Worker 毎に独立セッション必須）

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

本 ADR は「`tags`, `captions`, `scores`, `ratings` テーブルで UNIQUE 制約を設けない」と定めているが、
これは「DB スキーマが履歴保持を許容する」という宣言であり、Repository 実装が常に履歴を保持するという
意味ではない。

**rating は別レイヤーの判断として `(image_id, model_id)` キーの現在値 (latest win) で upsert する。**

- `AnnotationRepository._save_ratings()` は、同一 `image_id + model_id` の既存 row を UPDATE、
  なければ INSERT する。複数 row が積み重なる tags/captions とは異なり、rating は canonical な
  現在値が SSoT として意味を持つ (ADR 0031 §6、Amendment 2026-06-07 §4)。
- この方針は UNIQUE 制約なしのスキーマと矛盾しない。UNIQUE 制約がなければ重複 row も許容できるが、
  Repository が応用として「最新値のみ保持」する設計を選んでいる。
- tags/captions は引き続き履歴保持 (複数 row) が基本方針。rating だけの例外的 upsert 運用。

重複 submit 時の挙動については ADR 0031 Amendment 2026-06-07 を参照。