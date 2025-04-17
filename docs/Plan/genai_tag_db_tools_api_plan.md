# genai-tag-db-tools 外部操作API追加計画

## 1. 目的

`genai-tag-db-tools` ライブラリに、外部アプリケーション (例: `lorairo`) からタグデータベース (`tags_v4.db` など) を安全かつ容易に操作するためのAPIを追加する。
特に、以下の機能を提供することを目指す。

-   タグ文字列から `tag_id` を検索する機能。
-   存在しないタグをタグデータベースに新規登録し、新しい `tag_id` を返す機能。
-   (将来的に) タグ情報の更新や削除など、その他の管理機能。

## 2. 背景

`lorairo` の `db_repository.py` (`_save_tags` メソッド) では、アノテーション保存時にタグ文字列に対応する `tag_id` が必要となる。
現状ではアタッチされたDBへの読み取りアクセスしか想定しておらず、新しいタグをタグデータベースに登録する標準的な方法が存在しない。
`genai-tag-db-tools` 自身がタグDBの管理責任を持つべきであり、外部アプリケーションが直接DBファイルを書き換えるのは避けるべきである。

## 3. 実装方針案

-   `genai-tag-db-tools` パッケージ内に新しいモジュール (例: `api.py` や `services.py`) を作成する。
-   タグの検索、新規登録を行う関数やクラスメソッドを定義する。
    -   内部で既存の `TagDatabaseManager` 等を利用する。
    -   データベース接続やセッション管理はライブラリ内部で完結させる。
-   `lorairo` 側からは、この新しいAPIをインポートして利用するように `db_repository.py` の `_get_or_create_tag_id_external` (またはそれを呼び出す箇所) を修正する。

## 4. タスクリスト

-   [ ] `genai-tag-db-tools` にAPI用モジュールの設計・作成。
-   [ ] タグ検索API (`find_tag_id(tag_string: str) -> int | None`) の実装。
-   [ ] 新規タグ登録API (`register_new_tag(tag_string: str) -> int`) の実装 (重複チェック含む)。
-   [ ] `lorairo` 側の `db_repository.py` から新しいAPIを利用するように修正。
-   [ ] 関連するテストコードの作成・更新。
-   [ ] ドキュメントの更新。
