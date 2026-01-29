# image-annotator-lib 技術仕様書

**作成日**: 2025-10-22
**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## 技術スタック

- Python >= 3.12
- Deep Learning: PyTorch, ONNX Runtime, TensorFlow
- AI Framework: PydanticAI (構造化出力)
- Config: TOML
- Quality: Ruff, Mypy strict, pytest

## ディレクトリ構造

```
src/image_annotator_lib/
├── api.py                        # メインAPI
├── core/
│   ├── base/                     # 基底クラス群
│   │   ├── annotator.py          # BaseAnnotator
│   │   ├── transformers.py       # TransformersBase
│   │   ├── onnx.py              # ONNXBase
│   │   ├── webapi.py            # WebApiBase
│   │   └── pydantic_ai_annotator.py  # PydanticAI Mixin
│   ├── config.py                # ModelConfigRegistry
│   ├── model_factory.py         # ModelLoad
│   ├── registry.py              # ModelRegistry
│   ├── types.py                 # 統一型定義
│   ├── provider_manager.py      # ProviderManager
│   └── pydantic_ai_factory.py   # PydanticAIProviderFactory
└── model_class/annotator_webapi/
    ├── anthropic_api.py
    ├── google_api.py
    ├── openai_api_chat.py
    └── openai_api_response.py
```

## 主要技術決定

### 2025-06-25: PydanticAI Provider-levelアーキテクチャ
- ProviderManager: APIプロバイダーごとクライアントインスタンス管理・共有
- PydanticAIProviderFactory: Agent効率キャッシュ・再利用

### 2025-05-13: 型定義一元管理 (core/types.py)
- UnifiedAnnotationResult, AnnotationSchema, TaskCapability集約
- 循環参照防止

### 2025-04-19: CUDA非対応環境CPUフォールバック
- 環境に応じてcuda/cpu自動判定

### 2025-04-18: ログ出力ライブラリ変更
- logging → loguru (構造化ログ、動的レベル変更)

## 新モデル追加方法

### ローカルモデル
1. model_class/に基底クラス継承クラス作成
2. `_generate_tags`/`_run_inference`実装
3. annotator_config.toml設定追加

### Web APIモデル (Provider-Level)
1. WebApiBaseAnnotator + PydanticAIAnnotatorMixin継承
2. `__init__`で両方のinit呼び出し
3. `__enter__`で`_setup_agent()`
4. `run_with_model`実装
5. `_run_inference`で`run_with_model`委譲
6. ProviderManagerに追加
7. annotator_config.toml設定追加 (api_model_id指定)

## テスト
- pytest + pytest-xdist, pytest-cov
- PydanticAI: TestModel/FunctionModel使用, models.ALLOW_MODEL_REQUESTS=False
- マーカー: unit, integration, webapi, fast, standard
