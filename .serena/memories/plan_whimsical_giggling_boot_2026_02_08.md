# Plan: whimsical-giggling-boot

**Created**: 2026-02-08 14:28:39
**Source**: plan_mode
**Original File**: whimsical-giggling-boot.md
**Status**: planning

---

# UX不足機能実装計画（修正版）

## Context

UX監査で特定された6つの不足機能を補完する。現在、主要操作（タグ追加、選択解除、検索、設定、エラーログ）で「無言失敗」が多発しており、ユーザーはエラーや操作結果を知ることができない。この計画はSerena Memory `plan_ux_missing_features_implementation_2026_02_08` を精査・修正したもの。

### 元計画からの主な修正点
1. **Phase 1-3（選択解除クリア）**: `_clear_display()` が既に存在するため1行変更で完了
2. **Phase 2（設定画面）**: importパス問題の具体的対策を明確化（`..windows` → `..window`）。UIがQWidgetベースのためQDialogラッパーが必要
3. **Phase 4（プレビュー）**: FIXMEはスタンドアロン実行限定。メインアプリでは問題なし → 調査のみ
4. **テスト計画**: 既存テスト（23項目）の拡張 vs 新規作成を明確化
5. **エラーログエクスポート**: `current_error_records` 属性を利用したCSV出力

---

## Phase 1: P0 UXフィードバック基盤

### 1-1. バッチタグ追加の入力エラー通知

**変更ファイル**: [batch_tag_add_widget.py](src/lorairo/gui/widgets/batch_tag_add_widget.py)

`_on_add_tag_clicked()` (L282-322) の3つのTODOを実装:
- L295-296: ステージング空 → `QMessageBox.warning(self, "タグ追加エラー", "ステージングリストに画像がありません。\n画像を選択してからタグを追加してください。")`
- L302-303: 空タグ → `QMessageBox.warning(self, "タグ追加エラー", "タグを入力してください。")`
- L309-310: 正規化失敗 → `QMessageBox.warning(self, "タグ追加エラー", f"タグ '{tag_text}' の正規化に失敗しました。")`

**変更ファイル**: [main_window.py](src/lorairo/gui/window/main_window.py)

`_handle_batch_tag_add()` (L1097-1120):
- 成功時: `self.statusBar().showMessage(f"タグ '{tag}' を {len(image_ids)} 件の画像に追加しました", 5000)`
- 失敗時: `QMessageBox.critical(self, "タグ追加失敗", f"タグ '{tag}' の追加に失敗しました。")`

### 1-2. クイックタグ追加の失敗通知

**変更ファイル**: [quick_tag_dialog.py](src/lorairo/gui/widgets/quick_tag_dialog.py)

`_on_add_clicked()` (L89-103):
- L93 空入力: `self._tag_input.setPlaceholderText("タグを入力してください")` + return（非モーダル）
- L100 正規化失敗: `QMessageBox.warning(self, "タグエラー", f"タグ '{tag}' の正規化に失敗しました。")`

**変更ファイル**: [main_window.py](src/lorairo/gui/window/main_window.py)

`_handle_quick_tag_add()` (L1147-1160):
- 成功時: `self.statusBar().showMessage(f"クイックタグ '{tag}' を追加しました", 5000)`
- 失敗時: `QMessageBox.critical(self, "タグ追加失敗", f"クイックタグ '{tag}' の追加に失敗しました。")`

### 1-3. 選択解除時クリア処理（1行変更）

**変更ファイル**: [main_window.py](src/lorairo/gui/window/main_window.py)

`_handle_selection_changed_for_rating()` (L962-998) の `len(image_ids) == 0` 分岐:

```python
if len(image_ids) == 0:
    self.selectedImageDetailsWidget._clear_display()
    logger.debug("No images selected - display cleared")
```

**根拠**: `_clear_display()` (L506-546) は既にRatingScoreEditWidget（PG-13/score 0にリセット）、全ラベル、タグ、キャプション、アノテーション表示を一括クリアする。新規メソッド不要。

### 1-4. 検索入力エラーフィードバック

**変更ファイル**: [filter_search_panel.py](src/lorairo/gui/widgets/filter_search_panel.py)

3箇所の修正:
1. `_on_search_requested()` 内の条件未指定スキップ（L892-893）: ステータスラベル表示 `"検索条件が未指定です"` + 3秒後自動クリア
2. 日付範囲無効（L904-906）: `QMessageBox.warning(self, "日付範囲エラー", "日付フィルターが有効ですが、有効な日付範囲を取得できません。")`
3. 例外ハンドラ（L936-957）: `_update_ui_for_state(ERROR)` 時にステータスメッセージを表示

**追加UI**: `_status_label` (QLabel) を `setup_custom_widgets()` 内で `progress_layout` に追加。`_state_messages[ERROR]` のテキストをこのラベルに反映。

---

## Phase 2: 設定画面復旧（P1）

### 2-1. ConfigurationWindow クラス作成

**新規ファイル**: [src/lorairo/gui/window/configuration_window.py](src/lorairo/gui/window/configuration_window.py)

**設計**: QDialog + 内部QWidget構成（UIファイルがQWidgetベースのため）
```python
class ConfigurationWindow(QDialog):
    def __init__(self, config_service: ConfigurationService, parent: QWidget | None = None):
        super().__init__(parent)
        self._config_service = config_service
        self._ui_widget = QWidget()
        self._ui = Ui_ConfigurationWindow()
        self._ui.setupUi(self._ui_widget)
        layout = QVBoxLayout(self)
        layout.addWidget(self._ui_widget)
        button_box = QDialogButtonBox(Ok | Cancel)
        button_box.accepted.connect(self._on_save_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
```

主要メソッド:
- `_populate_from_config()`: `config_service.get_all_settings()` からUI入力欄を初期化
- `_on_save_and_accept()`: UI値を `config_service.update_setting()` で更新 → `save_settings()` → `accept()`
- `_on_save_as()`: `QFileDialog.getSaveFileName()` で保存先指定

### 2-2. SettingsController importパス修正

**変更ファイル**: [settings_controller.py](src/lorairo/gui/controllers/settings_controller.py)

L69: `from ..windows.configuration_window` → `from ..window.configuration_window`
L71: `ConfigurationWindow(parent=self.parent)` → `ConfigurationWindow(config_service=self.config_service, parent=self.parent)`

---

## Phase 3: エラーログエクスポート（P1）

### 3-1. エクスポート機能実装

**変更ファイル**: [error_log_viewer_widget.py](src/lorairo/gui/widgets/error_log_viewer_widget.py)

`_on_export_log_clicked()` (L287-298) を置換:
- `self.current_error_records` が空なら warning
- `QFileDialog.getSaveFileName()` で保存先選択
- CSV形式でエクスポート（カラム: ID, 操作種別, エラーメッセージ, 発生日時, 解決済み）
- 成功: `QMessageBox.information()`、失敗: `QMessageBox.critical()`
- import: `csv`, `QFileDialog` を追加

---

## Phase 4: プレビュー表示サイズ（P2 → 調査のみ）

**判断変更**: FIXMEコメント (L230) は `__main__` ブロック内のみ。`_adjust_view_size()` はレイアウト内で正常動作。

**アクション**: メインアプリ内で再現確認 → 再現しなければ `__main__` ブロックのFIXMEを更新してクローズ。再現すれば `_adjust_view_size()` のタイミング調整。

---

## テスト計画

| Phase | ファイル | アクション | テスト数 |
|-------|---------|----------|---------|
| 1-1 | [test_batch_tag_add_widget.py](tests/unit/gui/widgets/test_batch_tag_add_widget.py) | 既存23項目を拡張 | +3 |
| 1-2 | 新規: `tests/unit/gui/widgets/test_quick_tag_dialog.py` | 新規作成 | 4 |
| 1-3 | 既存テストに追加 | 選択解除時の `_clear_display` 呼び出し確認 | +1 |
| 1-4 | 新規: `tests/unit/gui/widgets/test_filter_search_panel.py` | 新規作成 | 4-5 |
| 2 | 新規: `tests/unit/gui/controllers/test_settings_controller.py` | 新規作成 | 4 |
| 2 | 新規: `tests/unit/gui/window/test_configuration_window.py` | 新規作成 | 4 |
| 3 | [test_error_log_viewer_widget.py](tests/unit/gui/widgets/test_error_log_viewer_widget.py) | スタブテスト置換 | 4 (replaces 1) |

**QMessageBoxモックパターン**（既存プロジェクト規約準拠）:
```python
monkeypatch.setattr(QMessageBox, "warning", lambda *args: QMessageBox.Ok)
```

---

## リスク対策

| リスク | 影響 | 対策 |
|--------|------|------|
| ConfigurationWindow のカスタムWidget初期化失敗 | 高 | 最小機能（APIキーのみ）で起動確認 → 段階追加 |
| 既存テスト `test_tag_add_request_empty_staging` がQMessageBox追加で破壊 | 低 | monkeypatchでQMessageBoxモック追加 |
| Phase 1-3 の二重クリア（selection_changed + current_image_data_changed両方発火） | 低 | `_clear_display()` はべき等操作のため問題なし |
| FilterSearchPanel のステータスラベル追加がレイアウト崩壊 | 低 | 既存 `progress_layout` に追加、高さ固定 |

---

## 実装順序

1. **Phase 1-1 → 1-2 → 1-3 → 1-4** (P0即効改善、独立性が高いため順次実装)
2. **Phase 2** (設定画面、最もコード量が多い)
3. **Phase 3** (エラーログ、小規模)
4. **Phase 4** (調査のみ)

## 検証方法

1. `uv run pytest tests/unit/gui/widgets/test_batch_tag_add_widget.py -v`
2. `uv run pytest tests/unit/gui/widgets/test_quick_tag_dialog.py -v`
3. `uv run pytest tests/unit/gui/widgets/test_filter_search_panel.py -v`
4. `uv run pytest tests/unit/gui/controllers/test_settings_controller.py -v`
5. `uv run pytest tests/unit/gui/widgets/test_error_log_viewer_widget.py -v`
6. 全テスト: `uv run pytest -m unit --tb=short`
7. 型チェック: `uv run mypy -p lorairo`
8. フォーマット: `uv run ruff check src/ tests/ --fix && uv run ruff format src/ tests/`
