# Windows / Linux 環境の分離

Windows がホストチェックアウトを所有します。コンテナは同じチェックアウトを `/workspaces/LoRAIro` に **読み書き可能 (rw)** でバインドマウントして作業します。実装作業は各 OS で個別に作成する `.agents/worktree/` 配下の worktree から開始します。片方の OS で登録した worktree は他方の OS から解決できない絶対パスを持つため、もう一方の OS の `git worktree list` では `prunable` と表示されます。ホームディレクトリの状態は名前付きボリュームで OS ごとに分離しています。

| 状態 | Windows | コンテナ |
| --- | --- | --- |
| Git / ソース / プロジェクトのフック・ルール・エージェント・スキル | ホストチェックアウト | 同じホストチェックアウト (`/workspaces/LoRAIro` へ rw バインドマウント) |
| worktree | Windows から作成したホスト側 `.agents/worktree/` | コンテナから作成した同じ `.agents/worktree/` |
| OS ごとの共有 Python | ホスト `.venv/Scripts/python.exe` | `/workspaces/LoRAIro/.venv` の既存 `lorairo-venv` ボリューム (`bin/python`) |
| Codex ユーザー設定 / 認証 / 履歴 | Windows ユーザー `.codex` | `/home/vscode/.codex` の `lorairo-codex-config` |
| Claude ユーザー設定 / 認証 / 履歴 | Windows ユーザー `.claude` | `/home/vscode/.claude` の既存 `lorairo-claude-config` |
| LoRAIro ユーザー設定 / ログ | `LocalAppData/LoRAIro` | Linux XDG config / state ボリューム |
| Annotator ユーザー設定 / ランタイムキャッシュ / インストールマーカー / ログ | `LocalAppData/image-annotator-lib` | Linux XDG config / cache / state ボリューム |
| `node_modules` / ビルド・テスト・型キャッシュ / カバレッジ | ホストチェックアウト | 同じホストチェックアウト (非分離) |

`lorairo-venv` ボリュームはホストの `.venv` パス上にマウントされます。そのため、コンテナが Windows 環境へ書き込むことはなく、Windows から Linux 環境が見えることもありません。Windows 環境および既存の名前付きボリュームはすべて保持されます。プロジェクトの `.claude` / `.codex` ディレクトリはホームボリュームで覆われないため、共通設定は両 OS から読み取れます。

PR #1395 で一時的に、読み取り専用のホストマウントと `/workspaces/LoRAIro-linux` (ボリューム `lorairo-linux-checkout`) の独立した Linux チェックアウトをデフォルトとしました。これはドキュメント上の誤りであり撤回済みです。現在のデフォルトプロファイルでは、このチェックアウトをマウントも初期化もしません。

## Shared-worktree プロファイル (オプトイン)

上記のデフォルトプロファイルは、すでに shared-worktree 構成になっています。オプトインの追加機能 (Herdr と SSH ファイルのボリューム永続化、sshd Feature のデフォルトポートマッピング、ボリューム名プレフィックス) については、[shared-worktree/README.md](shared-worktree/README.md) を参照してください。このプロファイルは明示的な `--config` 指定時のみ選択されます。

## 初回マイグレーションとリビルド

まずエージェントの作業を完了させてください。プロセスと未コミット変更のある worktree を確認し、進行中の作業を保護します。別 OS のパスが見つからないように見えても、worktree を prune や repair しないでください。既存の混在した worktree 登録はホストに残したままにし、作業の保存を確認したうえで、必ず作成元の OS から片付けてください。

古いコンテナを置き換える前に、**Linux** 側の Codex ホームをバックアップして移行します。移行先には未作成かつ Git 無視対象のバックアップディレクトリを指定してください。ヘルパーはバイトを書き込む前に、末尾ディレクトリを POSIX モード `0700` で、各アーカイブ・コピーした Git 設定・マニフェストをモード `0600` で作成します。Windows では現在のユーザーのみにアクセスを許可する保護された DACL をアトミックに作成し、書き込み前に ACL を検証したうえで、これを強制できないストレージを拒否します。既存のバックアップディレクトリやファイルは保持したまま処理を拒否するため、部分移行後は新しい保存先を選んでください。ヘルパーはすべての状態をコピーする間 SQLite の書き込みを凍結し、不透明なアーカイブを保持します。空でない移行先ボリュームへの上書きは拒否し、認証情報のバイト列は出力せずに検証します。Windows の Codex 認証情報には一切アクセスしません。

~~~powershell
python scripts/migrate_container_codex.py --container <old-container-id> --backup-dir <private-new-directory>
~~~

以前 Git 無視対象だったプロジェクトの Codex 設定に有効な sandbox / inherit 設定が含まれていた場合は、そのファイルを置き換える前に `--project-config <original-project-config.toml>` を追加してください。Linux ユーザー設定に引き継がれるのは、これらポータブルな設定のみです。プロジェクト環境パスや Windows ユーザーホームの状態は一切インポートされません。存在しない任意の XDG ディレクトリや従来の `.gitconfig` は空の状態として扱われます。

コンテナを削除する前に、Linux 専用のアプリ / XDG 状態もバックアップしてください。Windows の絶対パスから Linux ユーザー設定を初期化してはいけません。ホスト既存の `config/lorairo.toml` は、両方のファイルを保存したあとでのみ Windows ユーザー設定へ移してください。共有ファイルは読み取り専用のデフォルト値であり、ポータブルなパスのみを含めるべきです。従来の annotator 上書き設定は、対応する OS のユーザーディレクトリへ明示的に移行する必要があり、別 OS へ自動採用されることはありません。

ホストの main チェックアウトを更新する前に、既存の Git 無視対象 `.codex/config.toml` をチェックアウト外へ退避してください。`git pull --ff-only` は警告なしにその無視ファイルを追跡対象のポータブルポリシーで置き換えます。pull 後、`python scripts/configure_agent_environment.py --legacy-codex-config <saved-config.toml>` を実行すると、OS ユーザーの Codex 設定に sandbox / inherit 設定を引き継げます。

PR がマージされファイルの退避が完了したら、`git pull --ff-only` でホストの main チェックアウトを更新します。その後、**Dev Containers: Rebuild Container** またはインストール済みの Dev Containers CLI を実行してください。

~~~powershell
node <devContainersSpecCLI.js> up --workspace-folder H:/LoRAIro --remove-existing-container
~~~

ボリュームの削除は不要です。postCreate が共有ホストチェックアウト内で `make setup` を実行します。撤回された #1395 プロファイルで作成された `lorairo-linux-checkout` ボリュームはマウントされず、そのまま残ります。手動で削除する前に、未公開の作業が残っていないか確認してください。起動ログは Linux 専用で `/home/vscode/.local/state/LoRAIro/postCreate.log` に出力されます。

## セットアップと優先順位

`make setup` は、submodule の初期化、依存同期、OS ユーザーエージェント設定、追跡済み Git フックのインストール、スキル復元、ハーネス復元を意図的に直列実行します。Make がない Windows 環境では、これらのスクリプトを同じ順序で実行してください。通常の `scripts/dev_tasks.py` コマンドは依存同期を行いません。

`scripts/configure_agent_environment.py` は、`UV_PROJECT_ENVIRONMENT` を **現在の OS ユーザー** の Codex / Claude 設定へマージします。プロジェクト設定はユーザー設定を上書きするため、プロジェクトの Codex 設定および Claude のローカル / プロジェクト設定からはこのキーを削除します。`CODEX_HOME` の変更だけでは不十分です。その他の設定は保持され、移行前に非公開バックアップを作成します。バックアップは検証済みの非公開ディレクトリ内に排他的な新規ファイルとして保存されます。既存の権限が広いバックアップディレクトリはそのまま残し、新しいバックアップはその隣に作成した非公開ディレクトリを使用します。設定ファイルは移行先ファイルシステム上の非公開ステージングディレクトリから置き換えられ、POSIX `0600` または現在ユーザーのみを許可する保護された Windows DACL を維持します。ステージングファイルは失敗時に削除され、中断後も Git の無視対象となります。

共有のガイダンスとランタイムは `scripts/install_agent_harness.py` または `make harness-install` で復元します。このランタイム専用ラッパーは OS ユーザー設定を保持します。上流のフルインストーラーを直接実行すると絶対パスを含むプロジェクト設定が再生成される可能性があるため、実行後に `configure_agent_environment.py` を走らせ、エージェント利用前に共有プロジェクト設定へ OS 固有の絶対パスが含まれていないことを確認してください。

デフォルトの実行環境は、リンクされた worktree から設定する場合も含め、この OS チェックアウトの Git 共通ルートにある `.venv` です。Windows は `Scripts/python.exe`、Linux は `bin/python` を解決します。worktree 専用環境やネストされたパッケージ環境は絶対に作成しないでください。ホスト上に残っている Linux の `local_packages/*/.venv` は保持されますが、使用されません。

スキルは OS 固有のシンボリックリンクやジャンクションではなく、通常のディレクトリとして展開されます。再インストール時はプロジェクションマニフェストを確認し、ユーザーの編集を保持します。追跡済みの `.githooks/pre-commit` が現在 OS の共有インタープリタを選択します。`core.hooksPath=.githooks` により、生成された Linux フックが Windows フックを上書きする事故を防ぎます。`pre-commit install` は不要です。代わりにプロジェクトのセットアップを再実行してください。

LoRAIro 設定の優先順位は「コードデフォルト < ポータブルプロジェクトデフォルト < OS ユーザー設定」です。分離テスト向けの明示的な設定パス指定も引き続きサポートします。Annotator のシステムカタログやモデル重みはプロジェクトアセットとして残し、ユーザー上書き設定・ランタイムメタデータ・インストールマーカーは OS ローカルに保持します。キャッシュやネイティブ実行ファイルを OS 間でコピーしないでください。

## リビルド後の検証

~~~bash
cd /workspaces/LoRAIro
python scripts/dev_tasks.py lint --dry-run
python -X utf8 scripts/validate_harness.py
git config --local --get core.hooksPath
uv run --no-sync python -c 'import sys; print(sys.executable)'
codex login status
~~~

セットアップを再度実行し、Windows の `.venv`、Windows ユーザー設定、Windows で作成した worktree 登録が変化していないことを確認してください。検証にはテストデータのみを使用します。対話的な Qt は Windows で実行し、コンテナ内の Qt テストは offscreen を使います。実際の SQLite データベースに対する Windows GUI とコンテナ CLI からの同時アクセスは引き続き非サポートです。

チェックアウト内の生成ファイル (キャッシュ、カバレッジ、`node_modules`) は両 OS で共有されます。分離されるのはホームディレクトリの状態と venv のみです。

コンテナイメージは Node / Codex / Claude を `vscode` ユーザーとしてインストールします。これらの実行ファイルはイメージの状態であり、ユーザーデータはボリュームの状態です。キャッシュされたイメージレイヤーに古い CLI が残る場合があるため、CLI を更新したいときだけキャッシュなしでリビルドしてください。

参考資料: [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/), [VS Code source mount configuration](https://code.visualstudio.com/remote/advancedcontainers/change-default-source-mount)
