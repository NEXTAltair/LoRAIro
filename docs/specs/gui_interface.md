# GUIインターフェース 仕様書

## 1. 概要

本ドキュメントは、`lorairo` アプリケーションのグラフィカルユーザーインターフェース (GUI) の仕様を定義する。GUI は `PySide6` および `superqt` ライブラリを用いて構築される。

## 2. 全体構成

アプリケーションは単一のメインウィンドウ (`MainWindow`) で構成される。

```mermaid
graph TD
    subgraph MainWindow
        A[サイドバー (sidebarList)];
        B[コンテンツエリア (contentStackedWidget)];
        C[データセットセレクター (datasetSelector)];
        D[メニューバー (menubar)];
        E[ステータスバー (statusbar)];
    end

    A --> B;
    C --> MainWindow;
    D --> MainWindow;
    E --> MainWindow;

    subgraph コンテンツエリア (Pages)
        P1[画像編集 (pageImageEdit)];
        P2[AIタグ付け (pageImageTagger)];
        P3[データセット概要 (pageDatasetOverview)];
        P4[エクスポート (pageExport)];
        P5[設定 (pageSettings)];
    end

    B -.-> P1;
    B -.-> P2;
    B -.-> P3;
    B -.-> P4;
    B -.-> P5;

    style MainWindow fill:#eee,stroke:#333,stroke-width:2px
```

-   **メインウィンドウ:** 左側にサイドバー、右側にコンテンツエリアを配置するスプリッター (`mainWindowSplitter`) を持つ。上部にはデータセット選択ウィジェットとメニューバー、下部にはステータスバーが表示される。
-   **サイドバー (`sidebarList`):** 機能ページを選択するためのリスト。選択された項目に応じてコンテンツエリアの表示が切り替わる。項目は「画像編集」「AIタグ付け」「データセット概要」「エクスポート」「設定」など。
-   **コンテンツエリア (`contentStackedWidget`):** サイドバーで選択された機能ページ（ウィジェット）を表示する。
-   **データセットセレクター (`datasetSelector`):** 処理対象の画像が含まれるディレクトリを選択する。選択されたディレクトリ内の画像が各機能ページで利用される。履歴機能を持つ (`DirectoryPickerWidget` を使用)。
-   **ステータスバー (`statusbar`):** アプリケーションの状態や簡単なメッセージを表示する。

## 3. 主要機能ページ仕様

### 3.1. 画像編集ページ (`pageImageEdit` / `ImageEditWidget`)

-   **目的:** 選択された画像に対して、リサイズやアップスケールなどの一括処理を実行する。
-   **主要コンポーネント:**
    -   **画像リスト (`tableWidgetImageList`):**
        -   データセットセレクターで選択されたディレクトリ内の画像を表示するテーブル。
        -   表示項目: サムネイル、ファイル名、パス、解像度、ファイルサイズ、既存タグ、既存キャプション。
        -   複数選択可能。選択された画像が処理対象となる。
        -   アイテム選択時に画像プレビューを更新する。
    -   **画像プレビュー (`ImagePreview`):**
        -   テーブルで選択された画像を表示する (`ImagePreviewWidget` を使用)。
    -   **処理オプション:**
        -   **リサイズ解像度 (`comboBoxResizeOption`):** 目標解像度を選択するコンボボックス (例: "512x512", "768x768" など)。選択された値は `ConfigManager` に保存される。
        -   **アップスケーラー (`comboBoxUpscaler`):** 使用するアップスケーラーモデルを選択するコンボボックス。選択されたモデル名は `ConfigManager` に保存される。
    -   **処理開始ボタン (`pushButtonStartProcess`):** 選択された画像に対して、設定されたオプションで一括処理を開始する。処理はバックグラウンドスレッドで実行され、プログレスダイアログが表示される (`Controller` と `ProgressWidget` を使用)。
-   **処理フロー (`process_all_images`, `process_image`):**
    1.  選択された画像リストをループ処理。
    2.  各画像について、DBに登録済みか確認 (`idm.detect_duplicate_image`)。
        -   未登録ならオリジナル画像をDBに登録 (`idm.register_original_image`)。
    3.  既存のアノテーションファイル (.txt, .caption) があれば読み込み、DBに保存 (`ImageAnalyzer.get_existing_annotations`, `idm.save_annotations`)。
        -   タグが5単語を超える場合は作品名か判定し、そうでなければキャプションとして扱うロジックあり。
    4.  指定された目標解像度で処理済みの画像がDBに存在するか確認 (`idm.check_processed_image_exists`)。存在すればスキップ。
    5.  `ImageProcessingManager.process_image` を呼び出して画像処理（枠除去、色空間正規化、アップスケール判定、リサイズ）を実行。
        -   アップスケールは `comboBoxUpscaler` で選択されたモデルを使用。
        -   リサイズは `comboBoxResizeOption` で選択された解像度を目標値として使用。
    6.  処理結果の画像が存在すれば、ファイルシステムに保存 (`fsm.save_processed_image`) し、メタデータをDBに登録 (`idm.register_processed_image`)。
-   **初期化 (`initialize`, `initialize_processing`):**
    -   `ConfigManager`, `FileSystemManager`, `ImageDatabaseManager` のインスタンスを受け取る。
    -   `ConfigManager` から目標解像度、優先解像度、アップスケーラーモデルリストを取得し、UIに設定。
    -   処理開始時に `FileSystemManager` と `ImageProcessingManager` を初期化。

### 3.2. AIタグ付けページ (`pageImageTagger` / `ImageTaggerWidget`)

-   **目的:** 選択された画像に対してAIによるタグ・キャプション生成を実行し、結果の確認・編集・保存を行う。
-   **主要コンポーネント:**
    -   **サムネイルセレクター (`ThumbnailSelector`):**
        -   データセット内の画像（.webp限定）をサムネイル表示し、処理対象を選択する (`ThumbnailSelectorWidget` を使用)。
        -   単一選択、複数選択（Ctrl/Shiftキー使用）に対応。
        -   選択された画像は `selected_webp` リストに保持される。
        -   選択変更時に画像プレビューとアノテーション表示を更新する。
    -   **画像プレビュー (`ImagePreview`):**
        -   サムネイルセレクターで最後に選択された画像を表示する (`ImagePreviewWidget` を使用)。
    -   **DB検索 (`dbSearchWidget`):**
        -   タグやキャプションでDB内の画像を検索し、結果をサムネイルセレクターに表示する機能 (`TagFilterWidget` を使用)。
        -   タグ未付与、NSFWコンテンツのフィルタリングオプションあり。
    -   **AIモデル選択:**
        -   **アノテーター/モデル (`comboBoxModel`):** `image-annotator-lib` が提供する利用可能な全てのアノテーター（APIベース、ローカルモデル等）のリストを表示し、選択する。選択されたモデル名は `ConfigManager` に保存される。(変更)
        -   **タグフォーマット (`comboBoxTagFormat`):** 出力タグの整形に使用するフォーマット名 (danbooru, e621, derpibooru) を選択。
    -   **プロンプト設定:**
        -   **メインプロンプト (`textEditMainPrompt`):** AIに渡す主要な指示。編集可能で `ConfigManager` に保存される。
        -   **追加プロンプト (`textEditAddPrompt`):** AIに渡す追加の指示。編集可能で `ConfigManager` に保存される。
        -   **画像生成プロンプト (`textEditGenaiPrompt`):** (※用途不明瞭) 編集可能で `ConfigManager` に保存される。タグとしてDBに別途登録されるロジックあり。
    -   **処理オプション:**
        -   **低解像度画像使用 (`lowRescheckBox`):** チェック時、AIへの入力にDB内の低解像度版処理済み画像を使用する。
    -   **生成実行ボタン (`pushButtonGenerate`):**
        -   選択された画像 (`selected_webp`) と **アノテーター/モデル設定** に基づき、`image-annotator-lib` の `annotate` 関数を呼び出してタグ・キャプション・スコア生成を実行する。(変更)
        -   処理結果は `all_results` 辞書 (キー: 画像パス) に保持される。
        -   最後に処理した画像の結果をタグ/キャプション編集エリアとスコアスライダーに表示する。
    -   **結果表示/編集:**
        -   **タグ (`textEditTags`):** 生成されたタグをカンマ区切りで表示。編集可能。
        -   **キャプション (`textEditCaption`):** 生成されたキャプションを表示。編集可能。
        -   **スコア (`scoreSlider`):** 生成されたスコアを0-100の範囲で表示。ツールチップで実際の値表示。編集不可？
    -   **保存オプション:**
        -   **テキストファイル保存 (`checkBoxText`):** チェック時、タグとキャプションを画像と同名の .txt / .caption ファイルとして保存。
        -   **JSONファイル保存 (`checkBoxJson`):** チェック時、アノテーション情報をJSONファイルとして保存。
        -   **DB登録 (`checkBoxDB`):** チェック時、生成/編集されたアノテーションをデータベースに保存。
        -   **キャプションをタグにマージ (`MergeCaptionWithTagscheckBox`):** テキストファイル保存時にキャプションをタグリストの先頭に追加するかどうか。
    -   **保存実行ボタン (`pushButtonSave`):**
        -   選択された保存オプションに基づき、`all_results` に保持されたアノテーション情報をファイルまたはDBに保存する。
        -   テキスト/JSON保存時は保存先ディレクトリを選択するダイアログを表示 (`DirectoryPickerSave`)。
        -   DB保存時は `idm.save_annotations` を呼び出す。画像がDB未登録の場合は先に登録する。
-   **初期化 (`initialize`):**
    -   `ConfigManager`, `ImageDatabaseManager` のインスタンスを受け取る。
    -   `ConfigManager` からプロンプト、**利用可能なアノテーター/モデルリスト (ライブラリから取得)**、ディレクトリパスなどを取得し、UIに設定。(変更)
    -   DB検索ウィジェットを初期化。
-   **データフロー:**
    -   メインウィンドウのデータセットセレクターで選択された画像リストが `load_images` で渡される。
    -   DB検索結果も `load_images` でサムネイル表示が更新される。
    -   生成/編集されたアノテーションは `all_results` 辞書に一時保持され、保存ボタン押下時に永続化される。

### 3.3. データセット概要ページ (`pageDatasetOverview` / `DatasetOverviewWidget`)

-   **目的:** 選択されたデータセット内の画像のメタデータやアノテーション情報を一覧表示・確認する。
-   **主要コンポーネント:**
    -   **サムネイルセレクター (`thumbnailSelector`):** データセット内の画像を表示・選択 (`ThumbnailSelectorWidget` を使用)。
    -   **画像プレビュー (`ImagePreview`):** 選択された画像を表示 (`ImagePreviewWidget` を使用)。
    -   **メタデータ表示:**
        -   ファイル名 (`fileNameValueLabel`)
        -   パス (`imagePathValueLabel`)
        -   フォーマット (`formatValueLabel`)
        -   モード (`modeValueLabel`)
        -   アルファチャンネル有無 (`alphaChannelValueLabel`)
        -   解像度 (`resolutionValueLabel`)
        -   アスペクト比 (`aspectRatioValueLabel`)
        -   拡張子 (`extensionValueLabel`)
    -   **アノテーション表示:**
        -   タグ (`tagsTextEdit`): 関連付けられたタグをカンマ区切りで表示。**読み取り専用**。
        -   キャプション (`captionTextEdit`): 関連付けられたキャプションを表示。**読み取り専用**。
    -   **DB検索 (`dbSearchWidget`):** タグやキャプション等でDB内の画像を検索し、結果をサムネイルセレクターに表示 (`TagFilterWidget` を使用)。日付範囲、解像度、タグ未付与、NSFWフィルタリングオプションあり。
-   **処理フロー:**
    -   データセットセレクターでディレクトリが選択されると `load_images` が呼ばれ、サムネイルセレクターに画像が表示される。
    -   サムネイルが選択されると `update_preview` が呼ばれ、画像プレビューとメタデータ・アノテーション表示が更新される (`update_metadata`, `update_annotations`)。
    -   メタデータは `FileSystemManager.get_image_info` で取得。
    -   アノテーションはまず既存ファイル (`.txt`, `.caption`) を探し (`ImageAnalyzer.get_existing_annotations`)、なければDBから取得 (`idm.get_image_annotations`) して表示。
    -   DB検索ウィジェットで検索が実行されると `on_filter_applied` が呼ばれ、DBを検索 (`idm.get_images_by_filter`) し、結果の画像パスリストでサムネイルセレクターを更新 (`update_thumbnail_selector`)。
-   **初期化 (`initialize`):**
    -   `ConfigManager`, `ImageDatabaseManager` のインスタンスを受け取る。

### 3.4. エクスポートページ (`pageExport` / `DatasetExportWidget`)

-   **目的:** データベース内の画像とアノテーション情報を、指定された形式（テキスト、JSON）で外部ディレクトリに出力する。
-   **主要コンポーネント:**
    -   **DB検索 (`dbSearchWidget`):** エクスポート対象の画像をDBから検索する (`TagFilterWidget` を使用)。日付範囲、解像度、タグ未付与、NSFWフィルタリングオプションあり。
    -   **サムネイルセレクター (`thumbnailSelector`):** 検索結果の画像を表示し、エクスポート対象を選択する (`ThumbnailSelectorWidget` を使用)。
    -   **画像数表示 (`imageCountLabel`):** 検索結果の画像数とDB全体の画像数を表示。
    -   **画像プレビュー (`imagePreview`):** 選択された画像を表示 (`ImagePreviewWidget` を使用)。
    -   **エクスポート先ディレクトリ (`exportDirectoryPicker`):** 出力先フォルダを選択する (`DirectoryPickerWidget` を使用)。
    -   **エクスポートオプション:**
        -   **テキスト形式 (`checkBoxTxtCap`):** チェック時、.txt (タグ) / .caption ファイルを出力。
        -   **JSON形式 (`checkBoxJson`):** チェック時、メタデータとアノテーションを含むJSONファイルを出力。
        -   **キャプションをタグにマージ (`MergeCaptionWithTagscheckBox`):** テキスト形式出力時にキャプションをタグリストの先頭に追加するかどうか。
        -   **最新のアノテーションのみ (`latestcheckBox`):** チェック時、指定された期間内に更新されたアノテーションのみを出力対象とする。
        -   **フィルタリング期間 (`latestMinutesSpinBox`):** (追加) `latestcheckBox` がオンの場合に有効化。最新とみなす期間を分単位で指定する (デフォルト: 5)。
    -   **エクスポート実行ボタン (`exportButton`):** 選択された画像とオプションに基づき、エクスポート処理を開始する。
    -   **プログレスバー (`exportProgressBar`):** エクスポートの進捗を表示。
    -   **ステータスラベル (`statusLabel`):** 処理状況を表示。
-   **処理フロー (`export_dataset`):**
    1.  サムネイルセレクターで選択された画像リストを取得。
    2.  各画像パスに対応する `image_id` を `image_path_id_map` (DB検索時に作成) から取得。
    3.  `image_id` を使ってDBからアノテーション情報を取得 (`idm.get_image_annotations`)。
    4.  `latestcheckBox` がオンの場合、`latestMinutesSpinBox` から期間（分）を取得し、その期間でアノテーションをフィルタリング (`idm.filter_recent_annotations(annotations, minutes=...)`)。(変更)
    5.  選択されたエクスポート形式に応じて `FileSystemManager` のエクスポートメソッド (`export_dataset_to_txt`, `export_dataset_to_json`) を呼び出す。
    6.  プログレスバーとステータスラベルを更新。
    7.  完了またはエラー時にメッセージボックスを表示。
-   **初期化 (`initialize`):**
    -   `ConfigManager`, `FileSystemManager`, `ImageDatabaseManager` のインスタンスを受け取る。
    -   日付範囲スライダーを初期化。
    -   エクスポート先ディレクトリの初期値を設定。
    -   `latestMinutesSpinBox` の初期値を設定 (例: 5)。

### 3.5. 設定ページ (`pageSettings` / `SettingsWidget`)

-   **目的:** アプリケーションの動作に関わる各種設定（ディレクトリパス、ログレベルなど）を表示・編集・保存する。**APIキーおよびHugging Face関連情報は `.env` ファイルで管理する。**
-   **主要コンポーネント:**
    -   **ディレクトリ設定:**
        -   出力先 (`dirPickerOutput`)
        -   バッチAPIレスポンスファイル保存先 (`dirPickerResponse`)
        -   編集済みデータセット出力先 (`dirPickerEditedOutput`)
        -   (それぞれ `DirectoryPickerWidget` を使用)
    -   **~~APIキー設定:~~** (削除 - `.env` ファイルで管理)
    -   **~~Hugging Face設定:~~** (削除 - `.env` ファイルで管理)
    -   **ログ設定:**
        -   ログレベル (`comboBoxLogLevel`): DEBUG, INFO, WARNING, ERROR, CRITICAL から選択。
        -   ログファイルパス (`filePickerLogFile` - `FilePickerWidget` を使用)
    -   **保存ボタン:**
        -   上書き保存 (`buttonSave`): 現在の設定を `processing.toml` に保存。
        -   名前を付けて保存 (`buttonSaveAs`): 設定を別名の TOML ファイルとして保存。
-   **処理フロー:**
    -   初期化時に `ConfigManager` から設定値を読み込み、各UIウィジェットに表示 (`initialize_ui` 内の各メソッド)。**APIキーとHugging Face情報は `.env` から読み込まれるため、この画面では表示・編集しない。**
    -   各設定ウィジェットの値が変更されると、対応する `ConfigManager` の `config` 辞書の値がリアルタイムで更新される (各 `on_..._editingFinished`, `on_..._changed` スロット)。
    -   保存ボタンクリック時に `FileSystemManager.save_toml_config` を呼び出して設定ファイルを保存。
-   **初期化 (`initialize`):**
    -   `ConfigManager` のインスタンスを受け取る。
    -   `ConfigManager` から設定値を読み込み、UIに反映。
    -   カスタムウィジェット（ピッカー）のシグナルを接続。

## 4. 共通コンポーネント仕様

*(再利用されるウィジェットの仕様を記述)*

### 4.1. サムネイルセレクター (`ThumbnailSelectorWidget`)

*(詳細仕様を記述)*

### 4.2. 画像プレビュー (`ImagePreviewWidget`)

*(詳細仕様を記述)*

### 4.3. フィルターウィジェット (`TagFilterWidget`)

*(詳細仕様を記述)*

### 4.4. ディレクトリ/ファイルピッカー (`DirectoryPickerWidget`, `FilePickerWidget`, `PickerWidget`)

*(詳細仕様を記述)*

### 4.5. プログレスダイアログ (`ProgressWidget`, `Controller`)

*(詳細仕様を記述)*

---