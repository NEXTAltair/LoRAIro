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

`db_core.py` だけが `loguru` ではなく標準の `logging`(`logging.getLogger`)を使用していた。`log.py` の `initialize_logging()` には標準 `logging` から `loguru` へのブリッジ(`InterceptHandler` など)が存在しない。そのため、`db_core` が出力するログ(エンジン生成、`PRAGMA` 適用、`get_db_session()` のトランザクション失敗時の ERROR とトレースバック)は `loguru` のファイルや標準エラー出力の sink に届かず、`logs/lorairo.log` に一切記録されなかった。

特に以下の 2 点が深刻な問題であった。

- `get_db_session()` のトランザクション失敗時に `logger.error(..., exc_info=True)` で出力するトレースバックがファイルログに残らず、DB 書き込み失敗の事後調査ができない。
- ADR 0042(#569)で追加した `PRAGMA journal_mode=WAL` の適用ログをアプリログで確認できない。

さらに、調査の過程で次の 2 点も判明した。

- `loguru` の `logger.error(msg, exc_info=True)` は標準 `logging` 互換の `exc_info` を解釈しないため、トレースバックを出力しない。`loguru` では `logger.opt(exception=True)` を使う必要がある。
- `db_core` の初期化ログがモジュールレベル(インポート時)で出力されており、`initialize_logging()` より先に実行されるため、どのロガーを使ってもファイル sink に記録されない。

## Decision

`db_core` のログ出力を `loguru` に統一する。`InterceptHandler` による標準 `logging` 全体の集約は採用しない。

- `db_core.py` のロガーを `from ..utils.log import logger`(`loguru`)へ統一する。
- `exc_info=True` を渡していた 3 箇所を `logger.opt(exception=True)` に書き換える。この際、`LOG_FORMAT` へ `{exception}` は**追加しない**。`opt(exception=True)` はフォーマット指定に `{exception}` がなくてもトレースバックを付加するため、両方を併用するとトレースバックが二重出力される(実機検証で確認済み)。
- モジュールレベルの初期化ログを `_get_default_session_factory()` の遅延初期化ブロックへ移動する。これにより、実際にデフォルト DB を準備するタイミング(すなわち `initialize_logging()` 実行後)で出力されるようにする。

## Consequences

DB 層のログ(エンジン生成、`PRAGMA` 適用、トランザクション失敗時のトレースバック、初期化完了)が `loguru` のファイル sink に乗り、`logs/lorairo.log` に記録されるようになる。ADR 0042 で導入した WAL 適用もアプリログで確認できる。

一方、SQLAlchemy や Alembic などの外部ライブラリが出力する標準 `logging` のログは、引き続き `loguru` には集約されない。これらも捕捉する必要が生じた場合は、`initialize_logging()` に `loguru` 公式の `InterceptHandler` を追加する案(案 B)を将来検討する。本 ADR はアプリケーションコード(`db_core`)の規約統一に限定し、YAGNI に従って外部ライブラリログの集約は見送る。

> 注:`docs/decisions/` には 0042 番台のファイルが複数存在する(索引未登録の番号衝突)。本 ADR は索引に登録済みの 0042 の次として 0043 を採番した。番号衝突の整理は別タスクとする。
