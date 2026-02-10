# LoRAIro 新テストアーキテクチャ設計

**作成日**: 2026-02-10
**対象**: テスト構成リファクタリング
**ステータス**: 設計完了、実装待ち

---

## 設計方針

### 原則 1: CLAUDE.md 準拠

- テストレイヤー: unit / integration / gui / bdd の 4層
- pytest マーカー統一: `@pytest.mark.unit` | `integration` | `gui` | `bdd`
- 最小カバレッジ 75% 維持
- モック対象: 外部API、ファイルシステム、ネットワークのみ（内部サービス間はモック不可）

### 原則 2: 単一責任の原則

- 各層の conftest.py は「本当に共有されるもの」のみ定義
- ローカルフィクスチャは各テストモジュール内に定義
- conftest.py の責務: その層に属する複数テストファイルが共有する初期化・モック・ヘルパーのみ

### 原則 3: 実行性能

- 現在の実行時間（推定 5-10分）から +20% 以内に抑える
- session スコープのフィクスチャ最適化でテスト起動時間を短縮
- 将来的な pytest-xdist 並列実行を妨げない構成

### 原則 4: 保守性

- テストファイル 300行以下（超える場合は分割必須）
- 新規テスト追加時の判断基準が明確（フローチャート後述）
- フィクスチャ数: 各 conftest.py で 10-15個以下

---

## 現状分析サマリー

### 定量データ（2026-02-10 時点）

| 項目 | 値 |
|---|---|
| 総テストファイル | 96個（test_*.py） |
| 総テスト関数 | 1,272個 |
| 総テストクラス | 246個 |
| pytest 収集テスト数 | 2,329 |
| conftest.py | 1個（ルートのみ、802行、34フィクスチャ） |
| unit/ テストファイル | 65個 |
| integration/ テストファイル | 25個 |
| BDD features | 2個、step_defs 1個 |
| gui/ ディレクトリ | 空（0ファイル） |

### 現在の問題点

1. **conftest.py 肥大化**: 802行、34フィクスチャが1ファイルに集約。DB/Qt/ストレージ/画像/タグDB が混在
2. **フィクスチャ重複**: `mock_db_manager`（5箇所）、`mock_config_service`（4箇所）が各テストファイルで個別定義
3. **空ディレクトリ**: `tests/gui/`、`tests/services/`、`tests/manual/`、`tests/performance/` にファイルなし
4. **マーカー不統一**: 定義は 16種あるが適用は一部のみ。unit テストの大多数にマーカーなし
5. **pytest-qt 違反**: `qtbot.wait()` 固定時間待機が 15箇所（5ファイル）
6. **BDD カバレッジ不足**: 2 feature（DB管理、ログ）のみ。GUI/AI統合のシナリオなし
7. **大規模テストファイル**: `test_thumbnail_selector_widget.py`（800+行）、`test_filter_search_integration.py`（700+行）

---

## 現状 -> 新構造のマッピング

| 現在のディレクトリ | 新構造 | アクション | 理由 |
|---|---|---|---|
| `tests/unit/` (65 files) | `tests/unit/` | conftest.py 追加 | 既存構造を維持、層別 conftest 追加 |
| `tests/integration/` (25 files) | `tests/integration/` | conftest.py 追加 | 既存構造を維持、DB/ストレージフィクスチャ移動 |
| `tests/integration/gui/` (13 files) | `tests/integration/gui/` | そのまま | GUI統合テストとして適切な配置 |
| `tests/features/` (2 files) | `tests/bdd/features/` | 移動 | BDD ディレクトリ正規化 |
| `tests/step_defs/` (1 file) | `tests/bdd/step_defs/` | 移動 | BDD ディレクトリ正規化 |
| `tests/gui/` (空) | 削除 | 削除 | unit/gui/ と integration/gui/ に統合済み |
| `tests/services/` (空) | 削除 | 削除 | unit/services/ と integration/services/ に統合済み |
| `tests/manual/` (空) | 削除 | 削除 | テストファイルなし（将来必要時に再作成） |
| `tests/performance/` (空) | 削除 | 削除 | テストファイルなし（将来必要時に再作成） |

**注意**: `tests/unit/gui/` 内のテストには `@pytest.mark.gui` が付与されているものが多い。これらは Qt 依存のユニットテストであり、ディレクトリ移動は不要。マーカーで実行制御する。

---

## 新ディレクトリ構成

```
tests/
├── conftest.py                    # ルート共通（最小限: genai-tag-db mock, Qt config, project_root）
│
├── unit/                          # ユニットテスト層（65 files）
│   ├── conftest.py               # ユニット用フィクスチャ（画像、サンプルデータ、タイムスタンプ）
│   ├── database/                 # DB リポジトリの単体テスト (8 files)
│   ├── gui/                      # Qt ウィジェット・サービスの単体テスト (34 files)
│   │   ├── cache/
│   │   ├── controllers/
│   │   ├── services/
│   │   ├── state/
│   │   ├── widgets/
│   │   ├── window/
│   │   └── workers/
│   ├── services/                 # ビジネスロジックの単体テスト (9 files)
│   ├── storage/                  # ストレージの単体テスト (1 file)
│   ├── workers/                  # ワーカーの単体テスト (1 file)
│   └── *.py                      # ルートレベル単体テスト (12 files)
│
├── integration/                   # 統合テスト層（25 files）
│   ├── conftest.py               # 統合用フィクスチャ（DB初期化、ストレージ、リポジトリ）
│   ├── database/                 # DB 統合テスト (1 file)
│   ├── gui/                      # GUI 統合テスト (13 files)
│   │   ├── widgets/
│   │   ├── window/
│   │   └── workers/
│   ├── services/                 # サービス統合テスト (1 file)
│   └── *.py                      # ルートレベル統合テスト (10 files)
│
├── bdd/                           # BDD E2E テスト層（新規ディレクトリ）
│   ├── conftest.py               # BDD 用フィクスチャ
│   ├── features/                 # Gherkin シナリオ (2 files: 移動元 tests/features/)
│   │   ├── database_management.feature
│   │   └── logging.feature
│   └── step_defs/                # ステップ定義 (1 file: 移動元 tests/step_defs/)
│       └── test_database_management.py
│
└── resources/                     # テストリソース（変更なし）
    └── img/
```

---

## テストマーカー統一

### pyproject.toml マーカー定義（整理後）

```toml
[tool.pytest.ini_options]
markers = [
    "unit: ユニットテスト（外部依存はモック）",
    "integration: 統合テスト（内部コンポーネント結合）",
    "gui: Qt GUI アクセスを含むテスト（ヘッドレス実行可能）",
    "bdd: BDD E2E テスト（pytest-bdd シナリオ）",
    "slow: 遅いテスト（5秒以上）",
    "webapi: Web API ベースのアノテーターテスト",
]
```

**削除対象マーカー** (未使用・過度に細分化):
- `fast_integration` -> `integration` に統合
- `gui_show` -> `gui` に統合（offscreen 対応済み）
- `scorer`, `tagger`, `model_factory` -> テスト内コメントで分類
- `fast`, `standard` -> `unit` に統合
- `real_api` -> `webapi` に統合
- `bdd_core` -> `bdd` に統合
- `api_model_discovery` -> `webapi` に統合

### マーカー適用ルール

| テストの場所 | 必須マーカー | 追加マーカー（任意） |
|---|---|---|
| `tests/unit/` (Qt不使用) | `@pytest.mark.unit` | なし |
| `tests/unit/gui/` (Qt使用) | `@pytest.mark.unit`, `@pytest.mark.gui` | なし |
| `tests/integration/` (Qt不使用) | `@pytest.mark.integration` | `@pytest.mark.slow` |
| `tests/integration/gui/` (Qt使用) | `@pytest.mark.integration`, `@pytest.mark.gui` | `@pytest.mark.slow` |
| `tests/bdd/` | `@pytest.mark.bdd` | なし |

### 実行コマンド

```bash
# カテゴリ別実行
uv run pytest -m unit                    # ユニットテストのみ
uv run pytest -m integration             # 統合テストのみ
uv run pytest -m gui                     # GUI テストのみ（unit + integration）
uv run pytest -m bdd                     # BDD テストのみ
uv run pytest -m "not slow"              # 遅いテストを除外

# CI/CD 段階実行
uv run pytest -m "unit and not gui"      # 最速: 純粋ロジックのみ (~20秒)
uv run pytest -m "unit"                  # 標準: 全ユニット (~60秒)
uv run pytest -m "unit or integration"   # 完全: ユニット + 統合 (~180秒)
uv run pytest                            # フル: 全テスト
```

---

## conftest.py の責務分割

### tests/conftest.py（ルート - 最小限、目標: 80-120行）

**責務**:
- genai-tag-db-tools モジュールレベルモック（全テスト必須、import前に実行）
- Qt ヘッドレス環境設定（Linux コンテナ対応）
- `project_root` フィクスチャ（参照用）

**移動対象フィクスチャ**: 34個中 27個を下位 conftest.py に移動

**残留フィクスチャ（7個）**:
1. `mock_genai_tag_db_tools` (session, autouse) - 外部パッケージモック管理
2. `configure_qt_for_tests` (session, autouse) - Qt 環境設定
3. `qapp_args` (session) - QApplication パラメータ
4. `qapp` (session) - QApplication インスタンス
5. `project_root` (session) - プロジェクトルート参照
6. `qt_main_window_mock_config` (function) - MainWindow モック設定
7. `critical_failure_hooks` (function) - エラーハンドリングテスト用

### tests/unit/conftest.py（ユニット用、目標: 120-160行）

**責務**:
- テスト画像フィクスチャ（`test_image_dir`, `test_image_path`, `test_image` 等）
- サンプルデータフィクスチャ（`sample_image_data`, `sample_processed_image_data`, `sample_annotations`）
- タイムスタンプフィクスチャ（`current_timestamp`, `past_timestamp`）
- 共通モックフィクスチャ（`mock_config_service`）

**受け入れフィクスチャ（13個）**: ルート conftest.py から移動
1. `test_image_dir` (function)
2. `test_image_path` (function)
3. `test_image` (function)
4. `test_image_array` (function)
5. `test_image_paths` (function)
6. `test_images` (function)
7. `test_image_arrays` (function)
8. `sample_image_data` (function)
9. `sample_processed_image_data` (function)
10. `sample_annotations` (function)
11. `current_timestamp` (function)
12. `past_timestamp` (function)
13. `mock_config_service` (function)

### tests/integration/conftest.py（統合テスト用、目標: 200-280行）

**責務**:
- データベース初期化（`test_engine_with_schema`、初期 ModelType/Model データ挿入）
- セッション管理（`db_session_factory`, `test_session`）
- リポジトリフィクスチャ（`test_repository`, `temp_db_repository`, `test_db_manager`）
- ファイルシステム管理（`temp_dir`, `storage_dir`, `fs_manager`）
- 外部タグDB テストフィクスチャ（`test_tag_db_path`, `test_tag_repository`, `test_image_repository_with_tag_db`）

**受け入れフィクスチャ（14個）**: ルート conftest.py から移動
1. `temp_dir` (function)
2. `storage_dir` (function)
3. `fs_manager` (function)
4. `test_db_url` (function)
5. `test_engine_with_schema` (function)
6. `db_session_factory` (function)
7. `test_session` (function)
8. `test_repository` (function)
9. `temp_db_repository` (function)
10. `test_db_manager` (function)
11. `test_tag_db_path` (function)
12. `test_tag_repository` (function)
13. `test_image_repository_with_tag_db` (function)
14. `mock_config_service` (function) - DB マネージャ用に統合テスト側でも定義

**注意**: `mock_config_service` は unit と integration 両方で必要。同一実装を conftest_helpers.py で共有するか、各層で個別定義する。推奨は各層で個別定義（依存関係を明示的に）。

### tests/bdd/conftest.py（BDD 用、目標: 40-80行）

**責務**:
- pytest-bdd 設定
- BDD ステップコンテキスト
- テストデータセットアップヘルパー

**フィクスチャ（3-5個）**:
1. `bdd_context` (function) - ステップ間の状態共有
2. DB/ストレージフィクスチャの再利用（必要に応じて integration conftest から import）

---

## フィクスチャ依存関係最適化

### 依存深度の制限

**現状の問題**: 最大依存深度 5（`test_image_repository_with_tag_db`）

**目標**: 最大依存深度 3 以下

**最適化アプローチ**:

```
# 現在（深度 5）:
temp_dir -> test_db_url -> test_engine_with_schema -> db_session_factory -> test_repository
                                                                          -> test_session

# 最適化後（深度 3）:
test_engine_with_schema（独立: in-memory DB使用、temp_dir 不要）
  -> db_session_factory
     -> test_session
     -> test_repository
```

`test_db_url` は in-memory SQLite (`sqlite:///:memory:`) を使用しているため、`temp_dir` への依存を削除可能。

### スコープ最適化候補

| フィクスチャ | 現在 | 推奨 | 理由 |
|---|---|---|---|
| `test_engine_with_schema` | function | function | テスト間の独立性確保（スキーマ+初期データ含む） |
| `test_image` | function | session | テスト用画像は不変、再読み込み不要 |
| `test_image_dir` | function | session | ディレクトリパスは不変 |

**注意**: session スコープへの変更はテスト間の状態共有リスクあり。読み取り専用のフィクスチャのみ対象。

---

## テスト配置判断フローチャート

新しいテストを追加する際の判断基準:

```
Q1: 外部依存（DB, ファイルシステム, Qt）なしで実行可能か？
  -> YES: tests/unit/ に配置、@pytest.mark.unit
  -> NO: Q2 へ

Q2: Qt/PySide6 を使用するか？
  -> YES: Q3 へ
  -> NO: Q4 へ

Q3: 単一ウィジェット/サービスのテストか？
  -> YES: tests/unit/gui/ に配置、@pytest.mark.unit @pytest.mark.gui
  -> NO: tests/integration/gui/ に配置、@pytest.mark.integration @pytest.mark.gui

Q4: 複数コンポーネントの結合テストか？
  -> YES: tests/integration/ に配置、@pytest.mark.integration
  -> NO: tests/unit/ に配置、@pytest.mark.unit

Q5: エンドツーエンドのユーザーワークフローか？
  -> YES: tests/bdd/ に配置、@pytest.mark.bdd
```

---

## 重複フィクスチャの統合計画

### 統合対象

| フィクスチャ名 | 重複箇所 | 統合先 | 方針 |
|---|---|---|---|
| `mock_db_manager` | 5ファイルで個別定義 | `tests/unit/conftest.py` | 共通モックを conftest に、特殊な設定は各テスト内で上書き |
| `mock_config_service` | 4ファイルで個別定義 | `tests/unit/conftest.py` + `tests/integration/conftest.py` | 各層の conftest で1回定義 |
| `test_images_data` | 2ファイルで個別定義 | `tests/integration/conftest.py` | 統合テスト用サンプルデータとして統合 |
| `mock_dependencies` | 複数の統合テストで類似パターン | `tests/integration/gui/conftest.py`（必要時新規作成） | GUI統合テスト用の共通依存モック |

---

## pytest-qt ベストプラクティス違反の修正計画

### 対象箇所（15箇所）

| ファイル | 違反箇所数 | 修正方法 |
|---|---|---|
| `test_mainwindow_signal_connection.py` | 7 | `qtbot.wait(50-100)` -> `qtbot.waitUntil()` |
| `test_ui_layout_integration.py` | 11 | `qtbot.wait(10-100)` -> `qtbot.waitUntil()` |
| `test_model_checkbox_widget.py` | 2 | `qtbot.wait(100)` -> `qtbot.waitUntil(lambda: widget.isEnabled())` |
| `test_main_window_tab_integration.py` | 3 | `qtbot.wait(10)` -> `qtbot.waitUntil()` |
| `test_rating_score_edit_widget.py` | 1 | `qtbot.wait(10)` -> `qtbot.waitSignal()` |

### 修正パターン

```python
# Before:
qtbot.wait(100)
assert widget.isEnabled()

# After:
qtbot.waitUntil(lambda: widget.isEnabled(), timeout=1000)
```

---

## パフォーマンス見積り

### 実行時間の比較

| テストカテゴリ | 現在（推定） | 新構造後（推定） | 変化 |
|---|---|---|---|
| unit (Qt不使用) | ~30秒 | ~25秒 | -17% (フィクスチャ最適化) |
| unit (Qt使用) | ~30秒 | ~30秒 | +/-0% |
| integration (Qt不使用) | ~30秒 | ~30秒 | +/-0% |
| integration (Qt使用) | ~90秒 | ~85秒 | -6% (waitUntil 最適化) |
| bdd | ~20秒 | ~20秒 | +/-0% |
| **合計** | ~200秒 | ~190秒 | **-5%** |

**conftest.py 分割による起動時間改善**: 各テストカテゴリの起動時間が 5-10% 短縮（不要なフィクスチャの評価スキップ）

**pytest-qt 最適化による改善**: 固定待機の合計 ~1.5秒が条件待機に変更（テスト安定性向上 + 微小な速度改善）

---

## 大規模テストファイルの分割計画

### test_thumbnail_selector_widget.py（800+行）

分割先:
- `test_thumbnail_selector_widget_initialization.py` - 初期化、サイズ設定
- `test_thumbnail_selector_widget_selection.py` - 選択機能、クリック操作
- `test_thumbnail_selector_widget_display.py` - 表示更新、レイアウト

### test_filter_search_integration.py（700+行）

分割先:
- `test_filter_search_basic_integration.py` - 基本フィルター操作
- `test_filter_search_advanced_integration.py` - 複合条件、エッジケース

---

## 成功基準

- [ ] 全テスト成功（100% pass rate）
- [ ] カバレッジ 75%+ 維持
- [ ] 実行時間 +20% 以内（~240秒未満）
- [ ] conftest.py 行数: ルート 120行以下
- [ ] 空ディレクトリ削除完了（gui/, services/, manual/, performance/）
- [ ] BDD ディレクトリ正規化完了（features/ + step_defs/ -> bdd/）
- [ ] マーカー適用率 80%以上（全テスト関数に対して）
- [ ] pytest-qt 違反 0箇所
- [ ] 重複フィクスチャ 0箇所

---

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) - Testing Rules セクション
- [docs/testing.md](testing.md) - テスト戦略とベストプラクティス
- [.claude/rules/testing.md](../.claude/rules/testing.md) - テスト規約
- [migration_roadmap.md](migration_roadmap.md) - 移行ロードマップ
