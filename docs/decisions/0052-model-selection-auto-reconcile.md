---
type: ADR
title: ModelSelectionWidget 初回表示時の model reconcile
status: Accepted
timestamp: 2026-06-01
tags: []
---
# ADR 0052: ModelSelectionWidget 初回表示時の model reconcile

## Context

Issue #598 の調査で、`image-annotator-lib` のモデル検出結果から外れた WebAPI モデルが、CLI の `models refresh` または GUI の手動「更新」ボタンを押すまで DB 上で有効(`available`)のまま残る問題が確認された。

既存の `ModelSyncService.sync_available_models()` と `reconcile_model_availability()` は正しく動作する。しかし、GUI 起動時にこれらを自動実行する経路が存在しなかった。

## Decision

コンテナ連携済み(container-backed)の `ModelSelectionWidget` を初回生成するタイミングで、既存のモデル更新ワーカーを非同期で 1 回だけ自動実行する。

- 自動実行はプロセス内で 1 回のみ行う。
- 自動同期が成功した後は、その時点で生存しているすべてのコンテナ連携済み `ModelSelectionWidget` を再読み込みする。
- 手動の「更新」ボタンは従来どおり維持する。
- 自動実行の成功および失敗はログへ記録し、モーダルダイアログは表示しない。
- 自動実行が失敗しても、ウィジェットの表示やアプリの起動は止めない。
- DB の再読み込みは既存の成功ハンドラ経由で行い、無効化(de-list)済みのモデルを表示から除外する。

## Consequences

複数の `ModelSelectionWidget` が生成されても二重同期を防げる。同期完了後は、各ウィジェットの表示も古い DB キャッシュから最新の状態へ更新される。

起動直後の初回ウィジェット表示では、短時間だけ更新中の進捗が表示される場合があるが、UI スレッドはブロックしない。なお、バージョン変更検知や永続的な同期履歴の管理は今回導入しない。
