---
type: ADR
title: GUI アノテーションキャッシュの明示無効化 (再読込操作 + 対象指定 API)
status: Accepted
timestamp: 2026-07-05
tags: [gui, dataset-state, annotation-cache, cli-interop, invalidation, wal]
---
# ADR 0084: GUI アノテーションキャッシュの明示無効化 (再読込操作 + 対象指定 API)

- **関連 Issue**: #1171(CLI の DB 書き込みがプレビュー再表示で反映されない)、#1169(クロス OS ロック調査)、#965(検索時アノテーション遅延ロード)、#980(アノテーションのみ再取得)
- **関連 ADR**: 0067(SQLite Concurrency: `busy_timeout` および §4 手動リロード方針)、0042(WAL 選定)

## Context

`DatasetStateManager` は検索結果を `include_annotations=False` で保持し、サムネイル選択時に `_ensure_annotations_loaded` が対象 1 件だけアノテーションを遅延ロードする(#965)。ロード済みかどうかの判定にはキャッシュ辞書内の `"tags"` キーの有無をセンチネルとして使っている。そのため、一度ロードした画像は、再検索によってキャッシュ辞書が再構築されるまで DB へ再照会されない。

この仕組みにより、CLI(エージェント)が同じ DB へタグを書き込んでも、GUI 側でその画像を再選択してプレビューを開き直しただけでは変更が反映されない(#1171)。なお、ADR 0067 §4 は「外部更新の自動検知は非目標とし、手動の再検索または再読み込みにとどめる」と定めており、自動反映は方針外である。

また、`.db` ファイルの更新時刻(mtime)を無効化トリガーに使う案も検討したが、採用できない。WAL モードでは書き込みが `-wal` ファイルに入り、チェックポイントが走るまで `.db` 本体の更新時刻が変わらないためである(Windows 実機で確認済み)。

## Decision

**明示的な再読込操作と、対象を指定してキャッシュを無効化する API を基礎とする。**

1. **`DatasetStateManager.invalidate_annotations(image_ids)` を追加する**
   - キャッシュ辞書からアノテーション関連キー(`tags`、`tags_text`、`captions`、`caption_text`、`scores`、`score_value`、`score_labels`、`ratings`、`quality_summary`)を削除する。これにより `"tags"` センチネルを外し、`_ensure_annotations_loaded` による遅延ロードを再び有効化する。#965 の再選択最適化(選択ごとの DB 往復回避)はそのまま維持する。
   - 現在表示中の画像が対象に含まれる場合は、`refresh_image_annotations`(#980)で即時に DB から再取得し、`current_image_data_changed` を再発行して表示を更新する。
2. **GUI に明示的な再読込操作を追加する**
   - 選択画像詳細ペイン(`SelectedImageDetailsWidget`)に「DBから再読込」ボタンを配置し、押下時に `invalidate_annotations([current_image_id])` を呼び出す。
3. **自動検知は導入しない**
   - 更新時刻監視、ポーリング、ウィンドウフォーカス復帰時の一括無効化などは導入しない。ADR 0067 §4 の手動リロード方針を維持し、必要になった場合は別 Issue で改めて判断する。

## Consequences

- CLI からの書き込み後に、ユーザーまたは実機確認手順は「DBから再読込」ボタンで対象画像の最新アノテーションを取得できる。再検索による全キャッシュ再構築も従来どおり機能する。
- 無効化処理は辞書キーの削除のみで負荷が小さい。無効化後の次回選択では #965 の遅延ロード経路をそのまま再利用できる。
- `.db` の更新時刻に基づく自動無効化は WAL モードと両立しないため、将来も採用しない(本 ADR をその根拠とする)。

## Related

- Issue #1171 / #1169 / #965 / #980
- ADR 0067 §4(手動リロード)、ADR 0042(WAL)
