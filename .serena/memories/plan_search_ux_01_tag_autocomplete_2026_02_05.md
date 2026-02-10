# Plan: タグオートコンプリート機能

**Created**: 2026-02-05
**Source**: manual_sync
**Original File**: search-ux-01-tag-autocomplete.md
**Status**: planning

---

## 概要
検索入力欄でタグ名を入力中に候補をサジェストし、選択できる機能を追加する。

## 目的
- タグ名の正確な入力が不要になる
- 発見性向上（どんなタグがあるか分かる）
- 入力時間短縮

---

## 実装方針

### アプローチ: QCompleter + 非同期検索

Qt標準の`QCompleter`を使用し、`genai-tag-db-tools`の`search_tags()`APIで候補を取得する。

---

## 変更対象ファイル

### 1. FilterSearchPanel（UI統合）
**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`

**追加内容**:
- `QCompleter`のセットアップ
- 入力変更時のデバウンス処理
- 候補選択時のカンマ区切り挿入

```python
# 追加するメソッド
def _setup_tag_completer(self) -> None:
    """タグオートコンプリートを設定"""
    self.tag_completer = QCompleter()
    self.tag_completer.setCaseSensitivity(Qt.CaseInsensitive)
    self.tag_completer.setCompletionMode(QCompleter.PopupCompletion)
    self.ui.lineEditSearch.setCompleter(self.tag_completer)

    # デバウンスタイマー
    self._completer_timer = QTimer()
    self._completer_timer.setSingleShot(True)
    self._completer_timer.timeout.connect(self._fetch_tag_suggestions)

    self.ui.lineEditSearch.textChanged.connect(self._on_search_text_changed)

def _on_search_text_changed(self, text: str) -> None:
    """入力変更時の処理（デバウンス付き）"""
    # 最後のカンマ以降のテキストを取得
    current_term = self._get_current_input_term(text)
    if len(current_term) >= 2:  # 2文字以上で検索開始
        self._completer_timer.start(300)  # 300msデバウンス

def _fetch_tag_suggestions(self) -> None:
    """タグ候補を取得"""
    # search_tags() を呼び出して候補を取得
```

### 2. TagSuggestionService（新規作成）
**ファイル**: `src/lorairo/services/tag_suggestion_service.py`

**責務**:
- `search_tags()`のラッパー
- 結果のキャッシング（LRU）
- 最近使用タグの優先表示

```python
class TagSuggestionService:
    def __init__(self, merged_reader: MergedTagReader):
        self.reader = merged_reader
        self._cache: dict[str, list[str]] = {}
        self._recent_tags: list[str] = []

    def get_suggestions(self, query: str, limit: int = 15) -> list[str]:
        """タグ候補を取得"""
        request = TagSearchRequest(
            query=query,
            partial=True,  # 部分一致
            include_aliases=True,
            include_deprecated=False,
            resolve_preferred=True,
        )
        result = search_tags(self.reader, request)
        tags = [item.tag for item in result.items[:limit]]
        return self._prioritize_recent(tags)
```

### 3. 既存コード活用
**活用するAPI**:
- `genai_tag_db_tools.search_tags()` - タグ検索
- `genai_tag_db_tools.models.TagSearchRequest` - 検索リクエスト
- `db_repository.merged_reader` - MergedTagReaderインスタンス

---

## UI設計

### 動作フロー
```
1. ユーザーが入力開始
2. 2文字以上で300ms待機（デバウンス）
3. search_tags(partial=True)で候補取得
4. QCompleterポップアップ表示（最大15件）
5. 候補選択でカンマ区切り挿入
6. 次のタグ入力へ
```

### カンマ区切り対応
```
入力例: "1girl, long_"
         ↑ この部分で補完

選択後: "1girl, long_hair, "
                        ↑ カンマとスペース追加
```

---

## テスト計画

### ユニットテスト
- `tests/unit/services/test_tag_suggestion_service.py`
  - 候補取得の正常系
  - 空クエリの処理
  - キャッシュ動作確認

### GUIテスト
- `tests/unit/gui/widgets/test_filter_search_panel_autocomplete.py`
  - QCompleter設定確認
  - デバウンス動作確認
  - カンマ区切り挿入確認

---

## 検証方法

1. アプリ起動: `uv run lorairo`
2. 検索パネルで「1gi」と入力
3. 候補リストに「1girl」が表示されることを確認
4. 候補選択で正しく挿入されることを確認
5. テスト実行: `uv run pytest tests/unit/services/test_tag_suggestion_service.py -v`

---

## 工数見積もり
- TagSuggestionService実装: 中
- FilterSearchPanel統合: 中
- テスト作成: 小
- **合計**: 中程度
