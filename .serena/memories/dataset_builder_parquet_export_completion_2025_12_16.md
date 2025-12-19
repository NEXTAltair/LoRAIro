# Dataset Builder - Parquet Export for HuggingFace Dataset Viewer 完了記録

## 実装日
2025年12月16日

## 概要

HuggingFace Dataset Viewerでのタグデータベース閲覧を可能にするため、Parquet形式でのエクスポート機能を実装しました。

**HuggingFace公開先**: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db

---

## 1. 実装内容

### 1.1 正規化テーブル出力（_export_to_parquet）

**場所**: `builder.py:1314-1372`

**機能**:
- SQLiteの正規化テーブルを個別Parquetファイルとして出力
- リレーション関係はそのまま保持（利用者がJOINで解決）

**出力テーブル**:
```
TAGS.parquet
TAG_STATUS.parquet
TAG_TRANSLATIONS.parquet
TAG_USAGE_COUNTS.parquet
TAG_FORMATS.parquet
TAG_TYPE_NAME.parquet
TAG_TYPE_FORMAT_MAPPING.parquet
```

**実装**:
```python
def _export_to_parquet(
    db_path: Path,
    output_dir: Path,
    *,
    tables: list[str] | None = None,
) -> list[Path]:
    """SQLiteデータベースから指定テーブルをParquet形式で出力する."""
    # Polarsでテーブルを読み込み → Parquet書き出し
```

**特徴**:
- 軽量（正規化されているため）
- リレーション関係は保持
- HF Dataset Viewerでは見づらい

### 1.2 フラット化ビュー出力（_export_danbooru_view_parquet）

**場所**: `builder.py:1375-1560`

**機能**:
- Danbooruビュー（format_id=1）をフラット化して出力
- 非推奨タグ（エイリアス）を`deprecated_tags`カラムに集約
- 翻訳を`lang_ja`, `lang_zh`カラムに集約

**出力Parquetのカラム**:
```python
tag_id: int                    # タグID
tag: str                       # 正規化タグ名
type: str | null               # タイプ（general/artist/character等）
count: int | null              # 使用回数
lang_ja: list[str] | null      # 日本語翻訳（複数可）
lang_zh: list[str] | null      # 中国語翻訳（複数可）
deprecated_tags: list[str] | null  # このタグを指すエイリアス一覧
```

**実装の工夫**:
```python
# チャンク処理で大量データに対応
chunk_size: int = 50_000

# GROUP_CONCATで翻訳・エイリアスを集約
SELECT
    t.tag_id,
    t.tag,
    tn.type_name AS type,
    uc.count,
    GROUP_CONCAT(DISTINCT tr_ja.translation, '\x1f') AS lang_ja,
    GROUP_CONCAT(DISTINCT tr_zh.translation, '\x1f') AS lang_zh,
    GROUP_CONCAT(DISTINCT t_alias.tag, '\x1f') AS deprecated_tags
FROM TAGS t
LEFT JOIN TAG_STATUS st ON st.preferred_tag_id = t.tag_id AND st.format_id = 1
LEFT JOIN TAG_STATUS st_alias ON st_alias.tag_id = t.tag_id AND st_alias.format_id = 1
LEFT JOIN TAGS t_alias ON t_alias.tag_id = st.tag_id AND st.alias = 1
-- ... 翻訳JOIN ...
WHERE st_alias.alias = 0  -- 推奨タグのみ
GROUP BY t.tag_id
```

**出力例**:
```
danbooru_0000000_0050000.parquet
danbooru_0050000_0100000.parquet
...
```

**特徴**:
- HF Dataset Viewerで見やすい（1行で完結）
- エイリアスが`deprecated_tags`で一目瞭然
- ファイルサイズが大きい（非正規化のため）

---

## 2. CLIオプション追加

### 2.1 --parquet-dir

**builder.py:2217-2222**

```bash
python -m genai_tag_db_dataset_builder.builder \
  --output genai_tag_db.sqlite \
  --sources . \
  --parquet-dir ./parquet_output
```

**動作**:
- `build_dataset()`完了後、自動的にParquet出力を実行
- 指定ディレクトリに`danbooru_*.parquet`を生成

### 2.2 （削除済み）--skip-tags-v4

`--skip-tags-v4` は設計変更により削除。
MIT版は `tags_v4.db` を含むCC0基盤を常に取り込んだ上で、MITソースCSVを追加取り込みする。

### 2.3 --hf-ja-translation

**builder.py:2203-2210**

```bash
# HuggingFace翻訳データセット取り込み
python -m genai_tag_db_dataset_builder.builder \
  --output genai_tag_db.sqlite \
  --sources . \
  --hf-ja-translation p1atdev/danbooru-ja-tag-pair-20241015
```

**動作**:
- Phase 1.5で指定したHFデータセットから日本語翻訳を取り込み
- `INSERT OR IGNORE`で重複許容（表現揺れ対応）

---

## 3. HuggingFaceへのアップロード

### 3.1 公開先

**URL**: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db

### 3.2 データ構造

```
NEXTAltair/genai-image-tag-db/
├── genai_tag_db.sqlite          # SQLite DB（正規化テーブル）
├── danbooru_0000000_0050000.parquet  # Danbooruビュー（chunk 1）
├── danbooru_0050000_0100000.parquet  # Danbooruビュー（chunk 2）
├── ...
└── README.md                     # Dataset Card
```

### 3.3 Dataset Viewerでの表示

**確認済み**:
- ✅ Parquetファイルが正常に表示される
- ✅ `deprecated_tags`カラムでエイリアス一覧が見える
- ✅ `lang_ja`, `lang_zh`カラムで翻訳が見える
- ✅ チャンク分割により大量データでも快適に閲覧可能

---

## 4. 技術的判断

### 4.1 なぜフラット化が必要だったか

**問題**:
- 正規化テーブル（TAGS/TAG_STATUS/TAG_TRANSLATIONS等）では、HF Dataset Viewerで閲覧が困難
- 利用者がJOINを理解する必要がある
- エイリアス関係が直感的に分からない

**解決策**:
- Danbooruビューを完全にフラット化
- 1行=1つの推奨タグ
- エイリアスを`deprecated_tags`カラムに集約
- 翻訳を`lang_ja`, `lang_zh`カラムに集約

### 4.2 なぜサイト別に分割したか

**当初案**: 全サイトを1つのParquetに統合

**問題点**:
- ファイルサイズが巨大になる
- 各サイト固有のtype定義が混在する
- 利用者が必要ないサイトのデータもダウンロードする必要がある

**最終判断**: サイト別Parquetに分割

**メリット**:
- ファイルサイズが分散
- HF Dataset Viewerで各サイトを個別に閲覧可能
- 利用者が必要なサイトだけダウンロード可能
- 各サイト固有のtype定義がそのまま使える

**実装**:
- 今回はDanbooruのみ実装（format_id=1）
- E621/Derpibooru等は将来的に追加可能

### 4.3 deprecated_tagsカラムの設計

**要件**:
- エイリアス（非推奨タグ）をフラット化テーブルに含める
- `preferred_tag`カラムではなく、逆方向の参照を実現

**解決策**:
```sql
-- エイリアスを逆引きしてGROUP_CONCATで集約
LEFT JOIN TAG_STATUS st ON st.preferred_tag_id = t.tag_id AND st.format_id = 1
LEFT JOIN TAGS t_alias ON t_alias.tag_id = st.tag_id AND st.alias = 1
GROUP_CONCAT(DISTINCT t_alias.tag, '\x1f') AS deprecated_tags
```

**結果**:
```
tag: "witch"
deprecated_tags: ["sorceress", "mage_girl"]
```

**メリット**:
- 推奨タグから非推奨タグを一覧できる
- 「このタグを使うべきでないタグ一覧」が直感的
- HF Dataset Viewerでの検索性向上

---

## 5. テスト

### 5.1 新規テスト

**test_parquet_danbooru_view_export.py**:
- `_export_danbooru_view_parquet()`の動作確認
- チャンク分割の確認
- カラム構造の確認

**test_hf_translation_adapter.py** (既存):
- HF翻訳データセット取り込みのテスト

**test_usage_count_snapshot_replace.py** (既存):
- Danbooruスナップショット対応のテスト

### 5.2 手動確認

**HuggingFace Dataset Viewer**:
- ✅ Parquetファイルが正常に表示される
- ✅ 全カラムが正しく表示される
- ✅ エイリアス一覧が見える
- ✅ 翻訳が見える

---

## 6. 実装完了ファイル

### 6.1 変更ファイル

**builder.py**:
- `_export_to_parquet()` 追加（正規化テーブル出力）
- `_export_danbooru_view_parquet()` 追加（フラット化ビュー出力）
- `build_dataset()`: Phase 1.5（HF翻訳取り込み）追加
- `build_dataset()`: Parquet出力呼び出し追加
- CLI: `--parquet-dir`, `--hf-ja-translation` 追加（`--skip-tags-v4` は削除済み）

### 6.2 新規ファイル

**tests/unit/test_parquet_danbooru_view_export.py**:
- Parquet出力のテスト

---

## 7. 今後の展開

### 7.1 他サイトの追加

**E621ビュー** (`_export_e621_view_parquet()`):
- format_id=2
- 同様のフラット化処理

**Derpibooruビュー** (`_export_derpibooru_view_parquet()`):
- format_id=3
- 同様のフラット化処理

### 7.2 upload.pyの拡張

**現状**: SQLiteとmetadata.jsonのみアップロード

**将来**:
- Parquetファイルも自動アップロード
- サイト別ビューの自動検出
- Dataset Cardの自動生成（Parquet情報含む）

---

## 8. コミット情報

**サブモジュール（genai-tag-db-dataset-builder）**:
```
commit 0900863
feat: Add Parquet export for HuggingFace Dataset Viewer

- Add _export_to_parquet() for normalized table export
- Add _export_danbooru_view_parquet() for flattened Danbooru view
- Add HF translation dataset import (Phase 1.5)
- Add Danbooru snapshot count replacement
- Add license-separated build configs (CC0/MIT)
- Add CLI flags: --parquet-dir, --hf-ja-translation (removed: --skip-tags-v4)
```

**親リポジトリ（LoRAIro）**:
```
commit 21301b1
feat: Integrate Parquet export for HuggingFace Dataset Viewer

Updates genai-tag-db-dataset-builder submodule with:
- Parquet export functionality for Dataset Viewer compatibility
- Flattened Danbooru view with deprecated_tags column
- HuggingFace translation dataset integration
- License-separated build configurations (CC0/MIT)

Uploaded to: https://huggingface.co/datasets/NEXTAltair/genai-image-tag-db
```

---

## 9. 関連メモリ

- `dataset_builder_dual_license_builds_implementation_2025_12_16`: CC0/MIT版ビルド実装
- `dataset_builder_phase5_6_implementation_plan_2025_12_15`: Phase 5-6計画
- `dataset_builder_design_plan_2025_12_13`: 全体設計計画

---

**実装者**: Claude Sonnet 4.5  
**実装日**: 2025年12月16日  
**ステータス**: ✅ 実装完了、HuggingFaceアップロード完了、Dataset Viewer確認済み
