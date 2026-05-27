# 設定管理 仕様書

## 1. 概要

本ドキュメントは、`lorairo` アプリケーションにおける設定ファイルの読み込み、初回生成、デフォルト値の管理、および関連する処理の仕様を定義する。

## 2. 設定ファイルの場所と形式

-   **設定ファイルパス:** `config/lorairo.toml` (プロジェクトルートからの相対パス)
-   **形式:** TOML (Tom's Obvious, Minimal Language)

## 3. 設定の読み込みとデフォルト値

-   **読み込み処理:** 設定は `src/lorairo/utils/config.py` の `get_config()` 関数によって読み込まれる。`get_config()` はファイル作成を行わない。
-   **初回生成:** アプリケーション起動時の `ConfigurationService` 初期化では `ensure_config_file()` により、`config/lorairo.toml` が存在しない場合にユーザー編集対象の設定ファイルを生成する。
-   **デフォルト値の定義:** アプリケーションの実行時デフォルト設定値は、`src/lorairo/utils/config.py` 内の `DEFAULT_CONFIG` ディクショナリで定義されている。
-   **設定のマージ:**
    1.  `get_config()` はまず `DEFAULT_CONFIG` のディープコピーを内部的に保持する。
    2.  次に `config/lorairo.toml` ファイルを読み込む。
    3.  `config/lorairo.toml` に存在する設定値で `DEFAULT_CONFIG` の値を上書き（ディープマージ）する。空文字列 (`""`) もユーザーの明示値として上書きする。
    4.  最終的にマージされた設定ディクショナリがアプリケーション全体で使用される。

## 4. 設定項目

主要な設定項目とそのデフォルト値については `src/lorairo/utils/config.py` の `DEFAULT_CONFIG` を参照すること。初回生成される `config/lorairo.toml` はユーザー編集対象の項目だけを含み、実行時内部デフォルトは `DEFAULT_CONFIG` から補完される。

## 5. 注意点

-   設定ファイルが存在しない場合、`get_config()` は `DEFAULT_CONFIG` ベースの設定を返し、ファイル作成は行わない。
-   設定ファイルの初回生成に失敗した場合、`ConfigurationService` 初期化は失敗する。
-   設定ファイルの変更を反映するには、通常アプリケーションの再起動が必要となる。
