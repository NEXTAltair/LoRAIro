# CLAUDE.md

本ファイルは、Claude Code(claude.ai/code)がこのリポジトリで作業する際の指針をまとめたものである。

## 基本原則

- 依頼されたことだけを行い、余計な変更や不足を残さない。
- 目的達成に本当に必要な場合を除き、ファイルを新規作成しない。
- 新規ファイルを作るより、常に既存ファイルの編集を優先する。
- ユーザーから明示的に求められない限り、ドキュメントファイル(`*.md`)や README を自発的に作成しない。

## 仮想環境ルール(厳守)

**常にプロジェクトルートの仮想環境を使う。**

- 仮想環境の場所: `/workspaces/LoRAIro/.venv`
- ローカルパッケージ配下(`local_packages/*/`)から `uv run` を直接実行しない。
- 必ずプロジェクトルート(`/workspaces/LoRAIro/`)から `uv run` を実行する。
- ローカルパッケージは `uv sync` による editable インストールでプロジェクトルートの `.venv` を共有する。

```bash
# 正しい例: LoRAIro 本体のテストはプロジェクトルートから実行する
cd /workspaces/LoRAIro
uv run pytest                                # tests/ のみを収集(ADR 0024)

# 正しい例: ローカルパッケージのテストは Makefile 経由でパッケージルートから独立実行する
# (ADR 0024: パッケージごとに独立 .venv が作られるが、make の直列実行と CI ランナー隔離で
#  Issue #222 の並列ドリフトを防ぐ)
make test-iam-lib    # cd local_packages/image-annotator-lib && uv run pytest
make test-genai-tag  # cd local_packages/genai-tag-db-tools  && uv run pytest

# 誤った例: 複数パッケージで uv sync を並列実行する(Issue #222 の原因)
(cd local_packages/image-annotator-lib && uv sync) &
(cd local_packages/genai-tag-db-tools  && uv sync) &
wait
```

**並列実行の注意**: 複数の `uv run` を同時に実行する場合は [.claude/rules/parallel-execution.md](.claude/rules/parallel-execution.md) を参照する。`uv run --active` はフックで自動ブロックされる。

## 開発コマンド

### 環境セットアップ

```bash
make setup                 # サブモジュール(local_packages/*)取得 + uv sync --dev
# 個別に実行する場合:
#   git submodule update --init --recursive
#   uv sync --dev

# UI コードの生成(.ui ファイルを変更したら必ず実行)
uv run python scripts/generate_ui.py
```

### アプリケーション起動

```bash
uv run lorairo            # GUI アプリケーションを起動
make run-gui              # Makefile 経由で起動
```

### テスト実行

```bash
# LoRAIro 本体のテストのみ(testpaths = ["tests"]、ADR 0024)
uv run pytest
uv run pytest -m unit              # ユニットテストのみ
uv run pytest -m integration       # 統合テストのみ
uv run pytest -m gui               # GUI テスト(ヘッドレス)
uv run pytest -m bdd               # BDD テスト(pytest-bdd)
uv run pytest --cov=src --cov-report=xml

# ローカルパッケージのテストは各パッケージルートで独立した pytest セッションとして実行
make test-iam-lib                  # image-annotator-lib(Python 3.12)
make test-genai-tag                # genai-tag-db-tools
make test-all                      # 3 セッションを直列実行
```

### 診断ログ

`src/lorairo/utils/config.py` では `platformdirs` を使い、`DEFAULT_LOG_PATH = user_log_path("LoRAIro", appauthor=False) / "lorairo.log"` を既定ログ出力先としている。

- Windows: `%LOCALAPPDATA%\LoRAIro\Logs\lorairo.log`
- Linux / Dev Container: `~/.local/state/LoRAIro/log/lorairo.log`
- ワークスペースログ(git 管理外): `logs/lorairo.log`、`logs/image-annotator-lib.log`

これらは最優先のデバッグ情報源である。実行時エラー、GUI 操作の失敗、アノテーションやモデル周りの問題、ワーカー失敗、アプリ挙動に関わるテスト失敗を調べる際は、ユーザーの指示や添付がなくても自ら確認する。

読み込みは必ず行数を制限して行う。

```bash
tail -200 ~/.local/state/LoRAIro/log/lorairo.log
tail -200 logs/lorairo.log
tail -200 logs/image-annotator-lib.log
```

ログファイルが存在しない場合はその旨を記録して先へ進む。ログを git に追加したり、応答に大量のログを貼り付けたりせず、関連箇所だけを要約する。

### コード品質チェック

```bash
make format                # Ruff でフォーマットと自動修正
make mypy                  # 型チェック
uv run ruff format src/ tests/
uv run ruff check src/ tests/ --fix
uv run mypy -p lorairo
```

### データベースマイグレーション

```bash
alembic upgrade head       # マイグレーションを適用
alembic revision --autogenerate -m "description"
```

### クリーンアップ

```bash
make clean                 # ビルド成果物とキャッシュを削除
```

## プロジェクトアーキテクチャ

### 主要コンポーネント

**アプリケーションの入口**
- エントリーポイント: `src/lorairo/main.py`
- メインウィンドウ: `src/lorairo/gui/window/main_window.py`
- 設定ファイル: `config/lorairo.toml`

**データ層**
- スキーマ定義: `src/lorairo/database/schema.py`
- リポジトリ群: `src/lorairo/database/repository/`
- マネージャー: `src/lorairo/database/db_manager.py`
- コア接続層: `src/lorairo/database/db_core.py`

**サービス層(2 層構成)**
- **ビジネスロジックサービス**(`src/lorairo/services/`)— Qt 非依存
- **GUI サービス**(`src/lorairo/gui/services/`)— Qt 依存、Signal ベース
- 全サービスの一覧は [docs/services.md](docs/services.md) を参照

**AI 連携(ローカルパッケージ)**
- **image-annotator-lib**: `src/lorairo/annotation/annotator_adapter.py`、`annotation_runner.py`
- **genai-tag-db-tools**: `src/lorairo/database/repository/annotation_record.py`(公開 API: `search_tags()`、`register_tag()`)

**ワーカー**: `src/lorairo/gui/workers/`(DatabaseRegistration、Annotation、Search、Thumbnail)

**ストレージ**: `lorairo_data/project_name_YYYYMMDD_NNN/`(SQLite データベースと `image_dataset/`)

### 主な設計パターン

- **リポジトリパターン**: データアクセスをリポジトリ層に抽象化する。
- **サービス層**: ビジネスロジックを GUI とデータアクセスから分離する。
- **ワーカーパターン**: Qt の `QThread` と `QObject.moveToThread()` で非同期処理を実装する。
- **Qt 非依存コア**: コアサービスは Qt に依存せず、GUI ラッパーはコンポジションで包む。
- **依存性注入(DI)**: サービスを GUI コンポーネントへ注入する。

### ローカル依存パッケージ

- `local_packages/genai-tag-db-tools` — タグ DB 管理。ユーザー DB は `format_id` 1000 以上を使用し、起動時に自動初期化する。
- `local_packages/image-annotator-lib` — AI アノテーション。対応プロバイダーは OpenAI、Anthropic、Google、ローカル ML。

### 開発時の規約

- **コードスタイル**: Ruff(最大行長 108)、型ヒント必須、モダン Python 型記法(`list` / `dict`、`X | None`)、`os` ではなく `pathlib` を使用。`# type: ignore` や `# noqa` は使わず、`Any` を避け、具体的なクラス名を付ける。
- **エラー処理**: 広範な `Exception` ではなく具体的な例外(`FileNotFoundError`、`ValueError` など)だけを捕捉する。
- **ドキュメント**: Google スタイルの docstring、日本語の実装コメント、Issue 番号付きの `FIXME` / `PENDING` タグを使う。
- **テスト**: カバレッジ 75% 以上を維持する。`pytest-qt` では `qtbot.waitSignal()` や `qtbot.waitUntil()` を使い、`QMessageBox` は必ずモック化する。
- **データベース**: Alembic マイグレーションは `src/lorairo/database/migrations/` に配置する。
- **ログ**: Loguru を使用する。`INFO` はバッチ単位のサマリーのみ、`DEBUG` に項目単位の詳細を出す。詳細は `.claude/rules/logging.md` を参照する。
- **依存管理**: `uv.lock` は git で追跡する(ADR 0025、uv 公式推奨)。`pyproject.toml` やサブモジュールピンを更新した際は lockfile もあわせてコミットする。
  - **AI 推論 SDK**(`pydantic-ai`、`anthropic`、`openai`、`google-genai`、`litellm`、`transformers`、`huggingface-hub`、`torch`)は常に最新の安定版を使う。`pyproject.toml` には下限(`>=`)のみを指定し、上限(`<X.Y`)は付けない。
  - 新モデル対応・WebAPI バグ修正・月次見直しのタイミングで `uv lock --upgrade-package <name>` を実行して更新する。詳細は [.claude/rules/dependency-management.md](.claude/rules/dependency-management.md) を参照する。

## 問題解決のアプローチ

**設計原則**: YAGNI、可読性最優先、単一責任の原則

**解決策の検討手順**:
1. 候補となるアプローチを最低 3 案挙げる。
2. 複雑さ・保守性・性能のトレードオフを評価する。
3. 最適な解決策を選ぶ。
4. 決定内容を `docs/decisions/` に ADR として記録する。

**ユーザーへ確認すべきタイミング**: 原則への違反が避けられないとき、3 回以上試行しても詰まったとき、要件が曖昧なとき、確立されたアーキテクチャへ影響する設計変更が必要なとき。

## トラブルシューティング

- **テストが検出されないとき**: ローカルパッケージ内に競合する `.venv` がないか確認し、`uv sync --dev` を実行する。
- **UI 生成の不整合**: 「`SearchFilterService` が設定されていません」や `filterSearchPanel` 不在のエラーが出た場合は、次を実行して UI コードを再生成する(`.ui` ファイル変更後は毎回必須)。

```bash
uv run python scripts/generate_ui.py
```

## クイックリファレンス

### 開発ワークフロー(調査 → 計画 → 実装 → 検証 → 記録)

かつての `/planning`、`/implement`、`/test`、`/build-fix`、`/code-review`、`/save-session` コマンドは廃止済みであり、現在はネイティブ機能・superpowers・LoRAIro スキルに統合されている。

- **調査**: `check-existing` スキルで要件を整理し、既存ライブラリや `local_packages/` を確認する。
- **計画**: ネイティブの Plan Mode(`/plan`)または superpowers の `brainstorming` → `writing-plans` を使う(`rules/planning-memory.md` により ADR と教訓の事前確認が強制される)。
- **実装**: superpowers の `executing-plans` / `test-driven-development` に加え、`lorairo-repository-pattern` や `lorairo-qt-widget` スキルを使う(ブランチ運用は `rules/git-workflow.md` に従う)。
- **検証**: superpowers の `test-driven-development` と `lorairo-test-generator` スキル(test-sync を含む)、および `rules/testing.md` に従う。LoRAIro では共通ルールのコミット前 mypy に優先して、全体の型チェックを CI に任せる。ローカルでは変更対象の Ruff と関連する pytest を実行し、型定義の変更や型エラーの調査時に限り、対象を絞って mypy を実行する。
- **デバッグ**: superpowers の `systematic-debugging` と `build-error-resolver` エージェントを使う。
- **レビュー**: 組み込みの `/code-review`、`code-reviewer` / `security-reviewer` エージェント、superpowers の `requesting-code-review` を使う。
- **記録**: `docs/decisions/` の ADR と `docs/lessons-learned.md` を更新する。

### エージェント

実験的機能として Agent Teams が有効になっている(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)。推奨チームサイズは 3〜5 人、1 人あたり 5〜6 タスクとし、担当ファイルを分離して競合を防ぐ。

- **investigation**: コードベースの調査・分析
- **solutions**: 多角的な問題解決・アプローチ評価
- **code-formatter**: コード品質管理(Ruff 統合)
- **test-runner**: テスト実行と結果解析
- **db-schema-reviewer**: スキーマとマイグレーションの品質検査

### スキル

`.agents/skills/` に以下のスキルを配置している。

- `check-existing`: 実装前の既存解調査
- `lorairo-repository-pattern`、`interface-design`、`lorairo-qt-widget`、`lorairo-test-generator`
- `lorairo-cli-db-access`: 画像 DB の調査・編集は `sqlite3` 直接実行ではなく `lorairo-cli` を使う
- `lorairo-design-capture`、`sqlalchemy-query-patterns`、`okf-bundle`、`lazy-import-refactor`
- `pr-maintainer`: PR 保守ポリシー
- `pr-autoloop`: PR 保守ループの自走

スキルは `npx skills`(Vercel)で管理し、`.claude/skills/<name>` は `.agents/skills/<name>` へのシンボリックリンクとなっている。外部ソースのスキル([altairs-agent-dev-kit](https://github.com/NEXTAltair/altairs-agent-dev-kit) 由来およびサードパーティ製)は git 追跡対象外であり、`make setup` または `make skills-install` で `skills-lock.json` から自動復元する(詳細は `docs/development-workflow.md` を参照)。

#### `pr-autoloop` の Claude Code 実装

Claude Code で `pr-autoloop` スキルのポーリング待機を回す際は、**`ScheduleWakeup` による自走**を使う(修正・返信・エスカレーション・マージの判断基準は `pr-maintainer` スキルと ADR 0039 に従う)。

- 1 ターンを 1 ポーリングサイクルとし、`gh pr view` と `gh pr checks` で状態を取得して `continue` / `repair` / `escalate` / `merge` / `timeout` のいずれかに分類する。
- 分類が `continue` の場合は `ScheduleWakeup(delaySeconds=180, prompt=スキル再実行)` で次のサイクルを予約する。3 分間隔は ADR 0039 に準拠し、180 秒はプロンプトキャッシュが維持される範囲(270 秒未満)に収まる。
- 合計 20 分(約 6〜7 サイクル)を上限とし、到達したら PR に日本語コメントを残して停止する。
- **`sleep && <次のコマンド>` のような直列スリープや先頭スリープは実行環境でブロックされる**(`.claude/rules/testing.md`)。`ScheduleWakeup` を使えないセッションでのみ、上限付きの bash `until` ループで代替する。

### PR 作成前チェック

`gh pr create` でサブモジュール(`local_packages/*`)の変更を含む PR を作成する場合は、事前に CI と同等のフィルタ条件でローカルテストを実行する(`.claude/rules/testing.md` の「CI-equivalent filter」を参照)。この確認はフック(`.claude/hooks/hook_pre_pr_submodule_check.py`)によって強制される。例外的にスキップする場合は、コマンド内に `CI-EQUIV-TESTED` マーカーを含める。

### 設定ファイルの例

```toml
# config/lorairo.toml
[api]
openai_key = ""
claude_key = ""
google_key = ""

[directories]
database_base_dir = "lorairo_data"

[log]
level = "INFO"
```

## 関連ドキュメント

- [アーキテクチャ](docs/architecture.md) — システム設計原則
- [サービスカタログ](docs/services.md) — 全サービス一覧
- [テストガイド](docs/testing.md) — テスト戦略
- [外部パッケージ統合](docs/integrations.md) — ローカルパッケージ連携
- [設計判断(ADR)](docs/decisions/README.md) — ADR インデックス
- [開発の教訓](docs/lessons-learned.md) — バグパターンと教訓
- [開発ワークフロー](docs/development-workflow.md) — 開発プロセス詳細
- [ドキュメント管理方針](docs/documentation-maintenance.md) — ドキュメントの維持ルール
