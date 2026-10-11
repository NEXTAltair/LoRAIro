# Agent harness restoration

初回導入や未キャッシュruntimeへのbranch切替時は、Claude/Codexを停止し、通常のターミナルで以下を実行する。
runtime未復元時はagent内の復元ツール呼び出しも拒否される。復元後にagentを再開する。

共通フック本体とデフォルトルールは `NEXTAltair/altairs-agent-dev-kit` が管理する。
LoRAIroには接続設定、固有のルール、teammate監視だけを置く。共通コードをここへ再移植しない。

```text
python -X utf8 scripts/install_agent_harness.py
python -X utf8 -m unittest discover -s scripts/tests -v
python -X utf8 scripts/validate_harness.py
```

`agent-harness.lock.json` のcommitからkitを取得し、kitのruntime-only導入処理を呼ぶ。
復元先はgitignoredの共通Pythonフックと `*.default.json`。
共通の `.claude/agents`、`.claude/rules`、`.codex/agents` も復元し、生成元のdigestを
`.agent-kit/guidance-state.json` に記録する。pin更新で削除・改名されたファイルは、
現在のdigestが前回生成時と一致する場合だけ削除する。手編集や管理外のファイル、リンクは保持する。
保持した旧ファイルは生成管理から外し、次回以降も自動削除しない。
追跡中のイベント設定、固有ルール、`.codex/config.toml` は変更しない。
`make setup` でも復元する。既存環境の修復にはPythonコマンドか `make harness-install` を使う。

Windowsとコンテナは別の共有 `.venv` を使う。
`python scripts/configure_agent_environment.py` は現在 OS の Git common root `.venv` を検証し、
Codex **ユーザー設定** と Claude **ユーザー設定** に共有環境を指定する。
プロジェクト `.codex/config.toml`、`.claude/settings.json`、`settings.local.json` には
OS 固有の絶対パスを置かない。プロジェクト設定の優先度が高いため、home volume 追加のみでは
解決しない。Linux の独立 checkout は `/workspaces/LoRAIro-linux`、既存 venv volume は
その `.venv` にマウントする。詳細は [環境分離](../.devcontainer/README.md) を参照。
フック起動には両環境のPATH上に `python` とGitが必要（汎用Linux kitの既定は `python3`）。

Claudeはexec形式、CodexはGitルート解決とWindows用コマンドを使う。
新規worktreeに共通ランタイムがなければ共有checkoutへフォールバックする。
固有のルールは作業中のworktreeから読み、共有checkoutのルールにすり替えない。
GNU timeoutは不要。Codexの未対応WorktreeCreate登録は撤去し、worktree作成は既存のGit運用に従う。
`.ui` の生成は既存画面のため維持し、対象worktreeのソースと共有Pythonを使って同期なしで実行する。

ユーザー設定や `.claude/settings.local.json` に旧フックが残っていると重複実行される。
移行時は各エージェントの `/hooks` で定義元を確認する。変更後は再起動し、Codexが要求する
フックの信頼確認を行う。信頼のバイパスはしない。

ハーネス検証は追跡設定とローカル設定の両方を検査する。スキルの配置検査は従来どおり別に行う。
WindowsとLinuxで復元・起動テストをCI実行する。
