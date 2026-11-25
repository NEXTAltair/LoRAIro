# Shared-worktree プロファイル (オプトイン)

デフォルトプロファイル (`../devcontainer.json`) は、すでに shared-worktree 構成を採用しています。ホストチェックアウトを `/workspaces/LoRAIro` に **rw** でバインドマウントし、OS ごとの worktree を `.agents/worktree/` 配下に配置したうえで、既存の `lorairo-venv` ボリュームを `/workspaces/LoRAIro/.venv` にマウントし、`UV_PROJECT_ENVIRONMENT` をそのパスへ設定します。本プロファイルはこの構成を維持したまま、オプトインの追加機能のみを加えます。具体的には、`bootstrap.sh` で復元する永続ボリューム (Herdr バイナリ、`~/.claude.json`、SSH の `authorized_keys` / `known_hosts`)、sshd Feature のデフォルトポートマッピング (`2222:2222`)、新規ボリュームのシードに使う `LORAIRO_VOLUME_PREFIX` です。デフォルトプロファイルとは異なり、`make setup`、`uv sync`、および clone は一切実行しません。

利用時は `--config .devcontainer/shared-worktree/devcontainer.json` で明示的に選択してください。デフォルトプロファイルの Dev Containers ロックファイルは共有されないため、必要に応じて Feature を個別にピン留めしてください。

## 永続化の対象と保存先

| 状態 | 保存先 |
| --- | --- |
| Codex / Claude / XDG の config・cache・state | 既存の名前付きボリューム (`lorairo-codex-config`, `lorairo-claude-config`, `lorairo-linux-*`) |
| venv、worktree | `lorairo-venv`, `lorairo-worktrees` |
| Herdr バイナリ (0.9.x)、`~/.claude.json`、`~/.ssh/authorized_keys`、`~/.ssh/known_hosts` (任意) | `~/.persist` の `lorairo-shared-persist` (`bootstrap.sh restore` で復元) |
| sshd の **ホストキー** | 永続化しない: 新しいコンテナは新しいキーを持つ (手順 6 を参照) |

`bootstrap.sh restore` は、必須ファイルがシードされていない場合に失敗 (exit 1) します。また、内容が異なる既存ファイルや、シンボリックリンク・ディレクトリ・特殊ファイルが配置先にある場合は上書きしません。`bootstrap.sh save` は変更された設定の旧バイト列を `~/.persist/backups/` に退避し、異なる Herdr バイナリの上書きを拒否します (アップグレード時は永続化済みコピーを意図的に削除してください)。`known_hosts` は任意の不透明バイト列として保持します。失われても再検証の手間が生じるだけです。

## 空でない既存ボリュームがある場合: 新しいプレフィックスでシードする

`lorairo-codex-config` や `lorairo-linux-config/cache/state` がすでに存在して空でない場合 (用途が不明な場合を含む)、**それらには触れずに残し**、代わりに明示的なプレフィックス配下へ新しいボリュームをシードしてください。プレフィックスは 5 つの名前を指定します: `<prefix>-codex-config`、`<prefix>-linux-config`、`<prefix>-linux-cache`、`<prefix>-linux-state`、`<prefix>-shared-persist`。Claude、venv、worktree、拡張機能、bash 履歴の各ボリュームは `lorairo-*` 名のまま維持されます。移行ヘルパー (`--volume-prefix`) とプロファイル (`LORAIRO_VOLUME_PREFIX`) には **同じ** 値を指定してください。ヘルパーによる XDG Git 設定のコピー先も新しい `<prefix>-linux-config` になります。`--volume-prefix` は `--volume` / `--shared-volume` と併用できず、値としての `lorairo` 自体も書き込み前に拒否されます。

~~~powershell
$prefix = "lorairo-herdr-20261106"          # 新規・小文字のみ。部分移行済みのプレフィックスは再利用しない
# 1) 5 つの対象すべてが存在しないか空であることを確認 (読み取り専用)
foreach ($n in "codex-config","linux-config","linux-cache","linux-state","shared-persist") { docker volume inspect "$prefix-$n" }
# 2) シード実行 (docker cp 実行中は移行元コンテナが一時停止し、エージェント・Herdr・SSH もその間凍結する)
python scripts/migrate_container_codex.py --container <old-id> --backup-dir <new private dir> --with-shared-extras --volume-prefix $prefix
# 3) Dev Containers CLI から同じプレフィックスが見える状態で新コンテナを作成
$env:LORAIRO_VOLUME_PREFIX = $prefix
devcontainer up --workspace-folder <host checkout> --config .devcontainer/shared-worktree/devcontainer.json --id-label <new-label>
~~~

プレフィックス付きのボリュームであっても空でなければ拒否されます。部分的な移行で失敗したあとは **再試行せず**、バックアップディレクトリとすべてのボリュームをそのまま保持したうえで、新しいプレフィックスと新しいバックアップディレクトリを意図的に選び直してください。バックアップディレクトリは非公開権限 (0700、ファイルは 0600、Windows では保護された DACL) で作成されます。VS Code を閉じても Herdr やエージェントが停止しないよう、本プロファイルは `shutdownAction: none` を設定しています。なお、ここに記載したコマンドはこの環境で Docker に対して実行していません (末尾を参照)。

## 再作成ランブック (`<placeholder>` 付きコマンドはこのホストで未検証)

現在稼働中のコンテナは Codex / XDG が **overlay** 上にあり (名前付きホームボリュームなし)、`~/.persist` マウントもありません。そのため `bootstrap.sh save` だけではシードできず、フル移行が必要です。

1. **ドレイン**: エージェントの作業を停止し、未コミット変更のある worktree を保存します。`~/.codex` や SQLite へ書き込むプロセスがないことを確認してください。古いコンテナは削除せず残します。
2. **移行パスの選択**
   - Codex / XDG が overlay 上にある場合 (現行コンテナ): 追加ファイル込みのフル移行を実行します。
     `python scripts/migrate_container_codex.py --container <old-id> --backup-dir <new private dir> --with-shared-extras`
   - Codex / XDG がすでに名前付きボリューム上にある場合 (本プロファイルから作成したコンテナ): 追加ファイルのみ移行します。
     `python scripts/migrate_container_codex.py --container <id> --backup-dir <new private dir> --shared-extras-only`
     (この種のコンテナでは、再作成前に SSH 経由で `bootstrap.sh save` を実行すると永続ボリュームを更新できます。)
3. **ボリュームの特定と空チェック (移行実行前)**: `lorairo-codex-config`、`lorairo-linux-config`、`lorairo-linux-cache`、`lorairo-linux-state` (フル移行時のみ)、および `lorairo-shared-persist` に対して `docker volume inspect <name>` を実行し、すべての移行先が空または未作成であることを確認します。移行処理は空でないボリュームを拒否し、既存の状態を削除も上書きもしません。
   別の `--backup-dir` を指定しても、空でないボリュームはクリアされません。`--volume` が名前を変えるのは Codex ボリュームのみ、`--shared-volume` が変えるのは永続ボリュームのみであり、XDG ボリューム名はヘルパーとプロファイルの `mounts` で固定されています。カスタムボリューム名を使う場合は、プロファイルの対応する `mounts` エントリも合わせて変更してください。部分移行後に止まった場合は、バックアップディレクトリとすべてのボリュームをそのまま残し、確認のうえ新しいボリューム名と対応するマウントを選んで明示的に復旧します。
   必須の移行元ファイル (Herdr、`~/.claude.json`、`authorized_keys`) が欠けている場合、成果物を一切書き込む前に中断します。
4. **明示的な設定で新コンテナを作成 (旧コンテナは保持)**:
   `devcontainer up --workspace-folder <host checkout> --config .devcontainer/shared-worktree/devcontainer.json --id-label <new-label>`
   (`<new-label>` で旧コンテナと区別し、`--remove-existing-container` は意図的に使いません。)
   旧コンテナが稼働中だとホストのポート 2222 が競合するため、先に旧コンテナを停止してください (`docker stop <old-id>`)。削除はしないでください。
5. postCreate が `bootstrap.sh restore` を実行します。ログに `restored` / `already present` が出力され、`refusing` がないことを確認してください。
6. **SSH ホストキー**: 新コンテナでは sshd のホストフィンガープリントが変わります。信頼できる経路 (新コンテナ内の Dev Containers ターミナル) から公開鍵ごとにフィンガープリントを取得してください:
   `for k in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -lf "$k"; done`
   これをクライアントの表示と照合します。`ssh-keyscan` の出力だけでは検証になりません。一致を確認してから古い `known_hosts` エントリを置き換えてください。`StrictHostKeyChecking=no` は絶対に使わないでください。
7. **検証**: 同じ Herdr セッション (`herdr --session val-orchestration status server --json`)、両エージェントとの会話の往復、既存モニターの動作を確認します。認証・フック・信頼承認の判断はユーザーが行います。
8. **ロールバック**: 新コンテナを停止し、`docker start <old-id>` を実行します。バックアップと旧コンテナは変更されておらず、名前付きボリュームも削除されません。

上記の Docker を伴う手順 (ビルド、シード、再作成) は、ここでは **未実行・未検証** です。
