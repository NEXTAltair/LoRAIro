# テストアーキテクチャ設計ドキュメント作成完了

**作成日**: 2026-02-10
**作成者**: Agent 2 (テストアーキテクチャ設計リード)

## 作成ドキュメント

1. **`docs/new_test_architecture.md`** - 新テストアーキテクチャ設計
   - CLAUDE.md Testing Rules 完全準拠の4層設計（unit/integration/gui/bdd）
   - 現状 -> 新構造のマッピング（96ファイルの配置方針）
   - conftest.py 分割計画（802行1ファイル -> 4ファイル合計 440-640行）
   - テストマーカー統一（16個 -> 6個に整理）
   - フィクスチャ依存関係最適化（最大深度 5 -> 3 以下）
   - テスト配置判断フローチャート
   - pytest-qt ベストプラクティス違反修正計画（15箇所）

2. **`docs/migration_roadmap.md`** - 5フェーズ移行ロードマップ
   - Phase 1: 準備（conftest.py分割、ディレクトリ整理）- 1-2日
   - Phase 2: ユニットテスト最適化（マーカー、重複削除）- 2-3日
   - Phase 3: 統合テスト整理（マーカー、フィクスチャ共有化）- 2-3日
   - Phase 4: GUI/BDD標準化（pytest-qt修正、BDDパス更新）- 2-3日
   - Phase 5: 検証・クリーンアップ - 1-2日
   - リスク評価とロールバック手順

3. **`docs/conftest_template.py`** - conftest.py 実装テンプレート
   - tests/conftest.py: ルート最小限（80-120行、7フィクスチャ）
   - tests/unit/conftest.py: ユニット用（120-160行、15フィクスチャ）
   - tests/integration/conftest.py: 統合用（200-280行、14フィクスチャ）
   - tests/bdd/conftest.py: BDD用（40-80行、2フィクスチャ）

## 設計判断

- **既存 unit/integration 構造を維持**: 65+25 ファイルの大規模移動を回避
- **conftest.py 分割を最優先**: 802行 -> 4ファイルで保守性大幅向上
- **BDD ディレクトリ正規化**: features/ + step_defs/ -> bdd/ に統合
- **空ディレクトリ削除**: gui/, services/, manual/, performance/ を削除
- **マーカー pytestmark 方式**: モジュールレベル定義で全関数に自動適用
