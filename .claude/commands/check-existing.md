---
allowed-tools: mcp__serena__search_for_pattern, mcp__serena__find_file, mcp__serena__list_dir, mcp__serena__read_memory, mcp__serena__write_memory, mcp__context7__resolve-library-id, mcp__context7__get-library-docs, cipher_memory_search, cipher_store_reasoning_memory, cipher_extract_entities, cipher_query_graph, Read, Bash, TodoWrite, WebSearch, WebFetch, Task
description: 実装予定機能に対する既存ライブラリ・ツールの徹底調査コマンド(要件明確化ヒアリング付き)
---
# Check Existing Solutions

実装予定機能に対する既存ライブラリ・ツールの徹底調査コマンド(要件明確化ヒアリング付き)

## 使用方法
```
/check-existing $ARGUMENTS
```

**$ARGUMENTS**: 実装予定の機能・要件を記述(曖昧でも可)
- 例: `画像処理の何か`、`データベース関連`、`GUI widget`、`AI annotation tool`

## 実行手順

### Phase 1: Memory-Based事前調査

**過去の類似調査結果を活用した効率的調査開始:**

#### 1.1 既存知識の確認
- **Cipher記憶検索**: `cipher_memory_search` で類似機能の過去調査結果を確認
- **Serena記憶参照**: `mcp__serena__read_memory` でプロジェクト固有の要件を確認
- **関連エンティティ**: `cipher_extract_entities` で重要な技術要素を特定

#### 1.2 調査戦略の決定
- 既存知識を基に効率的な調査計画を立案
- 重複調査を回避し、知識不足領域を特定
- Web検索キーワードの事前準備

### Phase 2: 戦略的要件明確化ヒアリング

**積極的質問による実装指向の要件定義:**

#### 2.1 実装意図の深掘り
- **Q**: 「この機能で解決したい具体的な問題は何ですか?」
- **Q**: 「現在どのような方法で対応していて、何が不満ですか?」
- **Q**: 「成功した場合、どのような改善効果を期待していますか?」

#### 2.2 技術的詳細の特定
- **Q**: 「処理対象のデータサイズ・量はどの程度ですか?」
- **Q**: 「リアルタイム処理ですか?バッチ処理ですか?」
- **Q**: 「LoRAIroのどのワークフローに組み込む予定ですか?」
- **Q**: 「ユーザーの操作は?自動実行?GUI操作?設定ファイル?」

#### 2.3 制約と優先度の明確化
- **Q**: 「絶対に外せない機能は何ですか?(Must-have)」
- **Q**: 「あると嬉しい機能は何ですか?(Nice-to-have)」
- **Q**: 「パフォーマンス要件はありますか?(処理速度、メモリ使用量、精度等)」
- **Q**: 「複雑さを避けて、シンプルで理解しやすい実装を優先しますか?」

#### 2.4 Web検索キーワードの特定
- **Q**: 「この機能を英語で説明するとどうなりますか?」
- **Q**: 「業界固有の専門用語はありますか?」
- **Q**: 「類似ツールで知っているものはありますか?」
- **Q**: 「PyPIやGitHubで検索するとしたら、どんなキーワードを使いますか?」

### Phase 3: 要件定義書生成

ヒアリング結果を以下の形式で整理:

```markdown
## 明確化された要件定義

### 核心機能
- **メイン処理**: [具体的な処理内容]
- **入力形式**: [データ型、ファイル形式、UI操作等]
- **出力形式**: [期待する結果の形式]

### 技術的要件
- **統合箇所**: [LoRAIroのどの部分]
- **パフォーマンス**: [速度・メモリ・精度要件]
- **依存関係**: [既存ライブラリとの関係]

### 機能的要件
- **Must-have**: [絶対に必要な機能]
- **Nice-to-have**: [あると良い機能]
- **制約・除外**: [やらない/できないこと]

### 検索キーワード候補
- **メインキーワード**: [核心機能を表すキーワード]
- **技術キーワード**: [実装技術・フレームワーク関連]
- **ドメインキーワード**: [業界・分野特有の用語]
```

### Phase 4: Web検索中心の包括的調査

**戦略的Web検索とCipher統合による徹底的な既存解決策発見:**

#### 4.1 段階的Web検索戦略
##### 第1段階: 基本キーワード検索
- **PyPI検索**: `WebSearch` で "python [機能名] library PyPI"
- **GitHub Topics**: `WebSearch` で "[機能名] python topic:python"
- **標準ライブラリ**: `WebSearch` で "python standard library [機能名]"

##### 第2段階: 詳細・専門検索
- **実装例検索**: `WebSearch` で "[機能名] python implementation example"
- **比較記事**: `WebSearch` で "best python [機能名] libraries comparison"
- **Stack Overflow**: `WebSearch` で "[機能名] python site:stackoverflow.com"

##### 第3段階: 最新情報・トレンド
- **2024-2025動向**: `WebSearch` で "[機能名] python 2024 2025 latest"
- **GitHubトレンド**: `WebSearch` で "trending [機能名] python repositories"
- **技術ブログ**: `WebSearch` で "[機能名] python tutorial blog 2024"

#### 4.2 Cipher統合による多角的分析
- **包括的技術調査**: Cipher経由でWebSearch + context7 + perplexity-askを統合活用
- **リアルタイム情報**: 最新のライブラリ動向と技術トレンドの把握
- **クロス検証**: 複数ソースからの情報を統合して信頼性確認

#### 4.3 専門エージェント活用
- **🔍 Investigation Agent**: 既存コードベース内の類似機能調査
- **📚 Library Research Agent**: Context7活用による技術ドキュメント詳細調査
- **🎯 Solutions Agent**: 発見された選択肢の比較評価・実装可能性分析

#### 4.4 LoRAIro統合性調査
- **依存関係確認**: `Bash uv list` で既存ライブラリとの互換性確認
- **local_packages機能**: genai-tag-db-tools、image-annotator-libでの代替可能性
- **アーキテクチャ適合**: `mcp__serena__get_symbols_overview` で統合箇所の分析

### Phase 5: 適合性評価・知識蓄積・推奨事項

**調査結果の評価・記録・推奨事項決定:**

#### 5.1 知識蓄積戦略
- **調査過程記録**: `cipher_store_reasoning_memory` で評価プロセスと判断根拠を保存
- **ライブラリ評価**: 発見された各ライブラリの特性・制約・適用可能性を記録
- **技術関係分析**: `cipher_query_graph` でライブラリ間の依存関係・競合関係を分析
- **プロジェクト結論**: `mcp__serena__write_memory` で当該プロジェクト向けの最終結論を保存

#### 5.2 結果レポート生成

```markdown
# 既存解決策調査結果 ({機能名}_{YYYYMMDD_HHMMSS}.md)

## ヒアリング結果
[Phase 2で生成された要件定義書]

## Web検索・調査プロセス
- **検索キーワード**: [使用したキーワード一覧]
- **調査ソース**: [PyPI/GitHub/Stack Overflow/技術ブログ等]
- **発見ライブラリ数**: [調査した候補数]

## 発見された既存解決策

### 🎯 完全代替可能(要件適合度90%以上)
- **ライブラリ名**: [具体的な適合理由]
- **統合方法**: [LoRAIroへの組み込み手順]
- **推奨度**: ⭐⭐⭐⭐⭐

### 🔧 組み合わせ利用(要件適合度60-89%)
- **主ライブラリ**: [メイン機能提供]
- **補完方法**: [不足機能の補完策]
- **実装工数**: [予想される作業量]

### 📚 参考実装(要件適合度30-59%)
- **参考価値**: [学習・応用可能な要素]
- **独自実装**: [必要な追加開発範囲]

## 最終推奨事項

### ✅ 採用推奨解決策
- **選択理由**: [客観的評価根拠]
- **統合手順**: [具体的な導入ステップ]
- **注意点**: [制限事項・考慮点]

### ⚠️ 独自実装必要性
- **理由**: [既存解決策の限界・不足]
- **最小実装範囲**: [本当に必要な独自開発部分]
- **既存活用**: [部分的に使える機能・ライブラリ]

## 知識蓄積完了
- **Cipher記憶**: 長期参照用のライブラリ評価知識として保存済み
- **Serena記憶**: プロジェクト固有の要件・結論として保存済み
```

## 実行例

```
User: @check-existing 画像処理の何か
AI: 画像処理について詳しく教えてください。具体的にどのような処理を実現したいですか?
    - 画像の変換・フィルタリング?
    - メタデータ抽出・分析?
    - AI による画像認識・分類?
    - ファイル形式変換?
    - その他?

User: AIで画像の内容を解析して説明文を生成したい
AI: AI画像解析について詳しく確認させてください...
    [ヒアリング継続 → 要件明確化 → 調査実行]
```

このアプローチにより、曖昧な要求から始まっても最終的に的確な既存解決策を発見できます。

## 最適化されたMCP調査戦略 (Cipher Aggregator Mode)

### Memory-First + Web検索中心アプローチ

check-existingコマンドでは以下の最適化戦略を採用:

#### 🧠 Memory-First事前調査 (1-3秒)
```
既存知識の活用:
- cipher_memory_search: 過去の類似機能調査結果を検索
- mcp__serena__read_memory: プロジェクト固有の要件・制約確認
- cipher_extract_entities: 重要な技術要素の特定
```

#### 🔍 Web検索中心調査 (主要手法)
```
段階的Web情報収集:
- WebSearch: PyPI、GitHub、Stack Overflow、技術ブログの体系的調査
- WebFetch: 特定ページの詳細情報取得
- Cipher統合: WebSearch + context7 + perplexity-askの組み合わせ
```

#### 🚀 補完的直接操作 (詳細分析)
```
ローカル分析・技術調査:
- mcp__serena__search_for_pattern: コードベース内類似機能
- mcp__context7__resolve-library-id: 技術ドキュメント取得
- mcp__context7__get-library-docs: API仕様確認
```

#### 🎯 長期記憶蓄積
```
調査結果の永続化:
- cipher_store_reasoning_memory: 調査過程と評価結果の保存
- cipher_query_graph: 技術間の関係性分析
- mcp__serena__write_memory: プロジェクト固有の結論保存
```

### 調査効率最適化

#### Memory-First原則
1. **過去調査確認**: 類似機能の調査履歴を優先参照
2. **重複回避**: 既存知識で充足する部分は再調査しない
3. **知識不足特定**: 追加調査が必要な領域を明確化

#### Web検索戦略
1. **段階的深掘り**: 基本→詳細→最新トレンドの順で調査
2. **複数ソース**: PyPI + GitHub + Stack Overflow + 技術ブログ
3. **クロス検証**: 複数の情報源で信頼性確認

#### 記録・蓄積戦略
**Serena Memory**: 現在の調査進捗と要件
**Cipher Memory**: 将来参照可能なライブラリ評価知識

### エラーハンドリング・フォールバック
- **Web検索失敗**: 直接context7操作で技術ドキュメント取得
- **Cipher統合タイムアウト**: 段階分割で個別調査実行
- **情報不足**: 専門エージェント(Task)による詳細分析
