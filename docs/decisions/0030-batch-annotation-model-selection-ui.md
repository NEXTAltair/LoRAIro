# ADR 0030: Batch Annotation Model Selection UI

- **日付**: 2026-05-20
- **ステータス**: Accepted

## Context

Batch Tag のアノテーション設定 UI は、モデル選択の入口が複数あり、現在の適用条件をユーザーが
読み取りにくい。

現在の主な構成は以下。

- `AnnotationFilterWidget`
  - 機能タイプ: `Caption生成` / `Tag生成` / `品質スコア`
  - 実行環境: `Web API` / `ローカルモデル`
- `ModelSelectionWidget`
  - 一覧上部に `executionEnvCombo` (`すべて` / `APIモデルのみ` / `ローカルモデルのみ`)
  - `apply_filters(provider, capabilities, exclude_local, execution_env)` で複数条件を受ける
- `WidgetSetupService`
  - `AnnotationFilterWidget.filter_changed` を `ModelSelectionWidget.apply_filters()` に接続
  - 空の `capabilities` を `["caption", "tags", "scores"]` に置換

この構成では、実行環境フィルタが二系統に分かれ、さらに UI のチェック状態と実際の適用条件が
一致しない。結果として「表示されない」「絞り込みが効いているのか分からない」という体験になる。

関連 Issue:

- LoRAIro #298: provider=None のローカル/APIモデル判定とフィルタ条件の不整合
- LoRAIro #299: 空の機能フィルタ時にデフォルト上書きされ全件表示が不可能
- LoRAIro #300: モデル実行環境フィルタが複数 UI 経路で分断され UX が不明瞭

### Historical Background

この UI は一度に設計されたものではなく、複数回の段階的統合と不具合回避の積み重ねで現在の形に
なっている。

- 2025-07-29: `924e1f0d` (`feat: Add hybrid annotation UI prototype and supporting components`)
  - multi-model annotation interface の基礎として `ModelSelectionWidget` が追加された。
- 2025-07-29: `3a2e44f5`
  (`feat: Complete Phase 1 hybrid annotation UI implementation and plan Phase 2.5 architecture refactoring`)
  - `AnnotationControlWidget` が追加され、当時の設計書
    `tasks/plans/hybrid_annotation_ui_comprehensive_design_plan_20250729.md` では
    「実行環境選択 (Web API / ローカルモデル)」と「機能タイプ選択」を持つ設計だった。
  - 同設計書は「既存ウィジェット最大活用」「デッドコード削除」を掲げていたが、後続で UI が分割され、
    一部の責務が複数 Widget に残った。
- 2025-07-30: `4043e581`
  (`feat: Complete Phase 2.5 architectural refactoring with unified filter system`)
  - Qt Designer + Service layer 分離の一環として `ModelSelectionWidget.ui` と
    `ModelSelectionService` が整備された。
- 2025-08-06: `88203110`
  (`feat: complete Phase 4 ModelSelectionWidget integration`)
  - `ModelSelectionWidget` が `ModelSelectionCriteria` を使う高度なフィルタリング UI として
    近代化された。この時点で汎用性・後方互換性を重視した設計が入った。
- 2026-01-21: `9ebe8733`
  (`feat: Add AnnotationFilterWidget for batch tag annotation filtering`)
  - Batch Tag タブ向けに `AnnotationFilterWidget` が追加され、capability checkbox と
    environment checkbox が `ModelSelectionWidget` へ接続された。
  - 同時に `exclude_local` が追加され、Web API フィルタを provider 系の条件で表現する経路が入った。
- 2026-01-22: `08af6c23`
  (`fix: AnnotationFilterWidget set_filters environment clearing`)
  - `set_filters(environment=None)` のクリア挙動を直すため `_UNSET` sentinel が追加された。
  - これは「未指定」と「明示クリア」を区別するための互換実装で、現在の UI 状態モデルを複雑にしている。
- 2026-02-10: `170e5904`
  (`fix: アノテーション走査でアップスケーラーモデルを非表示化`)
  - 初期状態で upscaler が表示される問題を避けるため、`["caption", "tags", "scores"]` の
    デフォルト capability filter が追加された。
- 2026-02-10: `e760506c`
  (`fix: Web APIフィルター適用時のマニュアルedit・アップスケーラー表示除外`)
  - 環境フィルタだけ操作した場合にも MANUAL_EDIT / upscaler が表示されないよう、
    空 capability を `["caption", "tags", "scores"]` に補完する処理が追加された。
- 2026-05-12: `6415d54c` (`fix(#245): ライブラリ送信値を Model.litellm_model_id に統一`)
  - GUI のモデル識別子が `Model.name` から `Model.litellm_model_id` へ移った。
- 2026-05-13: `780b624e`
  (`fix(#241): API key 状況に応じたモデル表示フィルタと事前 validation`)
  - direct / openrouter route の畳み込みと API key 状況に応じた表示制御が追加された。
- 2026-05-13: `e90121b1`
  (`feat(#249): モデル route preference の永続化と GUI 設定 (Phase 2)`)
  - route preference が config / 設定画面に移され、`ModelSelectionWidget` は route 表示・選択も
    担うようになった。

つまり現在の使いにくさは、過去の個別問題に対して `WidgetSetupService` と
`ModelSelectionWidget` に条件を追加してきた結果であり、単一の設計意図ではない。

## Decision

Batch Tag のアノテーションモデル選択 UI は、以下の **二段階フィルタ** に統一する。

1. **実行環境を選ぶ**
   - `Web API`
   - `ローカル`
2. **選択された実行環境の中でタスクを絞る**
   - `Caption`
   - `Tags`
   - `Scores`
   - `すべて`

### SSoT

Batch annotation におけるフィルタ状態の SSoT は、アノテーション設定領域のフィルタ UI とする。

`ModelSelectionWidget` は、渡されたフィルタ状態に従って候補モデルを表示し、選択状態を管理する
表示・選択コンポーネントに寄せる。

### 削除・非採用

以下は Batch annotation UI から削除する。

- `ModelSelectionWidget.executionEnvCombo`
  - 理由: `AnnotationFilterWidget` 側の実行環境選択と重複し、現在の適用条件を不透明にするため。
- `exclude_local` を UI 層で直接受け渡す経路
  - 理由: 「APIのみ」という UI 表現と provider 正規化が混ざるため。実行環境は
    `environment = "api" | "local"` として表現する。
- 空の `capabilities` を `["caption", "tags", "scores"]` に暗黙補完する経路
  - 理由: UI 上の未選択状態と実際のフィルタ条件がズレるため。
- `provider="local"` を UI 層から直接注入する経路
  - 理由: provider と実行環境は同じ概念ではない。ローカル判定は `requires_api_key` /
    model registry metadata 側で扱う。

### 採用する意味論

`environment`:

```python
Literal["api", "local"]
```

Batch annotation の実行対象モデル選択では、環境未選択状態を持たない。初期値は利用者が次に行う
実行を明確にするため `api` または `local` のどちらかに決める。初期値は実装時に config /
利用頻度を見て決めるが、UI 上は常に片方が選択される。

`task_filter`:

```python
Literal["all", "caption", "tags", "scores"]
```

`all` は「選択中の実行環境に存在する全タスク」を意味する。空配列や `None` を UI 操作上の
「すべて」として扱わない。

### 表示方針

- フィルタは上から順に `環境 -> タスク -> モデル一覧` の順で配置する。
- モデル一覧の上には現在の適用条件を短く表示する。
  - 例: `Web API / Tags`
  - 例: `ローカル / すべて`
- モデル一覧は provider group よりもタスク適合性と選択状態を優先して見せる。
- route preference (`auto` / `direct` / `openrouter`) はモデル実行経路の設定であり、
  Batch annotation の一次フィルタ UI には出さない。既存の設定画面に残す。

## Rationale

### なぜ二段階フィルタか

アノテーション実行時に最初に必要な判断は「Web API を使うか、ローカルで処理するか」である。
この判断は API key、速度、コスト、オフライン性に直結するため、タスク種別よりも上位の意思決定になる。

その後に `Caption` / `Tags` / `Scores` を絞る方が、ユーザーの意図とモデル候補の出方が一致する。

### なぜ `executionEnvCombo` を残さないか

同じ概念を別 UI に残すと、片方の見た目と実際の適用条件がズレる。これは実装上の互換性よりも
操作体験への悪影響が大きい。

Batch annotation の model selection では `AnnotationFilterWidget` 相当のフィルタ UI を
唯一の入力源にする。

### なぜ空配列を「すべて」としないか

空配列は「何も選んでいない」に見える。これを内部で `caption/tags/scores` に置換すると、
UI 表示と適用条件が一致しなくなる。

ユーザーに見える状態として `すべて` を用意し、その値をそのままフィルタ条件へ渡す。

### なぜ provider ではなく environment か

`provider` は `openai` / `anthropic` / `google` / `openrouter` / `local` などの
ルーティング・由来の情報であり、実行環境とは一致しない。

Batch annotation の一次判断は `requires_api_key` に近い。UI は provider を直接操作せず、
`environment` として扱う。

## Consequences

### 良い点

- 現在の適用条件が `環境 -> タスク` の順で読み取れる。
- 実行環境フィルタの重複がなくなる。
- 「全件表示」が明示的に表現できる。
- UI 層から provider 正規化の知識を削れる。
- 古い互換経路を減らし、テスト対象が狭くなる。

### 悪い点・トレードオフ

- `ModelSelectionWidget` を他画面で汎用フィルタ UI として使っている場合、呼び出し側の移行が必要。
- `executionEnvCombo` に依存した既存テストは削除または仕様変更が必要。
- 初期値を `api` / `local` のどちらにするかは、実利用に基づいて別途決める必要がある。

### 実装方針

実装 Issue では以下の順で進める。

1. `AnnotationFilterWidget` の UI モデルを `environment` + `task_filter` に再定義する。
2. `ModelSelectionWidget.apply_filters()` の入力を `environment` + `task_filter` 中心に縮約する。
3. Batch annotation 経路から `executionEnvCombo` / `exclude_local` / `provider="local"` 注入を削除する。
4. `ModelSelectionService` 側は `environment` を `requires_api_key` 判定へ変換し、provider 直指定に依存しない。
5. 既存テストを二段階フィルタ仕様へ更新する。

## Amendment: Issue #339 実装結果 (2026-05-22)

Issue #339 では、本 ADR の「環境を先に選ぶ」「Batch annotation のフィルタ UI を唯一の入力源に
寄せる」方針を維持しつつ、実装範囲をより局所的な UX 整理として確定した。

### 確定した仕様

- Batch annotation UI では、実行環境をローカルモデル capability 絞り込みより上に表示する。
- 旧「機能タイプ」表記は使わず、ローカルモデルの対応能力を絞り込む UI として表示する。
- capability 絞り込みはローカルモデル向けの絞り込みであり、ローカル選択時だけ操作可能にする。
- Web API 選択時は通常のモデル一覧を表示せず、API 設定と利用可能モデルに従うことを示す
  placeholder を表示する。
  - この仕様は後続の Issue #585 amendment で撤回した。
- Batch annotation のモデル選択では、`upscaler` などアノテーション用途ではないモデルを
  構造化された model type / capability 情報で除外する。表示名文字列には依存しない。
- Web API モデルの主表示では、`openrouter/...` などの経路込み ID を前面に出さない。
  `litellm_model_id` は実行用 ID として保持し、raw route / provider 情報は tooltip などの
  補助情報で確認できるようにする。
- OpenRouter 経由モデルの provider / family 表示は、`Model.provider` 列だけに依存せず、
  route ID から導出した canonical identity を使う。

### 実装上の決定

- #340, #341, #342 は PR #345 で実装した。
- #343 は PR #346 で実装した。
- #343 の route / 表示名 / canonical key / provider family 判定は、共有の
  `ModelRouteIdentity` に集約した。GUI と CLI は同じ解釈を使う。
- 実行時のモデル指定は引き続き `Model.litellm_model_id` を正本とし、表示名とは分離する。

### 本文からの差分

本 ADR 本文では `task_filter = Literal["all", "caption", "tags", "scores"]` として
単一値のタスクフィルタ化を想定していたが、Issue #339 では既存 checkbox ベースの capability
絞り込みを維持したまま、ローカルモデル用フィルタであることを UI 上明確化する方針に変更した。

また、Web API は capability 別の通常モデル一覧としては扱わず、Batch annotation UI では
placeholder 表示にする。Web API の利用可否と route preference は API 設定・provider availability
側の責務とし、Batch annotation のローカルモデル絞り込み UI には混ぜない。

## Amendment: Issue #585 Web API モデル一覧表示方針の修正 (2026-05-31)

Issue #341 / #339 で採用した「Web API 選択時は通常のモデル一覧を表示せず placeholder を表示する」
方針は、Batch Tag UI の実利用に照らして撤回する。

### Context

Web API モデルをローカルモデルの capability 絞り込みと同じ操作感で扱うと、`Caption` / `Tags` /
`Scores` が Web API の実行タスク選択であるかのように見える。これは Issue #339 時点の問題意識として
妥当だった。

しかし、一覧そのものを非表示にすると、Batch Tag タブ上で使用する Web API モデルをどこで選ぶのかが
分からない。placeholder は「API 設定と利用可能モデルに従う」ことを示していたが、実行対象モデルを
確認・選択する導線としては不十分だった。

### Decision

Batch Tag のモデル選択領域は、実行環境に応じて同じ場所で表示内容を切り替える。

- `ローカルモデル` 選択時は、ローカルモデル一覧を表示し、ローカルモデル対応機能フィルタを有効化する。
- `Web APIモデル` 選択時は、Web API モデル一覧を同じモデル選択領域に表示する。
- Web API 選択時は、ローカルモデル対応機能フィルタを無効化したままにする。
- Web API モデル候補は、ローカル capability フィルタではなく API key availability /
  route preference / provider availability に従って表示する。
- placeholder は、Web API モデル候補が 0 件、API key 未設定、registry 未同期など、候補を表示できない
  理由がある場合だけ使う。

### Rationale

当時の代替案は「Web API モデル一覧を非表示にし、API 設定側に責務を寄せる」ことだったが、
Batch Tag の実行前に対象モデルを確認・選択できないため、操作体験として成立しない。

同じモデル選択領域で Web API 一覧に切り替えれば、ユーザーは実行対象モデルを確認できる。一方で、
ローカルモデル対応機能フィルタを無効化すれば、Issue #339 の「Web API をローカル capability
絞り込み対象に見せない」という目的も維持できる。

### Consequences

- `annotation_only=True && execution_env == "APIモデルのみ"` で早期に placeholder を表示する実装は、
  この ADR の正本仕様ではない。
- Batch Tag の Web API 選択時も、Web API モデル候補を通常のモデル表示経路へ流す必要がある。
- #343 / #346 で整備した Web API モデルの provider / family 表示は、Batch Tag 側の一覧表示にも
  適用する。
- テストは Web API 選択時の一覧表示と、候補 0 件時の placeholder 表示を分けて検証する。

## Related

- ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary
- ADR 0026: On-Demand Runtime Validation Strategy
- ADR 0029: Unified Dataset Quality Tier
- LoRAIro #339: GUI: バッチアノテーションのモデル選択UXを整理する
- LoRAIro #340: GUI: バッチアノテーションの実行環境とローカルモデル絞り込みを整理する
- LoRAIro #341: GUI: Web API選択時のモデル一覧をプレースホルダー表示にする
- LoRAIro #342: GUI: アノテーションモデル選択からアップスケーラーモデルを除外する
- LoRAIro #343: GUI: Web APIモデル名をprovider単位で見やすく表示する
- LoRAIro #585: GUI: バッチタグのWebAPIモデル選択がプレースホルダーのままで利用可能モデルが表示されない
- LoRAIro PR #345: fix: refine batch annotation model filtering
- LoRAIro PR #346: fix: improve web api model display names
