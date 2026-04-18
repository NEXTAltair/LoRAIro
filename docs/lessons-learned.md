# Lessons Learned

LoRAIro 開発で得られた教訓。バグパターン・設計ミス・解決策の本質を記録。

## Architecture

- **2層サービス設計**: GUI層とビジネスロジック層を分離しないとモノリスが膨張する。Qt依存のないコアサービスを先に設計し、GUIラッパーを後から追加する順序が正しい（ADR 0001, 0009参照）。
- **MainWindow 肥大化**: 1,645行→688行(58%削減)を実現した教訓: 初期化フェーズを5段階に分け、各フェーズをServiceヘルパーに委譲する。GUIオーケストレーターは「接着剤」に留める。

## Testing

- **統合テストの価値**: モックが通ってもprod移行で失敗するケースが発生。外部依存(DB, ファイルシステム)はモックせず実際のテストDBを使用する。
- **pytest-qt のアンチパターン**: `qtbot.wait(固定時間)` は不安定。`qtbot.waitSignal()` または `qtbot.waitUntil(条件)` を使う。`QCoreApplication.processEvents()` 直接呼び出しも避ける。
- **QMessageBox の忘れがち**: テスト中に `QMessageBox.question` をモックしないとテストがハングする。必ず `monkeypatch` でモックする。

## PySide6 / Qt

- **UIファイル生成を忘れると連鎖エラー**: `.ui` ファイル変更後に `uv run python scripts/generate_ui.py` を実行しないと、`MainWindow_ui.py` が古いままで `filterSearchPanel` 等のウィジェットが見つからず起動失敗する。
- **Signalの二重発火**: Worker完了Signalを複数箇所で接続すると同一イベントが重複処理される。接続は1箇所に統一し、Worker生成時に接続する。

## Database / SQLAlchemy

- **セッション管理の落とし穴**: バッチ処理中のセッションをWorker間で共有するとデッドロックが発生する。Worker毎に独立したセッションを使用する。
- **バッチタグ追加のアトミック性**: タグ追加をループで個別コミットすると、エラー時に中間状態が残る。`Session.add_all()` + 一括コミットでアトミック性を保証する（ADR 0012参照）。
- **書き込み・読み込みの対称性**: カラムと子テーブルに同一意味のデータを並存させる二重管理は禁止。書き込み API と読み込み API が同一テーブルを参照することを PR レビューで必ず確認する。Issue #118 (NSFW 判定) と Issue #119 (manual_rating フィルタ) は同パターンで発生した（ADR 0015参照）。
- **User DB 初期化順序**: Base DBが存在しない環境でもUser DBは単独で動作する必要がある。`init_user_db()` は Base DB の有無に依存しない設計にする。

## Integration

- **Annotator Lib との境界**: annotation_logic.py でアダプターパターンを使い、image-annotator-lib の内部型 (`PHashAnnotationResults`) をLoRAIro内部型に変換する。Lib の型変更がLoRAIro全体に波及しない設計が重要。
- **Torch インポートの遅延**: Torch を起動時にインポートするとGUI表示が数秒遅延する。`importlib.import_module()` による遅延インポートで起動時間を短縮する（ADR 0010参照）。
- **アノテーターWorker のコード崩壊インシデント（2026-02-09）**: 大規模リファクタリング中にWorker実装が意図せず削除された。原因: `replace_symbol_body` ツールの適用範囲が予期以上に広かった。対策: シンボル置換後は必ずdiffで変更範囲を確認する。
