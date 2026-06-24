---
type: ADR
title: Provider Batch 実行 UI の個別実行フロー統一
status: Accepted
timestamp: 2026-05-29
tags: []
---
# ADR 0041: Provider Batch 実行 UI の個別実行フロー統一

- **関連 Issue**: #545 (epic), #547 (本 ADR 起票 / 設計確定), #548 (B), #549 (C), #550 (D)
- **関連 ADR**: 0030 (Batch Annotation Model Selection UI), 0036 (GUI Compound Widget 分割方針), 0038 (Provider Batch API Integration Strategy)
- **一部改訂**: ADR 0074 — ステージング集合の SSoT を `StagingWidget` から `StagingStateManager` へ移し、`StagingWidget` は view に降格 (`connect_shared_staging` 廃止)。統一フロー・共通コンポーネント構成は不変。
- **一部改訂**: ADR 0076 (Proposed) — §1 統一レイアウトの「右上に単一選択ピッカー + Submit」条項を relocation。submit の置き場を Jobs タブから Annotate の dispatch 射影へ移す。「1 submit = 1 model」不変条件・staging 共通化は不変。

## Context

GUI の Provider Batch タブ (`ProviderBatchJobWidget`) は、一枚ずつの個別実行フロー
(`tabBatchTag`) と比べて操作モデルが大きく異なる。同じアノテーション実行機能なのに、
タブごとに操作概念が変わって見え、利用者がフローを覚え直す必要がある (#545)。

調査で判明した現状差分:

| 観点 | 個別実行フロー (`tabBatchTag`) | Provider Batch タブ |
|---|---|---|
| ステージング | `BatchTagAddWidget` + `ThumbnailSelectorWidget`（サムネイル、最大500枚、`DatasetStateManager` 連携） | `lineEditImageIds`（"1, 2, 3" テキスト）+ "Use Selected" のみ |
| モデル選択 | `ModelSelectionWidget`（チェックボックス複数選択、`get_selected_models()` → litellm_model_id、`annotation_only` フィルタ） | 単一 `QComboBox`（task_type フィルタ、1モデル） |
| 実行 | `AnnotationWorkflowController.start_annotation_workflow()` | `provider_batch_workflow_service.submit_images()`（`Submit` ボタン） |
| 実装形態 | `.ui`（Qt Designer XML）+ placeholder promotion | Python 手組み (`_setup_ui()`) |
| 固有要素 | なし | task_type(annotation/rating_preflight)、endpoint マッピング、1ジョブ=1モデル制約、job 一覧/詳細/items/cancel/fetch/import |

個別実行フローのレイアウト構造 (`MainWindow.ui` の `tabBatchTag`):

```
splitterBatchTagMain (水平)
├─ 左: BatchTagAddWidget (サムネイルステージング + N/500枚 + 追加/クリア)
└─ 右: groupBoxBatchOperations
     └─ splitterBatchTagOperations (垂直)
        ├─ groupBoxAnnotation
        │    labelAnnotationTarget (◎ ステージング: N 枚)
        │    annotationFilterPlaceholder        ← フィルタ枠
        │    modelSelectionPlaceholder (ModelSelectionWidget)
        │    btnAnnotationExecute (実行)
        └─ annotationDisplayPlaceholder (結果表示)
```

`provider_batch_job_widget.py` が改修の競合ハブになるため、本 ADR で B/C/D が並列・順次に
着手できるよう **境界・制約・コンポーネント interface 契約** を先に確定する。

## Decision

### 1. 統一レイアウト（個別実行と同形 + batch 固有を限定追加）

Provider Batch タブを `tabBatchTag` と同じ「左ステージング / 右上=実行フロー / 右下=状態表示」
構造に揃える。

```
Provider Batch タブ ─ splitterMain (水平)
├─ 左: StagingWidget (個別実行と同形 — サムネイル grid / N/500枚 / [選択を追加] / [クリア])
└─ 右: splitter (垂直)
     ├─ groupBox 実行設定
     │    labelTarget (◎ ステージング: N 枚)
     │    Task: [annotation ▼]              ← filter 枠 (annotationFilterPlaceholder に対応)
     │    Model: ◉ 単一選択 (batch-capable) ← ModelSelectionWidget
     │    Prompt:[default]  Description:[____]
     │    [Submit]                          ← btnAnnotationExecute に対応
     └─ batch 固有: 状態表示                ← annotationDisplayPlaceholder に対応
          Jobs table [状態を確認] (+ running job のみ [キャンセル])
          Detail | Items
```

**対応関係**: 左=ステージング（個別実行と同一）／右上=実行フロー（target → task_type を filter 枠
→ 単一選択モデル → Submit）／右下=batch 固有の job 状態表示（個別実行の「結果表示」位置）。
これにより *基本操作の見え方は同一、差分は batch 固有設定 (task_type/prompt/description) と
状態表示 (jobs/detail/items) に限定* という #545 受け入れ条件を満たす。

### 2. 実行制約

- **1 submit = 1 batch job / 1 provider / 1 model**（複数同時実行はしない）
- モデル選択は **単一選択**（排他的に1つ）。単一モデル選択により provider も1つに固定される。
- task_type と provider/endpoint の対応（service 層 / CLI と同一 — `provider_batch_workflow_service.py`,
  `cli/commands/batch.py` の `_TASK_TYPE_ENDPOINTS` を SSoT とする）:

  | task_type | provider | endpoint | 追加条件 |
  |---|---|---|---|
  | `annotation` | openai | `/v1/chat/completions` | — |
  | `annotation` | anthropic | `/v1/messages` | — |
  | `rating_preflight` | openai | `/v1/moderations` | litellm_model_id が `openai/omni-moderation-*` |

  > **rating_preflight の制約は `openai/omni-moderation-*` で固定**する（`model_type=ratings` だけ
  > では緩い）。submit 側 `ProviderBatchWorkflowService._validate_submit_task()` は
  > rating_preflight の litellm_model_id が `openai/omni-moderation-*` でない場合に reject する。
  > batch-capable フィルタを `model_type=ratings` で緩く出すと、UI フィルタは通過するのに submit で
  > 失敗するモデルを露出してしまうため、フィルタ条件も `openai/omni-moderation-*` に揃える。

  > **注意**: `annotation` は openai / anthropic の両方が有効なため、task_type だけでは provider は
  > 一意に決まらない（provider は選択モデルが決める）。現 `ProviderBatchJobWidget` は annotation を
  > anthropic 限定にしているが、これは GUI 側のみの未対応であり、service+CLI は openai annotation
  > (`/v1/chat/completions`) を既にサポートしている（ADR 0038）。統一 GUI ではこの既存サポート経路を
  > 回帰させず、`annotation → openai` も batch-capable フィルタに含める。

### 3. ステージング共通化: 専用 `StagingWidget` を抽出

`BatchTagAddWidget` からサムネイル表示 + 状態管理部を新規 `StagingWidget` に抽出する。
`BatchTagAddWidget` は `StagingWidget` を包含し、その上にタグ入力 UI を足す形にリファクタする
（個別実行フローの挙動は不変、既存 GUI テストで担保）。Provider Batch も同コンポーネントを包含する。
ADR 0036 の compound widget 分割方針に沿った責務分離。

### 4. 実装形態: `.ui` (Qt Designer XML) 化

現状 Python 手組みの `ProviderBatchJobWidget` を、コードベース慣習に合わせて
新規 `src/lorairo/gui/designer/ProviderBatchJobWidget.ui` で定義し、`scripts/generate_ui.py`
で `ProviderBatchJobWidget_ui.py` を生成する。`StagingWidget` / `ModelSelectionWidget` は
placeholder promotion（または実行時 placeholder 差し込み）で組み込む。
widget クラスは多重継承パターン `class ProviderBatchJobWidget(QWidget, Ui_ProviderBatchJobWidget)`。

### 5. 画像 ID の取得経路

`lineEditImageIds` / "Use Selected" / `_parse_image_ids()` を廃止し、submit 対象 image ID は
`StagingWidget.get_image_ids()` から取得する。テキスト直接入力には依存しない（#545 受け入れ条件）。

### 6. task_type の置き場所

右上の filter 枠（model selection の直上）に配置する。変更時に B の batch-capable フィルタを
再評価する。UI 表示確認後に問題があれば配置を調整する（暫定確定）。

### 7. ジョブ状態操作: 主操作は「状態を確認」に絞る

Provider Batch の状態表示は、service lifecycle (`refresh` / `cancel` / `fetch` / `import`) を
そのまま主ボタンとして露出しない。通常ユーザーの主操作は **選択ジョブの状態を provider に
問い合わせる「状態を確認」だけ**に絞る。

- `更新` と `状態更新` を別々の主ボタンとして並べない。
  - `更新`: ローカル DB の job 一覧再読込にすぎず、provider への状態問い合わせではない。
  - `状態更新`: provider に問い合わせて job status を DB に反映する。
  - この 2 つは名称だけでは区別しづらく、通常フローでは「状態を確認」に統合する。
- `状態を確認` 実行後、job が完了していれば **結果取得 (`fetch`) と DB 保存 (`import`) まで
  自動で行う**。ユーザーに `取得` → `取り込み` の段階操作を要求しない。
- job が未完了なら、状態だけを更新して「処理中」「検証中」などを表示する。
- `キャンセル` は実行中/検証中など cancel 可能な状態でのみ副次操作として表示または有効化する。
- `詳細` は主ボタンにせず、行選択、詳細ペイン、または二次操作として提供する。
- `取得` / `取り込み` は通常フローの主ボタンから外す。必要な場合は、デバッグ・事故復旧・再取り込み用の
  二次操作として残す。

この決定は「ジョブ完了確認は手動でよいが、完了後の provider 結果取得と LoRAIro DB 保存を
手動ステップとして露出しすぎない」ことを目的とする。バッチ API は非同期ジョブだが、ユーザー視点の
通常フローは「送信 → 後で状態を確認 → 完了していれば保存済み」であるべきで、内部 lifecycle の
各段階を個別ボタンとして学習させない。

## コンポーネント interface 契約

B/C が実 API に対して並列着手できるよう、以下を契約として固定する。

### B: `ModelSelectionWidget` への追加 API（所有ファイル: `model_selection_widget.py`）

```python
# 単一選択モード（チェックボックスを排他的に1つだけ有効化）
def set_single_selection_mode(self, enabled: bool) -> None: ...

# batch-capable フィルタ（task_type で provider/model を絞る）
# task_type 変更時は再呼び出しで load_models() を再評価する
def set_batch_capable_filtering(
    self, enabled: bool, task_type: str, model_source: Any
) -> None: ...

# 既存。単一選択モードでは 0 or 1 要素を返す
def get_selected_models(self) -> list[str]: ...      # litellm_model_id

# 利便: 単一選択モード用
def get_selected_model(self) -> str | None: ...
```

- batch-capable 判定ロジック（現 `ProviderBatchJobWidget._direct_provider_for_model` /
  `_model_supports_task_type` / `_load_batch_capable_models` / `_litellm_id_from_batch_model`）を
  `ModelSelectionWidget`（または共有ヘルパ）へ移設し、D 側に重複実装させない。
  - `_model_supports_task_type` は上記 task_type ↔ provider/endpoint 表に従い、
    `annotation` で **openai / anthropic 両方**を許可する（anthropic 限定にしない）。
    `rating_preflight` は `openai/omni-moderation-*` のみ許可する。
- **batch-capable フィルタは direct provider route を強制する**。`ModelSelectionWidget` は通常
  `route_preference`(Issue #249) と API key 有無で direct/OpenRouter 行を `preferred` に折り畳むため、
  `route_preference=openrouter` や OpenRouter キーのみの構成では `get_selected_models()` が
  `openrouter/...` を返し得る。Provider Batch submit は direct `openai`/`anthropic` endpoint しか
  持たないため、batch-capable モードでは **route 折り畳みを無視して direct route 候補
  (`openai/...` / `anthropic/...`) を選び、direct の litellm_model_id を返す**。OpenRouter route は
  表示・選択対象から除外する（現 `ProviderBatchJobWidget` の direct-only 挙動を維持）。
- **単一選択モードでは bulk 選択コントロールを単一モード対応にする**。`select_all_models()` /
  `select_recommended_models()` は内部で `ModelCheckboxWidget.set_selected(True)` を呼び checkbox
  signal を bypass するため、単一選択モードのまま放置すると「0 or 1」保証が破れる。対応:
  単一選択モードでは対応 UI ボタン（select all / recommended 相当）を **hide / disable** し、
  メソッド側も単一モードでは no-op もしくは「最後の1つだけ選択」に倒す。
- 既存 `annotation_only` フィルタ・複数選択モードの挙動は変えない（単一選択は opt-in）。

### C: 新規 `StagingWidget` の公開 API（所有ファイル: 新規 `staging_widget.py` + テスト）

```python
class StagingWidget(QWidget):
    staged_images_changed = Signal(list)   # list[int]
    staging_cleared = Signal()
    MAX_STAGING_IMAGES = 500

    def set_dataset_state_manager(self, mgr: DatasetStateManager) -> None: ...
    def add_image_ids(self, image_ids: list[int]) -> None: ...
    def add_selected_images(self) -> None: ...   # DatasetStateManager.selected_image_ids
    def clear(self) -> None: ...
    def get_image_ids(self) -> list[int]: ...
    def count(self) -> int: ...
    # staged 画像の metadata/path アクセサ（id だけでなく filename / stored_path も返す）
    def get_staged_items(self) -> "OrderedDict[int, tuple[str, str]]": ...  # {id: (filename, stored_path)}
```

- 最大枚数・重複排除・カウント表示・サムネイル描画を `BatchTagAddWidget` と共通化する。
- **個別実行フローの path 取得経路を Wave 1 内で壊さない**。`MainWindow._get_staged_image_paths_for_annotation()`
  は現在 `batchTagAddWidget._staged_images`（`{id: (filename, stored_path)}`）から画像パスを構築している。
  `StagingWidget` 抽出時は (a) `get_staged_items()` で metadata/path を公開し、かつ
  (b) `BatchTagAddWidget._staged_images` 互換アクセサを内部 `StagingWidget` へ委譲して維持する。
  これにより `main_window.py` を触らずに（= Wave 2/D を待たずに）個別実行の execute フローが動き続ける。
  Wave 2 で `main_window.py` を `get_staged_items()` 経由に移行する。

## ファイル所有権 / Wave プラン（Agent Teams）

```
Wave 0 (1人・ブロッキング): #547 A 本 ADR + interface 契約確定
  ↓
Wave 1 (2人・完全並列・ファイル分離)
  ├─ #548 B: model_selection_widget.py (batch-capable フィルタ + 単一選択モード)
  └─ #549 C: staging_widget.py 新規抽出 + BatchTagAddWidget リファクタ
  ↓ (B の filter/単一選択 API と C の StagingWidget を消費)
Wave 2 (1人・単独所有): #550 D
  provider_batch_job_widget.py + ProviderBatchJobWidget.ui (新規) + main_window.py
  = .ui 化 + StagingWidget/ModelSelectionWidget 組込 + Submit 導線 + job パネル整理
  + テスト更新 + スクショ
```

`provider_batch_job_widget.py` を単独所有にすることで merge conflict をゼロにする
（feedback: parallel single-file placeholder-swap の教訓）。

## Rationale

### モデル選択: 単一選択に制限（複数選択 → fan-out を採らない）

- ユーザー方針「1回の処理 = 1バッチ・1プロバイダ・1モデル」に厳密一致。
- fan-out（複数選択 → モデルごとに job 生成）は UI を最も個別実行に近づけるが、1 submit で
  複数 job + コスト増が暗黙に発生し、batch のコスト管理意図と相反する。
- 「複数選択可・Submit 時に検証」は選べるのに拒否する UX ノイズになるため不採用。

### ステージング: 専用 `StagingWidget` 抽出（個別再実装 / non-Qt model 分離を採らない）

- 「ステージングは既存と同じ形が一番わかりやすい」というユーザー要望に最も忠実。
- 個別再実装は staging ロジックが2重化し将来 drift するリスク。
- non-Qt の `StagingModel` 分離は描画 widget 抽出が結局必要で作業量が増え、現時点では YAGNI。

### 実装形態: `.ui` XML 化

- 他 widget（`ModelSelectionWidget`, `BatchTagAddWidget` 等）が全て `.ui` + `generate_ui.py` 慣習。
  手組みのまま拡張すると慣習から外れ、レイアウト保守性が下がる。ユーザー指示でも XML 化を選択。

### task_type: filter 枠配置（暫定）

- task_type は model フィルタの入力（provider/model を絞る）なので、論理的に model selection の
  直上が自然。個別実行の `annotationFilterPlaceholder` 位置と対応が取れる。
- 実 UI 表示で違和感があれば D の実装中に調整する余地を残す。

## Consequences

**良い点**
- 基本操作（ステージング → モデル選択 → 実行）の見え方が個別実行と統一され、学習コストが下がる。
- `StagingWidget` 抽出で staging ロジックの単一情報源化（ADR 0036 準拠）。
- `.ui` 化でレイアウト保守が他 widget と揃う。
- ファイル所有分離により Wave 1 の B/C を安全に並列実行できる。

**悪い点 / トレードオフ**
- `BatchTagAddWidget` のリファクタは個別実行フローへの回帰リスクがあり、既存 GUI テストでの
  担保が必須。
- `.ui` 新規作成 + `ProviderBatchJobWidget` 全面書き換えは D の作業量が大きい（Wave 2 に集約）。
- 単一選択制限により、複数モデルを試したい場合は submit を複数回行う必要がある（意図的制約）。

**フォローアップ**
- task_type の配置は UI 表示確認後に再評価しうる。
- 複数モデル一括が将来必要になった場合は本 ADR を Superseded として再検討する。
- #545 の残作業として、Provider Batch の batch-capable モデル一覧が空になる原因だった
  `image-annotator-lib.list_batch_capable_models()` の None metadata guard を含む
  image-annotator-lib #129 merge commit を submodule pin に取り込む。LoRAIro 側の
  batch eligibility 判定は ADR 0038 どおり image-annotator-lib を SSoT とし、LoRAIro DB へ
  永続化しない。
- #545 の再確認で、`StagingWidget` の class は共有されていたが通常アノテーションとバッチAPIで
  state 実体が別々だったこと、およびバッチAPI側モデル選択の placeholder 置換を統合テストで
  保証していなかったことが判明した。Provider Batch タブは `BatchTagAddWidget` 側の
  `StagingWidget` と同じ staged items を共有し、UI 表示名は日本語の「バッチAPI」に統一する。