---
type: Guide
title: タグ修正とキャプション確認
description: DBへの編集と、出力時だけの調整を区別します。
sidebar:
  order: 6
---

## まず生成結果を確認する

画像を選び、詳細パネルでタグ、キャプション、評価を確認します。AIの結果が正しいとは限りません。学習に不要なタグや画像と矛盾する表現がないかを見ます。

現行のキャプション表示は読み取り専用です。自由入力のキャプション編集欄がある前提で操作しないでください。タグをキャプションへ移す機能はタグ側のメニューから利用できます。

## 恒久変更と出力用変更

- タグ追加・置換・rejectはDB上の内容に影響します。
- 出力overlayの「出力除外」は、出力のための一時調整です。
- 「reject(DB)」は一時除外ではありません。対象範囲の説明を確認し、取り消し可能だと考えずに実行してください。

AIタグにはモデルから個別confidenceが返らない場合があります。confidence値に基づく自動的なノイズ除去が常に使えるわけではありません。

## CLIで変更内容を確認してから適用する

タグ変更は既定でdry-runです。最初に`--apply`なしで対象を確認します。

```powershell
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor"
uv run --no-sync lorairo-cli tags add -p "my-project" --image-ids 42,57 --tags "cat,outdoor" --apply
uv run --no-sync lorairo-cli tags remove -p "my-project" --image-ids 42 --tags "bad_tag" --apply
uv run --no-sync lorairo-cli tags replace -p "my-project" --image-ids 42 --from "bad tag" --to "good_tag" --apply
```

削除はsoft-rejectとして扱われますが、一般的な「元に戻す」操作を保証するものではありません。大量変更前はバックアップしてください。CLIで変更した後はGUIを再検索・再読込して最新状態を確認します。
