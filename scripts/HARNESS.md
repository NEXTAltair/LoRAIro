# エージェントハーネスの復元と運用

## 初回導入およびブランチ切替時の復元手順

初回導入時や、未キャッシュのランタイムを含むブランチへ切り替えたときは、Claude や Codex を一度停止する。その後、通常のターミナルで以下のコマンドを実行する。

ランタイムが未復元の状態では、エージェント内部からの復元ツール呼び出しも拒否される。復元が完了してからエージェントを再開する。

```text
python -X utf8 scripts/install_agent_harness.py
python -X utf8 -m unittest discover -s scripts/tests -v
python -X utf8 scripts/validate_harness.py
```

`make setup` でもハーネスは復元される。既存環境を修復したい場合は、上記の Python コマンドまたは `make harness-install` を使う。

## 責務分離の原則

共通フック本体とデフォルトルールは `NEXTAltair/altairs-agent-dev-kit` が管理する。LoRAIro 側には接続設定、プロジェクト固有のルール、チームメート監視だけを配置する。共通コードを LoRAIro 側へ再移植してはならない。

## 復元と更新の仕組み

復元スクリプトは `agent-harness.lock.json` に記録されたコミットから kit を取得し、kit のランタイム専用導入処理を呼び出す。

- **復元先**: git 管理外の共通 Python フック、`*.default.json`、および共通の `.claude/agents`、`.claude/rules`、`.codex/agents`。
- **ダイジェスト管理**: 生成元のダイジェストを `.agent-kit/guidance-state.json` に記録する。
- **pin 更新時の削除ルール**: 削除または改名されたファイルは、現在のダイジェストが前回生成時と一致する場合のみ自動削除する。
- **手編集ファイルの保護**: 手動で編集したファイル、管理外のファイル、リンクはそのまま保持する。保持した旧ファイルは生成管理から外し、次回以降も自動削除しない。
- **保護対象**: git 追跡中のイベント設定、固有ルール、`.codex/config.toml` は変更しない。

## OS 別の共有 `.venv` と環境設定

Windows と Dev Container はそれぞれ別の共有 `.venv` を使用する。

- `python scripts/configure_agent_environment.py` を実行すると、現在 OS の Git 共通ルートにある `.venv` を検証し、Codex および Claude の**ユーザー設定**に共有環境を登録する。
- プロジェクト側の `.codex/config.toml`、`.claude/settings.json`、`settings.local.json` には OS 固有の絶対パスを書かない。プロジェクト設定はユーザー設定より優先度が高いため、ホームボリュームの追加だけでは競合を解決できない。
- コンテナはホストチェックアウトを `/workspaces/LoRAIro` に読み書き可能(rw)でマウントし、既存の venv ボリューム `lorairo-venv` を `/workspaces/LoRAIro/.venv` にマウントする。詳細は [環境分離](../.devcontainer/README.md) を参照すること。
- フックを起動するには、両環境の PATH 上に `python` と Git が必要である(汎用 Linux 向け kit の既定は `python3`)。

## エージェント別の動作と worktree 運用

- **実行方式**: Claude は `exec` 形式、Codex は Git ルート解決と Windows 用コマンドを使用する。GNU timeout は不要である。
- **worktree の作成と参照**: Codex では Git コマンドで `.agents/worktree/` 配下に新規 worktree を作成する。新規 worktree に共通ランタイムがない場合は、共有チェックアウトへフォールバックする。一方、固有ルールは作業中の worktree から読み込み、共有チェックアウトのルールへすり替えない。
- **Codex の `workspace-write` 権限**: `workspace-write` モードでは `.agents/` と共有 `.git/` が保護されるため、編集や Git 操作にはセッション権限に応じた承認が必要になる。作業ファイルを編集できるようにするには、使用中 OS のユーザー設定で `[sandbox_workspace_write]` の `writable_roots` に共有チェックアウト配下の `.agents/worktree/` の絶対パスを追加する(既存のパス指定は維持する)。共有 `.git/` への書き込みやネットワーク操作には、セッションの承認設定がそのまま適用される。
- **`.ui` ファイルの生成**: 既存画面のために維持しており、対象 worktree のソースと共有 Python を使って同期なしで実行する。

## 移行時の注意と検証

- ユーザー設定や `.claude/settings.local.json` に旧フックが残っていると、フックが重複実行される。移行時は各エージェントの `/hooks` で定義元を確認すること。
- 設定変更後はエージェントを再起動し、Codex が要求するフックの信頼確認を実施する。信頼確認を回避してはならない。
- ハーネス検証は追跡対象の設定とローカル設定の両方を検査する。スキルの配置検査は従来どおり別に行う。
- 復元と起動のテストは、Windows と Linux の両環境で CI 実行する。
