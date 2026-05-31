# ADR 0046: Loguru Placeholder Format

- **日付**: 2026-05-31
- **ステータス**: Accepted

## Context

Loguru logger に stdlib logging 形式の `%s` / `%r` / `%d` placeholder を渡すと、
値が展開されず、調査に必要な route_preference などの値がログに残らない。

## Decision

`src/lorairo` の Loguru 呼び出しでは `{}` / `{!r}` placeholder を使う。stdlib
`logging.getLogger()` を使うコードの `%` placeholder は対象外とする。

## Rationale

Loguru の遅延 formatting と既存の logger 呼び出し形を保ちながら、実際の値を
ログへ出せる。f-string への全面変更よりも差分が小さく、不要な文字列評価も避けられる。

## Consequences

Loguru 呼び出しに stdlib 形式 placeholder を追加しないよう、AST ベースの単体テストで
`logger.<level>("...%s...", arg, ...)` 形式を検出する。
