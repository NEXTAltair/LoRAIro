# image-annotator-lib 製品要求仕様書（PRD）

**作成日**: 2025-10-22
**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## プロジェクト目標

1. 多様な画像アノテーションタスク（タギング、スコアリング）の再利用可能なPythonライブラリ
2. 異なるアノテーションタイプやモデルに対応する柔軟で拡張可能なアーキテクチャ
3. pydantic-ai活用でWeb APIから構造化された信頼性の高いアノテーションデータ取得
4. ProviderManagerによるプロバイダーレベルのリソース共有でWeb API利用の効率性最大化
5. 他アプリケーション/ワークフローとの容易な統合
6. 高いコード品質、テストカバレッジ、明確なドキュメント
7. 統一されたAPIの提供

## 主要機能

### 統一アノテーションインターフェース
`annotate`関数でローカルモデルとWeb APIモデルを透過的に扱う

### 多様なモデルサポート
**ローカル**: ONNX, Transformers, TensorFlow, CLIP
**Web API**: Google (Gemini), OpenAI (GPT), Anthropic (Claude) - pydantic-ai + AnnotationSchema

### 効率的なリソース管理
- ProviderManager: プロバイダーごとのクライアントインスタンス共有
- PydanticAIProviderFactory: Agent LRUキャッシュ
- ModelLoad: ローカルモデルLRUキャッシュ + CUDA/CPU管理

## 変更履歴

### 2025-06-25: Provider-level管理アーキテクチャ導入
- ProviderManager, PydanticAIProviderFactory, PydanticAIAnnotatorMixin導入
- APIクライアント再利用によるパフォーマンス向上

### 2025-05-10: Web APIアノテータの責務分離
- OpenAIApiAnnotator, AnthropicApiAnnotator個別ファイル分離
- AnnotationSchemaによる型仕様統一

## 品質目標
- テストカバレッジ: 75%以上
- 型安全性: Mypy strict mode準拠
- コード品質: Ruff linter/formatter準拠
- ドキュメント: Google style docstring（日本語）
