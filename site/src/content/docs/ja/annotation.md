---
type: Guide
title: AIアノテーションとJobs
description: ローカル推論・WebAPI・Provider Batchを区別して実行します。
sidebar:
  order: 5
---

## 実行前の確認

ステージングの画像と枚数、使うモデル、生成する種類（tags、caption、score、rating）を確認します。利用可能なモデルは環境やプロバイダーによって異なります。

| 実行方法 | 処理場所と注意 |
| --- | --- |
| ローカルモデル | 手元で推論します。初回のモデル・タグDB取得には通信が必要な場合があります。 |
| WebAPI同期実行 | 対象画像とプロンプトを外部プロバイダーへ送信します。料金と送信許可を確認します。 |
| Provider Batch | 外部送信を非同期ジョブとして処理します。無料処理やローカル推論ではありません。 |

機密画像や第三者の画像を送る前に、送信してよいか確認してください。アプリはAPI費用の上限管理を行いません。再実行・リトライも追加リクエストになる場合があります。

## GUIで実行する

1. モデルを選び、対象枚数を確認します。
2. 「同期実行」または「Batch API 実行」を選びます。Batchの適格性はモデルによって異なります。
3. Jobsで進行状態・完了・失敗を確認します。
4. 完了後、画像のタグやキャプションを確認します。失敗時は原因を読んでから再試行します。

プロバイダー間の自動フォールバックはありません。Batchをキャンセルしても、既に行われた処理や課金が取り消されるとは限りません。

## CLIで同期実行する

```powershell
uv run --no-sync lorairo-cli models list
uv run --no-sync lorairo-cli annotate run -p "my-project" --model "MODEL_ID" --image-id 42 --image-id 57
```

`MODEL_ID`は一覧にあるモデルIDに置き換えます。画像は`--image-id`を繰り返して指定します。`--batch-size`は同期処理の分割幅で、Provider Batchへ送信する指定ではありません。

## Provider Batchの管理

CLIには`batch submit/list/status/fetch/import/cancel`があります。引数は`uv run --no-sync lorairo-cli batch --help`と各サブコマンドの`--help`で確認します。取得とDBへの取り込みは別の操作です。`import`はプロジェクトDBを更新します。

Batch対応は全プロバイダー共通ではありません。APIキーや画像を含む結果ファイルは公開しないでください。
