# Plan: velvety-wondering-sloth

**Created**: 2026-02-11 15:17:58
**Source**: plan_mode
**Original File**: velvety-wondering-sloth.md
**Status**: planning

---

# Agent Teams計画: PydanticAI Model Factory実装方式の比較実験

## Context

**Issue**: [NEXTAltair/image-annotator-lib#1](https://github.com/NEXTAltair/image-annotator-lib/issues/1)
**問題**: image-annotator-libのPydanticAI統合におけるモデルファクトリー実装が複雑化。2つの設計候補を並行実装し比較検証する。

**現状**:
- **Plan 2（APIキー検出+フォールバック案）** が本番実装済み（3層階層: ProviderManager → ProviderInstance → PydanticAIProviderFactory）
- **Plan 1（PydanticAI完全準拠案）** がプロトタイプとして`prototypes/pydanticai_integration/`に存在
- テストカバレッジ: 25%（目標75%）、ユニットテスト不足

**目的**: 両プランを本番品質で実装し、コード可読性・パフォーマンス・拡張性を定量評価して推奨案を決定する。

---

## Team Structure

```
┌─────────────────────────────────────┐
│  Team Lead (user session / Sonnet)  │
│  - 実験コーディネーション            │
│  - Plan approval / 最終評価          │
│  - 結果統合 & 推奨案決定             │
└──────────┬──────────────────────────┘
           │ delegate mode推奨
    ┌──────┴──────┬──────────────┐
    ▼             ▼              ▼
┌─────────┐ ┌─────────┐ ┌──────────┐
│ plan1   │ │ plan2   │ │ evaluator│
│ (Haiku) │ │ (Haiku) │ │ (Haiku)  │
│         │ │         │ │          │
│ Plan1   │ │ Plan2   │ │ BDDテスト │
│ 実装    │ │ 改善    │ │ ベンチ   │
│         │ │         │ │ マーク   │
│ worktree│ │ worktree│ │ 評価基盤 │
│ plan1/  │ │ plan2/  │ │ main     │
└─────────┘ └─────────┘ └──────────┘
```

| Role | Model | 担当 | Working Directory |
|------|-------|------|-------------------|
| **Lead** | Sonnet (or user's model) | コーディネーション、Plan承認、最終評価 | `/workspaces/LoRAIro` |
| **plan1** | Haiku | Plan 1の本番品質実装 | `/workspaces/LoRAIro-plan1` (worktree) |
| **plan2** | Haiku | Plan 2のリファクタ・テスト強化 | `/workspaces/LoRAIro-plan2` (worktree) |
| **evaluator** | Haiku | 共通テスト・ベンチマーク・評価フレームワーク | `/workspaces/LoRAIro` (main) |

---

## Setup（事前準備）

### 1. Agent Teams機能の有効化

`.claude/settings.local.json` に追加:
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### 2. Git Worktree作成

```bash
# Plan 1用worktree
git worktree add /workspaces/LoRAIro-plan1 -b experiment/plan1-pydanticai-compliance

# Plan 2用worktree
git worktree add /workspaces/LoRAIro-plan2 -b experiment/plan2-apikey-fallback

# 各worktreeで環境構築
cd /workspaces/LoRAIro-plan1 && uv sync --dev
cd /workspaces/LoRAIro-plan2 && uv sync --dev
```

### 3. 評価用ブランチ作成（メインworktree）

```bash
cd /workspaces/LoRAIro
git checkout -b experiment/evaluation
```

---

## Task List（共有タスクリスト）

### Phase 1: 環境準備 & 評価フレームワーク設計（evaluator主担当）

| ID | Task | Owner | Depends | 詳細 |
|----|------|-------|---------|------|
| T1 | 共通BDDフィーチャーファイル作成 | evaluator | - | 両プラン共通で通過すべきBDDシナリオ定義 |
| T2 | ベンチマークフレームワーク作成 | evaluator | - | pytest-benchmark統合、メトリクス収集スクリプト |
| T3 | 評価基準ドキュメント作成 | evaluator | - | 定量/定性評価項目の定義 |

### Phase 2: 並行実装（plan1 / plan2 主担当）

| ID | Task | Owner | Depends | 詳細 |
|----|------|-------|---------|------|
| T4 | Plan 1: コア実装 | plan1 | T1 | `infer_model()`完全依存、単一クラス設計 |
| T5 | Plan 1: OpenRouter対応 | plan1 | T4 | OpenRouter動的モデル発見の実装 |
| T6 | Plan 1: ユニットテスト | plan1 | T4 | 75%カバレッジ目標 |
| T7 | Plan 1: BDD通過確認 | plan1 | T1,T4 | evaluatorのBDDシナリオをパス |
| T8 | Plan 2: DRY違反解消 | plan2 | - | ProviderInstance統一化 |
| T9 | Plan 2: テスト環境判定簡素化 | plan2 | T8 | 45行ロジックの分解・テスタブル化 |
| T10 | Plan 2: ユニットテスト強化 | plan2 | T8,T9 | 75%カバレッジ目標 |
| T11 | Plan 2: BDD通過確認 | plan2 | T1,T8 | evaluatorのBDDシナリオをパス |

### Phase 3: ベンチマーク & 評価（evaluator主担当、全員協力）

| ID | Task | Owner | Depends | 詳細 |
|----|------|-------|---------|------|
| T12 | Plan 1ベンチマーク実行 | evaluator | T7 | パフォーマンスメトリクス収集 |
| T13 | Plan 2ベンチマーク実行 | evaluator | T11 | パフォーマンスメトリクス収集 |
| T14 | コード複雑度分析 | evaluator | T7,T11 | radon/lizard等でCyclomatic Complexity測定 |
| T15 | 比較レポート作成 | evaluator | T12,T13,T14 | 定量/定性分析の統合レポート |

### Phase 4: 最終決定（Lead主導）

| ID | Task | Owner | Depends | 詳細 |
|----|------|-------|---------|------|
| T16 | 推奨案の決定 | lead | T15 | 評価結果に基づく最終判断 |
| T17 | 選択されたプランのmainマージ準備 | plan1/plan2 | T16 | PRの作成 |

---

## Teammate Spawn Prompts

### Lead起動プロンプト（ユーザーが実行）

```
PydanticAI Model Factory実装方式の比較実験を行うAgent Teamを作成してください。

# チーム構成
3人のteammateを生成:
1. "plan1" - Plan 1（PydanticAI完全準拠案）の実装担当。Haikuモデルを使用。
2. "plan2" - Plan 2（APIキー検出+フォールバック案）のリファクタ担当。Haikuモデルを使用。
3. "evaluator" - テスト・ベンチマーク・評価フレームワーク担当。Haikuモデルを使用。

# ワークフロー
1. まずevaluatorに共通BDDテストと評価基準を作成させる
2. plan1とplan2はそれぞれのworktreeで並行実装
3. 両プランのBDD通過を確認後、evaluatorがベンチマーク実行
4. 結果を統合して推奨案を決定

# delegate modeを有効にして、自分はコーディネーションに専念
# 全teammateにPlan approval必須
```

### plan1 Spawn Prompt

```
あなたは image-annotator-lib の PydanticAI Model Factory 比較実験において、
**Plan 1（PydanticAI完全準拠案）** の実装を担当します。

# Working Directory
/workspaces/LoRAIro-plan1 (git worktree)

# 実装方針
PydanticAIの`infer_model()`に完全に依存する設計:

1. **単一クラス設計**: `PydanticAIWebApiAnnotator` 1クラスで全プロバイダー対応
   - プロトタイプ参照: local_packages/image-annotator-lib/prototypes/pydanticai_integration/
   - 特に pydanticai_webapi_annotator.py と dependencies.py

2. **設計原則**:
   - PydanticAI の infer_model() でモデル名からプロバイダーを自動解決
   - WebApiDependencies (Pydantic BaseModel) で依存性注入
   - 設定ファイル最小化（モデルID文字列のみで動作）
   - OpenRouter対応: 動的モデル発見

3. **変更対象ファイル** (local_packages/image-annotator-lib/src/image_annotator_lib/):
   - core/pydantic_ai_factory.py → 大幅簡素化
   - core/provider_manager.py → 削除または統合
   - core/base/pydantic_ai_annotator.py → WebApiDependencies DI統合
   - core/simplified_agent_wrapper.py → 不要になる可能性あり
   - model_class/annotator_webapi/*.py → 統一クラスに集約

4. **既存テストの維持**: 既存のBDDテスト・統合テストが通ること

5. **新規テスト**: ユニットテスト75%カバレッジ目標

# 制約
- LoRAIro側の統合ポイント (annotator_adapter.py) のAPIは変更しない
- image-annotator-lib の公開API (annotate(), list_available_annotators_with_metadata()) は互換維持
- Python 3.12、Ruff formatting (line length: 108)

# コミュニケーション
- 実装計画をleadに送信してplan approvalを得てから実装開始
- BDD通過後、evaluatorにベンチマーク実行を依頼
- 設計判断で迷った場合はplan2 teammateと議論
```

### plan2 Spawn Prompt

```
あなたは image-annotator-lib の PydanticAI Model Factory 比較実験において、
**Plan 2（APIキー検出+フォールバック案）** のリファクタリングを担当します。

# Working Directory
/workspaces/LoRAIro-plan2 (git worktree)

# リファクタリング方針
現在の3層階層構造を維持しつつ、以下の問題を解決:

1. **DRY違反解消**: ProviderInstance 4クラスの重複コードを統一
   - 現状: AnthropicProviderInstance, OpenAIProviderInstance,
     OpenRouterProviderInstance, GoogleProviderInstance がほぼ同一コード
   - 目標: ジェネリックな ProviderInstance + Provider固有設定のみ分離

2. **テスト環境判定の簡素化** (core/pydantic_ai_factory.py):
   - 現状: 45行の _is_test_environment() (inspect.stack()含む)
   - 目標: 明示的フラグベース + 環境変数の2段階判定に簡素化
   - パフォーマンス改善: inspect.stack() 削除

3. **APIキー検出の一元化**:
   - 現状: 3段階検出 × 4プロバイダー × テスト判定の組み合わせ爆発
   - 目標: config_registry層での一元管理、ProviderInstance層では受け取るだけ

4. **変更対象ファイル** (local_packages/image-annotator-lib/src/image_annotator_lib/):
   - core/provider_manager.py → ProviderInstance統一化
   - core/pydantic_ai_factory.py → テスト判定簡素化
   - core/base/pydantic_ai_annotator.py → Agent設定統合
   - core/config.py → APIキー検出の一元化

5. **テスト強化**:
   - OpenRouter特別処理のユニットテスト
   - _run_agent_safely() のエラーハンドリングテスト
   - APIキー3段階検出の全パターンテスト
   - 75%カバレッジ目標

# 制約
- LoRAIro側の統合ポイント (annotator_adapter.py) のAPIは変更しない
- image-annotator-lib の公開API互換維持
- Provider-levelリソース共有パターンは維持（プラン2の利点）
- Python 3.12、Ruff formatting (line length: 108)

# コミュニケーション
- リファクタリング計画をleadに送信してplan approvalを得てから実装開始
- BDD通過後、evaluatorにベンチマーク実行を依頼
- 設計判断で迷った場合はplan1 teammateと議論
```

### evaluator Spawn Prompt

```
あなたは image-annotator-lib の PydanticAI Model Factory 比較実験において、
**テスト・ベンチマーク・評価** を担当します。

# Working Directory
/workspaces/LoRAIro (main worktree)

# Phase 1: 共通テストフレームワーク作成

1. **共通BDDフィーチャーファイル** (tests/features/):
   両プランが通過すべきシナリオを定義:

   ```gherkin
   Feature: PydanticAI Model Factory統一テスト

   Scenario: 単一プロバイダーでのアノテーション実行
   Scenario: 複数プロバイダーの並行実行
   Scenario: APIキー未設定時のエラーハンドリング
   Scenario: OpenRouterカスタムヘッダー送信
   Scenario: モデルID文字列からのプロバイダー自動判定
   Scenario: Agent/Providerキャッシュの効率性
   Scenario: 認証エラー時のグレースフル処理
   ```

2. **ベンチマークフレームワーク**:
   - pytest-benchmark統合スクリプト
   - メトリクス: 初回ロード時間、推論応答時間、メモリ使用量
   - Agent/Provider生成のオーバーヘッド測定
   - 10回/100回/1000回の繰り返し測定

3. **評価基準ドキュメント**:
   定量指標:
   - Cyclomatic Complexity (radon)
   - コード行数 (LOC)
   - テストカバレッジ (%)
   - 初回ロード時間 (ms)
   - 推論応答時間 (ms)
   - メモリ使用量 (MB)

   定性指標:
   - 新プロバイダー追加の容易さ（必要な変更箇所数）
   - デバッグ容易性（スタックトレースの明確さ）
   - 設定ファイルの簡潔さ
   - PydanticAIアップデートへの追従性

# Phase 2: ベンチマーク実行
- plan1とplan2のBDD通過後、各worktreeでベンチマーク実行
- 結果をJSON/CSV形式で収集

# Phase 3: 比較レポート作成
- 定量データの比較表
- 定性評価のまとめ
- 推奨案と根拠

# 制約
- メインworktreeのコードは変更しない（テスト/ベンチマークファイルのみ追加）
- 評価は客観的・定量的であること
- Python 3.12、Ruff formatting (line length: 108)

# コミュニケーション
- 評価フレームワーク完成後、plan1とplan2にBDDシナリオを共有
- 各プランのBDD通過報告を受けてベンチマーク実行
- 最終レポートをleadに提出
```

---

## 評価基準の詳細

### 定量指標

| 指標 | 測定方法 | 重み |
|------|---------|------|
| コード行数 (LOC) | `wc -l` / `cloc` | 15% |
| Cyclomatic Complexity | `radon cc` | 20% |
| テストカバレッジ | `pytest --cov` | 15% |
| 初回ロード時間 | `pytest-benchmark` (Agent生成) | 15% |
| 推論応答時間 | `pytest-benchmark` (mock API) | 10% |
| メモリ使用量 | `tracemalloc` / `psutil` | 10% |
| 新プロバイダー追加コスト | 必要な変更ファイル数・行数 | 15% |

### 定性指標

| 指標 | 評価方法 |
|------|---------|
| デバッグ容易性 | エラー発生時のスタックトレース比較 |
| 設定の簡潔さ | TOML設定ファイルの比較 |
| PydanticAI追従性 | infer_model() 依存度、バージョンアップ影響 |
| LoRAIro統合影響 | annotator_adapter.py への変更必要性 |

---

## ファイル競合回避マップ

| ファイルパス | plan1 | plan2 | evaluator |
|-------------|-------|-------|-----------|
| `core/pydantic_ai_factory.py` | 書換 | リファクタ | 読取のみ |
| `core/provider_manager.py` | 削除/統合 | リファクタ | 読取のみ |
| `core/base/pydantic_ai_annotator.py` | 書換 | リファクタ | 読取のみ |
| `core/config.py` | 微修正 | APIキー一元化 | 読取のみ |
| `tests/unit/core/test_pydantic_*` | 新規作成 | 既存修正 | 読取のみ |
| `tests/features/*.feature` | 読取のみ | 読取のみ | **新規作成** |
| `benchmarks/` | 読取のみ | 読取のみ | **新規作成** |

**競合なし**: 各teammateはそれぞれのworktreeで独立作業。evaluatorはメインworktreeでテスト/ベンチマークのみ追加。

---

## 成果物

1. **Plan 1実装ブランチ**: `experiment/plan1-pydanticai-compliance`
   - 本番品質のコード、75%+カバレッジ、BDD通過
2. **Plan 2改善ブランチ**: `experiment/plan2-apikey-fallback`
   - リファクタリング済みコード、75%+カバレッジ、BDD通過
3. **評価レポート**: `docs/experiment-report-pydanticai-factory.md`
   - 定量/定性比較、推奨案と根拠
4. **共通BDDテスト**: `tests/features/pydantic_ai_factory_unified.feature`
   - 両プラン共通の受け入れテスト

---

## Verification（検証手順）

### 各Phase完了時の確認

**Phase 1完了チェック**:
```bash
# BDDフィーチャーファイルが存在すること
ls tests/features/pydantic_ai_factory_unified.feature

# ベンチマークスクリプトが存在すること
ls benchmarks/
```

**Phase 2完了チェック**:
```bash
# Plan 1: worktreeでテスト実行
cd /workspaces/LoRAIro-plan1
uv run pytest local_packages/image-annotator-lib/tests/ -m "unit or bdd" --cov --cov-report=term

# Plan 2: worktreeでテスト実行
cd /workspaces/LoRAIro-plan2
uv run pytest local_packages/image-annotator-lib/tests/ -m "unit or bdd" --cov --cov-report=term

# 両方とも75%以上のカバレッジ、BDD全パス
```

**Phase 3完了チェック**:
```bash
# ベンチマーク結果の存在確認
ls benchmarks/results/

# レポートの存在確認
cat docs/experiment-report-pydanticai-factory.md
```

**Phase 4完了チェック**:
```bash
# 選択されたプランのPR作成確認
gh pr list --search "PydanticAI Model Factory"
```

### 最終確認: LoRAIro統合テスト

```bash
# メインプロジェクトのテストが通ること（選択プランマージ後）
cd /workspaces/LoRAIro
uv run pytest tests/ --timeout=10 --timeout-method=thread
```

---

## Hook設定（品質ゲート）

Agent Teams の Hook を使って品質を担保:

### TaskCompleted Hook

```bash
#!/bin/bash
# .claude/hooks/task-completed.sh
# タスク完了時にテストとカバレッジを検証

TASK_DESCRIPTION="$1"

# テスト関連タスクの場合、カバレッジチェック
if echo "$TASK_DESCRIPTION" | grep -q "テスト\|test\|BDD"; then
  COVERAGE=$(uv run pytest --cov --cov-report=term 2>&1 | grep "TOTAL" | awk '{print $NF}' | tr -d '%')
  if [ "$COVERAGE" -lt 75 ]; then
    echo "カバレッジが75%未満です: ${COVERAGE}%"
    exit 2  # タスク完了を拒否
  fi
fi
```

### TeammateIdle Hook

```bash
#!/bin/bash
# .claude/hooks/teammate-idle.sh
# teammateがidleになった時、未完了タスクがあれば再活性化

echo "未完了タスクを確認中..."
# exit 2 で再活性化、exit 0 でidle許可
```

---

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| Worktree環境差異 | テスト結果の不一致 | 同一Pythonバージョン、`uv sync` 統一 |
| PydanticAI API変更 | Plan 1の実装が動かない | `pydantic-ai>=0.3.2` 固定 |
| Haiku性能限界 | 複雑なリファクタリングで品質低下 | Lead（Sonnet）がPlan承認で品質ゲート |
| ベンチマーク環境差 | 比較結果のブレ | 同一マシン・同一条件で連続実行 |
| LoRAIro統合破壊 | メインプロジェクトが壊れる | 公開API互換を制約条件に設定 |

---

## 注意事項

- **モデルコスト**: Teammateは全てHaikuを使用。LeadのみSonnet（コーディネーション品質確保）
- **Plan approval必須**: 各teammateは実装計画をleadに提出し、承認後に実装開始
- **Delegate mode推奨**: Leadはコーディネーションに専念し、直接実装しない
- **Worktreeクリーンアップ**: 実験完了後に `git worktree remove` で整理
