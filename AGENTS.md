# リポジトリガイドライン(AGENTS.md)

## プロジェクト構成とモジュール配置

- `src/lorairo/` — メインの Python パッケージ(エントリーポイント: `lorairo.main:main`)
  - `config/`: 設定管理
  - `database/`: SQLAlchemy と Alembic によるデータベース層
  - `gui/`: PySide6 による GUI
  - `image/`: 画像処理
  - `utils/`: 共通ヘルパー
- `tests/` — pytest テストスイートとフィクスチャ(`tests/resources/` にテスト用アセットを配置)
- `local_packages/` — アプリから利用する editable インストールのサブモジュール(`genai-tag-db-tools/`、`image-annotator-lib/` など)
- `docs/` — 開発者向けリファレンスおよび ADR
- `site/` — 多言語対応の Starlight ユーザーガイド
- `scripts/` — 開発用ユーティリティ(GUI 起動、UI 生成、テスト実行など)

## ビルド・テスト・開発コマンド

- 実行依存のインストール: `uv sync`(または `make install`)
- 開発依存と editable セットアップ: `make install-dev`
- GUI の起動(Windows): `uv run --no-sync lorairo` または `make run-gui`(コンテナ内のテストはヘッドレス実行)
- テスト実行: `make test`(リポジトリ既定の pytest 設定で実行)
- 型チェック: `make mypy`(`lorairo` パッケージに対して厳格チェックを実行)
- フォーマット・Lint 修正: `make format`(Ruff を適用)
- ユーザーガイド(`site/` 配下):
  - `npm ci`: ドキュメント依存のインストール
  - `npm run build`: 翻訳の整合性検証とサイトビルド
  - `npm run preview`: ビルド結果のプレビュー
  - 日本語を原本とする執筆ルールは `site/README.md` を参照

## コーディング規約と命名規則

- Python 3.12、インデントはスペース 4 つ、最大行長は 108 文字とする。
- フォーマッター・リンターには Ruff を使う。文字列はダブルクォートで統一し、インポート順は Ruff に任せる。
- `*/gui/designer/` 配下のコードは Qt Designer からの自動生成物であり、Lint 対象外とする。特別な理由がない限り手で編集しない。

## テスト方針

- 使用フレームワーク: `pytest`、`pytest-qt`、`pytest-bdd`
- 命名規則: ファイルは `test_*.py`、クラスは `Test*`、関数は `test_*`
- カバレッジ基準: 75% 未満で失敗(`pyproject.toml` の `coverage` 設定に従う)
- 高速なユニットテストの実行例: `uv run pytest -m "fast"`

## 診断ログの活用

`src/lorairo/utils/config.py` では、`platformdirs` を用いて既定のログ出力先 `DEFAULT_LOG_PATH = user_log_path("LoRAIro", appauthor=False) / "lorairo.log"` を定義している。

- Windows: `%LOCALAPPDATA%\LoRAIro\Logs\lorairo.log`
- Linux / Dev Container: `~/.local/state/LoRAIro/log/lorairo.log`(あわせて git 管理外のワークスペースログ `logs/lorairo.log` と `logs/image-annotator-lib.log` も出力される)

これらのログは最優先のデバッグ情報源として扱う。実行時エラー、GUI 操作の失敗、アノテーションやモデル周りの不具合、ワーカー失敗、アプリ挙動に関わるテスト失敗を調査する際は、ユーザーから指示や添付がなくても自ら確認する。

ログの読み込みは行数を制限して行う。

- `tail -200 ~/.local/state/LoRAIro/log/lorairo.log`
- `tail -200 logs/lorairo.log`
- `tail -200 logs/image-annotator-lib.log`

対象ファイルが存在しない場合はその旨を記録して先へ進む。ログファイルを git に追加したり、応答へ大量のログをそのまま貼り付けたりせず、関連する行だけを要約して報告する。

## コミットとプルリクエストの規約

- コミットメッセージは Conventional Commits に従う(例: `feat: ...`、`refactor: ...`、`docs: ...`、`test: ...`、`chore: ...`)。
- PR には変更内容の明確な説明、テスト結果、GUI 変更がある場合はスクリーンショットを含める。
- 関連する Issue をリンクし、マイグレーションや設定変更がある場合は必ず明記する。

## LoRAIro のスキル運用

リポジトリ固有のスキルは `.agents/skills/` に配置して git で管理しており、`.claude/skills/<name>` からリンクしている。外部スキル(kit やサードパーティ由来の `check-existing`、`pr-maintainer`、`pr-autoloop` など)は git 追跡対象外であり、`make setup` または `make skills-install` で `skills-lock.json` から復元する。

該当する作業を始める前に、必ず対象スキルの `SKILL.md` を読むこと。手順・安全制約・検証方法がそこに記載されている。全 32 スキルの一覧、重複時の優先ルール、作業別の最小チェックリスト、検証済みウォークスルーは [`docs/development/agent-skills-guide.md`](docs/development/agent-skills-guide.md) を参照する。

| 作業内容 | スキル | 主な制約 |
|---|---|---|
| 画像 DB の参照・編集(画像・タグ・アノテーション・エラー) | `lorairo-cli-db-access` | `lorairo_data/*` へ `sqlite3` を直接使わず、`lorairo-cli` を経由する(9p マウントと WAL の保護) |
| リポジトリ・永続化コードの新規実装 | `lorairo-repository-pattern` | `src/lorairo/database/repository/`(`BaseRepository`)経由で型安全なトランザクションを使う |
| 新規クエリ・遅いクエリ・N+1 の調査 | `sqlalchemy-query-patterns` | `selectinload` などで一括取得し、`EXPLAIN` で実行計画を確認する |
| PySide6 ウィジェット・ワーカー・Qt Designer 作業 | `lorairo-qt-widget` | `LoRAIroWorkerBase`(`QObject` + `moveToThread`)を使い、`.ui` 変更後は `scripts/generate_ui.py` で再生成する |
| Qt 実装前の UI 設計意図の整理 | `interface-design` | 先に設計意図とトークン(`src/lorairo/gui/theme.py`)を決め、その後に `lorairo-qt-widget` で実装する |
| ワイヤーフレームや claude.ai デザインとのレイアウト同期 | `lorairo-design-capture` | 静的 HTML ではなく、描画時の実行状態を取得する |
| テスト作成 | `lorairo-test-generator` | `QMessageBox` はモック化し、固定時間待機ではなく `qtbot.waitUntil` を使う |
| ADR や概念ドキュメントの追加・編集 | `okf-bundle` | frontmatter を単一の情報源(SSoT)とし、索引は `make adr-index` で再生成する |
| 機能のスコープ検討(再利用か新規実装か) | `check-existing`(外部) | まず `local_packages/` を確認する |
| エージェント作成 PR の保守 | `pr-maintainer` / `pr-autoloop`(外部) | 下記の「エージェントの Git ワークフロー」に従う |

### スキルの優先順位と重複時のルール

- **追跡済みの LoRAIro スキルを最優先する**: `.agents/skills/` の LoRAIro 固有スキルと `skills-lock.json` の汎用外部スキルが重複する場合は、常に LoRAIro スキルに従う(例: `sql-optimization-patterns` や `database-migration` より `lorairo-repository-pattern` + `sqlalchemy-query-patterns` を優先し、`python-testing-patterns` や `qa-expert` より `lorairo-test-generator` を優先する)。
- **GUI 作業の順序**: `interface-design`(設計意図・トークン)→ `lorairo-design-capture`(描画時のプロトタイプ状態)→ `lorairo-qt-widget`(PySide6 実装)の順に進める。React/Vercel 向けの外部スキル(`vercel-*`、`deploy-to-vercel`)は Python/Qt コードへ適用しない。`web-design-guidelines` は `site/` の Starlight ユーザーガイドにのみ適用する。

## エージェントの Git ワークフロー

### ワークツリーの作成と完了基準

- Issue 解決、機能開発、PR 準備、複数ファイルにわたる実装作業は、必ず `.agents/worktree/` 配下の専用ワークツリーから開始する。
- 共有メインチェックアウト(`/workspaces/LoRAIro`)で実装作業の編集・ステージ・コミット・リベース・プッシュを行わない。
- ワークツリーは最新のリモートベースから作成する。
  - 例: `git fetch origin && git worktree add .agents/worktree/issue-123 -b fix/issue-123 origin/main`
- ユーザーが明示的に「公開前で止める」「ドラフトのままにする」と指示しない限り、Issue 解決や機能実装の完了は「実装 → 検証 → コミット → プッシュ → レビュー可能な PR の作成 → CI・レビューの保守自走 → 安全確認後のマージ」までを一連のゴールとする。
- ローカル実装だけで作業を終えず、PR URL と最終的な監視状態を成果として報告する。認証・ネットワーク・検証失敗・スコープ不明などで PR 作成がブロックされた場合は、黙って止めずにブロッカーを明示して報告する。

### ワークツリー内での `uv` と共有 `.venv` の運用

- `.agents/worktree/` 配下で `uv` を実行するときは、現在の OS チェックアウトの Git 共通ルートにある共有 `.venv` を使う。
  - Windows ではホスト側チェックアウトの `.venv` を使う。
  - Dev Container ではホスト側チェックアウトを `/workspaces/LoRAIro` に読み書きマウントし、`/workspaces/LoRAIro/.venv`(ホスト `.venv` 上にマウントされた名前付きボリューム `lorairo-venv`)を使う。
- `python scripts/configure_agent_environment.py` を実行し、現在の OS の**ユーザーレベル**の Codex 設定および Claude 設定に `UV_PROJECT_ENVIRONMENT` を設定する。
- OS 固有の絶対パスを共有の `.codex/config.toml`、`.claude/settings.json`、`.claude/settings.local.json` に書き込まない。プロジェクト設定はユーザー設定を上書きするため、`CODEX_HOME` の変更やホームボリューム追加だけでは解決しない(本リポジトリでは、プロジェクト設定に仮想環境パスを置く kit 側の案内例を上書きしている)。
- 共有環境が見当たらない場合は、`uv` に誤ったパスへ新規環境を作らせず、作業を止めて実際の OS 環境を正しく構成する。
- Codex のコマンドに毎回 `UV_PROJECT_ENVIRONMENT=...` を付けない。コマンド承認の妨げになり、通常のコマンド形状が隠れてしまう。環境設定が効いていないシェルでのみ、インラインでの `UV_PROJECT_ENVIRONMENT` 指定をフォールバックとして使う。
- ワークツリー内に専用の `.venv` を作成したり、共有 `.venv` へのシンボリックリンクを張ったりしない。Python バージョン不一致時に `uv` が環境を削除・再作成して共有環境を壊す恐れがあり、掃除の残骸も増える。共有環境を使えない場合は、`uv` 単体のヘルプや確認コマンドだけを実行できる。
- 検証コマンドは対象のワークツリー内から実行する。CLI のスモークテスト、読み取り専用チェック、並列ワーカーでの検証において editable インストールの解決先が曖昧になり得る場合は、`uv run --no-sync` に加えて、対象ワークツリーの `src` とローカルパッケージの `src` を指す `PYTHONPATH` を明示する。
- 既定で同期が走る `uv run` や `uv sync`、依存更新などの環境書き換え操作は、共有 `.venv` への書き込みとして扱う。複数ワーカーで並列実行せず、必ず直列に実行する。

### PR の公開状態・保守自走・マージ後の片付け

- エージェントが作成する PR は、原則としてドラフトではなくレビュー可能な状態(ready for review)で作成する。ユーザー指示でドラフト作成した PR も、レビュー許可が出たらすぐに ready へ切り替え、PR 保守自走(CI ポーリング、bot レビュー確認、ワークツリー内での修正、日本語での返信、安全なマージ、最終状態の報告)を開始・再開する。
- PR 作成直後に `gh pr view "$PR" --json isDraft -q .isDraft` を確認する。`true` の場合は `gh pr ready "$PR"` を実行して再確認する。ドラフト状態の PR に `gh pr merge --auto` を設定しない。
- PR のマージが完了したら、変更の残っていないワークツリーを即座に `git worktree remove <path>` または共有チェックアウトからの `make worktree-cleanup-merged` で削除する。マージ済みワークツリーを放置しない。
- **`pr-autoloop` の Codex 実装(待機方式の上書き)**: PR 保守ループの共通仕様は `pr-autoloop` スキル(ポリシーは `pr-maintainer`、判断根拠は ADR 0039)で定義されている。Codex はこのループを**同一セッション内でインライン実行**する。PR 作成後、約 3 分間隔で最大 20 分間 `gh pr view` と `gh pr checks` をポーリングし、各サイクルを `continue` / `repair` / `escalate` / `merge` / `timeout` に分類する。対応可能な指摘は PR ワークツリーで修正して日本語で返信し、安全ならスカッシュマージする。Codex では Claude Code の `ScheduleWakeup` を使わず、セッション内でポーリングして最終監視状態を報告する。修正回数が上限(4 回)を超える場合はループを続けずエスカレーションする。
- エージェント固有のルールは本ファイルおよび `.claude/rules/git-workflow.md` への参照にとどめ、矛盾するワークフロー記述を重複させない。

### クロス OS 環境(Windows / Dev Container)の注意点

- Windows と Dev Container は同じチェックアウトを共有しているため、片方の OS で作成したワークツリーは、もう片方の OS から解決できない絶対パスとして登録される(`git worktree list` で `prunable` と表示される)。パスが見つからないからといって別 OS のワークツリーを prune・修復・削除してはならない。片付けは必ず作成元の OS 上でローカル変更を確認してから行う。
- セットアップ処理は両チェックアウトに共通フック・ルール・エージェント・スキルを復元する。スキルはポータブルなディレクトリコピーであり、`core.hooksPath=.githooks` が現在の OS の Python を使って共通フックを実行する。片方の OS の Python パスを埋め込む `pre-commit install` は実行しない。

## Codex の並列エージェント運用

- 大規模なタスク、複数 Issue・複数 PR にまたがる作業、広範囲のリファクタリングでは、1 セッションで直列処理せず積極的にサブエージェントを活用する。
- Issue・モジュール・責務境界・テストや検証の役割ごとに分割できる場合は並列ワーカーを使う。
- 各ワーカーには必ず `.agents/worktree/` 配下の専用ワークツリーを割り当て、複数ワーカーに同じワークツリーを編集させない。
- 実装開始前に、各ワーカーへ明確なブランチ名と担当ファイル・モジュールを割り当てる。
  - 例: `git worktree add .agents/worktree/issue-304 -b fix/issue-304-thumbnail origin/main`
- ワーカー間の書き込み範囲は可能な限り重複させない。2 つのワーカーが同一ファイルを編集する必要がある場合は、リード側で実行順を制御するか統合を直接担当する。
- リードとなる Codex セッションは、ワーカーの担当範囲定義、編集の競合確認、差分レビュー、テスト実行または確認、PR 作成、マージ後の親 Issue チェックリスト更新を担う。
- 独立して動かせる役割は、実装ワーカー、調査用エクスプローラー、検証用 `test-runner`、PR レビュー用 `code-reviewer` へ適切に振り分ける。
- 1 ファイルの軽微な修正や 1 コマンドで終わる作業など、調整コストが作業量を上回る場合はサブエージェントを起動しない。
- 親 Issue に独立したサブ Issue のチェックリストがある場合は、まとめ PR の明示的な指示がない限り、並列ワーカーで 1 サブ Issue につき 1 PR とする構成を既定とする。

## Codex の tmux 監視運用

- 大規模な並列作業では、分割ペインでワーカーの進捗を監視するために `tmux` セッションを作成してよい。
- 実用的な範囲で「ワーカーのワークツリーごとに 1 ペイン+リード調整用 1 ペイン」の構成を推奨する。
- 各ワーカーペインには、ワーカー名、ワークツリーパス、ブランチ名、git ステータス、最新コミット、実行中の検証コマンドまたはログを表示する。
- `tmux` による監視は観測目的であり、各ワーカーに専用の `.agents/worktree/` を割り当てる原則に代わるものではない。
- セッション名は親 Issue やブランチに紐づく分かりやすい名前を付ける(例: `codex-308`、`codex-agent-rules`)。
- 必要な長時間 `tmux` セッションを残す場合は、セッション名・稼働中ペイン・実行コマンドをユーザーへ報告する。

## セキュリティと設定の注意点

- API キーはローカルの `.env` に保存し(`.env.example` を参照)、秘密情報をコミットしない。
- ローカルデータとログ(`logs/`、`lorairo_data/`)はバージョン管理に含めない。

<!-- agent-kit:begin -->
## Agent kit rules

altairs-agent-dev-kit 0.7.1 が管理する区画。手で編集せず `agent_kit.py install` で更新する。
Claude Code と Antigravity は同じ内容を自分の rules ディレクトリから読み込む。
それ以外のエージェントは次の一覧に従ってファイルを読む。

作業を始める前に必ず読む:
- [.agents/rules/parallel-execution.md](.agents/rules/parallel-execution.md) — uv を並列に走らせて共有 venv を壊さないための運用

該当する作業の前に読む:
- [.agents/rules/coding-style.md](.agents/rules/coding-style.md) — Python 実装の lint / 型チェック設定と lint 結果の扱い (対象: `**/*.py`, `pyproject.toml`)
- [.agents/rules/dependency-management.md](.agents/rules/dependency-management.md) — 依存パッケージを追加・更新するとき。AI 推論 SDK は最新追従、他は計画的 bump
- [.agents/rules/logging.md](.agents/rules/logging.md) — ログ出力を追加・変更するとき。レベル設計と量の基準
- [.agents/rules/planning-memory.md](.agents/rules/planning-memory.md) — 計画・設計を始める前に ADR / 過去の計画 / lessons-learned を確認するとき
- [.agents/rules/security.md](.agents/rules/security.md) — Ruff S ルールで検出できないセキュリティ判断 (秘密情報・入力検証等) (対象: `**/*.py`)
- [.agents/rules/testing.md](.agents/rules/testing.md) — テストを書く・実行する・カバレッジを判断するとき (pytest)
<!-- agent-kit:end -->
