# Phase 3: プレビュー系標準化実装計画（更新版） - 2025/08/03

## 🎯 **Phase 3概要**
**フェーズ2完了後の状況を踏まえた更新計画**

### **前提状況**
- **Phase 2完了**: SearchFilterService統一アーキテクチャ確立・78%効率向上達成
- **継承パターン**: 既にQWidget + Ui_*で統一済み ✅
- **実装対象**: SelectedImageDetailsWidgetのDB操作分離 + DatasetStateManager統合

### **実装戦略**
- **推奨アプローチ**: 段階的責任分離（Phase 1-2実証済みパターン継承）
- **総実装時間**: 5.5時間（目標6時間以内）
- **アーキテクチャ継承**: SearchFilterService統一パターン完全適用

---

## 📋 **詳細実装ロードマップ**

### **Phase 3.1: ImageDetailsService実装** ⏱️ 1.5時間
**目的**: DB操作分離サービス層実装

#### **実装仕様**
```python
# src/lorairo/gui/services/image_details_service.py
class ImageDetailsService:
    """Phase 1-2パターン継承のサービス層"""
    
    def __init__(self, db_manager: ImageDatabaseManager):
        """SearchFilterServiceと同一パターン"""
        self.db_manager = db_manager
    
    def get_image_details(self, image_id: int) -> ImageDetails:
        """_fetch_image_details移行"""
        
    def get_annotation_data(self, image_id: int) -> AnnotationData:
        """_fetch_annotation_data移行"""
        
    def update_rating(self, image_id: int, rating: str) -> bool:
        """Rating更新機能"""
        
    def update_score(self, image_id: int, score: int) -> bool:
        """Score更新機能"""
```

#### **実装タスク**
- [ ] サービスファイル作成（Phase 1-2パターン適用）
- [ ] DB操作メソッド移行（_fetch_*メソッド）
- [ ] エラーハンドリング・ログ記録
- [ ] 型安全性確保（全型アノテーション）

---

### **Phase 3.2: SelectedImageDetailsWidget分離** ⏱️ 1.5時間
**目的**: UI専用ウィジェットへの変換

#### **実装仕様**
```python
class SelectedImageDetailsWidget(QWidget, Ui_SelectedImageDetailsWidget):
    """UI専用・DB操作完全分離"""
    
    def __init__(self, parent: QWidget | None = None):
        """db_manager依存除去"""
        
    def set_image_details_service(self, service: ImageDetailsService) -> None:
        """Phase 1-2依存注入パターン継承"""
        self.image_details_service = service
        
    def load_image_details(self, image_id: int) -> None:
        """サービス経由情報取得"""
        if self.image_details_service:
            details = self.image_details_service.get_image_details(image_id)
            self._update_details_display(details)
```

#### **実装タスク**
- [ ] コンストラクタ修正（db_manager除去）
- [ ] DB操作完全除去（サービス呼び出し化）
- [ ] 依存注入実装（set_image_details_service）
- [ ] 後方互換性確保

---

### **Phase 3.3: ImagePreviewWidget状態統合** ⏱️ 1時間
**目的**: DatasetStateManager統合

#### **実装仕様**
```python
class ImagePreviewWidget(QWidget, Ui_ImagePreviewWidget):
    """DatasetStateManager統合対応"""
    
    def set_dataset_state_manager(self, state_manager: DatasetStateManager) -> None:
        """状態管理統合"""
        self.state_manager = state_manager
        self.state_manager.current_image_changed.connect(self._on_current_image_changed)
        
    @Slot(int)
    def _on_current_image_changed(self, image_id: int) -> None:
        """自動プレビュー更新"""
        if image_data := self.state_manager.get_image_by_id(image_id):
            self.load_image(Path(image_data.file_path))
```

#### **実装タスク**
- [ ] DatasetStateManagerシグナル接続
- [ ] 自動更新機能実装
- [ ] プレビュー最適化
- [ ] メモリ管理改善

---

### **Phase 3.4: MainWorkspaceWindow統合** ⏱️ 30分
**目的**: サービス注入・統合

#### **実装タスク**
- [ ] ImageDetailsServiceインスタンス化・注入
- [ ] DatasetStateManager接続更新
- [ ] シグナル・スロット再構成
- [ ] 統合動作確認

---

### **Phase 3.5: テスト・検証** ⏱️ 1時間
**目的**: 品質保証・完了処理

#### **テスト構成**
- **ImageDetailsService単体テスト**: 10テスト
- **Widget統合テスト**: 5テスト
- **総計**: 15テスト追加（Phase 1-2: 49 → Phase 3後: 64テスト）

#### **検証基準**
- [ ] 全15テスト成功
- [ ] ruff/mypy全チェック合格
- [ ] 既存機能100%動作保証
- [ ] Windows GUI動作確認

---

## 🎯 **成功指標・期待効果**

### **定量目標**
- ✅ **実装時間**: 5.5時間（目標6時間以内）
- ✅ **テスト成功**: 64/64テスト（49+15）
- ✅ **アーキテクチャ統一**: 95%Pattern適合性
- ✅ **機能互換性**: 100%

### **アーキテクチャ完成効果**
- **GUI層完全統一**: 全ウィジェット統一アーキテクチャ適用
- **サービス層完成**: SearchFilterService + ImageDetailsService
- **状態管理統一**: DatasetStateManager中心統合
- **開発テンプレート確立**: 新規ウィジェット開発標準

### **Phase 4-5準備効果**
- **最終統合基盤**: Phase 4-5への最適移行準備
- **保守性向上**: 一貫構造による容易な保守・拡張
- **品質標準化**: 統一テスト・検証パターン

---

## 📊 **Phase 1-2-3統合実績**

### **効率化実績継承**
- **Phase 1**: 67%複雑性削減
- **Phase 2**: 78%効率向上（45%+33%追加）
- **Phase 3**: 5.5h実装（目標6h以内）
- **統合効果**: LoRAIro GUI統一化アーキテクチャ完成

### **技術基盤確立**
- **統一アーキテクチャ**: SearchFilterService設計パターン
- **責任分離パターン**: UI層⇔サービス層⇔データ層
- **依存注入パターン**: set_*_service()統一インターフェース
- **テスト戦略**: Phase 1-2-3一貫したテスト体制

---

## 🔄 **Phase 4-5連携準備**

### **確立された基盤**
- **サービス層**: 2サービス統一（SearchFilter + ImageDetails）
- **UI層**: 全ウィジェット標準化完了
- **状態管理**: DatasetStateManager統合完了
- **テスト体制**: 64テスト品質保証体制

### **次フェーズへの移行準備**
- **アーキテクチャ基盤**: 完全確立済み
- **実装パターン**: 実証済み効率的手法確立
- **品質保証**: 統一された検証・テスト手法

**Phase 3完了により、LoRAIro GUI統一化の技術的基盤が完全確立され、最終統合フェーズへの最適な準備が整います。**

---

**作成日**: 2025/08/03  
**更新内容**: フェーズ2完了状況反映・実装戦略最適化  
**実装準備**: Phase 1-2実証済みパターン継承による最小リスク実装