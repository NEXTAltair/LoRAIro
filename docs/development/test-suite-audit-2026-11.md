---
type: Report
title: テストスイート棚卸し台帳 (2026-11)
description: "3 repo のテストを棚卸しした記録。変更前の計測値、改善目標と根拠、削除・統合したテスト、CI から外したテスト、従わなかったルールを持つ (Issue #1632)"
status: active
timestamp: 2026-11-23
tags: [process, validation]
---
# テストスイート棚卸し台帳 (2026-11)

LoRAIro 本体と image-annotator-lib、genai-tag-db-tools のテストを棚卸しした記録。Issue #1632 の完了条件の証拠を兼ねる。
テスト方針として残す判断は [testing.md](../testing.md) に置き、この台帳は今回の計測値と変更の記録だけを持つ。

セッションの定義 (filter は `.github/workflows/ci.yml` と同じ):

| 記号 | 対象 | 実行場所 | path と `-m` |
|---|---|---|---|
| S1 | 本体 unit (GUI 除く) | repo root | `tests/unit --ignore=tests/unit/gui -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` |
| S2 | 本体 unit GUI | repo root | `tests/unit/gui -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` |
| S3 | 本体 integration + bdd | repo root | `tests/integration tests/bdd -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` |
| S4 | image-annotator-lib | `local_packages/image-annotator-lib` | `-m "not downloads_and_runs_model and not calls_real_webapi"` |
| S5 | genai-tag-db-tools | `local_packages/genai-tag-db-tools` | `-m "not slow and not network"` |

## (a) 変更前の baseline

| セッション | テスト件数 | wall time | ピーク RSS (KB) | 行カバレッジ |
|---|---|---|---|---|
| S1 | 4810 passed, 2 skipped, 3 deselected | 14:32.82 (873 秒) | 1,077,104 | 52.0% |
| S2 | 3549 passed | 4:21.27 (261 秒) | 1,828,044 | 68.1% |
| S3 | 561 passed, 1 deselected | 7:30.11 (450 秒) | 1,463,340 | 54.0% |
| S4 | 1418 passed, 16 deselected | 4:47.12 (287 秒) | 2,120,800 | 84.7% |
| S5 | 1049 passed | 3:17.80 (198 秒) | 525,276 | 87.2% |

S1〜S3 の coverage データを `coverage combine` した合算は 92.0%。

### 計測条件

- 日付: 2026-11-23。対象 commit: LoRAIro `ba5b0ce9`、image-annotator-lib `fc84da0`、genai-tag-db-tools `2f433ce`
- 環境: WSL2 上の dev container (割当メモリ 32 GiB、swap 8 GiB、32 論理 CPU)。repo は 9p (drvfs) の bind mount、`.venv` は ext4、pytest の一時ディレクトリ (`/tmp`) は overlay
- 1 セッションずつ直列に実行し、同時に他の pytest を動かさない。wall time とピーク RSS は GNU time 1.9 の `/usr/bin/time -v` (`Elapsed (wall clock) time` と `Maximum resident set size`)
- 実行形: `/usr/bin/time -v -o <file> timeout -k 30 3600 /workspaces/LoRAIro/.venv/bin/python -m pytest <上表の path と -m> <下記の追加引数>`
  - S1〜S3: `--cov=src --cov-fail-under=0 --timeout=<S1,S2 は 120 / S3 は 300> --timeout-method=thread -x`
  - S4: `--cov=image_annotator_lib --cov-fail-under=0`、S5: `--cov=src --cov-fail-under=0`
  - 共通: `--durations=0 -p no:cacheprovider --cov-report=term`、環境変数 `QT_QPA_PLATFORM=offscreen`、`COVERAGE_FILE` はセッションごとに別ファイル
  - CI の実行行との差は `--timeout-method=thread`、`--durations=0`、`-p no:cacheprovider` と coverage の出力形式だけ。path と `-m` は同じ
- 行カバレッジは `coverage report --precision=1` の TOTAL
- 各 1 回の値。ローカルは 9p と fsync の費用が大きく、CI (ubuntu-latest) より 3〜6 倍遅い。参考として、同日の main の CI では S1 の pytest 表示が 343 秒だった
- ばらつきの参考: 8 commit 古い main (`05ae4de7`) で同じ手順の S1 は 18:07、S2 は 4:36 だった

## (b) 改善目標と根拠

| セッション | wall time の目標 | ピーク RSS の目標 | 根拠にした主な見込み |
|---|---|---|---|
| S1 | 11:30 以下 (baseline 比 -21%) | baseline 以下 (1,077,104 KB) | CLI の subprocess 52 回起動の集約 (約 80 秒)、テストごとの DB 準備の複製化 (約 80 秒)、モジュール終端の `gc.collect()` の軽量化 (約 100 秒)、migration テストの upgrade 共有 (約 40 秒)、torch を読み込む subprocess の置き換え (約 11 秒) |
| S2 | 3:30 以下 (-20%) | baseline 以下 (1,828,044 KB) | `gc.collect()` の軽量化 (40〜50 秒)、ファイル DB の `create_all` (約 12 秒)、重い fixture の共有 (約 15 秒) |
| S3 | 5:00 以下 (-33%) | baseline 以下 (1,463,340 KB) | ファイル SQLite への `create_all` (0.73 秒 × 約 170 回 = 約 125 秒) の軽量化、CLI テストの alembic 再実行 (40〜50 秒)、`gc.collect()` (25〜30 秒)、cold 起動 subprocess の同時起動 (約 25 秒) |
| S4 | 3:50 以下 (-20%) | baseline 以下 (2,120,800 KB) | cold import の subprocess 約 10 本の集約 (約 70 秒)、モデル解放ごとの full GC の軽量化 (未計測の仮説) |
| S5 | 2:30 以下 (-24%) | baseline 以下 (525,276 KB) | テストごとのファイル DB 作成の複製化と、1 件ずつ commit するシードの一括化 (約 65 秒 + 35〜50 秒) |

目標の決め方:

- wall time は、棚卸しで特定した改善の見込み秒 (ログの実測秒からの見積もり) の合計の 6〜7 割を目標にした。見込みは未実測の推定を含むことと、ローカルの計測が 1 回で 2 割ほど揺れた実績があることから、見込みの全量は目標にしない
- ピーク RSS は「baseline を超えない」を目標にした。棚卸しでは、ピークの主因はテスト側の大きな割当ではなく、プロセスに常駐するネイティブライブラリ (S4 は tensorflow / torch / transformers の実 import、S2 は Qt) と分かり、検証内容を変えずに下げられる策を特定できなかったため。実装中にテスト側の原因 (巨大な画像の生成など) が見つかれば下げる
- メモリの事故防止は、ピーク RSS の削減ではなく #1632 の安全策 (割当前の見積もりと拒否、プロセス群の後始末、終了コードの伝播) で担保する
- 行カバレッジはセッションごとに baseline を下回らない。S1〜S3 の合算は 75% 以上 (`fail_under`) を保つ

## 変更後の実測

対象 commit: LoRAIro `e0a63777` (このゴールの PR をすべて merge した main)、image-annotator-lib `c9028ac`、genai-tag-db-tools `1fe7add`。計測条件と実行形は (a) と同じ。5 セッションを S5 → S4 → S3 → S2 → S1 の順に 1 本ずつ直列に実行し、全セッション exit 0。

| セッション | テスト件数 | wall time (目標) | ピーク RSS KB (baseline) | 行カバレッジ (baseline) |
|---|---|---|---|---|
| S1 | 4844 passed, 2 skipped, 3 deselected | 7:28.13 (11:30 以下) | 941,472 (1,077,104) | 52.1% (52.0%) |
| S2 | 3544 passed | 3:28.22 (3:30 以下)。3 回の中央値 | 1,737,392 (1,828,044) | 68.6% (68.1%) |
| S3 | 555 passed, 1 deselected | 4:06.53 (5:00 以下) | 925,464 (1,463,340) | 54.3% (54.0%) |
| S4 | 1402 passed, 16 deselected | 2:05.54 (3:50 以下) | 2,119,668 (2,120,800) | 84.7% (84.7%) |
| S5 | 1046 passed | 0:52.02 (2:30 以下) | 520,704 (525,276) | 87.2% (87.2%) |

S1〜S3 の合算カバレッジは 92.0% (baseline 92.0%)。

読み方の注意:

- **S2 の wall time は 3 回の中央値**。同じ commit で続けて 3 回計測した値は 3:28.22 / 3:55.53 / 3:24.48 (ピーク RSS は 1,737,392 / 1,738,496 / 1,737,688 KB、カバレッジは 3 回とも 68.6%)。目標との差 (数秒) より計測のばらつき (約 30 秒) が大きいため、中央値で判定した。2 回目は目標を超えている。計測中、同じマシンで別セッションの作業が動いており、load average は 3〜4 だった
- **S2 の目標は当初の見込みより厳しくなった**。目標 3:30 は、モジュール終端の `gc.collect()` を `gc.freeze()` で軽くする案の効果 (ローカルで teardown 54 → 23 秒) を見込んで決めた。この案は CI の Integration Tests がハングしたため採用しなかった (下記)。目標は変えず、ダイアログテストの DB 準備の複製化と、cold import を検査する子プロセスの先行起動 (PR #1640) を追加した
- **S2 のカバレッジ 68.6% は、対象の文数が baseline と違う**。変更後の S2 は alembic を一度も実行しないため、migration スクリプト (1,082 文。通常の import ではなく alembic が読み込む) が集計対象に現れない。baseline の S2 は GUI テストが実 DB の準備を通じて migration を実行しており、うち 376 文が実行済みだった。migration を除いた同じ範囲で比べると 68.7% → 68.6% で、未実行の文は `db_core.py` (+66)、`service_container.py` (+19)、`repository/model.py` (+7) などで 99 文増え、別のファイルで 70 文減った。増えた分は、GUI テストが実 ServiceContainer と実 project DB を構築しなくなったことによる (DB 層の検証は S1 と S3 にあり、合算の未実行文は migration を含めて baseline と同水準: 4,137 → 4,140、文数は別作業の機能追加で +112)。「GUI unit セッションが DB 層をついでに通っていた分が無くなった」という変化で、S2 単独の実行済み文数は 35,041 → 34,631 に減っている
- **S4 のピーク RSS は baseline との差が 0.05% しかない**。ピークは収集時の tensorflow / torch / transformers の実 import で決まり (収集完了時点で約 1.8 GB)、テスト側では下げられなかった。計測のたびに baseline を上回る可能性がある
- **ピーク RSS は 1 プロセスの最大値**。S3 と S4 は、cold 起動を検査する子プロセス 3〜4 本を同時に起動する形に変えたため、その間 (十数秒) は子プロセスの合計で 1.1〜1.3 GB を追加で使う。`/usr/bin/time` の値にはこの合計は現れない
- テスト件数の S1 の増加 (4810 → 4844) は、別作業の機能追加 (#1633) のテストと、`scripts/run_bounded.py` のテスト 7 件による

### 効いた変更

| 変更 | 対象 | 実測の効果 |
|---|---|---|
| テスト中の SQLite 接続に `PRAGMA synchronous=OFF` | 本体 `tests/conftest.py`、genai-tag-db-tools `tests/conftest.py` | ファイル DB への `create_all` が 1 回 0.64 → 0.019 秒。S5 は 3:18 → 0:52、S3 の setup 合計は 148 → 約 40 秒 |
| 子プロセス起動の集約 | 本体 `tests/unit/cli/test_exit_code_process.py` (52 回 → 3 回)、`test_cli_import_lightness.py`、lib の cold import 検査 | `test_exit_code_process.py` は 109 → 11 秒 |
| 準備済み DB の複製、alembic の `ScriptDirectory` の使い回し | 本体 unit / integration の CLI・public_api テスト | DB 準備の約 2 秒は、alembic が 9p 上の versions を毎回読み込む時間だった。1.3 → 0.12 秒 |
| 収集直後の `gc.collect(); gc.freeze()` | lib `tests/conftest.py` のみ | モデル解放系のテストが 1 件 0.85〜1 秒 → 0.15〜0.2 秒 |
| 破棄されないウィジェットの解放 | `tests/integration/test_main_window_tab_integration.py`、`tests/unit/gui/widgets/test_crop_dialog.py` | S3 のピーク RSS が 1.46 GB → 0.93 GB |
| 呼び出しを記録する `MagicMock` を回数だけ数える stub に | `tests/unit/test_dataset_export_all_formats.py` の 1 万件ケース | このケースの確保が約 160 MB → 7 MB。S1 のピーク RSS が 1.08 GB → 0.94 GB |

### 採用しなかった変更

- 本体の `tests/conftest.py` で収集直後に `gc.freeze()` を実行する案。ローカルでは teardown が S1 で 129 → 62 秒、S2 で 54 → 23 秒に減ったが、CI の Integration Tests が 15 分の上限でハングした (run 45116885766。メインスレッドが `ModelSelectionWidget.setupUi`、`SearchFacetsWorker` のスレッドが SQLAlchemy の処理中のまま停止し、#1077 / #1090 と同じ形)。因果は確定していないが、外した後は通っている
- 計測環境だけを速くする変更 (pytest の一時ディレクトリを tmpfs へ移すなど)。baseline と条件が変わるため行っていない

## (c) 削除・統合したテスト

分類は「陳腐化 / 重複 / 過剰エッジケース / 実装詳細の検証」。削除・統合を行った PR が、同じ PR でこの表に行を足す。

### 本体 unit (GUI 除く)

対象は `tests/unit` のうち `tests/unit/gui` を除いた部分。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| tests/unit/cli/test_exit_code_process.py::test_process_exit_contract の子プロセス 45 ケース (8 シナリオ × 3 状態 × json/no-json の 48 から代表 3 を除いたもの) | 重複 | 子プロセスで検証していたのは「シナリオと状態から main() が出す終了コード 0 / 3 / 1 と最終 JSON 行」で、同じ差し替えと argv で in-process の `main()` を呼べば同じ写像を検証できる。子プロセスでしか見えないのは interpreter の終了コードと実 stdout パイプだけで、代表 3 ケース (0 / 3 / 1、json と no-json を両方含む) で残した | 同ファイル::test_main_exit_contract (48 ケース全件、in-process) と ::test_process_exit_contract (代表 3 ケース、子プロセス)。シナリオ定義は `install_scenario()` 1 か所を両方が使う |
| tests/unit/cli/test_exit_code_process.py::test_maintenance_check_findings_still_exit_zero の子プロセス実行 (4 ケース) | 重複 | 「findings があっても exit 0」は main() の写像で、プロセス境界の終了コードは上の代表 3 ケースが確認する。テスト関数と 4 ケースの assert は残し、実行を in-process の `main()` に替えた | 同テスト (in-process) と ::test_process_exit_contract |
| tests/unit/public_api/test_types.py::TestExportCriteria::test_has_any_filter_score_min_zero_is_true | 重複 | 本体が ::test_has_any_filter_with_score_min と同一 (`ExportCriteria(score_min=0.0).has_any_filter() is True`)。残す側の docstring に「0.0 でも有効」とある | tests/unit/public_api/test_types.py::TestExportCriteria::test_has_any_filter_with_score_min |
| tests/unit/test_existing_file_reader.py::TestSidecarAnnotationReader::test_init | 陳腐化 | `assert reader is not None` だけ。コンストラクタは同クラスの全テストが呼ぶ | 同クラスの get_existing_annotations 系テスト |
| tests/unit/test_existing_file_reader.py::TestSidecarAnnotationReader::test_tag_cleaner_integration | 陳腐化 | 本体が test_init と同一で、名前の TagCleaner 連携を何も検証していない | 同上 |
| tests/unit/test_existing_file_reader.py::TestSidecarAnnotationReader::test_file_path_construction | 実装詳細の検証 | 対象メソッド自体を `patch.object` で差し替えて呼び、mock が呼ばれたことを確かめるだけで実装を通らない | 同上 |
| tests/unit/public_api/test_tags_api.py::TestGetUnknownTags::test_each_tag_has_type_name_unknown | 重複 | ::test_returns_tag_info_list_from_service が 2 件とも `type_name == "unknown"` と `count == 0` を assert 済み | tests/unit/public_api/test_tags_api.py::TestGetUnknownTags::test_returns_tag_info_list_from_service |
| tests/unit/public_api/test_tags_api.py::TestGetUnknownTags::test_each_tag_has_zero_count | 重複 | 同上 (`count == 0`) | 同上 |
| tests/unit/public_api/test_tags_api.py::TestGetAvailableTypes::test_delegates_to_tag_management_service | 重複 | `get_all_available_types.assert_called_once()` だけで、::test_returns_list_of_type_names が同じ assert と戻り値を検証済み | tests/unit/public_api/test_tags_api.py::TestGetAvailableTypes::test_returns_list_of_type_names |
| tests/unit/public_api/test_tags_api.py::TestGetAvailableTypes::test_returns_single_type | 重複 | 1 要素のリストを素通しするだけで、複数要素の ::test_returns_list_of_type_names と同じ分岐 | 同上 |
| tests/unit/database/test_db_repository_ai_rating_filter.py::TestApplyAIRatingFilter::test_apply_ai_rating_filter_case_insensitive | 陳腐化 | 3 通りの入力で `is not None` を見るだけ。`_apply_ai_rating_filter` は常に Select を返すので失敗しえない | tests/unit/database/test_db_repository_ai_rating_filter.py::TestApplyAIRatingFilter::test_apply_ai_rating_filter_creates_subqueries |
| tests/unit/database/test_db_repository_ai_rating_filter.py::TestApplyAIRatingFilter::test_apply_ai_rating_filter_all_rating_values | 陳腐化 | 5 値のループで `is not None` を見るだけ。値ごとの分岐は `_apply_ai_rating_filter` に無い | 同上 |
| tests/unit/test_dataset_export_service.py::TestDatasetExportService::test_initialization | 陳腐化 | fixture が mock で渡した属性 4 つに `is not None` を見るだけ | 同ファイルの export 系テスト (同じ fixture で同じコンストラクタを通る) |
| tests/unit/workers/test_database_related_workers.py::TestDatabaseRegistrationWorker::test_import_paths_are_correct | 陳腐化 | import して `is not None` を見るだけ。import できなければ同ファイルの他テストが先に失敗する | tests/unit/workers/test_database_related_workers.py::TestDatabaseRegistrationWorker::test_worker_execution_with_real_objects |
| tests/unit/database/test_image_repository_histogram.py::TestGetCreatedAtHistogram::test_empty_db_returns_empty_list | 重複 | 本体が「空 DB で `get_created_at_histogram(bins=10)` が `[]`」で tz の指定有無だけが違う。tz 省略の経路は同ファイルの他テストが通る | tests/unit/database/test_image_repository_created_at_filter.py::TestCreatedAtHistogram::test_empty_db_returns_empty_list |

### 本体 unit GUI

対象は `tests/unit/gui`。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| `tests/unit/gui/controllers/test_annotation_workflow_controller.py::TestStartAnnotationWorkflow::test_start_annotation_workflow_no_api_keys` | 陳腐化 | `get_api_keys` の戻り値を空にしているが、`AnnotationWorkflowController` は `get_api_keys` を呼ばない (`git grep get_api_keys src/lorairo/gui/controllers` が 0 件)。設定は効かず、経路は success テストと同じ。このテストが持っていた「callback に設定の利用可能モデル一覧が渡る」assert は success テストへ移した | 同ファイル `TestStartAnnotationWorkflow::test_start_annotation_workflow_success` |
| `tests/unit/gui/controllers/test_annotation_workflow_controller.py::TestStartAnnotationWorkflow::test_start_annotation_workflow_with_available_providers` | 陳腐化 | 上と同じく `get_api_keys` の設定は効かない。`len(available_models) >= 3` は fixture が返す固定 6 件の長さを見ているだけ (`_get_available_models` は config の戻り値をそのまま返す)。一覧が callback へ渡ることは、success テストが一覧そのものの一致で検証する | 同ファイル `TestStartAnnotationWorkflow::test_start_annotation_workflow_success` |
| `tests/unit/gui/widgets/test_error_notification_widget.py::TestErrorNotificationWidgetInit::test_has_clicked_signal` | 実装詳細の検証 | `hasattr(widget, "clicked")` のみ。同ファイルのテストが `qtbot.waitSignal(widget_no_db.clicked)` で実際の発火を確かめている | 同ファイル `TestErrorNotificationWidgetClickSignal::test_click_emits_signal` |
| `tests/unit/gui/widgets/test_model_selection_widget.py::TestModelSelectionWidgetInit::test_has_model_selection_changed_signal` | 実装詳細の検証 | `hasattr` のみ。発火は別テストが `qtbot.waitSignal(w.model_selection_changed)` で確かめている | 同ファイル `TestModelSelectionWidgetModelSelectionChanged::test_on_model_selection_changed_emits_signal` |
| `tests/unit/gui/widgets/test_image_preview_widget.py::TestImagePreviewWidget::test_load_image_clears_before_loading` | 実装詳細の検証 | 実装は `QImageReader` で読む (#1221/#1554) のに `QPixmap` を patch しており、検証は `_clear_preview` が呼ばれたことだけだった。読み込み前のクリアは、統合先のテストが「前の画像の表示と参照が残らない」という観察できる結果 (シーンの中身、`pixmap_item`、`_current_pixmap`、`_current_image_path`) で検証する | 同ファイル `test_load_image_error_after_valid_image_resets_scene_rect_and_centers` |

### 本体 integration + bdd

対象は `tests/integration` と `tests/bdd`。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| tests/integration/gui/test_widget_integration.py::TestWidgetSignalIntegration::test_filter_search_to_model_selection_signal_flow | 陳腐化 | Mock 同士をテスト内で `connect` し、`connect.assert_called_with` を見るだけ。src のコードを呼ばない | なし (src の検証を含まない) |
| tests/integration/gui/test_widget_integration.py::TestWidgetSignalIntegration::test_annotation_results_to_data_display_signal_flow | 陳腐化 | 同上 (Mock の自己検証) | なし |
| tests/integration/gui/test_widget_integration.py::TestWidgetSignalIntegration::test_status_filter_to_image_list_signal_flow | 陳腐化 | 同上 (Mock の自己検証) | なし |
| tests/integration/gui/test_widget_integration.py::TestMainWorkspaceIntegration::test_three_panel_layout_integration | 陳腐化 | テスト内で Mock の属性を作り、その `hasattr` を確かめるだけ | なし |
| tests/integration/gui/test_widget_integration.py::TestMainWorkspaceIntegration::test_end_to_end_annotation_workflow | 陳腐化 | テスト内で Mock のメソッドを呼び、その呼び出しを確かめるだけ | なし |
| tests/integration/gui/test_widget_integration.py::TestWidgetServiceIntegration::test_filter_search_panel_with_search_service_integration | 陳腐化 | パネルの UI 部品を Mock に差し替え、パネル側の処理をテスト内に書き直して実行している。実際に通る src は `create_search_conditions` / `create_search_preview` だけ | tests/unit/gui/services/test_search_filter_service.py::test_create_search_preview_comprehensive (解像度・重複除外の preview を同じ粒度で確認)、同ファイル内の ::test_search_filter_conditions_and_preview_integration |
| tests/integration/gui/test_widget_integration.py::TestWidgetServiceIntegration::test_custom_range_slider_date_mode_integration | 重複 | 日付モードとラベル長 10 文字の確認 | tests/unit/gui/widgets/test_custom_range_slider.py::test_set_date_range / ::test_date_mode_labels |
| tests/integration/gui/test_filter_search_integration.py::TestWidgetIntegration::test_custom_range_slider_date_mode | 重複 | CustomRangeSlider 単体の `set_date_range` | tests/unit/gui/widgets/test_custom_range_slider.py::test_set_date_range |
| tests/integration/gui/test_filter_search_integration.py::TestWidgetIntegration::test_custom_range_slider_numeric_mode | 重複 | CustomRangeSlider 単体の `set_range` | tests/unit/gui/widgets/test_custom_range_slider.py::test_set_range |
| tests/integration/gui/test_filter_search_integration.py::TestWidgetIntegration::test_range_slider_signal_emission | 重複 | `update_labels` が valueChanged を出すことの確認 | tests/unit/gui/widgets/test_custom_range_slider.py::test_signal_connections_mock (`update_labels` 後の発行) / ::test_value_changed_signal |
| tests/integration/gui/test_filter_search_integration.py::TestFilterSearchIntegration::test_error_handling_integration | 陳腐化 | 最後の assert が `len(results_received) >= 0` で常に真。docstring も検証できていないと書いている | なし (同じ `_on_search_requested` 経路は ::test_signal_flow_integration が通る) |
| tests/integration/test_main_window_tab_integration.py::TestSignalConnections::test_tab_changed_signal_connected | 陳腐化 | `hasattr(window, "_on_main_tab_changed")` だけ。コメントで接続の検証は省略と明記 | なし (currentChanged は同ファイルのタブ切替テストが実際に通る) |
| tests/integration/test_main_window_tab_integration.py::TestAnnotationControlVisibility::test_tab_changed_handler_exists | 重複 | 上と同じ `hasattr` の assert | なし |
| tests/integration/test_main_window_tab_integration.py::TestStatePreservation::test_dataset_state_manager_preserved_across_tabs | 陳腐化 | 同じ属性を 3 回読んで `is` で比べるだけで、タブ切替で変わり得ない | なし |
| tests/integration/test_main_window_tab_integration.py::TestBatchTagWidgetIntegration::test_batchtagaddwidget_exists | 重複 | `batch_tag_add_widget is not None` の確認 | 同ファイルの ::test_batchtagaddwidget_placeholder_replaced (同じ not None に加えて objectName と splitter 内の配置を確認) |
| tests/integration/gui/test_worker_coordination.py::TestWorkerSystemPerformance::test_memory_usage_stability | 陳腐化 | 末尾が `assert True` で、メモリについて何も確認していない | なし (SearchWorker.run は tests/unit/workers の SearchWorker テストが通る) |
| tests/integration/cli/test_dataset_cli.py::test_cli_show_prints_folders | 重複 | ::test_cli_exclude_dir_adds_to_default_exclusions と同じ取り込み (`--exclude-dir 3_skipme`) と `dataset show` を実行し、出力の別の行を確かめていた | 同ファイルの ::test_cli_exclude_dir_adds_to_default_exclusions_and_show_prints_folders に統合 (両方の assert を残した) |

### image-annotator-lib

対象は `local_packages/image-annotator-lib/tests` (image-annotator-lib PR #195)。parametrize をまとめた行を含み、テスト件数では 20 件。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| `tests/unit/core/test_lazy_torch_import.py::test_import_does_not_eager_load_torch` | 重複 | bare `import image_annotator_lib` 後の `torch` / `torchvision` (とその下位 module) の有無を見る。下位 module が居れば親 package も sys.modules に居るので、smoke の `torch, torchvision, transformers, onnxruntime, tensorflow` の判定の部分集合。cold import の subprocess 1 本 (約 10 秒) | tests/unit/test_import_smoke.py::test_import_image_annotator_lib_does_not_eager_load_heavy_deps |
| `tests/unit/detection/test_detection.py::test_detection_import_does_not_load_heavy_deps` | 重複 | `image_annotator_lib.detection` の import は package `__init__` を通るので、smoke と同じ cold import を別プロセスで払っていた (約 10 秒)。detection の import + `list_detectors()` 後の heavy 判定を smoke の同じ subprocess に移し、assert も移した (判定する module 集合は smoke 側の方が広い) | tests/unit/test_import_smoke.py::test_import_image_annotator_lib_does_not_eager_load_heavy_deps (`loaded["detection"] == []`) |
| `tests/unit/fast/test_model_errors.py::test_model_exceptions` | 陳腐化 | テスト内で `raise X` した例外を `pytest.raises(X)` で受けるだけで src を通らない。例外クラスは coverage の omit 対象 (`exceptions/*`) | (なし。例外は他のテストが実際に送出・捕捉している) |
| `tests/unit/fast/test_basic_error_handling.py::TestErrorHandling::test_model_exceptions[*] (7 件)` | 陳腐化 | 同上 (`raise exception_class(...)` を受けるだけ) | (なし) |
| `tests/unit/fast/test_basic_error_handling.py::TestErrorHandling::test_invalid_image_input` | 陳腐化 | `MagicMock().predict.side_effect = TypeError` を設定して呼び、同じ TypeError を確かめるだけ。src を通らない | (なし) |
| `tests/unit/fast/test_basic_error_handling.py::TestErrorHandling::test_memory_error_handling` | 陳腐化 | テスト内で定義した例外を投げて受けるだけ。src を通らない | (なし) |
| `tests/unit/standard/core/test_model_factory_unit.py::test_get_model_size_from_config_success` | 重複 | config_registry mock で 2.5 GB → 2560 MB、`assert_called_once_with` まで同一 | tests/unit/core/test_model_factory.py::test_get_model_size_from_config_success |
| `tests/unit/standard/core/test_model_factory_unit.py::test_get_model_size_from_config_not_found` | 重複 | KeyError → None の同じ分岐 | tests/unit/core/test_model_factory.py::test_get_model_size_from_config_not_in_config |
| `tests/unit/standard/core/test_model_factory_unit.py::test_save_size_to_config` | 重複 | 2048 MB → 2.0 GB を runtime cache に保存し system 側を呼ばない、の 4 assert まで同一 | tests/unit/core/test_model_factory.py::test_save_size_to_config_success |
| `tests/unit/standard/core/test_model_factory_unit.py::test_get_models_sorted_by_last_used` | 重複 | 最終使用時刻の古い順に並ぶ、の同じ分岐 | tests/unit/core/test_model_factory.py::test_get_models_sorted_by_last_used (空の場合は ::test_get_models_sorted_by_last_used_empty) |
| `tests/unit/standard/core/test_model_factory_unit.py::test_check_memory_before_load_sufficient` | 重複 | psutil の available が足りる場合に True の同じ分岐 | tests/unit/core/test_model_factory.py::test_check_memory_before_load_sufficient |
| `tests/unit/standard/core/test_model_factory_unit.py::test_check_memory_before_load_insufficient` | 重複 | available が足りない場合に False の同じ分岐 | tests/unit/core/test_model_factory.py::test_check_memory_before_load_insufficient |
| `tests/unit/core/test_model_factory.py::test_update_model_state_released` | 重複 | `status="released"` 後に状態・メモリ・最終使用が消えることを確かめる。standard 側は同じ手順を loaded から実行し、`_get_model_state is None` / `_get_model_memory_usage == 0.0` まで確かめる上位集合 | tests/unit/standard/core/test_model_factory_unit.py::test_update_model_state_released |
| `tests/unit/core/test_model_factory.py::test_release_model_state` | 重複 | 同じ 3 assert。standard 側はさらに `_MODEL_SIZES` が残ることも確かめる | tests/unit/standard/core/test_model_factory_unit.py::test_release_model_state |

### genai-tag-db-tools

対象は `local_packages/genai-tag-db-tools/tests` (genai-tag-db-tools PR #157)。3 件。このほか、名前と中身が食い違っていた 2 件を改名した (`test_convert_tag_returns_original_when_missing` → `test_convert_tag_is_deprecated_not_implemented`、`test_get_format_id_none_returns_zero` → `test_get_format_id_is_deprecated_not_implemented`)。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| `tests/unit/test_tag_searcher_service.py::test_convert_tag_uses_preferred_tag` | 重複 | `convert_tag` は常に NotImplementedError を出す廃止済みの関数。同一のコードと assert で、名前が示す動作は src に存在しない | `tests/unit/test_tag_searcher_service.py::test_convert_tag_is_deprecated_not_implemented` (旧名 `test_convert_tag_returns_original_when_missing` を改名) |
| `tests/unit/test_tag_searcher_service.py::test_convert_tag_skips_invalid_target` | 重複 | 同上 | `tests/unit/test_tag_searcher_service.py::test_convert_tag_is_deprecated_not_implemented` |
| `tests/unit/test_tag_searcher.py::test_convert_tag_is_not_implemented` | 重複 | 廃止済みの関数は reader を参照しないため、DB を作っても同じ例外を確かめているだけ | `tests/unit/test_tag_searcher_service.py::test_convert_tag_is_deprecated_not_implemented` |

## (d) CI の既定実行から外したテスト

該当なし。

## (e) 従わなかったルール・skill・hook

| ファイル | 該当箇所 | 従わなかった理由 | kit の Issue |
|---|---|---|---|
| `.claude/rules/planning-memory.md` | 「必須: 計画策定前の知識確認」(ADR 索引・教訓・最新計画をコード調査の前に確認) | ADR は索引でテスト関連 (0016 / 0024) の存在を確認するに留め、本文の通読は省いた。棚卸しの入力は計測ログであり、全 ADR の通読は baseline 計測の開始を遅らせるだけだった | NEXTAltair/altairs-agent-dev-kit#43 |
| `.claude/rules/problem-solving.md` | 「調査の手順」3 (web で先行事例を探す) | fixture の scope 変更や DB の複製化は、計測ログで原因と効果を直接確かめられるため、web 調査を先に行わなかった | NEXTAltair/altairs-agent-dev-kit#44 |
| superpowers `using-superpowers` skill | 「Invoke relevant or requested skills BEFORE any response or action」 | 実行ブリーフが手順と委譲方針を定めており、brainstorming / writing-plans を挟むと同じ内容を二重に作ることになるため起動しなかった | NEXTAltair/altairs-agent-dev-kit#45 |
| `.claude/rules/git-workflow.md` | 「完了の定義」6 と「クリーンアップ」(merge 後 worktree を `git worktree remove` で即削除) | submodule を初期化した worktree は `git worktree remove` が `fatal: working trees containing submodules cannot be moved or removed` で失敗する。merge のたびの即削除はせず、全 PR の merge 後に未コミット変更が無いことを確かめてまとめて削除した | NEXTAltair/altairs-agent-dev-kit#46 |
| `CLAUDE.md`「pr-autoloop の Claude Code 実装」/ `pr-autoloop` skill | 「1 ターン = 1 poll サイクル」「`ScheduleWakeup(delaySeconds=180)` で次サイクルを予約」 | 上限 80 ターンの実行で PR が 9 本あり、1 poll 1 ターンでは待機だけで上限に近づく。PR ごとに `gh pr checks --watch` と回数上限付きの待機ループをバックグラウンドで 1 本走らせ、完了通知で再開した。merge・修正・エスカレーションの判断基準は `pr-maintainer` に従った | NEXTAltair/altairs-agent-dev-kit#50 |
| `.claude/rules/git-workflow.md` / `issue-to-merge`・`worktree-workflow` skill | 実装着手時の skill の手順 | skill を起動せず、実行ブリーフの委譲方針 (領域ごとの worktree を先に作り、実装エージェントへ渡す) に従った。worktree の配置 (`.agents/worktree/` 配下の短い名前)・ブランチ・PR の方針はルールどおり | NEXTAltair/altairs-agent-dev-kit#45 |

## #1632 の安全策

| 安全策 | 実装 | 自動テスト |
|---|---|---|
| 割当前の見積もりと拒否 | image-annotator-lib `tests/unit/fixtures/onnx_models.py` の `estimate_tagger_onnx_bytes` と `build_tagger_onnx(max_bytes=...)` (image-annotator-lib Issue #193 / PR #194) | `tests/unit/fixtures/test_onnx_models_budget.py::test_oversized_model_is_rejected_before_allocation`、`::test_model_within_budget_is_built`、`::test_budget_can_be_raised_explicitly`、`::test_estimate_matches_incident_size` |
| タイムアウト時のプロセス群の後始末 | `scripts/run_bounded.py` (PR #1634) | `tests/unit/scripts/test_run_bounded.py::test_timeout_kills_whole_process_group`、`::test_downstream_process_group_is_cleaned_up`、`::test_normal_exit_returns_zero_and_cleans_leftover_grandchild`、`::test_target_start_failure_cleans_up_downstream` |
| パイプ越しの終了コードの伝播 | `scripts/run_bounded.py --pipe-to` (PR #1634) | `tests/unit/scripts/test_run_bounded.py::test_pipe_success_does_not_hide_upstream_failure` |

- 合成モデルの予算は既定 256 MiB。見積もりは float32 の重み (`3 × H × W × K × 4` バイト) の 8 倍で、生成中の float64 の一時領域と書き出し時のコピーを含む。予算は `max_bytes` 引数か環境変数 `IAL_TEST_SYNTHETIC_MODEL_BUDGET_BYTES` で明示的に引き上げた場合だけ広がる (意図的な大規模計測の opt-in)。事故時のサイズ (448 × 448、10000 タグ) は見積もりが約 180 GiB になり、既定の予算でも 16 GiB の予算でも重みの生成より前に拒否される
- `scripts/run_bounded.py` は対象を新しいプロセス群で起動し、タイムアウト (終了コード 124)・ラッパーへのシグナル・対象の終了後のいずれでも、群に残ったプロセスを SIGTERM → SIGKILL で止める。`--memory-limit-gb` はプロセスの `RLIMIT_AS` を設定する (`::test_memory_limit_rejects_oversized_allocation`)。`--pipe-to` の下流が成功しても、終了コードは対象のものを返す。使い方は [testing.md](../testing.md) の「上限付き実行 (run_bounded)」

### コンテナのメモリ・スワップ制限 (設計のみ。今回は適用しない)

現状は制限が無い。cgroup v2 の `memory.max` と `memory.swap.max` はどちらも `max` で、`.devcontainer/devcontainer.json` の `runArgs` にメモリ指定は無い。コンテナ内の 1 プロセスが WSL の割当 (32 GiB + swap 8 GiB) を使い切ると、WSL 全体と Windows 側が巻き込まれる。

- 案: `runArgs` に `--memory=24g --memory-swap=24g` を足す。swap を同値にしてコンテナからの swap 使用を止め、超過時は WSL 全体の枯渇ではなくコンテナ内の OOM kill で終わらせる。WSL 側に 8 GiB を残す
- 既存ワークロードへの影響: GPU 推論 (ONNX / Transformers) の常駐と、llama-server (Clef) のモデル読み込みが同じコンテナで動く。24 GiB の根拠は今回のテスト計測 (最大 2.1 GiB) だけでは足りず、実運用のピーク (アノテーション実行中の RSS) の計測が先に必要
- 再作成の要否: `runArgs` の変更は dev container の再作成 (Rebuild) が必要。稼働中のコンテナには `docker update --memory` でも適用できるが、再作成すると消える
- 当面の策: 重い計測は `scripts/run_bounded.py --memory-limit-gb` でプロセス単位に上限を掛ける

## Follow-up

- モジュール終端の `gc.collect()` (`tests/conftest.py::_collect_qt_wrappers_on_main_thread`) は、S1 で約 80 秒、S2 で約 50 秒の teardown を占める。`gc.freeze()` で軽くする案は CI のハングで見送った。安全に使える形があるかは、CI で繰り返し試す必要がある
- S2 は目標に対する余裕が無い (3 回の計測のうち 1 回は目標超過)。`tests/unit/gui/widgets/test_image_comparison_dialog.py` の fixture がテストごとに呼ぶ `gc.collect()` (約 4 秒) は意図を確認できず、手を付けていない
- `tests/unit/gui/conftest.py` は、cold import を検査する子プロセスを `pytest_collection_finish` で先に起動する (PR #1640)。conftest のフックからテストモジュールの関数を呼ぶ構造で、テスト単体の読みやすさは下がっている
- `tests/unit/cli/test_exit_code_process.py` の in-process 実行は、`main()` が立てる JSON 出力モードのグローバル変数を戻さない。今は失敗しないが、テスト順に依存しうる (PR #1635 のレビュー指摘)
- `tests/unit/conftest.py` の `_reuse_alembic_script_directory` は session scope なので、ローカルで `tests/` 全体を 1 回の pytest で回すと integration にも掛かったまま残る。CI はセッションを分けているので影響しない
- bdd の `test_crop_dialog_flow` は 2000 × 1500 の CropDialog が 15 シナリオで約 200 MB 積み上がる。`tests/unit/gui/tab/test_annotate_tab.py` (+276 MB) と `test_export_tab.py` (+171 MB) もモジュール終端の gc 後に常駐量が増える。原因は未調査
- CI の Integration Tests が PR #1638 で 1 回、`test_main_window_tab_integration.py` の fixture で MainWindow の構築中にハングし、15 分で打ち切られた。再実行で通った。この PR は integration のテストを変更していない
- image-annotator-lib の `mypy src/` は 69 件のエラーが出る (PR #194 の作業中に確認。今回の変更とは無関係)
- genai-tag-db-tools の `tests/unit/test_cli.py::test_build_register_service_returns_service` は mock の戻り値を assert しているだけだが、実関数を通る唯一のテストなので削除せず、書き直しの候補として残した
- 棚卸しで確信度「中」とした削除候補 (bdd と integration で重複する sidecar_import / crop_wiring、worker_coordination の 9 件など) は、突合が済んでいないため残した
- `scripts/validate_docs.py` の全体実行が main で失敗する (`Service count mismatch: expected 70, found 72`)。今回の変更とは無関係
- `_prepare_project_database` は最新 revision の DB でも毎回 alembic upgrade を実行する (1 回 1.2〜1.6 秒、ローカル計測)。全 CLI コマンドとプロジェクト切替がこの時間を払う
- baseline 計測中、別セッション由来の image-annotator-lib の fork テストのプロセスが親を失って 4 時間以上残っていた (PPID 1)。テスト実行の後始末が効かない経路がある
- 古い main での S3 の初回計測で、CLI の cold 起動テストが 9p 上のディレクトリ読み取りの `[Errno 12] Cannot allocate memory` で 1 件失敗した。再計測では再現しなかった
