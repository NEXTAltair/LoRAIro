# LoRAIro 全体処理フロー概要

本ドキュメントは、LoRAIro アプリケーションにおける主要なデータ処理の流れを、実装の詳細から離れて概観することを目的とする。

## 1. アーキテクチャ概要: サービス層の役割

`lorairo` アプリケーションは、責務を分離するためにレイヤードアーキテクチャを採用しています。特に `src/lorairo/services` フォルダに含まれる**サービス層**は、以下の重要な役割を担います。

-   **仲介 (Mediation):** GUI 層 (`src/lorairo/gui`) からのユーザー操作や要求を受け付けます。
-   **ビジネスロジックの実行:** 要求に基づいて、アプリケーション固有のビジネスルールやワークフローを実行します。
-   **下位層との連携:** ビジネスロジックの実行に必要なデータ永続化 (`src/lorairo/database`) や、具体的な画像処理 (`src/lorairo/editor` 内のコンポーネント) など、下位のレイヤーと連携します。
-   **関心の分離:** GUI 層が直接データベースや複雑な処理ロジックに依存することを防ぎ、各層の独立性を高めます。これにより、コードの再利用性、テスト容易性、保守性が向上します。

例えば、`ImageEditWidget` でユーザーが処理開始ボタンを押すと、`ImageProcessingService` が呼び出され、このサービスが必要な設定を `ConfigurationService` から取得し、実際の画像処理を `ImageProcessingManager` に依頼し、結果を `ImageDatabaseManager` を介してデータベースに保存する、といった流れになります。

以降のセクションでは、このサービス層が関与する主要な処理フローを具体的に説明します。

## 2. データセットの準備と登録 (主に `ImageEditWidget` または `ImageTaggerWidget` の初期処理)

1.  **画像ファイルの選択:** ユーザーは GUI のデータセットセレクターで、処理対象の画像が含まれるディレクトリを選択する。
2.  **画像情報の取得と表示:** 選択されたディレクトリ内の画像がリスト表示（サムネイル等）され、ユーザーは処理対象を選択できる。選択された画像のメタデータ（解像度、フォーマット等）が表示される。
3.  **データベースへの初期登録 (処理開始時):**
    *   ユーザーが画像編集やAIタグ付けなどの処理を開始すると、対象の画像がデータベース (`images` テーブル) にまだ登録されていなければ、重複チェック（ファイル名、pHash）が行われる。
    *   未登録の場合、オリジナル画像は指定された保存用フォルダにコピーされ (`FileSystemManager`)、そのパスや画像のメタデータ、一意なUUIDなどがデータベースに登録される (`ImageRepository.add_original_image`)。
    *   画像に付随する既存のアノテーションファイル (`.txt`, `.caption`) が存在する場合、その内容が読み込まれ、データベースの `tags`, `captions` テーブルに `existing=True` として登録される (`ImageAnalyzer.get_existing_annotations`, `ImageRepository.save_annotations`)。

## 3. 画像処理 (主に `ImageEditWidget` から実行)

1.  **処理実行:** ユーザーは GUI の画像編集ページで、リサイズ目標解像度やアップスケーラーを選択し、処理開始ボタンを押す。
2.  **画像処理実行:** 選択された各画像に対して、以下の処理が順次実行される (`ImageProcessingService` → `ImageProcessingManager.process_image`)。
    *   **枠除去:** 画像周囲の不要な枠を自動検出・除去 (`AutoCrop`)。
    *   **色空間正規化:** 画像をRGB/RGBAに変換 (`ImageProcessor.normalize_color_profile`)。
    *   **アップスケール (条件付き):** 画像解像度が目標より低く、アップスケーラーが指定されていれば実行 (`Upscaler`)。
    *   **リサイズ:** 指定されたルールに基づき、目標解像度に合わせてリサイズ (`ImageProcessor.resize_image`)。
3.  **処理結果の保存:**
    *   処理後の画像は、指定された保存用フォルダに WebP 形式で保存される (`FileSystemManager.save_processed_image`)。
    *   処理後の画像のメタデータ（解像度、パス等）がデータベースの `processed_images` テーブルに登録される (`ImageDatabaseManager` → `ImageRepository.add_processed_image`)。

## 4. AI アノテーション (主に `ImageTaggerWidget` から実行)

1.  **実行指示:** ユーザーは GUI の AI タグ付けページで、アノテーション対象の画像と使用する AI モデル（アノテーター）を選択し、生成実行ボタンを押す。
2.  **ライブラリ呼び出し:** `AnnotationService` が `AnnotationWorker` を使用して、`ai_annotator.py` 経由で `image-annotator-lib` の `annotate` 関数を呼び出す。この際、画像データ（PIL Imageオブジェクトのリスト）、pHashリスト、選択されたモデル名のリストを渡す。
3.  **アノテーション生成 (ライブラリ内部):** `image-annotator-lib` が選択されたモデル（APIまたはローカル）と通信し、タグ、キャプション、スコア、レーティングなどの情報を生成・整形する。
4.  **結果の取得と処理:** `AnnotationWorker` はライブラリから `PHashAnnotationResults` 型の結果を受け取り、pHash をキーとする辞書として処理する。
    *   結果からタグリストを取得する。
    *   `formatted_output` をパースしてキャプションとスコアを抽出する。
    *   (レーティング情報も同様に取得・処理する)
5.  **データベースへの保存:**
    *   取得・整形されたタグ、キャプション、スコア、レーティング情報が、対応する画像ID、モデルIDと共にデータベース (`tags`, `captions`, `scores`, `ratings` テーブル) に保存される (`ImageRepository.save_annotations` など)。
    *   タグ保存時には、`tag_db` に存在しないタグであれば `genai-tag-db-tools` を介して `tag_db` に新規登録する。

## 5. データセットのエクスポート (主に `DatasetExportWidget` から実行)

1.  **対象画像の選択:** ユーザーは GUI のエクスポートページで、DB検索機能やサムネイル選択によりエクスポートしたい画像を特定・選択する。
2.  **エクスポート設定:** 出力形式（テキスト、JSON）、出力先ディレクトリ、オプション（最新アノテーションのみ、キャプションマージ等）を選択する。
3.  **エクスポート実行:**
    *   選択された画像のIDに基づき、データベースから必要なアノテーション情報（タグ、キャプション等）を取得する (`idm.get_image_annotations`)。
    *   オプションに応じてアノテーション情報をフィルタリング・加工する。
    *   指定された形式とディレクトリにファイルを出力する (`FileSystemManager.export_dataset_to_txt`, `export_dataset_to_json`)。