# Phase 6.5 Schema Design Analysis: deepghs/site_tags Integration

## 策定日
2025-12-17（2025-12-18 方針更新）

## 目的
`deepghs/site_tags` 統合に向けてスキーマ変更の方針を確定する（混乱防止のため「決定事項」と「却下理由」だけ残す）。

---

## 決定事項（2025-12-18）

- `TAG_FORMATS.license` は導入しない（format自体のライセンスは固定ではなく、意味が壊れやすい）。
- ビルド成果物のライセンスは Hugging Face リポジトリ側で表現し、DB内に冗長に保持しない。
- 「このDBはどこから来たか」を辿れるようにするため、**単一テーブル `DATA_SOURCES` を追加**する。
  - URL / revision(sha) / retrieved_at / license_spdx / notes を保持（ローカルパスは不要）。
- 行単位（tag/alias/count/translation）の完全トレースはしない（解析DB化を避ける）。
  - 代替として `DATABASE_METADATA` に `build.base_db` / `build.timestamp` / `sources.used` のような **サマリ**を入れる。
- 投入データ側（deprecated/日時）の設計は Phase 6.6 で別管理。

---

## 検討したが却下（要点のみ）

- 案A: `TAG_FORMATS` に `source_url/license/last_updated` を追加
  - 却下理由: format識別とソース/ビルドのメタデータが混ざる。`TAG_FORMATS.license` が混乱の元。
- 案B: formatメタデータを 1:1 で別テーブル分離
  - 却下理由: 現時点の目的（道案内）には過剰。
- 案C: JSONメタデータ列
  - 却下理由: 型・検証が弱く、運用が不透明になりやすい。
- 案D: format↔source を多対多で完全追跡
  - 却下理由: 目的に対して過剰で、解析DB化する。

---

## 採用プラン（Approach E）

### 追加スキーマ（最小）

```sql
CREATE TABLE DATA_SOURCES (
    source_id INTEGER PRIMARY KEY,
    source_name TEXT UNIQUE NOT NULL,
    source_url TEXT NOT NULL,
    license_spdx TEXT,
    revision TEXT,
    retrieved_at DATETIME,
    notes TEXT
);
```

### `DATABASE_METADATA` へ入れるサマリ例

```sql
INSERT INTO DATABASE_METADATA VALUES ('build.base_db', 'genai-image-tag-db-cc0.sqlite');
INSERT INTO DATABASE_METADATA VALUES ('build.timestamp', '2025-12-18T00:00:00Z');
INSERT INTO DATABASE_METADATA VALUES ('sources.used', 'deepghs/site_tags,...');
```

---

## リスク（要点のみ）

- `DATA_SOURCES` 更新漏れ（URL/revisionを書き忘れる）
  - 対策: ビルド処理に組み込み、`DATABASE_METADATA.sources.used` も同時更新。
- revision取得失敗（HF/Git取得エラー）
  - 対策: ビルドは継続しつつ、`notes` に理由を残す。

---

## 参照

- `.serena/memories/dataset_builder_phase6_6_site_tags_data_semantics_plan_2025_12_18.md`（投入データの意味付け: is_deprecated / created_at / updated_at）
- `.serena/memories/dataset_builder_deepghs_site_tags_investigation_log_2025_12_17.md`
- `.serena/memories/dataset_builder_deepghs_site_tags_field_semantics_2025_12_18.md`
- `.serena/memories/dataset_builder_deepghs_site_tags_type_category_mappings_2025_12_18.md`
