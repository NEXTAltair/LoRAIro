# ADR 0057: CLI Machine-Readable (JSONL) Output and Error Contract

- **日付**: 2026-06-05
- **ステータス**: Proposed
- **関連 Issue**: #634 (epic) / #636 / #637

## Context

`lorairo-cli` は Typer + rich で実装された人間向け CLI である。出力は `console.print` による
色マークアップ付きの装飾テキスト、Rich Table、Progress バーで構成され、唯一 `project list --format json`
のみが構造化出力を返す。エラーは各コマンドに `console.print("[red]Error:...]")` + `typer.Exit(...)` が
散在し、exit code の使い分け (`Exit(1)` / `Exit(2)`) がコマンドごとに揺れている。装飾・進捗・エラーが
すべて stdout に混在しており、AI エージェントや自動化スクリプトが出力をパースできない。

sibling package の `genai-tag-db-tools` (tag-db) は agent-friendly CLI 契約 (stdout=JSONL / stderr=logs、
安定エラーコードによる構造化 error、コマンド introspection) を確立済みで、AI エージェントが安定して駆動
できる CLI を実現している。LoRAIro CLI にも同等の機械可読契約を定義し、人間向け対話 UX を損なわずに
エージェント駆動を可能にする。

本 ADR は **「機械可読出力が選択された経路」の出力契約とエラー契約**を固定する。どの条件で機械可読出力と
人間向け rich 出力を切り替えるか (トリガ) およびエントリポイント方針 (`lorairo` / `lorairo-cli` の二分、
help/version 挙動) は **ADR 0058** で定義する (出力モード = 明示 `--json` フラグ、entry は 2 本分離維持)。
本 ADR はそれらの決定を前提に、契約の中身を確定する。

## Decision

### 1. stdout = JSONL 専用 / stderr = ログ・進捗・装飾

stdout には機械可読 JSONL のみを出力する。1 行 = 1 つの valid JSON object。シリアライズは単一の
`_emit` ヘルパーを経由し `json.dumps(line, ensure_ascii=False, default=str)` で行う
(`ensure_ascii=False` で日本語タグを保持、`default=str` は `Path` / `datetime` 等の非自明な値のフォールバック)。

**`kind` とエラー `code` は安定した wire 値を持たねばならない**。これらは `StrEnum` (または素の `str`) で
定義し、`"INVALID_INPUT"` のような契約値にシリアライズされることを保証する。通常の `Enum` を `default=str`
に頼ると `"ErrorCode.INVALID_INPUT"` のような不安定値になり、`code` で分岐するエージェントが壊れるため禁止する。

ログ (loguru)、進捗バー (rich Progress)、人間向け装飾はすべて stderr に出す。stdout は機械契約専用とし、
人間向けレンダリングと混在させない。

### 2. stdout の kind は 3 種: `item` / `result` / `error`

```jsonc
// item — per-record 出力を持つコマンドの 1 レコード (N 行)。record を model_dump(mode="json") で展開。
//        list 系コマンドと、annotate の画像ごとアノテーション結果が該当。
{"kind": "item", ...}

// result — 成功時の末尾 1 行。ok:true + message + 件数メタ。
{"kind": "result", "ok": true, "message": "...", "processed": 480, "total": 480}

// error — 失敗時の末尾 1 行。
{"kind": "error", "ok": false, "code": "INVALID_INPUT", "message": "...",
 "retryable": false, "user_action_required": true, "hint": "...", "details": {...}}
```

- **`item` を出すコマンド**: per-record の出力を持つもの。list 系コマンドに加え、`annotate run` は画像ごとに
  curated な `item` (phash / model / tags / score 等) を 1 行ずつ流す。`export create` / `images update` の
  ような per-record 出力を持たないバッチ操作は `item` を出さず最終 `result` のみ。
- **進捗を表す `event` kind は採用しない**。`item` を流すコマンドは item 数が進捗を表し、`item` を持たない
  バッチ操作は最終 `result` で足りる。進捗は §1 のとおり stderr の人間向け Progress バーに限定する。
- **不変条件**: コマンド実行は必ず 1 行の `result` または `error` で終わる。list 系は `item` を N 行
  流した後に件数サマリの `result` を 1 行出す。

### 3. バッチ操作は 1 回 500 枚ハードキャップ (GUI staging と整合)

変更を伴うバッチ操作 (`annotate run` / `export create` / `images update` のタグ一括) は、1 回の呼び出しで
処理対象を **最大 500 枚** に制限する。GUI の StagingWidget が最大 500 枚キャップである挙動に合わせる。

選択結果が 500 枚を超える場合、**画像 decode / 処理を一切行う前に** `INVALID_INPUT` の `error` で弾く。
`details` に超過情報を載せ、利用者に絞り込みを促す。

```jsonc
{"kind": "error", "ok": false, "code": "INVALID_INPUT",
 "message": "Selection exceeds per-run limit of 500 images (requested 720).",
 "retryable": false, "user_action_required": true,
 "hint": "Narrow the selection to 500 or fewer.",
 "details": {"limit": 500, "requested": 720}}
```

この上限は **§2 の `batch_size` (モデル処理 chunk = 同時に decode する枚数) とは別概念**で、「1 コマンドが
処理する総数」を制限する。**500 超のときの recourse は操作で分かれる**:

- `annotate run`: 500 超は弾くが、ADR 0053 の `--limit` / `--offset` / `--image-id` sharding で 500 ずつ
  反復実行できる。annotation 結果は画像ごとに DB へ蓄積されるため shard を跨いだ反復は安全。
- `export create`: recourse なし。export の json 成果物は `metadata.json` を上書き方式で生成し、分割再実行
  による pagination/merge が成果物を壊すため分割手段を提供しない。500 超はフィルタ絞り込みで対応する。

この 500 キャップは ADR 0053 の「1 回の呼び出しで総数無制限に annotate を実行できる」前提を**改定**する。
ADR 0053 の `batch_size` streaming と sharding 機構自体は維持し、前者はキャップ内のメモリ境界、後者は
キャップを跨ぐ反復手段として活きる。

read / list 系コマンド (`images list` 等) はこのキャップの対象外であり、自前の `--limit` / `--offset`
ページング (ADR 0049) を持つ。「変更操作は 500 上限・閲覧はページング」と性質で分ける。

### 4. エラーコードセット = 14 種

tag-db と共有する安定コア 11 種に、AI 推論ドメイン固有の 3 種を加えた **全 14 種**。各コードに `retryable` /
`user_action_required` フラグを定義し、エージェントは message 文字列をパースせずこのフラグで分岐する。
共有コア 11 種のフラグ意味は tag-db ADR 0003 の mapping を authoritative とし、本表で全コードを明示する。

| コード | 区分 | retryable | user_action | 主因 / エージェント反応 |
|---|---|---|---|---|
| `INVALID_INPUT` | 共有 | false | true | 引数/選択が不正 → 入力を直す |
| `VALIDATION_FAILED` | 共有 | false | true | 検証失敗 → 入力を直す |
| `PRECONDITION_FAILED` | 共有 | false | true | 前提未達 → 先行操作を実行 |
| `NOT_FOUND` | 共有 | false | true | 対象なし → 指定を見直す |
| `ALREADY_EXISTS` | 共有 | false | true | 既存衝突 → 別名/既存を使う |
| `CONFLICT` | 共有 | false | true | 状態衝突 → 解消して再実行 |
| `IO_ERROR` | 共有 | false | false | ファイル I/O 失敗 |
| `NETWORK_ERROR` | 共有 | true | false | 一時的ネットワーク障害 → 再試行 |
| `DB_ERROR` | 共有 | false | false | DB 操作失敗 |
| `TIMEOUT` | 共有 | true | false | タイムアウト → 再試行 |
| `INTERNAL_ERROR` | 共有 | false | false | 想定外内部エラー |
| `RESOURCE_EXHAUSTED` | 拡張 | true | false | OOM → batch_size を下げて再試行 |
| `AUTH_ERROR` | 拡張 | false | true | API キー未設定/無効 → キーを設定 |
| `RATE_LIMITED` | 拡張 | true | false | provider 429 → backoff して再試行 (`details.retry_after`) |

### 5. `classify_exception`: 例外 → コード分類

raise された例外をエラーコードに分類する関数を新設する。2 つの技法を採用する。

- **cause-chain walking**: `__cause__` / `__context__` を遡り、`raise X from e` で wrap された真因を拾う。
  LoRAIro は iam-lib 例外を `typer.Exit` で包む等の多層 wrap が多いため必須。
- **module-prefix matching**: 例外クラスをモジュール名で判定し、分類のために `torch` / 推論 SDK を
  eager import しない。LoRAIro はこれらを lazy import 化しているため (ADR 0010 系)、eager import は
  起動コスト増・メモリ枯渇を招く。

分類例: `ImageLoadMemoryError` / iam-lib `OutOfMemoryError` / `RuntimeError("...out of memory...")`
→ `RESOURCE_EXHAUSTED`、LoRAIro 独自の `APIKeyNotConfiguredError` (`src/lorairo/api/exceptions.py`、
openai/claude/google で送出) および `anthropic.` / `openai.` / `google.` 系 SDK の `AuthenticationError`
→ `AUTH_ERROR`、同 `RateLimitError` → `RATE_LIMITED`。

LoRAIro はプロバイダ SDK に到達する前に自前で `APIKeyNotConfiguredError` を投げる経路があるため、SDK の
`AuthenticationError` だけでなくこの独自例外も明示的に `AUTH_ERROR` へ写す (でないとキー未設定が generic
な実行時コードに落ち、エージェントが「キーを設定」アクションを受け取れない)。

### 6. exit code policy: 0 / 2 / 1

| exit | 意味 | コード |
|---|---|---|
| 0 | 成功 | — |
| 2 | 入力・検証 | `INVALID_INPUT`, `VALIDATION_FAILED` |
| 1 | 実行時 | 上記以外すべて |

exit code はエラーコードから機械的に導出する。Click の usage error 既定が exit 2 であることと整合する。

### 7. 中央集権エラー境界

各コマンドに散在する `except ... → console.print → Exit(...)` を撤廃し、エラー処理を `cli.main:main` の
1 箇所に集約する。

- Typer/Click app は `standalone_mode=False` で呼ぶ (または同等の wrapper を噛ます)。既定の
  `standalone_mode=True` は Click が自前で usage error を表示し interpreter を終了させ、この境界を
  **バイパス**して stdout に終端 `error` 行が出ない。
- Click usage error (`UsageError` / `BadParameter`) → `INVALID_INPUT` の `error` 行 + exit 2
- それ以外の例外 → `classify_exception` → `error` 行 emit → §6 のマップで exit
- traceback は `INTERNAL_ERROR` のときだけ stderr へ (stdout の JSONL 純度を維持)
- 各コマンド本体は型付き例外を raise / 伝播するだけで、エラー整形を持たない
- 機械可読 (JSONL) / 人間向け (rich) の出力モード分岐も、この境界の 1 箇所だけで行う

## Rationale

- **stdout 純度**: 機械可読契約の根幹。装飾・進捗・エラーが stdout に混じるとパース不能になる。stderr を
  人間とログの経路に分けることで、同一コマンドが人間にもエージェントにも使える。
- **`event` kind を持たない**: annotate は `item` をストリームするため item 数が進捗そのもので、別途
  `event` 行は冗長。export はバッチ操作で機械的な途中経過が不要。進捗バーは人間向けに価値があるので
  stderr に残す。tag-db の「JSONL が読みにくいならフォーマットでなくコマンドが情報を出しすぎている」
  という設計哲学を継承し、各コマンドは curated な projection を出す。
- **500 ハードキャップ**: GUI の staging (最大 500 枚) と挙動を統一し、全バッチ操作 (annotate / export /
  images update) の「1 コマンドが処理する総数」を 500 に揃える。`batch_size` (モデル処理 chunk) とは
  別概念。処理前に弾くため副作用ゼロで fail fast。annotate は ADR 0053 の sharding
  (`--limit`/`--offset`/`--image-id`) で 500 ずつ反復でき上限が実害にならない。export は json 成果物が
  `metadata.json` 上書き方式で安全分割できず反復手段を持たないが、実運用上 1 回の学習データセットが
  500 枚を超えることは稀で阻害にならない。ADR 0053 の「無制限実行」前提のみを本 ADR が改定し、
  streaming/sharding 機構は維持する。
- **14 コード**: tag-db と 11 種を共有してエージェントの学習コストを下げる。拡張 3 種は反応が一意に異なる
  ケース (OOM=batch 縮小再試行 / auth=キー設定 / rate=backoff) だけに限定する。`MODEL_ERROR` のような
  総称は中身が `NETWORK_ERROR` / `NOT_FOUND` / `VALIDATION_FAILED` に分解でき、総称化するとかえって機械が
  反応しにくくなるため採用しない。
- **module-prefix / cause-chain**: LoRAIro は推論 SDK・torch を lazy import 化しているため、分類のための
  eager import を避ける必要があり、多層 wrap の真因特定にも cause-chain 遡及が要る。
- **中央集権境界**: 現状の散在 `except` が exit code 揺れの主因。1 箇所集約で契約を機械的に保証し、
  コマンド本体を薄くできる。
- **exit code 0/2/1**: Click の usage error 既定が exit 2 であり「2=入力問題」が自然。tag-db と揃う。

## Consequences

- 各コマンドの出力を「人間向け render (stderr / TTY)」と「機械向け dict (stdout JSONL)」に分離する
  リファクタが全コマンドに必要になる (実装は別タスク)。
- 各コマンドの散在エラーハンドリングを撤廃し中央境界へ移行する破壊的変更。exit code の意味が現状から
  フリップ (現状の `Exit(2)`=想定外 → 本 ADR では 2=入力・検証) するため、既存の呼び出し側スクリプトに
  影響し得る。
- 14 コードの `classify_exception` / `ErrorInfo` モジュールを新設する。
- 500 キャップにより 500 枚超の一括操作は不可となり、利用者は絞り込みまたは反復呼び出しで対応する。
- broad `except Exception` はコーディング規約で原則禁止だが、CLI 境界の 1 箇所に限り本 ADR で許可する
  (例外をエラー行に変換する境界という理由による)。
- 契約の SSoT は**コード**に置く: `kind` / エラー `code` は `StrEnum`、各 payload は `api.*` の Pydantic
  型 (ADR 0037) として定義する。`docs/cli.md` (新設) はそれらから生成 or 参照する human/agent 向け文書で
  あり、wire スキーマを二重定義しない (introspection の `describe` も同じ型から生成する)。
- annotate の 1 回処理総数が 500 に制限され、ADR 0053 の無制限実行前提が改定される。500 超の annotate は
  `--limit`/`--offset`/`--image-id` で shard して反復する運用になる。

## 関連

- ADR 0020 (CLI Message Language Policy) — JSONL モードの message 言語方針と整合
- ADR 0037 (api Facade Wiring Policy) — 契約 SSoT は `api.*` Pydantic、CLI は薄いラッパー
- ADR 0049 (Apply CLI Image List Limit in the Repository Query) — read/list 系のページング (500 キャップ対象外)
- ADR 0053 (CLI Streaming Annotation Memory-Bounded Contract) — 本 ADR が「1 回の呼び出しで総数無制限」
  前提を 500 キャップで改定 (streaming/sharding 機構は維持)。`RESOURCE_EXHAUSTED` / streaming とも整合
- ADR 0058 (CLI Output Mode Trigger and Entry-Point Policy) — 出力モードのトリガ (`--json`) とエントリ方針を供給 (本 ADR の前提)
- tag-db ADR 0003 (CLI JSONL Output & Error Contract) — 移植元の参照契約
- tag-db ADR 0005 (CLI Command Introspection) — 後続の introspection 契約 (別 ADR)
