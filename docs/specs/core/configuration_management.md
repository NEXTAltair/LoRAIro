# 設定管理 仕様書

## 1. 概要

本ドキュメントは、`lorairo` アプリケーションにおける設定ファイルの読み込み、初回生成、デフォルト値の管理、および関連処理の仕様を定義する。

## 2. 設定ファイルの場所と形式

- **設定ファイルパス**: `config/lorairo.toml`(プロジェクトルートからの相対パス)
- **形式**: TOML(Tom's Obvious, Minimal Language)

## 3. 設定の読み込みとデフォルト値

- **読み込み処理**: 設定は `src/lorairo/utils/config.py` の `get_config()` 関数によって読み込む。`get_config()` は設定ファイルを作成しない。
- **初回生成**: アプリケーション起動時の `ConfigurationService` 初期化では、`ensure_config_file()` を呼び出す。`config/lorairo.toml` が存在しない場合、ユーザー編集対象の設定ファイルを初回生成する。
- **デフォルト値の定義**: アプリケーションの実行時デフォルト設定値は、`src/lorairo/utils/config.py` 内の `DEFAULT_CONFIG` 辞書で定義する。
- **設定のマージ手順**:
  1. `get_config()` は、まず `DEFAULT_CONFIG` のディープコピーを内部に保持する。
  2. 次に `config/lorairo.toml` ファイルを読み込む。
  3. `config/lorairo.toml` に存在する設定値で `DEFAULT_CONFIG` の値を上書き(ディープマージ)する。空文字列(`""`)もユーザーの明示値として上書きする。
  4. 最終的にマージされた設定辞書をアプリケーション全体で使用する。

## 4. 設定項目

主要な設定項目とデフォルト値は、`src/lorairo/utils/config.py` の `DEFAULT_CONFIG` を参照する。初回生成される `config/lorairo.toml` にはユーザー編集対象の項目のみを含め、実行時の内部デフォルト値は `DEFAULT_CONFIG` から補完する。

## 5. 注意点

- 設定ファイルが存在しない場合、`get_config()` は `DEFAULT_CONFIG` ベースの設定を返し、ファイル作成は行わない。
- 設定ファイルの初回生成に失敗した場合、`ConfigurationService` の初期化は失敗する。
- 設定ファイルの変更を反映するには、通常アプリケーションの再起動が必要である。
