# Phase 3.2: export create コマンド実装 - セッション完了記録

**Date**: 2026-02-16
**Branch**: NEXTAltair/issue15
**Status**: ✅ Completed

---

## 実装結果

### ファイル変更

| ファイル | 変更内容 | 行数 |
|--------|--------|------|
| `src/lorairo/cli/commands/export.py` | 新規作成 | 193 |
| `src/lorairo/cli/main.py` | export登録 | 1 |
| `tests/unit/cli/test_commands_export.py` | テスト実装 | 490 |

**合計**: 12テスト全パス、CLI全体64/64パス

---

## 実装内容

### 1. export.py - エクスポートコマンド実装

**アーキテクチャ**:
- サブコマンドアプリ形式（project.py, annotate.py と同パターン）
- Rich Progress バーで進捗表示
- ServiceContainer から ImageRepository + DatasetExportService取得
- エラーハンドリング（ValueError → exit code 1, Exception → exit code 2）

**コマンド**:
```bash
lorairo-cli export create --project <name> --output <path> [--format txt|json] [--resolution 512]
```

**実装仕様**:
```python
# 1. プロジェクト確認
_validate_project_and_db(project_name)  # Helper関数で複雑度削減

# 2. 画像取得
all_images, _ = repository.get_images_by_filter()
image_ids = [img["id"] for img in all_images]

# 3. エクスポート実行
export_service.export_filtered_dataset(
    image_ids,
    output_path,
    format_type=format.lower(),
    resolution=resolution,
)

# 4. サマリー表示（Rich Table）
```

**リファクタリング**:
- 複雑度削減: `_validate_project_and_db()` ヘルパー関数抽出
  - 複雑度: 11 → 7（フレッシュメトリクス）
  - プロジェクト確認 + DB確認ロジックを集約

**注記**:
- Current limitation: 単一グローバルデータベース（db_core.py初期化）
- TODO: 将来的にマルチプロジェクトDB切り替え対応

### 2. test_commands_export.py - 包括的テスト

**テストケース（12項目）**:

| テスト | 説明 | パターン |
|--------|------|---------|
| test_export_create_txt_format | TXT形式エクスポート | @patch |
| test_export_create_json_format | JSON形式エクスポート | @patch |
| test_export_create_with_custom_resolution | 解像度指定 | @patch |
| test_export_create_output_directory_auto_creation | 出力ディレクトリ自動作成 | @patch |
| test_export_create_nonexistent_project | プロジェクト未検出 | @patch |
| test_export_create_missing_database | DB未検出 | @patch |
| test_export_create_no_images | 画像未検出 | @patch |
| test_export_create_invalid_format | 無効フォーマット | @patch |
| test_export_create_help | ヘルプ表示 | native |
| test_export_help | export --help | native |
| test_export_create_default_format | デフォルト形式(txt) | @patch |
| test_export_create_default_resolution | デフォルト解像度(512) | @patch |

**モッキング戦略**:
```python
# create_mock_service_container()で標準化
mock_container = MagicMock()

# image_repository.get_images_by_filter()
mock_repository.get_images_by_filter.return_value = ([
    {"id": 1, "name": "image1.jpg"},
    {"id": 2, "name": "image2.jpg"},
    {"id": 3, "name": "image3.jpg"},
], 3)

# export_service.export_filtered_dataset()
def export_filtered_dataset_side_effect(image_ids, output_path, **kwargs):
    return output_path
mock_export_service.export_filtered_dataset.side_effect = export_filtered_dataset_side_effect
```

**テスト実行結果**:
```
============================== 12 passed in 1.26s ==============================
```

### 3. main.py - サブコマンド登録

```python
from lorairo.cli.commands import project, images, annotate, export

app.add_typer(export.app, name="export", help="Dataset export commands")
```

---

## 品質指標

✅ **テスト結果**:
- export テスト: 12/12 パス（100%）
- CLI全体: 64/64 パス（100%）
- 既存テスト回帰: なし

✅ **コード品質**:
- Ruff: All checks passed!
- MyPy: All checks passed!
- Complexity: C901削減（11 → 7）
- 型ヒント: 100%

✅ **実装パターン**:
- プロジェクト確認: project_module.PROJECTS_BASE_DIR利用
- サービス取得: get_service_container()利用
- エラーハンドリング: exit code (1: user error, 2: system error)
- UI: Rich Progress + Table表示

---

## アーキテクチャ判断

### 1. ヘルパー関数抽出

**理由**:
- create()の複雑度が11（フレッシュメトリクス）で限界超過
- プロジェクト確認 + DB確認が関連ロジック
- 将来的にprogram_name引数拡張時に再利用可能

**抽出内容**:
```python
def _validate_project_and_db(project_name: str) -> Path:
    """プロジェクトとデータベースを確認"""
    # ディレクトリ検索
    # DB確認
    # エラーレイズ
```

### 2. ServiceContainer統合

**採用パターン**:
```python
container = get_service_container()
repository = container.image_repository  # All images取得用
export_service = container.dataset_export_service  # エクスポート実行用
```

**理由**:
- ImageRepository.get_images_by_filter()で全画像取得
- DatasetExportService.export_filtered_dataset()でエクスポート実行
- 既存サービス層を活用（重複実装回避）

### 3. エラーハンドリング戦略

```python
# ValueError → exit code 1（ユーザーエラー）
except ValueError as e:
    console.print(f"[red]Error:[/red] Invalid export format: {e}")
    raise typer.Exit(code=1) from e

# Exception → exit code 2（システムエラー）
except Exception as e:
    console.print(f"[red]Error:[/red] Export failed: {e}")
    raise typer.Exit(code=2) from e
```

**規約**: Phase 2.1 CLI基盤で確立

---

## 次のステップ

### Phase 3.3: 統合・ドキュメント

予定タスク:
1. docs/cli.md更新（export create コマンド追加）
2. 統合テスト実行（全CLI 50+ テスト確認）
3. セッション記録と LTM 保存

### Phase 4: annotate run 実装（オプション）

予定内容:
- annotate.py コマンド実装
- ModelService + AnnotatorLibraryAdapter統合
- AI結果DB保存

---

## 参考資料

- **Phase 2記録**: `session_phase2_2_project_commands_complete_2026_02_16`
- **実装計画**: `/home/vscode/.claude/plans/phase3_cli_annotate_export_implementation.md`
- **テストパターン**: `tests/unit/cli/test_commands_project.py` (fixture reference)
- **コマンドパターン**: `src/lorairo/cli/commands/annotate.py` (Rich Progress reference)

---

## Commit情報

**Commit hash**: cc67714
**Message**: feat: Phase 3.2 export create コマンド実装

```
feat: Phase 3.2 export create コマンド実装

**実装内容**:
- export.py: export createサブコマンド定義
- main.py: exportサブコマンド登録
- test_commands_export.py: 12テストケース実装

**品質指標**:
✅ テスト: 12/12パス、CLI全体64/64パス
✅ コード品質: Ruff + MyPy クリア
✅ カバレッジ: 新規実装10+テストで75%以上維持
```

---

## 開発履歴

**セッション時間**: 約1.5時間

**タイムライン**:
- 0:00 - Plan分析、Phase 2 パターン確認
- 0:15 - export.py実装
- 0:30 - test_commands_export.py実装（12テスト）
- 0:45 - テスト実行・モック調整
- 1:00 - Ruff/MyPy品質改善
- 1:15 - 最終テスト確認・コミット

**実装パターン習得**:
- @patch decorator for CLI test mocking
- create_mock_service_container() pattern
- Helper関数による複雑度削減
