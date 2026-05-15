# Test Side Effects from Lazy Import Refactor

Module-level import を関数内に移したときに発生する test 側の副作用と対応パターン集。

## Pattern 1: @patch module attribute → AttributeError

### Symptom

```
AttributeError: <module 'pkg.foo' from '...'> does not have the attribute 'torch'
```

### Cause

Module-level の `import torch` を削除すると、`pkg.foo.torch` という module attribute が消滅する。`@patch("pkg.foo.torch")` は attribute を指定して patch するため、attribute 不在で fail する。

### Fix

`monkeypatch.setitem(sys.modules, ...)` で torch module そのものを mock に差し替える。関数内 `import torch` が `sys.modules` を参照するため、これで mock が注入される。

```python
def test_foo(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    mock_torch = MagicMock()
    monkeypatch.setitem(sys.modules, "torch", mock_torch)

    # 関数を呼び出すと、関数内 `import torch` が mock_torch を取得する
    annotator = SomeAnnotator()
    annotator.run_inference(...)
```

### 注意点

- pytest monkeypatch fixture は teardown で自動 restore する
- 同一 test session 内で既に real torch が `sys.modules` 済みでも、`monkeypatch.setitem` で一時的に差し替えできる
- subprocess test (fresh interpreter) では `sys.modules` 汚染がないので mock 不要のケースもある

## Pattern 2: Context manager mock setup

torch.no_grad() を `with` 文で使う:

```python
def test_foo(monkeypatch):
    import sys
    from unittest.mock import MagicMock
    mock_torch = MagicMock()
    monkeypatch.setitem(sys.modules, "torch", mock_torch)

    # MagicMock は __enter__/__exit__ を自動サポートするので通常不要
    # 明示が必要な場合のみ:
    mock_torch.no_grad.return_value.__enter__ = MagicMock()
    mock_torch.no_grad.return_value.__exit__ = MagicMock(return_value=False)
```

`MagicMock` (not `Mock`) は magic methods を auto-spec するため、`with mock_torch.no_grad():` は通常そのまま動作する。

## Pattern 3: getattr-based / nested attribute access

```python
mock_torch.cuda.is_available.return_value = False
mock_torch.cuda.OutOfMemoryError = RuntimeError  # subclass 模倣
mock_torch.Tensor = type("MockTensor", (), {})  # isinstance check 用
```

`MagicMock` は属性アクセスで子 MagicMock を自動生成するため、ほぼ全ての nested access パターンで動く。`isinstance` check が必要な場合のみ実 type を割り当てる。

## Pattern 4: Real torch を保持したいが特定関数のみ mock

```python
def test_foo(monkeypatch):
    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    # 他の torch attribute は real のまま
```

この pattern は `patch("torch.cuda.is_available")` でも実現可能だが、lazy import 化された code base では `monkeypatch.setattr` の方が見通しが良い。

## Pattern 5: Subprocess regression test

```python
import subprocess
import sys
import textwrap


def test_import_does_not_eager_load_torch():
    """`import lib` 単体で torch が load されないことを fresh interpreter で確認"""
    script = textwrap.dedent("""
        import sys
        import image_annotator_lib  # noqa: F401

        loaded = sorted(
            m for m in sys.modules
            if m == "torch" or m.startswith("torch.")
        )
        if loaded:
            for m in loaded:
                print(f"LEAK: {m}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"eager-loaded:\n{result.stderr}"
```

同一 pytest session 内で既に他テストが torch を import 済みだと `sys.modules` に残留して検出不能になるため、fresh interpreter を subprocess で起動して検証する。

iam-lib では `tests/unit/core/test_lazy_torch_import.py` で本パターンを採用 (PR #62)。

## 判定フロー

修正対象が:
- `@patch("path.to.module.torch")` → **Pattern 1** で sys.modules 注入に変更
- `torch.no_grad()` 等の context manager 使用 → **Pattern 2** (通常は MagicMock 自動対応)
- `torch.cuda.is_available()` 等の nested access → **Pattern 3** で mock setup
- 既存 `monkeypatch.setattr("torch.cuda.is_available", ...)` 形式 → **Pattern 4**、変更不要
- module-level import 排除そのものの検証 → **Pattern 5** で subprocess regression test 追加
