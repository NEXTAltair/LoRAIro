# Plan: 検索履歴・最近の検索

**Created**: 2026-02-05
**Source**: manual_sync
**Original File**: search-ux-04-search-history.md
**Status**: planning

---

## 概要
検索履歴を自動保存し、過去の検索条件を簡単に再利用できる機能を追加する。

## 目的
- 繰り返し検索の効率化
- 過去の検索条件を思い出せる
- 作業の継続性向上

---

## 実装方針

### アプローチ: FavoriteFiltersServiceパターンの拡張

既存の`FavoriteFiltersService`と同じ`QSettings`永続化パターンを使用し、自動保存の検索履歴サービスを新規作成する。

---

## 変更対象ファイル

### 1. SearchHistoryService（新規作成）
**ファイル**: `src/lorairo/services/search_history_service.py`

**責務**:
- 検索履歴の自動保存
- LRUキャッシュで件数制限（最大10件）
- タイムスタンプ付き保存
- 重複検出・マージ

```python
from datetime import datetime
import json
from PySide6.QtCore import QSettings

class SearchHistoryService:
    """検索履歴の管理サービス"""

    MAX_HISTORY_SIZE = 10
    _history_group = "SearchHistory"

    def __init__(self):
        self._settings = QSettings("LoRAIro", "LoRAIro")

    def add_to_history(self, conditions: dict[str, Any]) -> None:
        """検索条件を履歴に追加"""
        history = self._load_history()

        # 重複チェック（同じ条件があれば更新）
        entry = {
            "conditions": conditions,
            "timestamp": datetime.now().isoformat(),
        }

        # 同じ条件の古いエントリを削除
        history = [h for h in history if not self._conditions_equal(h["conditions"], conditions)]

        # 先頭に追加
        history.insert(0, entry)

        # LRU: 最大件数を超えたら古いものを削除
        if len(history) > self.MAX_HISTORY_SIZE:
            history = history[:self.MAX_HISTORY_SIZE]

        self._save_history(history)

    def get_history(self) -> list[dict[str, Any]]:
        """検索履歴を取得（新しい順）"""
        return self._load_history()

    def clear_history(self) -> None:
        """履歴をクリア"""
        self._save_history([])

    def _load_history(self) -> list[dict[str, Any]]:
        """履歴をQSettingsから読み込み"""
        self._settings.beginGroup(self._history_group)
        history_json = self._settings.value("entries", "[]")
        self._settings.endGroup()
        try:
            return json.loads(history_json)
        except json.JSONDecodeError:
            return []

    def _save_history(self, history: list[dict[str, Any]]) -> None:
        """履歴をQSettingsに保存"""
        self._settings.beginGroup(self._history_group)
        self._settings.setValue("entries", json.dumps(history, ensure_ascii=False, default=str))
        self._settings.endGroup()
        self._settings.sync()

    def _conditions_equal(self, cond1: dict, cond2: dict) -> bool:
        """2つの検索条件が同等かどうか判定"""
        # キーワードと主要フィルターで比較
        keys_to_compare = ["keywords", "search_type", "tag_logic", "resolution_filter"]
        return all(cond1.get(k) == cond2.get(k) for k in keys_to_compare)
```

### 2. FilterSearchPanel（UI統合）
**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`

**追加内容**:
```python
def setup_search_history_ui(self) -> None:
    """検索履歴UIを作成"""
    self.history_group = QGroupBox("検索履歴")
    self.history_group.setCheckable(True)
    self.history_group.setChecked(False)  # 初期状態は折りたたみ

    self.history_list = QListWidget()
    self.history_list.setMaximumHeight(120)
    self.history_list.itemDoubleClicked.connect(self._on_history_item_clicked)

    self.button_clear_history = QPushButton("履歴クリア")
    self.button_clear_history.clicked.connect(self._on_clear_history_clicked)

def set_search_history_service(self, service: SearchHistoryService) -> None:
    """SearchHistoryServiceを設定"""
    self.search_history_service = service
    self._refresh_history_list()

def _on_search_requested(self) -> None:
    """検索実行時に履歴に追加"""
    # 既存の検索処理...

    # 履歴に追加
    if self.search_history_service:
        conditions = self.get_current_conditions()
        self.search_history_service.add_to_history(conditions)
        self._refresh_history_list()

def _refresh_history_list(self) -> None:
    """履歴リストを更新"""
    self.history_list.clear()
    if not self.search_history_service:
        return

    history = self.search_history_service.get_history()
    for entry in history:
        preview = self._format_history_preview(entry)
        self.history_list.addItem(preview)

def _format_history_preview(self, entry: dict) -> str:
    """履歴エントリのプレビュー文字列を生成"""
    cond = entry["conditions"]
    keywords = cond.get("keywords", [])
    keyword_str = ", ".join(keywords[:3])
    if len(keywords) > 3:
        keyword_str += "..."

    timestamp = entry.get("timestamp", "")[:10]  # 日付部分のみ
    return f"[{timestamp}] {keyword_str or '(フィルターのみ)'}"

def _on_history_item_clicked(self, item: QListWidgetItem) -> None:
    """履歴項目クリック時の処理"""
    index = self.history_list.row(item)
    history = self.search_history_service.get_history()
    if 0 <= index < len(history):
        conditions = history[index]["conditions"]
        self.apply_conditions(conditions)
```

### 3. MainWindow（サービス初期化）
**ファイル**: `src/lorairo/gui/window/main_window.py`

**追加内容**:
```python
def _setup_search_filter_integration(self) -> None:
    # 既存のSearchFilterService設定...

    # SearchHistoryService追加
    self.search_history_service = SearchHistoryService()
    self.filter_search_panel.set_search_history_service(self.search_history_service)
```

---

## データ構造

### 履歴エントリ
```python
{
    "conditions": {
        "search_type": "tags",
        "keywords": ["1girl", "blue_eyes"],
        "tag_logic": "and",
        "resolution_filter": "1024x1024",
        # ... 他のフィルター
    },
    "timestamp": "2026-02-05T12:34:56.789"
}
```

### QSettings保存形式
```
[SearchHistory]
entries=[{"conditions": {...}, "timestamp": "..."}, ...]
```

---

## UI設計

### 履歴表示形式
```
検索履歴
┌─────────────────────────────────────┐
│ [2026-02-05] 1girl, blue_eyes, ...  │
│ [2026-02-04] landscape, nature      │
│ [2026-02-03] (フィルターのみ)        │
│ ...                                  │
└─────────────────────────────────────┘
[履歴クリア]
```

### 配置
- お気に入りフィルターグループの下
- 折りたたみ可能（デフォルトは折りたたみ）

---

## テスト計画

### ユニットテスト
- `tests/unit/services/test_search_history_service.py`
  - 履歴追加・取得
  - LRU制限動作
  - 重複検出・マージ
  - 永続化確認

### GUIテスト
- `tests/unit/gui/widgets/test_filter_search_panel_history.py`
  - 履歴リスト更新
  - 履歴項目クリックで条件適用
  - 履歴クリア

---

## 検証方法

1. アプリ起動: `uv run lorairo`
2. 検索を数回実行
3. 検索履歴グループを展開
4. 履歴項目が表示されることを確認
5. 履歴項目ダブルクリックで条件が復元されることを確認
6. アプリ再起動後も履歴が保持されることを確認
7. テスト実行: `uv run pytest tests/unit/services/test_search_history_service.py -v`

---

## 工数見積もり
- SearchHistoryService実装: 小
- FilterSearchPanel統合: 小
- MainWindow統合: 極小
- テスト作成: 小
- **合計**: 小
