# クラス再設計・リファクタリング計画

## 1. 背景

現在のコードベースでは、GUIとビジネスロジックの密結合、クラス間の密結合、状態管理の課題、ライブラリインターフェースの曖昧さ、テスト容易性の低さなどの問題点が指摘されている。これらの問題を解決し、保守性、拡張性、テスト容易性を向上させるために、大規模なリファクタリングを実施する。

## 2. 基本方針: レイヤードアーキテクチャの導入

責務の分離を明確にするため、以下のレイヤードアーキテクチャを採用する。

1.  **プレゼンテーション層 (GUI):** ユーザーインターフェースの表示、ユーザー入力受付、Application/Service層への処理依頼、結果表示を担当。
2.  **アプリケーション/サービス層:** GUIからのリクエストを受け、ドメインロジックやインフラストラクチャ層の機能を組み合わせてユースケースを実現。
3.  **ドメイン層 (Core):** アプリケーションの中核となるビジネスルールやデータ構造を定義 (SQLAlchemyモデルなど)。
4.  **インフラストラクチャ層:** データベースアクセス、ファイルシステム操作、外部API/ライブラリ連携など、技術的詳細を担当。

## 3. 主要な変更計画

### 3.1. データベース層の刷新 (SQLAlchemy移行)

-   **目的:** 標準 `sqlite3` から SQLAlchemy ORM へ移行し、コードの可読性・保守性を向上させ、`genai-tag-db-tools` との技術スタックを統一する。画像レーティング機能、手動編集フラグ等に対応した新しいスキーマを導入する。
-   **対象ファイル:** `src/lorairo/database/database.py`
-   **作業内容:**
    -   `docs/specs/database_management.md` に定義されたスキーマに基づき、SQLAlchemy モデルクラス (`src/lorairo/database/models.py` などに新規作成) を定義する。
    -   現在の `ImageRepository` を SQLAlchemy ベースの Repository クラス (`src/lorairo/database/repository.py` などに新規作成) に置き換える。CRUD操作や必要な検索メソッドを実装する。
    -   Alembic を導入し、データベースの初期化とマイグレーションを管理する設定を行う。
    -   `models` テーブルへの初期データ投入処理を実装する (Alembicマイグレーション or アプリ初期化)。
-   **関連する決定事項:**
    -   `TAGS.tag_id` は外部キー制約なし (`nullable=True`)。
    -   `tag_db` に存在しないタグは `genai-tag-db-tools` を介して新規登録するロジックを `save_annotations` 周辺に実装。

### 3.2. AIアノテーション機能のライブラリ委譲

-   **目的:** AIモデルとの直接通信ロジックを `lorairo` 本体から削除し、`image-annotator-lib` に完全に委譲する。
-   **対象ファイル:** `src/lorairo/annotations/` (主に `caption_tags.py`, `api_utils.py`, `cleanup_txt.py`)
-   **作業内容:**
    -   `docs/specs/ai_annotation_interface.md` に定義されたインターフェースに基づき、`image-annotator-lib` を呼び出す処理を実装する。
    -   `AnnotatorClient` (仮称) のようなラッパークラスをインフラストラクチャ層に作成し、ライブラリ呼び出しの詳細をカプセル化することを検討。
    -   `AnnotationService` (仮称) をアプリケーション/サービス層に作成し、ライブラリ呼び出しの準備、結果の整形（`formatted_output` のパース含む）、DB保存指示を行う。
    -   現在の `ImageAnalyzer`, `APIClientFactory`, `TagCleaner` のうち、`lorairo` 本体で不要になる部分を削除または修正。(`TagCleaner` の一部ロジックは `AnnotationService` に残る可能性あり)

### 3.3. GUIとビジネスロジックの分離

-   **目的:** GUIウィジェットからビジネスロジックを分離し、責務を明確化、テスト容易性を向上させる。
-   **対象ファイル:** `src/lorairo/gui/window/` 配下の各ウィジェット (`edit.py`, `tagger.py`, `overview.py`, `export.py`, `settings.py`)
-   **作業内容:**
    -   各ウィジェットクラスから、`ImageDatabaseManager`, `FileSystemManager`, `ImageProcessingManager`, `ImageAnalyzer` (またはその後継クラス) の直接的な呼び出しを削除する。
    -   代わりに、新設するアプリケーション/サービス層のクラス (`ImageProcessingService`, `AnnotationService`, `DatasetManagementService`, `ConfigurationService` など) のメソッドを呼び出すように変更する。
    -   UIイベント（ボタンクリック、テキスト変更など）は、サービス層への処理依頼のトリガーとする。
    -   サービス層からの結果（データやステータス）を受け取り、UIに表示する処理に特化させる。
    -   `SettingsWidget` から APIキーと Hugging Face 設定のUI要素を削除し、`.env` ファイルからの読み込みを前提とするように関連ロジックを修正。

### 3.4. 状態管理の見直し

-   **目的:** `ConfigManager` でグローバルに保持されている `dataset_image_paths` のような状態の管理方法を見直し、データの流れを明確化する。
-   **対象ファイル:** `src/lorairo/gui/window/main_window.py` (`ConfigManager`, `MainWindow`)、各ページウィジェット
-   **作業内容:**
    -   `dataset_image_paths` を `ConfigManager` から削除し、`MainWindow` または各ページが必要に応じて `FileSystemManager` を介して取得・管理するように変更することを検討。
    -   あるいは、明確なデータフロー（例: `MainWindow` が保持し、各ページに渡す）を定義する。
    -   `ImageTaggerWidget` の `all_results` のような大きな状態保持について、メモリ効率を考慮した代替案（例: 処理結果を都度DBに書き込む、必要なデータのみ保持するなど）を検討。

### 3.5. テスト戦略の策定と実装

-   **目的:** リファクタリング後のコード品質を保証し、今後の開発を容易にするためのテストを導入する。
-   **作業内容:**
    -   各レイヤー（特にサービス層、リポジトリ層）に対するユニットテストを作成する。依存関係はモックやスタブを使用して分離する。
    -   主要なユースケース（画像処理フロー、アノテーションフロー、エクスポートフローなど）に対する結合テストを作成する。
    -   BDD (pytest-bdd) を活用し、Feature ファイルとステップ定義を作成して、ユーザー視点での振る舞いをテストする。
    -   テストカバレッジを計測し、目標値を設定して維持する。

## 4. 段階的な進め方 (案)

1.  **データベース層の刷新:** SQLAlchemy モデル定義、Repositoryクラス実装、Alembic設定。
2.  **AIアノテーション連携:** `AnnotatorClient` (仮), `AnnotationService` (仮) の実装、`image-annotator-lib` 呼び出し部分の実装。
3.  **GUIリファクタリング (段階的に):**
    *   まず `ImageTaggerWidget` を新しいサービス層 (`AnnotationService`, `DatasetManagementService`) と連携するように修正。
    *   次に `ImageEditWidget` を `ImageProcessingService`, `DatasetManagementService` と連携するように修正。
    *   `DatasetOverviewWidget`, `DatasetExportWidget` を `DatasetManagementService` と連携するように修正。
    *   `SettingsWidget` を修正。
4.  **状態管理の見直し:** `ConfigManager` や各ウィジェットの状態保持方法を修正。
5.  **テスト実装:** 各段階で並行してユニットテスト、結合テスト、BDDテストを実装。

この計画は状況に応じて見直すものとする。