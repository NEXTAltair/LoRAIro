# Decision-model experiments (#1366)

Jev / Clef を使い、タグ適合度、画像の品質スコア、手動スコアを手掛かりにした好み予測、
キャプションの文章品質と内容の一致を試す独立 CLI。アプリ、DB、モデル一覧には接続しない。
Python 3.12+ の標準ライブラリだけで動作し、追加依存や環境同期は不要。

## 起動

リポジトリルートから実行する。worktree では設定済みの共有環境を使用する。

```text
uv run --no-sync python scripts/probe_decision_models.py --cases scripts/decision_probe_cases.jsonl
```

既定は API を呼ばず、入力と要求を検証する dry run。
結果の `dry_run` はモデルが正しく判定したことを意味しない。
結果は gitignore 対象の `logs/decision-probes/results.json` に保存する。

Jev の文章チェック:

```text
uv run --no-sync python scripts/probe_decision_models.py --cases scripts/decision_probe_cases.jsonl --provider typesafe --task caption_check --live --output logs/decision-probes/jev-captions.json
```

`TYPESAFE_API_KEY` を起動するシェルの環境変数に設定する。スクリプトは `.env` を自動ロードしない。
キーをコマンド引数、ケース、結果ファイルへ書かない。

Clef / Clef-flash:

```text
uv run --no-sync python scripts/probe_decision_models.py --cases scripts/decision_probe_cases.jsonl --provider cloudflare --model clef-flash --live --output logs/decision-probes/clef-flash.json
```

`CLOUDFLARE_API_TOKEN`（または `CLOUDFLARE_AUTH_TOKEN`）と `CLOUDFLARE_ACCOUNT_ID` が必要。
Workers AI を利用できるアカウント／トークンで実行する。

既存 OpenRouter 設定を使って Jev の入口を試す場合:

```text
uv run --no-sync python scripts/probe_decision_models.py --cases scripts/decision_probe_cases.jsonl --provider openrouter --config config/lorairo.toml --task caption_check --limit 2 --live --output logs/decision-probes/openrouter-jev.json
```

`OPENROUTER_API_KEY` を優先し、明示 `--config` がある場合だけ `[api].openrouter_key` を読み取る。
System One endpoint / Jev の利用可否はアカウントとサービス側の提供状況に依存する。
HTTP 401 / 403 / 404 は入口の失敗であり、モデルの能力の判定材料にはしない。

`--task` は繰り返し指定できる。`--limit` はケース数。
好みケースは履歴あり／なしで各 1 回、質問が 64 件を超えるケースは分割して呼び出す。
`--attempts`（既定 2）には transient HTTP failure の再試行を含む。

## ケース

UTF-8 JSONL、1 行 1 ケース。`id` は一意、`task` は次のいずれか。

| task | 入力 | 判定 |
|---|---|---|
| `caption_check` | `caption`, `format` | 文法、不自然さ、途切れ、重複、矛盾、応答の混入 |
| `caption_match` | `caption` と `image` または `description` | キャプションの主張が根拠と一致するか |
| `tag_fit` | `tags` と `image` または `description` | 候補ごとの独立した適合確率 |
| `quality_score` | `image` または `description` | 一般的な技術・視覚品質のスコア |
| `preference` | 対象と `examples` | そのユーザーの手動スコアの予測 |
| `custom` | `state`, `questions`, 任意の `image` | 他の案用の独自質問 |

`format` は `sentence` / `phrases` / `tags`。短句・タグ列を文法エラー扱いしない基準を使う。
`caption_check` は画像を送信せず、文章としての質だけを調べる。

サンプルに含む好み履歴・正解は架空の動作確認用データ。本人の好みを学習済みという意味ではない。
品質スコアのサンプルには主観的な正解を付けていない。実画像と本人の評価を追加して比較する。

### 実画像

ケースの `image` は JSONL ファイルを基準にしたローカルパス。

```json
{"id":"image-tags-001","task":"tag_fit","image":"images/001.png","tags":["blue eyes","red hair"],"expected":{"tag_000":true,"tag_001":false}}
```

画像は Clef の `images` に data URL として埋め込む。PNG / JPEG / WebP、1 枚 4 MiB 以下、
ケース全体で 4 枚・合計 8 MiB 以下、送信 JSON は 13 MiB 以下。
解像度を 16 メガピクセル以下にして用意する。リサイズは行わない。
Jev を指定した画像ケースは、画像を捨てて続行せず `skipped` にする。

画像がなく `description` で代用した評価は `basis=text_proxy` と記録する。
実画像に対する精度は `basis=image` の結果で確かめる。両者の指標は別々に集計する。

### 好みの予測

```json
{"id":"holdout-001","task":"preference","image":"images/target.png","manual_score":8.2,"examples":[{"id":"past-001","image":"images/past.png","manual_score":9.1}]}
```

スコアは LoRAIro の DB と同じ 0.0–10.0（GUI 内部値 0–1000 ではない）。
5 段階の Score question を使い、返却される 0–4 の期待値を 0–10 へ換算する。
元の確率分布・confidence も保持する。Noul の適合確率には別の confidence 値を作らない。

対象の `manual_score` は結果の誤差計算だけに使い、API には送らない。
`examples` の手動スコアだけがモデルに渡る。対象を例に含めない。
同じ ID / 同じ画像パス / 同じ画像バイト列の混入はエラーにする。
テキストを根拠とする対象では、同一の記述を履歴に混ぜることもエラーにする。
対象 1 枚＋履歴画像 3 枚まで利用でき、テキスト記述の履歴も使える。

同じ対象を履歴あり／なしで評価する。未採点の対象は `manual_score` を省略する。
未採点をゼロ点として扱わない。
これは few-shot 個人化の実験で、モデルの重み更新や永続的な好み学習を行うスクリプトではない。
評価対象と履歴を分け、手動スコアに対する MAE が履歴なしより改善するか確認する。

### 他の案

`custom` では System One の `noul` / `choice` / `score` 質問を直接指定できる。
画像は 0 番目として参照する。データセットの特徴集計、クロップの適性、用途別の選択などに使える。

```json
{"id":"crop-001","task":"custom","image":"images/crop.png","state":{"purpose":"Learn sleeve embroidery","target_image_index":0},"questions":{"detail_visible":{"type":"noul","instructions":"Is the sleeve embroidery clearly visible in image 0?"}},"expected":{"detail_visible":true}}
```

`expected` は送信しない。Noul は boolean、Choice は選択肢キー、Score は数値。
`quality_score` / `preference` の正解は 0–10、custom Score の正解は question の段階番号を使う。
ケースの一括構築・検証を終えてから API を呼ぶ。

## 結果の読み方

結果はケース／モデル／根拠種別／好み履歴の有無ごとに保存する。
送信した要求のハッシュ、モデルが返した実際の ID、確率、スコア、usage、経過秒数を残す。
要求本文・画像 base64・認証情報は結果に保存しない。

- 正解付き Noul: 0.5 閾値の一致率、Brier score（小さいほど良い）。
- 正解付き Choice: 一致率。
- 正解付き Score: MAE（小さいほど良い）。
- 正解なし: 生の判定だけを保持し、精度の結論は出さない。
- `dry_run` / `skipped` / `error`: 精度指標へ入れない。live で成功がゼロなら終了コード 1。

少数の例で動いたことを採用判断に直結させず、実データの正常例・異常例・曖昧な例を追加する。
モデル／質問を変えた場合は `--output` を変えて結果を比較する。

### 初回の実 API 試行 (2026-10-06)

上記サンプル全件を OpenRouter の System One endpoint へ送信し、18 回すべて成功。
返却モデル ID は `typesafe/jev-1.13-20260917`。
文章チェックは正解付き 42 項目すべて一致、文章同士の内容一致は 2 項目、タグの代理評価は
4 項目すべて一致した。架空の好み 2 件では MAE が履歴なし 3.10、履歴あり 0.5125。
これらは小さな架空データ／テキストの試行で、実画像・本人の好みの精度を示す結果ではない。
Clef の実画像試行は Cloudflare 認証情報を設定して別途実行する。

一次仕様:

- [TypeSafe System One API](https://docs.typesafe.ai/api)
- [TypeSafe SDK の OpenRouter 接続例](https://docs.typesafe.ai/sdk/python/usage#configuring-the-base-url)
- [Jev の入力仕様](https://docs.typesafe.ai/concepts/state)
- [Clef の入力・出力スキーマ](https://developers.cloudflare.com/workers-ai/models/clef/)
- [Clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/)

## スクリプトの検証

```text
uv run --no-sync pytest -c scripts/tests/pytest.ini scripts/tests/test_decision_model_probe.py -q -o addopts=""
uv run --no-sync ruff check scripts/probe_decision_models.py scripts/tests/test_decision_model_probe.py
```

ここでのテストは送信形式、教師ラベルの分離、集計、エラー処理を確認する。実 API 精度は別途測る。
