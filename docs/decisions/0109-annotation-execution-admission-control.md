---
type: ADR
title: アノテーション実行の受付・待機・停止はアプリが行い、ローカルモデルは 1 つずつ実行して即時保存する
status: Accepted
timestamp: 2026-11-11
tags: [annotation, memory, worker, local-ml, execution-control]
---

# ADR 0109: アノテーション実行の受付・待機・停止はアプリが行い、ローカルモデルは 1 つずつ実行して即時保存する

## Context

多数の画像を TensorFlow 系モデルへ一括投入した実行で、推論がメモリを使い切り、後続モデルへ進んだ後に
PC 全体の操作が困難になった。image-annotator-lib 側は lib ADR 0013 で推論の小分け・推論前の見積もり・
実デバイス判定・OOM の分類 (`error_code`) を入れ、「全体を止めるか待つかはアプリが `error_code` と
`InferenceRuntimeInfo` で判断する」と定めた。アプリ側に残っていた問題は次の通り。

| 観点 | 変更前の GUI 経路 (`AnnotationWorker`) |
|---|---|
| モデルの順序 | 選択順の全モデルを `execute_annotation` に 1 回で渡し、lib 内部の per-model ループで逐次実行 |
| 受付 | 空きメモリを見ずに実行。アプリに空きメモリ取得コードなし |
| 結果の保存単位 | lib が全モデルを終えて戻るまで 1 件も DB 保存しない (例外時だけモデル単位 fallback) |
| 中止 | lib のモデル間 iteration 直前に確認。完了済みモデルの結果は lib 内に留まり保存されない |
| OOM | lib の `OUT_OF_MEMORY` / `INSUFFICIENT_MEMORY` はログだけで `error_records` に残らない |
| 表示 | 実行先 (CPU/GPU)・待機・メモリ不足の理由を出す場所がない |

CLI (`annotate`) はチャンクごとに保存し、durable run (ADR 0053 系) で再開できるため、本 ADR の対象は
GUI の `AnnotationWorker` に限る。

## Decision

### 1. 役割分担

- **lib**: 処理枚数 (小分け)、推論前の見積もりによるモデル内の枚数調整、推論中 OOM の検出とモデル解放、
  モデル重みのロード前ガードと待機中キャッシュの追い出し (lib ADR 0012 / 0013)。
- **アプリ**: モデルの実行順、モデル単位の受付判定と待機、見送り、メモリ不足後に残りを続けるかの判断、
  保存単位、中止、表示。

使う lib API は `UnifiedAnnotationResult.error_code` (`OUT_OF_MEMORY` / `INSUFFICIENT_MEMORY`)、
`UnifiedAnnotationResult.execution_device`、`get_inference_runtime_info(model_name)`
(`execution_device` のみ参照)。lib 呼び出しは `AnnotatorLibraryAdapter` に閉じ込める。
`set_tensorflow_cpu_threads` は今回使わない (スレッド数上限の既定値を決める実測が無いため)。

### 2. モデル単位ループ (案 A)

`AnnotationWorker._run_annotation` は選択順にモデルを 1 つずつ処理する。

1. ローカル ML モデルなら受付判定 (3.)。待機しても回復しなければ見送って理由を記録し、次のモデルへ。
2. `execute_annotation(image_paths, [そのモデル])` を呼ぶ。
3. 結果をそのモデルの分だけ即時保存する (`_persist_incremental_results`)。
4. 結果に `OUT_OF_MEMORY` / `INSUFFICIENT_MEMORY` があり、後ろにローカル ML モデルが残っていれば、
   同じ受付判定 (待機込み) で続けるかを決める。回復しなければ残りのローカル ML モデルを待たずに
   見送る (WebAPI モデルは続ける)。
5. モデルの境目で中止を確認する。

ローカル ML かどうかは registry の `ModelInfo.requires_api_key` で判定する。WebAPI モデル
(`requires_api_key=True`) は RAM / VRAM をほぼ使わないため受付判定の対象外。registry に無いモデルと
registry 取得失敗時は、保守的にローカル扱いにする。

**一括呼び出しから変わること**: lib の per-model ループと同じ順序・同じ画像で呼ぶため、推論結果と
モデルのキャッシュ (lib のインスタンスレジストリはプロセス内で共有) は変わらない。失うのは次の 2 点で、
いずれも推論時間に対して小さいため受け入れる。

- `AnnotationRunner` が画像ファイルを開く処理がモデル数だけ繰り返される (PIL は遅延読み込み)。
- DB に pHash が無い画像を含む場合、lib の pHash 計算がモデル数だけ繰り返される (登録済み画像は
  ADR 0033 Decision 6 どおり DB の pHash を渡すので再計算しない)。

一括呼び出しが例外で落ちた時だけ使っていたモデル単位 fallback は、通常経路と同じになったため廃止した。
lib 呼び出しの例外は従来の fallback と同じく L2 (ADR 0033) として記録し、次のモデルへ進む。

### 3. 受付判定

判定は Qt 非依存の `AnnotationExecutionPolicy` (`services/annotation_execution_policy.py`) が行う。

```text
受付 = 空き RAM ≥ ram_safety_margin_gb
       かつ (空き VRAM が取得できる場合) 空き VRAM ≥ vram_safety_margin_gb
```

- 空き RAM は `psutil.virtual_memory().available`。psutil は従来 accelerate 経由の間接依存だったため、
  直接 import するのに合わせて明示依存にした。lib の取得関数は公開 API ではないため使わない。
- 空き VRAM は、torch が既に import 済みで CUDA が初期化済みの場合だけ `torch.cuda.mem_get_info` で
  取る。torch を新たに import したり CUDA コンテキストを作ったりしない (それ自体が VRAM を使い、
  lib の torch 遅延 import 方針にも反する)。取れなければ VRAM の判定は省略する。
- **モデルごとの必要量 (重み) は加算しない。** 重みのロード可否と待機中キャッシュの追い出しは lib の
  ロード前ガード (lib ADR 0012) が担っており、アプリからは既にキャッシュ済みかどうかが見えない。
  `estimated_size_gb` を足すと同じモデルの再実行を常に二重計上し、待つ必要のない場面で待機・見送りが
  起きる。アプリの判定は「OS と他プロセスのための余裕が残っているか」に限り、推論中の入力量の見積もりは
  lib の推論前見積もりに任せる。
- 空きが足りなければ `wait_poll_interval_sec` ごとに再確認し、`wait_timeout_sec` を超えたら見送る。
  待機中も 0.5 秒刻みで中止を確認する。
- 取得関数・時計・sleep は DI でき、テストは fake で決定論的に書く。

### 4. 設定と暫定既定値

`[annotation_execution]` セクション (既定値の SSoT は `utils/config.py` の `DEFAULT_CONFIG`)。

| キー | 既定値 | 意味 |
|---|---|---|
| `admission_check_enabled` | `true` | false で受付判定・待機をしない |
| `ram_safety_margin_gb` | `4.0` | 実行前に残す空き RAM (GB) |
| `vram_safety_margin_gb` | `1.0` | 空き VRAM が取れる場合に残す量 (GB) |
| `wait_poll_interval_sec` | `5.0` | 空きが足りないときの再確認間隔 (秒) |
| `wait_timeout_sec` | `120.0` | 回復を待つ上限 (秒)。超えたらそのモデルを見送る |
| `skip_completed_on_rerun` | `false` | true で同じモデルの結果が既にある画像を推論から外す |

既定値は**実測前の暫定値**である。RAM の余裕は lib の推論前見積もりの余裕 (2GB) より大きく取り、
OS の操作性を優先した保守値にした。実機計測の結果が出たら見直す。不正な値 (負数・型違い) は既定値に戻す。

### 5. メモリ不足の扱いと保存単位

- lib が返した `OUT_OF_MEMORY` / `INSUFFICIENT_MEMORY` は `AnnotationSaveService` の記録対象 code に加え、
  `error_records` に残してエラータブで確認できるようにする。メモリ不足は画像の性質ではないため、
  再実行時の送信前 filter (`REFUSAL_ERROR_TYPES`) には加えない。
- アプリが受付判定で見送ったモデルは、対象画像ごとに `error_type="INSUFFICIENT_MEMORY"` で記録する
  (lib の推論前見積もり不足と同じ分類にし、エラータブで「メモリ不足」として並べる)。
- `ModelErrorDetail.error_code` に lib の `error_code` を載せ、サマリーダイアログでメモリ不足を
  他のエラーと区別して表示する。見送った画像は「失敗分を再ステージング」の対象になる。
- 保存単位はモデル単位。中止・見送り・後続モデルの OOM・プロセス終了でも、完了したモデルの結果は残る。
- 再実行時に完了済みを飛ばす手段は、CLI には `--missing-model` と durable run があるが GUI に無かった。
  `skip_completed_on_rerun` を有効にすると、`--missing-model` と同じ判定 (未 reject の tag/caption、
  score/score_label/rating の存在) で `(画像, モデル)` 単位に外す。既定は無効で、意図的な再推論を
  黙って省略しない。

### 6. 表示

- 待機中は `AnnotationPhase.WAITING_FOR_MEMORY` と、理由・残り秒を `AnnotationProgress.note` で
  ステータスバー常設部品 (ADR 0108) とジョブ台帳に出す。
- 実行先が `cpu` と分かったモデル (現状は lib が記録する TensorFlow 系だけ) は進捗とサマリーの
  「実行状況」に出す。実行先が取れないモデルには何も出さない。
- 中止時はモデルの境目で止まり、「完了した N モデルの結果は保存済み」を終端表示に出す。
- 文言に内部クラス名や例外文字列を入れない。

## Rationale

- **案 A (アプリがモデル単位で呼ぶ) を採る理由**: 保存単位・受付・中止の粒度をすべてモデルの境目に
  揃えられ、lib の API を変えずに済む。lib にコールバック (モデル完了・中止要求) を足す案は lib の
  公開 API 変更を伴い、アプリの判断を lib 内のループに持ち込むことになる。結果だけを途中で受け取る
  案は保存単位は解決するが、受付判定をモデル実行の前に挟めない。
- **並列化しない理由**: 今回の障害は直列実行で起きており、原因は 1 モデル内の入力量と見積もりの欠如
  だった。並列化するとモデル同士がメモリを奪い合い、受付判定の前提 (判定時点の空きが実行中も
  おおむね残る) が崩れる。GPU 直列キュー (ADR 0066) とも整合する。並列化は実測と別の判断材料が
  揃ってから検討する。
- **CLI を変えない理由**: CLI はチャンク単位の保存と durable run で中断・再開を扱っており、
  完了済みの結果が失われる問題は GUI 経路に固有だった。受付判定を CLI に入れるかは別途判断する。

## Consequences

- 一括呼び出しを前提にしていた `AnnotationWorker` のテストは、モデル単位の呼び出しを検証する形に
  置き換えた。
- 推論中のモデル内 (画像の間) の中止は lib に引数が無いため今回の範囲外で、中止はモデルの境目と
  待機中にだけ効く。
- 受付判定は判定時点の空きを見るだけで、推論中のピークは保証しない。推論中の超過は lib の小分け・
  推論前見積もり・OOM 検出に任せる。
- VRAM の判定は torch が CUDA を初期化済みのときだけ働く。TensorFlow 専用の GPU メモリは見ない。
- 既定値は暫定で、実機計測に基づく見直しと並列化は follow-up とする。

## Related

- [Issue #1468](https://github.com/NEXTAltair/LoRAIro/issues/1468)
- image-annotator-lib ADR 0012 (Local Model Context Ownership and Resource Budgets)、
  ADR 0013 (TensorFlow Inference Chunking, Memory Estimate and Runtime Report)
- [ADR 0033](0033-annotation-worker-batch-execution-contract.md)、
  [ADR 0053](0053-cli-streaming-annotation-memory-bounded-contract.md)、
  [ADR 0066](0066-unified-jobs-lifecycle-view.md)、
  [ADR 0079](0079-jobs-stage-progress-and-summary-band.md)、
  [ADR 0108](0108-statusbar-permanent-progress-widget.md)
