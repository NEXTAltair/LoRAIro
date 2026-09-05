---
type: Guide
title: 開発環境とヘッドレステスト
description: Windows実行・コンテナ開発と共有Python環境の使い分け。
sidebar:
  order: 10
---

## Windowsとコンテナの役割

コード編集はDev Container、GUI実行はWindowsで行います。コンテナはGUIを表示せず、テストはQt offscreenで実行します。WindowsとLinuxで`.venv`の実体を共有するのではなく、各OS内でmainとworktreeがそのOS用環境を共有します。

## 開発依存の導入

mainの共有チェックアウトで実行します。Python、Git、uvが必要です。

```powershell
git submodule update --init --recursive
python scripts/dev_tasks.py install-dev
```

Linuxで`python`がなければ`python3`を使います。この操作は共有環境を更新するため、他のアプリ・テスト・エージェントが使っていない時に行います。Kitの導入・設定は別の管理対象です。

## 通常の開発コマンド

```powershell
python scripts/dev_tasks.py test
python scripts/dev_tasks.py test-all
python scripts/dev_tasks.py lint
python scripts/dev_tasks.py format
python scripts/dev_tasks.py test-all --dry-run
```

`test`はLoRAIro本体、`test-all`は3パッケージをそれぞれ独立したテスト処理で順に実行します。BDDも引き続きpytest-bddで扱います。`lint`は読み取り専用、`format`はRuffによる自動整形・修正です。通常タスクは依存を自動同期しません。

GPU実モデルの`test-runtime-local`と、実際に課金され得るAPIの`test-runtime-webapi`は明示実行用です。通常の`test-all`に混ぜません。

## worktree

作業用worktreeには専用`.venv`を作りません。共通コマンドはGitからmain側の環境を特定し、対象worktreeのソースを使います。`UV_PROJECT_ENVIRONMENT`が設定されている場合は、その環境のmain共有`.venv`の絶対パスと一致させます。

VS Codeでworktreeを直接開く場合は「Python: Select Interpreter」でmain側の共有インタープリターを選びます。Windows GUIの起動にはoffscreenを付けません。

詳しいコマンドの契約は[開発タスク説明](https://github.com/NEXTAltair/LoRAIro/blob/main/scripts/DEV_TASKS.md)にあります。
