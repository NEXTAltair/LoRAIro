# Plan: lexical-launching-quill

**Created**: 2026-02-10 15:03:06
**Source**: plan_mode
**Original File**: lexical-launching-quill.md
**Status**: implemented

---

# LoRAIro テストファイル形骸化分析計画

## Context

LoRAIroプロジェクトはPhase 2-3のリファクタリング（2025-11〜2026-02）で大規模なコード変更を経験しました：

- **HybridAnnotationController削除** (2025-11-19): MainWindowへの統合
- **ImageProcessingManager永続インスタンス削除** (2025-11): 一時作成パターンへの変更
- **WorkerService旧API削除** (2025-11): `start_annotation()`, `start_enhanced_single_annotation()`

これらの変更により、95個のテストファイルの一部が形骸化している可能性があります。チームリーダーの指示により、テストファイルとソースコードの対応を分析し、削除推奨ファイルを特定します。

## 目標

1. **形骸化テストの特定**: OBSOLETE（完全形骸化）、PARTIALLY_OBSOLETE（部分形骸化）を判定
2. **API不一致の検出**: テストが旧APIを前提としているケースを発見
3. **削除推奨リストの作成**: 優先度付きで対応アクションを提示
4. **レポート生成**: JSON + Markdownで分析結果を出力

## 分析対象

- **テストファイル総数**: 95個（conftest.py含む）
- **重点調査対象**:
  - `HybridAnnotationController`参照（削除済み）
  - `ImageProcessingManager`永続インスタンス（削除済み）
  - `WorkerService.start_annotation()`呼び出し（削除済み）

## 形骸化判定基準

### 1. OBSOLETE（参照先消滅型）

**定義**: テスト対象のクラス、メソッド、モジュールがソースコードから完全に削除またはリネームされている。

**判定条件**:
- Import対象のクラスがソースに存在しない
- Patch対象のメソッドが削除されている
- テスト内で呼び出すメソッドが存在しない

**例**:
```python
# tests/integration/gui/test_worker_coordination.py L144
annotation_id = worker_service.start_annotation([], [], [])
# → WorkerService.start_annotation()は削除済み（L166-167で確認）
```

### 2. PARTIALLY_OBSOLETE（部分形骸化型）

**定義**: テストファイル内の一部テストケースのみが形骸化している。

**判定条件**:
- 10個のテストケース中、2個が削除済みメソッドを呼び出している
- 残り8個は有効

**対応**: 該当テストケースのみ修正または削除

### 3. API_MISMATCH（API不一致型）

**定義**: テスト対象は存在するが、メソッドシグネチャや振る舞いが大幅に変更され、テストが旧APIを前提としている。

**判定条件**:
- 引数数・型が現在の実装と異なる
- 戻り値型が変更されている
- Qtシグナル名が変更されている

### 4. VALID（有効テスト）

**定義**: テスト対象が存在し、APIも一致している。

## 分析手順

### Phase 1: テストファイル一覧取得

```bash
find /workspaces/LoRAIro/tests -name "*.py" -type f
```

### Phase 2: テストファイルごとの参照抽出

各テストファイルに対してAST解析で以下を抽出:

1. **Import文**:
   ```python
   from lorairo.gui.controllers.hybrid_annotation_controller import HybridAnnotationController
   ```

2. **Patch対象**:
   ```python
   @patch("lorairo.gui.services.worker_service.start_annotation")
   ```

3. **メソッド呼び出し**:
   ```python
   worker_service.start_annotation([], [], [])
   ```

### Phase 3: ソースコード存在確認

Serena MCPとGrepツールを使用:

1. **モジュール存在確認**:
   ```python
   # lorairo.gui.controllers.hybrid_annotation_controller
   Glob(pattern="hybrid_annotation_controller.py", path="src/lorairo/gui/controllers")
   ```

2. **クラス存在確認**:
   ```python
   Grep(pattern="class HybridAnnotationController", path="src/lorairo/gui/controllers")
   ```

3. **メソッド存在確認**:
   ```python
   Grep(pattern="def start_annotation", path="src/lorairo/gui/services/worker_service.py")
   ```

### Phase 4: 判定フロー

```
モジュール存在? → NO → OBSOLETE
    ↓ YES
クラス存在? → NO → OBSOLETE
    ↓ YES
メソッド存在? → NO → OBSOLETE
    ↓ YES
シグネチャ一致? → NO → API_MISMATCH
    ↓ YES
VALID
```

### Phase 5: レポート生成

JSON + Markdown形式で出力。

## 優先順位

### P0（最優先）- 削除済みコンポーネント参照

推定5-10ファイル:
- `HybridAnnotationController`参照
- `ImageProcessingManager`永続インスタンス
- `WorkerService.start_annotation()`呼び出し

**検出方法**:
```bash
grep -r "HybridAnnotationController" tests/ --include="*.py"
grep -r "start_annotation\|start_enhanced_single_annotation" tests/ --include="*.py"
```

**確認済み問題**:
- `tests/integration/gui/test_worker_coordination.py` L144

### P1（高優先）- 統合テスト

約20ファイル:
- `tests/integration/gui/*.py`
- `tests/integration/services/*.py`

**理由**: 複数コンポーネントの連携テストのため、API変更の影響を受けやすい

### P2（中優先）- GUIユニットテスト

約30ファイル:
- `tests/unit/gui/widgets/*.py`
- `tests/unit/gui/services/*.py`

### P3（低優先）- ビジネスロジックユニットテスト

約35ファイル:
- `tests/unit/services/*.py`
- `tests/unit/database/*.py`

**理由**: Qt-freeサービスは安定しているため変更頻度低い

### P4（最低優先）- conftest.py

約10ファイル:
- `tests/*/conftest.py`

**理由**: フィクスチャは実テストで間接検証される

## 出力レポート構造

### JSON形式

```json
{
  "analysis_date": "2026-02-10T15:30:00",
  "total_test_files": 95,
  "summary": {
    "obsolete": 12,
    "partially_obsolete": 8,
    "api_mismatch": 5,
    "valid": 70
  },
  "files": [
    {
      "path": "tests/integration/gui/test_worker_coordination.py",
      "status": "PARTIALLY_OBSOLETE",
      "test_count": 7,
      "obsolete_tests": [
        {
          "test_name": "test_concurrent_worker_management",
          "line": 144,
          "issue": {
            "type": "METHOD_NOT_FOUND",
            "severity": "HIGH",
            "called_method": "worker_service.start_annotation([], [], [])",
            "replacement": "Use start_enhanced_batch_annotation() instead"
          }
        }
      ]
    }
  ]
}
```

### Markdown形式

```markdown
# テスト形骸化分析レポート

## サマリー

| ステータス | ファイル数 | 割合 |
|-----------|----------|------|
| OBSOLETE | 12 | 12.6% |
| PARTIALLY_OBSOLETE | 8 | 8.4% |
| API_MISMATCH | 5 | 5.3% |
| VALID | 70 | 73.7% |

## 即削除推奨（CRITICAL）

1. tests/unit/gui/test_hybrid_controller.py
   - 問題: HybridAnnotationController削除済み
   - 対応: ファイル削除

## 修正推奨（HIGH）

2. tests/integration/gui/test_worker_coordination.py (L144)
   - 問題: start_annotation()削除済み
   - 対応: start_enhanced_batch_annotation()に置き換え
```

## Critical Files

### 分析実装に必要な重要ファイル

1. **tests/integration/gui/test_worker_coordination.py**
   - 実際の形骸化例（L144でstart_annotation呼び出し）
   - PARTIALLY_OBSOLETE判定のリファレンス

2. **src/lorairo/gui/services/worker_service.py**
   - 削除済みAPIの確認（L166-167でコメント記載）
   - 新API: start_enhanced_batch_annotation()

3. **src/lorairo/gui/controllers/**
   - 現存するコントローラー一覧
   - HybridAnnotationController削除の確認

4. **docs/testing.md**
   - テスト戦略とパターン参照

5. **.serena/memories/test_mapping_analysis_2026_02_08.md**
   - Phase 1調査結果（95個のテストファイル一覧）

6. **.serena/memories/legacy_code_cleanup_phase_e_2025_11_25.md**
   - 削除済みコンポーネント一覧

## 実装アプローチ

### 使用ツール

- **Glob**: テストファイル一覧取得、ソースファイル存在確認
- **Grep**: import文検索、メソッド定義確認、patch対象検索
- **Read**: テストファイル詳細読み込み、AST解析用

### バッチ処理戦略

効率化のため、類似パターンをバッチ処理:

#### バッチ1: 削除済みクラス検出
```bash
# HybridAnnotationController参照
grep -r "HybridAnnotationController" tests/ --include="*.py"

# ImageProcessingManager永続インスタンス
grep -r "ImageProcessingManager()" tests/ --include="*.py"
```

#### バッチ2: WorkerService旧API検出
```bash
grep -r "start_annotation\|start_enhanced_single_annotation" tests/ --include="*.py"
```

#### バッチ3: Controllers参照確認
```bash
grep -r "from lorairo.gui.controllers" tests/ --include="*.py"
```

### 分析順序

```
Phase 1: P0 + 確認済み問題ファイル（30分）
  → test_worker_coordination.py確認
  → HybridAnnotationController参照探索
  → ImageProcessingManager参照探索

Phase 2: P1統合テスト（1-2時間）
  → tests/integration/gui/全7ファイル分析
  → tests/integration/services/分析

Phase 3: P2 GUIユニットテスト（2-3時間）
  → tests/unit/gui/widgets/分析
  → tests/unit/gui/services/分析

Phase 4: P3ビジネスロジック（1-2時間）
  → tests/unit/services/分析
  → tests/unit/database/分析

Phase 5: P4フィクスチャ（30分）
  → conftest.py確認
```

## Verification

### 分析完了後の品質確認

1. **精度検証**:
   - False Positive率: 5%以下
   - False Negative率: 0%
   - 方法: OBSOLETE判定ファイルをランダムサンプリング（10ファイル）、手動照合

2. **完全性検証**:
   - 全テストファイルカバレッジ: 100%
   - 削除済みコンポーネント検出率: 100%
   - 方法: test_worker_coordination.pyが検出されることを確認

3. **レポート品質**:
   - 対応アクション明記: すべてのOBSOLETEファイルに対応方法記載
   - 優先度設定: CRITICAL/HIGH/MEDIUM/LOW区分
   - 置き換え情報: 削除済みAPIの代替手段明示

## 注意事項

- **実際のファイル削除は行わない**（Teammate 4が担当）
- 判定が難しい場合はPARTIALLY_OBSOLETEに分類し、人間確認を推奨
- import文だけでなく、テスト内のpatch()やモック対象も確認
- plan modeで実行し、レポート完成後にleadの承認を得る

## 期待される成果物

1. **test_obsolescence_report.json** - 機械可読な分析結果
2. **test_obsolescence_report.md** - 人間可読なレポート
3. **削除推奨ファイルリスト** - 優先度付きアクションリスト
