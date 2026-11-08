---
type: ADR
title: 生成メタデータを登録時に読み取り、再取り込みと再解析では原データとアノテーションを保つ
status: Accepted
timestamp: 2026-11-08
tags: [generation-metadata, registration, reanalysis, cli]
---

# ADR 0106: 生成メタデータを登録時に読み取り、再取り込みと再解析では原データとアノテーションを保つ

## Context

ADR 0105 で、生成メタデータの parser と保存先 (原データ / 解析結果) を用意した。画像の登録経路は
GUI の worker、CLI / API、データセット取り込み、クロップと複数あるが、どれも
`ImageDatabaseManager.register_original_image` を通る (GUI worker と CLI / API は
`register_image_with_side_effects` 経由)。既に登録済みの画像には解析結果が無く、同じ画像の再取り込みや
parser の更新で、保存済みの原データとユーザーのタグ・キャプションを壊さない方針が要る。

## Decision

- **登録時の読み取りは `register_original_image` の 1 箇所で行う。** 新規 / 別版 / 重複の分類と保存が
  決まった後に、登録元のファイルから生成メタデータを読み取って保存する (`record_generation_metadata`)。
  GUI は既存の `DatabaseRegistrationWorker` の中で、CLI / API とデータセット取り込み・クロップも同じ処理で動く。
- **失敗しても登録を続ける。** 読み取り・復号の失敗は `failed` の解析結果として保存する。解析結果の保存で
  DB エラー (`SQLAlchemyError`) が起きたときは警告を出して登録結果を変えない (解析結果は未解析のまま)。
- **再取り込み (重複) は、未解析のときだけ解析する。** 既に解析結果がある画像では、原データも解析結果も
  変えない。機能追加前に登録された画像は、再取り込みのときに初めて解析される。
- **再解析は明示的な操作にする。** `lorairo-cli images analyze-metadata` で、保存済みの画像ファイル
  (`stored_image_path`) から読み直す。
  - 画像 ID を省くと、未解析の画像を ID 順に最大 `--limit` 件 (既定・上限 500) 処理し、残りの件数と
    `next_after_id` (処理した最大の画像 ID) を返す。ファイル欠落などで解析結果を作れなかった画像は未解析の
    まま残るため、`--after-id` に `next_after_id` を渡して先へ進める (失敗を解析結果として記録しない)。
  - 画像 ID を指定すると、その画像のうち未解析のものだけ処理する。`--force` で解析結果を置き換える
    (parser の版を上げたとき用)。
  - いずれの場合も、保存済みの原データは書き換えず、まだ無い取得元だけを足す (ADR 0105)。
  - ファイルが見つからない画像は `file_missing` として報告し、解析結果は変えない。
- **生成プロンプトをタグ・キャプションへ自動で反映しない。** 登録と再解析は、`Tag` / `Caption` に
  書き込まない。生成プロンプトを学習用のタグ・キャプションへ写す操作は、必要になったら別の明示的な操作として足す。
- **AI 生成の判定 (#1396) には `get_generation_evidence(image_id)` を渡す。** 戻り値は生成ツールと
  解析状態、判定の可否 (`is_ai_generated`、ADR 0105 と同じ条件)。未解析なら None。

## Consequences

- 登録 1 件あたり、画像ヘッダーの読み取りと 2 テーブルへの書き込みが増える (画像の展開はしない)。
- クロップ画像は Pillow で書き出し直すため生成情報を持たず、`no_metadata` になる。
- 再取り込みでファイル側の生成情報が変わっていても、解析済みなら古い結果のまま残る。置き換えるには
  `images analyze-metadata --force` を使う。
- GUI から再解析する入口は無い (CLI のみ)。必要になったら後続で足す。

## Related

- Issue #1482, #1481, #1396, #1398
- ADR 0105 (生成メタデータの保存), ADR 0061 (登録時の分類と副作用の統一)
