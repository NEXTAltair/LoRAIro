# ADR 0002: Database Schema Decisions

- **日付**: 2025-04-16
- **ステータス**: Accepted

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
