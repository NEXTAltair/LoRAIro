# テスト・検証フェーズ

implementフェーズで実装されたコードについて、包括的なテスト・検証を実行します。

## 使用方法
```bash
@test テスト対象の説明
```

## 重要原則
- 関連するコードは全て読むこと
- 全ての処理においてultrathinkでしっかりと考えて作業を行うこと
- `.cursor/rules/test_rules/testing-rules.mdc`のテスト方針に完全準拠すること
- 75%以上のテストカバレッジを維持すること

## 説明
テスト対象: $ARGUMENTS

implementフェーズで実装された上記機能について、ユニット・統合・BDD（E2E）テストを包括的に実行し、品質とユーザー要件の充足を検証します。異常系テストも含めた堅牢性確認を行います。

## タスクに含まれるべきTODO

### 1. テスト準備・環境確認
1. implementフェーズの実装結果確認
2. テスト環境セットアップ確認（`uv sync --dev`）
3. 既存テストスイートの実行と基線確認
4. 新規実装部分のテスト対象特定
5. テストデータ・リソース準備

### 2. ユニットテスト実行・拡充（tests/unit/）
6. 単一クラス・関数の振る舞いテスト実行
7. 新規実装コンポーネントのユニットテスト作成
8. 外部依存関係の最小限モック化
9. 境界値・エッジケーステスト実装
10. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m unit` による単体テスト全実行

### 3. 統合テスト実行・拡充（tests/integration/）
11. LoRAIro内部モジュール間連携テスト実行
12. サービス層統合テスト実装
13. データベース操作統合テスト実行
14. AI統合（local packages）テスト実行
15. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m integration` による統合テスト全実行

### 4. GUIテスト実行・拡充（tests/gui/）
16. PySide6 コンポーネントテスト実行
17. ユーザーインタラクションシナリオテスト実装
18. Signal/Slot 連携テスト実行
19. 非同期処理（QThread）テスト実行
20. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m gui` によるGUIテスト全実行（ヘッドレス環境対応）

### 5. BDD（E2E）テスト実行・拡充（tests/bdd/）
21. 実際のユーザーシナリオ完全実行テスト
22. Feature/Scenario/Given-When-Then パターン実装
23. 外部依存関係を含む完全な統合テスト
24. データ永続化・復旧シナリオテスト
25. AI アノテーション完全ワークフローテスト

### 6. 異常系・エラーハンドリングテスト
26. 主要正常系パス確認後の異常系計画
27. エラーハンドリング・不正入力テスト実装
28. ファイルシステムエラーシナリオテスト
29. AI API エラー・タイムアウトシナリオテスト
30. データベース接続・整合性エラーテスト

### 7. パフォーマンス・負荷テスト
31. バッチ処理パフォーマンステスト（1000画像/5分目標）
32. メモリ使用量監視テスト
33. 大容量データセット処理テスト
34. 並行処理・リソース競合テスト
35. AI API レート制限対応テスト

### 8. 品質指標・カバレッジ確認
36. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest --cov=src --cov-report=html` によるカバレッジ測定
37. テストカバレッジ >75% 確認・必要時追加テスト実装
38. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff check` による最終コード品質チェック
39. `UV_PROJECT_ENVIRONMENT=.venv_linux uv run mypy src/` による型安全性最終確認
40. コード複雑度・可読性チェック

### 9. 回帰テスト・互換性確認
41. 既存機能への影響確認（回帰テスト）
42. 設定ファイル互換性テスト
43. データベースマイグレーション前後整合性テスト
44. 異なるAI プロバイダー間互換性テスト
45. クロスプラットフォーム動作確認（Linux/Windows）

### 10. ユーザー受け入れテスト計画
46. 実際のユーザーワークフロー検証
47. UI/UX 使いやすさ確認
48. エラーメッセージ・ログの分かりやすさ確認
49. ドキュメント・ヘルプとの整合性確認
50. パフォーマンス体感確認

### 11. セキュリティ・安定性テスト
51. API キー・機密情報漏洩防止テスト
52. ファイルアクセス権限・パス検証テスト
53. 入力値検証・インジェクション対策テスト
54. リソース枯渇・メモリリークテスト
55. 長時間稼働安定性テスト

### 12. ドキュメント・完了処理
56. テスト結果の包括的分析・レポート作成
57. 発見された問題・改善点の文書化
58. カバレッジレポートの保存（@coverage.xml）
59. テスト結果を文書化し、`tasks/test_results/test_{YYYYMMDD_HHMMSS}.md`に保存
60. テスト完了をコンソール出力で通知（echo "✅ テスト検証完了"）
61. 次ステップ（修正・改善・リリース）への推奨事項提示

## 実行内容

### テスト準備フェーズ
- 実装結果確認と基線設定
- テスト環境・データ準備
- テスト計画詳細化

### 包括的テスト実行フェーズ
- 段階的テスト実行（Unit → Integration → GUI → BDD）
- 異常系・パフォーマンステスト
- 品質指標・カバレッジ確認

### 検証・分析フェーズ
- テスト結果総合分析
- 問題・改善点特定
- 受け入れ基準適合確認

## 必読ファイル
- `tasks/implementations/implement_{implementation_target}_{YYYYMMDD_HHMMSS}.md` - 実装結果詳細
- `.cursor/rules/test_rules/testing-rules.mdc` - テスト方針・基準
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
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m unit` 実行・全パス確認
- [ ] 新規コンポーネントテスト網羅確認
- [ ] モック戦略適切性確認
- [ ] 境界値・エッジケース網羅確認
- [ ] テストカバレッジ貢献確認

### 統合テスト
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m integration` 実行・全パス確認
- [ ] モジュール間連携正常性確認
- [ ] データベース操作整合性確認
- [ ] AI統合機能正常性確認
- [ ] サービス層統合確認

### GUIテスト
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest -m gui` 実行・全パス確認（ヘッドレス）
- [ ] ユーザーインタラクション正常性確認
- [ ] 非同期処理・応答性確認
- [ ] Signal/Slot 連携確認
- [ ] エラー表示・ハンドリング確認

### 品質・カバレッジ確認
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest --cov=src --cov-report=html` 実行
- [ ] テストカバレッジ >75% 確認
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run ruff check` クリア確認
- [ ] `UV_PROJECT_ENVIRONMENT=.venv_linux uv run mypy src/` クリア確認
- [ ] パフォーマンス基準クリア確認

## 出力形式
1. **ultrathinkテストプロセス**: テスト戦略と実行思考過程
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
テスト完了後、問題があれば `@investigate` で原因調査、または改善実装のため `@plan` で計画策定を行います。