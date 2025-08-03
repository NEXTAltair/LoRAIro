# Phase 3: プレビュー系標準化実装計画（最終版） - 2025/08/03

## 🎯 **Phase 3概要（ImageDBWriteService採用）**

### **最終決定事項**
- **新サービス名**: `ImageDBWriteService`（画像データベース書き込みサービス）
- **命名理由**: DB書き込み動作の明確性・既存クラスとの混同完全回避
- **前提状況**: Phase 2完了（SearchFilterService統一アーキテクチャ確立・78%効率向上達成）
- **実装戦略**: 段階的責任分離（Phase 1-2実証済みパターン継承）

### **アーキテクチャ設計原則**
- **Read/Write分離**: SearchFilterService（読み取り）vs ImageDBWriteService（書き込み）
- **GUI特化**: GUI層でのDB書き込み操作専門サービス
- **既存クラス区別**: database層（ImageDatabaseManager, ImageRepository）と明確に区別

---

## 📋 **詳細実装ロードマップ**

### **Phase 3.1: ImageDBWriteService実装** ⏱️ 1.5時間
**目的**: SelectedImageDetailsWidgetからDB書き込み操作分離

#### **実装仕様**
```python
# src/lorairo/gui/services/image_db_write_service.py
class ImageDBWriteService:
    """画像データベース書き込みサービス（GUI専用）"""
    
    def __init__(self, db_manager: ImageDatabaseManager):
        """SearchFilterServiceと同一パターンのコンストラクタ"""
        self.db_manager = db_manager
    
    # === DB書き込み系機能 ===
    def update_rating(self, image_id: int, rating: str) -> bool:
        """Rating情報をDBに書き込み"""
        
    def update_score(self, image_id: int, score: int) -> bool:
        """Score情報をDBに書き込み"""
        
    # === DB読み取り系機能（詳細情報専用） ===
    def get_image_details(self, image_id: int) -> ImageDetails:
        """単一画像の詳細情報取得（分離対象：_fetch_image_details）"""
        
    def get_annotation_data(self, image_id: int) -> AnnotationData:
        """単一画像のアノテーション情報取得（分離対象：_fetch_annotation_data）"""
```

#### **実装タスク**
- [ ] サービスファイル作成（Phase 1-2パターン適用）
- [ ] SelectedImageDetailsWidgetからDB操作メソッド移行
- [ ] エラーハンドリング・ログ記録（SearchFilterService同等レベル）
- [ ] 型安全性確保（全型アノテーション完備）

---

### **Phase 3.2: SelectedImageDetailsWidget分離** ⏱️ 1.5時間
**目的**: UI専用ウィジェットへの変換・DB操作完全除去

#### **実装仕様**
```python
class SelectedImageDetailsWidget(QWidget, Ui_SelectedImageDetailsWidget):
    """UI専用ウィジェット（DB書き込み操作完全分離）"""
    
    def __init__(self, parent: QWidget | None = None):
        """db_manager依存を除去"""
        super().__init__(parent)
        self.setupUi(self)
        self.image_db_write_service: ImageDBWriteService | None = None
        
    def set_image_db_write_service(self, service: ImageDBWriteService) -> None:
        """Phase 1-2依存注入パターン継承"""
        self.image_db_write_service = service
        
    def load_image_details(self, image_id: int) -> None:
        """ImageDBWriteService経由での情報取得"""
        if self.image_db_write_service:
            details = self.image_db_write_service.get_image_details(image_id)
            self._update_details_display(details)
            
    def _on_save_clicked(self) -> None:
        """保存処理（ImageDBWriteService経由）"""
        if self.image_db_write_service and self.current_image_id:
            # Rating更新
            self.image_db_write_service.update_rating(
                self.current_image_id, self.current_details.rating_value
            )
            # Score更新
            self.image_db_write_service.update_score(
                self.current_image_id, self.current_details.score_value
            )
```

#### **実装タスク**
- [ ] コンストラクタ修正（db_manager依存除去）
- [ ] DB操作完全除去（ImageDBWriteService呼び出し化）
- [ ] 依存注入実装（set_image_db_write_service）
- [ ] 後方互換性確保・段階的移行サポート

---

### **Phase 3.3: ImagePreviewWidget状態統合** ⏱️ 1時間
**目的**: DatasetStateManager統合による状態管理統一

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
        """状態変更時の自動プレビュー更新"""
        if image_data := self.state_manager.get_image_by_id(image_id):
            self.load_image(Path(image_data.file_path))
```

#### **実装タスク**
- [ ] DatasetStateManagerシグナル接続
- [ ] 自動更新機能実装（current_image_changed対応）
- [ ] プレビュー表示最適化
- [ ] メモリ管理改善（画像切り替え時のリソース最適化）

---

### **Phase 3.4: MainWorkspaceWindow統合** ⏱️ 30分
**目的**: ImageDBWriteServiceインスタンス化・サービス注入

#### **実装仕様**
```python
# src/lorairo/gui/window/main_workspace_window.py内
def _setup_image_db_write_service(self) -> None:
    """ImageDBWriteService統合"""
    self.image_db_write_service = ImageDBWriteService(self.db_manager)
    
    # ウィジェットにサービス注入
    self.selected_image_details_widget.set_image_db_write_service(
        self.image_db_write_service
    )
    
def _setup_state_integration(self) -> None:
    """DatasetStateManager統合"""
    self.image_preview_widget.set_dataset_state_manager(self.dataset_state_manager)
```

#### **実装タスク**
- [ ] ImageDBWriteServiceインスタンス化・注入
- [ ] DatasetStateManager接続更新
- [ ] シグナル・スロット再構成
- [ ] 統合動作確認

---

### **Phase 3.5: テスト・検証・品質保証** ⏱️ 1時間
**目的**: ImageDBWriteService品質保証と完了処理

#### **テスト構成**
```python
# tests/unit/gui/services/test_image_db_write_service.py
class TestImageDBWriteService:
    """ImageDBWriteService単体テスト（Phase 1-2パターン継承）"""
    
    def test_constructor_with_db_manager(self):
        """コンストラクタ正常初期化（Phase 1-2パターン）"""
        
    def test_update_rating_success(self):
        """Rating更新機能正常動作"""
        
    def test_update_score_success(self):
        """Score更新機能正常動作"""
        
    def test_get_image_details_success(self):
        """画像詳細取得成功ケース"""
        
    def test_get_annotation_data_success(self):
        """アノテーション取得成功ケース"""
        
    # === エラーハンドリングテスト ===
    def test_update_rating_invalid_image_id(self):
        """不正なimage_id指定時の適切な処理"""
        
    def test_db_connection_error_handling(self):
        """DB接続エラー時の例外処理"""
```

#### **テスト戦略**
- **ImageDBWriteService単体テスト**: 10テスト
- **Widget統合テスト**: 5テスト
- **総計**: 15テスト追加（Phase 1-2: 49 → Phase 3後: 64テスト）

#### **検証基準**
- [ ] 全15テスト成功
- [ ] ruff/mypy全チェック合格
- [ ] 既存機能100%動作保証
- [ ] Windows GUI動作確認

---

## 🎯 **完成アーキテクチャ・サービス層統一**

### **GUI層サービス対称性完成**
```python
# 読み取り特化サービス（Phase 1-2確立済み）
SearchFilterService      # 🔍 検索・フィルター・統計・アノテーション管理
+
# 書き込み特化サービス（Phase 3新規）  
ImageDBWriteService     # ✏️ 書き込み・更新・詳細取得
↓
# データ層（既存継続）
ImageDatabaseManager    # 🔧 DB接続・管理
ImageRepository         # 📁 データアクセス・CRUD
```

### **責任分離の美しい対称性**
| 機能領域 | SearchFilterService | ImageDBWriteService |
|---------|-------------------|-------------------|
| **主要操作** | 🔍 検索・読み取り・統計 | ✏️ 書き込み・更新・詳細 |
| **データフロー** | DB → GUI（読み取り） | GUI → DB（書き込み） |
| **具体例** | `execute_search_with_filters()` | `update_rating()`, `update_score()` |
| **DB操作** | SELECT中心・集計処理 | UPDATE/INSERT中心・個別操作 |
| **スコープ** | 複数画像・データセット全体 | 単一画像・詳細情報 |

### **既存クラスとの明確な区別**
| クラス名 | 場所 | 責任 | 検索時の区別 |
|---------|-----|------|------------|
| `ImageDatabaseManager` | `database/` | DB接続・管理 | Manager = 管理 |
| `ImageRepository` | `database/` | データアクセス | Repository = 保存庫 |
| `SearchFilterService` | `gui/services/` | GUI検索操作 | SearchFilter = 検索 |
| **`ImageDBWriteService`** | `gui/services/` | **GUI書き込み操作** | **DBWrite = 書き込み** |

---

## 📊 **成功指標・期待効果**

### **定量目標**
- ✅ **実装時間**: 5.5時間（目標6時間以内）
- ✅ **テスト成功**: 64/64テスト（49+15）
- ✅ **アーキテクチャ統一**: 95%Pattern適合性
- ✅ **機能互換性**: 100%

### **アーキテクチャ完成効果**
- **GUI層完全統一**: Read/Write責任分離の美しい対称性
- **サービス層完成**: Search + DBWrite による機能分離完成
- **命名の明確性**: 検索時の混同完全回避・直感的理解
- **開発テンプレート確立**: 新規サービス開発の標準パターン

### **Phase 4-5準備効果**
- **最終統合基盤**: Phase 4-5への最適移行準備
- **保守性向上**: Read/Write分離による明確な責任範囲
- **拡張性確保**: 新機能追加時の影響範囲限定化

---

## 🔄 **Phase 1-2-3統合実績**

### **効率化実績継承**
- **Phase 1**: 67%複雑性削減
- **Phase 2**: 78%効率向上（45%+33%追加）
- **Phase 3**: 5.5h実装（目標6h以内）
- **統合効果**: LoRAIro GUI統一化アーキテクチャ完成

### **技術基盤確立**
- **統一アーキテクチャ**: Read/Write分離による完璧な対称性
- **責任分離パターン**: UI層⇔サービス層⇔データ層
- **依存注入パターン**: set_*_service()統一インターフェース
- **テスト戦略**: Phase 1-2-3一貫したテスト体制

---

## 🔄 **Phase 4-5連携準備**

### **確立された基盤**
- **サービス層**: 2サービス完全統一（SearchFilter + ImageDBWrite）
- **UI層**: 全ウィジェット標準化完了
- **状態管理**: DatasetStateManager統合完了
- **テスト体制**: 64テスト品質保証体制

### **次フェーズへの移行準備**
- **アーキテクチャ基盤**: Read/Write分離による完全確立
- **実装パターン**: 実証済み効率的手法確立
- **品質保証**: 統一された検証・テスト手法

**Phase 3完了により、LoRAIro GUI統一化の技術的基盤が完全確立され、最終統合フェーズへの最適な準備が整います。Read/Write分離による美しい対称性により、保守性・拡張性・理解しやすさが大幅に向上します。**

---

**作成日**: 2025/08/03  
**最終更新**: ImageDBWriteService採用・実装計画最終確定  
**実装準備**: Phase 1-2実証済みパターン継承による最小リスク実装