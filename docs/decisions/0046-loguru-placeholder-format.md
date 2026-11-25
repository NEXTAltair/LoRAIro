---
type: ADR
title: Loguru Placeholder Format
status: Accepted
timestamp: 2026-05-31
tags: []
---
# ADR 0046: Loguru Placeholder Format

## Context

Loguru のロガーに標準ライブラリ `logging` 形式のプレースホルダ(`%s`、`%r`、`%d`)を渡すと、値が展開されない。その結果、障害調査に必要な `route_preference` などの値がログに残らない問題が起きる。

## Decision

`src/lorairo` における Loguru の呼び出しでは、`{}` および `{!r}` 形式のプレースホルダを使用する。

なお、標準ライブラリの `logging.getLogger()` を使うコードに含まれる `%` 形式のプレースホルダは、本決定の対象外とする。

## Rationale

`{}` 形式のプレースホルダを使うことで、Loguru の遅延フォーマットと既存のロガー呼び出し形式を維持したまま、実際の値をログへ出力できる。

また、f-string への全面的な書き換えに比べて変更差分を小さく抑えられ、出力されないログに対する不要な文字列評価も避けられる。

## Consequences

Loguru の呼び出しに標準ライブラリ形式のプレースホルダが混入しないよう、AST ベースの単体テストを追加する。このテストにより、`logger.<level>("...%s...", arg, ...)` 形式の呼び出しを自動検出する。
