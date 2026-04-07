# ADR 0003: Annotator Config Management

- **日付**: 2025-11-15
- **ステータス**: Accepted

## Context

PydanticAI 統合完了後、97 件の古い `*ApiAnnotator` クラス参照が `annotator_config.toml` に残存。レガシーコード整理に伴い設定管理方式を見直す必要があった。起動時に毎回 API からモデルリストを取得すると重いという制約あり。

## Decision

**全モデル明示的管理方式（アプローチ4）**を採用:
- `annotator_config.toml` で全モデルを明示管理
- API から取得した情報を `available_api_models.toml` にキャッシュ
- `deprecated_on` フィールドで廃止モデルを追跡
- `last_seen` フィールドで最終確認日時を記録

## Rationale

- **完全自動検出（却下）**: 起動が重い、API 依存
- **ハイブリッド（却下）**: 2系統管理の複雑性
- **プラグインシステム（却下）**: YAGNI 原則、現時点で不要

パフォーマンス重視（起動時の重い API 取得を回避）とトレーサビリティ（廃止履歴保持）のバランスで採用。

## Consequences

- 通常起動: ローカルキャッシュ使用（高速）
- 初回/強制更新: `force_refresh=True` で API から全取得
- 廃止モデルは削除せず `deprecated_on` で履歴保持
- 旧 `*ApiAnnotator` クラス 4 ファイル 2581 行を完全削除（PydanticAI で全機能カバー済み）
