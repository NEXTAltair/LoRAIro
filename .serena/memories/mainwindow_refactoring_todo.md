# MainWindowリファクタリングTODO（別ブランチ作業）

**作成日**: 2025-11-10
**対象ブランチ**: 新規ブランチ（feature/annotator-library-integrationではない）
**優先度**: 中
**工数見積**: 大（2-3週間）

---

## 背景

ユーザーからの質問:
> 「MainWindowは巨大なのが修正が必要な気がするんだがどうだろう。メインウィンドウはウィジェットを配置とウィジェット館の情報の受け渡しに機能を絞ったほうが良くないか?」

**回答**: はい、その通りです。

---

## 現状分析

### 基本メトリクス
- **総行数**: 1,645行
- **総メソッド数**: 46メソッド
- **シグナルハンドラー**: 18メソッド
- **依存サービス数**: 9つ

### 責任範囲（6つの責任）

#### 責任1: サービス初期化・管理 (~100行)
**該当メソッド**:
- `__init__()` (189-341行)
- `_initialize_core_services()` (376-459行)
- `_handle_fatal_error()` (461-474行)

**内容**: ServiceContainer、ConfigurationService、WorkerService、AnnotationService、DatasetStateManagerの初期化

**判定**: ✅ MainWindowの責任として適切

---

#### 責任2: ウィジェット配置・設定 (~150行)
**該当メソッド**:
- `_setup_ui()` (343-374行)
- `_configure_custom_widgets()` (476-523行)
- `_setup_responsive_splitter()` (525-552行)

**内容**: Qt Designer生成UIのセットアップ、カスタムウィジェット設定

**判定**: ✅ MainWindowの本来の責任

---

#### 責任3: イベント接続・ルーティング (~300行)
**該当メソッド**:
- `_connect_events()` (554-670行)
- 18個のシグナルハンドラー

**内容**: ウィジェット間のシグナル接続、WorkerServiceパイプライン接続、AnnotationServiceシグナル接続

**判定**: ✅ MainWindowの本来の責任

---

#### 責任4: ビジネスロジックの実装 (~500行) ← **分離対象**
**該当メソッド**:
- `_on_search_completed_start_thumbnail()` (817-886行, 70行)
- `_resolve_optimal_thumbnail_data()` (888-955行, 68行)
- `_on_thumbnail_loading_completed()` (957-1022行, 66行)
- `_on_search_pipeline_cancelled()` (1024-1064行, 41行)

**内容**:
- データ検証・変換ロジック
- パイプライン制御（SearchWorker → ThumbnailWorker連鎖）
- 条件分岐による処理制御
- エラーハンドリング

**問題**: LoRAIro設計原則違反「Service Layer: Business logic belongs in service classes, not GUI components」

**分離先候補**:
- `SearchPipelineService`: パイプライン制御ロジック
- `ImageDataTransformService`: データ変換ロジック

---

#### 責任5: UIアクション実装 (~400行) ← **分離対象**
**該当メソッド**:
- `select_and_process_dataset()` (672-746行, 75行)
- `_start_batch_registration()` (748-793行, 46行)
- `start_annotation()` (795-815行, 21行)
- `open_settings()` (1066-1230行, 165行)
- `export_data()` (1232-1300行, 69行)

**内容**:
- データセット選択ワークフロー
- バッチ登録開始ロジック
- アノテーション処理開始
- 設定ウィンドウ処理（165行の複雑なロジック）
- データエクスポート機能

**問題**: ワークフロー制御ロジックがMainWindow内に実装されている

**分離先候補**:
- `DatasetController`: データセット選択ワークフロー
- `SettingsController`: 設定ウィンドウ処理
- `ExportController`: データエクスポート処理

---

#### 責任6: 状態管理・同期 (~100行) ← **分離対象**
**該当メソッド**:
- `_verify_state_manager_connections()` (1302-1349行, 48行)
- `get_selected_images()` (1351-1381行, 31行)
- `_on_batch_annotation_progress()` (1120-1139行, 20行)

**内容**:
- DatasetStateManagerとの連携ロジック
- 選択画像の取得・管理
- 進捗状態の管理

**問題**: 状態管理ロジックがMainWindow内に散在

**分離先候補**:
- `SelectionStateService`: 選択状態の管理
- `ProgressStateService`: 進捗状態の管理

---

## 問題点

### 1. God Objectの兆候
- ✅ 多数のメソッド: 46個（推奨20-30以下）
- ✅ 長大なコード: 1,645行（推奨500行以下）
- ✅ 多様な責任: 6つの異なる責任
- ✅ 過度な依存: 9つのサービス/マネージャー

### 2. 設計原則違反
- **単一責任原則（SRP）違反**: 6つの異なる責任を持つ
- **LoRAIro Service Layer原則違反**: ビジネスロジックがGUIコンポーネントに混在

### 3. Qt/PySide6ベストプラクティスとの乖離

**Qt公式ドキュメント**:
> "A main window provides a framework for building an application's user interface."

**現在の実装**: ビジネスロジック、データ変換、パイプライン制御がMainWindow内に実装

### 4. テスタビリティへの影響
- ビジネスロジックがGUI環境必須
- 単体テスト困難
- モックが複雑

### 5. 保守性への影響
- 1ファイル1,645行で変更の影響範囲が広い
- 関連機能が分散
- 新機能追加時にMainWindowが肥大化

---

## リファクタリング計画

### Phase 1: サービス層の分離

#### 1.1 SearchPipelineService作成
**責任**: SearchWorker → ThumbnailWorkerのパイプライン制御

**抽出対象**:
- `_on_search_completed_start_thumbnail()` (70行)
- `_on_search_pipeline_cancelled()` (41行)

**API例**:
```python
class SearchPipelineService:
    def start_pipeline(self, search_criteria: SearchCriteria) -> None
    def on_search_completed(self, search_result: dict) -> None
    def cancel_pipeline(self) -> None
```

#### 1.2 ImageDataTransformService作成
**責任**: 画像メタデータからサムネイル表示用データへの変換

**抽出対象**:
- `_resolve_optimal_thumbnail_data()` (68行)

**API例**:
```python
class ImageDataTransformService:
    def resolve_optimal_thumbnail_data(self, metadata: list[dict]) -> list[ThumbnailData]
```

#### 1.3 SelectionStateService作成
**責任**: 選択画像の状態管理

**抽出対象**:
- `get_selected_images()` (31行)
- `_verify_state_manager_connections()` (48行)

**API例**:
```python
class SelectionStateService:
    def get_selected_images(self) -> list[dict]
    def verify_connections(self) -> bool
```

---

### Phase 2: Controllerパターンの導入

#### 2.1 DatasetController作成
**責任**: データセット選択ワークフロー

**抽出対象**:
- `select_and_process_dataset()` (75行)
- `_start_batch_registration()` (46行)

**API例**:
```python
class DatasetController:
    def select_and_process_dataset(self) -> None
    def start_batch_registration(self, dataset_path: Path) -> None
```

#### 2.2 SettingsController作成
**責任**: 設定ウィンドウ処理

**抽出対象**:
- `open_settings()` (165行)

**API例**:
```python
class SettingsController:
    def open_settings_dialog(self) -> None
    def save_settings(self, settings: dict) -> None
```

#### 2.3 AnnotationController作成
**責任**: アノテーション関連の複雑なロジック

**抽出対象**:
- `start_annotation()` (21行)
- `_on_batch_annotation_finished()` (関連ロジック)

**API例**:
```python
class AnnotationController:
    def start_annotation(self, images: list, models: list) -> None
    def handle_batch_finished(self, result: BatchAnnotationResult) -> None
```

---

### Phase 3: MainWindowの縮小

#### 3.1 残す責任
- ✅ ウィジェット配置・設定
- ✅ イベント接続・ルーティング
- ✅ サービス初期化・注入

#### 3.2 削除する責任
- ❌ ビジネスロジック → Service層へ
- ❌ UIアクション → Controller層へ
- ❌ 状態管理 → Service層へ

#### 3.3 期待される結果
- **行数**: 1,645行 → 600-800行（60%削減）
- **メソッド数**: 46個 → 20-25個（50%削減）
- **責任数**: 6つ → 3つ（本来の責任のみ）

---

## 実装順序

### ステップ1: 新規ブランチ作成
```bash
git checkout -b feature/mainwindow-refactoring
```

### ステップ2: サービス層実装（Phase 1）
1. SearchPipelineService実装 + テスト
2. ImageDataTransformService実装 + テスト
3. SelectionStateService実装 + テスト
4. MainWindowから段階的に移行

### ステップ3: Controller層実装（Phase 2）
1. DatasetController実装 + テスト
2. SettingsController実装 + テスト
3. AnnotationController実装 + テスト
4. MainWindowから段階的に移行

### ステップ4: MainWindow縮小（Phase 3）
1. 不要なメソッド削除
2. シグナル接続の整理
3. テスト更新

### ステップ5: 統合テスト
1. 全体の動作確認
2. 回帰テスト
3. パフォーマンステスト

---

## 完了基準

- ✅ MainWindow行数: 600-800行以内
- ✅ MainWindowメソッド数: 20-25個以内
- ✅ MainWindow責任数: 3つ（初期化、配置、接続）
- ✅ 全テストパス
- ✅ Service層のカバレッジ75%以上
- ✅ Controller層のカバレッジ75%以上

---

## リスク

### 1. 影響範囲の広さ
- MainWindowは多くのウィジェット・サービスと連携
- 段階的な移行が必須

### 2. テストの複雑さ
- 既存テストの更新が必要
- 新規Service/Controllerのテスト追加

### 3. 互換性
- 既存のシグナル接続を維持する必要
- 段階的なリファクタリングで対応

---

## 参考資料

### 既存の良好な分離例
- `FilterSearchPanel`: ServiceとWorkerの依存注入、独立した動作
- `ThumbnailSelectorWidget`: DatasetStateManagerとの連携に特化
- `WorkerService`: ワーカー管理ロジックのサービス化

### 設計原則
- CLAUDE.md: "Service Layer: Business logic belongs in service classes, not GUI components"
- Qt公式ドキュメント: "A main window provides a framework for building an application's user interface"

### メトリクス基準
- 推奨行数: 500行以下
- 推奨メソッド数: 20-30個以下
- 推奨依存数: 5個以下

---

## 関連ファイル

- **対象**: `src/lorairo/gui/window/main_window.py` (1,645行)
- **参照**: `src/lorairo/gui/widgets/filter_search_panel.py` (良好な分離例)
- **参照**: `src/lorairo/gui/services/worker_service.py` (Service層の例)

---

## 次のアクション

1. このTODOを別ブランチ作業として登録
2. 優先度・スケジュールを決定
3. Phase 1から段階的に実装開始

---

**作成者**: Claude Code
**最終更新**: 2025-11-10
