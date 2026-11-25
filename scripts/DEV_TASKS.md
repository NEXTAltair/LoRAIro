# ポータブル開発タスク

Windows PowerShell と Linux の両方で、同じエントリーポイント (Python 3.12+) を使用できる。

```text
python scripts/dev_tasks.py test
python scripts/dev_tasks.py test-all
python scripts/dev_tasks.py lint
python scripts/dev_tasks.py format
python scripts/dev_tasks.py run-gui
python scripts/dev_tasks.py test-all --dry-run
```

`make test`、`make lint`、およびその他の移行済みターゲットはこのスクリプトへ委譲する。`python` エイリアスがない Linux 環境では `python3` を使用する。Make は適切なデフォルトを自動選択し、`make PYTHON=...` で上書きできる。

## 初回セットアップと依存関係の変更

**メインの共有チェックアウト**から submodule を初期化し、ワークスペースをインストールする。

```text
git submodule update --init --recursive
python scripts/dev_tasks.py install-dev
```

これは共有環境への明示的な書き込み操作である。同期中は、その環境を使用する他のタスクを停止する。`make setup` は従来どおり外部エージェントスキルの復元も追加で実行し、skill-lock の失敗はここではバイパスしない。実行依存のみのインストールには `install` を使用する。新しい worktree ではタスクに必要な submodule のみ初期化し、`install` / `install-dev` の実行や独自の `.venv` 作成は行わない。

## タスクの前提条件

前提条件の定義元は `dev_tasks.py` 内の `TASKS` レジストリである。コマンドを選択しても、追加の前提条件や同期権限が付与されるわけではない。

| タスク | インタープリタ / ツール | 必須のローカルパッケージチェックアウト |
| --- | --- | --- |
| `adr-drift`, `adr-index`, `adr-okf`, `docs-okf` | ランチャー Python、標準ライブラリのみ | なし (`docs-okf` は存在するパッケージドキュメントも検査する) |
| `lint`, `format`, `generate-ui` | Ruff / PySide6 導入済みの共有 Python | なし |
| `format-iam-lib`, `format-genai-tag` | Ruff 導入済みの共有 Python | 指定パッケージのみ |
| `test-iam-lib`, `test-genai-tag` | テスト依存導入済みの共有 Python | 指定パッケージのみ |
| `test-runtime-local`, `test-runtime-webapi` | IAM / ランタイム依存導入済みの共有 Python | `image-annotator-lib` のみ (WebAPI は LoRAIro 設定も参照する) |
| `test`, `test-all`, `mypy`, `run-gui` | アプリ / テスト / 型チェック依存導入済みの共有 Python | 両パッケージ |
| `install`, `install-dev` | uv (既存の共有 Python は不要) | 両パッケージ、メインチェックアウトのみ |

ドキュメント系タスクは、`.git`、`.venv`、uv、初期化済み submodule がなくても動作する。`UV_PROJECT_ENVIRONMENT` に古いパスが設定されている場合でも動作する。`adr-drift` は利用可能であれば Git 履歴を使用し、利用できない場合は従来の制限付きフォールバックを維持する。その他のタスクは Git を使って共有環境を特定する。必須 submodule が欠けている場合は暗黙に fetch せずエラーとする。無関係な submodule は検査しない。

共有環境を同期するのはインストール系タスクのみである。ただし、その他のタスクがすべて読み取り専用という意味ではない。format や UI / インデックス生成は出力を書き込み、テストはキャッシュやフィクスチャを書き込み、明示的なランタイムテストはモデルのダウンロードや有料 API 呼び出しを行う場合がある。レジストリが制御するのは前提条件であり、OS サンドボックスではない。

## 環境の安全性

デフォルトの実行環境はハードコードされた `/workspaces` パスではなく、Git 経由で見つけたメインチェックアウトの `.venv` である。`UV_PROJECT_ENVIRONMENT` を設定する場合、その値は同じ環境を指す絶対パスでなければならない。Windows 上の古い Linux パスは拒否される。設定元を正しく修正することとし、古いパスを満たす目的でディレクトリを作成してはならない。

共有ランタイムを使うタスクは、インストール済みのインタープリタを検証して直接実行する。uv の呼び出しやプロジェクト環境の探索は行わない。不足する依存はテスト中に補うのではなく、明示的にインストールする必要がある。アプリコードをインポートするタスクでは、アクティブな worktree の必須ソースディレクトリが `PYTHONPATH` によって共有 editable インストールパスを上書きする。`VIRTUAL_ENV` とコマンドの `PATH` により、子ツールも同じ共有環境を選択する。静的解析ツールにはアプリソースを注入しない。3 つのパッケージはそれぞれ独立した pytest プロセス、作業ディレクトリ、カバレッジを維持する。

テストタスクは Qt の `offscreen` を選択する。Windows の GUI 実行では、このランナーからその設定は引き継がれない。実モデルおよび有料 API のテストは明示的な `test-runtime-local` / `test-runtime-webapi` タスクのまま維持され、通常の `test-all` には含まれない。

## UI・ADR・クリーンアップ

`generate-ui`、`adr-drift`、`adr-index`、`adr-okf`、`docs-okf` は同じポータブルランナーを使用する。既存の `.ui` 生成は Qt Designer の編集ツールなしで利用できる。UIC はシェルや追加同期を介さず、選択されたインタープリタ配下で実行される。

メンテナンス操作は実行前にプレビューできる。

```text
python scripts/safe_cleanup.py clean --dry-run
python scripts/safe_cleanup.py venv-rebuild --dry-run
```

実行時は `--dry-run` を外すか、`make clean` / `make venv-rebuild` を使用する。`clean` が削除するのは、ルートにある指定済みのビルド成果物と、`src`・`tests`・`scripts` 配下の Python キャッシュのみである。ネストされたリポジトリ、仮想環境、リンク / ジャンクション、データディレクトリ、worktree は一切走査しない。削除対象のキャッシュは再生成可能だが、バックアップは取られない。ローカルパッケージのキャッシュは意図的にそのまま残す。

`venv-rebuild` はメインチェックアウトから**システム Python** を用いて実行しなければならない。先に同じ環境を使用する他のプロセスを停止する。明示的な `install-dev` を実行する前に、旧 `.venv` は `.venv.backup-<unique ID>` へリネームされる。このバックアップはインストールが失敗しても保持される。自動削除や自動ロールバックは行わない。出力されたバックアップパスを確認し、必要であれば手動で復旧する。再構築は他のタスクと並列実行しない。

worktree のクリーンアップは引き続き別系統の kit 側で管理する。ここでは kit フックや Codex 設定は変更しない。
