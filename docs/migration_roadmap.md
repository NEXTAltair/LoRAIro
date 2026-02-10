# LoRAIro テストリファクタリング移行ロードマップ

**作成日**: 2026-02-10
**設計ドキュメント**: [new_test_architecture.md](new_test_architecture.md)
**ステータス**: 設計完了、Phase 1 実装待ち

---

## フェーズ概要

| Phase | 目標 | 時間見積 | 前提条件 |
|-------|------|----------|----------|
| 1 | 準備: conftest.py 分割 + ディレクトリ整理 | 1-2日 | なし |
| 2 | ユニットテスト最適化 | 2-3日 | Phase 1 完了 |
| 3 | 統合テスト整理 | 2-3日 | Phase 1 完了 |
| 4 | GUI / BDD 標準化 | 2-3日 | Phase 2, 3 完了 |
| 5 | 検証・クリーンアップ | 1-2日 | Phase 4 完了 |

**総所要時間**: 約 8-13日

---

## Phase 1: 準備（実装前）

**目標**: 新構造の基盤を整備。テストの破壊的変更なし。

**時間**: 1-2日

### チェックリスト

- [ ] 1.1 空ディレクトリの削除
- [ ] 1.2 BDD ディレクトリの作成・移動
- [ ] 1.3 ルート conftest.py の分割
- [ ] 1.4 tests/unit/conftest.py の作成
- [ ] 1.5 tests/integration/conftest.py の作成
- [ ] 1.6 tests/bdd/conftest.py の作成
- [ ] 1.7 pyproject.toml マーカー定義の整理
- [ ] 1.8 全テスト実行・成功確認

### 詳細タスク

#### 1.1 空ディレクトリの削除

対象:
- `tests/gui/` - テストファイルなし（`tests/gui/controllers/` サブディレクトリも含む）
- `tests/services/` - テストファイルなし
- `tests/manual/` - テストファイルなし
- `tests/performance/` - テストファイルなし

```bash
# 実行前確認: 各ディレクトリにファイルがないことを確認
ls -la tests/gui/ tests/services/ tests/manual/ tests/performance/

# 削除
rm -rf tests/gui/ tests/services/ tests/manual/ tests/performance/
```

#### 1.2 BDD ディレクトリの作成・移動

```bash
# 新ディレクトリ作成
mkdir -p tests/bdd/features
mkdir -p tests/bdd/step_defs

# ファイル移動（git mv で履歴維持）
git mv tests/features/database_management.feature tests/bdd/features/
git mv tests/features/logging.feature tests/bdd/features/
git mv tests/step_defs/test_database_management.py tests/bdd/step_defs/

# 空の旧ディレクトリ削除
rmdir tests/features/ tests/step_defs/
```

**注意**: `test_database_management.py` 内の feature ファイル参照パスを更新する必要がある。

#### 1.3 ルート conftest.py の分割

**方針**: 現在の 802行 conftest.py から、以下のフィクスチャのみ残す:

**残留フィクスチャ（7個）**:
1. モジュールレベルの genai-tag-db-tools パッチ（削除不可）
2. `mock_genai_tag_db_tools` (session, autouse)
3. `configure_qt_for_tests` (session, autouse)
4. `qapp_args` (session)
5. `qapp` (session)
6. `project_root` (session)
7. `qt_main_window_mock_config` (function)
8. `critical_failure_hooks` (function)

**移動対象**: 残り 27個のフィクスチャ

**作業手順**:
1. `tests/unit/conftest.py` を新規作成し、画像・サンプルデータ・タイムスタンプフィクスチャを移動
2. `tests/integration/conftest.py` を新規作成し、DB・ストレージ・タグDBフィクスチャを移動
3. ルート conftest.py から移動済みフィクスチャを削除
4. 各テストファイルのフィクスチャ参照が壊れないことを確認

#### 1.4 tests/unit/conftest.py の作成

`conftest_template.py` の「ユニットテスト」セクションを参照。

**配置フィクスチャ（13個）**:
- 画像フィクスチャ: `test_image_dir`, `test_image_path`, `test_image`, `test_image_array`, `test_image_paths`, `test_images`, `test_image_arrays`
- サンプルデータ: `sample_image_data`, `sample_processed_image_data`, `sample_annotations`
- タイムスタンプ: `current_timestamp`, `past_timestamp`
- モック: `mock_config_service`

#### 1.5 tests/integration/conftest.py の作成

`conftest_template.py` の「統合テスト」セクションを参照。

**配置フィクスチャ（14個）**:
- 一時ディレクトリ: `temp_dir`
- ストレージ: `storage_dir`, `fs_manager`
- DB初期化: `test_db_url`, `test_engine_with_schema`, `db_session_factory`, `test_session`
- リポジトリ: `test_repository`, `temp_db_repository`, `test_db_manager`
- タグDB: `test_tag_db_path`, `test_tag_repository`, `test_image_repository_with_tag_db`
- モック: `mock_config_service`（統合テスト用のバリエーション）

**重要な依存解決**:
- `test_engine_with_schema` が `test_db_url` に依存 -> `test_db_url` は in-memory なので `temp_dir` 不要
- `test_db_manager` が `test_repository` + `mock_config_service` に依存 -> 両方を同じ conftest.py に配置
- `fs_manager` が `storage_dir` に依存 -> `storage_dir` が `temp_dir` に依存

#### 1.6 tests/bdd/conftest.py の作成

`conftest_template.py` の「BDD テスト」セクションを参照。

**配置フィクスチャ（2-4個）**:
- `bdd_context` (function)
- 必要に応じて DB/ストレージフィクスチャを参照

#### 1.7 pyproject.toml マーカー定義の整理

現在の 16 マーカーを 6 マーカーに整理:

```toml
markers = [
    "unit: ユニットテスト（外部依存はモック）",
    "integration: 統合テスト（内部コンポーネント結合）",
    "gui: Qt GUI アクセスを含むテスト（ヘッドレス実行可能）",
    "bdd: BDD E2E テスト（pytest-bdd シナリオ）",
    "slow: 遅いテスト（5秒以上）",
    "webapi: Web API ベースのアノテーターテスト",
]
```

#### 1.8 全テスト実行・成功確認

```bash
# プロジェクトルートから実行
uv run pytest tests/ --tb=short -q

# テスト収集数が変わらないことを確認（2,329 tests expected）
uv run pytest tests/ --co -q | tail -1
```

### Phase 1 完了条件

- [ ] 全テスト PASS（0 failures）
- [ ] テスト収集数が Phase 1 前と同一
- [ ] ルート conftest.py が 120行以下
- [ ] 空ディレクトリが存在しない
- [ ] BDD ファイルが `tests/bdd/` に配置

---

## Phase 2: ユニットテスト最適化

**目標**: ユニットテスト層の品質向上。マーカー適用・重複フィクスチャ削除。

**時間**: 2-3日

### チェックリスト

- [ ] 2.1 `@pytest.mark.unit` を全ユニットテストに付与
- [ ] 2.2 `@pytest.mark.gui` を Qt 使用ユニットテストに付与
- [ ] 2.3 重複 `mock_db_manager` フィクスチャの統合（5箇所）
- [ ] 2.4 重複 `mock_config_service` フィクスチャの統合（4箇所）
- [ ] 2.5 大規模テストファイルの分割
- [ ] 2.6 全テスト実行・成功確認

### 詳細タスク

#### 2.1 `@pytest.mark.unit` の付与

対象: `tests/unit/` 以下の全 65 テストファイル

作業方法:
- 各テストファイルの先頭（import 後）にマーカーを追加
- クラスレベルの場合: クラスデコレータとして追加
- 関数レベルの場合: 各テスト関数にデコレータとして追加
- 推奨: `pytestmark = pytest.mark.unit` をモジュールレベルで定義（全関数に自動適用）

```python
# tests/unit/services/test_model_filter_service.py
import pytest

pytestmark = pytest.mark.unit

# ...以降の全テスト関数に自動適用
```

#### 2.2 `@pytest.mark.gui` の付与

対象: `tests/unit/gui/` 以下で Qt を使用するテストファイル（約 34 files）

```python
# tests/unit/gui/widgets/test_batch_tag_add_widget.py
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.gui]
```

#### 2.3 重複 `mock_db_manager` の統合

**現在の重複箇所（5箇所）**:
1. `tests/unit/services/test_search_criteria_processor.py`
2. `tests/unit/gui/services/test_search_filter_service.py`
3. `tests/unit/test_dataset_export_service.py`
4. `tests/unit/services/test_model_filter_service.py`
5. その他

**統合方法**:
1. `tests/unit/conftest.py` に共通の `mock_db_manager` フィクスチャを定義
2. 各テストファイルの個別定義を削除
3. テスト固有のモック設定は各テスト内で `mock_db_manager.method.return_value = ...` で上書き

#### 2.4 重複 `mock_config_service` の統合

**現在の重複箇所（4箇所）**:
1. `tests/conftest.py` (L381) - 元の定義
2. `tests/unit/test_upscaler_info_recording.py`
3. `tests/unit/test_dataset_export_service.py`
4. `tests/unit/services/test_annotator_library_adapter.py`

**統合方法**: Phase 1 で `tests/unit/conftest.py` に移動済み。各ファイルの個別定義を削除。

#### 2.5 大規模テストファイルの分割

**対象 1**: `tests/unit/gui/widgets/test_thumbnail_selector_widget.py` (800+ lines)

分割先:
- `test_thumbnail_selector_widget_init.py` - 初期化、コンストラクタ
- `test_thumbnail_selector_widget_selection.py` - 選択操作、マルチ選択
- `test_thumbnail_selector_widget_display.py` - 表示、更新、レイアウト

**対象 2**: 他に 300行超のファイルがあれば同様に分割

#### 2.6 全テスト実行確認

```bash
# マーカー付きテスト実行
uv run pytest -m unit --tb=short -q
uv run pytest tests/ --tb=short -q
```

### Phase 2 完了条件

- [ ] 全テスト PASS
- [ ] `tests/unit/` 以下の全テストに `@pytest.mark.unit` 付与
- [ ] 重複フィクスチャ 0箇所
- [ ] 300行超のテストファイル 0個

---

## Phase 3: 統合テスト整理

**目標**: 統合テスト層の最適化。マーカー適用・フィクスチャ共有化。

**時間**: 2-3日

### チェックリスト

- [ ] 3.1 `@pytest.mark.integration` を全統合テストに付与
- [ ] 3.2 `@pytest.mark.gui` を Qt 使用統合テストに付与
- [ ] 3.3 DB初期化を `tests/integration/conftest.py` に一元化
- [ ] 3.4 ストレージ関連フィクスチャの共有化
- [ ] 3.5 統合テスト間の依存関係をドキュメント化
- [ ] 3.6 大規模テストファイルの分割
- [ ] 3.7 全テスト実行・成功確認

### 詳細タスク

#### 3.1 `@pytest.mark.integration` の付与

対象: `tests/integration/` 以下の全 25 テストファイル

```python
# tests/integration/test_batch_processing_integration.py
import pytest

pytestmark = pytest.mark.integration
```

#### 3.2 `@pytest.mark.gui` の付与

対象: `tests/integration/gui/` 以下のテストファイル（約 13 files）

```python
# tests/integration/gui/test_filter_search_integration.py
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.gui]
```

#### 3.3 DB初期化の一元化

Phase 1 で `tests/integration/conftest.py` に `test_engine_with_schema` を配置済み。
統合テスト固有の DB 関連フィクスチャが各テストファイルで個別定義されていないか確認し、あれば conftest.py に統合。

#### 3.4 ストレージ関連フィクスチャの共有化

Phase 1 で `tests/integration/conftest.py` に `temp_dir`, `storage_dir`, `fs_manager` を配置済み。
統合テスト固有のストレージフィクスチャが個別定義されていないか確認。

#### 3.5 依存関係のドキュメント化

各統合テストファイルの先頭に、テスト対象コンポーネントとその依存関係をコメントで記載:

```python
"""
統合テスト: FilterSearchService + SearchWidget

テスト対象:
    - SearchFilterService: 検索フィルター条件の管理
    - FilterSearchPanel: 検索UI ウィジェット

依存フィクスチャ:
    - qapp: QApplication（session scope）
    - mock_dependencies: モック依存セット

関連テスト:
    - tests/unit/gui/services/test_search_filter_service.py (ユニットテスト)
"""
```

#### 3.6 大規模テストファイルの分割

**対象**: `tests/integration/gui/test_filter_search_integration.py` (700+ lines)

分割先:
- `test_filter_search_basic_integration.py` - 基本フィルター（テキスト検索、タグ検索）
- `test_filter_search_advanced_integration.py` - 複合条件（AND/OR、日付範囲、レーティング）

### Phase 3 完了条件

- [ ] 全テスト PASS
- [ ] `tests/integration/` 以下の全テストに `@pytest.mark.integration` 付与
- [ ] DB初期化が conftest.py に一元化
- [ ] 300行超のテストファイル 0個
- [ ] 各統合テストに依存関係コメント付与

---

## Phase 4: GUI / BDD 標準化

**目標**: pytest-qt ベストプラクティス完全適用。BDD シナリオ正規化。

**時間**: 2-3日

### チェックリスト

- [ ] 4.1 pytest-qt `qtbot.wait()` 固定待機の修正（15箇所）
- [ ] 4.2 `qtbot.addWidget()` の使用確認・追加
- [ ] 4.3 BDD ステップ定義のパス更新
- [ ] 4.4 `@pytest.mark.bdd` の付与
- [ ] 4.5 全テスト実行・成功確認

### 詳細タスク

#### 4.1 pytest-qt 固定待機の修正

**対象ファイル・箇所（15箇所）**:

| ファイル | 行番号 | 現在 | 修正後 |
|---|---|---|---|
| `test_mainwindow_signal_connection.py` | L45, L119, L165, L217, L247, L252, L274 | `qtbot.wait(50-100)` | `qtbot.waitUntil(lambda: <condition>, timeout=1000)` |
| `test_ui_layout_integration.py` | L103, L159, L164, L174, L189, L204, L287, L302, L320, L335, L362 | `qtbot.wait(10-100)` | `qtbot.waitUntil(lambda: <condition>, timeout=1000)` |
| `test_model_checkbox_widget.py` | L219, L224 | `qtbot.wait(100)` | `qtbot.waitUntil(lambda: widget.isEnabled(), timeout=1000)` |
| `test_main_window_tab_integration.py` | L87, L97, L101 | `qtbot.wait(10)` | `qtbot.waitUntil(lambda: <condition>, timeout=1000)` |
| `test_rating_score_edit_widget.py` | L108 | `qtbot.wait(10)` | `qtbot.waitSignal(<signal>, timeout=1000)` |

**修正パターン**:

```python
# パターン A: ウィジェット状態待機
# Before:
qtbot.wait(100)
assert widget.isEnabled()

# After:
qtbot.waitUntil(lambda: widget.isEnabled(), timeout=1000)

# パターン B: Signal 発火待機
# Before:
widget.trigger_action()
qtbot.wait(100)
assert widget.result is not None

# After:
with qtbot.waitSignal(widget.action_completed, timeout=1000):
    widget.trigger_action()
assert widget.result is not None

# パターン C: UI 更新待機
# Before:
widget.update_display()
qtbot.wait(50)
assert widget.label.text() == "updated"

# After:
widget.update_display()
qtbot.waitUntil(lambda: widget.label.text() == "updated", timeout=1000)
```

#### 4.2 `qtbot.addWidget()` の使用確認

全 GUI テスト（`@pytest.mark.gui`）で、作成したウィジェットに `qtbot.addWidget()` が呼ばれていることを確認。
不足があれば追加（メモリリーク・クリーンアップ警告の防止）。

#### 4.3 BDD ステップ定義のパス更新

`tests/bdd/step_defs/test_database_management.py` 内の feature ファイル参照パスを更新:

```python
# Before:
scenarios("../features/database_management.feature")

# After:
scenarios("../features/database_management.feature")
# パスが相対的に同じ場合は変更不要。
# tests/step_defs/ -> tests/bdd/step_defs/ への移動に伴い、
# tests/features/ -> tests/bdd/features/ も移動しているため相対パスは同一。
```

実際のパス参照方法を確認し、必要に応じて修正。

#### 4.4 `@pytest.mark.bdd` の付与

```python
# tests/bdd/step_defs/test_database_management.py
import pytest

pytestmark = pytest.mark.bdd
```

### Phase 4 完了条件

- [ ] 全テスト PASS
- [ ] `qtbot.wait()` 固定待機 0箇所
- [ ] BDD テストが `tests/bdd/` から正常実行
- [ ] 全 BDD テストに `@pytest.mark.bdd` 付与

---

## Phase 5: 検証・クリーンアップ

**目標**: 全テスト実行。カバレッジ確認。ドキュメント更新。

**時間**: 1-2日

### チェックリスト

- [ ] 5.1 全テスト実行（マーカー別）
- [ ] 5.2 カバレッジ測定
- [ ] 5.3 実行時間測定
- [ ] 5.4 マーカー適用率確認
- [ ] 5.5 ドキュメント更新
- [ ] 5.6 不要ファイルの最終クリーンアップ

### 詳細タスク

#### 5.1 全テスト実行

```bash
# カテゴリ別実行
uv run pytest -m unit --tb=short -q
uv run pytest -m integration --tb=short -q
uv run pytest -m gui --tb=short -q
uv run pytest -m bdd --tb=short -q

# 全テスト実行
uv run pytest tests/ --tb=short -q

# テスト収集数確認（移行前後で差異がないこと）
uv run pytest tests/ --co -q | tail -1
```

#### 5.2 カバレッジ測定

```bash
uv run pytest --cov=src/lorairo --cov-report=term-missing --cov-report=html
```

**確認項目**:
- 全体カバレッジ >= 75%
- 各モジュールのカバレッジ低下がないこと
- カバレッジレポートを `htmlcov/` に出力して詳細確認

#### 5.3 実行時間測定

```bash
# 全テスト実行時間
time uv run pytest tests/ --tb=short -q

# カテゴリ別実行時間
time uv run pytest -m unit --tb=short -q
time uv run pytest -m integration --tb=short -q
time uv run pytest -m gui --tb=short -q
time uv run pytest -m bdd --tb=short -q
```

**基準**: 全テスト実行時間が移行前 +20% 以内

#### 5.4 マーカー適用率確認

```bash
# マーカー付きテスト数
uv run pytest -m unit --co -q | tail -1
uv run pytest -m integration --co -q | tail -1
uv run pytest -m gui --co -q | tail -1
uv run pytest -m bdd --co -q | tail -1

# マーカーなしテスト数（理想は 0）
uv run pytest -m "not (unit or integration or gui or bdd)" --co -q | tail -1
```

**基準**: マーカーなしテスト = 全テストの 20% 以下

#### 5.5 ドキュメント更新

更新対象:
1. `docs/testing.md` - テスト構造セクションを新構造に更新
2. `CLAUDE.md` - テストコマンドセクションの確認（変更不要の可能性大）

#### 5.6 最終クリーンアップ

- 不要になった空の `__init__.py` ファイルの削除
- `.pyc` キャッシュのクリア
- git で追跡不要なファイルの確認

### Phase 5 完了条件

- [ ] 全テスト 100% PASS
- [ ] カバレッジ >= 75%
- [ ] 実行時間 +20% 以内
- [ ] マーカーなしテスト <= 20%
- [ ] docs/testing.md 更新完了

---

## リスク評価と対策

| リスク | 発生確率 | 影響度 | 対策 |
|---|---|---|---|
| conftest.py 分割でテスト失敗 | 中 | 高 | Phase 1 完了時に全テスト実行。失敗即修正 |
| フィクスチャ移動で依存解決失敗 | 中 | 高 | フィクスチャの依存ツリーを事前に確認。pytest の conftest.py 探索順序を理解した上で配置 |
| BDD パス変更で step_defs が feature を見つけられない | 低 | 中 | 相対パスの事前検証。Phase 1 で即テスト実行 |
| マーカー付与で既存 CI が壊れる | 低 | 低 | マーカーは「追加」のみ（既存動作に影響なし）。pyproject.toml のマーカー定義更新で Warning 解消 |
| カバレッジ低下 | 低 | 中 | Phase 5 で詳細測定。テスト追加で回復 |
| 実行時間増加 | 低 | 低 | conftest.py 分割で起動時間改善。pytest-qt 最適化で相殺 |

### ロールバック手順

各 Phase で問題が発生した場合:

```bash
# Phase 1 のロールバック
git stash  # または git checkout -- tests/

# Phase 2-4 は各 Phase ごとにコミットし、
# 問題発生時は該当 Phase のコミットを revert
git revert <phase-commit-hash>
```

---

## 成功基準（全Phase完了時）

| 基準 | 目標値 | 測定方法 |
|---|---|---|
| テスト成功率 | 100% | `uv run pytest` で 0 failures |
| カバレッジ | >= 75% | `--cov-report=term` |
| 実行時間 | +20% 以内 | `time uv run pytest` |
| ルート conftest.py 行数 | <= 120行 | `wc -l tests/conftest.py` |
| 空ディレクトリ | 0個 | `find tests -type d -empty` |
| pytest-qt 違反 | 0箇所 | `grep -r "qtbot.wait(" tests/` |
| マーカーなしテスト | <= 20% | pytest --co で確認 |
| 重複フィクスチャ | 0個 | 手動コードレビュー |

---

## 関連ドキュメント

- [new_test_architecture.md](new_test_architecture.md) - 新テストアーキテクチャ設計
- [docs/testing.md](testing.md) - テスト戦略とベストプラクティス
- [CLAUDE.md](../CLAUDE.md) - プロジェクト全体ガイド
