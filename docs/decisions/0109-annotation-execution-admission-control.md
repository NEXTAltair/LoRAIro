---
type: ADR
title: アノテーション実行の受付・待機・停止はアプリが行い、ローカルモデルは 1 つずつ実行して即時保存する
status: Accepted
timestamp: 2026-11-11
tags: [annotation, memory, worker, local-ml, execution-control]
---

# ADR 0109: アノテーション実行の受付・待機・停止はアプリが行い、ローカルモデルは 1 つずつ実行して即時保存する

## Context

多数の画像を TensorFlow 系モデルへ一括投入した実行において、推論がメモリを使い切り、後続モデルへ進んだ後に PC 全体の操作が困難になる事象が発生した。`image-annotator-lib` 側では lib ADR 0013 により、推論の小分け・推論前の見積もり・実デバイス判定・OOM の分類(`error_code`)を導入し、「全体を止めるか待機するかはアプリ側が `error_code` と `InferenceRuntimeInfo` で判断する」と定めた。

一方で、アプリ側には次の課題が残っていた。

| 観点 | 変更前の GUI 経路(`AnnotationWorker`) |
|---|---|
| モデルの順序 | 選択順の全モデルを `execute_annotation` へ 1 回で渡し、lib 内部のモデル単位ループで逐次実行 |
| 受付 | 空きメモリを確認せずに実行。アプリに空きメモリ取得コードが無い |
| 結果の保存単位 | lib が全モデルを終えて戻るまで 1 件も DB 保存しない(例外時のみモデル単位フォールバック) |
| 中止 | lib のモデル間反復の直前に確認。完了済みモデルの結果は lib 内に留まり保存されない |
| OOM | lib の `OUT_OF_MEMORY` / `INSUFFICIENT_MEMORY` はログ出力のみで `error_records` に残らない |
| 表示 | 実行先(CPU / GPU)・待機・メモリ不足の理由を表示する場所が無い |

CLI(`annotate`)はチャンクごとに保存し、永続実行(durable run、ADR 0053 系)で再開できるため、本 ADR の対象は GUI の `AnnotationWorker` に限定する。

## Decision

### 1. lib とアプリの役割分担

- **lib**: 処理枚数の小分け、推論前の見積もりによるモデル内の枚数調整、推論中 OOM の検出とモデル解放、モデル重みのロード前ガードおよび待機中キャッシュの追い出し(lib ADR 0012 / 0013)。
- **アプリ**: モデルの実行順、モデル単位の受付判定と待機、見送り、メモリ不足後に残りを続けるかの判断、保存単位、中止制御、および進捗・状態の表示。

利用する lib API は、`UnifiedAnnotationResult.error_code`(`OUT_OF_MEMORY` / `INSUFFICIENT_MEMORY`)、`UnifiedAnnotationResult.execution_device`、`get_inference_runtime_info(model_name)`(`execution_device` のみ参照)とする。lib 呼び出しは `AnnotatorLibraryAdapter` に閉じ込める。なお、`set_tensorflow_cpu_threads` はスレッド数上限の既定値を決める実測が無いため今回は使わない。

### 2. モデル単位ループ(案 A)

`AnnotationWorker._run_annotation` は選択順にモデルを 1 つずつ処理する。

1. ローカル ML モデルであれば受付判定(§3)を行う。待機しても回復しなければ見送って理由を記録し、次のモデルへ進む。
2. `execute_annotation(image_paths, [そのモデル])` を呼び出す。
3. 結果をそのモデルの分だけ即時保存する(`_persist_incremental_results`)。
4. 結果に `OUT_OF_MEMORY` または `INSUFFICIENT_MEMORY` が含まれ、後続にローカル ML モデルが残っていれば、同じ受付判定(待機込み)で継続可否を判断する。回復しなければ残りのローカル ML モデルを待たずに見送る(WebAPI モデルは継続する)。
5. モデルの境目で中止要求を確認する。

ローカル ML かどうかはレジストリの `ModelInfo.requires_api_key` で判定する。WebAPI モデル(`requires_api_key=True`)は RAM / VRAM をほぼ消費しないため受付判定の対象外とする。レジストリに無いモデルやレジストリ取得失敗時は、保守的にローカル扱いとする。

**一括呼び出しからの変化**: lib 内部のモデル単位ループと同じ順序・同じ画像で呼び出すため、推論結果やモデルのキャッシュ(lib のインスタンスレジストリはプロセス内で共有)は変わらない。増加するコストは次の 2 点だが、いずれも推論時間に対して十分に小さいため許容する。

- `AnnotationRunner` が画像ファイルを開く処理がモデル数だけ繰り返される(PIL は遅延読み込み)。
- DB に pHash が無い画像を含む場合、lib の pHash 計算がモデル数だけ繰り返される(登録済み画像は ADR 0033 Decision 6 どおり DB の pHash を渡すため再計算されない)。

一括呼び出しが例外で落ちた時だけ使っていたモデル単位フォールバックは、通常経路と同一になったため廃止する。lib 呼び出しの例外は従来のフォールバックと同じく L2(ADR 0033)として記録し、次のモデルへ進む。

### 3. 受付判定

受付判定は Qt 非依存の `AnnotationExecutionPolicy`(`services/annotation_execution_policy.py`)が担う。

```text
受付 = 空き RAM ≥ ram_safety_margin_gb
       かつ (空き VRAM が取得できる場合) 空き VRAM ≥ vram_safety_margin_gb
```

- **空き RAM**: `psutil.virtual_memory().available` で取得する。`psutil` は従来 `accelerate` 経由の間接依存だったため、直接インポートするのに合わせて明示依存へ追加した。lib の取得関数は公開 API ではないため使わない。
- **空き VRAM**: `torch` が既にインポート済みかつ CUDA が初期化済みの場合に限り、`torch.cuda.mem_get_info` で取得する。新たに `torch` をインポートしたり CUDA コンテキストを生成したりしない(それ自体が VRAM を消費し、lib の `torch` 遅延インポート方針にも反するため)。取得できない場合は VRAM の判定を省略する。
- **モデルごとの必要量(重み)は加算しない**: 重みのロード可否と待機中キャッシュの追い出しは lib のロード前ガード(lib ADR 0012)が担っており、アプリからは既にキャッシュ済みかどうか判別できない。`estimated_size_gb` を加算すると同じモデルの再実行で常に二重計上となり、不要な待機や見送りが起きる。アプリの判定は「OS と他プロセスのための余裕が残っているか」に限定し、推論中の入力量の見積もりは lib の推論前見積もりに委ねる。
- **待機と中止**: 空きが不足していれば `wait_poll_interval_sec` ごとに再確認し、`wait_timeout_sec` を超えたら見送る。待機中も 0.5 秒刻みで中止要求を確認する。
- **テスト容易性**: 取得関数・時計・sleep は DI 可能とし、テストはフェイク(fake)を用いて決定論的に記述する。

### 4. 設定と暫定既定値

`[annotation_execution]` セクションを設ける(既定値の SSoT は `utils/config.py` の `DEFAULT_CONFIG`)。

| キー | 既定値 | 意味 |
|---|---|---|
| `admission_check_enabled` | `true` | `false` で受付判定・待機を行わない |
| `ram_safety_margin_gb` | `4.0` | 実行前に残す空き RAM(GB) |
| `vram_safety_margin_gb` | `1.0` | 空き VRAM が取得できる場合に残す量(GB) |
| `wait_poll_interval_sec` | `5.0` | 空きが足りないときの再確認間隔(秒) |
| `wait_timeout_sec` | `120.0` | 回復を待つ上限(秒)。超過したらそのモデルを見送る |
| `skip_completed_on_rerun` | `false` | `true` で同じモデルの結果が既にある画像を推論から外す |

これらの既定値は**実測前の暫定値**である。RAM の余裕は lib の推論前見積もりの余裕(2GB)より大きく設定し、OS の操作性を優先した保守的な値とした。実機計測の結果が出た段階で見直す。なお、負数や型違いなどの不正な設定値は既定値へフォールバックする。

### 5. メモリ不足の扱いと保存単位

- lib が返した `OUT_OF_MEMORY` と `INSUFFICIENT_MEMORY` を `AnnotationSaveService` の記録対象コードに追加し、`error_records` へ残してエラータブで確認できるようにする。メモリ不足は画像固有の性質ではないため、再実行時の送信前フィルタ(`REFUSAL_ERROR_TYPES`)には加えない。
- アプリが受付判定で見送ったモデルは、対象画像ごとに `error_type="INSUFFICIENT_MEMORY"` として記録する(lib の推論前見積もり不足と同じ分類にし、エラータブで「メモリ不足」として並べる)。
- `ModelErrorDetail.error_code` に lib の `error_code` を載せ、サマリーダイアログでメモリ不足を他のエラーと区別して表示する。見送った画像は「失敗分を再ステージング」の対象となる。
- 保存単位はモデル単位とする。中止・見送り・後続モデルの OOM・プロセス終了のいずれが起きても、完了済みモデルの結果は保持される。
- 再実行時に完了済み画像を飛ばす仕組みは、CLI には `--missing-model` と永続実行があったが GUI には無かった。`skip_completed_on_rerun` を有効にすると、`--missing-model` と同じ判定(未リジェクトのタグ / キャプション、または score / score_label / rating の存在)で(画像, モデル)単位に除外する。意図的な再推論を黙って省略しないよう既定値は無効とする。

### 6. 表示

- 待機中は `AnnotationPhase.WAITING_FOR_MEMORY` と理由・残り秒数を `AnnotationProgress.note` でステータスバー常設部品(ADR 0108)とジョブ台帳へ表示する。
- 実行先が `cpu` と判明したモデル(現状は lib が記録する TensorFlow 系のみ)は、進捗とサマリーの「実行状況」へ表示する。実行先を取得できないモデルには何も表示しない。
- 中止時はモデルの境目で停止し、「完了した N モデルの結果は保存済み」を終端表示に出す。
- ユーザー向け文言には内部クラス名や例外文字列を含めない。

## Rationale

- **案 A(アプリがモデル単位で呼び出す)を採る理由**: 保存単位・受付・中止の粒度をすべてモデルの境目に揃えられ、lib の API を変更せずに済む。lib にコールバック(モデル完了・中止要求)を追加する案は公開 API の変更を伴い、アプリ側の判断を lib 内部のループへ持ち込むことになる。結果だけを途中で受け取る案は保存単位の問題は解決できるが、モデル実行前の受付判定を挟めない。
- **並列化しない理由**: 今回の障害は直列実行で発生しており、根本原因は 1 モデル内の入力量と見積もりの欠如だった。並列化するとモデル同士がメモリを奪い合い、受付判定の前提(判定時点の空きが実行中もおおむね残る)が崩れる。GPU 直列キュー(ADR 0066)とも整合する。並列化は実測と別の判断材料が揃ってから検討する。
- **CLI を変えない理由**: CLI はチャンク単位の保存と永続実行によって中断・再開を扱っており、完了済み結果が失われる問題は GUI 経路に固有だった。CLI へ受付判定を導入するかは別途判断する。

## Consequences

- 一括呼び出しを前提としていた `AnnotationWorker` のテストは、モデル単位の呼び出しを検証する構成へ置き換えた。
- 推論中のモデル内(画像の間)での中止は lib に引数が無いため今回の対象外とし、中止はモデルの境目と待機中にのみ効く。
- 受付判定は判定時点の空き容量を見るだけであり、推論中のピーク消費量は保証しない。推論中の超過は lib 側の小分け・推論前見積もり・OOM 検出に委ねる。
- VRAM の判定は `torch` が CUDA を初期化済みのときだけ機能する。TensorFlow 専用の GPU メモリは監視しない。
- 既定値は暫定であり、実機計測に基づく見直しと並列化は後続課題とする。

## Related

- [Issue #1468](https://github.com/NEXTAltair/LoRAIro/issues/1468)
- `image-annotator-lib` ADR 0012(Local Model Context Ownership and Resource Budgets)、ADR 0013(TensorFlow Inference Chunking, Memory Estimate and Runtime Report)
- [ADR 0033](0033-annotation-worker-batch-execution-contract.md)、[ADR 0053](0053-cli-streaming-annotation-memory-bounded-contract.md)、[ADR 0066](0066-unified-jobs-lifecycle-view.md)、[ADR 0079](0079-jobs-stage-progress-and-summary-band.md)、[ADR 0108](0108-statusbar-permanent-progress-widget.md)
