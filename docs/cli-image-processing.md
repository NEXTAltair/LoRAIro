---
type: Reference
title: CLI offline image processing
status: Accepted
tags: [cli, images, processing]
---

# オフライン処理済み画像の生成

`images process` は、登録済みの元画像をアノテーション・Provider Batch・エクスポートで使用する処理済み画像パスへ結び付けます。元ファイルと画像 ID はそのまま保持します。

```bash
lorairo-cli --json images process --project dataset --image-ids-file ids.txt --resolution 512
lorairo-cli --json annotate run --project dataset --image-id 1 --model local-model --resolution 512
lorairo-cli --json batch submit --project dataset --image-ids 1 --model provider/model --resolution 512
lorairo-cli --json export create --project dataset --image-ids-file ids.txt --resolution 512 --output exported
```

`--image-ids` (CSV、最大 500 件) と `--image-ids-file` (改行 / カンマ区切り、最大 100,000 件) のどちらか 1 つを必ず選択してください。空の入力は `INVALID_INPUT` (exit 2) です。重複する ID は 1 回だけ処理します。選択された ID セット外の画像が登録・処理されることはありません。存在しない ID や破損・欠損した元画像は個別の失敗として報告されます。

解像度には目標とする長辺サイズを指定します (32〜8192 の 32 の倍数)。既存の CPU パイプラインにより自動クロップ、色正規化、Lanczos リサイズを行い、縦横サイズを 32 の倍数へ揃えます。極端に細長く、いずれかの辺が 0 になる画像は画像単位のエラーで失敗します。推奨解像度バケットや設定済みのアップスケーラーが明示的なサイズ指定を上書きすることはありません。モデルの読み込み・ダウンロードや推論 API 呼び出しは行わず、GPU も不要です。小さな元画像も通常の Lanczos 補間で拡大される場合があり、学習済みモデルは呼び出しません。

指定解像度に完全一致する有効かつデコード可能な出力がすでにあり、寸法・モード・アルファが DB レコードと一致する場合は、元画像の存在とデコード可能性を確認したうえでスキップします。同じ厳密解像度の行が複数ある場合は、アノテーション / Batch / エクスポートの選択と同じく最初の厳密一致行を使用します。最初の行が破損している場合、あとの有効ファイルへスキップするのではなく最初の行を修復します。近傍解像度で要求サイズを代替することはありません。欠損または破損した厳密出力は既存の処理済みパス上で再構築します。`--rebuild` を指定すると有効なファイルも再生成します。置き換えは同一ディレクトリ内の一時ファイルとアトミックリネームで行い、元画像行や処理済み画像 ID は変更しません。再生成された寸法が既存の DB メタデータと異なる場合、不整合なデータでファイルを置き換えず `processed_metadata_mismatch` を報告します。既存の `upscaler_used` が空でない場合、またはモード / アルファが一致しない場合は、`processed_provenance_mismatch` でオフライン再構築を拒否し、既存のファイルと行を保護します。別の解像度を指定して別個のオフライン出力を作成するか、元の処理済みファイルを復元してください。`--rebuild` を付けなければ有効なアップスケール済みファイルもスキップでき、ファイルが変更されないため出所 (provenance) は保持されます。

プロジェクトの画像データセット外や元画像ストレージ内のパスを上書きすることはありません。新しい解像度では処理済みファイルを作成し、既存の DB 登録サービスを通じて元画像 ID と関連付けます。DB 登録が失敗した場合は未リンクの出力パスを報告し、生成済みファイルを黙って削除しません。

各 JSONL の `item` には `image_id`、`status` (`success`、`skipped`、`failed`)、`resolution`、`output_path`、`processed_image_id`、`reason` が含まれます。末尾の `result` には total / processed / skipped / failed の件数とそれぞれの ID セットが含まれます。有効なスキップのみの場合は `ok:true`、status `success`、exit 0 を維持します。1 件でも失敗がある場合は `ok:false` となり、他に利用可能な選択 ID があれば status `partial_success` (exit 3)、そうでなければ `failed` (exit 1) を返します。入力検証エラーは処理前に exit 2 で終了します。

アノテーションおよび Batch の元画像保護ガードは引き続き有効です。生成した処理済みパスを選択するには `--resolution` を指定してください。この生成処理がガードを回避するために元画像の DB パスを書き換えることはありません。

実装は `ImageProcessingManager`、`FileSystemManager`、`ImageDatabaseManager` を再利用しています。CLI 固有の処理は厳密 ID 選択、オフラインポリシー、検証済み再利用、および ID ごとのレポート出力です。既存の GUI 処理に変更はありません。
