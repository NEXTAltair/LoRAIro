# Decision Log

This file records architectural and implementation decisions using a list format.
2025-04-14 03:00:00 - Log of updates made.

* [2025-04-14 03:26:14] - `uv pip install` コマンド等で依存関係を管理
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