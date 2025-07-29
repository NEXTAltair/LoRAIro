# ハイブリッドアノテーション UI 包括設計書

**最終更新**: 2025/07/29 09:00:00
**ステータス**: 設計フェーズ
**前身**: `tasks/plans/annotation_ui_unified_plan_20250729.md` + `docs/migration/annotation_ui_optimization_report.md`

## 🎯 設計方針

### 既存ウィジェット活用による機能分担

**設計原則**:

- ✅ **既存ウィジェット最大活用** - 重複実装を避ける､デッドコードは削除してコードの可読性を上げる
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
- 品質スコア表示（Aesthetic、MUSIQ 等）
- 表示モード切替（readonly/editable）
- 履歴表示機能（バージョン選択）

### 1. `AnnotationControlWidget.ui` (新規作成)

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

**目的**: 選択画像の DB 情報詳細表示
**サイズ**: 250x200px (左パネル用コンパクト)
**共通コンポーネント活用**: AnnotationDataDisplayWidget (readonly mode)

**機能** (シンプル版):

- 画像基本情報（ファイル名、サイズ）
- 既存アノテーション表示（共通コンポーネント使用）
  - タグ内容のシンプル表示
  - キャプション内容のシンプル表示
  - 品質スコア値の表示

**TODO: 詳細機能拡張**

- アノテーション履歴・バージョン管理
- 複数表示形式対応（タブ/テーブル選択）
- 詳細メタデータ表示

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
    ├── AnnotationControlWidget (新規追加: 300x400px)
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

#### 右パネル (プレビュー領域に表示する画像は 512x512 のサイズに画像を DB に登録したときに作成するリサイズした画像を使うため 512px 以上)

```xml
<item>
  <widget class="ImagePreviewWidget" name="imagePreview"/>
</item>
<item>
  <widget class="AnnotationControlWidget" name="annotationControl"/>
</item>
<item>
  <widget class="AnnotationResultsWidget" name="annotationResults"/>
</item>
```

## 🔄 データフロー設計

### コントローラー構成

```python
class AnnotationCoordinator:
    """全体調整役 - MainWorkspaceWindow内"""

    def __init__(self):
        self.control_widget = AnnotationControlWidget()
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
# AnnotationControlWidget シグナル
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

**実装順序**: Qt Designer での .ui ファイル作成を最優先し、その後 .py ウィジェット実装

#### ステップ 1.1: `AnnotationDataDisplayWidget` (45 分) **← 共通コンポーネント優先**

**Stage 1.1-A: Qt Designer UI 作成 (25 分)**

- [ ] Qt Designer で `AnnotationDataDisplayWidget.ui` 作成
- [ ] タグ・キャプション・スコア表示エリアのレイアウト設計
- [ ] 表示モード切替 UI コンポーネント配置

**Stage 1.1-B: Python ウィジェット実装 (20 分)**

- [ ] 対応する .py ウィジェット実装
- [ ] 表示モード切替機能実装

#### ステップ 1.2: `AnnotationStatusFilterWidget` (30 分)

**Stage 1.2-A: Qt Designer UI 作成 (20 分)**

- [ ] Qt Designer で `AnnotationStatusFilterWidget.ui` 作成
- [ ] 状態フィルタ UI 設計（チェックボックス・統計表示）

**Stage 1.2-B: Python ウィジェット実装 (10 分)**

- [ ] 対応する .py ウィジェット実装

#### ステップ 1.3: `SelectedImageDetailsWidget` (45 分)

**Stage 1.3-A: Qt Designer UI 作成 (25 分)**

- [ ] Qt Designer で `SelectedImageDetailsWidget.ui` 作成
- [ ] 画像詳細情報表示レイアウト設計
- [ ] 共通コンポーネント `AnnotationDataDisplayWidget` の配置

**Stage 1.3-B: Python ウィジェット実装 (20 分)**

- [ ] DB 情報表示機能実装
- [ ] 共通コンポーネント統合 (readonly mode)

#### ステップ 1.4: `AnnotationControlWidget` (1.5 時間)

**Stage 1.4-A: Qt Designer UI 作成 (1 時間)**

- [ ] Qt Designer で `AnnotationControlWidget.ui` 作成
- [ ] 複数モデル選択 UI 設計（プロバイダー・機能タイプ・モデル選択）
- [ ] 実行制御ボタン配置

**Stage 1.4-B: Python ウィジェット実装 (30 分)**

- [ ] ModelInfoManager 統合
- [ ] 実行制御ロジック実装

#### ステップ 1.5: `AnnotationResultsWidget` (1 時間)

**Stage 1.5-A: Qt Designer UI 作成 (40 分)**

- [ ] Qt Designer で `AnnotationResultsWidget.ui` 作成
- [ ] タブ式結果表示 UI 設計
- [ ] 共通コンポーネント `AnnotationDataDisplayWidget` の配置（editable mode）

**Stage 1.5-B: Python ウィジェット実装 (20 分)**

- [ ] 共通コンポーネント統合
- [ ] エクスポート機能統合

#### ステップ 1.6: `ThumbnailSelectorWidget` 拡張 (30 分)

**Stage 1.6-A: Qt Designer UI 拡張 (20 分)**

- [ ] 既存 `ThumbnailSelectorWidget.ui` にグリッドサイズ可変スライダー追加

**Stage 1.6-B: Python 拡張実装 (10 分)**

- [ ] アノテーション状態オーバーレイ機能実装

### Phase 2: MainWorkspaceWindow 統合 (1 時間)

#### ステップ 2.1: 左パネル拡張

- [ ] AnnotationStatusFilterWidget 追加
- [ ] SelectedImageDetailsWidget 追加

#### ステップ 2.2: 右パネル拡張

- [ ] AnnotationControlWidget 追加
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

- `tasks/plans/annotation_ui_unified_plan_20250729.md` (統合済み)
- `docs/migration/annotation_ui_optimization_report.md` (統合済み)

### 既存参考ファイル

- `src/lorairo/gui/designer/ImageTaggerWidget.ui`
- `src/lorairo/gui/designer/ImagePreviewWidget.ui`
- `src/lorairo/gui/designer/ThumbnailSelectorWidget.ui`
- `src/lorairo/gui/designer/ModelResultTab.ui`

### 実装対象

**新規作成ファイル**:

- `src/lorairo/gui/designer/AnnotationDataDisplayWidget.ui` (新規: 共通コンポーネント)
- `src/lorairo/gui/designer/AnnotationControlWidget.ui` (新規)
- `src/lorairo/gui/designer/AnnotationResultsWidget.ui` (新規)
- `src/lorairo/gui/designer/AnnotationStatusFilterWidget.ui` (新規)
- `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui` (新規)
- `src/lorairo/gui/widgets/annotation_coordinator.py` (新規)

**拡張対象ファイル**:

- `src/lorairo/gui/designer/ThumbnailSelectorWidget.ui` (拡張: グリッドサイズ可変機能)

**削除対象ファイル**:

- `src/lorairo/gui/designer/ImageTaggerWidget.ui` (削除: 269 行 → 機能分割済み)

---

## 🔗 共通コンポーネント活用の利点

### **DRY 原則の実現**

- タグ・キャプション・スコア表示ロジックの一元化
- UI 一貫性の保証
- 保守性向上（1 箇所の修正で全体に反映）

### **最終的なコード分散**

```
ImageTaggerWidget.ui (削除: 269行)
    ↓ 機能分割 & 共通化
├── AnnotationDataDisplayWidget.ui      (共通: ~100行)
├── AnnotationControlWidget.ui    (制御: ~150行)
├── AnnotationResultsWidget.ui          (結果: ~80行) ← 共通コンポーネント活用
├── SelectedImageDetailsWidget.ui       (詳細: ~70行) ← 共通コンポーネント活用
└── AnnotationStatusFilterWidget.ui     (フィルタ: ~50行)

合計: ~450行 (共通化により実質重複なし)
各ウィジェット: 200行以下達成 ✓
```

## 🔧 技術仕様詳細

### DB 連携仕様 - SelectedImageDetailsWidget 表示内容

**対象テーブル**:

```sql
-- 主要データソース
SELECT
    i.id, i.file_path, i.width, i.height, i.created_at,
    t.content as tag_content, t.created_at as tag_date,
    c.content as caption_content, c.created_at as caption_date,
    s.value as score_value, s.score_type, s.created_at as score_date,
    r.rating_value, r.rating_type, r.created_at as rating_date
FROM images i
LEFT JOIN tags t ON i.id = t.image_id
LEFT JOIN captions c ON i.id = c.image_id
LEFT JOIN scores s ON i.id = s.image_id
LEFT JOIN ratings r ON i.id = r.image_id
WHERE i.id = ?
```

**表示項目** (シンプル版):

- **画像メタデータ**: ファイル名、元画像サイズ (width x height)
- **アノテーション情報**:
  - 既存タグ内容 (シンプル表示)
  - 既存キャプション内容 (シンプル表示)
  - 品質スコア値 (Aesthetic, MUSIQ 等)

**TODO: 詳細表示形式検討**

```
今後検討すべき表示オプション:
- [ ] タブ形式 vs ソート可能テーブル形式の選択
- [ ] タグ詳細情報 (作成日時、使用モデル、信頼度等) の表示方法
- [ ] キャプション履歴・バージョン管理表示
- [ ] スコア推移・比較表示機能
- [ ] カラム情報の拡張 (メタデータ、プロバイダー情報等)
- [ ] フィルタリング・検索機能 (タグ内検索等)
- [ ] エクスポート機能 (選択アノテーションの出力)
```

### ModelInfoManager 仕様 - image-annotator-lib 連携

**主要 API 呼び出し**:

```python
from image_annotator_lib import (
    list_available_annotators_with_metadata,
    get_available_models,
    discover_available_vision_models
)

class ModelInfoManager:
    def get_available_annotators(self) -> dict:
        """利用可能なアノテーター一覧とメタデータを取得"""
        return list_available_annotators_with_metadata()

    def get_models_by_provider(self, provider: str) -> list:
        """プロバイダー別モデル一覧を取得"""
        return get_available_models()

    def refresh_model_discovery(self):
        """新しいモデルの発見・更新"""
        return discover_available_vision_models()
```

**UI への情報提供**:

- プロバイダー別モデルリスト (OpenAI/Anthropic/Google/Local)
- 各モデルの機能タイプ (Caption/Tagger/Scorer)
- モデルの利用可能性状態 (API 接続状況)
- get_available_annotators でモデルの情報はすべて渡されるので複数の関数を使う必要はないかも

### エラーハンドリング - AnnotationResultsWidget 表示

**エラー表示方式**:

```python
# 画像ごとのエラー情報表示
class AnnotationResultsWidget:
    def display_model_error(self, image_id: str, model_name: str, error: Exception):
        """モデル別エラー詳細をタブに表示"""
        error_tab = self.create_error_tab(model_name)
        error_tab.show_error_details({
            'error_type': type(error).__name__,
            'error_message': str(error),
            'timestamp': datetime.now(),
            'retry_available': True
        })
```

**エラー種別**:

- **API 接続エラー**: タイムアウト、認証失敗、レート制限
- **モデル実行エラー**: メモリ不足、処理失敗
- **データエラー**: 画像読み込み失敗、形式不正

**TODO: センシティブコンテンツエラーの DB 記録方針**

```
検討事項:
- [ ] 既存ratingsテーブル活用 vs 新規annotation_errorsテーブル作成
- [ ] ratingsテーブル制約 (model_id NOT NULL, normalized_rating必須) とエラー記録の整合性
- [ ] エラー種別の分類・管理方法 (APIレスポンスコード、エラーメッセージ等)
- [ ] UI表示: レーティング情報 vs エラー情報の区別表示
- [ ] 検索・フィルタリング: センシティブ判定画像の効率的な抽出方法

決定事項: 別タスクで詳細設計・実装を行う
現時点では AnnotationResultsWidget でのエラー表示のみ実装
```

### 既存アーキテクチャとの統合

**現在のコントローラー構造**:

```python
# 既存: 単一画面専用コントローラー
src/lorairo/gui/controllers/annotation_controller.py

# 新規: 統合コーディネーター
src/lorairo/gui/widgets/annotation_coordinator.py
```

**役割分担**:

- **AnnotationController**: 個別ウィジェットの動作制御
- **AnnotationCoordinator**: ウィジェット間連携・状態管理
- **MainWorkspaceWindow**: UI コンテナとしての役割のみ

モジュールのプレフィックスに `hybrid_` は要らない気がするなんのハイブリッドかわからない

### 設定管理連携方針

**ConfigurationService 統合**:

```python
class AnnotationCoordinator:
    def __init__(self, config_service: ConfigurationService):
        self.config_service = config_service
        self.setup_model_settings()

    def setup_model_settings(self):
        """設定からモデル情報を取得・UI反映"""
        api_keys = self.config_service.get_api_settings()
        self.model_info_manager.update_api_keys(api_keys)
```

**リアルタイム設定反映**:

- 設定変更時の即座な UI 更新
- ~~API 接続状況の動的表示~~ この機能は不要｡ アノテーターライブラリに必要な引数だけ渡して実行する仕組みなので､結果のエラーだけ判断できれば十分
- ~~モデル選択状態の永続化~~ この機能は不要｡ その都度アノテーションを行いたいモデルのチェックボックスを選択するで十分

**次ステップ**: Phase 1.1 共通コンポーネント `AnnotationDataDisplayWidget` 作成開始
