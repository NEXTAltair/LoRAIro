# Plan: enchanted-questing-puddle

**Created**: 2026-02-06 03:01:46
**Source**: plan_mode
**Original File**: enchanted-questing-puddle.md
**Status**: planning

---

# サムネイル表示ページネーション機能 実装計画

**Created**: 2026-02-06
**Updated**: 2026-02-06 (方針確定版 v2)
**Status**: planning_refined

---

## 概要

**問題**: 18,252件の検索結果で全QPixmapをメモリ保持 → タイムアウト発生
**解決策**: 表示側ページネーション + プリフェッチ（検索結果メタデータは全件保持、画像キャッシュは5ページ=約500枚）

## 用語メモ（実装で使う定義）

- **SoT (Single Source of Truth)**: その情報の「唯一の正」データ。重複保持しない基準データ。
- **本計画のSoT**:
  - 検索結果メタデータ/選択状態のSoT = `DatasetStateManager`
  - ページ番号/ページサイズ/総ページ数のSoT = `PaginationStateManager`
- **P50/P95**:
  - P50: 50%点（中央値）
  - P95: 95%点（遅い側の代表値）
  - 例: ページ読み込み時間P95 1.0秒 = 95%の遷移が1.0秒以内
- **ステージング**: `BatchTagAddWidget`のバッチタグ追加対象リスト（DatasetStateManagerの選択状態とは別）

## アーキテクチャ

```
SearchResult (全件メタデータ)
    ↓
DatasetStateManager (SoT: メタデータ/選択状態)
    ↓
PaginationStateManager (SoT: ページ状態, DatasetStateManagerを参照)
    ↓
ThumbnailPageCache (単一キャッシュ, LRU: 5ページ分)
    ↓
ThumbnailSelectorWidget (表示)
    ↓
PaginationNavWidget (ナビゲーションUI)
```

---

## 決定済み仕様（2026-02-06）

1. **検索完了時**:
   - 検索結果メタデータは全件を `DatasetStateManager` に保存
   - ページ状態を初期化して1ページ目を表示
   - 画像キャッシュは表示ページ + 4ページ分（合計5ページ、約500枚）に制限

2. **旧リクエスト**:
   - ページ切替連打時の旧要求はキャンセル/破棄してよい（最新要求優先）

3. **キャッシュ**:
   - `image_cache` と `scaled_cache` を一本化
   - 新規 `ThumbnailPageCache` を単一キャッシュとして扱う

4. **選択**:
   - Shiftでのページ跨ぎ範囲選択は実装しない

5. **UI表示**:
   - 新ページ確定まで旧ページ表示維持
   - ローディングオーバーレイを表示
   - ページナビゲーションはスクロール領域外（固定フッター）

6. **テスト**:
   - 連打遷移
   - 検索中キャンセル
   - ページ切替中の再検索
   - 既存テストの前提見直しを実施

7. **ステージング操作対象**（BatchTagAddWidget）:
   - 可視範囲の選択のみを対象とする（全選択一括追加はデフォルトでは提供しない）
   - ページ遷移で既存ステージングはクリアしない

8. **プリフェッチポリシー**:
   - **前後均等方式**: 現在ページを中心に前後2ページずつ
   - 例: Page 3 表示中 → [1, 2, 3, 4, 5] をキャッシュ
   - 境界処理: Page 1 → [1, 2, 3, 4, 5], Page 183 → [179, 180, 181, 182, 183]

9. **ID管理**:
   - `PaginationStateManager`は`DatasetStateManager`を参照してimage_idを取得
   - 独立したコピーは保持しない（SoT原則に忠実）

---

## 新規コンポーネント

### 1. PaginationStateManager
**場所**: `src/lorairo/gui/state/pagination_state.py`

```python
class PaginationStateManager(QObject):
    page_changed = Signal(int)
    loading_started = Signal(int)
    loading_completed = Signal(int, list)

    def __init__(self, dataset_state: DatasetStateManager):
        self._dataset_state = dataset_state  # 参照方式
        self._current_page: int = 1
        self._page_size: int = 100

    @property
    def _all_image_ids(self) -> list[int]:
        """DatasetStateManagerから動的に取得"""
        return [m["id"] for m in self._dataset_state.filtered_images]

    + get_page_image_ids(page: int) -> list[int]
    + get_prefetch_pages(page: int) -> list[int]  # 前後均等方式
    + total_pages: int (property)
```

### 2. ThumbnailPageCache
**場所**: `src/lorairo/gui/cache/thumbnail_page_cache.py`

```python
class ThumbnailPageCache:
    - _max_pages: int = 5
    - _cache: OrderedDict[int, list[tuple[int, QPixmap]]]  # 単一キャッシュ

    + get_page(page_num) -> list | None  # LRU更新
    + set_page(page_num, thumbnails)      # 古いページ自動evict
    + has_page(page_num) -> bool
    + clear()
```

### 3. PaginationNavWidget
**場所**: `src/lorairo/gui/widgets/pagination_nav_widget.py`

```
UI: [|<] [<] [Page 1 of 183] [>] [>|] [Loading...]
配置: スクロール領域外の固定フッター

Signals:
- page_requested(int)

Methods:
- update_state(current, total, is_loading)
```

---

## 変更コンポーネント

### 4. ThumbnailWorker
**ファイル**: `src/lorairo/gui/workers/thumbnail_worker.py`

**変更内容**: ページ単位読み込み対応 + リクエスト識別

```python
def __init__(
    self,
    search_result: SearchResult,
    thumbnail_size: QSize,
    db_manager: ImageDatabaseManager,
    image_id_filter: list[int] | None = None,  # NEW
    request_id: str | None = None,              # NEW
    page_num: int | None = None,                # NEW
):
```

### 5. WorkerService
**ファイル**: `src/lorairo/gui/services/worker_service.py`

**追加メソッド**:
```python
def start_thumbnail_page_load(
    self,
    search_result: SearchResult,
    thumbnail_size: QSize,
    image_ids: list[int],
    page_num: int,
    request_id: str,
    cancel_previous: bool = True,
) -> str:
```

### 6. ThumbnailSelectorWidget
**ファイル**: `src/lorairo/gui/widgets/thumbnail.py`

**追加**:
- `pagination_state: PaginationStateManager`
- `page_cache: ThumbnailPageCache`
- `pagination_nav: PaginationNavWidget`
- `setup_pagination_ui()`
- `_display_page(page_num)`
- `_on_page_changed(page)`
- `_show_loading_overlay()` / `_hide_loading_overlay()`
- 旧ページ維持表示 + 新ページ確定時差し替え
- Shiftページ跨ぎ範囲選択は非対応
- `image_cache`/`scaled_cache` の一本化（`ThumbnailPageCache`へ）

---

## 実装フェーズ

### Phase 1: 基盤クラス
1. `PaginationStateManager` 作成（DatasetStateManager参照方式）
2. `ThumbnailPageCache` 作成
3. ユニットテスト

### Phase 2: Worker拡張
1. `ThumbnailWorker` に `image_id_filter/request_id/page_num` 追加
2. `WorkerService.start_thumbnail_page_load()` 追加
3. 旧要求キャンセル/破棄ロジック実装（最新要求優先）
4. ユニットテスト

### Phase 3: UIコンポーネント
1. `PaginationNavWidget` 作成
2. 固定フッターへ配置（スクロール領域外）
3. `ThumbnailSelectorWidget` へ統合
4. 旧ページ維持 + ローディングオーバーレイ表示

### Phase 4: 統合
1. 検索完了時フロー変更（全件メタデータ同期 + 1ページ目要求）
2. プリフェッチロジック実装（前後均等方式、合計5ページ保持）
3. `PipelineControlService` 更新

### Phase 5: 選択・仕上げ
1. Shiftページ跨ぎ範囲選択は非対応を明示
2. キーボードナビゲーション（PageUp/Down）
3. ステージング対象仕様の実装（可視範囲の選択のみ、BatchTagAddWidget）
4. パフォーマンステスト

---

## 重要ファイル

| ファイル | 役割 |
|---------|------|
| `src/lorairo/gui/widgets/thumbnail.py` | メイン改修対象 |
| `src/lorairo/gui/workers/thumbnail_worker.py` | 部分読み込み対応 |
| `src/lorairo/gui/state/dataset_state.py` | SoT（メタデータ/選択） |
| `src/lorairo/gui/state/pagination_state.py` | SoT（ページ状態）**新規** |
| `src/lorairo/gui/cache/thumbnail_page_cache.py` | LRUキャッシュ **新規** |
| `src/lorairo/gui/widgets/pagination_nav_widget.py` | ナビUI **新規** |
| `src/lorairo/gui/services/worker_service.py` | 新メソッド追加 |
| `src/lorairo/gui/services/pipeline_control_service.py` | パイプライン修正 |

---

## テスト方針

### ユニットテスト
- `PaginationStateManager`: ページ計算、ID抽出、前後均等プリフェッチ
- `ThumbnailPageCache`: LRU eviction、キャッシュヒット/ミス
- `ThumbnailWorker`: フィルタ付き読み込み、request_id/page_num整合性

### 統合テスト
- ページナビゲーションフロー
- キャッシュプリフェッチ（前後均等方式）
- 連打遷移（旧要求キャンセル/破棄）
- 検索中キャンセル
- ページ切替中の再検索
- 既存テスト前提変更の回帰確認

### パフォーマンステスト
- 18,000件でのメモリ使用量（目標: <500MB）
- ページ読み込み時間（目標: P95 <1秒）

---

## 検証方法

1. **機能検証**:
   ```bash
   uv run lorairo
   # 18,000件以上のデータセットで検索実行
   # ページ遷移、プリフェッチ、旧要求キャンセル動作確認
   ```

2. **テスト実行**:
   ```bash
   uv run pytest tests/unit/gui/state/test_pagination_state.py
   uv run pytest tests/unit/gui/cache/test_thumbnail_page_cache.py
   uv run pytest tests/unit/gui/workers/test_thumbnail_worker.py -k "filter or request"
   uv run pytest tests/integration/gui/test_pagination_integration.py
   ```

3. **メモリ監視**:
   ```bash
   # memory_profiler 等でメモリ使用量確認
   # 目標: 500件分のQPixmap相当（総件数非依存で上限固定）
   ```

---

## パラメータ設定

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| `page_size` | 100 | 1ページあたりの表示件数 |
| `max_cached_pages` | 5 | キャッシュ保持ページ数（約500枚） |
| `prefetch_policy` | 前後均等 | 現在ページを中心に前後2ページずつ |

**メモリ削減効果**: 18,252件 → 500件分 (約97%削減)

---

## 背景情報

### 検討した4つのアプローチ
1. **従来型ページネーション**: 実装コスト低、UX中程度
2. **無限スクロール**: メモリが増加し続ける問題
3. **仮想スクロール**: アーキテクチャ変更が大きい
4. **ハイブリッド**: 複雑すぎる

### 採用理由
- 即効性: 現在のタイムアウト問題を最小コストで解決
- UX維持: プリフェッチにより遷移時の待機時間を最小化
- 既存アーキテクチャ活用: ThumbnailSelectorWidgetの拡張で対応可能

### 関連Memory
- `design_pagination_approach_comparison_2026_02_05.md`: アプローチ比較検討の詳細
