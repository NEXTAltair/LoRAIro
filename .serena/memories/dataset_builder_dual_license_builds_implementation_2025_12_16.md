# Dataset Builder - Dual License Builds Implementation

## 実装日
2025年12月16日

## 概要

CC0版とMIT版の2つのライセンス別ビルドを作成するため、以下の機能を実装しました：

1. **HuggingFace翻訳データアダプタ** - CC0ライセンスの日本語翻訳データ取り込み
2. **tags_v4.dbスキップ機能** - MIT版でtags_v4.dbを除外
3. **Danbooruスナップショット対応** - 最新のcount値を完全置換
4. **ライセンス別ソースフィルタ** - include/exclude リストによる柔軟な制御

---

## 1. 新規ファイル

### 1.1 HuggingFace翻訳アダプタ

**ファイル**: `src/genai_tag_db_dataset_builder/adapters/hf_translation_adapter.py` (103行)

**クラス**: `P1atdevDanbooruJaTagPairAdapter`

**目的**: 
- `p1atdev/danbooru-ja-tag-pair-20241015` 形式のHFデータセットから日本語翻訳を取り込み
- CC0ライセンスの翻訳データをPhase 1.5で追加

**主要機能**:
```python
@dataclass(frozen=True)
class P1atdevDanbooruJaTagPairAdapter:
    repo_id_or_path: str
    revision: str | None = None
    split: str | None = None
    language: str = "ja"
    
    def read(self) -> pl.DataFrame:
        # ローカル or HFリモートから自動判定
        # カラム名の柔軟な推定（tag/source_tag/danbooru_tag）
        # カンマ区切り翻訳の展開（"魔女, ウィッチ" → 2行）
        # 返り値: DataFrame(source_tag, japanese)
```

**カラム名推定**:
- Tag列候補: `tag`, `source_tag`, `danbooru_tag`, `title`
- 翻訳列候補: `japanese`, `ja`, `jp`, `translation`, `other_names`

**対応スキーマ（実データ確認済み）**:
- `p1atdev/danbooru-ja-tag-pair-20241015` は `title` がタグ、`other_names` が翻訳候補（list）として入っている。
- `is_deleted=True` の行は翻訳として取り込まない。

**翻訳の複数展開**:
- `"魔女, ウィッチ"` → `["魔女", "ウィッチ"]` として2つのレコード生成
- 表現揺れを許容（TAG_TRANSLATIONS の UNIQUE(tag_id, language, translation)）

**テスト**: `tests/unit/test_hf_translation_adapter.py`

### 1.2 ライセンス別ビルド設定

**ディレクトリ**: `license_builds/`

#### README.md
- CC0版/MIT版のビルドコマンド例
- `--skip-tags-v4` フラグの説明

#### include_cc0_sources.txt (5ファイル)
```
TagDB_DataSource_CSV/danbooru_241016.csv
TagDB_DataSource_CSV/TAG_FORMATS_202407081830.csv
TagDB_DataSource_CSV/TAG_TYPES_202407081829.csv
TagDB_DataSource_CSV/FORMAT_TAG_TYPES_202407081829.csv
TagDB_DataSource_CSV/translation/Tags_zh_full.csv
```

**方針**: tags_v4.db（自家製、CC0-1.0）+ 最小限のCSVソース

#### include_mit_sources.txt (12ファイル)
```
TagDB_DataSource_CSV/A/danbooru_machine_jp.csv
TagDB_DataSource_CSV/A/danbooru_klein10k_jp.csv
TagDB_DataSource_CSV/A/danbooru.csv
TagDB_DataSource_CSV/A/derpibooru.csv
TagDB_DataSource_CSV/A/e621.csv
TagDB_DataSource_CSV/A/e621_sfw.csv
TagDB_DataSource_CSV/A/EnglishDictionary.csv
TagDB_DataSource_CSV/A/rising_v2.csv
TagDB_DataSource_CSV/A/dataset_rising_v2.csv
TagDB_DataSource_CSV/rising_v3.csv
TagDB_DataSource_CSV/TagsList-Easter-e5.csv
TagDB_DataSource_CSV/TagsList-Easter-Final.csv
```

**方針**: tags_v4.dbをスキップ、MITライセンスのCSVのみ

---

## 2. builder.py の主要変更 (227行追加)

### 2.1 新規パラメータ

```python
def build_dataset(
    output_path: Path | str,
    sources_dir: Path | str,
    version: str,
    report_dir: Path | str | None = None,
    overrides_path: Path | str | None = None,
    include_sources_path: Path | str | None = None,
    exclude_sources_path: Path | str | None = None,
    skip_tags_v4: bool = False,  # NEW
    hf_ja_translation_datasets: list[str] | None = None,  # NEW
    overwrite: bool = False,
) -> None:
```

**skip_tags_v4**: tags_v4.db の取り込みをスキップ（MIT版用）
**hf_ja_translation_datasets**: HF datasets リスト（例: `["p1atdev/danbooru-ja-tag-pair-20241015"]`）

### 2.2 Phase 1の変更（tags_v4.dbスキップ対応）

```python
# tags_v4.db の取り込みを条件分岐
tags_v4_path = None
if not skip_tags_v4:
    tags_v4_path = _first_existing_path([
        sources_dir / "tags_v4.db",
        sources_dir / "TagDB_DataSource_CSV" / "tags_v4.db",
        sources_dir / "local_packages" / "genai-tag-db-tools" / ... / "tags_v4.db",
    ])
    
if tags_v4_path:
    logger.info(f"[Phase 1] Importing tags_v4.db from {tags_v4_path}")
    # 通常の取り込み処理
else:
    if skip_tags_v4:
        logger.warning("[Phase 1] tags_v4.db import skipped, starting from empty")
    else:
        logger.warning("[Phase 1] tags_v4.db not found, starting from empty")
    next_tag_id = 1
    existing_tags = set()
```

**動作**:
- `--skip-tags-v4` 指定時は tags_v4.db を探さずスキップ
- 空のDBから開始（next_tag_id=1, existing_tags=set()）

### 2.3 Phase 1.5の追加（HF翻訳取り込み）

```python
# Phase 1.5: Hugging Face datasets から翻訳（日本語）を取り込む（任意）
if hf_ja_translation_datasets:
    logger.info(f"[Phase 1.5] Importing HF JA translations: {len(hf_ja_translation_datasets)} dataset(s)")
    for repo_id in hf_ja_translation_datasets:
        source_name = f"hf://datasets/{repo_id}"
        try:
            df_hf = P1atdevDanbooruJaTagPairAdapter(repo_id).read()
        except Exception as e:
            logger.warning(f"[Phase 1.5] Failed to load translations from {source_name}: {e}")
            continue
        
        trans_rows = _extract_translations(df_hf, tags_mapping)
        if not trans_rows:
            logger.warning(f"[Phase 1.5] No translations extracted from {source_name}")
            continue
        
        for tag_id, language, translation in trans_rows:
            conn.execute(
                "INSERT OR IGNORE INTO TAG_TRANSLATIONS (tag_id, language, translation) VALUES (?, ?, ?)",
                (tag_id, language, translation),
            )
        conn.commit()
        logger.info(f"[Phase 1.5] Imported translations: {source_name} (rows={len(trans_rows)})")
```

**動作**:
- tags_mapping 構築後（Phase 1完了後）に実行
- HFからDataFrame取得 → `_extract_translations()` で (tag_id, language, translation) に変換
- `INSERT OR IGNORE` で重複許容（表現揺れ対応）

### 2.4 Phase 2の変更（Danbooruスナップショット対応）

**新規関数**:

```python
def _infer_source_timestamp_utc_midnight(path: Path) -> str | None:
    """ファイル名から日付推定（danbooru_241016.csv → 2024-10-16 00:00:00+00:00）."""
    # _(\d{8}) パターン検出（例: _20241016）
    # _(\d{6}) パターン検出（例: _241016）
    # UTCの00:00:00に固定したタイムスタンプ文字列を返す

def _is_authoritative_count_source(path: Path) -> bool:
    """最新スナップショットとしてcountを上書きするソースか判定."""
    # ^danbooru_\d{6,8}\.csv$ にマッチするか

def _select_latest_count_snapshot(paths: list[Path]) -> tuple[Path, str] | None:
    """countの最新スナップショットを選択."""
    # タイムスタンプでソート → 最新を返す

def _replace_usage_counts_for_format(
    conn: sqlite3.Connection,
    *,
    format_id: int,
    counts_by_tag_id: dict[int, int],
    timestamp: str,
) -> None:
    """TAG_USAGE_COUNTS の特定format_idをスナップショットで置換."""
    conn.execute("DELETE FROM TAG_USAGE_COUNTS WHERE format_id = ?", (format_id,))
    # 一括INSERT（created_at/updated_at を timestamp で統一）
```

**Phase 2での適用**:

```python
# 最新Danbooruスナップショット検出
csv_files = sorted(csv_dir.rglob("*.csv"))
danbooru_snapshot = _select_latest_count_snapshot(csv_files)
has_authoritative_danbooru_counts = danbooru_snapshot is not None

if danbooru_snapshot_path and danbooru_snapshot_ts:
    logger.info(f"[Phase 2] Danbooru count snapshot detected: {danbooru_snapshot_path.name} "
                f"(timestamp={danbooru_snapshot_ts}). "
                "TAG_USAGE_COUNTS(format_id=1) をスナップショットで置換します。")

# CSV処理ループ内
for csv_path in csv_files:
    is_authoritative_counts = (danbooru_snapshot_path is not None 
                               and csv_path == danbooru_snapshot_path)
    
    # usage_count処理
    if is_authoritative_counts:
        # スナップショット: 蓄積だけ（最後に一括置換）
        for tag_id, format_id, count in usage_rows:
            if format_id != 1:
                continue
            danbooru_snapshot_counts[tag_id] = max(
                danbooru_snapshot_counts.get(tag_id, 0), count
            )
    else:
        # 非スナップショット: format_id=1 の count は無視
        if fmt_i == 1 and has_authoritative_danbooru_counts and not is_authoritative_counts:
            continue
        # 通常の max マージ処理

# CSVループ終了後
if danbooru_snapshot_counts:
    _replace_usage_counts_for_format(
        conn,
        format_id=1,
        counts_by_tag_id=danbooru_snapshot_counts,
        timestamp=danbooru_snapshot_ts,
    )
```

**動作**:
1. `danbooru_241016.csv` などの最新スナップショットを検出
2. スナップショットからの count は蓄積
3. 他のソースから format_id=1 の count が来ても無視
4. 最後に format_id=1 の TAG_USAGE_COUNTS を DELETE → INSERT で完全置換
5. created_at/updated_at をスナップショット日時で統一

---

## 3. ビルドコマンド

### 3.1 CC0版（tags_v4.db を含む）

```powershell
.\.venv\Scripts\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\out_db_cc0\genai_tag_db.sqlite `
  --sources . `
  --report-dir .\out_db_cc0 `
  --include-sources .\license_builds\include_cc0_sources.txt `
  --overwrite
```

**含まれるデータ**:
- tags_v4.db（自家製、CC0-1.0）
- danbooru_241016.csv（最新スナップショット）
- TAG_FORMATS/TAG_TYPES/FORMAT_TAG_TYPES（マスタ）
- Tags_zh_full.csv（中国語翻訳）

**HF翻訳追加例**:
```powershell
# --hf-ja-translation 引数でHF datasetを指定（繰り返し指定可）
.\.venv\Scripts\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\out_db_cc0\genai_tag_db.sqlite `
  --sources . `
  --report-dir .\out_db_cc0 `
  --include-sources .\license_builds\include_cc0_sources.txt `
  --hf-ja-translation p1atdev/danbooru-ja-tag-pair-20241015 `
  --overwrite
```

### 3.2 MIT版（tags_v4.db をスキップ）

```powershell
.\.venv\Scripts\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\out_db_mit\genai_tag_db.sqlite `
  --sources . `
  --report-dir .\out_db_mit `
  --include-sources .\license_builds\include_mit_sources.txt `
  --skip-tags-v4 `
  --overwrite
```

**含まれるデータ**:
- tags_v4.db なし
- A/ディレクトリ配下のCSV（MIT）
- rising_v3.csv, TagsList-Easter-*.csv（MIT）

---

## 4. 設計判断

### 4.1 tags_v4.db の扱い

**CC0版**:
- tags_v4.db を含める（自家製DBとして CC0-1.0 でライセンス）
- Phase 1で通常通り取り込み

**MIT版**:
- `--skip-tags-v4` フラグで tags_v4.db をスキップ
- 空のDBから開始（next_tag_id=1）

### 4.2 Danbooru count の扱い

**問題**: 複数ソースから異なる時期の count が来ると、古い値で上書きされる可能性

**解決策**:
- 最新スナップショット（`danbooru_241016.csv`）を検出
- format_id=1 の TAG_USAGE_COUNTS を**完全置換**（max マージではなく）
- タイムスタンプをファイル名から推定して統一

**利点**:
- スナップショット時点の正確な count を保証
- created_at/updated_at が統一される

### 4.3 HF翻訳データの取り込み

**Phase 1.5の位置付け**:
- Phase 1（tags_v4.db）の後、Phase 2（CSV）の前
- tags_mapping が既に構築されている前提

**INSERT OR IGNORE の理由**:
- 表現揺れを許容（"魔女", "ウィッチ" 両方を登録）
- UNIQUE(tag_id, language, translation) で重複排除

### 4.4 ソースフィルタリング

**既存機能**:
- `--exclude-sources` でブラックリスト指定（既存）

**新規機能**:
- `--include-sources` でホワイトリスト指定（Phase 2で追加済み）

**優先順位**:
1. `--include-sources` にマッチするか？ → No なら除外
2. `--exclude-sources` にマッチするか？ → Yes なら除外
3. 両方ない場合は全て含める

---

## 5. テスト状況

### 5.1 全体テスト結果
```
============================= 125 passed ==============================
```

### 5.2 新規テスト

**test_hf_translation_adapter.py**:
- HFデータセット読み込み（ローカル/リモート）
- カラム名推定
- カンマ区切り翻訳の展開
- エラーハンドリング

**test_usage_count_snapshot_replace.py**:
- スナップショット検出
- タイムスタンプ推定
- count 完全置換

**test_source_filters.py** (既存に追加):
- `_should_include_source()` のテスト
- `_infer_source_timestamp_utc_midnight()` のテスト
- `_is_authoritative_count_source()` のテスト

---

## 6. 実装完了ファイル

### 新規作成
1. `src/genai_tag_db_dataset_builder/adapters/hf_translation_adapter.py` (103行)
2. `license_builds/README.md` (35行)
3. `license_builds/include_cc0_sources.txt` (6行)
4. `license_builds/include_mit_sources.txt` (12行)
5. `tests/unit/test_hf_translation_adapter.py`
6. `tests/unit/test_usage_count_snapshot_replace.py`

### 変更ファイル
1. `src/genai_tag_db_dataset_builder/builder.py` (+227行)
2. `src/genai_tag_db_dataset_builder/adapters/__init__.py` (+2行)
3. `tests/unit/test_source_filters.py` (+13行)

---

## 7. 今後の作業

### HFアップロード
1. CC0版ビルド実行 → `out_db_cc0/genai_tag_db.sqlite` 生成
2. MIT版ビルド実行 → `out_db_mit/genai_tag_db.sqlite` 生成
3. HuggingFaceへのアップロード
   - `NEXTAltair/genai-tag-db-unified-cc0`
   - `NEXTAltair/genai-tag-db-unified-mit`

### メタデータ生成
- `metadata.py` で統計情報生成
- Dataset Card 作成（ライセンス別）

---

## 8. 関連メモリ

- `dataset_builder_design_plan_2025_12_13`
- `dataset_builder_phase2_5_implementation_plan_2025_12_14`
- `dataset_builder_phase2_5_completion_report_2025_12_14`
- `dataset_builder_tag_database_hybrid_architecture_pattern_2025_12_13`

---

**実装者**: Claude Sonnet 4.5  
**実装日**: 2025年12月16日  
**ステータス**: ✅ 実装完了、テスト全PASS
