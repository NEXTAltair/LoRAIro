# 登録した画像だけを後続処理へ渡す

`images register --json` は DB 登録が返した結果を入力ごとの `kind=item` 行として出力します。
`input_path`、`outcome` (`registered` / `variant` / `duplicate` / `failed`)、
`image_id` (未確定なら null)、`project`、`selected`、`error` を持ちます。
パス検索や登録前後の pHash 差分から ID を推測しません。

既定の対象は registered と variant のユニーク ID です。
`--include-duplicates` を指定すると、別ディレクトリ由来を含む既存 duplicate ID も対象です。
同じ ID が複数入力に現れても、対象として最初に選ばれた行だけが `selected=true` になります。
既存の sidecar 取込みと件数フィールドを維持します。`registered` は従来どおり
include-duplicates 時の重複成功も含み、`variant` は別版件数、`target_count` は対象のユニーク ID 数です。
DB を使わない Python direct 登録では ID を作らず、従来の登録結果を返します。

## JSONL から ID ファイルを作る

同じプロジェクトを全段階で指定します。例のモデル ID は利用環境の `models list` で確認してください。
登録後の処理済み画像生成には `images process` (#1314) を使用します。
Windows のドライブパスを自動変換しません。コンテナではマウント済み Linux パスを指定します。

```bash
lorairo-cli images register /mounted/incoming --project demo --json > registration.jsonl
```

終了コード 0 **かつ最後の行が成功した終端 result** であることを確認してから変換します。
以下は失敗・中断・途中までの出力を完全な集合として扱わない例です。登録コマンドの終了コードを先に確認してください。

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

```bash
lorairo-cli images process --project demo --image-ids-file registered-ids.txt --resolution 512 --json
lorairo-cli batch submit --project demo --model openai/omni-moderation-latest --task-type rating_preflight --image-ids-file registered-ids.txt --resolution 512 --json
lorairo-cli annotate run --project demo --model LOCAL_MODEL_ID --image-ids-file registered-ids.txt --resolution 512 --batch-size 10 --json
lorairo-cli export create --project demo --image-ids-file registered-ids.txt --output exported
```

Batch は非同期です。必要な rating 結果は対応 job の fetch/import を完了してから後続注釈へ進めます。
`annotate run` は DB 保存を行います。ファイル出力は `export create` を使い、未対応の `--output` は渡しません。
裸の ID はプロジェクト内のみ有効です。別プロジェクトにも同番号が存在する場合、ID ファイルだけでは取り違えを検出できません。

## 入力範囲と順序

ID ファイルは UTF-8 の改行／カンマ区切りの正整数、最大 100,000 ユニーク ID です。
重複は最初の順序で排除します。存在しないファイル、空、不正 UTF-8、不正 ID、上限超過は
機械可読エラーになります。明示入力から全件選択へ戻りません。
`annotate run --image-id` (反復) と `--image-ids-file`、
`batch submit --image-ids` (CSV) と `--image-ids-file` はそれぞれ排他です。

注釈は入力全体の存在確認後、`--unrated` / `--missing-model` 等との積集合を取得し、
ID 昇順、offset、limit の順に適用します。入力外の metadata を先読みしません。
従来の反復 ID 経路の選択上限 500 を維持し、ファイル経路は 500 件単位の DB 取得、
`min(batch_size, 500)` 件単位の画像ロードで処理します。解像度選択はその後です。
処理済み画像がない ID は注釈では skipped、全件欠損なら失敗終了です。
Batch は処理済み画像の欠損を送信前にエラーにします。
`--resolution` を省略して原画像を直接渡す既存ガードも維持します。
Batch の 0 解像度は最小、正値は従来の closest/exact 選択です。

## 部分失敗と再開

登録の終端 result は `status=success|partial_success|failed`、`ok`、既存件数、
`project`、`target_count`、`interrupted`、`unprocessed` を持ちます。大量 item を再格納しません。
終端の `error_details` は最大 100 件のサンプルです。省略があれば `error_details_truncated=true`、
実際の失敗件数は `errors` で確認し、各 item の完全な `error` を参照します。ID 集合は切り詰めません。
画像行の登録後に sidecar 取込みが失敗・中断した場合も、確定した `image_id` と登録 `outcome` を保持します。
この item は `error` を持ち、終端では成功件数ではなく `errors` に数えます。`selected` は登録 outcome と
重複選択方針から決めるため、確定した新規・別版 ID を復旧用に保持できます。終端失敗を無視して後続へ
自動実行せず、sidecar の保存状態を確認してください。
Python API の既定 `collect_items=True` は従来どおり全エラー詳細を保持します。
登録失敗・中断は exit 1、正常な重複 skip や空ディレクトリは exit 0 です。
書き込み失敗や終端欠落は完全な登録集合を保証しません。切り詰めた集合をそのまま処理しないでください。

明示 ID 注釈は既存 annotation 行に加え `type=annotation_outcome` 行を各入力 ID につき一度出力します。
`status=completed|failed|skipped|unexecuted` と `saved` で DB 保存を確認できます。
一部モデルのみ失敗した画像は、保存済み情報を保持しつつ failed になります。
例外・中断時は既に確定した結果を維持し、当該実行単位の未確定 ID を failed、残りを unexecuted とします。
事前準備の予期しない例外・中断では、推論を開始していない対象 ID をすべて unexecuted として失敗終端を返します。
API キー不足等の意図した入力検証エラーは従来どおり入力エラーとして扱います。
終端 result は集計だけを持ち、失敗・未実行があれば `ok=false`、exit 1 です。

Batch は DB の取得単位と独立した Provider adapter 上限 500 でジョブを分けます。
全入力の存在・画像ファイル・要求構築を送信前に検証します。
`type=batch_submission` 行に `status=submitted|failed|unsubmitted`、`image_ids`、`job_id`、`reason` を出力します。
各ジョブの成功直後に割当集合を出力し、後続失敗でも先行 job ID を失いません。
終端 result は `job_ids` と submitted/failed/unsubmitted 件数を持ちます。
互換フィールド `job_id` と `job` は先頭ジョブだけを指します。先頭の metadata を取得できなければ `job=null` を維持し、後続ジョブの情報で置き換えません。
送信中の例外は Provider 側受付後に発生した可能性があります。failed は送信未確認の集合です。
Provider とローカル job 状態を確認してから再開し、送信済み集合を含む全件の自動再送は行いません。
