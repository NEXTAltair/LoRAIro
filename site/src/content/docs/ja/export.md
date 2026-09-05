---
type: Guide
title: データセットを出力
description: ステージングまたは画像IDから学習用ファイルを作成します。
sidebar:
  order: 7
---

## GUIで出力する

1. ステージングの画像と枚数を確認します。
2. 「エクスポート」で解像度と形式を選びます。
3. 出力用タグ調整を確認し、「検証」を実行します。
4. 問題がなければ「エクスポート」を実行し、生成された画像とテキストを確認します。

解像度候補は512・768・1024・1536です。形式には「TXT（タグ分離）」「TXT（キャプション統合）」「JSON」があります。利用する学習ツールが期待する形式を選んでください。

出力用の一時除外とDBのrejectは別です。詳しくは[タグ修正](../editing/)を参照してください。

## CLIは画像IDを指定する

現行の`export create`は検索フィルターを受け取りません。先に検索して対象IDを確認します。古い`--tags cat`の例は使えません。

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids-file ids.txt -o ./dataset
```

この2行は代替の指定方法です。`--image-ids`と`--image-ids-file`は同時指定できません。直接指定は最大500件です。大量出力には、改行またはカンマ区切りのIDを記入した`ids.txt`を使います。CLIはTXTとJSONの両方を生成します。

出力先は空の専用ディレクトリを使い、既存データセットと意図せず混在させないでください。実行後にファイル数・画像・タグ内容を確認してから学習へ渡します。

## タグの言語別データセット

多言語タグ出力はCLIで明示します。

```powershell
uv run --no-sync lorairo-cli export create -p "my-project" --image-ids 42,57 -o ./dataset --tag-language canonical --tag-language ja
```

複数言語の場合は`canonical/`、`ja/`などに、画像も含む完全なデータセットをそれぞれ作成します。その分の空き容量が必要です。1言語の場合は出力rootを使います。

登録済みの主訳がないタグはcanonical表記に戻ります。これはキャプションの自動翻訳ではありません。ガイドの4言語対応とは別機能で、すべてのタグに4言語の訳が揃うことを保証しません。GUIからの多言語タグ出力手順は現時点では提供していません。
