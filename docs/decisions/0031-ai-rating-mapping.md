# ADR 0031: AI Rating Mapping to Canonical Rating

- **日付**: 2026-05-21
- **ステータス**: Accepted

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

3. **`r15` は `R` にマッピングする** (Issue #333 で「設定/方針で決定」とされた曖昧点)。
   「R15 (15 歳以上推奨)」を成人向け寄りに保守的に解釈し、`danbooru4` の
   `questionable→R` と同列に扱う。

4. **`XXX` は mapper から自動生成しない。** mapper の出力は `PG/PG-13/R/X` のみ。
   `XXX` は別基準 (手動・専用判定) なしに自動付与しない。

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

## 関連

- Issue: NEXTAltair/LoRAIro#333
- Upstream: NEXTAltair/image-annotator-lib#79 (parent) / #80 (rating 出力実装) /
  #81 (新規 rating model 候補)
- ADR 0015 (Manual Rating Storage Unification) — manual / AI rating の Rating テーブル統一
