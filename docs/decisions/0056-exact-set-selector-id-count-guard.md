# ADR 0056: exact-set selector の大量ID集合ガード / count-only 軽量化方針

- **日付**: 2026-06-05
- **ステータス**: Accepted
- **関連 Issue**: #624 (本 ADR), #612 / PR #623 (exact-set selector 導入)

## Context

ADR 0055 で `ImageFilterCriteria.image_ids` を exact-set selector として追加した
(PR #623)。Codex review (#623 round 3-4) で、**大量 ID 集合 / count-only API** に関する
2 点が hardening の余地として残った (#624)。

1. **metadata 取得ヘルパーの IN 一括構築**
   `_fetch_images_by_exact_ids` の存在チェックは `BATCH_CHUNK_SIZE` で分割するが、
   `_fetch_filtered_metadata` 経由の metadata 取得 (`_fetch_original_image_metadata` /
   `_fetch_processed_image_metadata`) は `Image.id.in_(image_ids)` を全 ID で一括構築する。
   理論上 SQLite のバインド変数上限超で `too many SQL variables` になり得る。これは
   exact-set 固有ではなく、`get_images_by_filter` の通常フィルタ経路でも共通の既存制約。

2. **`get_images_count_only` の image_ids exact-set が重い**
   count_only が `_fetch_images_by_exact_ids` に委譲し、件数だけ欲しいのに metadata +
   tags/captions/scores/ratings まで eager-load してから捨てている (count-only の
   「軽量」契約に反する)。

計画策定時の追加調査で、**`get_images_by_ids` (error workflow 用の別 ID 経路) も同じ
全 ID 一括 IN** を持つことが判明した (`db_manager.py` の未解決エラー全件 fetch から呼ばれる)。
exact-set selector ではないが同じバインド上限リスクを持つため、本 ADR で併せて扱う。

### 前提となる事実

- **実バインド上限は緩い**: 本プロジェクトの SQLite (3.40.1) の
  `SQLITE_LIMIT_VARIABLE_NUMBER` は **250,000**。Issue 本文が言及した「999」は旧 SQLite の
  既定値で、もはや当てはまらない。既存定数 `BaseRepository.BATCH_CHUNK_SIZE = 15000`
  (32,766 の約半分の安全マージン) はこの実上限に対してかなり保守的。
- **対象集合は構造的に有界**: GUI ステージングは `StagingWidget.MAX_STAGING_IMAGES = 500`
  で上限管理される。exact-set selector を使う経路 (GUI エクスポート / CLI / API の
  `export_with_criteria`) はいずれも明示集合で、現実の LoRA 学習データは数十枚オーダー。
- **ADR 0019 (Export Filter Required Design)**: LoRA 学習データ作成に「全件エクスポート」の
  正常ケースは存在しない。大量集合は防ぐべきエラー (21k 件事故, Issue #166)。「何枚でも
  無制限に出せる」方向の hardening は本プロジェクトの設計思想に逆行する。

## Decision

**exact-set selector (有界集合) には「数字ガード」(500) を、`get_images_by_ids` (非有界な
error 復旧集合) には「チャンク分割」を導入する。exact-set の metadata 取得ヘルパーの
チャンク分割は行わない。count-only の直接 COUNT 化も行わない (対象外とする)。**

> **改訂 (Codex review #625)**: 当初は `get_images_by_ids` も `BATCH_CHUNK_SIZE` で「ガード
> (ValueError)」する設計だった。しかしこの経路は error workflow の未解決エラー**全件**を
> 受け取る非有界集合であり、上限超で reject すると**エラー復旧パスが壊れる** (Codex P2 指摘)。
> 「集合が有界なら reject、非有界なら分割」という原則に従い、by_ids は**ガードでなく分割**に
> 改める。exact-set (有界 500) の数字ガード方針は不変。

### 1. 大量 ID 集合は数字ガードで弾く (課題①)

- `_fetch_images_by_exact_ids` の入口で `len(requested) > EXACT_SET_MAX_IDS` を検出したら
  `ValueError` を送出する。曖昧な SQLite `too many SQL variables` ではなく、明確な
  契約違反エラーとして早期に落とす。
- **ガード閾値はステージング上限と同じ 500** とする。exact-set selector はエクスポート
  集合 (ステージング由来) を表すため、`MAX_STAGING_IMAGES` (= 500) と同じ有界性を契約と
  して持たせるのが意味的に自然。バインド安全 (実上限 250,000) は副次的に満たされる。
- **GUI 定数を直接 import しない**: リポジトリ層は Qt-free (ADR 0001) のため、
  `StagingWidget.MAX_STAGING_IMAGES` を参照せず、リポジトリ層に定数
  `EXACT_SET_MAX_IDS = 500` を定義する (コメントで「= MAX_STAGING_IMAGES, ADR 0056」と
  相互参照)。両者の drift 防止のため、test で
  `EXACT_SET_MAX_IDS == StagingWidget.MAX_STAGING_IMAGES` を assert する (test は GUI を
  import してよい)。
- ガードにより `len(image_ids) <= 500 (< BATCH_CHUNK_SIZE)` が保証されるため、既存の
  存在チェック分割ループ (`for i in range(0, len(requested), BATCH_CHUNK_SIZE)`) は不要と
  なり、単一 IN 句に戻して簡素化できる。`_fetch_*_metadata` のチャンク化 (課題①の Issue
  提案) は実装しない。

### 1b. `get_images_by_ids` はチャンク分割する (関連経路, Codex #625)

- `get_images_by_ids` (`image.py`, error workflow 用の別 ID 経路) も全 ID を一括 IN で
  構築するため、同じバインド上限リスクを持つ。
- **この経路はエクスポート集合ではなく非有界**である。呼び出し元 (`db_manager.py` の
  error workflow) が **未解決アノテーションエラーの全件** (`get_error_image_ids()`) を
  そのまま渡す。上限超で `ValueError` を投げると、まさにエラーが大量にある時にエラー画像
  の閲覧・復旧パスが壊れる (Codex P2 指摘)。
- したがって reject ではなく **`BATCH_CHUNK_SIZE` でチャンク分割**し、各チャンクの結果を
  連結して返す。順序保証のない既存契約 (DB 取得順) を維持するため、連結順は呼び出し順の
  chunk 順となる。`find_image_ids_by_phashes` 等で既に使う標準パターンに合わせる。
- 「集合が有界なら reject (exact-set 500)、非有界なら分割 (by_ids)」が本 ADR の原則。
  exact-set の metadata ヘルパーを分割しないのは、それが 500 で有界だからであり、矛盾しない。

### 2. count-only は現状の委譲を維持する (課題②)

- `get_images_count_only(image_ids=...)` は引き続き `_fetch_images_by_exact_ids` の
  総件数を返す (B1)。`SELECT COUNT` への直接置換 (B2) は行わない。
- 受け入れ条件「`get_images_by_filter` の総件数と一致」は、同一 helper を共有する現状の
  委譲で構造的に満たされている。

## Rationale

### 課題① — A2 (数字ガード) を採用

| 選択肢 | 概要 | 採否 |
|--------|------|------|
| A1. 全経路をチャンク分割 (Issue 提案) | metadata 取得も `BATCH_CHUNK_SIZE` で分割 | 却下 |
| **A2. 数字ガード** | 上限超で `ValueError`、分割ループ削除 | **採用** |
| A3. 何もしない | 現状維持 | 却下 |

- A1 却下: 「何枚でも無制限に出せる」方向は **ADR 0019 (誤エクスポート防止) に逆行**。
  実バインド上限 250,000 に対しガードを **500** (ステージング上限と同値) に置くと、
  数十枚で回す現実の利用では分割が発火する条件に**永遠に到達しない**。コードを増やして
  到達不能な経路を守るのは YAGNI 違反。
- A2 採用: コードはむしろ**減る** (既存分割ループを単一 IN に簡素化)。SQLite の不明瞭な
  例外を明確な契約違反エラーに変換でき、ADR 0019 の「大量集合は防ぐべきエラー」思想とも
  整合する。
- A3 却下: 生の `too many SQL variables` が呼び出し側に漏れ、原因が分かりにくい。

### 課題② — B1 (現状維持) を採用

| 選択肢 | 概要 | 採否 |
|--------|------|------|
| **B1. 現状の委譲を維持** | helper の総件数を返す | **採用** |
| B2. 直接 COUNT クエリ | metadata を取らず `SELECT COUNT` | 却下 |

- B2 却下: 軽量化のために `_filter_by_resolution` (解像度該当版の選定ロジック) を素の SQL で
  再現する必要があり、特に `resolution != 0` で `get_images_by_filter` と**件数がズレる
  リスク**を持つ。これは受け入れ条件「総件数一致」が警告する罠そのもの。ガードで集合が
  有界 (≤ 数十枚) になった以上、B1 が抱える「annotation の無駄ロード」は無視できる規模で
  あり、B2 は「無視できる無駄を消すために件数ズレバグを埋め込む」割に合わない交換。
- B1 採用: ゼロコードで、同一 helper を共有するため `get_images_by_filter` との件数一致が
  構造的に保証される。将来プロファイリングで実害が確認された場合は、parallel COUNT では
  なく「annotation を eager-load しない軽量 ID 解決」への refactor を検討する (本 ADR では
  対象外)。

## Consequences

### 良い点

- ◎ exact-set selector のコードが**簡素化**される (存在チェック分割ループ削除 → 単一 IN)。
- ◎ 不明瞭な SQLite 例外を明確な `ValueError` 契約違反に変換。
- ◎ ADR 0019 (誤エクスポート防止) の「大量集合は防ぐべきエラー」思想と整合。
- ◎ count_only の件数一致が現状のまま構造的に保証される (件数ズレバグを導入しない)。
- ◎ `get_images_by_ids` は非有界な error 復旧集合をチャンク分割で安全に扱える。隠れた
  bind 上限クラッシュを除去しつつ、大量エラー時でも復旧パスを壊さない (Codex #625)。

### トレードオフ

- △ `len(image_ids) > 500` の exact-set 呼び出しは `ValueError` になる。呼び出し側でバッチ
  分割する責務が生じるが、現実の利用 (≤ 500 ステージング / 数十枚) では発生しない。CLI/API
  から 500 超の exact-set を投げる経路があれば、呼び出し側で分割するか上限を再検討する。
- △ 2 経路で異なる戦略を採る (exact-set=数字ガード500 / by_ids=チャンク分割)。「有界集合は
  reject・非有界集合は分割」という原則で統一されるが、なぜ違うのかを本 ADR で明示する。
- △ count_only の exact-set 経路は引き続き annotation を eager-load して捨てる。集合が
  有界なため実害は無視できる規模。

### 受け入れ条件への対応 (#624)

- [x] `_fetch_*_metadata` のチャンク化 → **不要と判断** (数字ガードで `<= 500` 保証)。
  代わりに `_fetch_images_by_exact_ids` 入口にガードを追加。
- [x] count_only の直接 COUNT 化 → **対象外** (B1 維持で総件数一致は既に成立)。
- [x] `_fetch_images_by_exact_ids`: `len > 500` で `ValueError` の回帰テストを追加。
- [x] `get_images_by_ids`: `BATCH_CHUNK_SIZE` 超を分割して全件返す回帰テストを追加
  (当初の「ValueError」案は Codex #625 でチャンク分割に改訂)。
- [x] `EXACT_SET_MAX_IDS == StagingWidget.MAX_STAGING_IMAGES` の drift 防止 assert を追加。

## Related

- ADR 0055: Workspace Export Target = Staging Set / Selection-Source Unification
  (exact-set selector 導入元)
- ADR 0019: Export Filter Required Design (大量集合は防ぐべきエラー、誤エクスポート防止)
- Issue #624 (本 ADR), #612 / PR #623, Codex review #623 (round 3-4)
- PR #625 / Codex review #625 (by_ids を guard→chunk に改訂した P2 指摘)
