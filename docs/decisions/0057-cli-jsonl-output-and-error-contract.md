---
type: ADR
title: CLI Machine-Readable (JSONL) Output and Error Contract
status: Accepted (§2/§3/§4/§6 を ADR 0060 で amend)
timestamp: 2026-06-05
tags: []
---
# ADR 0057: CLI Machine-Readable (JSONL) Output and Error Contract

- **関連 Issue**: #634 (epic) / #636 / #637

## Context

`lorairo-cli` は Typer と Rich で実装された人間向けの CLI である。出力は `console.print` による色マークアップ付きの装飾テキスト、Rich Table、Progress バーで構成されており、構造化出力を返すのは `project list --format json` のみである。

エラー処理も各コマンドに `console.print("[red]Error:...]")` と `typer.Exit(...)` が散在しており、終了コード(`Exit(1)` と `Exit(2)`)の使い分けがコマンドごとに揺れている。装飾・進捗・エラーがすべて標準出力(stdout)へ混在しているため、AI エージェントや自動化スクリプトが出力を安定してパースできない。

一方、兄弟パッケージの `genai-tag-db-tools`(tag-db)では、エージェント向け CLI 契約がすでに確立されている。具体的には、stdout を JSONL、stderr をログへ分離し、安定したエラーコードによる構造化エラーとコマンドイントロスペクションを提供している。LoRAIro CLI にも同等の機械可読契約を定義し、人間向けの対話 UX を損なわずにエージェント駆動を可能にする。

本 ADR では、**機械可読出力が選択された経路における出力契約とエラー契約**を固定する。機械可読出力と人間向け Rich 出力を切り替える条件(トリガ)やエントリポイント方針(`lorairo` と `lorairo-cli` の二分、help / version の挙動)は **ADR 0058** で定義している(出力モードは明示的な `--json` フラグ、エントリポイントは 2 本分離を維持)。本 ADR はそれらの決定を前提として契約の中身を確定する。

## Scope / Non-Goals

本 ADR が固定するのは、CLI 機械可読出力の**決定事項と契約**である(stdout / stderr の分離、3 種類の `kind`、不変条件、500 枚上限、14 エラーコード集合とフラグ、終了コード、中央エラー境界の責務)。

以下の具体的な実装メカニズムは本 ADR では網羅せず、実装 Issue(#640、#641)および自動生成される `docs/cli.md`(ワイヤスキーマの SSoT)で確定する。

- Click / Typer の起動およびパースの細部
- 各 SDK・ライブラリ固有の例外形状(例:`google-genai` の `google.genai.errors.APIError` のステータスコード)の網羅的な分類
- 各コマンドの射影(projection)フィールド定義

なお、本 ADR 中の `classify_exception` などの記述は代表例であり、網羅的な実装仕様ではない。

## Decision

### 1. stdout は JSONL 専用、stderr はログ・進捗・装飾専用とする

stdout には機械可読な JSONL のみを出力し、1 行につき 1 つの有効な JSON オブジェクトとする。

- シリアライズは単一の `_emit` ヘルパーを経由し、`json.dumps(line, ensure_ascii=False, allow_nan=False, default=str)` を用いる。
  - `ensure_ascii=False` により日本語タグをそのまま保持する。
  - `default=str` は `Path` や `datetime` などの非自明な値に対するフォールバックとして機能する。
  - `allow_nan=False` により非有限の浮動小数点数を弾く。
- 非有限のスコアやメトリクス(`NaN`、`Infinity`)は標準 JSON で不正となるため、`_emit` は出力前に `None` へ正規化する。これにより、非有限値が混入しても stdout の JSON 妥当性を壊さない。
- **`kind` とエラー `code` は安定したワイヤ値を持たなければならない**。これらは `StrEnum`(または素の `str`)で定義し、`"INVALID_INPUT"` のような契約値へシリアライズされることを保証する。通常の `Enum` を `default=str` に委ねると `"ErrorCode.INVALID_INPUT"` のような不安定な値になり、`code` で分岐するエージェントが壊れるため禁止する。
- ログ(Loguru)、進捗バー(Rich Progress)、人間向けの装飾はすべて stderr へ出力する。stdout は機械契約専用とし、人間向けレンダリングと混在させない。

### 2. stdout の `kind` は `item`、`result`、`error` の 3 種類とする

```jsonc
// item — per-record 出力を持つコマンドの 1 レコード (N 行)。record を model_dump(mode="json") で展開。
//        list 系コマンドと、annotate の画像ごとアノテーション結果が該当。
{"kind": "item", ...}

// result — 集計の末尾 1 行。成功は ok:true、部分失敗は後述の契約で ok:false。
{"kind": "result", "ok": true, "message": "...", "processed": 480, "total": 480}

// error — 失敗時の末尾 1 行。
{"kind": "error", "ok": false, "code": "INVALID_INPUT", "message": "...",
 "retryable": false, "user_action_required": true, "hint": "...", "details": {...}}
```

- **`item` を出力するコマンド**:レコード単位の出力を持つコマンドが対象である。list 系コマンドに加え、`annotate run` では画像ごとに精査された `item`(phash、model、tags、score など)を 1 行ずつ出力する。一方、`export create` や `images update` のようにレコード単位の出力を持たないバッチ操作は `item` を出さず、最終の `result` のみを出力する。
- **進捗を表す `event` kind は採用しない**:`item` を流すコマンドでは出力された `item` 数がそのまま進捗を表し、`item` を持たないバッチ操作は最終の `result` で十分である。進捗表示は §1 のとおり stderr の人間向け Progress バーに限定する。
- **不変条件**:すべてのコマンド実行は、必ず 1 行の `result` または `error` で終了する。list 系コマンドは **`--fetch` 指定時のみ** `item` を N 行出力した後に件数サマリの `result` を 1 行出す。**既定(フラグなし)では `item` を出さず、`result`(件数)のみ**を出力する(ADR 0060:件数既定 / `--fetch` 明示)。

### 3. バッチ操作は 1 回あたり 500 枚のハードキャップを設ける(GUI ステージングと整合)

変更を伴うバッチ操作(`annotate run`、`export create`、および `images update` のタグ一括更新)は、1 回の呼び出しで処理できる対象を**最大 500 枚**に制限する。これは GUI の `StagingWidget` における最大 500 枚上限と挙動を揃えるためである。

選択結果が 500 枚を超える場合、**画像のデコードや処理を一切実行する前に** `RESULT_SET_TOO_LARGE` の `error` を返して拒否する(ADR 0060 で `INVALID_INPUT` から統一)。その際、`details` に超過情報を格納し、利用者へ絞り込みを促す。

```jsonc
{"kind": "error", "ok": false, "code": "RESULT_SET_TOO_LARGE",
 "message": "Selection exceeds per-run limit of 500 images (requested 720).",
 "retryable": false, "user_action_required": true,
 "hint": "Narrow the selection to 500 or fewer.",
 "details": {"limit": 500, "requested": 720}}
```

この上限は **§2 の `batch_size`(モデル処理のチャンクサイズ、すなわち同時にデコードする枚数)とは別概念**であり、「1 コマンドが処理する総数」を制限するものである。**500 枚を超えた場合の対処手段(recourse)は操作ごとに異なる**。

- **`annotate run`**:500 枚超は拒否するが、ADR 0053 の分割実行(シャーディング)を用いて 500 枚ずつ反復実行できる。ただし、**`--unrated` や `--missing-model` のような処理によって対象集合が縮むフィルタ(mutating フィルタ)**を使う場合、**`--offset` を加算してはならない**。最初の 500 件を処理すると対象集合が縮むため、`--offset 500` を指定すると未処理レコードを読み飛ばしてしまう。この場合は、**集合が空になるまで `--limit 500 --offset 0` を繰り返す**(縮んだ集合の先頭 500 件を毎回取得する)か、安定した **`--image-id` または ID 範囲**で分割する。`--offset` の加算が安全なのは、固定された ID 集合を反復する場合に限る。
- **`export create`**:分割による代替手段は設けない。エクスポートの JSON 成果物は `metadata.json` を上書き方式で生成するため、分割再実行によるページングやマージを行うと成果物が破損する。500 枚を超える場合はフィルタによる絞り込みで対応する。
- **`images update`(タグ一括更新)**:500 枚超は拒否する。代替手段は `annotate run` と同様である(DB 変更が画像ごとに冪等へ蓄積されるため、mutating フィルタでは `--limit 500 --offset 0` の反復、固定集合では `--image-id` または ID 範囲で分割する)。具体的なフラグ提供は #640 で確定する。

この 500 枚上限により、ADR 0053 の「1 回の呼び出しで総数無制限にアノテーションを実行できる」という前提を**改定**する。ADR 0053 の `batch_size` ストリーミング機構と分割実行機構そのものは維持し、前者は上限内でのメモリ境界として、後者は 500 枚を跨ぐ反復手段として活かす。

なお、参照・一覧系コマンド(`images list` など)も基本は 500 件で上限管理するが、**件数既定と `--fetch` 明示**という別の形式で実現する(ADR 0060)。変更系バッチの「処理前ハード拒否」とは異なり、参照・一覧系は既定で件数のみを返し、`--fetch` 時に総数が 500 件を超えていれば `RESULT_SET_TOO_LARGE` で弾いて絞り込みを促す。完全なページング契約(件数既定、`--fetch`、`limit` / `offset`、安定順序、DB プッシュダウン)は ADR 0049 および ADR 0060(#639)で定義する。

### 4. エラーコードセットは全 15 種類とする

tag-db と共有する安定コア 11 種類に、AI 推論ドメイン固有の 3 種類とページングドメインの 1 種類(ADR 0060)を加えた**全 15 種類**を定義する。各コードには `retryable` および `user_action_required` フラグを付与し、エージェントは `message` 文字列をパースせず、これらのフラグで分岐判断を行う。

共有コア 11 種類のフラグ意味は tag-db ADR 0003 の対応表を正本とし、以下の表に全コードを明示する。

| コード | 区分 | retryable | user_action | 主因とエージェントの反応 |
|---|---|---|---|---|
| `INVALID_INPUT` | 共有 | false | true | 引数や選択が不正 → 入力を修正する |
| `VALIDATION_FAILED` | 共有 | false | true | 検証失敗 → 入力を修正する |
| `PRECONDITION_FAILED` | 共有 | false | true | 前提条件の未達 → 先行操作を実行する |
| `NOT_FOUND` | 共有 | false | true | 対象が存在しない → 指定を見直す |
| `ALREADY_EXISTS` | 共有 | false | true | 既存との衝突 → 別名または既存リソースを使う |
| `CONFLICT` | 共有 | false | true | 状態の衝突 → 衝突を解消して再実行する |
| `IO_ERROR` | 共有 | false | false | ファイル I/O 失敗 |
| `NETWORK_ERROR` | 共有 | true | false | 一時的なネットワーク障害 → 再試行する |
| `DB_ERROR` | 共有 | false | false | DB 操作失敗 |
| `TIMEOUT` | 共有 | true | false | タイムアウト → 再試行する |
| `INTERNAL_ERROR` | 共有 | false | false | 想定外の内部エラー |
| `RESOURCE_EXHAUSTED` | 拡張 | true | true | OOM → `batch_size` を下げてから再試行する(同一条件での再実行は再失敗する) |
| `AUTH_ERROR` | 拡張 | false | true | API キーの未設定または無効 → キーを設定する |
| `RATE_LIMITED` | 拡張 | true | false | プロバイダの 429 応答 → バックオフ後に再試行する(`details.retry_after` を参照) |
| `RESULT_SET_TOO_LARGE` | 拡張(ADR 0060) | false | true | 結果が 500 件上限を超過 → 検索条件を追加して絞り込む |

`retryable=true` かつ `user_action_required=true` の組み合わせは、「再試行は可能だが、入力や設定を変更してから実行する必要がある」ことを意味する(例:`RESOURCE_EXHAUSTED` は `batch_size` を下げてから再試行する必要があり、同一条件のまま再実行すると再び失敗する)。

**同一条件のまま再実行して成功し得るのは、`user_action_required=false` かつ `retryable=true` のコード(`NETWORK_ERROR`、`TIMEOUT`、およびバックオフ後の `RATE_LIMITED`)のみ**である。エージェントはこの 2 フラグの組み合わせによって「そのまま再試行」と「条件を調整してから再試行」を区別する。

### 5. `classify_exception` による例外からエラーコードへの分類

送出された例外をエラーコードへ分類する関数 `classify_exception` を新設し、以下の 2 つの技法を採用する。

- **原因チェーンの走査(cause-chain walking)**:`__cause__` と `__context__` を遡り、`raise X from e` でラップされた真因を取得する。LoRAIro では `image-annotator-lib` の例外を `typer.Exit` で包むなど多層ラップが多いため必須となる。
- **モジュール接頭辞による判定(module-prefix matching)**:例外クラスをモジュール名で判定し、分類のために `torch` や推論 SDK を先行インポート(eager import)しない。LoRAIro はこれらを遅延インポート(lazy import)化しており(ADR 0010 系)、先行インポートは起動コスト増やメモリ枯渇を招くためである。

代表的な分類例は以下のとおりである。

- `ImageLoadMemoryError`、`image-annotator-lib` の `OutOfMemoryError`、`RuntimeError("...out of memory...")` → `RESOURCE_EXHAUSTED`
- LoRAIro 独自の `APIKeyNotConfiguredError`(`src/lorairo/api/exceptions.py`、OpenAI / Claude / Google で送出)および `anthropic.` / `openai.` / `google.` 系 SDK の `AuthenticationError` → `AUTH_ERROR`
- 同 SDK の `RateLimitError` → `RATE_LIMITED`

LoRAIro はプロバイダ SDK に到達する前の段階で独自に `APIKeyNotConfiguredError` を送出する経路を持つ。そのため、SDK の `AuthenticationError` だけでなく、この独自例外も明示的に `AUTH_ERROR` へ分類する。これを怠ると、キー未設定が汎用的な実行時エラーへ落ちてしまい、エージェントが「キーを設定する」という対処方針を受け取れなくなる。

### 6. 終了コード方針(0 / 2 / 1)

| exit | 意味 | 該当コード |
|---|---|---|
| 0 | 成功 | — |
| 2 | 入力・検証エラー | `INVALID_INPUT`, `VALIDATION_FAILED`, `RESULT_SET_TOO_LARGE`(ADR 0060) |
| 1 | 実行時エラー | 上記以外すべて |

例外に対する終了コードは、エラーコードから機械的に導出する。これは Click の usage error の既定値が終了コード 2 であることと整合する。また、`RESULT_SET_TOO_LARGE` は入力(選択や検索条件が広すぎる)を修正すべきエラーであるため終了コード 2 を割り当てる(従来 `INVALID_INPUT` が担っていた上限違反の終了コードを維持、ADR 0060)。

### 7. 中央集権のエラー境界

各コマンドに散在している `except ...` から `console.print` および `Exit(...)` を行う処理を撤廃し、エラー処理を `cli.main:main` の 1 箇所へ集約する。

- Typer / Click アプリは `standalone_mode=False` で呼び出す(または同等のラッパーを挟む)。既定の `standalone_mode=True` では Click が独自に usage error を表示してインタプリタを終了させるため、中央境界が**バイパス**され、stdout に終端 `error` 行が出力されなくなる。
- Click の usage error(`UsageError`、`BadParameter`)は `INVALID_INPUT` の `error` 行を出力し、終了コード 2 で終了する。
- それ以外の例外は `classify_exception` で分類し、`error` 行を出力したうえで §6 の対応表に従い終了する。
- トレースバックは `INTERNAL_ERROR` の場合に限り stderr へ出力し、stdout の JSONL 純度を維持する。
- 各コマンド本体は型付きの例外を送出・伝播するのみとし、エラー整形ロジックを持たない。
- 機械可読(JSONL)と人間向け(Rich)の出力モード分岐も、この中央境界の 1 箇所のみで行う。

## Rationale

- **stdout の純度**:機械可読契約の根幹である。装飾・進捗・エラーが stdout に混在するとパース不能になる。stderr を人間向け表示とログの経路へ分離することで、同一コマンドを人間とエージェントの双方から利用できるようになる。
- **`event` kind を持たない理由**:`annotate` は `item` をストリーム出力するため、出力された件数自体が進捗となる。`export` はバッチ操作であり機械的な途中経過を必要としない。進捗バーは人間向けとして価値があるため stderr に残す。tag-db の「JSONL が読みにくいならフォーマットではなくコマンドが情報を出しすぎている」という設計哲学を継承し、各コマンドは精査された射影のみを出力する。
- **500 枚のハードキャップ**:GUI のステージング上限(最大 500 枚)と挙動を統一し、すべてのバッチ操作(`annotate`、`export`、`images update`)の 1 コマンドあたり処理総数を 500 枚に揃える。`batch_size`(モデル処理チャンク)とは別概念である。処理前に弾くことで副作用ゼロのまま早期失敗(fail fast)できる。`annotate` は ADR 0053 の分割実行(`--limit`、`--offset`、`--image-id`)で 500 枚ずつ反復できるため実害がない。`export` は `metadata.json` 上書き方式のため安全な分割ができないが、実運用で 1 回の学習データセットが 500 枚を超えるケースは稀である。本 ADR は ADR 0053 の「無制限実行」前提のみを改定し、ストリーミングと分割実行の機構は維持する。
- **14 コード設計の根拠**:tag-db と 11 種類を共有することでエージェントの学習コストを下げる。拡張 3 種類は、エージェントの反応が一意に異なるケース(OOM はバッチ縮小後の再試行、認証はキー設定、レート制限はバックオフ)のみに限定した。`MODEL_ERROR` のような総称は中身が `NETWORK_ERROR`、`NOT_FOUND`、`VALIDATION_FAILED` に分解でき、総称化するとかえって機械的な反応が難しくなるため採用しない。
- **モジュール接頭辞判定と原因チェーン走査**:LoRAIro は推論 SDK や `torch` を遅延インポート化しているため、分類時の先行インポートを避ける必要がある。また、多層ラップされた例外から真因を特定するには原因チェーンの遡及が不可欠である。
- **中央集権のエラー境界**:各コマンドに散在する `except` が終了コードの揺れを引き起こしていた。1 箇所へ集約することで契約を機械的に保証でき、コマンド本体も薄く保てる。
- **終了コード 0 / 2 / 1**:Click の usage error の既定値が 2 であるため、「2 は入力問題」とする設計が自然であり、tag-db とも整合する。

## Consequences

- 各コマンドの出力を「人間向けレンダリング(stderr / TTY)」と「機械向け辞書出力(stdout JSONL)」へ分離するリファクタリングが全コマンドで必要になる(実装は別タスク)。
- 各コマンドに散在していたエラーハンドリングを撤廃して中央境界へ移行する破壊的変更となる。終了コードの意味が従来から反転する(従来の `Exit(2)`=想定外から、本 ADR では 2=入力・検証エラー)ため、既存の呼び出し側スクリプトに影響し得る。
- 14 コードを扱う `classify_exception` および `ErrorInfo` モジュールを新設する。
- 500 枚上限により、500 枚を超える一括操作はできなくなる。利用者は条件の絞り込みまたは反復呼び出しで対応する。
- 広範な `except Exception` はコーディング規約で原則禁止されているが、例外をエラー行へ変換する CLI 中央境界の 1 箇所に限り本 ADR で許可する。
- 契約の SSoT は**コード**に置く。`kind` とエラー `code` は `StrEnum`、各ペイロードは `api.*` の Pydantic 型(ADR 0037)として定義する。新設する `docs/cli.md` はそれらから生成または参照するドキュメントとし、ワイヤスキーマを二重定義しない(イントロスペクションの `describe` も同じ型から生成する)。
- `annotate` の 1 回あたり処理総数が 500 枚に制限され、ADR 0053 の無制限実行の前提が改定される。500 枚を超えるアノテーションは、`--limit`、`--offset`、`--image-id` で分割して反復実行する運用となる。

## Amendment (2026-06-06, ADR 0060 / #639)

ADR 0060(CLI Bounded Pagination and Count-First Contract)により、本 ADR は以下のとおり改定された(適用済み)。

- **§2 list 系の `item` 契約**:「list 系は `item` を N 行出力し、終端 `result` を出す」という記述を、「既定(フラグなし)では `item` を出さず `result`(件数)のみを返し、`--fetch` 指定時に `item` を N 行出力して終端 `result` を出す」へ具体化した。
- **§3 上限超過コード**:変更系バッチ(`annotate`、`export`、`images update`)の 500 枚超過時のエラーコードを、`INVALID_INPUT` から `RESULT_SET_TOO_LARGE` へ統一した。代替手段(分割実行など)は変更しない。
- **§3 read / list 系の扱い**:参照・一覧系も基本 500 件で上限管理するが、件数既定と `--fetch` 明示によって実現することを明記した。
- **§4 エラーコード**:`RESULT_SET_TOO_LARGE`(拡張、`retryable=false`、`user_action_required=true`)を追加し、全 15 種類とした。
- **§6 終了コード**:`RESULT_SET_TOO_LARGE` を終了コード 2(入力・検証エラー)へ割り当てた。

## 関連

- ADR 0020(CLI Message Language Policy)— JSONL モードにおけるメッセージ言語方針と整合
- ADR 0037(api Facade Wiring Policy)— 契約の SSoT は `api.*` の Pydantic 型とし、CLI は薄いラッパーとする
- ADR 0049(Apply CLI Image List Limit in the Repository Query)— read / list 系のページング機構
- ADR 0060(CLI Bounded Pagination and Count-First Contract)— read / list 系の有界ページング契約を確定し、本 ADR の §2 / §3 / §4 / §6 を改定(`RESULT_SET_TOO_LARGE` 追加、上限コード統一、件数既定)
- ADR 0053(CLI Streaming Annotation Memory-Bounded Contract)— 本 ADR が「1 回の呼び出しで総数無制限」の前提を 500 枚上限で改定(ストリーミングおよび分割実行機構は維持)。`RESOURCE_EXHAUSTED` とストリーミング方針も整合
- ADR 0058(CLI Output Mode Trigger and Entry-Point Policy)— 出力モードのトリガ(`--json`)とエントリ方針を供給(本 ADR の前提)
- tag-db ADR 0003(CLI JSONL Output & Error Contract)— 移植元の参照契約
- tag-db ADR 0005(CLI Command Introspection)— 後続のイントロスペクション契約(別 ADR)

## 2026-09-06 追補: 集計結果と部分失敗 (#1313)

`images register`、`annotate import-batch`、`batch import`、`errors resolve` の集計完了時には、成功件数を保持するため `kind=result` を使用する。

- `status=success` は `ok=true`、終了コード 0 とする。
- `partial_success` と `failed` は `ok=false` とする。2026-11-03 の追補により、部分成功は終了コード 3、全件失敗は終了コード 1 とする。
- 正常スキップと空集合は `success`、成功または正常スキップを含む失敗は `partial_success`、それ以外の失敗は `failed` と判定する。
- レガシー形式の未一致・パースエラー・保存エラー、および Batch の未完了取込みも失敗として扱う。
- Batch の空結果はジョブ完了と同義ではないため、`job_imported` を別途確認する。
- 集計を返せない例外については、既存の `kind=error` 契約を維持する。`result` の後に `error` を重ねず、終端 1 行の不変条件を守る。
- 既存の件数フィールドは維持しつつ、失敗対象と理由を追加する。従来の部分失敗における終了コード 0 へ依存しているスクリプトは移行が必要である。

詳細と調査用フィールドについては、[CLIの部分失敗契約](../cli.md#部分失敗と既存スクリプトの移行-1313) を参照すること。

## 2026-11-03 追補: 部分成功専用の終了コード

部分成功を専用の終了コード `3` として区別する。成功は `0`、全件失敗および実行時例外は `1`、入力・検証失敗は `2` を維持する。JSONL の既存フィールドと正常スキップの扱いは変更しない。

対象は登録、画像更新・処理、アノテーション・取込み、Batch 送信・取込み、エラー解決、エクスポート・予行、レビューである。旧形式の画像更新では `failed_tags` と終了コードを併用する。また、終了コードだけを見て成功済みや送信済みの対象を全件再送してはならない。
