# テストディレクトリ構造の問題点（2025-11-07）

## 発見された問題

### 重複するテストファイル名
**発見日**: 2025-11-07
**影響**: pytestのコレクションエラーで一部テストが実行不可

**具体例**:
```
local_packages/image-annotator-lib/tests/unit/core/test_error_handling.py
local_packages/image-annotator-lib/tests/unit/fast/test_error_handling.py
```

**エラーメッセージ**:
```
import file mismatch:
imported module 'test_error_handling' has this __file__ attribute:
  /workspaces/LoRAIro/local_packages/image-annotator-lib/tests/unit/core/test_error_handling.py
which is not the same as the test file we want to collect:
  /workspaces/LoRAIro/local_packages/image-annotator-lib/tests/unit/fast/test_error_handling.py
HINT: remove __pycache__ / .pyc files and/or use a unique basename for your test file modules
```

### ディレクトリ構造の不明瞭さ

**現状の構造**:
```
tests/
├── unit/
│   ├── core/           # コアモジュールのテスト
│   ├── fast/           # 高速テスト? (目的不明)
│   ├── adapters/
│   └── ...
├── integration/
└── model_class/
```

**問題点**:
1. `unit/fast/` ディレクトリの目的が不明確
   - `@pytest.mark.fast` マーカーがあればディレクトリ分離は不要では?
   - `unit/core/` との使い分け基準が不明
2. 同じモジュール名のテストファイルが複数箇所に存在
   - pytestはモジュール名の一意性を要求する
3. ディレクトリ階層とテスト対象の対応が不明瞭

### 影響範囲
- Test Explorerでのテスト実行時にコレクションエラー
- 開発者が新規テストファイルを配置する際の混乱
- CI/CDでの予期しないテスト失敗

## TODO: 要改善事項

### 短期対応（即時）
- [x] 重複ファイル名のリネーム
  - `tests/unit/fast/test_error_handling.py` → `test_basic_error_handling.py`

### 中長期対応（計画要）
1. **ディレクトリ構造の再設計**
   - `unit/fast/` ディレクトリの目的を明確化または削除
   - テストファイル配置ルールの策定
   - ディレクトリ階層とソースコード構造の一致

2. **命名規則の確立**
   - テストファイル名の一意性を保証するルール
   - 例: `test_{module_path}_{test_type}.py` 形式
   - 既存ファイルの段階的リネーム

3. **ドキュメント整備**
   - テストディレクトリ構造の説明を CLAUDE.md に追加
   - 新規テスト作成時のガイドライン策定

4. **Pre-Commit Hook検討**
   - 重複モジュール名の検出
   - テストファイル命名規則の自動チェック

## 関連情報
- **プロジェクト**: image-annotator-lib
- **影響コンポーネント**: テストスイート全体
- **優先度**: 中（現在は workaround で対応可能だが、将来的な混乱を防ぐため改善推奨）

## 参考
- pytest公式ドキュメント: [Good Integration Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- 現在のテストマーカー: `unit`, `integration`, `webapi`, `fast`, `slow`, `scorer`, `tagger`
