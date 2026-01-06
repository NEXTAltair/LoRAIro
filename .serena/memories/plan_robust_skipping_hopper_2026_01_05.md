# Plan: robust-skipping-hopper

**Created**: 2026-01-05 01:29:29
**Source**: plan_mode
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

1. **バッチ編集機能（全機能必要）:**
   - ✅ 複数画像に同じタグ/キャプションを一括適用
   - ✅ 複数画像を個別に順次編集
   - ✅ 複数画像の既存タグ/キャプションを一括削除・置換

2. **Rating/Score の即時編集:**
   - ✅ サムネイル上で直接編集可能に（右クリックメニュー）
   - ImageEditPanelWidgetはQStackedWidgetから削除し、個別編集モードで再利用

3. **課題:**
   - ❌ 右パネルが情報過多で見づらい
   - ❌ 複数画像の編集効率が悪い（1枚ずつしか編集できない）

4. **UI配置の検討:**
   - オプション2: 新しい独立したパネル（下部や左側）
   - オプション3: ダイアログウィンドウ（別ウィンドウ）
   - ユーザーは推奨を求めている

### UI配置の推奨案

**推奨: オプション2（新しい独立したパネル）**

**理由:**
- ✅ MainWindow内で完結、ワークフローが統一される
- ✅ ドッキング可能なパネルにすれば、ユーザーがカスタマイズ可能
- ✅ 既存のMainWindow構造（Splitter）に追加しやすい
- ✅ ステージングエリアと検索結果を同時に見ることができる
- ✅ 右パネルの情報過多問題を解決（編集機能を分離）

**オプション3（ダイアログ）の欠点:**
- ❌ 別ウィンドウなので、検索結果とステージングエリアを同時に見られない
- ❌ ウィンドウ管理が煩雑になる
- ❌ モーダルダイアログだと他の操作ができなくなる
- ❌ 非モーダルでも画面が分散して使いづらい可能性

**具体的な配置案:**
```
┌─────────────────────────────────────────────────────────┐
│ MainWindow                                              │
├─────────────────────────────────────────────────────────┤
│ [Search/Filter Panel (左)]  │ [Thumbnail Grid (中央)]  │
│                              │                          │
│                              │ [ステージングパネル (下部)]│
├──────────────────────────────┼──────────────────────────┤
│ [Selected Details (右パネル)] - 読み取り専用のみ         │
└─────────────────────────────────────────────────────────┘
```

**詳細:**
- 中央パネルをVertical Splitterで分割
- 上部: ThumbnailSelectorWidget（サムネイル一覧）
- 下部: 新しいBatchEditStagingWidget（ステージングエリア + バッチ編集）
- 右パネル: SelectedImageDetailsWidget（単一画像の詳細表示のみ）
- Rating/Score: サムネイル右クリックメニューで即時編集

### オプション4: タブ方式の提案（ユーザー提案）

**レイアウト案:**
```
┌────────────────────────────────────────────────────────┐
│ MainWindow                                             │
├────────────────────────────────────────────────────────┤
│ [Search Panel] │ [Thumbnail Grid (中央・全画面)]     │
├────────────────┼────────────────────────────────────────┤
│                │ [右パネル - QTabWidget]               │
│                │ ┌────────────────────────────────────┐ │
│                │ │ [詳細] [バッチ編集]               │ │
│                │ ├────────────────────────────────────┤ │
│                │ │ Tab 1: 画像詳細 (Selected Details)│ │
│                │ │ Tab 2: バッチ編集 (Batch Staging) │ │
│                │ └────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

**詳細:**
- 右パネルを QTabWidget に変更
- Tab 1: SelectedImageDetailsWidget（現行の詳細表示）
- Tab 2: BatchEditStagingWidget（新規作成）
- サムネイルグリッドは中央全体を使用（縦分割なし）
- Rating/Score: サムネイル右クリックメニューで即時編集

### UI配置の比較分析

| 観点 | オプション2（パネル分割） | オプション4（タブ方式） |
|------|-------------------------|------------------------|
| **情報の同時表示** | ✅ サムネイル+ステージング同時表示 | ❌ タブ切り替え必要 |
| **画面のすっきり感** | △ パネルが多い | ✅ すっきり、見やすい |
| **情報過多問題** | △ 軽減（分散） | ✅ 完全解決（タブで分離） |
| **実装の複雑さ** | 中程度（Splitter追加） | 低い（QTabWidget） |
| **ワークフロー** | 上→下への視覚的な流れ | タブ切り替えで機能切り替え |
| **スペース効率** | △ 画面分割で各エリア縮小 | ✅ 効率的（全スペース活用） |
| **サムネイル表示領域** | △ 縦分割で表示領域減少 | ✅ 広い表示領域 |
| **UX一貫性** | 新しいパターン | ✅ 既存のView/Edit切替と同様 |
| **学習曲線** | 新しいレイアウトに慣れる必要 | ✅ タブは直感的 |

### 推奨の再評価

**ユーザーの課題:**
- "右パネルが情報過多" → タブ方式が最も効果的に解決

**推奨: オプション4（タブ方式）**

**理由の更新:**
1. **情報過多の根本解決**: タブで機能を明確に分離、必要な情報だけ表示
2. **サムネイル表示領域の最大化**: 縦分割しないため、サムネイルを広く表示できる
3. **実装がシンプル**: QTabWidget追加のみ、既存のQStackedWidgetパターンに近い
4. **UX一貫性**: 既存の View/Edit 切り替えパターンと同じ感覚で使える
5. **画面がすっきり**: 同時に1つの機能に集中できる

**パネル分割の欠点（再評価）:**
- サムネイル表示領域が縮小する（縦分割により）
- 画面が複雑になり、情報過多問題が完全には解決しない
- 小さい画面では見づらくなる可能性

**タブ方式のデメリット:**
- サムネイルとステージングエリアを同時に見られない
  - **対策**: ステージングエリア内に小さいサムネイルプレビューを表示
  - **対策**: ドラッグ&ドロップでサムネイルからステージングエリアへ追加

### 確定した設計方針

**選択: タブ方式（オプション4）**

## Phase 2: 詳細設計（完了）

Plan agentによる設計が完了しました。

## Phase 3: 設計レビュー（完了）

以下のファイルを確認し、設計の妥当性を検証しました:
- `/home/vscode/.claude/plans/robust-skipping-hopper-agent-a31061a.md` - 包括的な実装計画
- `src/lorairo/gui/services/image_db_write_service.py` - 既存のサービス構造
- `src/lorairo/gui/widgets/thumbnail.py` - サムネイルウィジェット
- `src/lorairo/gui/designer/MainWindow.ui` - 現在のQStackedWidget構造

ユーザーの要件と設計が一致していることを確認しました。

---

# 最終実装計画

## エグゼクティブサマリー

**目的**: GUIレイアウトの情報過多問題を解決し、シンプルなバッチタグ追加機能を提供

**アプローチ**: 右パネルをQStackedWidgetからQTabWidgetに変更し、バッチタグ追加専用タブを追加

**実装期間**: 3日間（24時間）

**主要機能**:
1. **タブ方式UI**: [画像詳細] [Rating/Score編集] [バッチタグ追加] の3タブ構成
2. **Rating/Score編集分離**: SelectedImageDetailsWidget から分離し、独立タブに配置
3. **バッチタグ追加**: 1つのタグを複数画像に一括追加（TagDBtools 正規化使用）

## 新規作成ファイル

### 1. RatingScoreEditWidget (UI + Python)
**ファイル**:
- `src/lorairo/gui/designer/RatingScoreEditWidget.ui` - Qt Designer UI定義
- `src/lorairo/gui/widgets/rating_score_edit_widget.py` - Rating/Score 編集ロジック
- `tests/unit/gui/widgets/test_rating_score_edit_widget.py` - 単体テスト

**機能**:
- Rating 選択（ComboBox: PG, PG-13, R, X, XXX）
- Score 入力（SpinBox: 0-1000）
- "保存"ボタン

**シグナル**:
```python
rating_changed = Signal(int, str)  # image_id, rating
score_changed = Signal(int, int)   # image_id, score
```

**注**: SelectedImageDetailsWidget から分離した既存の編集機能

### 2. BatchTagAddWidget (UI + Python)
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

### 3. Integration Tests
**ファイル**: `tests/integration/gui/test_batch_tag_add_integration.py`

## 既存ファイル変更

### 1. MainWindow.ui（優先度: 高）
**変更内容**: QStackedWidget → QTabWidget（3タブ構成）
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
  <widget class="QWidget" name="tabRatingScoreEdit">
    <attribute name="title"><string>Rating/Score編集</string></attribute>
    <layout class="QVBoxLayout">
      <item>
        <widget class="RatingScoreEditWidget"/>
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
- MainWindow.uiからは完全に削除
- RatingScoreEditWidget に Rating/Score 編集機能を移行
- ImageEditPanelWidget クラスは削除（不要）

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

### 4. SelectedImageDetailsWidget（優先度: 高）
**ファイル**:
- `src/lorairo/gui/designer/SelectedImageDetailsWidget.ui`
- `src/lorairo/gui/widgets/selected_image_details_widget.py`

**変更内容**: Rating/Score 編集機能を削除
- Rating/Score 編集UI（ComboBox, SpinBox, 保存ボタン）を削除
- 読み取り専用の表示のみに変更
- 編集関連のシグナルとスロットを削除

### 5. MainWindow（優先度: 高）
**ファイル**: `src/lorairo/gui/window/main_window.py`

**追加メソッド**:
```python
# Rating/Score 編集ハンドラー
def _handle_rating_changed(image_id: int, rating: str) -> None
def _handle_score_changed(image_id: int, score: int) -> None

# バッチタグ追加ハンドラー
def _handle_batch_tag_add(image_ids: list[int], tag: str) -> None
def _handle_staging_cleared() -> None
```

**シグナル接続** (`_connect_events()`):
```python
# RatingScoreEditWidget
self.ratingScoreEditWidget.rating_changed.connect(self._handle_rating_changed)
self.ratingScoreEditWidget.score_changed.connect(self._handle_score_changed)

# BatchTagAddWidget
self.batchTagAddWidget.tag_add_requested.connect(self._handle_batch_tag_add)
self.batchTagAddWidget.staging_cleared.connect(self._handle_staging_cleared)
```

**実装詳細**:
- `_handle_rating_changed()`: ImageDBWriteService.update_rating() を呼び出し
- `_handle_score_changed()`: ImageDBWriteService.update_score() を呼び出し
- `_handle_batch_tag_add()`: ImageDBWriteService.add_tag_batch() を呼び出し
- 成功/失敗のメッセージ表示
- 成功時は DatasetStateManager.refresh_images() で UI 更新

### 6. DatasetStateManager（優先度: 中）
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
- [ ] RatingScoreEditWidget.ui作成（Qt Designer）
- [ ] RatingScoreEditWidget Python クラス実装（Rating ComboBox + Score SpinBox + 保存ボタン）
- [ ] SelectedImageDetailsWidget.ui変更（Rating/Score 編集UI削除）
- [ ] BatchTagAddWidget.ui作成（Qt Designer）
- [ ] BatchTagAddWidget Python クラス実装（シンプル: ステージングリスト + タグ入力 + ボタン）
- [ ] MainWindow.ui変更（QStackedWidget → QTabWidget 3タブ構成）
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

### 5. タグ正規化の責務
- **正規化場所**: BatchTagAddWidget._on_add_button_clicked() 内で実施
- **Service側**: 正規化済みタグを受け取る前提（バリデーションなし）
- **空/無効タグ**: Widget側で事前チェック、空文字列はエラーメッセージ表示
- **正規化失敗**: TagDBtools API がエラーを返した場合、ユーザーにエラー表示
- **単一責務**: Widget = UI + 正規化、Service = DB操作のみ

### 6. ドラッグ選択同期の整合性
- **現状**: DatasetStateManager.selected_image_ids → ThumbnailItem の選択状態を反映
- **追加**: QGraphicsScene.selectionChanged → DatasetStateManager.selected_image_ids に逆同期
- **整合性保証**:
  - scene.selectionChanged を blockSignals() で一時的にブロックして循環参照を回避
  - ThumbnailSelectorWidget._sync_selection_to_state() 内で blockSignals(True) → set_selected_images() → blockSignals(False)
- **優先順位**: DatasetStateManager を真の状態として扱う

### 7. ステージングリストの挙動
- **重複扱い**: 同じ image_id は追加しない（set で管理）
- **順序**: 追加順を保持（OrderedDict または list + set の組み合わせ）
- **個別削除**: 各ステージング項目に "削除" ボタンを配置
- **全クリア**: "クリア" ボタンで全件削除
- **上限超過**: 500枚を超える場合、エラーメッセージ表示（追加しない）

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
- 3タブ構成: 画像詳細（読み取り専用） + Rating/Score編集 + バッチタグ追加
- Rating/Score: SelectedImageDetailsWidget から分離し、独立タブに配置
- バッチ操作: 1つのタグ追加のみ
- 右クリックメニュー: 実装しない
- 個別編集（順次編集）: 実装しない

