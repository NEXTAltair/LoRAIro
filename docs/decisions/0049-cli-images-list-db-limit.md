---
type: ADR
title: CLI 画像一覧の取得件数制限をリポジトリクエリへ適用する
status: Accepted
timestamp: 2026-06-01
tags: []
---
# ADR 0049: CLI 画像一覧の取得件数制限をリポジトリクエリへ適用する

## 背景

`lorairo-cli images list --limit N` はこれまで、一致する画像レコードを全件取得してから CLI 層で Python リストをスライスしていた。大規模プロジェクトでは、少数の画像一覧を表示するだけでもデータセット全体のメタデータ取得コストが発生していた。

一方で、CLI は `Showing N of M images.` と表示するため、一致する総件数も引き続き必要である。

## 決定

`ImageFilterCriteria` に `limit` と `offset` を追加する。

`ImageRepository.get_images_by_filter()` は次の手順で処理を行う。

1. 既存のフィルタ済み ID クエリを構築する。
2. サブクエリからフィルタ結果の総件数を集計する。
3. ID クエリに安定した `Image.id` 順のソートと `offset` / `limit` を適用する。
4. ページング済みの ID のみを対象にアノテーションメタデータを取得する。

`lorairo-cli images list` は、リポジトリ呼び出し後にスライスするのではなく、`ImageFilterCriteria` 経由で `--limit` の値を渡す。

## 影響

`get_images_by_filter()` の戻り値は引き続き `(records, total_count)` のまま維持される。`limit` 未指定時の挙動は変わらない。`limit` 指定時は `records` に要求されたページ分だけが入り、`total_count` にはフィルタ全体の総件数が返る。

ページング結果に対して、ID に基づく決定論的な順序が保証される。
