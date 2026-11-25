---
type: ADR
title: "SQLite Concurrency: busy_timeout + Lock Error Classification"
status: Accepted (2026-06-15)
timestamp: 2026-06-15
tags: []
---
# ADR 0067: SQLite Concurrency: busy_timeout + Lock Error Classification

- **関連 Issue**: [NEXTAltair/LoRAIro#767](https://github.com/NEXTAltair/LoRAIro/issues/767)
- **関連 ADR**: [ADR 0042](0042-batch-annotation-db-save-io.md)(Batch Annotation DB Save I/O)、[ADR 0057](0057-cli-jsonl-output-and-error-contract.md)(CLI Error Contract)

## Context

LoRAIro の画像 DB には SQLite を使用している。`db_core.create_db_engine()` は接続時に `journal_mode=WAL` と `synchronous=NORMAL` を設定済みであり、読み取りと書き込みの並行性は一定程度確保されている。しかし SQLite の仕様上、同時書き込みは 1 プロセスに限定される。

GUI を開いたまま CLI を併用する運用(検索、一覧表示、アノテーション保存、画像登録など)では、両者が同じプロジェクト DB に書き込もうとすると `database is locked` が発生する。従来のコードには `busy_timeout` の設定がなく、ごく短時間の競合であっても即座に失敗していた。

本 ADR の目標は完全な複数ライター対応ではなく、SQLite と WAL を前提に実用上の併用性を高める第一段階を整えることである。

## Decision

### 1. `busy_timeout` を設定する

`create_db_engine()` の SQLite connect リスナーで `PRAGMA busy_timeout` を設定する。値は `config/lorairo.toml` の `[database] busy_timeout_ms` で調整可能とし、既定値は `30000`(30000ms)とする。`DEFAULT_CONFIG` にも同名キーを追加し、`db_core.BUSY_TIMEOUT_MS` を SSoT とする。

これにより、短時間の書き込み競合では即時失敗せず、設定時間まで SQLite 側でリトライ待機するようになる。

### 2. ロック競合エラーを分類・表示する

`database is locked` および `database is busy` を示す `OperationalError` を、汎用の DB エラーとは区別して扱う。判定ロジックは `lorairo.database.db_errors.is_sqlite_lock_error()` に集約する。この関数は例外の cause-chain を辿って型名とメッセージから判定し、重い依存をインポートしない設計とする。CLI と GUI の双方でこの判定を共有する。

- **CLI**: `_errors.classify_exception()` において、SQLite ロックを再試行可能な `CONFLICT`(`retryable=True`)に分類し、対処ヒントを表示する。ロック例外も `OperationalError` の一種であるため、汎用 SQLAlchemy エラーより先に評価する。`CONFLICT` は ADR 0057 の安定エラーコード集合(15 種)に含まれているため、新規コードは増やさない。
- **GUI**: `LoRAIroWorkerBase` のエラー整形において、ロック発生時は「他プロセス(CLI 等)が書き込み中。完了を待って再読み込み/再実行」という分かりやすい日本語メッセージへ置換する。

### 3. 長時間トランザクション保持フローは現状維持とする

主要な書き込みフローを調査した結果、重い処理(画像 I/O、WebAPI 呼び出し、モデル実行)の最中に DB トランザクションを保持し続ける箇所は見つからなかった。

- リポジトリ層は `with self.session_factory() as session:` の短命セッションで CRUD を完結させている(`BaseRepository`、`AnnotationRepository` ほか)。
- CLI の `annotate run` はチャンク単位で「画像ロード → アノテーション(セッションなし) → 短い保存トランザクション」に分離済みである(ADR 0042 / 0053)。
- GUI のアノテーション保存および画像登録ワーカーも、Manager 経由の短命セッションを使用している。

したがって本 ADR では既存フローを変更しない。将来的に画像単位コミットの集約が必要になった場合は、ADR 0042 のバッチ保存 API を踏襲する。

### 4. GUI の外部更新検知は手動リロードに留める

CLI が DB を書き換えても、GUI がメモリ上に保持している検索結果や件数表示は自動更新されない。本段階では手動での再検索・再読み込みによって対応する方針とする。DB ファイルの更新時刻監視や更新イベントのポーリングは将来課題(後続 Issue)とする。

### 非目標

- SQLite で完全な複数同時書き込みを保証すること
- 大量アノテーション保存を GUI と CLI で同時実行しても衝突しないようにすること
- PostgreSQL 等への移行

## Rationale

WAL、`busy_timeout`、短トランザクションの組み合わせは、SQLite の併用性を高める現実的な第一段階である。`busy_timeout` は 1 行の PRAGMA で大半の短時間競合を吸収でき、アプリケーション側でリトライループを組むより単純である。また、ロック競合を `CONFLICT`(`retryable=True`)に分類することで、エージェントも人間も「待って再試行すれば解決する一時的な競合」と「恒久的な DB エラー」を区別できる。

別案としてアプリケーション層で `OperationalError` を捕捉し指数バックオフで再試行する案も検討したが、`busy_timeout` が SQLite ネイティブで同等の機能を提供するため、YAGNI に従い見送った。複数ライターへの本格対応(PostgreSQL 移行など)は、需要が生じた時点で別途検討する。

## Consequences

- 既定 30 秒まで書き込み競合を待機するため、GUI と CLI の併用時に発生する `database is locked` の即時失敗が大幅に減る。
- 競合が 30 秒を超えた場合はロックエラーとして分類され、ユーザーに再試行を促すメッセージが表示される(CLI は `CONFLICT` とヒント、GUI は専用文言)。
- `busy_timeout` は待機を行う仕組みのため、デッドロック級の長時間ロックが発生した場合は応答が最大 30 秒ブロックし得る。ただし待機時間は設定で短縮できる。
- GUI への外部更新の自動反映は未対応であるため、CLI 併用後は手動での再検索・再読み込みが必要となる(ドキュメントへ明記する)。
