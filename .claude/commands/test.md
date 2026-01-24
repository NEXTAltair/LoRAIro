---
allowed-tools: mcp__serena__find_symbol, mcp__serena__find_referencing_symbols, mcp__serena__get_symbols_overview, mcp__serena__search_for_pattern, mcp__serena__read_memory, mcp__serena__write_memory, cipher_memory_search, cipher_store_reasoning_memory, cipher_extract_entities, cipher_query_graph, Read, Edit, Write, Bash, TodoWrite, Task
description: 実装コードのテスト・検証を実行します。クイックチェック（Ruff/mypy/pytest）から包括的テストまで対応。

---
# テスト・検証フェーズ

## 使用方法

```bash
/test              # クイック品質チェック（Ruff/mypy/pytest）
/test 対象の説明   # 包括的テスト実行
```

**例:**
- `/test` - Ruff/mypy/pytest のクイックチェックのみ
- `/test src/lorairo/services/` - 指定パスの包括的テスト
- `/test 新しいタグ管理機能` - 機能全体の包括的テスト

## クイック品質チェック（引数なしの場合）

引数なしで `/test` を実行した場合、以下のクイックチェックのみを実行します：

### Step 1: Ruff Lint検証
```bash
echo "=== Ruff Lint Check ==="
uv run ruff check src/ tests/ --output-format=grouped
```
**期待結果**: エラー0件

### Step 2: mypy 型チェック
```bash
echo "=== mypy Type Check ==="
uv run mypy -p lorairo --pretty
```
**期待結果**: エラー0件

### Step 3: pytest テスト実行
```bash
echo "=== pytest Test Execution ==="
uv run pytest --cov=src --cov-report=term-missing -v
```
**期待結果**: 全テストパス、カバレッジ75%以上

### 出力形式（クイックチェック）
```markdown
# Quick Verification Report

| Check | Status | Details |
|-------|--------|---------|
| Ruff  | ✅/❌ | X errors |
| mypy  | ✅/❌ | X errors |
| pytest | ✅/❌ | X passed, Y failed |
| Coverage | ✅/❌ | XX.X% (target: 75%) |

## Overall Status
✅ All checks passed - Ready for commit
❌ Checks failed - See details above
```

**エラー時**: `/build-fix` で修正案を取得

---

## 包括的テスト（引数ありの場合）

以下は引数を指定した場合の包括的テスト実行内容です。

## 重要原則

### LoRAIro品質方針
- **コード品質第一**: シンプルさ、可読性、テスタビリティ、保守性を最優先
- **Memory-First**: 過去のテスト知識とパターンを活用した効率的テスト実行
- **段階的検証**: 小さな単位でのインクリメンタルテストを徹底

### テスト基本原則
- 関連するコードは全て読むこと use serena
- 全ての処理において ultrathink でしっかりと考えて作業を行うこと
- 過去のテスト経験を必ず確認してからテスト開始すること
- `.cursor/rules/test_rules/testing-rules.mdc`のテスト方針に完全準拠すること
- 75%以上のテストカバレッジを維持すること

## 説明

テスト対象: $ARGUMENTS

implement フェーズで実装された上記機能について、ユニット・統合・BDD(E2E)テストを包括的に実行し、品質とユーザー要件の充足を検証します。異常系テストも含めた堅牢性確認を行います。

## タスクに含まれるべき TODO

### 1. Memory-First事前分析・テスト準備

過去のテストパターンと現在のプロジェクト状況を確認：
- 詳細なMemory-Firstワークフローは **mcp-memory-first-development** Skill参照
- 高速Memory操作は **mcp-serena-fast-ops** Skill参照
- 複雑な分析は **mcp-cipher-complex-analysis** Skill参照

テスト準備タスク:
1. implement フェーズの実装結果確認
2. 既存テストスイートの実行と基線確認
3. 新規実装部分のテスト対象特定
4. テストデータ・リソース準備

### 2. ユニットテスト実行・拡充(tests/unit/)

6. 単一クラス・関数の振る舞いテスト実行
7. 新規実装コンポーネントのユニットテスト作成
8. 外部依存関係の最小限モック化
9. 境界値・エッジケーステスト実装
10. `uv run pytest -m unit` による単体テスト全実行

### 3. 統合テスト実行・拡充(tests/integration/)

11. LoRAIro 内部モジュール間連携テスト実行
12. サービス層統合テスト実装
13. データベース操作統合テスト実行
14. AI 統合(local packages)インターフェーステスト実行(Mockを使用)
15. `uv run pytest -m integration` による統合テスト全実行

### 4. GUI テスト実行・拡充(tests/gui/)

16. PySide6 コンポーネントテスト実行
17. ユーザーインタラクションシナリオテスト実装
18. Signal/Slot 連携テスト実行
19. 非同期処理(QThread)テスト実行
20. `uv run pytest -m gui` による GUI テスト全実行(ヘッドレス環境対応)

### 5. BDD(E2E)テスト実行・拡充(tests/bdd/)

21. 実際のユーザーシナリオ完全実行テスト
22. Feature/Scenario/Given-When-Then パターン実装
23. 実際のAI API(OpenAI、Claude、Gemini等)を使用した完全統合テスト
24. 実際のMLモデル(CLIP、DeepDanbooru等)を使用したアノテーションテスト
25. データ永続化・復旧シナリオテスト(実際の外部依存関係含む)
26. AI アノテーション完全ワークフローテスト(実コスト発生あり)

### 6. 異常系・エラーハンドリングテスト

27. 主要正常系パス確認後の異常系計画
28. エラーハンドリング・不正入力テスト実装
29. ファイルシステムエラーシナリオテスト
30. AI API エラー・タイムアウトシナリオテスト
31. データベース接続・整合性エラーテスト

### 7. パフォーマンス・負荷テスト

32. バッチ処理パフォーマンステスト(1000 画像/5 分目標)
33. メモリ使用量監視テスト
34. 大容量データセット処理テスト
35. 並行処理・リソース競合テスト
36. AI API レート制限対応テスト

### 8. 品質指標・カバレッジ確認

37. `uv run pytest --cov=src --cov-report=html` によるカバレッジ測定
38. テストカバレッジ >75% 確認・必要時追加テスト実装
39. `uv run ruff check` による最終コード品質チェック
40. `uv run mypy src/` による型安全性最終確認
41. コード複雑度・可読性チェック

### 9. 回帰テスト・互換性確認

42. 既存機能への影響確認(回帰テスト)
43. 設定ファイル互換性テスト
44. データベースマイグレーション前後整合性テスト
45. 異なる AI プロバイダー間互換性テスト
46. クロスプラットフォーム動作確認(Linux/Windows)

### 10. ユーザー受け入れテスト計画

47. 実際のユーザーワークフロー検証
48. UI/UX 使いやすさ確認
49. エラーメッセージ・ログの分かりやすさ確認
50. ドキュメント・ヘルプとの整合性確認
51. パフォーマンス体感確認

### 11. セキュリティ・安定性テスト

52. API キー・機密情報漏洩防止テスト
53. ファイルアクセス権限・パス検証テスト
54. 入力値検証・インジェクション対策テスト
55. リソース枯渇・メモリリークテスト
56. 長時間稼働安定性テスト

### 12. 知識蓄積・完了処理

テスト知識を長期記憶として保存（**mcp-memory-first-development** Skill参照）

完了処理タスク:
57. テスト結果の包括的分析・レポート作成
58. 発見された問題・改善点の文書化
59. カバレッジレポートの保存(@coverage.xml)
60. テスト完了をコンソール出力で通知(echo "✅ テスト検証完了")
61. 次ステップ(修正・改善・リリース)への推奨事項提示

## 実行内容

### テスト準備フェーズ

#### Memory-Firstテスト準備
過去のテスト知識を確認（**mcp-memory-first-development** Skill参照）

#### 詳細テスト分析
- **🔍 Investigation Agent活用**: テスト対象コードの詳細分析
  ```
  Use the investigation agent for test preparation:
  - Symbol-level test target identification
  - Reference tracking for integration test planning
  - Code complexity assessment for test strategy
  ```
- 実装結果確認と基線設定
- テスト環境・データ準備
- テスト計画詳細化

### 包括的テスト実行フェーズ

- **🔧 Code Formatter Agent活用**: テストコード品質管理
  ```
  Use the code-formatter agent for test code quality:
  - Test code formatting and linting
  - Test structure optimization
  - Code quality verification
  ```
- 段階的テスト実行(Unit → Integration → GUI → BDD)
- 異常系・パフォーマンステスト
- 品質指標・カバレッジ確認

### 検証・分析・知識蓄積フェーズ

#### テスト結果検証
- テスト結果総合分析
- 問題・改善点特定
- 受け入れ基準適合確認

#### テスト知識の蓄積
テスト判断と教訓を長期記憶として保存（**mcp-memory-first-development** Skill参照）

## 必読ファイル

- **Serena Memory**: `mcp__serena__read_memory` でプロジェクト固有の実装結果確認
- **Cipher Memory**: `cipher_memory_search` で類似実装のテスト履歴参照- `.cursor/rules/test_rules/testing-rules.mdc` - テスト方針・基準
- `pyproject.toml` - テスト設定・カバレッジ設定
- `tests/` - 既存テスト構造・パターン
- `tests/resources/` - テストリソース・データ
- `tests/conftest.py` - テスト共通設定・フィクスチャ

## テスト実行チェックリスト

### テスト開始前

- [ ] 実装完了・機能動作確認
- [ ] テスト環境セットアップ確認
- [ ] 既存テストスイート正常実行確認
- [ ] テストデータ・リソース準備確認
- [ ] テスト計画・対象範囲確認

### ユニットテスト

- [ ] `uv run pytest -m unit` 実行・全パス確認
- [ ] 新規コンポーネントテスト網羅確認
- [ ] モック戦略適切性確認
- [ ] 境界値・エッジケース網羅確認
- [ ] テストカバレッジ貢献確認

### 統合テスト

- [ ] `uv run pytest -m integration` 実行・全パス確認
- [ ] モジュール間連携正常性確認
- [ ] データベース操作整合性確認
- [ ] AI 統合インターフェース正常性確認(Mock使用)
- [ ] サービス層統合確認

### GUI テスト

- [ ] `uv run pytest -m gui` 実行・全パス確認(ヘッドレス)
- [ ] ユーザーインタラクション正常性確認
- [ ] 非同期処理・応答性確認
- [ ] Signal/Slot 連携確認
- [ ] エラー表示・ハンドリング確認

### 品質・カバレッジ確認

- [ ] `uv run pytest --cov=src --cov-report=html` 実行
- [ ] テストカバレッジ >75% 確認
- [ ] `uv run ruff check` クリア確認
- [ ] `uv run mypy src/` クリア確認
- [ ] パフォーマンス基準クリア確認

## 出力形式

1. **ultrathink テストプロセス**: テスト戦略と実行思考過程
2. **テスト実行結果サマリー**: 各テストレベルの実行結果
3. **カバレッジ分析**: テストカバレッジ詳細・不足箇所
4. **品質指標**: コード品質・型安全性・パフォーマンス評価
5. **異常系テスト結果**: エラーハンドリング・堅牢性評価
6. **回帰テスト結果**: 既存機能への影響確認結果
7. **パフォーマンステスト結果**: 処理速度・リソース使用量評価
8. **発見された問題**: バグ・改善点・リスク
9. **受け入れ基準適合状況**: ユーザー要件充足度評価
10. **推奨事項**: 修正・改善・次ステップへの提言

## 次のコマンド

テスト完了後、問題があれば `/investigate` で原因調査、または改善実装のため `/planning` で計画策定を行います。

## Memory管理とSkills

このコマンドでは以下のSkillsを活用してメモリー管理を効率化します：
- **mcp-memory-first-development**: Memory-First開発ワークフロー
- **mcp-serena-fast-ops**: 高速テスト分析とMemory操作
- **mcp-cipher-complex-analysis**: テスト知識の長期記憶化

詳細な使い方は各SkillのSKILL.mdを参照してください。
