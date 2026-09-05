---
type: Guide
title: 設定・バックアップ・問題解決
description: 秘密情報とプロジェクトを守り、復旧時の問題を切り分けます。
sidebar:
  order: 8
---

## 設定

GUIの「設定」（Ctrl+,）で設定を確認できます。`config/lorairo.toml`には保存先やAPIキーなどが入ります。APIキー、設定ファイル全体、秘密の画像パスが見えるスクリーンショットを公開しないでください。

主な設定には、APIキー、プロジェクト・出力・Batch結果の保存先、追加プロンプト、モデルの接続経路、DB待機時間、ログレベルがあります。復旧時はコピー元PCの絶対パスが残っていないか確認します。

## バックアップ

1. GUI、CLI、Batch取り込みなど、DBへ書き込む処理を終了します。
2. 実際の保存先にあるプロジェクト全体を別の場所へコピーします。通常は`lorairo_data/`内です。
3. `image_database.db`だけでなく、`image_dataset/`、ユーザータグDB（`user_tags.sqlite`）なども保存します。
4. `config/lorairo.toml`と必要なBatch結果を、秘密情報として別途保管します。

稼働中のSQLite DBファイルだけをコピーする方法は避けます。復旧時はバックアップ原本を上書きせず、復旧用コピーを使って画像・タグ・設定を確認してください。

## 起動や依存エラー

WindowsとLinuxの`.venv`は別物です。別OSの環境をコピーして使わず、対象OSで依存を導入します。共有環境を再構築する前には、動作中のアプリ・テスト・エージェントの利用を止めます。

GUIが表示されない場合は、Windows側に`QT_QPA_PLATFORM=offscreen`が設定されていないか確認します。コンテナのテストではoffscreenが正常です。

## GPUを認識しない

```powershell
nvidia-smi
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.version.cuda)"
```

GPUを利用する予定なのにfalseの場合は、ドライバー、GPUの対応、PyTorch環境を確認します。アプリのデータを削除してもGPU構成の問題は解決しません。

## DB競合・外部通信

`CONFLICT`が出た場合は、他の書き込み処理を終えてから再試行します。GUIとCLIで同時に書き込まないでください。初回タグDB取得に失敗した場合はネットワークと、必要ならHugging Face認証設定を確認します。

WebAPIエラーは認証・利用上限・モデル対応・送信制限などを確認し、同じ操作を繰り返す前に原因を調べます。

## 問題を報告する

操作手順、OS、再現条件と、関連するログの短い範囲を添えます。主なログは`logs/lorairo.log`、`logs/image-annotator-lib.log`、`logs/lorairo-cli.log`です。APIキーや個人情報、公開したくない画像パスを伏せてください。
