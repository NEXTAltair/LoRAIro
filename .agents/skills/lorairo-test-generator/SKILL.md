---
name: lorairo-test-generator
version: "1.0.0"
description: Generate pytest unit, integration, and GUI tests for LoRAIro with fixtures, mocks, 75%+ coverage, and pytest-qt for PySide6. Use when creating test suites or ensuring code quality.
metadata:
  short-description: LoRAIro向けpytest/pytest-qtテスト生成（fixtures、mocks、カバレッジ重視）。
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

# Test Generation for LoRAIro

pytest+pytest-qt test generation with fixtures, mocks, and 75%+ coverage for LoRAIro project.

## When to Use

Use this skill when:
- **Creating tests**: After implementing new features
- **Improving coverage**: Increasing existing test coverage
- **Regression testing**: After refactoring code
- **GUI testing**: Implementing PySide6 widget tests

## Test Categories

### pytest Markers

**Three test levels:**
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

### Running Tests

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

### Native Dependency Smoke Tests

LoRAIro shares one canonical `.venv` at `/workspaces/LoRAIro/.venv`, including when commands run from
`.agents/worktree/` checkouts. Treat default-sync `uv run`, `uv sync`, dependency upgrades, and torch/NVIDIA
wheel repairs as shared environment mutations; do not run them concurrently across workers.

Run a torch/CUDA smoke test after dependency updates, after failures involving local annotators, or when errors
mention missing native libraries such as `libcudnn.so.9`, `libcusparseLt.so.0`, `libtorch_cuda.so`, or `triton`:

```bash
uv run --no-sync python -c "import torch, torchvision; print(torch.__version__, torchvision.__version__, torch.cuda.is_available())"
find .venv/lib/python*/site-packages -name 'libcudnn.so*' -o -name 'libcusparseLt.so*'
uv pip check
```

Known failure mode: `uv` can leave NVIDIA/PyTorch packages in an inconsistent state where package metadata and
`RECORD` say `nvidia-cudnn-cu13` or `nvidia-cusparselt-cu13` is installed, but the actual `.so` files are missing.
`uv pip check` may not detect this because dependencies are still installed from the resolver's perspective.

Repair order:
1. Prefer non-mutating checks first (`uv run --no-sync ...`, `find`, `uv pip check`).
2. If only specific NVIDIA shared objects are missing, force-reinstall the narrow package(s), for example
   `uv pip install --force-reinstall nvidia-cudnn-cu13 nvidia-cusparselt-cu13`.
3. Reinstall `torch` / `torchvision` from the configured PyTorch CUDA index only when the narrow repair fails.
4. If repeated narrow repairs expose more missing native libraries, or installed metadata repeatedly disagrees with
   actual files, stop repairing piecemeal and tell the user that the shared `.venv` likely needs to be rebuilt.
5. Do not remove or recreate the shared `.venv` from an agent session unless the user explicitly asks for shared
   environment maintenance. The user is the authority on whether other sessions are still using the shared `.venv`.

## Core Patterns

### 1. Unit Tests

**Repository test example:**
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

**Service test with mocks:**
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

### 2. Integration Tests

**Full workflow test:**
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

### 3. GUI Tests (pytest-qt)

**Widget test:**
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

### 4. Fixtures

**Common fixtures:**
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

## Best Practices

**DO:**
- Use AAA pattern (Arrange, Act, Assert)
- Single assertion per test (or tightly coupled assertions on one outcome)
- Use fixtures for setup/teardown
- Apply appropriate pytest markers (`unit`, `integration`, `gui`, `cli`, `bdd`)
- Mock `QMessageBox` (`monkeypatch`) in GUI tests so modal dialogs never block headless runs
- Use `qtbot.waitSignal()` or `qtbot.waitUntil()` instead of fixed `qtbot.wait()`
- Respect package test boundaries (ADR 0024: run LoRAIro main tests with `make test`, `image-annotator-lib` with `make test-iam-lib`, `genai-tag-db-tools` with `make test-genai-tag`)
- Maintain 75%+ code coverage

**DON'T:**
- Create dependencies between tests
- Call external APIs or download models in standard test runs (`not downloads_and_runs_model and not calls_real_webapi`)
- Leave `QMessageBox.question` / `warning` / `critical` unmocked
- Hardcode paths (use `tests/resources/` or `tmp_path`)
- Use print statements (use logger or assert messages)
- Write slow unit tests (keep under 1 second)

## Coverage Requirements

```bash
# Generate coverage report
uv run --no-sync pytest --cov=src --cov-report=html

# View in browser: htmlcov/index.html

# Requirements:
# - Minimum: 75% (configured in pyproject.toml [tool.coverage.report] fail_under = 75)
# - Target: Unit 90%+, Integration 80%+, GUI 70%+
```

## Project Structure

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

## Test Sync (diff-driven, 旧 /test sync)

コード変更後に、テストの**追加・修正・削除**を差分から判定して同期する。新規実装直後だけでなく、
リファクタやシグネチャ変更の後にも使う。

### 手順

1. **変更検出**: 変更されたソースを特定し、種別を分類する。
   ```bash
   git diff --name-status HEAD~1..HEAD -- 'src/**/*.py'
   ```
   - `A` (Added) → 対応テストを**追加**
   - `M` (Modified) → シグネチャ/振る舞い変更ならテストを**修正**（内部実装のみなら実行で確認、変更不要のことが多い）
   - `D` (Deleted) → 対応テストを**削除**（削除前にユーザー確認）
2. **影響範囲の特定**: `Grep` で変更シンボルの参照元を追い、波及するテストを洗う。
3. **テストファイル対応表**:
   - `src/lorairo/database/repository/foo.py` → `tests/unit/database/repository/test_foo_repository.py`
   - `src/lorairo/services/foo.py` → `tests/unit/services/test_foo.py`
   - `src/lorairo/gui/tab/foo_tab.py` → `tests/unit/gui/tab/test_foo_tab.py`
   - `src/lorairo/gui/widgets/bar.py` → `tests/unit/gui/widgets/test_bar.py`
4. **同期アクション実行**: 追加は本 skill の Core Patterns に従い生成。修正は変更 API に合わせ更新。削除は確認後に実施。
5. **検証**: 新規/修正テストと回帰テストを `make test` または `uv run --no-sync pytest -m "not downloads_and_runs_model and not calls_real_webapi"` で確認（定義は `scripts/dev_tasks.py` および `pyproject.toml`）。

クイック品質チェック（Ruff/mypy/pytest）は `make lint` / `make mypy` / `make test` で直接実行する。

## Before Writing Tests

類似のテストパターン・既存 fixture を確認する（`tests/conftest.py`、近接する `test_*.py`）。再利用価値のあるテスト戦略・モック方針は `docs/lessons-learned.md` に記録する。

## Examples

See [examples.md](./examples.md) for detailed test implementation scenarios.

## Reference

See [reference.md](./reference.md) for complete pytest and pytest-qt API reference.
