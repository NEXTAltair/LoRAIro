# バッチタグアノテーション タブ UX設計改善

**作成日**: 2026-02-09
**目的**: ステージング画像の可視性向上とアノテーション進捗フィードバック改善
**優先度**: 中 (UX快適性向上)

## 現状の問題点分析

### 1. 視覚的な離散性 - 構造的問題

**現在の配置**:
```
┌────────────────────────────────────────────────────────┐
│ バッチタグタブ (tabBatchTag)                           │
├────────────────┬──────────────────────────────────────┤
│ LEFT (50%)     │ RIGHT (50%)                          │
│                │ ┌────────────────────────────────────┤
│ BatchTagAdd    │ │ tabWidgetBatchTagWorkflow          │
│ Widget         │ │ ├─ tabBatchTagTagAdd               │
│ (ステージング) │ │ │  └─ BatchTagAddWidget (別)       │
│                │ │ └─ tabBatchTagAnnotation           │
│                │ │    └─ groupBoxAnnotation           │
│                │ │       ├─ labelAnnotationTarget     │
│                │ │       ├─ AnnotationFilterWidget    │
│                │ │       ├─ ModelSelectionWidget      │
│                │ │       └─ btnAnnotationExecute      │
│                │ ├─ annotationDisplayPlaceholder     │
│                │ │  (結果表示)                       │
└────────────────┴──────────────────────────────────────┘
```

**問題**:
- ステージング一覧（左）とアノテーション操作（右）が水平に分断
- 同じバッチ操作フローなのに UI が分離されている
- 「どの画像を対象に処理するか」を確認するため、ユーザーが左右を交互に見る必要

### 2. ステージング画像数の可視性欠如

**現在**:
- `labelAnnotationTarget`: "対象: ステージング済み画像" (静的文字列)
- `btnAnnotationExecute`: 常に Enabled
- 0件の場合でも実行可能 → 後続エラー処理に依存

**期待**:
- "◎ ステージング: 25枚 / 500枚" など動的表示
- 0件の場合は btnAnnotationExecute を Disabled に
- ビジュアルフィードバック (アイコン + カウント)

### 3. アノテーション進捗フィードバックの弱さ

**AnnotationWorker の進捗シグナル**:
```python
# base.py の WorkerProgress
progress_updated = Signal(WorkerProgress)
# 内容: progress (0-100), message (str), processed_count (int), total_count (int)
```

**現在の接続**:
- annotationDisplayPlaceholder への接続が不明確
- 実行中: どの画像？どのモデル？ → UI反映なし

**期待**:
- QProgressBar: 全体進捗 (0-100%)
- QLabel: 現在処理中の画像名 / モデル名
- リアルタイム更新（50ms スロットリング）

### 4. ワークフローの非効率性

**タグ追加フロー**:
1. tabBatchTagTagAdd をクリック
2. BatchTagAddWidget でステージング追加＆タグ入力
3. tabBatchTagAnnotation をクリック
4. AnnotationFilterWidget で条件設定
5. ModelSelectionWidget でモデル選択
6. btnAnnotationExecute をクリック

→ タブ切り替え多し、操作対象がタブ依存

## 改善案: 3つのアプローチ

### Option A: 「左カラム拡張」型 (垂直統合)

**構成**:
```
┌────────────────────────────────────┐
│ バッチタグ操作                      │
├────────────────────────────────────┤
│ [ステージング一覧]                  │ (60%)
│ ┌──────────────────────────────────┤
│ │ ThumbnailSelectorWidget (160px H)│
│ └──────────────────────────────────┤
│ [ステージング情報]                  │ (コンパクト)
│ ┌──────────────────────────────────┤
│ │ "◎ ステージング: 25枚"           │
│ │ [クリア] [タグ追加] [実行]        │ (Horizontal)
│ └──────────────────────────────────┤
│ [アノテーション設定]                │ (40%)
│ ┌──────────────────────────────────┤
│ │ AnnotationFilterWidget           │
│ │ ModelSelectionWidget             │
│ │ [アノテーション実行]              │
│ │ [進捗表示]                       │
│ └──────────────────────────────────┘
```

**実装**:
- 水平スプリッター削除
- 垂直レイアウト統一 (VBoxLayout)
- BatchTagAddWidget はコンパクト化（高さ制限）

**メリット**:
- 全ワークフローが1画面で見える
- 視覚的な連続性が確保される
- ステージング↓実行という自然な流れ

**デメリット**:
- 画面が狭い場合、ステージング一覧が圧迫される
- スマートフォン/小さいウィンドウでは使いにくい

**推奨度**: 中 (大画面向け)

---

### Option B: 「右カラム統合」型 (タブ廃止)

**構成**:
```
┌──────────────────┬──────────────────────────────┐
│ LEFT (左ステージ) │ RIGHT (統合操作パネル)       │
│                  │ ┌────────────────────────────┤
│ Staging List     │ │ [タグ追加] [アノテーション] │ (Tab)
│ (50%)            │ │ ────────────────────────────│
│                  │ │ 現在のタブコンテンツ        │
│                  │ │ (BatchTagAddWidget or       │
│                  │ │  groupBoxAnnotation)        │
│                  │ │ ────────────────────────────│
│                  │ │ [進捗表示]                  │
└──────────────────┴──────────────────────────────┘
```

**実装**:
- tabWidgetBatchTagWorkflow は QTabBar のみ (コンテンツなし)
- 実際のコンテンツは右カラム中央に配置
- 全体の統一感が出る

**メリット**:
- 視覚的な一体感
- スペース効率が良い

**デメリット**:
- タブ切り替えロジックが複雑化
- UI Designer 再構築が必要

**推奨度**: 低 (実装コスト > 効果)

---

### Option C: 「ステータス表示 + ボタン状態管理」型 (最小改変) ★推奨★

**構成** (既存 + 改善):
```
groupBoxAnnotation 内:
┌────────────────────────────────────┐
│ ◎ ステージング: 25枚 / 500枚       │ ← 動的表示
│ ────────────────────────────────────│
│ [AnnotationFilterWidget]           │
│ [ModelSelectionWidget]             │
│ ────────────────────────────────────│
│ [アノテーション実行]                │ ← Disabled if count=0
│ ────────────────────────────────────│
│ [進捗表示]                         │ (実行中のみ表示)
│ ┌────────────────────────────────────┤
│ │ ████████░░ 25/100 (処理中:image002)│
│ │ 現在のモデル: GPT-4               │
│ └────────────────────────────────────┘
```

**実装**:
1. `labelAnnotationTarget` を動的に更新
   - BatchTagAddWidget.staged_images_changed(list) に接続
   - "◎ ステージング: {count} / 500" にフォーマット
   
2. `btnAnnotationExecute` の有効/無効制御
   - ステージング数 = 0 → Disabled
   - ステージング数 > 0 → Enabled

3. 進捗表示ウィジェット追加 (groupBoxAnnotation 下部)
   - QProgressBar (0-100%)
   - QLabel (現在処理中の情報)
   - AnnotationWorker.progress_updated に接続

**メリット**:
- 既存 UI 構造を最小限の変更で改善
- BatchTagAddWidget との連携が明確化
- ビジュアルフィードバックで UX 向上
- 実装工数が小さい (1-2時間)

**デメリット**:
- 右カラムの情報密度が上昇
- 垂直スペースが限定的

**推奨度**: 高 ★ (効果/工数のバランス最適)

---

## Option C 詳細設計

### UI モックアップ

```
現在のバッチタグタブ:
┌─ 左カラム ────────┬─ 右カラム ────────────────┐
│ BatchTagAdd       │ tabWidgetBatchTagWorkflow │
│ Widget            │ ┌─ タグ追加               │
│ (ステージング)    │ │ BatchTagAddWidget       │
│                   │ └─ アノテーション設定 ←★│
│ [サムネイル...]   │    groupBoxAnnotation    │
│                   │    ┌──────────────────────│
│                   │    │ ◎ ステージング: 0/500
│                   │    │ (動的更新) ←★改善     │
│                   │    │ ──────────────────────│
│                   │    │ AnnotationFilter...   │
│                   │    │ ModelSelection...     │
│                   │    │ ──────────────────────│
│                   │    │ [実行] (←Disabled)    │
│                   │    │ ──────────────────────│
│                   │    │ 進捗: ████░░ 10/100  │ ←★新規
│                   │    │ 処理中: image_002.png│
│                   │    │ モデル: gpt-4-vision │
│                   │    └──────────────────────│
└───────────────────┴───────────────────────────┘
```

### 必要な変更

#### 1. MainWindow UI (MainWindow.ui 修正)

**labelAnnotationTarget を QLabel から QFrame に変更** (オプション):
- 背景色を設定可能にする (薄い青色で注目度向上)
- またはそのまま QLabel で OK

**新規ウィジェット追加** (groupBoxAnnotation 内):
```xml
<item>
  <widget class="QProgressBar" name="progressAnnotation">
    <property name="value"><number>0</number></property>
    <property name="visible"><bool>false</bool></property>
  </widget>
</item>
<item>
  <widget class="QLabel" name="labelAnnotationProgress">
    <property name="text"><string>準備完了</string></property>
    <property name="visible"><bool>false</bool></property>
  </widget>
</item>
```

#### 2. MainWindow.py (シグナル接続)

```python
# _setup_batch_tag_tab_widgets() 内で追加

# BatchTagAddWidget の staged_images_changed シグナル接続
if hasattr(self, "batchTagAddWidget") and self.batchTagAddWidget:
    self.batchTagAddWidget.staged_images_changed.connect(
        self._on_batch_staging_changed
    )
    logger.info("BatchTagAddWidget.staged_images_changed を接続")

# AnnotationWorker の progress_updated シグナル接続
# (WorkerService 経由)
if hasattr(self, "workerService") and self.workerService:
    self.workerService.progress_updated.connect(
        self._on_annotation_progress_updated
    )
    logger.info("WorkerService.progress_updated を接続")
```

**スロットハンドラー追加**:

```python
@Slot(list)
def _on_batch_staging_changed(self, staged_image_ids: list) -> None:
    """ステージング画像数変更時のハンドラー"""
    count = len(staged_image_ids)
    max_count = 500  # BatchTagAddWidget.MAX_STAGING_IMAGES
    
    # labelAnnotationTarget を動的に更新
    if hasattr(self, "ui") and hasattr(self.ui, "labelAnnotationTarget"):
        self.ui.labelAnnotationTarget.setText(
            f"◎ ステージング: {count} / {max_count} 枚"
        )
    
    # btnAnnotationExecute の有効/無効制御
    if hasattr(self, "ui") and hasattr(self.ui, "btnAnnotationExecute"):
        self.ui.btnAnnotationExecute.setEnabled(count > 0)
    
    logger.debug(f"ステージング画像数: {count} 枚")

@Slot(object)  # WorkerProgress
def _on_annotation_progress_updated(self, progress: Any) -> None:
    """アノテーション進捗更新時のハンドラー"""
    if not hasattr(self, "ui"):
        return
    
    # progress_updated シグナルの内容
    # progress: int (0-100)
    # message: str
    # processed_count: int
    # total_count: int
    
    progress_value = progress.progress if hasattr(progress, "progress") else 0
    message = progress.message if hasattr(progress, "message") else ""
    processed = progress.processed_count if hasattr(progress, "processed_count") else 0
    total = progress.total_count if hasattr(progress, "total_count") else 0
    
    # progressAnnotation を更新
    if hasattr(self.ui, "progressAnnotation"):
        self.ui.progressAnnotation.setValue(progress_value)
        self.ui.progressAnnotation.setVisible(progress_value > 0)
    
    # labelAnnotationProgress を更新
    if hasattr(self.ui, "labelAnnotationProgress"):
        if processed > 0:
            progress_text = f"{message} ({processed}/{total})"
        else:
            progress_text = message
        self.ui.labelAnnotationProgress.setText(progress_text)
        self.ui.labelAnnotationProgress.setVisible(progress_value > 0)
    
    logger.debug(f"進捗: {progress_value}% - {message}")
```

#### 3. AnnotationWorker (既存コード確認)

現在既に以下のシグナルを発行している:
- `progress_updated(WorkerProgress)` ✓
- `WorkerProgress` には progress, message, processed_count, total_count を含む ✓

追加作業不要。

### Signal/Slot接続図

```
BatchTagAddWidget
└─ staged_images_changed(list[int])
   └─ MainWindow._on_batch_staging_changed()
      ├─ labelAnnotationTarget.setText()
      └─ btnAnnotationExecute.setEnabled()

AnnotationWorker
└─ progress_updated(WorkerProgress)
   └─ MainWindow._on_annotation_progress_updated()
      ├─ progressAnnotation.setValue()
      ├─ progressAnnotation.setVisible()
      ├─ labelAnnotationProgress.setText()
      └─ labelAnnotationProgress.setVisible()
```

## 実装優先度

### Phase 1: 基本改善 (1-2時間) - ★推奨開始点★
1. labelAnnotationTarget を動的更新 (シグナル接続)
2. btnAnnotationExecute の有効/無効制御
3. UI ファイルに progressAnnotation + labelAnnotationProgress 追加

### Phase 2: ビジュアル改善 (1時間)
1. progressAnnotation のカスタムスタイル
2. labelAnnotationProgress のフォント調整
3. 背景色調整 (注目度向上)

### Phase 3: 将来の拡張 (検討中)
1. ステージング一覧の圧縮表示 (Option A へのシフト)
2. キャンセルボタンの追加
3. エラーログ表示パネルの追加

## テスト計画

### ユニットテスト
1. `_on_batch_staging_changed()` - 0件/25件/500件の場合
2. `_on_annotation_progress_updated()` - 0%/50%/100% の場合
3. btnAnnotationExecute.isEnabled() の状態確認

### 統合テスト
1. ステージング追加 → labelAnnotationTarget 更新
2. ステージングクリア → btnAnnotationExecute Disabled
3. アノテーション実行 → progressAnnotation 表示

### UX テスト (手動)
1. ステージング 0 件 → ボタン Disabled の確認
2. ステージング追加 → ボタン有効化の確認
3. 実行中 → 進捗表示のリアルタイム更新確認

## 関連ファイル

- **UI 定義**: `/workspaces/LoRAIro/src/lorairo/gui/designer/MainWindow.ui`
- **メインウィンドウ**: `/workspaces/LoRAIro/src/lorairo/gui/window/main_window.py`
- **ステージング管理**: `/workspaces/LoRAIro/src/lorairo/gui/widgets/batch_tag_add_widget.py`
- **ワーカー基底**: `/workspaces/LoRAIro/src/lorairo/gui/workers/base.py`
- **アノテーションワーカー**: `/workspaces/LoRAIro/src/lorairo/gui/workers/annotation_worker.py`

## まとめ

**推奨アプローチ: Option C - ステータス表示 + ボタン状態管理**

- 既存 UI 構造を尊重（大きな再構築なし）
- ステージング画像数の動的表示で可視性向上
- 0件の場合はボタン無効化でエラー回避
- リアルタイム進捗表示で UX 向上
- 実装工数が小さい (1-2時間)

