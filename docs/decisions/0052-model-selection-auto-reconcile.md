---
type: ADR
title: ModelSelectionWidget 初回表示時の model reconcile
status: Accepted
timestamp: 2026-06-01
tags: []
---
# ADR 0052: ModelSelectionWidget 初回表示時の model reconcile

## Context

Issue #598: image-annotator-lib の discovery から外れた WebAPI モデルは
`models refresh` または GUI の手動「更新」まで DB 上で available のまま残る。
既存の `ModelSyncService.sync_available_models()` と
`reconcile_model_availability()` は正しく動くが、GUI 起動時の自動実行経路がない。

## Decision

`ModelSelectionWidget` の container-backed 初回生成時に、既存のモデル refresh worker を
非同期で 1 回だけ自動実行する。

- 自動実行はプロセス内 1 回だけにする。
- 自動 sync 成功後は、その時点で生存している container-backed `ModelSelectionWidget` をすべて
  再読込する。
- 手動「更新」ボタンは従来どおり維持する。
- 自動実行の成功/失敗はログに記録し、モーダルダイアログは表示しない。
- 自動実行の失敗はウィジェット表示やアプリ起動を止めない。
- DB 再読込は既存の成功ハンドラ経由で行い、de-list 済みモデルを表示から落とす。

## Consequences

複数の `ModelSelectionWidget` が生成されても二重 sync は避けられ、sync 後は各 widget の表示も
stale な DB キャッシュから更新される。起動直後の初回 widget 表示では短時間だけ refresh
progress が表示される可能性があるが、UI スレッドはブロックしない。version-change 検知や永続的な
sync 履歴は今回導入しない。