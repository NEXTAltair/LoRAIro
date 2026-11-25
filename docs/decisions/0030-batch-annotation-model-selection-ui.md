---
type: ADR
title: Batch Annotation Model Selection UI
status: Superseded
timestamp: 2026-05-20
tags: []
---
# ADR 0030: Batch Annotation Model Selection UI

> **Superseded by [ADR 0075](0075-annotation-pipeline-composition-domain-model.md)(2026-06-23)**:
> 本 ADR の「二段階フィルタ」モデル選択 UI と `environment = Literal["api", "local"]`(環境未選択状態なし)は、ステージ別ピッカーへの移行(#741 / #839 / #845)により実態と乖離した。選択 UI のドメインモデルと環境意味論(3 値 `all` / `api` / `local`、既定 `all`)の正準は ADR 0075 である。本 ADR は経緯の記録として残す。

## Context

Batch Tag のアノテーション設定 UI はモデル選択の入口が複数に分かれており、現在適用されている条件をユーザーが読み取りにくい状態であった。

当時の主な構成は以下のとおりである。

- `AnnotationFilterWidget`
  - 機能タイプ: `Caption生成` / `Tag生成` / `品質スコア`
  - 実行環境: `Web API` / `ローカルモデル`
- `ModelSelectionWidget`
  - 一覧上部に `executionEnvCombo`(`すべて` / `APIモデルのみ` / `ローカルモデルのみ`)を配置
  - `apply_filters(provider, capabilities, exclude_local, execution_env)` で複数条件を受け取る
- `WidgetSetupService`
  - `AnnotationFilterWidget.filter_changed` を `ModelSelectionWidget.apply_filters()` に接続
  - 空の `capabilities` を `["caption", "tags", "scores"]` に置換

この構成では実行環境フィルタが二系統に分かれ、さらに UI のチェック状態と実際の適用条件が一致しない。その結果、「モデルが表示されない」「絞り込みが効いているか分からない」という操作体験になっていた。

関連 Issue:

- LoRAIro #298: `provider=None` のローカル・API モデル判定とフィルタ条件の不整合
- LoRAIro #299: 空の機能フィルタ時にデフォルト上書きされ、全件表示ができない
- LoRAIro #300: モデル実行環境フィルタが複数 UI 経路に分断され UX が不明瞭

### 歴史的背景

この UI は一度に設計されたものではなく、複数回の段階的統合と不具合回避を積み重ねた結果として現在の形になった。

- **2025-07-29** `924e1f0d`(`feat: Add hybrid annotation UI prototype and supporting components`):
  複数モデル対応アノテーション UI の基礎として `ModelSelectionWidget` が追加された。
- **2025-07-29** `3a2e44f5`(`feat: Complete Phase 1 hybrid annotation UI implementation and plan Phase 2.5 architecture refactoring`):
  `AnnotationControlWidget` が追加された。当時の設計書 `tasks/plans/hybrid_annotation_ui_comprehensive_design_plan_20250729.md` では「実行環境選択(Web API / ローカルモデル)」と「機能タイプ選択」を持つ構成であった。既存ウィジェットの最大活用とデッドコード削除を掲げていたが、後続の UI 分割により一部の責務が複数ウィジェットに残存した。
- **2025-07-30** `4043e581`(`feat: Complete Phase 2.5 architectural refactoring with unified filter system`):
  Qt Designer とサービス層の分離の一環として、`ModelSelectionWidget.ui` と `ModelSelectionService` が整備された。
- **2025-08-06** `88203110`(`feat: complete Phase 4 ModelSelectionWidget integration`):
  `ModelSelectionWidget` が `ModelSelectionCriteria` を用いる高度なフィルタリング UI として刷新され、汎用性と後方互換性を重視した設計が導入された。
- **2026-01-21** `9ebe8733`(`feat: Add AnnotationFilterWidget for batch tag annotation filtering`):
  Batch Tag タブ向けに `AnnotationFilterWidget` が追加され、機能チェックボックスと環境チェックボックスが `ModelSelectionWidget` へ接続された。同時に `exclude_local` が追加され、Web API フィルタをプロバイダー系条件で表現する経路が入った。
- **2026-01-22** `08af6c23`(`fix: AnnotationFilterWidget set_filters environment clearing`):
  `set_filters(environment=None)` のクリア挙動を直すため `_UNSET` 番兵値が追加された。未指定と明示クリアを区別する互換実装により、UI の状態モデルが複雑化した。
- **2026-02-10** `170e5904`(`fix: アノテーション走査でアップスケーラーモデルを非表示化`):
  初期状態でアップスケーラーが表示される問題を避けるため、`["caption", "tags", "scores"]` の既定機能フィルタが追加された。
- **2026-02-10** `e760506c`(`fix: Web APIフィルター適用時のマニュアルedit・アップスケーラー表示除外`):
  環境フィルタのみを操作した場合でも `MANUAL_EDIT` やアップスケーラーが表示されないよう、空の `capabilities` を `["caption", "tags", "scores"]` へ補完する処理が追加された。
- **2026-05-12** `6415d54c`(`fix(#245): ライブラリ送信値を Model.litellm_model_id に統一`):
  GUI のモデル識別子が `Model.name` から `Model.litellm_model_id` へ移行した。
- **2026-05-13** `780b624e`(`fix(#241): API key 状況に応じたモデル表示フィルタと事前 validation`):
  直接経路・OpenRouter 経路の畳み込みと、API キー状況に応じた表示制御が追加された。
- **2026-05-13** `e90121b1`(`feat(#249): モデル route preference の永続化と GUI 設定 (Phase 2)`):
  経路優先設定が設定ファイルと設定画面へ移され、`ModelSelectionWidget` は経路の表示・選択も担うようになった。

つまり現在の使いにくさは、単一の設計意図によるものではなく、過去の個別課題に対して `WidgetSetupService` と `ModelSelectionWidget` へ条件を継ぎ足してきた結果である。

## Decision

Batch Tag のアノテーションモデル選択 UI は、以下の**二段階フィルタ**に統一する。

1. **実行環境を選ぶ**
   - `Web API`
   - `ローカル`
2. **選択した実行環境の中でタスクを絞る**
   - `Caption`
   - `Tags`
   - `Scores`
   - `すべて`

### SSoT

バッチアノテーションにおけるフィルタ状態の SSoT は、アノテーション設定領域のフィルタ UI とする。

`ModelSelectionWidget` は、渡されたフィルタ状態に従って候補モデルを表示し、選択状態を管理する表示・選択コンポーネントへ寄せる。

### 削除・非採用とする要素

以下はバッチアノテーション UI から削除する。

- **`ModelSelectionWidget.executionEnvCombo`**:
  `AnnotationFilterWidget` 側の実行環境選択と重複し、現在の適用条件を不透明にするため削除する。
- **`exclude_local` を UI 層で直接受け渡す経路**:
  「API のみ」という UI 表現とプロバイダー正規化が混ざるため削除する。実行環境は `environment = "api" | "local"` で表現する。
- **空の `capabilities` を `["caption", "tags", "scores"]` へ暗黙補完する経路**:
  UI 上の未選択状態と実際のフィルタ条件がずれるため削除する。
- **`provider="local"` を UI 層から直接注入する経路**:
  プロバイダーと実行環境は異なる概念である。ローカル判定は `requires_api_key` およびモデルレジストリのメタデータ側で扱う。

### 採用する意味論

`environment`:

```python
Literal["api", "local"]
```

バッチアノテーションの実行対象モデル選択では、環境未選択状態を持たない。利用者が次に行う実行を明確にするため、UI 上は常に `api` または `local` の片方が選択される。初期値は実装時に設定と利用頻度を踏まえて決定する。

`task_filter`:

```python
Literal["all", "caption", "tags", "scores"]
```

`all` は「選択中の実行環境に存在する全タスク」を意味する。空配列や `None` を UI 操作上の「すべて」として扱わない。

### 表示方針

- フィルタは上から順に「環境 → タスク → モデル一覧」の順で配置する。
- モデル一覧の上部には、現在の適用条件を短く表示する(例: `Web API / Tags`、`ローカル / すべて`)。
- モデル一覧はプロバイダーグループよりも、タスク適合性と選択状態を優先して表示する。
- 経路優先設定(`auto` / `direct` / `openrouter`)はモデル実行経路の設定であり、バッチアノテーションの一次フィルタ UI には出さず、既存の設定画面に残す。

## Rationale

### なぜ二段階フィルタか

アノテーション実行時に最初に必要な判断は、「Web API を使うか、ローカルで処理するか」である。この判断は API キー、処理速度、コスト、オフライン動作に直結するため、タスク種別よりも上位の意思決定になる。

実行環境を決めた後に `Caption`・`Tags`・`Scores` で絞り込む方が、ユーザーの意図とモデル候補の表示が一致する。

### なぜ `executionEnvCombo` を残さないか

同じ概念を別 UI に残すと、片方の見た目と実際の適用条件がずれる。これは実装互換性よりも操作体験への悪影響が大きいため、バッチアノテーションのモデル選択では `AnnotationFilterWidget` 相当のフィルタ UI を唯一の入力源とする。

### なぜ空配列を「すべて」としないか

空配列はユーザーから見ると「何も選んでいない」状態に見える。これを内部で `caption` / `tags` / `scores` に置換すると、UI 表示と実際の適用条件が食い違う。ユーザーに見える状態として `すべて` を用意し、その値をそのままフィルタ条件へ渡す。

### なぜ `provider` ではなく `environment` か

`provider` は `openai`・`anthropic`・`google`・`openrouter`・`local` などのルーティングや由来を表す情報であり、実行環境とは一致しない。バッチアノテーションの一次判断は `requires_api_key` に近いため、UI はプロバイダーを直接操作せず `environment` として扱う。

## Consequences

### 良い点

- 現在の適用条件を「環境 → タスク」の順で直感的に読み取れる。
- 実行環境フィルタの重複が解消される。
- 「全件表示」を明示的に表現できる。
- UI 層からプロバイダー正規化の知識を取り除ける。
- 古い互換経路が減り、テスト対象が狭くなる。

### 悪い点・トレードオフ

- `ModelSelectionWidget` を他画面で汎用フィルタ UI として使っている場合、呼び出し側の移行が必要になる。
- `executionEnvCombo` に依存した既存テストは削除または仕様変更が必要になる。
- 初期値を `api` と `local` のどちらにするかは、実利用に基づいて別途決定する必要がある。

### 実装方針

実装 Issue では以下の順序で進める。

1. `AnnotationFilterWidget` の UI モデルを `environment` と `task_filter` に再定義する。
2. `ModelSelectionWidget.apply_filters()` の入力を `environment` と `task_filter` 中心に縮約する。
3. バッチアノテーション経路から `executionEnvCombo`・`exclude_local`・`provider="local"` 注入を削除する。
4. `ModelSelectionService` 側で `environment` を `requires_api_key` 判定へ変換し、プロバイダー直指定への依存をなくす。
5. 既存テストを二段階フィルタ仕様へ更新する。

## Amendment: Issue #339 実装結果(2026-05-22)

Issue #339 では、本 ADR の「環境を先に選ぶ」「バッチアノテーションのフィルタ UI を唯一の入力源へ寄せる」という方針を維持しつつ、実装範囲をより局所的な UX 整理として確定した。

### 確定した仕様

- バッチアノテーション UI では、実行環境をローカルモデルの機能絞り込みより上に表示する。
- 旧「機能タイプ」表記は使わず、ローカルモデルの対応能力を絞り込む UI として表示する。
- 機能絞り込みはローカルモデル専用とし、ローカル選択時のみ操作可能にする。
- Web API 選択時は通常のモデル一覧を表示せず、API 設定と利用可能モデルに従うことを示すプレースホルダーを表示する(この仕様は後続の Issue #585 改訂で撤回した)。
- バッチアノテーションのモデル選択では、`upscaler` などアノテーション用途ではないモデルを、構造化されたモデル種別および機能情報で除外する(表示名文字列には依存しない)。
- Web API モデルの主表示では、`openrouter/...` のような経路込み ID を前面に出さない。`litellm_model_id` は実行用 ID として保持し、生の経路やプロバイダー情報はツールチップなどの補助情報で確認できるようにする。
- OpenRouter 経由モデルのプロバイダー・ファミリー表示は、`Model.provider` 列だけに依存せず、経路 ID から導出した正規識別子(canonical identity)を使う。

### 実装上の決定

- #340・#341・#342 は PR #345 で実装した。
- #343 は PR #346 で実装した。
- #343 の経路・表示名・正規キー・プロバイダーファミリー判定は、共有の `ModelRouteIdentity` に集約し、GUI と CLI で同じ解釈を使う。
- 実行時のモデル指定は引き続き `Model.litellm_model_id` を正本とし、表示名とは分離する。

### 本文からの差分

本 ADR 本文では `task_filter = Literal["all", "caption", "tags", "scores"]` による単一値のタスクフィルタ化を想定していた。Issue #339 では、既存のチェックボックスベースの機能絞り込みを維持したまま、ローカルモデル用フィルタであることを UI 上明確化する方針へ変更した。

また、Web API は機能別の通常モデル一覧としては扱わず、バッチアノテーション UI ではプレースホルダー表示とした。Web API の利用可否と経路優先設定は API 設定およびプロバイダー利用可否側の責務とし、ローカルモデル絞り込み UI には混ぜない構成とした。

## Amendment: Issue #585 Web API モデル一覧表示方針の修正(2026-05-31)

Issue #341 / #339 で採用した「Web API 選択時は通常のモデル一覧を表示せずプレースホルダーを表示する」という方針は、Batch Tag UI の実利用に照らして撤回する。

### Context

Web API モデルをローカルモデルの機能絞り込みと同じ操作感で扱うと、`Caption`・`Tags`・`Scores` が Web API の実行タスク選択であるかのように見えてしまう。これは Issue #339 時点の問題意識として妥当であった。

しかし、一覧そのものを非表示にすると、Batch Tag タブ上で使用する Web API モデルをどこで選ぶのかが分からない。プレースホルダーは「API 設定と利用可能モデルに従う」と示していたが、実行対象モデルを確認・選択する導線としては不十分であった。

### Decision

Batch Tag のモデル選択領域は、実行環境に応じて同じ場所で表示内容を切り替える。

- `ローカルモデル` 選択時は、ローカルモデル一覧を表示し、ローカルモデル対応機能フィルタを有効化する。
- `Web APIモデル` 選択時は、Web API モデル一覧を同じモデル選択領域に表示する。
- Web API 選択時は、ローカルモデル対応機能フィルタを無効化したままにする。
- Web API モデル候補は、ローカル機能フィルタではなく API キーの利用可否・経路優先設定・プロバイダー利用可否に従って表示する。
- プレースホルダーは、Web API モデル候補が 0 件、API キー未設定、レジストリ未同期など、候補を表示できない理由がある場合にのみ使用する。

### Rationale

当時の代替案は「Web API モデル一覧を非表示にし、API 設定側へ責務を寄せる」ことであったが、Batch Tag 実行前に対象モデルを確認・選択できないため操作体験として成立しない。

同じモデル選択領域で Web API 一覧に切り替えれば、ユーザーは実行対象モデルを直接確認できる。同時にローカルモデル対応機能フィルタを無効化すれば、Issue #339 の「Web API をローカル機能絞り込みの対象に見せない」という目的も維持できる。

### Consequences

- `annotation_only=True && execution_env == "APIモデルのみ"` で早期にプレースホルダーを表示する実装は、本 ADR の正本仕様ではない。
- Batch Tag の Web API 選択時も、Web API モデル候補を通常のモデル表示経路へ流す必要がある。
- #343 / #346 で整備した Web API モデルのプロバイダー・ファミリー表示は、Batch Tag 側の一覧表示にも適用する。
- テストは、Web API 選択時の一覧表示と候補 0 件時のプレースホルダー表示を分けて検証する。

## Related

- ADR 0023: PydanticAI / LiteLLM WebAPI Inference Boundary
- ADR 0026: On-Demand Runtime Validation Strategy
- ADR 0029: Unified Dataset Quality Tier
- LoRAIro #339: GUI: バッチアノテーションのモデル選択 UX を整理する
- LoRAIro #340: GUI: バッチアノテーションの実行環境とローカルモデル絞り込みを整理する
- LoRAIro #341: GUI: Web API 選択時のモデル一覧をプレースホルダー表示にする
- LoRAIro #342: GUI: アノテーションモデル選択からアップスケーラーモデルを除外する
- LoRAIro #343: GUI: Web API モデル名を provider 単位で見やすく表示する
- LoRAIro #585: GUI: バッチタグの WebAPI モデル選択がプレースホルダーのままで利用可能モデルが表示されない
- LoRAIro PR #345: fix: refine batch annotation model filtering
- LoRAIro PR #346: fix: improve web api model display names
