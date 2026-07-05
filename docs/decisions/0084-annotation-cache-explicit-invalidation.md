---
type: ADR
title: GUI アノテーションキャッシュの明示無効化 (再読込操作 + 対象指定 API)
status: Accepted
timestamp: 2026-07-05
tags: [gui, dataset-state, annotation-cache, cli-interop, invalidation, wal]
---
# ADR 0084: GUI アノテーションキャッシュの明示無効化 (再読込操作 + 対象指定 API)

- **関連 Issue**: #1171 (CLI の DB 書き込みがプレビュー再表示で反映されない), #1169 (クロス OS ロック調査), #965 (検索時アノテーション遅延ロード), #980 (アノテーションのみ再取得)
- **関連 ADR**: 0067 (SQLite Concurrency: busy_timeout / §4 手動リロード方針), 0042 (WAL 選定)

## Context

`DatasetStateManager` は検索結果を `include_annotations=False` で保持し、サムネイル選択時に
`_ensure_annotations_loaded` が対象 1 件だけアノテーションを遅延ロードする (#965)。ロード済みか
どうかはキャッシュ dict の `"tags"` キー有無をセンチネルとして判定し、一度ロードした画像は
検索で dict が再構築されるまで DB へ再照会しない。

このため、CLI (エージェント) が同じ DB へタグを書き込んでも、GUI で当該画像を再選択して
プレビューを再表示しただけでは反映されない (#1171)。ADR 0067 §4 は「外部更新の自動検知は
非目標、手動の再検索/再読み込みに留める」と定めており、自動反映は方針外。

なお `.db` ファイルの mtime を無効化トリガーに使う案は、**WAL では書き込みが `-wal` に入り
checkpoint まで `.db` 本体の mtime が変わらない** (Windows 実機で確認済み) ため機能しない。

## Decision

**明示リロード + 対象指定無効化 API を基礎にする。**

1. `DatasetStateManager.invalidate_annotations(image_ids)` を追加する。
   - キャッシュ dict からアノテーションキー (`tags` / `tags_text` / `captions` /
     `caption_text` / `scores` / `score_value` / `score_labels` / `ratings` /
     `quality_summary`) を落として `"tags"` センチネルを外し、`_ensure_annotations_loaded`
     の遅延ロードを再武装する。#965 の再選択最適化 (毎選択の DB 往復回避) は維持する。
   - 現在表示中の画像が対象に含まれる場合は `refresh_image_annotations` (#980) で即時
     DB 再取得し、`current_image_data_changed` を再発行して表示を更新する。
2. GUI に明示的な再読込操作を追加する。選択画像詳細ペイン (`SelectedImageDetailsWidget`)
   の「DBから再読込」ボタンが `invalidate_annotations([current_image_id])` を呼ぶ。
3. 自動検知 (mtime 監視 / ポーリング / focus 復帰時の一括無効化) は導入しない。
   ADR 0067 §4 の手動リロード方針を維持し、必要になれば別 Issue で判断する。

## Consequences

- CLI 書き込み後、ユーザー (または実機確認手順) は「DBから再読込」ボタンで対象画像の
  最新アノテーションを取得できる。検索全体の再実行 (再検索) も従来どおり全キャッシュを
  再構築する。
- 無効化はキー削除のみで安価。無効化後の次回選択は #965 の遅延ロード経路をそのまま通る。
- `.db` mtime ベースの自動無効化は WAL と両立しないため、将来も採用しない (本 ADR が根拠)。

## Related

- Issue #1171 / #1169 / #965 / #980
- ADR 0067 §4 (手動リロード), ADR 0042 (WAL)
