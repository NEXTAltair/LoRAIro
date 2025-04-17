# ストレージ管理リファクタリング チェックリスト

## 1. `FileSystemUtils` (モジュール: `lorairo.utils.filesystem`)

-   [ ] `create_directory` 関数の実装
-   [ ] `copy_file` 関数の実装
-   [ ] `find_files_recursively` 関数の実装
-   [ ] `get_file_size` 関数の実装
-   [ ] `path_exists` 関数の実装
-   [ ] `ensure_unique_path` 関数の実装
-   [ ] `FileSystemUtils` の単体テスト作成

## 2. `ProjectStructure` (クラス: `lorairo.storage.structure.ProjectStructure`)

-   [ ] `__init__` コンストラクタの実装
-   [ ] `output_dir`, `target_resolution` プロパティの実装
-   [ ] `image_dataset_dir` メソッドの実装
-   [ ] `original_images_base_dir` メソッドの実装
-   [ ] `resolution_base_dir` メソッドの実装
-   [ ] `get_daily_subdir_path` メソッドの実装
-   [ ] `original_images_dir` メソッドの実装
-   [ ] `resized_images_dir` メソッドの実装
-   [ ] `batch_request_dir` メソッドの実装
-   [ ] `get_next_sequence_number` メソッドの実装
-   [ ] `ProjectStructure` の単体テスト作成

## 3. `ImageStorage` (クラス: `lorairo.storage.image.ImageStorage`)

-   [ ] `__init__` コンストラクタの実装 (依存性注入: `ProjectStructure`, `FileSystemUtils`)
-   [ ] `save_original_image` メソッドの実装
-   [ ] `save_processed_image` メソッドの実装
-   [ ] `get_image_info` メソッドの実装
-   [ ] `ImageStorage` の単体テスト作成

## 4. `BatchRequestProcessor` (クラス: `lorairo.storage.batch.BatchRequestProcessor`)

-   [ ] `__init__` コンストラクタの実装 (依存性注入: `ProjectStructure`, `FileSystemUtils`)
-   [ ] `create_batch_request_file` メソッドの実装
-   [ ] `append_request` メソッドの実装
-   [ ] `split_if_needed` メソッドの実装
-   [ ] `BatchRequestProcessor` の単体テスト作成

## 5. `DatasetExporter` (クラス: `lorairo.storage.export.DatasetExporter`)

-   [ ] `__init__` コンストラクタの実装 (依存性注入: `FileSystemUtils`)
-   [ ] `export_to_txt` メソッドの実装
-   [ ] `export_to_json` メソッドの実装
-   [ ] `DatasetExporter` の単体テスト作成

## 6. `ConfigPersistence` (モジュール: `lorairo.config.persistence` など)

-   [ ] `save_toml_config` 関数の実装/確認
-   [ ] `load_toml_config` 関数の実装/確認
-   [ ] 既存の設定管理モジュールとの統合 (必要に応じて)
-   [ ] `ConfigPersistence` 関連のテスト作成/確認

## 7. `FileSystemManager` のアダプター化 (一時対応)

-   [ ] `FileSystemManager._create_directory` を `FileSystemUtils.create_directory` 呼び出しに置換
-   [ ] `FileSystemManager.get_image_files` を `FileSystemUtils.find_files_recursively` 呼び出しに置換
-   [ ] `FileSystemManager.get_image_info` を `ImageStorage.get_image_info` 呼び出しに置換 (要 `ImageStorage` インスタンス化)
-   [ ] `FileSystemManager._get_next_sequence_number` を `ProjectStructure.get_next_sequence_number` 呼び出しに置換 (要 `ProjectStructure` インスタンス化)
-   [ ] `FileSystemManager.save_processed_image` を `ImageStorage.save_processed_image` 呼び出しに置換
-   [ ] `FileSystemManager.copy_file` を `FileSystemUtils.copy_file` 呼び出しに置換
-   [ ] `FileSystemManager.save_original_image` を `ImageStorage.save_original_image` 呼び出しに置換
-   [ ] `FileSystemManager.create_batch_request_file` を `BatchRequestProcessor.create_batch_request_file` 呼び出しに置換 (要 `BatchRequestProcessor` インスタンス化)
-   [ ] `FileSystemManager.save_batch_request` を `BatchRequestProcessor.append_request` 呼び出しに置換
-   [ ] `FileSystemManager.split_jsonl` を `BatchRequestProcessor.split_if_needed` 呼び出しに置換
-   [ ] `FileSystemManager.export_dataset_to_txt` を `DatasetExporter.export_to_txt` 呼び出しに置換 (要 `DatasetExporter` インスタンス化)
-   [ ] `FileSystemManager.export_dataset_to_json` を `DatasetExporter.export_to_json` 呼び出しに置換
-   [ ] `FileSystemManager.save_toml_config` を `ConfigPersistence.save_toml_config` 呼び出しに置換
-   [ ] `FileSystemManager.initialize` と関連するインスタンス変数を削除または非推奨化

## 8. 依存箇所の修正

-   [ ] `FileSystemManager` を直接インポート・利用している箇所を検索
-   [ ] 各利用箇所で、`FileSystemManager` の代わりに適切な新しいコンポーネント (`FileSystemUtils`, `ProjectStructure`, `ImageStorage` 等) を利用するようにコードを修正
    -   [ ] (例) GUI コード
    -   [ ] (例) アプリケーション層のサービス
    -   [ ] (例) 他の Core 層モジュール
-   [ ] 各修正箇所で関連するテストを実行・修正

## 9. `FileSystemManager` の削除

-   [ ] すべての `FileSystemManager` への参照がなくなったことを確認
-   [ ] `src/lorairo/storage/file_system.py` ファイルを削除
-   [ ] `FileSystemManager` に関連するテストコードを削除または更新

## 10. ドキュメント更新

-   [ ] `docs/specs/core/storage_management.md` を最終的な実装に合わせて更新
-   [ ] プロジェクト README や関連ドキュメント内の `FileSystemManager` に関する記述を更新
-   [ ] このチェックリスト (`storage_refactoring_checklist.md`) を完了済みに更新 