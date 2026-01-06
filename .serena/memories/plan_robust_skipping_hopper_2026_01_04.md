# Plan: robust-skipping-hopper

**Created**: 2026-01-04
**Source**: manual_sync
**Original File**: robust-skipping-hopper.md
**Status**: planning

---

# GUI編集機能分離とステージングウィジェット設計計画

## 目的
GUIレイアウトの可読性向上のため、編集機能を分離し、検索→選択→ステージング→編集のワークフローを実現する新ウィジェットを設計する。

## Phase 1: 初期理解（完了）

### 現在のGUI構造

**編集機能の現状:**
- **SelectedImageDetailsWidget**: 読み取り専用（View Mode）- 単一画像のメタデータ表示
- **ImageEditPanelWidget**: 編集専用（Edit Mode）- Rating/Score/Tags/Caption編集
- **切り替え**: QStackedWidget で View ↔ Edit モード切り替え（Ctrl+E）
- **編集範囲**: 単一画像のみ（複数選択は未対応）

**既存の複数選択機能:**
- ThumbnailSelectorWidget: Ctrl+Click, Shift+Click で複数選択可能
- DatasetStateManager: 複数選択を管理（`selected_image_ids`）
- **未活用**: 複数選択されても編集は常に単一画像のみ

**最近の変更（2026-01-04）:**
- Phase 2-3: SelectedImageDetailsWidget を読み取り専用化
- Phase 4-5: Favorite Filters 機能追加
- 編集機能が ImageEditPanelWidget に完全分離済み

### 要件の確定

**ユーザー回答に基づく要件:**

1. **バッチ編集機能:**
   - ✅ 1つのタグを複数画像に一括追加（TagDBtools 正規化使用）

2. **Rating/Score の編集:**
   - ✅ 既存の右カラムで継続（変更なし）

3. **課題:**
   - ❌ 右パネルが情報過多で見づらい
   - ❌ 複数画像の編集効率が悪い（1枚ずつしか編集できない）

### 確定した設計方針

**選択: タブ方式（オプション4）**

---

# 最終実装計画

## エグゼクティブサマリー

**目的**: GUIレイアウトの情報過多問題を解決し、シンプルなバッチタグ追加機能を提供

**アプローチ**: 右パネルをQStackedWidgetからQTabWidgetに変更し、バッチタグ追加専用タブを追加

**実装期間**: 3日間（24時間）

**主要機能**:
1. **タブ方式UI**: [画像詳細] と [バッチタグ追加] の2タブ構成
2. **バッチタグ追加**: 1つのタグを複数画像に一括追加（TagDBtools 正規化使用）
3. **Rating/Score編集**: 既存の右カラムで継続（変更なし）

## 新規作成ファイル

### 1. BatchTagAddWidget (UI + Python)
**ファイル**:
- `src/lorairo/gui/designer/BatchTagAddWidget.ui` - Qt Designer UI定義
- `src/lorairo/gui/widgets/batch_tag_add_widget.py` - バッチタグ追加ロジック
- `tests/unit/gui/widgets/test_batch_tag_add_widget.py` - 単体テスト

**機能**:
- ステージングリスト（複数画像を表示、最大500枚）
- 1つのタグ入力フィールド（QLineEdit）
  - TagDBtools の正規化ロジックを使用
  - 入力時のバリデーション
- "選択中の画像を追加"ボタン（DatasetStateManager.selected_image_ids から取得）
- "追加"ボタン（ステージング画像すべてにタグを追加）
- "クリア"ボタン（ステージングリストをクリア）

**シグナル**:
```python
staged_images_changed = Signal(list)  # List[int]
tag_add_requested = Signal(list, str)  # image_ids, tag
staging_cleared = Signal()
```

### 2. Integration Tests
**ファイル**: `tests/integration/gui/test_batch_tag_add_integration.py`

## 既存ファイル変更

### 1. MainWindow.ui（優先度: 高）
**変更内容**: QStackedWidget → QTabWidget
```xml
<!-- BEFORE: stackedWidgetDetail -->
<widget class="QStackedWidget" name="stackedWidgetDetail">
  <widget class="SelectedImageDetailsWidget"/>
  <widget class="ImageEditPanelWidget"/>  <!-- 削除: タブ化により不要 -->
</widget>

<!-- AFTER: tabWidgetRightPanel -->
<widget class="QTabWidget" name="tabWidgetRightPanel">
  <widget class="QWidget" name="tabImageDetails">
    <attribute name="title"><string>画像詳細</string></attribute>
    <layout class="QVBoxLayout">
      <item>
        <widget class="SelectedImageDetailsWidget"/>
      </item>
    </layout>
  </widget>
  <widget class="QWidget" name="tabBatchTagAdd">
    <attribute name="title"><string>バッチタグ追加</string></attribute>
    <layout class="QVBoxLayout">
      <item>
        <widget class="BatchTagAddWidget"/>
      </item>
    </layout>
  </widget>
</widget>
```

**ImageEditPanelWidgetの扱い**:
- MainWindow.uiからは削除（QStackedWidget → QTabWidget 変更により）
- ImageEditPanelWidgetクラス自体は削除せず保持（既存の単一画像編集で使用継続）
- 別の場所で引き続き使用（SelectedImageDetailsWidget と連携）

### 2. ImageDBWriteService（優先度: 高）
**ファイル**: `src/lorairo/gui/services/image_db_write_service.py`

**追加メソッド（1つ）**:
```python
def add_tag_batch(image_ids: list[int], tag: str) -> bool:
    """
    複数画像に1つのタグを追加（既存タグに追加、重複は許可しない）

    Args:
        image_ids: 対象画像のIDリスト
        tag: 追加するタグ（TagDBtools で正規化済み）

    Returns:
        bool: 成功した場合 True
    """
```

**実装詳細**:
- TagDBtools の正規化ロジックを使用（呼び出し元で正規化）
- 既存タグに追加（append mode）
- 重複タグは自動的にスキップ（set操作で重複排除）
- SQLAlchemy session.commit() による全件一括コミット
- エラー時の自動ロールバック
- 包括的なロギング

### 3. ThumbnailSelectorWidget（優先度: 中）
**ファイル**: `src/lorairo/gui/widgets/thumbnail.py`

**追加機能**: ドラッグ選択の状態同期
```python
# 新メソッド
def _sync_selection_to_state() -> None:
    """selectedItems()をDatasetStateManagerに同期"""

# 接続先
scene.selectionChanged.connect(self._sync_selection_to_state)
# または mouseReleaseEvent 内で呼び出し
```

**実装詳細**:
- `selectedItems()` で選択中のThumbnailItemを取得
- 各アイテムから `image_id` を抽出
- `dataset_state.set_selected_images(image_ids)` で状態更新
- バッチタグ追加で選択画像を利用

### 4. MainWindow（優先度: 高）
**ファイル**: `src/lorairo/gui/window/main_window.py`

**追加メソッド**:
```python
# バッチタグ追加ハンドラー
def _handle_batch_tag_add(image_ids: list[int], tag: str) -> None
def _handle_staging_cleared() -> None
```

**シグナル接続** (`_connect_events()`):
```python
# BatchTagAddWidget
self.batchTagAddWidget.tag_add_requested.connect(self._handle_batch_tag_add)
self.batchTagAddWidget.staging_cleared.connect(self._handle_staging_cleared)
```

**実装詳細**:
- `_handle_batch_tag_add()`: ImageDBWriteService.add_tag_batch() を呼び出し
- 成功/失敗のメッセージ表示
- 成功時は DatasetStateManager.refresh_images() で UI 更新

### 5. DatasetStateManager（優先度: 中）
**ファイル**: `src/lorairo/gui/state/dataset_state.py`

**追加メソッド**:
```python
def refresh_image(image_id: int) -> None
    """単一画像のメタデータをDBから再読み込み"""

def refresh_images(image_ids: list[int]) -> None
    """複数画像のメタデータをDBから再読み込み"""
```

## 実装フェーズ（3日間）

### Phase 1: UI Foundation（1日間）
**Day 1**:
- [ ] BatchTagAddWidget.ui作成（Qt Designer）
- [ ] BatchTagAddWidget Python クラス実装（シンプル: ステージングリスト + タグ入力 + ボタン）
- [ ] MainWindow.ui変更（QStackedWidget → QTabWidget）
- [ ] UI生成スクリプト実行: `uv run python scripts/generate_ui.py`

**検証**: スタンドアロンでウィジェット表示確認

### Phase 2: Service Layer & Selection Sync（1日間）
**Day 2**:
- [ ] ImageDBWriteService.add_tag_batch() メソッド追加（1つのみ）
- [ ] ThumbnailSelectorWidget にドラッグ選択同期機能追加
- [ ] DatasetStateManager.refresh_images() メソッド追加

**検証**:
- add_tag_batch() の単体テスト
- ドラッグ選択が DatasetStateManager に反映されることを確認

### Phase 3: Integration & Testing（1日間）
**Day 3**:
- [ ] MainWindow にシグナル接続とハンドラー実装
- [ ] 統合テスト（選択 → ステージング → タグ追加 → 保存）
- [ ] BatchTagAddWidget 単体テスト（目標80%+カバレッジ）
- [ ] カバレッジ検証: `uv run pytest --cov=src --cov-report=xml`
- [ ] Google-style docstrings追加
- [ ] ドキュメント更新（`docs/services.md`）

**目標**: 全体カバレッジ75%+ 維持

## データフロー

### バッチタグ追加フロー
```
1. ThumbnailSelectorWidget（Ctrl+Click または ドラッグで複数選択）
   ↓
2. QGraphicsScene.selectionChanged → ThumbnailSelectorWidget._sync_selection_to_state()
   ↓
3. DatasetStateManager.selected_image_ids 更新
   ↓
4. "選択中の画像を追加"ボタンクリック（BatchTagAddWidget）
   ↓
5. ステージングリストに追加（画像サムネイル表示）
   ↓
6. タグ入力フィールドにタグを入力（例: "landscape"）
   ↓
7. "追加"ボタンクリック
   ↓
8. BatchTagAddWidget.tag_add_requested シグナル（image_ids, tag）
   ↓
9. MainWindow._handle_batch_tag_add(image_ids, tag)
   ↓
10. ImageDBWriteService.add_tag_batch(image_ids, tag)（トランザクション）
   ↓
11. DB更新（全件コミット or ロールバック）
   ↓
12. DatasetStateManager.refresh_images(image_ids)
   ↓
13. UI更新（サムネイル、詳細パネル）
   ↓
14. 完了メッセージ表示 + ステージングリストクリア
```

## リスク評価と対策

### Risk 1: タグ正規化の一貫性
**問題**: TagDBtools の正規化ロジックとの統合が不完全
**対策**:
- TagDBtools の正規化 API を使用
- 入力時のバリデーション
- 正規化後のタグをプレビュー表示

### Risk 2: データベース一貫性
**問題**: バッチ操作の部分的失敗でDB不整合
**対策**:
- SQLAlchemy sessionトランザクション使用
- エラー時の自動ロールバック
- 包括的なロギング

### Risk 3: UI応答性
**問題**: 大規模バッチ操作でUIフリーズ
**対策**:
- ステージング上限500枚
- 当初は同期処理（シンプルな実装）
- 必要に応じてWorkerServiceで非同期化

## テスト戦略

### 単体テスト（Unit Tests）

**BatchTagAddWidget** (`test_batch_tag_add_widget.py`):
- 初期化テスト
- ステージング追加/削除/クリア
- タグ入力バリデーション
- シグナル発行テスト（tag_add_requested, staging_cleared）
- TagDBtools 正規化統合

**ImageDBWriteService.add_tag_batch()** (`test_image_db_write_service.py`):
- 成功ケース（複数画像にタグ追加）
- 重複タグのスキップ
- 無効入力のバリデーション
- トランザクションロールバック

**ThumbnailSelectorWidget** (`test_thumbnail_selector_widget.py`):
- ドラッグ選択同期テスト
- DatasetStateManager への反映確認

### 統合テスト（Integration Tests）

**Batch Tag Add Workflow** (`test_batch_tag_add_integration.py`):
- フルワークフロー: 選択 → ステージング → タグ追加 → 保存
- UI状態同期確認
- エラーハンドリング

### カバレッジ目標
- 全体: 75%+
- BatchTagAddWidget: 80%+
- ImageDBWriteService.add_tag_batch(): 90%+
- MainWindowバッチハンドラー: 80%+

## 成功基準

### 機能要件
- [ ] 1つのタグを複数画像に一括追加
- [ ] ドラッグ選択の DatasetStateManager 同期
- [ ] トランザクション保証（全件成功 or 全件ロールバック）
- [ ] UI即時更新（タグ追加後）

### 技術要件
- [ ] SQLAlchemyトランザクション使用
- [ ] テストカバレッジ75%+ 維持
- [ ] 既存の単一画像編集に影響なし
- [ ] TagDBtools 正規化ロジック統合
- [ ] Google-styleドキュメント
- [ ] 完全な型ヒント

### パフォーマンス要件
- [ ] 100枚へのタグ追加が3秒以内
- [ ] UI応答性維持
- [ ] 500枚ステージングでメモリ50MB未満

### UX要件
- [ ] タブ切り替えがスムーズ
- [ ] タグ追加の視覚的フィードバック
- [ ] ユーザーフレンドリーなエラーメッセージ

## 重要な設計判断

### 1. タブ方式を選択した理由
- 情報過多問題を根本解決
- サムネイル表示領域を最大化
- 実装がシンプル（QTabWidget）
- UX一貫性（既存のView/Edit切替と同様）

### 2. 機能のシンプル化
- バッチ編集は1つのタグ追加のみに限定
- Rating/Score/Caption は既存の右カラムで編集（変更なし）
- 複雑な一括操作（削除・置換・個別編集）は実装しない
- TagDBtools の正規化ロジックを活用

### 3. トランザクション戦略
- SQLAlchemy sessionベースのトランザクション
- 全件コミット or 全件ロールバック（部分的成功なし）
- データ一貫性を最優先

### 4. ステージング上限500枚
- メモリ消費とのバランス
- 実用的な範囲（通常100枚以下）
- シンプルな実装で十分

## 次のステップ

1. このプランをレビュー
2. Phase 1開始: UI Foundation（1日間）
3. 各フェーズ完了後にテスト実施
4. コードレビューしてメインブランチにマージ

---

**計画完了日**: 2026-01-04
**見積もり期間**: 3日間（24時間）
**推定完了日**: 2026-01-07（作業日ベース）

**簡素化された設計**:
- バッチ操作: 1つのタグ追加のみ
- Rating/Score: 既存の右カラムで編集（変更なし）
- クイック編集: 実装しない
- 個別編集: 実装しない