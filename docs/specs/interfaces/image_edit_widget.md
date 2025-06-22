### 3.1. 画像編集ページ (`pageImageEdit` / `ImageEditWidget`)

-   **目的:** 選択された画像に対して、リサイズやアップスケールなどの一括処理を実行する。
-   **責務:**
    -   データセット内の画像リストとメタデータ、既存アノテーションの表示。
    -   画像プレビューの表示。
    -   リサイズ、アップスケールオプションの選択UIの提供。
    -   ユーザー操作（画像選択、オプション変更、処理開始）の受付とサービス層 (`ImageProcessingService`) への処理依頼。
-   **依存関係 (DI):**
    -   `ConfigurationService`: アプリケーション設定（目標解像度、アップスケーラーリスト等）の取得・更新。
    -   `FileSystemManager`: (※ 直接の依存は減らす方向だが、現状初期化で受け取っている場合あり)
    -   `ImageDatabaseManager`: (※ 直接の依存は減らす方向だが、現状初期化で受け取っている場合あり)
    -   `ImageProcessingService`: 画像処理の実行依頼。
    -   `ImageTextFileReader`: 画像に関連する既存アノテーション（タグ、キャプション）の取得。
    -   `MainWindow` (Optional): 親ウィンドウへの参照。データセット画像の受け渡し、長時間処理の実行依頼（プログレス表示連携）に使用。
-   **主要コンポーネント:**
    -   **画像リスト (`tableWidgetImageList`):**
        -   `MainWindow` から渡されたデータセットディレクトリ内の画像を表示するテーブル。
        -   表示項目: サムネイル、ファイル名、パス、解像度 (`QPixmap` から取得)、ファイルサイズ (`Path.stat` から取得)、既存タグ、既存キャプション (`ImageTextFileReader` から取得)。
        -   アイテム選択時に画像プレビューを更新 (`on_tableWidgetImageList_itemSelectionChanged`)。
    -   **画像プレビュー (`ImagePreview`):**
        -   テーブルで選択された画像を表示する (`ImagePreviewWidget` を使用)。`load_image` メソッドを持つ。
    -   **処理オプション:**
        -   **リサイズ解像度 (`comboBoxResizeOption`):** 目標解像度を選択するコンボボックス。選択変更時 (`on_comboBoxResizeOption_currentIndexChanged`) に `ConfigurationService.update_image_processing_setting("target_resolution", ...)` を呼び出す。
        -   **アップスケーラー (`comboBoxUpscaler`):** 使用するアップスケーラーモデルを選択するコンボボックス。選択変更時 (`on_comboBoxUpscaler_currentIndexChanged`) に `ConfigurationService.update_image_processing_setting("upscaler", ...)` を呼び出す。モデルリストは `ConfigurationService.get_upscaler_models()` から取得。
    -   **処理開始ボタン (`pushButtonStartProcess`):**
        -   クリック時 (`on_pushButtonStartProcess_clicked`) に、現在表示されている画像リスト (`directory_images`) と選択されたアップスケーラー (`comboBoxUpscaler.currentText()`) を引数として、`MainWindow.some_long_process` メソッドを呼び出す。
        -   `MainWindow.some_long_process` には、実際の処理関数として `ImageProcessingService.process_images_in_list` を渡す。これにより、画像処理がバックグラウンドで実行され、進捗が `MainWindow` 経由で表示される。
-   **初期化 (`initialize`):**
    -   上記依存関係のサービスインスタンスと `MainWindow` を受け取る。
    -   `ConfigurationService` から目標解像度 (`get_image_processing_config`)、優先解像度 (`get_preferred_resolutions`)、アップスケーラーモデルリスト (`get_upscaler_models`) を取得し、UIに設定・内部状態を初期化。
    -   テーブルヘッダーの設定を行う。
-   **表示更新 (`showEvent`, `load_images`):**
    -   ウィジェットが表示される際 (`showEvent`) に、`MainWindow` が保持しているデータセット画像パスリスト (`dataset_image_paths`) があれば `load_images` を呼び出す。
    -   `load_images` は、渡された画像パスリストを `directory_images` に保持し、テーブルをクリア (`setRowCount(0)`) した後、各画像パスについて `_add_image_to_table` を呼び出してテーブルに行を追加する。最初の画像はプレビューにも表示する。
-   **テーブル行追加 (`_add_image_to_table`):**
    -   与えられた画像パスについて、ファイル名、パス、解像度、サイズを取得し、`QTableWidgetItem` を作成してテーブルに設定する。
    -   サムネイルは `QPixmap` で作成し、`setData(Qt.ItemDataRole.DecorationRole, ...)` で設定する。
    -   既存アノテーションは `ImageTextFileReader.get_annotations_for_display(file_path)` で取得し、タグとキャプションを結合してテーブルに設定する。

## 関連ドキュメント

-   GUI全体の構成: [gui_interface.md](./gui_interface.md)
-   画像処理サービス仕様: [image_processing_service.md](../application/image_processing_service.md)
-   コア画像処理仕様: [image_processing.md](../core/image_processing.md)