# Plan: 除外検索（NOT検索）

**Created**: 2026-02-05
**Source**: manual_sync
**Original File**: search-ux-05-exclude-search.md
**Status**: planning

---

## 概要
特定のタグを除外する検索機能を追加する。

## 目的
- より精密なフィルタリング
- 不要な結果の除外
- ワークフロー効率化

---

## 実装方針

### アプローチ: プレフィックス方式（`-tag`）

入力テキストで`-`プレフィックスを使用して除外タグを指定する。

```
例: "1girl, -1boy, blue_eyes"
    → 「1girl」AND「blue_eyes」を含み、「1boy」を含まない
```

---

## 変更対象ファイル

### 1. SearchConditions（データモデル拡張）
**ファイル**: `src/lorairo/services/search_models.py`

**追加内容**:
```python
@dataclass
class SearchConditions:
    # 既存フィールド...
    search_type: str
    keywords: list[str]
    tag_logic: str
    # ...

    # 新規フィールド
    excluded_keywords: list[str] | None = None  # 除外するキーワード

    def to_db_filter_args(self) -> dict[str, Any]:
        """DB APIの引数に直接変換"""
        return {
            # 既存の引数...
            "tags": self.keywords if self.search_type == "tags" else None,
            "use_and": self.tag_logic == "and",

            # 新規追加
            "excluded_tags": self.excluded_keywords if self.search_type == "tags" else None,
        }
```

### 2. SearchFilterService（入力解析拡張）
**ファイル**: `src/lorairo/gui/services/search_filter_service.py`

**変更内容**:
```python
def parse_search_input(self, input_text: str) -> tuple[list[str], list[str]]:
    """
    UI入力テキストの解析とキーワード抽出

    Args:
        input_text: ユーザー入力テキスト

    Returns:
        tuple: (含むキーワードリスト, 除外キーワードリスト)
    """
    if not input_text:
        return [], []

    positive_keywords = []
    negative_keywords = []

    keywords = [kw.strip() for kw in input_text.split(",") if kw.strip()]
    for kw in keywords:
        if kw.startswith("-") and len(kw) > 1:
            # 除外キーワード
            negative_keywords.append(kw[1:])
        else:
            # 含むキーワード
            positive_keywords.append(kw)

    logger.debug(f"入力解析完了: '{input_text}' -> 含む={positive_keywords}, 除外={negative_keywords}")
    return positive_keywords, negative_keywords

def create_search_conditions(
    self,
    search_type: str,
    keywords: list[str],
    excluded_keywords: list[str] | None = None,  # 新規追加
    tag_logic: str = "and",
    # ... 他の引数
) -> SearchConditions:
    """検索条件を作成"""
    return SearchConditions(
        search_type=search_type,
        keywords=keywords,
        excluded_keywords=excluded_keywords,
        tag_logic=tag_logic,
        # ...
    )
```

### 3. ImageDatabaseManager（引数追加）
**ファイル**: `src/lorairo/database/db_manager.py`

**変更内容**:
```python
def get_images_by_filter(
    self,
    tags: list[str] | None = None,
    excluded_tags: list[str] | None = None,  # 新規追加
    caption: str | None = None,
    resolution: str | None = None,
    use_and: bool = True,
    # ... 他の引数
) -> tuple[list[dict[str, Any]], int]:
    """フィルター条件に基づいて画像を取得"""
    return self.repository.get_images_by_filter(
        tags=tags,
        excluded_tags=excluded_tags,  # 追加
        caption=caption,
        resolution=resolution,
        use_and=use_and,
        # ...
    )
```

### 4. ImageRepository（SQLクエリ拡張）
**ファイル**: `src/lorairo/database/db_repository.py`

**変更内容**:

#### get_images_by_filter() シグネチャ追加
```python
def get_images_by_filter(
    self,
    tags: list[str] | None = None,
    excluded_tags: list[str] | None = None,  # 新規追加
    caption: str | None = None,
    # ...
) -> tuple[list[dict[str, Any]], int]:
```

#### _build_image_filter_query() シグネチャ追加
```python
def _build_image_filter_query(
    self,
    session: Session,
    tags: list[str] | None,
    excluded_tags: list[str] | None,  # 新規追加
    caption: str | None,
    # ...
) -> Select:
    # 既存のフィルター構築...
    query = self._apply_tag_filter(query, tags, excluded_tags, use_and, include_untagged)
```

#### _apply_tag_filter() 拡張
```python
def _apply_tag_filter(
    self,
    query: Select,
    tags: list[str] | None,
    excluded_tags: list[str] | None,  # 新規追加
    use_and: bool,
    include_untagged: bool,
) -> Select:
    """タグフィルターを適用（除外タグ対応）"""

    # 既存の正タグフィルター処理...
    if tags:
        if use_and:
            for tag_term in tags:
                pattern, is_exact = self._prepare_like_pattern(tag_term)
                # EXISTS サブクエリ
                exists_subquery = (
                    select(Tag.id)
                    .where(Tag.image_id == Image.id)
                    .where(Tag.tag == pattern if is_exact else Tag.tag.like(pattern))
                    .correlate(Image)
                    .exists()
                )
                query = query.where(exists_subquery)
        else:
            # OR検索の場合...

    # 新規: 除外タグフィルター
    if excluded_tags:
        for excluded_tag in excluded_tags:
            pattern, is_exact = self._prepare_like_pattern(excluded_tag)

            # NOT EXISTS: 該当タグを持たない画像のみ
            not_exists_subquery = (
                select(Tag.id)
                .where(Tag.image_id == Image.id)
                .where(Tag.tag == pattern if is_exact else Tag.tag.like(pattern))
                .correlate(Image)
                .exists()
            )
            query = query.where(~not_exists_subquery)  # NOT演算子

    return query
```

### 5. FilterSearchPanel（UI更新）
**ファイル**: `src/lorairo/gui/widgets/filter_search_panel.py`

**変更内容**:
```python
def _on_search_requested(self) -> None:
    """検索要求処理"""
    # ...
    search_text = self.ui.lineEditSearch.text().strip()

    # 入力解析（除外キーワード対応）
    keywords, excluded_keywords = self.search_filter_service.parse_search_input(search_text)

    # 検索条件作成
    conditions = self.search_filter_service.create_search_conditions(
        search_type=self._get_primary_search_type(),
        keywords=keywords,
        excluded_keywords=excluded_keywords if excluded_keywords else None,
        tag_logic="and" if self.ui.radioAnd.isChecked() else "or",
        # ...
    )
```

### 6. 検索プレビュー更新
**ファイル**: `src/lorairo/gui/services/search_filter_service.py`

**変更内容**:
```python
def create_search_preview(self, conditions: SearchConditions) -> str:
    """人間が読みやすい検索条件プレビューの生成"""
    parts = []

    # 含むキーワード
    if conditions.keywords:
        logic = "AND" if conditions.tag_logic == "and" else "OR"
        parts.append(f"キーワード: {', '.join(conditions.keywords)} ({logic})")

    # 除外キーワード（新規追加）
    if conditions.excluded_keywords:
        parts.append(f"除外: {', '.join(conditions.excluded_keywords)}")

    # 他のフィルター...

    return " | ".join(parts) if parts else "条件なし"
```

---

## UIヘルプ

### プレースホルダーテキスト更新
```python
self.ui.lineEditSearch.setPlaceholderText(
    "検索キーワードを入力（カンマ区切り、-で除外）..."
)
```

### ツールチップ追加
```python
self.ui.lineEditSearch.setToolTip(
    "例: 1girl, blue_eyes, -1boy\n"
    "「-」で始まるタグは除外されます"
)
```

---

## テスト計画

### ユニットテスト

#### test_search_filter_service.py 追加
```python
def test_parse_search_input_with_exclusion():
    """除外キーワードの解析テスト"""
    service = SearchFilterService(...)

    positive, negative = service.parse_search_input("1girl, -1boy, blue_eyes")
    assert positive == ["1girl", "blue_eyes"]
    assert negative == ["1boy"]

def test_parse_search_input_only_exclusion():
    """除外のみの検索"""
    positive, negative = service.parse_search_input("-1boy, -monochrome")
    assert positive == []
    assert negative == ["1boy", "monochrome"]
```

#### test_db_repository_exclude_tags.py 新規
```python
def test_apply_tag_filter_with_exclusion():
    """除外タグフィルターのテスト"""
    # タグ "1girl" を持ち、"1boy" を持たない画像のみ返す

def test_exclude_multiple_tags():
    """複数の除外タグ"""
    # 複数の除外タグが全てAND条件で適用される

def test_positive_and_negative_tags():
    """正タグと除外タグの組み合わせ"""
```

---

## 検証方法

1. アプリ起動: `uv run lorairo`
2. データベースに複数タグを持つ画像を用意
3. 検索欄に `1girl, -1boy` と入力
4. 「1girl」を含み「1boy」を含まない画像のみ表示されることを確認
5. 検索プレビューに「除外: 1boy」が表示されることを確認
6. テスト実行:
   ```bash
   uv run pytest tests/unit/gui/services/test_search_filter_service.py -v
   uv run pytest tests/unit/database/test_db_repository_exclude_tags.py -v
   ```

---

## 後方互換性

- `excluded_keywords`はデフォルト`None`で既存コードに影響なし
- `parse_search_input()`の戻り値変更は呼び出し元の修正が必要
  - 影響箇所: `FilterSearchPanel._on_search_requested()`
  - 影響箇所: `SearchFilterService.create_search_conditions()` 呼び出し元

---

## 工数見積もり
- SearchConditions拡張: 極小
- SearchFilterService拡張: 小
- Repository層実装: 中
- FilterSearchPanel統合: 小
- テスト作成: 小
- **合計**: 小〜中
