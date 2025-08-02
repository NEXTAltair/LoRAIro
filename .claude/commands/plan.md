---
allowed-tools: mcp__serena__get_symbols_overview, mcp__serena__find_symbol, mcp__serena__search_for_pattern, mcp__serena__read_memory, mcp__serena__write_memory, mcp__context7__resolve-library-id, mcp__context7__get-library-docs, Read, Bash, TodoWrite, Task
description: investigateフェーズの結果を基に、LoRAIro プロジェクトの実装戦略と詳細設計を策定します。
---

## 使用方法
```bash
/plan 実装対象の説明
```

## 重要原則
- 関連するコードは全て読むこと
- 全ての処理においてultrathinkでしっかりと考えて作業を行うこと
- LoRAIroの確立されたアーキテクチャパターンに従うこと

## 説明
実装対象: $ARGUMENTS

investigateフェーズで特定された要件と課題を基に、上記実装対象にLoRAIroプロジェクトの包括的な実装計画を策定します。複数のアプローチを検討し、トレードオフを評価した上で最適な解決策を選択します。

## タスクに含まれるべきTODO

### 1. 要件明確化
1. investigateフェーズの結果を確認・分析
2. 問題の具体的な定義と成功基準の設定
3. 制約条件の特定（時間・リソース・互換性）
4. 既存コードベース・アーキテクチャのコンテキスト収集
5. 不明点の明確化（仮定を避け具体的に質問）

### 2. 包括的分析
6. 現状評価（既存機能・コード・設定）
7. ギャップ分析（不足・問題点の特定）
8. 影響分析（影響を受けるコンポーネント特定）
9. リスク評価（潜在的問題の洗い出し）
10. 依存関係マッピング（コンポーネント間の関係）

### 3. 解決策設計
11. 複数アプローチの検討（最低2-3の異なる手法）
12. 各アプローチの長短評価とトレードオフ分析
13. 既存アーキテクチャパターンとの適合性確認
14. スケーラビリティ考慮（長期的な持続可能性）
15. テスト戦略の策定（検証方法の計画）

### 4. LoRAIro固有考慮事項
16. サービス層への影響確認
17. データベーススキーマ変更の必要性評価
18. GUIコンポーネントへの影響
19. 設定管理（config/lorairo.toml）の更新計画
20. AI統合への影響（アノテーションプロバイダー）

### 5. 品質・パフォーマンス計画
21. 型安全性確保（適切な型ヒント）
22. エラーハンドリング戦略
23. ログ記録計画
24. メモリ使用量管理（大画像処理考慮）
25. データベースクエリ効率化
26. AI API呼び出しの最適化（レート制限・キャッシュ）

### 6. 実装計画詳細化
27. タスク分割（管理可能な小単位への分解）
28. 実装順序の決定（依存関係考慮）
29. 必要リソース特定（ツール・ライブラリ・データ）
30. タイムライン見積もり（各フェーズの現実的時間）
31. マイルストーン定義（進捗追跡のチェックポイント）

### 7. テスト・検証計画
32. 単体テスト計画（UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m unit）
33. 統合テスト計画（UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m integration）
34. GUIテスト計画（UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m gui）
35. モック戦略（外部依存関係）
36. テストデータ準備（画像・データセット）

### 8. 配置・移行計画
37. ローカルパッケージ更新の必要性
38. 依存関係変更（新Python パッケージ）
39. 設定移行戦略（ユーザー設定更新）
40. データ移行計画（既存データ変換）
41. ロールバック計画（変更の取り消し方法）

### 9. 文書化・完了処理
42. 設計決定の記録とその理由
43. 計画結果を文書化し、`tasks/plans/plan_{YYYYMMDD_HHMMSS}.md`に保存
44. ユーザー検証（明確な選択肢提示・トレードオフ説明）
45. フィードバック収集と承認取得
46. 計画完了をコンソール出力で通知（echo "📋 プランニング完了"）
47. implementフェーズへの引き継ぎ事項整理

## 実行内容

### 要件明確化フェーズ
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

### 実装計画フェーズ
- 詳細タスク分割と順序決定
- リスク分析と対策立案
- テスト・検証戦略策定

## 必読ファイル
- `tasks/investigations/investigate_{investigation_target}_{YYYYMMDD_HHMMSS}.md` - 前フェーズの結果
- `.cursor/rules/plan.mdc` - プランニングガイドライン
- `docs/architecture.md` - アーキテクチャ仕様
- `docs/technical.md` - 技術実装パターン
- `src/lorairo/services/` - 既存サービス実装
- `src/lorairo/database/schema.py` - データベース構造
- `config/lorairo.toml` - 現在の設定

## 出力形式（プランニングテンプレート準拠）
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
計画完了・承認後は `@implement` コマンドで実装を開始します。
