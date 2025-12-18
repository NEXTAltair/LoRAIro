# Dataset Builder Phase 6.5: CC4版ローカルビルド計画

## 策定日
2025年12月17日

## 概要

**目的**: deepghs/site_tags を統合した CC-BY-4.0 ライセンス版（CC4版）のローカルビルドを実施する。Phase 7（リポジトリ自動化）の前段階として、スキーマ拡張とビルドプロセスを確立する。

**スコープ**:
- 新スキーマ設計とマイグレーション実装
- CC0版の新スキーマでの再ビルド
- CC0版をベースにCC4版を差分追記
- MIT版も新スキーマで再ビルド

---

## 実装アプローチ（採用: アプローチ2）

### アプローチ2の実装順序

1. **CC0版スキーマ変更**:
   - 新スキーマ設計（TAG_STATUS列追加、site_tags対応）
   - マイグレーションスクリプト実装
   - 既存CC0版DBの新スキーマへ移行

2. **CC0版再ビルド**:
   - 新スキーマでCC0版をフルビルド
   - テスト・検証

3. **CC4版ビルド**:
   - CC0版SQLiteをベースに差分追記（`--base-db`）
   - deepghs/site_tags 統合（18サイト）
   - CC-BY-4.0 ライセンス版として出力

4. **MIT版再ビルド**:
   - 新スキーマのCC0版をベースに再ビルド
   - 既存のMIT差分ビルド戦略を流用

### 採用理由

- **スキーマ一貫性**: CC0版で新スキーマを先に確立すれば、CC4/MIT版は同じスキーマのベースを使える
- **既存パターン流用**: MIT差分ビルド戦略（`--base-db`, `--skip-danbooru-snapshot-replace`）をCC4版でも使用
- **テストの容易さ**: CC0版で新スキーマを検証してからCC4版を作成
- **データ移行の効率**: スキーマ変更1回で全ライセンス版に適用

---

## Phase 6.5の前提条件

### 完了済み調査（2025-12-17）

**deepghs/site_tags 調査結果**:
- Clone先: `C:\LoRAIro\external_sources\site_tags`（約4.86GiB）
- 18サイト分のSQLite（12種類の異なるスキーマ）
- 各サイトにCSV/JSON/Parquet形式も併存

**スキーマ分析**:
- SQLite: 12種類のユニークなスキーマ署名
- Danbooruの deprecated/alias 関係（deprecated でも置換先なし 3,221件）
- format_name 命名規則: ドメインのドット前まで（例外: `en.pixiv.net` → `pixiv`）

**生成済みファイル**:
- `.serena/memories/dataset_builder_deepghs_site_tags_investigation_log_2025_12_17.md`
- `.serena/memories/deepghs_site_tags_sqlite_schema_summary_2025_12_17.md`
- `.serena/memories/deepghs_site_tags_sqlite_schema_matrix_2025_12_17.tsv`
- `.serena/memories/deepghs_site_tags_non_sqlite_schema_summary_2025_12_17.md`
- `.serena/memories/deepghs_site_tags_non_sqlite_schema_matrix_2025_12_17.tsv`

### 既存実装の活用

**MIT差分ビルド戦略**（`dataset_builder_mit_build_strategy_update_2025_12_16.md`）:
- `--base-db`: ベースとなる既存SQLiteファイルを指定
- `--skip-danbooru-snapshot-replace`: Danbooruスナップショット置換をスキップ
- Phase 0/1（DB作成・Danbooru tags_v3.db取り込み）を自動スキップ
- CC0版をコピーして差分追記

---

## 新スキーマ設計

### スキーマ変更（最小）

方針:
- `TAG_FORMATS` は拡張しない（`source_url` 等も不要）。
- ビルド結果の出典/ライセンスは Hugging Face リポジトリ側の README で管理する。
- DB内に「道案内」が必要になった場合は、format単位ではなく **DB全体のメタデータ**として持つ（任意）。

任意（道案内用）:
- `DATABASE_METADATA(key TEXT PRIMARY KEY, value TEXT NOT NULL)`
  - 例: `build.base_db_url`, `build.base_db_revision`, `build.timestamp`, `sources.used`
  - ローカルパスは保存しない。

### deepghs/site_tags の format_name マッピング

**命名規則**（調査結果より）:
- ドメインのドット前まで: `danbooru.donmai.us` → `danbooru`
- 例外: `en.pixiv.net` → `pixiv`

**18サイトのマッピング**:
```python
SITE_TO_FORMAT_NAME = {
    "anime-pictures.net": "anime-pictures",
    "booru.allthefallen.moe": "allthefallen", # 例外
    "chan.sankakucomplex.com": "sankaku",  # 例外
    "danbooru.donmai.us": "danbooru",
    "e621.net": "e621",
    "en.pixiv.net": "pixiv",  # 例外
    "gelbooru.com": "gelbooru",
    "hypnohub.net": "hypnohub",
    "konachan.com": "konachan",
    "konachan.net": "konachan-net",
    "lolibooru.moe": "lolibooru",
    "pixiv.net": "pixiv",
    "rule34.xxx": "rule34",
    "safebooru.donmai.us": "safebooru",
    "wallhaven.cc": "wallhaven",
    "xbooru.com": "xbooru",
    "yande.re": "yandere",
    "zerochan.net": "zerochan",
}
```

### マイグレーション戦略

**既存CC0版DBの移行**:
- `TAG_STATUS.deprecated` / `TAG_STATUS.deprecated_at` / `TAG_STATUS.source_created_at` など、site_tags統合で必要な列の追加（Phase 6.6の決定に従う）。
- （任意）`DATABASE_METADATA` を追加して、DB全体のビルド情報だけ記録する。

補足（方針）:
- マイグレーションは基本「1回限りの運用」なので、ビルダーCLI（`builder.py`）に `--migrate-schema` を追加して肥大化させない。
- 代わりに `tools/migrate_db.py` を「移行専用スクリプト」として使う。

---

## 実装計画

### Phase 6.5.1: スキーマ設計とマイグレーション（Week 1、3日間）

**Day 1: スキーマ設計**

**タスク**:
- [x] site_tags統合に必要な列の最終確認（TAG_STATUSの列追加など）
- [x] マイグレーションスクリプト作成（TAG_STATUS列追加 / 任意でDATABASE_METADATA追加）
- [ ] Serenaメモリ作成: `dataset_builder_cc4_schema_design_2025_12_17`

**Day 2: マイグレーション実装**

**タスク**:
- [ ] `tools/migrate_db.py` でマイグレーション適用（`builder.py` には組み込まない）
- [ ] `migrations/*.sql` は「変更履歴の記録」として残しつつ、実行は `tools/migrate_db.py` に一本化（冪等 / 再実行可）
- [ ] マイグレーション前後の検証コマンドを固定化（`PRAGMA table_info` / `PRAGMA integrity_check`）

**Day 3: マイグレーション検証**

**タスク**:
- [x] 既存CC0版DBに対してマイグレーション実行
- [x] スキーマ検証（PRAGMA table_info で確認）
- [x] データ整合性確認（PRAGMA integrity_check）

### Phase 6.5.2: CC0版再ビルド（Week 1-2、4日間）

**Day 4-5: CC0版フルビルド**

**タスク**:
- [ ] 新スキーマでCC0版をフルビルド
- [ ] Parquet エクスポート

**Day 6-7: CC0版検証**

**タスク**:
- [ ] データ整合性検証（FK/CHECK/UNIQUE制約）
- [ ] カバレッジ測定（≥75%）
- [ ] レポート確認（source_effects.tsv等）

### Phase 6.5.3: deepghs/site_tags Adapter 実装（Week 2、5日間）

**Day 8-10: SiteTags_Adapter 実装**

**実装**:
```python
# src/genai_tag_db_dataset_builder/adapters/site_tags_adapter.py

class SiteTags_Adapter(BaseAdapter):
    """deepghs/site_tags の各サイトSQLiteを統合DBへ変換"""

    def __init__(self, site_db_path: Path, site_name: str):
        self.site_db_path = site_db_path
        self.site_name = site_name
        self.format_name = SITE_TO_FORMAT_NAME.get(site_name)

    def process(self) -> pd.DataFrame:
        """サイトSQLiteからタグ情報を抽出"""
        conn = sqlite3.connect(self.site_db_path)

        # スキーマ署名に応じた処理分岐
        schema_sig = self._get_schema_signature(conn)

        if schema_sig == "4f167646818c0e5589fb47027e794c2203632a8d":
            # Danbooru系スキーマ
            df = self._process_danbooru_schema(conn)
        elif schema_sig == "064e075251ad8b333851f0b2b2c57b31011a813c":
            # anime-pictures.net スキーマ
            df = self._process_anime_pictures_schema(conn)
        # ... 他のスキーマ

        conn.close()
        return df

    def _process_danbooru_schema(self, conn) -> pd.DataFrame:
        """Danbooru系スキーマの処理"""
        # tags テーブルから取得
        df_tags = pd.read_sql("""
            SELECT name, post_count, category, is_deprecated
            FROM tags
        """, conn)

        # tag_aliases テーブルから取得
        df_aliases = pd.read_sql("""
            SELECT alias, tag FROM tag_aliases
        """, conn)

        # 統合DB形式に変換
        # ...
        return df
```

**タスク**:
- [ ] BaseAdapter からの継承
- [ ] 12種類のスキーマ署名に対応した処理分岐
- [ ] Danbooru系/anime-pictures系等のスキーマ別処理実装
- [ ] ユニットテスト（モックSQLite使用）

**Day 11-12: SiteTags_Adapter テスト**

**タスク**:
- [ ] 18サイト分のSQLiteでテスト実行
- [ ] データ変換の正確性検証
- [ ] エラーハンドリング確認

### Phase 6.5.4: CC4版ビルド（Week 3、5日間）

**Day 13-14: CC4版ビルドスクリプト作成**

**ビルドコマンド**（PowerShell）:
```powershell
# CC4版ビルド（CC0版をベースに差分追記）
.\\.venv\\Scripts\\python.exe -m genai_tag_db_dataset_builder.builder `
  --output .\\out_db_cc4\\genai-image-tag-db-cc4.sqlite `
  --sources C:\\LoRAIro\\external_sources\\site_tags `
  --report-dir .\\out_db_cc4 `
  --base-db .\\out_db_cc0\\genai-image-tag-db-cc0.sqlite `
  --skip-danbooru-snapshot-replace `
  --parquet-dir .\\out_db_cc4\\parquet `
  --overwrite
```

**タスク**:
- [ ] CC4版ビルド設定ファイル作成（`license_builds/include_cc4_sources.txt`）
- [ ] ビルドスクリプト実行
- [ ] ビルドログ収集

**Day 15-17: CC4版検証**

**タスク**:
- [ ] データ整合性検証（FK/CHECK/UNIQUE制約）
- [ ] 18サイト分のデータが正しく統合されているか確認
- [ ] source_effects.tsv の確認（deepghs/site_tags のみが記録されているか）
- [ ] Parquet エクスポート検証

### Phase 6.5.5: MIT版再ビルド（Week 3-4、3日間）

**Day 18-20: MIT版再ビルド**

**タスク**:
- [ ] 新スキーマのCC0版をベースにMIT版再ビルド
- [ ] 既存のMIT差分ビルド戦略を流用
- [ ] データ整合性検証

### Phase 6.5.6: ドキュメント整備（Week 4、2日間）

**Day 21-22: ドキュメント作成**

**タスク**:
- [ ] Serenaメモリ作成: `dataset_builder_phase6_5_cc4_local_build_completion_2025_12_17`
- [ ] README 更新（CC4版ビルド手順）
- [ ] ライセンス表記更新（CC-BY-4.0 対応）
- [ ] dataset_builder__index.md 更新

---

## 成功基準

### Phase 6.5.1（スキーマ設計）

- [x] site_tags統合に必要な列追加の確定
- [x] マイグレーションスクリプト実装
- [x] 既存CC0版DBへのマイグレーション成功

### Phase 6.5.2（CC0版再ビルド）

- [ ] 新スキーマでCC0版フルビルド成功
- [ ] データ整合性検証 100%パス
- [ ] Parquet エクスポート成功

### Phase 6.5.3（Adapter実装）

- [ ] SiteTags_Adapter 実装完了
- [ ] 12種類のスキーマ署名に対応
- [ ] ユニットテスト≥80%カバレッジ

### Phase 6.5.4（CC4版ビルド）

- [ ] CC4版ビルド成功
- [ ] 18サイト分のデータ統合確認
- [ ] source_effects.tsv に deepghs/site_tags のみ記録

### Phase 6.5.5（MIT版再ビルド）

- [ ] MIT版再ビルド成功
- [ ] 新スキーマで整合性確認

### Phase 6.5.6（ドキュメント）

- [ ] 完了記録作成
- [ ] README/ライセンス表記更新

---

## タイムライン

### Week 1
- Day 1: スキーマ設計
- Day 2: マイグレーション実装
- Day 3: マイグレーション検証
- Day 4-5: CC0版再ビルド
- Day 6-7: CC0版検証

### Week 2
- Day 8-10: SiteTags_Adapter 実装
- Day 11-12: SiteTags_Adapter テスト

### Week 3
- Day 13-14: CC4版ビルドスクリプト作成
- Day 15-17: CC4版検証

### Week 3-4
- Day 18-20: MIT版再ビルド

### Week 4
- Day 21-22: ドキュメント整備

**総所要時間**: 4週間（22営業日）

---

## リスク管理

### 高リスク

**R1: スキーママイグレーションの失敗**
- 発生確率: 中
- 影響度: 高
- 対策: 既存DBのバックアップ、段階的マイグレーション

**R2: deepghs/site_tags のスキーマ多様性**
- 発生確率: 高
- 影響度: 中
- 対策: 調査結果の12スキーマ署名に基づく分岐処理

### 中リスク

**R3: CC4版ビルド時間超過**
- 発生確率: 中
- 影響度: 中
- 対策: キャッシュ活用、並列処理検討

**R4: ライセンス混在の誤検出**
- 発生確率: 低
- 影響度: 高
- 対策: source_effects.tsv の厳密な検証

---

## Phase 7 への引き継ぎ

**Phase 6.5 完了後の状態**:
- CC0/MIT/CC4 全てが新スキーマで統一
- CC4版の差分ビルド戦略が確立
- deepghs/site_tags 統合の実績

**Phase 7 で活用**:
- 新スキーマを前提としたリポジトリ自動化
- CC4版も含めた3ライセンス版の自動ビルド
- SiteTags_Adapter を Fetcher Layer と統合

---

## 参照

- **調査結果**:
  - `dataset_builder_deepghs_site_tags_investigation_log_2025_12_17.md`
  - `deepghs_site_tags_sqlite_schema_summary_2025_12_17.md`
  - `deepghs_site_tags_non_sqlite_schema_summary_2025_12_17.md`

- **既存実装**:
  - `dataset_builder_mit_build_strategy_update_2025_12_16.md`: MIT差分ビルド戦略
  - `dataset_builder_dual_license_builds_implementation_2025_12_16.md`: ライセンス別ビルド

- **Phase 7 計画**:
  - `dataset_builder_phase7_repository_automation_plan_2025_12_17.md`

---

**策定者**: Claude Sonnet 4.5
**策定日**: 2025年12月17日
