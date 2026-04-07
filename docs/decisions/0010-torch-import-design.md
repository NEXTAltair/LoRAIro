# ADR 0010: Torch Import Design

- **日付**: 2025-10-28
- **ステータス**: Accepted

## Context

pytest 実行時に `RuntimeError: function '_has_torch_function' already has a docstring` が発生。環境問題ではなく、重い ML ライブラリ (torch, tensorflow, onnxruntime) をモジュールレベルでインポートしていたことが原因。

## Decision

**遅延インポート（Lazy Import）**を採用:
- モジュールレベルの `import torch` / `import onnxruntime` を削除
- 関数/メソッド内で必要な時のみインポート
- 型定義のみの用途には `TYPE_CHECKING` ブロックを使用

```python
# Before (module-level)
import torch  # 全テストで初期化

# After (method-level)
def determine_effective_device(...):
    import torch  # 必要な時だけ
```

## Rationale

問題の連鎖: `test_base.py` → `base/annotator.py` → `utils.py` (torch 初期化) → `model_factory.py` (torch + tensorflow + onnx + anthropic + openai 全初期化)。ONNX モデルのテストで anthropic は不要なのに全ライブラリがロードされていた。

## Consequences

- pytest collection エラー解消
- テスト実行時のメモリ使用量削減
- テスト実行速度向上
- `TYPE_CHECKING` ブロック内の型は文字列リテラルで参照する必要あり (`"ort.InferenceSession"`)
