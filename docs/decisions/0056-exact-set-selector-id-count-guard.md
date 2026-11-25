---
type: ADR
title: exact-set selector の大量ID集合ガード / count-only 軽量化方針
status: Accepted
timestamp: 2026-06-05
tags: []
---
# ADR 0056: exact-set selector の大量ID集合ガード / count-only 軽量化方針

- **関連 Issue**: #624 (本 ADR), #612 / PR #623 (exact-set selector 導入)

## Context

ADR 0055 において、`ImageFilterCriteria.image_ids` を exact-set selector として追加した(PR #623)。その後、Codex review(#623 round 3-4)において、**大量 ID 集合の扱いと count-only API** に関する以下の 2 点が堅牢化の余地として挙げられた(#624)。

1. **メタデータ取得ヘルパーでの `IN` 句一括構築**
   `_fetch_images_by_exact_ids` の存在チェックは `BATCH_CHUNK_SIZE` で分割している。しかし、`_fetch_filtered_metadata` 経由のメタデータ取得(`_fetch_original_image_metadata` および `_fetch_processed_image_metadata`)は、`Image.id.in_(image_ids)` を全 ID に対して一括構築している。理論上は SQLite のバインド変数上限を超過して `too many SQL variables` エラーが発生し得る。なお、これは exact-set 固有ではなく、`get_images_by_filter` の通常フィルタ経路にも共通する既存制約である。

2. **`get_images_count_only` の exact-set 経路の重さ**
   `get_images_count_only` は `_fetch_images_by_exact_ids` へ処理を委譲している。そのため、件数のみを取得したいにもかかわらず、メタデータに加えて tags・captions・scores・ratings まで eager-load してから破棄しており、count-only の「軽量」という契約に反している。

さらに計画策定時の追加調査で、**`get_images_by_ids`(エラー復旧ワークフロー用の別 ID 経路)も同様に全 ID を一括 `IN` で構築している**ことが判明した(`db_manager.py` の未解決エラー全件取得から呼び出される)。これは exact-set selector ではないものの同じバインド上限リスクを持つため、本 ADR で併せて方針を定める。

### 前提となる事実

- **実際のバインド上限は大きい**:本プロジェクトで使用している SQLite(3.40.1)の `SQLITE_LIMIT_VARIABLE_NUMBER` は **250,000** である。Issue 本文が言及した「999」は旧バージョンの既定値であり、現状には当てはまらない。既存定数 `BaseRepository.BATCH_CHUNK_SIZE = 15000`(32,766 の約半分の安全マージン)は、この実上限に対して十分に保守的である。
- **対象集合は構造的に有界である**:GUI のステージングは `StagingWidget.MAX_STAGING_IMAGES = 500` で上限管理されている。exact-set selector を使う経路(GUI エクスポート、CLI、API の `export_with_criteria`)はいずれも明示集合であり、実運用における LoRA 学習データは数十枚規模である。
- **ADR 0019(Export Filter Required Design)**:LoRA 学習データの作成に「全件エクスポート」という正常ケースは存在しない。大量集合のエクスポートは防ぐべきエラーである(21k 件事故、Issue #166)。「何枚でも無制限に出力できる」方向への堅牢化は、本プロジェクトの設計思想に逆行する。

## Decision

**有界集合である exact-set selector には「数値ガード(500)」を導入し、非有界なエラー復旧集合を扱う `get_images_by_ids` には「チャンク分割」を導入する。exact-set のメタデータ取得ヘルパーに対するチャンク分割および count-only の直接 `COUNT` 化は行わない(対象外とする)。**

> **改定(Codex review #625)**:当初は `get_images_by_ids` にも `BATCH_CHUNK_SIZE` によるガード(`ValueError` 送出)を設ける設計だった。しかし、この経路はエラー復旧ワークフローにおける未解決エラー**全件**を受け取る非有界集合であり、上限超過で拒否すると**エラー復旧パスそのものが壊れる**(Codex P2 指摘)。「集合が有界なら拒否、非有界なら分割」という原則に従い、`get_images_by_ids` は**ガードではなくチャンク分割**へ改めた。なお、exact-set(有界 500)に対する数値ガードの方針は変更しない。

### 1. 大量 ID 集合は数値ガードで弾く(課題①)

- `_fetch_images_by_exact_ids` の入口で `len(requested) > EXACT_SET_MAX_IDS` を検出した場合、`ValueError` を送出する。曖昧な SQLite の `too many SQL variables` ではなく、明確な契約違反エラーとして早期に失敗させる。
- **ガード閾値はステージング上限と同じ 500** とする。exact-set selector はステージング由来のエクスポート集合を表すため、`MAX_STAGING_IMAGES`(500)と同じ有界性を契約として持たせるのが意味的に自然である。これにより、バインド変数の安全性(実上限 250,000)も副次的に満たされる。
- **GUI 定数を直接 import しない**:リポジトリ層は Qt 非依存(ADR 0001)であるため、`StagingWidget.MAX_STAGING_IMAGES` を参照せず、リポジトリ層に定数 `EXACT_SET_MAX_IDS = 500` を定義する(コメントで「`= MAX_STAGING_IMAGES`, ADR 0056」と相互参照する)。両者の乖離を防ぐため、テストで `EXACT_SET_MAX_IDS == StagingWidget.MAX_STAGING_IMAGES` をアサートする(テスト側では GUI を import してよい)。
- このガードにより `len(image_ids) <= 500`(`BATCH_CHUNK_SIZE` 未満)が保証される。そのため、既存の存在チェック分割ループ(`for i in range(0, len(requested), BATCH_CHUNK_SIZE)`)は不要となり、単一の `IN` 句へ戻して簡素化できる。課題①の Issue で提案された `_fetch_*_metadata` のチャンク化は実装しない。

### 1b. `get_images_by_ids` はチャンク分割する(関連経路、Codex #625)

- `get_images_by_ids`(`image.py`、エラー復旧ワークフロー用の別 ID 経路)も全 ID を一括 `IN` で構築しており、同じバインド上限リスクを持つ。
- **この経路はエクスポート集合ではなく非有界**である。呼び出し元(`db_manager.py` のエラー復旧ワークフロー)は、**未解決アノテーションエラーの全件**(`get_error_image_ids()`)をそのまま渡す。上限超過で `ValueError` を送出すると、エラーが大量に発生した肝心の場面でエラー画像の閲覧・復旧パスが機能しなくなる(Codex P2 指摘)。
- したがって、拒否ではなく **`BATCH_CHUNK_SIZE` 単位でチャンク分割**し、各チャンクの結果を連結して返す。順序保証のない既存契約(DB 取得順)を維持するため、連結順は呼び出し順のチャンク順とする。これは `find_image_ids_by_phashes` などで既に採用している標準パターンに合わせる。
- 本 ADR の原則は「集合が有界なら拒否(exact-set は 500 上限)、非有界なら分割(`get_images_by_ids`)」である。exact-set のメタデータヘルパーを分割しないのは 500 件で有界だからであり、両者は矛盾しない。

### 2. count-only は現状の委譲を維持する(課題②)

- `get_images_count_only(image_ids=...)` は引き続き `_fetch_images_by_exact_ids` の総件数を返す(B1)。`SELECT COUNT` への直接置換(B2)は行わない。
- 受け入れ条件である「`get_images_by_filter` の総件数と一致すること」は、同一ヘルパーを共有する現状の委譲によって構造的に満たされている。

## Rationale

### 課題①:A2(数値ガード)を採用した理由

| 選択肢 | 概要 | 採否 |
|--------|------|------|
| A1. 全経路をチャンク分割(Issue 提案) | メタデータ取得も `BATCH_CHUNK_SIZE` で分割する | 却下 |
| **A2. 数値ガード** | 上限超過で `ValueError` を送出し、分割ループを削除する | **採用** |
| A3. 何もしない | 現状を維持する | 却下 |

- **A1 を却下した理由**:「何枚でも無制限に出力できる」方向への改修は **ADR 0019(誤エクスポート防止)に逆行する**。実バインド上限 250,000 に対してガードを **500**(ステージング上限と同値)に設定すると、数十枚単位で運用する現実のケースでは分割処理に到達しない。到達不能な経路を守るためにコードを増やすのは YAGNI に反する。
- **A2 を採用した理由**:既存の分割ループを単一 `IN` 句へ簡素化できるため、むしろコード量が減る。SQLite の分かりにくい例外を明確な契約違反エラーへ変換でき、ADR 0019 の「大量集合は防ぐべきエラー」という思想とも整合する。
- **A3 を却下した理由**:生の `too many SQL variables` 例外が呼び出し側へ漏れ、原因の特定が難しくなる。

### 課題②:B1(現状維持)を採用した理由

| 選択肢 | 概要 | 採否 |
|--------|------|------|
| **B1. 現状の委譲を維持** | ヘルパーの総件数を返す | **採用** |
| B2. 直接 `COUNT` クエリ | メタデータを取得せず `SELECT COUNT` を実行する | 却下 |

- **B2 を却下した理由**:軽量化のために `_filter_by_resolution`(解像度該当版の選定ロジック)を素の SQL で再現する必要があり、特に `resolution != 0` の条件で `get_images_by_filter` と**件数が食い違うリスク**が生じる。これは受け入れ条件「総件数一致」が警戒している不具合そのものである。数値ガードにより集合が有界(実運用では数十枚以下)になった以上、B1 が抱えるアノテーションの余分な読み込みは無視できる規模である。無視できる無駄を削るために件数ズレのバグを持ち込むのは割に合わない。
- **B1 を採用した理由**:追加コードが不要であり、同一ヘルパーを共有するため `get_images_by_filter` との件数一致が構造的に保証される。将来プロファイリングで実害が確認された場合は、並列の `COUNT` クエリではなく「アノテーションを eager-load しない軽量な ID 解決」へのリファクタリングを検討する(本 ADR の対象外)。

## Consequences

### 良い点

- exact-set selector のコードが**簡素化**される(存在チェックの分割ループを削除し、単一 `IN` 句へ戻せる)。
- 分かりにくい SQLite 例外を、明確な `ValueError` による契約違反エラーへ変換できる。
- ADR 0019(誤エクスポート防止)の「大量集合は防ぐべきエラー」という思想と整合する。
- `count_only` の件数一致が現状のまま構造的に保証され、件数ズレのバグを導入せずに済む。
- `get_images_by_ids` は非有界なエラー復旧集合をチャンク分割で安全に処理できる。潜在的なバインド上限クラッシュを除去しつつ、大量エラー発生時でも復旧パスを維持できる(Codex #625)。

### トレードオフ

- `len(image_ids) > 500` の exact-set 呼び出しは `ValueError` となる。呼び出し側でバッチ分割する責務が生じるが、現実の運用(ステージング上限 500 以下、通常は数十枚)では発生しない。将来 CLI や API から 500 件超の exact-set を渡す経路が必要になれば、呼び出し側での分割または上限の見直しを検討する。
- 2 つの経路で異なる戦略を採る(exact-set は 500 の数値ガード、`get_images_by_ids` はチャンク分割)。「有界集合は拒否、非有界集合は分割」という統一原則に基づく違いであり、その根拠を本 ADR に明記しておく。
- `count_only` の exact-set 経路では引き続きアノテーションを eager-load して破棄するが、集合が有界なため実害は無視できる規模にとどまる。

### 受け入れ条件への対応(#624)

- [x] `_fetch_*_metadata` のチャンク化 → **不要と判断**(数値ガードで `<= 500` を保証)。代わりに `_fetch_images_by_exact_ids` の入口へガードを追加。
- [x] `count_only` の直接 `COUNT` 化 → **対象外**(B1 維持により総件数一致はすでに成立)。
- [x] `_fetch_images_by_exact_ids`:`len > 500` で `ValueError` を送出する回帰テストを追加。
- [x] `get_images_by_ids`:`BATCH_CHUNK_SIZE` を超える件数を分割して全件返す回帰テストを追加(当初の `ValueError` 案は Codex #625 でチャンク分割へ改訂)。
- [x] `EXACT_SET_MAX_IDS == StagingWidget.MAX_STAGING_IMAGES` の乖離防止アサートを追加。

## Related

- ADR 0055: Workspace Export Target = Staging Set / Selection-Source Unification(exact-set selector の導入元)
- ADR 0019: Export Filter Required Design(大量集合は防ぐべきエラー、誤エクスポート防止)
- Issue #624(本 ADR), #612 / PR #623, Codex review #623(round 3-4)
- PR #625 / Codex review #625(`get_images_by_ids` をガードからチャンク分割へ改訂した P2 指摘)
