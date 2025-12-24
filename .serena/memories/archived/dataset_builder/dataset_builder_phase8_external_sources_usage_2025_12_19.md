# Phase 8: external_sources の「どのデータをどう使うか」メモ

**注**: このメモリの内容は `dataset_builder_phase8_hf_based_ci_update_plan_2025_12_19.md` に統合済み（2025-12-19更新）。
最新の計画はそちらを参照してください。

目的：CI更新（HFの base sqlite を取得 → 差分追記）に向けて、clone済みリポジトリの **利用対象ファイル** と **不要ファイル** を明確化する。

前提：
- 更新ビルドは原則 `--base-db`（HFから取得した base sqlite）で差分追記
- “repo単位で全部拾う” は事故りやすいので、最初から **paths_include（allow-list）** を持つ
- 翻訳ソースは `TAG_TRANSLATIONS` のみを更新し、usage count（`TAG_USAGE_COUNTS`）は **ホスティングサイト由来** のデータのみ更新対象とする

## 1) booru-japanese-tag（MIT）

- Local: `C:\LoRAIro\external_sources\booru-japanese-tag`
- Upstream: https://github.com/boorutan/booru-japanese-tag
- Commit: `035c0d63cbf70f6a3d8da4fbef31a122b48a9814`
- License: MIT（repo内 `LICENSE`）

### 使うもの（翻訳）
- `danbooru-machine-jp.csv`
  - 形式：ヘッダ無し / `tag,translation_ja` の2カラム
  - 用途：Danbooruタグの **日本語翻訳** を `TAG_TRANSLATIONS(language='ja')` に追加

### 使わない（不要/ノイズ）
- `app.db`（翻訳管理用DB）
- `danbooru-only-machine-jp.csv`（機械翻訳のみで誤訳/文字化けが多い）
- `danbooru.csv`（tagcomplete由来のタグ一覧。DB側の正規ソースを優先したい）
- `.idea/`, `asset/`, `main.go`, `translate/*`, `db/*`（ツール/画像）

### 取り込み単位の結論（暫定）
- **成果物単位**（`danbooru-machine-jp.csv` のみ採用）が安全

## 2) p1atdev/danbooru-ja-tag-pair-20241015（CC0-1.0）

- Local: `C:\LoRAIro\external_sources\danbooru-ja-tag-pair-20241015`
- Upstream: https://huggingface.co/datasets/p1atdev/danbooru-ja-tag-pair-20241015
- Commit: `846b9a569c8595ba5fdde77a06af92d589e94692`
- License: CC0-1.0（README frontmatter）

### 使うもの（翻訳）
- `data/train-00000-of-00001.parquet`
  - schema（確認済み）：`title`（tag）, `other_names`（list[string]）
  - 用途：Danbooruタグの **日本語翻訳（複数候補）** を `TAG_TRANSLATIONS(language='ja')` に追加

## 3) KBlueLeaf/danbooru2023-metadata-database（MIT）

- Local: `C:\LoRAIro\external_sources\danbooru2023-metadata-database`
- Upstream: https://huggingface.co/datasets/KBlueLeaf/danbooru2023-metadata-database
- Commit: `da5c8c2be09022b5aaf718d18bd981cdf32111ff`
- License: DBファイルはMIT / コードはApache-2.0（README記載）

### 中身（SQLite）
- `danbooru2023.db` / `danbooru2023-no-index.db` の主要テーブル：
  - `tag(id, name, type, popularity)`
  - `post(...)`（file_url 等、投稿メタデータ）
  - `posttagrelation(post_id, tag_id)`（多対多）
  - `localpost(...)`（ローカル参照用）

### 重要な実データ確認
- `tag.popularity` は **全行 0**（`MAX(popularity)=0`）だった
  - よって、このデータセットから **tagごとの使用回数（count）** を取り込む用途には使えない（`TAG_USAGE_COUNTS.count` のソースにはしない）
  - `type`（0..4）は値があるので、type補完用途なら検討余地はある

### CIでの扱い（結論）
- DB本体（最大24GB）はCIで扱うのは不適
- `post` は画像投稿のメタデータで、タグDB（タグ中心）の更新には使わない前提
- 使うとしても **`parquet/tag.parquet` のみ**に絞る（軽量）

## 4) hearmeneigh/e621-rising-v3-curated（学習データセット / 巨大）

- Local: `C:\LoRAIro\external_sources\e621-rising-v3-curated`
- Upstream: https://huggingface.co/datasets/hearmeneigh/e621-rising-v3-curated
- Commit: `7d25a37a69983a2ba17b6489cdf89511b31d683a`

### 結論
- 画像+tagsの巨大データ（約53GB）で、タグDB更新用途としてCIで扱うのは重い
- この系列の tag counts / tags 集計は **ホスティングサイト全体の集計ではなく「学習データセット内での出現回数」**
  - したがって、`TAG_USAGE_COUNTS`（ホスティングサイト由来の使用回数）を更新するソースとしては不適
- Phase8（CI更新）では **取り込まない**
  - もし将来使うなら「学習データセット由来の参考統計」として別枠で扱い、既存DBのusage countには混ぜない

## 5) tag-for-autocompletion-with-translation（Tags zh_CN 系）

- Local: `C:\LoRAIro\external_sources\tag-for-autocompletion-with-translation`
- Upstream: https://github.com/sgmklp/tag-for-autocompletion-with-translation
- Commit: `5712959dff486b5a418517d95412d432d0e7ca9f`
- License: **要確認**（repoに LICENSE が無い）

### 使うもの（翻訳）
- `Tags-zh-full.csv`
  - 形式：`tag,type,"translation"`（3カラム）
  - 用途：`TAG_TRANSLATIONS(language='zh-CN')` に追加（簡体字想定）
  - `type` は基本使わない

### 使わない（不要/事故りやすい）
- `Tags.csv` + `Tags-zh-lite.csv`（行対応joinが必要になり事故りやすい）
- `config.json`（拡張機能の設定）

## 6) toynya/Z3D-E621-Convnext（license: other）

- Local: `C:\LoRAIro\external_sources\Z3D-E621-Convnext`
- Upstream: https://huggingface.co/toynya/Z3D-E621-Convnext
- Commit: `39b081cafc120253513e6e9c21283892c6994e62`
- README: license `other`

### 結論
- ライセンスが曖昧で、モデル/重みが主体
- `tags-selected.csv` も用途がモデル向けタグセットで、タグDBのソースとして必須ではない
- Phase8（CI更新）では **取り込まない**

## 次にやること（Phase8向け）

1. `sources.yml`（repo取得 + paths_include）を作るなら、まずは以下の軽量ソースから
   - CC0: `p1atdev/danbooru-ja-tag-pair-20241015`（翻訳）
   - MIT: `booru-japanese-tag/danbooru-machine-jp.csv`（翻訳差分）
   - zh-CN翻訳: `tag-for-autocompletion-with-translation/Tags-zh-full.csv`（※license要確認）
2. `danbooru2023-metadata-database` は **type補完が必要になった場合のみ** `parquet/tag.parquet` を検討
3. `e621-rising-v3-curated` は CI更新の対象にしない（学習データセット内集計であり、ホスティングサイト由来countの更新には不適）
