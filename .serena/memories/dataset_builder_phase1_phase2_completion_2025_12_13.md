# Dataset Builder Phase 1 & Phase 2 完了記録

## 完了日
2025年12月13日

## 作業概要
Phase 1（アダプタ実装）とPhase 2（マージロジック実装）を完了

---

## Phase 1: アダプタ実装 ✅

### 実装済みアダプタ

**1. BaseAdapter（抽象クラス）**:
- `read()`, `validate()`, `repair()` 抽象メソッド定義
- `STANDARD_COLUMNS` 標準列定義
- 全アダプタの基底クラス
  - `read()` は単一DataFrame（通常）または複数テーブル辞書（tags_v4等）を返し得る

**2. Tags_v4_Adapter**:
- tags_v4.dbからPolars DataFrameへエクスポート
- `read()`: 全テーブル読み込み（TAGS, TAG_STATUS, TAG_TRANSLATIONS, TAG_USAGE_COUNTS）
- `get_existing_tags()`: 既存タグのset取得（merge_tags用）
- `get_next_tag_id()`: 次のtag_id取得（max+1）

**3. CSV_Adapter**:
- 汎用CSVパーサー（壊れたCSVの修復機能付き）
- `repair_mode="derpibooru"`: format_id=3補完
- `repair_mode="dataset_rising_v2"`: 90%以上null列削除
- `repair_mode="english_dict"`: fomat_id→format_idリネーム
- `read()`: Polars.read_csvでtruncate_ragged_lines対応

**4. JSON_Adapter**:
- JSONファイル読み込み（r34-e4_tags_タグリスト.json用）
- `read()`: json.load → Polars DataFrame変換

**5. Parquet_Adapter**:
- Parquetファイル読み込み（deepghs/site_tags, danbooru-wiki-2024用）
- `read()`: Polars.read_parquet

### テスト実装

**test_tags_v4_adapter.py**:
- unit: 存在しないファイルのFileNotFoundErrorテスト
- integration: 実際のtags_v4.db読み込みテスト（skip可能）
  - integration の tags_v4.db 解決順:
    - `GENAI_TAG_DB_TOOLS_DB_PATH`（明示パス）
    - LoRAIroワークスペース内の `local_packages/genai-tag-db-tools/.../tags_v4.db`
    - `GENAI_TAG_DB_TOOLS_ALLOW_DOWNLOAD=1` かつ `GENAI_TAG_DB_TOOLS_DB_URL` 指定時にダウンロード（GitHub Releases等の“直接DL URL”推奨）

**test_csv_adapter.py** (7テスト):
- 初期化エラーテスト
- derpibooru修復テスト
- dataset_rising_v2修復テスト
- EnglishDictionary修復テスト
- validate系テスト（有効/無効/空DataFrame）

---

## Phase 2: マージロジック実装 ✅

### 実装済み関数

**1. merge_tags()**:
- **アルゴリズム**: set差分方式（巨大JOINなし）
- **処理フロー**:
  1. source_tagを正規化してtag列生成
  2. 既存tagとの差分抽出（~pl.col("tag").is_in(existing_tags)）
  3. 重複除去（unique(subset=["tag"])）
  4. tagでソート（再現性確保）
  5. tag_id採番（max+1から連番、with_row_index使用）
- **返却値**: tag_id, tag, source_tag列のDataFrame

**2. process_deprecated_tags()**:
- **処理フロー**:
  1. canonical自身のレコード生成（alias=0, preferred_tag_id=自身）
  2. deprecated_tagsをカンマ分割
  3. 各aliasを正規化してtag_id取得
  4. aliasレコード生成（alias=1, preferred_tag_id=canonical）
- **返却値**: TAG_STATUSレコードのリスト

**3. detect_conflicts()**:
- **JOINキー**: tag + format_id（tag_idは不安定なので使用しない）
- **検出項目**:
  - type_id不一致: pl.col("type_id") != pl.col("type_id_new")
  - alias変更: (pl.col("alias") == 0) & (pl.col("alias_new") == 1)
- **返却値**: type_conflicts, alias_changesの辞書

### テスト実装

**test_merge.py** (10テスト):
- `TestMergeTags`: 4テスト
  - 基本的なマージ
  - 重複排除
  - 既存タグ除外
  - 空DataFrame処理
- `TestProcessDeprecatedTags`: 3テスト
  - deprecated_tags有り
  - deprecated_tags無し
  - 存在しないalias
- `TestDetectConflicts`: 3テスト
  - type_id不一致検出
  - alias変更検出
  - 衝突無し

**全テスト結果**: 10 passed, 0 failed（`test_merge.py`）
※全体の件数はマーカー指定/実行環境で変動（integration は DB やネットワークで skip になり得る）

---

## 実装詳細

### merge_tags()の改善点

**旧設計の問題**:
- normalized列を追加してJOIN（不要な処理）
- 巨大outerJOIN前提（非効率）

**新実装**:
- TAGS.tagを同一性の基準とする（正規化済み、UNIQUE制約あり）
- 既存tagと存在チェック→不足分のみINSERT
- tagでset差分を取る（シンプル・高速）

### process_deprecated_tags()の設計

**処理順序**:
1. canonical作成: 新規タグをTAGSに追加（merge_tagsで実施）
2. alias作成: deprecated_tags列からエイリアス関係を抽出
3. TAG_STATUS付与: format単位でcanonical/aliasを登録

### detect_conflicts()の修正

**JOINキー変更**: tag_id → **tag + format_id**

**理由**:
- tag_idは採番がビルドで揺れる可能性がある
- tagは正規化済みの安定したキー

---

## ディレクトリ構造

```
src/genai_tag_db_dataset_builder/
├── __init__.py
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py
│   ├── csv_adapter.py
│   ├── json_adapter.py
│   ├── parquet_adapter.py
│   └── tags_v4_adapter.py
├── core/
│   ├── __init__.py
│   ├── normalize.py
│   └── merge.py
└── utils/
    └── __init__.py

tests/unit/
├── __init__.py
├── test_normalize.py
├── test_tags_v4_adapter.py
├── test_csv_adapter.py
└── test_merge.py
```

---

## 次のステップ: Phase 3

**Phase 3: SQLite最適化（Week 6）**:
1. create_database()実装（page_size/auto_vacuum設定）
2. optimize_database()実装（VACUUM→ANALYZE）
3. インデックス構築
4. 配布用PRAGMA設定

**Phase 4: CI/CD構築（Week 7）**:
1. GitHub Actions ワークフロー作成
2. HFアップロード機能実装
3. metadata生成機能実装
4. Dataset Card Template作成

---

## 技術的決定事項の確認

### 同一性の基準 = TAGS.tag（正規化済み）
- ✅ `UNIQUE(tag)` 制約でDB側で重複防止
- ✅ tagが同じなら同一タグと判定
- ✅ tag_idは内部連番（性能用）で公開IDにしない

### 正規化の境界
- ✅ `normalize_tag()` は入力CSV→TAGS.tagへの変換のみ
- ✅ DB内のtag列は既に正規化済みなので再正規化しない
- ✅ 二重正規化や不整合を防ぐため、この境界を厳守

### マージの簡潔化
- ✅ tagでset差分を取る（巨大JOINは不要）
- ✅ 不足分のみINSERT
- ✅ 衝突検出はtag+format_idでJOIN（tag_idは後から引く）

---

## 実装品質指標

**ユニットテスト**: 17テスト（normalize除く）
- CSV_Adapter: 7テスト
- merge: 10テスト

**コード行数**:
- adapters/: 約400行
- core/: 約250行

**設計原則遵守**:
- ✅ 全関数にdocstring付き
- ✅ type hints完備
- ✅ Google-style docstring
- ✅ 設計計画通りの実装

---

**作業者**: Claude Sonnet 4.5
**作業時間**: 2025-12-13
**ステータス**: Phase 1, 2 完了 → Phase 3 準備完了
