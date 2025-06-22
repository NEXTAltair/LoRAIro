# 設定管理 仕様書

## 1. 概要

本ドキュメントは、`lorairo` アプリケーションにおける設定ファイルの読み込み、デフォルト値の管理、および関連する処理の仕様を定義する。

## 2. 設定ファイルの場所と形式

-   **設定ファイルパス:** `config/lorairo.toml` (プロジェクトルートからの相対パス)
-   **形式:** TOML (Tom's Obvious, Minimal Language)

## 3. 設定の読み込みとデフォルト値

-   **読み込み処理:** 設定はアプリケーション起動時などに `src/lorairo/utils/config.py` の `get_config()` 関数によって読み込まれる。
-   **デフォルト値の定義:** アプリケーションの基本的なデフォルト設定値は、`src/lorairo/utils/config.py` 内の `DEFAULT_CONFIG` ディクショナリで定義されている。
-   **設定のマージ:**
    1.  `get_config()` はまず `DEFAULT_CONFIG` のディープコピーを内部的に保持する。
    2.  次に `config/lorairo.toml` ファイルを読み込む。
    3.  `config/lorairo.toml` に存在する設定値で `DEFAULT_CONFIG` の値を上書き（ディープマージ）する。ただし、`config/lorairo.toml` の値が空文字列 (`""`) の場合は上書きしない。
    4.  最終的にマージされた設定ディクショナリがアプリケーション全体で使用される。

## 4. 設定項目

主要な設定項目とそのデフォルト値については `src/lorairo/utils/config.py` の `DEFAULT_CONFIG` を参照すること。

-   **`directories`:** 各種ファイルの保存先ディレクトリパス
    -   `database`: データベースファイル (`image_database.db`) の保存ディレクトリ
    -   `dataset`: データセット画像のデフォルトディレクトリ
    -   他
-   **`database`:** データベース関連の設定
    -   `image_db_filename`: 画像データベースのファイル名
    -   `tag_db_package`: タグDB (`tags_v4.db`) を含むPythonパッケージ名 (importlib.resourcesで使用)
    -   `tag_db_filename`: タグDBのファイル名
-   **`image_processing`:** 画像処理関連の設定
-   **`log`:** ログ設定
-   他

## 5. 注意点

-   設定ファイルが存在しない場合や、必須セクション (`directories`, `image_processing`) が欠けている場合は、`get_config()` がエラーを送出する。
-   設定ファイルの変更を反映するには、通常アプリケーションの再起動が必要となる。