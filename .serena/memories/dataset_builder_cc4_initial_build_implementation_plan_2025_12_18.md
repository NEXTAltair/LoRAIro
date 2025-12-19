# CC4 初回ビルド実装計画（LoRAIro-cc4-dataset / feature/cc4-dataset-build）

## 目的（このワークツリーのスコープ）
- **初回 CC4 版**（CC-BY-4.0）をローカルで作成し、HFへ手動アップロードできる状態にする。
- ベースDBは **ローカルの CC0 版** `genai-image-tag-db-cc0.sqlite` を使用（HFからダウンロードしない）。
- deepghs/site_tags（18サイト・12スキーマ）を統合し、SQLite + Parquet（danbooru view）+ README を生成する。

## スコープ外（別ワークツリー）
- HF上のCC0/MIT/CC4をベースにした「更新専用」自動化フロー。

---

## 前提（既存実装の再利用ポイント）
- `builder.py`
  - `--base-db` で Phase 0/1 をスキップできる（CC0 SQLite コピー → 追記）
  - `--skip-danbooru-snapshot-replace` がある（CC0 の Danbooru authoritative snapshot を保持する目的）
  - Parquet export（danbooru view / 全テーブル）が既に実装済み
- Adapter 構造は `BaseAdapter`（read/validate/repair）で統一されている
- `master_data.py`
  - deepghs/site_tags 用に format_id 4-18 が予約済み
  - `TAG_TYPE_FORMAT_MAPPING` の準備済み（不足はレポート+後追い修正方針）
- マイグレーション
  - 初回CC4は「**migration適用済みCC0**」を base とする（このワークツリーで migration を走らせない）

---

## 1) SiteTags_Adapter 設計（新規）

### 1-1. 役割
- deepghs/site_tags 配下の各サイトディレクトリ（例: `danbooru.donmai.us/`）を入力として、統合DBへ投入可能な中間表へ変換する。
- 基本は **SQLite（tags.sqlite / tag_aliases等）優先**。
- ただし「同じ site_tags データソース内」に **SQLite以外（CSV/JSON/Parquet）のほうが情報が豊富な場合**（例: 多言語 `trans_*`、親子/関連ID等）は、初回CC4でも必要な範囲だけ追加で読む。
  - 目的は“便利だから”ではなく、**ソース側に存在する言語は全部取り込む**ため。
- git-lfs の警告は「データが取得できない」等の実害が無い限り無視する。

### 1-2. 実装形（BaseAdapter継承）
- 新規: `src/genai_tag_db_dataset_builder/adapters/site_tags_adapter.py`
  - `class SiteTagsAdapter(BaseAdapter)`
  - `read(path: Path) -> pd.DataFrame` で、サイト単位（ディレクトリ単位）を入力として扱う
  - `validate/repair` は「変換不能・欠損・矛盾」を **レポート化してスキップ/縮退**（初回は過剰に止めない）

### 1-3. 12種類のスキーマ署名対応
- 方式: `schema_signature = (table_names, columns_by_table)` から分岐
- 各分岐は「**最低限必要な共通フィールド**」を作れることをゴールにする（不足は NULL / レポート）

共通に揃える最小フィールド（中間表）:
- `source_tag`（原表記）
- `format_name`（サイト→format名のマッピング）
- `type_raw`（サイト固有の category/type の生値）
- `count`（post_count/num/posts 等）
- `is_deprecated`（取れるなら）
- `source_created_at` / `source_updated_at`（取れるなら。用途は Phase 6.6 の意味論に従う）
- `alias_pairs`（alias→tag、取れるなら）
- `translations`（`tag_jp` 等、取れるなら）

### 1-4. format_name マッピング
- `.serena/memories/dataset_builder_phase6_5_cc4_local_build_plan_2025_12_17.md` の `SITE_TO_FORMAT_NAME` を採用。
  - 例外を含む: `en.pixiv.net -> pixiv`, `chan.sankakucomplex.com -> sankaku`, `booru.allthefallen.moe -> allthefallen`, `anime-pictures.net -> anime-pictures`

### 1-5. Type / category mapping 適用
- 方針: 「サイト固有のtype/category生値」→ 統合DBの `type_id` へ変換
- ソース: `.serena/memories/dataset_builder_deepghs_site_tags_type_category_mappings_2025_12_18.md`
- 未確定・未知値は `type_id=-1 (fallback_unknown)` へ落とし、`type_category_unknown.tsv` に出す

### 1-6. alias / deprecated の取り込み方針
- alias（推奨先）
  - 文字列ベースの alias テーブル（`tag_aliases(alias, tag)` 等）を取り込み、統合DBでは `TAG_STATUS.alias=true` で表現
  - `preferred_tag_id` は推奨先（tag）を指す
- 無効タグ吸い込み（`invalid_tag` / `bad_tag` 等）
  - **redirectしない**（このDBで誘導しない）
  - alias元（非推奨タグ側）を `deprecated=true` として保持し、`alias=false` / `preferred_tag_id=tag_id`
- `is_deprecated` があるサイト（Danbooru等）
  - `TAG_STATUS.deprecated=true` を入れる
  - `deprecated_at` は取得できない場合 NULL

### 1-7. 日付の扱い
- 目標: "カウントの観測日時" / "非推奨になった日" / "ホスティングサイトに登録された日" を、取れる範囲でDBに入れる。

- `TAG_STATUS.source_created_at`
  - ソース側に `created_at` がある場合はそれを入れる（= ホスティングサイト登録日として扱う）。
  - 取れない場合は `NULL`（ビルド時刻で埋めない）。

- `TAG_STATUS.deprecated_at`
  - ソース側に「非推奨化の日時」を直接持つケースは少ないため、原則 `NULL`。
  - ただし `is_deprecated=1` かつ `updated_at` 等がある場合は、それを deprecated_at として採用してよい（= 非推奨化の近似）。

- `TAG_USAGE_COUNTS.created_at/updated_at`
  - 可能なら「そのcount値の観測日時」として `source_updated_at`（ソース側の updated_at 等）を採用。
  - 取れない場合は既存運用（NULL or 既定）。

---

## 2) include_cc4_sources.txt 設計

### 2-1. 目的
- CC4 版では **CC0 base DB** に対して「CC4差分（deepghs/site_tags）」のみを追記する。
- したがって include リストは deepghs/site_tags の対象ディレクトリ（18サイト）だけを列挙する。

### 2-2. 形式案
- `license_builds/include_cc4_sources.txt` を追加
- 記載例（ディレクトリ指定でOK）:
  - `external_sources/site_tags/danbooru.donmai.us/`
  - `external_sources/site_tags/e621.net/`
  - ...（18件）

### 2-3. CC0との差分明確化
- CC0 由来（tags_v4.db / ローカルCSV）は **このワークツリーでは触らない**（base-db 側にすべて含まれる）。
- CC4 で増えるのは「site_tags由来の format_id 4-18 を中心とした TAG_STATUS / TAG_USAGE_COUNTS / 翻訳など」。

---

## 3) ビルドコマンド設計（初回 CC4）

### 3-1. ベースDB
- `--base-db` は **ローカルでビルド済み CC0** を指定
  - 例: `.../out_db_cc0/genai-image-tag-db-cc0.sqlite`

### 3-2. --skip-danbooru-snapshot-replace の要否
- **要（付ける）**:
  - CC0版で authoritative Danbooru snapshot を既に適用済み。
  - site_tags 側にも danbooru が含まれるため、ここで再度の「置換」を走らせると CC0の前提を崩す可能性がある。
  - 初回CC4は「CC0保持 + site_tags追加」に集中する。

### 3-3. --include-sources
- `--include-sources license_builds/include_cc4_sources.txt` を使う
- `--sources` は LoRAIro ルート（`C:\LoRAIro`）にしておき、include で site_tags 配下だけ拾う形に統一（既存の挙動に合わせる）

### 3-4. Parquet出力
- CC0/MITと揃えて `--parquet-dir out_db_cc4/parquet_danbooru`
- 初回は danbooru view のみ（目的: HF Dataset Viewerでサンプル表示）。

---

## 4) README生成方針（CC4）

### 4-1. frontmatter
- `license: cc-by-4.0`
- `language`: **実際に取り込んだ言語コードの一覧**（ビルド後に `SELECT DISTINCT language FROM TAG_TRANSLATIONS` で確定し、frontmatterへ反映）
  - 例: `en, ja, zh, ko, ru, pt, fr, it, vi, de, es, th, ...`
- `configs.data_files: parquet_danbooru/*.parquet`

### 4-2. 帰属表記（重要）
- 「CC0 base（genai-image-tag-db-cc0.sqlite）」をベースにしていること
- deepghs/site_tags を取り込んでいること（URL、取得日/コミットshaは README に記載）

### 4-3. Schema説明
- CC0 README の schema 説明を継承
- 追加列（`TAG_STATUS.deprecated/deprecated_at/source_created_at`）の意味を明記

### 4-4. CC-BY-4.0説明
- 再配布条件（クレジット/表示/改変表示等）を簡潔に
- 具体的な出典（deepghs/site_tags）URLを含める

---

## 5) 実装順序（どこから触るか）

1. `license_builds/include_cc4_sources.txt` の追加（18サイトを列挙し、拾う範囲を固定）
2. `SiteTagsAdapter` 骨格作成（サイトディレクトリ→tags.sqlite等の検出）
3. schema signature の抽出と分岐枠組み（12スキーマ対応の器）
4. type/category mapping 適用（全サイト対応。未知は `fallback_unknown` + レポート）
5. 多言語翻訳の取り込み（存在する言語は全部。SQLiteで足りなければ JSON/CSV を補助的に読む）
6. alias/deprecated の取り込み（invalid_tag/bad_tag への redirect はしない）
7. builder 側の source discovery に SiteTagsAdapter を登録
8. CC4ビルド（**最初から18サイト全部**を対象に実行）
9. レポート確認（unknown type, alias欠損等）→ 必要ならマッピング追加
10. CC4 README作成（frontmatter含む、CC0ベース + deepghs/site_tags の帰属を明記）

---

## 6) テスト戦略

前提:
- 実装としては **最初から18サイトを取り込める**形にする。
- ただし検証は段階的に行い、原因切り分けを容易にする。

検証の段階:
- Unit（最小）: schema signature 分岐ロジック（12パターン）を、少量フィクスチャ（SQLiteの schema だけ）で検証
- Integration（中）: 代表サイト（danbooru/e621/sankaku/gelbooru/anime-picturesなど）の sqlite を使って read→変換→投入まで
- Full（重）: 18サイトでCC4ビルド（build→PRAGMA integrity_check/quick_check）

最低限の自動検証:
- `PRAGMA integrity_check` / `quick_check`
- 主要テーブルの行数増加が妥当か（ゼロ/極端な減少は失敗扱い）
- レポート出力が存在し、件数が把握できること（unknown type / alias欠損等）

---

## 7) リスク管理

- **R1: 12スキーマ対応の複雑さ**
  - 対策: 「共通中間表」方式＋ signature 分岐。未知は fallback + レポートで止めない。
- **R2: type/category mapping の不確定**（例: anime-pictures 5/6/7）
  - 対策: unknown は `fallback_unknown` に落とし、レポートで後追い。
- **R3: データ量（約4.86GiB）**
  - 対策: SQLite優先で読み、必要最小カラムのみ抽出。最初は danbooru/e621/sankaku から段階追加。
- **R4: alias先欠損/無効タグ吸い込み**
  - 対策: redirectしないポリシーで deprecated 化 + レポート。
- **R5: 多言語の取り込み元が SQLite に無いサイトがある**
  - 対策: 同一 site_tags 内の JSON/CSV を補助的に読み、`trans_*` / `tag_jp` 等がある場合は翻訳として取り込む（なければ欠落でOK）。
  - 対策: redirectしないポリシーで deprecated 化 + レポート。

---

## 出力（初回CC4の成果物）
- `out_db_cc4/genai-image-tag-db-cc4.sqlite`
- `out_db_cc4/parquet_danbooru/*.parquet`
- `out_db_cc4/README.md`
- レポート一式（例: `source_effects.tsv`, `type_category_unknown.tsv`, `alias_*`）

---

## 未確定（ユーザー確認が必要ならここに追記）
- CC4版のHFリポジトリ名（`NEXTAltair/genai-image-tag-db-cc4` で良いか等）
