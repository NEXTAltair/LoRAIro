# ADR 0026: On-Demand Runtime Validation Strategy

- **日付**: 2026-05-17
- **ステータス**: Accepted

## Context

Issue #276 で、現在の test suite が mock 中心に寄っており、実使用フローでしか発覚しない不具合を CI で検出できていないことが明確になった。

Issue #267 の動作確認中に、以下の不具合が連続して検出された:

| Issue | 内容 | 現 CI が見逃した理由 |
|---|---|---|
| #267 | `AutoModelForVision2Seq` 削除に伴う `ImportError` | production code path で実モデルロード経路が実行されない |
| NEXTAltair/image-annotator-lib#66 | `cafe_aesthetic` で ValidationError | scorer 実推論が実行されない |
| #274 | `openai/gpt-4o-mini` で connection error | OpenAI 実 API 呼び出しが実行されない |
| #275 | `anthropic/claude-haiku-4-5` で `KeyError: 'type'` | Anthropic 実 API 呼び出しが実行されない |

一方で、実 API キーを使うテストや Hugging Face 等からローカルモデルをダウンロードして実行するテストを CI の必須・定期実行に含めると、外部サービス障害、rate limit、課金、secret 管理、モデル配布状態、ネットワーク帯域、CPU-only CI での実行時間に test result が依存する。

したがって、LoRAIro には次の 2 つを分ける設計判断が必要である:

1. CI で継続的に保証する deterministic な E2E
2. 開発者が必要時にローカルで実行する実使用 validation

## Decision

LoRAIro の実使用面検証を **CI E2E** と **On-demand runtime validation** に分離する。

### CI E2E

CI で実行する E2E は、deterministic な local fixture / fake backend / mocked provider を使うものに限定する。

対象は以下のような「アプリケーション配線」の検証である:

- CLI subprocess が起動する
- 設定ファイルを読む
- project / DB / output directory が作成される
- annotation / export workflow が最後まで流れる
- fake backend でも期待する DB 更新や出力ファイルが残る

CI E2E は `tests/integration/` 配下に置き、pytest marker として `integration` / `e2e` / 必要に応じて `cli` を付与する。

BDD は E2E の必須実装形式とはしない。Given/When/Then でユーザー仕様を表現する価値があるシナリオだけを `tests/bdd/` に置く。単なる subprocess smoke や配線確認は統合テストとして実装する。

### Runtime validation responsibility

実外部依存を使うテストは、LoRAIro の CI mandatory / scheduled lane には含めない。

ただし、以下の runtime validation 詳細方針は LoRAIro 側では定義しない:

- provider API key を使った実 Web API 呼び出し
- Hugging Face 等からのローカル ML model download
- 実ローカルモデル推論
- provider availability / model registry state / paid quota / network bandwidth に依存する検証

これらは image-annotator-lib の責務であり、同リポジトリの ADR で test lanes / marker / skip 条件 / CI 方針を定義する。

LoRAIro 側で扱う on-demand validation は、LoRAIro の adapter / config / DB 保存 / export workflow が実 library contract と整合しているかの確認に限定する。実行タイミングは以下を想定する:

- リリース前
- `AnnotatorLibraryAdapter` / model registry sync / annotation save boundary を変更したとき
- LoRAIro 側で実使用不具合を再現・修正するとき
- Issue #276 の子 Issue (#277-#280) で定義される確認項目を検証するとき

GitHub Actions の `workflow_dispatch` による LoRAIro manual workflow は将来追加してよい。ただし opt-in とし、必要な secrets や cache が無い場合は skip する。PR 必須 check や scheduled workflow にはしない。

### Fake backend boundary

LoRAIro の deterministic E2E は、annotation library の内部挙動を検証しない。

特に、LoRAIro E2E は「画像を実際にアノテーションできるか」を検証しない。それは image-annotator-lib の責務である。

LoRAIro E2E は「annotation library 境界から妥当な annotation result が返ったとき、LoRAIro がその結果を保存・参照・export できるか」を検証する。

E2E では `ServiceContainer.annotator_library` 境界に `AnnotatorLibraryAdapter` 互換の fake implementation を注入し、`PHashAnnotationResults` 互換の固定結果を返す。

fake injection は `AnnotatorLibraryProtocol` + factory 差し替え方式で実装する。Protocol は LoRAIro が annotation library 境界に要求する最小の振る舞い (`annotate`, `is_model_deprecated`, model registry API など) を定義し、`AnnotatorLibraryAdapter` と `FakeAnnotatorLibrary` の両方がその形を満たす。

`ServiceContainer` は具象 `AnnotatorLibraryAdapter` ではなく factory から `AnnotatorLibraryProtocol` を生成する。通常時の factory は `AnnotatorLibraryAdapter(config_service)` を返す。CI E2E では明示的なテスト専用スイッチにより `FakeAnnotatorLibrary` を返す factory に切り替える。

```text
LoRAIro E2E:
CLI / GUI workflow
  -> ServiceContainer.annotator_library
  -> FakeAnnotatorLibrary
  -> deterministic PHashAnnotationResults
  -> AnnotationSaveService
  -> DB / export
```

この fake は、実 Web API、Hugging Face model download、torch / transformers / local inference を呼び出してはならない。

subprocess-based CI E2E で fake injection を有効化するため、テスト専用環境変数 `LORAIRO_TEST_FAKE_ANNOTATOR=1` を使用する。この環境変数は production feature ではなく、ユーザー向け設定 (`lorairo.toml`) として公開しない。fake 有効化時はログに明示し、`ServiceContainer.reset_for_testing()` は factory 状態も初期化する。

LoRAIro 側で検証するのは以下に限定する:

- CLI / GUI workflow が annotation library 境界へ到達すること
- annotation library 境界から返った妥当な結果を受け取れること
- 受け取った結果を DB に保存できること
- DB に保存した tag / caption を参照できること
- 保存結果を export など後続 workflow で利用できること
- `AnnotatorLibraryAdapter` が image-annotator-lib public API に正しい引数で委譲すること

image-annotator-lib の model loading / provider API / inference contract は、image-annotator-lib 側 ADR に従って同リポジトリで検証する。LoRAIro の deterministic E2E にその責務を混ぜない。

score の戻り値 contract は model 実装ごとの差分があり、NEXTAltair/image-annotator-lib#66 の設計判断に依存する。そのため、LoRAIro の初期 CI E2E fake result では score を合格基準に含めない。score の library contract が image-annotator-lib 側で確定した後、必要であれば LoRAIro 側の保存・参照テストを追加する。

LoRAIro 側で検証しないもの:

- 実モデルがロードできること
- 実 Web API provider が応答すること
- 入力画像に対して意味のある tag / caption / score が生成されること
- scorer の数値がモデル品質として妥当であること
- scorer が tag を派生生成するか、score のみを返すかといった score result contract
- provider 別 response schema / model availability / retry / timeout の runtime contract

### CI E2E acceptance criteria

LoRAIro の CI E2E は、以下を合格基準とする:

1. 対象 workflow が成功終了する。
2. project / DB / registered image / export output など、LoRAIro が管理する永続状態が作成される。
3. fake backend が返した deterministic annotation result が DB に保存される。
4. 保存済み annotation result を export など後続 workflow で利用できる。
5. 実 Web API、Hugging Face model download、torch / transformers による実 local inference を行わない。

実装時は、DB に保存された tag と caption を取得して検証する。score は NEXTAltair/image-annotator-lib#66 と image-annotator-lib 側の score result contract が確定するまで、CI E2E fake result の必須検証対象にしない。score persistence を LoRAIro 側で先に確認する必要がある場合は、fake annotation workflow E2E ではなく、明示的な scalar score を使う service / DB 境界の狭いテストとして扱う。

合格基準には、ログ文言の完全一致、Rich 表示の見た目、実モデルの推論品質、実 provider の応答内容、実行時間の厳密な秒数、private method の呼び出し回数を含めない。

### Marker policy

pytest marker は以下の意味で使う:

| Marker | 用途 |
|---|---|
| `e2e` | deterministic local fixtures / fake backend で動く E2E |
| `cli` | CLI entrypoint / subprocess / command workflow |
| `real_api` | LoRAIro 側 adapter / config boundary の on-demand validation。provider API 自体の責務は image-annotator-lib 側 ADR に委譲 |
| `webapi` | Web API annotator 関連 |
| `slow` | 通常 CI から除外する重いテスト |
| `model_factory` / `scorer` / `tagger` | model loading / inference domain の分類 |

`e2e` は「実外部依存を使う」という意味ではない。外部依存を使う場合は `real_api` や `slow` 等と組み合わせ、CI の通常 lane から除外する。

## Rationale

### なぜ実 API / 実ローカルモデルを CI に含めないか

実 API と実ローカルモデルの検証は、実使用不具合を検出する価値が高い。一方で、LoRAIro の CI 品質ゲートに含めるには不安定要素が多い。

- 外部 provider の障害や rate limit で failure になる
- API 利用料金が CI trigger に紐づく
- API key / secret の管理負担が増える
- provider のレスポンス schema や model availability が予告なく変わる
- model download が大きく、CI 時間と cache 容量を消費する
- CPU-only runner では推論時間が読みにくい
- torch / transformers / CUDA 周辺の環境差が failure 原因になりやすい

これらを LoRAIro mandatory CI に含めると、PR の品質ゲートが「LoRAIro の regression」ではなく「外部環境の状態」に左右される。また、実 API / 実モデルの contract は image-annotator-lib の責務であり、LoRAIro ADR が詳細を規定すると責任境界が曖昧になる。

### なぜ deterministic E2E は CI に残すか

CLI 起動、設定読み込み、DB 作成、出力ファイル生成、workflow orchestration は LoRAIro 側の責務であり、CI で継続的に保証する価値がある。

fake backend / mocked provider を使えば、外部 API や model download に依存せず、実行経路と入出力 contract を検証できる。これは mock-heavy unit tests だけでは拾いにくい wiring regression を補完する。

fake 化の境界は `ServiceContainer.annotator_library` とする。ここは LoRAIro 本体と image-annotator-lib の境界であり、CLI 経路と GUI 経路の双方が最終的に到達する共通依存である。`image_annotator_lib.annotate()` 内部や model loader を直接 fake 化すると library 内部構造に E2E が引きずられる。一方で `AnnotationLogic` 全体を fake 化すると、LoRAIro 側の adapter 接続が検証対象から外れる。そのため、`AnnotatorLibraryAdapter` 互換 fake を `annotator_library` として注入する。

Protocol 方式を採用する理由は、LoRAIro が必要とするのは `AnnotatorLibraryAdapter` という具象クラスではなく、「annotation library として呼べる形」だからである。ABC 継承を要求すると fake / adapter の実装を LoRAIro 固有の親クラスに縛るが、Protocol なら既存 adapter と fake が同じメソッド形を満たすだけでよい。これは外部 library 境界と test double の差し替えに向いている。

### なぜ BDD ではなく integration を基本配置にするか

Issue #276 で必要な E2E の主目的は、ユーザー仕様の自然言語表現ではなく、実行経路の接続確認である。

BDD は feature / steps のメンテナンスコストがあるため、単なる subprocess smoke や配線確認に使うと過剰になる。仕様として読み下したい重要フローだけを BDD に置き、それ以外の deterministic E2E は `tests/integration/` に置く。

### 却下した選択肢

| 案 | 却下理由 |
|---|---|
| PR ごとに実 API / 実モデルを実行する | secret / 課金 / 外部障害 / 実行時間が PR gate に混入する |
| weekly / nightly で実 API / 実モデルを自動実行する | 個人開発・小規模運用ではコストと flake に対する効果が釣り合わない |
| mock test だけを増やす | #267 / NEXTAltair/image-annotator-lib#66 / #274 / #275 のような production path / provider contract / 実推論の問題を検出できない |
| 手動確認だけにする | CLI 配線や workflow regression まで属人化し、通常の regression signal が弱い |
| E2E をすべて BDD に寄せる | 実行経路確認に対して feature / steps の保守コストが過剰 |

## Consequences

### 良い点

- PR CI の安定性と速度を維持しながら、CLI / workflow wiring の regression を検出できる。
- 実 API key や model download を CI の必須条件にしないため、secret 管理・課金・外部障害の影響を避けられる。
- `e2e` marker の意味が「CI 可能な deterministic E2E」として明確になる。
- 実使用 validation は、必要なタイミングでローカル実行できる形に残る。
- BDD は仕様表現に価値があるシナリオに集中できる。

### 悪い点・トレードオフ

- 実 API / 実モデルの regression は PR CI では自動検出されない。
- リリース前や provider/model 周辺変更時に、開発者が on-demand validation を実行する運用 discipline が必要になる。
- 実 API / 実モデル validation の実行環境は開発者ローカルに依存する。
- manual workflow を後で追加する場合、secret skip、課金、失敗時 triage の運用設計が別途必要になる。

### 運用ルール

- `@pytest.mark.e2e` を付けるテストは、原則として CI で deterministic に実行できなければならない。
- deterministic E2E では `ServiceContainer.annotator_library` 境界を fake 化し、image-annotator-lib 内部挙動や「実際にアノテーションできるか」を検証対象にしない。
- fake injection は `AnnotatorLibraryProtocol` + factory 差し替えで行う。CLI subprocess E2E では `LORAIRO_TEST_FAKE_ANNOTATOR=1` を使う。
- 実 provider API を呼ぶ LoRAIro 側 validation には `real_api` を付け、通常 CI から除外する。provider API contract の詳細検証は image-annotator-lib 側 ADR に従う。
- model download / 実推論 / 長時間実行を伴う検証は LoRAIro 側 E2E に含めない。必要な場合は image-annotator-lib 側 ADR に従って同リポジトリで扱う。
- CLI full workflow E2E は、可能な限り fake backend / fixture を使って `tests/integration/` に置く。
- BDD はユーザー仕様として読み下したいシナリオに限定し、E2E の標準配置にはしない。
- LoRAIro 側で実 API / 実モデル validation を CI scheduled job に昇格する場合は、本 ADR と image-annotator-lib 側 ADR の両方を見直す。

## Related

- **Umbrella Issue**: #276 (テスト設計: 実使用面の E2E 検証が不足)
- **子 Issue**: #277 (Local model smoke), #278 (Real API), #279 (CLI E2E), #280 (Manual checklist)
- **実例 Issue**: #267, #274, #275, NEXTAltair/image-annotator-lib#66
- **移管済み Issue**: #273 → NEXTAltair/image-annotator-lib#66
- **score contract 検討**: NEXTAltair/image-annotator-lib#66 (Score モデルの `UnifiedAnnotationResult` contract 不整合)
- **image-annotator-lib Issue**: NEXTAltair/image-annotator-lib#65 (実API・実ローカルモデルの on-demand runtime validation)
- **委譲先 ADR**: image-annotator-lib `docs/decisions/0001-runtime-validation-test-lanes.md`
- **関連 ADR**: 0024 (pytest Test Responsibility Separation by Package)
- **関連ファイル**:
  - `pyproject.toml` (`[tool.pytest.ini_options].markers`)
  - `.github/workflows/ci.yml`
  - `tests/integration/`
  - `tests/bdd/`
