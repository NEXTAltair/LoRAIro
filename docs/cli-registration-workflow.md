# 登録した画像だけを後続処理へ渡す

`images register --json` を実行すると、DB 登録の結果を入力ファイルごとの `kind=item` 行として出力します。各行には `input_path`、`outcome`(`registered`、`variant`、`duplicate`、`failed`)、`image_id`(未確定なら `null`)、`project`、`selected`、`error` が含まれます。パス検索や登録前後の pHash 差分から ID を推測する必要はありません。

## 対象 ID の選択ルール

- **既定の対象**: `registered` と `variant` のユニークな ID です。
- **重複を含める場合**: `--include-duplicates` を指定すると、別ディレクトリ由来を含む既存の `duplicate` ID も対象に含まれます。
- **重複入力の扱い**: 同じ ID が複数の入力に現れた場合、対象として最初に選ばれた行だけが `selected=true` になります。
- **件数フィールド**: 既存の sidecar 取込みと件数フィールドを維持します。`registered` は従来どおり `--include-duplicates` 時の重複成功も含み、`variant` は別版件数、`target_count` は対象のユニーク ID 数を表します。
- **DB を使わない経路**: DB を使わない Python 直接登録では ID を生成せず、従来の登録結果を返します。

## JSONL から ID ファイルを作成する

全段階で同じプロジェクトを指定してください。例のモデル ID は、利用環境で `models list` を実行して確認します。登録後の処理済み画像生成には `images process`(#1314)を使用します。なお、Windows のドライブパスは自動変換されないため、コンテナ環境ではマウント済みの Linux パスを指定してください。

```bash
lorairo-cli images register /mounted/incoming --project demo --json > registration.jsonl
```

ID ファイルへ変換する前に、終了コードが 0 であること、**かつ最後の行が成功した終端 `result` であること**を確認してください。以下の例は、失敗・中断・途中までの出力を完全な集合として誤認しないための変換スクリプトです。実行前に登録コマンドの終了コードを確認してください。

```python
import json
from pathlib import Path

records = [json.loads(line) for line in Path("registration.jsonl").read_text(encoding="utf-8").splitlines()]
assert records and records[-1].get("kind") == "result"
assert records[-1].get("ok") is True and records[-1].get("status") == "success"
assert records[-1]["project"] == "demo"
ids = [r["image_id"] for r in records[:-1] if r.get("kind") == "item" and r.get("selected")]
assert len(ids) == len(set(ids)) == records[-1]["target_count"]
assert 0 < len(ids) <= 100_000  # 空や上限超過を切り詰めない
Path("registered-ids.txt").write_text("\n".join(map(str, ids)) + "\n", encoding="utf-8")
```

作成した ID ファイルを後続のコマンドへ渡します。

```bash
lorairo-cli images process --project demo --image-ids-file registered-ids.txt --resolution 512 --json
lorairo-cli batch submit --project demo --model openai/omni-moderation-latest --task-type rating_preflight --image-ids-file registered-ids.txt --resolution 512 --json
lorairo-cli annotate run --project demo --model LOCAL_MODEL_ID --image-ids-file registered-ids.txt --resolution 512 --batch-size 10 --json
lorairo-cli export create --project demo --image-ids-file registered-ids.txt --output exported
```

### 後続処理での注意点

- **Batch の非同期性**: Batch は非同期で実行されます。後続のアノテーションにレーティング結果が必要な場合は、対応ジョブの `fetch` と `import` を完了してから進んでください。
- **出力先の分離**: `annotate run` は DB への保存のみを行います。ファイル出力には `export create` を使い、未対応の `--output` は渡さないでください。
- **ID のスコープ**: 裸の ID はプロジェクト内でのみ有効です。別プロジェクトにも同じ番号が存在する場合、ID ファイルだけでは取り違えを検出できません。

## 入力範囲と処理順序

### ID ファイルの形式と排他オプション

- ID ファイルは UTF-8 エンコーディングで、改行またはカンマ区切りの正整数を記述します。上限は 100,000 ユニーク ID です。
- 重複する ID は最初に出現した順序を保って排除します。
- 存在しないファイル、空ファイル、不正な UTF-8、不正な ID、上限超過は機械可読なエラーになります。明示入力から全件選択へフォールバックすることはありません。
- `annotate run --image-id`(反復指定)と `--image-ids-file` は排他です。
- `batch submit --image-ids`(CSV 指定)と `--image-ids-file` も排他です。

### 注釈と Batch の対象解決

注釈(`annotate run`)では、入力全体の存在確認を行ったあと、`--unrated` や `--missing-model` などとの積集合を取得します。その後、ID 昇順・offset・limit の順に適用します。入力外のメタデータを先読みすることはありません。

- 従来の反復 ID 経路では選択上限 500 件を維持します。
- ファイル経路では 500 件単位で DB から取得し、`min(batch_size, 500)` 件単位で画像をロードして処理します。解像度選択はそのあとで行います。
- 処理済み画像がない ID は注釈では `skipped` になり、全件欠損している場合は失敗終了します。
- Batch では、処理済み画像の欠損を送信前にエラーとして検出します。
- `--resolution` を省略して原画像を直接渡すことを防ぐ既存ガードも維持します。
- Batch で解像度に `0` を指定した場合は最小解像度を、正の値を指定した場合は従来の closest / exact 選択を適用します。

## 部分失敗と再開

### 登録(`images register`)

登録の終端 `result` には `status`(`success`、`partial_success`、`failed`)、`ok`、既存件数、`project`、`target_count`、`interrupted`、`unprocessed` が含まれます。大量の item を終端行へ再格納することはありません。

- **エラー詳細のサンプル**: 終端の `error_details` は最大 100 件のサンプルです。省略がある場合は `error_details_truncated=true` になります。実際の失敗件数は `errors` で確認し、個別の完全なエラーは各 item の `error` を参照してください。ID 集合自体は切り詰めません。
- **sidecar 取込み失敗時の扱い**: 画像行の登録後に sidecar 取込みが失敗・中断した場合も、確定済みの `image_id` と登録 `outcome` を保持します。この item は `error` を持ち、終端では成功件数ではなく `errors` に数えます。`selected` は登録 `outcome` と重複選択方針から決まるため、確定した新規・別版 ID を復旧用に保持できます。終端が失敗している場合は後続処理を自動実行せず、sidecar の保存状態を確認してください。
- **バイナリ様 sidecar のスキップ**: 復号結果に NUL を含む sidecar(全ゼロや BOM のない UTF-16 を含む)はバイナリ様とみなし、警告ログを残して取り込まずに画像登録を続けます。このスキップは `errors` に数えません。
- **Python API と終了コード**: Python API の既定である `collect_items=True` は、従来どおり全エラー詳細を保持します。終了コードは登録失敗・中断が 1、正常な重複スキップや空ディレクトリが 0 です。書き込み失敗や終端欠落があると完全な登録集合を保証できないため、切り詰めた集合をそのまま後続処理へ渡さないでください。

### 明示 ID 注釈(`annotate run`)

明示 ID での注釈では、既存の annotation 行に加えて、各入力 ID につき 1 回 `type=annotation_outcome` 行を出力します。`status`(`completed`、`failed`、`skipped`、`unexecuted`)と `saved` で DB 保存を確認できます。

- 一部のモデルのみ失敗した画像は、保存済み情報を保持しつつ `failed` になります。
- 例外や中断が発生した場合は、確定済みの結果を維持したうえで、当該実行単位の未確定 ID を `failed`、残りを `unexecuted` とします。
- 事前準備中の予期しない例外や中断では、推論を開始していない対象 ID をすべて `unexecuted` とし、失敗終端を返します。
- API キー不足などの意図した入力検証エラーは、従来どおり入力エラーとして扱います。
- 終端 `result` は集計値のみを持ち、失敗または未実行がある場合は `ok=false`、exit 1 で終了します。

### Batch 送信(`batch submit`)

Batch では、DB の取得単位とは独立した Provider adapter 上限(500 件)ごとにジョブを分割します。送信前に全入力の存在・画像ファイル・要求構築を検証します。

- `type=batch_submission` 行に `status`(`submitted`、`failed`、`unsubmitted`)、`image_ids`、`job_id`、`reason` を出力します。
- 各ジョブの送信成功直後に割当集合を出力するため、後続ジョブが失敗しても先行ジョブの ID を失いません。
- 終端 `result` には `job_ids` と `submitted`・`failed`・`unsubmitted` の各件数が含まれます。
- 互換フィールドの `job_id` と `job` は先頭ジョブのみを指します。先頭のメタデータを取得できなかった場合は `job=null` を維持し、後続ジョブの情報で上書きしません。
- 送信中に発生した例外は、プロバイダ側で受け付けられたあとに起きた可能性があります。そのため `failed` は送信未確認の集合を表します。プロバイダ側とローカルのジョブ状態を確認してから再開し、送信済み集合を含む全件の自動再送は行わないでください。
