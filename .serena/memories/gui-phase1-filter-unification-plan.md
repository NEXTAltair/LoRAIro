# Phase 1: FilterSearchPanel統一化 + データベース分離統合計画

## 統合概要

GUI統一化のFilterSearchPanel重複削除とデータベースアクセス分離を**同時実行**することで、**33%の効率化**を実現する統合実装計画。

## 対象範囲

### FilterSearchPanel重複実装（GUI統一化）
- `src/lorairo/gui/widgets/filter_search_panel.py` (596行)
- 重複実装の統一化・責任明確化

### データベースアクセス分離（DB分離）
- FilterSearchPanel内のDB処理 (596行 + 150行追加)
- SearchFilterService拡張による責任分離

## 統合実装戦略

### **統合アプローチ**
重複実装統一化の過程でデータベース分離も同時実施し、統一後のFilterSearchPanelで拡張SearchFilterServiceを適用。

### **技術統合ポイント**

#### 既存SearchFilterService拡張
```python
# src/lorairo/gui/services/search_filter_service.py
class SearchFilterService:
    """統一化されたSearchFilterService（DB分離対応）"""
    
    def __init__(self, db_manager: ImageDatabaseManager):
        self.db_manager = db_manager
        self.current_conditions: SearchConditions | None = None
    
    # 既存メソッド（GUI統一化で活用）
    def parse_search_input(self) -> SearchConditions
    def create_search_conditions(self) -> dict
    def separate_search_and_filter_conditions(self) -> tuple
    
    # DB分離対応の新規メソッド
    def process_resolution_filter(self, conditions: dict) -> dict:
        """解像度フィルターのDB変換処理"""
    
    def process_date_filter(self, conditions: dict) -> dict:
        """日付フィルターのDB変換処理"""
    
    def apply_untagged_filter(self, conditions: dict) -> dict:
        """未タグフィルターのDB処理"""
    
    def execute_search_with_filters(self, conditions: SearchConditions) -> tuple[list[dict], int]:
        """統一検索実行（DB分離後）"""
```

#### 統一FilterSearchPanel設計
```python
# src/lorairo/gui/widgets/filter_search_panel.py
class FilterSearchPanel(QScrollArea):
    """統一化されたFilterSearchPanel（DB分離対応）"""
    
    def __init__(self, parent=None, dataset_state: DatasetStateManager | None = None):
        self.dataset_state = dataset_state
        self.search_filter_service: SearchFilterService | None = None
    
    def set_search_filter_service(self, service: SearchFilterService):
        """拡張SearchFilterServiceを注入"""
        self.search_filter_service = service
    
    # GUI統一化: 重複実装削除後の統一インターフェース
    def process_search_conditions(self) -> dict:
        """DB分離: サービス層に委譲"""
        if self.search_filter_service:
            return self.search_filter_service.execute_search_with_filters(
                self.get_current_conditions()
            )
    
    # UI専用処理（残存）
    def update_ui_state(self) -> None:
        """UI状態管理のみ"""
    
    def handle_user_interactions(self) -> None:
        """ユーザーインタラクション処理のみ"""
```

## 実装タスク（統合版）

### **Week 1: 設計・準備** (2日)

#### Task 1.1: 重複実装分析 + DB処理特定 (4h)
- [ ] FilterSearchPanel重複実装の詳細分析
- [ ] DB処理の責任分離対象特定 (596行 + 150行)
- [ ] 統合実装のアーキテクチャ設計

#### Task 1.2: SearchFilterService拡張設計 (4h)
- [ ] 既存機能の活用範囲確定
- [ ] DB分離対応の新規メソッド設計
- [ ] 依存関係・インターフェース設計

### **Week 2: 実装・統合** (4日)

#### Task 2.1: SearchFilterService拡張実装 (6h)
- [ ] DB処理メソッドの実装
- [ ] 既存機能との統合テスト
- [ ] エラーハンドリング・ログ実装

#### Task 2.2: FilterSearchPanel統一化実装 (8h)
- [ ] 重複実装の削除・統一
- [ ] 拡張SearchFilterServiceとの連携実装
- [ ] UI専用処理の分離・明確化

#### Task 2.3: 統合テスト・検証 (6h)
- [ ] 単体テスト（SearchFilterService拡張）
- [ ] 統合テスト（FilterSearchPanel統一化）
- [ ] パフォーマンステスト（DB分離効果）

### **Week 3: 最終調整** (2日)

#### Task 3.1: 品質保証・最適化 (4h)
- [ ] 既存機能への影響確認
- [ ] コードレビュー・リファクタリング
- [ ] ドキュメント更新

#### Task 3.2: 統合完了・次フェーズ準備 (2h)
- [ ] Phase 1統合完了確認
- [ ] Phase 2統合準備（AnnotationControlWidget）
- [ ] 進捗レポート作成

## 技術詳細

### **データベース分離対象**

#### 移動対象処理 (746行)
1. **検索条件変換処理**
   - `_process_search_conditions()` → `SearchFilterService.separate_search_and_filter_conditions()`
   - `_process_option_filters()` → `SearchFilterService.create_search_conditions()`

2. **フィルター処理**
   - `_process_resolution_filter()` → `SearchFilterService.process_resolution_filter()`
   - `_process_date_filter()` → `SearchFilterService.process_date_filter()`
   - `_apply_untagged_filter()` → `SearchFilterService.apply_untagged_filter()`
   - `_apply_tagged_filter_logic()` → `SearchFilterService.apply_tagged_filter_logic()`

3. **UI専用処理（残存）**
   - ユーザーインタラクション処理
   - 状態表示・更新処理
   - PySide6依存の処理

### **統合効果**

#### 効率化効果
- **個別実行**: GUI統一化 13.5h + DB分離 4.5h = 18h
- **統合実行**: 12h
- **削減効果**: 6h削減（**33%効率化**）

#### 品質向上効果
- 重複実装削除による保守性向上
- 責任分離による単体テスト容易性向上
- アーキテクチャ一貫性の確保

## 成功指標

### **統合完了指標**
- [ ] FilterSearchPanel重複実装削除: 100%
- [ ] DB処理のSearchFilterService移行: 746行完了
- [ ] 既存機能の動作保証: 100%
- [ ] 単体テストカバレッジ: 90%以上

### **効率化指標**
- [ ] 実装期間: 計画8日以内
- [ ] 開発工数: 12h以内
- [ ] 既存機能への影響: 0件
- [ ] アーキテクチャ準拠: 100%

## リスク管理

### **技術リスク**
- **リスク**: 既存機能への影響
- **対策**: 段階的統合・継続的テスト

### **スケジュールリスク**
- **リスク**: 統合複雑性による遅延
- **対策**: 1日単位の進捗確認・調整

### **品質リスク**
- **リスク**: 責任分離の不完全性
- **対策**: アーキテクチャレビュー・コードレビュー

## 次フェーズ連携

### **Phase 2準備**
- AnnotationControlWidget分離設計
- DatabaseOperationService実装準備
- 統合アプローチの適用検討

### **アーキテクチャ発展**
- クリーンアーキテクチャの継続適用
- サービス層の一貫した設計
- GUI層責任分離の完全化

**Phase 1統合により、GUI統一化とDB分離の両方を効率的に達成し、後続フェーズの基盤を確立**