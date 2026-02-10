# Session: SQLAlchemy使用状況レポート (LoRAIro + genai-tag-db-tools)

**Date**: 2026-02-06
**Branch**: feature/annotator-library-integration
**Status**: completed (調査・分析のみ、コード変更なし)

---

## 実施内容

両パッケージのSQLAlchemy使用状況を包括的に調査し、比較レポートを作成した。

### 調査対象ファイル
- LoRAIro: `db/schema.py`, `db/db_core.py`, `db/db_repository.py`, `db/db_manager.py`, `migrations/env.py`
- genai-tag-db-tools: `db/schema.py`, `db/runtime.py`, `db/repository.py`, `db/query_utils.py`, `core_api.py`, `services/tag_register.py`

## 主要な発見事項

### 1. Query APIの不統一
- **LoRAIro**: SQLAlchemy 2.0 `select()` API を全面使用
- **genai-tag-db-tools**: レガシー `session.query()` API を全面使用
- 同一プロジェクト内で2つのAPIスタイルが混在している

### 2. スキーマ定義は統一済み
- 両パッケージとも `DeclarativeBase` + `Mapped` + `mapped_column` (2.0スタイル) を使用
- テーブル名の命名規則のみ異なる（LoRAIro: 小文字 / tag-db: 大文字）

### 3. genai-tag-db-tools特有の設計
- CQRS風の読み書き分離 (`TagReader` + `TagRepository`)
- マルチDB設計 (3ベースDB + 1ユーザーDB)
- `MergedTagReader` による5パターンのマージ戦略
- `TagSearchPreloader` による手動N+1対策（LoRAIroの joinedload/selectinload とは異なるアプローチ）

### 4. エンジン・セッション管理
- LoRAIro: モジュールレベル単一ファクトリ + `get_db_session()` contextmanager
- tag-db: グローバル変数によるデュアルファクトリ（ベース/ユーザー）

## 設計意図・次のステップ

### genai-tag-db-tools の session.query() → select() 移行を検討中
- **対象**: repository.py (~50箇所), query_utils.py (~20箇所), runtime.py (1箇所)
- **移行パターン**:
  - `session.query(Model).filter(...)` → `session.execute(select(Model).where(...)).scalars()`
  - `session.query(Model.col)` → `session.execute(select(Model.col))`
  - `session.query(func.max(...)).scalar()` → `session.execute(select(func.max(...))).scalar()`
  - `session.get(Model, pk)` → そのまま（2.0でも有効）
- **リスク**: テストの広範な影響確認が必要
- **ステータス**: 未着手（Plan Mode で詳細設計後に実施予定）

## 未完了・次のステップ
- [ ] genai-tag-db-tools の select() API 移行計画をPlan Modeで策定
- [ ] 移行後のテスト網羅性を確認（genai-tag-db-tools側のテスト状況把握）
- [ ] bulk_insert_mappings の代替（2.0推奨パターン）を調査
