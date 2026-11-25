---
type: Reference
title: サービス層アーキテクチャ
status: Accepted
timestamp: 2026-10-11
tags: [service-layer]
depends_on: [pyside6]
---
# サービス層アーキテクチャ

## 概要

LoRAIro は 2 層サービスアーキテクチャを採用し、Qt 非依存のビジネスロジックと Qt 依存の GUI サービスを分離している。

**設計原則**:
- **ビジネスロジックサービス**: Qt に依存せず、CLI・GUI・API のすべてで再利用できる
- **GUI サービス**: Qt に依存し、Signal/Slot によるウィジェット間通信を担う
- **Qt-Free Core パターン**: コアサービスは Qt 非依存とし、GUI ラッパーがコンポジションパターンで Signal 機能を追加する

**ディレクトリ構成**:
- `src/lorairo/services/` — ビジネスロジックサービス群
- `src/lorairo/gui/services/` — GUI サービス群

カタログとの乖離を防ぐため、サービス件数は本ドキュメントへ直書きせず、`ls src/lorairo/services/*.py` 等で都度確認する。

## ビジネスロジックサービス

Qt 依存のないビジネスロジックサービス群である。CLI、GUI、API のすべてから共通利用できる。

### コアインフラ

#### ServiceContainer
- **パス**: `src/lorairo/services/service_container.py`
- **クラス**: `ServiceContainer`
- **目的**: 依存性注入(DI)コンテナとして全サービスを一元管理する
- **パターン**: シングルトンパターン
- **関数**: `get_service_container()`、`get_config_service()`、`get_model_sync_service()`

#### ConfigurationService
- **パス**: `src/lorairo/services/configuration_service.py`
- **クラス**: `ConfigurationService`
- **目的**: アプリケーション設定の読み込み、更新、保存を担う
- **設定ファイル**: `config/lorairo.toml`

### タグ管理

#### TagManagementService
- **パス**: `src/lorairo/services/tag_management_service.py`
- **クラス**: `TagManagementService`
- **目的**: User DB 専用のタグ管理を担う(Base DB は対象外)
- **統合**: `genai-tag-db-tools` 公開 API(`search_tags()`、`register_tag()`)
- **方針**: `format_id=1000+`、`type_name="unknown"` をプレースホルダーとして扱う
- **操作**: `unknown` タイプタグの検索、タイプ一覧の取得、一括タイプ更新

#### RefinementService(Qt-free)
- **パス**: `src/lorairo/services/refinement_service.py`
- **目的**: `genai-tag-db-tools` の `recommend_manual_refinement` を呼び出し、ローカルの無視設定(タグと `reason_code` 単位)を除外した「表示すべきリコメンド」を返す
- **補足**: 判定ロジック、承認反映、Base DB 提案は `genai-tag-db-tools` 側の責務である。同一の `(tag, format_name)` はプロセス内キャッシュで再評価を避ける

#### StagingTagAggregation(Qt-free)
- **パス**: `src/lorairo/services/staging_tag_aggregation.py`
- **目的**: ステージング集合内のタグを集計する(Issue #945)。左ペインの `StagingTagPanel`(#947)が結果を利用する

#### TriggerVocab(Qt-free)
- **パス**: `src/lorairo/services/trigger_vocab.py`
- **目的**: トリガーワード語彙のユーザー DB 登録と補完を担う(Issue #946)。`ExportOverlayBar`(#948)のトリガー補完リストへ供給する
- **保存先**: ユーザー DB(`USER_TAGS`、`tag_id >= 1_000_000_000`)の専用フォーマットへ隔離して登録する。canonical タグ DB や Danbooru タグ DB は汚染しない
- **補足**: トリガーはリテラルとして扱い、変換をバイパスする。正規化せずそのまま格納し、重複のみ排除する

### AI アノテーション

#### AnnotationProgress(Qt-free)
- **パス**: `src/lorairo/services/annotation_progress.py`
- **クラス**: `AnnotationPhase`、`AnnotationProgress`
- **目的**: アノテーションの工程、対象画像数、モデル数、経過時間をセッション内のスナップショットとして保持する(Issue #1386)
- **境界**: 処理済み件数や残り時間は推定しない。キャンセル要求後の停止待ちを完了と区別し、終了後は経過時間を固定する

#### AnnotationExecutionPolicy(Qt-free)
- **パス**: `src/lorairo/services/annotation_execution_policy.py`
- **クラス**: `AnnotationExecutionPolicy`、`AnnotationExecutionSettings`、`MemorySnapshot`
- **目的**: ローカル ML モデル実行前の受付判定(空き RAM・VRAM と安全余裕)、回復待ち、見送り判断を担う(ADR 0109)
- **設定**: `[annotation_execution]`。空きメモリ取得、時計、sleep 処理は DI でき、テストでは fake を用いる

#### AnnotationReviewService
- **パス**: `src/lorairo/services/annotation_review_service.py`
- **目的**: 既存のタグ・キャプションと、関連画像群から抽出した未付与タグをローカル Clef の型付き判定 API で照合する
- **境界**: タグクラウドの集計を再利用し、警告と追加候補を別の基準で判定する。注釈、`confidence`、`reviewed` は変更しない

#### AnnotationReviewStore
- **パス**: `src/lorairo/services/annotation_review_store.py`
- **目的**: 画像ごとの最新判定と候補条件を保存し、現在の画像・注釈・設定との一致を検証する
- **鮮度管理**: 内容が変わった結果は古い判定として返し、確率表示と採用操作を無効にする

#### AnnotationReviewAdoptionService
- **パス**: `src/lorairo/services/annotation_review_adoption_service.py`
- **目的**: 最新かつ現在有効な追加候補を、ユーザーの選択に応じて手動タグとして採用する
- **境界**: 保存時刻、候補 ID、画像と注釈の鮮度を照合する。確率を `confidence` や手動スコアへ書き込まない

#### AnnotationSaveService
- **パス**: `src/lorairo/services/annotation_save_service.py`
- **クラス**: `AnnotationSaveService`
- **目的**: 画像 ID をキーとしたペイロードから、AI アノテーション結果を DB へ保存する
- **操作**: プロバイダーバッチおよび正規化済みアノテーション結果の保存、スキップ・エラー件数の集計

#### ModerationPreflightService
- **パス**: `src/lorairo/services/moderation_preflight_service.py`
- **目的**: WebAPI アノテーション送信前に OpenAI moderation preflight を実行する。画像ごとに moderation モデルを通し、フラグ付き画像を送信対象から除外する
- **操作**: 画像単位の moderation 実行と、スキップ理由(`ModerationPreflightSkip`)の収集
- **境界**: `ModerationRunner` プロトコルで単一 moderation モデルの実行を抽象化する

#### AnnotatorLibraryAdapter
- **パス**: `src/lorairo/annotation/annotator_adapter.py`
- **クラス**: `AnnotatorLibraryAdapter`
- **目的**: `image-annotator-lib` の統合アダプター
- **プロバイダー**: OpenAI、Anthropic、Google、ローカル ML モデル
- **戻り値**: `PHashAnnotationResults`

### 画像処理

#### ImageProcessingService
- **パス**: `src/lorairo/services/image_processing_service.py`
- **クラス**: `ImageProcessingService`
- **目的**: リサイズ、フォーマット変換、品質評価などの画像処理ワークフローを担う

#### DatasetExportService
- **パス**: `src/lorairo/services/dataset_export_service.py`
- **クラス**: `DatasetExportService`
- **目的**: データセットのエクスポート機能を提供する

#### crop_batch_service(Qt-free)
- **パス**: `src/lorairo/services/crop_batch_service.py`
- **関数**: `run_crop_batch()`
- **目的**: `CropRectProvider` が返す矩形候補からクロップ画像を一括作成する(ADR 0103)。1 矩形につき 1 結果を返し、部分失敗があっても継続する。同じ親画像・矩形・由来の組み合わせは `skipped` とし、dry-run にも対応する。1 件の作成処理には `crop_service.create_crop_image` を再利用する

#### JsonlCropRectProvider(Qt-free)
- **パス**: `src/lorairo/services/crop_rect_jsonl_provider.py`
- **クラス**: `JsonlCropRectProvider`
- **目的**: 外部で用意した矩形 JSONL(1 行につき `image_id` と矩形)を読む `CropRectProvider` の初期実装(ADR 0103)。不正な行は行番号付きで保持し、500 行を超える入力は件数確認の段階で拒否する

#### DetectorCropRectProvider(Qt-free)
- **パス**: `src/lorairo/services/crop_detect_provider.py`
- **クラス**: `DetectorCropRectProvider`(検出器境界: `ObjectDetector`、実装: `LibObjectDetector`)
- **目的**: `image-annotator-lib` の物体検出器(`person`、`face`、`head`)で矩形を決める `CropRectProvider`(ADR 0110)。余白、閾値、最小長辺、既存クロップとの IoU を判定し、作成対象外の矩形は理由コード付き候補として返す。検出 0 件や失敗は `CropRectNotice` で通知し、ライブラリ本体は検出実行時までインポートしない

#### ExportOverlay(Qt-free)
- **パス**: `src/lorairo/services/export_overlay.py`
- **目的**: エクスポート時の画像単位タグ変換パイプライン(ADR 0080 §1-§4)
- **パイプライン順序**:
  1. `replace` を適用する
  2. `exclude` を除去する
  3. `convert` を適用する(alias から preferred への変換と meta 除外)
  4. `add` を先頭へリテラル追加する(変換はバイパス)
  5. 順序を保持したまま重複を除去する

### モデル管理

#### ModelFilterService
- **パス**: `src/lorairo/services/model_filter_service.py`
- **クラス**: `ModelFilterService`
- **目的**: AI モデルのフィルタリングと管理を担う

#### ModelSelectionService
- **パス**: `src/lorairo/services/model_selection_service.py`
- **クラス**: `ModelSelectionService`
- **目的**: モデル選択ロジックとプリセット管理を担う

#### ModelRouteService
- **パス**: `src/lorairo/services/model_route_service.py`
- **目的**: WebAPI モデルの direct 経路と OpenRouter 経路の判定、表示用の畳み込み、API キーの事前検証を担う

#### ModelSyncService
- **パス**: `src/lorairo/services/model_sync_service.py`
- **クラス**: `ModelSyncService`
- **目的**: モデル設定の同期とキャッシュ管理を担う

#### ModelRegistryProtocol
- **パス**: `src/lorairo/services/model_registry_protocol.py`
- **目的**: モデルレジストリのプロトコルを定義する

### 検索・フィルタ

#### search_review_status(ヘルパー)
- **パス**: `src/lorairo/services/search_review_status.py`
- **目的**: 保存済みの Clef 判定を鮮度確認したうえで検索サムネイルへ付与し、全検索結果から現在有効な警告を絞り込む
- **境界**: 検索時にローカル Clef の起動や推論は行わない。未チェック、失敗、未評価、古い結果を区別して扱う

#### SearchCriteriaProcessor
- **パス**: `src/lorairo/services/search_criteria_processor.py`
- **クラス**: `SearchCriteriaProcessor`
- **目的**: 検索条件の処理とフィルタリングロジックを担う

#### SearchModels
- **パス**: `src/lorairo/services/search_models.py`
- **目的**: 検索用のデータモデルを定義する

### 状態管理

#### SelectionStateService
- **パス**: `src/lorairo/services/selection_state_service.py`
- **クラス**: `SelectionStateService`
- **目的**: アプリケーション内の選択状態を管理する

### ユーティリティ

#### DbMaintenanceCheckService(Qt-free)
- **パス**: `src/lorairo/services/db_maintenance_check_service.py`
- **クラス**: `DbMaintenanceCheckService`
- **目的**: Provider Batch の DB 状態の整合性と、画像実ファイルの欠損を読み取り専用で点検する(`maintenance check`、ADR 0099)

#### DateFormatter
- **パス**: `src/lorairo/services/date_formatter.py`
- **目的**: 日付フォーマットの統一処理を担う

#### FavoriteFiltersService
- **パス**: `src/lorairo/services/favorite_filters_service.py`
- **クラス**: `FavoriteFiltersService`
- **目的**: お気に入りフィルター条件の永続化を管理する

#### FolderCommonTags(Qt-free)
- **パス**: `src/lorairo/services/folder_common_tags.py`
- **目的**: ディレクトリ取り込み時に、サブフォルダごとの共通タグを直下の全画像へ `MANUAL_EDIT` タグとして付与する

#### ImageRegistrationService
- **パス**: `src/lorairo/services/image_registration_service.py`
- **クラス**: `ImageRegistrationService`
- **目的**: 画像ファイルの DB 登録ワークフローを管理する

#### ProjectManagementService
- **パス**: `src/lorairo/services/project_management_service.py`
- **目的**: プロジェクトの作成、切り替え、管理を担う

#### TagSuggestionService
- **パス**: `src/lorairo/services/tag_suggestion_service.py`
- **目的**: タグのオートコンプリート候補取得とキャッシュ管理を担う(TTL + LRU、スレッドセーフ)
- **統合**: `genai-tag-db-tools` の `search_tags()` API

### バッチインポート

#### ProviderBatchJobService
- **パス**: `src/lorairo/services/provider_batch_service.py`
- **目的**: Provider Batch API のジョブライフサイクルを扱う共通サービス境界
- **操作**: `submit_batch`、`submit`(レガシー)、`refresh`、`cancel`、`fetch_results`、`download_results`
- **ステータス正規化**: `normalize_status()` と `validate_transition()` で 10 種の共通ステータスを管理する
- **Custom ID の SSoT**: `build_custom_id(image_id)` で `img-{image_id}` 形式を生成する
- **利用ガイド**: [docs/provider-batch-api.md](provider-batch-api.md)

#### ProviderBatchWorkflowService
- **パス**: `src/lorairo/services/provider_batch_workflow_service.py`
- **目的**: GUI・API・CLI から再利用する Provider Batch API のワークフローファサード
- **操作**: `build_submit_request`、`submit_images`、`refresh`、`cancel`、`fetch_results`、**`import_results`**、`apply_result_items`
- **再インポート制御**: `import_results()` は `job.status == "imported"` または `imported_at IS NOT NULL` の場合に拒否する
- **アダプター配線**: `ServiceContainer.provider_batch_workflow_service` は、`image-annotator-lib` 境界へ委譲する `ProviderBatchLibraryAdapter` を主要プロバイダー用に登録する

#### provider_batch_capability(ヘルパー)
- **パス**: `src/lorairo/services/provider_batch_capability.py`
- **目的**: Provider Batch 適格性を扱う Qt 非依存ヘルパー。モデルオブジェクトから batch-capable 判定、direct プロバイダー解決、`litellm_model_id` 抽出を行う
- **関数**: `direct_provider_for_model()`、`litellm_id_from_batch_model()`
- **用途**: `ModelSelectionWidget` の batch-capable フィルタなど

#### provider_batch_library_compat(ヘルパー)
- **パス**: `src/lorairo/services/provider_batch_library_compat.py`
- **目的**: `image-annotator-lib` の Provider Batch DTO との互換ヘルパー。LoRAIro 側のリクエスト・レスポンスを導入済みライブラリの DTO へ相互変換する
- **関数**: `to_library_submit_request()` など

#### BatchImportService
- **パス**: `src/lorairo/services/batch_import_service.py`
- **目的**: OpenAI Batch API の JSONL 結果を一括インポートする

#### BatchContentParser
- **パス**: `src/lorairo/services/batch_content_parser.py`
- **目的**: OpenAI Batch API 応答の content テキストを解析する

#### BatchImageMatcher
- **パス**: `src/lorairo/services/batch_image_matcher.py`
- **クラス**: `BatchImageMatcher`
- **目的**: JSONL の `custom_id` と DB の `image_id` を一括照合する
- **操作**: `match_all(custom_ids)`(ADR 0062 形式の `ph:{phash}:le:{long_edge}` は pHash で照合し、それ以外はファイル名の stem で照合する)、`extract_stem(custom_id)`
- **結果**: `ImageMatchResult`(`matched` / `unmatched` / `ambiguous`)

### ジョブ・品質・パイプライン(Wireframes v11 / ADR 0066)

#### DispatchProjectionService(Qt-free)
- **パス**: `src/lorairo/services/dispatch_projection_service.py`
- **目的**: アノテーション画面で選択されたモデル集合を、非同期 Provider Batch 送信の射影として確定する(ADR 0076 §2)。選択モデルと `list_batch_capable_models()` の検出結果の積集合を取り、`provider_batch_capability` ヘルパーでプロバイダーとタスクのルールを判定する
- **不変条件**: 非 batch-capable モデルが混在する場合は拒否し、部分射影は行わない。1 送信につき 1 モデル(1 `DispatchEntry` につき `provider_batch_jobs` 1 行)とする

#### CostEstimationService
- **パス**: `src/lorairo/services/cost_estimation_service.py`
- **クラス**: `CostEstimationService`
- **目的**: アノテーション推論のコストと所要時間をバッチ全体で概算する(Wireframes v11 Frame 2B / Issue #747)

#### ErrorTriageService
- **パス**: `src/lorairo/services/error_triage_service.py`
- **クラス**: `ErrorTriageService`
- **目的**: エラーレコードを同一原因でグルーピングし、サマリとフィルタを提供する(Qt-free)

#### JobLedgerService
- **パス**: `src/lorairo/services/job_ledger_service.py`
- **クラス**: `JobLedgerService`
- **目的**: インメモリのジョブ台帳として、ジョブのライフサイクル状態を一元管理する(ADR 0066 Unified Jobs Lifecycle View)

#### PipelineCompositionService
- **パス**: `src/lorairo/services/pipeline_composition.py`
- **クラス**: `PipelineCompositionService`
- **目的**: アノテーションパイプライン構成の Qt 非依存ドメインモデル(Wireframes v11 Frame 2A / Phase 6a)

#### DatasetImportService
- **パス**: `src/lorairo/services/dataset_import_service.py`
- **クラス**: `DatasetImportService`
- **目的**: Kohya-ss 形式の学習データセットを版・フォルダ・学習テキストとして取り込む(Qt-free)。画像は登録のみ行い、画像直下の `Tag` には書き込まない。永続化は `DatasetRepository`(`src/lorairo/database/repository/dataset.py`)が担う。CLI は `lorairo-cli dataset import / export / show / diff / copy-tags / usage` を提供する(`copy-tags` は学習テキストをライブラリの `Tag` へ写す。ADR 0104)

#### KohyaDatasetExportService
- **パス**: `src/lorairo/services/kohya_dataset_export_service.py`
- **クラス**: `KohyaDatasetExportService`
- **目的**: 保存済みの版を Kohya-ss 形式(画像、学習テキスト、sd-scripts 用 TOML)で書き出す(Qt-free)

#### DatasetVersionDiffService
- **パス**: `src/lorairo/services/dataset_version_diff.py`
- **クラス**: `DatasetVersionDiffService`(関数: `diff_snapshots()`)
- **目的**: 2 つの版のフォルダ、画像(追加・削除・差し替え)、学習テキスト(要素の追加・削除・並び替え)の差分を表示時に計算する(Qt-free、保存はしない)。CLI は `lorairo-cli dataset diff` に対応する

#### ImageComparisonService(Qt-free)
- **パス**: `src/lorairo/services/image_comparison.py`
- **クラス・関数**: `ImageComparisonService`、`ComparisonSelection`、`diff_tags()`、`diff_caption()`、`snapshot_from_metadata()`
- **目的**: 2 枚の画像の現在のタグ(共通・左のみ・右のみ)とキャプション(原文を保ったテキスト差分)を読み取り専用で比較し、比較画面の左右選択と片側固定の状態を管理する。片側に情報が無い場合は比較せず、欠けている側を返す。画面は `gui/widgets/image_comparison_dialog.py`、読み込みは `gui/workers/image_comparison_worker.py` が担う

#### GenerationMetadataParser(Qt-free)
- **パス**: `src/lorairo/services/generation_metadata_parser.py`
- **関数**: `extract_generation_metadata()`、`read_generation_sources()`、`parse_generation_sources()`、`parse_sd_webui_parameters()`
- **目的**: 画像に埋め込まれた生成情報(PNG の `parameters`、`prompt`、`workflow`、EXIF UserComment)を整形前の原データとして取り出し、SD WebUI 形式を共通項目へ解析する。ComfyUI は判定のみ行う。結果型は `domain/generation_metadata.py`、保存は `GenerationMetadataRepository` が担う(ADR 0105)

#### KohyaScanner
- **パス**: `src/lorairo/services/kohya_scanner.py`
- **目的**: `<繰り返し数>_<名前>/` フォルダと学習テキストをスキャンし、トリガーワード候補を検出する(Qt-free)

#### LearningText
- **パス**: `src/lorairo/services/learning_text.py`
- **関数**: `split_elements()`、`join_elements()`
- **目的**: 学習テキストを正規化せずに要素分割および連結する

#### KohyaConfigNormalizer
- **パス**: `src/lorairo/services/kohya_config_normalizer.py`
- **目的**: Kohya_ss GUI の設定 JSON を sd-scripts の引数名と型へ正規化する。秘密の値を除去し、未変換キーを分離する

#### SdScriptsToml / SdScriptsArgTable
- **パス**: `src/lorairo/services/sd_scripts_toml.py`、`src/lorairo/services/sd_scripts_arg_table.py`
- **目的**: sd-scripts 用 TOML(`--dataset_config`、`--config_file`)の書き出しと、引数名・型の対応表を提供する(対応表は `scripts/gen_sd_scripts_arg_table.py` で生成)

#### QualityIssueDetectionService
- **パス**: `src/lorairo/services/quality_issue_detection_service.py`
- **クラス**: `QualityIssueDetectionService`
- **目的**: アノテーション品質の構造的問題を閾値非依存で検出する(Qt-free)

#### TagCloudService
- **パス**: `src/lorairo/services/tag_cloud_service.py`
- **クラス**: `TagCloudService`
- **目的**: キーワード連動の共起タグ探索(共起グラフ生成)を担う

## GUI サービス

Qt 依存の GUI サービス群である。Signal/Slot によるウィジェット間通信をサポートする。

### ワーカー調整

#### WorkerService
- **パス**: `src/lorairo/gui/services/worker_service.py`
- **クラス**: `WorkerService`
- **目的**: Qt ベースの非同期タスク調整を担う
- **パターン**: `QThreadPool` + `QRunnable`
- **統合**: `WorkerManager` と連携する

### 検索・フィルタ

#### SearchFilterService
- **パス**: `src/lorairo/gui/services/search_filter_service.py`
- **クラス**: `SearchFilterService`
- **目的**: GUI 向けの検索・フィルタ操作を担う
- **統合**: `MainWindow` へ統合済み
- **シグナル**: 検索結果およびフィルタ状態の変更通知

### パイプライン制御

#### PipelineControlService
- **パス**: `src/lorairo/gui/services/pipeline_control_service.py`
- **クラス**: `PipelineControlService`
- **目的**: 処理パイプラインの制御と状態管理を担う

### 状態・進捗管理

#### ProgressStateService
- **パス**: `src/lorairo/gui/services/progress_state_service.py`
- **クラス**: `ProgressStateService`
- **目的**: 進捗状態の管理と Signal 通知を担う

#### ResultHandlerService
- **パス**: `src/lorairo/gui/services/result_handler_service.py`
- **クラス**: `ResultHandlerService`
- **目的**: 処理結果のハンドリングと UI 反映を担う

### データベース統合

#### ImageDBWriteService
- **パス**: `src/lorairo/gui/services/image_db_write_service.py`
- **クラス**: `ImageDBWriteService`
- **目的**: 画像データベース書き込み操作の GUI ラッパー

### GUI ウィジェット

Qt ベースの GUI ウィジェット群である。`MainWindow` 内で `QTabWidget` として統合される。

#### BatchTagAddWidget
- **パス**: `src/lorairo/gui/widgets/batch_tag_add_widget.py`
- **UI ファイル**: `src/lorairo/gui/designer/BatchTagAddWidget.ui`
- **クラス**: `BatchTagAddWidget`
- **目的**: 複数画像に対して 1 つのタグを一括追加する
- **構成**:
  - `QTabWidget` のタブ 3(バッチタグ追加)として統合される
  - `OrderedDict[int, str]` でステージングリストを管理する(挿入順保持と重複防止)
  - ステージング上限は 500 画像である
- **統合**:
  - `TagCleaner.clean_format()` で正規化する(アンダースコアを空白へ変換し小文字化)
  - `DatasetStateManager.selected_image_ids` から選択画像を取得する
  - `ImageDBWriteService.add_tag_batch()` で DB へ一括書き込む
- **シグナル**:
  - `staged_images_changed(list)`: ステージングリスト変更通知
  - `tag_add_requested(list, str)`: タグ追加リクエスト(`image_ids`, `normalized_tag`)
  - `staging_cleared()`: ステージングリストクリア通知
- **機能**:
  - ドラッグ選択同期(`ThumbnailSelectorWidget` から `DatasetStateManager` へ連携)
  - 個別削除(Delete キーで選択アイテムを削除)
  - 全クリアボタン
  - 空タグのバリデーション
  - 重複画像の自動スキップ
- **テスト**:
  - ユニットテスト: 21 件、カバレッジ 97%
  - 統合テスト: 11 件、成功率 100%

#### RatingScoreEditWidget
- **パス**: `src/lorairo/gui/widgets/rating_score_edit_widget.py`
- **UI ファイル**: `src/lorairo/gui/designer/RatingScoreEditWidget.ui`
- **クラス**: `RatingScoreEditWidget`
- **目的**: 単一画像の Rating と Score を編集する
- **構成**:
  - `QTabWidget` のタブ 2(Rating/Score 編集)として統合される
  - 読み取り専用化した `SelectedImageDetailsWidget` から分離されている
- **UI コンポーネント**:
  - Rating 選択: `QComboBox`(`PG`, `PG-13`, `R`, `X`, `XXX`)
  - Score 調整: `QSlider`(内部値 0–1000、表示 0.00–10.00)
  - 現在値ラベル: リアルタイム更新
- **データ変換**:
  - UI 内部: 0–1000(精度維持)
  - UI 表示: 0.00–10.00(`value / 100.0`)
  - DB 格納: 0.0–10.0 Float(`value / 100.0`)
- **シグナル**:
  - `rating_changed(int, str)`: Rating 変更通知(`image_id`, `rating`)
  - `score_changed(int, int)`: Score 変更通知(`image_id`, `score`)

## 設計パターン

### Qt-Free Core パターン

CLI ツールを Qt 非依存で動作させつつ、GUI には完全な Signal サポートを提供するためのパターンである。

**実装例: `TagRegisterService`**

```
Core Service (Qt-free):
  genai_tag_db_tools/services/tag_register.py
  - TagRegisterService (Qt依存なし)
  - register_tag(), search_and_register() 等のコアロジック

GUI Wrapper (Qt-dependent):
  genai_tag_db_tools/gui/services/gui_tag_register_service.py
  - GuiTagRegisterService (QObject継承)
  - Compositionパターンでコアサービスを内包
  - Signal emit (tag_registered, error_occurred等)
```

**利点**:
- CLI ツールはコアサービスを直接使用でき、Qt を必要としない
- GUI アプリは GUI ラッパー経由で Signal 通知を受け取れる
- コアロジックを単独でユニットテストできる

### 依存性注入(DI)

`ServiceContainer` が全サービスのシングルトン管理、依存関係の自動解決、テスト時のモック注入を担う。

**使用例**:

```python
from src.lorairo.services.service_container import get_service_container

container = get_service_container()
config = container.get_config_service()
tag_service = container.get_tag_management_service()
```

### Signal 通信

GUI サービス間は Qt の Signal/Slot によるイベント駆動アーキテクチャで疎結合に連携し、非同期処理の完了などを通知する。

**主要シグナル**:
- `SearchFilterService`: 検索結果、フィルタ変更
- `ProgressStateService`: 進捗更新
- `ResultHandlerService`: 処理完了、エラー通知

## サービスライフサイクル

### 初期化順序

1. **ConfigurationService**: 設定ファイルを読み込む
2. **ServiceContainer**: DI コンテナを初期化する
3. **ビジネスロジックサービス**: コアサービス群を初期化する
4. **GUI サービス**: ウィジェット連携サービス群を初期化する

### シャットダウン順序

1. **GUI サービス**: Signal を切断し、リソースを解放する
2. **ビジネスロジックサービス**: 処理中タスクの完了を待機する
3. **データベース**: コネクションを終了する
4. **設定**: 設定を保存する

## テスト戦略

### ユニットテスト

- ビジネスロジックサービスは Qt 非依存のまま単独でテストする
- モック対象はファイルシステム、ネットワーク、外部 API などの外部依存に限定する
- カバレッジ目標は 75% 以上とする

### 統合テスト

- GUI サービスは pytest-qt で Signal の発火と遷移を検証する
- 待機には `qtbot.waitSignal()` と `qtbot.waitUntil()` を使う
- モック対象は `QMessageBox` などの UI 要素のみとする

### テスト構成

```
tests/
├── unit/
│   └── services/          # Business Logic Services
├── integration/
│   └── gui/services/      # GUI Services
└── bdd/                   # E2E tests
```

## メンテナンスガイドライン

### 新規サービスの追加

1. **ビジネスロジックサービス**(`src/lorairo/services/` に作成):
   - Qt に依存させない
   - Google スタイルの docstring を記述する
   - 型ヒントを必ず付与する
   - `ServiceContainer` へ登録する

2. **GUI サービス**(`src/lorairo/gui/services/` に作成):
   - `QObject` を継承する
   - 必要な Signal を定義する
   - コンポジションパターンでコアロジックへ委譲する

### サービスの責務

単一責任の原則(SRP)に従い、1 サービスにつき 1 つの明確な責務を持たせる。処理が複雑化した場合は分割を検討する。

- 分割例: `ModelService` を `ModelFilterService`、`ModelSelectionService`、`ModelSyncService` へ分離

### 非推奨化プロセス

1. `@deprecated` デコレーターを付与する
2. 新サービスへの移行手順を文書化する
3. 1 リリースサイクルの経過後に削除する

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) — 開発概要
- [docs/integrations.md](integrations.md) — 外部パッケージ統合
- [docs/testing.md](testing.md) — テスト戦略
- [docs/architecture.md](architecture.md) — システム設計原則
