# Decision Log

This file records architectural and implementation decisions using a list format.
2025-04-14 03:00:00 - Log of updates made.

* [2025-04-14 03:26:14] - `uv sync` コマンド等で依存関係を管理
* [2025-04-14 03:27:12] - ソースコードを `src` ディレクトリに配置
* [2025-04-16 13:08:01] - データベース層の SQLAlchemy 移行とスキーマ変更が完了。今後の作業を進める際は、必ず `docs/specs` と `docs/Plan` ディレクトリに保存された仕様書および計画書を参照すること。

## Decision

* [2025-04-14 03:26:14] - uv をパッケージマネージャーとして採用
* [2025-04-14 03:27:12] - プロジェクト構成を src/lorairo 配下に整理
* [2025-04-14 11:15:03] - ファイル作成はAIが行わず、ユーザーに操作を依頼する原則を採用
* [2025-04-14 12:05:10] - AIアノテーション機能 (タグ/キャプション/スコア生成) を `lorairo` 本体から削除し、`image-annotator-lib` に委譲
* [2025-04-14 12:20:38] - データベース管理機能を標準 `sqlite3` から SQLAlchemy に変更

## Rationale

* [2025-04-14 03:26:14] - 速度と使いやすさ
* [2025-04-14 03:27:12] - 標準的なPythonプロジェクト構造への準拠
* [2025-04-14 11:15:03] - AIによる意図しないファイルシステム変更リスクの低減、ユーザーによる操作の明確化
* [2025-04-14 12:05:10] - 関心の分離、`lorairo` 本体の責務をデータセット管理と画像処理に集中、ライブラリの独立性向上
* [2025-04-14 12:20:38] - ORM導入によるコードの可読性・保守性向上、`genai-tag-db-tools` との技術スタック統一

## Implementation Details

* [2025-04-14 11:15:03] - AIはファイル作成が必要な場合、ユーザーに依頼するメッセージを生成する
* [2025-04-14 12:05:10] - `lorairo` 内の `ImageAnalyzer`, `APIClientFactory` 等の関連コードを削除し、`image-annotator-lib` のインターフェースを呼び出すように変更
* [2025-04-14 12:20:38] - `src/lorairo/database/database.py` を SQLAlchemy ベースのスキーマ定義とリポジトリクラスに置き換える
* [2025-04-16 13:08:01] - SQLAlchemy 移行完了に伴い、関連するデータベースアクセスコードを更新。Alembicによるマイグレーションスクリプト (`src/lorairo/database/migrations/`) を作成・適用済み。

* [2025-04-16 15:11:00] - ConfigManager のリファクタリング方針を決定 (docs/Plan/refactoring_plan.md 参照)

## Decision

* [2025-04-16 15:11:00] - `ConfigManager` の責務を動的なGUI設定状態の保持に限定し、クラス名を `AppSettings` 等に変更。`dataset_image_paths` を分離。インスタンス管理はシングルトン維持(案D)またはDI導入(案E)を検討。

## Rationale

* [2025-04-16 15:11:00] - `ConfigManager` の責務が曖昧で、設定値以外の状態 (`dataset_image_paths`) を保持しているため、責務分離の原則に反する。シングルトンパターンのテスト容易性の問題を解消するためDI導入も検討。

## Implementation Details

* [2025-04-16 15:11:00] - `ConfigManager` を改名し、`dataset_image_paths` 関連ロジックを削除。`dataset_image_paths` は `MainWindow` (案B) または `DatasetSelector` (案A) で管理。インスタンス管理方法 (案D or E) を選択し実装。設定保存メソッドを追加。詳細は `docs/Plan/refactoring_plan.md` のチェックリスト参照。

## 2024-07-13: 設定管理リファクタリング (ConfigManager -> ConfigurationService)

- **決定事項:**
    - 旧 `ConfigManager` (シングルトン) を廃止し、設定の読み書き責務を持つ `ConfigurationService` を新設した。
    - `ConfigurationService` は `MainWindow` でインスタンス化し、依存性注入 (DI) パターンで `ConfigurationWindow` (旧 `SettingsWidget`) に渡すようにした。
    - GUI層のクラス名 `SettingsWidget` および関連ファイル名を `ConfigurationWindow` に変更した。（UIファイル含む）
    - `ConfigManager` が保持していた `dataset_image_paths` は `MainWindow` が直接管理するように変更した。
    - `ConfigurationWindow` の基本的なユニットテストを作成した。
- **理由:**
    - `ConfigManager` のシングルトン実装はテスト容易性を低下させていたため、DIパターンを採用したかった。
    - `ConfigManager` が設定値以外の状態 (`dataset_image_paths`) を保持しており、単一責任の原則に反していた。
    - クラス名 `SettingsWidget` よりも `ConfigurationWindow` の方が、扱う内容（アプリケーションの構成設定）をより正確に表すと判断したため、サービス層 (`ConfigurationService`) と合わせて命名を統一した。
    - リファクタリングに伴い、テストカバレッジを向上させるためユニットテストを追加した。
- **影響範囲:**
    - `src/lorairo/gui/window/main_window.py`
    - `src/lorairo/gui/window/configuration_window.py` (旧 `settings.py`)
    - `src/lorairo/gui/designer/ConfigurationWindow.ui` (旧 `SettingsWidget.ui`)
    - `src/lorairo/gui/designer/ConfigurationWindow_ui.py` (旧 `SettingsWidget_ui.py`)
    - `src/lorairo/services/configuration_service.py` (新規作成)
    - `tests/gui/window/test_configuration_window.py` (新規作成)
    - `docs/Plan/` 配下の計画書、チェックリスト
- **残課題:**
    - 他のウィジェット (`ImageEditWidget` など) で `ConfigurationService` を利用するよう修正が必要。
    - `dataset_image_paths` の `MainWindow` での管理方法が最適か、他の状態管理方法 (案A, C) も含めて継続検討の余地あり。
    - `ConfigurationService` の設定ファイルパス決定ロジック、エラーハンドリングの改善。
    - 関連する仕様書 (`configuration_management.md`, `gui_interface.md`) の更新。

## 2024-07-14: ImageEditWidget リファクタリング (ロジック分離)

- **決定事項:**
    - `ImageEditWidget` からビジネスロジック (設定アクセス、画像処理、アノテーション表示) を分離した。
    - 設定値へのアクセスは `ConfigurationService` の公開メソッド経由に変更した。
    - 画像処理 (DB操作、ファイル保存含む) ロジックを新設した `ImageProcessingService` (`src/lorairo/services/`) に移譲した。
    - アノテーション表示のためのデータ取得ロジックを新設した `ImageTextFileReader` (`src/lorairo/annotations/`) に移譲した。
    - 当初 `AnnotationService` として作成したクラス名を、ファイルからの読み込みという役割を明確にするため `ImageTextFileReader` に変更し、`annotations` ディレクトリに移動した。
- **理由:**
    - GUI ウィジェットとビジネスロジックの責務を明確に分離し、単一責任の原則 (SRP) に従うため。
    - `ConfigurationService` の内部実装への直接アクセス (`_config`) を排除し、カプセル化を強化するため。
    - 画像処理やアノテーション取得のロジックを再利用可能にし、テスト容易性を向上させるため。
    - クラス名を実態に合わせてより分かりやすくするため。
- **影響範囲:**
    - `src/lorairo/gui/window/edit.py`
    - `src/lorairo/gui/window/main_window.py`
    - `src/lorairo/services/image_processing_service.py` (新規作成)
    - `src/lorairo/annotations/image_text_reader.py` (新規作成、旧 `services/annotation_service.py` から移動・改名)
    - `src/lorairo/services/configuration_service.py` (メソッド追加)
    - `docs/Plan/` 配下の計画書、チェックリスト
- **残課題:**
    - `ImageProcessingService` 内のエラーハンドリングの詳細化 (UIへのフィードバックなど)。
    - `ImageTextFileReader` へのファイルベース (.txt/.json) アノテーション読み込みロジックの統合 (計画書に TODO 記載済み)。
    - `ImageEditWidget` のユニットテスト作成/更新。