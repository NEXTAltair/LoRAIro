# ADR 0053: CLI Streaming Annotation Memory-Bounded Execution Contract

- **日付**: 2026-05-29
- **ステータス**: Accepted
- **関連 Issue**: #531 (epic) / #536 / #537 / #538

## Context

`lorairo-cli annotate run` は `_load_images_from_db()` で対象画像レコードを**全件** `PIL.Image.Image`
として decode し、`pil_images` に一括保持してから `annotator.annotate(...)` に渡していた。21,192 件規模の
データセットで annotation 開始前に `[Errno 12] Cannot allocate memory` (OOM 相当) に到達する。

以下の構造的な欠陥が同時に存在した。

- `--batch-size` は CLI option として定義されていたが、load にも `annotate(...)` にも伝播せず**実質未使用**。
- メモリ枯渇 (`MemoryError` / `OSError(errno.ENOMEM)`) が、通常の破損画像 warning と同じ `except Exception`
  に握り込まれ、致命的失敗が skip 継続扱いになって観測上 exit 0 で素通りしていた。
- 大規模データセットを部分実行・sharding する手段 (`--limit` / `--offset` / `--image-id`) がなかった。

GUI 側の batch annotation は ADR 0033 (AnnotationWorker Batch Execution Contract) / ADR 0034
(Worker / Operation / Pipeline Lifecycle Boundary) で実行契約が確立済みだが、CLI の `annotate run` は
worker 層を経由しない独立経路であり、同等のメモリ境界・失敗分類契約が未定義だった。本 ADR はその CLI 経路の
実行契約を確定する。

## Decision

### 1. `--batch-size` で同時保持する decoded PIL 画像数を bound する

`annotate run` は対象レコードを `batch_size` 単位の chunk に分割し、chunk ごとに

1. chunk 内の画像のみ open/load (`_load_batch_images`)
2. `annotator.annotate(images, ...)` を呼ぶ
3. `save_annotation_results(...)` で chunk 結果を DB 保存
4. `finally` で chunk の全画像を `img.close()` し、次 chunk 前にメモリ解放

を反復する。データセットが `batch_size` を超える場合 `annotate()` は複数回呼ばれる。同時にメモリに載る
decoded 画像数は常に高々 `batch_size` 件に bound される。

### 2. ロード失敗を SKIP / FATAL の 2 種に分類する

```python
class LoadFailureAction(Enum):
    SKIP = "skip"      # 破損 / 欠損ファイル → warning して継続
    FATAL = "fatal"    # MemoryError / errno.ENOMEM → 致命

class ImageLoadMemoryError(RuntimeError): ...

def _classify_load_failure(exc: BaseException) -> LoadFailureAction: ...
```

- **SKIP**: 個々の破損 / 欠損画像。warning ログを出し `failed_count++` で継続。従来挙動を維持。
- **FATAL**: `MemoryError` および `errno.ENOMEM` 相当の `OSError`。`ImageLoadMemoryError` を raise し、
  呼び出し側が `typer.Exit(code=1)` で**致命的に中断**する。メモリ枯渇を破損画像 skip に紛れさせない。

### 3. 全失敗判定を「全チャンク通算 0 成功で Exit(1)」へ意味を保ったまま変更する

従来の `_handle_annotation_results` は「結果空 or 全モデル失敗で Exit(1)」だった。streaming 化に伴い、
判定対象を**全チャンク通算**に拡張する。

- 1 chunk の annotation 失敗で全体を中断しない。
- run 全体を通算して 1 件も成功しなければ Exit(1)。
- サマリーは通算カウンタ (`total_loaded` / `agg_success` / `agg_skip` / `agg_error`) で表示する。

### 4. 部分実行 / sharding は CLI レベル slice で行う (DB 層非変更)

`--limit N` / `--offset N` / `--image-id ID` (repeatable) を提供する。フィルタ済み**メタデータ dict**
(画像 decode 前) に対して以下の固定順序で適用する。

**`image-id フィルタ → offset → limit`**

```python
def _select_image_records(
    image_records: list[dict[str, Any]],
    *,
    limit: int | None,
    offset: int,
    image_ids: list[int] | None,
) -> list[dict[str, Any]]: ...
```

- `image_ids` 指定時、要求 ID のうち未存在のものは warning。
- 選択結果が空なら呼び出し側が `typer.Exit(code=1)`。
- メタデータは dict のため 21k 件でもメモリ問題はない (画像 decode のみ §1 の chunk で bound)。
  `get_images_by_filter()` がページング非対応なため、DB 層を変更せず CLI 層で slice する。

## Rationale

- **DB 層 slice ではなく CLI 層 slice**: `get_images_by_filter()` はページング非対応で全 ID 取得 →
  メタデータ化する。メタデータ dict は軽量でメモリ問題を起こさず、OOM の真因は画像 decode の一括保持に
  限定される。よって DB 層を改修せず、画像 decode を制御する `batch_size` chunk と、メタデータに対する
  CLI slice の二段構えで十分。db-schema-reviewer を要する DB 変更を避けられる。
- **メモリ枯渇を独立例外にする**: `MemoryError` / `ENOMEM` を破損画像 skip と同じ経路に握り込むと、
  致命的失敗が exit 0 で素通りし、自動化 / スクリプト連携で失敗検知できない。専用例外 + 専用 exit code で
  運用者と上位プロセスが確実に検知できる。
- **通算判定**: chunk 単位で「全失敗 Exit」を判定すると、最初の小 chunk が失敗しただけで残りの健全な
  データを処理せず中断してしまう。run 全体の通算で判定することで、部分的失敗を許容しつつ「全滅」だけを
  失敗扱いする従来意味を保つ。
- **GUI worker 契約 (ADR 0033/0034) との整合**: CLI は worker 層を経由しない別経路だが、「batch 単位の
  実行・失敗分類・terminal outcome の明示」という設計原則は共通。CLI 経路でも同原則を契約として固定する。

## Consequences

- `_load_images_from_db()` の全件一括 decode は廃止され、chunk streaming driver に置き換わる。
- `annotate run` の exit code 挙動が明文化される: 通常破損は skip 継続、メモリ枯渇は Exit(1)、全滅は Exit(1)。
- `--batch-size` がメモリ消費の実効上限になる。運用者は環境のメモリに応じて調整できる。
- `--limit` / `--offset` / `--image-id` により大規模データセットの分割実行 / 再開 / 特定画像のみの実行が可能になる。
- exit code 0 観測の真因 (呼び出し側 wrapper / shell 経路) は非ブロッキングの追加調査事項として #537 に残す。
  本契約 (FATAL → Exit(1)) でユーザー影響は解消される。

## 関連

- ADR 0033 (AnnotationWorker Batch Execution Contract) — GUI worker 側の batch 実行契約
- ADR 0034 (Worker / Operation / Pipeline Lifecycle Boundary) — terminal outcome / 失敗分類の原則
- ADR 0049 (Apply CLI Image List Limit in the Repository Query) — CLI list 系の DB limit 方針
