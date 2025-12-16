# データセットビルダー コアアルゴリズム修正 (GPT再チェック対応)

## 修正日
2025年12月13日

## 修正理由
GPT再チェックで指摘された設計の不整合を修正

---

## 1. 根本原則の明確化

### 同一性の基準 = TAGS.tag（正規化済み）
- **UNIQUE(tag)制約**でDB側で重複防止
- tagが同じなら同一タグと判定
- **tag_idは内部連番**（性能用）で公開IDにしない

### 正規化の境界
- `normalize_tag()`は**入力CSV→TAGS.tagへの変換のみ**
- **DB内のtag列は既に正規化済み**なので再正規化しない
- 二重正規化や不整合を防ぐため、この境界を厳守

### tag_idの扱い
- **既存tags_v4.dbのtag_idは保持**
- **新規追加はmax(tag_id)+1から採番**
- **再現性のため新規タグはtagでソート後に採番**
- tag_idは内部処理のみ、外部公開はtag列を使用

---

## 2. マージアルゴリズム（修正版）

**旧アルゴリズムの問題点**:
- normalized列を追加してJOINする設計（不要な処理）
- 巨大outerJOIN前提（非効率）

**新アルゴリズム**:
```python
def merge_tags(
    existing_tags: set[str],  # 既存のtag一覧（tags_v4.dbから取得）
    new_df: pl.DataFrame,     # 新規ソース（source_tag列あり）
    next_tag_id: int          # 次のtag_id（max(tag_id)+1）
) -> pl.DataFrame:
    """
    新規タグをマージ（set差分方式）
    """
    # 1. source_tagを正規化してtag列生成
    new_df = new_df.with_columns(
        pl.col("source_tag").map_elements(normalize_tag).alias("tag")
    )
    
    # 2. set差分抽出（既存tagにないもののみ）
    new_tags_df = new_df.filter(
        ~pl.col("tag").is_in(existing_tags)
    )
    
    # 3. 重複除去
    new_tags_df = new_tags_df.unique(subset=["tag"])
    
    # 4. 再現性のためtagでソート
    new_tags_df = new_tags_df.sort("tag")
    
    # 5. tag_id採番（max+1から連番）
    new_tags_df = new_tags_df.with_row_count("row_num").with_columns(
        (pl.col("row_num") + next_tag_id).alias("tag_id")
    ).drop("row_num")
    
    return new_tags_df.select(["tag_id", "tag", "source_tag"])
```

**改善点**:
- tagでset差分を取る（シンプル・高速）
- 巨大JOINは不要
- 不足分のみINSERT

---

## 3. エイリアス生成フロー

**処理順序**:
1. **canonical作成**: 新規タグをTAGSに追加（merge_tagsで実施）
2. **alias作成**: deprecated_tags列からエイリアス関係を抽出
3. **TAG_STATUS付与**: format単位でcanonical/aliasを登録

**deprecated_tags処理**:
```python
def process_deprecated_tags(
    canonical_tag: str,
    deprecated_tags: str,
    format_id: int,
    tags_mapping: dict[str, int]  # tag → tag_id
) -> list[dict]:
    """deprecated_tags列からTAG_STATUSレコード生成"""
    canonical_tag_id = tags_mapping[canonical_tag]
    records = []
    
    # canonical自身（alias=0）
    records.append({
        "tag_id": canonical_tag_id,
        "format_id": format_id,
        "alias": 0,
        "preferred_tag_id": canonical_tag_id
    })
    
    # aliasレコード（alias=1）
    if deprecated_tags:
        for alias_source_tag in deprecated_tags.split(","):
            alias_tag = normalize_tag(alias_source_tag.strip())
            if alias_tag in tags_mapping:
                alias_tag_id = tags_mapping[alias_tag]
                records.append({
                    "tag_id": alias_tag_id,
                    "format_id": format_id,
                    "alias": 1,
                    "preferred_tag_id": canonical_tag_id
                })
    
    return records
```

**衝突時の扱い**:
- 既存aliasがcanonicalに昇格する場合 → `alias_changes.csv`に記録
- デフォルトは既存優先

---

## 4. 衝突検出（修正版）

**JOINキー修正**: tag_id → **tag + format_id**

**理由**:
- tag_idは採番がビルドで揺れる可能性がある
- tagは正規化済みの安定したキー

**修正後のロジック**:
```python
def detect_conflicts(
    existing_df: pl.DataFrame,  # 既存TAG_STATUS（tag列JOIN済み）
    new_df: pl.DataFrame,       # 新規データ（tag列あり）
    tags_mapping: dict[str, int]
) -> dict:
    """tag + format_id でJOIN（tag_idは後から引く）"""
    
    merged = existing_df.join(
        new_df,
        on=["tag", "format_id"],  # tag_idではなくtagを使用
        how="inner",
        suffix="_new"
    )
    
    # type_id不一致
    type_conflicts = merged.filter(
        pl.col("type_id") != pl.col("type_id_new")
    )
    
    # alias変更（既存=0、新規=1）
    alias_changes = merged.filter(
        (pl.col("alias") == 0) & (pl.col("alias_new") == 1)
    )
    
    return {
        "type_conflicts": type_conflicts,
        "alias_changes": alias_changes
    }
```

---

## 5. TAGS テーブル制約追加

```sql
CREATE TABLE TAGS (
    tag_id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL UNIQUE,  -- ★UNIQUE制約追加
    source_tag TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**制約の意味**:
- `UNIQUE(tag)`: 正規化済みタグの重複をDB側で防止
- `tag`: lowercase + アンダースコア→スペース変換済み
- `source_tag`: 元データ（正規化前）

---

## 6. 実装への影響

### 削除すべきコード
- `normalized`列の追加処理
- `outerJOIN on normalized`
- `map_elements(normalize_tag)`のDB内tag列への適用

### 追加すべきコード
- `UNIQUE(tag)`制約の明示
- エイリアス生成フロー（process_deprecated_tags）
- tag + format_idベースの衝突検出

### 修正すべきコード
- merge_tags(): set差分方式に変更
- detect_conflicts(): JOINキーをtag + format_idに変更

---

**参照**: dataset_builder_design_plan_2025_12_13.md
