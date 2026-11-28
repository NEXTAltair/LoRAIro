---
type: ADR
title: プロジェクトを横断した画像の検索・コピーと由来の記録
status: Accepted
timestamp: 2026-11-28
tags: [project, database, migration, dataset, provenance, cli]
---

# ADR 0112: プロジェクトを横断した画像の検索・コピーと由来の記録

## Context

プロジェクトは画像 DB(SQLite)と `image_dataset/` を 1 つのディレクトリに持ち、DB ごとに画像 ID・モデル ID が独立している。別のプロジェクトにある画像を探して再利用し、複数プロジェクトの画像を組み合わせてデータセットの版を作りたいという要求がある(Issue #1661)。

再利用の方式には次の 2 案があった。

- **参照**: 取り込み先の DB に「別 DB の画像 ID」を持たせ、ファイルと注釈はコピー元を読む
- **コピー**: 画像ファイルと注釈を取り込み先に複製し、コピー元は由来として記録だけする

参照方式は、DB をまたぐ整合性(コピー元の移動・削除・schema の更新)を取り込み先が保証できず、検索・書き出し・GUI の全経路に「別 DB の行」を扱う分岐が要る。プロジェクトの統合(Issue #1660)も、最終的にはコピー元の行を取り込み先へ移す処理になる。

## Decision

### 1. コピーで再利用し、DB をまたぐ参照は作らない

別プロジェクトの画像はコピーで取り込む。複製するのは、画像ファイル、処理済み画像(行とファイル)、タグ・キャプション・スコア・スコアラベル・レーティング、生成メタデータ(解析結果と原データ)とする。コピーした画像には新しい uuid を振り、コピー元のプロジェクト名・画像 ID・uuid を由来として記録する。

DB をまたぐ外部キーや参照は作らない。コピー元のその後の変更・削除には追従しない。

複製しないもの: エラー記録、ファイル名エイリアス、クロップの親子関係、Provider Batch の記録、レビュー結果、データセット(版の取り込みは #1660 の範囲)。

### 2. 由来と操作の記録を 3 つの表で持つ

Alembic migration `c1d2e3f4a5b6` で次の表を追加する。

- `project_transfer_runs`: 取り込み 1 回分(コピー元 1 プロジェクトにつき 1 行)。種類(`copy_images` / `merge_project`)、コピー元のプロジェクト名とディレクトリ、複製した枚数と由来だけ足した枚数を持つ
- `image_origins`: 画像ごとの由来。`(image_id, source_project_name, source_image_uuid)` で一意。1 画像に複数の由来を持てる
- `dataset_version_origins`: 版ごとの由来(コピー元のプロジェクト・データセット名・版 ID・版名)。本 ADR の時点では書き込まず、#1660 で使う

注釈の行ごとの由来表は作らない。注釈の出所は従来どおり `model_id`(AI モデル・擬似モデル)で表す。

由来のコピー元はプロジェクト名(`.lorairo-project` メタデータの `name`)で識別する。プロジェクトの格納先(`lorairo_data/`)の中で `name` が一意であることを前提にする。コピー元の検索(`source_project_name` + `source_image_uuid` / `source_version_id`)と、取り込みの記録ごとの参照(`transfer_run_id`)のために、両方の由来表に index を付ける。

### 3. 同じ画像は複製せず、由来を足して注釈を和集合にする

取り込み先に同じ画像があるかは、ADR 0061 の分類(pHash 完全一致の候補を属性で比べる `classify_phash_candidate`)で判定する。DUPLICATE なら画像を複製せず、既存の画像に由来を足し、注釈を次の規則で和集合にする。同じ実行の中で先に複製した画像も候補に含める。

- タグ: `(モデル, タグ)` が既にあれば既存の行を優先する
- キャプション・スコア・スコアラベル・レーティング: 値と `created_at` が一致する行があれば足さない(スコアは手動編集かどうかも比べる)。コピーする行の `created_at` / `updated_at` はコピー元から引き継ぐため、同じ値でも別の時点の記録(例: 2 → 8 → 2 の履歴)は残り、最新の `created_at` で現在の値を選ぶ処理の結果は変わらない。同じコピーを繰り返しても行は増えない
- 生成メタデータ: 解析結果は取り込み先に無いときだけ、原データは無い `(種類, キー)` だけ足す
- モデルは `litellm_model_id` で対応付け、取り込み先に無ければコピー元の値で作る
- タグの `tag_id`(外部タグ DB の ID)は、取り込み先で同じタグ文字列に付いている値を使い、無ければ NULL にする。コピー元の `tag_id` はユーザー DB の ID を含み得るため持ち込まない

同じ由来が既に記録されている画像(再実行)は、由来を重ねず、足りない注釈だけを足す。

### 4. コピー元は読み取り専用で開き、変更しない

コピー元・検索対象の DB は `create_project_session_factory(path, read_only=True)` で開く。schema が head でない DB は開かず、`ReadOnlyPreconditionError`(理由 `schema_upgrade_required`)で `project prepare` 等による更新を案内する。コピー元の DB と画像ファイルは書き換えない(ファイルは読むだけ)。

### 5. 取り込み先は 1 セッション 1 commit、ファイルは staging から移す

取り込み先への書き込みは 1 つのセッションで行い、最後に 1 回だけ commit する。ファイルは取り込み先の `image_dataset/.transfer_staging/` にコピーしてから最終パスへ移し、その後に commit する。途中で例外が起きたら rollback し、移したファイルと作ったディレクトリ、staging を削除する。計画(`--dry-run` / `--confirm` なし)は同じ判定をセッション内で行ってから rollback し、ファイルを一切書かない。

### 6. 複数プロジェクト由来の画像から版を作る

`DatasetVersionBuildService` は、プロジェクト内の画像(コピーした画像を含む)から 1 フォルダの版を作る。学習テキスト(`.txt`)は、採用中(`rejected_at IS NULL`)のタグを登録順・重複なしで `", "` で連結する(書き出しと同じ書式)。版は Kohya 取り込みと同じく作業中として作り、書き終えてから確定し、`KOHYA_DATASET` のタグを最新版へ同期する(ADR 0104)。失敗したら版を削除する。版の画像ごとの由来は `image_origins` から読んで示す。

### 7. CLI

- `images search-projects --projects A,B | --all-projects --query ...`: 読み取り専用の横断検索。結果にプロジェクト・画像 ID・既存の由来を出す
- `images copy IMAGE_IDS --from-project SRC -p DST [--dry-run | --confirm]`: `--confirm` が無ければ計画だけを出す
- `images origins IMAGE_IDS -p DST`: 画像の由来
- `dataset build-version -p DST --dataset D --version V --folder <repeats>_<name> --image-ids ... [--trigger W] [--parent-version ID] [--dry-run | --confirm]`
- `dataset origins VERSION_ID -p DST`: 版の画像・学習テキスト・由来

### 8. プロジェクトの統合(#1660)で再利用する

#1660 のプロジェクト統合は、`ProjectTransferService.stage_images`(取り込み先のセッションに画像・注釈・由来を足すだけで commit しない処理)と、staging → 最終パス → 1 commit の方式をそのまま使う。統合では `project_transfer_runs.kind = 'merge_project'` を記録し、取り込んだ版の由来を `dataset_version_origins` に書く。

## Constraints

- コピー元の DB は schema が head であること(古い DB は開かない)
- 取り込み先とコピー元が同じプロジェクトのときは実行しない
- 1 回に指定できる画像 ID は CLI の上限(500)まで

## Consequences

- 画像ファイルと注釈が取り込み先に複製されるため、ディスク使用量は増えるが、コピー元の移動・削除の影響を受けない
- コピー元で後から付けた注釈は自動では反映されない。再実行すると足りない注釈だけを足す
- 由来はプロジェクト名で記録するため、コピー元のプロジェクト名を変えると同じ画像でも別の由来として扱う
- 取り込み先で `tag_id` が NULL のタグが増えることがある(Kohya 取り込みのタグと同じ扱い)

## Related

- ADR 0061(pHash 候補の属性比較による重複判定)
- ADR 0098(作業中の版)
- ADR 0104(学習テキストのタグ同期)
- Issue #1661、Issue #1660
