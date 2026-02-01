# Plan: wild-rolling-ripple

**Created**: 2026-01-31
**Source**: manual_sync
**Original File**: wild-rolling-ripple.md
**Status**: implemented

---

# Tech-Debt整理計画: High Tier全18ファイル + __main__ハーネス

## スコープ
- **対象**: Priority >= 10.5 の18ファイル（合計 ~11,000行）+ __main__ハーネス（全30ファイル中24対象）
- **目標**: R/E/T スコア改善、最長メソッド60行以下、カバレッジ75%維持
- **方針**: 公開API維持（後方互換）、各フェーズ独立マージ可能
- **推奨実施順序**: Phase 2 → 1 → 5 → 3 → 4（並行可: 2+5, 1単独。3はPhase 5後）
- **新規ファイル**: プロダクション16本 + テスト17本 = 33ファイル

## フェーズ概要

| Phase | 対象領域 | 削減見込 | 新規ファイル | 依存 |
|-------|---------|---------|------------|------|
| 1 | WebAPI Annotator共通化 (5ファイル) | ~430行 | 1 | なし |
| 2 | ModelFactory Loader分離 (1→6ファイル) | ~1,100行 | 6 | なし |
| 3 | Database Worker分離 + Repository減量 (3ファイル) | ~1,600行 | 5 | Phase 5（associated_file_reader参照） |
| 4 | annotator-lib小規模整理 (6ファイル) | ~850行 | 2 | Phase 1 |
| 5 | genai-tag-db-tools Repository + batch_processor (2ファイル) | ~700行 | 1 | なし（Phase 3がPhase 5のassociated_file_readerを参照） |
| 並行 | __main__ハーネス整理 (24ファイル) | ~500-1000行 | 1 | なし |

---

## Phase 1: WebAPI Annotator共通化 (P=13.5~12.0, 合計1,134行)

**対象**: webapi_helpers.py(315行), openai_api_chat.py(220行), anthropic_api.py(206行), google_api.py(214行), openai_api_response.py(179行)

**問題点**:
- raw_output処理が5ファイルで完全重複（MagicMock検出→model_dump→__dict__→fallbackの4段階分岐）
- エラーハンドリング重複（ModelHTTPError, UnexpectedModelBehavior, Exceptionの3段階catch文）
- webapi_helpers.py: `_initialize_api_client()` 120行に4プロバイダー分岐密集、.env毎回再読み込み
- 画像変換重複: 各クラスの`_preprocess_images_to_binary()`が同一実装

**新規**: `core/base/webapi_common.py` (~150行)
- `WebApiResponseProcessor`: raw_output変換統合（convert_to_raw_output()）
- `WebApiErrorHandler`: 3段階catch文をisinstance分岐で統合（handle_inference_error()）
- `ApiKeyCache`: .env遅延読み込み＋キャッシュ（ClassVar, get_api_key()）

**変更**:
- 各WebAPIクラスのrun_with_model()重複コード→WebApiResponseProcessorに置換
- エラーハンドリング→WebApiErrorHandlerに委譲
- webapi_helpers.py: _initialize_api_client() 120行→プロバイダー別4メソッド（_init_openai_client等、各25-30行）
- _get_api_key()→ApiKeyCache.get_api_key()に置換

**成功基準**: 1,134行→~700行（38%削減）、公開API不変、75%カバレッジ維持
**リスク**: MagicMock対策統合漏れ(高)→既存unit test検証、PydanticAI Agent caching(中)→呼び出し不変
**テスト**: 新規test_webapi_common.py（30ケース）+ 既存5プロバイダーintegration test回帰

---

## Phase 2: ModelFactory Loader分離 (P=13.5, 1,532行)

**対象**: model_factory.py(1,532行)

**問題点**:
- God Object: ModelLoadクラス1,532行に5内部Loader全包含
- ClassVar辞書4個: _MODEL_STATES, _MEMORY_USAGE, _MODEL_LAST_USED, _MODEL_SIZES
- 長メソッド: _CLIPLoader._calculate_specific_size() 58行
- 深ネスト: _CLIPLoader._infer_classifier_structure() 5レベル
- 重複: gc.collect(), サイズ計算, メモリチェックが各Loaderで重複
- Lazy import散在: torch, tensorflow, transformers, onnxruntime

**新規ファイル**:
1. `core/loaders/__init__.py`
2. `core/loaders/loader_base.py` (~200行) — LoaderBase(ABC)
   - ClassVar辞書4個を一元管理、threading.Lock排他制御
   - load_components(): 共通フロー（サイズ計算→メモリチェック→ロード→状態更新）
   - _ensure_memory_available(): LRU eviction共通実装
   - abstract: _load_components_internal(), _calculate_specific_size()
3. `core/loaders/transformers_loader.py` (150-250行) — AutoModelForVision2Seq
4. `core/loaders/onnx_loader.py` (150-250行) — InferenceSession
5. `core/loaders/tensorflow_loader.py` (150-250行) — H5/SavedModel判定
6. `core/loaders/clip_loader.py` (150-250行) — _infer_classifier_structure含む

**ModelLoad Facade化** (~400行):
- _get_loader()で遅延初期化、load_*_components()は各Loaderに委譲
- 全公開API（load_transformers_components, cache_to_main_memory, get_model_state）シグネチャ完全維持

**成功基準**: 1,532行→~400行Facade + 各Loader150-250行（計~1,000行）、公開API不変
**リスク**: ClassVar競合(高)→LoaderBase一元管理+Lock、循環import(高)→依存一方向、Lazy import移行(中)→TYPE_CHECKING+関数内import統一
**テスト**: 新規6ファイル（test_loader_base + 各Loader独立test）+ 既存test_model_factory回帰

---

## Phase 3: Database Worker分離 + Repository減量 (P=12.0~10.5, 合計4,338行)

**対象**: database_worker.py(485行), db_repository.py(2,783行), db_manager.py(1,070行)

**問題点**:
- database_worker.py: 3独立Worker（Registration, Search, Thumbnail）が1ファイル混在、execute()100行/126行
- db_repository.py: 60メソッド巨大クラス、100行超メソッド4個（_format_annotations_for_metadata 135行, get_images_by_filter 133行等）、深ネスト137箇所
- db_manager.py: register_original_image() 105行、専用unit testなし

**Worker3分割**:
- database_registration_worker.py (~160行): execute()を段階別メソッドで60行以下に
- search_worker.py (~80行)
- thumbnail_worker.py (~150行): _load_batch() + _process_single()に分割

**ヘルパー抽出**:
- database/helpers/tag_id_resolver.py (~100行): TagIdResolver（外部タグDB検索＋登録、resolve_tag_ids/bulk）
- database/helpers/annotation_formatter.py (~200行): format_for_metadata/export

**長大メソッド分割**:
- get_images_by_filter 133行→40行オーケストレーター + _apply_tag/rating/date/annotation_filters
- _get_or_create_tag_id_external 105行→TagIdResolverに委譲
- register_original_image 105行→40行 + _validate/_extract/_generate

**成功基準**: Worker3分離、db_repository 2,783→~2,000行、db_manager 1,070→~700行、最長60行以下
**リスク**: Worker Signal配線(中)→型判定不変、ヘルパー抽出(高)→private置換のみ、db_managerテスト不足(中)→先行test追加
**テスト**: 新規6ファイル（Worker×3, TagIdResolver, AnnotationFormatter, test_db_manager）+ 既存82 tests回帰

---

## Phase 4: annotator-lib小規模整理 (P=13.5~10.5, Phase 1依存, 合計2,537行)

**対象**: api.py(495行), registry.py(609行), annotator.py(260行), onnx.py(332行), adapters.py(307行), provider_manager.py(534行)

**問題点**:
- api.py: annotate() 136行にpHash計算・モデルループ・エラー処理混在、グローバル_MODEL_INSTANCE_REGISTRY
- registry.py: _register_models() 114行、グローバル_REGISTRY_INITIALIZED
- annotator.py: predict() 91行に前処理・推論・整形・結果処理集約、4レベルネスト
- onnx.py: _format_predictions_single() 99行
- adapters.py: 3Adapterで重複（try-except、パラメータ展開）
- provider_manager.py: 4Provider重複画像変換（Image→WEBP→BinaryContent）

**新規**:
- `core/instance_cache.py` (~80行): InstanceCache（ClassVar + Lock, get_or_create/clear）
- `core/model_factory_adapters/adapter_base.py` (~100行): AdapterBase(ABC)（_create_client, _build_request, call_api共通フロー）

**分割**:
- annotate() 136行→40行 + _prepare_images(30行) + _execute_models(40行) + _execute_single_model(30行)
- _register_models() 114行→_discover/_filter/_register 3段階
- _format_predictions_single() 99行→_filter_by_threshold/_map_to_tags/_build_annotation_result 3段階
- 4Provider画像変換→ProviderInstanceBase._convert_image_to_binary()共通化

**成功基準**: api.py 495→~300行、adapters.py 307→~150行、全メソッド60行以下
**リスク**: InstanceCacheスレッドセーフ(中)→Lock+test、AdapterBase後方互換(低)→公開API内部変更のみ
**テスト**: 新規test_instance_cache + test_adapter_base + 既存integration回帰

---

## Phase 5: genai-tag-db-tools + batch_processor (P=12.0, 合計1,495行)

**対象**: repository.py(1,288行), batch_processor.py(207行)

**問題点**:
- repository.py: TagReader(330行/33メソッド), TagRepository(517行/22メソッド), MergedTagReader(372行/35メソッド)
- search_tags() 55行の7段階フィルタ、update_tags_type_batch() 90行
- MergedTagReader全メソッドが_iter_repos()パターン繰返し
- batch_processor.py: process_directory_batch() 133行、コールバック4個混在

**変更（メソッド分割のみ、CQRS見送り）**:
- search_tags→_build_search_query + _apply_search_filters + _format_search_results
- update_tags_type_batch→_validate + _chunk + _execute_batch_updates
- MergedTagReader→_merge_from_repos()共通ヘルパー（getattr+結果マージ）
- process_directory_batch→_discover_images + _check_duplicates + _register_to_db + _process_associated_files
- 重複コード統合: utils/associated_file_reader.py（Phase 3 Workerからも参照）

**成功基準**: repository.py 1,288→~900行、batch_processor.py 207→~150行、97%カバレッジ維持
**リスク**: MergedTagReaderマージ順序(高)→既存test検証、重複統合Worker影響(中)→Phase 3後実施
**テスト**: 既存genai-tag-db-tools全実行 + test_batch_processor回帰 + MergedTagReader優先順位重点検証

---

## __main__ハーネス整理 (30ファイル中24対象)

**アクション別分類**:
- **__main__ブロック削除 (18)**: GUI Widget14 + genai-tag-db-tools Widget4 → scripts/debug/widget_preview.pyに統合
- **ファイルごと削除 (3)**: prototypes/pydanticai_integration/ (simple_test, pydantic_ai_agent, openai_agent_annotator)
- **移動 (3)**: integration_test.py→tests/、config.py→scripts/check_config.py
- **保持 (6)**: main.py×2, tag_statistics.py, check_api_model_discovery.py, manual_simple_test.py, test_unified_provider_level_integration.py

**統合スクリプト**: scripts/debug/widget_preview.py
- `uv run python scripts/debug/widget_preview.py WidgetClassName`
- WIDGET_REGISTRY辞書で全ウィジェットをモジュールパス+クラス名で管理
- importlib.import_module()で動的ロード

---

## 新規ファイル一覧（全Phase合計）

**Phase 1** (1+1): webapi_common.py + test
**Phase 2** (6+6): loaders/__init__.py, loader_base.py, transformers/onnx/tensorflow/clip_loader.py + tests
**Phase 3** (5+7): 3 Worker files, tag_id_resolver.py, annotation_formatter.py + tests
**Phase 4** (2+2): instance_cache.py, adapter_base.py + tests
**Phase 5** (1+1): associated_file_reader.py + test
**__main__** (1): widget_preview.py

**合計**: プロダクション16 + テスト17 = 33ファイル

## 検証計画（全Phase共通）
1. ruff check + format → 2. mypy → 3. pytest unit → 4. pytest integration → 5. カバレッジ75%確認

**詳細設計のコード例（クラス定義・メソッドシグネチャ）は上記各Phaseセクションに記載済み。本Memory単体で計画の全貌を把握可能。**