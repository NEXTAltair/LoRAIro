# torch初期化エラーの根本原因：モジュールレベルインポート設計問題

## 調査日
2025-10-28

## 背景
Phase 2 Task 3.4（基底クラステスト拡張 8% → 40%）実施中、pytest実行時に以下のエラーが発生：
```
RuntimeError: function '_has_torch_function' already has a docstring
```

## 根本原因
環境問題ではなく**コード設計の問題**。重いMLライブラリを過剰にモジュールレベルでインポートしているため、pytest collection時にすべてのライブラリが初期化され、torchの複数初期化エラーが発生。

## 発見した設計問題

### 1. utils.py - torch の不要なモジュールレベルインポート
- **場所**: `src/image_annotator_lib/core/utils.py` Line 11
- **現状**: `import torch` をモジュールレベルで実行
- **使用箇所**: `determine_effective_device()` 関数内のみ（Lines 244, 257, 261の3箇所）
- **影響**: utils.py をインポートする全モジュールで torch が初期化される
- **修正案**: 関数内で lazy import
  ```python
  def determine_effective_device(requested_device: str, model_name: str | None = None) -> str:
      actual_device = requested_device
      if requested_device.startswith("cuda"):
          import torch  # ← ここに移動
          try:
              if not torch.cuda.is_available():
                  # ... 以下同じ
  ```

### 2. model_factory.py - すべてのMLライブラリのモジュールレベルインポート (**最重要**)
- **場所**: `src/image_annotator_lib/core/model_factory.py` Lines 11-30
- **現状**: 以下をすべてモジュールレベルでインポート
  - `import onnxruntime as ort` (line 11)
  - `import tensorflow as tf` (line 13)
  - `import torch` (line 14)
  - `import torch.nn as nn` (line 15)
  - `from anthropic import Anthropic` (lines 16-17)
  - `from google import genai` (lines 18-19)
  - `from openai import OpenAI` (lines 20-23)
  - `from transformers...` (lines 26-30)
- **影響**: model_factory をインポートする全モジュールですべてのライブラリが初期化される
- **問題点**:
  - ONNXモデルのテストで anthropic/openai は不要
  - WebAPIモデルのテストで tensorflow/onnxruntime は不要
  - なのに、すべてがロードされる
- **修正案**: 各 Adapter クラスのメソッド内、または各ロードメソッド内で lazy import
  ```python
  # Before (module-level)
  import torch
  from openai import OpenAI
  
  # After (method-level)
  class OpenAIAdapter(ApiClient):
      def call_api(self, ...):
          from openai import OpenAI  # ← メソッド内でインポート
  ```

### 3. types.py - 型定義のための実装インポート
- **場所**: `src/image_annotator_lib/core/types.py` Lines 8-12
- **現状**: 型定義のために実装ライブラリをモジュールレベルでインポート
  - `import onnxruntime as ort` (line 8)
  - `from transformers.models.auto.processing_auto import AutoProcessor` (line 10)
  - `from transformers.models.clip import CLIPModel, CLIPProcessor` (line 11)
  - `from transformers.pipelines.base import Pipeline as TransformersPipelineObject` (line 12)
- **影響**: types.py をインポートする全モジュールで onnxruntime と transformers が初期化される
- **問題点**: TypedDict の型定義に実装ライブラリは不要。`TYPE_CHECKING` で遅延インポートすべき
- **修正案**: 条件付きインポート + 文字列リテラル型ヒント
  ```python
  from typing import TYPE_CHECKING
  
  if TYPE_CHECKING:
      import onnxruntime as ort
      from transformers.models.auto.processing_auto import AutoProcessor
      from transformers.models.clip import CLIPModel, CLIPProcessor
      from transformers.pipelines.base import Pipeline as TransformersPipelineObject
  
  class ONNXComponents(TypedDict):
      session: "ort.InferenceSession"  # 文字列リテラルに変更
      csv_path: Path
  ```

## 問題の連鎖構造
```
test_base.py
  → base/annotator.py → utils.py (torch 初期化)
  → base/onnx.py → model_factory.py (torch + tensorflow + transformers + onnx + anthropic + openai 初期化)
                 → types.py (onnxruntime + transformers 初期化)
```

テストファイルが基底クラスをインポートすると、不要なすべてのMLライブラリが初期化される構造。

## 修正の優先順位
1. **model_factory.py** - 最も深刻。すべてのライブラリを不要にロード
2. **types.py** - 型定義のために実装をインポートするアンチパターン
3. **utils.py** - 単一関数のために torch をグローバルインポート

## 期待される効果
- pytest collection エラー解消
- テスト実行時のメモリ使用量削減
- テスト実行速度向上
- 不要なライブラリの初期化回避

## ステータス
- **発見日**: 2025-10-28
- **対応**: 別タスクで実施予定
- **関連タスク**: Phase 2 Task 3.4（基底クラステスト拡張）は、この修正後に実施可能

## 参考: ユーザーの洞察
> "その原因の説明を見るとPytorchのインストールや.venvが悪いというよりテストの設計が悪い気がする"

ユーザーの指摘通り、環境ではなくコード設計の問題だった。
