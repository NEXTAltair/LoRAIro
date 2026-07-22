---
type: ADR
title: transitive依存のセキュリティ更新と環境別torch境界
status: Accepted
timestamp: 2026-07-22
tags:
  - dependencies
  - security
  - pyasn1
  - setuptools
  - torch
---
# ADR 0090: transitive依存のセキュリティ更新と環境別torch境界

## Context

Dependabotは、`google-auth`から参照されるpyasn1 0.6.3に2件、tensorflowとtorchから
参照されるsetuptools 81.0.0に1件のアラートを報告した。pyasn1の問題は未信頼ASN.1入力の
処理時に発生する計算量DoSで、0.6.4に修正がある。setuptoolsの問題はmacOSでsdistを
作成・公開する際のUnicode正規化差による`MANIFEST.in`除外漏れで、83.0.0に修正がある。

一方、setuptools 83.0.0を現在のlockへ強制すると、uv resolverはtorch 2.12.1と
torchvision 0.27.1も更新する。LoRAIroのtorchは、利用者がOS・GPU・CUDAに合う公式配布物を
`uv pip install`する環境別導入であり、一般的なlock更新でバージョンを決めない。

## Decision

pyasn1のみを0.6.4へ更新する。setuptoolsは81.0.0を維持し、当該アラートは脆弱なsdist公開
経路をLoRAIroが使用しないこと、修正を強制するとtorchの環境別導入境界を越えることを
記録して`not_used`で却下する。

## Rationale

pyasn1は独立して更新でき、google-auth/google-genai経路の互換性リスクも小さいため、修正版を
採用する。setuptoolsのためにtorchまで一括更新する方法は、Dependabotアラートの解消範囲を
超えて利用者の実行環境選択へ影響する。実行時に到達しないsdist専用問題について、その変更を
正当化できない。

## Consequences

- `uv.lock`ではpyasn1 0.6.4を正準とする。
- torch 2.12.1+cu132、torchvision 0.27.1+cu132、setuptools 81.0.0は維持する。
- pyasn1の2件は修正版反映として閉じる。
- setuptoolsの1件は適用外理由と環境別torch制約をコメントして閉じる。
- 将来torchを環境別手順で更新した際、setuptools 83.0.0以上へ自然に解決できるか再評価する。
