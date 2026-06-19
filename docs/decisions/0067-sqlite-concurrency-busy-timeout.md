---
type: ADR
title: SQLite Concurrency: busy_timeout + Lock Error Classification
status: Accepted (2026-06-15)
timestamp: 2026-06-15
tags: []
---
# ADR 0067: SQLite Concurrency: busy_timeout + Lock Error Classification

- **関連 Issue**: [NEXTAltair/LoRAIro#767](https://github.com/NEXTAltair/LoRAIro/issues/767)
- **関連 ADR**: [ADR 0042](0042-batch-annotation-db-save-io.md) (Batch Annotation DB Save I/O),
  [ADR 0057](0057-cli-jsonl-output-and-error-contract.md) (CLI Error Contract)

## Context

LoRAIro の画像 DB は SQLite。`db_core.create_db_engine()` は接続時に
`journal_mode=WAL` と `synchronous=NORMAL` を設定済みで、読み取りと書き込みの
並行性はある程度確保されている。しかし SQLite は **同時書き込みを 1 プロセスに
限定**する。

GUI を開いたまま CLI を併用する運用 (検索・一覧・アノテーション保存・画像登録) では、
両者が同じプロジェクト DB に書き込もうとすると `database is locked` が発生する。
従来コードには `busy_timeout` の設定がなく、短時間の競合でも即時失敗していた。

目標は「完全な複数 writer 対応」ではなく、SQLite/WAL 前提で実用上の併用性を上げる
第一段階を整えること。

## Decision

### 1. busy_timeout を設定する

`create_db_engine()` の SQLite connect リスナーで `PRAGMA busy_timeout` を設定する。
値は `config/lorairo.toml` の `[database] busy_timeout_ms` で調整可能 (既定 30000ms)。
DEFAULT_CONFIG にも同名キーを追加し、`db_core.BUSY_TIMEOUT_MS` を SSoT とする。

短時間の書き込み競合では即時失敗せず、この時間まで SQLite 側でリトライ待機する。

### 2. ロック競合エラーを分類・表示する

`database is locked` / `database is busy` を示す `OperationalError` を、汎用 DB エラーとは
区別して扱う。判定ロジックは `lorairo.database.db_errors.is_sqlite_lock_error()` に集約し
(cause-chain を辿り型名 + メッセージで判定、重依存を import しない)、以下で共有する。

- **CLI**: `_errors.classify_exception()` で SQLite ロックを再試行可能な `CONFLICT`
  (`retryable=True`) に分類し、対処ヒントを表示する。汎用 SQLAlchemy エラーより先に
  評価する (ロックも `OperationalError` のため)。`CONFLICT` は ADR 0057 の安定 wire
  コード集合 (15 種) 内なので新コードは増やさない。
- **GUI**: `LoRAIroWorkerBase` のエラー整形で、ロック時は「他プロセス (CLI 等) が
  書き込み中。完了を待って再読み込み/再実行」という分かりやすい日本語に置換する。

### 3. 長トランザクション保持フローは現状維持 (短トランザクション原則を確認)

主要な書き込みフローを調査した結果、重い処理 (画像 I/O・WebAPI・モデル実行) の最中に
DB トランザクションを保持し続ける箇所は見つからなかった。

- リポジトリ層は `with self.session_factory() as session:` の短命セッションで CRUD を
  完結させる (BaseRepository / AnnotationRepository ほか)。
- CLI `annotate run` は chunk 単位で「画像ロード → アノテーション (セッション無し) →
  短い保存トランザクション」に分離済み (ADR 0042 / 0053)。
- GUI アノテーション保存・画像登録ワーカーも Manager 経由の短命セッションを使う。

よって本 ADR では既存フローを変更しない。将来 per-image commit の集約が必要になった
場合は ADR 0042 の batch save API を踏襲する。

### 4. GUI の外部更新検知は手動リロードに留める (非目標を明確化)

CLI が DB を書き換えても GUI のメモリ上の検索結果・件数表示は自動更新されない。
本段階では **手動の再検索/再読み込み**で対応する方針とし、DB ファイル更新時刻の監視や
更新イベントのポーリングは将来課題 (後続 Issue) とする。

### 非目標

- SQLite で完全な複数同時 writer を保証すること
- 大量アノテーション保存を GUI と CLI で同時実行しても衝突しないこと
- PostgreSQL 等への移行

## Rationale

WAL + busy_timeout + 短トランザクションは SQLite 併用性を上げる現実的な第一段階。
busy_timeout は 1 行の PRAGMA で大半の短時間競合を吸収でき、アプリ側のリトライループ
より単純。ロック競合を `CONFLICT` (retryable) に分類することで、エージェント/人間とも
「待って再試行すればよい一時的競合」と「恒久的な DB エラー」を区別できる。

別案として「アプリ層で `OperationalError` を捕捉して指数バックオフ再試行」も検討したが、
busy_timeout が SQLite ネイティブに同等を提供するため YAGNI として見送った。複数 writer の
本格対応 (PostgreSQL 移行) は需要が出た時点で別途検討する。

## Consequences

- 既定 30 秒まで書き込み競合を待機するため、GUI/CLI 併用時の `database is locked` 即時
  失敗が大幅に減る。
- 競合が 30 秒を超えた場合はロックとして分類され、ユーザーに再試行を促すメッセージが出る
  (CLI は `CONFLICT` + ヒント、GUI は専用文言)。
- busy_timeout は「待つ」挙動なので、デッドロック級の長時間ロック時は応答が最大 30 秒
  ブロックし得る。値は設定で短縮可能。
- GUI の外部更新自動反映は未対応。CLI 併用後は手動で再検索/再読み込みが必要 (ドキュメント
  に明記)。