---
type: ADR
title: pytest Test Responsibility Separation by Package
status: "Accepted (created), 2026-05-19 (amended #291: single-venv via UV_PROJECT_ENVIRONMENT)"
timestamp: 2026-05-13
tags: []
---
# ADR 0024: pytest Test Responsibility Separation by Package

## Context

Issue #247 において、ルートディレクトリ `/workspaces/LoRAIro` から引数なしで `uv run pytest` を実行すると、テスト全体が `Interrupted: 31 errors during collection` で停止することが判明した。原因は、`pyproject.toml` の `testpaths` に含まれる `local_packages/image-annotator-lib/tests/` 側で 31 件の収集エラー(collection error)が発生することにある。

根本原因は、pytest 実行境界の責務分離が崩れている点である。具体的には次の 2 点が問題になっている。

1. **`tests/conftest.py` のモック注入がライブラリ自身のテストに波及する(主因、29 件)**
   LoRAIro 本体の GUI テストでは、torch や tensorflow の動的ロードによるハングを防ぐため、`tests/conftest.py` がモジュールレベルで `sys.modules["image_annotator_lib"]` を `types.ModuleType` ベースのモックに差し替えている。この隔離は LoRAIro 本体のテストには必須である。しかし、ルート pytest が `local_packages/image-annotator-lib/tests/` まで収集すると、モックがライブラリ自身のテストにも継承される。その結果、`parent_module = <MagicMock>` に対して `AttributeError: __spec__` が発生し、テスト収集が失敗する。
2. **ファイル名の衝突(副次、1 件)**
   `tests/unit/gui/services/test_worker_service.py` と `local_packages/genai-tag-db-tools/tests/gui/unit/test_worker_service.py` のベース名が同一であるため、単一の pytest セッションでは `import file mismatch` が発生する。CI では `--ignore=...test_worker_service.py` で局所的に回避していたが、責務境界としては脆弱である。

つまり、ルート pytest はインポート前提・`conftest.py` の責務・カバレッジ計測対象が異なる 3 種類のテストを同一プロセスに混在させていた。

| 対象 | `conftest.py` の前提 | カバレッジ対象 | Python |
|---|---|---|---|
| LoRAIro 本体 | `tests/conftest.py`(ライブラリモック必須) | `src/lorairo` | 3.13 |
| image-annotator-lib | ライブラリ側 `conftest.py`(実体インポート前提) | `image_annotator_lib` | **3.12**(`>=3.12,<3.13`) |
| genai-tag-db-tools | パッケージ側 `conftest.py` | `src/genai_tag_db_tools` | 3.13 |

なお、ADR 0016(Coverage Threshold Policy, amended)ではすでに、image-annotator-lib について「torch/ML がヘッドレス CI でハングするため `tests/conftest.py` でモック化し、CI では 0% となるため `[tool.coverage.run] source` から除外する」と明文化している。本 ADR は、パッケージ境界で計測責務を分離するこの判断を、カバレッジだけでなく pytest セッション境界まで一貫させる拡張である。

## Decision

**pytest セッション境界をパッケージ境界に揃える。** LoRAIro リポジトリ内のテスト実行は、以下の 3 つの独立した pytest セッションで構成する。これにより、`conftest.py`・インポート名前空間・カバレッジ・Python バージョンの責務を明確に分離する。

| セッション | 作業ディレクトリ | `testpaths` | Python | 起動方法 |
|---|---|---|---|---|
| LoRAIro 本体 | `/workspaces/LoRAIro` | `["tests"]` | 3.13 | `uv run pytest` / `make test` |
| image-annotator-lib | `local_packages/image-annotator-lib` | `["tests"]` | 3.13 | `make test-iam-lib`(LoRAIro ルート `.venv` 共有 + `--no-sync`) |
| genai-tag-db-tools | `local_packages/genai-tag-db-tools` | `["tests"]` | 3.13 | `make test-genai-tag` |

具体的な固定事項は以下のとおりである。

1. **ルート `pyproject.toml` の `testpaths` を `["tests"]` のみに固定する。**
   `pythonpath` は LoRAIro 本体がローカルパッケージを editable 依存としてインポートする経路に必要なため維持する。
2. **ルート `[tool.coverage.run] source` を `["src"]` のみに固定する。**
   ADR 0016 で `genai-tag-db-tools` を `source` に含めていた判断を本 ADR で更新し、別ジョブで独立してカバレッジを計測する方針へ切り替える。
3. **CI ワークフローをパッケージ単位のジョブに分離する。**
   - `test-unit` / `test-integration`: LoRAIro 本体のみを対象とする。`local_packages/*/tests` の引き渡し、`--cov=...genai-tag-db-tools/src/...`、および `--ignore=...test_worker_service.py` の局所回避を削除する。
   - `test-genai-tag-db-tools`(新規): `working-directory: local_packages/genai-tag-db-tools` で独立実行する。
   - `test-image-annotator-lib`(新規): `working-directory: local_packages/image-annotator-lib` かつ Python 3.12 で独立実行する。初期段階ではマーカー `-m "not real_api and not heavy and not system_integration"` を指定し、高速・標準テストのみを実行する。
     - 注記: ADR 0026 および iam-lib ADR 0001 amended(2026-05-18)により、現行運用では旧 `real_api` / `heavy` / `system_integration` マーカーは `calls_real_webapi` / `downloads_and_runs_model` に置換済みである。最新の CI フィルタは `.github/workflows/ci.yml` と `docs/testing.md` を参照すること。
   - `coverage-gate`: LoRAIro 本体の `coverage-unit` と `coverage-integration` のみを `coverage combine` の対象とする。ローカルパッケージのカバレッジは別アーティファクトとして保持し、本体の `fail_under=75` には混ぜない。
4. **ベース名衝突の対応は別 pytest セッションへの自然分離で解決する。**
   リネームや名前空間の強制は行わない。
5. **Makefile ターゲットを以下のとおり定義する。**
   - `make test`: LoRAIro 本体のみを実行する。
   - `make test-iam-lib` / `make test-genai-tag`: 各パッケージルートへ `cd` して `uv run pytest` を実行する。
   - `make test-all`: `$(MAKE)` チェーンで 3 セッションを順次実行する(単一の pytest 呼び出しに混ぜない)。

## Rationale

### なぜ「pytest セッション境界 = パッケージ境界」を選んだか

- `tests/conftest.py` で `sys.modules` を直接書き換える必要があるのは LoRAIro 本体のテストだけである。一方、ライブラリ自身のテストは実体インポートの検証を目的とする。`conftest.py` の責務境界・pytest セッション境界・パッケージ境界を一致させることで、互いの前提が干渉しなくなる。
- ADR 0016 の時点で、カバレッジ `source` をパッケージ境界で分離する判断は確立していた。pytest セッションだけが全テストを混在させたまま残っていたことが歪みの原因であった。本 ADR でセッション境界もカバレッジ境界に揃え、`conftest.py`・カバレッジ・Python バージョンの 3 つの責務を 1 つの境界に統合する。
- ベース名衝突をリネームではなく境界分離で解決することで、将来同種の衝突が起きても再発しない構造になる。

### 却下した選択肢

| 案 | 却下理由 |
|---|---|
| **A. ルート `conftest.py` を条件分岐化する**(`if "image_annotator_lib/tests" not in rootdir:` で注入をスキップ) | `sys.modules` 注入は `conftest.py` のモジュールロード時点(テスト収集より前)に発生するため、rootdir や conftest 階層の判定が間に合わない。さらに、ライブラリ側テストが LoRAIro 側モックなしで torch を実体ロードしてハングする可能性も残る。 |
| **B. 単一 pytest セッションで `--ignore` / `--collect-ignore-glob` を増やす** | `conftest.py` の責務漏れという根本原因が残る。ベース名衝突も `--ignore` による局所回避にとどまり、カバレッジ計測対象も混在する。 |
| **C. ベース名衝突をリネームで解決する** | `local_packages/genai-tag-db-tools` はサブモジュールのため LoRAIro 側から勝手にリネームできない。仮にリネームしても `conftest.py` の責務問題は別途解決が必要になる。 |
| **D. `local_packages` 配下に独自 `.venv` を作って完全分離する** | 並列実行ルール(Issue #222 の教訓)で禁止している `.venv` 重複の温床となる。`uv run --active` フックによるブロックや tensorflow の重複ダウンロードのリスクが大きい。CI では作業ディレクトリの分離で十分である。 |
| **E. パスフィルタ(`paths:`)でジョブを条件実行する** | 初期段階で導入すると CI の乖離に気づきにくくなる。本 ADR では全ジョブの常時実行から始め、安定化後に別 Issue で導入を検討する。 |

### 既存資産・ADR との整合

- **ADR 0016(Coverage Threshold Policy, amended)**: 本 ADR で `genai-tag-db-tools` の `source` 包含判断を更新し、別ジョブでの独立計測へ移行する。`image-annotator-lib` を `source` から除外する判断はそのまま維持する。
- **`tests/conftest.py` のライブラリモック注入は削除しない**: モック注入経路を維持したまま、セッション境界で責務干渉を断つ設計とする。
- **Python 3.12/3.13 の二系統管理**: LoRAIro 本体は `>=3.12,<3.14`、image-annotator-lib は `>=3.12,<3.13` である。ライブラリ CI ジョブは Python 3.12 で固定する。3.13 への統一は将来検討とするが、本 ADR のスコープ外とする。

## Consequences

### 良い点

- `uv run pytest` の意味が「LoRAIro 本体のテストのみ」と明確になり、引数なし呼び出しが期待どおり完走する。
- `conftest.py`・インポート名前空間・カバレッジ・Python バージョンの 4 軸の責務がパッケージ境界に揃い、各境界の前提が独立する。
- `coverage-gate` の `fail_under=75` が LoRAIro 本体のみを対象とする明確な品質ゲートになる。ローカルパッケージのカバレッジ低下が本体ゲートに影響しなくなる。
- ベース名衝突の局所回避(`--ignore=...test_worker_service.py`)を撤去でき、将来同種の衝突も構造的に発生しない。
- image-annotator-lib に初めて独立した pytest CI が立ち上がる(従来は `refresh-models.yml` のみで pytest CI がなかった)。

### 悪い点・トレードオフ

- CI ジョブ数が 3 から 5 に増え、全体の実行時間が延びる。特にライブラリの torch / tensorflow セットアップは初回キャッシュなしで数分かかるため、`actions/setup-uv` のキャッシュとマーカー除外(`not heavy` 等)で軽減する。
- Python 3.12/3.13 の二系統管理が必要になる(ライブラリ CI のみ Python 3.12)。将来ライブラリを 3.13 対応にする別 Issue が必要である。
- ローカル開発者は、全テスト確認(`make test-all`)と本体のみ(`make test`)の使い分けを意識する必要がある。Makefile のヘルプと CLAUDE.md で案内する。
- `local_packages/genai-tag-db-tools` はサブモジュールのため、CI のチェックアウトで `submodules: recursive` を明示する必要がある(lint / typecheck / test-unit / test-integration は対応済み)。
- **`make test-iam-lib` は LoRAIro ルート `.venv` を共有する(#291 amendment 2026-05-19)**:
  `cd local_packages/image-annotator-lib && UV_PROJECT_ENVIRONMENT=$(CURDIR)/.venv uv run --no-sync pytest` により、LoRAIro の `.venv`(Python 3.13、名前付きボリューム)を共有する。これにより bind mount の I/O 制約(LoRAIro #288)を解消し、tensorflow の重複インストールを回避する。
  - `$(CURDIR)/.venv` は Makefile 内で動的に解決されるため、Dev Container(`/workspaces/LoRAIro/`)とワークツリー(`/tmp/worktrees/<wt>/`)の両方で同一ターゲットが動作する。
  - `make test-iam-lib` は内部で `_ensure-root-venv`(`uv sync --dev`)を前提ターゲットとして実行し、新規チェックアウトや開発依存追加直後のインストール漏れを防ぐ。
  - iam-lib の開発依存(`pytest-clarity` / `pytest-mock` / `pytest-xdist`)は LoRAIro の `[dependency-groups] dev` に統合済みである(ADR 0024 L90 (a) を解決)。
  - `--no-sync` フラグにより、カレントディレクトリが iam-lib ルートの状態で LoRAIro `.venv` が iam-lib の `pyproject.toml` に合わせて自動再同期されるのを防ぐ。
  - pytest セッション境界 = パッケージ境界の不変条件は維持される(作業ディレクトリはパッケージルート、`conftest.py` は iam-lib 側、カバレッジ計測はパッケージ自身の `fail_under`)。
  - **`make test-genai-tag` は本改訂の対象外**とし、従来の `cd <pkg> && uv run pytest`(パッケージ配下の独立 `.venv`)を維持する。
- **(b) torch/torchvision の収集時遅延インポート問題**は pytest セッション境界の維持で回避できるため、本改訂では未対応とする。単一の pytest 呼び出し(ルートから `uv run pytest` でライブラリテストも収集する構成)は引き続きスコープ外とする。

### 運用ルール

- 新規パッケージを `local_packages/` に追加する場合は、本 ADR に従って独立した CI ジョブを追加する。ルートの `testpaths` や `coverage.source` に追加してはならない。
- `tests/conftest.py` で新たな `sys.modules` モックを追加する場合は、対象パッケージのテストを `testpaths` に含めないことを必ず確認する(本 ADR の中核となる不変条件)。
- `coverage-gate` にローカルパッケージのカバレッジを結合してはならない。各パッケージは自身の `fail_under` を運用する。
- パスフィルタによるジョブの条件実行は本 ADR のスコープ外とする。導入する場合は別 ADR で議論する。

## Related

### 2026-09-05 amendment: portable shared-environment tasks

上記の genai-tag 独立 `.venv` 維持と、テスト前提ターゲットでの暗黙同期を更新する。Windows および Dev Container の開発タスクは `scripts/dev_tasks.py` から実行し、Git 共通ディレクトリ(Git common directory)で検出した共有チェックアウトの `.venv` を全 3 パッケージで利用する。現在の全ワークスペースメンバーは Python 3.13 に対応している。

- 依存導入は共有チェックアウトで明示的に `install-dev` を実行する。`uv sync --all-packages --all-groups` により、メンバーの開発依存もまとめて導入する。
- 通常のテスト・整形・型検査では同期を行わない。ワークツリー内への環境作成や、実行ごとの共有環境更新も行わない。環境更新と他の検証は並行実行しない。
- ソース解決は対象ワークツリーの `PYTHONPATH` を優先する。pytest は各パッケージルートで別プロセスとして起動し、`conftest.py` とカバレッジの境界は従来どおり維持する。
- 別 OS の絶対パス、ワークツリーローカルの `.venv`、未導入の環境はエラーとし、復元方法を提示する。
- Windows ホストとコンテナの `.venv` 自体は別実体とし、既存の名前付きボリュームを維持する。

既存の uv と Python 標準ライブラリを再利用し、新しいタスク管理依存は増やさない。根拠は https://docs.astral.sh/uv/concepts/projects/config/#project-environment-path および https://docs.astral.sh/uv/reference/cli/#uv-sync である。

### 2026-09-05 amendment: task prerequisite boundaries (Issue #1302)

PR #1301 では、文書専用タスクにもアプリ全体の前提条件を要求してしまい、個別免除の後も同じ境界の指摘が再発した。タスク名ごとの例外を増やすのではなく、`TaskSpec` に実行環境・必要なパッケージ集合・ワークツリーインポート経路の要否・ヘッドレス実行の要否を宣言する。

- `stdlib`: ADR / OKF 系タスクは起動中の Python を直接使い、Git 共通ディレクトリ・共有 `.venv`・uv・サブモジュール検査を経由しない。drift 本体の Git 利用とフォールバックは維持する。
- `shared`: インストール済みの共有 Python を直接使う。以前の `uv run --no-sync` ラッパーは不要とし、通常実行には環境解決・作成・同期の経路を持たせない。アプリをインポートするタスクのみ、対象ワークツリーの必要ソースを優先する。
- `sync`: `install` / `install-dev` のみが uv を呼ぶ。共有メインチェックアウトに限定し、ワークスペースの全メンバーを要求する。共有環境を並行して書き換えない。
- Ruff や UI 生成にはアプリの全サブモジュールを要求しない。パッケージ単独のテストや整形は、そのパッケージだけを検査する。コマンドと依存の一覧は `scripts/DEV_TASKS.md` にまとめる。
- 環境更新と成果物の書き込みは別責務である。整形・インデックス生成・UI 生成・テスト出力は従来どおり行う。なお、この宣言は OS の権限やサンドボックス機構ではない。

既存ツールも比較したが、新しいタスクフレームワークは追加しない。Nox は通常 virtualenv を作成し、Poe の uv executor は環境選択を追加し、Just は OS 別のシェル設定が必要になる。いずれも LoRAIro 固有の共有環境や必要サブモジュールの判断が別途必要となるため、既存の標準ライブラリ製ランナーに薄い分類表を持たせるのが最小の変更である。

参考: [Nox](https://nox.thea.codes/en/stable/usage.html)、[Poe](https://poethepoet.natn.io/guides/without_poetry.html)、[Just](https://just.systems/man/en/prerequisites.html)。

全タスクの必要パッケージ欠落行列と、Git・uv・venv・サブモジュールのない文書専用の実プロセスを Windows と Linux で検証する。Kit の設定・フック・ワークツリーライフサイクルは本変更の対象外とする。

### Links

- **Issue**: #247(`uv run pytest` の全 `testpaths` 実行が収集エラーで停止する)
- **更新する ADR**: 0016(Coverage Threshold Policy)— `genai-tag-db-tools` の `source` 包含判断を更新
- **前提となる ADR**: 0016(`image-annotator-lib` の `source` 除外判断)
- **関連 PR レビュー**: PR #251 Codex P2 r3236152479 — 複数 `.venv` の懸念。順次実行前提と CI ランナー隔離により本 ADR では WontFix とし、完全な単一 `.venv` 化は別 Issue 候補とする
- **関連ファイル**:
  - `pyproject.toml`(`testpaths` / `coverage.run.source`)
  - `Makefile`(`test` / `test-iam-lib` / `test-genai-tag` / `test-all`)
  - `.github/workflows/ci.yml`(ジョブ分離)
  - `tests/conftest.py`(ライブラリモック注入)
