---
allowed-tools: mcp__serena__find_symbol, mcp__serena__find_referencing_symbols, mcp__serena__replace_symbol_body, mcp__serena__insert_after_symbol, mcp__serena__insert_before_symbol, mcp__serena__replace_regex, mcp__serena__get_symbols_overview, mcp__serena__think_about_task_adherence, mcp__serena__think_about_whether_you_are_done, mcp__serena__write_memory, Read, Edit, MultiEdit, Write, Bash, TodoWrite, Task
description: plan フェーズで策定された実装計画に基づき、LoRAIro プロジェクトの実際のコード実装を行います。
---

# 実装・開発フェーズ

## 使用方法

```bash
/implement $ARGUMENTS
```

## 重要原則

- 関連するコードは全て読むこと
- 全ての処理において ultrathink でしっかりと考えて作業を行うこと
- インクリメンタル開発（小さな単位での継続的実装）を徹底すること

## 説明

実装対象: $ARGUMENTS

plan フェーズで承認された設計に基づき、上記実装対象に LoRAIro の確立されたアーキテクチャパターンに従って高品質なコードを実装します。テスト駆動開発とコード品質維持を重視した段階的実装を行います。

## タスクに含まれるべき TODO

### 1. 実装前チェックリスト

1. plan フェーズの実装計画を詳細確認
2. 要件・設計の完全理解確認
3. 開発環境セットアップ確認（`uv sync --dev`）
4. テスト戦略の理解と準備
5. 既存アーキテクチャパターンの特定

### 2. 実装準備

6. `feature/implement-<topic>` ブランチ作成
7. 実装対象コンポーネントの既存コード詳細分析
8. 依存関係とインターフェースの確認
9. 実装順序の最終確認（依存関係順）
10. 初期テストケース準備

### 3. コード品質基準遵守

11. 全関数に型ヒント（Type Hints）実装
12. 包括的例外処理（Exception Handling）実装
13. 適切な Loguru ログ記録実装
14. コメント追加（なぜを説明、何をではなく）
15. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff format` による一貫したフォーマット

### 4. LoRAIro 実装パターン適用

#### サービス層実装（src/lorairo/services/）

16. 依存性注入パターンでサービス実装
17. ConfigurationService と DatabaseManager の適切な利用
18. BaseWorker パターンの継承と活用
19. エラーハンドリングとログ記録の統一

#### データベース操作実装（src/lorairo/database/）

20. リポジトリパターンでデータアクセス実装
21. スキーマ変更必要時の Alembic マイグレーション作成
22. データ整合性とトランザクション管理
23. 効率的クエリパターンの実装

#### AI 統合実装（src/lorairo/annotations/）

24. image-annotator-lib の適切な統合
25. genai-tag-db-tools の活用実装
26. PHashAnnotationResults の正しい処理
27. AI プロバイダーエラーハンドリング

#### GUI 実装（src/lorairo/gui/）

28. PySide6 パターンに従ったウィジェット実装
29. Qt Designer ファイル更新（必要時）
30. Signal/Slot による適切なコンポーネント間通信
31. 非同期処理（QThread）による UI 応答性確保

### 5. テスト駆動開発

32. 実装と並行した単体テスト作成（UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m unit）
33. コンポーネント間統合テスト実装（UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m integration）
34. GUI コンポーネントテスト実装（UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m gui）
35. テストカバレッジ >75% 維持
36. モック戦略による外部依存関係分離

### 6. 設定・環境管理

37. config/lorairo.toml への新設定追加（必要時）
38. ConfigurationService との統合
39. 下位互換性確保
40. 適切なデフォルト値設定

### 7. 品質検証

41. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff check` によるリンティングクリア
42. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run mypy src/` による型チェッククリア
43. 全テストスイートの実行・パス確認
44. 手動機能テストの実行
45. パフォーマンス影響確認

### 8. 非同期・並行処理

46. 長時間処理の QThread 実装
47. プログレス通知とキャンセル機能
48. UI ブロッキング回避
49. 適切なエラー伝播とハンドリング

### 9. ドキュメント・完了処理

50. 実装完了コードの自己レビュー
51. 関連ドキュメント更新
52. 実装結果を文書化し、`tasks/implementations/implement_{YYYYMMDD_HHMMSS}.md`に保存
53. 小さな原子的コミット（明確なコミットメッセージ）
54. 実装完了をコンソール出力で通知（echo "⚙️ 実装完了"）
55. test フェーズへの引き継ぎ事項整理

## 実行内容

### 実装準備フェーズ

- plan フェーズ結果の詳細分析
- **🔍 Investigation Agent活用**: 実装対象の既存コード詳細調査
  ```
  Use the investigation agent for detailed code analysis:
  - Symbol-level implementation pattern analysis
  - Reference tracking for integration points
  - Architecture consistency verification
  ```
- **📚 Library Research Agent活用**: 実装時の技術情報取得
- **Context7 実装ガイド取得**: 実装対象ライブラリの詳細ドキュメント・パターン取得
- 既存コードパターンの理解
- 実装環境の確認・準備

### コード実装フェーズ

- **🔧 Code Formatter Agent活用**: コード品質管理
  ```
  Use the code-formatter agent for code quality maintenance:
  - Automatic Ruff formatting and linting
  - Symbol-level code replacement and optimization
  - Code structure improvement
  ```
- インクリメンタル開発による段階的実装
- テスト駆動開発（TDD）の実践
- 継続的品質チェック

### 検証・統合フェーズ

- 包括的テスト実行
- 品質基準クリア確認
- 機能統合と動作確認

## 必読ファイル

- `tasks/plans/plan_{plan_purpose}_{YYYYMMDD_HHMMSS}.md` - 実装計画詳細
- `.claude/commands/implement.md` - 実装ガイドライン（本コマンド文書を一次参照とし、最新手順はここに集約）
- `src/lorairo/services/` - 既存サービス実装パターン
- `src/lorairo/database/schema.py` - データベーススキーマ
- `src/lorairo/gui/` - GUI 実装パターン
- `config/lorairo.toml` - 設定ファイル構造
- `tests/` - 既存テストパターン

## 実装チェックリスト

### 実装開始前

- [ ] 要件完全理解確認
- [ ] 既存コードパターン確認
- [ ] 実装アプローチ計画確認
- [ ] 開発環境セットアップ確認
- [ ] テスト戦略特定確認

### 実装中

- [ ] インクリメンタル開発実践
- [ ] テストと並行実装
- [ ] 適切な型ヒント使用
- [ ] 包括的エラーハンドリング実装
- [ ] 適切なログ記録追加
- [ ] コードスタイルガイドライン遵守
- [ ] 必要に応じたドキュメント更新

### 品質チェック

- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff format` 実行・フォーマット確認
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff check` 実行・問題修正
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run mypy src/` 実行・型エラー解決
- [ ] テストカバレッジ >75% 確保
- [ ] 全テスト実行・パス確認
- [ ] 手動機能テスト実行

## 出力形式

1. **ultrathink 実装プロセス**: 実装アプローチと思考過程
2. **実装概要**: 実装したコンポーネントと機能
3. **アーキテクチャ適合**: 既存パターンへの統合状況
4. **コード品質**: 型安全性・エラーハンドリング・テスト状況
5. **データベース変更**: スキーマ変更・マイグレーション（該当時）
6. **テスト結果**: 実装したテストと実行結果
7. **設定変更**: 新規設定・設定変更（該当時）
8. **パフォーマンス影響**: 実装による性能への影響評価
9. **完了状況**: 実装完了項目と残課題
10. **次ステップ**: test フェーズへの引き継ぎ事項

## 次のコマンド

実装完了後は `/test` コマンドで包括的検証を実施します。
