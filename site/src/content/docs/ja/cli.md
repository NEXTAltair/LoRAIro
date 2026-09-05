---
type: Guide
title: CLIの使い方
description: PowerShellでも使えるコマンド確認とJSONL出力の扱い。
sidebar:
  order: 9
---

## コマンドを確認する

リポジトリのディレクトリから、作成済みの環境を使って実行します。

```powershell
uv run --no-sync lorairo-cli --help
uv run --no-sync lorairo-cli images --help
uv run --no-sync lorairo-cli export create --help
uv run --no-sync lorairo-cli --json list-commands
uv run --no-sync lorairo-cli --json describe "images update"
```

`list-commands`と`describe`は、エージェントが利用可能な操作や引数を確認するための入口です。古い手順の引数が認識されない場合は、現行の`--help`と照合してください。

## JSONLモード

`--json`をコマンドの前に指定すると、標準出力が1行1JSONオブジェクトになります。ログや進捗は標準エラーへ出ます。終端の`result`または`error`を確認してください。終了コードは成功0、入力・検証エラー2、その他のエラー1です。

環境変数`LORAIRO_CLI_JSON=1`も利用できますが、対話用途では明示フラグの方が意図を確認しやすくなります。

JSONLは画像IDだけの一覧ではありません。検索結果からIDを抽出する場合は`kind`などの構造を確認し、メッセージ行を混ぜないようにします。

## 目的別の手順

- [プロジェクト作成・画像登録](../projects/)
- [JSONファイルによる検索](../search/)
- [モデル一覧・同期アノテーション](../annotation/)
- [dry-run後のタグ編集](../editing/)
- [画像IDによる出力](../export/)

CLIはGUIと同じプロジェクトデータを扱います。大量更新前はバックアップし、GUIと同時書き込みしないでください。詳細な開発者向け契約は[CLIリファレンス](https://github.com/NEXTAltair/LoRAIro/blob/main/docs/cli.md)にあります。
