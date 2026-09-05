---
type: Guide
title: プロジェクトと画像登録
description: プロジェクトの保存内容と、安全に画像を登録する方法。
sidebar:
  order: 3
---

## 保存されるもの

画像情報、アノテーション、編集内容はプロジェクト単位で管理します。通常の保存先は`lorairo_data/<project>_YYYYMMDD_NNN/`で、SQLiteデータベースと`image_dataset/`などが含まれます。設定を変更した環境では保存先も異なります。

元の画像フォルダーと、LoRAIroのプロジェクト保存先を区別してください。バックアップには画像DBだけでなくプロジェクト全体が必要です。

## GUIで画像を登録する

1. 「検索」タブを開きます。
2. 「データセット」の「選択」から画像フォルダーを選びます。
3. 登録処理の終了を待ち、検索結果と件数を確認します。

この「選択」は登録元フォルダーを選ぶ操作です。既存プロジェクトを開くボタンではありません。意図しないフォルダー全体を指定しないよう、最初は小さな検証用フォルダーで試してください。

## CLIで対象プロジェクトを明示する

```powershell
uv run --no-sync lorairo-cli project create "my-project"
uv run --no-sync lorairo-cli project list
uv run --no-sync lorairo-cli images register ./images --project "my-project"
uv run --no-sync lorairo-cli images list --project "my-project" --fetch
```

`my-project`は自分のプロジェクト名に置き換えます。画像IDは登録後の一覧で確認し、ガイドの例にあるIDをそのまま使わないでください。

CLIの登録は、既定で同一pHashの画像をスキップします。重複を含める`--include-duplicates`は、重複登録が必要な場合だけ使用します。

## 登録後

画像を登録しただけではアノテーションや出力は実行されません。[検索とステージング](../search/)で対象を選んでから次へ進みます。登録や編集などの書き込みをGUIとCLIで同時に行わないでください。
