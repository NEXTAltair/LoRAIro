# Plan: composed-discovering-ullman

**Created**: 2026-02-03 08:45:53
**Source**: plan_mode
**Original File**: composed-discovering-ullman.md
**Status**: implemented

---

# Tech Debt Batch A 最適化計画

## 目的
R/E/T（Readability/Efficiency/Testability）スコア12.0以上の7ファイルを最適化する。
- 長大関数の分割（<=60行目標）
- UI/IO/DBの責務分離
- 重複コード除去
- 既存テストの回帰ガード維持（75%+カバレッジ）

## 実施順序（ボトムアップ依存関係順）

依存される側から着手し、影響を上流に波及させない。

### Phase 1: Foundation（低リスク・基盤クラス）

#### Step 1: base/annotator.py (260行 → ~180行)
**対象**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/base/annotator.py`

| 問題 | 対策 |
|------|------|
| `predict()` 91行 | フェーズ分割: `_prepare_input()`, `_execute_prediction()`, `_build_result()` に抽出 |
| エラー結果生成3箇所重複 | `_create_error_result(error_type, message)` ヘルパー抽出 |

**検証**: `uv run pytest local_packages/image-annotator-lib/tests/unit/core/test_base_annotator_di.py local_packages/image-annotator-lib/tests/unit/standard/core/base/test_annotator.py -v`

#### Step 2: adapters.py (307行 → ~230行)
**対象**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory_adapters/adapters.py`

| 問題 | 対策 |
|------|------|
| `OpenAIAdapter.call_api()` 95行, `GoogleClientAdapter.call_api()` 93行 | 各アダプターの `call_api()` を `_build_messages()`, `_build_tools()`, `_execute_request()`, `_parse_response()` に分割 |
| 共通化前の差分整理が無い | プロバイダー別 schema/params の差分表を先に作成し、共通化範囲を確定 |
| tool/function schema設定が3アダプターで重複 | 共通スキーマ生成を基底クラスまたはモジュール関数に抽出 |

**検証**: `uv run pytest local_packages/image-annotator-lib/tests/unit/core/model_factory_adapters/test_adapters.py -v`

#### Step 3: genai-tag-db-tools/repository.py (1,309行 → ~900行)
**対象**: `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py`

| 問題 | 対策 |
|------|------|
| `MergedTagReader` 33メソッドの委譲パターン（3種のマージ戦略が混在） | **パターンヘルパー抽出**: `_first_found()`, `_merge_by_key()`, `_accumulate_unique()` の3ヘルパーを定義。各メソッドは明示的シグネチャを保持しつつ、本体を1-2行に圧縮 |
| `update_tag_status()` 77行 | バリデーション・更新・後処理に分割 |
| `update_tags_type_batch()` 63行 | 型解決ロジックを `_resolve_type_id()` に抽出 |

**実装ルール**: ヘルパーの戻り値は `Any` 許容、公開メソッドの戻り型シグネチャは具体型を維持。

**MergedTagReader リファクタリング詳細**:
```python
# ヘルパー: 3つのマージパターンを抽象化
def _first_found(self, method: str, *args, **kwargs) -> Any:
    """User優先で最初にヒットした結果を返す（15メソッドで使用）"""

def _merge_by_key(self, method: str, key_fn, *args, **kwargs) -> list:
    """全repoから集めてキーで重複排除（5メソッドで使用）"""

def _accumulate_unique(self, method: str, key_fn, *args, **kwargs) -> list:
    """全repoから蓄積して一意化（3メソッドで使用）"""

# Before: 10行/メソッド
def get_tag_id_by_name(self, keyword: str, partial: bool = False) -> int | None:
    if self._has_user():
        assert self.user_repo is not None
        user_id = self.user_repo.get_tag_id_by_name(keyword, partial=partial)
        if user_id is not None: return user_id
    for repo in self._iter_base_repos():
        base_id = repo.get_tag_id_by_name(keyword, partial=partial)
        if base_id is not None: return base_id
    return None

# After: 2行/メソッド（シグネチャ+型ヒント保持、IDE補完・mypy対応）
def get_tag_id_by_name(self, keyword: str, partial: bool = False) -> int | None:
    return self._first_found("get_tag_id_by_name", keyword, partial=partial)
```

**メリット**: IDE補完維持（明示的メソッド定義）+ コード量~60%削減 + テスタビリティ向上（ヘルパー単体テスト可能）+ 外部ライブラリ不要

**検証**: `uv run pytest local_packages/genai-tag-db-tools/tests/unit/test_tag_repository.py -v`

### Phase 2: Integration（中リスク・インフラ層）

#### Step 4: webapi_helpers.py (315行 → ~220行)
**対象**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory_adapters/webapi_helpers.py`

| 問題 | 対策 |
|------|------|
| `_initialize_api_client()` 123行の4分岐 | プロバイダー別初期化関数に分割し、辞書ディスパッチ: `_PROVIDER_INITIALIZERS = {"openai": _init_openai, ...}` |
| `.env`読み込み2箇所重複 | `_load_env_api_key(key_name)` に統一 |
| `prepare_web_api_components()` 75行 | コンポーネント構築を `_build_model_config()`, `_build_client()` に分割 |

**検証**: `uv run pytest local_packages/image-annotator-lib/tests/unit/core/model_factory_adapters/test_webapi_helpers.py -v`

#### Step 5: registry.py (609行 → ~450行)
**対象**: `local_packages/image-annotator-lib/src/image_annotator_lib/core/registry.py`

| 問題 | 対策 |
|------|------|
| `_register_models()` 98行 | モジュール発見・クラスフィルタ・登録の3段階に分割 |
| `initialize_registry()` 70行 | `_init_logger()`, `_discover_api_models()`, `_update_config()` に分割 |
| `list_available_annotators_with_metadata()` 71行 | メタデータ組み立てをイテレータ/ヘルパーに抽出 |
| obsoleteクラスフィルタ重複 | `_is_obsolete_annotator(cls)` 共通関数化 |

**検証**: `uv run pytest local_packages/image-annotator-lib/tests/unit/standard/core/test_registry.py -v`

#### Step 6: annotation_worker.py (403行 → ~280行)
**対象**: `src/lorairo/gui/workers/annotation_worker.py`

| 問題 | 対策 |
|------|------|
| `execute()` 123行 | `_run_annotation()`, `_save_results()`, `_handle_error()` に分割 |
| エラーレコード保存2箇所重複 | `_save_error_record(image_id, error)` 抽出 |
| image_id 取得失敗時の挙動が曖昧 | Noneの場合は記録をスキップし warning ログ（or 明示的に失敗を記録） |
| `_convert_to_annotations_dict()` 106行 | Pydantic/dict二重アクセスパターンを `_extract_field(result, field_name)` で統一 |

**検証**: `uv run pytest tests/unit/gui/workers/test_annotation_worker.py tests/integration/gui/workers/test_worker_error_recording.py -v`

### Phase 3: God Class分割（高リスク・段階的実施）

#### Step 7: db_repository.py (2,785行 → ~1,500行)
**対象**: `src/lorairo/database/db_repository.py`

**最大のリスクファイル**（60メソッド、73ユニット+5統合テストファイル）。4サブステップで段階的に分割。

##### Step 7a: ImageQueryBuilder抽出
| 問題 | 対策 |
|------|------|
| `get_images_by_filter()` 130行 + 8個のフィルタヘルパー | `ImageQueryBuilder` クラスに抽出（同一ファイル内） |

##### Step 7b: 長大メソッド分割
| 問題 | 対策 |
|------|------|
| `get_image_annotations()` 112行 | `_fetch_tags()`, `_fetch_scores()`, `_fetch_caption()` に分割 |
| `update_model()` 94行 | `_validate_model_update()`, `_apply_model_changes()` に分割 |
| `add_tag_to_images_batch()` 94行 | タグ解決・バッチ挿入・結果集計に分割 |

##### Step 7c: タグ操作の集約
| 問題 | 対策 |
|------|------|
| タグ登録ロジック6メソッドに散在 | `_TagOperations` 内部クラスまたはMixinに集約（外部APIは変更しない） |

##### Step 7d: 統合テスト実行・最終確認
全テスト実行で回帰がないことを確認。

**検証（各サブステップ後）**:
```bash
uv run pytest tests/unit/database/test_db_repository_*.py -v
uv run pytest tests/integration/database/ tests/integration/test_batch_processing_integration.py -v
```

## 追加タスク（メモ記載の要調整事項）

#### Step 8: tag_register.py ガード追加
**対象**: `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/services/tag_register.py`

| 問題 | 対策 |
|------|------|
| type_id/type_name不整合が検知されない | バリデーションガードまたはwarningログ追加 |

**テスト更新**:
- `tests/gui/unit/test_gui_tag_register_service.py` - 新メソッド呼び出し検証
- `tests/unit/test_tag_register_service.py` - 不整合検知のアサーション追加

## リスク管理

| リスク | 対策 |
|--------|------|
| db_repository分割で回帰 | サブステップごとにテスト実行、問題あれば即ロールバック |
| MergedTagReaderヘルパーのAny戻り値 | `_first_found` 等の戻り値型はAnyだが、公開メソッドのシグネチャで具体型を維持 |
| アダプター基底変更で全プロバイダー影響 | Step 2完了後にBDDテストも実行（例: `local_packages/image-annotator-lib/tests/features`） |

## 検証計画（全体）

各Step完了後:
1. 対象テスト実行（上記の各Step検証コマンド）
2. `uv run ruff check` + `uv run ruff format --check`
3. `uv run mypy -p lorairo` (LoRAIro本体変更時)
4. 可能なら `uv run pytest -m "fast"` を先行で回す（重い統合テスト前の煙テスト）

全Step完了後:
```bash
uv run pytest -x --timeout=300
uv run ruff check src/ local_packages/
uv run mypy -p lorairo
```

## 成功基準
- 全関数60行以下（例外的に80行まで許容）
- 重複コードブロック（5行以上）ゼロ（SQLAlchemy/Qtの定型パターンは例外）
- テストカバレッジ75%以上維持
- ruff/mypy警告ゼロ
