---
type: Reference
title: Read-only duplicate candidate report
status: Accepted
tags: [cli, phash, image-review]
---

# 保存済み pHash による重複候補レポート

```sh
lorairo-cli --json images duplicates --project training --max-distance 4 --limit 100
```

`images duplicates` は既存のプロジェクト全体を読み取り、保存済みの 64 ビット知覚ハッシュ (pHash) を使って重複候補のクラスタを報告します。画像ファイルを開く処理、ハッシュ計算、画像登録、ファイル削除、データ更新、データベース準備、モデルプロバイダー呼び出しは一切行いません。グローバルの `--read-only` オプションを省略した場合でも、常に既存の厳格な読み取り専用 DB アクセスポリシーを使用します。未準備または非互換のプロジェクトは `PRECONDITION_FAILED` (exit 1) を返します。CLI ログおよび SQLite の WAL / 共有メモリ管理は、既存の読み取り専用ランタイムポリシーに従います。

## 距離とクラスタリング

`--max-distance` には 0 から 64 までの整数を指定できます。これは保存済み pHash 同士をリンクする最大のハミング距離 (異なるビット数) です。0 は完全一致するハッシュのみをグループ化し、64 は有効なハッシュを持つすべての画像を連結します。デフォルト値の 4 は 64 ビット中 4 ビットの差異 (6.25%) を許容します。これはレビュー開始用の小さな許容値であり、データセットに合わせて校正されたしきい値や視覚的類似度の割合ではありません。候補を増やしたい場合は値を大きくしてください。

クラスタは **連結成分 (connected components)** です。A と B が近く、B と C が近い場合、A と C の距離がしきい値を超えていても 3 枚は同じクラスタに属します。各メンバーは何らかの条件を満たすリンク列でつながっていますが、他のすべてのメンバーと近いとは限りません。結果は決定論的であり、メンバーは画像 ID 昇順、クラスタは最小 ID 昇順で並び、`cluster_id` にはその最小 ID が使われます。これは計算された連結成分の識別子であり、永続的な DB レコードではありません。

出力はあくまでレビュー用の候補です。同一または類似の pHash には、カラー版とグレースケール版、解像度違い、あるいは無関係な画像が含まれることがあります。一方、トリミングや編集が異なる画像は見逃される場合があります。このレポートは候補を削除可能と判定するものではなく、[ADR 0061](decisions/0061-phash-duplicate-variant-classification.md) に記載された登録時の重複 / バリアント分類も変更しません。

## 計算量と出力の上限付き全件検出

サービスはハッシュを読み込む前にプロジェクトの画像枚数を数えます。**10,000 枚を超える**場合は比較前に `RESULT_SET_TOO_LARGE` (exit 2) を返し、詳細に `matched` と `limit` を含めます。この件数にはハッシュ欠損や無効ハッシュの画像も含まれます。件数取得と読み込みの間にプロジェクトが増加した場合に備え、2 回目のサイズ検証も行います。暗黙の部分スキャンは行わず、`--limit` を小さくしてもこの入力上限はバイパスできません。

最初に同一ハッシュ同士をグループ化します。しきい値 1〜63 では、`ImageHash` のハミング距離と同等の XOR / popcount により、異なるハッシュの全ペアを比較します。一意な有効ハッシュ数を U とすると、比較回数は U(U-1)/2 回、最大 **49,995,000** 回です。しきい値 0 と 64 ではペア比較を行いません。`compared_hash_pairs` には実際に実行した異なるハッシュ間の比較回数を報告します。同一ハッシュは画像ペアごとに比較せず連結します。実装は二乗サイズのエッジリストではなく連結成分の所属情報を保持します。

`--limit` には 1〜500 (デフォルト 100) を指定できます。これは出力するクラスタ行数 **および** 各クラスタ内に表示するメンバー数の上限です。検出処理とサマリー件数は、受理されたプロジェクト内の全画像を対象に算出します。出力が省略された場合は `clusters_truncated` とクラスタごとの `members_truncated` で明示し、全件の `cluster_count` と `member_count` をあわせて報告します。

## JSONL フィールド

各 `kind:item` には `cluster_id`、`member_count`、`members`、`members_truncated` が含まれます。各メンバーには `image_id`、`stored_image_path`、`original_image_path`、および小文字に正規化された `phash` が含まれます。パスは DB に保存された文字列そのままを出力し、ファイルの存在確認や画像内容の検証は行いません。

末尾の `kind:result` には `ok:true`、`status:"success"`、`read_only:true`、`candidate_only:true`、`project` に加えて以下の件数が含まれます。

| フィールド | 意味 |
| --- | --- |
| `total_images` | 受理されたプロジェクトスナップショット内の全画像数 |
| `valid_phash_images` | 前後の空白を除去したあと有効な 16 桁 16 進ハッシュを持つ画像数 |
| `missing_phash_images` | 保存ハッシュが null または空文字の画像数 |
| `invalid_phash_images` | 空ではないが 16 桁の 16 進数でない値を持つ画像数 |
| `unique_phashes` | 一意な有効ハッシュ値の数 |
| `cluster_count` | 2 枚以上の画像を含む全連結成分の数 |
| `clustered_images` | それらの連結成分に属する画像数 |
| `unclustered_images` | 単独 (シングルトン) のまま残った有効ハッシュ画像数 |
| `returned_clusters` | 実際に出力されたクラスタ行数 |
| `compared_hash_pairs` | 実際に実行された異なるハッシュ間のペア比較回数 |

`total_images = valid_phash_images + missing_phash_images + invalid_phash_images` および `valid_phash_images = clustered_images + unclustered_images` が成り立ちます。欠損・無効なハッシュは集計されますが検出対象からは除外され、レポートがハッシュを補完したり再計算したりすることはありません。これらの件数が 0 でない場合やクラスタが 1 つも見つからない場合でも、レポート実行が正常に終われば exit 0 となります。無効な引数は exit 2 を返します。

結果にはさらに `max_distance`、`hash_bits:64`、`distance_metric:"hamming"`、`clustering:"connected_components"`、`limit`、`max_images:10000`、`max_pair_comparisons:49995000`、`clusters_truncated` が含まれます。

Python からの呼び出しには `lorairo.public_api.duplicate_report.report_duplicates(project_name, max_distance=4, limit=100)` を使用してください。型付きの `clusters` と `summary()` を持つ同じ `DuplicateReport` を返します。純粋関数の `analyze_saved_hashes` は、データベースや画像ファイルなしで検証できるよう合成の `SavedImageHash` レコードを受け取れます。

## Clef レビュー用のクラスタ代表画像 (`--representatives`)

```sh
lorairo-cli images duplicates --project training --representatives > representatives.txt
lorairo-cli review run --project training --image-ids-file representatives.txt
```

`--representatives` を指定すると、クラスタレポートの代わりに各重複クラスタから代表画像を 1 枚ずつ出力します。これにより [`review run`](cli.md) で代表画像のみを確認できます。

- **選定ルール**: 保存されているピクセル数 (`width × height`) が最大の画像を代表とします。同数の場合は最小の `image_id` を選びます。入力順にかかわらず、同じ入力からは常に同じ結果が得られます。幅・高さが欠損または 0 以下の場合はピクセル数不明とみなし、既知のピクセル数を持つ画像に必ず負けます。全メンバーが不明な場合は最小の `image_id` を選びます。保存済みの寸法のみを参照し、画像ファイルは開きません。
- **シングルトンは除外されます。** どのクラスタにも属さない画像 (ハッシュ欠損や無効ハッシュの画像を含む) は出力されません。これらを含めるオプションはありません。
- **全クラスタを出力します。** 切り詰めると残りの代表画像に到達できなくなるため、`--representatives` と `--limit` の併用は拒否されます (exit 2)。プロジェクト上限の 10,000 枚により、代表画像の出力は最大 5,000 枚に抑えられます。
- **プレーン出力**: stdout には `cluster_id` 昇順で 1 行につき 1 つの整数画像 ID のみを出力します。加工せずそのまま保存して `review run --image-ids-file` へ渡せます。サマリー、500 枚上限の警告、および参考情報である旨の注記は stderr に出力されます。クラスタがない場合、stdout は空で終了コードは 0 となります (空の ID ファイルを `review run` に渡すと、リクエスト送信前に `INVALID_INPUT`、exit 2 で拒否されます)。
- **JSONL 出力 (`--json`)**: 各 `kind:item` は `image_id`、`cluster_id`、`member_count`、`width`、`height`、`pixel_count` (不明時は `null`) を持ちます。末尾の `kind:result` は、クラスタ上限レポート専用フィールドである `limit`・`returned_clusters`・`clusters_truncated` を除いた上記の件数に加え、`representatives_only:true`、`representative_count`、`review_max_images:500`、`exceeds_review_max_images`、`reference_only:true` を含みます。JSONL ストリーム自体は ID ファイルではないため、`jq -r 'select(.kind=="item") | .image_id'` で ID を抽出してください。
- **500 枚のレビュー上限**: `review run` が 1 回の実行で受け付ける一意な画像は最大 500 枚です。これを超えると、プロジェクトを開く前かつリクエスト送信前に `RESULT_SET_TOO_LARGE` (exit 2) を返します。`exceeds_review_max_images` が true の場合 (または stderr に分割警告が表示された場合) は、`split -l 500 representatives.txt part-` などでリストを分割し、パートごとに `review run` を実行してください。

Python からの呼び出しでは `report_duplicates(...).representatives` (`cluster_id` 順、クラスタごとに 1 件の `DuplicateRepresentative` リスト、`limit` の制限なし) を参照できます。純粋関数の `analyze_saved_hashes` はデータベースなしで検証するため、任意の `width` / `height` を持つ `SavedImageHash` レコードを受け取ります。

### 結果は参考情報として扱ってください

代表画像の Clef レビュー結果は **参考情報のみ** です。pHash が近い画像同士が同じアノテーション誤りを共有することを示す正解データ (ground-truth) はないため、クラスタ内の他画像に対する根拠として使ってはいけません。代表画像からクラスタメンバーへのコピーは行われず、タグ・キャプション・画像の変更や削除も発生しません。本コマンドは読み取り専用であり、`review run` もデフォルトでは結果を保存しません (`--save-results` 指定時のみ保存します。詳細は [ADR 0095](decisions/0095-clef-review-batch-results.md) を参照してください)。
