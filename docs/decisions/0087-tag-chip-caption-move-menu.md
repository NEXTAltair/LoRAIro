---
type: ADR
title: タグ chip 右クリックをキャプション移動の操作ハブにする
status: Accepted
timestamp: 2026-07-09
tags: [GUI, Tags, Captions]
---
# ADR 0087: タグ chip 右クリックをキャプション移動の操作ハブにする

## Context

再取り込みした学習データセットの `.txt` タグ欄には、タグではなくキャプションとして扱うべき
文章的な文字列が混入することがある。既存のタグ chip は翻訳なしを点線スタイルで表示でき、
右クリックから翻訳・種別・使用頻度・refinement 操作へ進めるため、ユーザーが目視で判断する
入口としてすでに機能している。

## Decision

未マッチ長文用の隔離キューや自動降格判定は作らず、既存のタグ chip 右クリックメニューを
操作ハブとして拡張する。

- 「別のタグに置換…」は入力ダイアログで置換先を受け取り、既存の
  `tag_replace_requested(from, to)` と `replace_tag_for_images_batch` 経路へ流す。
- 「キャプションに移動」は現在表示中の caption 投影文字列へ `, ` 区切りでタグ文字列を追記し、
  既存の `ImageDBWriteService.update_caption` で新しい caption 行として保存する。
- caption 保存が成功した場合だけ、元タグを `reject_reason='incorrect'` で soft-reject する。

## Rationale

タグ欄の文章混入は少数で、人間が「置換 / キャプションへ移動 / 削除 / 種別変更」をその場で
選べれば足りる。専用 triage UI はデータ分類ルールや保存先契約を増やす一方、既存 chip には
翻訳なし表示と per-tag 操作の文脈が揃っている。

caption テーブルは複数行を持てるが、現行 UI と export は最新の投影済み caption 文字列を扱う。
そのため移動時は呼び出し側で現在 caption とタグ文字列を結合し、保存 API には完成済みの
caption 文字列を渡す。

## Consequences

caption 側はまだ chip 化されていないため、今回の移動はタグから caption への片方向だけにする。
将来 caption 複数表示 UI が入った場合は、caption 側の per-item 操作として逆方向の移動を追加できる。
