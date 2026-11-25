# Configuration Service 仕様書

## 1. 概要

本ドキュメントは、アプリケーション層における設定管理サービス(`ConfigurationService`)の仕様を定義する。このサービスは、GUI 層(インターフェース層)と、設定ファイルの読み書きを担うコア層(`src/lorairo/utils/config.py`)との仲介役として機能する。

## 2. 責務

- **設定の準備と読み込み**: アプリケーション起動時にコア層の `ensure_config_file` を呼び出し、設定ファイル(`config/lorairo.toml`)が存在しない場合は生成したうえで読み込み、内部に保持する。
- **設定値の提供**: GUI 層や他のサービスからの要求に応じ、特定の設定値または設定全体を返す。
  - `get_setting(section, key, default)`: 指定したセクションとキーの設定値を取得する。
  - `get_all_settings()`: すべての設定情報を辞書として返す(内部状態の直接的な公開を避けるため、必要に応じて読み取り専用ビューの提供を検討する)。
  - 特定用途向けのゲッターメソッド(例:`get_image_processing_config()`、`get_output_directory()`)を提供する。
- **設定値の更新**: GUI 層からのユーザー操作などに基づき、内部に保持している設定値を更新する。
  - `update_setting(section, key, value)`: 指定したセクションとキーの値を更新する。
  - 特定用途向けのセッターメソッド(例:`update_image_processing_setting(key, value)`)を提供する。
- **設定の保存**: 現在の内部設定を、コア層の `write_config_file` を使ってファイルへ保存する。
  - `save_settings(target_path)`: 指定したパス、または初期化時に設定されたパスへ保存する。

## 3. 依存関係

- `src/lorairo/utils/config.py`: 設定ファイルの読み込み(`get_config`)、初回生成(`ensure_config_file`)、書き込み(`write_config_file`)を担うコア機能。
- `src/lorairo/utils/log.py`: ログ出力機能。

## 4. 注意点

- サービスインスタンスは、原則としてアプリケーション起動時に DI コンテナなどを介して生成し、必要なコンポーネントへ注入する設計を想定している(現行実装との差異がないか要確認)。
- 設定ファイルの形式や具体的なキー名は、コア層の仕様(`docs/specs/core/configuration_management.md`)を参照する。
