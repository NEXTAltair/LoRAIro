# ADR 0031: AI Rating Mapping to Canonical Rating

- **日付**: 2026-05-21
- **ステータス**: Accepted (amended 2026-05-27)

## Context

image-annotator-lib は Issue #80 (closed) で rating 出力を **model-native** な
`RatingPrediction(raw_label, confidence_score, source_scheme)` のリストとして
`UnifiedAnnotationResult.ratings` で返すようになった。ライブラリは LoRAIro の
`PG/PG-13/R/X/XXX` へは変換しない (責務分離: library はモデルが出した raw label /
confidence / source scheme を返すだけ)。

しかし LoRAIro 側 `AnnotationSaveService._append_model_result()` は `ratings` を
`str(ratings)` で雑に文字列化しており、`raw_rating_value` / `normalized_rating` の
両方に `"[RatingPrediction(...)]"` という壊れた値が入っていた。結果として:

- `normalized_rating` が canonical 値にならず、特定レーティング検索
  (`_apply_ai_rating_filter` の通常分岐) で永久にヒットしない。
- DB に意味のある AI rating が保存されない。

rating はデータセットごとに分類体系が異なる (Danbooru 系 `general/sensitive/
questionable/explicit`、e621 系 `safe/questionable/explicit`、anime_rating
`safe/r15/r18` 等)。LoRAIro 側でこれらを canonical rating に変換する mapper が必要。

## Decision

1. **model-native rating → canonical rating の変換は LoRAIro 側責務とする。**
   純粋関数モジュール `src/lorairo/domain/rating_mapper.py` に集約する
   (`domain/quality_tier.py` と同じ derived-view パターン)。

2. **マッピング表** (`(source_scheme, raw_label) -> canonical rating`):

   | source_scheme (alias) | raw label | canonical |
   |---|---|---|
   | `danbooru4` (`wdtagger`, `camie`) | `general` | `PG` |
   | `danbooru4` | `sensitive` | `PG-13` |
   | `danbooru4` | `questionable` | `R` |
   | `danbooru4` | `explicit` | `X` |
   | `e6213` (`z3d`, `danbooru3`) | `safe` / `general` | `PG` |
   | `e6213` | `questionable` | `R` |
   | `e6213` | `explicit` | `X` |
   | `sankaku3` (`anime_rating`) | `safe` | `PG` |
   | `sankaku3` | `r15` | `R` |
   | `sankaku3` | `r18` | `X` |
   | `binary_nsfw` | `sfw` | `PG` |
   | `binary_nsfw` | `nsfw` | `R` |
   | `openai_moderation_v1` | `pg` | `PG` |
   | `openai_moderation_v1` | `pg13` | `PG-13` |
   | `openai_moderation_v1` | `r` | `R` |
   | `openai_moderation_v1` | `x` | `X` |
   | `openai_moderation_v1` | `xxx` | `XXX` |

3. **`r15` は `R` にマッピングする** (Issue #333 で「設定/方針で決定」とされた曖昧点)。
   「R15 (15 歳以上推奨)」を成人向け寄りに保守的に解釈し、`danbooru4` の
   `questionable→R` と同列に扱う。

4. **通常の model-native rating mapper は `XXX` を自動生成しない。** Danbooru / e621 /
   sankaku / binary NSFW 系の出力は `PG/PG-13/R/X` までに丸める。`XXX` は手動 rating、
   または `openai_moderation_v1` のような専用判定 scheme でのみ自動付与を許可する。

5. **保存先は既存 `ratings` テーブルを使う。** rating scheme ごとの新規テーブル・
   新規カラムは作らない。`raw_rating_value` には model-native label、
   `normalized_rating` には LoRAIro canonical rating を保存する。

6. **list[RatingPrediction] は最高 `confidence_score` の 1 件に絞る。**
   `Rating` テーブルは `(image_id, model_id)` で upsert されるため 1 モデル = 1 行。
   `confidence_score` が `None` の予測は最下位扱い、全 None / 同値なら先頭 (top-1)。

7. **マッピング不能 (未知 scheme / 未知 label) は保存せず skip + warning。**
   壊れた値を DB に入れるより、その画像を AI rating 未設定のまま残す方が安全。

8. **`source_scheme` は DB に保存しない。** `ratings` テーブルに保存先カラムが無く、
   mapper の判定入力としてのみ使う。

9. **後方互換 `str` / `list[str]` 経路を維持する。** `source_scheme` を持たないため
   canonical 値とみなし、`PG/PG-13/R/X/XXX` であればそのまま保存、それ以外は skip。

### Amendment 2026-05-27: OpenAI Moderations preflight rating

LoRAIro#471 では、OpenAI Moderations Batch を annotation API 送信前の rating preflight として使う。
これは新しい moderation review system ではなく、既存 rating pipeline への入力である。

決定:

1. **専用 `ModerationResult` DTO、専用 DB table、専用 persistence API は追加しない。**
   image-annotator-lib は OpenAI Moderations response を既存
   `UnifiedAnnotationResult.ratings: list[RatingPrediction]` に畳み込む。

   ```python
   RatingPrediction(
       raw_label="r",
       source_scheme="openai_moderation_v1",
       confidence_score=0.78,
   )
   ```

2. **OpenAI `category_scores` から最も重い LoRAIro rating 候補を採用する。**
   category ごとの個別 preflight policy は LoRAIro 側に作らない。

   重み順:

   ```text
   PG < PG-13 < R < X < XXX
   ```

3. **初期 mapping は単純な threshold table とする。**

   | OpenAI category | score 条件 | raw_label | canonical | 備考 |
   |---|---:|---|---|---|
   | `sexual` | `>= 0.98` | `xxx` | `XXX` | annotation API に送らない |
   | `sexual` | `>= 0.90` | `x` | `X` | annotation API に送らない |
   | `sexual` | `>= 0.60` | `r` | `R` | annotation API に送る |
   | `sexual` | `>= 0.30` | `pg13` | `PG-13` | annotation API に送る |
   | `violence/graphic` | `>= 0.50` | `r` | `R` | gore / 出血 / バトル漫画を送信対象に残す |
   | `violence` | `>= 0.60` | `pg13` | `PG-13` | annotation API に送る |
   | `self-harm` | `>= 0.70` | `r` | `R` | annotation API に送る |
   | `self-harm/intent` | `>= 0.70` | `r` | `R` | annotation API に送る |
   | `self-harm/instructions` | `>= 0.70` | `r` | `R` | annotation API に送る |

   どの条件にも一致しない場合は `raw_label="pg"` とする。

4. **初期対象カテゴリを画像 rating に必要なものだけに絞る。**

   評価対象:

   - `sexual`
   - `violence`
   - `violence/graphic`
   - `self-harm`
   - `self-harm/intent`
   - `self-harm/instructions`

   初期実装では無視する:

   - `harassment`
   - `harassment/threatening`
   - `hate`
   - `hate/threatening`
   - `illicit`
   - `illicit/violent`
   - `sexual/minors`

   `harassment`, `hate`, `illicit` 系は画像単体 rating / annotation preflight ではなく text moderation
   の領域である。`sexual/minors` は OpenAI docs 上 text-only category であり、LoRAIro の画像 rating
   には使わない。`self-harm/intent` / `self-harm/instructions` は image input でも score が返るため、
   親カテゴリ `self-harm` と同じ `R` 判定に畳む。

5. **annotation API 送信可否は canonical rating だけで判断する。**

   ```text
   PG / PG-13 / R -> annotation API に送る
   X / XXX        -> annotation API に送らない
   ```

   `violence/graphic` は `R` までに丸める。グロテスク表現や出血描写は Civitai / LoRAIro rating 上
   `R` になり得るが、それだけで annotation API 送信を止めない。

6. **OpenAI Moderations Batch は既存 Provider Batch schema を使う。**

   - `provider_batch_jobs.endpoint = "/v1/moderations"`
   - `provider_batch_items.task_type = "rating_preflight"`
   - `provider_batch_jobs.model_id` / `provider_batch_items.model_id` には
     `omni-moderation-latest` 等の moderation model ledger entry を設定する
   - moderation model ledger entry は `model_type="rating"` / DB `model_types=["ratings"]`
     として登録し、`scores` / `tags` には分類しない
   - `provider_batch_items.image_id` で対象画像と対応付ける
   - `provider_batch_items.raw_response` は OpenAI moderation response の保存に使ってよい
   - canonical rating は既存 `ratings` table に保存する

   `provider_batch_items.raw_response` は監査・debug・将来の threshold 調整用の補助情報であり、
   送信可否の SSoT にはしない。送信可否の SSoT は `ratings.normalized_rating` とする。

7. **LoRAIro は provider artifact JSONL を直接 parse しない。**

   OpenAI Batch output/error JSONL の取得・parse、Moderations response の category score 抽出、
   `RatingPrediction` への畳み込みは image-annotator-lib の責務である。LoRAIro 側で
   OpenAI-specific artifact parser を追加しない。

8. **rating 専用モデルには `model_type="rating"` を使う。**

   `TaskCapability.RATINGS` は出力 capability、`model_type="rating"` は主用途分類である。
   `AnimeRatingAnnotator` や OpenAI Moderations preflight のように rating だけを返すモデルは
   `model_type="scorer"` に寄せず、LoRAIro DB では `model_types=["ratings"]` に写像する。
   一方で WDTagger / CamieTagger のように tags と rating を両方返すモデルは、従来どおり
   `model_type="tagger"` + `capabilities=["tags", "ratings"]` とし、DB では
   `["tags", "ratings"]` に分類する。スコアも返す rating-capable scorer も同様に
   `["scores", "ratings"]` を維持する。

参考:

- OpenAI Moderation guide: https://platform.openai.com/docs/guides/moderation/overview
- OpenAI Moderations API reference: https://platform.openai.com/docs/api-reference/moderations
- OpenAI Batch API guide: https://platform.openai.com/docs/guides/batch
- ADR 0038: Provider Batch API Integration Strategy
- Civitai content levels: `docs/specs/civitai-content-levels.md`

### Unmapped labels

mapper が `source_scheme` + `raw_label` を解決できない場合、LoRAIro は誤った
`normalized_rating` を保存しない。該当 rating は保存対象から外し、warning を出す。

未知 label は主に以下のケースで発生する。

- image-annotator-lib に新しい `source_scheme` が追加されたが、LoRAIro 側 mapper が未対応。
- 既存 scheme に新しい label が増えた。例: `danbooru4` に未知の rating tier が追加される。
- model card / `config.json` の label spelling が変わった。例: `sfw` と想定していたが `normal`
  や `safe_for_work` が返る。
- provider / WebAPI が prompt にない自由記述を返す。例: `probably safe`, `borderline`, `adult`.
- rating ではない content category が混入する。例: `anime picture`.
- `source_scheme` が欠落・typo している。

これらを `PG` や `UNRATED` に丸めると、安全側の判定を誤る。未知 label は保存しないことで
「未判定」として残し、mapper 追加・model adapter 修正・手動 rating のいずれかで解決する。

## Rationale

- **なぜ `domain/` に置くか**: `quality_tier.py` が `(model_name, raw_label) ->
  QualityTier` の純粋マッピングを既に `domain/` で担っており、rating mapper も
  raw annotation を変更しない derived-view 計算で同性質。レイヤーの一貫性。
- **なぜ skip するか (マッピング不能時)**: ADR 0015 の「書き込み・読み込みの対称性」
  教訓どおり、`normalized_rating` は検索フィルタが参照する canonical 集合に限定する。
  未知値を入れると「成功したが 0 件」のサイレント不整合を生む。
- **なぜ最高 confidence か**: 現状 lib は ONNX tagger で argmax 済みの 1 要素 list を
  返すが、将来の multi-label rating 分類器に備え list 入力でも決定的に 1 行へ正規化。
- **scheme エイリアス**: lib が現在 emit するのは `danbooru4` / `e6213` のみ。
  Issue #81 の新規 rating モデル候補 (`anime_rating` 等) に備え、表記揺れ・モデル系統
  差をエイリアスで吸収しておく (forward-compat)。
- **なぜ Civitai 互換を優先するか**: LoRAIro の rating は、dataset 作成だけでなく
  Civitai 投稿・WebAPI 投入・NSFW 除外の判断にも使われる。Civitai の browsing /
  generation 制限では `R` 以上が mature / NSFW 側として扱われるため、
  `questionable` / `r15` / binary `NSFW` のような曖昧な signal は `PG-13` ではなく
  `R` に寄せる。これにより、LoRAIro の既存 NSFW 除外 (`R` / `X` / `XXX`) と
  mapping の意味が一致する。
- **なぜ binary NSFW を専用項目にしないか**: binary NSFW は、細かな rating を決める
  というより API 送信可否や除外判定に使う signal である。専用カラムを増やすと、
  既存の rating / NSFW filter と二重管理になる。永続化が必要な場合は
  `SFW -> PG`、`NSFW -> R` として既存 rating record に寄せる。
- **なぜ OpenAI Moderations も専用項目にしないか**: 今回の目的はカテゴリ別 review ではなく、
  annotation API に送るかどうかを既存 rating で判断すること。`category_scores` は
  `openai_moderation_v1` の threshold table で canonical rating に畳み、専用 table は必要になるまで
  追加しない。

## Consequences

- 良い点: AI rating が canonical 値で `ratings` テーブルに保存され、「AIレーティング:
  未設定のみ」検索で保存済み画像が再対象にならない。特定レーティング検索も機能する。
- 良い点: 既存 tags/captions/scores 保存経路は不変。manual rating (`MANUAL_EDIT`) と
  AI rating の優先・分離 (`_apply_ai_rating_filter` の `Model.name != "MANUAL_EDIT"`)
  は保たれる。
- トレードオフ: 未知 scheme のモデルは AI rating が保存されず未設定のまま残る
  (`source_scheme="unknown"` 等)。新 scheme 追加時は `rating_mapper.py` の表更新が必要。
- 新しい rating モデル / scheme を追加する場合は `_LABEL_MAP` / `_SCHEME_ALIASES` に
  行を追加し、`tests/unit/domain/test_rating_mapper.py` にテストを追加する。
- OpenAI Moderations 由来 rating は `X/XXX` の場合に annotation API 送信を止める。`R` 以下は送信するため、
  `violence/graphic` / gore / 出血表現を過剰に除外しない。
- OpenAI category score を後から細かく検索する機能は初期実装では弱い。必要になった場合は
  `provider_batch_items.raw_response` の summary cache または専用 table を別 ADR で再検討する。

### Implementation Status (2026-05-27)

OpenAI Moderations preflight (Amendment 2026-05-27) は以下の PR で merged:

- image-annotator-lib #121 (T1): `webapi/openai_moderations.py` converter
- image-annotator-lib #122 (T2): `webapi/batch/adapters/openai.py` OpenAI Batch adapter
- LoRAIro #509 (T3): provider batch wiring (`task_type=rating_preflight` 透過、`model_id` 必須化、`omni-moderation-latest` 補完、GUI task selector)
- LoRAIro #510 (T4): `filter_excluded_by_rating()` による WebAPI annotation 送信前 prefilter
- LoRAIro #511: image-annotator-lib submodule pin を PR #122 merge commit に固定

実 OpenAI Moderations Batch contract の runtime validation は image-annotator-lib
`tests/runtime_validation/` 配下で ADR 0026 / ADR 0001 amended に従って行う。
LoRAIro 側 boundary 配線は `tests/integration/test_provider_batch_rating_preflight_e2e.py`
で deterministic に CI 監視する。

### Amendment 2026-06-07: 重複 submit 許容と rating upsert 方針の明記 (Issue #673)

`rating_preflight` では、`images list --unrated` で取得した未 rating 画像を submit しても、
import 前の同一画像を別 job で重複 submit してしまうことがある (submit 時点では rating が存在
しないため、重複を事前に防ぐ手段がない)。この挙動と対処方法を以下に明記する。

#### 重複 submit の許容

1. **DB スキーマ上は重複 submit を許容する。** `UNIQUE(job_id, custom_id)` のため同一 job 内の
   重複は防がれるが、別 job からの同一 `image_id` の submit は止めない。DB unique 制約も追加しない。
   理由: `submit` 時点では provider から結果が返っておらず、重複を hard error にすると正常な
   再試行 (job 失敗後の resubmit) も阻害する。

2. **raw moderation 結果は `provider_batch_items.raw_response` に job ごとに保持される。**
   重複 job ごとに別 row が作られるため、provider 側の raw response は全件監査可能。

3. **重複 submit の確認は `batch status --items` で行う。**
   ```bash
   lorairo-cli batch status <job_id> --project <project> --items
   ```
   出力には `image_id`, `custom_id`, `model_id`, `task_type`, `status`, `error_type` が
   含まれる。複数 job の items を横断確認することで重複 submit の有無を検出できる。

#### rating upsert 方針

4. **`ratings` テーブルの canonical rating は `(image_id, model_id)` キーの現在値 (latest win)
   として upsert される。** `batch import` 時の `_save_ratings()` は、同一 `image_id + model_id`
   の既存 row を UPDATE (上書き)、なければ INSERT する。

5. **重複 import の結果は「最後に import した job の result が canonical rating になる」。**
   ブレの履歴を保持したい場合は `provider_batch_items.raw_response` が監査/debug 用として残る。

6. **`batch import --json` の summary (`imported` / `skipped` / `errors` / `total`) は
   image 単位の集計であり、INSERT / UPDATE の内訳 (ratings_inserted / ratings_updated) は
   現時点では出力しない。** 理由: `_save_ratings()` 内部の update / insert 区別カウンタを
   返すには複数レイヤーの変更が必要なため、docs/CLI help でのセマンティクス明記を先行する。
   将来の改善が必要な場合は別 Issue で対応する。

## 関連

- Issue: NEXTAltair/LoRAIro#333
- Issue: NEXTAltair/LoRAIro#471
- Issue: NEXTAltair/LoRAIro#673
- Issue (umbrella): NEXTAltair/LoRAIro#507
- Upstream: NEXTAltair/image-annotator-lib#79 (parent) / #80 (rating 出力実装) /
  #81 (新規 rating model 候補) / #119 / #120
- ADR 0002 (Database Schema Decisions) — UNIQUE なしの方針と rating upsert の層別判断
- ADR 0015 (Manual Rating Storage Unification) — manual / AI rating の Rating テーブル統一
- ADR 0026 (On-Demand Runtime Validation Strategy) — 実 OpenAI Moderations Batch 検証境界
- ADR 0038 (Provider Batch API Integration Strategy) — OpenAI `/v1/moderations` Batch lifecycle
