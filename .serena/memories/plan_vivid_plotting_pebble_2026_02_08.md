# Plan: vivid-plotting-pebble

**Created**: 2026-02-08 07:31:58
**Source**: plan_mode
**Original File**: vivid-plotting-pebble.md
**Status**: planning

---

# バッチレーティング設定機能 実装計画

## Context

**背景:**
現在のLoRAIroでは、画像のレーティング/スコア設定は1件ずつしか行えません。ユーザーが特定のタグで検索した結果（例: 100枚）のレーティングを一括で設定したい場合、1件ずつ開いて設定する必要があり、非効率です。

**ユーザー要求:**
1. ワークスペースでサムネイル複数選択
2. 左カラムのレーティング設定を有効化
3. 特定のタグで検索した結果を一括でレーティング設定

**解決策:**
既存のBatchTagAddWidget パターンを踏襲し、RatingScoreEditWidget をバッチモード対応に拡張します。複数選択時に「X件選択中」と表示し、Save時に全選択画像のレーティング/スコアを一括更新します。

---

## アーキテクチャ概要

### レイヤー構成

```
UI層 (RatingScoreEditWidget)
  ↓ batch_rating_changed(image_ids, rating) [新規シグナル]
MainWindow (ハンドラ)
  ↓ update_rating_batch(image_ids, rating)
Service層 (ImageDBWriteService)
  ↓ update_rating_batch(image_ids, rating, model_id)
Repository層 (DBRepository)
  - トランザクション管理: 全件成功 or 全件ロールバック
```

### BatchTagAdd パターンとの違い

| 項目 | BatchTagAdd | BatchRating/Score |
|------|-------------|-------------------|
| ステージング | あり（最大500枚） | **なし（直接適用）** |
| データ型 | append（既存タグに追加） | **replace（既存値を上書き）** |
| UI状態表示 | ステージングリスト表示 | **「X件選択中」表示** |
| 適用タイミング | "追加"ボタン | **"Save"ボタン** |

---

## データフロー

### 複数選択モード（新規実装）

1. **ThumbnailSelectorWidget**: Ctrl/Shift+クリックで複数選択
2. **DatasetStateManager**: `selection_changed` シグナル発火
3. **MainWindow**: `_handle_selection_changed_for_rating()` で RatingScoreEditWidget に通知
4. **RatingScoreEditWidget**: バッチモード切り替え
   - UI表示: 「3件選択中」ラベル表示
   - 現在値: 全選択画像が同じ値なら表示、異なる場合は「--」（ユーザー選択）
5. **ユーザー操作**: Rating/Scoreを変更 → Save
6. **RatingScoreEditWidget**: `batch_rating_changed(image_ids, rating)` シグナル発火
7. **MainWindow**: `_handle_batch_rating_changed()` 実行
8. **ImageDBWriteService**: `update_rating_batch(image_ids, rating)` 実行
9. **DBRepository**: トランザクション内で全件UPDATE
10. **DatasetStateManager**: `refresh_images(image_ids)` でキャッシュ一括更新

---

## ファイル変更一覧

### 1. UI層: RatingScoreEditWidget

**ファイル:** `src/lorairo/gui/widgets/rating_score_edit_widget.py`

**新規シグナル:**
```python
batch_rating_changed = Signal(list, str)  # (image_ids: list[int], rating: str)
batch_score_changed = Signal(list, int)   # (image_ids: list[int], score: int)
```

**新規属性:**
```python
self._selected_image_ids: list[int] = []  # 複数選択時のIDリスト
self._is_batch_mode: bool = False         # バッチモードフラグ
```

**新規/変更メソッド:**
- `populate_from_selection(image_ids: list[int])` - 複数選択時のフォーム入力
  - 全画像のRating/Scoreを取得
  - 共通値のみ表示、異なる場合は「--」（プレースホルダー）
  - 「X件選択中」ラベル追加
- `_on_save_clicked()` の拡張 - バッチモード分岐追加
  - `_is_batch_mode == True` なら `batch_rating_changed` シグナル発行
  - `_is_batch_mode == False` なら従来の `rating_changed` シグナル発行

---

### 2. Service層: ImageDBWriteService

**ファイル:** `src/lorairo/gui/services/image_db_write_service.py`

**新規メソッド:**
```python
def update_rating_batch(self, image_ids: list[int], rating: str) -> bool:
    """複数画像のRatingを一括更新

    Args:
        image_ids: 更新対象の画像IDリスト
        rating: Rating値 ("PG", "PG-13", "R", "X", "XXX")

    Returns:
        bool: 更新成功/失敗
    """
    # バリデーション
    # Repository層呼び出し
    # エラーハンドリング

def update_score_batch(self, image_ids: list[int], score: int) -> bool:
    """複数画像のScoreを一括更新

    Args:
        image_ids: 更新対象の画像IDリスト
        score: Score値 (0-1000範囲のUI値)

    Returns:
        bool: 更新成功/失敗
    """
    # UI値(0-1000) → DB値(0.0-10.0)の変換
    # Repository層呼び出し
    # エラーハンドリング
```

**参考:** `add_tag_batch()` (L301-L354)

---

### 3. Repository層: DBRepository

**ファイル:** `src/lorairo/database/db_repository.py`

**新規メソッド:**
```python
def update_rating_batch(
    self,
    image_ids: list[int],
    rating: str,
    model_id: int | None,
) -> tuple[bool, int]:
    """複数画像のRatingを原子的に更新

    Args:
        image_ids: 更新対象の画像IDリスト
        rating: Rating値
        model_id: モデルID（手動編集時は None）

    Returns:
        tuple[bool, int]: (成功フラグ, 更新件数)
    """
    # 単一トランザクション内で処理
    # UPDATE Rating SET normalized_rating=... WHERE image_id IN (...)
    # 失敗時は全件ロールバック

def update_score_batch(
    self,
    image_ids: list[int],
    score: float,  # DB値 (0.0-10.0)
    model_id: int | None,
) -> tuple[bool, int]:
    """複数画像のScoreを原子的に更新

    Args:
        image_ids: 更新対象の画像IDリスト
        score: Score値 (DB値 0.0-10.0)
        model_id: モデルID（手動編集時は None）

    Returns:
        tuple[bool, int]: (成功フラグ, 更新件数)
    """
    # 単一トランザクション内で処理
    # UPDATE Score SET score=... WHERE image_id IN (...)
    # 失敗時は全件ロールバック
```

**トランザクション管理パターン:**
```python
with self.session_factory() as session:
    try:
        # バッチ UPDATE
        stmt = update(Rating).where(Rating.image_id.in_(image_ids)).values(...)
        session.execute(stmt)
        session.commit()
        return (True, len(image_ids))
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Batch update failed: {e}", exc_info=True)
        raise
```

**参考:** `add_tag_to_images_batch()` (L862-L930)

---

### 4. MainWindow 統合

**ファイル:** `src/lorairo/gui/window/main_window.py`

**新規シグナル接続:**
```python
# RatingScoreEditWidget のバッチシグナル接続
self.ratingScoreEditWidget.batch_rating_changed.connect(self._handle_batch_rating_changed)
self.ratingScoreEditWidget.batch_score_changed.connect(self._handle_batch_score_changed)

# DatasetStateManager の選択変更シグナル接続
self.dataset_state_manager.selection_changed.connect(self._handle_selection_changed_for_rating)
```

**新規ハンドラ:**
```python
def _handle_selection_changed_for_rating(self, image_ids: list[int]) -> None:
    """選択変更時のRatingScoreEditWidget更新ハンドラ"""
    if len(image_ids) == 0:
        # 選択なし
        self.ratingScoreEditWidget.clear()
    elif len(image_ids) == 1:
        # 単一選択: 従来の populate_from_image_data()
        image_data = self.dataset_state_manager.get_image_by_id(image_ids[0])
        self.ratingScoreEditWidget.populate_from_image_data(image_data)
    else:
        # 複数選択: 新規 populate_from_selection()
        self.ratingScoreEditWidget.populate_from_selection(image_ids)

def _handle_batch_rating_changed(self, image_ids: list[int], rating: str) -> None:
    """バッチレーティング変更ハンドラ"""
    logger.info(f"Batch rating change: {len(image_ids)} images, rating='{rating}'")

    success = self._execute_batch_rating_write(image_ids, rating)
    if success:
        # キャッシュ更新
        if self.dataset_state_manager:
            self.dataset_state_manager.refresh_images(image_ids)
        logger.info(f"Batch rating update completed")

def _execute_batch_rating_write(self, image_ids: list[int], rating: str) -> bool:
    """バッチレーティング書き込み実行"""
    if not self.image_db_write_service:
        logger.warning("ImageDBWriteService not initialized")
        return False

    success = self.image_db_write_service.update_rating_batch(image_ids, rating)
    return success

def _handle_batch_score_changed(self, image_ids: list[int], score: int) -> None:
    """バッチスコア変更ハンドラ"""
    # _handle_batch_rating_changed() と同様の処理

def _execute_batch_score_write(self, image_ids: list[int], score: int) -> bool:
    """バッチスコア書き込み実行"""
    # _execute_batch_rating_write() と同様の処理
```

**参考:** `_handle_batch_tag_add()` (L966-L990)

---

### 5. DatasetStateManager（既存メソッド活用）

**ファイル:** `src/lorairo/gui/state/dataset_state.py`

**使用する既存メソッド:**
- `refresh_images(image_ids: list[int])` (L474-L530) - バッチ更新後のキャッシュ一括更新
- `get_image_by_id(image_id: int)` (L355-L388) - 単一画像メタデータ取得

**変更なし（既存機能のみ使用）**

---

## 実装手順

### Phase 1: Repository層（バッチ更新クエリ）

1. `DBRepository.update_rating_batch()` 実装
2. `DBRepository.update_score_batch()` 実装
3. ユニットテスト作成: `tests/unit/database/test_db_repository_batch_rating_score.py`
   - トランザクション成功ケース
   - トランザクション失敗→ロールバック確認

### Phase 2: Service層（ビジネスロジック）

1. `ImageDBWriteService.update_rating_batch()` 実装
2. `ImageDBWriteService.update_score_batch()` 実装
3. 統合テスト作成: `tests/integration/services/test_image_db_write_service_batch.py`
   - Service → Repository の連携確認
   - バリデーションエラーハンドリング

### Phase 3: UI層（ウィジェット拡張）

1. `RatingScoreEditWidget` 拡張
   - 新規シグナル定義
   - `populate_from_selection()` 実装
     - 全選択画像のRating/Score取得
     - 共通値のみ表示、異なる場合は「--」
     - 「X件選択中」ラベル追加
   - `_on_save_clicked()` 拡張
     - バッチモード分岐追加
2. GUIテスト作成: `tests/unit/gui/widgets/test_rating_score_edit_widget_batch.py`
   - 単一選択↔複数選択の遷移確認
   - バッチモード時のシグナル発火確認

### Phase 4: MainWindow統合

1. シグナル接続追加
2. ハンドラ実装
3. 統合テスト作成: `tests/integration/gui/test_batch_rating_integration.py`
   - E2Eフロー: 選択→Rating変更→DB更新→キャッシュ更新

### Phase 5: E2Eテスト・検証

1. 手動検証チェックリスト実行
2. リグレッションテスト: 単一選択時の動作確認

---

## テスト戦略

### ユニットテスト

**Repository層:**
- トランザクション成功: 全件更新確認
- トランザクション失敗: 全件ロールバック確認
- 不正なimage_ids: エラーハンドリング

**Service層:**
- バリデーション: Rating値の検証（"PG", "PG-13", "R", "X", "XXX"のみ）
- バリデーション: Score値の検証（0-1000範囲）
- UI値↔DB値変換: Score の 0-1000 ↔ 0.0-10.0

**UI層:**
- シグナル発火: batch_rating_changed / batch_score_changed
- 状態遷移: 単一選択 ↔ 複数選択 ↔ 選択なし
- UI表示: 「X件選択中」ラベル、共通値/プレースホルダー

### 統合テスト

- E2Eフロー: UI → MainWindow → Service → Repository → DB更新 → キャッシュ更新
- エラーリカバリー: DB更新失敗時のロールバック確認

### GUIテスト（pytest-qt）

- 複数選択操作: Ctrl+クリック、Shift+クリック
- Rating/Score変更操作: comboBox変更、スライダー変更
- Saveボタン押下: qtbot.mouseClick()

---

## 検証方法（実装後の動作確認）

### 機能検証チェックリスト

#### 単一選択時（既存動作）
- [ ] 1件選択時、Rating/Score編集可能
- [ ] Save後、DB更新される
- [ ] Save後、サムネイル表示が更新される
- [ ] 既存テストが全てパス

#### 複数選択時（新規機能）
- [ ] 2件以上選択時、「X件選択中」表示
- [ ] 全選択画像が同じRating/Scoreなら表示、異なる場合は「--」
- [ ] Save後、全選択画像のDBが更新される
- [ ] Save後、全選択画像のサムネイル表示が更新される

#### エラーハンドリング
- [ ] DB更新失敗時、全件ロールバック
- [ ] 不正なRating値入力時、バリデーションエラー
- [ ] Score値範囲外入力時、バリデーションエラー

#### パフォーマンス
- [ ] 100件選択時、2秒以内に更新完了
- [ ] 500件選択時、5秒以内に更新完了

---

## Critical Files for Implementation

実装に最も重要なファイル（優先度順）:

1. **`src/lorairo/database/db_repository.py`**
   - バッチ更新クエリの核心実装
   - トランザクション管理パターン
   - 参考: `add_tag_to_images_batch()` (L862-L930)

2. **`src/lorairo/gui/services/image_db_write_service.py`**
   - Service層のバッチ処理ビジネスロジック
   - バリデーションとUI↔DB値変換
   - 参考: `add_tag_batch()` (L301-L354), `update_rating()` (L138-L175), `update_score()` (L177-L214)

3. **`src/lorairo/gui/widgets/rating_score_edit_widget.py`**
   - UI層のバッチモード切り替えロジック
   - 新規シグナル定義、`populate_from_selection()` 実装

4. **`src/lorairo/gui/window/main_window.py`**
   - シグナル接続とハンドラ実装の統合ポイント
   - 参考: `_handle_batch_tag_add()` (L966-L990)

5. **`src/lorairo/gui/state/dataset_state.py`**
   - キャッシュ更新メカニズム（既存メソッド活用）
   - 使用: `refresh_images()` (L474-L530)

---

## リスクと対策

### リスク1: トランザクション失敗時の部分更新

**対策:** 単一トランザクションで全件処理、失敗時は全件ロールバック（BatchTagAddパターン踏襲）

### リスク2: 大量画像選択時のパフォーマンス

**対策:**
- 初期実装: 制限なし（SQLiteのIN句制限は999個まで、段階的処理で対応可能）
- 必要に応じて: チャンク分割処理（500枚ずつ）、プログレスダイアログ表示

### リスク3: 単一選択時の動作変更

**対策:** `_is_batch_mode` フラグで完全に分岐、既存テストを全てパス確認

---

## 実装の核心ポイント

1. **トランザクション管理:** Repository層で全件commit/rollback（原子性保証）
2. **キャッシュ更新:** DB書き込み後に `refresh_images()` 必須
3. **UI値↔DB値変換:** Score の 0-1000 ↔ 0.0-10.0 変換を Service層で実施
4. **後方互換性:** 単一選択時の動作は完全に保持（`_is_batch_mode` で分岐）
5. **UI表示:** 全選択画像が同じ値なら表示、異なる場合は「--」（ユーザー選択）
