# Plan: optimized-wibbling-snowglobe (Post-Review Revision)

**Created**: 2026-01-29
**Source**: manual_sync
**Original File**: optimized-wibbling-snowglobe.md
**Status**: planning (post-review fixes)

---

# LoRAIro GUI ユーザビリティ改善計画 — 修正計画 (Post-Review)

## 実装状況

Phase 1〜2.2 の実装完了後、コードレビューで以下の問題が発見された。
本計画はレビュー指摘事項の修正を行う。

---

## レビュー指摘事項サマリー

| 重要度 | 問題 | ファイル |
|--------|------|----------|
| **CRITICAL** | TagCleaner インポートパスが間違い（実行時クラッシュ） | quick_tag_dialog.py |
| **MAJOR** | タグ正規化ロジック重複（DRY違反） | quick_tag_dialog.py, batch_tag_add_widget.py |
| **MAJOR** | パネル表示切替の初期化時 race condition | main_window.py |
| **MAJOR** | QSettings バージョン管理不足 | main_window.py |
| **MINOR** | lazy import → top-level import に変更 | main_window.py |
| **MINOR** | _handle_quick_tag_add のロジック重複 | main_window.py |

## 修正 1: TagCleaner インポートパス修正 [CRITICAL]

- `genai_tag_db_tools.utils.tag_cleaner` → `genai_tag_db_tools.utils.cleanup_str`
- ファイル: `src/lorairo/gui/widgets/quick_tag_dialog.py:4`

## 修正 2: タグ正規化ロジック共通化 [MAJOR]

- モジュールレベル関数 `normalize_tag()` を `batch_tag_add_widget.py` に定義
- `QuickTagDialog` と `BatchTagAddWidget` の両方から呼び出す
- `_normalize_tag()` インスタンスメソッドは共通関数へのデリゲートに変更

## 修正 3: パネル表示切替 race condition [MAJOR]

- `_restore_panel_visibility()` で `blockSignals(True)` により復元時のシグナル抑制
- パネル可視状態を `setVisible()` で直接設定

## 修正 4: QSettings バージョン管理 [MAJOR]

- `SETTINGS_VERSION = 1` クラス定数追加
- `_save_window_state()` でバージョン保存
- `_restore_window_state()` でバージョン不一致時はデフォルト値を使用

## 修正 5: lazy import → top-level import [MINOR]

- `QuickTagDialog` のインポートを `main_window.py` ファイル先頭に移動
- `_show_quick_tag_dialog()` 内の lazy import を削除

## 修正 6: バッチタグ書き込みロジック共通化 [MINOR]

- `_execute_batch_tag_write(image_ids, tag) -> bool` 共通メソッドを抽出
- `_handle_batch_tag_add()` と `_handle_quick_tag_add()` はこの共通メソッドを呼び出す

## 実装順序

1. 修正 1: TagCleaner インポートパス修正 (CRITICAL)
2. 修正 2: タグ正規化ロジック共通化
3. 修正 5: lazy import → top-level import
4. 修正 6: バッチタグ書き込みロジック共通化
5. 修正 3: パネル表示切替 race condition
6. 修正 4: QSettings バージョン管理

## 検証方法

```bash
uv run python -c "from lorairo.gui.widgets.quick_tag_dialog import QuickTagDialog; print('OK')"
uv run ruff check src/lorairo/gui/widgets/quick_tag_dialog.py src/lorairo/gui/widgets/batch_tag_add_widget.py src/lorairo/gui/window/main_window.py
uv run mypy src/lorairo/gui/widgets/quick_tag_dialog.py src/lorairo/gui/widgets/batch_tag_add_widget.py src/lorairo/gui/window/main_window.py --ignore-missing-imports
uv run pytest tests/unit/gui/widgets/ -v
```
