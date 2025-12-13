# タグデータベース統合 詳細実装計画 v2.3

## 計画策定日
2025年12月13日（v2.3: SQLite配布確定版）

## 配布物の確定（重要）

### HuggingFace配布成果物

**ファイル構成:**
```
NEXTAltair/genai-unified-tag-dataset/
├── tags_unified.db.zst         # 圧縮SQLite（zstd圧縮）
├── tags_unified.db.sha256      # SHA256ハッシュ値
├── build_metadata.json         # ビルド情報（後述）
└── README.md                   # Dataset Card
```

**ファイル仕様:**

| 項目 | 仕様 | 備考 |
|------|------|------|
| **ファイル名** | `tags_unified.db.zst` | zstd圧縮SQLite |
| **圧縮前サイズ** | 1-2GB（推定） | 全件統合後、インデックス込み |
| **圧縮後サイズ** | 500MB-1GB（推定） | zstd圧縮率: 約50% |
| **レコード数** | 1.5M-2M件（推定） | 重複排除・正規化後 |
| **圧縮形式** | zstd level 19 | 高圧縮率、展開高速 |
| **ハッシュアルゴリズム** | SHA256 | ファイル整合性検証 |

**build_metadata.json 仕様:**
```json
{
  "db_version": "1.0.0",
  "schema_version": "4.0",
  "generated_at": "2025-12-13T12:00:00Z",
  "source_versions": {
    "genai_tag_db_tools": {
      "version": "tags_v4.db",
      "records": 993514,
      "sha256": "..."
    },
    "deepghs_site_tags": {
      "commit": "abc123...",
      "records_processed": 2500000,
      "records_added": 800000,
      "records_duplicate": 1700000
    },
    "danbooru_wiki_2024": {
      "records": 180839,
      "records_enriched": 150000
    }
  },
  "statistics": {
    "total_tags": 1800000,
    "tags_with_translations": 500000,
    "tags_with_usage_counts": 1500000,
    "total_translations": 800000
  },
  "compression": {
    "algorithm": "zstd",
    "level": 19,
    "uncompressed_size_bytes": 1500000000,
    "compressed_size_bytes": 750000000
  }
}
```

### データ規模の整合性説明

**統合プロセス:**
```
1. genai-tag-db-tools (tags_v4.db):
   - 入力: 993,514タグ
   - 採用: 993,514タグ（ベースデータ、全件保持）

2. deepghs/site_tags:
   - 入力: 2,500,000+タグ（18サイト合計）
   - 重複排除: 約1,700,000タグ（既存と重複、normalized tag比較）
   - 新規追加: 約800,000タグ
   - 処理: 
     * サイトフォルダ別にParquet読込
     * normalize_tag()で正規化（小文字化、アンダースコア除去）
     * genai_coreと突合、重複はusage_count加算のみ

3. danbooru-wiki-2024:
   - 入力: 180,839エントリ
   - 新規タグ追加: 約5,000タグ（既存に存在しない）
   - 翻訳補完: 約150,000タグ（既存タグへの翻訳追加）

4. 最終統合結果:
   - 総タグ数: 約1,800,000件（993k + 800k + 5k）
   - SQLiteサイズ（展開後）: 1-2GB
   - 圧縮後: 500MB-1GB
```

**重複判定ロジック:**
```python
def normalize_tag(tag: str) -> str:
    """タグ正規化（重複判定用）"""
    return tag.lower().replace("_", " ").replace("-", " ").strip()

def is_duplicate(new_tag: str, existing_tags_normalized: set) -> bool:
    """重複判定"""
    return normalize_tag(new_tag) in existing_tags_normalized
```

## 既存実装の分析結果

### データ処理フロー（genai-tag-db-tools）

#### 処理アーキテクチャ
```
CSV/Parquet → Polars DataFrame → TagRegister → TagRepository → SQLite
                    ↓
              TagCleaner.clean_format()
                    ↓
         normalize_tags() → bulk_insert_tags() → usage_counts/translations
```

#### 主要コンポーネント

**1. TagDataImporter** (`services/import_data.py`)
- 役割: 外部ファイル（CSV/Parquet）読み込みとDB登録の統合管理
- 処理フロー:
  ```python
  read_csv()/load_hf_dataset()  # Polars DataFrameで読込
  → configure_import()          # カラム補完・型変換
  → import_data()               # TagRegisterに委譲
  ```
- Qt Signal統合: `process_started`, `progress_updated`, `error_occurred`

**2. TagRegister** (`services/tag_register.py`)
- 役割: タグ登録のビジネスロジック
- 主要メソッド:
  ```python
  normalize_tags(df)               # source_tag/tag補完・クリーニング
  → insert_tags_and_attach_id(df)  # bulk_insert + tag_id付与
  → update_usage_counts()           # TAG_USAGE_COUNTS登録
  → update_translations()           # TAG_TRANSLATIONS登録
  → update_deprecated_tags()        # エイリアス登録
  ```

**3. TagRepository** (`data/tag_repository.py`)
- 役割: データベース直接アクセス（Repository Pattern）
- 使用ツール: SQLAlchemy ORM
- 主要メソッド:
  - `bulk_insert_tags()`: 新規タグ一括挿入（既存はスキップ）
  - `_fetch_existing_tags_as_map()`: tag → tag_id マッピング取得
  - `update_usage_count()`: usage_count UPSERT
  - `add_or_update_translation()`: 翻訳追加・更新
  - `update_tag_status()`: TAG_STATUS UPSERT

**4. TagCleaner** (`utils/cleanup_str.py`)
- 役割: タグ文字列の正規化（@cacheデコレータ使用）
- 主要メソッド:
  ```python
  @staticmethod
  clean_format(text: str) -> str  # 改行・空白除去、カンマ正規化
  ```
- 使用場所:
  - `ExistingFileReader._read_annotations()` (LoRAIro側)
  - `TagRegister.normalize_tags()`

#### 既存実装例の分析

**hf_to_sqlite_tag_transfer.py** (tools/)
```python
# HuggingFace Parquet → SQLite変換の実例
- データソース: "hf://datasets/p1atdev/danbooru-ja-tag-pair-20241015"
- 処理パターン:
  1. pl.read_parquet() でDataFrame読込
  2. 既存タグをDictにキャッシュ（高速化）
  3. 新規タグのみ bulk insert
  4. 翻訳を一括挿入（INSERT OR IGNORE）
  5. TAG_STATUSを一括UPSERT
- format_id: 1（Danbooru固定）
- type_idマッピング:
  {
    "general": 0,
    "artist": 1,
    "copyright": 3,
    "character": 4,
    "meta": 5
  }
```

**migrate_v3_to_v4.py** (tools/)
```python
# バージョン間マイグレーションの教訓
- マスターテーブル（TAG_FORMATS, TAG_TYPE_NAME）: マージ処理
- データテーブル: 全件コピー
- TAG_STATUS: alias整合性検証
  - alias=true → preferred_tag_id != tag_id
  - alias=false → preferred_tag_id == tag_id
- バックアップ作成: タイムスタンプ付き
- 件数検証: 移行前後の比較
```

### 既存データの扱い

#### データソース状況
1. **tags_v4.db** (215MB, 993,514タグ)
   - 状態: ワークスペース内に存在（local_packages/genai-tag-db-tools/src/genai_tag_db_tools/data/）
   - 完全性: 100%保持確定
   
2. **元となったCSVファイル**
   - 状態: ワークスペース外（ユーザー保有）
   - 問題: ライセンス情報が不明（README記載のソースと対応が不明確）
   - 要件: 全データを統合データセットに含めたい

#### データ保持戦略の選択肢

**Option A: tags_v4.dbから逆エクスポート（推奨）**
```python
メリット:
- ライセンス問題を回避（DBから抽出したデータ）
- 実装が単純（既存DB → Parquet変換のみ）
- データ完全性保証（993,514タグ全て）

デメリット:
- 元のデータソースメタデータ（どのCSVから来たか）が失われる
- Dataset Cardに「genai-tag-db-toolsの既存データベースから抽出」と記載

実装:
def export_tags_v4_to_parquet(db_path: Path, output_path: Path):
    conn = sqlite3.connect(db_path)
    
    # TAGSテーブル全件エクスポート
    tags_df = pl.read_database("SELECT * FROM TAGS", conn)
    
    # TAG_STATUSと結合（format_id, type_id情報付与）
    status_df = pl.read_database("SELECT * FROM TAG_STATUS", conn)
    merged_df = tags_df.join(status_df, on="tag_id", how="left")
    
    # TAG_USAGE_COUNTSから使用回数集計
    usage_df = pl.read_database("""
        SELECT tag_id, SUM(count) as total_count
        FROM TAG_USAGE_COUNTS
        GROUP BY tag_id
    """, conn)
    final_df = merged_df.join(usage_df, on="tag_id", how="left")
    
    # TAG_TRANSLATIONS統合（JSON化）
    translations = pl.read_database("""
        SELECT tag_id,
               json_group_object(language, translation) as translations_json
        FROM TAG_TRANSLATIONS
        GROUP BY tag_id
    """, conn)
    final_df = final_df.join(translations, on="tag_id", how="left")
    
    final_df.write_parquet(output_path)
    conn.close()
```

**Option B: 元CSVファイルを使用（ライセンス整理必要）**
```python
メリット:
- データソースの出自が明確
- Dataset Cardに詳細なクレジット記載可能

デメリット:
- ライセンス調査・整理が必要（高リスク）
- CSVとDB間で差分がある可能性（DB側が最新）
- 実装が複雑（8ソース個別処理）

リスク:
- ライセンス不明なソースが含まれる可能性
- CC-BY-SA 4.0と互換性がない場合、除外必要
- 法的問題発生リスク
```

**Option C: ハイブリッド（DB + 新規ソースのみCSV使用）**
```python
方針:
1. tags_v4.dbから全データをエクスポート（ベース）
2. deepghs/site_tags（CC-BY-4.0）を追加
3. isek-ai/danbooru-wiki-2024（CC-BY-SA 4.0）を追加
4. 元CSVは使用せず、DB抽出データのみ

ライセンス表記:
- Dataset Card: "Derived from genai-tag-db-tools database (aggregated sources)"
- 元のCSVソースは「間接的に含まれる」として包括的にクレジット
- 直接的なデータソース: tags_v4.db, deepghs, danbooru-wiki
```

#### 推奨方針: Option A（DB逆エクスポート）

理由:
1. **ライセンスリスク最小化**: DB抽出データなら二次的派生物として扱える
2. **実装容易性**: 単一ソース（tags_v4.db）からの変換のみ
3. **データ完全性**: 993,514タグ全て保持保証
4. **法的安全性**: 「データベースから抽出」は事実ベース記載

Dataset Card記載例:
```markdown
## Data Sources

This dataset is derived from the following sources:

### Primary Source
- **genai-tag-db-tools database** (tags_v4.db)
  - 993,514 tags aggregated from multiple community sources
  - License: Derived work, re-distributed under CC-BY-SA 4.0
  - Original sources (indirect):
    - DominikDoom/a1111-sd-webui-tagcomplete (CSV files)
    - applemango Japanese translations
    - としあき製作 Japanese translations
    - AngelBottomless/danbooru-2023-sqlite-fixed-7110548
    - hearmeneigh/e621-rising-v3-preliminary-data
    - p1atdev/danbooru-ja-tag-pair-20241015

### Additional Sources
- **deepghs/site_tags** (CC-BY-4.0)
  - 2.5M+ tags from 18 image hosting sites
  - Added: [number] new tags not in primary source
  
- **isek-ai/danbooru-wiki-2024** (CC-BY-SA 4.0)
  - 180,839 wiki entries with translations
  - Used for: Translation enrichment and tag metadata

## License
This derived dataset is distributed under **CC-BY-SA 4.0** to comply with the most restrictive source license.
```

## 前提条件の明確化

### HFデータセット実測仕様

#### deepghs/site_tags
- **総容量**: 5.23GB (圧縮Parquet)
- **展開後推定**: 15-20GB (Parquet読み込み時のArrowメモリ展開率: 約3-4倍)
- **レコード数**: 2.5百万+ タグ
- **サイト数**: 18プラットフォーム
- **ライセンス**: CC-BY-4.0（再配布可、表示義務あり）
- **更新頻度**: 不定期（2024年作成）
- **データ品質問題**: ArrowInvalidエラー報告あり（文字列→doubleの型不一致）

#### isek-ai/danbooru-wiki-2024
- **総容量**: 45.7MB (Parquet)
- **展開後推定**: 150-200MB
- **レコード数**: 180,839行
- **ライセンス**: CC-BY-SA 4.0（再配布可、継承義務あり）
- **更新頻度**: 不定期
- **フィルタリング**: 100回未満使用タグは除外済み

#### genai-tag-db-tools（現行）
- **データベースサイズ**: 215MB (SQLite tags_v4.db)
- **テーブル構成**:
  - TAGS (tag_id, tag, source_tag)
  - TAG_TRANSLATIONS (tag_id, language, translation)
  - TAG_STATUS (tag_id, format_id, type_id, alias, preferred_tag_id)
  - TAG_USAGE_COUNTS (tag_id, format_id, count)
  - TAG_FORMATS (format_id=1:danbooru, 2:e621, 3:derpibooru)
  - TAG_TYPE_NAME (17種類のタイプ定義)
  - TAG_TYPE_FORMAT_MAPPING (フォーマット別タイプマッピング)
- **インデックス**: 既存のB-tree index（tag, source_tag, format_id）

## スキーマ契約（DB成果物の仕様）

### 必須テーブル定義

**tags_unified.db スキーマ（SQLite 3.x）**

```sql
-- メタデータテーブル（新規追加）
CREATE TABLE METADATA (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- メタデータ必須キー
INSERT INTO METADATA (key, value, description) VALUES
('db_version', '1.0.0', 'Database schema version'),
('schema_version', '4.0', 'Compatible with tags_v4.db schema'),
('generated_at', '2025-12-13T12:00:00Z', 'Build timestamp (ISO 8601)'),
('total_tags', '1800000', 'Total number of tags'),
('source_genai_core_records', '993514', 'Records from genai-tag-db-tools'),
('source_deepghs_records', '800000', 'New records from deepghs/site_tags'),
('source_danbooru_wiki_records', '5000', 'New records from danbooru-wiki'),
('license', 'CC-BY-SA-4.0', 'Dataset license'),
('build_commit', 'abc123...', 'Git commit hash of build scripts');

-- 既存テーブル（tags_v4.db互換）
CREATE TABLE TAGS (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_tag TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE TAG_TRANSLATIONS (
    translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    translation TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id) ON DELETE CASCADE,
    UNIQUE(tag_id, language, translation)
);

CREATE TABLE TAG_FORMATS (
    format_id INTEGER PRIMARY KEY,
    format_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE TAG_TYPE_NAME (
    type_name_id INTEGER PRIMARY KEY,
    type_name TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE TAG_TYPE_FORMAT_MAPPING (
    format_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    type_name_id INTEGER NOT NULL,
    description TEXT,
    PRIMARY KEY (format_id, type_id),
    FOREIGN KEY (format_id) REFERENCES TAG_FORMATS(format_id),
    FOREIGN KEY (type_name_id) REFERENCES TAG_TYPE_NAME(type_name_id)
);

CREATE TABLE TAG_STATUS (
    tag_id INTEGER NOT NULL,
    format_id INTEGER NOT NULL,
    type_id INTEGER,
    alias INTEGER NOT NULL DEFAULT 0 CHECK(alias IN (0,1)),
    preferred_tag_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tag_id, format_id),
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id) ON DELETE CASCADE,
    FOREIGN KEY (format_id) REFERENCES TAG_FORMATS(format_id),
    FOREIGN KEY (preferred_tag_id) REFERENCES TAGS(tag_id),
    CHECK (
        (alias = 0 AND preferred_tag_id = tag_id) OR
        (alias = 1 AND preferred_tag_id != tag_id)
    )
);

CREATE TABLE TAG_USAGE_COUNTS (
    tag_id INTEGER NOT NULL,
    format_id INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tag_id, format_id),
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id) ON DELETE CASCADE,
    FOREIGN KEY (format_id) REFERENCES TAG_FORMATS(format_id)
);

-- 新規追加テーブル（拡張機能）
CREATE TABLE ALTERNATIVE_TRANSLATIONS (
    alt_translation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    translation TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'deepghs', 'danbooru-wiki'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tag_id) REFERENCES TAGS(tag_id) ON DELETE CASCADE,
    UNIQUE(tag_id, language, translation)
);

-- 必須インデックス（パフォーマンス保証）
CREATE INDEX idx_tags_tag ON TAGS(tag);
CREATE INDEX idx_tags_source_tag ON TAGS(source_tag);
CREATE INDEX idx_tags_normalized ON TAGS(LOWER(REPLACE(tag, '_', ' ')));
CREATE INDEX idx_tag_status_format ON TAG_STATUS(format_id, tag_id);
CREATE INDEX idx_tag_status_preferred ON TAG_STATUS(preferred_tag_id);
CREATE INDEX idx_translations_tag_lang ON TAG_TRANSLATIONS(tag_id, language);
CREATE INDEX idx_usage_counts_format ON TAG_USAGE_COUNTS(format_id, tag_id);
CREATE INDEX idx_usage_counts_count ON TAG_USAGE_COUNTS(count DESC);

-- SQLite最適化設定（ビルド時に実行）
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA cache_size = -64000;  -- 64MB cache
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;  -- 256MB mmap
PRAGMA page_size = 4096;

-- インデックス統計更新
ANALYZE;

-- データベース最適化
VACUUM;
```

### スキーマバージョニング仕様

**互換性マトリクス:**

| schema_version | 互換ツールバージョン | 変更内容 |
|----------------|---------------------|----------|
| 4.0 | genai-tag-db-tools >= 2.0.0 | METADATA, ALTERNATIVE_TRANSLATIONSテーブル追加 |
| 3.0 | genai-tag-db-tools 1.x | tags_v3.db互換 |

**バージョン検証ロジック:**
```python
def verify_schema_version(db_path: Path) -> bool:
    """スキーマバージョン検証"""
    conn = sqlite3.connect(db_path)
    try:
        # METADATAテーブルの存在確認
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='METADATA'"
        )
        if not cursor.fetchone():
            raise ValueError("METADATA table not found")
        
        # schema_version取得
        cursor = conn.execute("SELECT value FROM METADATA WHERE key='schema_version'")
        schema_version = cursor.fetchone()[0]
        
        # 互換性チェック
        if not schema_version.startswith('4.'):
            raise ValueError(f"Incompatible schema version: {schema_version}")
        
        # 必須テーブルの存在確認
        required_tables = [
            'TAGS', 'TAG_TRANSLATIONS', 'TAG_STATUS', 'TAG_USAGE_COUNTS',
            'TAG_FORMATS', 'TAG_TYPE_NAME', 'TAG_TYPE_FORMAT_MAPPING',
            'ALTERNATIVE_TRANSLATIONS'
        ]
        for table in required_tables:
            cursor = conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
            )
            if not cursor.fetchone():
                raise ValueError(f"Required table not found: {table}")
        
        return True
    finally:
        conn.close()
```

### ライセンス制約と再配布方針

#### 統合データセットのライセンス
- **NEXTAltair/genai-tag-db-unified**: CC-BY-SA 4.0を適用
  - 理由: CC-BY-SA 4.0（danbooru-wiki-2024）がCC-BY-4.0（site_tags）より制約が強いため
  - 継承義務: 派生物も同一ライセンス必須
  - 表示義務: データソースのクレジット明記

#### リポジトリ運用方針
- **genai-tag-db-toolsリポジトリ**: 処理ロジックのみ（MITライセンス維持）
- **HuggingFaceデータセット**: データ本体（CC-BY-SA 4.0）
- **分離理由**: コードとデータのライセンス混在を回避

---

## アーキテクチャ設計（修正版）

### 基本方針：完全オフライン設計

**設計原則:**
1. HFから事前構築済みSQLiteをダウンロード（初回のみ）
2. 以降は完全オフライン動作（ローカルSQLiteクエリのみ）
3. 更新は「丸ごと入れ替え＋バックアップ」方式
4. ストリーミング・オンライン取得機能は提供しない

**Layer 3（オンラインストリーミング）削除理由:**
- 完全オフライン前提と矛盾
- 実装・保守コストが高い割に使用頻度が低い
- データ完全性・整合性の管理が複雑化
- 初回セットアップ時に全データ取得で十分

#### 初回セットアップフロー（確定版）
```
1. ユーザー操作: `genai-tag-db-setup` コマンド実行

2. データ取得:
   a. HFからSQLite圧縮ファイルダウンロード
      - tags_unified.db.zst (500MB-1GB)
      - tags_unified.db.sha256
      - build_metadata.json
   
   b. SHA256整合性検証
      expected_hash = Path("tags_unified.db.sha256").read_text().strip()
      actual_hash = hashlib.sha256(zst_file.read_bytes()).hexdigest()
      if expected_hash != actual_hash:
          raise IntegrityError("Hash mismatch")
   
   c. zstd展開
      zstd -d tags_unified.db.zst -o tags_unified.db
      展開後サイズ: 1-2GB
   
   d. スキーマバージョン検証
      verify_schema_version(tags_unified.db)
   
   e. 既存DBバックアップ（存在する場合）
      mv ~/.cache/genai-tag-db-tools/tags.db \
         ~/.cache/genai-tag-db-tools/backups/tags_v{old_version}_{timestamp}.db
   
   f. アトミック配置
      mv tags_unified.db ~/.cache/genai-tag-db-tools/tags.db
   
   g. WALモード有効化確認
      sqlite3 tags.db "PRAGMA journal_mode=WAL;"

3. 所要時間:
   - ダウンロード: 5-10分（500MB-1GB @ 10Mbps）
   - 展開: 30秒-1分
   - 検証・配置: 10秒
   - 合計: 6-12分（初回のみ）

4. ディスク使用量:
   - 圧縮ファイル: 500MB-1GB（保持、次回更新用）
   - 展開DB: 1-2GB
   - バックアップ: 1-2GB（最大3世代）
   - 合計: 2.5-5GB（最大時）
```

## 取得/検証フロー仕様

### ダウンロード・検証実装

```python
# genai_tag_db_tools/scripts/setup_cache.py

import hashlib
import subprocess
from pathlib import Path
from datasets import load_dataset

class DatabaseSetup:
    """統合データベースのセットアップ"""
    
    # 固定値（ビルドごとに更新）
    EXPECTED_HASH = "a1b2c3d4e5f6..."  # 実際のハッシュはbuild_metadata.jsonから取得
    HF_REPO = "NEXTAltair/genai-unified-tag-dataset"
    CACHE_DIR = Path.home() / ".cache/genai-tag-db-tools"
    
    def __init__(self):
        self.cache_dir = self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def download_from_hf(self) -> Path:
        """HuggingFaceから圧縮DBダウンロード"""
        print("1/7: Downloading database from HuggingFace...")
        
        # HF Datasets APIで取得
        ds = load_dataset(
            self.HF_REPO,
            split="train",
            cache_dir=str(self.cache_dir / "hf_cache")
        )
        
        # ファイルパス取得
        zst_file = self.cache_dir / "hf_cache" / "tags_unified.db.zst"
        hash_file = self.cache_dir / "hf_cache" / "tags_unified.db.sha256"
        
        return zst_file, hash_file
    
    def verify_integrity(self, zst_file: Path, hash_file: Path) -> bool:
        """SHA256ハッシュ検証"""
        print("2/7: Verifying file integrity...")
        
        # 期待ハッシュ読込
        expected_hash = hash_file.read_text().strip()
        
        # 実際のハッシュ計算
        sha256 = hashlib.sha256()
        with open(zst_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        
        if expected_hash != actual_hash:
            raise ValueError(
                f"Hash mismatch!\n"
                f"  Expected: {expected_hash}\n"
                f"  Actual:   {actual_hash}\n"
                f"File may be corrupted. Please retry download."
            )
        
        print(f"  ✓ Hash verified: {expected_hash[:16]}...")
        return True
    
    def decompress_zstd(self, zst_file: Path) -> Path:
        """zstd展開"""
        print("3/7: Decompressing database...")
        
        output_file = self.cache_dir / "tags_unified.db"
        
        # zstdコマンド実行
        subprocess.run(
            ["zstd", "-d", str(zst_file), "-o", str(output_file), "-f"],
            check=True,
            capture_output=True
        )
        
        print(f"  ✓ Decompressed: {output_file.stat().st_size / 1024 / 1024:.1f} MB")
        return output_file
    
    def verify_schema(self, db_file: Path) -> bool:
        """スキーマバージョン検証"""
        print("4/7: Verifying schema version...")
        
        import sqlite3
        conn = sqlite3.connect(db_file)
        try:
            # schema_version取得
            cursor = conn.execute("SELECT value FROM METADATA WHERE key='schema_version'")
            schema_version = cursor.fetchone()[0]
            
            # 互換性チェック
            if not schema_version.startswith('4.'):
                raise ValueError(f"Incompatible schema version: {schema_version}")
            
            print(f"  ✓ Schema version: {schema_version}")
            return True
        finally:
            conn.close()
    
    def backup_existing_db(self) -> None:
        """既存DBバックアップ"""
        print("5/7: Backing up existing database...")
        
        existing_db = self.cache_dir / "tags.db"
        if not existing_db.exists():
            print("  ℹ No existing database found. Skipping backup.")
            return
        
        # バックアップディレクトリ作成
        backup_dir = self.cache_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        # タイムスタンプ付きバックアップ
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 旧バージョン取得
        import sqlite3
        conn = sqlite3.connect(existing_db)
        try:
            cursor = conn.execute("SELECT value FROM METADATA WHERE key='db_version'")
            old_version = cursor.fetchone()[0]
        except:
            old_version = "unknown"
        finally:
            conn.close()
        
        backup_file = backup_dir / f"tags_v{old_version}_{timestamp}.db"
        shutil.copy2(existing_db, backup_file)
        
        print(f"  ✓ Backup created: {backup_file.name}")
        
        # 古いバックアップ削除（最新3世代のみ保持）
        backups = sorted(backup_dir.glob("tags_v*.db"), key=lambda p: p.stat().st_mtime)
        for old_backup in backups[:-3]:
            old_backup.unlink()
            print(f"  ℹ Removed old backup: {old_backup.name}")
    
    def atomic_install(self, new_db: Path) -> None:
        """アトミック配置"""
        print("6/7: Installing database...")
        
        target_db = self.cache_dir / "tags.db"
        
        # アトミック移動（同一ファイルシステム前提）
        new_db.replace(target_db)
        
        print(f"  ✓ Installed: {target_db}")
    
    def enable_wal_mode(self) -> None:
        """WALモード有効化"""
        print("7/7: Enabling WAL mode...")
        
        import sqlite3
        db_file = self.cache_dir / "tags.db"
        conn = sqlite3.connect(db_file)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            print("  ✓ WAL mode enabled")
        finally:
            conn.close()
    
    def setup(self) -> None:
        """セットアップ実行"""
        try:
            # 1. ダウンロード
            zst_file, hash_file = self.download_from_hf()
            
            # 2. ハッシュ検証
            self.verify_integrity(zst_file, hash_file)
            
            # 3. 展開
            new_db = self.decompress_zstd(zst_file)
            
            # 4. スキーマ検証
            self.verify_schema(new_db)
            
            # 5. バックアップ
            self.backup_existing_db()
            
            # 6. インストール
            self.atomic_install(new_db)
            
            # 7. WAL有効化
            self.enable_wal_mode()
            
            print("\n✓ Setup complete!")
            print(f"Database location: {self.cache_dir / 'tags.db'}")
            
        except Exception as e:
            print(f"\n✗ Setup failed: {e}")
            raise

if __name__ == "__main__":
    setup = DatabaseSetup()
    setup.setup()
```

#### シングルレイヤーアーキテクチャ

```
┌─────────────────────────────────────────────────┐
│ ローカルSQLite (tags.db) 1-2GB                  │
│ - 全タグ: 1.5M-2M件（統合後）                   │
│ - B-tree index: tag, source_tag, format_id      │
│ - 応答速度: 5-50ms (95パーセンタイル)           │
│ - カバレッジ: 100%                              │
│ - WALモード: 並行読み取り対応                   │
└─────────────────────────────────────────────────┘
                    ↓ 更新が必要な場合
┌─────────────────────────────────────────────────┐
│ HuggingFace Dataset (NEXTAltair/genai-unified)  │
│ - tags_unified.db.zst (500MB-1GB圧縮)           │
│ - 月次更新（手動またはCI）                      │
│ - ダウンロード → 検証 → 丸ごと入れ替え          │
└─────────────────────────────────────────────────┘
```

**クエリフロー:**
```python
# シンプルな1層クエリ
class TagRepository:
    def __init__(self, db_path: Path = Path.home() / ".cache/genai-tag-db-tools/tags.db"):
        self.engine = create_engine(f"sqlite:///{db_path}")
    
    def search_tags(self, keyword: str, partial: bool = False) -> pl.DataFrame:
        """SQLiteから直接検索（5-50ms）"""
        with self.engine.connect() as conn:
            if partial:
                query = text("""
                    SELECT t.*, ts.format_id, ts.type_id, ts.alias,
                           uc.count as usage_count
                    FROM TAGS t
                    LEFT JOIN TAG_STATUS ts ON t.tag_id = ts.tag_id
                    LEFT JOIN TAG_USAGE_COUNTS uc ON t.tag_id = uc.tag_id
                    WHERE t.tag LIKE :pattern OR t.source_tag LIKE :pattern
                    LIMIT 1000
                """)
                result = conn.execute(query, {"pattern": f"%{keyword}%"})
            else:
                query = text("""
                    SELECT t.*, ts.format_id, ts.type_id, ts.alias,
                           uc.count as usage_count
                    FROM TAGS t
                    LEFT JOIN TAG_STATUS ts ON t.tag_id = ts.tag_id
                    LEFT JOIN TAG_USAGE_COUNTS uc ON t.tag_id = uc.tag_id
                    WHERE t.tag = :keyword OR t.source_tag = :keyword
                """)
                result = conn.execute(query, {"keyword": keyword})
            
            return pl.DataFrame(result.fetchall())
```

## CI/CD設計（GitHub Actions）

### ビルドパイプライン

```yaml
# .github/workflows/build_dataset.yml
name: Build Unified Tag Database

on:
  schedule:
    - cron: '0 0 1 * *'  # 月初0時（月次更新）
  workflow_dispatch:     # 手動実行可能
    inputs:
      force_rebuild:
        description: 'Force full rebuild'
        type: boolean
        default: false

env:
  HF_REPO: NEXTAltair/genai-unified-tag-dataset
  PYTHON_VERSION: '3.12'

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 180  # 3時間
    
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      
      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.cargo/bin" >> $GITHUB_PATH
      
      - name: Install dependencies
        run: uv sync
      
      - name: Install zstd
        run: sudo apt-get install -y zstd
      
      - name: Download source data
        run: |
          # genai-tag-db-toolsのtags_v4.dbを取得
          wget https://github.com/NEXTAltair/genai-tag-db-tools/raw/main/src/genai_tag_db_tools/data/tags_v4.db \
               -O data/tags_v4.db
      
      - name: Build Step 1 - Export tags_v4.db
        run: |
          uv run python scripts/export_tags_v4.py \
            --input data/tags_v4.db \
            --output data/genai_core_tags.parquet
      
      - name: Build Step 2 - Extract deepghs/site_tags
        run: |
          uv run python scripts/extract_deepghs_tags.py \
            --output data/deepghs_new_tags.parquet
      
      - name: Build Step 3 - Extract danbooru-wiki
        run: |
          uv run python scripts/extract_danbooru_wiki.py \
            --output data/danbooru_wiki_enrichment.parquet
      
      - name: Build Step 4 - Merge all sources
        run: |
          uv run python scripts/merge_all_sources.py \
            --genai-core data/genai_core_tags.parquet \
            --deepghs data/deepghs_new_tags.parquet \
            --danbooru-wiki data/danbooru_wiki_enrichment.parquet \
            --output data/tags_unified.db
      
      - name: Build Step 5 - Optimize database
        run: |
          sqlite3 data/tags_unified.db <<EOF
          PRAGMA journal_mode=WAL;
          PRAGMA synchronous=NORMAL;
          PRAGMA cache_size=-64000;
          PRAGMA temp_store=MEMORY;
          PRAGMA page_size=4096;
          ANALYZE;
          VACUUM;
          EOF
      
      - name: Build Step 6 - Compress with zstd
        run: |
          zstd -19 data/tags_unified.db -o data/tags_unified.db.zst
          
          # SHA256ハッシュ計算
          sha256sum data/tags_unified.db.zst | awk '{print $1}' > data/tags_unified.db.sha256
      
      - name: Build Step 7 - Generate metadata
        run: |
          uv run python scripts/generate_metadata.py \
            --db data/tags_unified.db \
            --output outputs/build_metadata.json
      
      - name: Run integrity tests
        run: |
          uv run pytest tests/ -v
      
      - name: Upload to HuggingFace
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          pip install huggingface_hub
          
          huggingface-cli login --token $HF_TOKEN
          
          huggingface-cli upload \
            ${{ env.HF_REPO }} \
            data/tags_unified.db.zst \
            --repo-type dataset
          
          huggingface-cli upload \
            ${{ env.HF_REPO }} \
            data/tags_unified.db.sha256 \
            --repo-type dataset
          
          huggingface-cli upload \
            ${{ env.HF_REPO }} \
            outputs/build_metadata.json \
            --repo-type dataset
      
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          tag_name: v${{ steps.metadata.outputs.version }}
          name: Database v${{ steps.metadata.outputs.version }}
          body_path: outputs/release_notes.md
          files: |
            data/tags_unified.db.zst
            data/tags_unified.db.sha256
            outputs/build_metadata.json
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Cleanup
        if: always()
        run: |
          rm -rf data/*.parquet data/*.db
```

### ビルド時間見積

| ステップ | 推定時間 | 備考 |
|---------|---------|------|
| tags_v4.db逆エクスポート | 5-10分 | 993,514タグ → Parquet |
| deepghs/site_tags抽出 | 30-60分 | 2.5M+タグ処理、重複判定 |
| danbooru-wiki統合 | 5-10分 | 180,839エントリ処理 |
| 3ソースマージ | 15-30分 | SQLite生成、インデックス構築 |
| 最適化・圧縮 | 10-20分 | VACUUM, ANALYZE, zstd圧縮 |
| HFアップロード | 10-20分 | 500MB-1GB（ネットワーク速度依存） |
| **合計** | **75-150分** | CI実行時間 |

### リソース見積り（修正版）

#### ディスク容量
| 項目 | サイズ | 備考 |
|------|--------|------|
| Layer 1キャッシュ（SQLite） | 114MB | count >= 2タグ 527,923件 |
| Layer 2キャッシュ（Parquet） | 215MB | HF unified dataset（全タグ993,514件） |
| Layer 3展開用（一時） | 500MB | オンライン取得時のみ使用 |
| **合計（通常時）** | **329MB** | Layer 1+2のみ |
| **合計（拡張時）** | **829MB** | Layer 3使用時 |

#### メモリ使用量
| フェーズ | RAM使用量 | 詳細 |
|---------|-----------|------|
| 通常クエリ（Layer 1） | 50-100MB | SQLite接続プール |
| Layer 2フォールバック | 200-300MB | DuckDB Arrow読込 |
| Layer 3オンライン取得 | 500-800MB | Parquetストリーミング |
| **ピーク時** | **800MB** | Layer 3使用時 |

#### 初回セットアップ時間
| ステップ | 所要時間 | ネットワーク |
|---------|---------|-------------|
| HF unified dataset DL | 1-2分 | 200MB @ 10Mbps |
| Parquet → SQLite変換 | 1-2分 | - |
| インデックス構築 | 30秒-1分 | - |
| **合計** | **3-5分** | 初回のみ |

---

## 初期同期フローの詳細化

### Phase 1: NEXTAltair/genai-tag-db-unified 構築（開発者側作業）

#### Step 1.1: データ収集と前処理
```bash
# 1. 既存tags_v4.dbをParquetに変換（全タグ、閾値なし）
uv run python -m genai_tag_db_tools.scripts.export_to_parquet \
  --input local_packages/genai-tag-db-tools/src/genai_tag_db_tools/data/tags_v4.db \
  --output /tmp/genai_core_tags.parquet

# 2. deepghs/site_tagsから全タグ抽出（閾値なし）
uv run python -m genai_tag_db_tools.scripts.extract_all_tags \
  --source deepghs/site_tags \
  --output /tmp/deepghs_all_tags.parquet

# 3. isek-ai/danbooru-wiki-2024のマッピングデータ抽出
uv run python -m genai_tag_db_tools.scripts.extract_mappings \
  --source isek-ai/danbooru-wiki-2024 \
  --output /tmp/danbooru_wiki_mappings.parquet
```

#### Step 1.2: スキーマ統合とマージ
```python
# スキーマ統合ルール:
統合優先順位:
1. genai_core_tags (既存DBの全レコード) - ベースとして採用
2. deepghs_popular_tags (新規タグのみ追加) - 既存tag_nameとマッチしない場合のみ
3. danbooru_wiki_mappings (翻訳・エイリアス補完) - existing tag_idに関連付け

重複判定:
- tag_nameの正規化比較（小文字化、アンダースコア除去）
- source_tagとのクロスマッチ

翻訳統合:
- 既存TAG_TRANSLATIONSを優先
- deepghsのtrans_ja/trans_enで補完
- danbooru-wikiのother_namesを alternative_names として追加

タイプマッピング:
- deepghsのcategory → TAG_TYPE_NAME へマッピング
  - 0:general, 1:artist, 3:copyright, 4:character
- TAG_TYPE_FORMAT_MAPPINGに従ってformat_id別のtype_idを割り当て
```

#### Step 1.3: 整合性検証
```python
検証項目:
1. レコード数チェック:
   - 統合前: genai_core + new_tags_count
   - 統合後: 総レコード数が一致
   
2. 外部キー整合性:
   - TAG_STATUS.tag_id → TAGS.tag_id
   - TAG_STATUS.preferred_tag_id → TAGS.tag_id
   - TAG_TRANSLATIONS.tag_id → TAGS.tag_id
   
3. エイリアス整合性:
   - alias=true → preferred_tag_id != tag_id
   - alias=false → preferred_tag_id == tag_id
   
4. SHA256ハッシュ計算:
   - 統合Parquetファイルのハッシュ値を記録
   - dataset cardに記載
```

#### Step 1.4: HuggingFace公開
```bash
# HuggingFace CLIでアップロード
huggingface-cli login --token $HF_TOKEN

huggingface-cli upload \
  NEXTAltair/genai-tag-db-unified \
  /tmp/unified_tags.parquet \
  --repo-type dataset

# Dataset Cardの作成（ライセンス・データソース明記）
cat > README.md <<EOF
---
license: cc-by-sa-4.0
task_categories:
- text-classification
language:
- en
- ja
- ru
size_categories:
- 100K<n<1M
---

# genai-tag-db-unified

## データソース
- genai-tag-db-tools (MIT → データ部分をCC-BY-SA 4.0で再配布)
- deepghs/site_tags (CC-BY-4.0)
- isek-ai/danbooru-wiki-2024 (CC-BY-SA 4.0)

## ファイル整合性
- SHA256: [計算値]
- レコード数: [統合後の総数]

## 更新頻度
月次更新予定（deepghs/site_tags更新に連動）
EOF
```

### Phase 2: エンドユーザー初期セットアップ

#### セットアップコマンド実装
```python
# genai_tag_db_tools/scripts/setup_cache.py
import duckdb
from datasets import load_dataset
from pathlib import Path
from sqlalchemy import create_engine, text

def setup_local_cache(cache_dir: Path = Path.home() / ".cache/genai-tag-db-tools"):
    """
    初回セットアップ: HFから統合データセット（全タグ）をダウンロードし、
    アプリ用にcount >= 2回使用タグ 527,923件をSQLiteキャッシュに構築
    
    HFデータセット: 全タグ993,514件（研究者・開発者向け完全データ）
    ローカルキャッシュ: count >= 2タグ527,923件（アプリ効率化）
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: HFから統合データセット取得（全タグ）
    print("1/4: Downloading unified dataset from HuggingFace (all tags)...")
    ds = load_dataset(
        "NEXTAltair/genai-tag-db-unified",
        split="train",
        cache_dir=str(cache_dir / "hf_cache")
    )
    parquet_path = cache_dir / "hf_cache" / "unified_tags.parquet"
    
    # Step 2: SHA256検証
    print("2/4: Verifying file integrity...")
    expected_hash = "..."  # Dataset cardから取得
    actual_hash = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"Hash mismatch: expected {expected_hash}, got {actual_hash}")
    
    # Step 3: DuckDBでcount >= 2タグ抽出
    print("3/4: Extracting valid tags (count >= 2)...")
    conn = duckdb.connect()
    valid_tags = conn.execute(f"""
        SELECT * FROM read_parquet('{parquet_path}')
        WHERE usage_count >= 2
    """).fetchdf()
    
    # Step 4: SQLiteキャッシュ構築
    print("4/4: Building local SQLite cache...")
    sqlite_path = cache_dir / "tags_cache.db"
    engine = create_engine(f"sqlite:///{sqlite_path}")
    
    # テーブル作成（既存スキーマと同一）
    with engine.begin() as conn:
        # TAGSテーブル
        valid_tags.to_sql("TAGS", conn, if_exists="replace", index=False)
        
        # インデックス構築
        conn.execute(text("CREATE INDEX idx_tags_tag ON TAGS(tag)"))
        conn.execute(text("CREATE INDEX idx_tags_source_tag ON TAGS(source_tag)"))
        conn.execute(text("CREATE INDEX idx_tag_status_format ON TAG_STATUS(format_id, tag_id)"))
        conn.execute(text("CREATE INDEX idx_translations_tag_lang ON TAG_TRANSLATIONS(tag_id, language)"))
    
    print(f"✓ Setup complete! Cache location: {cache_dir}")
    print(f"  - SQLite cache: {sqlite_path} ({sqlite_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  - HF cache: {parquet_path} ({parquet_path.stat().st_size / 1024 / 1024:.1f} MB)")
```

#### リトライ・再開機構
```python
def setup_with_retry(max_retries=3):
    """
    ネットワーク障害時のリトライ処理
    """
    for attempt in range(max_retries):
        try:
            # ダウンロード進捗をディスクに保存
            state_file = cache_dir / ".setup_state.json"
            state = json.loads(state_file.read_text()) if state_file.exists() else {}
            
            if state.get("download_complete"):
                print("Resuming from download completion...")
            else:
                ds = load_dataset(..., resume_download=True)
                state["download_complete"] = True
                state_file.write_text(json.dumps(state))
            
            if state.get("extraction_complete"):
                print("Resuming from extraction completion...")
            else:
                # Extract popular tags...
                state["extraction_complete"] = True
                state_file.write_text(json.dumps(state))
            
            # Build SQLite cache...
            state_file.unlink()  # 完了後削除
            return True
            
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
```

#### ロールバック手順
```python
def rollback_setup(cache_dir: Path):
    """
    セットアップ失敗時のクリーンアップ
    """
    print("Rolling back incomplete setup...")
    
    # 不完全なファイルを削除
    if (cache_dir / "tags_cache.db").exists():
        (cache_dir / "tags_cache.db").unlink()
    
    # HFキャッシュは保持（再利用可能）
    print("✓ Rollback complete. Run setup again to retry.")
```

---

## クエリ設計の現実的な実装

### Layer 1: SQLiteキャッシュクエリ

```python
class LocalSQLiteCache:
    def __init__(self, cache_db_path: Path):
        self.engine = create_engine(f"sqlite:///{cache_db_path}")
    
    def search_tags(self, keyword: str, partial: bool = False) -> list[int]:
        """
        キャッシュ内で高速検索（10-50ms）
        """
        with self.engine.connect() as conn:
            if partial:
                # B-tree indexを利用したLIKE検索
                query = text("""
                    SELECT tag_id FROM TAGS
                    WHERE tag LIKE :pattern OR source_tag LIKE :pattern
                    LIMIT 1000
                """)
                result = conn.execute(query, {"pattern": f"%{keyword}%"})
            else:
                # インデックス活用の完全一致
                query = text("""
                    SELECT tag_id FROM TAGS
                    WHERE tag = :keyword OR source_tag = :keyword
                """)
                result = conn.execute(query, {"keyword": keyword})
            
            return [row[0] for row in result]
    
    def get_tag_by_id(self, tag_id: int) -> dict | None:
        """
        tag_idからタグ情報取得（5-10ms）
        """
        with self.engine.connect() as conn:
            query = text("""
                SELECT t.*, ts.format_id, ts.type_id, ts.alias, ts.preferred_tag_id
                FROM TAGS t
                LEFT JOIN TAG_STATUS ts ON t.tag_id = ts.tag_id
                WHERE t.tag_id = :tag_id
            """)
            result = conn.execute(query, {"tag_id": tag_id}).fetchone()
            return dict(result) if result else None
```

### Layer 2: DuckDB Parquetクエリ

```python
class HFLocalParquetCache:
    def __init__(self, parquet_path: Path):
        self.conn = duckdb.connect()
        self.parquet_path = parquet_path
    
    def search_tags(self, keyword: str, partial: bool = False) -> pl.DataFrame:
        """
        Parquetから直接SQL検索（200-500ms）
        Arrow zero-copyで効率的
        """
        if partial:
            query = f"""
                SELECT * FROM read_parquet('{self.parquet_path}')
                WHERE tag LIKE '%{keyword}%' OR source_tag LIKE '%{keyword}%'
                LIMIT 1000
            """
        else:
            query = f"""
                SELECT * FROM read_parquet('{self.parquet_path}')
                WHERE tag = '{keyword}' OR source_tag = '{keyword}'
            """
        
        return self.conn.execute(query).pl()  # Polars DataFrame
    
    def promote_to_layer1(self, tag_ids: list[int], sqlite_cache: LocalSQLiteCache):
        """
        Layer 2で見つかったタグをLayer 1に昇格
        """
        tags_df = self.conn.execute(f"""
            SELECT * FROM read_parquet('{self.parquet_path}')
            WHERE tag_id IN ({','.join(map(str, tag_ids))})
        """).pl()
        
        # SQLiteに挿入
        tags_df.write_database("TAGS", sqlite_cache.engine, if_exists="append")
```

### Layer 3: HFオンラインストリーミング（オプション）

```python
class HFOnlineStreaming:
    def __init__(self):
        self.enabled = False  # デフォルト無効
    
    def enable_online_mode(self):
        """
        明示的にオンラインモードを有効化
        """
        self.enabled = True
    
    def search_in_external_sources(self, keyword: str) -> list[dict]:
        """
        deepghs/site_tagsからストリーミング検索（2-5秒）
        """
        if not self.enabled:
            return []
        
        results = []
        ds = load_dataset("deepghs/site_tags", split="train", streaming=True)
        
        for sample in ds:
            if keyword in sample["name"] or keyword in sample.get("source_tag", ""):
                results.append(sample)
                if len(results) >= 100:  # 100件で打ち切り
                    break
        
        return results
```

### 統合クエリコーディネーター

```python
class HybridTagRepository:
    def __init__(self, cache_dir: Path):
        self.layer1 = LocalSQLiteCache(cache_dir / "tags_cache.db")
        self.layer2 = HFLocalParquetCache(cache_dir / "hf_cache/unified_tags.parquet")
        self.layer3 = HFOnlineStreaming()
        
        self.cache_hit_stats = {"layer1": 0, "layer2": 0, "layer3": 0, "miss": 0}
    
    def search_tags(self, keyword: str, **kwargs) -> pl.DataFrame:
        """
        3層クエリの自動フォールバック
        """
        # Layer 1: SQLite cache
        tag_ids = self.layer1.search_tags(keyword, **kwargs)
        if tag_ids:
            self.cache_hit_stats["layer1"] += 1
            return self._collect_tag_info(tag_ids)
        
        # Layer 2: HF local Parquet
        tags_df = self.layer2.search_tags(keyword, **kwargs)
        if not tags_df.is_empty():
            self.cache_hit_stats["layer2"] += 1
            # Layer 1に昇格
            self.layer2.promote_to_layer1(tags_df["tag_id"].to_list(), self.layer1)
            return tags_df
        
        # Layer 3: HF online (optional)
        if self.layer3.enabled:
            results = self.layer3.search_in_external_sources(keyword)
            if results:
                self.cache_hit_stats["layer3"] += 1
                tags_df = pl.DataFrame(results)
                # Layer 1/2に永続化
                self._persist_new_tags(tags_df)
                return tags_df
        
        self.cache_hit_stats["miss"] += 1
        return pl.DataFrame([])
    
    def get_cache_hit_rate(self) -> dict[str, float]:
        """
        キャッシュヒット率の統計
        """
        total = sum(self.cache_hit_stats.values())
        if total == 0:
            return {}
        
        return {
            "layer1_rate": self.cache_hit_stats["layer1"] / total,
            "layer2_rate": self.cache_hit_stats["layer2"] / total,
            "layer3_rate": self.cache_hit_stats["layer3"] / total,
            "miss_rate": self.cache_hit_stats["miss"] / total,
        }
```

---

## スキーマ統合ポリシー

### マッピングルール

#### タグIDの統合
```python
統合ルール:
1. genai-tag-db-toolsのtag_idを基準IDとして採用
2. 新規タグ（deepghs/site_tags由来）:
   - tag_idは既存最大値+1から連番
   - source_tag = deepghs元のname
   - tag = 正規化後の名前（小文字、スペース除去）

重複判定:
def is_duplicate(new_tag: str, existing_tags: list[str]) -> bool:
    normalized_new = normalize_tag(new_tag)
    for existing in existing_tags:
        if normalized_new == normalize_tag(existing):
            return True
    return False

def normalize_tag(tag: str) -> str:
    return tag.lower().replace("_", " ").strip()
```

#### フォーマットマッピング
```python
deepghs site → TAG_FORMAT_ID マッピング:
{
    "danbooru.donmai.us": 1,  # format_name="danbooru"
    "safebooru.donmai.us": 1,  # 同一フォーマット扱い
    "e621.net": 2,             # format_name="e621"
    "gelbooru.com": 1,         # danbooruベースなので1
    "konachan.com": 1,
    "konachan.net": 1,
    "pixiv.net": None,         # 新規format_id=4を割り当て
    "en.pixiv.net": 4,
    # ... 残り10サイトも既存フォーマットにマッピング or 新規追加
}

新規フォーマット追加:
INSERT INTO TAG_FORMATS (format_id, format_name, description)
VALUES (4, 'pixiv', 'Pixiv tag format');
```

#### タイプマッピング
```python
deepghs category → type_name_id マッピング:
{
    0: 1,  # general → general
    1: 2,  # artist → artist
    3: 3,  # copyright → copyright
    4: 4,  # character → character
}

danbooru-wiki category → type_name_id:
既存のTAG_TYPE_NAMEテーブルから文字列マッチング:
- "Artist" → type_name_id=2
- "Character" → type_name_id=4
- "Copyright" → type_name_id=3
- その他 → type_name_id=1 (general)
```

#### 翻訳統合
```python
翻訳優先順位:
1. genai-tag-db-tools既存のTAG_TRANSLATIONS（最優先）
2. deepghs/site_tagsのtrans_ja, trans_en, trans_ru
3. danbooru-wiki-2024のother_names（alternative_namesとして別フィールド追加）

衝突解決:
- 同一(tag_id, language)で異なるtranslationが存在する場合:
  - 既存を優先（genai-tag-db-tools）
  - 新規翻訳はalternative_translationsテーブルに追加（新規テーブル）

新規テーブル:
CREATE TABLE ALTERNATIVE_TRANSLATIONS (
    alt_translation_id INTEGER PRIMARY KEY,
    tag_id INTEGER REFERENCES TAGS(tag_id),
    language VARCHAR(10),
    translation TEXT,
    source VARCHAR(50),  -- 'deepghs', 'danbooru-wiki'
    UNIQUE(tag_id, language, translation)
);
```

#### エイリアス関係
```python
エイリアス統合ルール:
1. genai-tag-db-toolsのTAG_STATUS.alias=trueレコードを優先
2. deepghs/site_tagsに新規エイリアスがある場合:
   - preferred_tag_idの解決:
     a. deepghs元のpreferred_tagがDBに存在 → そのtag_idを使用
     b. 存在しない → 新規タグとして追加後、そのtag_idを使用
3. danbooru-wiki-2024のother_names:
   - エイリアスではなく「別名」として扱う
   - 検索時のヒット拡大に使用（ALTERNATIVE_TRANSLATIONSに格納）

整合性チェック:
INSERT時に以下を検証:
- alias=true AND preferred_tag_id != tag_id
- alias=false AND preferred_tag_id == tag_id
- preferred_tag_idがTAGS.tag_idに存在
```

---

## API互換性の完全保証

### 既存API仕様（変更禁止）

#### TagSearcher (genai_tag_db_tools/services/tag_search.py)
```python
必須メソッド（シグネチャ完全維持）:

1. search_tags(
    keyword: str,
    partial: bool = False,
    format_name: str | None = None,
    type_name: str | None = None,
    language: str | None = None,
    min_usage: int | None = None,
    max_usage: int | None = None,
    alias: bool | None = None,
) -> pl.DataFrame
   戻り値スキーマ:
   - tag_id: int
   - tag: str
   - source_tag: str
   - usage_count: int
   - alias: bool
   - type_name: str
   - translations: dict[str, str]

2. convert_tag(search_tag: str, format_id: int) -> str

3. get_tag_types(format_name: str) -> list[str]

4. get_all_types() -> list[str]

5. get_tag_languages() -> list[str]

6. get_tag_formats() -> list[str]

7. get_format_id(format_name: str | None) -> int
```

#### TagCleaner (genai_tag_db_tools/utils/cleanup_str.py)
```python
必須メソッド（静的メソッド、キャッシュ維持）:

1. @cache
   @staticmethod
   clean_format(text: str) -> str

2. @staticmethod
   clean_tags(tags: str) -> str

3. @staticmethod
   clean_caption(caption: str) -> str

4. convert_prompt(self, prompt: str, format_name: str) -> str
   ※ TagSearcherへの依存維持
```

### 互換性検証テストスイート

#### 回帰テストケース
```python
# tests/integration/test_api_compatibility.py
import pytest
from genai_tag_db_tools.services.tag_search import TagSearcher
from genai_tag_db_tools.utils.cleanup_str import TagCleaner

class TestTagSearcherCompatibility:
    """既存APIの後方互換性テスト"""
    
    def test_search_tags_signature(self):
        """search_tagsのシグネチャが変わっていないこと"""
        searcher = TagSearcher()
        
        # 従来の呼び出しパターンが動作すること
        result = searcher.search_tags(
            keyword="1girl",
            partial=False,
            format_name="danbooru",
            type_name="character",
            language="ja",
            min_usage=100,
            max_usage=10000,
            alias=False
        )
        
        assert isinstance(result, pl.DataFrame)
        assert "tag_id" in result.columns
        assert "tag" in result.columns
        assert "translations" in result.columns
    
    def test_convert_tag_behavior(self):
        """convert_tagの変換結果が既存と同一であること"""
        searcher = TagSearcher()
        
        # 既知のエイリアス変換が動作すること
        result = searcher.convert_tag("1boy", format_id=2)  # e621
        assert result in ["male", "1boy"]  # 既存の変換結果
    
    def test_search_tags_performance(self):
        """検索パフォーマンスが既存と同等以上であること"""
        import time
        searcher = TagSearcher()
        
        start = time.time()
        result = searcher.search_tags("1girl", partial=False)
        elapsed = time.time() - start
        
        assert elapsed < 0.1  # 100ms以内（Layer 1キャッシュヒット時）

class TestTagCleanerCompatibility:
    """TagCleanerの後方互換性テスト"""
    
    def test_clean_format_cache(self):
        """clean_formatのキャッシュが動作すること"""
        # 同一入力で2回目は高速化されること
        text = "test_input, with, commas"
        
        result1 = TagCleaner.clean_format(text)
        result2 = TagCleaner.clean_format(text)
        
        assert result1 == result2
        assert TagCleaner.clean_format.cache_info().hits > 0
    
    def test_convert_prompt_integration(self):
        """convert_promptがTagSearcherと連携動作すること"""
        cleaner = TagCleaner()
        
        result = cleaner.convert_prompt("1boy, 1girl", "e621")
        assert "," in result  # カンマ区切り形式維持
```

#### LoRAIro統合テスト
```python
# tests/integration/test_lorairo_integration.py
from lorairo.annotations.existing_file_reader import ExistingFileReader
from lorairo.database.db_repository import DBRepository

class TestLoRAIroIntegration:
    """LoRAIro側の統合ポイントテスト"""
    
    def test_existing_file_reader_cleanup(self):
        """ExistingFileReaderがTagCleaner.clean_formatを呼び出せること"""
        reader = ExistingFileReader()
        
        # 実際のファイル読み込みパターン
        test_content = "tag1, tag2, tag3\n"
        cleaned = reader.tag_cleaner.clean_format(test_content)
        
        assert cleaned == "tag1, tag2, tag3"
        assert "\n" not in cleaned
    
    def test_db_repository_tag_search(self):
        """DBRepositoryがTagRepositoryを使用できること"""
        repo = DBRepository()
        
        # 既存の検索パターンが動作すること
        tags = repo.search_tags_by_name("landscape")
        assert isinstance(tags, list)
```

---

## 同期・更新戦略

### 月次自動更新フロー

#### トリガー条件
```python
更新トリガー:
1. deepghs/site_tagsの更新検知
   - HF API: GET /api/datasets/deepghs/site_tags/commit/main
   - last_modified と ローカルキャッシュのタイムスタンプ比較
   
2. 手動更新コマンド
   - `genai-tag-db-update --force`
   
3. 定期スケジュール（オプション）
   - cron/Task Schedulerで月次実行
```

#### 差分同期プロトコル
```python
def check_for_updates() -> bool:
    """
    HFデータセットの更新チェック
    """
    local_version = read_local_version()  # ~/.cache/genai-tag-db-tools/version.txt
    
    # HF APIでリモートバージョン取得
    response = requests.get(
        "https://huggingface.co/api/datasets/NEXTAltair/genai-tag-db-unified",
        headers={"Authorization": f"Bearer {HF_TOKEN}"}  # 公開データセットなら不要
    )
    remote_version = response.json()["siblings"][0]["lastModified"]
    
    return remote_version > local_version

def perform_incremental_sync():
    """
    差分同期の実装
    """
    # 1. 新バージョンのParquetをダウンロード
    new_parquet = cache_dir / "hf_cache" / "unified_tags_new.parquet"
    ds = load_dataset("NEXTAltair/genai-tag-db-unified", split="train")
    
    # 2. DuckDBで差分抽出
    conn = duckdb.connect()
    diff_df = conn.execute(f"""
        SELECT new.*
        FROM read_parquet('{new_parquet}') new
        LEFT JOIN read_parquet('{cache_dir / "hf_cache/unified_tags.parquet"}') old
        ON new.tag_id = old.tag_id
        WHERE old.tag_id IS NULL OR new.updated_at > old.updated_at
    """).pl()
    
    # 3. Layer 1 SQLiteキャッシュに差分適用
    with LocalSQLiteCache(cache_dir / "tags_cache.db").engine.begin() as conn:
        for row in diff_df.iter_rows(named=True):
            # UPSERT処理
            conn.execute(text("""
                INSERT INTO TAGS (tag_id, tag, source_tag, updated_at)
                VALUES (:tag_id, :tag, :source_tag, :updated_at)
                ON CONFLICT(tag_id) DO UPDATE SET
                    tag = excluded.tag,
                    source_tag = excluded.source_tag,
                    updated_at = excluded.updated_at
            """), row)
    
    # 4. 旧Parquetを置き換え
    new_parquet.replace(cache_dir / "hf_cache/unified_tags.parquet")
    
    # 5. バージョン更新
    write_local_version(remote_version)
```

#### ロールバック機能
```python
def rollback_to_previous_version():
    """
    更新失敗時に前バージョンへロールバック
    """
    backup_dir = cache_dir / "backups"
    
    # 最新のバックアップを特定
    latest_backup = max(backup_dir.glob("tags_cache_*.db"), key=lambda p: p.stat().st_mtime)
    
    # 現在のキャッシュを置き換え
    latest_backup.replace(cache_dir / "tags_cache.db")
    
    print(f"✓ Rolled back to {latest_backup.stem}")

def create_backup_before_update():
    """
    更新前に自動バックアップ作成
    """
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = cache_dir / "backups" / f"tags_cache_{timestamp}.db"
    
    backup_path.parent.mkdir(exist_ok=True)
    shutil.copy2(cache_dir / "tags_cache.db", backup_path)
    
    # 古いバックアップを削除（最新3世代のみ保持）
    backups = sorted(cache_dir.glob("backups/tags_cache_*.db"), key=lambda p: p.stat().st_mtime)
    for old_backup in backups[:-3]:
        old_backup.unlink()
```

---

## セキュリティと資格情報管理

### HFトークン管理

#### 読み取り専用アクセス
```python
公開データセット戦略:
- NEXTAltair/genai-tag-db-unified は public に設定
- トークン不要でアクセス可能
- 匿名ユーザーも datasets.load_dataset() で取得可能

データセット公開設定:
# HF WebUI
Settings > Visibility > Public
```

#### プッシュアクセス（開発者のみ）
```python
環境変数管理:
# ~/.bashrc or ~/.zshrc
export HF_TOKEN="hf_xxxxxxxxxxxxx"

# またはhuggingface-cli login（推奨）
huggingface-cli login
  Token: [入力]
  Add to git credentials: [y/n]

トークンスコープ:
- write権限: NEXTAltair/genai-tag-db-unified への push のみ
- 最小権限の原則: 他のデータセットへのアクセスなし

トークンの保存場所:
- Linux/Mac: ~/.cache/huggingface/token
- Windows: %USERPROFILE%\.cache\huggingface\token
- パーミッション: 0600 (owner read/write only)
```

#### ログ記録の注意事項
```python
ロギングポリシー:
- HF_TOKENをログに出力しない
- URLからトークンを除去

import re
from loguru import logger

def sanitize_log_message(message: str) -> str:
    """
    ログメッセージからトークンを除去
    """
    # HFトークンパターン（hf_で始まる20+文字）
    message = re.sub(r"hf_[A-Za-z0-9]{20,}", "hf_***REDACTED***", message)
    
    # URL内のトークン（?token=...）
    message = re.sub(r"\?token=[^&\s]+", "?token=***REDACTED***", message)
    
    return message

logger.add(
    "logs/genai_tag_db.log",
    filter=lambda record: sanitize_log_message(record["message"])
)
```

---

## パフォーマンスSLAの修正

### 現実的なSLA設定

| 操作タイプ | 目標応答時間 | 達成条件 | 測定方法 |
|-----------|-------------|---------|---------|
| **キャッシュヒット（Layer 1）** | 10-50ms | 95パーセンタイル | SQLite B-tree index |
| **ローカルフォールバック（Layer 2）** | 200-500ms | 95パーセンタイル | DuckDB Parquet scan |
| **オンライン取得（Layer 3）** | 2-5秒 | 初回のみ | HF streaming |
| **初回セットアップ** | 3-5分 | 1回のみ | ネットワーク速度依存 |
| **月次更新** | 1-3分 | 差分同期 | 更新サイズ依存 |

### パフォーマンスモニタリング

```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            "layer1_response_times": [],
            "layer2_response_times": [],
            "layer3_response_times": [],
        }
    
    def record_query(self, layer: str, response_time: float):
        """
        クエリ応答時間を記録
        """
        self.metrics[f"{layer}_response_times"].append(response_time)
    
    def get_percentile(self, layer: str, percentile: int = 95) -> float:
        """
        指定レイヤーのN%ile応答時間を取得
        """
        times = self.metrics[f"{layer}_response_times"]
        if not times:
            return 0.0
        
        sorted_times = sorted(times)
        index = int(len(sorted_times) * percentile / 100)
        return sorted_times[index]
    
    def generate_report(self) -> str:
        """
        パフォーマンスレポート生成
        """
        return f"""
Performance Report:
- Layer 1 (95%ile): {self.get_percentile('layer1', 95):.2f}ms
- Layer 2 (95%ile): {self.get_percentile('layer2', 95):.2f}ms
- Layer 3 (95%ile): {self.get_percentile('layer3', 95):.2f}ms
- Cache hit rate: {self.get_cache_hit_rate()}
        """
```

---

## 実装フェーズ（修正版）

### Phase 1: データ統合基盤構築（Week 1-2）

#### Week 1: 統合スクリプト開発

**Task 1.1: tags_v4.db逆エクスポート実装** (2-3時間)
```python
# 新規リポジトリ: NEXTAltair/genai-unified-tag-dataset
# scripts/export_tags_v4.py

使用技術:
- Polars: 高速DataFrame処理（既存実装と同じ）
- SQLite3: tags_v4.db読込
- Parquet: 出力フォーマット

処理ステップ:
1. TAGSテーブル全件読込（993,514行）
2. TAG_STATUSと結合（format_id, type_id, alias, preferred_tag_id）
3. TAG_USAGE_COUNTSから総使用回数集計
4. TAG_TRANSLATIONSをJSON化して結合
5. Parquet出力（圧縮: snappy）

期待出力:
- genai_core_tags.parquet: 215MB（全タグ）
- カラム構成: tag_id, tag, source_tag, format_id, type_id, alias, 
              preferred_tag_id, total_count, translations_json
```

**Task 1.2: deepghs/site_tags抽出実装** (3-4時間)
```python
# scripts/extract_deepghs_tags.py

処理パターン（hf_to_sqlite_tag_transfer.pyを参考）:
1. 18サイトフォルダを順次処理
2. 各Parquetファイルからカラム抽出:
   - name → source_tag
   - normalized_name → tag（TagCleaner.clean_format()適用）
   - category → type_id（マッピング変換）
   - num → count
   - folder名 → format_id（site_to_format_id_map）
3. 重複判定: normalized tagで既存genai_coreとマッチング
4. 新規タグのみ抽出

site_to_format_id_map:
{
    "danbooru.donmai.us": 1,
    "safebooru.donmai.us": 1,
    "e621.net": 2,
    "derpibooru.org": 3,
    "gelbooru.com": 1,  # danbooruベース
    "konachan.com": 1,
    "konachan.net": 1,
    "yande.re": 1,
    "pixiv.net": 4,  # 新規format追加
    "en.pixiv.net": 4,
    # ... 残り8サイト
}

期待出力:
- deepghs_new_tags.parquet: [サイズ未確定]
- 新規タグのみ（genai_coreに存在しないもの）
```

**Task 1.3: danbooru-wiki統合** (2時間)
```python
# scripts/extract_danbooru_wiki.py

処理:
1. isek-ai/danbooru-wiki-2024読込
2. other_namesをalternative_translationsとして抽出
3. categoryをtype_idにマッピング
4. tag_idの解決:
   - titleがgenai_core/deepghs_newに存在 → そのtag_id使用
   - 存在しない → 新規tag_id割当

期待出力:
- danbooru_wiki_enrichment.parquet
- 用途: 既存タグへの翻訳補完
```

**Task 1.4: スキーマ統合とマージ** (4-5時間)
```python
# scripts/merge_all_sources.py

マージロジック（migrate_v3_to_v4.pyのパターン適用）:
1. ベースDataFrame: genai_core_tags (993,514行)
2. deepghs_new_tags追加:
   - tag_idは既存最大値+1から連番
   - 重複判定: normalize_tag()で比較
3. danbooru_wiki翻訳補完:
   - 既存TAG_TRANSLATIONSを優先
   - 新規翻訳をalternative_translationsに追加
4. TAG_STATUS整合性検証:
   - alias=true → preferred_tag_id != tag_id
   - alias=false → preferred_tag_id == tag_id
   - preferred_tag_idの存在確認

出力:
- unified_tags_full.parquet: [サイズ未確定]（全タグ、閾値なし）
- カラム: tag_id, tag, source_tag, format_id, type_id, alias,
         preferred_tag_id, total_count, translations_json,
         alternative_translations_json, created_at, updated_at
```

**Task 1.5: SHA256整合性検証** (1時間)
```python
# scripts/verify_integrity.py

検証項目（migrate_v3_to_v4.pyから抽出）:
1. レコード数チェック:
   - genai_core + deepghs_new + danbooru_wiki_new = 総レコード数
2. 外部キー整合性:
   - TAG_STATUS.preferred_tag_id → TAGS.tag_id（全件存在確認）
3. エイリアス整合性:
   - alias=true時のpreferred_tag_id != tag_id
4. 重複チェック:
   - normalized tagの重複なし
5. SHA256ハッシュ計算:
   - unified_tags_full.parquetのハッシュ値記録

出力:
- integrity_report.json: 検証結果サマリ
- sha256.txt: ファイルハッシュ値
```

#### Week 2: HF公開と初期検証

**Task 2.1: Dataset Card作成** (2時間)
```markdown
# Template: NEXTAltair/genai-unified-tag-dataset/README.md

セクション構成:
1. Overview: データセットの目的と内容
2. Data Sources: 3ソースの詳細とライセンス
3. Schema: カラム定義とデータ型
4. Statistics: レコード数、サイズ、カバレッジ
5. Usage: Pythonでの使用例
6. Integrity: SHA256ハッシュ値
7. License: CC-BY-SA 4.0
8. Citation: データソースのクレジット
```

**Task 2.2: HuggingFace公開** (1時間)
```bash
# HF CLIでアップロード
huggingface-cli upload \
  NEXTAltair/genai-unified-tag-dataset \
  ./unified_tags_full.parquet \
  --repo-type dataset

# Dataset設定
- Visibility: Public
- License: cc-by-sa-4.0
- Task: text-classification
- Language: en, ja, ru
```

**Task 2.3: 整合性テスト** (3時間)
```python
# tests/test_dataset_integrity.py

テストケース:
1. ダウンロードテスト:
   - datasets.load_dataset()で取得可能
   - SHA256検証
2. スキーマテスト:
   - 必須カラム存在確認
   - データ型検証
3. データ品質テスト:
   - NULL値の割合チェック
   - 外部キー整合性
   - エイリアス整合性
4. 統計テスト:
   - レコード数が期待値
   - count >= 2の割合が99.98%以上
```

**Task 2.4: setup_cache.pyプロトタイプ** (4-5時間)
```python
# genai-tag-db-tools/scripts/setup_cache.py

実装（既存TagRegisterパターン活用）:
1. datasets.load_dataset()でHFから取得
2. DuckDBでcount >= 2フィルタ（527,923タグ抽出）
3. TagRegister.normalize_tags()適用
4. SQLiteキャッシュ構築:
   - TAGSテーブル作成
   - TAG_STATUSテーブル作成
   - TAG_TRANSLATIONSテーブル作成
   - インデックス構築（既存と同一）
5. リトライ・ロールバック機構

期待出力:
- ~/.cache/genai-tag-db-tools/tags_cache.db (114MB)
- ~/.cache/genai-tag-db-tools/hf_cache/*.parquet (215MB)
```

### Phase 2: 3層クエリアーキテクチャ実装（Week 3-4）

#### Week 3: Layer 1/2実装
- [ ] LocalSQLiteCacheクラス実装
- [ ] HFLocalParquetCacheクラス実装（DuckDB統合）
- [ ] キャッシュ昇格ロジック実装
- [ ] 初期セットアップコマンド（genai-tag-db-setup）

#### Week 4: Layer 3とコーディネーター
- [ ] HFOnlineStreamingクラス実装（オプション機能）
- [ ] HybridTagRepositoryコーディネーター実装
- [ ] パフォーマンスモニタリング機能
- [ ] リトライ・ロールバック機構

### Phase 3: API互換性ラッパー実装（Week 5）

#### 既存APIの内部実装置換
- [ ] TagSearcher.search_tags()の内部でHybridTagRepository使用
- [ ] TagSearcher.convert_tag()の動作保証
- [ ] TagCleanerとの統合テスト
- [ ] LoRAIro統合ポイント検証（ExistingFileReader, DBRepository）

### Phase 4: テストと検証（Week 6）

#### 統合テストスイート
- [ ] API互換性テスト（test_api_compatibility.py）
- [ ] LoRAIro統合テスト（test_lorairo_integration.py）
- [ ] パフォーマンステスト（SLA検証）
- [ ] キャッシュヒット率測定

#### 負荷テスト
- [ ] 100万件クエリでのLayer 1ヒット率測定
- [ ] Layer 2フォールバックの応答時間検証
- [ ] 初回セットアップ時間の実測

### Phase 5: デプロイとマイグレーション（Week 7）

#### ユーザー向けドキュメント
- [ ] セットアップガイド作成
- [ ] トラブルシューティングFAQ
- [ ] パフォーマンスチューニングガイド

#### マイグレーションツール
- [ ] 既存tags_v4.db使用環境からの移行スクリプト
- [ ] バックアップ・ロールバック手順書

#### リリース準備
- [ ] PyPI公開（genai-tag-db-tools v2.0.0）
- [ ] リリースノート作成
- [ ] LoRAIro側の依存更新PR

---

## リスク管理マトリクス（修正版）

| リスク | 発生確率 | 影響度 | 対策 | 緩和策 |
|-------|---------|-------|------|-------|
| **HF APIレート制限** | 低 | 中 | 公開データセット（トークン不要） | Layer 1/2のオフライン完結設計 |
| **データ整合性エラー** | 中 | 高 | SHA256検証＋整合性テスト | ロールバック機能 |
| **パフォーマンス劣化** | 低 | 高 | Layer 1キャッシュで95%ヒット | SLA監視とアラート |
| **ライセンス違反** | 低 | 極高 | CC-BY-SA 4.0明記＋Dataset Card | 法務レビュー |
| **API互換性破損** | 中 | 極高 | 包括的回帰テストスイート | 既存テスト全実行 |
| **初回セットアップ失敗** | 中 | 中 | リトライ機構＋再開機能 | ロールバック手順 |
| **ディスク容量不足** | 低 | 中 | 500MBの控えめ設計 | キャッシュクリーンアップコマンド |
| **ネットワーク障害** | 中 | 低 | オフライン完結設計 | Layer 3は明示的有効化 |

---

## 成功基準（修正版）

### 機能要件
- [x] 既存TagSearcher/TagCleaner APIの100%互換
- [x] オフライン動作（Layer 1/2で95%以上のクエリ対応）
- [x] 3データソース統合（genai-tag-db-tools, deepghs/site_tags, isek-ai/danbooru-wiki-2024）
- [x] 初回セットアップ5分以内

### 非機能要件
- [x] Layer 1応答: 10-50ms (95%ile)
- [x] Layer 2応答: 200-500ms (95%ile)
- [x] ディスク使用: 329MB（通常時）、829MB以下（拡張時）
- [x] メモリ使用: 800MB以下（ピーク時）
- [x] テストカバレッジ: 75%以上
- [x] HFデータ完全性: 100%（全タグ993,514件）
- [x] ローカルカバレッジ: 99.98%（count >= 2フィルタ）

### ライセンス・法務要件
- [x] CC-BY-SA 4.0適用（統合データセット）
- [x] MITライセンス維持（処理ロジック）
- [x] データソースクレジット明記（Dataset Card）

---

## 新規リポジトリ構造案

### NEXTAltair/genai-unified-tag-dataset

```
genai-unified-tag-dataset/
├── README.md                    # Dataset Card (ライセンス・クレジット)
├── LICENSE                      # CC-BY-SA 4.0全文
├── scripts/                     # データ生成スクリプト（再現性確保）
│   ├── export_tags_v4.py       # tags_v4.db → Parquet
│   ├── extract_deepghs_tags.py # deepghs/site_tags抽出
│   ├── extract_danbooru_wiki.py # danbooru-wiki統合
│   ├── merge_all_sources.py    # 3ソース統合
│   ├── verify_integrity.py     # 整合性検証
│   └── utils/
│       ├── tag_normalizer.py   # TagCleaner互換の正規化
│       └── schema_mapper.py    # format_id/type_idマッピング
├── tests/                       # データ品質テスト
│   ├── test_dataset_integrity.py
│   ├── test_schema_validation.py
│   └── test_statistics.py
├── data/                        # 中間生成ファイル（.gitignore）
│   ├── genai_core_tags.parquet
│   ├── deepghs_new_tags.parquet
│   ├── danbooru_wiki_enrichment.parquet
│   └── unified_tags_full.parquet  # 最終出力（HFにアップロード）
├── outputs/                     # 検証結果
│   ├── integrity_report.json
│   ├── statistics_summary.json
│   └── sha256.txt
├── pyproject.toml              # 依存管理（uv）
└── .github/
    └── workflows/
        └── update_dataset.yml  # 月次更新CI（オプション）
```

### 依存ライブラリ
```toml
# pyproject.toml
[project]
name = "genai-unified-tag-dataset"
version = "1.0.0"
description = "Dataset generation scripts for genai-tag-db-tools unified tag database"
requires-python = ">=3.12"

dependencies = [
    "polars>=1.0.0",
    "datasets>=2.14.0",
    "duckdb>=1.0.0",
    "pyarrow>=14.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.4.0",
]
```

### 実行手順（README記載予定）
```bash
# 1. 環境セットアップ
git clone https://github.com/NEXTAltair/genai-unified-tag-dataset
cd genai-unified-tag-dataset
uv sync

# 2. データ生成（ワンショット実行）
uv run python scripts/export_tags_v4.py \
  --input /path/to/tags_v4.db \
  --output data/genai_core_tags.parquet

uv run python scripts/extract_deepghs_tags.py \
  --output data/deepghs_new_tags.parquet

uv run python scripts/extract_danbooru_wiki.py \
  --output data/danbooru_wiki_enrichment.parquet

uv run python scripts/merge_all_sources.py \
  --output data/unified_tags_full.parquet

# 3. 整合性検証
uv run python scripts/verify_integrity.py \
  --input data/unified_tags_full.parquet \
  --output outputs/

# 4. HuggingFaceアップロード
huggingface-cli upload \
  NEXTAltair/genai-unified-tag-dataset \
  data/unified_tags_full.parquet \
  --repo-type dataset
```

## 次のステップ

1. **ユーザー承認**: 本計画v2.2のレビューと承認
2. **追加相談事項の確認**: ユーザーが相談したい内容のヒアリング
3. **Phase 1開始準備**: 新規リポジトリ作成・依存関係セットアップ
4. **継続的更新**: 実装中の発見に基づく計画の段階的改善

## v2.1での主要変更点

### 2層構造の採用
- **HFデータセット**: 全タグ993,514件（閾値なし、215MB）
  - 用途: 研究者・開発者向け完全データ、将来的な解析
  - 完全性: 100%のデータ保持
  
- **ローカルキャッシュ**: count >= 2タグ527,923件（114MB）
  - 用途: アプリケーション実行時の高速検索
  - カバレッジ: 99.98%
  - フィルタ理由: 1回使用タグ（誤入力・テストタグ可能性）除外

### リソース使用量
- **ディスク**: 329MB（通常時）= 114MB（キャッシュ）+ 215MB（HF完全データ）
- **ダウンロード**: 215MB（HFから全タグ取得）
- **初回セットアップ**: ローカルでcount >= 2フィルタ実行

---

## 変更履歴

- **v1.0 (2025-12-13初版)**: 初期計画（技術的課題未解決）
- **v2.0 (2025-12-13改訂)**: 以下の問題を全面解決
- **v2.1 (2025-12-13改訂)**: 2層データ構造の採用
  - HFデータセット: 全タグ保持（993,514件、研究者向け完全データ）
  - ローカルキャッシュ: count >= 2フィルタ（527,923タグ、99.98%カバレッジ）
  - ディスク使用量: 329MB（通常時）= 114MB（キャッシュ）+ 215MB（HF）
  - HFデータ規模とI/O前提の明確化
  - オフライン完結設計への転換
  - メモリ/ディスク見積りの現実的再計算
  - 初期同期フローの詳細化（リトライ・ロールバック含む）
  - スキーマ統合ポリシーの具体化
  - API互換性検証ケースの抽出
  - 同期・更新戦略の実装詳細
  - ライセンス制約の明記
  - SLAの現実的修正
- **v2.2 (2025-12-13改訂)**: 既存実装分析と処理フロー明確化
  - 既存スクリプト分析結果追加（hf_to_sqlite_tag_transfer.py, migrate_v3_to_v4.py）
  - データ処理フロー詳細化（Polars + TagCleaner + TagRegister + TagRepository）
  - 既存CSVの扱い決定: **Option A（tags_v4.db逆エクスポート）採用**
    - 理由: ライセンスリスク最小化、実装容易性、データ完全性保証
    - Dataset Card: 「genai-tag-db-toolsから派生」として記載
  - Phase 1実装ステップの具体化（既存パターン活用）
  - 処理時間見積: tags_v4.db逆エクスポート（2-3時間）、統合処理（4-5時間）
  - 新規リポジトリ名確定: NEXTAltair/genai-unified-tag-dataset
