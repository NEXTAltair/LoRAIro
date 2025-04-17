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
    -   [ ] `docs/specs/database_management.md` に定義されたスキーマに基づき、SQLAlchemy モデルクラス (`src/lorairo/database/models.py` などに新規作成) を定義する。
    -   [ ] 現在の `ImageRepository` を SQLAlchemy ベースの Repository クラス (`src/lorairo/database/repository.py` などに新規作成) に置き換える。CRUD操作や必要な検索メソッドを実装する。
    -   [ ] Alembic を導入し、データベースの初期化とマイグレーションを管理する設定を行う。
    -   [ ] `models` テーブルへの初期データ投入処理を実装する (Alembicマイグレーション or アプリ初期化)。
-   **関連する決定事項:**
    -   `TAGS.tag_id` は外部キー制約なし (`nullable=True`)。
    -   `tag_db` に存在しないタグは `genai-tag-db-tools` を介して新規登録するロジックを `save_annotations` 周辺に実装。

### 3.2. AIアノテーション機能のライブラリ委譲

-   **目的:** AIモデルとの直接通信ロジックを `lorairo` 本体から削除し、`image-annotator-lib` に完全に委譲する。
-   **対象ファイル:** `src/lorairo/annotations/` (主に `caption_tags.py`, `api_utils.py`, `cleanup_txt.py`)
-   **作業内容:**
    -   [ ] `docs/specs/ai_annotation_interface.md` に定義されたインターフェースに基づき、`image-annotator-lib` を呼び出す処理を実装する。
    -   [ ] `AnnotatorClient` (仮称) のようなラッパークラスをインフラストラクチャ層に作成し、ライブラリ呼び出しの詳細をカプセル化することを検討。
    -   [ ] `AnnotationService` (仮称) をアプリケーション/サービス層に作成し、ライブラリ呼び出しの準備、結果の整形(`formatted_output` のパース含む)、DB保存指示を行う。
    -   [ ] 現在の `ImageAnalyzer`, `APIClientFactory`, `TagCleaner` のうち、`lorairo` 本体で不要になる部分を削除または修正。(`TagCleaner` の一部ロジックは `AnnotationService` に残る可能性あり)

### 3.3. GUIとビジネスロジックの分離

-   **目的:** GUIウィジェットからビジネスロジックを分離し、責務を明確化、テスト容易性を向上させる。
-   **対象ファイル:** `src/lorairo/gui/window/` 配下の各ウィジェット (`edit.py`, `tagger.py`, `overview.py`, `export.py`, `configuration_window.py`)
-   **作業内容:** (進捗: `ConfigurationWindow`, `ImageEditWidget`)
    -   [x] 各ウィジェットクラスから、`ImageDatabaseManager`, `FileSystemManager`, `ImageProcessingManager`, `ImageAnalyzer` (またはその後継クラス) の直接的な呼び出しを削除する。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [x] 代わりに、新設するアプリケーション/サービス層のクラス (`ImageProcessingService`, `ImageTextFileReader`, `DatasetManagementService`, `ConfigurationService` など) のメソッドを呼び出すように変更する。 (`ConfigurationWindow`, `ImageEditWidget` 分完了, `ImageTextFileReader` 新設)
    -   [x] UIイベント(ボタンクリック、テキスト変更など)は、サービス層への処理依頼のトリガーとする。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [x] サービス層からの結果(データやステータス)を受け取り、UIに表示する処理に特化させる。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [x] `ConfigurationWindow` (旧`SettingsWidget`) から APIキーと Hugging Face 設定の直接的な設定ファイルアクセスを削除し、Service経由とする。
-   **チェックリスト:**
    -   [x] 各GUIウィジェット (`edit.py`, `tagger.py`, `overview.py`, `export.py`, `configuration_window.py`) を特定する。 (一部完了)
    -   [x] 各ウィジェットから直接呼び出しをリストアップする。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [x] 各直接呼び出しに対応するアプリケーション/サービス層のメソッドを特定または設計する。 (`ConfigurationService`, `ImageProcessingService`, `ImageTextFileReader` 新設・設計完了)
    -   [x] 各ウィジェットのUIイベントハンドラを特定する。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [x] UIイベントハンドラ内のビジネスロジックをサービス層メソッド呼び出しに置き換える。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [x] サービス層メソッドからの戻り値を受け取りUIを更新する処理を実装する。 (`ConfigurationWindow`, `ImageEditWidget` 分完了)
    -   [ ] `ConfigurationWindow` から APIキーと Hugging Face 設定関連のUI要素とロジックを削除する。(実施せずService経由に)
    -   [ ] `.env` ファイルからの設定読み込みが正しく機能することを確認する。
    -   [ ] GUIウィジェットのユニットテストを作成または更新し、サービス層のモックを使用してテストする。 (`ConfigurationWindow` 分完了)
    -   [x] 関連ドキュメント (`gui_interface.md` など) を更新する。
    -   [ ] **TODO:** `ImageTextFileReader` にファイルベース (.txt/.json) のアノテーション読み込みロジック (`caption_tags.py`, `cleanup_txt.py` の既存機能) を統合する。

### 3.4. 状態管理の見直し

-   **目的:** `ConfigManager` でグローバルに保持されていた `dataset_image_paths` のような状態の管理方法を見直し、データの流れを明確化する。
-   **対象ファイル:** `src/lorairo/gui/window/main_window.py` (`ConfigManager` 削除済み, `MainWindow`)、各ページウィジェット
-   **作業内容:**
    -   [x] `dataset_image_paths` を `ConfigManager` から削除。 (`MainWindow` で保持するように変更)
    -   [ ] 明確なデータフロー(例: `MainWindow` が保持し、各ページに渡す)を定義する。
    -   [ ] `ImageTaggerWidget` の `all_results` のような大きな状態保持について、メモリ効率を考慮した代替案(例: 処理結果を都度DBに書き込む、必要なデータのみ保持するなど)を検討。

### 3.4.1. ConfigManager の役割明確化とリファクタリング (2024-05-24 修正)

-   **役割:** (旧 `ConfigManager`) ~~`utils.config.get_config()` で読み込まれた初期設定をベースとし、GUI操作によって動的に変更されるアプリケーション設定の状態を保持・管理する役割~~ → `ConfigurationService` が担当
-   **課題:**
    -   [x] `ConfigManager` がシングルトンパターンで実装されていた → `ConfigManager` 削除、`ConfigurationService` は `MainWindow` でインスタンス化 (DI)
    -   [x] `dataset_image_paths` という状態を `ConfigManager` が保持していた → `MainWindow` が保持
    -   [x] クラス名 `ConfigManager` が実態と齟齬があった → `ConfigManager` 削除
-   **リファクタリング案:** (実施内容を反映)
    1.  **`ConfigManager` の責務明確化:** → `ConfigurationService` を新設して責務を委譲
        -   [x] クラス名を変更 (`ConfigManager` -> `ConfigurationService`)
        -   [x] 初期化時に設定を読み込み、内部状態で保持 (`ConfigurationService.__init__`)
        -   [x] GUIからの設定変更を受け付け、内部状態を更新 (`ConfigurationService.update_setting`)
        -   [x] `load_config_from_file` 静的メソッド削除 (`ConfigManager` ごと削除)
    2.  **`dataset_image_paths` の分離:**
        -   [x] `ConfigManager` から `dataset_image_paths` 関連コードを削除
        -   [x] `dataset_image_paths` の管理責任を移譲 (`MainWindow` が保持 - 案Bに近い形)
    3.  **インスタンス管理方法の見直し:**
        -   [x] シングルトン廃止 (`ConfigManager` 削除)
        -   [x] `MainWindow` が `ConfigurationService` インスタンスを生成・保持し、`initialize` メソッドで注入 (DI - 案E)
-   **チェックリスト:** (実施内容に合わせて更新)
    -   [x] `ConfigManager` のクラス名を役割に合わせて変更する (実施せず、`ConfigurationService` を新設)
    -   [x] クラスの docstring を更新し、責務を明確化する (`ConfigurationService`)
    -   [x] `ConfigManager` から `dataset_image_paths` 関連のコードを削除する。
    -   [x] `dataset_image_paths` の管理・更新ロジックを `MainWindow` に実装する。
    -   [x] `ConfigManager` のインスタンス管理方法を見直す (シングルトン廃止、DI導入)。
    -   [x] `MainWindow` でインスタンスを生成し、DI を行うように `initialize` メソッド等を修正する。
    -   [x] 各ページウィジェットが DI されたインスタンスを使用するように修正する (`ConfigurationWindow` 分完了)。
    -   [x] `ConfigurationService` の初期化処理を修正し、`get_config()` の結果を内部状態として保持するようにする。
    -   [x] `ConfigurationWindow` で設定変更時に `ConfigurationService` の状態を更新する処理を実装する。
    -   [ ] 他のウィジェットが必要な設定値を `ConfigManager` (削除済) の代わりに `ConfigurationService` から取得するように修正する。(今後のタスク)
    -   [x] データセットディレクトリ変更時に、関連するページウィジェットの表示が正しく更新されることを確認する (分離後の実装)。
    -   [x] `ConfigurationService` に設定をファイルに保存するメソッド (`save_settings()`) を追加する。
    -   [x] `ConfigurationWindow` の保存ボタンクリック時の処理 (`on_buttonSave_clicked`) を修正し、`FileSystemManager` の代わりに `ConfigurationService` の `save_settings()` メソッドを呼び出すように変更する。
    -   [x] (もしあれば) 関連するテストコードを修正する。 (`ConfigurationWindow` のテスト作成完了)
    -   [ ] 関連ドキュメント (`gui_interface.md`, `configuration_management.md` など) を更新する。

---

## 3.x. 全体横断的なリファクタリング・運用・ドキュメント・CI/CD・依存管理

### 3.x.1. ログ機能・運用改善
- [x] `loguru` の導入と `logging` からの完全移行
- [x] 設定ファイル主導のロギング (`config/lorairo.toml` `[log]` セクション)
- [x] モジュールごとのログレベル制御
- [x] テスト・運用時のログ出力一貫性確認
- [ ] ログ仕様・運用ガイド (`logging_specification.md`) の最新化・Memory Bank反映

### 3.x.2. 依存ライブラリ・自作パッケージ管理
- [x] 必須/不要/自作ライブラリの整理 (`lib.md` 参照)
- [ ] `genai-tag-db-tools` のAPI拡張・外部連携 (`genai_tag_db_tools_api_plan.md`)
- [ ] 依存パッケージのバージョン管理・ドキュメント整備

### 3.x.3. Memory Bank運用・ドキュメント
- [x] Memory Bankコアファイルの作成・運用開始
- [ ] Memory Bank運用ガイド (`memory_bank_plan.md`) の整備・運用ルールの明文化
- [ ] UMB(Update Memory Bank)コマンド運用の徹底

### 3.x.4. ドキュメント・設計仕様の整備
- [ ] 仕様書・設計書・インターフェース定義の最新化(Plan/specs配下全体)
- [ ] Mermaid図・全体フロー図の最新化
- [ ] 進捗・決定事項のMemory Bank/decisionLog.mdへの反映

### 3.x.5. CI/CD・テスト自動化
- [ ] テスト自動化(pytest, pytest-bdd, coverage, ruff等)
- [ ] CI/CDパイプラインの整備(GitHub Actions等)
- [ ] テスト・CI運用ガイドの作成

---

## 4. 段階的な進め方 (全体像)

```mermaid
flowchart TD
    subgraph DB層刷新[DB層刷新(SQLAlchemy)]
        done1[完了]
    end
    subgraph AIアノテーション委譲
        A1[仕様確認]
        A2[既存ロジック整理]
        A3[AnnotatorClient新設]
        A4[AnnotationService新設]
        A5[テスト修正]
    end
    subgraph 設定管理リファクタ[設定管理リファクタ (ConfigurationService)]
        B0[ConfigManager削除]
        B1[ConfigurationService新設]
        B2[MainWindowでDI]
        B3[ConfigWindow修正]
        B4[dataset_path分離]
        done2[完了]
    end
    subgraph GUI/ロジック分離
        C1[直接呼び出し削除]
        C2[サービス層経由化]
        C3[UIイベント整理]
    end
    subgraph 状態管理見直し
        D1[データフロー定義]
        D2[大きな状態保持の代替]
    end
    subgraph テスト戦略
        E1[ユニットテスト]
        E2[結合テスト]
        E3[BDD]
        E4[カバレッジ]
    end
    subgraph ドキュメント整備
        F1[仕様書更新]
        F2[MemoryBank反映]
    end
    done1 --> A1
    A1 --> A2 --> A3 --> A4 --> A5
    A5 --> B0
    B0 --> B1 --> B2 --> B3 --> B4 --> done2 # 設定管理完了
    done2 --> C1 # GUI/ロジック分離へ
    C1 --> C2 --> C3
    C3 --> D1
    D1 --> D2
    D2 --> E1
    E1 --> E2 --> E3 --> E4
    E4 --> F1
    F1 --> F2
```

---

## 5. チェックリスト運用・進捗管理

- 各タスクをissueやTODOリストとして管理
- 完了したものはチェック済みにし、進捗をMemory Bankやprogress.mdに反映
- 各ステップで設計・実装・テスト・ドキュメントの観点で抜け漏れがないか確認

---

## 6. 参考: 全体処理フロー概要

- データセット準備・登録 → 画像処理 → AIアノテーション → DB保存 → エクスポート
- 詳細は `overall_workflow.md`、各仕様書参照