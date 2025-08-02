# Phase 2: アノテーション系分離 + データベース操作統合計画

## 統合概要

GUI統一化のAnnotationControlWidget責任分離とデータベースアクセス分離（アノテーション系）を**連携実行**することで、**31%の効率化**を実現する統合実装計画。

## 対象範囲

### AnnotationControlWidget責任分離（GUI統一化）
- `src/lorairo/gui/widgets/annotation_control_widget.py`
- UI/Logic/State/Data層の明確な分離
- ModelManager service extraction

### データベース操作分離（DB分離）
- アノテーション状態のDB集計処理 (100行)
- DatabaseOperationService新規作成
- データ操作専用サービス層の確立

## 統合実装戦略

### **連携アプローチ**
AnnotationControlWidget責任分離の設計時にDatabaseOperationService連携を組み込み、アノテーション状態管理の責任分離を統合実施。

### **技術統合ポイント**

#### DatabaseOperationService新規実装
```python
# src/lorairo/services/database_operation_service.py
class DatabaseOperationService:
    """データベース操作専用サービス（アノテーション系統合）"""
    
    def __init__(self, db_manager: ImageDatabaseManager):
        self.db_manager = db_manager
        self.logger = logger
    
    # アノテーション系データ操作（DB分離対応）
    def get_annotation_status_counts(self) -> dict:
        """アノテーション状態の集計（データ集計処理）"""
        try:
            # annotation_status_filter_widget.pyから移行
            return self.db_manager.get_annotation_status_summary()
        except Exception as e:
            self.logger.error(f"アノテーション状態集計エラー: {e}")
            return {}
    
    def update_annotation_status(self, image_id: int, status: str) -> None:
        """アノテーション状態の更新（データ更新処理）"""
        try:
            # 重い書き込み操作の責任を担当
            self.db_manager.update_image_annotation_status(image_id, status)
        except Exception as e:
            self.logger.error(f"アノテーション状態更新エラー: {e}")
    
    def process_annotation_batch_operations(self, operations: list[dict]) -> BatchResult:
        """バッチアノテーション処理（重い処理、進捗報告対応）"""
        # AnnotationControlWidget分離で発生するバッチ処理を担当
```

#### AnnotationService拡張（責任分離対応）
```python
# src/lorairo/services/annotation_service.py
class AnnotationService:
    """アノテーション管理サービス（責任分離統合版）"""
    
    def __init__(self, db_operation_service: DatabaseOperationService):
        self.db_operation_service = db_operation_service
        self.model_manager = ModelManager()  # 分離されたModelManager
    
    # AnnotationControlWidget分離で抽出されるビジネスロジック
    def manage_annotation_workflow(self, image_ids: list[int]) -> WorkflowResult:
        """アノテーションワークフロー管理（UI層から分離）"""
        
    def coordinate_model_operations(self, model_configs: dict) -> ModelResult:
        """モデル操作の調整（ModelManager連携）"""
        
    def handle_annotation_state_changes(self, changes: list[dict]) -> None:
        """アノテーション状態変更処理（DB操作連携）"""
        # DatabaseOperationServiceと連携
        for change in changes:
            self.db_operation_service.update_annotation_status(
                change['image_id'], change['status']
            )
```

#### 分離後AnnotationControlWidget
```python
# src/lorairo/gui/widgets/annotation_control_widget.py
class AnnotationControlWidget(QWidget):
    """責任分離後のAnnotationControlWidget（UI専用）"""
    
    def __init__(self, parent=None, dataset_state: DatasetStateManager | None = None):
        self.dataset_state = dataset_state
        self.annotation_service: AnnotationService | None = None
        self.database_operation_service: DatabaseOperationService | None = None
    
    def set_services(self, annotation_service: AnnotationService, 
                    db_operation_service: DatabaseOperationService):
        """統合サービス層の注入"""
        self.annotation_service = annotation_service
        self.database_operation_service = db_operation_service
    
    # UI専用処理（残存）
    def update_ui_controls(self) -> None:
        """UI制御のみ"""
    
    def handle_user_interactions(self) -> None:
        """ユーザーインタラクション処理のみ"""
    
    # ビジネスロジック委譲
    def process_annotation_request(self, request: AnnotationRequest) -> None:
        """アノテーション処理要求（サービス層に委譲）"""
        if self.annotation_service:
            result = self.annotation_service.manage_annotation_workflow(request.image_ids)
            self.update_ui_from_result(result)
```

## 実装タスク（統合版）

### **Week 1: 設計・準備** (2日)

#### Task 1.1: AnnotationControlWidget責任分析 + DB操作特定 (4h)
- [ ] AnnotationControlWidget内の責任分析（UI/Logic/State/Data）
- [ ] アノテーション系DB操作の特定・分離対象確認 (100行)
- [ ] DatabaseOperationService設計（アノテーション系機能込み）

#### Task 1.2: 統合サービス設計 (4h)
- [ ] AnnotationService拡張設計（責任分離対応）
- [ ] DatabaseOperationService詳細設計
- [ ] ModelManager service抽出設計

### **Week 2: 実装・統合** (3日)

#### Task 2.1: DatabaseOperationService実装 (6h)
- [ ] アノテーション系データ操作メソッド実装
- [ ] バッチ処理・進捗報告機能実装
- [ ] エラーハンドリング・ログ実装

#### Task 2.2: AnnotationService拡張実装 (6h)
- [ ] AnnotationControlWidgetから抽出したビジネスロジック実装
- [ ] DatabaseOperationService連携実装
- [ ] ModelManager連携実装

#### Task 2.3: AnnotationControlWidget分離実装 (4h)
- [ ] UI専用処理への簡素化
- [ ] サービス層との連携実装
- [ ] DatasetStateManager連携維持

### **Week 3: テスト・検証** (1-2日)

#### Task 3.1: 統合テスト・検証 (4h)
- [ ] DatabaseOperationService単体テスト
- [ ] AnnotationService統合テスト
- [ ] AnnotationControlWidget UI/サービス連携テスト

#### Task 3.2: パフォーマンス・品質確認 (2-3h)
- [ ] アノテーション処理パフォーマンステスト
- [ ] 既存機能への影響確認
- [ ] アーキテクチャ準拠確認

## 技術詳細

### **責任分離対象**

#### AnnotationControlWidget分離内容
1. **UI層（残存）**
   - ユーザーインタラクション処理
   - 状態表示・UI更新
   - PySide6依存処理

2. **Logic層（AnnotationServiceに移行）**
   - アノテーションワークフロー管理
   - モデル選択・設定ロジック
   - 処理結果の調整・変換

3. **State層（DatasetStateManager活用）**
   - アノテーション状態管理
   - 選択状態管理

4. **Data層（DatabaseOperationServiceに移行）**
   - アノテーション状態のDB集計
   - アノテーション状態の更新
   - バッチアノテーション処理

### **ModelManager Service抽出**
```python
# src/lorairo/services/model_manager.py
class ModelManager:
    """モデル管理専用サービス"""
    
    def get_available_annotation_models(self) -> list[dict]:
        """利用可能なアノテーションモデル取得"""
    
    def configure_model_settings(self, model_type: str, settings: dict) -> None:
        """モデル設定の管理"""
    
    def validate_model_compatibility(self, model_type: str) -> bool:
        """モデル互換性確認"""
```

### **統合効果**

#### 効率化効果
- **個別実行**: GUI分離 14h + DB分離 2h = 16h
- **統合実行**: 11h
- **削減効果**: 5h削減（**31%効率化**）

#### アーキテクチャ向上効果
- 責任分離による単体テスト容易性向上
- データ操作の統一的な管理
- ビジネスロジックの再利用性向上

## 成功指標

### **統合完了指標**
- [ ] AnnotationControlWidget責任分離: UI/Logic/State/Data完全分離
- [ ] DatabaseOperationService実装: アノテーション系データ操作100%移行
- [ ] ModelManager抽出: モデル管理責任の独立化
- [ ] 既存機能の動作保証: 100%

### **効率化指標**
- [ ] 実装期間: 計画6-8日以内
- [ ] 開発工数: 11h以内
- [ ] アノテーション処理性能: 既存レベル維持
- [ ] 単体テストカバレッジ: 85%以上

## リスク管理

### **技術リスク**
- **リスク**: AnnotationControlWidget機能の複雑性
- **対策**: 段階的分離・継続的テスト

### **統合リスク**
- **リスク**: DatabaseOperationService設計の過大化
- **対策**: 責任範囲の明確化・インターフェース単純化

### **品質リスク**
- **リスク**: アノテーション処理の性能劣化
- **対策**: パフォーマンステスト・最適化

## Phase 3連携準備

### **プレビュー系標準化準備**
- DatabaseOperationService基盤の活用
- 統一されたサービス層設計の適用
- 責任分離パターンの継承

### **アーキテクチャ発展**
- サービス層の完全な確立
- GUI層のUI専用化完成
- データ操作の統一的管理体制

**Phase 2統合により、アノテーション系の責任分離とデータベース操作統一を効率的に達成し、Phase 3の基盤を確立**