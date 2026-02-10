# GUIテスト ヘッドレス環境修正 (2026-02-10)

## 修正した問題

### 1. テスト収集時のハング（image_annotator_lib）
- **根本原因**: `image_annotator_lib.__init__.py` → `core/registry.py` → `_gather_available_classes()` が
  `importlib.import_module()` で model_class/ 内の全ファイルを動的にインポートし、
  torch/tensorflow 等の重いMLライブラリのロードをトリガー
- **インポートチェーン**: `MainWindow` → `WorkerService` → `AnnotatorLibraryAdapter` → `image_annotator_lib`
  (`annotator_adapter.py:9` のモジュールレベルインポート)
- **修正**: `tests/conftest.py` にモジュールレベルの `sys.modules` injection で
  `image_annotator_lib` と14サブモジュールを軽量モックに置換

### 2. pytest-qt カスタムフィクスチャの競合
- **根本原因**: カスタム `qapp` フィクスチャが `app.quit()` を呼び、pytest-qt内蔵と競合。
  `qapp_args` が `--platform offscreen` を二重設定
- **修正**: カスタム `qapp` と `configure_qt_for_tests` を削除。
  `qapp_args` をシンプルなアプリ名のみに変更。
  Qt ヘッドレス設定はモジュールレベルの `os.environ.setdefault` で実施

### 3. セグフォ（ErrorDetailDialogテスト）
- **根本原因**: `patch.object(ErrorDetailDialog, "reject")` がQDialogの
  C++メソッドをクラスレベルでパッチし、Shibokenの内部状態と衝突
- **修正**: `monkeypatch.setattr` + インスタンスレベルモックに変更

### 4. 統合GUIテストのQMessageBoxハング
- **根本原因**: `tests/unit/gui/conftest.py` の QMessageBox autouseモックが
  `tests/integration/gui/` のテストには適用されない
- **修正**: `tests/integration/gui/conftest.py` を作成し、同じQMessageBoxモックを追加

## 修正ファイル
- `tests/conftest.py` - image_annotator_lib モック追加、qapp/qapp_args修正
- `tests/unit/gui/widgets/test_error_detail_dialog.py` - patch.object → monkeypatch
- `tests/integration/gui/conftest.py` - QMessageBox autouseモック（新規作成）

## 結果
- 修正前: テスト収集・実行時に無限ハング
- 修正後: 全テスト83秒で完了、ハング0件、セグフォ0件
- 1162 PASSED, 52 FAILED, 27 ERROR, 18 SKIPPED
