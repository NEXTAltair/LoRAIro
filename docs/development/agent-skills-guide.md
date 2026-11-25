---
type: Guide
title: Agent Skills 棚卸しとワークフロー別適用ガイド
status: Accepted
timestamp: 2026-11-09
tags: [process, cli, db-read, db-write, gui-widget, worker, validation]
depends_on: [pyside6, sqlalchemy, sqlite]
---

# Agent Skills 棚卸しとワークフロー別適用ガイド

本ドキュメントは Issue #1477(#1357 の残件)に基づき、リポジトリ内の全 Agent Skill(`.agents/skills/` の追跡対象スキル 8 件および `skills-lock.json` の外部スキル 24 件、計 32 件)を棚卸しした記録である。重複解消の優先順位ルール、古い参照の修正記録、代表 5 ワークフローの最小手順、および実タスクによる検証結果をまとめる。

---

## 1. スキル棚卸し一覧(全 32 件)

スキルは以下の 3 区分に分類する。同一タスクに複数のスキルが該当する場合は、**区分 A(LoRAIro 固有 / 開発ハーネス必須)を常に最優先**する。

- **A. Primary(LoRAIro 固有 / ハーネス標準)**: リポジトリ追跡対象(`sourceType: local`)の 8 件と、`NEXTAltair/altairs-agent-dev-kit` 由来の開発ワークフロースキル 10 件。
- **B. Secondary(汎用 Python / DB 参考)**: `wshobson/agents` 由来の汎用ベストプラクティス 6 件。LoRAIro 固有規約(`AGENTS.md`、区分 A スキル、ADR)と矛盾する場合は区分 A を優先する。
- **C. Out-of-Stack(対象外 / 条件付き参照)**: `vercel-labs/agent-skills` 由来の React、Next.js、React Native、Vercel デプロイ系 6 件(LoRAIro 本体の Python + PySide6 スタックでは使用しない)と、Starlight ドキュメントサイト(`site/`)の Web UI レビュー時にのみ補助参照する `web-design-guidelines` 1 件。

### 1.1 区分 A: Primary(LoRAIro 固有・追跡対象 8 件)

| スキル名 | 管理元 | 主な責務 |
|---|---|---|
| `lorairo-cli-db-access` | `.agents/skills/`(追跡対象) | `lorairo_data/<project>/image_database.db` の調査・編集を `sqlite3` 直接接続ではなく `lorairo-cli` 経由で安全に行う |
| `lorairo-repository-pattern` | `.agents/skills/`(追跡対象) | `src/lorairo/database/repository/` の Aggregate 単位 Repository 実装規約(`BaseRepository` 継承とトランザクション境界) |
| `sqlalchemy-query-patterns` | `.agents/skills/`(追跡対象) | LoRAIro の SQLite + SQLAlchemy 2.0 クエリ最適化(`selectinload`、バッチ操作、Keyset ページング、`EXPLAIN QUERY PLAN`) |
| `interface-design` | `.agents/skills/`(追跡対象) | デスクトップ・ツール UI のデザイン意図、ドメイン探索、トークン設計、コンポーネント駆動同期原則 |
| `lorairo-design-capture` | `.agents/skills/`(追跡対象) | 操作プロトタイプ(`docs/design/wireframes/wireframes.html` 等)の描画時 JS 変換後における実効状態を Qt・DS ミラーへ反映する |
| `lorairo-qt-widget` | `.agents/skills/`(追跡対象) | PySide6 ウィジェット、タブ分割(`gui/tab/`)、Signal/Slot、`LoRAIroWorkerBase`(`QThread` + `moveToThread`)、Qt Designer 統合 |
| `lorairo-test-generator` | `.agents/skills/`(追跡対象) | `pytest` / `pytest-qt` テスト作成、カバレッジ 75% 以上の維持、`QMessageBox` モック、差分起点のテスト同期 |
| `okf-bundle` | `.agents/skills/`(追跡対象) | Open Knowledge Format(OKF)バンドルの frontmatter 検証(`okf_validate.py`)と索引・テーブル生成(`okf_index.py`) |

### 1.2 区分 A: Primary(開発ハーネス・ワークフロー外部スキル 10 件)

| スキル名 | 管理元(`skills-lock.json`) | 主な責務 |
|---|---|---|
| `check-existing` | `NEXTAltair/altairs-agent-dev-kit` | 新機能実装前に `local_packages/`(`image-annotator-lib`、`genai-tag-db-tools`)や既存モジュール、外部ライブラリを調査する |
| `pr-maintainer` | `NEXTAltair/altairs-agent-dev-kit` | エージェント作成 PR の保守ポリシー(CI・bot レビュー確認、同一 worktree での修正、日本語返信、マージ判定、4 回上限エスカレーション) |
| `pr-autoloop` | `NEXTAltair/altairs-agent-dev-kit` | PR 保守を完了まで自動継続するポーリングループ(Codex セッションでは `AGENTS.md` のインラインポーリング規約に従う) |
| `github-ops` | `NEXTAltair/altairs-agent-dev-kit` | `gh` CLI および GitHub API を用いた Issue・PR・Actions の調査と操作 |
| `lazy-import-refactor` | `NEXTAltair/altairs-agent-dev-kit` | `torch` などの重いネイティブ依存を関数内遅延 import へリファクタリングする(ADR 0010 準拠) |
| `docs-freshness-audit` | `NEXTAltair/altairs-agent-dev-kit` | ドキュメントのリンク切れ、古いパス参照、実装との乖離を定期監査する |
| `claude-md-progressive-disclosurer` | `NEXTAltair/altairs-agent-dev-kit` | `AGENTS.md` や `CLAUDE.md` の肥大化を抑え、詳細を専用ドキュメントやスキルへ分離する |
| `goal-prompt-crafter` | `NEXTAltair/altairs-agent-dev-kit` | 自律マルチターン実行の完了条件(Definition of Done)を検証可能な形で定義する |
| `prompt-optimizer` | `NEXTAltair/altairs-agent-dev-kit` | 曖昧な要求を EARS 形式の明確な仕様へ変換する |
| `skill-creator` | `NEXTAltair/altairs-agent-dev-kit` | 新規 `SKILL.md` の設計、作成、更新ガイド |

### 1.3 区分 B: Secondary(汎用 Python / DB 参考スキル 6 件)

| スキル名 | 管理元(`skills-lock.json`) | 位置づけ・優先関係 |
|---|---|---|
| `sql-optimization-patterns` | `wshobson/agents` | 汎用 RDBMS(PostgreSQL・MySQL 中心)の SQL 最適化。**LoRAIro では `sqlalchemy-query-patterns` を優先する** |
| `database-migration` | `wshobson/agents` | 汎用ゼロダウンタイム移行ガイド。**LoRAIro はローカル SQLite + Alembic(`src/lorairo/database/migrations/`)のため、Alembic 標準手順と `lorairo-repository-pattern` を優先する** |
| `python-testing-patterns` | `wshobson/agents` | 汎用 pytest パターン。**LoRAIro では `lorairo-test-generator` を優先する** |
| `qa-expert` | `NEXTAltair/altairs-agent-dev-kit` | 大規模 QA プロセス・90% 目標テンプレート。**LoRAIro のカバレッジ基準(75% 必須)とパッケージ境界(ADR 0024)は `lorairo-test-generator` を優先する** |
| `python-type-safety` | `wshobson/agents` | Python 3.12 の型ヒント、Protocol、Generic の汎用リファレンス(`make mypy` 補助) |
| `python-error-handling` | `wshobson/agents` | 例外階層と部分失敗処理の汎用リファレンス |
| `python-performance-optimization` | `wshobson/agents` | `cProfile` などによる汎用プロファイリングリファレンス |

### 1.4 区分 C: Out-of-Stack(対象外 / 条件付きスキル 7 件)

| スキル名 | 管理元(`skills-lock.json`) | 扱い |
|---|---|---|
| `web-design-guidelines` | `vercel-labs/agent-skills` | PySide6 GUI には**適用しない**。`site/`(Starlight ユーザーガイド)の Web アクセシビリティ確認時のみ補助参照できる |
| `deploy-to-vercel` | `vercel-labs/agent-skills` | **対象外**(LoRAIro はデスクトップアプリと GitHub Pages ドキュメントの構成である) |
| `vercel-cli-with-tokens` | `vercel-labs/agent-skills` | **対象外** |
| `vercel-composition-patterns` | `vercel-labs/agent-skills` | **対象外**(React 19 向け。Qt ウィジェット分割は `lorairo-qt-widget` を使用する) |
| `vercel-react-best-practices` | `vercel-labs/agent-skills` | **対象外** |
| `vercel-react-native-skills` | `vercel-labs/agent-skills` | **対象外** |
| `vercel-react-view-transitions` | `vercel-labs/agent-skills` | **対象外** |

---

## 2. 重複領域の解消ルールと古い参照の修正記録

### 2.1 重複するスキル群の使い分けルール

1. **DB・Repository・SQL クエリ**(`lorairo-repository-pattern` + `sqlalchemy-query-patterns` と `sql-optimization-patterns` / `database-migration` の使い分け)
   - 稼働中 DB(`lorairo_data/*/image_database.db`)のレコード調査やタグ編集には **`lorairo-cli-db-access`** を使う。
   - Python コードでの永続化層実装では、**`lorairo-repository-pattern`**(クラス設計とトランザクション境界)と **`sqlalchemy-query-patterns`**(N+1 回避、バッチ操作、SQLite 最適化)をセットで使う。
   - `sql-optimization-patterns` と `database-migration` は PostgreSQL などのサーバー型 DB を前提としているため、LoRAIro の SQLite 実装では参照しない。
2. **GUI デザイン・実装**(`interface-design` → `lorairo-design-capture` → `lorairo-qt-widget` と `web-design-guidelines` の使い分け)
   - 新規画面やウィジェットのトーン&マナー、トークン設計は **`interface-design`** で決める。
   - 操作プロトタイプ(`docs/design/wireframes/wireframes.html`)や Claude Design から画面構成やナビゲーション順を同期する際は、**`lorairo-design-capture`** で描画時 JS 変換後の実効状態を特定する。
   - PySide6 のクラス実装、Signal/Slot 配線、`LoRAIroWorkerBase` 連携、`.ui` 再生成は **`lorairo-qt-widget`** に従う。
   - `web-design-guidelines` や `vercel-*` は PySide6 の作業では参照しない。
3. **テスト作成・品質検証**(`lorairo-test-generator` と `python-testing-patterns` / `qa-expert` の使い分け)
   - **`lorairo-test-generator`** を唯一の実務基準とする(`pyproject.toml` のカバレッジ 75% 下限、`QMessageBox` モック必須、`qtbot.waitSignal` / `waitUntil`、ADR 0024 のパッケージ別 pytest セッション分離)。
4. **PR 保守**(`pr-maintainer` + `pr-autoloop` + `github-ops`)
   - **`pr-maintainer`** が判断ポリシー(修正対象、マージ条件、エスカレーション基準)を定め、**`pr-autoloop`** がポーリング継続手順を定める(Codex セッションでは `AGENTS.md` のインラインポーリング規約を適用する)。

### 2.2 追跡対象スキルの古い参照の洗い出しと修正結果

Issue #1477 の監査で `.agents/skills/*/SKILL.md` 内の現行コードツリーと乖離していた参照を洗い出し、以下のとおり更新した。

| スキル | 検出された古い参照・課題 | 修正内容 |
|---|---|---|
| `lorairo-repository-pattern` | ADR 0035(#423)で廃止された `src/lorairo/database/db_repository.py` と `tests/database/test_db_repository.py` を参照していた。SQLAlchemy 1.x の `session.query()` と `from src.lorairo...` を使用していた | `src/lorairo/database/repository/*.py`(`BaseRepository` 継承の Aggregate 分割構成)と `tests/unit/database/repository/test_*_repository.py`、SQLAlchemy 2.0 の `select()`、`from lorairo...` へ更新した |
| `sqlalchemy-query-patterns` | ファイル構成で廃止済みの `src/lorairo/database/db_repository.py` を参照し、スキーマ図に `ScoreLabel`、`Project`、`CropRelation`、`GenerationMetadata`、`ProviderBatchJob` が未掲載だった | `src/lorairo/database/repository/` の各モジュールと現行スキーマ構成へ更新した |
| `lorairo-qt-widget` | 非同期ワーカー例が汎用 `QRunnable` の擬似コード(`worker.signals.progress`、`_worker_manager.submit`)であり、ディレクトリ構成に `src/lorairo/gui/tab/` が未記載だった | `LoRAIroWorkerBase[T](QObject)` と `WorkerManager.start_worker()`(`QThread` + `moveToThread`)の実装パターン、および `src/lorairo/gui/tab/` と `src/lorairo/gui/theme.py` を明記した |
| `lorairo-design-capture` | #867 / #869 で廃止された `TabReorganizationService` に言及し、検証ワンライナーが `.venv/bin/python` を直接実行していた | `MainWindow._setup_*_tab()` による `src/lorairo/gui/tab/*_tab.py` 構成と `uv run --no-sync python` へ更新した |
| `lorairo-test-generator` | ディレクトリ図が旧構造(`tests/database/`、`tests/services/`、`tests/gui/` 直下)のままで、未追跡の `.claude/rules/testing.md` や外部専用エージェント名を参照していた | 現行の `tests/unit/{cli,database/repository,gui/tab,gui/widgets,gui/window,gui/workers,services}/`、`tests/integration/`、`tests/bdd/` の構造と、`QMessageBox` モック、`qtbot.waitSignal`、ADR 0024 パッケージ境界へ更新した |
| `okf-bundle` | 使用例が `.claude/skills/okf-bundle/scripts/...` を参照しており、worktree などで投影前に解決できない場合があった | 正準パス `.agents/skills/okf-bundle/scripts/...` および `make adr-okf` / `make adr-index` / `make docs-okf` へ更新した |
| `interface-design` | トークン同期先が抽象表現のみだった | LoRAIro の実ファイル(`src/lorairo/gui/theme.py`、`docs/design/theme-v1/hifi-mock.html`、`docs/design/lorairo-design-system/`、`docs/design/wireframes/wireframes.html`)と `lorairo-design-capture` への連携を明記した |
| `lorairo-cli-db-access` | `lorairo-cli describe <command>` で空白を含むサブコマンド(例: `"images search"`)をクォートする必要がある点が未記載で、新規コマンド群(`dataset`、`maintenance`)も表に未掲載だった | `describe "<group> <command>"` のクォート指定と `dataset`・`maintenance` グループを追記した |

---

## 3. 代表ワークフロー別の適用条件と最小手順

### ワークフロー 1: 画像 DB の調査・レコード操作

- **適用条件**: `lorairo_data/<project>/image_database.db` 内の画像、タグ、キャプション、スコア、エラーレコードの件数確認、検索、タグ編集を行うとき。
- **使用スキル**: [`lorairo-cli-db-access`](../../.agents/skills/lorairo-cli-db-access/SKILL.md)
- **最小手順**:
  1. 稼働中の DB ファイルに `sqlite3` で直接接続しない(9p bind mount 上の `disk I/O error` と WAL 破損を防ぐ)。
  2. コマンド仕様を確認する場合は、`uv run --no-sync lorairo-cli list-commands` または `uv run --no-sync lorairo-cli describe "<group> <command>"` を実行する。
  3. まず count-first(既定)で件数を確認する。
     `uv run --no-sync lorairo-cli --json images list -p <project>`
  4. 500 件以下に絞り込んでから `--fetch`(または `--emit-ids`)でデータを取得・編集する。
  5. CLI にない集計 SQL(`GROUP BY` 等)が必要な場合のみ、`.db`、`.db-wal`、`.db-shm` の 3 ファイルを `/tmp` などの一時領域へコピーしたスナップショットに対して読み取り専用で `sqlite3` を実行する。

### ワークフロー 2: Repository・SQL クエリの追加・最適化

- **適用条件**: `src/lorairo/database/` 配下に永続化メソッドや検索フィルタを追加・改修するとき、または N+1 クエリや遅いクエリを改善するとき。
- **使用スキル**: [`lorairo-repository-pattern`](../../.agents/skills/lorairo-repository-pattern/SKILL.md) + [`sqlalchemy-query-patterns`](../../.agents/skills/sqlalchemy-query-patterns/SKILL.md)
- **最小手順**:
  1. 対象エンティティを管轄する Aggregate Repository(`src/lorairo/database/repository/{image,annotation_record,model,project,error_record,provider_batch,crop_relation,generation_metadata}.py`)を特定する。
  2. `BaseRepository` の `with self.session_factory() as session:` コンテキストマネージャ内で、SQLAlchemy 2.0 の `select()`、`insert()`、`update()` を用いて実装する。ビジネスロジックは Service 層に置き、Repository は純粋なデータアクセスに保つ。
  3. 1:N 関連の取得には `selectinload()`、大量件数の書き込みにはバルク操作または `BATCH_CHUNK_SIZE` 分割を適用し、ループ内クエリ(N+1)を避ける。
  4. 必要に応じて `ImageDatabaseManager`(`src/lorairo/database/db_manager.py`)のファサードメソッドへ配線する。
  5. `tests/unit/database/repository/test_*_repository.py` にインメモリ SQLite を用いた単体テストを追加する。

### ワークフロー 3: GUI ウィジェット・非同期ワーカー・デザイン同期

- **適用条件**: PySide6 の画面、タブ、ダイアログ、ウィジェット、非同期ワーカーを新規作成または改修するとき、あるいは操作プロトタイプと GUI レイアウトを同期するとき。
- **使用スキル**: [`interface-design`](../../.agents/skills/interface-design/SKILL.md) → [`lorairo-design-capture`](../../.agents/skills/lorairo-design-capture/SKILL.md) → [`lorairo-qt-widget`](../../.agents/skills/lorairo-qt-widget/SKILL.md)
- **最小手順**:
  1. **デザイン意図と実効状態の確認**:
     - 新規 UI 要素やトークン変更を伴う場合は `interface-design` と `src/lorairo/gui/theme.py` を確認する。
     - 操作プロトタイプ(`docs/design/wireframes/wireframes.html`)からナビゲーション順や画面構成を取り込む場合は、`lorairo-design-capture` に従い、描画時 JS(`restructureNav()` 等)適用後の**実効状態**を特定する。
  2. **責務配置の決定(1 タブ = 1 専用ウィジェット)**:
     - タブ固有の UI と配線は `src/lorairo/gui/tab/*_tab.py` に置き、`MainWindow`(`src/lorairo/gui/window/main_window.py`)は配置、サービス注入、トップレベル Signal 接続(glue)のみに保つ。
     - 複数画面で共有する部品だけを `src/lorairo/gui/widgets/` に切り出す。
  3. **Qt Designer とワーカー実装**:
     - `.ui` ファイルを変更した場合は、必ず `uv run --no-sync python scripts/generate_ui.py`(または `make generate-ui`)で `*_ui.py` を再生成する。
     - 重い処理は UI スレッドで行わず、`LoRAIroWorkerBase[T](QObject)` サブクラスと `WorkerManager` / `WorkerService`(`QThread` + `moveToThread`)で非同期実行する。
     - レイアウト崩れや余白の調査では推測でサイズポリシーを変えず、`height()`、`sizeHint()`、`minimumSizeHint()` を offscreen 実測して原因を特定する。

### ワークフロー 4: テスト作成・差分同期・品質検証

- **適用条件**: 新機能、バグ修正、リファクタリングに対して単体テスト、統合テスト、GUI テストを追加・更新するとき。
- **使用スキル**: [`lorairo-test-generator`](../../.agents/skills/lorairo-test-generator/SKILL.md)
- **最小手順**:
  1. 変更対象に対応するテストファイルを `tests/unit/`、`tests/integration/`、`tests/bdd/` から特定する(例: `src/lorairo/gui/tab/foo_tab.py` なら `tests/unit/gui/tab/test_foo_tab.py`)。
  2. GUI テストでは `QMessageBox` を必ず `monkeypatch` でモックし、非同期発火待ちには固定 `qtbot.wait()` ではなく `qtbot.waitSignal()` または `qtbot.waitUntil()` を使用する。
  3. パッケージ境界(ADR 0024)を守り、LoRAIro 本体テストは本体セッションで、submodule(`image-annotator-lib`、`genai-tag-db-tools`)のテストは各パッケージのセッション(`make test-iam-lib`、`make test-genai-tag`)で実行する。
  4. worktree から検証する場合は、共有 `.venv` を汚染しないよう `uv run --no-sync` を用いて対象テスト、Ruff、Mypy を実行する。

### ワークフロー 5: ADR・OKF ドキュメントの追加・保守

- **適用条件**: `docs/decisions/` に ADR を追加・改訂するとき、または `docs/` 配下に設計・開発ドキュメントを追加・更新するとき。
- **使用スキル**: [`okf-bundle`](../../.agents/skills/okf-bundle/SKILL.md)
- **最小手順**:
  1. ドキュメント冒頭に YAML frontmatter(`type`、`title`、`status`、`timestamp`、`tags` 等。ADR 0069・ADR 0082 準拠)を記述し、メタデータは frontmatter を唯一の SSoT とする。
  2. ADR を追加・更新した場合は `make adr-index`(または `okf_index.py`)で `docs/decisions/README.md` のテーブルと `docs/decisions/index.md` を自動生成する(生成ファイルを手編集しない)。
  3. 検証コマンドを実行して frontmatter と索引の整合を確認する。
     - ADR 検証: `make adr-okf`(または `okf_validate.py` + `okf_index.py --check`)
     - 通常ドキュメント検証: `make docs-okf`

---

## 4. 実例タスクによるスキル手順の検証記録

Issue #1477 の受け入れ基準「実例タスクを 1 件以上選び、skill のとおりに作業できることを確認して結果を記録する」に基づき、以下の 2 つの実例タスクを各スキルの手順どおりに実行・検証した。

### 実例検証 A: `okf-bundle` による ADR バンドル検証および本ガイドの OKF 検証

1. **ADR バンドルの frontmatter 検証**:
   ```bash
   uv run --no-sync python .agents/skills/okf-bundle/scripts/okf_validate.py \
     --bundle-root docs/decisions \
     --require type,title,status,timestamp \
     --exclude README.md
   ```
   - **結果**: `OKF 検証 OK: docs/decisions`(終了コード 0)
2. **ADR 索引(`index.md`)の差分チェック**:
   ```bash
   uv run --no-sync python .agents/skills/okf-bundle/scripts/okf_index.py \
     --bundle-root docs/decisions \
     --index \
     --index-output docs/decisions/index.md \
     --index-title "Architecture Decision Records" \
     --exclude README.md \
     --check
   ```
   - **結果**: `OK: docs/decisions/index.md は最新 (index.md)`(終了コード 0)
3. **通常ドキュメント(本ガイド `docs/development/agent-skills-guide.md` を含む `docs/`)の OKF 検証**:
   ```bash
   uv run --no-sync python .agents/skills/okf-bundle/scripts/okf_validate.py \
     --bundle-root docs \
     --skip-missing \
     --exclude README.md,CHANGELOG.md,CLAUDE.md,AGENTS.md,GEMINI.md,SKILL.md
   ```
   - **結果**: `OKF 検証 OK: docs`(終了コード 0)

### 実例検証 B: `lorairo-cli-db-access` による CLI コマンド仕様の機械可読取得

1. **コマンド一覧の取得(`list-commands`)**:
   ```bash
   uv run --no-sync lorairo-cli list-commands
   ```
   - **結果**: 終了コード 0 で 42 コマンドの JSONL カタログおよび `read_only` / `side_effects` 契約が出力されることを確認した。
2. **個別サブコマンド仕様の取得(`describe`)**:
   - 当初 `SKILL.md` の表記 `lorairo-cli describe <command>` に従い、クォートなしで `uv run --no-sync lorairo-cli describe images search` を実行したところ、`Error: Got unexpected extra argument (search)`(終了コード 2)となった。
   - サブコマンド名を単一引数としてクォートして再実行した。
     ```bash
     uv run --no-sync lorairo-cli describe "images search"
     ```
   - **結果**: 終了コード 0 で `images search` の入出力 JSON Schema(`limit` 上限 500、count-first 既定、`--emit-ids` オプション等)が JSONL で出力されることを確認した。この知見を `.agents/skills/lorairo-cli-db-access/SKILL.md` の基本形コマンド例へフィードバックし、修正済みである。
