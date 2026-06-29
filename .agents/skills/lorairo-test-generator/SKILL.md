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
dependencies:
  - lorairo-mem
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
- Single assertion per test
- Use fixtures for setup/teardown
- Apply appropriate pytest markers
- Maintain 75%+ code coverage

**DON'T:**
- Create dependencies between tests
- Call external APIs (use mocks)
- Hardcode paths (use `tests/resources/`)
- Use print statements (use logger or assert messages)
- Write slow unit tests (keep under 1 second)

## Coverage Requirements

```bash
# Generate coverage report
uv run pytest --cov=src --cov-report=html

# View in browser: htmlcov/index.html

# Requirements:
# - Minimum: 75%
# - Target: Unit 90%+, Integration 80%+, GUI 70%+
```

## Project Structure

```
tests/
├── conftest.py              # Shared fixtures
├── resources/               # Test data
│   ├── sample.jpg
│   └── test_config.toml
├── database/                # Database tests
│   └── test_db_repository.py
├── services/                # Service tests
│   └── test_image_processing_service.py
└── gui/                     # GUI tests
    ├── widgets/
    │   └── test_thumbnail_widget.py
    └── window/
        └── test_main_window.py
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
2. **影響範囲の特定**: `investigation` agent または `Grep` で変更シンボルの参照元を追い、波及するテストを洗う。
3. **テストファイル対応表**:
   - `src/lorairo/services/foo.py` → `tests/unit/services/test_foo.py`
   - `src/lorairo/gui/widgets/bar.py` → `tests/unit/gui/widgets/test_bar.py`
4. **同期アクション実行**: 追加は本 skill の Core Patterns に従い生成。修正は変更 API に合わせ更新。削除は確認後に実施。
5. **検証**: 新規/修正テストと回帰テストを `uv run pytest` で確認（CI-equivalent filter は `.claude/rules/testing.md`）。

クイック品質チェック（Ruff/mypy/pytest）は `make format` / `make mypy` / `uv run pytest` で直接実行する（専用コマンドは不要）。
エラー診断は superpowers `systematic-debugging` + `build-error-resolver` agent に委ねる。

## Memory Integration

**Before writing tests:**
1. 類似のテストパターン・既存 fixture を確認する（`tests/conftest.py`、近接する `test_*.py`）。
2. 長期記憶に該当知見があれば [[lorairo-mem]] の `ltm_search.py` で参照する。

**After writing tests:**
- 再利用価値のあるテスト戦略・モック方針は [[lorairo-mem]] に `type: howto` で保存する。

## Examples

See [examples.md](./examples.md) for detailed test implementation scenarios.

## Reference

See [reference.md](./reference.md) for complete pytest and pytest-qt API reference.
