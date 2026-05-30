# ADR 0042: Batch Annotation DB Save I/O

- **日付**: 2026-05-30
- **ステータス**: Accepted
- **関連 Issue**: [NEXTAltair/LoRAIro#568](https://github.com/NEXTAltair/LoRAIro/issues/568)
- **関連 ADR**: [ADR 0012](0012-batch-tag-atomic-transaction.md),
  [ADR 0035](0035-repository-aggregate-split-policy.md)

## Context

Provider Batch API の結果保存では、100 枚規模の画像に対して 1 画像ごとに
`save_annotations()` が呼ばれ、各呼び出しが独立した SQLite transaction を commit していた。

WSL2 devcontainer の `/workspaces` は 9p bind mount であり、SQLite の rollback journal と
`synchronous=FULL` の commit が重なると、fsync とメタデータ操作がホスト側まで波及して
LoRAIro だけでなく VSCode や OS 全体の応答性を落とす。

既存の手動 tag/rating/score batch 操作は単一 transaction を採用しているが、annotation result
保存だけが per-image commit のままだった。

## Decision

AnnotationRepository に複数画像をチャンク単位で保存する batch API を追加する。

- 既存の `save_annotations()` は単一画像 API として維持する。
- batch API は既存の `_save_tags()` / `_save_captions()` / `_save_scores()` /
  `_save_score_labels()` / `_save_ratings()` を同じ session 内で再利用し、chunk ごとに 1 回だけ
  commit する。
- サービス層は保存対象 payload を先に組み立て、chunk save が失敗した場合だけ、その chunk を
  per-image retry する。
- これにより通常時の commit 数を大幅に減らしつつ、従来の部分成功・個別エラー報告を維持する。
- SQLite engine は file-backed DB 向けに `journal_mode=WAL` と `synchronous=NORMAL` を設定する。
- ファイルログ sink は `enqueue=True` を使い、ログファイル I/O を呼び出しスレッドから分離する。

## Consequences

通常の Provider Batch result 保存では 100 枚規模でも commit は chunk 数まで減る。

失敗時は chunk rollback 後に per-image retry するため、失敗 chunk だけは従来相当の commit 数に戻る。
これはエラー局所化と既存 UI/API の保存件数 reporting を優先するための意図的な tradeoff である。

WAL は `-wal` / `-shm` サイドカーファイルを作る。SQLite が WAL を利用できない環境では PRAGMA
設定失敗を warning に留め、DB 初期化自体は継続する。
