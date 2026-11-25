---
trigger: always_on
description: "uv を並列に走らせて共有 venv を壊さないための運用"
---

# 並列実行と共有 venv の運用ルール

複数のパッケージマネージャ操作(例:`uv`)を並列実行した際に発生する、共有仮想環境(venv)の破損事故を防ぐための運用ルールである。プロジェクトルートの venv を共有するすべての操作に適用する。

worktree 間およびパッケージ間における実行環境の分離粒度の判断は、本ファイルに集約する。他のルール文書([git-workflow.md](git-workflow.md)、[testing.md](testing.md) など)からは本ファイルを参照するだけにとどめる。

> **プロジェクト固有:** 実際のプロジェクトルート venv のパス、パッケージマネージャ、CI で使う環境変数名は導入先で追記する。以下は `uv`(Python)を例とした記法である。

## 核心ルール

**並列で `uv` を実行する場合は、同一 venv に対する同期系操作を競合させない。** worktree 内で通常のコマンドを実行する際は共有 venv の場所を明示する。また、`uv sync` や `uv lock` などの環境書き換え系コマンドは直列化し、`uv run --active` は使わない。

## フックで自動ブロックされる操作

kit の PreToolUse フック(`hook_pre_commands.py`)は、導入先で `worktree_uv_guard: true` を上書き有効化している場合、`.agents/worktree/` 配下で共有 venv の明示(`UV_PROJECT_ENVIRONMENT=<project root>/.venv`)を伴わない `uv` 実行をブロックする。デフォルトルールは `hooks/rules/pre_commands.default.json`、導入先の上書き設定は `<project_root>/.claude/hooks/rules/pre_commands.json` に配置する。

```bash
# 禁止例(worktree_uv_guard 有効時にフックがブロックする)
uv run --active pytest
uv run --active python script.py

# 正しい
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run pytest
```

`--active` が必要な特殊なケースでも、venv を直接有効化済みであれば `.venv/bin/<command>` を直接呼び出すことでフックのブロックを回避できる。

## 運用ルール

核心ルールの具体的な運用は次の 4 点である。このうち 1 と 2 はフック(`worktree_uv_guard`)によって機械的に防止される。

1. **並列タスクは worktree で分離し、共有 venv を明示して使う。** 同一 venv に対して並列実行してはならない(`uv run pytest tests/unit/ & uv run pytest tests/integration/ &` のような並列起動は禁止)。
2. **`--active` 相当のフラグは使わない。** 有効化中の venv とマニフェストの制約が食い違うと、venv の再作成が引き起こされる。
3. **`uv sync` や `uv lock` などの書き換え系操作は直列に実行する。** `uv sync && uv sync --dev` のように逐次実行し、`&` で並列化しない。
4. **言語ランタイムのバージョンは固定ファイル(`.python-version` など)で管理する。** 手動で仮想環境を有効化したシェルでも、`python --version` と `.venv/bin/python --version` の一致を確認する。固定バージョンの変更は影響範囲が広いため、PR レビューを必須とする。

## venv 分離粒度:worktree 間

- 原則として worktree 内に専用の venv を作らず、プロジェクトルートの共有 venv を使う。
- worktree 配下でコマンドを実行する場合は、共有実行環境のパスを明示する。
- **共有 venv パスの指定はツール側の環境設定に常設し、毎回コマンド先頭へ環境変数を付けない**のが標準運用である。
  - Claude Code 系ツール:設定ファイル(例:`.claude/settings.json`)の `env` に `UV_PROJECT_ENVIRONMENT` を設定しておけば、worktree から素の `uv run ...` で共有 venv を利用できる。
  - Codex 系ツール:設定ファイル(例:`.codex/config.toml`)のシェル環境変数設定に同様の値を設定する。
- 常設設定が効かないシェル(手動端末など)では、`UV_PROJECT_ENVIRONMENT=<project root>/.venv uv ...` を明示する。
- 読み取り専用の検証で対象チェックアウトを固定したい場合は、`--no-sync` 相当のオプションと `PYTHONPATH` の明示を併用する。
- `uv` 単体のヘルプ表示や確認コマンドは venv を作成しないため、例外として許可する。
- worktree 固有の venv が必要な特殊事情がある場合は、理由を明示してから実行する。

| ツール | 共有 venv の常設方法 | コマンド記法 |
|---|---|---|
| Claude Code 系 | 設定ファイルの `env` | `uv run ...`(環境変数の前置不要) |
| Codex 系 | 設定ファイルのシェル環境変数設定 | `uv run ...`(環境変数の前置不要) |

どちらのツールでも、常設設定が効かないシェルでは `UV_PROJECT_ENVIRONMENT=<project root>/.venv uv ...` を明示する。

## venv 分離粒度:パッケージ(submodule)間

それぞれ独自の `pyproject.toml` を持つ独立パッケージ(submodule やモノレポ内のサブパッケージなど)を扱う場合は、以下の方針に従う。

- 各パッケージのテストは、それぞれ独立した `pytest` セッションとして実行する(単一の実行へ混ぜない)。
- ただし、パッケージごとに専用 venv を作成すると、重い依存(機械学習ライブラリなど)の重複ダウンロードや、低速な I/O 環境(ネットワークマウントなど)上での venv 作成により実用速度が著しく低下する。
- 対策として、プロジェクトルートの共有 venv(開発依存グループにまとめておく)を `UV_PROJECT_ENVIRONMENT` で指し示し、パッケージルートから `--no-sync` 相当で実行する。これにより、パッケージ固有の venv 作成を避けられる。

**注意**:常設した `UV_PROJECT_ENVIRONMENT` などの環境変数は、すべてのシェルコマンドへ継承される。独立した venv を持つべきサブプロジェクト(モノレポ内の別パッケージなど)を実行するコマンドやレシピでは、共有 venv を誤用しないよう自前の環境変数を明示的に上書きすること。上書きを忘れると静かに共有 venv へ流れてしまい、依存解決が壊れる。

```bash
# 例: パッケージルートから共有 venv を使ってテストを実行する
cd <package root>
UV_PROJECT_ENVIRONMENT=<project root>/.venv uv run --no-sync pytest
```

> **プロジェクト固有:** 実際のパッケージ一覧、依存グループへの統合方針、I/O 制約のあるマウント構成(Dev Container のネットワークマウントなど)は導入先で追記する。

## Windows 固有の注意:長命プロセスによるロックと暗黙の同期

Windows は POSIX と異なり、使用中のファイルを削除できない。GUI アプリなどの長命プロセスが共有 venv のエントリーポイント実行ファイル(`Scripts\*.exe`)から起動している間、その実行ファイルはロックされ続ける。

この状態でパッケージマネージャの暗黙的な同期(例:`uv run` 起動時の同期)が走ると、editable インストールのエントリーポイント再生成がロック中ファイルの削除失敗で中断する。その結果、**先に削除された別のエントリーポイントが消えたまま venv が部分破損する**(症状:`Failed to spawn: <command> / program not found`)。

- **予防**:長命プロセスが共有 venv から稼働している間は、同じ venv を使う CLI 実行に `--no-sync` 相当を常用する(venv を一切書き換えないため安全である)。
- **復旧**:長命プロセスを終了させてから、`uv sync --dev` 相当で再同期する。

> **プロジェクト固有:** 対象となる長命プロセス(GUI アプリなど)の名前、`--no-sync` 運用を明記したスキルやドキュメントへのポインタは導入先で追記する。

## venv 破損時の復旧手順

### 破損の兆候

以下のエラーが出力された場合は、venv の破損を疑う。

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

復旧時は次の点に注意する。
- 重い依存パッケージの再ダウンロードが発生し、数分〜十数分かかる場合がある。
- worktree 内の venv が破損した場合は、当該 worktree 内で同様に実行する。
- 復旧作業中は、他のパッケージマネージャコマンドを同時に実行しない。

> **プロジェクト固有:** 復旧を 1 コマンド化する Makefile ターゲットなどがあれば、ここに追記する。

## 並列タスク実行前の判断フロー

並列タスクを投入する前に、以下の順で確認する。

1. このタスクは内部でパッケージマネージャを呼び出すか。呼び出さないなら問題ない。
2. 並列実行する別タスクも同じツールを呼び出すか。呼び出さないなら問題ない。
3. 同じ venv を共有しているか。worktree などで分離済みなら問題ない。
4. 上記 3 つすべてに該当する場合は、**直列に並べ替えるか、専用 worktree を切って分離する**。
