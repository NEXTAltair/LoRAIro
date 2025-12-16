# Parquet出力（HF Dataset Viewer向け）計画 v1

## 背景 / 目的
- SQLiteはHFのDataset Viewerで中身が見づらいので、**閲覧・分析用にParquetも同時生成**する。
- SQLiteの正規化されたリレーション（TAGS / TAG_STATUS / TAG_TRANSLATIONS / TAG_USAGE_COUNTS）を、Viewerで扱いやすい**フラット表**に潰す。
- ただし「推奨タグ(preferred)がサイト/formatごとに変わる」ため、1つの巨大表に混ぜると意味が壊れる。

## 方針（確定）
1. **format（=ホスティングサイト）ごとに1 Parquet（=1表）**を出す。
   - 例: `parquet/danbooru.parquet`, `parquet/e621.parquet`, `parquet/derpibooru.parquet`（必要なら `unknown.parquet` も）
2. Parquetは「正規タグ1行」に集約する。
   - そのformatで `TAG_STATUS.alias=0` で扱われる **preferred_tag_id（推奨側）** を基準に行を作る。
   - 非推奨タグ（alias=1）は、正規タグ行の `aliases`（list）として**逆引きで集約**する。
3. 翻訳も表現揺れがあり得るので、言語ごとに **list[str] 集約**を許容する。

## 1表のカラム案（共通）
ユーザー案（先頭順）は維持し、サイト別に同一スキーマに揃える。

- `tag_id`（int）: 正規タグの tag_id
- `tag`（str）: 正規化済みタグ（TAGS.tag）
- `format_name`（str）: TAG_FORMATS.format_name
- `type_name`（str）: TAG_TYPE_NAME.type_name（TAG_TYPE_FORMAT_MAPPING 経由で解決）
- `count`（int|null）: TAG_USAGE_COUNTS.count（そのformatのみ）
- `aliases`（list[str]）: そのformatで当該tag_idを preferred_tag_id とする aliasタグ群（TAGS.tag）
- `lang_ja`（list[str]）: TAG_TRANSLATIONS(ja) を tag_id で集約
- `lang_zh`（list[str]）: TAG_TRANSLATIONS(zh) を tag_id で集約

※Viewerの都合でlist列が重い場合は、追加で `aliases_str`（`"a|b|c"`）のような文字列版も検討。

## 正規タグ行の定義（重要）
- 対象format_idについて `TAG_STATUS` の行を走査し、各行の `preferred_tag_id` を集約して「正規タグ集合」を作る。
- その集合の各 tag_id について:
  - `aliases`: `TAG_STATUS.alias=1 AND preferred_tag_id=<tag_id> AND format_id=<format_id>` の `tag_id` を逆引き → TAGS.tag を list化
  - `type_name`: 正規タグ側の `TAG_STATUS` 行の type_id を `TAG_TYPE_FORMAT_MAPPING` 経由で type_name に解決
  - `count`: `TAG_USAGE_COUNTS(tag_id, format_id)`
  - `translations`: `TAG_TRANSLATIONS(tag_id, language)` を集約

## 出力ファイルと命名
- 出力先は `--parquet-dir <dir>` で指定する（例: `out_db_cc0/parquet/`）。
- まずは `format_id=1 (danbooru)` のみを出力し、chunkで分割して `danbooru-00000.parquet` のように連番で保存する（Viewer/Pandas側では `pl.scan_parquet('danbooru-*.parquet')` でまとめて読める）。
- 将来的に他formatも出す場合は、`e621-*.parquet` のようにプレフィックスをformatごとに分ける。

## 既知のリスク / チェックポイント
- `TAG_TYPE_FORMAT_MAPPING` の不足は、SQLite生成時と同様に補完されている想定だが、Parquet生成時も `type_name` 解決不能の行が出る可能性がある。
  - その場合は `type_name='unknown'` にフォールバックし、件数をレポートする。
- `TAG_STATUS` の異常値（例: type_id=-1）
  - SQLite側で `fallback_unknown` が入っているので、Parquet側も同様にunknown扱い。

## 実装ステップ（次の作業）
1. SQLite（CC0版）を入力としてParquetを生成するCLI/ツールを追加
2. `format_id` ごとの DataFrame を構築
3. `aliases` と `lang_*` を groupby-agg(list) で集約
4. Parquetを書き出し
5. 生成後に簡易チェック（row数、NULL率、1-2件のスポット検証）

## 確定事項（ユーザー決定）
- Parquetはまず `format_id=1 (danbooru)` のみ出力（サンプル/先行実装）。
- alias=1 で preferred_tag_id に向く逆引きリスト列名は `deprecated_tags` とする。
- `deprecated_tags` に入れる文字列は `TAGS.tag`（正規化済み）だけ。
- 翻訳列は `lang_ja`, `lang_zh` 固定（list[str]集約）。
