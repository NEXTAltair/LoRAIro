# GUI実装手順指針とStage 2計画

## 📋 GUI実装手順の標準パターン（ユーザー指針）

### 実装順序
1. **UIファイル作成**: Qt Designerで.uiファイルのレイアウト設計
2. **ウィジェットクラス作成**: .uiファイルを基にしたウィジェット実装
3. **単体動作確認**: main部分でウィジェット単体の動作テスト
4. **統合**: 動作確認できたウィジェットを使用先ウィジェットに統合

### パターンの利点
- レイアウト設計と実装ロジックの分離
- 段階的な動作確認による問題の早期発見
- 独立した単体テストが可能
- 統合時の問題切り分けが容易

**重要**: この手順はLoRAIroプロジェクトでのGUI開発における標準的なアプローチとして今後の開発で必ず適用する。

## 🎯 Stage 2: ビジネスロジック分離フェーズ実装計画

### 現状分析
- ✅ **Stage 0-1完了**: git grep強制Hooks実装、ファイル名変更とデータ層責任強化
- ✅ **Hook System**: 完全実装済み（block_grep.py, bash_grep_checker.py, read_mcp_memorys.py）
- ✅ **CustomRangeSlider**: 87行に簡素化済み（superqt QDoubleRangeSlider活用）
- ✅ **SearchFilterService**: 1,182行で現在運用中（Stage 2で分離対象）

### 現在のブランチ状況
- **Current Branch**: `refactor/search-filter-service-cleanup`
- **Target**: SearchFilterServiceの責任分離によるアーキテクチャ品質向上

## 📋 Stage 2実装計画詳細

### Phase 1: サービス層分離（2日）

#### **SearchCriteriaProcessor新規作成**
```python
# src/lorairo/services/search_criteria_processor.py (300行目標)
class SearchCriteriaProcessor:
    """検索・フィルタリングビジネスロジック専用サービス"""
    
    def __init__(self, db_manager: ImageDatabaseManager):
        self.db_manager = db_manager
    
    # 移行対象メソッド（SearchFilterServiceから）:
    def execute_search_with_filters(self, conditions) -> tuple[list, int]:
        # DB検索はdb_managerに委譲、フロントエンドフィルターのみここで処理
    def separate_search_and_filter_conditions(self, conditions) -> tuple
    def _convert_to_db_query_conditions(self, search_conditions) -> dict
    def _apply_frontend_filters(self, images, filters) -> list
    def process_resolution_filter(self, conditions) -> dict
    def process_date_filter(self, conditions) -> dict
    def apply_untagged_filter(self, conditions) -> dict
    def apply_tagged_filter_logic(self, conditions) -> dict
```

#### **ModelFilterService新規作成**
```python
# src/lorairo/services/model_filter_service.py (350行目標)
class ModelFilterService:
    """モデル管理・フィルタリング専用サービス"""
    
    def __init__(self, db_manager: ImageDatabaseManager, 
                 model_selection_service: ModelSelectionService):
        # モデル情報はModelSelectionServiceから
        # DB操作はImageDatabaseManagerに委譲
    
    # 移行対象メソッド（SearchFilterServiceから）:
    def get_annotation_models_list(self) -> list
    def filter_models_by_criteria(self, criteria) -> list
    def infer_model_capabilities(self, model_data) -> list
    def apply_advanced_model_filters(self, images, conditions) -> list
    def optimize_advanced_filtering_performance(self, images, conditions) -> list
    def validate_annotation_settings(self, settings) -> ValidationResult
```

### Phase 2: ImageDatabaseManager責任拡張

#### **データ層責任移譲**
```python
# src/lorairo/database/db_manager.py への追加メソッド
class ImageDatabaseManager:
    def get_dataset_status(self) -> dict[str, Any]:
        """データセット統計情報取得 - データ層の適切な責任"""
        
    def get_annotation_status_counts(self) -> dict[str, int]:
        """アノテーション状態カウント - データ層の適切な責任"""
        
    def execute_filtered_search(self, conditions: dict) -> tuple[list, int]:
        """フィルタリング検索実行 - データ層の適切な責任"""
        
    def check_image_has_annotation(self, image_id: int) -> bool:
        """アノテーション存在チェック - データ層の適切な責任"""
```

**移譲対象処理**:
- get_dataset_status() → db_manager.get_dataset_status()
- get_annotation_status_counts() → db_manager.get_annotation_status_counts()
- filter_by_annotation_status() → db_manager.filter_by_annotation_status()
- get_directory_images() → db_manager.get_directory_images_metadata()

### Phase 3: SearchFilterService純化（GUI手順指針適用）

#### **GUI専用サービスに縮小（150行目標）**
```python
# src/lorairo/gui/services/search_filter_service.py (大幅縮小)
class SearchFilterService:
    """GUI専用検索フィルターサービス（150行目標）"""
    
    def __init__(self, 
                 criteria_processor: SearchCriteriaProcessor,
                 model_filter_service: ModelFilterService):
        # 純粋にGUI固有処理のみ
        self.criteria_processor = criteria_processor
        self.model_filter_service = model_filter_service
        
    # 残存メソッド（GUI専用）:
    def create_search_conditions_from_ui(self, ui_params) -> SearchConditions
    def create_search_preview(self, conditions) -> str
    def get_available_resolutions(self) -> list[str]
    def get_available_aspect_ratios(self) -> list[str]
    def validate_ui_inputs(self, inputs) -> ValidationResult
```

#### **後方互換性確保**
- 既存呼び出し元への一時的ラッパーメソッド実装
- 段階的移行期間でのAPI互換性維持

## 🔧 実装手順（GUI指針準拠）

### Day 1: サービス層基盤
1. **SearchCriteriaProcessor作成・実装**: ビジネスロジック移行
2. **ModelFilterService作成・実装**: モデル管理実装
3. **単体テスト作成**: 各サービス独立動作確認（main部分での動作テスト）

### Day 2: データ層拡張・GUI統合
1. **ImageDatabaseManagerメソッド追加**: データアクセス責任移譲
2. **SearchFilterService純化**: GUI専用に縮小（150行目標）
3. **後方互換ラッパー実装**: 既存呼び出し元対応
4. **統合テスト**: 既存GUI動作確認

## 📊 期待効果

### コード量最適化
- **現在**: SearchFilterService 1,182行
- **分離後**:
  - SearchCriteriaProcessor: 300行（新規）
  - ModelFilterService: 350行（新規）
  - SearchFilterService: 150行（純化）
  - ImageDatabaseManager: +100行（責任追加）
- **実質削減**: 282行削減 + 責任境界明確化

### アーキテクチャ改善
```
データ層: ImageDatabaseManager
├── データベース直接操作統合
└── 統計・検索実行責任

ビジネスロジック層（新規）:
├── SearchCriteriaProcessor (検索・フィルター)
└── ModelFilterService (モデル管理)

GUI層: SearchFilterService
└── UI専用処理のみ（150行）
```

### 技術的改善
- **責任分離**: レイヤードアーキテクチャの確立
- **保守性**: 単一責任原則によるメンテナンス容易性
- **再利用性**: ビジネスロジックの独立
- **テスタビリティ**: モック対象明確化による単体テスト向上

## ⚠️ リスク管理

### 高リスク要因と対策
**1. 既存機能の破綻**
- リスク: 分離時の見落としによる機能不全
- 対策: 段階的移行、包括的テスト、バックアップブランチ保持

**2. GUI手順指針の適用**
- 新規ウィジェット作成時は必ず.ui → クラス → 単体確認 → 統合の順序
- 既存SearchFilterServiceの変更は段階的実施
- 後方互換性維持による安全な移行

**3. パフォーマンス劣化**  
- リスク: サービス間通信オーバーヘッド
- 対策: パフォーマンステスト、プロファイリング、最適化

## ✅ 成功指標
- SearchFilterService 150行達成
- 新サービス層の独立動作確認
- 全GUI機能の継続動作
- テストカバレッジ 85%以上維持
- GUI手順指針の適切な適用

## 📋 次ステップ
完了後、Stage 3（GUI層純化）→ Stage 4（ウィジェット統合）へ進行予定

---

**計画策定日**: 2025-08-15
**対象ブランチ**: refactor/search-filter-service-cleanup
**GUI手順指針**: 必須適用パターンとして記録
**承認待ち**: ユーザー確認・実装開始承認