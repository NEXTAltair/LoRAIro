# Search-Thumbnail Integration Phase 2 Revised Plan

## 修正版計画作成日: 2025-08-21（Schema.py整合性対応済み）

## GPT-5指摘事項対応済み詳細仕様

### 1. 明示的シグナル配線仕様

#### FilterSearchPanel → MainWindow
```python
# FilterSearchPanel 発火側
self.search_completed.emit({
    "results": search_result.image_metadata,  # list[dict[str, Any]]
    "count": search_result.total_count,       # int
    "conditions": search_result.filter_conditions,  # dict[str, Any]
    "search_time": search_result.search_time  # float
})

# MainWindow 受信側
filter_search_panel.search_completed.connect(self._on_search_completed)
```

#### MainWindow → ThumbnailSelectorWidget
```python
# MainWindow 内部処理
def _on_search_completed(self, result: dict) -> None:
    # 1. 前回サムネイル処理のキャンセル
    self._cancel_previous_thumbnail_loading()
    
    # 2. サムネイル領域クリア（検索開始時要件）
    self.thumbnail_selector.scene.clear()
    
    # 3. 結果0件チェック
    if result["count"] == 0:
        return  # 非表示状態維持
    
    # 4. ThumbnailWorker起動
    worker_id = self.worker_service.start_thumbnail_loading(
        image_metadata=result["results"],
        thumbnail_size=QSize(200, 200)  # 設定から取得
    )
```

#### WorkerService → MainWindow
```python
# WorkerService シグナル
worker_service.thumbnail_finished.connect(self._on_thumbnail_finished)

# MainWindow 受信処理
def _on_thumbnail_finished(self, thumbnail_result: ThumbnailLoadResult) -> None:
    self.thumbnail_selector.load_thumbnails_from_result(thumbnail_result)
```

### 2. データスキーマ定義（Schema.py整合性確認済み）

#### SearchResult.image_metadata必須キー
調査結果: `get_images_by_filter()` → `_fetch_filtered_metadata()` が返すdict

**⚠️ Schema.py準拠修正済み**

```python
# 必須キー（オリジナル画像の場合: src/lorairo/database/schema.py Image テーブル）
{
    "id": int,                    # 画像ID (line 144)
    "stored_image_path": str,     # ファイルパス (line 148)
    "width": int,                 # 幅 (line 149)
    "height": int,                # 高さ (line 150)
    "created_at": datetime,       # 作成日時 (line 159)
    "phash": str,                 # ファイルハッシュ (line 146) ※file_hashから修正
    # file_size は schema.py に存在しないため削除
    # その他のImageテーブルカラム（uuid, original_image_path, format等）
}

# ProcessedImage の場合（resolution > 0: schema.py ProcessedImage テーブル）
{
    "id": int,                    # ProcessedImageのID (line 194)
    "image_id": int,              # 元画像のID (line 195)
    "stored_image_path": str,     # 処理済み画像パス (line 198)
    "width": int,                 # 処理済み幅 (line 199)
    "height": int,                # 処理済み高さ (line 200)
    "created_at": datetime,       # 作成日時 (line 207)
    # その他のProcessedImageテーブルカラム（mode, has_alpha等）
}
```

#### ThumbnailWorker引数仕様確認済み
```python
ThumbnailWorker(
    image_metadata: list[dict[str, Any]],  # 上記スキーマのリスト
    thumbnail_size: QSize,                 # (200, 200) など
    db_manager: ImageDatabaseManager       # DB接続
)
```

#### ThumbnailLoadResult出力仕様確認済み
```python
@dataclass
class ThumbnailLoadResult:
    loaded_thumbnails: list[tuple[int, QPixmap]]  # (image_id, pixmap)
    failed_count: int
    total_count: int  
    processing_time: float
```

### 3. 進捗表示統合仕様

#### フェーズ配分（生成→読み込みに修正）
- **検索フェーズ**: 30%
- **サムネイル読み込みフェーズ**: 70%

#### 進捗計算ロジック
```python
# FilterSearchPanel での表示テキスト
stage_messages = {
    "search": "検索中...",
    "thumbnail_loading": "サムネイル読み込み中...",
}

# 全体進捗計算（MainWindowで実装想定）
def calculate_overall_progress(search_progress: float, thumbnail_progress: float, current_stage: str) -> int:
    if current_stage == "search":
        return int(0.3 * search_progress)
    elif current_stage == "thumbnail_loading":  
        return int(30 + 0.7 * thumbnail_progress)
    return 0
```

#### WorkerService進捗シグナル購読
```python
# WorkerService.worker_progress_updated シグナル
worker_service.worker_progress_updated.connect(self._on_worker_progress)

def _on_worker_progress(self, worker_id: str, progress: float) -> None:
    if worker_id == self.current_search_worker_id:
        # 検索進捗更新
        overall = self.calculate_overall_progress(progress, 0, "search")
        self.update_progress_display(overall, "検索中...")
    elif worker_id == self.current_thumbnail_worker_id:
        # サムネイル進捗更新
        overall = self.calculate_overall_progress(100, progress, "thumbnail_loading")
        self.update_progress_display(overall, "サムネイル読み込み中...")
```

### 4. キャンセル伝播仕様

#### カスケードキャンセル実装
```python
class MainWindow:
    def _cancel_previous_thumbnail_loading(self) -> None:
        """新規検索開始時の前回サムネイル処理自動キャンセル"""
        if hasattr(self.worker_service, 'current_thumbnail_worker_id'):
            if self.worker_service.current_thumbnail_worker_id:
                self.worker_service.cancel_thumbnail_loading(
                    self.worker_service.current_thumbnail_worker_id
                )
    
    def _on_search_cancel_requested(self) -> None:
        """FilterSearchPanelからのキャンセル要求"""
        # 検索キャンセル
        if self.current_search_worker_id:
            self.worker_service.cancel_search(self.current_search_worker_id)
        
        # サムネイル処理もキャンセル  
        self._cancel_previous_thumbnail_loading()
        
        # UI完全リセット
        self._reset_pipeline_ui()
```

### 5. エラー・フォールバック仕様

#### サムネイル読み込み失敗時
```python
def _on_thumbnail_error(self, error: str) -> None:
    """サムネイル読み込みエラー時の処理"""
    logger.error(f"サムネイル読み込みエラー: {error}")
    
    # 検索結果も破棄（ユーザー要件）
    self.filter_search_panel.clear_search_preview()
    self.thumbnail_selector.scene.clear()
    
    # エラーメッセージ表示
    self.filter_search_panel.ui.textEditPreview.setPlainText(
        f"サムネイル読み込み中にエラーが発生しました: {error}"
    )
    
    # UI完全リセット
    self._reset_pipeline_ui()
```

#### 一部失敗時の継続表示方針
- **方針**: 成功分のみ表示、失敗分は非表示
- **実装**: `ThumbnailLoadResult.loaded_thumbnails` に成功分のみ含まれる設計を活用

### 6. 実装ポイント明文化

#### MainWindow新規メソッド
```python
def _on_search_completed(self, result: dict) -> None:
    """検索完了→サムネイル読み込み開始の中継処理"""

def _on_thumbnail_finished(self, thumbnail_result: ThumbnailLoadResult) -> None:  
    """サムネイル読み込み完了→表示反映"""

def _on_pipeline_progress(self, worker_id: str, progress: float) -> None:
    """パイプライン進捗の統合表示"""

def _cancel_previous_thumbnail_loading(self) -> None:
    """前回サムネイル処理のキャンセル"""

def _reset_pipeline_ui(self) -> None:
    """パイプライン UI状態の完全リセット"""
```

#### 依存注入前提確認済み
```python  
# MainWindow.__init__ で確認済み
self.worker_service = WorkerService(self.db_manager, self.file_system_manager)
```

### 7. テスト検証項目

#### シグナル遷移フロー検証
```python
# 期待される信号遷移
1. ユーザー検索実行
2. FilterSearchPanel.search_requested → WorkerService.start_search
3. WorkerService.search_finished → FilterSearchPanel._on_search_finished  
4. FilterSearchPanel.search_completed → MainWindow._on_search_completed
5. MainWindow → WorkerService.start_thumbnail_loading
6. WorkerService.thumbnail_finished → MainWindow._on_thumbnail_finished
7. MainWindow → ThumbnailSelectorWidget.load_thumbnails_from_result
8. サムネイル表示完了
```

#### エラー・キャンセル分岐検証
- 検索エラー → UI完全リセット
- サムネイル読み込みエラー → 検索結果破棄 + UI完全リセット  
- 検索段階キャンセル → パイプライン全停止
- サムネイル段階キャンセル → UI完全リセット

### 8. 削除済み項目（ユーザー指示）

#### 削除1: バッチサイズ・並列度制限
- ~~200件超での段階的処理~~
- ~~同時実行数制限~~  
- ワーカーは全件一括処理、必要時に後から実装

#### 削除2: 生成関連記述  
- ~~「サムネイル生成」~~ → 「サムネイル読み込み」に統一
- ~~進捗配分「生成90%」~~ → 「読み込み70%」に修正

#### 削除3: Schema.py不整合項目（修正対応済み）
- ~~`file_size`キー~~ → schema.pyに存在しないため削除
- ~~`file_hash`キー~~ → schema.py準拠で`phash`に修正

### 完了判定基準（修正版）

- ✅ 検索実行 → サムネイル自動読み込み → 表示の自動連鎖動作
- ✅ 明示的シグナル配線による確実な処理連携
- ✅ 2段階進捗統合表示（検索30% + 読み込み70%）
- ✅ カスケードキャンセル処理（検索→サムネイル読み込み連鎖停止）
- ✅ エラー時完全破棄・リセット（検索結果含む）
- ✅ 検索結果0件時適切非表示
- ✅ 検索開始時サムネイル領域即座クリア
- ✅ **Schema.py準拠データ構造確保**

### 実装順序
1. MainWindowシグナル配線実装
2. パイプライン制御メソッド実装  
3. 進捗統合表示実装
4. エラー・キャンセル処理実装
5. 統合テスト実行