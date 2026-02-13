# Plan: squishy-percolating-rose

**Created**: 2026-02-10 14:58:05
**Source**: plan_mode
**Original File**: squishy-percolating-rose.md
**Status**: planning

---

# テスト実行ベース形骸化検出 実装計画

## Context

LoRAIroプロジェクトのテストスイート（約90ファイル、1,259テスト）には、コードベースの変更に伴い形骸化したテストが存在する可能性があります。このタスクでは、全テストファイルを個別実行し、失敗するテストを検出・分類することで、「参照先消滅型」「API不一致型」の形骸化テストをリストアップします。

**背景:**
- 既に2つのintegration GUIテストファイルが削除済み（git staging area）
- test_gui_configuration_integration.pyがImageProcessingManager参照で失敗する可能性が既知
- 総テストファイル数: 約90ファイル（conftest.py除外）
  - Unit tests: 66ファイル
  - Integration tests: 24ファイル
  - BDD tests: 0ファイル（conftest.pyのみ）

**目的:**
形骸化したテストを特定し、Markdownレポートとして削除推奨ファイルリストを提供すること。実際のファイル削除は別のTeammate（Teammate 4）が担当。

## 実装アプローチ

### 1. テストファイルリストアップ (5分)

**方法:**
- `Glob`ツールで`tests/unit/**/*.py`, `tests/integration/**/*.py`, `tests/bdd/**/*.py`を取得
- conftest.py, __init__.py, __pycache__を除外
- 絶対パスのリストを作成

**出力:**
- test_files.txt（実行対象ファイルリスト、約90行）

### 2. 個別テスト実行とエラー分類 (60-90分)

**実行コマンド:**
```bash
uv run pytest <file> -v --timeout=10 --timeout-method=thread -x
```

**エラー分類ロジック:**
- **ImportError**: `ModuleNotFoundError`, `ImportError`を検出 → 参照先消滅型候補
- **AttributeError**: `AttributeError: module 'X' has no attribute 'Y'`を検出 → 参照先消滅型 or API不一致型候補
- **AssertionError**: テストロジックの失敗 → 詳細調査必要（判定保留）
- **Timeout**: 10秒でハング → 環境問題候補（判定保留）
- **Success**: テストパス → スキップ

**並列実行検討:**
- 90ファイル × 平均30秒 = 45分（順次実行の場合）
- pytestは各ファイル独立なので、複数プロセスで並列実行可能（3-4並列で15-20分に短縮）
- ただし、GUIテストはQtリソース競合のリスクあり → unit/databaseのみ並列、GUI系は順次

**出力:**
- test_results.json（ファイルごとの実行結果、エラー分類、エラーメッセージ）

### 3. 形骸化判定（ソースコード検証） (30分)

**判定フロー:**

#### 参照先消滅型の判定
1. エラーメッセージから参照先を抽出（例: `ModuleNotFoundError: No module named 'lorairo.xxx'`）
2. `Glob`で`src/lorairo/`配下を検索:
   - モジュール: `src/lorairo/xxx.py`または`src/lorairo/xxx/__init__.py`が存在するか
   - クラス: `Grep`で`class ClassName`を検索
   - メソッド: `Grep`で`def method_name`を検索
3. 存在しない場合 → **参照先消滅型**（削除推奨）
4. 存在する場合 → API不一致型の可能性（次のステップへ）

#### API不一致型の判定
1. テストファイルから旧APIの使用方法を抽出（`Read`ツール）
2. 実装ファイルから現在のAPIシグネチャを確認（`Read`ツール）
3. シグネチャが大幅に変更されている場合 → **API不一致型**（削除推奨）
4. 判定困難な場合 → **判定保留**（人間確認必要）

**出力:**
- obsolescence_report.json（形骸化判定結果、判定根拠）

### 4. Markdownレポート生成 (10分)

**レポート構造:**
```markdown
# テスト実行ベース形骸化検出レポート

## 実行サマリー
- 実行ファイル総数: XX
- 成功ファイル数: XX
- 失敗ファイル数: XX
- 形骸化判定ファイル数: XX

## 失敗テスト詳細

### 参照先消滅型（削除推奨）
| ファイル | 失敗原因 | 参照先 | 判定根拠 |
|---------|---------|-------|---------|
| tests/unit/test_xxx.py | ImportError | lorairo.module.Xxx | src/lorairo/module/にXxx.py存在せず |

### API不一致型（削除推奨）
| ファイル | 失敗原因 | 旧API | 新API | 判定根拠 |
|---------|---------|------|------|---------|
| tests/integration/test_yyy.py | AttributeError | old_method(a, b) | new_method(c) | src/lorairo/xxx.pyでシグネチャ変更確認 |

### 判定保留（要人間確認）
| ファイル | 失敗原因 | 理由 |
|---------|---------|------|
| tests/unit/test_zzz.py | AssertionError | テストロジックの問題か実装バグか不明 |

## 削除推奨ファイルリスト
- tests/unit/test_xxx.py（参照先消滅）
- tests/integration/test_yyy.py（API不一致）

## 詳細ログ
[各ファイルの実行ログ要約]
```

**出力:**
- reports/obsolete_tests_report.md（最終レポート）

## 重要なファイル

### 実装ファイル（新規作成）
- `scripts/detect_obsolete_tests.py` - メインスクリプト（ステップ1-4統合）
- `reports/obsolete_tests_report.md` - 生成されるレポート

### 参照ファイル（既存）
- `tests/conftest.py` - テスト環境設定（image_annotator_libモック、Qt headless）
- `tests/unit/gui/conftest.py` - QMessageBox自動モック（unit GUI）
- `tests/integration/gui/conftest.py` - QMessageBox自動モック（integration GUI）
- `pyproject.toml` - pytest設定（[tool.pytest.ini_options]）

## 実行時間見積もり

- **ステップ1**: 5分（Globでファイルリスト取得）
- **ステップ2**: 60-90分（90ファイル × 平均30秒、並列実行で20-30分に短縮可能）
- **ステップ3**: 30分（形骸化判定、ソースコード確認）
- **ステップ4**: 10分（Markdownレポート生成）

**合計**: 約105-135分（並列実行で75-85分に短縮可能）

## 検証方法

1. **レポート完成確認**:
   ```bash
   cat reports/obsolete_tests_report.md
   ```

2. **削除推奨ファイルの妥当性確認**:
   - 各ファイルの失敗原因が適切に分類されているか
   - 参照先消滅型: src/lorairo/に該当モジュール/クラスが実際に存在しないか
   - API不一致型: 旧APIと新APIの差異が明確に記録されているか

3. **判定保留の理由確認**:
   - AssertionErrorの詳細が記録されているか
   - 人間が判断できる情報が十分に提供されているか

4. **Team Leadへのレポート送信**:
   - SendMessageツールでレポート内容を要約して送信
   - 削除推奨ファイル数とその理由を明示

## 注意事項

- **ファイル削除は行わない**: このタスクは検出とレポート作成のみ。実際の削除はTeammate 4が担当。
- **エラーログは簡潔に**: 全文ではなく、エラーの種類と該当箇所のみ記録。
- **形骸化判定が困難な場合**: 無理に判定せず「判定保留」に分類し、理由を明記。
- **GUIテストの注意**: QT_QPA_PLATFORM=offscreenは自動設定されるが、並列実行時はQtリソース競合に注意。
- **image_annotator_libモック**: tests/conftest.pyで自動適用されるため、個別設定不要。

## 並列実行戦略（オプション）

時間短縮のため、以下の並列戦略を採用可能:

1. **Unit Database Tests** (8ファイル) - 並列グループ1
2. **Unit Services Tests** (9ファイル) - 並列グループ2
3. **Unit GUI Tests** (30ファイル) - 順次実行（Qt競合回避）
4. **Integration Tests** (24ファイル) - 順次実行（DB/GUI競合回避）

並列グループは`Bash`ツールで`&`を使って同時実行し、`wait`で完了待機。

## 既知の問題への対応

- **test_gui_configuration_integration.py**: ImageProcessingManager参照で失敗する可能性が高い。形骸化判定の際、src/lorairo/でImageProcessingManagerの存在を確認。
- **削除済みファイル**: test_thumbnail_details_annotation_integration.py, test_ui_layout_integration.pyは既にgit削除済みなので、Globで検出されない。
