---
type: Guide
title: Windowsでインストール
description: ソースからWindows用環境を作り、GUIとCLIを起動します。
sidebar:
  order: 2
---

## 必要なもの

- Git、uv、Python 3.13。Pythonはuvで導入できます。
- モデルと画像を保存できる空き容量。
- 標準のGPU推論環境を使う場合は、対応するNVIDIA GPUとドライバー。

この手順はソースからの導入です。標準PyTorchの取得先はCUDA 13.2用です。ドライバーやGPUの対応状況は環境ごとに確認してください。CPU版や別CUDA版への変更は、単なる起動オプションではなく依存設定・lockfileの変更を伴います。

## 初回セットアップ

PowerShellで実行します。パスに空白がある場合は引用符で囲みます。

```powershell
git clone https://github.com/NEXTAltair/LoRAIro.git
cd LoRAIro
git submodule update --init --recursive
uv python install 3.13
uv sync --python 3.13
uv run --no-sync lorairo
```

依存のインストールにはネットワーク通信と時間が必要です。アプリを起動したまま`uv sync`で環境を更新しないでください。

## 次回以降の起動

リポジトリのディレクトリから実行します。

```powershell
uv run --no-sync lorairo
uv run --no-sync lorairo-cli --help
```

`--no-sync`は起動時の依存更新を防ぎます。依存変更後はアプリやテストを停止してから、明示的に`uv sync`を実行します。

## 復旧コピーから再開する場合

既存の画像・DB・設定を消して再インストールする必要はありません。まず[バックアップと復旧](../troubleshooting/)を確認します。別OSからコピーした`.venv`はそのまま使用できません。Windows用とコンテナ内Linux用のPython環境を分けてください。

`UV_PROJECT_ENVIRONMENT`に旧コンテナの`/workspaces/...`が残っている場合は、Windows用の実際の共有環境に設定を直します。エラーを避けるためだけに旧パスを作成しないでください。

## 開発も行う場合

テスト・整形ツールを含める手順とDev Containerの使い分けは[開発環境](../development/)にまとめています。
