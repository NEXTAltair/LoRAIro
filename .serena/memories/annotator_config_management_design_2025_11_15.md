# アノテーター設定管理の設計分析と実装決定

**作成日**: 2025-11-15
**ブランチ**: feature/dynamic-annotator-config (worktree: /workspaces/LoRAIro-config-update)
**サブモジュールブランチ**: feature/remove-legacy-api-annotators

## 背景

PydanticAI統合完了後、97件の古い`*ApiAnnotator`クラス参照が`annotator_config.toml`に残存していた。
レガシーコード整理の一環として設定管理の最適化を検討。

## 検討した5つのアプローチ

### 1. 現状維持（手動TOML管理）
- **概要**: 既存の手動TOML編集を継続
- **メリット**: シンプル、既存ワークフロー維持
- **デメリット**: 手動更新の手間、ミスの可能性
- **評価**: 保守コストが高い

### 2. 完全自動検出（API定期取得）
- **概要**: 起動時に毎回APIから最新モデルリストを取得
- **メリット**: 常に最新情報
- **デメリット**: 起動が重い、API依存
- **評価**: パフォーマンス問題あり（却下理由）

### 3. ハイブリッド自動検出（API + ローカル手動）
- **概要**: APIモデルは自動検出、ローカルモデルは手動管理
- **メリット**: バランスが良い
- **デメリット**: 2系統管理の複雑性
- **評価**: 複雑性とメリットが不均衡

### 4. 全モデル明示的管理（deprecated_on追加）★採用
- **概要**: 
  - 全モデルを`annotator_config.toml`で明示管理
  - APIから取得したモデル情報を`available_api_models.toml`に保存
  - `deprecated_on`フィールドで廃止モデルを追跡
  - `last_seen`フィールドで最終確認日時を記録
- **メリット**: 
  - トレーサビリティ高い
  - 明示的な管理で予測可能
  - テスタビリティ高い
- **デメリット**: 初期設定コストやや高
- **評価**: 長期保守性が最優先のため採用

### 5. プラグインシステム（動的登録）
- **概要**: モデルクラスを動的に登録する拡張可能システム
- **メリット**: 拡張性最高
- **デメリット**: 過剰設計、現時点で不要
- **評価**: YAGNI原則により却下

## 採用アプローチ詳細（アプローチ4）

### 実装済み機能

1. **API Model Discovery** (`core/api_model_discovery.py`)
   - `discover_available_vision_models(force_refresh: bool)` 関数
   - OpenRouter APIから最新モデル情報取得
   - Vision対応・構造化出力・ツール利用の3条件でフィルタリング
   - 取得結果を`available_api_models.toml`に保存

2. **TOML更新ロジック** (`_update_toml_with_api_results`)
   - 既存モデル: `last_seen`更新、`deprecated_on`削除
   - 新規モデル: 追加登録
   - 廃止モデル: `deprecated_on`に現在時刻設定

3. **設定ファイル構造**
   - `annotator_config.toml`: 全モデル定義（手動 + 自動生成）
   - `available_api_models.toml`: API取得モデル情報のキャッシュ
   - `user_config.toml`: ユーザー設定オーバーライド

### 選択理由

ユーザー指示: "全モデルを明示的に管理にした理由は起動のたびに使用可能なモデルを取得する動作が重いからって理由だったと思う。次に起動時は保存したデータからモデルが使用不能になってないかチェックして使用不能ならモデルの情報を更新するって動作だったと思う。"

- パフォーマンス: 起動時の重い処理を回避
- トレーサビリティ: `deprecated_on`で廃止履歴を保持
- テスタビリティ: 明示的な設定で単体テスト容易

## レガシーコード削除実施内容

### 完全削除を選択した理由

ユーザー質問: "古い*ApiAnnotatorクラスは全部pydanticaiで対応できるところは対応させて消せるなら消したほうがいいよね?"

**選択肢:**
1. 段階的廃止（deprecation warning）
2. 完全削除 ★選択

**選択理由:** PydanticAI統合で全機能をカバー済み、レガシーコード保持の理由なし

### 削除実施内容

**ソースコード削除（4ファイル、1810行）:**
1. `model_class/annotator_webapi/anthropic_api.py` - AnthropicApiAnnotator
2. `model_class/annotator_webapi/google_api.py` - GoogleApiAnnotator
3. `model_class/annotator_webapi/openai_api_chat.py` - OpenRouterApiAnnotator
4. `model_class/annotator_webapi/openai_api_response.py` - OpenAIApiAnnotator

**テストファイル削除（3ファイル、771+行）:**
1. `tests/integration/test_anthropic_api_annotator_integration.py`
2. `tests/integration/test_google_api_annotator_integration.py`
3. `tests/unit/fast/test_api.py`

**合計削除:** 2581+行

### 設定ファイル更新

**サブモジュール設定:**
- `local_packages/image-annotator-lib/config/annotator_config.toml`: 97件 → 101件すべて`PydanticAIWebAPIAnnotator`
- `prototypes/pydanticai_integration/config/annotator_config.toml`: 同様に更新

**メインリポジトリ設定:**
- `/workspaces/LoRAIro/config/annotator_config.toml`: 削除 → テンプレートから自動再生成
- 再生成後: 95件すべて`PydanticAIWebAPIAnnotator`

**sed実行コマンド:**
```bash
sed -i 's/class = "OpenAIApiAnnotator"/class = "PydanticAIWebAPIAnnotator"/g'
sed -i 's/class = "AnthropicApiAnnotator"/class = "PydanticAIWebAPIAnnotator"/g'
sed -i 's/class = "GoogleApiAnnotator"/class = "PydanticAIWebAPIAnnotator"/g'
sed -i 's/class = "OpenRouterApiAnnotator"/class = "PydanticAIWebAPIAnnotator"/g'
```

### 検証結果

**PydanticAI統合テスト:**
- 33件すべてパス ✅
- テストパス: `local_packages/image-annotator-lib/tests/unit/core/test_pydantic_ai_factory.py`

**設定自動生成:**
- メインリポジトリconfig削除後、`config_registry.load()`で自動再生成成功
- テンプレートから正しくコピーされ、全モデルが`PydanticAIWebAPIAnnotator`

## コミット履歴

**サブモジュール（feature/remove-legacy-api-annotators）:**
1. `4fd0659` - レガシークラス削除（ソース4ファイル + テスト2ファイル + 設定更新）
2. `d85cebd` - レガシーテスト削除（test_api.py）

**メインリポジトリ:**
- config削除 + 自動再生成（コミット未作成）

## 今後の方針

### API Model Discovery運用

1. 初回起動: `force_refresh=True`で全モデル取得
2. 通常起動: `force_refresh=False`でローカルキャッシュ使用
3. 手動更新: 必要時に`force_refresh=True`で再取得

### モデル廃止時の対応

1. API応答にモデルが存在しない → `deprecated_on`に現在時刻設定
2. `last_seen`は更新しない（最後に確認できた日時を保持）
3. 廃止モデルは削除せず履歴として保持

### ローカルモデル管理

- 手動で`annotator_config.toml`に追記
- `class`フィールドで適切なアノテータークラスを指定
- APIモデルとの混在管理

## 教訓

1. **設計検討の記録**: 複数アプローチを検討した場合、必ずメモリに記録
2. **完全削除の判断**: 代替実装が完全に機能している場合、レガシーコードは即削除
3. **自動再生成の活用**: テンプレート機構があれば設定ファイル削除 → 再生成が有効
4. **段階的検証**: サブモジュール更新 → メインリポジトリ更新の順で安全に実施

---

**作成理由**: Configuration Management Designの議論内容が記録されておらず、今後の参照に支障が出るため作成
**関連memory**: `image_annotator_lib_completion_master_plan`, `current-project-status`
