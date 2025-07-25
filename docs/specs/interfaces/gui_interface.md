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

詳細は [image_edit_widget.md](./image_edit_widget.md) を参照。

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
    -   DB検索ウィジェットで検索が実行されると `on_filter_applied` が呼ばれ、DBを検索 (`idm.get_images_by_filter`) し、結果の画像パスリストでサムネイルセレクターを更新 (`