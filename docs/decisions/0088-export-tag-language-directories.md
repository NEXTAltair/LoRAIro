---
type: ADR
title: Export tag language directories for Kohya-compatible datasets
status: Accepted
timestamp: 2026-07-09
tags: [dataset-export, tag-translation, kohya]
---
# ADR 0088: Export tag language directories for Kohya-compatible datasets

## Context

タグ翻訳を学習 export に反映するとき、複数言語を同じ `.txt` に混ぜると Kohya/sd-scripts
からは「複数の語彙を同時に持つ 1 つの caption」として扱われる。これは「言語ごとに使える
dataset を出す」目的と異なり、trigger やタグ語彙の重みを混線させる。

Kohya の通常 dataset は画像と同名 stem の `.txt` sidecar を読むため、`img001.ja.txt` の
ような複数 extension 同居も利用側の `caption_extension` 切り替えを要求する。

## Decision

タグ言語が 1 つだけ指定された場合は、従来と同じ export root に画像と sidecar を出力する。
`canonical` は既存の tag format/canonical 出力を表す。

複数言語が指定された場合は、言語ごとに export root 直下へ完全な dataset ディレクトリを作る。

```text
export_dir/
  canonical/
    img001.webp
    img001.txt
  ja/
    img001.webp
    img001.txt
```

翻訳タグは export overlay と tag format 変換後のタグ列を入力にし、指定言語の主訳があるタグだけ
置換する。主訳が無いタグは canonical タグへ fallback する。

## Rationale

言語別ディレクトリなら各ディレクトリをそのまま Kohya に渡せる。画像コピーは増えるが、
初期実装では利用時の明快さを優先する。ディスク節約は将来 copy/hardlink/symlink の export
ポリシーとして追加できる。

## Consequences

TXT export と JSON metadata export は同じ tag language contract を使う。CLI の `export create`
は txt と json を続けて生成するため、複数言語時は各言語ディレクトリに `.txt` と `metadata.json`
が並ぶ。

GUI で複数言語選択 UI を追加する場合も、この service contract へ `tag_languages` を渡す。
