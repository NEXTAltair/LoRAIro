# Plan: 検索結果リアルタイムカウント表示

**Created**: 2026-02-05
**Source**: manual_sync
**Original File**: search-ux-02-realtime-count.md
**Status**: planning

---

## 概要
フィルター変更時に、検索実行前に該当件数をリアルタイムで表示する機能を追加する。

## 目的
- 検索実行前に結果の見当がつく
- 絞り込みすぎ/広すぎの調整が容易
- 無駄な検索実行の削減

---

## 実装方針

### アプローチ: デバウンス付きカウントクエリ

フィルター変更時にデバウンスを適用し、軽量なCOUNTクエリで件数のみを取得する。

---

## 変更対象ファイル

### 1. SearchFilterService（カウント取得メソッド追加）
**ファイル**: `src/lorairo/gui/services/search_filter_service.py`

**追加内容**:
```python
def get_estimated_count(self, conditions: SearchConditions) -> int:
    """検索条件に一致する画像の概算件数を取得（軽量クエリ）"""
    try:
        db_args = conditions.to_db_filter_args()
        count = self.db_manager.get_images_count_only(**db_args)
        return count
    except Exception as e:
        logger.warning(f"カウント取得エラー: {e}")
        return -1  # エラー時は-1
```

### 2. ImageDatabaseManager（カウント専用メソッド追加）
**ファイル**: `src/lorairo/database/db_manager.py`

**追加内容**:
```python
def get_images_count_only(self, **filter_args) -> int:
    """検索条件に一致する画像の件数のみを取得（軽量版）"""
    return self.repository.get_images_count_only(**filter_args)
```

### 3. ImageRepository（軽量カウントクエリ）
**ファイル**: `src/lorairo/database/db_repository.py`

**追加内容**:
```python
def get_images_count_only(
    self,
    tags: list[str] | None = None,
    caption: str | None = None,
    resolution: str | None = None,
    use_and: bool = True,
    # ... 他のフィルター引数
) -> int:
    """検索条件に一致する画像の件数のみを返す（メタデータ取得なし）"""
    with self.get_session() as session:
        # フィルタークエリを構築（既存メソッド活用）
        query = self._build_image_filter_query(
            session, tags, caption, resolution, use_and, ...
        )
        # COUNT(DISTINCT image.id) のみ実行
        count_query = select(func.count(distinct(Image.id))).select_from(query.subquery())
        result = session.execute(count_query).scalar()
        return result or 0
```

### 4. FilterSearchPanel（UI統合）
**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`

**追加内容**:
```python
def __init__(self, ...):
    # デバウンスタイマー
    self._count_update_timer = QTimer()
    self._count_update_timer.setSingleShot(True)
    self._count_update_timer.timeout.connect(self._update_estimated_count)

def _on_filter_changed(self) -> None:
    """フィルター変更時の処理"""
    self._count_update_timer.start(500)  # 500msデバウンス

def _update_estimated_count(self) -> None:
    """推定件数を更新"""
    conditions = self._build_current_conditions()
    count = self.search_filter_service.get_estimated_count(conditions)
    self._display_estimated_count(count)

def _display_estimated_count(self, count: int) -> None:
    """件数をUIに表示"""
    if count < 0:
        self.ui.labelEstimatedCount.setText("件数: --")
    elif count == 0:
        self.ui.labelEstimatedCount.setText("件数: 0件（条件を緩めてください）")
    else:
        self.ui.labelEstimatedCount.setText(f"件数: 約 {count:,} 件")
```

### 5. FilterSearchPanel.ui（UI要素追加）
**ファイル**: `src/lorairo/gui/designer/FilterSearchPanel.ui`

**追加内容**:
- `labelEstimatedCount`: 件数表示用ラベル
- 配置: 検索ボタンの近くまたはプレビューエリア

---

## シグナル接続

フィルター変更を検知するため、以下のシグナルを`_on_filter_changed()`に接続:
```python
# 既存のシグナル接続に追加
self.ui.checkboxTags.toggled.connect(self._on_filter_changed)
self.ui.checkboxCaption.toggled.connect(self._on_filter_changed)
self.ui.comboResolution.currentTextChanged.connect(self._on_filter_changed)
self.ui.comboAspectRatio.currentTextChanged.connect(self._on_filter_changed)
self.ui.comboRating.currentTextChanged.connect(self._on_filter_changed)
self.ui.comboAIRating.currentTextChanged.connect(self._on_filter_changed)
self.ui.checkboxDateFilter.toggled.connect(self._on_filter_changed)
self.ui.checkboxOnlyUntagged.toggled.connect(self._on_filter_changed)
self.ui.checkboxOnlyUncaptioned.toggled.connect(self._on_filter_changed)
self.ui.checkboxExcludeDuplicates.toggled.connect(self._on_filter_changed)
```

---

## パフォーマンス考慮

1. **デバウンス**: 500msで連続変更をまとめる
2. **軽量クエリ**: メタデータ取得なし、COUNTのみ
3. **非同期実行**: UIブロッキング防止（必要に応じてWorkerService活用）

---

## テスト計画

### ユニットテスト
- `tests/unit/database/test_db_repository_count.py`
  - カウントクエリの正確性
  - 各フィルター条件でのカウント
  - エラー時の挙動

### GUIテスト
- `tests/unit/gui/widgets/test_filter_search_panel_count.py`
  - デバウンス動作確認
  - 表示更新確認

---

## 検証方法

1. アプリ起動: `uv run lorairo`
2. データベースに画像を登録（または既存データ使用）
3. フィルター変更時に件数が更新されることを確認
4. 件数が0の場合のメッセージ確認
5. テスト実行: `uv run pytest tests/unit/database/test_db_repository_count.py -v`

---

## 工数見積もり
- Repository/Managerメソッド追加: 小
- FilterSearchPanel統合: 小
- UI要素追加: 小
- テスト作成: 小
- **合計**: 小
