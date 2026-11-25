---
type: ADR
title: CLI におけるタグ DB の遅延初期化
status: Accepted
timestamp: 2026-06-01
tags: []
---
# ADR 0050: CLI におけるタグ DB の遅延初期化

## 背景

`ServiceContainer` はコンストラクタ実行時に genai-tag-db-tools のデータベースを初期化していた。そのため、`lorairo-cli status`、`project list`、`images list --limit 5` のような読み取り専用 CLI コマンドでも、本来の処理の前に Hugging Face へ通信が発生していた。

`HF_TOKEN` が未設定の環境では、タグ管理を必要としないコマンドであっても、起動時のタグ DB 初期化に長い時間を要することがあった。

## 決定

`ServiceContainer` の構築処理は副作用を最小限に保つ。既定では genai-tag-db-tools のデータベースを初期化しない。

タグ DB の初期化は、外部タグ DB へのアクセスを実際に必要とする最初のサービス経路まで遅延させる。

- `ServiceContainer.tag_management_service`: `TagManagementService` を構築する直前に初期化する。
- `AnnotationRepository` のタグ ID 解決/登録処理: `MergedTagReader` を生成する直前に初期化する。

`ensure_tag_db_initialized()` は選択中の画像データベースパスを書き換えてはならない。`db_core.IMG_DB_PATH` / `DATABASE_URL` の管理責務はプロジェクト選択側にあり、タグ DB 初期化は genai-tag-db-tools のベース DB とユーザー DB の準備のみを担う。

## 影響

- 読み取り専用の CLI コマンドがタグ DB の初期化でブロックされなくなる。
- `lorairo-cli --help` と `version` は、引き続きサービス初期化の副作用を発生させない。
- タグ管理機能は、genai-tag-db-tools のユーザー DB API を利用する前に外部タグ DB を確実に初期化する。
- `AnnotationRepository` の構築コストは低いまま維持される。タグ ID 解決時には必要に応じて外部タグ DB サポートを初期化し、利用できない場合も従来どおりグレースフルデグラデーションを継続する。
- `set_active_project()` の後にタグ管理を開いても、プロジェクトルートの解決先が既定の画像データベースへリセットされなくなる。
