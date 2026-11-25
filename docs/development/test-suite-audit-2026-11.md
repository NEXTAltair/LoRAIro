---
type: Report
title: テストスイート棚卸し台帳 (2026-11)
description: "3 repo のテストを棚卸しした記録。変更前の計測値、改善目標と根拠、削除・統合したテスト、CI から外したテスト、従わなかったルールを持つ (Issue #1632)"
status: active
timestamp: 2026-11-23
tags: [process, validation]
---

# テストスイート棚卸し台帳(2026-11)

LoRAIro 本体、`image-annotator-lib`、`genai-tag-db-tools` のテストを棚卸しした記録であり、Issue #1632 の完了条件の証跡を兼ねる。テスト方針として継続的に残す判断は [testing.md](../testing.md) に記載し、本台帳には今回の計測値と変更履歴のみを記録する。

### セッションの定義

各セッションのフィルタ条件は `.github/workflows/ci.yml` と同一である。

| 記号 | 対象 | 実行場所 | パスと `-m` |
|---|---|---|---|
| S1 | 本体 unit(GUI 除く) | repo root | `tests/unit --ignore=tests/unit/gui -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` |
| S2 | 本体 unit GUI | repo root | `tests/unit/gui -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` |
| S3 | 本体 integration + bdd | repo root | `tests/integration tests/bdd -m "not gui_show and not calls_real_webapi and not downloads_and_runs_model and not slow"` |
| S4 | image-annotator-lib | `local_packages/image-annotator-lib` | `-m "not downloads_and_runs_model and not calls_real_webapi"` |
| S5 | genai-tag-db-tools | `local_packages/genai-tag-db-tools` | `-m "not slow and not network"` |

## (a)変更前のベースライン

| セッション | テスト件数 | 経過時間(wall time) | ピーク RSS(KB) | 行カバレッジ |
|---|---|---|---|---|
| S1 | 4810 passed, 2 skipped, 3 deselected | 14:32.82(873 秒) | 1,077,104 | 52.0% |
| S2 | 3549 passed | 4:21.27(261 秒) | 1,828,044 | 68.1% |
| S3 | 561 passed, 1 deselected | 7:30.11(450 秒) | 1,463,340 | 54.0% |
| S4 | 1418 passed, 16 deselected | 4:47.12(287 秒) | 2,120,800 | 84.7% |
| S5 | 1049 passed | 3:17.80(198 秒) | 525,276 | 87.2% |

S1〜S3 のカバレッジデータを `coverage combine` で合算した値は 92.0% である。

### 計測条件

- **日付と対象コミット**: 2026-11-23。LoRAIro `ba5b0ce9`、`image-annotator-lib` `fc84da0`、`genai-tag-db-tools` `2f433ce`。
- **実行環境**: WSL2 上の dev container(割当メモリ 32 GiB、swap 8 GiB、32 論理 CPU)。リポジトリは 9p(drvfs)の bind mount、`.venv` は ext4、pytest の一時ディレクトリ(`/tmp`)は overlay である。
- **実行方法と計測ツール**: 1 セッションずつ直列に実行し、他の pytest と並行させない。経過時間とピーク RSS は GNU time 1.9 の `/usr/bin/time -v`(`Elapsed (wall clock) time` と `Maximum resident set size`)で計測した。
- **実行コマンド形式**: `/usr/bin/time -v -o <file> timeout -k 30 3600 /workspaces/LoRAIro/.venv/bin/python -m pytest <上表の path と -m> <下記の追加引数>`
  - S1〜S3: `--cov=src --cov-fail-under=0 --timeout=<S1,S2 は 120 / S3 は 300> --timeout-method=thread -x`
  - S4: `--cov=image_annotator_lib --cov-fail-under=0`、S5: `--cov=src --cov-fail-under=0`
  - 共通: `--durations=0 -p no:cacheprovider --cov-report=term`、環境変数 `QT_QPA_PLATFORM=offscreen`、`COVERAGE_FILE` はセッションごとに別ファイルを指定した。
  - CI の実行行との差は `--timeout-method=thread`、`--durations=0`、`-p no:cacheprovider`、およびカバレッジ出力形式のみであり、パスと `-m` は同じである。
- **行カバレッジ**: `coverage report --precision=1` の TOTAL 値を採用した。
- **環境差とばらつき**: 各 1 回の計測値である。ローカル環境は 9p と fsync のコストが大きく、CI(ubuntu-latest)より 3〜6 倍遅い。参考として同日の main の CI では S1 の pytest 表示が 343 秒だった。また、8 コミット古い main(`05ae4de7`)で同手順を実行した際は S1 が 18:07、S2 が 4:36 だった。

## (b)改善目標と根拠

| セッション | 経過時間の目標 | ピーク RSS の目標 | 根拠とした主な見込み |
|---|---|---|---|
| S1 | 11:30 以下(ベースライン比 -21%) | ベースライン以下(1,077,104 KB) | CLI サブプロセス 52 回起動の集約(約 80 秒)、テストごとの DB 準備の複製化(約 80 秒)、モジュール終端の `gc.collect()` 軽量化(約 100 秒)、マイグレーションテストの upgrade 共有(約 40 秒)、torch を読み込むサブプロセスの置き換え(約 11 秒) |
| S2 | 3:30 以下(-20%) | ベースライン以下(1,828,044 KB) | `gc.collect()` の軽量化(40〜50 秒)、ファイル DB の `create_all`(約 12 秒)、重いフィクスチャの共有(約 15 秒) |
| S3 | 5:00 以下(-33%) | ベースライン以下(1,463,340 KB) | ファイル SQLite への `create_all`(0.73 秒 × 約 170 回 = 約 125 秒)の軽量化、CLI テストの Alembic 再実行(40〜50 秒)、`gc.collect()`(25〜30 秒)、cold 起動サブプロセスの同時起動(約 25 秒) |
| S4 | 3:50 以下(-20%) | ベースライン以下(2,120,800 KB) | cold import サブプロセス約 10 本の集約(約 70 秒)、モデル解放ごとの full GC の軽量化(未計測の仮説) |
| S5 | 2:30 以下(-24%) | ベースライン以下(525,276 KB) | テストごとのファイル DB 作成の複製化と、1 件ずつ commit するシードの一括化(約 65 秒 + 35〜50 秒) |

### 目標の決め方

- **経過時間**: 棚卸しで特定した改善見込み秒数(ログの実測秒からの見積もり)の合計に対し、6〜7 割を目標とした。見込みに未実測の推定が含まれる点と、ローカル計測が 1 回で 2 割ほど揺れた実績を考慮し、見込みの全量は目標に据えていない。
- **ピーク RSS**: 「ベースラインを超えないこと」を目標とした。棚卸しの結果、ピークの主因はテスト側の大きな割り当てではなく、プロセスに常駐するネイティブライブラリ(S4 は tensorflow、torch、transformers の実 import、S2 は Qt)であると判明し、検証内容を変えずに削減する策を特定できなかったためである。実装中に巨大な画像生成などテスト側の原因が見つかった場合は個別に削減する。
- **メモリ事故防止**: ピーク RSS の削減ではなく、#1632 の安全策(割り当て前の見積もりと拒否、プロセス群の後始末、終了コードの伝播)で担保する。
- **行カバレッジ**: セッションごとにベースラインを下回らないこととし、S1〜S3 の合算は 75% 以上(`fail_under`)を維持する。

## 変更後の実測

対象コミットは LoRAIro `e0a63777`(このゴールの PR をすべてマージした main)、`image-annotator-lib` `c9028ac`、`genai-tag-db-tools` `1fe7add` である。計測条件と実行コマンド形式は(a)と同一とし、5 セッションを S5 → S4 → S3 → S2 → S1 の順に 1 本ずつ直列実行して全セッションが終了コード 0 で完了した。

| セッション | テスト件数 | 経過時間(目標) | ピーク RSS KB(ベースライン) | 行カバレッジ(ベースライン) |
|---|---|---|---|---|
| S1 | 4844 passed, 2 skipped, 3 deselected | 7:28.13(11:30 以下) | 941,472(1,077,104) | 52.1%(52.0%) |
| S2 | 3544 passed | 3:28.22(3:30 以下)。3 回の中央値 | 1,737,392(1,828,044) | 68.6%(68.1%) |
| S3 | 555 passed, 1 deselected | 4:06.53(5:00 以下) | 925,464(1,463,340) | 54.3%(54.0%) |
| S4 | 1402 passed, 16 deselected | 2:05.54(3:50 以下) | 2,119,668(2,120,800) | 84.7%(84.7%) |
| S5 | 1046 passed | 0:52.02(2:30 以下) | 520,704(525,276) | 87.2%(87.2%) |

S1〜S3 の合算カバレッジは 92.0%(ベースライン 92.0%)である。

### 実測値の読み方に関する注意点

- **S2 の経過時間は 3 回の中央値である**: 同じコミットで連続 3 回計測したところ、3:28.22、3:55.53、3:24.48 となった(ピーク RSS は 1,737,392、1,738,496、1,737,688 KB、カバレッジはいずれも 68.6%)。目標との差(数秒)より計測のばらつき(約 30 秒)が大きいため中央値で判定した。2 回目は目標を超過している。なお、計測中は同一マシン上で別セッションの作業が動作しており、load average は 3〜4 だった。
- **S2 の目標は当初の見込みより厳しくなった**: 目標 3:30 は、モジュール終端の `gc.collect()` を `gc.freeze()` で軽量化する案(ローカルで teardown が 54 秒から 23 秒へ短縮)を見込んで設定した。しかし CI の Integration Tests がハングしたためこの案は不採用とした(詳細は後述)。目標値は変えず、ダイアログテストの DB 準備の複製化と、cold import を検査する子プロセスの先行起動(PR #1640)を追加した。
- **S2 のカバレッジ 68.6% は対象文数がベースラインと異なる**: 変更後の S2 では Alembic を一度も実行しないため、マイグレーションスクリプト(1,082 文。通常の import ではなく Alembic が読み込む)が集計対象に現れない。ベースラインの S2 では GUI テストが実 DB の準備を通じてマイグレーションを実行しており、そのうち 376 文が実行済みだった。マイグレーションを除いた同一範囲で比較すると 68.7% から 68.6% であり、未実行文は `db_core.py`(+66)、`service_container.py`(+19)、`repository/model.py`(+7)などで 99 文増えた一方、別ファイルで 70 文減った。増加分は GUI テストが実 `ServiceContainer` と実プロジェクト DB を構築しなくなったことによる。DB 層の検証は S1 と S3 で実施しており、合算の未実行文はマイグレーションを含めてベースラインと同水準である(4,137 → 4,140。総文数は別作業の機能追加で +112)。「GUI unit セッションが DB 層をついでに通過していた分がなくなった」変化であり、S2 単独の実行済み文数は 35,041 から 34,631 へ減っている。
- **S4 のピーク RSS はベースラインと 0.05% しか差がない**: ピーク値はテスト収集時の tensorflow、torch、transformers の実 import で決まる(収集完了時点で約 1.8 GB)ためテスト側では下げられず、計測のたびにベースラインを上回る可能性がある。
- **ピーク RSS は単一プロセスの最大値である**: S3 と S4 では cold 起動を検査する子プロセス 3〜4 本を同時起動する方式へ変更した。そのため、その間(十数秒)は子プロセス合計で 1.1〜1.3 GB を追加消費するが、`/usr/bin/time` の計測値にはこの合計は含まれない。
- **S1 のテスト件数増加(4810 → 4844)**: 別作業の機能追加(#1633)のテストと、`scripts/run_bounded.py` のテスト 6 件が加わったことによる。

### 効果があった変更

| 変更 | 対象 | 実測の効果 |
|---|---|---|
| テスト中の SQLite 接続へ `PRAGMA synchronous=OFF` を適用 | 本体 `tests/conftest.py`、`genai-tag-db-tools` `tests/conftest.py` | ファイル DB への `create_all` が 1 回あたり 0.64 秒から 0.019 秒へ短縮。S5 は 3:18 から 0:52、S3 の setup 合計は 148 秒から約 40 秒へ短縮 |
| 子プロセス起動の集約 | 本体 `tests/unit/cli/test_exit_code_process.py`(52 回 → 3 回)、`test_cli_import_lightness.py`、lib の cold import 検査 | `test_exit_code_process.py` が 109 秒から 11 秒へ短縮 |
| 準備済み DB の複製と Alembic `ScriptDirectory` の使い回し | 本体 unit・integration の CLI および `public_api` テスト | DB 準備の約 2 秒は Alembic が 9p 上の versions を毎回読み込む時間だった。1.3 秒から 0.12 秒へ短縮 |
| 収集直後の `gc.collect(); gc.freeze()` | lib `tests/conftest.py` のみ | モデル解放系テストが 1 件あたり 0.85〜1 秒から 0.15〜0.2 秒へ短縮 |
| 破棄されないウィジェットの解放 | `tests/integration/test_main_window_tab_integration.py`、`tests/unit/gui/widgets/test_crop_dialog.py` | S3 のピーク RSS が 1.46 GB から 0.93 GB へ削減 |
| 呼び出しを記録する `MagicMock` を回数のみ数える stub へ変更 | `tests/unit/test_dataset_export_all_formats.py` の 1 万件ケース | 該当ケースの確保メモリが約 160 MB から 7 MB へ削減。S1 のピーク RSS が 1.08 GB から 0.94 GB へ削減 |

### 採用しなかった変更

- **本体の `tests/conftest.py` で収集直後に `gc.freeze()` を実行する案**: ローカルでは teardown が S1 で 129 秒から 62 秒、S2 で 54 秒から 23 秒へ短縮されたが、CI の Integration Tests が 15 分の上限でハングした(run 45116885766。メインスレッドが `ModelSelectionWidget.setupUi`、`SearchFacetsWorker` のスレッドが SQLAlchemy の処理中で停止し、#1077 および #1090 と同じ症状だった)。因果関係は確定していないが、この変更を外した後は通過している。
- **計測環境だけを高速化する変更**: pytest の一時ディレクトリを tmpfs へ移すなどの変更は、ベースラインと計測条件が変わるため実施していない。

## (c)削除・統合したテスト

分類は「陳腐化」「重複」「過剰エッジケース」「実装詳細の検証」の 4 種とする。削除または統合を行った PR が、同一 PR 内で本表に行を追記する運用とした。

### 本体 unit(GUI 除く)

対象は `tests/unit` のうち `tests/unit/gui` を除いた範囲である。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| tests/unit/cli/test_exit_code_process.py::test_process_exit_contract の子プロセス 45 ケース(8 シナリオ × 3 状態 × json/no-json の 48 から代表 3 を除いたもの) | 重複 | 子プロセスで検証していたのは「シナリオと状態から `main()` が出す終了コード 0 / 3 / 1 と最終 JSON 行」であり、同じ差し替えと argv で in-process の `main()` を呼べば同一の写像を検証できる。子プロセスでしか見えないインタープリターの終了コードと実 stdout パイプは代表 3 ケース(0 / 3 / 1、json と no-json を両方含む)で残した | 同ファイル::test_main_exit_contract(48 ケース全件、in-process)と ::test_process_exit_contract(代表 3 ケース、子プロセス)。シナリオ定義は `install_scenario()` 1 か所を両方が共有する |
| tests/unit/cli/test_exit_code_process.py::test_maintenance_check_findings_still_exit_zero の子プロセス実行(4 ケース) | 重複 | 「findings があっても exit 0」は `main()` の写像であり、プロセス境界の終了コードは上の代表 3 ケースで確認している。テスト関数と 4 ケースのアサーションは残し、実行を in-process の `main()` へ切り替えた | 同テスト(in-process)と ::test_process_exit_contract |
| tests/unit/public_api/test_types.py::TestExportCriteria::test_has_any_filter_score_min_zero_is_true | 重複 | 本体が `::test_has_any_filter_with_score_min` と同一(`ExportCriteria(score_min=0.0).has_any_filter() is True`)であり、残す側の docstring にも「0.0 でも有効」と明記されている | tests/unit/public_api/test_types.py::TestExportCriteria::test_has_any_filter_with_score_min |
| tests/unit/test_existing_file_reader.py::TestSidecarAnnotationReader::test_init | 陳腐化 | `assert reader is not None` のみであり、コンストラクタは同クラスの全テストが呼んでいる | 同クラスの `get_existing_annotations` 系テスト |
| tests/unit/test_existing_file_reader.py::TestSidecarAnnotationReader::test_tag_cleaner_integration | 陳腐化 | 本体が `test_init` と同一であり、名前にある `TagCleaner` 連携を何も検証していない | 同上 |
| tests/unit/test_existing_file_reader.py::TestSidecarAnnotationReader::test_file_path_construction | 実装詳細の検証 | 対象メソッド自体を `patch.object` で差し替えて呼び出し、モックが呼ばれたことだけを確認しており実装を通らない | 同上 |
| tests/unit/public_api/test_tags_api.py::TestGetUnknownTags::test_each_tag_has_type_name_unknown | 重複 | `::test_returns_tag_info_list_from_service` が 2 件とも `type_name == "unknown"` と `count == 0` を検証済みである | tests/unit/public_api/test_tags_api.py::TestGetUnknownTags::test_returns_tag_info_list_from_service |
| tests/unit/public_api/test_tags_api.py::TestGetUnknownTags::test_each_tag_has_zero_count | 重複 | 同上(`count == 0`) | 同上 |
| tests/unit/public_api/test_tags_api.py::TestGetAvailableTypes::test_delegates_to_tag_management_service | 重複 | `get_all_available_types.assert_called_once()` のみであり、`::test_returns_list_of_type_names` が同じ検証と戻り値確認を実施済みである | tests/unit/public_api/test_tags_api.py::TestGetAvailableTypes::test_returns_list_of_type_names |
| tests/unit/public_api/test_tags_api.py::TestGetAvailableTypes::test_returns_single_type | 重複 | 1 要素のリストを素通しするだけであり、複数要素の `::test_returns_list_of_type_names` と同じ分岐を通る | 同上 |
| tests/unit/database/test_db_repository_ai_rating_filter.py::TestApplyAIRatingFilter::test_apply_ai_rating_filter_case_insensitive | 陳腐化 | 3 通りの入力で `is not None` を確認するのみである。`_apply_ai_rating_filter` は常に `Select` を返すため失敗しえない | tests/unit/database/test_db_repository_ai_rating_filter.py::TestApplyAIRatingFilter::test_apply_ai_rating_filter_creates_subqueries |
| tests/unit/database/test_db_repository_ai_rating_filter.py::TestApplyAIRatingFilter::test_apply_ai_rating_filter_all_rating_values | 陳腐化 | 5 値のループで `is not None` を確認するのみであり、値ごとの分岐は `_apply_ai_rating_filter` に存在しない | 同上 |
| tests/unit/test_dataset_export_service.py::TestDatasetExportService::test_initialization | 陳腐化 | フィクスチャがモックで渡した属性 4 つに対して `is not None` を確認するのみである | 同ファイルの export 系テスト(同じフィクスチャで同じコンストラクタを通る) |
| tests/unit/workers/test_database_related_workers.py::TestDatabaseRegistrationWorker::test_import_paths_are_correct | 陳腐化 | import して `is not None` を確認するのみであり、import できなければ同ファイルの他テストが先に失敗する | tests/unit/workers/test_database_related_workers.py::TestDatabaseRegistrationWorker::test_worker_execution_with_real_objects |
| tests/unit/database/test_image_repository_histogram.py::TestGetCreatedAtHistogram::test_empty_db_returns_empty_list | 重複 | 本体が「空 DB で `get_created_at_histogram(bins=10)` が `[]`」であり、`tz` 指定の有無しか違わない。`tz` 省略経路は同ファイルの他テストが通過する | tests/unit/database/test_image_repository_created_at_filter.py::TestCreatedAtHistogram::test_empty_db_returns_empty_list |

### 本体 unit GUI

対象は `tests/unit/gui` である。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| `tests/unit/gui/controllers/test_annotation_workflow_controller.py::TestStartAnnotationWorkflow::test_start_annotation_workflow_no_api_keys` | 陳腐化 | `get_api_keys` の戻り値を空に設定しているが、`AnnotationWorkflowController` は `get_api_keys` を呼ばない(`git grep get_api_keys src/lorairo/gui/controllers` が 0 件)。設定は効かず経路は success テストと同一である。callback に利用可能モデル一覧が渡る検証は success テストへ移した | 同ファイル `TestStartAnnotationWorkflow::test_start_annotation_workflow_success` |
| `tests/unit/gui/controllers/test_annotation_workflow_controller.py::TestStartAnnotationWorkflow::test_start_annotation_workflow_with_available_providers` | 陳腐化 | 上と同じく `get_api_keys` の設定は効かない。`len(available_models) >= 3` はフィクスチャが返す固定 6 件の長さを見ているだけである(`_get_available_models` は config の戻り値をそのまま返す)。一覧が callback へ渡ることは success テストが一覧の一致で検証する | 同ファイル `TestStartAnnotationWorkflow::test_start_annotation_workflow_success` |
| `tests/unit/gui/widgets/test_error_notification_widget.py::TestErrorNotificationWidgetInit::test_has_clicked_signal` | 実装詳細の検証 | `hasattr(widget, "clicked")` のみである。同ファイルのテストが `qtbot.waitSignal(widget_no_db.clicked)` で実際の発火を確認している | 同ファイル `TestErrorNotificationWidgetClickSignal::test_click_emits_signal` |
| `tests/unit/gui/widgets/test_model_selection_widget.py::TestModelSelectionWidgetInit::test_has_model_selection_changed_signal` | 実装詳細の検証 | `hasattr` のみである。実際の発火は別テストが `qtbot.waitSignal(w.model_selection_changed)` で確認している | 同ファイル `TestModelSelectionWidgetModelSelectionChanged::test_on_model_selection_changed_emits_signal` |
| `tests/unit/gui/widgets/test_image_preview_widget.py::TestImagePreviewWidget::test_load_image_clears_before_loading` | 実装詳細の検証 | 実装は `QImageReader` で読み込む(#1221 / #1554)にもかかわらず `QPixmap` をパッチしており、検証も `_clear_preview` の呼び出しだけだった。読み込み前のクリアは、統合先テストが「前の画像の表示と参照が残らない」という観察可能な結果(シーンの中身、`pixmap_item`、`_current_pixmap`、`_current_image_path`)で検証する | 同ファイル `test_load_image_error_after_valid_image_resets_scene_rect_and_centers` |

### 本体 integration + bdd

対象は `tests/integration` と `tests/bdd` である。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| tests/integration/gui/test_widget_integration.py::TestWidgetSignalIntegration::test_filter_search_to_model_selection_signal_flow | 陳腐化 | テスト内で Mock 同士を `connect` し、`connect.assert_called_with` を確認するのみで `src` のコードを呼ばない | なし(`src` の検証を含まない) |
| tests/integration/gui/test_widget_integration.py::TestWidgetSignalIntegration::test_annotation_results_to_data_display_signal_flow | 陳腐化 | 同上(Mock の自己検証) | なし |
| tests/integration/gui/test_widget_integration.py::TestWidgetSignalIntegration::test_status_filter_to_image_list_signal_flow | 陳腐化 | 同上(Mock の自己検証) | なし |
| tests/integration/gui/test_widget_integration.py::TestMainWorkspaceIntegration::test_three_panel_layout_integration | 陳腐化 | テスト内で Mock の属性を作り、その `hasattr` を確認するのみである | なし |
| tests/integration/gui/test_widget_integration.py::TestMainWorkspaceIntegration::test_end_to_end_annotation_workflow | 陳腐化 | テスト内で Mock のメソッドを呼び、その呼び出しを確認するのみである | なし |
| tests/integration/gui/test_widget_integration.py::TestWidgetServiceIntegration::test_filter_search_panel_with_search_service_integration | 陳腐化 | パネルの UI 部品を Mock へ差し替え、パネル側の処理をテスト内に書き直して実行している。実際に通る `src` は `create_search_conditions` と `create_search_preview` のみである | tests/unit/gui/services/test_search_filter_service.py::test_create_search_preview_comprehensive(解像度・重複除外のプレビューを同粒度で確認)、同ファイル内の `::test_search_filter_conditions_and_preview_integration` |
| tests/integration/gui/test_widget_integration.py::TestWidgetServiceIntegration::test_custom_range_slider_date_mode_integration | 重複 | 日付モードとラベル長 10 文字の確認が重複している | tests/unit/gui/widgets/test_custom_range_slider.py::test_set_date_range / `::test_date_mode_labels` |
| tests/integration/gui/test_filter_search_integration.py::TestWidgetIntegration::test_custom_range_slider_date_mode | 重複 | `CustomRangeSlider` 単体の `set_date_range` の重複 | tests/unit/gui/widgets/test_custom_range_slider.py::test_set_date_range |
| tests/integration/gui/test_filter_search_integration.py::TestWidgetIntegration::test_custom_range_slider_numeric_mode | 重複 | `CustomRangeSlider` 単体の `set_range` の重複 | tests/unit/gui/widgets/test_custom_range_slider.py::test_set_range |
| tests/integration/gui/test_filter_search_integration.py::TestWidgetIntegration::test_range_slider_signal_emission | 重複 | `update_labels` が `valueChanged` を送出することの確認が重複している | tests/unit/gui/widgets/test_custom_range_slider.py::test_signal_connections_mock(`update_labels` 後の発行) / `::test_value_changed_signal` |
| tests/integration/gui/test_filter_search_integration.py::TestFilterSearchIntegration::test_error_handling_integration | 陳腐化 | 末尾の検証が `len(results_received) >= 0` で常に真となる。docstring にも検証できていない旨が書かれている | なし(同じ `_on_search_requested` 経路は `::test_signal_flow_integration` が通る) |
| tests/integration/test_main_window_tab_integration.py::TestSignalConnections::test_tab_changed_signal_connected | 陳腐化 | `hasattr(window, "_on_main_tab_changed")` のみであり、コメントに接続検証は省略すると明記されている | なし(`currentChanged` は同ファイルのタブ切替テストが実際に通る) |
| tests/integration/test_main_window_tab_integration.py::TestAnnotationControlVisibility::test_tab_changed_handler_exists | 重複 | 上と同一の `hasattr` 検証である | なし |
| tests/integration/test_main_window_tab_integration.py::TestStatePreservation::test_dataset_state_manager_preserved_across_tabs | 陳腐化 | 同じ属性を 3 回読んで `is` で比較するだけであり、タブ切替によって変わり得ない | なし |
| tests/integration/test_main_window_tab_integration.py::TestBatchTagWidgetIntegration::test_batchtagaddwidget_exists | 重複 | `batch_tag_add_widget is not None` の確認が重複している | 同ファイルの `::test_batchtagaddwidget_placeholder_replaced`(同じ not None に加え `objectName` と splitter 内の配置を確認) |
| tests/integration/gui/test_worker_coordination.py::TestWorkerSystemPerformance::test_memory_usage_stability | 陳腐化 | 末尾が `assert True` であり、メモリについて何も確認していない | なし(`SearchWorker.run` は `tests/unit/workers` の `SearchWorker` テストが通る) |
| tests/integration/cli/test_dataset_cli.py::test_cli_show_prints_folders | 重複 | `::test_cli_exclude_dir_adds_to_default_exclusions` と同じ取り込み(`--exclude-dir 3_skipme`)および `dataset show` を実行し、出力の別の行を確認していた | 同ファイルの `::test_cli_exclude_dir_adds_to_default_exclusions_and_show_prints_folders` へ統合(両方の検証を残した) |

### image-annotator-lib

対象は `local_packages/image-annotator-lib/tests`(image-annotator-lib PR #195)である。parametrize をまとめた行を含み、テスト件数としては 20 件である。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| `tests/unit/core/test_lazy_torch_import.py::test_import_does_not_eager_load_torch` | 重複 | `import image_annotator_lib` 後の `torch`・`torchvision`(および下位モジュール)の有無を確認する。下位モジュールがあれば親パッケージも `sys.modules` に入るため、smoke の `torch, torchvision, transformers, onnxruntime, tensorflow` 判定の部分集合となる。cold import のサブプロセス 1 本(約 10 秒)を削減した | tests/unit/test_import_smoke.py::test_import_image_annotator_lib_does_not_eager_load_heavy_deps |
| `tests/unit/detection/test_detection.py::test_detection_import_does_not_load_heavy_deps` | 重複 | `image_annotator_lib.detection` の import はパッケージ `__init__` を通るため、smoke と同じ cold import コストを別プロセスで払っていた(約 10 秒)。detection の import と `list_detectors()` 後の重い依存判定を smoke の同一サブプロセスへ移し、検証も移植した(判定対象モジュール集合は smoke 側の方が広い) | tests/unit/test_import_smoke.py::test_import_image_annotator_lib_does_not_eager_load_heavy_deps(`loaded["detection"] == []`) |
| `tests/unit/fast/test_model_errors.py::test_model_exceptions` | 陳腐化 | テスト内で `raise X` した例外を `pytest.raises(X)` で受けるだけで `src` を通らない。例外クラスはカバレッジの除外対象(`exceptions/*`)である | なし(例外は他のテストが実際に送出・捕捉している) |
| `tests/unit/fast/test_basic_error_handling.py::TestErrorHandling::test_model_exceptions[*]`(7 件) | 陳腐化 | 同上(`raise exception_class(...)` を受けるだけ) | なし |
| `tests/unit/fast/test_basic_error_handling.py::TestErrorHandling::test_invalid_image_input` | 陳腐化 | `MagicMock().predict.side_effect = TypeError` を設定して呼び出し、同じ `TypeError` を確認するだけで `src` を通らない | なし |
| `tests/unit/fast/test_basic_error_handling.py::TestErrorHandling::test_memory_error_handling` | 陳腐化 | テスト内で定義した例外を送出して受けるだけで `src` を通らない | なし |
| `tests/unit/standard/core/test_model_factory_unit.py::test_get_model_size_from_config_success` | 重複 | `config_registry` モックで 2.5 GB → 2560 MB、`assert_called_once_with` まで同一である | tests/unit/core/test_model_factory.py::test_get_model_size_from_config_success |
| `tests/unit/standard/core/test_model_factory_unit.py::test_get_model_size_from_config_not_found` | 重複 | `KeyError` → `None` の同じ分岐である | tests/unit/core/test_model_factory.py::test_get_model_size_from_config_not_in_config |
| `tests/unit/standard/core/test_model_factory_unit.py::test_save_size_to_config` | 重複 | 2048 MB → 2.0 GB を実行時キャッシュへ保存しシステム側を呼ばない、という 4 つの検証まで同一である | tests/unit/core/test_model_factory.py::test_save_size_to_config_success |
| `tests/unit/standard/core/test_model_factory_unit.py::test_get_models_sorted_by_last_used` | 重複 | 最終使用時刻の古い順に並ぶ同じ分岐である | tests/unit/core/test_model_factory.py::test_get_models_sorted_by_last_used(空の場合は `::test_get_models_sorted_by_last_used_empty`) |
| `tests/unit/standard/core/test_model_factory_unit.py::test_check_memory_before_load_sufficient` | 重複 | `psutil` の available が足りる場合に `True` を返す同じ分岐である | tests/unit/core/test_model_factory.py::test_check_memory_before_load_sufficient |
| `tests/unit/standard/core/test_model_factory_unit.py::test_check_memory_before_load_insufficient` | 重複 | available が足りない場合に `False` を返す同じ分岐である | tests/unit/core/test_model_factory.py::test_check_memory_before_load_insufficient |
| `tests/unit/core/test_model_factory.py::test_update_model_state_released` | 重複 | `status="released"` 後に状態・メモリ・最終使用が消えることを確認する。standard 側は同じ手順を loaded から実行し、`_get_model_state is None` および `_get_model_memory_usage == 0.0` まで確認する上位集合である | tests/unit/standard/core/test_model_factory_unit.py::test_update_model_state_released |
| `tests/unit/core/test_model_factory.py::test_release_model_state` | 重複 | 同じ 3 つの検証であり、standard 側はさらに `_MODEL_SIZES` が残ることも確認する | tests/unit/standard/core/test_model_factory_unit.py::test_release_model_state |

### genai-tag-db-tools

対象は `local_packages/genai-tag-db-tools/tests`(genai-tag-db-tools PR #157)の 3 件である。このほか、名前と中身が食い違っていた 2 件を改名した(`test_convert_tag_returns_original_when_missing` → `test_convert_tag_is_deprecated_not_implemented`、`test_get_format_id_none_returns_zero` → `test_get_format_id_is_deprecated_not_implemented`)。

| ファイル::テスト名 | 分類 | 根拠 | 統合先 |
|---|---|---|---|
| `tests/unit/test_tag_searcher_service.py::test_convert_tag_uses_preferred_tag` | 重複 | `convert_tag` は常に `NotImplementedError` を送出する廃止済み関数である。同一のコードと検証であり、名前が示す動作は `src` に存在しない | `tests/unit/test_tag_searcher_service.py::test_convert_tag_is_deprecated_not_implemented`(旧名 `test_convert_tag_returns_original_when_missing` を改名) |
| `tests/unit/test_tag_searcher_service.py::test_convert_tag_skips_invalid_target` | 重複 | 同上 | `tests/unit/test_tag_searcher_service.py::test_convert_tag_is_deprecated_not_implemented` |
| `tests/unit/test_tag_searcher.py::test_convert_tag_is_not_implemented` | 重複 | 廃止済み関数は reader を参照しないため、DB を作っても同じ例外を確認しているだけである | `tests/unit/test_tag_searcher_service.py::test_convert_tag_is_deprecated_not_implemented` |

## (d)CI の既定実行から外したテスト

該当なし。

## (e)従わなかったルール・スキル・フック

| ファイル | 該当箇所 | 従わなかった理由 | kit の Issue |
|---|---|---|---|
| `.claude/rules/planning-memory.md` | 「必須: 計画策定前の知識確認」(ADR 索引・教訓・最新計画をコード調査の前に確認) | ADR は索引でテスト関連(0016、0024)の存在を確認するにとどめ、本文の通読を省いた。棚卸しの入力は計測ログであり、全 ADR の通読はベースライン計測の開始を遅らせるだけだった | NEXTAltair/altairs-agent-dev-kit#43 |
| `.claude/rules/problem-solving.md` | 「調査の手順」3(web で先行事例を探す) | フィクスチャのスコープ変更や DB の複製化は計測ログから原因と効果を直接確認できるため、事前の web 調査を行わなかった | NEXTAltair/altairs-agent-dev-kit#44 |
| superpowers `using-superpowers` スキル | 「Invoke relevant or requested skills BEFORE any response or action」 | 実行ブリーフが手順と委譲方針を定めており、`brainstorming` や `writing-plans` を挟むと同一内容を二重に作成することになるため起動しなかった | NEXTAltair/altairs-agent-dev-kit#45 |
| `.claude/rules/git-workflow.md` | 「完了の定義」6 と「クリーンアップ」(マージ後の worktree を `git worktree remove` で即削除) | submodule を初期化した worktree では `git worktree remove` が `fatal: working trees containing submodules cannot be moved or removed` で失敗する。マージごとの即削除はせず、全 PR マージ後に未コミット変更がないことを確認してまとめて削除した | NEXTAltair/altairs-agent-dev-kit#46 |
| `CLAUDE.md`「pr-autoloop の Claude Code 実装」 / `pr-autoloop` スキル | 「1 ターン = 1 poll サイクル」「`ScheduleWakeup(delaySeconds=180)` で次サイクルを予約」 | 上限 80 ターンの実行で PR が 9 本あり、1 ポーリング 1 ターンでは待機だけで上限に近づく。PR ごとに `gh pr checks --watch` と回数上限付きの待機ループをバックグラウンドで 1 本走らせ、完了通知で再開した。マージ・修正・エスカレーションの判断基準は `pr-maintainer` に従った | NEXTAltair/altairs-agent-dev-kit#50 |
| `.claude/rules/git-workflow.md` / `issue-to-merge`・`worktree-workflow` スキル | 実装着手時のスキル手順 | スキルを起動せず、実行ブリーフの委譲方針(領域ごとの worktree を先に作成して実装エージェントへ渡す)に従った。worktree の配置(`.agents/worktree/` 配下の短い名前)、ブランチ、PR の方針はルールどおりとした | NEXTAltair/altairs-agent-dev-kit#45 |

## #1632 の安全策

| 安全策 | 実装 | 自動テスト |
|---|---|---|
| 割り当て前の見積もりと拒否 | `image-annotator-lib` `tests/unit/fixtures/onnx_models.py` の `estimate_tagger_onnx_bytes` と `build_tagger_onnx(max_bytes=...)`(image-annotator-lib Issue #193 / PR #194) | `tests/unit/fixtures/test_onnx_models_budget.py::test_oversized_model_is_rejected_before_allocation`、`::test_model_within_budget_is_built`、`::test_budget_can_be_raised_explicitly`、`::test_estimate_matches_incident_size` |
| タイムアウト時のプロセス群後始末 | `scripts/run_bounded.py`(PR #1634) | `tests/unit/scripts/test_run_bounded.py::test_timeout_kills_whole_process_group`、`::test_downstream_process_group_is_cleaned_up`、`::test_normal_exit_returns_zero_and_cleans_leftover_grandchild`、`::test_target_start_failure_cleans_up_downstream` |
| パイプ越しの終了コード伝播 | `scripts/run_bounded.py --pipe-to`(PR #1634) | `tests/unit/scripts/test_run_bounded.py::test_pipe_success_does_not_hide_upstream_failure` |

- **合成モデルのメモリ予算**: 既定値は 256 MiB である。見積もりは float32 の重み(`3 × H × W × K × 4` バイト)の 8 倍とし、生成中の float64 一時領域と書き出し時のコピーを含む。予算は `max_bytes` 引数または環境変数 `IAL_TEST_SYNTHETIC_MODEL_BUDGET_BYTES` で明示的に引き上げた場合のみ拡張される(意図的な大規模計測のためのオプトイン)。事故時のサイズ(448 × 448、10000 タグ)では見積もりが約 180 GiB となり、既定予算でも 16 GiB 予算でも重み生成前に拒否される。
- **上限付き実行ラッパー**: `scripts/run_bounded.py` は対象を新しいプロセス群で起動し、タイムアウト(終了コード 124)、ラッパーへのシグナル、対象終了後のいずれでも残留プロセスを SIGTERM、次いで SIGKILL で停止する。`--memory-limit-gb` は対象の `RLIMIT_AS` を設定する(`::test_memory_limit_rejects_oversized_allocation`)。`--pipe-to` の下流が成功しても、終了コードは対象コマンドの値を返す。使い方は [testing.md](../testing.md) の「上限付き実行(run_bounded)」を参照する。

### コンテナのメモリ・スワップ制限(設計のみ・今回は適用しない)

現状ではメモリ制限がない。cgroup v2 の `memory.max` と `memory.swap.max` はいずれも `max` であり、`.devcontainer/devcontainer.json` の `runArgs` にメモリ指定は入っていない。コンテナ内の 1 プロセスが WSL の割当(32 GiB + swap 8 GiB)を使い切ると、WSL 全体と Windows 側が巻き込まれる。

- **検討案**: `runArgs` に `--memory=24g --memory-swap=24g` を追加する。swap を同値にしてコンテナからの swap 使用を止め、超過時は WSL 全体の枯渇ではなくコンテナ内の OOM kill で終わらせる。これにより WSL 側へ 8 GiB を残せる。
- **既存ワークロードへの影響**: GPU 推論(ONNX / Transformers)の常駐と `llama-server`(Clef)のモデル読み込みが同一コンテナで動作する。24 GiB の妥当性は今回のテスト計測(最大 2.1 GiB)だけでは判断できず、アノテーション実行中の実運用ピーク RSS を先に計測する必要がある。
- **再作成の要否**: `runArgs` の変更には dev container の再作成(Rebuild)が必要である。稼働中コンテナには `docker update --memory` でも適用できるが、再作成時に失われる。
- **当面の対策**: 重い計測には `scripts/run_bounded.py --memory-limit-gb` を使い、プロセス単位で上限を掛ける。

## Follow-up

- モジュール終端の `gc.collect()`(`tests/conftest.py::_collect_qt_wrappers_on_main_thread`)が、S1 で約 80 秒、S2 で約 50 秒の teardown 時間を占めている。`gc.freeze()` で軽量化する案は CI のハングにより見送ったため、安全に使える形があるか CI で反復検証する必要がある。
- S2 は目標に対する余裕がない(3 回の計測のうち 1 回は目標超過)。`tests/unit/gui/widgets/test_image_comparison_dialog.py` のフィクスチャがテストごとに呼ぶ `gc.collect()`(約 4 秒)は意図を確認できず未着手である。
- `tests/unit/gui/conftest.py` は cold import を検査する子プロセスを `pytest_collection_finish` で先行起動している(PR #1640)。conftest のフックからテストモジュールの関数を呼ぶ構造になっており、テスト単体の可読性が下がっている。
- `tests/unit/cli/test_exit_code_process.py` の in-process 実行は、`main()` が立てる JSON 出力モードのグローバル変数を復元していない。現状は失敗しないがテスト順に依存しうる(PR #1635 のレビュー指摘)。
- `tests/unit/conftest.py` の `_reuse_alembic_script_directory` はセッションスコープであるため、ローカルで `tests/` 全体を 1 回の pytest で実行すると integration にも効いたまま残る。CI ではセッションを分けているため影響しない。
- BDD の `test_crop_dialog_flow` では 2000 × 1500 の `CropDialog` が 15 シナリオで約 200 MB 積み上がる。`tests/unit/gui/tab/test_annotate_tab.py`(+276 MB)と `test_export_tab.py`(+171 MB)もモジュール終端の GC 後に常駐メモリが増えるが、原因は未調査である。
- CI の Integration Tests が PR #1638 で 1 回、`test_main_window_tab_integration.py` のフィクスチャで `MainWindow` 構築中にハングして 15 分で打ち切られた。再実行では通過した(この PR は integration テストを変更していない)。
- `image-annotator-lib` の `mypy src/` は 69 件のエラーが出る(PR #194 の作業中に確認。今回の変更とは無関係)。
- `genai-tag-db-tools` の `tests/unit/test_cli.py::test_build_register_service_returns_service` はモックの戻り値を検証しているだけだが、実関数を通る唯一のテストであるため削除せず、書き直し候補として残した。
- 棚卸しで確信度「中」とした削除候補(BDD と integration で重複する `sidecar_import` / `crop_wiring`、`worker_coordination` の 9 件など)は突合が済んでいないため残した。
- `scripts/validate_docs.py` の全体実行が main で失敗する(`Service count mismatch: expected 70, found 72`。今回の変更とは無関係)。
- `_prepare_project_database` は最新リビジョンの DB でも毎回 Alembic upgrade を実行する(ローカル計測で 1 回 1.2〜1.6 秒)。全 CLI コマンドとプロジェクト切替がこのコストを払っている。
- ベースライン計測中、別セッション由来の `image-annotator-lib` の fork テストプロセスが親を失って 4 時間以上残留していた(PPID 1)。テスト実行の後始末が効かない経路が残っている。
- 古い main での S3 初回計測時、CLI の cold 起動テストが 9p 上のディレクトリ読み取りで `[Errno 12] Cannot allocate memory` を出して 1 件失敗した。再計測では再現しなかった。
