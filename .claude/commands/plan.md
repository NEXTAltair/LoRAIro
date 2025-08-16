---
allowed-tools: mcp__serena__get_symbols_overview, mcp__serena__find_symbol, mcp__serena__search_for_pattern, mcp__serena__read_memory, mcp__serena__write_memory, mcp__context7__resolve-library-id, mcp__context7__get-library-docs, cipher_memory_search, cipher_store_reasoning_memory, cipher_extract_entities, cipher_query_graph, Read, Bash, TodoWrite, Task
description: investigateフェーズの結果を基に、LoRAIro プロジェクトの実装戦略と詳細設計を策定します。
---

## 使用方法
```bash
/plan 実装対象の説明
```

## 重要原則

### LoRAIro品質方針
- **コード品質第一**: シンプルさ、可読性、テスタビリティ、保守性を最優先
- **Memory-First**: 過去の設計パターンと知識を活用した効率的プランニング
- **段階的設計**: 小さな単位でのインクリメンタル設計を徹底

### プランニング基本原則
- 関連するコードは全て読むこと
- 全ての処理においてultrathinkでしっかりと考えて作業を行うこと
- 過去の設計知識を必ず確認してから計画策定すること
- LoRAIroの確立されたアーキテクチャパターンに従うこと

## 説明
実装対象: $ARGUMENTS

investigateフェーズで特定された要件と課題を基に、上記実装対象にLoRAIroプロジェクトの包括的な実装計画を策定します。複数のアプローチを検討し、トレードオフを評価した上で最適な解決策を選択します。

## タスクに含まれるべきTODO

### 1. Memory-Based事前分析と要件明確化
1. **Memory-First計画準備**: `cipher_memory_search` で類似設計の過去事例を確認
2. investigateフェーズの結果を確認・分析
3. **設計知識確認**: `mcp__serena__read_memory` でプロジェクト固有の設計状況を確認
4. 問題の具体的な定義と成功基準の設定
5. 制約条件の特定(時間・リソース・互換性)
6. 既存コードベース・アーキテクチャのコンテキスト収集
7. **設計予測**: 過去の設計で発見された問題とリスク要因の事前把握
8. 不明点の明確化(仮定を避け具体的に質問)

### 2. 包括的分析
6. 現状評価(既存機能・コード・設定)
7. ギャップ分析(不足・問題点の特定)
8. 影響分析(影響を受けるコンポーネント特定)
9. リスク評価(潜在的問題の洗い出し)
10. 依存関係マッピング(コンポーネント間の関係)

### 3. 解決策設計
11. 複数アプローチの検討(最低2-3の異なる手法)
12. 各アプローチの長短評価とトレードオフ分析
13. 既存アーキテクチャパターンとの適合性確認
14. スケーラビリティ考慮(長期的な持続可能性)
15. テスト戦略の策定(検証方法の計画)

### 4. LoRAIro固有考慮事項
16. サービス層への影響確認
17. データベーススキーマ変更の必要性評価
18. GUIコンポーネントへの影響
19. 設定管理(config/lorairo.toml)の更新計画
20. AI統合への影響(アノテーションプロバイダー)

### 5. 品質・パフォーマンス計画
21. 型安全性確保(適切な型ヒント)
22. エラーハンドリング戦略
23. ログ記録計画
24. メモリ使用量管理(大画像処理考慮)
25. データベースクエリ効率化
26. AI API呼び出しの最適化(レート制限・キャッシュ)

### 6. 実装計画詳細化
27. タスク分割(管理可能な小単位への分解)
28. 実装順序の決定(依存関係考慮)
29. 必要リソース特定(ツール・ライブラリ・データ)
30. タイムライン見積もり(各フェーズの現実的時間)
31. マイルストーン定義(進捗追跡のチェックポイント)

### 7. テスト・検証計画
32. 単体テスト計画(UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m unit)
33. 統合テスト計画(UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m integration)
34. GUIテスト計画(UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m gui)
35. モック戦略(外部依存関係)
36. テストデータ準備(画像・データセット)

### 8. 配置・移行計画
37. ローカルパッケージ更新の必要性
38. 依存関係変更(新Python パッケージ)
39. 設定移行戦略(ユーザー設定更新)
40. データ移行計画(既存データ変換)
41. ロールバック計画(変更の取り消し方法)

### 9. 知識蓄積・完了処理
42. **設計知識蓄積**: `cipher_store_reasoning_memory` で設計判断と根拠を保存
43. **設計関係記録**: `cipher_query_graph` で設計要素間の依存関係を記録
44. **プロジェクト記録**: `mcp__serena__write_memory` で現在プロジェクト向けの設計結果保存
45. 設計決定の記録とその理由
46. ユーザー検証(明確な選択肢提示・トレードオフ説明)
47. フィードバック収集と承認取得
48. 計画完了をコンソール出力で通知(echo "📋 プランニング完了")
49. implementフェーズへの引き継ぎ事項整理

## 実行内容

### 要件明確化フェーズ

#### Memory-Based設計準備
- **既存設計知識確認**: `cipher_memory_search` で類似設計パターンの過去事例を検索
- **アーキテクチャ分析**: `cipher_extract_entities` で重要な設計要素を特定
- **設計課題予測**: 過去の設計で発見された課題とリスク要因を確認

#### 詳細要件分析
- investigateフェーズ結果の詳細分析
- **🔍 Investigation Agent活用**: 既存実装の詳細調査とアーキテクチャ理解
- **📚 Library Research Agent活用**: 技術選定と設計パターン調査
- **Context7 設計パターン取得**: 関連ライブラリの設計ガイド・ベストプラクティス取得
- 問題定義と成功基準の明確化
- 制約・依存関係の特定

### 解決策設計フェーズ
- **🎯 Solutions Agent活用**: 複数アプローチの生成・評価・比較
  ```
  Use the solutions agent to generate and evaluate implementation approaches:
  - Multiple solution strategy generation
  - Risk-benefit analysis and trade-off evaluation
  - Architecture compatibility assessment
  ```
- アーキテクチャ適合性の評価
- パフォーマンス・セキュリティ考慮

### 実装計画・知識蓄積フェーズ

#### 実装計画策定
- 詳細タスク分割と順序決定
- リスク分析と対策立案
- テスト・検証戦略策定

#### 設計知識の蓄積
- **設計パターン記録**: `cipher_store_reasoning_memory` で設計アプローチと判断根拠を保存
- **技術関係分析**: `cipher_query_graph` で設計要素間の依存関係を記録
- **教訓保存**: 設計中に発見した課題・解決策・ベストプラクティスを長期記憶化
- **プロジェクト記録**: `mcp__serena__write_memory` で現在プロジェクト固有の設計結果を保存

## 必読ファイル
- `tasks/investigations/investigate_{investigation_target}_{YYYYMMDD_HHMMSS}.md` - 前フェーズの結果
- `.claude/commands/plan.md` - プランニングガイドライン(本コマンド文書を一次参照とし、最新手順はここに集約)
- `docs/architecture.md` - アーキテクチャ仕様
- `docs/technical.md` - 技術実装パターン
- `src/lorairo/services/` - 既存サービス実装
- `src/lorairo/database/schema.py` - データベース構造
- `config/lorairo.toml` - 現在の設定

## 出力形式(プランニングテンプレート準拠)
1. **ultrathink設計プロセス**: 設計決定の思考過程
2. **要件・制約整理**: 問題定義・成功基準・制約条件
3. **現状・ギャップ分析**: 既存状態と不足点
4. **複数ソリューション比較**: アプローチ候補とトレードオフ
5. **推奨ソリューション**: 選択理由と根拠
6. **アーキテクチャ設計**: 既存パターンへの統合方針
7. **実装計画**: 詳細ステップ・タスク分割・タイムライン
8. **テスト戦略**: 包括的検証計画
9. **リスク・対策**: 潜在的問題と軽減策
10. **次ステップ**: implementフェーズへの引き継ぎ

## 次のコマンド
計画完了・承認後は `/implement` コマンドで実装を開始します。

## 最適化されたプランニング戦略 (Cipher Aggregator Mode)

### Memory-First + 設計知識活用アプローチ

planコマンドでは以下の最適化戦略を採用:

#### 🧠 Memory-First設計準備 (1-3秒)
```
既存知識の活用:
- cipher_memory_search: 過去の類似設計パターンを検索
- mcp__serena__read_memory: プロジェクト固有の設計進捗を確認
- cipher_extract_entities: 重要な設計要素を特定
```

#### 🚀 高速コード分析 (主要手法)
```
効率的アーキテクチャ分析:
- mcp__serena__get_symbols_overview: 既存コード構造把握
- mcp__serena__find_symbol: 実装対象コンポーネント特定
- mcp__serena__search_for_pattern: アーキテクチャパターン調査
- mcp__serena__write_memory: 設計決定の記録
```

#### 🔄 cipher経由操作 (複合・戦略タスク)
```
複数視点での戦略分析:
- cipher_memory_search: 過去の設計パターンと意思決定の検索
- cipher_store_reasoning_memory: 設計決定と根拠の長期保存
- cipher_extract_entities: 重要な設計要素の特定
- cipher_query_graph: 設計要素間の関係性分析
```

#### 🎯 知識蓄積・記録
```
設計知識の永続化:
- cipher_store_reasoning_memory: 設計判断と根拠の保存
- cipher_query_graph: 設計要素間の関係性分析
- mcp__serena__write_memory: プロジェクト固有の設計結果保存
```

### 2重メモリ戦略

#### Serena Memory (プロジェクト固有・短期)
- **用途**: 現在の設計進捗と一時的な開発メモ
- **保存内容**: 
  - 現在の設計状況と次のステップ
  - 進行中の設計決定
  - 設計中の一時的な課題と解決策
  - 技術選定の評価結果

#### Cipher Memory (設計知識・長期)
- **用途**: 将来参照可能な設計パターン資産
- **保存内容**:
  - 設計アプローチと判断根拠
  - アーキテクチャ設計の意図と背景
  - パフォーマンス・保守性の評価
  - 設計時の課題と解決策
  - ベストプラクティスとアンチパターン
  - 技術選定の基準と結果

### プランニング効率最適化

#### Memory-First原則
1. **過去設計確認**: 類似機能の設計履歴を優先参照
2. **パターン再利用**: 成功した設計パターンの活用
3. **課題予測**: 過去に発見された問題とリスク要因の事前把握

#### 段階的設計戦略
1. **小単位設計**: 段階的な設計決定プロセス
2. **継続的検証**: エージェントによる設計品質確認
3. **知識蓄積**: 設計過程と結果の段階的記録

#### 記録・蓄積戦略
**Serena記録対象**: "今何を設計しているか" "次に何を決定するか"
**Cipher記録対象**: "なぜそう設計したか" "どのような判断をしたか"

### エラーハンドリング・継続戦略
- **Cipher統合タイムアウト**: 段階的設計に分割して継続
- **複雑な設計**: Investigation/Library-Research/Solutionsエージェントで分析
- **設計確認**: 専門エージェントによる設計品質評価
- **設計完了判定**: Serenaメモリによる客観的評価
