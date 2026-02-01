# サービス層アーキテクチャ

## 概要

LoRAIroは2層サービスアーキテクチャを採用し、Qt-freeなビジネスロジックとQt-dependentなGUIサービスを分離しています。

**設計原則:**
- **Business Logic Services**: Qt依存なし、CLI/GUI/API全てで再利用可能
- **GUI Services**: Qt依存、Signal/Slotによるウィジェット間通信
- **Qt-Free Core Pattern**: コアサービスはQt-free、GUIラッパーはCompositionパターンでSignalサポート

**ディレクトリ構成:**
- `src/lorairo/services/` - Business Logic Services (23 files)
- `src/lorairo/gui/services/` - GUI Services (8 files)

## ビジネスロジックサービス

Qt依存のないビジネスロジックサービス群。CLI、GUI、API全てで共通利用可能。

### コアインフラ

#### ServiceContainer
- **Path**: `src/lorairo/services/service_container.py`
- **Class**: `ServiceContainer`
- **Purpose**: 依存性注入(DI)コンテナ、全サービスの一元管理
- **Pattern**: Singleton pattern
- **Functions**: `get_service_container()`, `get_config_service()`, `get_model_sync_service()`

#### ConfigurationService
- **Path**: `src/lorairo/services/configuration_service.py`
- **Class**: `ConfigurationService`
- **Purpose**: アプリケーション設定の読み込み、更新、保存
- **Config**: `config/lorairo.toml` の管理

#### SignalManagerService
- **Path**: `src/lorairo/services/signal_manager_service.py`
- **Class**: `SignalManagerService`
- **Purpose**: アプリケーション全体のSignal通信管理
- **Protocol**: `signal_manager_protocol.py` でインターフェース定義

### タグ管理

#### TagManagementService
- **Path**: `src/lorairo/services/tag_management_service.py`
- **Class**: `TagManagementService`
- **Purpose**: User DB専用のタグ管理（Base DBは対象外）
- **Integration**: genai-tag-db-tools公開API (`search_tags()`, `register_tag()`)
- **Strategy**: format_id=1000+, type_name="unknown" placeholder
- **Operations**: unknown typeタグ検索、type一覧取得、一括type更新

### AIアノテーション

#### AnnotatorLibraryAdapter
- **Path**: `src/lorairo/services/annotator_library_adapter.py`
- **Class**: `AnnotatorLibraryAdapter`
- **Purpose**: image-annotator-lib統合アダプター
- **Providers**: OpenAI, Anthropic, Google, Local ML models
- **Returns**: `PHashAnnotationResults`

#### BatchProcessor
- **Path**: `src/lorairo/services/batch_processor.py`
- **Purpose**: バッチアノテーション処理の調整

#### OpenAIBatchProcessor
- **Path**: `src/lorairo/services/openai_batch_processor.py`
- **Purpose**: OpenAI Batch API専用プロセッサ

### 画像処理

#### ImageProcessingService
- **Path**: `src/lorairo/services/image_processing_service.py`
- **Class**: `ImageProcessingService`
- **Purpose**: 画像処理ワークフロー（リサイズ、変換、品質評価）

#### DatasetExportService
- **Path**: `src/lorairo/services/dataset_export_service.py`
- **Class**: `DatasetExportService`
- **Purpose**: データセットのエクスポート機能

### モデル管理

#### ModelFilterService
- **Path**: `src/lorairo/services/model_filter_service.py`
- **Class**: `ModelFilterService`
- **Purpose**: AIモデルのフィルタリングと管理

#### ModelSelectionService
- **Path**: `src/lorairo/services/model_selection_service.py`
- **Class**: `ModelSelectionService`
- **Purpose**: モデル選択ロジックとプリセット管理

#### ModelSyncService
- **Path**: `src/lorairo/services/model_sync_service.py`
- **Class**: `ModelSyncService`
- **Purpose**: モデル設定の同期とキャッシュ管理

#### ModelInfoManager
- **Path**: `src/lorairo/services/model_info_manager.py`
- **Class**: `ModelInfoManager`
- **Purpose**: モデルメタデータの管理

#### ModelRegistryProtocol
- **Path**: `src/lorairo/services/model_registry_protocol.py`
- **Purpose**: モデルレジストリのプロトコル定義

### Search & Filter

#### SearchCriteriaProcessor
- **Path**: `src/lorairo/services/search_criteria_processor.py`
- **Class**: `SearchCriteriaProcessor`
- **Purpose**: 検索条件の処理とフィルタリングロジック

#### SearchModels
- **Path**: `src/lorairo/services/search_models.py`
- **Purpose**: 検索用データモデル定義

### 状態管理

#### SelectionStateService
- **Path**: `src/lorairo/services/selection_state_service.py`
- **Class**: `SelectionStateService`
- **Purpose**: アプリケーション内選択状態の管理

### ユーティリティ

#### DateFormatter
- **Path**: `src/lorairo/services/date_formatter.py`
- **Purpose**: 日付フォーマット統一処理

#### BatchUtils
- **Path**: `src/lorairo/services/batch_utils.py`
- **Purpose**: バッチ処理のユーティリティ関数

#### UIResponsiveConversionService
- **Path**: `src/lorairo/services/ui_responsive_conversion_service.py`
- **Purpose**: UI応答性を保ったデータ変換処理

#### FavoriteFiltersService
- **Path**: `src/lorairo/services/favorite_filters_service.py`
- **Class**: `FavoriteFiltersService`
- **Purpose**: お気に入りフィルター条件の永続化管理
- **Storage**: QSettings (JSON serialization)
- **Operations**: `save_filter()`, `load_filter()`, `list_filters()`, `delete_filter()`, `filter_exists()`
- **Features**:
  - フィルター名での重複チェック
  - Unicode名対応
  - アプリケーション再起動後も永続化
- **Integration**: FilterSearchPanel経由で利用

## GUIサービス

Qt依存のGUIサービス群。Signal/Slotによるウィジェット間通信をサポート。

### Worker調整

#### WorkerService
- **Path**: `src/lorairo/gui/services/worker_service.py`
- **Class**: `WorkerService`
- **Purpose**: Qt-basedの非同期タスク調整
- **Pattern**: QThreadPool + QRunnable
- **Integration**: WorkerManagerと連携

### 検索・フィルタ

#### SearchFilterService
- **Path**: `src/lorairo/gui/services/search_filter_service.py`
- **Class**: `SearchFilterService`
- **Purpose**: GUI向け検索・フィルタ操作
- **Integration**: MainWindow統合完了
- **Signals**: 検索結果、フィルタ状態変更通知

### パイプライン制御

#### PipelineControlService
- **Path**: `src/lorairo/gui/services/pipeline_control_service.py`
- **Class**: `PipelineControlService`
- **Purpose**: 処理パイプラインの制御とステート管理

### 状態・進捗管理

#### ProgressStateService
- **Path**: `src/lorairo/gui/services/progress_state_service.py`
- **Class**: `ProgressStateService`
- **Purpose**: 進捗状態の管理とSignal通知

#### ResultHandlerService
- **Path**: `src/lorairo/gui/services/result_handler_service.py`
- **Class**: `ResultHandlerService`
- **Purpose**: 処理結果のハンドリングとUI反映

### データベース統合

#### ImageDBWriteService
- **Path**: `src/lorairo/gui/services/image_db_write_service.py`
- **Class**: `ImageDBWriteService`
- **Purpose**: 画像データベース書き込み操作のGUIラッパー

### ウィジェットセットアップ

#### WidgetSetupService
- **Path**: `src/lorairo/gui/services/widget_setup_service.py`
- **Class**: `WidgetSetupService`
- **Purpose**: ウィジェット初期化とセットアップのヘルパー
- **Methods**:
  - `setup_thumbnail_selector()` - サムネイルセレクター設定
  - `setup_image_preview()` - 画像プレビュー設定
  - `setup_selected_image_details()` - 画像詳細ウィジェット設定
  - `setup_splitter()` - スプリッター初期化
  - `setup_batch_tag_tab_widgets()` - バッチタグタブウィジェット統合（Phase 2.5）
  - `setup_all_widgets()` - 全ウィジェット一括設定

#### TabReorganizationService
- **Path**: `src/lorairo/gui/services/tab_reorganization_service.py`
- **Class**: `TabReorganizationService`
- **Purpose**: MainWindowのプログラム的UI再構成
- **Phase**: 2.5（Phase 2とPhase 3の間で実行）
- **Pattern**: 静的メソッド、.uiファイル無変更でレイアウト変更
- **Architecture**:
  - トップレベルタブ構造導入（ワークスペース / バッチタグ）
  - 既存ウィジェットの再親子化（3ステップ: removeWidget → setParent → addWidget）
  - Qt Designer定義ウィジェットをプログラム的に再配置
- **Methods**:
  - `create_main_tab_widget()` - トップレベルQTabWidget生成
  - `extract_existing_widgets()` - MainWindowから既存ウィジェット抽出
  - `build_workspace_tab()` - ワークスペースタブ構築
  - `build_batch_tag_tab()` - バッチタグタブスケルトン構築
  - `reorganize_main_window_layout()` - レイアウト再構成オーケストレーター
- **Integration**: MainWindow.__init__() Phase 2.5で呼び出し
- **Benefits**:
  - 作業モードの明確な視覚的分離（閲覧 vs 一括編集）
  - バッチタグ機能の全画面活用
  - .uiファイル無変更による安全性確保

### GUI Widgets

Qt-basedのGUIウィジェット群。MainWindow内でQTabWidgetとして統合。

#### BatchTagAddWidget
- **Path**: `src/lorairo/gui/widgets/batch_tag_add_widget.py`
- **UI**: `src/lorairo/gui/designer/BatchTagAddWidget.ui`
- **Class**: `BatchTagAddWidget`
- **Purpose**: 複数画像に対して1つのタグを一括追加
- **Architecture**:
  - QTabWidget タブ3（バッチタグ追加）として統合
  - OrderedDict[int, str] でステージングリスト管理（挿入順保持 + 重複防止）
  - 500画像のステージング上限
- **Integration**:
  - TagCleaner.clean_format() による正規化（underscores → spaces, lowercase）
  - DatasetStateManager.selected_image_ids からの選択画像取得
  - ImageDBWriteService.add_tag_batch() による一括DB書き込み
- **Signals**:
  - `staged_images_changed(list)` - ステージングリスト変更通知
  - `tag_add_requested(list, str)` - タグ追加リクエスト（image_ids, normalized_tag）
  - `staging_cleared()` - ステージングリストクリア通知
- **Features**:
  - ドラッグ選択同期（ThumbnailSelectorWidget → DatasetStateManager）
  - 個別削除（Delete キーで選択アイテム削除）
  - 全クリアボタン
  - 空タグバリデーション
  - 重複画像の自動スキップ
- **Testing**:
  - Unit tests: 21 tests, 97% coverage
  - Integration tests: 11 tests, 100% pass rate

#### RatingScoreEditWidget
- **Path**: `src/lorairo/gui/widgets/rating_score_edit_widget.py`
- **UI**: `src/lorairo/gui/designer/RatingScoreEditWidget.ui`
- **Class**: `RatingScoreEditWidget`
- **Purpose**: 単一画像のRating/Score編集
- **Architecture**:
  - QTabWidget タブ2（Rating/Score編集）として統合
  - SelectedImageDetailsWidget から分離（読み取り専用化）
- **UI Components**:
  - Rating選択: QComboBox（PG, PG-13, R, X, XXX）
  - Score調整: QSlider（0-1000内部値、0.00-10.00表示）
  - 現在値ラベル: リアルタイム更新
- **Data Conversion**:
  - UI内部: 0-1000（精度維持）
  - UI表示: 0.00-10.00（value/100.0）
  - DB格納: 0.0-10.0 Float（value/100.0）
- **Signals**:
  - `rating_changed(int, str)` - Rating変更通知（image_id, rating）
  - `score_changed(int, int)` - Score変更通知（image_id, score）

## 設計パターン

### Qt-Free Coreパターン

**目的:** CLIツールがQt依存なしで動作可能に、GUIは完全なSignalサポート

**実装例: TagRegisterService**

```
Core Service (Qt-free):
  genai_tag_db_tools/services/tag_register.py
  - TagRegisterService (Qt依存なし)
  - register_tag(), search_and_register() 等のコアロジック

GUI Wrapper (Qt-dependent):
  genai_tag_db_tools/gui/services/gui_tag_register_service.py
  - GuiTagRegisterService (QObject継承)
  - Compositionパターンでコアサービスを内包
  - Signal emit (tag_registered, error_occurred等)
```

**パターンの利点:**
- CLIツール: コアサービスを直接使用（Qt不要）
- GUIアプリ: GUIラッパー経由でSignal通知受信
- テスタビリティ: コアロジックは単独でテスト可能

### 依存性注入 (DI)

**ServiceContainerによるDI管理:**
- 全サービスのシングルトンインスタンス管理
- 依存関係の自動解決
- テスト時のモック注入サポート

**使用例:**
```python
from src.lorairo.services.service_container import get_service_container

container = get_service_container()
config = container.get_config_service()
tag_service = container.get_tag_management_service()
```

### Signal通信

**GUI Services間通信:**
- Qt Signal/Slotによる疎結合
- イベント駆動アーキテクチャ
- 非同期処理の完了通知

**主要Signal:**
- `SearchFilterService`: 検索結果、フィルタ変更
- `ProgressStateService`: 進捗更新
- `ResultHandlerService`: 処理完了、エラー通知

## サービスライフサイクル

### 初期化順序

1. **ConfigurationService**: 設定ファイル読み込み
2. **ServiceContainer**: DIコンテナ初期化
3. **Business Logic Services**: コアサービス初期化
4. **GUI Services**: ウィジェット連携サービス初期化

### シャットダウンプロセス

1. GUI Services: Signal切断、リソース解放
2. Business Logic Services: 処理中タスクの完了待機
3. Database: コネクション終了
4. Configuration: 設定保存

## テスト戦略

### ユニットテスト

- **Business Logic Services**: Qt依存なしで単独テスト可能
- **Mock不要**: 外部依存（filesystem, network, API）のみモック
- **Coverage Target**: 75%+

### 統合テスト

- **GUI Services**: pytest-qtによるSignalテスト
- **Pattern**: `qtbot.waitSignal()`, `qtbot.waitUntil()`
- **Mock**: `QMessageBox`等のUI要素のみ

### テスト構造

```
tests/
├── unit/
│   └── services/          # Business Logic Services
├── integration/
│   └── gui/services/      # GUI Services
└── bdd/                   # E2E tests
```

## メンテナンスガイドライン

### 新規サービス追加

1. **Business Logic Service**: Create in `src/lorairo/services/`
   - Qt依存なし
   - Google-style docstring
   - Type hints必須
   - ServiceContainerに登録

2. **GUI Service**: Create in `src/lorairo/gui/services/`
   - QObject継承
   - Signal定義
   - Compositionパターンでコアロジック委譲

### サービスの責任

**Single Responsibility Principle (SRP) 遵守:**
- 1サービス = 1明確な責任
- 複雑化したら分割を検討
- 例: `ModelService` → `ModelFilterService`, `ModelSelectionService`, `ModelSyncService`

### 非推奨化プロセス

1. `@deprecated` decorator追加
2. 新サービスへの移行パス文書化
3. 1リリースサイクル後に削除

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) - Development overview
- [docs/integrations.md](integrations.md) - External package integration
- [docs/testing.md](testing.md) - Testing strategies
- [docs/architecture.md](architecture.md) - System design principles
