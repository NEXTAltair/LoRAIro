# Lessons Learned

LoRAIro 開発で得られた教訓。バグパターン・設計ミス・解決策の本質を記録。

## Architecture

- **2層サービス設計**: GUI層とビジネスロジック層を分離しないとモノリスが膨張する。Qt依存のないコアサービスを先に設計し、GUIラッパーを後から追加する順序が正しい（ADR 0001, 0009参照）。
- **MainWindow 肥大化**: 1,645行→688行(58%削減)を実現した教訓: 初期化フェーズを5段階に分け、各フェーズをServiceヘルパーに委譲する。GUIオーケストレーターは「接着剤」に留める。
- **Service 層統合パターン** (#178): GUI/CLI/API の 3 経路から同一ビジネスロジックを呼ぶ場合、各経路で個別実装すると二重クエリ・整合性ズレ・重複バグ修正が発生する。ID 解決ロジックを `DatasetExportService.export_with_criteria()` に集約することで 3 経路の一貫性を保証した。Epic #166 では GUI/CLI/API がそれぞれ別々の export 実装を持っていたが、Service 層統合後はすべて同一メソッドを呼ぶ。

## Testing

- **統合テストの価値**: モックが通ってもprod移行で失敗するケースが発生。外部依存(DB, ファイルシステム)はモックせず実際のテストDBを使用する。
- **pytest-qt のアンチパターン**: `qtbot.wait(固定時間)` は不安定。`qtbot.waitSignal()` または `qtbot.waitUntil(条件)` を使う。`QCoreApplication.processEvents()` 直接呼び出しも避ける。
- **QMessageBox の忘れがち**: テスト中に `QMessageBox.question` をモックしないとテストがハングする。必ず `monkeypatch` でモックする。
- **カバレッジ閾値は CI で検証しないと aspirational 値のまま**: `fail_under=75` が長期間 CI で未検証のまま放置され、実測 58% が顕在化（Issue #131 で coverage-gate 新設後に判明）。新しい閾値を設定する際は必ず PR で CI 実測値と同時に設定し、aspirational な値のまま設定だけして放置しないこと。
- **デッドコードはカバレッジ分母を汚染して測定値を押し下げる**: Issue #138 で `src/` 本体から未参照の 9 モジュール / 3,957 LOC を削除して +17pt を達成。`grep` ベースの import graph 解析による定期的な dead code audit がカバレッジ改善に効果的（ADR 0016参照）。
- **Qt 描画専用コードと torch/ML ライブラリは coverage から除外が合理的**: ADR-0016 でコアサービス層の omit を禁止しつつ、Qt 描画専用 GUI の `omit` 基準と image-annotator-lib の `source` 除外基準を確立。headless CI では torch 初期化が困難なため、ML バックエンドは `[tool.coverage.run] source` から除外して計測対象外にするのが正しい（Issue #135）。

## PySide6 / Qt

- **UIファイル生成を忘れると連鎖エラー**: `.ui` ファイル変更後に `uv run python scripts/generate_ui.py` を実行しないと、`MainWindow_ui.py` が古いままで `filterSearchPanel` 等のウィジェットが見つからず起動失敗する。
- **Signalの二重発火**: Worker完了Signalを複数箇所で接続すると同一イベントが重複処理される。接続は1箇所に統一し、Worker生成時に接続する。

## Database / SQLAlchemy

- **セッション管理の落とし穴**: バッチ処理中のセッションをWorker間で共有するとデッドロックが発生する。Worker毎に独立したセッションを使用する。
- **バッチタグ追加のアトミック性**: タグ追加をループで個別コミットすると、エラー時に中間状態が残る。`Session.add_all()` + 一括コミットでアトミック性を保証する（ADR 0012参照）。
- **書き込み・読み込みの対称性**: カラムと子テーブルに同一意味のデータを並存させる二重管理は禁止。書き込み API と読み込み API が同一テーブルを参照することを PR レビューで必ず確認する。Issue #118 (NSFW 判定) と Issue #119 (manual_rating フィルタ) は同パターンで発生した（ADR 0015参照）。
- **User DB 初期化順序**: Base DBが存在しない環境でもUser DBは単独で動作する必要がある。`init_user_db()` は Base DB の有無に依存しない設計にする。
- **プロジェクト概念のスキーマ正規化** (ADR 0017): ファイル名から推論する暗黙構造は破綻する。`lorairo_data/<name>_<timestamp>/` ディレクトリ構造だけでプロジェクトを識別していたため、Issue #166 で `repository.get_images_by_filter()` 引数なし全件取得 (21k 件) バグが発生。`projects` テーブル + `Image.project_id` FK 化で `WHERE project_id = ?` インデックス検索に置換し根本解決。DB を第一級エンティティとして設計することで、LIKE 句マッチや全件スキャンを構造的に排除できる。

## Integration

- **Annotator Lib との境界**: annotation_logic.py でアダプターパターンを使い、image-annotator-lib の内部型 (`PHashAnnotationResults`) をLoRAIro内部型に変換する。Lib の型変更がLoRAIro全体に波及しない設計が重要。
- **Torch インポートの遅延**: Torch を起動時にインポートするとGUI表示が数秒遅延する。`importlib.import_module()` による遅延インポートで起動時間を短縮する（ADR 0010参照）。
- **アノテーターWorker のコード崩壊インシデント（2026-02-09）**: 大規模リファクタリング中にWorker実装が意図せず削除された。原因: `replace_symbol_body` ツールの適用範囲が予期以上に広かった。対策: シンボル置換後は必ずdiffで変更範囲を確認する。
- **フィルタ必須化による構造的誤操作防止** (ADR 0019): LoRA 学習データ作成用途の `export create` では「全件エクスポート」が正常ケースとして存在しない。フィルタなし呼び出しを `exit_code=2` で即座に拒否することで、21k 件の誤エクスポートを設計レベルで防止した。ランタイム警告やドライラン強制より「そもそも呼べない設計」の方がシンプルで一貫性がある。非対話環境 (CI/cron) でも安全に機能する。
