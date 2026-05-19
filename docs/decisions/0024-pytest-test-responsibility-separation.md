# ADR 0024: pytest Test Responsibility Separation by Package

- **日付**: 2026-05-13 (created), 2026-05-19 (amended #291: single-venv via UV_PROJECT_ENVIRONMENT)
- **ステータス**: Accepted

## Context

Issue #247 で、ルート `/workspaces/LoRAIro` から引数なしの `uv run pytest` を実行すると、`pyproject.toml` の `testpaths` に含まれる `local_packages/image-annotator-lib/tests/` 側で **31 件の collection error** が発生し、テスト全体が `Interrupted: 31 errors during collection` で停止することが判明した。

根本原因は **pytest 実行境界の責任分離が崩れていたこと**:

1. **`tests/conftest.py` の lib mock 注入が lib 自身のテストに波及 (主因, 29 件)**: LoRAIro 本体 GUI テストで torch/tensorflow の動的ロードによる hang を避けるため、`tests/conftest.py` がモジュールレベルで `sys.modules["image_annotator_lib"]` を `types.ModuleType` ベースのモックに差し替えている。これは LoRAIro 本体テストには必須の隔離だが、ルート pytest が `local_packages/image-annotator-lib/tests/` まで collection するとこの mock が lib 自身のテストにも継承され、`parent_module = <MagicMock>` で `AttributeError: __spec__` が発生して collection が失敗する。
2. **basename 衝突 (副次, 1 件)**: `tests/unit/gui/services/test_worker_service.py` と `local_packages/genai-tag-db-tools/tests/gui/unit/test_worker_service.py` が同一 basename で、単一 pytest セッションでは `import file mismatch` になる。CI では `--ignore=...test_worker_service.py` で局所回避していたが、責任境界としては弱い。

つまりルート pytest は import 前提・conftest 責務・coverage 対象が異なる 3 種類のテストを同じプロセスに混ぜていた:

| 対象 | conftest 前提 | coverage 対象 | Python |
|---|---|---|---|
| LoRAIro 本体 | `tests/conftest.py` (lib mock 必須) | `src/lorairo` | 3.13 |
| image-annotator-lib | lib 側 conftest (実体 import 前提) | `image_annotator_lib` | **3.12** (`>=3.12,<3.13`) |
| genai-tag-db-tools | package 側 conftest | `src/genai_tag_db_tools` | 3.13 |

なお ADR 0016 (Coverage Threshold Policy, amended) は既に「image-annotator-lib は torch/ML が headless CI でハングするため `tests/conftest.py` でモック化、CI では 0% となるため `[tool.coverage.run] source` から除外する」と明文化していた。本 ADR はこの「package 境界で計測責務を分離する」判断を coverage だけでなく **pytest セッション境界まで** 一貫させる拡張である。

## Decision

**pytest セッション境界 = package 境界に揃える。** LoRAIro リポジトリ内のテスト実行は以下 3 つの独立した pytest セッションで構成し、conftest / import namespace / coverage / Python バージョンの責務を境界化する。

| セッション | working-directory | testpaths | Python | 起動方法 |
|---|---|---|---|---|
| LoRAIro 本体 | `/workspaces/LoRAIro` | `["tests"]` | 3.13 | `uv run pytest` / `make test` |
| image-annotator-lib | `local_packages/image-annotator-lib` | `["tests"]` | 3.13 | `make test-iam-lib` (LoRAIro root `.venv` 共有 + `--no-sync`) |
| genai-tag-db-tools | `local_packages/genai-tag-db-tools` | `["tests"]` | 3.13 | `make test-genai-tag` |

具体的に固定する事項:

1. **ルート `pyproject.toml` の `testpaths` を `["tests"]` のみに固定する。** `pythonpath` は LoRAIro 本体が local package を editable dependency として import する経路に必要なので維持する。
2. **ルート `[tool.coverage.run] source` を `["src"]` のみに固定する。** ADR 0016 で `genai-tag-db-tools` を `source` に含めていた判断を本 ADR で更新し、別 job で独立 coverage 計測する方針に切替える。
3. **CI workflow を package 単位 job に分離する。**
   - `test-unit` / `test-integration`: LoRAIro 本体のみを対象 (`local_packages/*/tests` 引き渡しと `--cov=...genai-tag-db-tools/src/...` を削除、`--ignore=...test_worker_service.py` の局所回避を撤去)。
   - `test-genai-tag-db-tools` (新規): `working-directory: local_packages/genai-tag-db-tools` で独立実行。
   - `test-image-annotator-lib` (新規): `working-directory: local_packages/image-annotator-lib` + Python 3.12 で独立実行。初期段階は marker `-m "not real_api and not heavy and not system_integration"` で fast/standard のみ。
   - `coverage-gate`: LoRAIro 本体の `coverage-unit` / `coverage-integration` のみを `coverage combine` 対象とする。local package coverage は別 artifact として保持し本体の `fail_under=75` には混ぜない。
4. **basename 衝突対応は別 pytest セッションへの自然分離で済ませる。** rename / namespace 強制は行わない。
5. **Makefile target**:
   - `make test`: LoRAIro 本体のみ
   - `make test-iam-lib` / `make test-genai-tag`: 各 package root へ `cd` して `uv run pytest`
   - `make test-all`: `$(MAKE)` チェーンで 3 セッションを順次実行 (単一 pytest invocation に混ぜない)

## Rationale

### なぜ「pytest セッション境界 = package 境界」を選んだか

- `tests/conftest.py` が `sys.modules` を直接書き換える必要があるのは LoRAIro 本体テストだけ。lib 自身のテストは実体 import を検証するのが目的。**conftest の責務境界 = pytest セッション境界 = package 境界** を一致させると、各境界の前提が互いに干渉しない。
- ADR 0016 で既に coverage `source` を package 境界で分離する判断は確立済み。pytest セッションだけ「全部混ぜる」状態が残っていたのが歪みの源泉だった。本 ADR でセッション境界も coverage 境界に揃え、3 つの責務 (conftest / coverage / Python バージョン) を 1 つの境界に統合する。
- basename 衝突を rename ではなく境界分離で解決することで、将来同種の衝突が起きても再発しない構造になる。

### 却下した選択肢

| 案 | 却下理由 |
|---|---|
| **A. ルート conftest を条件分岐化 (`if "image_annotator_lib/tests" not in rootdir: 注入をスキップ`)** | `sys.modules` 注入は `conftest.py` モジュールロード時点 (= collection より前) に発生するため、rootdir/conftest hierarchy 判定が間に合わない。さらに lib 側テストが「LoRAIro 側 mock 無し」で torch を実体ロードして hang する可能性が残る。 |
| **B. 単一 pytest セッションで `--ignore` / `--collect-ignore-glob` を増やす** | conftest 責務漏れの根本原因は残る。basename 衝突対応も `--ignore` を増やす局所回避になり、coverage 計測対象も混在する。 |
| **C. basename 衝突を rename で解決** | `local_packages/genai-tag-db-tools` は submodule のため LoRAIro 側で勝手に rename できない。仮に rename しても conftest 責務問題は別途解決が必要。 |
| **D. local_packages 配下に独自 `.venv` を作って完全分離** | parallel-execution rules (Issue #222 教訓) で禁止している `.venv` 重複の温床。`uv run --active` Hook ブロックや tensorflow 重複ダウンロードのリスクが大きい。CI では working-directory 分離で十分。 |
| **E. path filter (`paths:` フィルタ) で job 条件実行** | 初期段階で導入すると CI drift に気づきにくくなる。本 ADR では全 job 常時実行から始め、安定化後に別 Issue で導入を検討する。 |

### 既存資産・ADR との整合

- **ADR 0016 (Coverage Threshold Policy, amended)**: 本 ADR が `genai-tag-db-tools` の `source` 包含判断を更新する (別 job で独立計測へ移行)。ADR 0016 の「`image-annotator-lib` を `source` から除外」判断はそのまま維持。
- **`tests/conftest.py` の lib mock 注入は削除しない**。本 ADR は mock 注入経路を維持したまま、セッション境界で責務干渉を断つ設計。
- **Python 3.12/3.13 二系統管理**: LoRAIro 本体は `>=3.12,<3.14`、image-annotator-lib は `>=3.12,<3.13`。lib CI job は Python 3.12 で固定する。3.13 統一は将来検討するが本 ADR のスコープ外。

## Consequences

### 良い点

- `uv run pytest` の意味が明確になる: 「LoRAIro 本体テストのみ」。引数なし呼び出しが期待通り完走する。
- conftest / import namespace / coverage / Python バージョンの 4 軸責務が package 境界に揃い、各境界の前提が独立する。
- `coverage-gate` の `fail_under=75` が LoRAIro 本体のみを対象にする明確な品質ゲートになる。local package の coverage 低下が本体 gate に影響しなくなる。
- basename 衝突の局所回避 (`--ignore=...test_worker_service.py`) を撤去でき、将来同種の衝突も構造的に発生しない。
- image-annotator-lib に独立 CI が初めて立ち上がる (現状は `refresh-models.yml` のみで pytest CI 無し)。

### 悪い点・トレードオフ

- CI job 数が 3 → 5 に増加し、全体実行時間が伸びる (lib の torch/tensorflow セットアップは初回キャッシュ無しで数分かかる)。`actions/setup-uv` のキャッシュと marker 除外 (`not heavy` 等) で軽減する。
- Python 3.12/3.13 二系統管理が必要 (lib CI のみ Python 3.12)。将来 lib を 3.13 対応にする別 Issue が必要。
- ローカル開発者は「全テスト確認 = `make test-all`」と「本体だけ = `make test`」の使い分けを意識する必要がある。Makefile help と CLAUDE.md でガイドする。
- `local_packages/genai-tag-db-tools` は submodule のため、CI checkout で `submodules: recursive` を明示する必要がある (既に lint / typecheck / test-unit / test-integration は対応済み)。
- **`make test-iam-lib` は LoRAIro root `.venv` を共有する** (#291 amendment 2026-05-19): `cd local_packages/image-annotator-lib && UV_PROJECT_ENVIRONMENT=/workspaces/LoRAIro/.venv uv run --no-sync pytest` で LoRAIro `.venv` (Python 3.13、named volume) を共有。bind mount I/O 制約 (LoRAIro #288) を解消、tensorflow 重複 install を回避。
  - iam-lib dev deps (`pytest-clarity` / `pytest-mock` / `pytest-xdist`) は LoRAIro `[dependency-groups] dev` に統合済 (ADR 0024 L90 (a) を解決)。
  - `--no-sync` フラグで LoRAIro `.venv` が iam-lib pyproject に合わせて re-sync されるのを防止。
  - pytest セッション境界 = package 境界 の invariant は維持 (cwd = package root、conftest は iam-lib 側、coverage 計測は package 自身の `fail_under`)。
  - **`make test-genai-tag` は本 amendment scope 外**、現状の `cd <pkg> && uv run pytest` (package 配下に独立 `.venv`) を維持。
- (b) torch/torchvision の collection lazy import 問題は pytest セッション境界維持で回避できるため、本 amendment では未対応。完全な single pytest invocation 化 (`uv run pytest` でルートから lib tests も collect) は依然として scope 外。

### 運用ルール

- 新規 package を `local_packages/` に追加する場合は、本 ADR に従い独立 CI job を追加する。ルート `testpaths` / `coverage.source` に追加してはならない。
- `tests/conftest.py` で新たな `sys.modules` mock を追加する場合は、その mock 対象 package の tests を `testpaths` に含めないことを必ず確認する (本 ADR の core invariant)。
- `coverage-gate` に local package の coverage を combine してはならない。各 package は package 自身の `fail_under` を運用する。
- path filter による job 条件実行は本 ADR の scope 外。導入する場合は別 ADR で議論する。

## Related

- **Issue**: #247 (uv run pytest 全 testpaths 実行が collection error で停止する)
- **更新する ADR**: 0016 (Coverage Threshold Policy) — `genai-tag-db-tools` の `source` 包含判断を更新
- **前提となる ADR**: 0016 (`image-annotator-lib` の `source` 除外判断)
- **関連 PR review**: PR #251 Codex P2 r3236152479 — multi-venv 懸念。順次実行前提 + CI runner 隔離で本 ADR では WontFix、完全 single-venv 化は別 Issue 候補。
- **関連ファイル**:
  - `pyproject.toml` (`testpaths` / `coverage.run.source`)
  - `Makefile` (`test` / `test-iam-lib` / `test-genai-tag` / `test-all`)
  - `.github/workflows/ci.yml` (job 分離)
  - `tests/conftest.py` (lib mock 注入)
