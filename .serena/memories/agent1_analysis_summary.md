# LoRAIro テスト分析レポート（Agent 1実行結果）

**実行日**: 2026-02-10
**分析対象**: `/workspaces/LoRAIro/tests/`

---

## 📊 現状統計

| 項目 | 値 |
|------|-----|
| 総テストファイル数 | 91個 |
| 総テスト行数 | 28,063行 |
| conftest.py ファイル数 | 1個（ルートのみ） |
| 推定テスト数 | 300+（見積り） |

---

## 📂 ディレクトリ別詳細分析

### features/（BDD シナリオ）
- ファイル数: 2個
- 総行数: 179行
- 特徴: Gherkin形式（.feature ファイル）
- 役割: BDD E2E テスト

### integration/（統合テスト）
- ファイル数: 25個
- 総行数: 7,593行
- 対象コンポーネント:
  - `integration/database/` - DB関連テスト
  - `integration/gui/` - GUI統合テスト
    - `widgets/` - ウィジェットテスト
    - `window/` - メインウィンドウテスト
    - `workers/` - ワーカーテスト
  - `integration/services/` - サービス統合テスト
- 特徴: 最も充実したテストカテゴリ（カバレッジの中核）

### step_defs/（BDD ステップ定義）
- ファイル数: 1個
- 総行数: 1,468行
- 役割: features/ のシナリオに対応するステップ実装

### gui/（GUIテスト専用）
- ファイル数: 0個
- 特徴: ディレクトリは存在するが、test_*.py ファイルなし
- 推測: GUIテストが integration/gui/ に統合されている可能性

### manual/（手動テスト）
- ファイル数: 0個
- 特徴: ディレクトリ存在、ファイルなし

### performance/（パフォーマンステスト）
- ファイル数: 0個
- 特徴: ディレクトリ存在、ファイルなし

### resources/（テストリソース）
- 用途: テスト画像、ダミーデータ
- サイズ: 数MB

---

## 🚨 重大な問題点

### 1. **conftest.py が一層のみ存在（HIGH優先度）**
**現状**: `tests/conftest.py` のみ
**期待**: Multi-layer 構造
```
tests/
├── conftest.py（全体共通）
├── integration/
│   └── conftest.py（統合テスト用）
├── gui/
│   └── conftest.py（GUI専用）
└── bdd/
    └── conftest.py（BDD専用）
```
**影響**:
- フィクスチャの責務が不明確
- 各テストカテゴリの独立性低い
- セットアップ/クリーンアップの重複可能性

### 2. **ディレクトリ構成と実装のズレ（HIGH優先度）**
**期待**: `tests/unit/`, `tests/gui/`, など分類
**現状**:
- `unit/` ディレクトリなし
- `gui/` ディレクトリはあるが、テストファイルなし
- テストが `integration/` に寄せ集められている

**推測**: GUIテスト（pytest-qt）が `integration/gui/` に統合されている

### 3. **テストマーカー統一未実装（MEDIUM優先度）**
- `@pytest.mark.unit` / `.integration` / `.gui` / `.bdd` の統一適用状況不明
- 現在の conftest.py で定義されているマーカー確認が必要

### 4. **重複テストの可能性（MEDIUM優先度）**
- 25ファイルの integration/ テストが全て異なる機能をテストしているか未確認
- 同じ機能の複数テスト実装の可能性あり

### 5. **手動/パフォーマンステスト未実装（LOW優先度）**
- `manual/`, `performance/` ディレクトリ存在但しファイルなし

---

## 📈 改善優先度（High > Medium > Low）

### Priority: HIGH

1. **Multi-layer conftest.py 体系の実装**
   - root conftest.py: 全体共通フィクスチャのみ
   - integration/conftest.py: DB初期化、統合テスト用フィクスチャ
   - gui/conftest.py: Qt初期化、QMessageBox モック
   - bdd/conftest.py: BDD ステップコンテキスト

2. **ディレクトリ構成の正規化**
   - `unit/` ディレクトリ作成・テスト移動
   - `gui/` ディレクトリの利用開始
   - `manual/` / `performance/` への今後のテスト配置基準確立

### Priority: MEDIUM

3. **テストマーカー統一**
   - すべてのテストに `@pytest.mark.unit|integration|gui|bdd` を付与
   - pytest.ini でマーカー定義

4. **重複テスト排除**
   - 25個の integration/ テストの詳細分析
   - 重複機能テストの統合・削除

5. **pytest-qt コンプライアンス確認**
   - GUI テストの waitSignal/waitUntil 使用
   - 違反パターン改修

### Priority: LOW

6. **手動テスト、パフォーマンステスト**
   - 今後の計画に基づき実装

---

## 📊 推定カバレッジ

- 総行数: 28,063行
- 対象コンポーネント: src/lorairo/
- **推定カバレッジ**: 60-75%（詳細 pytest --cov で要確認）
  - integration/ の充実度から、中核機能はカバー
  - 新規パッケージ (image-annotator-lib, genai-tag-db-tools) のカバレッジ未確認

---

## 🔍 次のステップ（Agent 2 へ）

1. **現状構造の確認**
   - `tests/conftest.py` の詳細確認
   - `integration/gui/` の pytest-qt 使用パターン確認

2. **設計アーキテクチャ立案**
   - Multi-layer conftest.py の責務分割
   - ディレクトリ再構成の実装計画
   - テストマーカー統一方針

3. **移行ロードマップ作成**
   - Phase 1-5 の詳細設計
   - リスク評価

---

## 📝 補足

- **計画ドキュメント** vs **現状のギャップ**が大きい
- 計画では unit/ 主力 + integration/ 補助的な想定だが、現状は integration/ に統合
- これは **パラダイム選択の違い** を示唆：
  - 計画: Unit-first 戦略（粒度が細かい）
  - 現状: Integration-first 戦略（粒度が大きい）

推奨: 現在の Integration-first アプローチを尊重しつつ、conftest.py の責務分割と マーカー統一を優先実装
