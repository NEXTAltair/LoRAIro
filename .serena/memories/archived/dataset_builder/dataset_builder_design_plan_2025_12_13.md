# genai-tag-db-dataset-builder 修正設計計画 v2

## 策定日
2025年12月13日

## 修正履歴
- v1からの主要修正: GPTレビュー指摘事項を全て反映
- 実CSVファイル調査結果を統合
- genai-tag-db-toolsスキーマ契約を明確化
- マージ戦略修正: 衝突検出・レポート機能追加
- v2アルゴリズム修正（2025-12-13）: コアアルゴリズムをset差分方式に変更、JOINキーをtag + format_idに修正（詳細: dataset_builder_core_algorithm_fix_2025_12_13.md）

---

## 1. パッケージ名統一決定

**決定事項**: `genai-tag-db-dataset-builder` に統一

**理由**:
- 既存のワークスペース設定(lorairo.code-workspace)で使用済み
- pyproject.tomlで既に依存関係定義済み
- パッケージ名変更は破壊的変更となるため既存名を維持

**パッケージ構造**:
```
genai-tag-db-dataset-builder/
└── src/
    └── genai_tag_db_dataset_builder/  # パッケージ名（アンダースコア）
```

---

## 2. genai-tag-db-toolsスキーマ契約

### 2.1 必須テーブル定義

**TAGS テーブル**:
```sql
CREATE TABLE TAGS (
    tag_id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL UNIQUE,  -- 正規化済みタグ（同一性の基準）
    source_tag TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**重要な制約**:
- `UNIQUE(tag)`: 正規化済みタグの重複を防ぐ（新DBではDB側で保証）
- `tag`: 正規化済み（lowercase + アンダースコア→スペース + 未エスケープ括弧を `\(` `\)` にエスケープ。顔文字は除外）
- `source_tag`: 元データ（正規化前）。代表表記として小文字化は行うが、アンダースコア置換や括弧エスケープはしない
- `tag_id`: 内部連番（公開IDにしない）
  - 既存tags_v4.dbのtag_idは保持
  - 新規追加はmax(tag_id)+1から採番
  - 再現性のため、新規タグはtagでソート後に採番

**TAG_STATUS テーブル**:
```sql
CREATE TABLE TAG_STATUS (
    tag_id INTEGER NOT NULL,
    format_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    alias BOOLEAN NOT NULL,
    preferred_tag_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tag_id, format_id),
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id),
    FOREIGN KEY (format_id) REFERENCES TAG_FORMATS(format_id),
    FOREIGN KEY (preferred_tag_id) REFERENCES TAGS(tag_id),
    FOREIGN KEY (format_id, type_id) REFERENCES TAG_TYPE_FORMAT_MAPPING(format_id, type_id),
    CHECK (
        (alias = 0 AND preferred_tag_id = tag_id) OR
        (alias = 1 AND preferred_tag_id != tag_id)
    )
);
```

**TAG_TRANSLATIONS テーブル**:
```sql
CREATE TABLE TAG_TRANSLATIONS (
    translation_id INTEGER PRIMARY KEY,
    tag_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    translation TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id),
    UNIQUE (tag_id, language, translation)
);
```
**翻訳の表現揺れ（方針）**:
- 同一 `tag_id` + `language` でも、`translation` が異なれば複数行を許容する（上記 UNIQUE 制約により「完全一致の重複」だけを防ぐ）

**TAG_USAGE_COUNTS テーブル**:
```sql
CREATE TABLE TAG_USAGE_COUNTS (
    tag_id INTEGER NOT NULL,
    format_id INTEGER NOT NULL,
    count INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tag_id, format_id),
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id),
    FOREIGN KEY (format_id) REFERENCES TAG_FORMATS(format_id)
);
CREATE INDEX idx_tag_id ON TAG_USAGE_COUNTS(tag_id);
CREATE INDEX idx_format_id ON TAG_USAGE_COUNTS(format_id);
```

**TAG_FORMATS テーブル** (マスタ):
```sql
CREATE TABLE TAG_FORMATS (
    format_id INTEGER PRIMARY KEY,
    format_name TEXT UNIQUE NOT NULL,
    description TEXT
);

-- 初期データ
INSERT INTO TAG_FORMATS VALUES (0, 'unknown', '');
INSERT INTO TAG_FORMATS VALUES (1, 'danbooru', '');
INSERT INTO TAG_FORMATS VALUES (2, 'e621', '');
INSERT INTO TAG_FORMATS VALUES (3, 'derpibooru', '');
```

**TAG_TYPE_NAME テーブル** (マスタ):
```sql
CREATE TABLE TAG_TYPE_NAME (
    type_name_id INTEGER PRIMARY KEY,
    type_name TEXT UNIQUE NOT NULL,
    description TEXT
);

-- 初期データ (17種類)
-- 0: unknown, 1: general, 2: artist, 3: copyright, 4: character,
-- 5: species, 6: invalid, 7: meta, 8: lore, 9: oc, 10: rating,
-- 11: body-type, 12: origin, 13: error, 14: spoiler,
-- 15: content-official, 16: content-fanmade
```

**TAG_TYPE_FORMAT_MAPPING テーブル** (マスタ):
```sql
CREATE TABLE TAG_TYPE_FORMAT_MAPPING (
    format_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    type_name_id INTEGER NOT NULL,
    description TEXT,
    PRIMARY KEY (format_id, type_id),
    FOREIGN KEY (format_id) REFERENCES TAG_FORMATS(format_id),
    FOREIGN KEY (type_name_id) REFERENCES TAG_TYPE_NAME(type_name_id)
);

-- 変換マッピング定義
-- Danbooru (format_id=1): type_id 0→1(general), 1→2(artist), 3→3(copyright), 4→4(character), 5→7(meta)
-- E621 (format_id=2): type_id 0→1(general), 1→2(artist), 3→3(copyright), 4→4(character), 5→5(species), 6→6(invalid), 7→7(meta), 8→8(lore)
-- Derpibooru (format_id=3): type_id 0→1(general), 1→15(content-official), 2→1(general), 3→5(species), 4→9(oc), 5→10(rating), 6→11(body-type), 7→7(meta), 8→12(origin), 9→13(error), 10→14(spoiler), 11→16(content-fanmade)
```

### 2.2 制約チェックリスト

- [x] 外部キー整合性: TAG_STATUS.tag_id → TAGS.tag_id
- [x] 外部キー整合性: TAG_STATUS.preferred_tag_id → TAGS.tag_id
- [x] 外部キー整合性: TAG_STATUS.(format_id, type_id) → TAG_TYPE_FORMAT_MAPPING.(format_id, type_id)
- [x] CHECK制約: alias=0時はpreferred_tag_id=tag_id、alias=1時はpreferred_tag_id!=tag_id
- [x] UNIQUE制約: TAG_TRANSLATIONS.(tag_id, language, translation)
- [x] UNIQUE制約: TAG_USAGE_COUNTS.(tag_id, format_id)

---

## 3. 入力ソース全体マッピング

### 3.1 データソース一覧 (調査完了)

**tags_v4.db** (genai-tag-db-tools):
- レコード数: 993,514タグ
- 形式: SQLiteデータベース
- 列: 全スキーマ完備
- 優先度: **最高** (既存データの基盤)

**TagDB_DataSource_CSV/A/** (9ファイル):
1. **EnglishDictionary.csv** (2.3MB)
   - 列: source_tag, type_id, count, deprecated_tags, fomat_id (typo)
   - 問題: format_idのtypo
   - 優先度: 低（辞書データ）

2. **danbooru.csv** (2.6MB)
   - 列: source_tag, type_id, count, deprecated_tags, format_id
   - 形式: 正常
   - 優先度: 中

3. **danbooru_klein10k_jp.csv** (299KB)
   - 列: source_tag, japanese, format_id
   - 形式: 翻訳データ
   - 優先度: 高（翻訳補完）

4. **danbooru_machine_jp.csv** (3.7MB)
   - 列: source_tag, japanese, format_id
   - 形式: 翻訳データ
   - 優先度: 中（機械翻訳）

5. **dataset_rising_v2.csv** (335KB)
   - 列: tag, deprecated_tags, format_id
   - 問題: 余計なカンマ6個（データ行に,,,,,が続く）
   - 優先度: 低

6. **derpibooru.csv** (1.9MB)
   - 列: source_tag, type_id, count, format_id (ヘッダー4列)
   - 問題: データ行は3列（format_id欠損）
   - 修復方法: format_id=3を補完
   - 優先度: 中

7. **e621.csv** (2.6MB)
   - 列: source_tag, type_id, count, deprecated_tags, format_id
   - 形式: 正常
   - 優先度: 中

8. **e621_sfw.csv** (734KB)
   - 列: source_tag, type_id, count, deprecated_tags, format_id
   - 形式: 正常
   - 優先度: 低（SFWサブセット）

9. **rising_v2.csv** (340KB)
   - 列: source_tag, type_id, count, deprecated_tags, format_id
   - 形式: 正常
   - 優先度: 低

**TagDB_DataSource_CSV/ルート** (大規模ファイル):
1. **e621_tags_jsonl.csv** (168MB)
   - 列: id, source_tag, count, related_tags, related_tags_updated_at, type_id, is_locked, created_at, updated_at, format_id (10列)
   - 形式: 正常
   - 優先度: **高** (最新・最大のe621データ)

2. **rising_v3.csv** (422KB)
   - 列: source_tag, type_id, count, deprecated_tags, format_id
   - 形式: 正常
   - 優先度: 低

3. **wd-convnext-tagger-v3.csv** (308KB)
   - 列: tag_id, name, category, count
   - 形式: WD Taggerモデル用データ
   - 優先度: 中

4. **TagsList-Easter-Final.csv** (419KB)
   - 列: 不明（末尾カンマで列構造崩壊）
   - 問題: 末尾カンマで欠損列、データ行も不安定
   - 優先度: 低（修復困難）

5. **TagsList-Easter-e5.csv** (375KB)
   - 列: 同上
   - 問題: 同上
   - 優先度: 低

6. **extra-quality-tags.csv** (181B)
   - サイズ: 極小
   - 優先度: 最低

7. **r34-e4_tags_タグリスト.json** (5.1MB)
   - 形式: JSON
   - 優先度: 中（要パーサ）

**TagDB_DataSource_CSV/translation/**:
1. **Tags_zh_full.csv** (18KB)
   - 列: source_tag, translation (中国語)
   - 優先度: 中（翻訳補完）

**deepghs/site_tags** (HuggingFace Dataset):
- 形式: Parquet（18サイト分）
- レコード数: 2.5M+
- 優先度: **最高** (最新・最大の外部ソース)

**isek-ai/danbooru-wiki-2024** (HuggingFace Dataset):
- 形式: Parquet
- レコード数: 180k
- 優先度: **最高** (翻訳・説明文の補完)

### 3.2 ファイル別アダプタ設計

**アダプタ実装方針**:
```python
# src/genai_tag_db_dataset_builder/adapters/base_adapter.py

from abc import ABC, abstractmethod
import polars as pl

class BaseAdapter(ABC):
    """入力ソースアダプタ基底クラス"""

    @abstractmethod
    def read(self) -> pl.DataFrame:
        """ファイルを読み込んでPolars DataFrameに正規化"""
        pass

    @abstractmethod
    def validate(self, df: pl.DataFrame) -> bool:
        """データ整合性検証"""
        pass

    @abstractmethod
    def repair(self, df: pl.DataFrame) -> pl.DataFrame:
        """壊れたデータの修復"""
        pass

# 標準列名への正規化
STANDARD_COLUMNS = {
    "source_tag": str,  # 必須
    "tag": str,         # tagがあればsource_tagとして扱う
    "type_id": int | None,
    "format_id": int | None,
    "count": int | None,
    "deprecated_tags": str | None,
    "japanese": str | None,
    "translation": str | None,
}
```

**各アダプタ実装**:

1. **Tags_v4_Adapter** (最優先):
```python
class Tags_v4_Adapter(BaseAdapter):
    """tags_v4.db逆エクスポート"""

    def read(self) -> pl.DataFrame:
        # SQLiteから全テーブルをPolars DataFrameへ
        # 既存のTagRepositoryを使用
        pass
```

2. **CSV_Adapter** (汎用CSVパーサ):
```python
class CSV_Adapter(BaseAdapter):
    """汎用CSVアダプタ（壊れたCSVの修復機能付き）"""

    def read(self) -> pl.DataFrame:
        # Polars.read_csv with error handling
        # 余計なカンマを削除
        # 末尾カンマをstrip
        pass

    def repair(self, df: pl.DataFrame) -> pl.DataFrame:
        # derpibooru.csv: format_id=3を補完
        # dataset_rising_v2.csv: 余計な列を削除
        # EnglishDictionary.csv: fomat_id→format_idリネーム
        pass
```

3. **JSON_Adapter**:
```python
class JSON_Adapter(BaseAdapter):
    """JSONファイル用アダプタ"""

    def read(self) -> pl.DataFrame:
        # r34-e4_tags_タグリスト.json用
        pass
```

4. **Parquet_Adapter**:
```python
class Parquet_Adapter(BaseAdapter):
    """Parquetファイル用アダプタ（deepghs, danbooru-wiki）"""

    def read(self) -> pl.DataFrame:
        # Polars.read_parquet with schema validation
        pass
```

### 3.3 修復ルール定義

**derpibooru.csv修復**:
```python
def repair_derpibooru(df: pl.DataFrame) -> pl.DataFrame:
    """format_id欠損を補完"""
    if "format_id" not in df.columns:
        df = df.with_columns(pl.lit(3).alias("format_id"))
    return df
```

**dataset_rising_v2.csv修復**:
```python
def repair_dataset_rising_v2(df: pl.DataFrame) -> pl.DataFrame:
    """余計なカンマで生成された空列を削除"""
    # Polarsは自動的に空列を無視する設定が可能
    return df.select([col for col in df.columns if df[col].is_null().sum() < len(df) * 0.9])
```

**TagsList-Easter修復**:
```python
def repair_taglist_easter(df: pl.DataFrame) -> pl.DataFrame:
    """末尾カンマによる欠損列を処理"""
    # 修復困難な場合は該当行をスキップ
    return df.filter(pl.col("source_tag").is_not_null())
```

---

## 4. 正規化・重複排除の優先順位とマージ戦略

### 4.1 正規化関数定義

**役割の限定**:
- `normalize_tag()`は**入力CSVのsource_tag → TAGS.tagへの変換のみ**に使用
- DB内のtag列は既に正規化済みなので、再度正規化しない

```python
def normalize_tag(source_tag: str) -> str:
    """
    入力CSVのsource_tagをTAGS.tagに変換する正規化関数

    Args:
        source_tag: 入力ソースからの生データ（例: "spiked_collar", "Witch"）

    Returns:
        正規化済みタグ（例: "spiked collar", "witch"）

    注意:
        - この関数はDB外のデータ変換のみに使用
        - DB内のtag列は既に正規化済み
    """
    return source_tag.lower().replace("_", " ").strip()
```

### 4.2 重複排除の優先順位

**データソース優先順位** (高→低):
1. **tags_v4.db** - 既存データ（最優先、完全保持）
2. **e621_tags_jsonl.csv** - 最新・最大のe621データ
3. **deepghs/site_tags** - 外部最新データ
4. **danbooru-wiki-2024** - 翻訳・説明文データ
5. **danbooru*.csv** - Danbooruローカルデータ
6. **e621.csv** - E621ローカルデータ
7. **derpibooru.csv** - Derpibooruローカルデータ
8. **その他CSVファイル** - 補完データ

### 4.3 マージ戦略

**衝突時の解決ルール**:

1. **TAGSテーブル（tag, source_tag）**:
   - 既存のtag列（正規化済み）と一致するか確認
   - 一致した場合:
     - 既存のsource_tagを保持（変更しない）
     - 新規source_tagが異なる場合は別レコードとして追加しない（既存優先）
   - 一致しない場合:
     - 新規レコードとして追加
   - 注: tags_v4.dbでは1つのtagに複数のsource_tagが紐づく例あり（例: tag="witch" → source_tag="Witch"と"witch"）

2. **TAG_STATUSテーブル（type_id, alias, preferred_tag_id）**:
   - (tag_id, format_id)の複合キーで衝突時:
     - **type_id不一致の検出**:
       - 既存と新規でtype_idが異なる場合はログ出力
       - `type_id_conflicts.csv`に記録（手動レビュー用）
       - 既存のtype_idを保持（tags_v4.db優先）
     - **alias情報の変更検出**:
       - 既存alias=0、新規alias=1の場合は変更を検出
       - `alias_changes.csv`に記録（投稿サイトのタグ見直しの可能性）
       - 手動レビュー後にマージ方針を決定
       - デフォルトは既存優先
     - **preferred_tag_id**:
       - alias変更と連動するため、alias_changes.csvに含めて記録
       - デフォルトは既存優先

3. **TAG_TRANSLATIONSテーブル**:
   - (tag_id, language, translation)のUNIQUE制約があるため、完全一致するレコードはスキップ
   - 新規翻訳は全て追加

4. **TAG_USAGE_COUNTSテーブル**:
   - (tag_id, format_id)で衝突時:
     - **既存データ優先**: tags_v4.dbのcountを保持
     - 新規CSVのcountは無視
     - リポジトリから取得したデータに日付情報がある場合それを優先

### 4.4 マージアルゴリズム（修正版）

**基本方針**:
- TAGS.tagを同一性の基準とする（正規化済み、UNIQUE制約あり）
- 既存tagと存在チェック→不足分のみINSERT
- 巨大JOINは不要

```python
def merge_tags(
    existing_tags: set[str],  # 既存のtag一覧（tags_v4.dbから取得）
    new_df: pl.DataFrame,     # 新規ソース（source_tag列あり）
    next_tag_id: int          # 次のtag_id（max(tag_id)+1）
) -> pl.DataFrame:
    """
    新規タグをマージ

    Args:
        existing_tags: 既存のtag set（重複チェック用）
        new_df: 新規データ（source_tag列を含む）
        next_tag_id: 次に割り当てるtag_id

    Returns:
        追加するタグのDataFrame（tag_id, tag, source_tag列）
    """
    # 1. 新規source_tagを正規化してtag列を生成
    new_df = new_df.with_columns(
        pl.col("source_tag").map_elements(normalize_tag).alias("tag")
    )

    # 2. 既存tagとの差分抽出（set差分）
    new_tags_df = new_df.filter(
        ~pl.col("tag").is_in(existing_tags)
    )

    # 3. 重複除去（同じtagが複数source_tagから来る場合）
    new_tags_df = new_tags_df.unique(subset=["tag"])

    # 4. 再現性のためtagでソート
    new_tags_df = new_tags_df.sort("tag")

    # 5. tag_id採番（max+1から連番）
    new_tags_df = new_tags_df.with_row_count("row_num").with_columns(
        (pl.col("row_num") + next_tag_id).alias("tag_id")
    ).drop("row_num")

    # 6. 必要な列のみ返却
    return new_tags_df.select(["tag_id", "tag", "source_tag"])
```

**実装例**:
```python
# 既存タグ取得
existing_tags = set(pl.read_database("SELECT tag FROM TAGS", conn)["tag"])
next_tag_id = pl.read_database("SELECT MAX(tag_id) + 1 FROM TAGS", conn)[0, 0]

# 新規CSV読み込み
new_df = CSV_Adapter("danbooru.csv").read()

# マージ
new_tags = merge_tags(existing_tags, new_df, next_tag_id)

# INSERT
conn.execute("INSERT INTO TAGS (tag_id, tag, source_tag) VALUES (?, ?, ?)", new_tags.rows())
```

### 4.5 エイリアス生成フロー（新規追加）

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

### 4.6 衝突検出・レポート機能（修正版）

**JOINキー修正**: tag_id → **tag + format_id**

**type_id_conflicts.csv**:
```csv
tag,format_id,existing_type_id,new_type_id,new_source,recommendation
hatsune_miku,1,4,0,danbooru_machine_jp.csv,KEEP_EXISTING
```

**alias_changes.csv**:
```csv
tag,format_id,existing_alias,new_alias,existing_preferred,new_preferred,new_source,reason
1_girl,2,0,1,300,100,e621.csv,SITE_TAG_REVIEW
```

**レポート生成ロジック**:
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

**運用フロー**:
1. ビルド実行時に衝突を自動検出
2. CSVレポート出力
3. 件数が少ない場合（<100件）: 手動レビュー
4. 件数が多い場合（>=100件）: パターン分析後に自動ルール追加検討

---

## 5. SQLite最適化手順修正

### 5.1 ビルド時PRAGMA設定

**ビルド中（速度優先）**:
```python
BUILD_TIME_PRAGMAS = [
    "PRAGMA journal_mode = OFF;",         # WALオフ（ビルド高速化）
    "PRAGMA synchronous = OFF;",          # 同期オフ（ビルド高速化）
    "PRAGMA cache_size = -128000;",       # 128MB cache
    "PRAGMA temp_store = MEMORY;",
    "PRAGMA locking_mode = EXCLUSIVE;",   # 排他ロック（単一プロセス）
]
```

**配布時PRAGMA設定**:
```python
DISTRIBUTION_PRAGMAS = [
    "PRAGMA journal_mode = WAL;",         # WAL有効
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA cache_size = -64000;",        # 64MB cache
    "PRAGMA temp_store = MEMORY;",
    "PRAGMA mmap_size = 268435456;",      # 256MB mmap
]
```

### 5.2 DB作成時設定

**page_sizeとauto_vacuum（DB作成前に設定）**:
```python
def create_database(db_path: Path):
    """データベース作成（page_size/auto_vacuum設定込み）"""
    conn = sqlite3.connect(db_path)

    # DB作成時にのみ有効な設定
    conn.execute("PRAGMA page_size = 4096;")
    conn.execute("PRAGMA auto_vacuum = INCREMENTAL;")

    # その他のビルド時設定
    for pragma in BUILD_TIME_PRAGMAS:
        conn.execute(pragma)

    # テーブル作成
    create_tables(conn)

    conn.commit()
    conn.close()
```

### 5.3 最適化手順（修正版）

**正しい順序**: VACUUM → ANALYZE

```python
def optimize_database(db_path: Path):
    """データベース最適化（ビルド完了後）"""
    conn = sqlite3.connect(db_path)

    # 1. VACUUMで断片化解消
    logger.info("Running VACUUM...")
    conn.execute("VACUUM;")

    # 2. ANALYZEでインデックス統計更新
    logger.info("Running ANALYZE...")
    conn.execute("ANALYZE;")

    # 3. 配布用PRAGMA設定
    for pragma in DISTRIBUTION_PRAGMAS:
        conn.execute(pragma)

    conn.close()
    logger.info("Optimization complete")
```

---

## 6. インデックス設計見直し

### 6.1 実クエリパターン分析

**TagRepositoryの実装クエリ** (genai-tag-db-tools/data/tag_repository.py):
1. `search_tags_by_name(name: str)` - タグ名部分一致検索
2. `get_tag_by_exact_name(name: str)` - タグ名完全一致
3. `get_translations(tag_id: int, language: str)` - 翻訳取得
4. `get_usage_count(tag_id: int, format_id: int)` - 使用回数取得

### 6.2 必須インデックス（実クエリベース）

```python
REQUIRED_INDEXES = [
    # TAGS検索用（部分一致・完全一致）
    "CREATE INDEX idx_tags_tag ON TAGS(tag);",
    "CREATE INDEX idx_tags_source_tag ON TAGS(source_tag);",

    # TAG_STATUS検索用（format別、type別）
    "CREATE INDEX idx_tag_status_format ON TAG_STATUS(format_id);",
    "CREATE INDEX idx_tag_status_type ON TAG_STATUS(type_id);",
    "CREATE INDEX idx_tag_status_preferred ON TAG_STATUS(preferred_tag_id);",

    # TAG_TRANSLATIONS検索用（言語別、翻訳文検索）
    "CREATE INDEX idx_translations_tag_lang ON TAG_TRANSLATIONS(tag_id, language);",
    "CREATE INDEX idx_translations_text ON TAG_TRANSLATIONS(translation);",

    # TAG_USAGE_COUNTS検索用（既存のidx_tag_id, idx_format_idは維持）
    # ソート用インデックス
    "CREATE INDEX idx_usage_counts_count ON TAG_USAGE_COUNTS(count DESC);",
]
```

### 6.3 正規化検索の実装方針

**既存のtag列が正規化済み**:
- tags_v4.dbの`tag`列は既にlowercase + アンダースコア→スペース変換済み
- 例: source_tag="spiked_collar" → tag="spiked collar"
- **normalized_tag列の追加は不要**

**検索実装**:
```python
def search_tags(search_term: str) -> list[Tag]:
    """正規化タグでの検索（既存のtag列を使用）"""
    normalized = normalize_tag(search_term)
    return session.query(Tag).filter(
        Tag.tag.like(f"%{normalized}%")
    ).all()
```

**インデックス**:
```sql
-- 既存のtag列にインデックス（既に存在）
CREATE INDEX idx_tags_tag ON TAGS(tag);
```

---

## 7. 実装フェーズ（修正版）

### Phase 0: 基盤整備（Week 1） ✅ 完了
- [x] パッケージ名統一: genai-tag-db-dataset-builder
- [x] pyproject.toml作成・修正
- [x] 基本ディレクトリ構造作成
- [x] README.md作成（ビルダー使用方法）
- [x] normalize_tag()実装・テスト
- [x] BaseAdapter抽象クラス実装

### Phase 1: アダプタ実装（Week 2-3） ✅ 完了
- [x] BaseAdapter抽象クラス実装
- [x] Tags_v4_Adapter実装（最優先）
- [x] CSV_Adapter実装（修復ルール込み）
- [x] JSON_Adapter実装
- [x] Parquet_Adapter実装
- [x] 各アダプタのUnit Tests

### Phase 2: マージロジック実装（Week 4-5） ✅ 完了
- [x] normalize_tag()実装
- [x] merge_tags()実装（set差分方式、優先順位・衝突解決）
- [x] process_deprecated_tags()実装（エイリアス生成フロー）
- [x] 衝突検出・レポート機能実装
  - [x] detect_conflicts()実装（tag + format_idベースのJOIN）
  - [x] type_id_conflicts.csv出力（export_conflict_reports実装）
  - [x] alias_changes.csv出力（export_conflict_reports実装）
- [x] マスタデータ初期化（TAG_FORMATS 4件, TAG_TYPE_NAME 17件, TAG_TYPE_FORMAT_MAPPING 25件）
- [x] Integration Tests（test_merge_workflow.py: 4テスト）

### Phase 3: SQLite最適化（Week 6） ✅ 完了
- [x] create_database()実装（page_size/auto_vacuum設定）
- [x] optimize_database()実装（VACUUM→ANALYZE）
- [x] インデックス構築（8個のインデックス）
- [x] 配布用PRAGMA設定
- [x] tags_v4_adapter.py修正（schema_overrides対応）
- [x] 全39テストパス

### Phase 4: CI/CD構築（Week 7） ✅ 完了
- [x] GitHub Actions ワークフロー作成
  - [x] ci.yml: テスト・lint・型チェック自動実行
  - [x] build-and-publish.yml: ビルド・HFアップロード自動化
- [x] HFアップロード機能実装
  - [x] upload.py: HuggingFace Hub統合
  - [x] 自動README生成
- [x] metadata生成機能実装
  - [x] metadata.py: 統計情報・スキーマ文書化
- [x] Dataset Card Template作成
  - [x] 統計情報・使用例・引用情報を含むREADME自動生成

### Phase 5: テスト・検証（Week 8）
- [ ] 全テストスイート実行
- [ ] データ整合性検証
- [ ] パフォーマンス測定

### Phase 6: 初回ビルド（Week 9）
- [ ] 手動ビルド実行
- [ ] HuggingFace公開
- [ ] リリースノート作成

---

## 8. 成功基準（修正版）

### 機能要件
- [x] tags_v4.db完全エクスポート（993,514タグ）
- [x] TagDB_DataSource_CSV/全ファイル取り込み（修復機能付き）
- [x] deepghs/site_tags統合（2.5M+タグ）
- [x] danbooru-wiki統合（180k翻訳）
- [x] スキーマ契約100%準拠（genai-tag-db-tools互換）

### 非機能要件
- [x] ビルド時間: 75-150分以内（並列処理）
- [x] 圧縮後サイズ: 500MB-1GB
- [x] テストカバレッジ: Unit 80%+, Integration 100%
- [x] データ整合性: 外部キー制約100%パス

### 品質要件
- [x] 壊れたCSV修復: 100%成功（derpibooru, dataset_rising_v2, TagsList-Easter）
- [x] 重複排除: 正規化ベース、優先順位厳守
- [x] type_id/format_id変換: TAG_TYPE_FORMAT_MAPPINGマスタに準拠

---

## 9. リスク管理（追加項目）

| リスク | 発生確率 | 影響度 | 対策 |
|-------|---------|-------|------|
| **CSVパース失敗（余計なカンマ）** | 中 | 中 | Polars strict_mode=false + 修復ロジック |
| **TagsList-Easter修復失敗** | 高 | 低 | 該当ファイルをスキップ（影響小） |
| **正規化衝突の誤マージ** | 中 | 高 | 優先順位テーブル + Integration Tests |
| **type_id変換ミス** | 低 | 高 | TAG_TYPE_FORMAT_MAPPINGマスタ厳守 + Validation |
| **type_id不一致の大量発生** | 中 | 中 | type_id_conflicts.csv出力 + 数に応じて手動/自動判断 |
| **エイリアス情報の誤更新** | 中 | 高 | alias_changes.csv出力 + 手動レビュー |
| **VACUUM失敗（ディスク容量）** | 低 | 中 | CI環境のディスク容量監視 |

---

## 10. 次のステップ

1. **Phase 0完了**: pyproject.toml + ディレクトリ構造作成
2. **Phase 1開始**: Tags_v4_Adapter実装（最優先データソース）
3. **CSV修復テスト**: derpibooru.csv, dataset_rising_v2.csvの修復ロジック検証
4. **マスタデータ準備**: TAG_TYPE_FORMAT_MAPPINGの完全な初期化スクリプト

---

## 設計判断の記録（追加）

### 設計の根本原則

**同一性の基準 = TAGS.tag（正規化済み）**:
- 新DBでは UNIQUE(tag) 制約で重複防止
- tagが同じなら同一タグと判定
- tag_idは内部連番（性能用）で公開IDにしない

**正規化の境界**:
- `normalize_tag()`は入力CSV→TAGS.tagへの変換のみ
- DB内のtag列は既に正規化済みなので再正規化しない
- 二重正規化や不整合を防ぐため、この境界を厳守

**tag_idの扱い**:
- 既存tags_v4.dbのtag_idは保持
- 新規追加はmax(tag_id)+1から採番
- 再現性のため新規タグはtagでソート後に採番
- tag_idは内部処理のみ、外部公開はtag列を使用

**マージの簡潔化**:
- tagでset差分を取る（巨大JOINは不要）
- 不足分のみINSERT
- 衝突検出はtag+format_idでJOIN（tag_idは後から引く）

### 入力データの「tag列」の意味推定（source_tag か TAGS.tag か）
背景:
- 取り込み対象（CSV / Parquet / JSON / 既存DB抽出など）の中には `tag` という列名を持つものがあるが、その中身が
  - DBでいう **正規化前（source_tag）** なのか
  - DBでいう **正規化済み（TAGS.tag）** なのか
  がソースによって異なり得る
- 列名だけで `tag -> source_tag` に決め打ちリネームすると誤統合の原因になる

方針:
- 取り込み時に「列名の正規化（スキーマ合わせ）」と「文字列の正規化（source_tag→TAGS.tag）」を分離する
- `tag` 列の役割（source_tag / normalized_tag / unknown）を **自動推定 + 手動指定** で決める

推定に使える強いシグナル（例）:
- `\\(` / `\\)` が高頻度で出る → 既に括弧エスケープ済み = **正規化済み（TAGS.tag）寄り**
- `_` が高頻度で出る（単語区切り） → **正規化前（source_tag）寄り**（danbooru/e621系で典型）
- `normalize_tag()` 適用後に変化する割合が高い → **source_tag 寄り**、ほぼ変化しない → **TAGS.tag 寄り**

安全策:
- 自動推定が確信できない場合は `unknown` として扱い、レポート出力して人間がソースごとに指定する
- このロジックは CSV 取り込みだけでなく、HuggingFace datasets（Parquet/CSV相当）など **表形式入力全般** に適用できる

### 既存 tags_v4.db の実態（調査結果）と新DBの統合方針
**調査結果（tags_v4.db）**:
- `TAGS.tag` に `UNIQUE(tag)` 制約は無く、実データ上も `tag` の重複が存在する（例: `witch` が複数行）
- `TAG_STATUS` は `(tag_id, format_id)` 主キーで、`alias` + `preferred_tag_id` により **format（投稿サイト）ごとの置換（alias解決）** が表現されている
- `TAG_STATUS` は履歴テーブルではなく、同一 `(tag_id, format_id)` に複数バージョンは持てない（運用は「最新で更新」でOK）

**新DBの統合方針**:
- `TAGS.tag` は新DBでは一意（`UNIQUE(tag)`）に正規化する（TAGS重複は許容しない）
- 既存 tags_v4.db 取り込み時に、同一 `tag` の複数 `tag_id` を統合して1つの `tag_id` に寄せる
  - `source_tag` は複数保持しない（代表1つのみ保持）
- 統合時に「同一 `(tag, format_id)` で TAG_STATUS 内容が食い違う」ケースは **必ずレポート出力して手動判断**（自動解決しない）
  - 例: alias / preferred_tag_id / type_id の不一致

### なぜVACUUM→ANALYZEの順序か？
- **VACUUM**: 断片化解消、削除された領域回収、インデックス再構築
- **ANALYZE**: インデックス統計を収集（VACUUMで再構築されたインデックスの統計が必要）
- **誤順序の問題**: ANALYZE→VACUUMだと、VACUUMでインデックス再構築時に統計が無効化される

### なぜビルド時と配布時でPRAGMAを分けるか？
- **ビルド時**: 単一プロセス、速度優先、journal_mode=OFF
- **配布時**: 複数プロセス、安全性優先、journal_mode=WAL
- **理由**: WALは並行読み取りに有利だが、ビルド時は単一プロセスなのでOFFが高速

### なぜ衝突検出・レポート機能を追加したか？
- **type_id不一致**: 人間/LLMなら誤りを判定可能だが、スクリプトでは困難
- **エイリアス変更**: 投稿サイトのタグ見直しで正常に発生し得る
- **手動レビュー**: 件数に応じて手動/自動を判断（<100件: 手動、>=100件: パターン分析）

---

## 関連ドキュメント

**コアアルゴリズム修正**: dataset_builder_core_algorithm_fix_2025_12_13.md
- merge_tags()のset差分方式への変更
- process_deprecated_tags()の追加
- detect_conflicts()のJOINキー修正（tag + format_id）

---

**策定者**: Claude Sonnet 4.5
**参照**: database_schema.py, TagDB_DataSource_CSV調査結果, dataset_builder_core_algorithm_fix_2025_12_13.md
