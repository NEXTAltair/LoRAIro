---
type: ADR
title: Pillow セキュリティ修正版を uv.lock の正準バージョンとする
status: Accepted
timestamp: 2026-07-22
tags:
  - dependencies
  - security
  - pillow
---
# ADR 0089: Pillow セキュリティ修正版を uv.lock の正準バージョンとする

## Context

`uv.lock` に固定していた Pillow 12.2.0 に対して、Dependabot から 13 件のセキュリティアラートが報告された。

LoRAIro はローカルデスクトップアプリケーションであり、指摘対象 API の多くは使用していない。しかし、ファイル内容から形式を判別する `Image.open()` を通じて到達し得る画像デコーダーのサービス拒否(DoS)や範囲外読み取りも含まれている。

## Decision

- Pillow 12.3.0 を `uv.lock` の正準バージョンとする。Pillow 12.3.0 は対象 13 件すべての修正を含むため、アラートを個別に却下せず依存更新によって解消する。
- torch に関するアラートは本決定の対象外とする。torch は利用環境に応じて利用者が配布元から `uv pip install` で導入する運用であり、該当する `torch.jit.script` も LoRAIro では使用していない。

## Rationale

デスクトップ用途であることを理由に全アラートを却下するよりも、互換性のある修正版へ更新する方が、外部由来データセットを扱う際のローカル DoS リスクを低い保守コストで除去できる。

全依存を一括更新する `uv sync -U` は torch を含む環境依存パッケージまで動かしてしまうため採用しない。変更範囲を限定するため、`uv lock --upgrade-package pillow` を用いる。

## Consequences

- `uv.lock` を利用する環境では Pillow 12.3.0 が再現される。
- Pillow 12.3.0 の互換性は、画像登録・変換・アノテーション経路のテストで確認する。
- torch の環境別インストール運用は変更しない。
- Dependabot の Pillow アラートは、本変更をデフォルトブランチへ反映した後に修正済み(fixed)として閉じる。
