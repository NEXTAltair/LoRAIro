---
type: ADR
title: Annotator Config Management
status: Superseded by ADR 0021 (partial — WebAPI セクションのみ)
timestamp: 2025-11-15
superseded_by: ["0021"]
tags: []
---
# ADR 0003: Annotator Config Management

## Context

PydanticAI の統合完了後、97 件の古い `*ApiAnnotator` クラス参照が `annotator_config.toml` に残存していた。レガシーコードの整理にあわせて、設定管理方式を見直す必要があった。また、起動時に毎回 API からモデル一覧を取得すると処理が重くなるという制約があった。

## Decision

**全モデル明示的管理方式(アプローチ4)**を採用する。

- `annotator_config.toml` で全モデルを明示的に管理する。
- API から取得したモデル情報は `available_api_models.toml` にキャッシュする。
- `deprecated_on` フィールドで廃止モデルを追跡する。
- `last_seen` フィールドで最終確認日時を記録する。

## Rationale

検討した代替案と却下理由は次のとおりである。

- **完全自動検出(却下)**: 起動時の処理が重くなり、API への依存も高まる。
- **ハイブリッド(却下)**: 2 系統の管理が併存し、複雑性が増す。
- **プラグインシステム(却下)**: YAGNI 原則に照らし、現時点では不要である。

起動時の重い API 取得を避けるパフォーマンス要件と、廃止履歴を保持する追跡可能性のバランスを重視して本案を採用した。

## Consequences

- 通常起動時はローカルキャッシュを利用するため高速に動作する。
- 初回起動時または強制更新時は、`force_refresh=True` を指定して API から全モデル情報を取得する。
- 廃止モデルは設定から削除せず、`deprecated_on` によって履歴を保持する。
- 旧 `*ApiAnnotator` クラス(4 ファイル、2,581 行)を完全に削除した(PydanticAI で全機能を代替済み)。

## 補足: ADR 0021 による部分的 supersede (2026-04-28)

WebAPI モデル管理については、[ADR 0021](0021-litellm-driven-model-registry.md) によって LiteLLM 駆動の動的解決へ移行した。約 11 ヶ月の運用で `available_api_models.toml` の追従が破綻し、`deprecated_on` フィルタも未実装のまま放置されたためである。

**ローカル ML モデル(ONNX、Transformers、CLIP)の管理に関する本 ADR の決定は引き続き有効である。** WebAPI セクションのみが ADR 0021 に置き換わる。
