# Image Processing Service 仕様書

## 1. 概要

本ドキュメントは、アプリケーション層における画像処理サービス (`ImageProcessingService`) の仕様を定義する。このサービスは、GUI層 (`ImageEditWidget`) からの要求を受け、画像処理のコア機能 (`ImageProcessingManager` など) とデータベース (`ImageDatabaseManager`)、ファイルシステム (`FileSystemManager`) を連携させ、一連の画像処理ワークフローを実行する。

## 2. 責務

-   **画像処理ワークフローの実行:** GUIから渡された画像パスリストに対して、以下の処理を順次実行する。
    -   処理対象画像のDB登録状況を確認し、未登録の場合はオリジナル画像を登録 (`idm.register_original_image`)。
    -   登録済みまたは新規登録した画像のメタデータを取得 (`idm.get_image_metadata`)。
    -   指定された目標解像度での処理済み画像がDBに存在しないか確認 (`idm.check_processed_image_exists`)。
    -   存在しない場合、`ImageProcessingManager` の `process_image` メソッドを呼び出して画像処理 (枠除去、色空間正規化、アップスケール、リサイズ) を実行。
    -   処理後の画像をファイルシステムに保存 (`fsm.save_processed_image`)。
    -   処理後の画像の情報をDBに登録 (`idm.register_processed_image`)。
-   **設定の利用:** `ConfigurationService` から画像処理に必要な設定値 (目標解像度、優先解像度、デフォルトアップスケーラ等) を取得し、処理に反映させる。
-   **進捗とステータスの通知:** 長時間実行される可能性があるため、処理の進捗状況 (パーセンテージ) と現在のステータス (処理中のファイル名など) を、コールバック関数を通じてGUI層に通知する。
-   **キャンセル処理:** GUI層からのキャンセル要求を検知し、処理を中断する機能を提供する。
-   **依存コンポーネントの初期化:** 内部で使用する `ImageProcessingManager` を、`ConfigurationService` から取得した設定に基づいて初期化する。

## 3. 主要メソッド

-   **`__init__(config_service, fsm, idm)`:** 依存サービスを受け取り、内部の `ImageProcessingManager` を初期化する。
-   **`process_images_in_list(image_paths, progress_callback, status_callback, is_canceled, upscaler_override)`:** 画像パスのリストを受け取り、一括で画像処理ワークフローを実行する。進捗・ステータス通知、キャンセル処理に対応。
-   **`_process_single_image(image_file, upscaler)`:** 単一の画像ファイルに対する処理ワークフローを実行する (内部メソッド)。

## 4. 依存関係

-   `ConfigurationService`: 画像処理設定の取得。
-   `FileSystemManager`: オリジナル画像のコピー、処理済み画像の保存、画像情報の取得。
-   `ImageDatabaseManager`: 画像のDB登録・検索、メタデータ管理。
-   `ImageProcessingManager` (`src/lorairo/editor/image_processor.py` 内): 実際の画像処理 (枠除去、正規化、アップスケール、リサイズ) を担当するコアコンポーネント。
-   `src/lorairo/utils/log.py`: ログ出力用。

## 5. 注意点

-   既存のアノテーションファイルの読み込み・DB登録処理は、元々 `ImageEditWidget` 内にあったが、責務分離の観点から `ImageProcessingService` または別のアノテーション関連サービスに移動することが望ましい (現状は `_process_single_image` 内でコメントアウトされている箇所あり)。
-   エラーハンドリング: 個別画像の処理でエラーが発生した場合の挙動 (処理を継続するか、全体を中断するか) は要検討。

## 6. 関連ドキュメント

-   コア画像処理仕様: [image_processing.md](../core/image_processing.md)
-   画像編集UI仕様: [image_edit_widget.md](../interfaces/image_edit_widget.md)