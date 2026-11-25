---
type: ADR
title: Legacy Tag DB Cleanup
status: Accepted
timestamp: 2026-01-02
tags: []
---
# ADR 0013: Legacy Tag DB Cleanup

## Context

`db_core.py` には、旧 Tag DB アーキテクチャへの参照が残存していた。

- `TAG_DB_PACKAGE` および `TAG_DB_FILENAME`:`genai_tag_db_tools.data` パッケージから DB を読み込む旧方式の定数
- `get_tag_db_path()`:`importlib.resources` でパッケージ内の DB パスを解決する関数
- `attach_tag_db_listener()`:SQLAlchemy のイベントリスナーで Tag DB をアタッチする関数

現在のアーキテクチャは、`ensure_databases()` による HuggingFace からのダウンロードと、`init_user_db()` による `user_tags.sqlite` の作成へすでに移行済みである。

## Decision

以下のレガシー定数および関数を完全に削除し、コード内のコメントに削除理由を明記する。

- `TAG_DB_PACKAGE` および `TAG_DB_FILENAME` 定数を削除する。
- `get_tag_db_path()` 関数を削除する。
- `attach_tag_db_listener()` 関数を削除する。

## Rationale

代替となる `genai-tag-db-tools` の公開 API(`search_tags()`、`register_tag()`、`MergedTagReader`)がすでに完全に機能している。不要なレガシーコードを残すと保守時の混乱を招くため、段階的廃止は行わず即時に削除する。

## Consequences

- `db_core.py` から旧アーキテクチャへの参照が完全に除去される。
- Base DB は、`ensure_databases()` により HuggingFace から 3 つの DB ファイルをダウンロードして利用する。
- User DB は、`init_user_db()` によりプロジェクトディレクトリ内に `user_tags.sqlite` を作成して利用する。
- `format_id 1000+` の予約領域により、ユーザータグと Base DB のタグが衝突しない設計を維持する。
