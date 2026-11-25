# Image Processing Service 仕様書

> **注記**: 実装先パスは `src/lorairo/image_transforms/image_processor.py` である(旧 `src/lorairo/editor/image_processor.py` は #717 のリネームにより現行パスへ変更された)。GUI 側の呼び出し元も、未実装のまま終了した `ImageEditWidget` 構想ではなく、現行の `src/lorairo/gui/tab/` 配下の各タブウィジェットである。
>
> 2026-07-05 監査: 本文の `process_images_in_list()` シグネチャ(`progress_callback`、`status_callback`、`is_canceled`、`upscaler_override`)と、`ImageDatabaseManager` のメソッド群(`register_original_image`、`get_image_metadata`、`check_processed_image_exists`、`register_processed_image`)が現行実装と一致することを確認済みである。生きた仕様書として維持する。

## 1. 概要

本ドキュメントは、アプリケーション層における画像処理サービス(`ImageProcessingService`)の仕様を定義する。このサービスは GUI 層(各タブウィジェット)からの要求を受け、画像処理のコア機能(`ImageProcessingManager` など)、データベース(`ImageDatabaseManager`)、およびファイルシステム(`FileSystemManager`)を連携させ、一連の画像処理ワークフローを実行する。

## 2. 責務

- **画像処理ワークフローの実行**: GUI から渡された画像パスのリストに対し、以下の処理を順次実行する。
  1. 対象画像の DB 登録状況を確認し、未登録であればオリジナル画像を登録する(`idm.register_original_image`)。
  2. 登録済み、または新規登録した画像のメタデータを取得する(`idm.get_image_metadata`)。
  3. 指定した目標解像度の処理済み画像が DB に存在するかを調べる(`idm.check_processed_image_exists`)。
  4. 存在しない場合、`ImageProcessingManager` の `process_image` を呼び出して画像処理(枠除去、色空間正規化、アップスケール、リサイズ)を実行する。
  5. 処理後の画像をファイルシステムへ保存する(`fsm.save_processed_image`)。
  6. 処理後の画像情報を DB へ登録する(`idm.register_processed_image`)。
- **設定の利用**: `ConfigurationService` から目標解像度、優先解像度、既定のアップスケーラなどの設定値を取得し、処理に反映する。
- **進捗とステータスの通知**: 処理が長時間に及ぶ場合に備え、進捗率(パーセンテージ)と現在のステータス(処理中のファイル名など)をコールバック関数経由で GUI 層へ通知する。
- **キャンセル処理**: GUI 層からのキャンセル要求を検知し、処理を中断する機能を提供する。
- **依存コンポーネントの初期化**: 内部で利用する `ImageProcessingManager` を、`ConfigurationService` から取得した設定に基づいて初期化する。

## 3. 主要メソッド

- **`__init__(config_service, fsm, idm)`**: 依存サービスを受け取り、内部の `ImageProcessingManager` を初期化する。
- **`process_images_in_list(image_paths, progress_callback, status_callback, is_canceled, upscaler_override)`**: 画像パスのリストを受け取り、画像処理ワークフローを一括実行する。進捗・ステータス通知およびキャンセル処理に対応する。
- **`_process_single_image(image_file, upscaler)`**: 単一の画像ファイルに対する処理ワークフローを実行する内部メソッド。

## 4. 依存関係

- `ConfigurationService`: 画像処理設定の取得。
- `FileSystemManager`: オリジナル画像のコピー、処理済み画像の保存、画像情報の取得。
- `ImageDatabaseManager`: 画像の DB 登録・検索およびメタデータ管理。
- `ImageProcessingManager`(`src/lorairo/image_transforms/image_processor.py` 内): 枠除去・正規化・アップスケール・リサイズといった実際の画像処理を担うコアコンポーネント。
- `src/lorairo/utils/log.py`: ログ出力機能。

## 5. 注意点

- 既存アノテーションファイルの読み込みおよび DB 登録処理を `ImageProcessingService` に持たせるか、別のアノテーション関連サービスへ分離するかは、責務分離の観点から検討が必要である。
- 個別画像の処理でエラーが発生した際の挙動(残りの処理を継続するか、全体を中断するか)については、エラーハンドリング方針の検討が必要である。

## 6. 関連ドキュメント

- コア画像処理仕様: [image_processing.md](../core/image_processing.md)
