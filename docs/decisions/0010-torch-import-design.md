---
type: ADR
title: Torch Import Design
status: Accepted
timestamp: 2025-10-28
tags: []
---
# ADR 0010: Torch Import Design

## Context

pytest の実行時に `RuntimeError: function '_has_torch_function' already has a docstring` が発生した。原因は環境依存の不具合ではなく、重い機械学習ライブラリ(`torch`、`tensorflow`、`onnxruntime`)をモジュールレベルでインポートしていたことだった。

## Decision

**遅延インポート(Lazy Import)**を採用する。

- モジュールレベルの `import torch` と `import onnxruntime` を削除する。
- 関数またはメソッドの内部で、実際に必要なタイミングのみインポートする。
- 型注釈のみを目的とする参照には `TYPE_CHECKING` ブロックを使用する。

```python
# Before (module-level)
import torch  # 全テストで初期化

# After (method-level)
def determine_effective_device(...):
    import torch  # 必要な時だけ
```

## Rationale

モジュールレベルのインポートにより、`test_base.py` から `base/annotator.py`、`utils.py`(`torch` の初期化)、`model_factory.py`(`torch`、`tensorflow`、`onnx`、`anthropic`、`openai` の全初期化)へと連鎖的に読み込みが広がっていた。その結果、ONNX モデルのテストでは不要な `anthropic` などのライブラリまで全件ロードされていた。

## Consequences

- pytest のテスト収集時エラーを解消した。
- テスト実行時のメモリ使用量を削減できた。
- テストの実行速度が向上した。
- `TYPE_CHECKING` ブロック内で参照する型は、`"ort.InferenceSession"` のように文字列リテラルで記述する必要がある。
