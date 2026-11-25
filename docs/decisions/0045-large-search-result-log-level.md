---
type: ADR
title: Large Search Result Log Level
status: Accepted
timestamp: 2026-05-31
tags: []
---
# ADR 0045: Large Search Result Log Level

## Context

通常の検索操作で結果件数が 10000 件を超えた場合、UI はユーザーへ注意を表示する。これと同時に、`update_search_preview()` が `WARNING` ログも出力していた。

しかし、大量の検索結果が返ること自体は処理の失敗ではない。その結果、エラー調査時に `WARNING` ログのノイズが増えていた。

## Decision

大量の検索結果を通知するログのレベルは `INFO` とする。

- UI 側の注意表示は従来どおり維持する。
- `WARNING` または `ERROR` として扱うのは、処理失敗、入力異常、タイムアウトなどの実際の問題に限定する。

## Rationale

ログレベルを `DEBUG` まで下げると、通常操作における検索規模を後から追跡しにくくなる。

一方で `INFO` であれば、正常なユーザー操作の観測値として記録を残せる。これにより、警告調査時のノイズを抑えつつ、運用上の文脈も保持できる。

## Consequences

`logs/lorairo.log` には、大量の検索結果が `INFO` として記録される。そのため、`WARNING` 以上でログを調査する際は、実際の失敗や復旧が必要な状態に集中できる。
