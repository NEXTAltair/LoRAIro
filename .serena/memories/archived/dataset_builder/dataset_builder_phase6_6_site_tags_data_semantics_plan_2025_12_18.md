# Phase 6.6（案）: deepghs/site_tags 統合に伴う「投入データ」の扱い（is_deprecated / created_at / updated_at 等）

策定日: 2025-12-18

目的:
- Phase6.5 は「データソース道案内用メタデータ（DATA_SOURCES等）」に絞った。
- こちらは **実際にDBへ投入されるタグ情報の意味付け**（非推奨・alias・日時）を決める。

前提:
- `genai-image-tag-db-cc0.sqlite` をベースに差分追記していく。
- deepghs/site_tags はサイトごとにスキーマが異なる。
- 「重要な日時」は以下のみ:
  1) タグが登録された日（source側にあるなら）
  2) タグが必要になった日（=このDBがそのタグを採用/観測した日）
  3) カウントが観測された日（count値の観測日時）

---

## 1) is_deprecated（非推奨）の扱い

### 1-1. 基本方針
- `is_deprecated` は **aliasとは別軸**として保持する（Danbooruで検証済み: deprecatedでも置換先が無いケースが多数）。
- DBツール側の挙動は「警告/非推奨表示」までを基本とし、強制置換は alias でのみ行う。

### 1-2. alias との関係（統合ルール）
- alias（置換先あり）の場合:
  - `TAG_STATUS.alias=true` かつ `preferred_tag_id` を置換先にする（従来通り）。
  - deprecatedフラグは「タグがdeprecatedである」情報として別途保持する（必要なら）。
- deprecated だが alias なしの場合:
  - `TAG_STATUS.alias=false` のまま（= preferred_tag_id は自分）。
  - deprecated 情報だけを保持できるようにする。

### 1-3. どこに持つか（スキーマ案）
- `TAG_STATUS` に持つ（formatごとの状態なので自然）。
  - `TAG_STATUS.deprecated BOOLEAN NOT NULL DEFAULT 0`
  - `TAG_STATUS.deprecated_at DATETIME NULL`

備考:
- e621 の `invalid_tag` / gelbooru の `bad_tag` は「無効タグ吸い込み先」なので、通常のaliasとして取り込まない（吸い込み先へは誘導しない）。
  - 代わりに、alias元タグ（= `tag_aliases.alias` 側）の `TAG_STATUS.deprecated=true` を立てて「非推奨/無効」情報として残す（非推奨化日時が取れない場合は `deprecated_at=NULL`）。
  - 必要ならレポートにも出す（後で精査できるように）。
  - これを `TAG_STATUS` に入れるために `preferred_tag_id=NULL` のような扱いにすると、既存の `TAG_STATUS` 制約（`preferred_tag_id NOT NULL` / `ck_preferred_tag_consistency`）と衝突するし、DBツール側のalias解決も複雑化する。
  - 「無効として吸い込まれた」事実はレポートに残せば十分（必要なら後で“無効alias専用テーブル”を追加検討）。
- Sankaku の `Limited visibility` は deprecated ではなく状態タグ扱い（typeとして残すだけでよい）。

---

## 2) created_at / updated_at の扱い（意味の統一）

ここが混乱しやすいので「どのテーブルの created_at/updated_at を何として扱うか」を固定する。

### 2-1. TAG_USAGE_COUNTS（count値の観測日時）
- `TAG_USAGE_COUNTS.count` はサイトの post_count 等。
- `TAG_USAGE_COUNTS.created_at/updated_at` は **count観測日時**として扱う。

優先順位:
1) ソース側に `updated_at` 等がある場合 → それを入れる
2) 無い場合 → ベースDB（cc0.sqlite）に既に入っている日時を保持
3) それも無い（新規レコード作成など） → ビルド時刻（挿入時刻）

### 2-2. TAG_STATUS（状態の観測日時）
- `TAG_STATUS.created_at/updated_at` は **そのformatにおける状態の観測日時**として扱う。

優先順位（TAG_USAGE_COUNTSと同じ思想）:
1) ソース側に `updated_at` があり、type/alias/deprecated 等の状態の根拠になる → それを入れる
2) 無い → ベースDBの既存値を保持
3) 新規作成 → ビルド時刻

補足:
- `TAG_STATUS.source_updated_at` のような列は追加しない。ソース側更新日時は count観測日時にも使われ得るため、必要なら `TAG_USAGE_COUNTS` 側で扱う。

### 2-3. TAGS（タグそのものの「必要になった日」）
- TAGS側の created_at/updated_at を以下に寄せる案:
  - `created_at` = このDBがその tag_id を初めて採用/観測した日（first_seen）
  - `updated_at` = 最後に観測/更新された日（last_seen）

source側（=取り込むデータソース/ホスティングサイト側）に「タグが登録された日」がある場合は、formatごとに意味が変わるため `TAG_STATUS` に持つ。

- `TAG_STATUS.source_created_at DATETIME NULL`

補足:
- `source_updated_at` は追加しない（更新時刻は count観測日時にも使われ得るため）。
- 取得できるサイトのみ埋める（Danbooru等）。

---

## 3) invalid_tag / bad_tag / orphan alias の運用

目的:
- 推奨先が存在しない alias 行を無理に入れて alias解決を壊さない。

ルール:
- `tag_aliases.tag` が `invalid_tag` / `bad_tag` など「無効タグ吸い込み先」の場合は、通常のaliasとして取り込まない（吸い込み先へは誘導しない）。
  - alias元タグ（= `tag_aliases.alias`）は `TAG_STATUS.deprecated=true` を立て、`deprecated_at` は取れないなら `NULL` のまま。
- 推奨先（tag）が **データソース側のtagsに存在しない** alias 行は、データが壊れているので通常のaliasとして取り込まない（レポートのみ）。
  - ただし Danbooru のように「推奨先は実在するのにスナップショット側の tags テーブルに欠落している」ケースがある（例: `\\m/`）。
  - その場合は `TAGS` を作成してから alias を貼る方が実用的（少数なら自動作成 + レポートで要確認）。
- 「非推奨だがalias無し」は deprecatedフラグで表現し、置換はしない。

### 3-1. alias衝突（同一 alias が複数 tag に向く）
- 基本は `alias -> tag` の 1:1 を前提として取り込む（`TAG_STATUS.alias=true`）。
- 例外として同一 `(format, alias)` に複数の `tag` がある場合:
  - **候補ごとのcountが取れる場合のみ**: count最大の `tag` を採用する。
  - countが取れない場合: 先勝ち（最初に見つかった `tag`）を採用し、衝突をレポートに残す。
  - count同値のタイブレークは考慮しない（先勝ちでよい）。

---

## 4) 取り込まない（意味だけ記録で十分）

- `views` / `subscriptions` / `pool_count` / `series_count` などは現時点では取り込まない。
- ただし「何の値か」だけは調査結果としてメモに残してある。

参照:
- `.serena/memories/dataset_builder_deepghs_site_tags_field_semantics_2025_12_18.md`
- `.serena/memories/dataset_builder_deepghs_site_tags_type_category_mappings_2025_12_18.md`

---

## 5) 初期レポート（最低限）
※「手で直す/判断する必要があるもの」だけに絞る。

- `alias_invalid_sink.tsv`
  - `format_name, alias, sink_tag, note`
  - 例: e621 `invalid_tag`, gelbooru `bad_tag`
- `alias_missing_target.tsv`
  - `format_name, alias, target, note`
  - 例: Danbooru の `\\m/`（推奨先の tags 側欠落疑い）
- `alias_conflicts.tsv`
  - `format_name, alias, target_candidates, chosen_target, chosen_reason`
- `type_category_unknown.tsv`
  - `format_name, raw_type_or_category, example_tags, note`
- `translation_collisions_zh.tsv`（中国語のみ）
  - `tag_id, tag, existing_lang, existing_text, incoming_lang, incoming_text, action(replace/append)`
