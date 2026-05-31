# ADR 0045: Large Search Result Log Level

- **日付**: 2026-05-31
- **ステータス**: Accepted

## Context

通常の検索操作で結果件数が 10000 件を超えると、UI はユーザーへ注意表示する一方で、
`update_search_preview()` が WARNING ログも出していた。大量結果自体は処理失敗ではなく、
エラー調査時の WARNING ノイズになっていた。

## Decision

大量検索結果の通知ログは INFO とする。UI 側の注意表示は維持し、処理失敗、入力異常、
タイムアウトなどの実際の問題だけを WARNING または ERROR として扱う。

## Rationale

DEBUG まで下げると通常操作の検索規模を追跡しづらい。INFO は正常なユーザー操作の
観測値として残せるため、警告調査のノイズを減らしつつ運用上の文脈を保持できる。

## Consequences

`logs/lorairo.log` では大量検索結果が INFO として記録される。WARNING 以上で調査する
場合は、実際の失敗や復旧が必要な状態に集中できる。
