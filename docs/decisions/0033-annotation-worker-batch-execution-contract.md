# ADR 0033: AnnotationWorker バッチ実行契約

- **日付**: 2026-05-23
- **ステータス**: Accepted
- **関連 Issue**: #384

## Context

`AnnotationWorker` (`src/lorairo/gui/workers/annotation_worker.py`) は **N 画像 × M モデル**
のアノテーション実行を担うが、以下の挙動が暗黙的になっており、複数の症状の根因になっている。

- migration sentinel (`__legacy_<id>__`) が models テーブルに残存し、name 一致経由で
  推論経路へ流れ込む脆弱性
- 内部 ID がサマリーダイアログに表示名 resolve なしで露出する
- 部分失敗時 (1 モデルのみエラー / 1 画像のみエラー / lib 内 `result.error` フィールド) の UI / DB
  挙動が明文化されていない
- 進捗指標がモデル進行ベースと画像数ベースで混在
- `_save_error_records` の保存単位 (per-image-path × per-model) が暗黙
- `phash_list` 引き渡しが常に `None` で lib 側計算に委ねている
- `ErrorRecord` テーブルに未使用の `retry_count` カラムが存在し、設計意図と実装が乖離している
  (`resolved_at` は Error Log Viewer の手動「解決済みマーク」UX で live、削除対象外)

本 ADR は **LoRAIro 内部 Worker レイヤー** の契約に絞る (用語注: 「バッチAPI」= プロバイダ提供
Batch WebAPI のことを指す → 別 ADR #395)。lib `model_name_list` 一括渡し最適化は #396。

### 現状の挙動 (実装観察)

| 観点 | 現状 |
|---|---|
| 進捗フェーズ | 5% (refusal filter) → 10-80% (モデル順次) → 85% (DB保存) → 100% |
| 進捗単位 | `model_idx / total_models` で 70% を分配。`total_count` は画像数を渡す (混在) |
| モデルループ | `for litellm_model_id in self.litellm_model_ids:` で per-model に lib 呼び出し |
| lib 例外 (per-model) | `_save_error_records` で per-image × model_name 保存、`model_errors` 追加、次モデル続行 |
| lib 内 `result.error` | `_build_image_summary` で `if error: continue`、`_build_model_statistics` で `error_count += 1` |
| 致命例外 (Worker 全体) | outer try で全画像エラー記録 + raise |
| error_records 単位 | (image_path, model_name) ペア。model_name=None は全体エラー |
| `__legacy_*__` sentinel | Worker `__init__` で除外、`_build_model_statistics` でも除外 (Phase 1.11 残骸) |
| `retry_count` | スキーマに存在するが Worker / Service 共に未使用 (`retry_count=0` 固定 INSERT のみ、参照なし) |
| `resolved_at` | Error Log Viewer / Detail Dialog の手動「解決済みマーク」UX で live (Decision 2 の自動 retry 不在とは独立) |
| API key | `AnnotatorLibraryAdapter` が ConfigurationService から取得して lib に渡す (Worker は無関与) |
| pHash | `phash_list=None` 固定。lib 側自動計算 |

## Decision

### 1. 進捗指標

**進捗の単位は `(画像 × モデル)` の総ステップ数を基準とする。**

- `total_steps = len(image_paths) × len(litellm_model_ids)` を進捗算定の分母とする
- `processed_count` / `total_count` は **画像数** を渡す (UI 表示の親しみやすさ優先)
- 進捗パーセンテージの内訳 (固定):
  - 0-5%: refusal filter
  - 5-90%: アノテーション実行 (`(完了モデル数 × 画像数) / total_steps` で線形配分)
  - 90-95%: DB 保存
  - 95-100%: 統計集計

### 2. 部分失敗の伝播

**3 階層を明示的に区別し、それぞれの責務を固定する。**

| 階層 | 発生源 | DB | UI ダイアログ | 続行 |
|---|---|---|---|---|
| L1: lib 内 `result.error` | image-annotator-lib が返す期待された失敗 (rate limit, content policy 等) | `error_records` に **保存しない** (lib 側で result.error として伝達済み) | `model_errors` に **加える** (model_statistics の error_count に集計) | 次画像・次モデル続行 |
| L2: per-model 例外 | lib 呼び出しが例外を raise (ネットワーク・キャンセル以外) | `error_records` に保存 (per-image × model_name) | `model_errors` に加える | 次モデル続行 |
| L3: 致命例外 | Worker.execute の outer try (refusal filter 失敗・DB 接続不能等) | `error_records` に保存 (per-image × model_name=None) | エラーダイアログ + Worker 失敗 Signal | 中断 |

**重要な変更**: L1 (lib `result.error`) を **error_records に保存しない**。
- 理由: lib 側で `UnifiedAnnotationResult.error` として既に構造化されており、DB に二重保存しない
- 影響: error_records は **Worker 自身が観測した失敗のみ** を記録するテーブルになる (責務明確化)

### 3. エラー分類は `error_type` のみで扱う

**重要度 (severity) の概念は導入しない。** `ErrorRecord.error_type` の自由文字列で分類する。

`error_type` の予約値 (Worker レイヤーで規約化):

| `error_type` | 用途 |
|---|---|
| `lib_call_exception` | L2: lib 呼び出しが例外で抜けた (再 retry はしない) |
| `fatal` | L3: Worker 自身の前提崩れ (refusal filter / DB 接続等) |
| `integrity_violation` | 内部整合性違反 (sentinel が推論経路に到達した等、設計バグの兆候) |

- 既存の自由文字列 `error_type` (例: `'API error'`, `'Network'`) は型名そのまま使う運用を継続
- 上記 3 つは予約値として Worker / Save Service が機械的にセットする
- スキーマ変更なし (severity カラム新設しない)

### 4. `_save_error_records` 保存ルール

**保存単位を「Worker が観測した実行失敗」に限定し、(image_path × model_name) ペアを 1 row とする。**

| ケース | image_path | model_name | error_type |
|---|---|---|---|
| L2 per-model 例外 | 各対象画像 | 失敗モデル ID | `lib_call_exception` (or 例外型名) |
| L3 致命例外 | 全対象画像 | `None` | `fatal` (or 例外型名) |
| 内部整合性違反 | 該当画像 | sentinel ID をそのまま記録 | `integrity_violation` |
| L1 lib `result.error` | (保存しない) | — | — |

### 5. API key 戦略

**Worker レイヤーは API key を扱わない。`AnnotatorLibraryAdapter` がカプセル化する責務を維持。**

- 現状の設計を確認・確定する (変更なし)
- 将来 `api_keys` の per-call override が必要になった場合は `AnnotationLogic.execute_annotation`
  の signature 拡張で対応 (Worker は無関与)

### 6. pHash 引き渡し規約

**LoRAIro 側で既に pHash 計算済みの場合は `phash_list` を Worker → Logic → Adapter → lib に渡す。**

- 現状: `_run_annotation` で常に `phash_list=None` (lib 側自動計算で二重計算発生)
- 変更: `AnnotationWorker.__init__` 時点で **画像 image_paths から pHash を一括取得**
  (DB に登録済みであれば `repository.get_phashes_by_filepaths()`、未登録は lib 委任)
- 引き渡しは optional のまま (None なら lib 自動計算へフォールバック)
- 効果: registered images のアノテーション再実行時に pHash 二重計算を回避

### 7. `__legacy_<id>__` sentinel を廃止する

**ADR 0023 Phase 1.11 で導入した `litellm_model_id="__legacy_<id>__"` sentinel を廃止し、
該当行を DB から削除する。**

- migration で `models WHERE litellm_model_id LIKE '__legacy_%'` を削除
- FK で参照する子テーブル (`annotation_results`, `tags`, `captions`, `scores`,
  `score_labels`, `ratings`, `error_records`, `model_function_associations` 等) の該当行も
  同 migration 内で削除 (cascade or 明示)
- Phase 1.11 で「履歴行として保持」と書かれた運用契約を撤回する (履歴価値より整合性リスクが
  上回ると判断)
- Worker `__init__` の `_is_legacy_sentinel_model_id` フィルタは migration 後に削除
- 残存 sentinel は `__manual_edit__` のみとなる。これは推論結果保存先として正規利用される
  ため、整合性違反ではない

### 8. `ErrorRecord.retry_count` カラムを削除する

**`retry_count` カラムを削除する。`resolved_at` は残す。**

- `retry_count`: 「Worker レイヤーで retry トラッキングする」設計を見越して用意されたが、
  Decision 2 のとおり **LoRAIro 側で自動 retry はしない**ため、永続的に未使用
  (`db_repository.py` で `retry_count=0` 固定 INSERT のみ、参照箇所なし)
- `resolved_at`: **残す**。Error Log Viewer / Error Detail Dialog で手動「解決済みマーク」
  機能 (`mark_error_resolved` / `mark_errors_resolved_batch`) が live。Decision 2 の
  「自動 retry はしない」とは独立した手動 UX 機能
- ユーザー起点の再実行機能 (失敗モデルのみ rerun 等) は別 ADR / 別 Issue で再検討する。
  そのときに必要なら `retry_count` を新規追加し直す
- migration で `error_records` テーブルから `retry_count` のみ drop

## Rationale

### なぜ 3 階層に分けるか (L1/L2/L3)

lib 側の `result.error` (構造化された失敗) と Worker 側の `try/except` (Python 例外) を同一の
error_records に保存すると、データの出所が辿れなくなり「lib バグなのか LoRAIro バグなのか」が
分からない。階層を分けることで責務が固定される:

- L1: provider SDK (`anthropic` / `openai` / `google-genai` / `litellm`) と lib が transient
  retry を完了した上で残った「期待された失敗」。回復処理 (retry / 別 route 切替) は lib 側で
  完結しており、LoRAIro は受け取った文字列を UI 表示と統計集計に使うだけ。
- L2: lib が想定外の例外を raise したケース (uncaught KeyError / AttributeError / RuntimeError 等)。
  LoRAIro 側で **再 retry はしない** (SDK / lib が既に試行済み)。Worker は捕捉して他モデル続行と
  失敗記録だけを担う。lib のバグまたは inputs 不整合が疑われるため `error_records` に保存して
  事後調査可能にする。
- L3: Worker 自身の前提崩れ (refusal filter 失敗・DB 接続不能・キャンセル等)。バッチ全体を
  中断し、UI にエラーダイアログを出す。

ユーザー起点の再実行 (失敗モデルのみ rerun 等) は本 ADR のスコープ外 (UI 設計の別 Issue)。

### なぜ severity を導入しないか

`ErrorRecord.error_type` は既に「分類」を表す自由文字列カラム。ここに重要度を別カラムとして
重ねると 2 軸 (分類 × 重要度) の組み合わせ管理になり、集計クエリが複雑化する。

実態として LoRAIro の error_records 利用者は「何の失敗か」(分類) を見て対応を判断する。
重要度を独立軸として扱う集計需要は現時点で存在しない。`error_type` に予約値
(`integrity_violation` / `fatal` / `lib_call_exception`) を導入して分類のみで分岐可能にする方が
スキーマも集計も単純。

### なぜ legacy sentinel を廃止するか

第一の理由は **過去 DB との互換性がもはや不要** という判断。`__legacy_<id>__` は Phase 1.11 で
旧 DB の `litellm_model_id=NULL` 行を UNIQUE NOT NULL 制約に通すための便宜的措置で、当時は
「履歴行として保持」運用契約で残した。しかし現時点で LoRAIro は開発フェーズであり、過去
アノテーション履歴 (legacy 行に紐付く `annotation_results` / `tags` / `scores` 等) を保持する
業務要件は存在しない。LoRA 学習データ生成も最新モデル出力で再アノテーションする運用が前提で、
過去履歴の提供元モデル特定が必要になるケースは想定されない。

互換保持が不要であれば、sentinel を残す合理性はない。さらに「履歴行として保持・推論経路には
乗らない」運用契約は name 一致経由のクエリ (後続 migration の `WHERE m.name IN (...)` 等) で
容易に破られる脆弱性も抱えていた。検知機構を増やすより、行自体を削除する方が構造的に安全。

### なぜ ErrorRecord の `retry_count` を消すか

`retry_count` は「LoRAIro 側で retry 管理する」設計仮説の遺物。Decision 2 で「LoRAIro 側で
自動 retry はしない」と確定するため、このカラムは永続的に使われない (現状も `retry_count=0`
固定 INSERT のみで、参照箇所なし)。dead column を残すと将来「retry できる前提のコード」が誤って
書かれるリスクがある。必要になったときに改めて追加し直す方が、設計意図の追跡が容易。

なお `resolved_at` は Error Log Viewer / Detail Dialog で手動「解決済みマーク」UX として live で
使われているため、本 ADR の削除対象外。Decision 2 (自動 retry 不在) と「手動 resolved マーク」は
独立した責務。

### なぜ進捗を `(画像 × モデル)` で算定するか

現状は `model_idx / total_models` で 70% 分配しているが、これだと「最後のモデルだけが時間
かかる」場合に進捗が一気に飛ぶ。`(完了モデル × 画像数) / 総ステップ` で見ると視覚的に滑らか。
lib `model_name_list` 一括渡し (#396) に移行しても、lib 内部は per-model ループなので
このメトリクスはそのまま使える。

### なぜ pHash を Worker から渡すか

LoRAIro DB には既に `phash` カラムがあり、画像登録時に計算済み。lib 側で再計算するのは
冗長 (画像枚数 × モデル数の倍率で計算コストがかかる)。一方、未登録画像 (アノテーション
試走) では lib 委任が正しい。optional + フォールバックが最適。

## Consequences

### 良い点

- 内部整合性違反が `error_type='integrity_violation'` で集計可能になる
- error_records テーブルが「Worker 観測の失敗」のみになり、責務が明確
- `__legacy_*__` sentinel が DB から消え、name 一致による推論経路流入の脆弱性が根絶される
- `retry_count` 削除で設計意図と実装が一致する (`resolved_at` は手動 UX のため維持)
- 進捗算定が `(画像 × モデル)` で統一され、lib 一括渡し移行時も契約変更不要
- pHash 二重計算が解消 (登録済み画像)
- スキーマ変更は legacy 行削除 + 未使用カラム drop のみ。severity 新設のような追加カラムなし

### 悪い点・トレードオフ

- legacy 行 + 子レコードの削除 migration で過去アノテーション履歴が一部失われる
  (該当モデル ID で紐付いていた annotation_results / tags / scores 等)
- L1 を保存しなくなる変更で、lib `result.error` 集計が DB の error_records からは取れなくなる
  (annotation_results 側の error フィールドから取る運用に統一)
- `phash_list` 取得経路を Worker `__init__` に追加 → DB クエリ 1 回増 (一括取得なので安価)
- ADR 0023 Phase 1.11 の「履歴行として保持」運用契約を撤回するため、Phase 1.11 セクションに
  撤回明記が必要

### 実装方針 (分解 Issue 草案)

1. **migration A**: `models WHERE litellm_model_id LIKE '__legacy_%'` と子テーブルの参照行を
   削除
2. **migration B**: `error_records` から `retry_count` カラムを drop (`resolved_at` は GUI live のため保持)
3. **Worker 修正**: `_is_legacy_sentinel_model_id` フィルタを削除 (migration A 後に不要)
4. **Worker 修正**: L1 (lib `result.error`) を `_save_error_records` 対象から外す
5. **Worker 修正**: 内部整合性違反検知時に `error_type='integrity_violation'` で記録
6. **Worker 修正**: 進捗算定を `(画像 × モデル)` に変更
7. **Worker 修正**: `__init__` で pHash を一括取得し `phash_list` に渡す
8. **Summary Dialog 修正**: 表示名 resolve 経路を追加、`integrity_violation` は専用セクションで表示
9. **ADR 0023 Phase 1.11 更新**: 「履歴行として保持」運用契約の撤回を追記
10. **テスト追加**: L1/L2/L3 各階層の挙動を BDD シナリオ化

## Related

- ADR 0005: Annotation Layer Reorganization (3 層分離アーキテクチャ)
- ADR 0015: Manual Rating Storage Unification (書き込み/読み込み対称性、二重管理回避)
- ADR 0023 Phase 1.11: PydanticAI/LiteLLM WebAPI Inference Boundary (legacy sentinel 導入元、本 ADR で撤回)
- ADR 0027: Score Labels DB Storage
- ADR 0030: Batch Annotation Model Selection UI
- LoRAIro #384: 本 ADR の起票元
- LoRAIro #395: プロバイダ Batch API 統合 (別 ADR)
- LoRAIro #396: annotator_adapter で model_name_list を一括渡し
- Lesson: 「SSoT スキーマ変更時は読み取り側 + 送信側の値経路を同時に切替える」(Issue #245)
