# CLI レーティング事前チェックワークフロー

このドキュメントでは、OpenAI Moderation を使って CLI から画像へレーティングを付与する手順を説明します。少数の画像には同期実行を、大規模な画像セットには Provider Batch を使ってください。

## 前提条件

- CLI 設定に OpenAI API キーを設定しておきます。
- プロジェクトへ画像を登録しておきます。
- バッチジョブを送信する前に、プロジェクト DB のモデル一覧を更新しておきます。

```bash
lorairo-cli project create main_dataset
lorairo-cli images register /path/to/images --project main_dataset
lorairo-cli models refresh --project main_dataset
lorairo-cli models list --category rating
```

`openai/omni-moderation-latest` または他の `openai/omni-moderation-*` レーティングモデルが一覧に表示されることを確認してください。

## 同期実行(Synchronous Path)

結果をすぐに得たい場合や、少数の画像だけを処理したい場合に使用します。

```bash
lorairo-cli annotate run \
  --project main_dataset \
  --model openai/omni-moderation-latest \
  --resolution 512
```

`--resolution 512`(または `lorairo-cli images process` で生成した任意の解像度)を指定してください。これにより、`annotate run` は元画像ではなく処理済み画像を対象として動作します。通常のアノテーション保存経路を通じ、moderation のレーティング結果が `ratings` テーブルへ保存されます。

## Provider Batch による非同期実行

非同期処理が適している大規模な画像セットに使用します。

### 1. 未レーティング画像の一覧取得

最初に、まだレーティングが付いていない画像を一覧取得します。読み取り・一覧系コマンドは count-first 設計(ADR 0060)のため、既定では件数のみを返します。実データ(`image_id` と `file_path`)を取得するには `--fetch` を指定してください。

```bash
# 件数のみ (count-first の既定)
lorairo-cli images list --project main_dataset --unrated --limit 50

# 実データ (image_id + file_path) を取得
lorairo-cli images list --project main_dataset --unrated --fetch --limit 50
```

`--limit` の上限は 500(作業集合上限)です。上限を超える選択は `RESULT_SET_TOO_LARGE` で拒否されるため、絞り込み条件を追加してください。

エージェント駆動でこのワークフローを実行する場合は、グローバルの `--json` フラグ(または環境変数 `LORAIRO_CLI_JSON=1`)を指定します。これにより機械可読な JSONL モードへ切り替わり、標準出力が JSONL のみ(`kind` は `item`、`result`、`error`)になるため解析しやすくなります(ADR 0057)。

```bash
lorairo-cli --json images list --project main_dataset --unrated --fetch --limit 50
```

### 2. バッチジョブの送信

選択した画像 ID を OpenAI Moderations へ送信します。

```bash
lorairo-cli batch submit \
  --project main_dataset \
  --task-type rating_preflight \
  --model openai/omni-moderation-latest \
  --image-ids 2,7,11
```

### 3. 状態確認・結果取得・取り込み

ジョブの状態を確認し、必要に応じて正規化済みの結果を取得したうえで取り込みます。

```bash
lorairo-cli batch status 1 --project main_dataset
lorairo-cli batch fetch 1 --project main_dataset
lorairo-cli batch import 1 --project main_dataset
```

`rating_preflight` を使うには、以下の条件をすべて満たす必要があります。

- OpenAI への直接接続であること
- エンドポイントが `/v1/moderations` であること
- `openai/omni-moderation-*` モデルであること
- `ratings` モデル種別として登録されているモデルであること

## 重複送信とレーティングの upsert 挙動

### 重複送信が起きる理由

`images list --unrated` は、`ratings` 行がまだ存在しない画像を返します。そのため、バッチジョブを送信済みでも未取り込みの段階では、同じ画像が引き続き未レーティングとして表示されます。

失敗したジョブの再送などを可能にするため、再送信はハードエラーにはなりません。その結果、同じ `image_id` が複数のプロバイダバッチジョブに含まれることがあります。

### 重複送信を検出する方法

ジョブ内の画像ごとのアイテムを確認するには、`batch status --items` を使用します。

```bash
lorairo-cli batch status <job_id> --project <project> --items
```

JSON モードでは、最終の `result` 行の前に各アイテムが `ProviderBatchItemRecord` 行として出力されます。

```bash
lorairo-cli --json batch status <job_id> --project <project> --items
```

出力フィールドは `id`、`job_id`、`custom_id`、`image_id`、`model_id`、`task_type`、`status`、`error_type` です。複数のジョブ間でアイテムを比較すると、重複送信された画像を特定できます。

状態による絞り込みには `--item-status` を、ページネーションには `--limit` と `--offset` を使用します。

```bash
lorairo-cli batch status <job_id> --project <project> --items --item-status failed
```

### 取り込み時の upsert セマンティクス

`batch import` を実行すると、`(image_id, model_id)` をキーとした upsert によって `ratings` テーブルへ結果が保存されます。

- 対象の画像とモデルのレーティング行がすでに存在する場合は、**更新(上書き)**します。
- 行が存在しない場合は、**新規挿入**します。

同じ画像を含む 2 つ目のジョブを取り込むと、1 つ目の取り込み結果は上書きされます。つまり、**最後に取り込んだ結果が現在の正規値として採用されます**。

各ジョブの生レスポンスは、監査やデバッグのために `provider_batch_items.raw_response` へ保持します。なお、`batch import` のサマリー(`imported`、`skipped`、`errors`、`total`)は挿入・更新の回数ではなく画像数を集計します。設計の根拠は ADR 0031 Amendment 2026-06-07 を参照してください。

## 既知の制限事項

バッチ送信時の画像パス解決に関する問題は、Issue #528 で別途追跡しています。使用中のビルドにこの不具合が残っている場合、上記の手順が正しくてもバッチ経路が失敗することがあります。
