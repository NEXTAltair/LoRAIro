---
type: ADR
title: 推移的依存のセキュリティ更新と環境別 torch 境界
status: Accepted
timestamp: 2026-07-22
tags:
  - dependencies
  - security
  - pyasn1
  - setuptools
  - torch
---
# ADR 0090: 推移的依存のセキュリティ更新と環境別 torch 境界

## Context

Dependabot から、以下の推移的依存(transitive 依存)に関するセキュリティアラートが報告された。

- **pyasn1 0.6.3(2 件)**: `google-auth` から参照される。信頼できない ASN.1 入力の処理時に発生する計算量 DoS であり、0.6.4 で修正されている。
- **setuptools 81.0.0(1 件)**: tensorflow と torch から参照される。macOS で sdist を作成・公開する際の Unicode 正規化差による `MANIFEST.in` の除外漏れであり、83.0.0 で修正されている。

しかし、現在のロックファイルへ setuptools 83.0.0 を強制すると、uv の依存解決器は torch 2.12.1 と torchvision 0.27.1 も同時に更新してしまう。LoRAIro における torch は、利用者が OS・GPU・CUDA に適合する公式配布物を `uv pip install` で導入する環境別運用であり、通常のロックファイル更新でバージョンを決定しない。

## Decision

- pyasn1 のみを 0.6.4 へ更新する。
- setuptools は 81.0.0 を維持する。該当アラートについては、脆弱な sdist 公開経路を LoRAIro が使用しないこと、および修正を強制すると torch の環境別導入境界を越えることを記録したうえで、`not_used` として却下する。

## Rationale

pyasn1 は単独で更新でき、`google-auth` および `google-genai` 経路での互換性リスクも小さい。そのため修正版を採用する。

一方、setuptools の更新のために torch まで一括変更すると、Dependabot アラートの解消範囲を超えて利用者の実行環境選択へ影響する。実行時に到達しない sdist 専用の問題に対して、その変更は正当化できない。

## Consequences

- `uv.lock` では pyasn1 0.6.4 を正準バージョンとする。
- torch 2.12.1+cu132、torchvision 0.27.1+cu132、および setuptools 81.0.0 を維持する。
- pyasn1 の 2 件のアラートは修正版反映として閉じる。
- setuptools の 1 件のアラートは、適用外である理由と環境別 torch 制約をコメントしたうえで閉じる。
- 将来、環境別手順で torch を更新した際に、setuptools 83.0.0 以上へ自然に解決できるかを再評価する。
