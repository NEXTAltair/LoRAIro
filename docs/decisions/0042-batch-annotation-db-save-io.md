---
type: ADR
title: Batch Annotation DB Save I/O
status: Accepted
timestamp: 2026-05-30
tags: []
---
# ADR 0042: Batch Annotation DB Save I/O

- **関連 Issue**: [NEXTAltair/LoRAIro#568](https://github.com/NEXTAltair/LoRAIro/issues/568)
- **関連 ADR**: [ADR 0012](0012-batch-tag-atomic-transaction.md),
  [ADR 0035](0035-repository-aggregate-split-policy.md)

## Context

Provider Batch API の結果保存では、100 枚規模の画像に対して 1 枚ずつ `save_annotations()` が呼ばれていた。そのため、各呼び出しが独立した SQLite トランザクションをコミットする構造になっていた。

WSL2 の devcontainer 環境における `/workspaces` は 9p バインドマウントである。SQLite の rollback journal と `synchronous=FULL` によるコミットが重なると、`fsync` とメタデータ操作がホスト側へ波及し、LoRAIro だけでなく VSCode や OS 全体の応答性を低下させていた。

既存の手動によるタグ・レーティング・スコアの一括操作では単一トランザクションを採用している。一方、アノテーション結果の保存だけが画像単位コミットのまま残っていた。

## Decision

`AnnotationRepository` に、複数画像をチャンク単位で保存するバッチ API を追加する。

- 既存の `save_annotations()` は、単一画像向け API としてそのまま維持する。
- 新規のバッチ API は、既存の `_save_tags()`、`_save_captions()`、`_save_scores()`、`_save_score_labels()`、`_save_ratings()` を同一セッション内で再利用し、チャンクごとに 1 回だけコミットする。
- サービス層は保存対象のペイロードを事前に組み立てる。チャンク保存が失敗した場合のみ、そのチャンクを画像単位で再試行する。
- これにより、通常時のコミット回数を大幅に削減しつつ、従来の部分成功および個別エラー報告の挙動を維持する。
- SQLite エンジンでは、ファイルベースの DB に対して `journal_mode=WAL` と `synchronous=NORMAL` を設定する。
- ファイルログの sink には `enqueue=True` を指定し、ログファイルの I/O を呼び出しスレッドから分離する。

## Consequences

通常の Provider Batch 結果保存では、100 枚規模でもコミット回数がチャンク数まで減少する。

失敗時はチャンクをロールバックしたうえで画像単位に再試行するため、失敗したチャンクのみ従来と同等のコミット回数に戻る。これは、エラーの局所化と既存 UI および API における保存件数報告の維持を優先した意図的なトレードオフである。

WAL モードでは `-wal` および `-shm` のサイドカーファイルが生成される。SQLite が WAL を利用できない環境では、`PRAGMA` の設定失敗を警告(warning)にとどめ、DB の初期化自体は継続する。
