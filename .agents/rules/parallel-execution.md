---
trigger: always_on
description: "uv を並列に走らせて共有 venv を壊さないための運用"
---

# Parallel Execution Rules

複数のパッケージマネージャ操作 (例: `uv`) を並列に走らせた際の共有仮想環境 (venv) 破損事故を再発させないための運用ルール。プロジェクトルートの venv を共有するすべての操作に適用する。venv / 実行環境の分離粒度 (worktree 間・package 間でどこまで環境を共有し、どこから分離するか) の判断はこのファイルに集約する。他のルール文書 ([git-workflow.md](git-workflow.md), [testing.md](testing.md) 等) からはこのファイルを参照するだけにとどめる。

> **プロジェクト固有:** 実際のプロジェクトルート venv のパス、パッケージマネージャ、CI で使う env 変数名は導入先で追記する。以下は `uv` (Python) を例にした記法。

## 核心ルール

**並列で `uv` を走らせる場合は同一 venv への同期系操作を競合させない。** worktree 内で実行する通常のコマンドは共有 venv の場所を明示して使う。`uv sync` / `uv lock` などの書き換え系は直列化し、`uv run --active` は使わない。

## Hook で自動ブロックされる操作

kit の PreToolUse hook (`hook_pre_commands.py`) は、導入先が `worktree_uv_guard: true` を override で有効化すると、`.agents/worktree/` 配下での `uv` 実行が共有 venv の明示 (`UV_PROJECT_ENVIRONMENT=<project root>/.venv`) を伴わない場合にブロックする。デフォルトルールは `hooks/rules/pre_commands.default.json`、導入先 override は `<project_root>/.claude/hooks/rules/pre_commands.json` に置く。

```bash
# 禁止例 (worktree_uv_guard 有効時に hook がブロック)
uv run --active pytest
uv run --active python script.py

# 正しい
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run pytest
```

`--active` が必要な特殊ケースでも、venv を直接 activate 済みなら `.venv/bin/<command>` を直接呼ぶことで hook ブロックを回避できる。

## 運用ルール

核心ルールの具体形は次の 3 つ。1 と 2 は hook (`worktree_uv_guard`) で機械的に止められる。

1. **並列タスクは worktree で分離し、共有 venv を明示して使う。** 同一 venv を並列で叩かない
   (`uv run pytest tests/unit/ & uv run pytest tests/integration/ &` のような並列起動は禁止)。
2. **`--active` 相当のフラグは使わない。** activate 中の venv とマニフェストの制約が食い違うと
   venv 再作成のトリガーになる。
3. **`uv sync` / `uv lock` 相当の書き換え系は直列に並べる。** `uv sync && uv sync --dev` のように
   逐次実行し、`&` で並列にしない。
4. **言語ランタイムのバージョンは固定ファイル (`.python-version` 等) で管理する。** 手動 activate する
   shell でも `python --version` と `.venv/bin/python --version` の一致を確認する。固定バージョンの
   変更は影響範囲が広いため PR レビュー必須。

## venv 分離粒度: worktree 間

- 原則としてワークツリー内に専用 venv を作らない (共有のプロジェクトルート venv を使う)
- worktree 配下で実行する場合は、共有実行環境のパスを明示する
- **共有 venv パスの指定はツール側の環境設定で常設し、コマンドには毎回 env prefix を付けない**のが標準運用
  - Claude Code 系ツール: 設定ファイル (例: `.claude/settings.json`) の `env` に `UV_PROJECT_ENVIRONMENT` を設定しておけば、worktree からでも素の `uv run ...` で共有 venv を使える
  - Codex 系ツール: 設定ファイル (例: `.codex/config.toml`) の shell 環境変数設定に同様の値を設定する
- その環境設定が効かない shell (手動端末など) では `UV_PROJECT_ENVIRONMENT=<project root>/.venv uv ...` を明示する
- read-only 検証で対象 checkout を固定したい場合は、`--no-sync` 相当のオプションと `PYTHONPATH` 明示を併用する
- `uv` 単体の help/inspection は venv を作らないため例外として許可する
- worktree 固有の venv が必要な特殊事情がある場合は、理由を明示してから実行する

| | 共有 venv 常設方法 | コマンド記法 |
|---|---|---|
| Claude Code 系 | 設定ファイルの `env` | `uv run ...` (env prefix 不要) |
| Codex 系 | 設定ファイルの shell 環境変数設定 | `uv run ...` (env prefix 不要) |

どちらも常設設定が効かない shell では `UV_PROJECT_ENVIRONMENT=<project root>/.venv uv ...` を明示する。

## venv 分離粒度: package (サブモジュール) 間

複数の独立した package (submodule / monorepo の sub-package 等、それぞれ独自の `pyproject.toml` を持つもの) を扱う場合:

- 各 package のテストはそれぞれ独立した pytest セッションとして実行するのが基本 (単一 invocation に混ぜない)
- ただし package ごとに専用 venv を作ると、重い依存 (機械学習ライブラリ等) の重複ダウンロードや低速な I/O 環境 (ネットワークマウント等) 上での venv 作成で実用速度を損なうことがある
- 対策: プロジェクトルートの共有 venv (dev dependency group にまとめておく) を `UV_PROJECT_ENVIRONMENT` で指し示し、package root から `--no-sync` 相当で実行することで、package 固有の venv 作成を避けられる

**注意**: 常設した `UV_PROJECT_ENVIRONMENT` などの環境変数は全シェルコマンドに継承される。独立した venv を持つべきサブプロジェクト (モノレポ内の別 package 等) を実行するコマンド / recipe は、共有 venv を誤って使わないよう自前の環境変数を明示的に上書きする。さもないと静かに共有 venv へ流れて依存解決が壊れる。

```bash
# 例: package root から共有 venv を使ってテストする
cd <package root>
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run --no-sync pytest
```

> **プロジェクト固有:** 実際の package 一覧、依存グループへの統合方針、I/O 制約のあるマウント構成 (devcontainer のネットワークマウント等) は導入先で追記する。

## Windows: 長命プロセスの entry point ロックと暗黙 sync

Windows は POSIX と異なり使用中ファイルを削除できない。GUI アプリ等の長命プロセスが共有 venv の
entry point 実行ファイル (`Scripts\*.exe`) から起動していると、その exe をロックし続ける。
この状態でパッケージマネージャの暗黙 sync (例: `uv run` の起動時 sync) が走ると、editable install の
entry point 再生成がロック中 exe の削除失敗で中断し、**先に削除された別の entry point が消えたまま
venv が部分破損**する (症状: `Failed to spawn: <command> / program not found`)。

- **予防**: 長命プロセスが共有 venv から稼働している間は、同じ venv を使う CLI 実行に
  `--no-sync` 相当を常用する (venv を一切書き換えないため安全)
- **復旧**: 長命プロセスを終了してから `uv sync --dev` 相当で再同期する

> **プロジェクト固有:** 対象となる長命プロセス (GUI アプリ等) の名前、`--no-sync` 運用を明記した
> skill / ドキュメントへのポインタは導入先で追記する。

## 復旧手順

### 兆候

以下のエラーが出たら venv 破損を疑う:

```
failed to remove directory '.venv/lib': Directory not empty
failed to rename file from .../*.tmp* to ...: No such file or directory (os error 2)
Removed virtual environment at: <project root>/.venv
Creating virtual environment at: <project root>/.venv
```

### 復旧コマンド

```bash
rm -rf .venv
uv sync --dev
```

注意点:
- 重い依存の再ダウンロードが発生する場合がある (数分~十数分)
- worktree 内の venv が壊れた場合は当該 worktree 内で同様に実行
- 復旧中は他のパッケージマネージャコマンドを走らせない

> **プロジェクト固有:** 復旧を1コマンド化する Makefile ターゲット等があれば、ここに追記する。

## 判断フロー

並列タスクをディスパッチする前のチェックリスト:

1. このタスクはパッケージマネージャを内部で呼び出すか? → No なら気にしなくて良い
2. 並列で走らせる別タスクも同じツールを呼ぶか? → No なら気にしなくて良い
3. 同じ venv を共有しているか? → No (worktree 分離済み) なら OK
4. 上記 3 すべて Yes → **直列に並べ替える、または worktree を切る**
