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

`uv.lock` が固定していた Pillow 12.2.0 に対して、Dependabot から13件のセキュリティ
アラートが報告された。LoRAIro はローカルデスクトップアプリであり、指摘対象 API の
多くは使用していない。一方で、ファイル内容から形式を判別する `Image.open()` を通じて
到達し得る画像デコーダーのサービス拒否や範囲外読み取りも含まれている。

## Decision

Pillow 12.3.0 を `uv.lock` の正準バージョンとする。Pillow 12.3.0 は対象13件すべての
修正を含むため、アラートを個別に却下せず依存更新で解消する。

torch のアラートはこの決定に含めない。torch は利用環境に応じて利用者が配布元から
`uv pip install` する運用であり、該当する `torch.jit.script` もLoRAIroでは使用しない。

## Rationale

デスクトップ用途を理由に全アラートを却下する方法より、互換性のある修正版へ更新する方が、
外部由来データセットを扱う際のローカルDoSリスクを低い保守コストで除去できる。
全依存を更新する `uv sync -U` はtorchを含む環境依存パッケージまで動かすため採用せず、
`uv lock --upgrade-package pillow` で変更範囲を限定する。

## Consequences

- `uv.lock` を利用する環境ではPillow 12.3.0が再現される。
- Pillow 12.3.0の互換性は画像登録・変換・アノテーション経路のテストで確認する。
- torch の環境別インストール運用は変更しない。
- DependabotのPillowアラートは本変更のdefault branch反映後にfixedとして閉じる。
