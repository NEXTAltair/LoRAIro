---
type: ADR
title: AI Rating Mapping to Canonical Rating
status: Accepted (amended 2026-06-21)
timestamp: 2026-05-21
tags: []
---
# ADR 0031: AI Rating Mapping to Canonical Rating

## Context

image-annotator-lib は Issue #80(クローズ済み)により、レーティング出力をモデル固有の `RatingPrediction(raw_label, confidence_score, source_scheme)` のリストとして `UnifiedAnnotationResult.ratings` で返すようになった。ライブラリは LoRAIro の `PG` / `PG-13` / `R` / `X` / `XXX` へ変換せず、モデルが出力した生ラベル・信頼度・分類体系(`source_scheme`)を返す責務にとどめている。

しかし、LoRAIro 側の `AnnotationSaveService._append_model_result()` は `ratings` を `str(ratings)` で単純に文字列化していた。そのため、`raw_rating_value` と `normalized_rating` の両方に `"[RatingPrediction(...)]"` という不正な文字列が格納されていた。その結果、次の問題が発生していた。

- `normalized_rating` が正規値にならないため、特定レーティング検索(`_apply_ai_rating_filter` の通常分岐)で一切ヒットしない。
- DB に意味のある AI レーティングが保存されない。

レーティングはデータセットごとに分類体系が異なる(Danbooru 系の `general` / `sensitive` / `questionable` / `explicit`、e621 系の `safe` / `questionable` / `explicit`、`anime_rating` の `safe` / `r15` / `r18` など)。これらを LoRAIro 側で正規レーティングへ変換するマッパーが必要である。

## Decision

1. **モデル固有レーティングから正規レーティングへの変換は LoRAIro 側の責務とする。**
   純粋関数モジュール `src/lorairo/domain/rating_mapper.py` に集約する(`domain/quality_tier.py` と同じ派生ビューのパターン)。

2. **マッピング表(`(source_scheme, raw_label) -> canonical rating`)を以下のとおり定義する。**

   | `source_scheme`(エイリアス) | 生ラベル | 正規値 |
   |---|---|---|
   | `danbooru4`(`wdtagger`、`camie`) | `general` | `PG` |
   | `danbooru4` | `sensitive` | `PG-13` |
   | `danbooru4` | `questionable` | `R` |
   | `danbooru4` | `explicit` | `X` |
   | `e6213`(`z3d`、`danbooru3`) | `safe` / `general` | `PG` |
   | `e6213` | `questionable` | `R` |
   | `e6213` | `explicit` | `X` |
   | `sankaku3`(`anime_rating`) | `safe` | `PG` |
   | `sankaku3` | `r15` | `R` |
   | `sankaku3` | `r18` | `X` |
   | `binary_nsfw` | `sfw` | `PG` |
   | `binary_nsfw` | `nsfw` | `R` |
   | `openai_moderation_v1` | `pg` | `PG` |
   | `openai_moderation_v1` | `pg13` | `PG-13` |
   | `openai_moderation_v1` | `r` | `R` |
   | `openai_moderation_v1` | `x` | `X` |
   | `openai_moderation_v1` | `xxx` | `XXX` |

3. **`r15` は `R` にマッピングする。**
   Issue #333 で方針決定が必要とされていた点である。「R15(15 歳以上推奨)」を成人向け寄りに保守的に解釈し、`danbooru4` の `questionable` → `R` と同列に扱う。

4. **通常のモデル固有レーティングマッパーは `XXX` を自動生成しない。**
   Danbooru・e621・Sankaku・binary NSFW 系の出力は `PG` / `PG-13` / `R` / `X` の範囲に丸める。`XXX` は手動レーティング、または `openai_moderation_v1` のような専用判定スキームでのみ自動付与を許可する。

5. **保存先は既存の `ratings` テーブルとする。**
   分類体系ごとの新規テーブルや新規カラムは作らない。`raw_rating_value` にモデル固有ラベル、`normalized_rating` に LoRAIro 正規レーティングを保存する。

6. **`list[RatingPrediction]` は最高 `confidence_score` の 1 件に絞る。**
   `Rating` テーブルは `(image_id, model_id)` で upsert されるため、1 モデルにつき 1 行となる。`confidence_score` が `None` の予測は最下位扱いとし、すべて `None` または同値の場合は先頭(top-1)を採用する。

7. **マッピング不能(未知スキームまたは未知ラベル)の場合は保存せずスキップし、警告ログを出す。**
   不正な値を DB へ入れるよりも、対象画像を AI レーティング未設定のまま残す方が安全である。

8. **`source_scheme` は DB に保存しない。**
   `ratings` テーブルに保存先カラムがないため、マッパーの判定入力としてのみ使用する。

9. **後方互換の `str` / `list[str]` 経路を維持する。**
   `source_scheme` を持たない入力は正規値とみなし、`PG` / `PG-13` / `R` / `X` / `XXX` であればそのまま保存し、それ以外はスキップする。

### Amendment 2026-05-27: OpenAI Moderations preflight rating

LoRAIro #471 では、OpenAI Moderations Batch をアノテーション API 送信前のレーティング事前検査(preflight)として利用する。これは独立したモデレーションレビュー機能ではなく、既存レーティングパイプラインへの入力として位置づける。

決定事項は以下のとおりである。

1. **専用の `ModerationResult` DTO、専用 DB テーブル、専用永続化 API は追加しない。**
   image-annotator-lib は OpenAI Moderations のレスポンスを既存の `UnifiedAnnotationResult.ratings: list[RatingPrediction]` に畳み込む。

   ```python
   RatingPrediction(
       raw_label="r",
       source_scheme="openai_moderation_v1",
       confidence_score=0.78,
   )
   ```

2. **OpenAI の `category_scores` から最も重い LoRAIro レーティング候補を採用する。**
   カテゴリごとの個別事前検査ポリシーは LoRAIro 側に作らない。重み順は以下のとおりとする。

   ```text
   PG < PG-13 < R < X < XXX
   ```

3. **初期マッピングは単純な閾値表とする。**

   | OpenAI カテゴリ | スコア条件 | `raw_label` | 正規値 | 備考 |
   |---|---:|---|---|---|
   | `sexual` | `>= 0.98` | `xxx` | `XXX` | アノテーション API に送らない |
   | `sexual` | `>= 0.90` | `x` | `X` | アノテーション API に送らない |
   | `sexual` | `>= 0.60` | `r` | `R` | アノテーション API に送る |
   | `sexual` | `>= 0.30` | `pg13` | `PG-13` | アノテーション API に送る |
   | `violence/graphic` | `>= 0.50` | `r` | `R` | gore・出血・バトル漫画を送信対象に残す |
   | `violence` | `>= 0.60` | `pg13` | `PG-13` | アノテーション API に送る |
   | `self-harm` | `>= 0.70` | `r` | `R` | アノテーション API に送る |
   | `self-harm/intent` | `>= 0.70` | `r` | `R` | アノテーション API に送る |
   | `self-harm/instructions` | `>= 0.70` | `r` | `R` | アノテーション API に送る |

   どの条件にも一致しない場合は `raw_label="pg"` とする。

4. **初期対象カテゴリを画像レーティングに必要なものだけに絞る。**

   評価対象:
   - `sexual`
   - `violence`
   - `violence/graphic`
   - `self-harm`
   - `self-harm/intent`
   - `self-harm/instructions`

   初期実装で無視するカテゴリ:
   - `harassment`
   - `harassment/threatening`
   - `hate`
   - `hate/threatening`
   - `illicit`
   - `illicit/violent`
   - `sexual/minors`

   `harassment`・`hate`・`illicit` 系は画像単体のレーティングや事前検査ではなくテキストモデレーションの領域である。`sexual/minors` は OpenAI 公式ドキュメント上テキスト専用カテゴリであるため画像レーティングには使わない。`self-harm/intent` と `self-harm/instructions` は画像入力でもスコアが返るため、親カテゴリ `self-harm` と同じ `R` 判定に畳み込む。

5. **アノテーション API への送信可否は正規レーティングのみで判断する。**

   ```text
   PG / PG-13 / R -> annotation API に送る
   X / XXX        -> annotation API に送らない
   ```

   `violence/graphic` は `R` までに丸める。グロテスク表現や出血描写は Civitai および LoRAIro のレーティング上 `R` になり得るが、それだけでアノテーション API 送信を止めない。

6. **OpenAI Moderations Batch は既存の Provider Batch スキーマを使用する。**
   - `provider_batch_jobs.endpoint = "/v1/moderations"`
   - `provider_batch_items.task_type = "rating_preflight"`
   - `provider_batch_jobs.model_id` および `provider_batch_items.model_id` には `omni-moderation-latest` 等のモデレーションモデル台帳エントリを設定する。
   - モデレーションモデルの台帳エントリは `model_type="rating"`、DB の `model_types=["ratings"]` として登録し、`scores` や `tags` には分類しない。
   - `provider_batch_items.image_id` で対象画像と対応付ける。
   - `provider_batch_items.raw_response` は OpenAI モデレーションレスポンスの保存に使用してよい。
   - 正規レーティングは既存の `ratings` テーブルに保存する。

   `provider_batch_items.raw_response` は監査・デバッグ・将来の閾値調整用の補助情報であり、送信可否の SSoT にはしない。送信可否の SSoT は `ratings.normalized_rating` とする。

7. **LoRAIro はプロバイダー成果物の JSONL を直接パースしない。**
   OpenAI Batch の出力・エラー JSONL の取得とパース、Moderations レスポンスのカテゴリスコア抽出、`RatingPrediction` への畳み込みは image-annotator-lib の責務である。LoRAIro 側に OpenAI 固有の成果物パーサーを追加しない。

8. **レーティング専用モデルには `model_type="rating"` を使う。**
   `TaskCapability.RATINGS` は出力機能、`model_type="rating"` は主用途分類である。`AnimeRatingAnnotator` や OpenAI Moderations 事前検査のようにレーティングだけを返すモデルは `model_type="scorer"` に寄せず、LoRAIro DB では `model_types=["ratings"]` に写像する。一方、WDTagger や CamieTagger のようにタグとレーティングを両方返すモデルは従来どおり `model_type="tagger"` + `capabilities=["tags", "ratings"]` とし、DB では `["tags", "ratings"]` に分類する。スコアも返すレーティング対応 scorer も同様に `["scores", "ratings"]` を維持する。

参考:
- OpenAI Moderation guide: https://platform.openai.com/docs/guides/moderation/overview
- OpenAI Moderations API reference: https://platform.openai.com/docs/api-reference/moderations
- OpenAI Batch API guide: https://platform.openai.com/docs/guides/batch
- ADR 0038: Provider Batch API Integration Strategy
- Civitai content levels: `docs/specs/civitai-content-levels.md`

### 未マッピングラベルの扱い

マッパーが `source_scheme` と `raw_label` を解決できない場合、LoRAIro は誤った `normalized_rating` を保存しない。該当レーティングは保存対象から外し、警告を出力する。

未知ラベルは主に以下のケースで発生する。

- image-annotator-lib に新しい `source_scheme` が追加されたが、LoRAIro 側のマッパーが未対応である。
- 既存スキームに新しいラベルが追加された(例: `danbooru4` に未知のレーティング段階が追加される)。
- モデルカードや `config.json` のラベル表記が変わった(例: `sfw` を想定していたが `normal` や `safe_for_work` が返る)。
- プロバイダーや WebAPI がプロンプトにない自由記述を返す(例: `probably safe`、`borderline`、`adult`)。
- レーティングではないコンテンツカテゴリが混入する(例: `anime picture`)。
- `source_scheme` が欠落または誤記されている。

これらを `PG` や `UNRATED` に丸めると安全側の判定を誤る。未知ラベルは保存せず「未判定」として残し、マッパー追加・モデルアダプター修正・手動レーティングのいずれかで解決する。

## Rationale

- **なぜ `domain/` に置くか**: `quality_tier.py` がすでに `(model_name, raw_label) -> QualityTier` の純粋マッピングを `domain/` で担っている。レーティングマッパーも生アノテーションを変更しない派生ビュー計算であり性質が同じため、レイヤーの一貫性を保つ。
- **なぜマッピング不能時にスキップするか**: ADR 0015 の「書き込み・読み込みの対称性」の教訓に従い、`normalized_rating` は検索フィルタが参照する正規集合に限定する。未知値を保存すると「保存は成功したが検索で 0 件」という静かな不整合を生む。
- **なぜ最高信頼度を採用するか**: 現状のライブラリは ONNX タガーで argmax 済みの 1 要素リストを返すが、将来のマルチラベルレーティング分類器に備え、複数要素のリスト入力でも決定的に 1 行へ正規化できるようにする。
- **スキームエイリアスを設ける理由**: ライブラリが現在出力するのは `danbooru4` と `e6213` のみだが、Issue #81 の新規レーティングモデル候補(`anime_rating` 等)に備え、表記揺れやモデル系統差を前方互換で吸収しておく。
- **なぜ Civitai 互換を優先するか**: LoRAIro のレーティングはデータセット作成だけでなく、Civitai 投稿・WebAPI 投入・NSFW 除外の判断にも使われる。Civitai の閲覧・生成制限では `R` 以上が成人向け・NSFW 側として扱われるため、`questionable`・`r15`・binary `NSFW` のような曖昧なシグナルは `PG-13` ではなく `R` に寄せる。これにより、LoRAIro 既存の NSFW 除外(`R` / `X` / `XXX`)と意味が一致する。
- **なぜ binary NSFW を専用項目にしないか**: binary NSFW は細かなレーティングを決めるより API 送信可否や除外判定に使うシグナルである。専用カラムを増やすと既存のレーティングおよび NSFW フィルタと二重管理になるため、永続化が必要な場合は `SFW -> PG`、`NSFW -> R` として既存レーティングレコードへ寄せる。
- **なぜ OpenAI Moderations も専用項目にしないか**: 今回の目的はカテゴリ別レビューではなく、アノテーション API へ送るかどうかを既存レーティングで判断することである。`category_scores` は `openai_moderation_v1` の閾値表で正規レーティングへ畳み込み、専用テーブルは必要になるまで追加しない。

## Consequences

- **良い点**: AI レーティングが正規値で `ratings` テーブルに保存され、「AI レーティング: 未設定のみ」検索で保存済み画像が再対象にならなくなる。特定レーティング検索も正常に機能する。
- **良い点**: 既存のタグ・キャプション・スコア保存経路は変更されない。手動レーティング(`MANUAL_EDIT`)と AI レーティングの優先・分離(`_apply_ai_rating_filter` の `Model.name != "MANUAL_EDIT"`)も維持される。
- **トレードオフ**: 未知スキーム(`source_scheme="unknown"` 等)のモデルは AI レーティングが保存されず未設定のまま残る。新スキーム追加時は `rating_mapper.py` の表更新が必要になる。
- 新しいレーティングモデルやスキームを追加する場合は、`_LABEL_MAP` と `_SCHEME_ALIASES` に行を追加し、`tests/unit/domain/test_rating_mapper.py` にテストを追加する。
- OpenAI Moderations 由来のレーティングでは `X` / `XXX` のみアノテーション API 送信を止める。`R` 以下は送信するため、`violence/graphic`・gore・出血表現を過剰に除外しない。
- OpenAI カテゴリスコアを後から細かく検索する機能は初期実装では弱い。必要になった場合は、`provider_batch_items.raw_response` のサマリキャッシュまたは専用テーブルを別 ADR で再検討する。

### 実装状況(2026-05-27)

OpenAI Moderations 事前検査(Amendment 2026-05-27)は以下の PR でマージ済みである。

- image-annotator-lib #121(T1): `webapi/openai_moderations.py` コンバーター
- image-annotator-lib #122(T2): `webapi/batch/adapters/openai.py` OpenAI Batch アダプター
- LoRAIro #509(T3): プロバイダーバッチ配線(`task_type=rating_preflight` 透過、`model_id` 必須化、`omni-moderation-latest` 補完、GUI タスクセレクター)
- LoRAIro #510(T4): `filter_excluded_by_rating()` による WebAPI アノテーション送信前プレフィルタ
- LoRAIro #511: image-annotator-lib サブモジュールピンを PR #122 のマージコミットに固定

実 OpenAI Moderations Batch 契約の実行時検証は、image-annotator-lib の `tests/runtime_validation/` 配下で ADR 0026 および ADR 0001 amended に従って行う。LoRAIro 側の境界配線は `tests/integration/test_provider_batch_rating_preflight_e2e.py` で決定論的に CI 監視する。

### Amendment 2026-06-07: 重複 submit 許容と rating upsert 方針の明記(Issue #673)

`rating_preflight` では、`images list --unrated` で取得した未レーティング画像を投入(submit)しても、インポート前の同一画像を別ジョブで重複投入してしまうことがある。投入時点ではまだレーティングが存在しないため、重複を事前に防ぐ手段がないからである。この挙動と対処方法を以下に明記する。

#### 重複投入の許容

1. **DB スキーマ上は重複投入を許容する。**
   `UNIQUE(job_id, custom_id)` により同一ジョブ内の重複は防がれるが、別ジョブからの同一 `image_id` の投入は止めない。DB の一意制約も追加しない。投入時点ではプロバイダーから結果が返っておらず、重複をハードエラーにするとジョブ失敗後の正常な再投入も阻害するためである。

2. **生のモデレーション結果は `provider_batch_items.raw_response` にジョブ単位で保持する。**
   重複ジョブごとに別行が作られるため、プロバイダー側の生レスポンスは全件監査できる。

3. **重複投入の確認は `batch status --items` で行う。**

   ```bash
   lorairo-cli batch status <job_id> --project <project> --items
   ```

   出力には `image_id`・`custom_id`・`model_id`・`task_type`・`status`・`error_type` が含まれる。複数ジョブのアイテムを横断確認することで、重複投入の有無を検出できる。

#### レーティング upsert 方針

4. **`ratings` テーブルの正規レーティングは `(image_id, model_id)` キーの現在値(後勝ち、latest win)として upsert する。**
   `batch import` 時の `_save_ratings()` は、同一 `image_id`・`model_id` の既存行があれば UPDATE(上書き)、なければ INSERT する。

5. **重複インポートでは「最後にインポートしたジョブの結果」が正規レーティングになる。**
   判定のブレ履歴を確認したい場合は、`provider_batch_items.raw_response` が監査・デバッグ用として残る。

6. **`batch import --json` のサマリ(`imported` / `skipped` / `errors` / `total`)は画像単位の集計であり、INSERT / UPDATE の内訳(`ratings_inserted` / `ratings_updated`)は現時点では出力しない。**
   `_save_ratings()` 内部の更新・挿入カウンタを返すには複数レイヤーの変更が必要になるため、ドキュメントと CLI ヘルプでの意味論明記を先行する。将来の改善が必要な場合は別 Issue で対応する。

## 関連

- Issue: NEXTAltair/LoRAIro#333
- Issue: NEXTAltair/LoRAIro#471
- Issue: NEXTAltair/LoRAIro#673
- Issue(親): NEXTAltair/LoRAIro#507
- 上流 Issue: NEXTAltair/image-annotator-lib#79(親)/ #80(レーティング出力実装)/ #81(新規レーティングモデル候補)/ #119 / #120
- ADR 0002(Database Schema Decisions)— UNIQUE なしの方針とレーティング upsert の層別判断
- ADR 0015(Manual Rating Storage Unification)— 手動・AI レーティングの Rating テーブル統一
- ADR 0026(On-Demand Runtime Validation Strategy)— 実 OpenAI Moderations Batch 検証境界
- ADR 0038(Provider Batch API Integration Strategy)— OpenAI `/v1/moderations` Batch ライフサイクル

### Amendment 2026-06-21: 評価スコアカードの AI・手動表示分離(Issue #825)

評価・スコア編集カード(`RatingScoreEditWidget`、Issue #812)は AI セクション(読み取り専用)と人間セクション(手動編集可能)に分かれている。当初は両セクションへリポジトリ解決済みの `rating_value` / `score_value`(手動優先・なければ AI の解決済み値)を渡していたため、AI セクションに「人間優先で解決された値」が表示され、純粋な AI 判定を確認できなかった。

決定事項は以下のとおりである。

1. **AI セクションは純粋な AI 値を読み取り専用で表示する。**
   - AI レーティング: `MANUAL_EDIT` を除外した最新の `Rating.normalized_rating`。なければ未設定(空)。
   - AI スコア: AI スコア行のみ(`is_edited_manually=False`)のモデル別最新値を `calibrate_to_display` で 0–10 化した加重平均(スコア導出は Issue #626 / ADR 0028 を踏襲)。AI スコア行がなければ未設定(`None`、UI 表示は `"--"`)。

2. **人間セクションは手動値のみを編集可能表示する。**
   - 手動レーティング: 最新の `MANUAL_EDIT` による `Rating.normalized_rating`。なければ未設定(`----`)。
   - 手動スコア: 最新の手動スコア行(`is_edited_manually=True`)。なければ未設定(UI 表示は `"--"`、スライダーは中立位置とし、ユーザーが操作して初めて手動値が確定する)。

3. **解決済み値(`rating_value` / `score_value`)は維持する。**
   フィルタ・検索・その他の利用箇所は従来どおり「手動優先・なければ AI」の解決済み値を使う。AI と手動の分離は表示面(スコアカード)のための追加情報であり、解決規約(Issue #4 / #626)は変更しない。

4. **リポジトリが AI・手動分離値を公開する。**
   `ImageRepository` はメタデータに `ai_rating_value`・`manual_rating_value`・`ai_score_value`・`manual_score_value` を追加する。GUI 側で `ratings` や `scores` リストから再導出して較正ロジックを二重持ちしない(SSoT はリポジトリとする)。

関連:
- ADR 0015: Manual Rating Storage Unification(`MANUAL_EDIT` 一元化)
- ADR 0028: Score Labels Usage and Display
- Issue #4 / #626: `rating_value` / `score_value` 解決規約
- Issue #812: 評価スコアカード AI 併記
