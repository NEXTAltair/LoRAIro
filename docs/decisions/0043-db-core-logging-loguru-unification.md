---
type: ADR
title: db_core Logging Loguru Unification
status: Accepted
timestamp: 2026-05-31
tags: []
---
# ADR 0043: db_core Logging Loguru Unification

- **関連 Issue**: [NEXTAltair/LoRAIro#572](https://github.com/NEXTAltair/LoRAIro/issues/572)
- **関連 ADR**: [ADR 0042](0042-batch-annotation-db-save-io.md)

## Context

`db_core.py` だけが loguru ではなく標準 `logging` (`logging.getLogger`) を使っていた。
`log.py` の `initialize_logging()` には標準 logging → loguru のブリッジ (InterceptHandler 等)
が無いため、db_core が出すログ (engine 生成・PRAGMA 適用・`get_db_session()` の
トランザクション失敗 ERROR + traceback) は loguru の file / stderr sink に乗らず、
`logs/lorairo.log` に一切記録されなかった。

特に問題だったのは:

- `get_db_session()` のトランザクション失敗 `logger.error(..., exc_info=True)` の traceback が
  ファイルログに残らず、DB 書き込み失敗の事後調査ができない。
- ADR 0042 (#569) で追加した `PRAGMA journal_mode=WAL` 適用ログをアプリログで確認できない。

加えて調査中に 2 点が判明した:

- loguru の `logger.error(msg, exc_info=True)` は標準 logging 互換の `exc_info` を解釈せず、
  traceback を出力しない。loguru では `logger.opt(exception=True)` を使う必要がある。
- db_core の初期化ログは module-level (import 時) で出力されており、これは
  `initialize_logging()` より前に実行されるため、どのロガーを使っても file sink に乗らない。

## Decision

db_core のログを loguru に統一する。InterceptHandler による標準 logging 全体の集約は採らない。

- `db_core.py` を `from ..utils.log import logger` (loguru) に統一する。
- `exc_info=True` を渡していた 3 箇所を `logger.opt(exception=True)` に変換する。
  `LOG_FORMAT` に `{exception}` は **追加しない** — `opt(exception=True)` は format に
  `{exception}` が無くても traceback を付加し、両方を使うと traceback が二重出力されるため
  (実機検証で確認)。
- module-level の初期化ログを `_get_default_session_factory()` の遅延ブロックへ移動し、
  実際に default DB を準備する (= `initialize_logging()` 後の) タイミングで出力する。

## Consequences

DB 層のログ (engine 生成・PRAGMA 適用・トランザクション失敗 traceback・初期化完了) が
loguru file sink に乗り、`logs/lorairo.log` に記録される。ADR 0042 の WAL 適用も
アプリログで確認可能になる。

SQLAlchemy / Alembic 等の外部ライブラリが出す標準 logging ログは依然 loguru に集約されない。
これらも捕捉したくなった場合は `initialize_logging()` に loguru 公式の InterceptHandler を
追加する案 (案B) を将来検討する。本 ADR はアプリコード (db_core) の規約統一に限定し、
YAGNI に従ってライブラリログ集約は見送る。

> 注: `docs/decisions/` には 0042 番台のファイルが複数存在する (索引未登録の番号衝突)。
> 本 ADR は索引に登録済みの 0042 の次として 0043 を採番した。番号衝突の整理は別タスク。