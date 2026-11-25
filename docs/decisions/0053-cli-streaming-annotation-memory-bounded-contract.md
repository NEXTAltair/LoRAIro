---
type: ADR
title: CLI Streaming Annotation Memory-Bounded Execution Contract
status: Accepted (1 回の呼び出しの処理総数上限は ADR 0057 で 500 に改定)
timestamp: 2026-05-29
tags: []
---
# ADR 0053: CLI Streaming Annotation Memory-Bounded Execution Contract

- **関連 Issue**: #531 (epic) / #536 / #537 / #538

> **改定(2026-06-05、ADR 0057)**: 本 ADR は「1 回の呼び出しで総数無制限にアノテーションを実行できる」ことを前提としていた。しかし、ADR 0057 がすべてのバッチ操作に 1 回あたり 500 枚の総数上限を課したため、`annotate` も 1 回 500 枚までに制限される。一方で、`batch_size` によるストリーミング処理(§1)および `--limit`、`--offset`、`--image-id` による分割実行(§4)の機構は維持され、後者は 500 枚を跨いで反復処理する手段として引き続き機能する。

## Context

`lorairo-cli annotate run` は、`_load_images_from_db()` で対象画像レコードを**全件** `PIL.Image.Image` としてデコードし、`pil_images` に一括保持してから `annotator.annotate(...)` へ渡していた。そのため、21,192 件規模のデータセットではアノテーション開始前に `[Errno 12] Cannot allocate memory`(OOM 相当)へ到達していた。

この問題には、以下の構造的な欠陥が同時に存在していた。

- `--batch-size` が CLI オプションとして定義されていたにもかかわらず、読み込み処理にも `annotate(...)` にも伝播せず**実質未使用**だった。
- メモリ枯渇(`MemoryError` および `OSError(errno.ENOMEM)`)が、通常の破損画像警告と同じ `except Exception` に握り込まれていた。その結果、致命的な失敗がスキップ継続扱いとなり、観測上は終了コード 0 で素通りしていた。
- 大規模データセットを部分実行または分割実行(シャーディング)するためのオプション(`--limit`、`--offset`、`--image-id`)が存在しなかった。

GUI 側のバッチアノテーションでは、ADR 0033(AnnotationWorker Batch Execution Contract)および ADR 0034(Worker / Operation / Pipeline Lifecycle Boundary)によって実行契約が確立されている。しかし、CLI の `annotate run` はワーカー層を経由しない独立経路であり、同等のメモリ境界と失敗分類の契約が未定義だった。本 ADR は、その CLI 経路における実行契約を確定する。

## Decision

### 1. `--batch-size` で同時保持するデコード済み PIL 画像数に上限を設ける

`annotate run` は対象レコードを `batch_size` 単位のチャンクに分割し、チャンクごとに以下の手順を反復する。

1. チャンク内の画像のみを開いて読み込む(`_load_batch_images`)。
2. `annotator.annotate(images, ...)` を呼び出す。
3. `save_annotation_results(...)` でチャンクの結果を DB へ保存する。
4. `finally` ブロックでチャンク内の全画像を `img.close()` し、次のチャンクへ進む前にメモリを解放する。

データセットが `batch_size` を超える場合、`annotate()` は複数回呼び出される。これにより、同時にメモリ上へ保持されるデコード済み画像数は常に高々 `batch_size` 件に制限される。

### 2. 読み込み失敗を `SKIP` と `FATAL` の 2 種類に分類する

```python
class LoadFailureAction(Enum):
    SKIP = "skip"      # 破損 / 欠損ファイル → warning して継続
    FATAL = "fatal"    # MemoryError / errno.ENOMEM → 致命

class ImageLoadMemoryError(RuntimeError): ...

def _classify_load_failure(exc: BaseException) -> LoadFailureAction: ...
```

- **`SKIP`**:個々の破損ファイルまたは欠損ファイル。警告ログを出力し、`failed_count` を加算して処理を継続する(従来挙動を維持)。
- **`FATAL`**:`MemoryError` および `errno.ENOMEM` 相当の `OSError`。`ImageLoadMemoryError` を送出し、呼び出し側が `typer.Exit(code=1)` で**致命的に中断**する。これにより、メモリ枯渇が破損画像のスキップ処理へ紛れ込むことを防ぐ。

### 3. 全失敗判定を「全チャンク通算で 0 件成功なら `Exit(1)`」へ拡張する

従来の `_handle_annotation_results` は「結果が空、または全モデル失敗で `Exit(1)`」としていた。ストリーミング化に伴い、この判定対象を**全チャンク通算**へ拡張する。

- 1 つのチャンクでアノテーションが失敗しても、全体の処理は中断しない。
- 実行全体を通算して 1 件も成功しなかった場合に限り、`Exit(1)` とする。
- サマリー表示には通算カウンタ(`total_loaded`、`agg_success`、`agg_skip`、`agg_error`)を使用する。

### 4. 部分実行および分割実行は CLI レベルのスライスで行う(DB 層は変更しない)

`--limit N`、`--offset N`、`--image-id ID`(複数回指定可能)を提供する。これらは、フィルタ済みの**メタデータ辞書**(画像デコード前)に対して以下の固定順序で適用する。

**`image-id` フィルタ → `offset` → `limit`**

```python
def _select_image_records(
    image_records: list[dict[str, Any]],
    *,
    limit: int | None,
    offset: int,
    image_ids: list[int] | None,
) -> list[dict[str, Any]]: ...
```

- `image_ids` を指定した際、要求された ID のうち存在しないものは警告ログを出力する。
- 選択結果が空の場合は、呼び出し側が `typer.Exit(code=1)` で終了する。
- メタデータは辞書形式であるため、21k 件規模でもメモリ上の問題は起きない(画像デコードのみ §1 のチャンク処理で上限を制御する)。`get_images_by_filter()` はページング未対応のため、DB 層を変更せず CLI 層でスライスを行う。

## Rationale

- **DB 層ではなく CLI 層でスライスする理由**:`get_images_by_filter()` はページング未対応であり、全 ID を取得してメタデータ化する構造になっている。メタデータ辞書は軽量でメモリ枯渇を起こさず、OOM の真因は画像デコードの一括保持に限定される。したがって、DB 層を改修せず、`batch_size` チャンクによるデコード制御と CLI 側スライスの二段構えで十分であり、db-schema-reviewer を要する DB 変更を回避できる。
- **メモリ枯渇を独立した例外とする理由**:`MemoryError` や `ENOMEM` を破損画像のスキップ経路に握り込むと、致命的な失敗が終了コード 0 で素通りし、自動化スクリプトから失敗を検知できなくなる。専用例外と明確な終了コードにより、運用者と上位プロセスが確実に異常を検知できる。
- **全チャンク通算で失敗判定する理由**:チャンク単位で「全失敗なら即終了」と判定すると、最初の小チャンクが失敗しただけで残りの健全なデータを処理せずに中断してしまう。実行全体を通算して判定することで、部分的な失敗を許容しつつ「全件失敗」だけを失敗扱いする従来の意味を保てる。
- **GUI ワーカー契約(ADR 0033 / 0034)との整合性**:CLI はワーカー層を経由しない別経路だが、「バッチ単位の実行、失敗の分類、最終結果(terminal outcome)の明示」という設計原則は共通である。CLI 経路でも同じ原則を契約として固定する。

## Consequences

- `_load_images_from_db()` による全件一括デコードは廃止され、チャンク単位のストリーミング駆動へ置き換わる。
- `annotate run` の終了コード挙動が明文化される(通常の破損画像はスキップ継続、メモリ枯渇は `Exit(1)`、全件失敗は `Exit(1)`)。
- `--batch-size` がメモリ消費の実効上限となり、運用者は実行環境のメモリ容量に応じて調整できる。
- `--limit`、`--offset`、`--image-id` により、大規模データセットの分割実行、再開、特定画像のみを対象とした実行が可能になる。
- 終了コード 0 が観測された真因(呼び出し側ラッパーやシェル経路の影響)は、非ブロッキングの追加調査事項として #537 に残す。本契約(`FATAL` → `Exit(1)`)によってユーザーへの直接的な影響は解消される。

## 関連

- ADR 0033(AnnotationWorker Batch Execution Contract)— GUI ワーカー側のバッチ実行契約
- ADR 0034(Worker / Operation / Pipeline Lifecycle Boundary)— 最終結果および失敗分類の原則
- ADR 0049(Apply CLI Image List Limit in the Repository Query)— CLI list 系の DB 上限方針
