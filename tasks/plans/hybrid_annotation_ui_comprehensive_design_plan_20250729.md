# ハイブリッドアノテーション UI 包括設計書

**最終更新**: 2025/07/29 09:00:00
**ステータス**: 設計フェーズ
**前身**: `tasks/plans/hybrid_annotation_ui_unified_plan_20250729.md` + `docs/migration/hybrid_annotation_ui_optimization_report.md`

## 🎯 設計方針

### 既存ウィジェット活用による機能分担

**設計原則**:

- ✅ **既存ウィジェット最大活用** - 重複実装を避ける
- ✅ **MainWorkspaceWindow 簡潔化** - コンテナとしての役割に集中
- ✅ **専用ウィジェット作成** - 新機能は独立したウィジェットとして実装
- ✅ **段階的統合** - 個別ウィジェット検証 → 統合の順序

## 📋 既存ウィジェット分析

### 利用可能な既存リソース

#### 1. `ImagePreviewWidget.ui`

**機能**: 画像プレビュー表示
**活用方法**: そのまま右パネルで使用

#### 2. `ThumbnailSelectorWidget.ui`

**機能**: サムネイル一覧表示（シンプル）
**拡張方針**: アノテーション状態オーバーレイ追加｡グリッドサイズの可変スラーイダーの追加

#### 3. `ImageTaggerWidget.ui`

**機能**: 完全なアノテーション機能

- API・モデル選択
- プロンプト入力
- 結果表示（タグ・キャプション・スコア）
- 保存機能

**課題**: 単一 API フォーカス、複数モデル同時実行非対応

## 🏗️ 新規ウィジェット設計

### 共通コンポーネント: `AnnotationDataDisplayWidget.ui` (新規作成)

**目的**: アノテーション結果の汎用表示コンポーネント
**サイズ**: 可変 (用途により調整)

**機能**:
- タグ表示領域（編集可能/読み取り専用）
- キャプション表示領域（編集可能/読み取り専用）
- 品質スコア表示（Aesthetic、MUSIQ等）
- 表示モード切替（readonly/editable）
- 履歴表示機能（バージョン選択）

### 1. `HybridAnnotationControlWidget.ui` (新規作成)

**目的**: 複数モデル選択・実行制御
**サイズ**: 300x400px (コンパクト)

**機能**:

- プロバイダー選択（OpenAI/Anthropic/Google/Local）
- 機能タイプ選択（Caption/Tagger/Scorer）
- 複数モデル選択（チェックリスト）
- 実行・停止・設定ボタン
- 進捗表示

### 2. `AnnotationResultsWidget.ui` (新規作成)

**目的**: モデル別結果表示
**サイズ**: 400x300px (中サイズ)
**共通コンポーネント活用**: AnnotationDataDisplayWidget (editable mode)

**機能**:

- タブ式結果表示（モデル別）
- 共通コンポーネントによるタグ・キャプション・スコア表示
- エクスポート機能
- 結果比較機能
- 結果編集機能

### 3. `SelectedImageDetailsWidget.ui` (新規作成)

**目的**: 選択画像のDB情報詳細表示
**サイズ**: 250x200px (左パネル用コンパクト)
**共通コンポーネント活用**: AnnotationDataDisplayWidget (readonly mode)

**機能**:
- 画像基本情報（ファイル名、サイズ、作成日時）
- 既存アノテーション表示（共通コンポーネント使用）
- アノテーション履歴（実行日時、使用モデル、結果概要）
- 品質スコア履歴
- エラー履歴

### 4. `AnnotationStatusFilterWidget.ui` (新規作成)

**目的**: アノテーション状態フィルタリング
**サイズ**: 250x100px (小サイズ)

**機能**:

- 状態別フィルタ（未処理・処理中・完了・エラー等）
- 状態統計表示
- 一括操作ボタン

## 🔧 MainWorkspaceWindow 統合設計

### 簡潔な統合アプローチ

```python
# MainWorkspaceWindow 3パネル構造（修正最小限）
MainWorkspaceWindow:
├── 左パネル: FilterSearchPanel (250-400px幅)
│   ├── 既存フィルター領域 (動的配置)
│   ├── AnnotationStatusFilterWidget (新規追加: 250x100px)
│   └── SelectedImageDetailsWidget (新規追加: 250x200px)
├── 中央パネル: ThumbnailSelectorWidget (可変幅)
│   └── アノテーション状態オーバーレイ + グリッドサイズ可変 (拡張)
└── 右パネル: PreviewDetailPanel (512px以上)
    ├── ImagePreviewWidget (既存)
    ├── HybridAnnotationControlWidget (新規追加: 300x400px)
    └── AnnotationResultsWidget (新規追加: 400x300px)
```

### ウィジェット配置仕様

#### 左パネル (250-400px 幅)

```xml
<item>
  <!-- 既存 FilterSearchContent -->
</item>
<item>
  <widget class="AnnotationStatusFilterWidget" name="annotationStatusFilter"/>
</item>
<item>
  <widget class="SelectedImageDetailsWidget" name="selectedImageDetails"/>
</item>
```

#### 中央パネル (可変幅)

```python
# ThumbnailSelectorWidgetの拡張
class EnhancedThumbnailSelector(ThumbnailSelectorWidget):
    def create_thumbnail_item(self, image_data):
        item = super().create_thumbnail_item(image_data)
        self.add_annotation_overlay(item, image_data['annotation_status'])
        return item
```

#### 右パネル (512px 以上)

```xml
<item>
  <widget class="ImagePreviewWidget" name="imagePreview"/>
</item>
<item>
  <widget class="HybridAnnotationControlWidget" name="annotationControl"/>
</item>
<item>
  <widget class="AnnotationResultsWidget" name="annotationResults"/>
</item>
```

## 🔄 データフロー設計

### コントローラー構成

```python
class HybridAnnotationCoordinator:
    """全体調整役 - MainWorkspaceWindow内"""

    def __init__(self):
        self.control_widget = HybridAnnotationControlWidget()
        self.results_widget = AnnotationResultsWidget()
        self.status_filter = AnnotationStatusFilterWidget()
        self.image_details_widget = SelectedImageDetailsWidget()
        self.thumbnail_selector = EnhancedThumbnailSelector()

    def connect_signals(self):
        # ウィジェット間連携
        self.control_widget.annotation_started.connect(
            self.results_widget.clear_results
        )
        self.status_filter.filter_changed.connect(
            self.thumbnail_selector.update_filter
        )
        self.thumbnail_selector.imageSelected.connect(
            self.image_details_widget.update_image_details
        )
        self.thumbnail_selector.imageSelected.connect(
            self.results_widget.load_existing_annotations
        )
```

### シグナル・スロット設計

```python
# HybridAnnotationControlWidget シグナル
annotation_started = Signal(list)      # selected_models
annotation_completed = Signal(dict)    # results
progress_updated = Signal(int)         # percentage

# AnnotationResultsWidget シグナル
result_selected = Signal(str)          # model_name
export_requested = Signal(list)       # results

# AnnotationStatusFilterWidget シグナル
filter_changed = Signal(str)           # status_filter
bulk_action_requested = Signal(str)    # action_type

# SelectedImageDetailsWidget シグナル
image_details_loaded = Signal(dict)    # image_info
annotation_history_clicked = Signal(int)  # annotation_id

# AnnotationDataDisplayWidget シグナル
data_edited = Signal(dict)             # edited_data
export_requested = Signal(str)         # export_format
```

## 📅 実装ロードマップ

### Phase 1: 個別ウィジェット作成 (3-4 時間)

#### ステップ 1.1: `AnnotationDataDisplayWidget` (45 分) **← 共通コンポーネント優先**

- [ ] Qt Designer で共通表示コンポーネント作成
- [ ] タグ・キャプション・スコア表示UI設計
- [ ] 表示モード切替機能実装
- [ ] 対応する .py ウィジェット実装

#### ステップ 1.2: `AnnotationStatusFilterWidget` (30 分)

- [ ] Qt Designer で新規 .ui ファイル作成
- [ ] 状態フィルタ UI 設計
- [ ] 対応する .py ウィジェット実装

#### ステップ 1.3: `SelectedImageDetailsWidget` (45 分)

- [ ] Qt Designer で詳細表示ウィジェット作成
- [ ] 共通コンポーネント統合 (readonly mode)
- [ ] DB情報表示機能実装

#### ステップ 1.4: `HybridAnnotationControlWidget` (1.5 時間)

- [ ] 複数モデル選択 UI 設計
- [ ] ModelInfoManager 統合
- [ ] 実行制御ボタン実装

#### ステップ 1.5: `AnnotationResultsWidget` (1 時間)

- [ ] タブ式結果表示 UI 設計
- [ ] 共通コンポーネント統合 (editable mode)
- [ ] エクスポート機能統合

#### ステップ 1.6: `ThumbnailSelectorWidget` 拡張 (30 分)

- [ ] グリッドサイズ可変スライダー追加
- [ ] アノテーション状態オーバーレイ機能

### Phase 2: MainWorkspaceWindow 統合 (1 時間)

#### ステップ 2.1: 左パネル拡張

- [ ] AnnotationStatusFilterWidget 追加
- [ ] SelectedImageDetailsWidget 追加

#### ステップ 2.2: 右パネル拡張

- [ ] HybridAnnotationControlWidget 追加
- [ ] AnnotationResultsWidget 追加

#### ステップ 2.3: 中央パネル拡張

- [ ] 拡張版 ThumbnailSelectorWidget 統合

### Phase 3: 統合テスト (1 時間)

#### ステップ 3.1: 個別ウィジェットテスト

- [ ] 各ウィジェット単体テスト

#### ステップ 3.2: 統合テスト

- [ ] ウィジェット間連携テスト
- [ ] UI 統合テスト

## 🎯 成功基準

### 技術目標

- ✅ **MainWorkspaceWindow.ui**: 200 行以下維持（現在 1068 行 →200 行以下）
- ✅ **個別ウィジェット**: 各 300 行以下
- ✅ **機能分担明確化**: 重複コード 0%
- ✅ **拡張性**: 新機能追加時の影響範囲限定

### ユーザビリティ目標

- ✅ **学習コスト**: 既存 ImageTaggerWidget ユーザーの即座理解
- ✅ **操作効率**: 複数モデル同時実行による 50%時短
- ✅ **視認性**: 状態オーバーレイによる進捗把握

## 🔗 関連ファイル

### 設計ドキュメント

- `tasks/plans/hybrid_annotation_ui_unified_plan_20250729.md` (統合済み)
- `docs/migration/hybrid_annotation_ui_optimization_report.md` (統合済み)

### 既存参考ファイル

- `src/lorairo/gui/designer/ImageTaggerWidget.ui`
- `src/lorairo/gui/designer/ImagePreviewWidget.ui`
- `src/lorairo/gui/designer/ThumbnailSelectorWidget.ui`
- `src/lorairo/gui/designer/ModelResultTab.ui`

### 実装対象

**新規作成ファイル**:
- `src/lorairo/gui/designer/AnnotationDataDisplayWidget.ui` (新規: 共通コンポーネント)
- `src/lorairo/gui/designer/HybridAnnotationControlWidget.ui` (新規)
- `src/lorairo/gui/designer/AnnotationResultsWidget.ui` (新規)
- `src/lorairo/gui/designer/AnnotationStatusFilterWidget.ui` (新規)
- `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui` (新規)
- `src/lorairo/gui/widgets/hybrid_annotation_coordinator.py` (新規)

**拡張対象ファイル**:
- `src/lorairo/gui/designer/ThumbnailSelectorWidget.ui` (拡張: グリッドサイズ可変機能)

**削除対象ファイル**:
- `src/lorairo/gui/designer/ImageTaggerWidget.ui` (削除: 269行 → 機能分割済み)

---

## 🔗 共通コンポーネント活用の利点

### **DRY原則の実現**
- タグ・キャプション・スコア表示ロジックの一元化
- UI一貫性の保証
- 保守性向上（1箇所の修正で全体に反映）

### **最終的なコード分散**
```
ImageTaggerWidget.ui (削除: 269行)
    ↓ 機能分割 & 共通化
├── AnnotationDataDisplayWidget.ui      (共通: ~100行)
├── HybridAnnotationControlWidget.ui    (制御: ~150行)
├── AnnotationResultsWidget.ui          (結果: ~80行) ← 共通コンポーネント活用
├── SelectedImageDetailsWidget.ui       (詳細: ~70行) ← 共通コンポーネント活用
└── AnnotationStatusFilterWidget.ui     (フィルタ: ~50行)

合計: ~450行 (共通化により実質重複なし)
各ウィジェット: 200行以下達成 ✓
```

**次ステップ**: Phase 1.1 共通コンポーネント `AnnotationDataDisplayWidget` 作成開始
