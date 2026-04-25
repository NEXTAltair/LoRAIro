# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Project` SQLAlchemy モデル (`src/lorairo/database/schema.py`)
- `Image.project_id` FK カラム (`src/lorairo/database/schema.py`)
- `ImageFilterCriteria.project_name` / `project_id` フィールド (`src/lorairo/database/filter_criteria.py`)
- `DatasetExportService.export_with_criteria()` — GUI/CLI/API 統合エクスポートメソッド (`src/lorairo/services/dataset_export_service.py`)
- Alembic マイグレーション: `projects` テーブル CREATE + `images.project_id` バックフィル
- `lorairo-cli export create` 新フィルタオプション 8 種: `--tags`, `--excluded-tags`, `--caption`, `--manual-rating`, `--ai-rating`, `--score-min`, `--score-max`, `--include-nsfw`

### Changed

> **BREAKING CHANGES** — 既存スクリプトやワークフローへの影響あり。移行手順は以下を参照。
>
> **Migration:**
>
> ```bash
> # データのバックアップ (推奨)
> cp -r lorairo_data/ lorairo_data_backup_$(date +%Y%m%d)/
>
> # DB スキーマ更新 (必須)
> uv run alembic upgrade head
>
> # 旧 CLI プロジェクトの移行 (CLI ユーザーのみ)
> # NOTE: scripts/migrate_legacy_projects.py はこのバージョンに同梱されています
> uv run python scripts/migrate_legacy_projects.py --dry-run  # プレビュー
> uv run python scripts/migrate_legacy_projects.py --backup   # 本番実行
> ```

- **[BREAKING]** `lorairo-cli export create` がフィルタ条件を **必須化** — フィルタ無し呼び出しは `exit_code=2`
  - 移行: 既存スクリプトに `--project <name>` 等を追加すること
  - エラー例: `Error: エクスポートには最低1つのフィルタ条件が必要です`
- **[BREAKING]** CLI プロジェクト保存場所を `~/.lorairo/projects/` から `lorairo_data/` へ統一
  - 移行: 既存プロジェクトは `uv run python scripts/migrate_legacy_projects.py --dry-run` でプレビュー

---

## Related

- [ADR 0017: Project DB Normalization](docs/decisions/0017-project-db-normalization.md)
- [ADR 0018: Project Storage Unification](docs/decisions/0018-project-storage-unification.md)
- [ADR 0019: Export Filter Required Design](docs/decisions/0019-export-filter-required-design.md)
- [Epic #166](https://github.com/NEXTAltair/LoRAIro/issues/166)

[Unreleased]: https://github.com/NEXTAltair/LoRAIro/compare/HEAD...HEAD
