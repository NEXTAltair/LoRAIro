---
name: lorairo-test-generator
version: "1.0.0"
description: Generate pytest unit, integration, and GUI tests for LoRAIro with fixtures, mocks, 75%+ coverage, and pytest-qt for PySide6. Use when creating test suites or ensuring code quality.
metadata:
  short-description: LoRAIro向けpytest/pytest-qtテスト生成(fixtures、mocks、カバレッジ重視)。
allowed-tools:
  # Code exploration
  - Grep
  - Grep
  - Grep
  # Memory (test patterns)
  - Grep
  # Fallback
  - Read
  - Write
  - Bash
---

# LoRAIro 向けテスト生成ガイド

LoRAIro プロジェクト向けに、`pytest` と `pytest-qt` を使ったテストを生成するためのガイドである。フィクスチャと mock を活用し、75% 以上のカバレッジを維持する。

## 適用場面

- **テストの新規作成**: 新機能を実装した直後にテストを追加するとき
- **カバレッジの改善**: 既存コードのテストカバレッジを引き上げるとき
- **回帰テスト**: リファクタリング後に既存挙動を検証するとき
- **GUI テスト**: PySide6 ウィジェットのテストを実装するとき

## テストカテゴリ

### pytest マーカー

テストは次の 3 つのレベルに分類する。

```python
# Unit tests: Single function/class, business logic
@pytest.mark.unit
def test_calculate_score():
    assert calculate_score(10, 20) == 0.5

# Integration tests: Multiple components
@pytest.mark.integration
def test_repository_service_integration():
    service = ImageProcessingService(repository)
    result = service.process_batch(images)
    assert len(result) > 0

# GUI tests: PySide6 widgets
@pytest.mark.gui
def test_widget_interaction(qtbot):
    widget = ThumbnailWidget()
    qtbot.addWidget(widget)
    assert widget.isVisible()
```

### テストの実行コマンド

```bash
# All tests
uv run pytest

# By category
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m gui

# With coverage
uv run pytest --cov=src --cov-report=html
```

### ネイティブ依存のスモークテスト

LoRAIro は `.agents/worktree/` 配下のチェックアウトを含め、`/workspaces/LoRAIro/.venv` にある単一の共有 `.venv` を利用する。暗黙の同期を伴う `uv run`、`uv sync`、依存パッケージの更新、および `torch`・NVIDIA wheel の修復は共有環境の変更に該当する。複数のワーカーから並列実行してはならない。

依存更新の後や、ローカルアノテーター関連の失敗時、あるいは `libcudnn.so.9`・`libcusparseLt.so.0`・`libtorch_cuda.so`・`triton` などのネイティブライブラリ不足を示すエラーが出たときは、次の `torch` / CUDA スモークテストを実行する。

```bash
uv run --no-sync python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__, torch.cuda.is_available())"
find .venv/lib/python*/site-packages -name 'libcudnn.so*' -o -name 'libcusparseLt.so*'
uv pip check
```

**既知の障害モード**: `uv` の操作によって NVIDIA・PyTorch パッケージが不整合な状態になることがある。パッケージのメタデータや `RECORD` 上では `nvidia-cudnn-cu13` や `nvidia-cusparselt-cu13` がインストール済みとなっているのに、実際の `.so` ファイルが欠損しているケースである。依存関係リゾルバー上は導入済みとみなされるため、`uv pip check` では検出できない場合がある。

**修復手順:**

1. まず環境を変更しない確認コマンドを優先して実行する(`uv run --no-sync ...`、`find`、`uv pip check`)。
2. 特定の NVIDIA 共有ライブラリだけが欠損している場合は、対象パッケージのみを強制再インストールする(例: `uv pip install --force-reinstall nvidia-cudnn-cu13 nvidia-cusparselt-cu13`)。
3. 局所的な修復で解決しない場合に限り、設定済みの PyTorch CUDA インデックスから `torch` と `torchvision` を再インストールする。
4. 局所修復を繰り返しても別のネイティブライブラリ欠損が次々と現れる場合や、インストール済みメタデータと実ファイルの不整合が続く場合は、個別修復を打ち切る。そのうえで、共有 `.venv` の再構築が必要である旨をユーザーへ報告する。
5. ユーザーから共有環境の保守を明示的に依頼されない限り、エージェントセッションから共有 `.venv` を削除・再作成しない。他のセッションが共有 `.venv` を使用中かどうかはユーザーが判断する。

## コアパターン

### 1. ユニットテスト

**リポジトリのテスト例:**

```python
@pytest.fixture
def test_repository(test_db_engine):
    session_factory = scoped_session(sessionmaker(bind=test_db_engine))
    repo = ImageRepository(session_factory)
    yield repo
    session_factory.remove()

@pytest.mark.unit
def test_add_image(test_repository):
    """Test image addition."""
    image = Image(path="/test/image.jpg", phash="abc123")
    result = test_repository.add(image)

    assert result.id is not None
    assert result.path == "/test/image.jpg"
```

**mock を使ったサービスのテスト例:**

```python
@pytest.fixture
def mock_repository():
    repo = Mock(spec=ImageRepository)
    repo.get_all.return_value = [Image(id=1, path="/img1.jpg")]
    return repo

@pytest.mark.unit
def test_process_batch(mock_repository):
    service = ImageProcessingService(mock_repository)
    result = service.process_batch(["/img1.jpg"])
    assert len(result) == 1
```

### 2. 統合テスト

**一連のワークフローを検証する例:**

```python
@pytest.mark.integration
def test_full_workflow(test_repository):
    """Test complete workflow."""
    # Arrange
    images = [Image(path=f"/img{i}.jpg") for i in range(5)]

    # Act & Assert
    added = test_repository.batch_add(images)
    assert len(added) == 5

    results = test_repository.search(SearchCriteria(min_score=0.5))
    assert isinstance(results, list)
```

### 3. GUI テスト(`pytest-qt`)

**ウィジェットのテスト例:**

```python
@pytest.fixture
def thumbnail_widget(qtbot):
    widget = ThumbnailWidget()
    qtbot.addWidget(widget)
    return widget

@pytest.mark.gui
def test_signal_emission(qtbot, thumbnail_widget):
    """Test signal emission."""
    with qtbot.waitSignal(thumbnail_widget.image_selected, timeout=1000) as blocker:
        thumbnail_widget.select_image(0)

    assert blocker.args[0] == "/path/to/image.jpg"

@pytest.mark.gui
def test_button_click(qtbot, thumbnail_widget):
    """Test button interaction."""
    qtbot.mouseClick(thumbnail_widget._ui.loadButton, Qt.LeftButton)
    assert thumbnail_widget._images_loaded is True
```

### 4. フィクスチャ

**共通フィクスチャの例:**

```python
@pytest.fixture(scope="session")
def test_data_dir():
    return Path(__file__).parent / "resources"

@pytest.fixture
def sample_image(test_data_dir):
    return test_data_dir / "sample.jpg"

@pytest.fixture(params=[1, 5, 10])
def batch_size(request):
    """Parameterized fixture."""
    return request.param
```

## ベストプラクティス

### 推奨事項

- AAA パターン(Arrange・Act・Assert)で構成する。
- 1 テストにつき 1 つのアサーション、または 1 つの結果に密接に関連するアサーションに絞る。
- セットアップと後片付けにはフィクスチャを使う。
- 適切な pytest マーカー(`unit`、`integration`、`gui`、`cli`、`bdd`)を付与する。
- ヘッドレス実行がモーダルダイアログで停止しないよう、GUI テストでは `QMessageBox` を `monkeypatch` で mock 化する。
- 固定時間の `qtbot.wait()` ではなく、`qtbot.waitSignal()` または `qtbot.waitUntil()` を使う。
- パッケージごとのテスト境界を守る(ADR 0024: LoRAIro 本体は `make test`、`image-annotator-lib` は `make test-iam-lib`、`genai-tag-db-tools` は `make test-genai-tag`)。
- コードカバレッジを 75% 以上に維持する。

### 禁止事項

- テスト間の実行順序や状態に依存させない。
- 標準テスト実行で外部 API を呼び出したり、モデルをダウンロードしたりしない(`not downloads_and_runs_model and not calls_real_webapi`)。
- `QMessageBox.question`・`warning`・`critical` を mock しないまま放置しない。
- ファイルパスをハードコードしない(`tests/resources/` または `tmp_path` を使う)。
- `print` 文を使わず、`logger` または `assert` メッセージを使う。
- 遅いユニットテストを書かない(1 秒未満に収める)。

## カバレッジ要件

```bash
# Generate coverage report
uv run --no-sync pytest --cov=src --cov-report=html

# View in browser: htmlcov/index.html

# Requirements:
# - Minimum: 75% (configured in pyproject.toml [tool.coverage.report] fail_under = 75)
# - Target: Unit 90%+, Integration 80%+, GUI 70%+
```

## テストディレクトリ構成

```
tests/
├── resources/               # Test assets (images, sample configs)
├── unit/                    # Unit & headless GUI tests
│   ├── cli/                 # CLI command unit tests
│   ├── database/            # Database & repository unit tests
│   │   └── repository/      # Aggregate repository tests (test_image_repository.py, etc.)
│   ├── gui/                 # PySide6 GUI tests
│   │   ├── tab/             # Tab widget tests (test_search_tab.py, test_annotate_tab.py, etc.)
│   │   ├── widgets/         # Reusable widget tests
│   │   ├── window/          # MainWindow tests (test_main_window.py, test_main_window_coverage.py)
│   │   └── workers/         # Worker & WorkerManager tests
│   └── services/            # Service layer unit tests
├── integration/             # Multi-component integration tests
└── bdd/                     # pytest-bdd feature scenarios
```

## テスト同期(差分駆動、旧 `/test sync`)

コードを変更したあと、差分からテストの**追加・修正・削除**を判定して同期する。新規実装の直後だけでなく、リファクタリングやシグネチャ変更のあとにも活用する。

### 手順

1. **変更の検出**: 変更されたソースファイルを特定し、変更種別を分類する。
   ```bash
   git diff --name-status HEAD~1..HEAD -- 'src/**/*.py'
   ```
   - `A`(Added): 対応するテストを**追加**する。
   - `M`(Modified): シグネチャや振る舞いが変わった場合はテストを**修正**する。内部実装のみの変更であればテスト実行で確認し、変更不要なことが多い。
   - `D`(Deleted): 対応するテストを**削除**する(削除前にユーザーへ確認する)。
2. **影響範囲の特定**: `Grep` で変更シンボルの参照元を追い、影響を受けるテストを洗い出す。
3. **テストファイル対応表**:
   - `src/lorairo/database/repository/foo.py` → `tests/unit/database/repository/test_foo_repository.py`
   - `src/lorairo/services/foo.py` → `tests/unit/services/test_foo.py`
   - `src/lorairo/gui/tab/foo_tab.py` → `tests/unit/gui/tab/test_foo_tab.py`
   - `src/lorairo/gui/widgets/bar.py` → `tests/unit/gui/widgets/test_bar.py`
4. **同期アクションの実行**: 追加は本スキルのコアパターンに従って生成し、修正は変更後の API に合わせて更新する。削除は確認後に実施する。
5. **検証**: 新規・修正テストおよび回帰テストを `make test`、または `uv run --no-sync pytest -m "not downloads_and_runs_model and not calls_real_webapi"` で確認する(コマンド定義は `scripts/dev_tasks.py` と `pyproject.toml` にある)。

テスト変更の簡易チェックは、変更ファイルへの Ruff と関連する pytest を実行する。パッケージ全体の型チェックは CI で実行する。

## テストを書く前の確認

事前に `tests/conftest.py` や近接する `test_*.py` を読み込み、類似のテストパターンや既存フィクスチャを確認する。再利用価値のあるテスト戦略や mock 方針は `docs/lessons-learned.md` に記録する。

## 実装例

詳細なテスト実装シナリオは [examples.md](./examples.md) を参照する。

## リファレンス

`pytest` および `pytest-qt` の完全な API リファレンスは [reference.md](./reference.md) を参照する。
