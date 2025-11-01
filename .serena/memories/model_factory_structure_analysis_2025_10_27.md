# model_factory.py 構造分析 - 2025-10-27

## ユーザー指示
「機能を分割するリファクタリングが必要だな､それは今度のタスクに回すからメモしておいて」

## 現状

**ファイル**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory.py`
- 行数: 2106行
- カバレッジ: 32% (1005 statements, 687 uncovered)
- 既存テスト: 41テスト（すべてパス）

**主要コンポーネント**:
- Adapter classes: OpenAIAdapter, AnthropicAdapter, GoogleClientAdapter
- Component classes: TransformersComponents, ONNXComponents, TensorFlowComponents, CLIPComponents
- Helper functions: _find_model_entry_by_name, _get_api_key, _process_model_id, _initialize_api_client
- Main class: ModelLoad (モデルロード・キャッシュ管理)
- Classifier class

## 課題

### テスト困難な理由
1. 複雑な関数シグネチャ
2. 外部依存（dotenv, OpenAI, anthropic, genai クライアント）
3. ファイルI/O依存
4. 長い依存チェーン

### Phase 2目標との乖離
- 目標: 60%カバレッジ
- 現在: 32%カバレッジ
- 差分: 28%不足

## 今後のタスク

次回作業時に機能分割を実施する。
詳細は別途計画時に検討。
