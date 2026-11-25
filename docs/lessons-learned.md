---
type: Reference
title: Lessons Learned
status: Accepted
timestamp: 2026-06-23
tags: [process]
---
# 開発の教訓(Lessons Learned)

LoRAIro の開発を通じて得た教訓を、バグパターン・設計ミス・解決策の本質に絞って記録する。

## アーキテクチャ

### 2 層サービス設計
GUI 層とビジネスロジック層を分離しないと、モノリスが肥大化する。Qt に依存しないコアサービスを先に設計し、GUI ラッパーを後から追加する順序が正しい(ADR 0001、0009 参照)。

### `MainWindow` の肥大化対策
1,645 行から 688 行(58% 削減)へ整理した際の教訓として、初期化フェーズを 5 段階に分け、各フェーズを Service ヘルパーへ委譲する構成が有効だった。GUI のオーケストレーターは各部品をつなぐ「接着剤」の役割にとどめる。

### サービス層への処理統合(Issue #178 / Epic #166)
GUI・CLI・API の 3 経路から同じビジネスロジックを呼ぶ場合、経路ごとに個別実装すると二重クエリ、整合性のずれ、重複するバグ修正が発生する。
ID 解決ロジックを `DatasetExportService.export_with_criteria()` に集約したことで、3 経路すべてが一貫した挙動になった。

## テスト

### 統合テストでは実 DB を使う
モックを使ったテストが通っても本番環境で失敗するケースがある。DB やファイルシステムなどの外部依存はモックに頼らず、実際のテスト用 DB を使って検証する。

### `pytest-qt` のアンチパターンを避ける
`qtbot.wait(固定時間)` は不安定になりやすい。代わりに `qtbot.waitSignal()` や `qtbot.waitUntil(条件)` を使う。`QCoreApplication.processEvents()` の直接呼び出しも避ける。

### `QMessageBox` は必ずモック化する
テスト中に `QMessageBox.question` などがモックされていないと、ダイアログ待ちでテストがハングする。必ず `monkeypatch` でモック化する。

### カバレッジ閾値は CI の実測とセットで設定する(Issue #131)
`fail_under=75` が長期間 CI で未検証のまま放置され、coverage-gate 新設時に実測 58% が露呈した。新しい閾値を導入する際は、理想値だけを先に書かず、必ず PR 上で CI の実測値とあわせて検証・設定する。

### デッドコードはカバレッジ分母を汚染する(Issue #138 / ADR 0016)
`src/` 本体から参照されていない 9 モジュール(3,957 行)を削除しただけでカバレッジが +17 ポイント改善した。`grep` ベースの import グラフ解析による定期的なデッドコード棚卸しが有効である。

### 描画専用 Qt コードと ML バックエンドの除外基準(Issue #135 / ADR 0016)
コアサービス層の `omit` を禁止しつつ、描画専用 GUI コードの `omit` 基準と `image-annotator-lib` の `source` 除外基準を定めた。ヘッドレス CI では `torch` の初期化が困難なため、ML バックエンドは `[tool.coverage.run] source` から除外して計測対象外とするのが合理的である。

### loguru の実ファイル sink がテストセッション全体を汚染する(Issue #578)
- **現象**: `test_configuration_window` の `dialog._on_accepted()` が本物の `initialize_logging(build_gui_log_config(...))` を呼び、`logs/lorairo.log` 向けのファイル sink を追加していた。loguru の `logger` はプロセスグローバルのシングルトンであるため、以降の全テストのログ(防御テストの想定例外 `テスト例外` や `disk full` など)が実アプリログへ混入した(全テスト実行で +56KB / 280 行)。
- **対策**: `tests/conftest.py` の session-autouse フィクスチャで `loguru.logger.add` をラップし、実 `DEFAULT_LOG_PATH` 宛の sink **だけ** をセッション一時ディレクトリへ転送する。
- **注意点**: `build_gui_log_config` の戻り値(`file_path=実パス`)は変えないため、`file_path == str(DEFAULT_LOG_PATH)` を検証する既存テストを壊さない。`DEFAULT_LOG_PATH` 自体の monkeypatch は、各テストモジュールが import 時に値を束縛済みのため機能しない。検証は全テスト実行で実ログのバイト増分が 0 であることを実測する。

### 状態復元・マイグレーション経路の取りこぼし対策(Issue #865)
- **現象**: Issue #863 の 1 カラム化が `restoreState` の orientation 巻き戻しで無効化されたバグは、62 件のテストをすべてすり抜けた。テスト・CI 環境の `QSettings` は空のため `settings_version != SETTINGS_VERSION` で早期 return し、そもそも `restoreState` が呼ばれていなかった(既存のスプリッターテストもモックで実 `restoreState` を呼んでいなかった)。
- **線引き**:
  1. 実際に踏んだバグには、事前状態を仕込んだリグレッションテストを 1 本だけ置く(例: `TestRestoreSplitterStatesOrientation` — 横方向の保存状態から縦方向が維持されることを検証、約 25 行、`MainWindow` 非構築で高速)。
  2. 復元経路を網羅的にテストするのは過剰である。`QSettings` の復元対象は主に見た目の状態で重大度が低く、`SETTINGS_VERSION` を上げる規約のほうが費用対効果が高い。「新規起動で動く」ことと「既存状態からのアップグレードで動く」ことは別物だと意識しつつ、必要な箇所にピンポイントでテストを置く。

### `sys.modules` モックと pytest セッション境界の一致(Issue #247 / ADR 0024)
- **現象**: `tests/conftest.py` がモジュールレベルで `sys.modules["image_annotator_lib"]` を `types.ModuleType` のモックに差し替えている。ルート pytest が `local_packages/image-annotator-lib/tests/` まで収集すると、そのモックがライブラリ自身のテストに継承され、`parent_module = <MagicMock>` による `AttributeError: __spec__` が収集時点で 29 件発生する。さらにサブモジュールの同名テスト(`test_worker_service.py`)とのファイル名衝突で `import file mismatch` も起きる。
- **教訓**: `conftest` の責務境界・pytest セッション境界・パッケージ境界を一致させる。`testpaths = ["tests"]` に限定し、ローカルパッケージのテストは各パッケージルートで独立した pytest セッション(別 CI ジョブ、`make test-iam-lib`、`make test-genai-tag`)として実行する。条件分岐 conftest や `--ignore` による局所回避は根本解にならない。

## PySide6 / Qt

### `.ui` 変更後の UI 生成忘れ
`.ui` ファイルを変更したあとに `uv run python scripts/generate_ui.py` を実行しないと、`MainWindow_ui.py` が古いままになり、`filterSearchPanel` などのウィジェットが見つからず起動に失敗する。

### Signal の二重発火
ワーカー完了 Signal を複数箇所で接続すると、同一イベントが重複処理される。接続箇所は 1 箇所に統一し、ワーカー生成時に接続する。

### 同期処理ボタンの再入と送信後の状態クリア(Issue #571)
- **現象**: `_set_submit_button_busy()` 内の `QApplication.processEvents()` がキュー済みのクリックを再配信するため、ボタンの無効化だけでは同期送信中の再入を防げない。
- **対策**: `submit_job()` の冒頭に `_submit_in_progress` 再入フラグを置く。
- **送信成功後の注意点**:
  1. `image_ids` は送信直前のスナップショットである。`clear()` で全消去すると `processEvents` 中に追加された未送信画像まで消えるため、`remove_image_ids(送信済み ID)` で送信分だけを除外する。
  2. `submit_images` の成功時点でプロバイダー側のジョブ作成は不可逆である。後続の表示更新(`select_job` → `refresh_detail`)がリポジトリ例外を投げても送信成功を覆してはならない。ステージング除外と成功表示を先に確定し、表示更新は局所的な `try` で隔離する。

### `QSplitter.restoreState()` が orientation まで巻き戻す問題(Issue #865)
- **現象**: `.ui`(`setupUi`)で `setOrientation(Vertical)` に設定しても、起動後の `_restore_window_state` → `_restore_splitter_states` が `QSettings` の旧(横方向)保存状態を `restoreState()` で復元すると、`orientation` が `Horizontal` に巻き戻り、Issue #863 の 1 カラム化が実機で無効化された。
- **対策**: `orientation` の正本(SSoT)は `.ui` であり `QSettings` ではない。復元前に `splitter.orientation()` を退避し、`restoreState()` のあとに `setOrientation(設計値)` を再適用する。また、永続化対象のレイアウト属性を変更した際は `SETTINGS_VERSION` を上げて旧状態を破棄する規約を守る。
- **教訓**:
  1. 「静的ソースが正しい」ことと「実行時に正しく動く」ことは別である。ユーザーから「直っていない」と繰り返し報告されたときは、静的確認をやめて実行時の挙動を直接検証して仮説を反証する(今回は実機で `restoreState` を叩き 3 秒で原因を特定した)。
  2. 状態復元やマイグレーション経路のバグは、クリーンスレートで始まる通常のテストでは再現しない。

### ユーザー操作起点ワーカーの多重起動とシャットダウンハング(Issue #1024 / #1027 / PR #1044)
- **現象**: 画像選択やタグ操作のたびに新しい `QThread` ワーカーを起動し、旧ワーカーを「結果を捨てるだけ」で放置すると、短時間で十数本が累積して SQLite を取り合い、1 本あたりの処理が分単位まで劣化する(実測: 16 本累積で 1 本の prefetch が 78 秒)。さらに終了時に 1 本ずつ直列で猶予待ち(2 秒 + terminate 1 秒 × N)を行うと、ワーカー数に比例してアプリがハングする(実測 53 秒)。
- **対策(3 点セット)**:
  1. **Single-flight**: 実行中ワーカーは常に 1 本だけにする。追加要求は最新 1 件だけを保留し、旧ワーカーへは待機なしの協調キャンセルを送る(GUI スレッドで `thread.wait()` しない)。
  2. **協調キャンセルのチェックポイント**: ネイティブの SQLite 呼び出し中のスレッドは `QThread.terminate()` でも止められない(実測で 16/16 全件失敗)。DB 往復の合間にキャンセル確認を入れて初めてキャンセルが効く。
  3. **一括ブロードキャストと共有デッドラインによる終了**: まず全ワーカーへ cancel / quit を一斉送信し、全体で共有するデッドラインまで待つ。残ったスレッドは `terminate` せず見捨てる。その際、ウィジェット所有のマネージャーと共に参照が消えると `QThread: Destroyed while thread is still running` で異常終了するため、プロセスグローバルのレジストリへ参照を退避する。

### `QRunnable` の Python 参照保持漏れによる `Signal source has been deleted`(Issue #1040 / #1047 / PR #1042)
- **現象**: `QRunnable` は `autoDelete` で C++ 側に所有権が移るが、親を持たない `QObject` 属性(シグナル保持用オブジェクト)は Python 側の参照が切れると GC 対象になる。ウィジェットが `pool.start()` するだけで参照を持たないと、実行中に GC が走って `run()` 内の `emit` が `RuntimeError: Signal source has been deleted` を起こす(`except` 節の `emit` で二重例外になる)。GC タイミング依存のため再現が難しい。
- **対策(2 点セット)**:
  1. ウィジェット側に実行中タスクの参照(`dict[request_id, task]`)を持たせ、起動前に登録して完了・失敗ハンドラで削除する。
  2. `run()` 内の `emit` を `try/except RuntimeError` で保護する。
- **検証と横展開**: `shiboken6.delete(task.signals)` を使えば破棄状態を決定的に再現できる。同種の問題を見つけたら `QRunnable` を grep して横展開監査を行う(#1040 の監査で `count_estimate.py` にも同型を発見し #1047 で修正)。

### `FlowLayout` と `widgetResizable=True` の `QScrollArea` による余白暴走(Issue #831 / #833 / #835 / #1025 / PR #1045)
- **現象**: タグチップの `FlowLayout` のような `heightForWidth` 型レイアウトは、最小幅で全アイテムを縦積みした過大な `minimumSizeHint` を返す。これを `widgetResizable=True` のスクロール領域内に間接配置すると、Qt がコンテナを最小サイズまで引き伸ばし、末尾にビューポートを超える巨大な余白と不要なスクロールが発生する。
- **誤った対処**: 余白の対症療法(上詰め・下固定・高さ手動合わせ)を繰り返しても、余白・隙間・クリップの間を行き来するだけで解決しない。まず `inner.height()` や `widget.minimumSizeHint()` を実測して原因を特定する。
- **根本対処**:
  - 折り返し領域を高さ上限付きの内側 `QScrollArea` に隔離し、親の高さがアイテム数に依存しないよう `min(heightForWidth(実幅), 上限)` で有界化する。`setFixedHeight(sizeHint)` の手動適用は `sizeHint` 過小報告によるクリップやタイミング依存を招くため避ける。
  - より素直な設計は、折り返し領域と高さ制御を専用ウィジェット(例: `TagChipBox(QWidget)`)に切り出し、`sizeHint` / `minimumSizeHint` を内部で閉じることである。Qt でのウィジェット分割とコンポジションは基本技法であり、大規模リファクタではない。
- **続報で判明した 2 つの追加要因(Issue #1025 / PR #1045)**:
  1. 内側コンテナの縦 `SizePolicy` が `Minimum`(`ShrinkFlag` なし)だと、`FlowLayout` の過大な `sizeHint`(実測: 40 チップで 996px)が最小高さとして固定され、`QScrollArea` が実幅の必要高さ(実測 46px)まで縮められず余白が残る → 縦方向は `Preferred` にする。
  2. チップ再構築直後の同期高さ計測では、新ウィジェットがレイアウト未確定かつ非表示のため `QWidgetItem.sizeHint()` が `(0, 0)` を返し箱が潰れる(次の `resizeEvent` で偶然回復するタイミング依存) → 同期計測前に明示的に可視化するか、レイアウト確定後に計測する。いずれもオフスクリーン実測(`container.height()`、`sizeHint()`、スクロールバー範囲のログ)で 30 分以内に特定できた。

## データベース / SQLAlchemy

### セッション管理の落とし穴
バッチ処理中のセッションをワーカー間で共有するとデッドロックが発生する。ワーカーごとに独立したセッションを使う。

### バッチタグ追加のアトミック性(ADR 0012)
タグ追加をループ内で個別コミットすると、途中エラー時に不整合な中間状態が残る。`Session.add_all()` と一括コミットでアトミック性を保証する。

### 書き込みと読み込みの対称性(Issue #118 / #119 / ADR 0015)
カラムと子テーブルに同じ意味のデータを二重管理してはならない。書き込み API と読み込み API が同一テーブルを参照していることを PR レビューで必ず確認する(Issue #118 の NSFW 判定、Issue #119 の `manual_rating` フィルタで同型の不具合が発生)。

### 送信判定における `ratings.normalized_rating` の単一参照
`ratings.raw_rating_value` は保存元の追跡用補助情報であり、`X` / `XXX` フィルタの判定は `normalized_rating` のみで行う。`PG`、`PG-13`、`R`、`UNRATED`、`None` は送信可能として通過させる。

### User DB の初期化順序
Base DB が存在しない環境でも User DB は単独で動作する必要がある。`init_user_db()` は Base DB の有無に依存しない設計にする。

### プロジェクト概念のスキーマ正規化(Issue #166 / ADR 0017)
`lorairo_data/<name>_<timestamp>/` というディレクトリ名だけでプロジェクトを識別する暗黙構造は破綻しやすい。実際に Issue #166 では `repository.get_images_by_filter()` の引数なし全件取得(21,000 件)バグを引き起こした。`projects` テーブルと `Image.project_id` 外部キーを導入し、`WHERE project_id = ?` のインデックス検索へ置き換えたことで、LIKE 句マッチや全件スキャンを構造的に排除できた。

### マルチスレッド GUI で実ファイル DB に `StaticPool` を使ってはならない(Issue #1002 / genai-tag-db-tools #116)
- **現象**: `poolclass=StaticPool` は 1 本の生 SQLite コネクションを全セッションで共有する。`connect_args={"check_same_thread": False}` は Python 側のスレッドチェックを外すだけで、内部の `sqlite3.Connection` への同時アクセスは防げない。GUI メインスレッドと `RefinementWorker`(`QThread`)が同一エンジンを共有した結果、`sqlite3.InterfaceError: bad parameter or other API misuse` が散発し、例外が出ないケースでは `_populate_rejected_tags()` などが古い結果を返して「編集が消えた」ように見えた。
- **対策**: `StaticPool` が必須なのは接続ごとに別 DB になってしまう `:memory:` テストだけである。実ファイル DB では既定の `QueuePool`(スレッドごとに独立コネクション)を使う。`create_db_engine()` は `":memory:" in database_url` の場合のみ `StaticPool` を使う分岐にする。
- **補足**: WAL モードと `busy_timeout`(Issue #767)は複数コネクションの安全な共存のための設定であり、`StaticPool` 下では機能しない。LoRAIro の `db_core.py` とサブモジュール `genai-tag-db-tools/db/runtime.py` の両方に同じ問題があったため、双方を修正した。

## 外部連携・インテグレーション

### `image-annotator-lib` との境界設計
`annotation_runner.py`(`AnnotationRunner`)でアダプターパターンを採用し、`image-annotator-lib` の内部型(`PHashAnnotationResults`)を LoRAIro 内部型へ変換する。ライブラリ側の型変更が LoRAIro 全体へ波及しない境界を維持する。

### `torch` の遅延インポート(ADR 0010)
起動時に `torch` をインポートすると GUI 表示が数秒遅れる。`importlib.import_module()` による遅延インポートで起動時間を短縮する。

### シンボル置換ツールによるコード欠損インシデント(2026-02-09)
大規模リファクタリング中に `replace_symbol_body` ツールの適用範囲が想定以上に広がり、アノテーターワーカーの実装が意図せず削除された。シンボル置換ツールの実行後は、必ず diff で変更範囲全体を確認する。

### フィルタ必須化による誤操作の構造的防止(ADR 0019)
LoRA 学習データ作成の `export create` では「全件エクスポート」が正常ユースケースとして存在しない。フィルタ未指定の呼び出しを終了コード `2` で即座に拒否することで、21,000 件の誤エクスポートを設計レベルで防いだ。実行時警告やドライラン強制よりも「そもそも危険な形で呼べない設計」のほうが単純で一貫性があり、CI や cron などの非対話環境でも安全に機能する。

### `BaseAnnotator` 階層での device 判定責務の分離(Issue #35 / ADR 0023 Phase 1.x)
WebAPI 経路は `WebApiAnnotator` に統一され、`device` は `"api"` 固定となった。もし `BaseAnnotator.__init__` で `_validate_device`(`determine_effective_device`)を呼ぶ構造のままにすると、WebAPI 系クラスが `super().__init__()` を呼んだ際に CUDA 判定が走り、CPU 専用コンテナで「CUDA 非対応 PyTorch」警告が出る。device 判定はローカル ML 系基底クラス(Transformers / ONNX / TF / Clip / Pipeline)の責務として分離し、`BaseAnnotator.device` は空文字 `""` で初期化してサブクラスが上書きする契約とする。

### 整数ビンタグをライブラリ標準出力から削除(Issue #281 / iam-lib ADR 0002)
`[CAFE]score_N`、`[IAP]score_N`、`[WD]score_N` のような整数ビンタグは任意の独自ポリシーであるため、`image-annotator-lib` の標準出力から排除した(調査時点で LoRAIro 側の利用箇所は 0 件)。再導入が必要になった場合は利用側が生の `scores` から派生計算する。これにより、検索やエクスポートの契約をモデル配布元の仕様と一致させられる。

### 数値スコアとカテゴリカルなスコアラベルのテーブル分離(Issue #281 / ADR 0027)
`aesthetic_shadow` や `cafe_aesthetic` などのスコアラーは、複数の数値スコア(`scores={hq, lq}` など)と単一のカテゴリカルラベルを返す。`Score` テーブルに `label` 列を足すと複数行のどれにラベルを入れるか曖昧になるため、`(image_id, model_id, label)` を独立した `score_labels` テーブルへ分離した。これにより `Tag` / `Caption` / `Rating` と対称な構造で扱える(ADR 0015 と同じ設計判断)。

### ADR と実装の整合はチェックリストで明示的に検査する(Issue #35 / PR #40)
ADR 0023 Phase 1 で廃止が決まっていた `available_api_models.toml` キャッシュ、WebAPI 用ユーザー TOML 上書き、`api_model_id` 互換シムが、実装 PR(#38)で大量に残置され、レビューで broken path として指摘された。ADR 決定後の実装 PR では、ADR の各条項と該当コード・公開 API をチェックリストで照合し、削除・置換漏れを diff レビューで確認する。フェーズ完了時に grep ベースで ADR 違反を点検すると再発を防げる。

### ライブラリと LoRAIro 間のエラー伝搬を文字列プレフィックスで疎結合に保つ(Issue #42 / ADR 0023 Phase 1.5)
`image-annotator-lib` の `SafetyRefusalError` や `ContentPolicyRefusalError` を LoRAIro の `error_records` へ伝える際、`UnifiedAnnotationResult.error` を `f"{ExceptionType}: {msg}"` 形式の文字列にし、LoRAIro 側で `startswith` 判定する方式を採った。例外型を直接 import して `isinstance()` で判定すると、サブモジュールのマージ順序やバージョン結合が厳しくなる。文字列プレフィックスなら、ライブラリ側で例外が増えても LoRAIro 側はプレフィックス一覧を更新するだけで済む。新しいエラー種別を増やすときは両側でプレフィックスを ADR で合意し、`error_records.error_type` にそのまま格納する慣習を守る。

### SSoT スキーマ変更時は「読み取り側」と「送信側」を同時に切り替える(Issue #245 / ADR 0023 Phase 1.11)
`Model.litellm_model_id` を一意なレジストリキーの正本(SSoT)に昇格させた際、読み取り側の検索(`get_models_by_litellm_ids` など)だけを更新し、GUI → Worker → Logic → ライブラリへの送信値に `Model.name` が残っていた。新規同期行では偶然 `name == litellm_model_id` で動くが、移行行(例: `name='openai/gpt-4o'`、`litellm_model_id='openrouter/openai/gpt-4o'`)では検索失敗となる。SSoT の切り替え時は、(1) DB スキーマ変更、(2) 読み取り API 切替、(3) 内部キーの送信経路切替、(4) UX 上の識別表示(GUI は `{name} ({provider})` + ツールチップに正規 ID、CLI は `litellm_model_id` 必須 + 曖昧一致時に候補一覧エラー)を必ず同一 ADR で一括実装する。

### `except` ブロック内での `asyncio.run()` 呼び出しによる偽の例外連鎖(Issue #302)
- **現象**: `try: asyncio.get_running_loop()` の `except RuntimeError:` ブロック内で `asyncio.run(...)` を呼ぶと、捕捉済みの `RuntimeError("no running event loop")` が有効なままコルーチンが実行される。その結果、コルーチン内で発生した `__cause__` を持たない例外の `__context__` に無関係な `RuntimeError` が連鎖し、診断表示(Issue #274 の `_format_exception_chain`)で誤診を招く(実機の WebAPI 429 エラー調査で発覚)。
- **対策**: イベントループの有無を確認する処理は `bool` を返すヘルパーへ分離し、`except` の `RuntimeError` を完全に抜けてから `asyncio.run()` を呼ぶ。`raise ... from ...` を使うモックテストでは `__cause__` が優先されるため、この不具合を見逃しやすい点にも注意する。

### Provider Batch のレーティング事前確認における既存スキーマの再利用(Issue #507 / ADR 0031 改訂 / ADR 0038)
`/v1/moderations` Batch を専用スキーマとして新設すると、既存の `provider_batch_jobs` / `provider_batch_items` / `ratings` と二重管理になる。`provider_batch_items.task_type = "rating_preflight"` と `provider_batch_jobs.model_id = <omni-moderation-latest>` でアノテーションバッチと区別し、結果を既存の `ratings.normalized_rating`(`X` / `XXX`)へ書き込むことで、後続ワーカーの `filter_excluded_by_rating()` が同じ正本を参照できる。決定論的な E2E テスト(`tests/integration/test_provider_batch_rating_preflight_e2e.py`)では偽の `ProviderBatchAdapter` を注入して submit → import → ratings 保存 → 除外判定を一貫検証し、実 OpenAI API の契約確認は `image-annotator-lib` の `tests/runtime_validation/` で手動実行する(ADR 0026)。

### 外部タグ DB の正規化変換は表示時ではなく書き込み境界のバッチ処理で行う(Issue #769 / ADR 0068 改訂)
- **現象**: Issue #772 で GUI 詳細表示時に `convert_tags` をタグ 1 件ずつ呼び出した結果、画像 1 枚の表示ごとに「タグ数 × タグ DB リポジトリ数 × 2(`get_format_id` + 検索)」の DB 往復が発生し、Windows 実機でサムネイル選択から詳細表示まで許容外に遅延した(ウィジェット単位のキャッシュでは初回表示コストを消せない)。`convert_tags` や `search_tags_bulk` の一括検索設計を、1 件ずつのループ呼び出しで台無しにしていた。
- **対策**: 正規表記の解決を保存境界(`_save_tags`、画像 1 枚あたり 1 回のバッチ検索)へ移し、`Tag.tag` に Danbooru 正規表記を保存して表示・エクスポート時は変換なしでそのまま出力するようにした。ただし手動編集値(`is_edited_manually=True`)は正規化せずユーザーの入力表記を尊重する。
- **教訓**: 外部 DB を参照する正規化を対話経路で 1 件ずつ呼んではならない。変換は書き込み時にバッチで 1 回だけ確定させ、読み取り・表示時の変換コストをゼロにする。`search_tags_bulk` のようなバッチ API をループ内で 1 件ずつ呼んでいないか必ず確認する。

### 同期・Batch 両経路での Pydantic スキーマ共有と PydanticAI の責務境界(Issue #518 / ADR 0023 / ADR 0038)
WebAPI アノテーションの構造化出力スキーマは `AnnotationSchema`(Pydantic `BaseModel`)を正本(SSoT)とする。同期経路は PydanticAI の `Agent(output_type=normalize_annotation_output)` を使い、Batch 経路は `AnnotationSchema.model_json_schema()` から純粋な Pydantic で OpenAI function-tool スキーマを直接生成する。PydanticAI はエージェント実行基盤でありスキーマ定義の責務は Pydantic 側にあるため、Batch 経路へ PydanticAI を持ち込むとプロバイダーバッチのライフサイクル(ファイルアップロード、ジョブ監視、成果物取得)と抽象が衝突する。
また、`/v1/responses` ではなく `/v1/chat/completions` Batch を選んだのは、同期経路とエンドポイント・ツールスキーマ・応答形式を一致させ、テストフィクスチャ・拒否検知・`normalize_annotation_output()` を両経路で共有するためである。安全性拒否は同期では `SafetyRefusalError`、Batch では `finish_reason=content_filter` や `message.refusal` 非 null を `BatchItemError(code="provider_safety_refusal")` に正規化し、`error_records` と `provider_batch_items.error_type` の両方で対称に扱えるようにしている。

### 裏付けとなるデータ経路を確認せずにデザイン UI を配線しない(Issue #851 撤去)
- **現象**: デザインシステム(AnnotateScreen ModelPicker)由来の `conf-min` スライダーを「推論後にタグごとの確信度(confidence)でフィルタする」前提で、`StageModelPickerDialog` → `annotate_tab` → `main_window` → `worker_service` → `controller` → `AnnotationWorker` の 5 層に配線した。しかし、(1) `image-annotator-lib` は推論時に静的 `tag_threshold`(既定 0.35)でフィルタしてから確信度を破棄するため保存値は常に `confidence_score=None` であり、(2) 公開 `annotate()` に実行時のモデル別閾値を渡す口もなかった。結果として機能しない配線が `PENDING` のまま残存し、撤去のうえ将来の lib 拡張を前提とする Issue(#851)へ再定義した。
- **教訓**: デザインツール上に存在する UI コントロールを実装する前に、それを支えるデータ経路が実在するかを必ず確認する。「あとでつなぐ」と複数層に配線すると、前提の誤りが `PENDING` として固定化される。
