---
type: ADR
title: ステージング集合の SSoT を StagingStateManager へ hoist
status: Accepted
timestamp: 2026-06-22
tags: [gui, state, staging]
---
# ADR 0074: ステージング集合の SSoT を StagingStateManager へ hoist

- **関連 Issue**: #867 (epic: MainWindow 分解), #876 (本 ADR / 実装)
- **改訂対象 ADR**: 0041 (Provider Batch 実行 UI 統一), 0055 (workspace / export target / staging 統一)
- **関連 ADR**: 0036 (GUI Compound Widget 分割方針)

## Context

ステージング集合 (送信・エクスポート・トリアージの共通対象集合) は `StagingWidget`
(`BatchTagAddWidget` と `ProviderBatchJobWidget` の 2 箇所に `.ui` promote) が
OrderedDict として所有し、`connect_shared_staging` が 2 つの `StagingWidget` 間で
OrderedDict 実体を双方向 sync する hack で共有していた。MainWindow の
`_on_staged_images_changed` が Search / Export / Results / Jobs / Annotate-pipeline へ
巨大 fan-out している。

Epic #867 で各タブを専用ウィジェット (`gui/tab/XxxTabWidget`) へ切り出すと、
「1 タブ (Annotate) が所有する SSoT を他 4 タブが reach-in する」**所有逆転**が生じる。
これは ADR 0041 が「ステージング責務は `StagingWidget` に委譲」と定めた境界に起因する。

## Decision

ステージング集合の SSoT を `StagingWidget` から **`gui/state/StagingStateManager` (QObject)**
へ hoist する。タブ抽出 (#868 以降) の前提工事として先行実施する。

1. **`StagingStateManager`**: OrderedDict `{image_id: (filename, stored_path)}` を保持し、
   add / remove / clear / get と `staged_images_changed` / `staging_cleared` Signal を提供する。
   メタデータ解決のため `DatasetStateManager` を注入する。
2. **`StagingWidget` は view へ降格**: 自前で既定 manager を持ちつつ、
   `set_staging_state_manager()` で共有 manager に差し替える。公開 API
   (`add_image_ids` / `clear` / `get_staged_items` 等) は manager へ委譲し、
   `staged_images_changed` / `staging_cleared` は manager のシグナルを **再 emit** して
   既存消費者の契約を維持する。`connect_shared_staging` は廃止する。
3. **共有**: MainWindow が単一の `StagingStateManager` を生成し、`BatchTagAddWidget` と
   `ProviderBatchJobWidget` の双方へ注入する。両 view が同一 manager を共有して自動同期する。
4. **fan-out 元を manager に一本化**: MainWindow は `staging_state_manager` のシグナルにのみ
   fan-out を接続し、各タブ widget のシグナルでの二重発火を避ける。
5. **`thumbnail_cache` (QPixmap) は view 保持**: GUI 描画リソースは manager に持たせず、
   各 `StagingWidget` がローカルに保持・再描画する。manager は純データのみを持つ。

## Rationale

- **所有逆転の解消**: SSoT を中立な state へ移すことで、以降のタブ抽出 (#868/#870/#872/#874)
  は manager を DI 購読するだけで済み、タブ間の reach-in が消える。
- **`connect_shared_staging` hack の除去**: 双方向 sync の代わりに「同一 manager 共有」という
  単純な構造になる。
- **互換性維持**: `StagingWidget` の公開 API とシグナルを温存したため、消費者
  (MainWindow / Export / Results 等) の変更を最小化できる。
- **`gui/state/` の既存パターンに整合**: `DatasetStateManager` / `PaginationStateManager` と
  同様、QObject + Signal の共有状態として配置する。

## ADR 0041 / 0055 への影響

- **ADR 0041**: 「ステージング責務は `StagingWidget` に委譲」→ **SSoT は `StagingStateManager`、
  `StagingWidget` は view** と再定義する。`StagingWidget` が 2 タブ共通コンポーネントである点、
  統一フロー (ステージング → モデル選択 → 実行) は不変。
- **ADR 0055**: workspace / export target / staging の統一対象の所在を `StagingStateManager`
  (SSoT) に更新する。統一の意図 (3 者が同一集合を指す) は不変。

両 ADR は本 ADR で **一部改訂** され、責務の所在のみ更新される (Status は Accepted のまま)。

## Consequences

- タブ抽出が DI 購読で素直になる (Epic #867 の以降のサブ Issue を簡素化)。
- `StagingWidget` 標準単体使用 (既定 manager) は従来どおり動作する。
- 将来、`thumbnail_cache` の共有最適化が必要になれば別途検討する (現状は view ごと再描画)。
