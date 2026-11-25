---
type: ADR
title: Provider Batch 実行 UI の個別実行フロー統一
status: Accepted
timestamp: 2026-05-29
tags: []
---
# ADR 0041: Provider Batch 実行 UI の個別実行フロー統一

- **関連 Issue**: #545(epic)、#547(本 ADR 起票・設計確定)、#548(B)、#549(C)、#550(D)
- **関連 ADR**: 0030(Batch Annotation Model Selection UI)、0036(GUI Compound Widget 分割方針)、0038(Provider Batch API Integration Strategy)
- **一部改訂**: ADR 0074 — ステージング集合の SSoT を `StagingWidget` から `StagingStateManager` へ移し、`StagingWidget` をビューに降格した(`connect_shared_staging` 廃止)。統一フローおよび共通コンポーネント構成は不変である。
- **一部改訂**: ADR 0076 — §1 統一レイアウトの「右上に単一選択ピッカー+Submit」条項を移設した。送信操作の配置先を Jobs タブから Annotate のディスパッチ射影へ移している。「1 submit = 1 model」の不変条件とステージング共通化は不変である。

## Context

GUI の Provider Batch タブ(`ProviderBatchJobWidget`)は、1 枚ずつの個別実行フロー(`tabBatchTag`)と比べて操作モデルが大きく異なっていた。同じアノテーション実行機能であるにもかかわらず、タブごとに操作概念が変わって見えるため、利用者がフローを覚え直す必要があった(#545)。

調査で判明した現状の差分は以下のとおりである。

| 観点 | 個別実行フロー(`tabBatchTag`) | Provider Batch タブ |
|---|---|---|
| ステージング | `BatchTagAddWidget` と `ThumbnailSelectorWidget`(サムネイル表示、最大 500 枚、`DatasetStateManager` 連携) | `lineEditImageIds`(`"1, 2, 3"` のテキスト入力)と `"Use Selected"` のみ |
| モデル選択 | `ModelSelectionWidget`(チェックボックス複数選択、`get_selected_models()` → `litellm_model_id`、`annotation_only` フィルタ) | 単一 `QComboBox`(`task_type` フィルタ、1 モデル) |
| 実行 | `AnnotationWorkflowController.start_annotation_workflow()` | `provider_batch_workflow_service.submit_images()`(`Submit` ボタン) |
| 実装形態 | `.ui`(Qt Designer XML)+プレースホルダー置換 | Python 手組み(`_setup_ui()`) |
| 固有要素 | なし | `task_type`(`annotation` / `rating_preflight`)、エンドポイントマッピング、1 ジョブ = 1 モデル制約、ジョブ一覧・詳細・項目・キャンセル・取得・取り込み |

個別実行フローのレイアウト構造(`MainWindow.ui` の `tabBatchTag`):

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

`provider_batch_job_widget.py` が改修時の競合ハブになるため、本 ADR では B・C・D の作業者が並列および順次で着手できるよう、**境界、制約、コンポーネントのインターフェース契約**を先に確定する。

## Decision

### 1. 統一レイアウト(個別実行と同形+バッチ固有要素の限定追加)

Provider Batch タブを、`tabBatchTag` と同じ「左:ステージング、右上:実行フロー、右下:状態表示」の構造に揃える。

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

各領域の対応関係は次のとおりである。

- **左**:ステージング(個別実行と同一)
- **右上**:実行フロー(対象件数、`task_type` のフィルタ枠、単一選択モデル、Submit ボタン)
- **右下**:バッチ固有のジョブ状態表示(個別実行の「結果表示」位置に対応)

これにより、「基本操作の見え方は同一とし、差分はバッチ固有設定(`task_type`・`prompt`・`description`)と状態表示(ジョブ一覧・詳細・項目)に限定する」という #545 の受け入れ条件を満たす。

### 2. 実行制約

- **1 回の送信 = 1 バッチジョブ・1 プロバイダ・1 モデル**とする(複数モデルの同時実行は行わない)。
- モデル選択は排他的な**単一選択**とする。モデルを 1 つに絞ることで、プロバイダも自動的に 1 つに確定する。
- `task_type` とプロバイダ・エンドポイントの対応は、サービス層および CLI と同一とする(`provider_batch_workflow_service.py` および `cli/commands/batch.py` の `_TASK_TYPE_ENDPOINTS` を SSoT とする)。

| `task_type` | provider | endpoint | 追加条件 |
|---|---|---|---|
| `annotation` | openai | `/v1/chat/completions` | — |
| `annotation` | anthropic | `/v1/messages` | — |
| `rating_preflight` | openai | `/v1/moderations` | `litellm_model_id` が `openai/omni-moderation-*` |

> **`rating_preflight` の制約は `openai/omni-moderation-*` で固定する**(`model_type=ratings` だけでは緩すぎる)。送信側の `ProviderBatchWorkflowService._validate_submit_task()` は、`rating_preflight` の `litellm_model_id` が `openai/omni-moderation-*` でない場合に拒否する。UI フィルタを `model_type=ratings` で緩くすると、選択できるのに送信時に失敗するモデルが露出してしまうため、フィルタ条件も `openai/omni-moderation-*` に揃える。

> **注意**:`annotation` は `openai` と `anthropic` の双方が有効であるため、`task_type` だけではプロバイダが一意に決まらない(選択モデルがプロバイダを決める)。既存の `ProviderBatchJobWidget` は `annotation` を `anthropic` 限定としていたが、これは GUI 側の未対応によるものであり、サービス層と CLI はすでに OpenAI の `annotation`(`/v1/chat/completions`)をサポートしている(ADR 0038)。統一 GUI ではこの既存サポート経路を後退させず、`annotation` における `openai` もバッチ対応フィルタに含める。

### 3. ステージング共通化:専用 `StagingWidget` の抽出

`BatchTagAddWidget` からサムネイル表示と状態管理の部分を切り出し、新規の `StagingWidget` として抽出する。`BatchTagAddWidget` は `StagingWidget` を包含し、その上にタグ入力 UI を重ねる形へリファクタリングする(個別実行フローの挙動は変えず、既存の GUI テストで担保する)。Provider Batch タブもこの `StagingWidget` を包含する。これは ADR 0036 の複合ウィジェット分割方針に沿った責務分離である。

### 4. 実装形態:`.ui`(Qt Designer XML)化

現在 Python 手組みとなっている `ProviderBatchJobWidget` を、コードベースの慣習に合わせて新規の `src/lorairo/gui/designer/ProviderBatchJobWidget.ui` で定義する。`scripts/generate_ui.py` を用いて `ProviderBatchJobWidget_ui.py` を生成し、`StagingWidget` および `ModelSelectionWidget` はプレースホルダー昇格(または実行時のプレースホルダー差し込み)で組み込む。ウィジェットクラスは多重継承パターン `class ProviderBatchJobWidget(QWidget, Ui_ProviderBatchJobWidget)` を採用する。

### 5. 画像 ID の取得経路

`lineEditImageIds`、`"Use Selected"`、および `_parse_image_ids()` を廃止する。送信対象の画像 ID は `StagingWidget.get_image_ids()` から取得し、テキスト直接入力には依存しない(#545 の受け入れ条件)。

### 6. `task_type` の配置場所

右上のフィルタ枠(モデル選択の直上)に配置する。`task_type` が変更された際は、B が実装するバッチ対応フィルタを再評価する。なお、この配置は暫定確定とし、実 UI の表示確認後に問題があれば調整する。

### 7. ジョブ状態操作:主操作は「状態を確認」に絞る

Provider Batch の状態表示では、サービス層のライフサイクル操作(`refresh`、`cancel`、`fetch`、`import`)をそのまま主ボタンとして露出させない。通常利用者の主操作は、**選択ジョブの状態をプロバイダへ問い合わせる「状態を確認」だけ**に絞る。

- `更新` と `状態更新` を別々の主ボタンとして並べない。
  - `更新` はローカル DB のジョブ一覧を再読込するだけであり、プロバイダへの問い合わせではない。
  - `状態更新` はプロバイダへ問い合わせてジョブ状態を DB に反映する操作である。
  - この 2 つは名称だけでは区別しにくいため、通常フローでは「状態を確認」へ統合する。
- 「状態を確認」の実行後、ジョブが完了していれば**結果取得(`fetch`)と DB 保存(`import`)まで自動実行する**。利用者に「取得 → 取り込み」という段階操作を要求しない。
- ジョブが未完了であれば、状態だけを更新して「処理中」「検証中」などを表示する。
- `キャンセル` は、実行中や検証中などキャンセル可能な状態でのみ副次操作として表示または有効化する。
- `詳細` は主ボタンにせず、行選択、詳細ペイン、または二次操作として提供する。
- `取得` と `取り込み` は通常フローの主ボタンから外す。必要な場合のみ、デバッグ・事故復旧・再取り込み用の二次操作として残す。

この決定は、「ジョブ完了の確認は手動でよいが、完了後の結果取得と DB 保存を手動ステップとして過剰に露出させない」ことを目的としている。バッチ API は非同期ジョブであるが、利用者視点の通常フローは「送信 → 後で状態を確認 → 完了していれば保存済み」であるべきであり、内部ライフサイクルの各段階を個別ボタンとして学習させない。

## コンポーネント interface 契約

B と C が実 API に対して並列着手できるよう、以下のインターフェースを契約として固定する。

### B:`ModelSelectionWidget` への追加 API(所有ファイル:`model_selection_widget.py`)

```python
# 単一選択モード(チェックボックスを排他的に1つだけ有効化)
def set_single_selection_mode(self, enabled: bool) -> None: ...

# batch-capable フィルタ(task_type で provider/model を絞る)
# task_type 変更時は再呼び出しで load_models() を再評価する
def set_batch_capable_filtering(
    self, enabled: bool, task_type: str, model_source: Any
) -> None: ...

# 既存。単一選択モードでは 0 or 1 要素を返す
def get_selected_models(self) -> list[str]: ...      # litellm_model_id

# 利便: 単一選択モード用
def get_selected_model(self) -> str | None: ...
```

実装要件は以下のとおりである。

- バッチ対応判定ロジック(現行の `ProviderBatchJobWidget._direct_provider_for_model`、`_model_supports_task_type`、`_load_batch_capable_models`、`_litellm_id_from_batch_model`)を `ModelSelectionWidget` または共有ヘルパーへ移設し、D 側へ重複実装させない。
  - `_model_supports_task_type` は前述の対応表に従い、`annotation` では **`openai` と `anthropic` の両方**を許可する(`anthropic` 限定にしない)。`rating_preflight` は `openai/omni-moderation-*` のみ許可する。
- **バッチ対応フィルタはプロバイダ直接経路を強制する**。`ModelSelectionWidget` は通常、`route_preference`(Issue #249)と API キー有無に応じて直接経路と OpenRouter 行を `preferred` に折り畳む。そのため、`route_preference=openrouter` や OpenRouter キーのみの環境では `get_selected_models()` が `openrouter/...` を返し得る。Provider Batch 送信は直接の `openai` および `anthropic` エンドポイントしか持たないため、バッチ対応モードでは**経路折り畳みを無視して直接経路候補(`openai/...`、`anthropic/...`)を選び、直接経路の `litellm_model_id` を返す**。OpenRouter 経路は表示・選択対象から除外する。
- **単一選択モードでは一括選択コントロールを単一モード対応にする**。`select_all_models()` や `select_recommended_models()` は内部で `ModelCheckboxWidget.set_selected(True)` を呼んでチェックボックスのシグナルを迂回するため、放置すると「0 または 1 件」の保証が破れる。単一選択モードでは対応する UI ボタン(全選択・推奨選択)を非表示または無効化し、メソッド側も単一モードでは何もしない(no-op)か最後の 1 件のみ選択する挙動へ倒す。
- 既存の `annotation_only` フィルタおよび複数選択モードの挙動は変更しない(単一選択は明示的な有効化とする)。

### C:新規 `StagingWidget` の公開 API(所有ファイル:新規 `staging_widget.py`+テスト)

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
    # staged 画像の metadata/path アクセサ(id だけでなく filename / stored_path も返す)
    def get_staged_items(self) -> "OrderedDict[int, tuple[str, str]]": ...  # {id: (filename, stored_path)}
```

実装要件は以下のとおりである。

- 最大枚数、重複排除、カウント表示、サムネイル描画を `BatchTagAddWidget` と共通化する。
- **個別実行フローのパス取得経路を Wave 1 内で壊さない**。現在 `MainWindow._get_staged_image_paths_for_annotation()` は `batchTagAddWidget._staged_images`(`{id: (filename, stored_path)}`)から画像パスを構築している。`StagingWidget` 抽出時は、(a) `get_staged_items()` でメタデータとパスを公開し、かつ (b) `BatchTagAddWidget._staged_images` 互換アクセサを内部の `StagingWidget` へ委譲して維持する。これにより `main_window.py` を触らずに(Wave 2 / D を待たずに)個別実行フローが動作し続ける。Wave 2 で `main_window.py` を `get_staged_items()` 経由へ移行する。

## ファイル所有権 / Wave プラン(Agent Teams)

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

`provider_batch_job_widget.py` を単独所有とすることで、マージ競合をゼロにする(同一ファイルの並列プレースホルダー置換で競合した過去の教訓を反映)。

## Rationale

### モデル選択:単一選択に制限する理由

- 「1 回の処理 = 1 バッチ・1 プロバイダ・1 モデル」というユーザー方針に厳密に一致する。
- 複数選択からモデルごとにジョブを生成する方式(fan-out)は UI を個別実行に近づけられるが、1 回の送信で複数ジョブとコスト増加が暗黙に発生し、バッチ処理のコスト管理意図と相反する。
- 「複数選択を許可しつつ送信時に検証で弾く」方式は、選べるのに拒否される UX ノイズを生むため不採用とした。

### ステージング:専用 `StagingWidget` を抽出する理由

- 「ステージングは既存と同じ形が最も分かりやすい」というユーザー要望に最も忠実である。
- タブごとに個別再実装するとステージングロジックが二重化し、将来の乖離リスクが生じる。
- 非 Qt の `StagingModel` を分離する案は、結局描画ウィジェットの抽出も必要となって作業量が増えるため、現時点では過剰設計(YAGNI)と判断した。

### 実装形態:`.ui` XML 化する理由

- 他のウィジェット(`ModelSelectionWidget`、`BatchTagAddWidget` など)がすべて `.ui` と `generate_ui.py` の慣習に従っている。手組みのまま拡張すると慣習から外れてレイアウト保守性が低下する。ユーザー指示でも XML 化が選択された。

### `task_type`:フィルタ枠へ配置する理由(暫定)

- `task_type` はプロバイダおよびモデルを絞り込むフィルタ入力であるため、モデル選択の直上に置くのが論理的に自然である。個別実行の `annotationFilterPlaceholder` とも位置の対応が取れる。
- 実 UI の表示確認で違和感があれば、D の実装中に調整できる余地を残す。

## Consequences

### 良い点

- 基本操作(ステージング → モデル選択 → 実行)の見え方が個別実行と統一され、学習コストが下がる。
- `StagingWidget` の抽出により、ステージングロジックが単一情報源化される(ADR 0036 準拠)。
- `.ui` 化によりレイアウトの保守方法が他ウィジェットと揃う。
- ファイル所有権の分離により、Wave 1 の B と C を安全に並列実行できる。

### 悪い点・トレードオフ

- `BatchTagAddWidget` のリファクタリングは個別実行フローへの回帰リスクを伴うため、既存 GUI テストによる担保が必須である。
- `.ui` の新規作成と `ProviderBatchJobWidget` の全面書き換えにより、D(Wave 2)の作業量が大きくなる。
- 単一選択制限により、複数モデルを試したい場合は送信を複数回行う必要がある(意図的な制約)。

### フォローアップ

- `task_type` の配置は UI 表示確認後に再評価し得る。
- 複数モデルの一括実行が将来必要になった場合は、本 ADR を Superseded として再検討する。
- #545 の残作業として、Provider Batch のバッチ対応モデル一覧が空になる原因であった `image-annotator-lib.list_batch_capable_models()` の None メタデータガードを含む `image-annotator-lib#129` マージコミットをサブモジュール pin に取り込む。LoRAIro 側のバッチ対応判定は ADR 0038 どおり `image-annotator-lib` を SSoT とし、LoRAIro DB へ永続化しない。
- #545 の再確認で、`StagingWidget` のクラスは共有されていたものの通常アノテーションとバッチ API で状態実体が別々であったこと、およびバッチ API 側のモデル選択プレースホルダー置換が統合テストで保証されていなかったことが判明した。Provider Batch タブは `BatchTagAddWidget` 側の `StagingWidget` と同一のステージング項目を共有し、UI 表示名は日本語の「バッチAPI」に統一する。
