# Python 品質チェックコマンド

フォーマット、Lint、および McCabe 複雑度チェックは Ruff が担う。明示的な `C4` と `C90` セレクターにより従来の広範な `C` 指定を維持しており、既存のデフォルト複雑度しきい値 (10) およびマイグレーション除外設定に変更はない。Radon / Lizard は開発依存から除外済みである。これらが提供していた個別のメトリクスレポートを再現するものではなく、サポート対象の代替手段は Ruff の `C901` 診断である。

共有プロジェクト環境が構成され依存関係がインストール済みであれば、以下のコマンドで検査できる。

```text
uv run --no-sync ruff check src/ tests/ --no-fix
uv run --no-sync ruff format src/ tests/ --check
```

これらのコマンドは Windows と Linux のどちらのシェルでも動作する。Make が導入されている環境では、`make lint` が `python scripts/dev_tasks.py lint` へ委譲し、共有環境を検証したうえで同じ 2 つのチェックを実行する。チェックコマンドはファイルを書き換えない。自動フォーマットは `make format`、エディタの保存時アクション、および既存の pre-commit フォーマッターで利用でき、これらの経路ではフォーマットと修正を明示的に実行する。

worktree からコマンドを実行する場合は、メインチェックアウトの実際の共有環境を使用する。残りの Makefile タスクには Linux 固有のパスやシェル構文が残っており、この変更は Makefile 全体のポータビリティを主張するものではない。検証の一環として `clean` や `venv-rebuild` を実行してはならない。移行済みコマンドと共有環境のルーティングについては [DEV_TASKS.md](DEV_TASKS.md) を参照する。安全なクリーンアップは agent-kit とは独立した別個の後続作業として扱う。

参考資料:

- https://docs.astral.sh/ruff/rules/complex-structure/
- https://docs.astral.sh/ruff/settings/#fix
