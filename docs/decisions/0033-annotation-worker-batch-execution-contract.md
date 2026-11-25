---
type: ADR
title: AnnotationWorker Batch Execution Contract
status: Accepted
timestamp: 2026-05-23
tags: []
---
# ADR 0033: AnnotationWorker Batch Execution Contract

- **関連 Issue**: #384

## Context

`AnnotationWorker`(`src/lorairo/gui/workers/annotation_worker.py`)は **N 画像 × M モデル** のアノテーション実行を担っている。しかし以下の挙動が暗黙のままとなっており、複数の不具合の根本原因になっている。

- マイグレーション用番兵値(`__legacy_<id>__`)が `models` テーブルに残存し、`name` 一致経由で推論経路へ流入する脆弱性がある。
- 内部 ID が表示名へ解決されないままサマリーダイアログへ露出する。
- 部分失敗時(1 モデルのみエラー、1 画像のみエラー、ライブラリ内の `result.error` フィールド)の UI・DB 挙動が明文化されていない。
- 進捗指標がモデル進行ベースと画像数ベースで混在している。
- `_save_error_records` の保存単位(画像パス × モデル)が暗黙である。
- `phash_list` の引き渡しが常に `None` であり、ライブラリ側の再計算に委ねている。
- `ErrorRecord` テーブルに未使用の `retry_count` カラムが存在し、設計意図と実装が乖離している(一方、`resolved_at` は Error Log Viewer の手動「解決済みマーク」UX で稼働中のため削除対象外)。

本 ADR は **LoRAIro 内部のワーカー層** の契約に絞る。なお、プロバイダー提供の Batch WebAPI は別 ADR(#395)、ライブラリの `model_name_list` 一括渡し最適化は #396 で扱う。

### 現状の挙動(実装観察)

| 観点 | 現状 |
|---|---|
| 進捗フェーズ | 5%(refusal フィルタ)→ 10–80%(モデル順次実行)→ 85%(DB 保存)→ 100% |
| 進捗単位 | `model_idx / total_models` で 70% を分配する一方、`total_count` には画像数を渡しており混在している |
| モデルループ | `for litellm_model_id in self.litellm_model_ids:` でモデル単位にライブラリを呼び出す |
| ライブラリ例外(モデル単位) | `_save_error_records` で画像 × `model_name` を保存し、`model_errors` へ追加して次モデルへ続行 |
| ライブラリ内 `result.error` | `_build_image_summary` で `if error: continue`、`_build_model_statistics` で `error_count += 1` |
| 致命例外(ワーカー全体) | 外側の `try` で全画像のエラーを記録し、例外を再送出 |
| `error_records` 保存単位 | `(image_path, model_name)` ペア。`model_name=None` は全体エラーを表す |
| `__legacy_*__` 番兵値 | ワーカーの `__init__` と `_build_model_statistics` の両方で除外(Phase 1.11 の残骸) |
| `retry_count` | スキーマに存在するがワーカー・サービスとも未使用(`retry_count=0` 固定 INSERT のみ、参照なし) |
| `resolved_at` | Error Log Viewer / Detail Dialog の手動「解決済みマーク」UX で稼働中(Decision 2 の自動リトライ不在とは独立) |
| API キー | `AnnotatorLibraryAdapter` が `ConfigurationService` から取得してライブラリへ渡す(ワーカーは無関与) |
| pHash | `phash_list=None` 固定。ライブラリ側で自動計算 |

## Decision

### 1. 進捗指標

**進捗の単位は `(画像 × モデル)` の総ステップ数を基準とする。**

- `total_steps = len(image_paths) × len(litellm_model_ids)` を進捗算定の分母とする。
- `processed_count` と `total_count` には UI 表示の分かりやすさを優先し、**画像数**を渡す。
- 進捗パーセンテージの内訳は以下で固定する。
  - 0–5%: refusal フィルタ
  - 5–90%: アノテーション実行(`(完了モデル数 × 画像数) / total_steps` で線形配分)
  - 90–95%: DB 保存
  - 95–100%: 統計集計

### 2. 部分失敗の伝播

**失敗を 3 階層に明示的に区別し、それぞれの責務を固定する。**

| 階層 | 発生源 | DB | UI ダイアログ | 続行可否 |
|---|---|---|---|---|
| L1: ライブラリ内 `result.error` | image-annotator-lib が返す想定内の失敗(レート制限、コンテンツポリシー等) | `error_records` に**保存しない**(ライブラリ側で `result.error` として伝達済み) | `model_errors` に**加える**(`model_statistics` の `error_count` に集計) | 次画像・次モデルへ続行 |
| L2: モデル単位例外 | ライブラリ呼び出しが例外を送出(ネットワーク・キャンセル以外) | `error_records` に保存(画像 × `model_name`) | `model_errors` に加える | 次モデルへ続行 |
| L3: 致命例外 | `Worker.execute` の外側 `try`(refusal フィルタ失敗、DB 接続不能等) | `error_records` に保存(画像 × `model_name=None`) | エラーダイアログとワーカー失敗シグナル | 中断 |

**重要な変更**: L1(ライブラリ `result.error`)は **`error_records` に保存しない**。ライブラリ側で `UnifiedAnnotationResult.error` としてすでに構造化されているため、DB への二重保存を避ける。これにより、`error_records` は**ワーカー自身が観測した失敗のみ**を記録するテーブルとなり、責務が明確になる。

### 3. エラー分類は `error_type` のみで扱う

**重要度(severity)の概念は導入しない。** `ErrorRecord.error_type` の自由文字列で分類する。

ワーカー層で規約化する `error_type` の予約値は以下のとおりである。

| `error_type` | 用途 |
|---|---|
| `lib_call_exception` | L2: ライブラリ呼び出しが例外で抜けた(再リトライはしない) |
| `fatal` | L3: ワーカー自身の前提崩れ(refusal フィルタ失敗、DB 接続不能等) |
| `integrity_violation` | 内部整合性違反(番兵値が推論経路に到達した等、設計バグの兆候) |

- 既存の自由文字列 `error_type`(例: `'API error'`、`'Network'`)は型名そのまま使う運用を継続する。
- 上記 3 つは予約値としてワーカーまたは保存サービスが機械的に設定する。
- スキーマ変更は行わない(`severity` カラムは新設しない)。

### 4. `_save_error_records` の保存ルール

**保存単位を「ワーカーが観測した実行失敗」に限定し、`(image_path × model_name)` ペアを 1 行とする。**

| ケース | `image_path` | `model_name` | `error_type` |
|---|---|---|---|
| L2 モデル単位例外 | 各対象画像 | 失敗モデル ID | `lib_call_exception`(または例外型名) |
| L3 致命例外 | 全対象画像 | `None` | `fatal`(または例外型名) |
| 内部整合性違反 | 該当画像 | 番兵 ID をそのまま記録 | `integrity_violation` |
| L1 ライブラリ `result.error` | (保存しない) | — | — |

### 5. API キー戦略

**ワーカー層は API キーを扱わない。`AnnotatorLibraryAdapter` がカプセル化する責務を維持する。**

- 現状の設計を確認し確定する(変更なし)。
- 将来 `api_keys` の呼び出し単位上書きが必要になった場合は、`AnnotationLogic.execute_annotation` のシグネチャ拡張で対応する(ワーカーは無関与)。

### 6. pHash 引き渡し規約

**LoRAIro 側で pHash を計算済みの場合は、`phash_list` を Worker → Logic → Adapter → ライブラリへ渡す。**

- 現状は `_run_annotation` で常に `phash_list=None` を渡しており、ライブラリ側の自動計算で二重計算が発生している。
- 変更後は `AnnotationWorker.__init__` 時点で `image_paths` から pHash を一括取得する(DB 登録済み画像は `repository.get_phashes_by_filepaths()` を使用し、未登録画像はライブラリへ委任する)。
- 引き渡しは省略可能(optional)のまま維持し、`None` の場合はライブラリ自動計算へフォールバックする。
- これにより、登録済み画像の再アノテーション時に pHash の二重計算を回避できる。

### 7. `__legacy_<id>__` 番兵値を廃止する

**ADR 0023 Phase 1.11 で導入した `litellm_model_id="__legacy_<id>__"` 番兵値を廃止し、該当行を DB から削除する。**

- マイグレーションで `models WHERE litellm_model_id LIKE '__legacy_%'` を削除する。
- 外部キーで参照する子テーブル(`annotation_results`、`tags`、`captions`、`scores`、`score_labels`、`ratings`、`error_records`、`model_function_associations` 等)の該当行も同マイグレーション内で削除する(カスケードまたは明示削除)。
- Phase 1.11 の「履歴行として保持する」という運用契約は、履歴価値より整合性リスクが上回ると判断して撤回する。
- ワーカー `__init__` の `_is_legacy_sentinel_model_id` フィルタはマイグレーション後に削除する。
- 残存する番兵値は `__manual_edit__` のみとなる。これは推論結果ではなく手動編集の保存先として正規利用されるため、整合性違反ではない。

### 8. `ErrorRecord.retry_count` カラムを削除する

**`retry_count` カラムを削除し、`resolved_at` は維持する。**

- `retry_count`: ワーカー層でリトライ管理を行う仮説のもと用意されたが、Decision 2 のとおり LoRAIro 側では自動リトライを行わないため永続的に未使用である(`db_repository.py` で `retry_count=0` 固定 INSERT のみで参照箇所なし)。
- `resolved_at`: Error Log Viewer および Error Detail Dialog の手動「解決済みマーク」機能(`mark_error_resolved` / `mark_errors_resolved_batch`)で稼働中である。Decision 2 の「自動リトライしない」方針とは独立した手動 UX 機能のため残す。
- ユーザー起点の再実行機能(失敗モデルのみの再実行など)は別 ADR または別 Issue で再検討し、必要になった時点で `retry_count` を改めて追加する。
- マイグレーションで `error_records` テーブルから `retry_count` カラムのみを削除する。

## Rationale

### なぜ 3 階層(L1 / L2 / L3)に分けるか

ライブラリ側の `result.error`(構造化された失敗)とワーカー側の `try/except`(Python 例外)を同じ `error_records` に保存すると、データの出所が辿れなくなり、ライブラリ不具合か LoRAIro 不具合かを判別できない。階層を分けることで各層の責務を固定できる。

- **L1**: プロバイダー SDK(`anthropic` / `openai` / `google-genai` / `litellm`)とライブラリが一時的障害のリトライを完了した後に残った「想定内の失敗」。回復処理(リトライや経路切替)はライブラリ側で完結しており、LoRAIro は受け取った文字列を UI 表示と統計集計に使うだけである。
- **L2**: ライブラリが想定外の例外(未捕捉の `KeyError` / `AttributeError` / `RuntimeError` 等)を送出したケース。SDK とライブラリがすでにリトライ済みのため LoRAIro 側で再リトライはしない。ワーカーは例外を捕捉して他モデルの実行継続と失敗記録のみを担い、事後調査のため `error_records` に保存する。
- **L3**: ワーカー自身の前提崩れ(refusal フィルタ失敗、DB 接続不能、キャンセル等)。バッチ全体を中断し、UI にエラーダイアログを表示する。

なお、ユーザー起点の再実行(失敗モデルのみの再実行等)は UI 設計の別 Issue とし、本 ADR のスコープ外とする。

### なぜ重要度(severity)を導入しないか

`ErrorRecord.error_type` はすでに分類を表す自由文字列カラムである。ここに重要度を別カラムで重ねると「分類 × 重要度」の 2 軸管理となり、集計クエリが複雑化する。

実際の利用者は「何の失敗か」という分類を見て対応を判断しており、重要度を独立軸として集計する需要は現時点で存在しない。`error_type` に予約値(`integrity_violation` / `fatal` / `lib_call_exception`)を設けて分類のみで分岐する方が、スキーマも集計も単純になる。

### なぜレガシー番兵値を廃止するか

第一の理由は、**過去 DB との互換性が不要である**という判断にある。`__legacy_<id>__` は Phase 1.11 で旧 DB の `litellm_model_id=NULL` 行を `UNIQUE NOT NULL` 制約へ通すための便宜的措置であり、当時は「履歴行として保持」する契約で残した。しかし LoRAIro は現在開発フェーズにあり、レガシー行に紐づく過去アノテーション履歴(`annotation_results` / `tags` / `scores` 等)を保持する業務要件はない。LoRA 学習データの生成も最新モデルによる再アノテーションが前提であり、過去履歴の提供元モデル特定が必要になる場面は想定されない。

互換保持が不要であれば番兵値を残す合理性はない。さらに「履歴行として保持し、推論経路に乗せない」という運用契約は、`name` 一致経由のクエリ(後続マイグレーションの `WHERE m.name IN (...)` 等)で容易に破られる脆弱性を抱えていた。検知機構を増やすより、行自体を削除する方が構造的に安全である。

### なぜ `ErrorRecord.retry_count` を削除するか

`retry_count` は「LoRAIro 側でリトライ管理を行う」設計仮説の遺物である。Decision 2 で LoRAIro 側の自動リトライを行わないと確定した以上、このカラムは永続的に使われない(現状も `retry_count=0` 固定 INSERT のみで参照箇所がない)。未使用カラムを残すと、将来「リトライできる前提のコード」が誤って書かれるリスクがある。必要になった時点で追加し直す方が設計意図を追いやすい。

一方、`resolved_at` は Error Log Viewer および Detail Dialog の手動「解決済みマーク」UX で稼働しているため削除対象外とする。自動リトライの不在と手動の解決済みマークは独立した責務である。

### なぜ進捗を `(画像 × モデル)` で算定するか

現状の `model_idx / total_models` による 70% 分配では、最後のモデルだけが長時間かかる場合に進捗が一気に飛ぶ。`(完了モデル数 × 画像数) / 総ステップ` を基準にすれば、視覚的に滑らかな進捗表示となる。ライブラリの `model_name_list` 一括渡し(#396)へ移行しても、ライブラリ内部はモデル単位ループのため同じ指標をそのまま利用できる。

### なぜ pHash をワーカーから渡すか

LoRAIro DB には画像登録時に計算済みの `phash` カラムがある。これをライブラリ側で毎回再計算すると、画像枚数 × モデル数に比例した無駄な計算コストが発生する。一方、未登録画像のアノテーション試走ではライブラリへの委任が正しい。したがって、省略可能引数とフォールバックの組み合わせが最適である。

## Consequences

### 良い点

- 内部整合性違反を `error_type='integrity_violation'` で集計できる。
- `error_records` テーブルが「ワーカーが観測した失敗」のみを扱う形になり、責務が明確になる。
- `__legacy_*__` 番兵値が DB から消え、`name` 一致による推論経路流入の脆弱性が根絶される。
- `retry_count` の削除により設計意図と実装が一致する(`resolved_at` は手動 UX のため維持)。
- 進捗算定が `(画像 × モデル)` で統一され、ライブラリ一括渡し移行時も契約変更が不要になる。
- 登録済み画像における pHash の二重計算が解消される。
- スキーマ変更はレガシー行削除と未使用カラム削除のみにとどまり、`severity` 新設のような追加カラムは発生しない。

### 悪い点・トレードオフ

- レガシー行と子レコードを削除するマイグレーションにより、該当モデル ID に紐づいていた過去アノテーション履歴(`annotation_results` / `tags` / `scores` 等)の一部が失われる。
- L1 を保存しなくなるため、ライブラリ `result.error` の集計は DB の `error_records` からは取得できなくなる(`annotation_results` 側のエラーフィールドから集計する運用へ統一)。
- `phash_list` 取得経路をワーカー `__init__` に追加するため DB クエリが 1 回増える(一括取得のため負荷は低い)。
- ADR 0023 Phase 1.11 の「履歴行として保持」運用契約を撤回するため、Phase 1.11 セクションへ撤回注記を追記する必要がある。

### 実装方針(分解 Issue 草案)

1. **マイグレーション A**: `models WHERE litellm_model_id LIKE '__legacy_%'` と子テーブルの参照行を削除する。
2. **マイグレーション B**: `error_records` から `retry_count` カラムを削除する(`resolved_at` は GUI 稼働中のため保持)。
3. **ワーカー修正**: マイグレーション A 後に不要となる `_is_legacy_sentinel_model_id` フィルタを削除する。
4. **ワーカー修正**: L1(ライブラリ `result.error`)を `_save_error_records` の対象から外す。
5. **ワーカー修正**: 内部整合性違反を検知した際に `error_type='integrity_violation'` で記録する。
6. **ワーカー修正**: 進捗算定を `(画像 × モデル)` 基準へ変更する。
7. **ワーカー修正**: `__init__` で pHash を一括取得し `phash_list` へ渡す。
8. **サマリーダイアログ修正**: 表示名の解決経路を追加し、`integrity_violation` を専用セクションで表示する。
9. **ADR 0023 Phase 1.11 更新**: 「履歴行として保持」運用契約の撤回を追記する。
10. **テスト追加**: L1 / L2 / L3 各階層の挙動を BDD シナリオ化する。

## Related

- ADR 0005: Annotation Layer Reorganization(3 層分離アーキテクチャ)
- ADR 0015: Manual Rating Storage Unification(書き込み・読み込み対称性、二重管理回避)
- ADR 0023 Phase 1.11: PydanticAI / LiteLLM WebAPI Inference Boundary(レガシー番兵値の導入元、本 ADR で撤回)
- ADR 0027: Score Labels DB Storage
- ADR 0030: Batch Annotation Model Selection UI
- LoRAIro #384: 本 ADR の起票元
- LoRAIro #395: プロバイダー Batch API 統合(別 ADR)
- LoRAIro #396: `annotator_adapter` で `model_name_list` を一括渡し
- 教訓: 「SSoT スキーマ変更時は読み取り側と送信側の値経路を同時に切り替える」(Issue #245)
