# Configuration Service 仕様書

## 1. 概要

本ドキュメントは、アプリケーション層における設定管理サービス (`ConfigurationService`) の仕様を定義する。このサービスは、GUI層（インターフェース層）と設定ファイルの読み書きを行うコア層 (`src/lorairo/utils/config.py`) との間の仲介役となる。

## 2. 責務

-   **設定の読み込み:** アプリケーション起動時に設定ファイル (`config/lorairo.toml`) をコア層の関数 (`get_config`) を使用して読み込み、内部に保持する。
-   **設定値の提供:** GUI層や他のサービスからの要求に応じて、特定の設定値または全体の設定情報を返す。
    -   `get_setting(section, key, default)`: 指定されたセクションとキーの設定値を取得する。
    -   `get_all_settings()`: 全ての設定情報を辞書として返す。(注意: 内部状態の直接的な公開は避け、必要に応じて読み取り専用のビューを提供するなどの改善を検討)
    -   特定の用途に特化したゲッターメソッド (例: `get_image_processing_config()`, `get_output_directory()`) を提供する。
-   **設定値の更新:** GUI層からのユーザー操作などに基づき、内部に保持している設定値を更新する。
    -   `update_setting(section, key, value)`: 指定されたセクションとキーの値を更新する。
    -   特定の用途に特化したセッターメソッド (例: `update_image_processing_setting(key, value)`) を提供する。
-   **設定の保存:** 現在の内部設定情報を、コア層の関数 (`write_config_file`) を使用してファイルに保存する。
    -   `save_settings(target_path)`: 指定されたパス、または初期化時に指定されたパスに設定を保存する。

## 3. 依存関係

-   `src/lorairo/utils/config.py`: 設定ファイルの読み込み (`get_config`) と書き込み (`write_config_file`) を担当するコア機能。
-   `src/lorairo/utils/log.py`: ログ出力用。

## 4. 注意点

-   サービスインスタンスは、通常アプリケーション起動時にDIコンテナなどを介して生成され、必要なコンポーネントに注入されることを想定する。(現状の実装とは異なる可能性があるため要確認)
-   設定ファイルのフォーマットや具体的なキー名は、コア層の仕様 (`docs/specs/core/configuration_management.md`) を参照すること。