---
type: Guide
title: テスト戦略とベストプラクティス
status: Accepted
timestamp: 2026-05-21
tags: [process, validation]
---

# テスト戦略とベストプラクティス

## 概要

LoRAIro は 3 層テスト戦略を採用し、75% 以上のコードカバレッジを維持する。

### テストレベル

- **ユニットテスト**: ビジネスロジックおよび Qt に依存しないサービス層
- **統合テスト**: GUI サービスおよびデータベース統合
- **BDD テスト**: 振る舞い仕様テスト(E2E に限定せず Service 層以上に適用する)

### 実行時検証ポリシー

ADR 0026 に基づき、CI で実行する E2E テストは決定論的なフィクスチャおよびフェイクバックエンドに基づくものに限定する。実際の API キー、ローカルモデルのダウンロード、実推論を伴う検証は通常 CI に含めず、ローカルでオンデマンドに実行する実行時検証として扱う。

### 使用フレームワーク

- `pytest`(テストランナー)
- `pytest-qt`(Qt GUI テスト)
- `pytest-cov`(カバレッジ計測)

## Tier 1: Smoke(実機モデル軽量 E2E)

Tier 1 は、`image-annotator-lib` の `tests/runtime_validation/` に集約したローカル専用の検証層であり、実モデルのダウンロードと実推論を行う。LoRAIro 側には実モデルテストを置かず、Makefile ターゲットから `image-annotator-lib` の実行時検証を間接実行する。

```bash
make test-runtime-local
```

このターゲットは、`local_packages/image-annotator-lib` で `downloads_and_runs_model` マーカーが付いた 5 モデルのスモークテストを実行し、ONNX、Transformers、Tensorflow、Pipeline、CLIP の各基底クラスを 1 モデルずつ検証する。初回は約 3.5 GB のモデルダウンロードと 20 分程度の実行時間を想定しており、キャッシュ後は数分程度で完了する。

ADR 0026 および iam-lib ADR 0001 amended(2026-05-18)により、この検証は CI に含めない。GitHub Actions ワークフロー、`workflow_dispatch`、`schedule`、CI キャッシュ、リポジトリシークレットを追加してはならない。

## Tier 2: 実 WebAPI 統合検証

Tier 2 は、`image-annotator-lib` の `tests/runtime_validation/test_real_webapi_runtime.py` に集約したローカル専用の検証であり、実プロバイダーの API キーを使って実 WebAPI リクエストを送信する。LoRAIro 側には実 WebAPI テストを置かず、LoRAIro の実運用設定経路で API キーを読み込むランナーから `image-annotator-lib` の検証を間接実行する。

```bash
make test-runtime-webapi
```

このターゲットは `ConfigurationService` 経由で `config/lorairo.toml` の `[api]` セクションを読み込み、サブプロセスの環境変数として `image-annotator-lib` のテストへ渡す。

| LoRAIro 設定キー | 子プロセスの環境変数 | プロバイダー |
|---|---|---|
| `openai_key` | `OPENAI_API_KEY` | OpenAI |
| `claude_key` | `ANTHROPIC_API_KEY` | Anthropic |
| `google_key` | `GEMINI_API_KEY` | Google |
| `openrouter_key` | `OPENROUTER_API_KEY` | OpenRouter |

API キーの値は標準出力やログに出力しない。ランナーはプロバイダーごとの設定済み・未設定の状態のみを表示し、未設定のプロバイダーは `image-annotator-lib` 側で `pytest.skip` される。

対象モデルは Google、OpenAI、Anthropic、OpenRouter の各 1 モデルである。#274 が未解決の間は、`OPENAI_API_KEY` が設定された環境で OpenAI ケースが失敗する可能性がある。この失敗は #274 の再現として扱い、#278 では skip や xfail にしない。

ADR 0026 および iam-lib ADR 0001 amended(2026-05-18)により、この検証も CI に含めない。GitHub Actions ワークフロー、`workflow_dispatch`、`schedule`、CI キャッシュ、リポジトリシークレットを追加してはならない。

## テスト構造

### ディレクトリ構成

```
tests/
├── unit/                    # Unit tests (Qt-free)
│   ├── services/            # Business logic services
│   ├── database/            # Database layer
│   └── annotation/          # Annotation logic
├── integration/             # Integration tests
│   ├── gui/                 # GUI services + widgets
│   │   ├── services/        # GUI services
│   │   └── widgets/         # Qt widgets
│   └── database/            # DB integration
├── bdd/                     # BDD振る舞い仕様テスト
│   ├── conftest.py          # bddマーカー自動付与
│   ├── features/            # Gherkin featureファイル
│   └── steps/               # ステップ定義(test_*.py)
├── resources/               # Test resources
│   ├── images/              # Sample images
│   ├── configs/             # Test configurations
│   └── databases/           # Test databases
└── conftest.py              # Shared fixtures
```

### テストマーカー

```python
import pytest

# Unit test
@pytest.mark.unit
def test_service_logic():
    pass

# Integration test
@pytest.mark.integration
def test_database_integration():
    pass

# GUI test
@pytest.mark.gui
def test_widget_interaction(qtbot):
    pass

# Slow test
@pytest.mark.slow
def test_batch_processing():
    pass

# Deterministic E2E test for CI
@pytest.mark.integration
@pytest.mark.e2e
def test_cli_workflow_with_fake_backend():
    pass

# On-demand real API validation, excluded from normal CI
@pytest.mark.calls_real_webapi
@pytest.mark.webapi
def test_provider_contract_with_real_webapi():
    pass
```

特定のマーカーを指定して実行する例を以下に示す。

```bash
uv run pytest -m unit              # Unit tests only
uv run pytest -m integration       # Integration tests only
uv run pytest -m gui               # GUI tests only
uv run pytest -m e2e               # Deterministic E2E tests
uv run pytest -m "not slow"        # Exclude slow tests
uv run pytest -m calls_real_webapi # On-demand real API validation
```

`e2e` マーカーは外部依存を実際に使うという意味ではなく、CI で安定実行できる E2E テストを表す。実 API キーを使うテストには `calls_real_webapi`、実モデルのダウンロードや実推論を行うテストには `downloads_and_runs_model` を付与し、通常 CI から除外する。

## pytest-qt ベストプラクティス

### Signal ベースのアサーション

#### 推奨: `qtbot.waitSignal()`

```python
def test_signal_emission(qtbot):
    widget = MyWidget()

    # Wait for signal with timeout
    with qtbot.waitSignal(widget.data_loaded, timeout=1000) as blocker:
        widget.load_data()

    # Assert signal arguments
    assert blocker.args[0] == expected_data
```

利点:

- タイムアウトが自動で処理される。
- 失敗時のメッセージが明確になる。
- 手動でイベントループを回す必要がない。

#### 非推奨: 手動の `processEvents()`

```python
# ❌ BAD: Manual event loop processing
def test_signal_bad(qtbot):
    widget = MyWidget()
    widget.load_data()

    # Fragile, timing-dependent
    QCoreApplication.processEvents()
    qtbot.wait(100)  # Arbitrary delay

    assert widget.data_ready  # May fail randomly
```

### UI 状態変更の待機

#### 推奨: `qtbot.waitUntil()`

```python
def test_ui_update(qtbot):
    widget = MyWidget()
    widget.start_processing()

    # Wait for UI state change
    qtbot.waitUntil(
        lambda: widget.status_label.text() == "Complete",
        timeout=2000
    )

    assert widget.is_finished()
```

利点:

- 条件ベースで待機できる。
- ポーリングが自動で行われる。
- タイムアウト時のエラーが分かりやすい。

#### 非推奨: 固定時間待機

```python
# ❌ BAD: Fixed delay without condition
def test_ui_bad(qtbot):
    widget = MyWidget()
    widget.start_processing()

    qtbot.wait(500)  # May be too short or too long

    assert widget.status_label.text() == "Complete"  # Flaky
```

### `QMessageBox` のモック

#### 推奨: `monkeypatch`

```python
def test_confirmation_dialog(qtbot, monkeypatch):
    widget = MyWidget()

    # Mock QMessageBox.question
    monkeypatch.setattr(
        QMessageBox,
        'question',
        lambda *args: QMessageBox.Yes
    )

    # Trigger action that shows dialog
    widget.delete_item()

    # Assert action completed
    assert widget.item_count == 0
```

よく使うモックの例:

```python
# Information dialog
monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)

# Warning dialog
monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)

# Critical error dialog
monkeypatch.setattr(QMessageBox, 'critical', lambda *args: None)

# Question dialog (Yes/No)
monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
```

### ウィジェット操作

#### クリック操作

```python
def test_button_click(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)  # Ensure cleanup

    # Wait for signal on button click
    with qtbot.waitSignal(widget.button.clicked):
        qtbot.mouseClick(widget.button, Qt.LeftButton)

    assert widget.action_performed
```

#### キーボード入力

```python
def test_text_input(qtbot):
    widget = MyLineEdit()
    qtbot.addWidget(widget)

    # Type text
    qtbot.keyClicks(widget, "test input")

    assert widget.text() == "test input"
```

#### キーシーケンス

```python
def test_shortcut(qtbot):
    widget = MyWidget()
    qtbot.addWidget(widget)

    # Trigger keyboard shortcut
    with qtbot.waitSignal(widget.save_triggered):
        qtbot.keyClick(widget, Qt.Key_S, Qt.ControlModifier)
```

### 非同期・スレッドテスト

#### ワーカースレッドの Signal

```python
def test_worker_completion(qtbot):
    service = WorkerService()

    # Wait for worker completion signal
    with qtbot.waitSignal(service.work_finished, timeout=5000) as blocker:
        service.start_work()

    # Verify result
    result = blocker.args[0]
    assert result.success
```

#### 複数の Signal

```python
def test_multi_step_process(qtbot):
    widget = MyWidget()

    # Wait for multiple signals in sequence
    with qtbot.waitSignal(widget.step1_done):
        widget.start()

    with qtbot.waitSignal(widget.step2_done):
        pass  # step2 auto-starts

    with qtbot.waitSignal(widget.all_complete):
        pass  # step3 auto-starts

    assert widget.final_result is not None
```

### ヘッドレステスト

#### Linux・コンテナ環境

```bash
# Set headless mode
export QT_QPA_PLATFORM=offscreen

# Run GUI tests
uv run pytest -m gui
```

#### Windows 環境

Windows ではネイティブウィンドウで GUI テストを実行する(必要に応じて Xvfb によるヘッドレス実行も選択できる)。

#### pytest 設定例

```python
# conftest.py
import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_qt_environment():
    """Ensure Qt runs in offscreen mode in CI/containers"""
    if not os.environ.get('DISPLAY'):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
```

## ユニットテスト

### ビジネスロジックサービス

```python
import pytest
from src.lorairo.services.tag_management_service import TagManagementService

@pytest.mark.unit
def test_tag_service_get_unknown_tags(tmp_path):
    # Setup: Initialize service with temp DB
    service = TagManagementService(user_db_dir=tmp_path)

    # Exercise: Call method
    tags = service.get_unknown_tags()

    # Verify: Assert expected behavior
    assert isinstance(tags, list)
    assert all(tag.type_name == "unknown" for tag in tags)
```

基本原則:

- ユニットテストに Qt 依存を持ち込まない。
- GUI モックを使わず、ビジネスロジックを直接検証する。
- 純粋関数とサービスメソッドを直接テストする。
- ファイル操作には `tmp_path` フィクスチャを使用する。

### データベース層

```python
@pytest.mark.unit
def test_image_repository_add(tmp_path):
    # Create temporary database
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(db_path)

    # Create repository
    repo = ImageRepository(session_factory)

    # Add image
    image = ImageModel(
        file_path="/path/to/image.jpg",
        phash="abc123",
        width=1024,
        height=768
    )
    repo.add(image)

    # Verify
    retrieved = repo.get_by_phash("abc123")
    assert retrieved.file_path == "/path/to/image.jpg"
```

データベースフィクスチャの例:

```python
@pytest.fixture
def test_db(tmp_path):
    """Create temporary test database"""
    db_path = tmp_path / "test.db"
    session_factory = create_session_factory(db_path)

    # Run migrations
    alembic_upgrade(db_path)

    yield session_factory

    # Cleanup (automatic via tmp_path)
```

### 外部依存のモック

#### モックを使うべき場面

外部 API の呼び出し:

```python
@patch('requests.post')
def test_api_call(mock_post):
    mock_post.return_value.json.return_value = {"result": "success"}

    service = ExternalAPIService()
    result = service.call_api()

    assert result == "success"
```

ファイルシステム操作(エラー処理を検証する場合):

```python
@patch('pathlib.Path.exists')
def test_file_not_found(mock_exists):
    mock_exists.return_value = False

    service = FileService()
    with pytest.raises(FileNotFoundError):
        service.load_file("missing.txt")
```

#### モックを使わないべき場面

データベース操作(`tmp_path` 上の実 SQLite を使用する):

```python
# ✅ GOOD: Real database in temp location
def test_database_query(tmp_path):
    db = create_database(tmp_path / "test.db")
    result = db.query(...)
    assert result is not None
```

純粋関数:

```python
# ✅ GOOD: No mocks needed for pure logic
def test_calculate_total():
    result = calculate_total([10, 20, 30])
    assert result == 60
```

## 統合テスト

### GUI サービスとウィジェットの統合

```python
@pytest.mark.integration
@pytest.mark.gui
def test_search_filter_service_integration(qtbot):
    # Create service + widget
    service = SearchFilterService()
    widget = SearchWidget(service)
    qtbot.addWidget(widget)

    # Connect signals
    results_received = False
    def on_results(results):
        nonlocal results_received
        results_received = True

    service.search_completed.connect(on_results)

    # Trigger search
    with qtbot.waitSignal(service.search_completed, timeout=2000):
        widget.search_button.click()

    assert results_received
```

### データベース統合(複数テーブル操作)

```python
@pytest.mark.integration
def test_image_with_annotations(test_db):
    repo = ImageRepository(test_db)
    annotation_repo = AnnotationRepository(test_db)

    # Create image
    image = ImageModel(file_path="/test.jpg", phash="abc")
    repo.add(image)

    # Add annotation
    annotation = AnnotationModel(
        image_id=image.id,
        caption="Test caption",
        tags=["tag1", "tag2"]
    )
    annotation_repo.add(annotation)

    # Verify relationship
    retrieved_image = repo.get_with_annotations(image.id)
    assert len(retrieved_image.annotations) == 1
    assert retrieved_image.annotations[0].caption == "Test caption"
```

### 外部パッケージ統合

#### `genai-tag-db-tools`

```python
@pytest.mark.integration
def test_tag_registration_integration(tmp_path):
    # Initialize User DB
    from genai_tag_db_tools.db.core import init_user_db
    init_user_db(user_db_dir=tmp_path)

    # Use TagManagementService
    service = TagManagementService(user_db_dir=tmp_path)

    # Register tag
    tag_id = service.register_tag("test_tag", type_name="general")

    # Verify
    tags = service.get_all_tags()
    assert any(tag.tag_name == "test_tag" for tag in tags)
```

#### `image-annotator-lib`

```python
@pytest.mark.integration
@pytest.mark.slow
def test_annotation_integration(monkeypatch):
    # Mock API call (avoid real API costs)
    mock_result = AnnotationResult(
        caption="Test caption",
        tags=["tag1"],
        confidence=0.9
    )
    monkeypatch.setattr(
        'image_annotator_lib.annotate',
        lambda *args, **kwargs: mock_result
    )

    # Use AnnotatorLibraryAdapter
    adapter = AnnotatorLibraryAdapter(config_service)
    result = adapter.annotate("test_image.jpg", provider="openai")

    assert result.caption == "Test caption"
```

## カバレッジ要件

### 目標: 75% 以上

計測コマンド:

```bash
uv run pytest --cov=src --cov-report=xml --cov-report=term
```

レポート出力例:

```
Name                                 Stmts   Miss  Cover
--------------------------------------------------------
src/lorairo/services/...               150     20    87%
src/lorairo/database/...               200     40    80%
src/lorairo/gui/services/...           100     30    70%  # Below target
--------------------------------------------------------
TOTAL                                 1500    300    80%
```

### カバレッジ除外

以下の箇所は `# pragma: no cover` でカバレッジ計測から除外する。

```python
# pragma: no cover

# Main entry points
if __name__ == "__main__":  # pragma: no cover
    main()

# Abstract methods
def abstract_method(self):
    raise NotImplementedError  # pragma: no cover

# Type checking blocks
if TYPE_CHECKING:  # pragma: no cover
    from typing import Protocol
```

### カバレッジ改善の優先度

1. **75% 未満**: 不足しているテストを直ちに追加する。
2. **75〜85%**: エッジケースのテストを追加する。
3. **85% 以上**: 統合テストの充実に注力する。

HTML レポートによる分析手順:

```bash
# Generate HTML coverage report
uv run pytest --cov=src --cov-report=html

# Open in browser
open htmlcov/index.html
```

## テストフィクスチャ

### データベースフィクスチャ

```python
# conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def test_db(tmp_path):
    """Create temporary SQLite database"""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Create tables
    Base.metadata.create_all(engine)

    SessionFactory = sessionmaker(bind=engine)
    return SessionFactory

@pytest.fixture
def populated_db(test_db):
    """Database with test data"""
    session = test_db()

    # Add test data
    session.add(ImageModel(file_path="/test1.jpg", phash="abc"))
    session.add(ImageModel(file_path="/test2.jpg", phash="def"))
    session.commit()

    return test_db
```

### 設定フィクスチャ

```python
@pytest.fixture
def test_config(tmp_path):
    """Test configuration service"""
    config_path = tmp_path / "test_config.toml"
    config_path.write_text("""
[api]
openai_key = "test-key"

[directories]
database_base_dir = "test_data"
    """)

    return ConfigurationService(config_path=config_path)
```

### Qt フィクスチャ

```python
@pytest.fixture
def main_window(qtbot):
    """MainWindow instance for testing"""
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window
```

## BDD 振る舞い仕様テスト

BDD は E2E テストに限定せず、「振る舞い仕様の表現形式」として Service 層以上に適用する。ツールは **pytest-bdd(>=8.1)** を使用する。適用レイヤーの判断基準(◎ ユーザー向けフロー、○ Service 層、△ Repository CRUD、✕ 内部ロジック)は `.claude/rules/testing.md` の「BDD テスト」セクションを参照する。

### 実装済みシナリオ

| フィーチャー | 内容 |
|---|---|
| `database_management.feature` | 画像登録、アノテーション保存、検索(タグ、キャプション、日付、NSFW、手動編集、レーティング) |
| `export_filter_required.feature` | `DatasetExportService.export_with_criteria()` の `criteria` と `image_ids` による分岐 |
| `logging.feature` | ログレベル制御、モジュール固有レベル、例外ログ記録 |

### ディレクトリ構成

```
tests/bdd/
├── conftest.py     # tests/bdd 配下に @pytest.mark.bdd を自動付与
├── features/       # Gherkin .feature ファイル(日本語Gherkin可)
└── steps/          # test_<feature名>.py — ステップ定義
```

### フィーチャーファイルの例

対象ファイル: `tests/bdd/features/database_management.feature`

```gherkin
Feature: 画像データベース管理機能

  Background:
    Given データベースが初期化されている
    And モデルが登録されている

  Scenario: オリジナル画像の登録
    Given テスト用の画像ファイル "file01.webp" が存在する
    When 画像を登録する
    Then 画像メタデータがデータベースに保存される
    And 画像のUUIDが生成される
```

先頭に `# language: ja` を記述すると、`機能`、`シナリオ`、`前提`、`もし`、`ならば`、`かつ` といったように Gherkin キーワード自体も日本語化できる。`export_filter_required.feature` がその例である。

### ステップ実装パターン

対象ファイル: `tests/bdd/steps/test_database_management.py`

```python
from pathlib import Path
from pytest_bdd import given, when, then, scenarios, parsers

# feature パスは __file__ 基準で絶対解決(cwd 依存を避ける)
_FEATURE_FILE = Path(__file__).parent.parent / "features" / "database_management.feature"
scenarios(str(_FEATURE_FILE))  # feature 内の全シナリオを一括登録

@given("データベースが初期化されている")
def given_db_initialized(test_db_manager):  # conftest.py の fixture を注入
    assert test_db_manager is not None

@when("画像を登録する")
def when_register_image(test_db_manager, fs_manager, test_image_path):
    # 実装は Service/Repository を呼ぶだけに留める
    ...
```

### pytest-bdd の使い方

#### `scenarios()` でシナリオを一括登録する

ステップファイルの先頭に `scenarios(str(_FEATURE_FILE))` を 1 行記述すれば、フィーチャーファイル内の全シナリオがテスト関数として登録される。LoRAIro では個別の `@scenario()` デコレータを使わず、常に `scenarios()` による一括登録を使用する。

#### `given`・`when`・`then` と `target_fixture`

- `@given` は事前条件、`@when` は操作、`@then` は検証を表す。
- ステップ間で値を引き継ぐ場合は `target_fixture` を使用する。戻り値が同名のフィクスチャとして後続ステップへ渡される。
- 既存の pytest フィクスチャは `given`、`when`、`then` の引数名で直接注入できる。

```python
@given(parsers.parse("there are {start:d} cucumbers"), target_fixture="cucumbers")
def given_cucumbers(start):
    return {"start": start, "eat": 0}  # 後続ステップが引数 cucumbers で受け取る

@when(parsers.parse("I eat {eat:d} cucumbers"))
def eat_cucumbers(cucumbers, eat):
    cucumbers["eat"] += eat
```

`target_fixture` は、特定シナリオだけで値を差し替えたい場合に既存フィクスチャを上書きする用途にも使える。

#### ステップ引数のパース

| パーサ | 用途 |
|---|---|
| `parsers.parse("... {n:d} ...")` | 基本形。`{name:d}` や `{name:f}` で型変換できるため、まずこれを使う |
| `parsers.cfparse(..., extra_types={...})` | カスタム型が必要な場合に使う |
| `parsers.re(r"...(?P<n>\d+)...")`, `converters={...}` | 正規表現が必要な場合に使う |

#### Background・Scenario Outline・datatable

- **Background**: 各シナリオの実行前に共通の `Given` を実行する。複数シナリオで重複する前提をまとめるために使う。
- **Scenario Outline + Examples**: `<変数>` プレースホルダと `Examples` テーブルでデータ駆動テストを記述する。`Examples` ブロックにタグを付けると `pytest -m <tag>` で絞り込める。
- **datatable**: ステップ直下の表は `datatable` 引数で `list[list[str]]` として受け取る(`database_management.feature` の「以下の画像とアノテーションが登録されている:」が該当する)。

### LoRAIro でのベストプラクティス

- **`scenarios()` 一括登録を徹底する**: `@scenario()` による個別指定は使わない。
- **フィーチャーパスは `__file__` 基準で解決する**: `Path(__file__).parent.parent / "features" / ...` と記述する。
- **ステップ間の状態は `target_fixture` またはコンテキストクラスで持ち回る**: モジュールグローバル変数で共有すると並列実行やテスト間汚染の原因になる。コンテキストクラスの例として `database_management.py` の `SearchContext` がある。
- **ステップ実装は薄く保つ**: `given`、`when`、`then` では Service や Repository を呼ぶだけにとどめ、ビジネスロジックをステップ内に書かない。
- **既存 pytest フィクスチャを再利用する**: DB マネージャや `FileSystemManager` は `conftest.py` のフィクスチャを引数で注入する。
- **`bdd` マーカーは自動付与に任せる**: `tests/bdd/conftest.py` の `pytest_collection_modifyitems` が自動付与するため、手動で `@pytest.mark.bdd` を書かない。
- **適用粒度を守る**: Repository 層の単純 CRUD へ BDD を広げると Gherkin が冗長になるため、`.claude/rules/testing.md` の適用表に従う。
- **タグの扱い**: フィーチャー内のタグは既定で pytest マーカーになる。`skip` などのカスタム挙動は `conftest.py` の `pytest_bdd_apply_tag` で実装する。
- **未実装ステップを検出する**: `uv run pytest --generate-missing --feature tests/bdd/features tests/bdd/steps/` を実行すると、フィーチャーにあって未実装のステップを洗い出せる。

### BDD テストの実行

```bash
uv run pytest -m bdd              # BDDテスト全体
uv run pytest tests/bdd/ -v       # ディレクトリ指定
```

## パフォーマンステスト

### ベンチマークテスト

```python
import pytest

@pytest.mark.benchmark
def test_database_query_performance(benchmark, populated_db):
    repo = ImageRepository(populated_db)

    # Benchmark query
    result = benchmark(repo.search, filters={"tags": "test"})

    assert len(result) > 0
```

ベンチマークの実行コマンド:

```bash
uv run pytest -m benchmark --benchmark-only
```

### 負荷テスト

```python
@pytest.mark.slow
def test_batch_annotation_1000_images(test_project):
    # Create 1000 test images
    images = [f"image_{i}.jpg" for i in range(1000)]
    test_project.add_images(images)

    # Measure batch processing time
    import time
    start = time.time()

    service = BatchProcessor()
    service.process_all(images)

    duration = time.time() - start

    # Assert reasonable performance
    assert duration < 300  # Under 5 minutes
```

## 上限付き実行(run_bounded)

長時間の pytest や計測を実行するときは、`... | tail` で直接つなげず `scripts/run_bounded.py` を経由する。`| tail` を直接使うと失敗時の終了コードが隠れるうえ、タイムアウトしても子プロセスがバックグラウンドに残留する(Issue #1632)。

このラッパーは対象コマンドを独立したプロセス群として起動し、タイムアウト時(終了コード 124)や終了後に孫プロセスまで SIGTERM、次いで SIGKILL で後始末する。`--pipe-to` で出力を絞った場合も、終了コードは対象コマンドの値をそのまま返す。`--memory-limit-gb` を指定すると、対象の仮想メモリ(`RLIMIT_AS`)に上限を設けられる(POSIX 専用)。

```bash
.venv/bin/python scripts/run_bounded.py --timeout 600 --memory-limit-gb 16 --pipe-to "tail -n 40" \
    -- .venv/bin/python -m pytest tests/unit --timeout=60 --timeout-method=thread
```

## 継続的インテグレーション

### GitHub Actions ワークフロー例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install uv
          uv sync --dev

      - name: Run tests
        env:
          QT_QPA_PLATFORM: offscreen
        run: |
          uv run pytest --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

## トラブルシューティング

### 不安定なテスト

- **症状**: 同じテストが成功したり失敗したりする。
- **原因**:
  - 条件待機の `waitUntil()` ではなく固定時間の `qtbot.wait()` を使っている。
  - 非同期・マルチスレッド処理で競合状態が発生している。
  - テスト間で状態が共有されている。
- **対処法**:

```python
# ❌ FLAKY
qtbot.wait(100)  # May not be enough

# ✅ ROBUST
qtbot.waitUntil(lambda: widget.is_ready(), timeout=1000)
```

### Qt クリーンアップ警告

- **症状**: `QObject::~QObject: Timers cannot be stopped from another thread` が出力される。
- **原因**: ウィジェットが適切に破棄・後始末されていない。
- **対処法**:

```python
@pytest.fixture
def widget(qtbot):
    w = MyWidget()
    qtbot.addWidget(w)  # Ensures cleanup
    return w
```

### データベースロック

- **症状**: `database is locked` エラーが発生する。
- **原因**: 複数のセッションが同じ SQLite DB へ同時にアクセスしている。
- **対処法**:

```python
# Use separate DB for each test
@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4()}.db"
    # ...
```

## テストリファクタリング Phase 2: マーカー自動付与(2026-02-10)

### 実装内容

`conftest.py` に pytest マーカー自動付与フックを実装した。

```python
# tests/unit/conftest.py の例
def pytest_collection_modifyitems(config, items):
    """tests/unit 配下のテストに @pytest.mark.unit を自動付与"""
    for item in items:
        if "tests/unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
```

マーカーの適用結果:

- `unit`: 1,025 テスト
- `integration`: 226 テスト
- `gui`: 622 テスト
- `bdd`: 29 テスト(`database_management` 10 件 + `logging` 19 件)

### 利点

1. **安全性**: テストファイルを直接編集せずにマーカーを付与できる。
2. **保守性**: マーカー定義を `conftest.py` に一元化できる。
3. **拡張性**: 新規テストを追加するだけで自動的にマーカーが付与される。
4. **層別管理**: 各層(`unit`、`integration`、`gui`、`bdd`)で独立したフィクスチャを管理できる。

### 次のステップ

**Phase 4(pytest-qt 改善・残作業)**:

- `qtbot.wait()` から `qtbot.waitUntil()` への移行(2026-07-05 時点で固定待機が 9 箇所残存)。
- 対象箇所は `grep -rn "qtbot\.wait(" tests/` で洗い出し、手動で条件待機へ書き換える。

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) — 開発概要
- [docs/services.md](services.md) — サービス層アーキテクチャ
- [docs/integrations.md](integrations.md) — 外部パッケージ統合
- [pytest-qt documentation](https://pytest-qt.readthedocs.io/)
- [pytest documentation](https://docs.pytest.org/)
