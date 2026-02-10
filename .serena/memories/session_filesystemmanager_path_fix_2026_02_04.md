# Session: FileSystemManager保存先パスバグ修正

**Date**: 2026-02-04
**Branch**: feature/annotator-library-integration
**Commit**: 5e8e4ee
**Status**: completed

---

## 実装結果

### バグの根本原因
- commit `18cc334` (2025-08-28) で `FileSystemManager.initialize_from_dataset_selection()` が復元された際、保存先パスが `selected_dir.parent / "lorairo_output"` に誤設定された
- 正しくは `get_current_project_root()` でプロジェクトディレクトリを取得すべきだった
- 2025-07-22以前 (commit `b776034`) では正しく `database_dir` を使用していた

### 変更ファイル
1. **src/lorairo/storage/file_system.py** (バグ修正)
   - `output_dir = selected_dir.parent / "lorairo_output"` → `output_dir = get_current_project_root()` (遅延import)
2. **tests/unit/storage/test_file_system_manager.py** (新規: リグレッションテスト5件)
   - プロジェクトルート使用確認、lorairo_output非作成確認、ディレクトリ構造確認
3. **tests/unit/gui/controllers/test_dataset_controller.py** (fixture値修正)
   - `"/test/lorairo_output"` → `"/test/lorairo_data/project_001"`
4. **scripts/fix_lorairo_output_paths.py** (新規: DB移行スクリプト)
   - pHash検証付きDBパス修正スクリプト

### DB移行結果
- images: 13,081件 (Windows絶対パス → 相対パス)
- processed_images: 13,080件
- 追加196件 (C:\LoRAIro\... 形式の絶対パス → 相対パス)
- 全件pHash検証済み、バックアップ作成済み

## 設計意図

### 遅延importの採用理由
- `get_current_project_root` は `db_core` モジュールに存在
- `file_system.py` からのトップレベルimportは循環参照リスクがあるため、メソッド内で遅延importを使用
- テストでは `lorairo.database.db_core.get_current_project_root` をpatchする必要がある（モジュールレベルではなくソース元をpatch）

### pHash検証によるDB移行の安全性
- ファイル存在確認だけでは不十分（同名別ファイルの可能性）
- pHash比較でファイル同一性を保証した上でのみパス更新
- processed_images（サムネイル）はpHash不要、ファイル存在確認のみ

## 問題と解決

### パッチターゲット誤り
- 問題: `lorairo.storage.file_system.get_current_project_root` でpatchしたがAttributeError
- 原因: 遅延importなのでモジュール属性に存在しない
- 解決: `lorairo.database.db_core.get_current_project_root` をpatch

### DB内パスの3パターン
1. `J:\...\1_素材\lorairo_output\image_dataset\...` (大多数)
2. `J:\...\Downloads\lorairo_output\image_dataset\...` (279件、ユーザー移動漏れ)
3. `C:\LoRAIro\lorairo_data\...\image_dataset\...` (196件、正しいディレクトリだが絶対パス)

全パターンを `image_dataset/...` 相対パスに統一完了。

## 未完了・次のステップ
- なし（本セッションのタスクは全て完了）
