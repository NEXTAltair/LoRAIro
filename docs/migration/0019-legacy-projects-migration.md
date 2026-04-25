# 旧 CLI プロジェクトの lorairo_data/ への移行手順

Epic #166 で CLI プロジェクトの保存場所が `~/.lorairo/projects/` から
`config/lorairo.toml` の `database_base_dir` (デフォルト: `lorairo_data/`) に統一されました。

## 対象ユーザー

以下に該当する場合に移行作業が必要です:

- `lorairo-cli project create` を `~/.lorairo/projects/` 存在時に使用したことがある
- `lorairo-cli project list` で旧場所のプロジェクトが表示されていた

## 前提条件

- Git 未コミットの変更がないこと
- `uv sync --dev` でセットアップ済みであること

## 手順

### ステップ 1: 事前バックアップ

移行前に旧プロジェクトディレクトリ全体をバックアップします。

```bash
cp -r ~/.lorairo/projects/ ~/.lorairo/projects_backup_$(date +%Y%m%d)/
```

バックアップが作成されたことを確認します:

```bash
ls -la ~/.lorairo/
```

### ステップ 2: 移行プレビュー (dry-run)

実際にファイルを移動せず、移行対象を確認します。
プロジェクトルートから実行してください。

```bash
uv run python scripts/migrate_legacy_projects.py --dry-run
```

出力例:

```
[DRY-RUN] 移行対象: 3 件
  ~/.lorairo/projects/my_project_20240101_001 -> lorairo_data/my_project_20240101_001
  ~/.lorairo/projects/my_project_20240115_002 -> lorairo_data/my_project_20240115_002
  ~/.lorairo/projects/test_project_20240201_003 -> lorairo_data/test_project_20240201_003
[DRY-RUN] 実際のファイル移動は行いません
```

移行対象に問題がないか確認してから次のステップへ進みます。

### ステップ 3: 本番移行

`--backup` オプションを指定すると、コピー完了後に旧ディレクトリを `.bak` にリネームします。
プロジェクトルートから実行してください。

```bash
uv run python scripts/migrate_legacy_projects.py --backup
```

出力例:

```
移行開始: 3 件
  コピー完了: my_project_20240101_001
  コピー完了: my_project_20240115_002
  コピー完了: test_project_20240201_003
旧ディレクトリをリネーム: ~/.lorairo/projects -> ~/.lorairo/projects.bak
移行完了: 成功=3, スキップ=0, エラー=0
```

### ステップ 4: DB スキーマ更新 (必須)

移行したプロジェクトの SQLite DB に新しいスキーマを適用します。
プロジェクトルートから実行してください。

```bash
uv run alembic upgrade head
```

マイグレーションが正常に完了したことを確認します:

```bash
uv run alembic current
```

### ステップ 5: 移行確認

移行後のプロジェクト一覧を確認します:

```bash
lorairo-cli project list
```

ステップ 2 の dry-run で確認した件数と一致していれば移行成功です。

### ロールバック手順

移行後に問題が発生した場合、以下の手順で元の状態に戻せます。

**`--backup` オプションを使用した場合 (`.bak` リネームを元に戻す):**

```bash
# .bak ディレクトリを元の名前に戻す
mv ~/.lorairo/projects.bak ~/.lorairo/projects
```

**事前バックアップから復元する場合:**

```bash
# バックアップから復元 (日付部分は実際のバックアップ名に合わせる)
cp -r ~/.lorairo/projects_backup_20240425/ ~/.lorairo/projects/
```

**lorairo_data/ にコピーされたプロジェクトを削除する場合:**

```bash
# 移行されたプロジェクトを手動で削除
rm -rf lorairo_data/<project_name>
```

## 注意事項

- このスクリプトはファイルコピーのみ担当します。DB バックフィルは Alembic マイグレーションが実施します
- `lorairo_data/` の相対パスはコマンド実行ディレクトリに依存するため、**プロジェクトルートから実行**してください
- `--backup` オプションを指定しない場合、旧ディレクトリはそのまま残ります (手動での削除が必要)
- 移行スクリプトは冪等性を持ちます。既に移行済みのプロジェクトは自動的にスキップされます
