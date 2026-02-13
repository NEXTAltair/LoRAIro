# PydanticAI Model Factory 比較実験結果 (2026-02-12)

## 実験概要
Agent Teams (3エージェント: plan1, plan2, evaluator) を使用して、image-annotator-lib の PydanticAI Model Factory の2つのリファクタリングアプローチを並行実装・比較。

## 結果サマリー

### 推奨: Plan 1 (PydanticAI完全準拠)
- **LOC 65.5%削減**: 1,020行 → 352行
- **BDD 100%通過**: 13/13シナリオ (Plan 2は7/13)
- **加重スコア**: Plan 1: 8.55/10, Plan 2: 7.40/10

### 主要メトリクス
| 指標 | Plan 1 | Plan 2 |
|---|---|---|
| 合計LOC | 352 | 807 |
| 関数数 | 10 | 28 |
| 平均CCN | 4.5 | 3.4 |
| ユニットテスト | 26 passed | 79 passed |
| BDD | 13/13 | 7/13 |

### 統合計画
1. Plan 1の `pydantic_ai_factory.py` + `provider_manager.py` をmainにマージ
2. Plan 2の `_is_test_environment()` 簡素化版を採用
3. `annotator_adapter.py` の統合テスト更新
4. WebAPIアノテータテストの更新

## 実装ファイル
- レポート: `local_packages/image-annotator-lib/docs/pydantic_ai_factory_comparison_report.md`
- Plan 1 worktree: `/workspaces/LoRAIro-plan1` (experiment/plan1-pydanticai-full-compliance)
- Plan 2 worktree: `/workspaces/LoRAIro-plan2` (experiment/plan2-api-key-fallback)

## 教訓
- Agent Teams: haiku モデルは複雑なコード変更に対して旧APIの参照が残る問題あり（手動修正が必要だった）
- Git worktree + submodule: editable installが元worktreeを参照する問題（PYTHONPATH上書きが必要）
- ベンチマーク: モジュール初期化（registry load, API discovery）が重くランタイムベンチマーク困難
