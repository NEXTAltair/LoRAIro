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
- **`sys.modules` ベースの lib mock を `tests/conftest.py` で行う場合、その lib の `tests/` を pytest `testpaths` に含めてはならない** (Issue #247, ADR 0024): `tests/conftest.py` がモジュールレベルで `sys.modules["image_annotator_lib"]` を `types.ModuleType` モックに差し替えていると、ルート pytest が `local_packages/image-annotator-lib/tests/` まで collection した瞬間に mock が lib 自身のテストに継承され、`parent_module = <MagicMock>` で `AttributeError: __spec__` が collection 時点で 29 件発生する。さらに submodule の同名テスト (`test_worker_service.py`) との basename 衝突も単一 pytest セッションでは `import file mismatch` になる。教訓: **conftest の責務境界 = pytest セッション境界 = package 境界を一致させる**。conftest mock を維持したまま、`testpaths = ["tests"]` に限定し local package のテストは package root の独立 pytest セッション (別 CI job / `make test-iam-lib` / `make test-genai-tag`) で実行する。条件分岐 conftest や `--ignore` 局所回避は根本解にならない。

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
- **BaseAnnotator hierarchy: WebAPI と Local ML で device 判定責務を分離** (Issue #35, ADR 0023 Phase 1.x): ADR 0023 Phase 1 で WebAPI 経路は `WebApiAnnotator` 1 種に統一され、device は `"api"` 固定で扱う設計になった。しかし `BaseAnnotator.__init__` が `_validate_device` (`determine_effective_device`) を踏む構造のままだと、将来 WebAPI 系クラスが `super().__init__()` を呼んだ瞬間に CUDA 判定が走り、CPU-only コンテナで「CUDA非対応PyTorch」WARNING が出る (Issue #35)。device 判定はローカル ML 系 base class (Transformers/ONNX/TF/Clip/Pipeline) の責務として分離するのが構造的解。`BaseAnnotator.device` は str sentinel (`""`) で初期化し、サブクラスが上書きする契約とする。
- **整数 bin tag (`[CAFE]score_N` / `[IAP]score_N` / `[WD]score_N`) を library 側から削除** (Issue #281, iam-lib ADR 0002): image-annotator-lib ADR 0002 で arbitrary policy として lib 標準出力から排除した。LoRAIro 側 consumer を inventory した結果 0 件 (Issue #281 調査時点)。再導入が必要になった consumer は raw `scores` から派生実装する。lib 側で配布元保証のない integer bin 化を行わないことで、検索 / Export contract を model 配布元と一致させる。
- **score (数値) と score_label (categorical) を別テーブルに分離する** (Issue #281, ADR 0027): canonical scorer (aesthetic_shadow / cafe_aesthetic) は `scores={hq, lq}` 等の **複数 row** と単一 categorical label を返す。`Score` テーブルに `label` 列を追加すると 2 行に同じ label を入れるか null を許容するか非自明になり、データセマンティクス歪み。`(image_id, model_id, label)` を独立した `score_labels` テーブルに分離することで、`Tag`/`Caption`/`Rating` と parallel な構造で扱える (ADR 0015 の Manual Rating Storage Unification と同じ設計判断)。
- **ADR と実装の整合は明示的検査でないと drift する** (Issue #35, PR #40): ADR 0023 Phase 1 で「`available_api_models.toml` キャッシュは廃止」「WebAPI 用 user TOML override は廃止」「`api_model_id` 互換シムを残さない」と決まっていたが、Phase 1 の PR #38 で実装変更だけ走り dead code / 互換シムが大量に残置された (`load_available_api_models` 関数、`AVAILABLE_API_MODELS_CONFIG_PATH` 公開 API、`_resolve_model_class` の `class = "WebApiAnnotator"` 受け入れ経路、metadata の `api_model_id` 重複キー等)。Codex P1 review で broken path として検出されてから完全掃除した。教訓: ADR 決定後の実装 PR では「ADR 各条項 → 該当コード / public API」のチェックリスト照合を行い、削除/置換漏れがないかを diff レビューで明示的に確認する。Phase 完了マイルストーンで grep ベースの ADR 違反検出を行うと再発防止になる。
- **lib と LoRAIro の error 構造化伝搬は文字列 prefix で疎結合に保つ** (Issue #42, ADR 0023 Phase 1.5): image-annotator-lib の `SafetyRefusalError` / `ContentPolicyRefusalError` を LoRAIro の `error_records` に伝搬する際、`UnifiedAnnotationResult.error` を `f"{ExceptionType}: {msg}"` 文字列にして LoRAIro 側で `startswith` 判定する方式を採用した。型を直接 import して `isinstance()` チェックすると、submodule pinning で lib 側 PR がマージ前に LoRAIro 側 import が壊れる、または bidirectional version coupling で submodule pointer bump タイミングが厳しくなる。文字列 prefix なら lib 側で例外型が増えても LoRAIro 側は prefix 一覧を更新するだけで済み、merge order 制約も緩やかになる。新しい error 種を追加する際は両側で prefix を ADR で合意し、`error_records.error_type` カラムにそのまま入れる慣習を守る。
- **SSoT スキーマ変更時は「読み取り側」だけでなく「送信側の値経路」も同時に切替える** (Issue #245, ADR 0023 Phase 1.11): Phase 1.11 で `Model.litellm_model_id` を UNIQUE NOT NULL registry key SSoT に昇格させた際、`get_models_by_litellm_ids` など読み取り側の lookup だけ切替えて、GUI → Worker → Logic → lib への送信値は `Model.name` のまま残してしまった。新規 sync 経路の行は `name == litellm_model_id` で偶然動くが、migration 経路 (例: `name='openai/gpt-4o', litellm_model_id='openrouter/openai/gpt-4o'`) では送信値が registry key に一致せず lookup miss する潜在バグになる。同種の SSoT 切替を行う際は (1) DB スキーマ変更、(2) 読み取り API 切替、(3) 内部キーの送信経路切替、(4) UX 上の disambiguation (GUI ラベル / CLI 入力解決) を必ず同じ ADR でセットにして実装する。GUI ラベルは `{name} ({provider})` 形式 + tooltip に正規 ID 併記、CLI は `litellm_model_id` 必須 + 曖昧マッチで Error + 候補一覧表示が定石。
