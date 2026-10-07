---
type: Reference
title: Clef によるアノテーション確認
tags: [clef, annotation, review, cloudflare]
---

# Clef によるアノテーション確認

Cloudflare Workers AI の Clef は、登録済みの画像とタグ・キャプションを照合する。
たとえば犬が写っていない画像の `dog` タグや、赤髪の人物を青髪と説明するキャプションを
個別の確認候補として表示する。判定は参考情報で、修正するかはユーザーが決める。

## 設定と実行

設定画面の API 欄で Cloudflare Account ID と API Token を設定する。
トークンには対象アカウントの Workers AI 実行権限が必要。
環境変数 `CLOUDFLARE_ACCOUNT_ID` と `CLOUDFLARE_API_TOKEN` も利用できる。
環境変数が設定されていればローカル設定より優先し、`CLOUDFLARE_AUTH_TOKEN` は
`CLOUDFLARE_API_TOKEN` が未設定の場合の代替として読む。

設定ファイル `config/lorairo.toml` の例:

```toml
[api]
cloudflare_account_id = "YOUR_ACCOUNT_ID"
cloudflare_api_token = "YOUR_API_TOKEN"

[annotation_review]
model = "clef-flash"      # clef も選択可
warning_threshold = 0.2
timeout = 60.0            # 各リクエストの上限秒数 (1–600)
```

画像を選択し、詳細欄の「この画像を確認」を押す。対象は表示中の 1 枚で、ステージ済み画像は含まない。
保存済みの元画像（クロップならそのクロップ画像）と
有効なタグ・キャプションを Cloudflare に送信する。有料 API の呼び出しはこの操作で開始し、
画像を選択しただけでは実行しない。soft-reject 済みの注釈は送信しない。

CLI は対象 ID を明示して実行する:

```bash
lorairo-cli --read-only review run --project my_dataset --image-ids 12,34
lorairo-cli --json review run --project my_dataset --image-ids-file ids.txt
```

CLI は 1 回につき最大 500 枚を確認する。ID ファイルを使う場合も同じ上限で、
超過時は通信・画像読み込み前に `RESULT_SET_TOO_LARGE` で拒否する。
CLI の結果は個々の候補に画像 ID、注釈 ID、種別、原文、状態、一致確率を付けて返す。
警告がある場合も正常な判定なら終了コードは 0。通信・解析失敗や古い判定は終了コード 1、
引数の誤りは 2。候補がない画像は未評価として報告し、通信しない。

## 一致確率と状態

一致確率は「このタグ・キャプションの内容が画像に支持されている」という質問が真である確率。
`0.03` は画像との一致が低い判定で、既定では `0.2` 未満を要確認とする。
ちょうど `0.2` は警告対象外。基準は設定で変更できるが、一般的な正解率を保証する値ではない。
警告がないことも注釈の正確さの保証にはならない。

| 状態 | 意味 |
|---|---|
| 要確認 | 一致確率が設定した基準を下回る |
| 警告対象外 | 評価が成功し、一致確率が基準以上 |
| 失敗 | 認証・通信・画像入力・応答解析などで評価できなかった |
| 未評価 | 候補がない、キャンセルされた、または前のリクエスト失敗で処理されなかった |
| 古い結果 | 画像ファイル・注釈・判定設定が変わったため、再確認が必要 |

64 件を超える注釈は分割して評価する。途中で失敗した場合、それまでの成功結果を残し、
失敗した部分と未評価の部分を分ける。自動再試行はしない。
確認中のキャンセルは次の送信を止める。送信済みの通信はタイムアウトまで終わらない場合がある。

## 複数画像の確認と結果の保存

「結果」タブの「検索で対象画像を選ぶ」から検索画面を開き、画像を選択して
「選択をステージングへ」を押す。「結果」タブに戻ると、対象の枚数とファイル名を表示する。
「対象一覧を開く」でステージ済み画像を確認・削除できる。「この N 枚を確認」を押すと開始する。
現在の選択画像や保存済み結果の画像は自動では対象に入らない。
1 回の対象は最大 500 枚。開始時の画像 ID を固定し、バックグラウンドで画像と有効な
タグ・キャプションの状態を読み取ってから Cloudflare に送信する。実行中に別の画像を選択したり
ステージングを変更したりしても、実行対象は変わらない。

画像ごとに最新の確認結果をプロジェクト DB に保存する。画像を切り替えたりアプリを再起動したり
しても結果は残る。結果には元の注釈 ID・文章、一致確率、警告や失敗の状態、判定モデル・基準、
確認時刻を保持する。途中で中止しても、それまでに完了した画像の結果は失われない。
CLI の明示実行は従来どおり読み取り専用で、結果を DB に保存しない。

「結果」画面で画像ごとの警告を確認し、手動確認の操作から検索画面の対象画像を開く。
結果一覧は直近の最大 500 枚を表示する。それ以前の結果も DB に保持し、対象画像の詳細欄から確認できる。
タグ・キャプションは既存の手動編集操作で修正する。画像や注釈、判定モデル・基準が変わった
結果は「古い結果」として扱い、現在の内容に対する一致確率として表示しない。

結果の保存には `annotation_review_results` テーブルを追加する。既存 DB は通常の
Alembic マイグレーションで更新される。保存対象は確認結果で、既存の注釈、confidence、
品質スコア、reviewed 状態、出力対象は変更しない。
文法の専用チェック、好みの予測、自動修復、出力対象の自動除外はこの確認の対象外。

## 表示例

以下は表示確認用の架空の結果で、実 API の精度検証ではない。

![画像ごとのタグ・キャプション確認結果](images/annotation-review-results.png)

![複数画像の確認開始。対象の枚数とファイル名を確認してから開始する](images/annotation-review-batch-start.png)

![結果画面のアノテーション確認と手動確認への導線](images/annotation-review-batch-results.png)

![Cloudflare の設定欄。保存済みトークンは表示しない](images/annotation-review-settings.png)

## ライブラリとの境界

`image_annotator_lib.decisions` は `annotate()` と別の公開 API。
Cloudflare 接続、ローカル画像の送信、真偽・候補選択・段階評価の型と検証を担当する。
LoRAIro は DB の注釈 ID を質問 ID (`tag_123` / `caption_456`) に対応付け、質問文、
警告基準、画面表示、編集後の無効化を担当する。
通常の annotation モデル選択や `AnnotationSaveService` に判定結果を流さない。

設計判断: [ADR 0094](decisions/0094-clef-annotation-review.md)、
[ADR 0095](decisions/0095-clef-review-batch-results.md)。
関連 Issue: [LoRAIro #1366](https://github.com/NEXTAltair/LoRAIro/issues/1366)、
[image-annotator-lib #167](https://github.com/NEXTAltair/image-annotator-lib/issues/167)。
API 仕様: [Cloudflare Clef-flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/)。
