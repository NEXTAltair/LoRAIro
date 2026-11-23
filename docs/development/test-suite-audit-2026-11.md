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

対象は `local_packages/image-annotator-lib/tests`。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|

### genai-tag-db-tools

対象は `local_packages/genai-tag-db-tools/tests`。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|

## (d) CI の既定実行から外したテスト

該当なし。

## (e) 従わなかったルール・skill・hook

| ファイル | 該当箇所 | 従わなかった理由 | kit の Issue |
|---|---|---|---|
| `.claude/rules/planning-memory.md` | 「必須: 計画策定前の知識確認」(ADR 索引・教訓・最新計画をコード調査の前に確認) | ADR は索引でテスト関連 (0016 / 0024) の存在を確認するに留め、本文の通読は省いた。棚卸しの入力は計測ログであり、全 ADR の通読は baseline 計測の開始を遅らせるだけだった | 起票後に追記 |
| `.claude/rules/problem-solving.md` | 「調査の手順」3 (web で先行事例を探す) | fixture の scope 変更や DB の複製化は、計測ログで原因と効果を直接確かめられるため、web 調査を先に行わなかった | 起票後に追記 |
| superpowers `using-superpowers` skill | 「Invoke relevant or requested skills BEFORE any response or action」 | 実行ブリーフが手順と委譲方針を定めており、brainstorming / writing-plans を挟むと同じ内容を二重に作ることになるため起動しなかった | 起票後に追記 |

## #1632 の安全策

実装した PR の merge 後に、テスト名と使い方を追記する。

- 割当前の見積もりと拒否: image-annotator-lib の合成 ONNX モデル生成 (`tests/unit/fixtures/onnx_models.py::build_tagger_onnx`)。image-annotator-lib Issue #193
- プロセス群の後始末と終了コードの伝播: `scripts/run_bounded.py`

### コンテナのメモリ・スワップ制限 (設計のみ。今回は適用しない)

現状は制限が無い。cgroup v2 の `memory.max` と `memory.swap.max` はどちらも `max` で、`.devcontainer/devcontainer.json` の `runArgs` にメモリ指定は無い。コンテナ内の 1 プロセスが WSL の割当 (32 GiB + swap 8 GiB) を使い切ると、WSL 全体と Windows 側が巻き込まれる。

- 案: `runArgs` に `--memory=24g --memory-swap=24g` を足す。swap を同値にしてコンテナからの swap 使用を止め、超過時は WSL 全体の枯渇ではなくコンテナ内の OOM kill で終わらせる。WSL 側に 8 GiB を残す
- 既存ワークロードへの影響: GPU 推論 (ONNX / Transformers) の常駐と、llama-server (Clef) のモデル読み込みが同じコンテナで動く。24 GiB の根拠は今回のテスト計測 (最大 2.1 GiB) だけでは足りず、実運用のピーク (アノテーション実行中の RSS) の計測が先に必要
- 再作成の要否: `runArgs` の変更は dev container の再作成 (Rebuild) が必要。稼働中のコンテナには `docker update --memory` でも適用できるが、再作成すると消える
- 当面の策: 重い計測は `scripts/run_bounded.py --memory-limit-gb` でプロセス単位に上限を掛ける

## Follow-up

- `scripts/validate_docs.py` の全体実行が main で失敗する (`Service count mismatch: expected 70, found 72`)。今回の変更とは無関係
- `_prepare_project_database` は最新 revision の DB でも毎回 alembic upgrade を実行する (1 回 1.2〜1.6 秒、ローカル計測)。全 CLI コマンドとプロジェクト切替がこの時間を払う
- baseline 計測中、別セッション由来の image-annotator-lib の fork テストのプロセスが親を失って 4 時間以上残っていた (PPID 1)。テスト実行の後始末が効かない経路がある
- 古い main での S3 の初回計測で、CLI の cold 起動テストが 9p 上のディレクトリ読み取りの `[Errno 12] Cannot allocate memory` で 1 件失敗した。再計測では再現しなかった
