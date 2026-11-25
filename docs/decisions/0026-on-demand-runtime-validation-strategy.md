---
type: ADR
title: On-Demand Runtime Validation Strategy
status: Accepted (amended)
timestamp: 2026-05-17
tags: []
---
# ADR 0026: On-Demand Runtime Validation Strategy

- **Amended**: 2026-05-18

## Context

Issue #276 の調査により、現在のテストスイートが mock 中心に偏っており、実使用フローでしか発覚しない不具合を CI で検出できていないことが明らかになった。

実際、Issue #267 の動作確認中には、以下の不具合が連続して見つかった。

| Issue | 内容 | 現 CI が見逃した理由 |
|---|---|---|
| #267 | `AutoModelForVision2Seq` 削除に伴う `ImportError` | 本番コード経路で実モデルロードが実行されない |
| NEXTAltair/image-annotator-lib#66 | `cafe_aesthetic` で `ValidationError` | scorer の実推論が実行されない |
| #274 | `openai/gpt-4o-mini` で接続エラー | OpenAI の実 API 呼び出しが実行されない |
| #275 | `anthropic/claude-haiku-4-5` で `KeyError: 'type'` | Anthropic の実 API 呼び出しが実行されない |

一方で、実 API キーを使うテストや、Hugging Face 等からローカルモデルをダウンロードして実行するテストを CI の必須・定期実行に含めることには大きな問題がある。テスト結果が外部サービス障害、レート制限、課金、シークレット管理、モデル配布状態、ネットワーク帯域、CPU のみ環境の実行時間に左右されるためである。

したがって、LoRAIro では次の 2 つを明確に分ける設計判断が必要になる。

1. CI で継続的に保証する決定論的な E2E テスト
2. 開発者が必要時にローカルで実行する実環境検証(on-demand runtime validation)

## Decision

LoRAIro の実使用面における検証を、**CI E2E** と **オンデマンド実行時検証(On-demand runtime validation)** に分離する。

### CI E2E

CI で実行する E2E テストは、決定論的なローカルフィクスチャ・フェイクバックエンド・モックプロバイダーを使うものに限定する。

検証対象は、以下のような「アプリケーション配線」である。

- CLI サブプロセスが起動する
- 設定ファイルを読み込む
- プロジェクト・DB・出力ディレクトリが作成される
- アノテーションおよびエクスポートのワークフローが最後まで流れる
- フェイクバックエンドでも期待する DB 更新や出力ファイルが残る

CI E2E は `tests/integration/` 配下に配置し、pytest マーカーとして `integration`・`e2e`、必要に応じて `cli` を付与する。

BDD は E2E の必須実装形式とはしない。Given/When/Then でユーザー仕様を表現する価値があるシナリオだけを `tests/bdd/` に置き、単なるサブプロセスのスモークテストや配線確認は統合テストとして実装する。

### 実行時検証の責務境界

実外部依存を使うテストは、LoRAIro の必須 CI や定期実行レーンには含めない。

また、以下の実行時検証に関する詳細方針は LoRAIro 側では定義しない。

- プロバイダーの API キーを使った実 Web API 呼び出し
- Hugging Face 等からのローカル ML モデルのダウンロード
- 実ローカルモデルによる推論
- プロバイダーの稼働状況、モデルレジストリの状態、有料クォータ、ネットワーク帯域に依存する検証

これらは image-annotator-lib の責務であり、同リポジトリの ADR でテストレーン・マーカー・スキップ条件・CI 方針を定義する。

LoRAIro 側で扱うオンデマンド検証は、アダプター・設定・DB 保存・エクスポートのワークフローが実ライブラリ契約と整合しているかの確認に限定する。想定する実行タイミングは以下のとおりである。

- リリース前
- `AnnotatorLibraryAdapter`・モデルレジストリ同期・アノテーション保存境界を変更したとき
- LoRAIro 側で実使用不具合を再現・修正するとき
- Issue #276 の子 Issue(#277〜#280)で定義される確認項目を検証するとき

GitHub Actions には、実モデルダウンロードや実 WebAPI 呼び出しを伴うワークフローを追加しない。`workflow_dispatch` や `schedule` を含め、CI 経由での実環境検証は禁止する(本 ADR amendment 2026-05-18)。実環境検証はすべて開発者ローカルで行い、必要時に手動実行する。

LoRAIro 側リポジトリには、実モデルダウンロードや実 WebAPI を呼ぶテストを一切持たない。これらは image-annotator-lib リポジトリの `tests/runtime_validation/` 配下に集約し(iam-lib ADR 0001 amended)、LoRAIro 側からは `Makefile` ターゲット(`test-runtime-local` / `test-runtime-webapi`)経由で間接実行する。

### フェイクバックエンド境界

LoRAIro の決定論的 E2E は、アノテーションライブラリの内部挙動を検証しない。特に「画像を実際にアノテーションできるか」は image-annotator-lib の責務であり、LoRAIro E2E の対象外である。

LoRAIro E2E が検証するのは、「アノテーションライブラリ境界から妥当なアノテーション結果が返ったとき、LoRAIro がその結果を保存・参照・エクスポートできるか」という点である。

E2E では `ServiceContainer.annotator_library` 境界に `AnnotatorLibraryAdapter` 互換のフェイク実装を注入し、`PHashAnnotationResults` 互換の固定結果を返す。

フェイク注入は `AnnotatorLibraryProtocol` とファクトリ差し替え方式で実装する。Protocol は LoRAIro がアノテーションライブラリ境界に要求する最小の振る舞い(`annotate`、`is_model_deprecated`、モデルレジストリ API など)を定義し、`AnnotatorLibraryAdapter` と `FakeAnnotatorLibrary` の双方がこれを満たす。

`ServiceContainer` は具象 `AnnotatorLibraryAdapter` を直接生成せず、ファクトリから `AnnotatorLibraryProtocol` を生成する。通常時のファクトリは `AnnotatorLibraryAdapter(config_service)` を返し、CI E2E では明示的なテスト専用スイッチによって `FakeAnnotatorLibrary` を返すファクトリへ切り替える。

```text
LoRAIro E2E:
CLI / GUI workflow
  -> ServiceContainer.annotator_library
  -> FakeAnnotatorLibrary
  -> deterministic PHashAnnotationResults
  -> AnnotationSaveService
  -> DB / export
```

このフェイクは、実 Web API・Hugging Face のモデルダウンロード・torch / transformers によるローカル推論を呼び出してはならない。

サブプロセスベースの CI E2E でフェイク注入を有効化するため、テスト専用環境変数 `LORAIRO_TEST_FAKE_ANNOTATOR=1` を使用する。この環境変数は本番機能ではなく、ユーザー向け設定(`lorairo.toml`)としては公開しない。フェイク有効化時はログへ明示し、`ServiceContainer.reset_for_testing()` でファクトリ状態も初期化する。

LoRAIro 側で検証する項目は以下に限定する。

- CLI / GUI ワークフローがアノテーションライブラリ境界へ到達すること
- アノテーションライブラリ境界から返った妥当な結果を受け取れること
- 受け取った結果を DB に保存できること
- DB に保存したタグやキャプションを参照できること
- 保存結果をエクスポートなどの後続ワークフローで利用できること
- `AnnotatorLibraryAdapter` が image-annotator-lib の公開 API へ正しい引数で委譲すること

image-annotator-lib のモデルロード・プロバイダー API・推論契約は、image-annotator-lib 側 ADR に従って同リポジトリで検証する。LoRAIro の決定論的 E2E にその責務を混ぜない。

スコアの戻り値契約はモデル実装ごとの差分があり、NEXTAltair/image-annotator-lib#66 の設計判断に依存する。そのため、LoRAIro の初期 CI E2E フェイク結果ではスコアを合格基準に含めない。スコアのライブラリ契約が image-annotator-lib 側で確定した後、必要に応じて LoRAIro 側の保存・参照テストを追加する。

LoRAIro 側で検証しない項目は以下のとおりである。

- 実モデルがロードできること
- 実 Web API プロバイダーが応答すること
- 入力画像に対して意味のあるタグ・キャプション・スコアが生成されること
- scorer の数値がモデル品質として妥当であること
- scorer がタグを派生生成するか、スコアのみを返すかといったスコア結果契約
- プロバイダー別のレスポンススキーマ・モデル利用可否・リトライ・タイムアウトの実行時契約

### CI E2E の合格基準

LoRAIro の CI E2E は、以下を合格基準とする。

1. 対象ワークフローが正常終了する。
2. プロジェクト・DB・登録画像・エクスポート出力など、LoRAIro が管理する永続状態が作成される。
3. フェイクバックエンドが返した決定論的アノテーション結果が DB に保存される。
4. 保存済みアノテーション結果をエクスポートなどの後続ワークフローで利用できる。
5. 実 Web API、Hugging Face モデルダウンロード、torch / transformers による実ローカル推論を行わない。

実装時は、DB に保存されたタグとキャプションを取得して検証する。スコアは NEXTAltair/image-annotator-lib#66 および image-annotator-lib 側のスコア結果契約が確定するまで、CI E2E フェイク結果の必須検証対象にしない。スコアの永続化を LoRAIro 側で先に確認する必要がある場合は、フェイクアノテーション E2E ではなく、明示的なスカラー値を使うサービス・DB 境界の狭いテストとして扱う。

なお、ログ文言の完全一致、Rich 表示の見た目、実モデルの推論品質、実プロバイダーの応答内容、実行時間の厳密な秒数、プライベートメソッドの呼び出し回数は合格基準に含めない。

### マーカー運用方針

pytest マーカーは以下の意味で使い分ける。

| マーカー | 用途 |
|---|---|
| `e2e` | 決定論的なローカルフィクスチャ・フェイクバックエンドで動く E2E(CI で実行) |
| `cli` | CLI エントリーポイント・サブプロセス・コマンドワークフロー |
| `webapi` | Web API アノテーター関連テスト全般(mock を含む、CI で実行可) |
| `calls_real_webapi` | 実プロバイダー API キーを使うオンデマンド検証(`webapi` の部分集合、**CI 非経由・ローカル専用**) |
| `downloads_and_runs_model` | 実モデルダウンロードと実推論を伴うオンデマンド検証(**CI 非経由・ローカル専用**) |
| `slow` | 通常 CI から除外する重いテスト |
| `model_factory` / `scorer` / `tagger` | モデルロード・推論領域の分類 |

`e2e` は「実外部依存を使う」という意味ではない。実外部依存を使う場合は `calls_real_webapi` または `downloads_and_runs_model` を付与し、CI から完全に除外する。

- **`webapi` と `calls_real_webapi` の区別**:
  - `webapi`: Web API アノテーターに関連するテスト全般(mock を含む)。CI で実行する。
  - `calls_real_webapi`: 実 API キーで実リクエストを送信するテスト。`webapi` の部分集合として併用できる(`@pytest.mark.webapi` と `@pytest.mark.calls_real_webapi`)。CI からは除外する。
- **マーカーの組み合わせ運用**:
  `calls_real_webapi` と `downloads_and_runs_model` は排他ではない。LoRAIro アダプター経由で実モデルと実 WebAPI の両方を 1 テストで検証する場合は、両マーカーを併用できる。フィルタ上は `not (downloads_and_runs_model or calls_real_webapi)` により CI から除外される。

## Rationale

### なぜ実 API・実ローカルモデルを CI に含めないか

実 API と実ローカルモデルの検証は、実使用不具合を検出する価値が高い。一方で、LoRAIro の CI 品質ゲートに含めるには不安定要素が多すぎる。

- 外部プロバイダーの障害やレート制限で失敗する
- API 利用料金が CI トリガーに紐づく
- API キーやシークレットの管理負担が増える
- プロバイダーのレスポンススキーマやモデル提供状況が予告なく変わる
- モデルダウンロードが大きく、CI 時間とキャッシュ容量を圧迫する
- CPU のみのランナーでは推論時間が読みにくい
- torch / transformers / CUDA 周辺の環境差が失敗原因になりやすい

これらを LoRAIro の必須 CI に含めると、PR の品質ゲートが「LoRAIro のリグレッション」ではなく「外部環境の状態」に左右されてしまう。また、実 API・実モデルの契約は image-annotator-lib の責務であり、LoRAIro ADR が詳細を規定すると責務境界が曖昧になる。

### なぜ決定論的 E2E は CI に残すか

CLI 起動、設定読み込み、DB 作成、出力ファイル生成、ワークフローの統合制御は LoRAIro 側の責務であり、CI で継続的に保証する価値がある。

フェイクバックエンドやモックプロバイダーを使えば、外部 API やモデルダウンロードに依存せず、実行経路と入出力契約を検証できる。これにより、mock 中心のユニットテストだけでは拾いにくい配線リグレッションを補完できる。

フェイク化の境界は `ServiceContainer.annotator_library` とする。ここは LoRAIro 本体と image-annotator-lib の接点であり、CLI 経路と GUI 経路の双方が最終的に到達する共通依存である。`image_annotator_lib.annotate()` 内部やモデルローダーを直接フェイク化すると、ライブラリ内部構造に E2E が引きずられる。逆に `AnnotationLogic` 全体をフェイク化すると、LoRAIro 側のアダプター接続が検証対象から外れてしまう。そのため、`AnnotatorLibraryAdapter` 互換のフェイクを `annotator_library` として注入する。

Protocol 方式を採用するのは、LoRAIro が必要としているのが具象クラス `AnnotatorLibraryAdapter` ではなく、「アノテーションライブラリとして呼べる形」だからである。ABC 継承を要求するとフェイクやアダプターの実装を LoRAIro 固有の親クラスに縛ることになるが、Protocol なら同じメソッド形を満たすだけで差し替えられる。外部ライブラリ境界とテストダブルの置換に適している。

### なぜ BDD ではなく統合テストを基本配置にするか

Issue #276 で必要な E2E の主目的は、ユーザー仕様の自然言語表現ではなく、実行経路の接続確認である。

BDD には feature ファイルとステップ実装の保守コストがかかるため、単なるサブプロセスのスモークテストや配線確認に使うと過剰になる。仕様として読み下したい重要フローだけを BDD に置き、それ以外の決定論的 E2E は `tests/integration/` に配置する。

### 却下した選択肢

| 案 | 却下理由 |
|---|---|
| PR ごとに実 API・実モデルを実行する | シークレット・課金・外部障害・実行時間が PR ゲートに混入する |
| 週次・日次で実 API・実モデルを自動実行する | 個人開発・小規模運用ではコストと不安定さに対して効果が見合わない |
| mock テストだけを増やす | #267 / NEXTAltair/image-annotator-lib#66 / #274 / #275 のような本番経路・プロバイダー契約・実推論の問題を検出できない |
| 手動確認だけにする | CLI 配線やワークフローのリグレッションまで属人化し、通常のリグレッション検知が弱くなる |
| E2E をすべて BDD に寄せる | 実行経路確認に対して feature / steps の保守コストが過剰になる |

## Consequences

### 良い点

- PR CI の安定性と速度を維持しながら、CLI およびワークフロー配線のリグレッションを検出できる。
- 実 API キーやモデルダウンロードを CI の必須条件にしないため、シークレット管理・課金・外部障害の影響を避けられる。
- `e2e` マーカーの意味が「CI 可能な決定論的 E2E」として明確になる。
- 実使用検証は、必要なタイミングでローカル実行できる形に整理される。
- BDD は仕様表現に価値があるシナリオへ集中できる。

### 悪い点・トレードオフ

- 実 API や実モデルのリグレッションは PR CI では自動検出されない。
- リリース前やプロバイダー・モデル周辺の変更時に、開発者がオンデマンド検証を実行する運用規律が必要になる。
- 実 API・実モデル検証の実行環境は開発者ローカルに依存する。
- 手動ワークフローを後から追加する場合、シークレット未設定時のスキップ、課金、失敗時の切り分けといった運用設計が別途必要になる。

### 運用ルール

- `@pytest.mark.e2e` を付与するテストは、原則として CI で決定論的に実行できなければならない。
- 決定論的 E2E では `ServiceContainer.annotator_library` 境界をフェイク化し、image-annotator-lib の内部挙動や「実際にアノテーションできるか」を検証対象にしない。
- フェイク注入は `AnnotatorLibraryProtocol` とファクトリ差し替えで行う。CLI サブプロセス E2E では `LORAIRO_TEST_FAKE_ANNOTATOR=1` を使う。
- 実プロバイダー API や実モデルダウンロードを伴うテストは LoRAIro 側リポジトリに置かない。image-annotator-lib リポジトリの `tests/runtime_validation/` 配下(ADR 0001 amended)に集約し、LoRAIro 側からは `Makefile` ターゲットで間接実行する。
- モデルダウンロード・実推論・長時間実行を伴う検証は LoRAIro 側 E2E に含めない。必要な場合は image-annotator-lib 側 ADR 0001(amended)に従って同リポジトリで扱う。
- CLI のフルワークフロー E2E は、可能な限りフェイクバックエンドとフィクスチャを使って `tests/integration/` に配置する。
- BDD はユーザー仕様として読み下したいシナリオに限定し、E2E の標準配置にはしない。
- 実 API・実モデル検証を CI(定期実行・`workflow_dispatch`・必須レーン)へ昇格することは禁止する(本 ADR amendment 2026-05-18)。再導入する場合は、本 ADR と image-annotator-lib ADR 0001 の両方を破棄し、新規 ADR で再設計する。

## Related

- **親 Issue**: #276(テスト設計: 実使用面の E2E 検証が不足)
- **子 Issue**: #277(Local model smoke)、#278(Real API)、#279(CLI E2E)、#280(Manual checklist)
- **実例 Issue**: #267、#274、#275、NEXTAltair/image-annotator-lib#66
- **移管済み Issue**: #273 → NEXTAltair/image-annotator-lib#66
- **スコア契約検討**: NEXTAltair/image-annotator-lib#66(Score モデルの `UnifiedAnnotationResult` 契約不整合)
- **image-annotator-lib Issue**: NEXTAltair/image-annotator-lib#65(実 API・実ローカルモデルのオンデマンド実行時検証)
- **委譲先 ADR**: image-annotator-lib `docs/decisions/0001-runtime-validation-test-lanes.md`
- **関連 ADR**: 0024(pytest Test Responsibility Separation by Package)
- **関連ファイル**:
  - `pyproject.toml`(`[tool.pytest.ini_options].markers`)
  - `.github/workflows/ci.yml`
  - `tests/integration/`
  - `tests/bdd/`
