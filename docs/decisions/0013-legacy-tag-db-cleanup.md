# ADR 0013: Legacy Tag DB Cleanup

- **日付**: 2026-01-02
- **ステータス**: Accepted

## Context

`db_core.py` に旧 Tag DB アーキテクチャへの参照が残存していた:
- `TAG_DB_PACKAGE` / `TAG_DB_FILENAME` — genai_tag_db_tools.data パッケージから DB を読む古い方式
- `get_tag_db_path()` — importlib.resources でパッケージ内 DB を解決
- `attach_tag_db_listener()` — SQLAlchemy イベントリスナーで Tag DB をアタッチ

現在のアーキテクチャは `ensure_databases()` (HuggingFace ダウンロード) + `init_user_db()` (user_tags.sqlite 作成) に移行済み。

## Decision

レガシー関数・定数を完全削除し、注釈コメントで削除理由を明記:
- `TAG_DB_PACKAGE` / `TAG_DB_FILENAME` 定数削除
- `get_tag_db_path()` 関数削除
- `attach_tag_db_listener()` 関数削除

## Rationale

代替実装 (genai-tag-db-tools Public API: `search_tags()`, `register_tag()`, `MergedTagReader`) が完全に機能している。レガシーコードを残すと混乱を招くため即削除（段階的廃止は不要）。

## Consequences

- `db_core.py` からレガシー参照が完全に除去される
- Base DB: `ensure_databases()` で HuggingFace からダウンロード（3 DB files）
- User DB: `init_user_db()` で user_tags.sqlite を project ディレクトリに作成
- `format_id 1000+` 予約でユーザータグと Base DB のタグが衝突しない設計を維持
