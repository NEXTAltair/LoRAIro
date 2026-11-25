---
type: ADR
title: ステージング集合の SSoT を StagingStateManager へ hoist
status: Accepted
timestamp: 2026-06-22
tags: [gui, state, staging]
---
# ADR 0074: ステージング集合の SSoT を StagingStateManager へ hoist

- **関連 Issue**: #867(epic: MainWindow 分解)、#876(本 ADR および実装)
- **改訂対象 ADR**: 0041(Provider Batch 実行 UI 統一)、0055(workspace / export target / staging 統一)
- **関連 ADR**: 0036(GUI Compound Widget 分割方針)

## Context

ステージング集合(送信・エクスポート・トリアージの共通対象集合)は、これまで `StagingWidget` が `OrderedDict` として所有していた。`StagingWidget` は `.ui` 上で `BatchTagAddWidget` と `ProviderBatchJobWidget` の 2 箇所に配置されており、`connect_shared_staging` が 2 つのインスタンス間で `OrderedDict` の実体を双方向同期する暫定処理によって状態を共有していた。さらに、`MainWindow` の `_on_staged_images_changed` が Search、Export、Results、Jobs、Annotate パイプラインの広範囲へ変更通知を分配している。

Epic #867 で各タブを専用ウィジェット(`gui/tab/XxxTabWidget`)へ分離すると、「1 つのタブ(Annotate)が所有する SSoT を他の 4 タブが内部参照する」という所有関係の逆転が発生する。この構造は、ADR 0041 が「ステージング責務は `StagingWidget` に委譲する」と定めた境界に起因している。

## Decision

ステージング集合の SSoT を `StagingWidget` から `gui/state/StagingStateManager`(`QObject`)へ引き上げる(hoist)。これはタブ抽出(#868 以降)の前提工事として先行実施する。

1. **`StagingStateManager` の新設**: `OrderedDict`(`{image_id: (filename, stored_path)}`)を保持し、追加・削除・クリア・取得の各操作と、`staged_images_changed` および `staging_cleared` シグナルを提供する。メタデータ解決のため `DatasetStateManager` を注入する。
2. **`StagingWidget` をビューへ降格**: 単体利用に備えて既定のマネージャを持ちつつ、`set_staging_state_manager()` で共有マネージャへ差し替えられるようにする。公開 API(`add_image_ids`、`clear`、`get_staged_items` 等)はマネージャへ委譲し、`staged_images_changed` と `staging_cleared` はマネージャのシグナルを再送出(再 emit)して既存利用者の契約を維持する。`connect_shared_staging` は廃止する。
3. **単一マネージャの共有**: `MainWindow` が単一の `StagingStateManager` を生成し、`BatchTagAddWidget` と `ProviderBatchJobWidget` の双方へ注入する。これにより両ビューが同一マネージャを共有して自動同期する。
4. **通知分配元の一本化**: `MainWindow` は `staging_state_manager` のシグナルにのみ後続の通知分配を接続する。各タブウィジェットのシグナル経由による二重発火を防ぐためである。
5. **`thumbnail_cache`(`QPixmap`)はビュー側で保持**: GUI 描画リソースはマネージャに持たせず、各 `StagingWidget` がローカルに保持・再描画する。マネージャは純粋なデータのみを管理する。

## Rationale

- **所有逆転の解消**: SSoT を中立な状態管理層へ移すことで、以降のタブ抽出(#868 / #870 / #872 / #874)ではマネージャを DI で受け取って購読するだけで済むようになり、タブ間の直接参照が消える。
- **双方向同期処理の撤廃**: `connect_shared_staging` による複雑な双方向同期を、「同一マネージャを共有する」という単純な構造へ置き換えられる。
- **既存契約の互換性維持**: `StagingWidget` の公開 API とシグナルを温存したため、`MainWindow`、Export、Results などの既存利用者側の変更を最小限に抑えられる。
- **`gui/state/` の既存設計との整合**: `DatasetStateManager` や `PaginationStateManager` と同様に、`QObject` とシグナルによる共有状態として統一的に配置できる。

## ADR 0041 / 0055 への影響

- **ADR 0041**: 「ステージング責務は `StagingWidget` に委譲」という定義を、「SSoT は `StagingStateManager`、`StagingWidget` はビュー」と再定義する。`StagingWidget` が 2 タブ共通コンポーネントである点や、統一フロー(ステージング → モデル選択 → 実行)は変わらない。
- **ADR 0055**: workspace、export target、staging の統一対象の所在を `StagingStateManager`(SSoT)へ更新する。3 者が同一集合を指すという統一の意図は変わらない。

両 ADR は本 ADR によって一部改訂され、責務の所在のみが更新される(ステータスは Accepted のまま維持する)。

## Consequences

- タブ抽出を DI 購読で素直に進められるようになり、Epic #867 の後続サブ Issue が簡素化される。
- `StagingWidget` を既定マネージャで単体使用するケースは従来どおり動作する。
- 将来的に `thumbnail_cache` の共有最適化が必要になった場合は別途検討する(現状はビューごとに再描画する)。
