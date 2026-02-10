# Session: GUIテスト ヘッドレス環境ハング修正

**Date**: 2026-02-10
**Branch**: feature/annotator-library-integration
**Commit**: df63493
**Status**: completed

---

## 実装結果

### 修正ファイル
- `tests/conftest.py` - image_annotator_lib sys.modules モック注入、カスタム qapp/configure_qt_for_tests 削除
- `tests/unit/gui/widgets/test_error_detail_dialog.py` - patch.object → monkeypatch 移行
- `tests/integration/gui/conftest.py` - QMessageBox autouse モック（新規作成）

### テストリファクタリング Phase 1 成果物（前セッションから引き継ぎ）
- `pytest.ini` - マーカー定義
- `tests/unit/conftest.py`, `tests/integration/conftest.py`, `tests/unit/gui/conftest.py`, `tests/bdd/conftest.py` - 5層conftest体系
- `scripts/add_test_markers.py`, `scripts/migrate_to_waituntil.py` 等のヘルパースクリプト

## テスト結果

- **修正前**: テスト収集・実行で無限ハング（5分+待機しても完了しない）
- **修正後**: 全1,259テストが83秒で完了
  - 1,162 PASSED / 52 FAILED / 27 ERROR / 18 SKIPPED
  - ハング: 0件、セグフォ: 0件

## 設計意図

### sys.modules injection パターン（image_annotator_lib モック）
- **選択理由**: conftest.py のモジュールレベルで sys.modules に軽量モックを注入し、lorairo の import チェーンが image_annotator_lib に到達しても torch/tensorflow がロードされないようにする
- **代替案**: lazy import に変更 → プロダクションコードの変更が大きすぎる
- **代替案**: テストファイルごとに mock.patch → テスト収集フェーズ（import時）には効かない

### pytest-qt 組み込み qapp フィクスチャの採用
- **選択理由**: pytest-qt の qapp は QApplication.instance() のチェック、app.quit() 非呼び出し等、堅牢な実装
- **代替案**: カスタム qapp 維持 → app.quit() が pytest-qt 内部と衝突するリスク

### QMessageBox monkeypatch パターン
- **選択理由**: monkeypatch.setattr は Python レベルの属性置換であり、Shiboken の C++ バインディング層と安全に共存
- **代替案**: patch.object → Shiboken のメモリ管理と衝突してセグフォの可能性

## 問題と解決

### 問題1: テスト収集時の無限ハング
- **原因**: annotator_adapter.py:9 のモジュールレベル import → image_annotator_lib → registry.py → importlib.import_module で model_class/ 全ファイル動的ロード → torch/tensorflow ロード
- **解決**: sys.modules injection で image_annotator_lib + 14サブモジュールを軽量モックに置換

### 問題2: ErrorDetailDialog テストのセグフォ
- **原因**: patch.object(ErrorDetailDialog, "reject") がQDialogのC++メソッドをクラスレベルでパッチ → Shiboken 内部状態破壊
- **解決**: monkeypatch.setattr + インスタンスレベルモックに変更

### 問題3: 統合GUIテストの QMessageBox ハング
- **原因**: tests/unit/gui/conftest.py の QMessageBox autouse モックが tests/integration/gui/ に適用されない
- **解決**: tests/integration/gui/conftest.py を作成し同じモックを配置

## 未完了・次のステップ

### テストリファクタリング Phase 2-5（計画済み・未実装）
- テストマーカー一括付与（@pytest.mark.unit/integration/gui/bdd）
- 重複テスト削除（5件）
- waitUntil 移行（21箇所）
- カバレッジ 75%+ 達成
- docs/testing.md 更新
- 計画ファイル: `.claude/plans/declarative-wobbling-hellman.md`

### 既存テスト不具合（52 FAILED + 27 ERROR）
- test_image_preview_widget.py の4 ERROR
- test_ui_layout_integration.py の15 ERROR
- 本セッションの修正対象外だが次セッションで対応検討
