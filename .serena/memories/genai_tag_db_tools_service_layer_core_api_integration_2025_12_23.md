# genai-tag-db-tools Service Layer core_api Integration (2025-12-23)

## 概要

GUI Service Layer (TagSearchService, TagStatisticsService) を core_api と Pydantic モデルに統合し、Service Layer Adapter Pattern を完成させました。

## 実装内容

### 1. DataFrame Conversion Helpers

**新規ファイル**: `src/genai_tag_db_tools/gui/converters.py` (63行)

#### 主要関数

1. **search_result_to_dataframe()**
   - `TagSearchResult` (Pydantic) → `pl.DataFrame` 変換
   - 空結果時のスキーマ定義保証
   - NULL値の適切な処理

2. **statistics_result_to_dict()**
   - `TagStatisticsResult` (Pydantic) → dict 変換
   - GUI表示用の単純な辞書形式

### 2. Service Layer Adapter Pattern

**変更ファイル**: `src/genai_tag_db_tools/services/app_services.py`

#### TagSearchService の変更

1. **初期化**
   - `MergedTagReader` の Lazy Initialization パターン導入
   - テスト時の DB ファイル不要化（フォールバック機能）

2. **search_tags() メソッド**
   - core_api.search_tags() を優先使用
   - Pydantic `ValidationError` の適切なハンドリング
   - `FileNotFoundError` 時に legacy TagSearcher へフォールバック
   - DataFrame 変換レイヤーを経由して GUI へ返却

3. **未実装機能の WARNING**
   - language フィルタ (core_api 未対応)
   - usage count フィルタ (core_api 未対応)
   - 将来の機能追加時に対応予定

#### TagStatisticsService の変更

1. **初期化**
   - `MergedTagReader` の Lazy Initialization パターン導入
   - TagSearchService と同じフォールバック戦略

2. **get_general_stats() メソッド**
   - core_api.get_statistics() を優先使用
   - `FileNotFoundError` 時に legacy TagStatistics へフォールバック
   - dict 変換レイヤーを経由して GUI へ返却

#### TagRegisterService

- 既に `register_tag()` メソッドで Pydantic モデル対応済み
- `register_or_update_tag()` は辞書→Pydantic変換を実施
- 追加変更なし（既存実装を維持）

### 3. 型ヒントの追加

**変更内容**: TYPE_CHECKING を使用した forward reference

```python
if TYPE_CHECKING:
    from genai_tag_db_tools.db.repository import MergedTagReader
    from genai_tag_db_tools.models import TagRegisterRequest, TagRegisterResult
```

- F821 エラー (Undefined name) の解消
- 実行時のインポート循環依存を回避

### 4. テストカバレッジ

**新規テストファイル**: `tests/test_gui_converters.py` (6テスト)

#### TestSearchResultToDataFrame

- `test_empty_result`: 空結果のスキーマ確認
- `test_single_item`: 単一アイテム変換
- `test_multiple_items`: 複数アイテム変換
- `test_null_values`: NULL値の適切な処理

#### TestStatisticsResultToDict

- `test_basic_conversion`: 基本的な変換確認
- `test_zero_values`: ゼロ値の保持確認

**テスト結果**: 全105テスト PASSED (新規6テスト含む)

## アーキテクチャパターン

### Service Layer Adapter Pattern

```
Widget → Service (core_api adapter) → core_api → Repository
         ↓ DataFrame変換
       QTableView
```

**利点**:
1. Widget層の変更が最小限（Signal/Slot構造不変）
2. 段階的移行が可能（Service毎に移行）
3. 既存テストコードの再利用性が高い
4. LoRAIro品質方針適合（シンプルさ、可読性優先）

### Lazy Initialization Pattern

**実装理由**:
- テスト時に DB ファイルが不要
- `get_default_repository()` の遅延実行
- 実行時エラーの最小化

**実装方法**:
```python
def _get_merged_reader(self) -> MergedTagReader:
    if not self._merged_reader_initialized:
        from genai_tag_db_tools.db.repository import MergedTagReader, get_default_repository
        base_repo = get_default_repository()
        self._merged_reader = MergedTagReader(base_repo=base_repo, user_repo=None)
        self._merged_reader_initialized = True
    return self._merged_reader
```

### Fallback Strategy

**実装理由**:
- core_api 統合失敗時の互換性維持
- 開発環境での柔軟性確保
- 本番環境での安定性向上

**フォールバック条件**:
1. `ValidationError`: Pydantic バリデーションエラー
2. `FileNotFoundError`: DB ファイル不在

## コード品質

### Ruff Format & Check

- 全修正ファイルで Ruff フォーマット適用
- Ruff チェック全通過
- コードスタイル統一維持

### 型ヒント

- 全新規関数に型ヒント追加
- TYPE_CHECKING による forward reference
- mypy 互換性確保

### Google-style Docstrings

- 全新規関数にdocstring追加
- Args, Returns, Raises セクション完備

## 未実装項目

### GUI Widget への完全移行

現状：Widget は Presenter 層を経由して Service を呼び出し

今後：Widget が直接 Service の Pydantic 統合版を使用するよう更新検討

### core_api 未対応フィルタ

1. **language フィルタ**
   - TagSearchRequest に language パラメータ未実装
   - 将来の core_api 拡張待ち

2. **usage count フィルタ**
   - TagSearchRequest に min_usage/max_usage パラメータ未実装
   - 将来の core_api 拡張待ち

### GUI テスト整備

- DbInitializationService のユニットテスト追加予定
- MainWindow の非同期初期化フローテスト追加予定
- オフライン時の挙動テスト追加予定

## ファイル構成

```
local_packages/genai-tag-db-tools/
├── src/genai_tag_db_tools/
│   ├── gui/
│   │   └── converters.py (新規 - 63行)
│   └── services/
│       └── app_services.py (更新 - 410行)
└── tests/
    └── test_gui_converters.py (新規 - 112行)
```

## 次のステップ

### Phase 2: Widget レイヤーの完全移行

1. **TagSearchWidget 更新**
   - Presenter 層の責務整理
   - Service 初期化時に MergedTagReader 注入確認

2. **TagRegisterWidget 更新**
   - `build_tag_info()` を `TagRegisterRequest` 構築に変更検討

3. **TagStatisticsWidget 更新**
   - 統計結果の表示ロジック確認

### Phase 3: 設定UI追加

- キャッシュディレクトリの GUI 指定
- HF トークンの GUI 設定
- 取得 DB ソースの切り替え UI

## 参照

- 計画: `.serena/memories/genai_tag_db_tools_gui_refactor_2025_12_23.md`
- 進捗: `.serena/memories/genai_tag_db_tools_refactor_progress_2025_12_20.md`
- core_api仕様: `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/core_api.py`
- models定義: `local_packages/genai-tag-db-tools/src/genai_tag_db_tools/models.py`

## �ǉ��^�p���[��

- DbInitWorker �� untime.init_user_db(cache_dir) ���g���ă��[�U�[DB�����������A�L���b�V���� cache_dir/base_dbs/<filename> ����ǂݏo���B
- DbInitializationService �̊����V�O�i���̓x�[�XDB�����̐��ۂ݂̂�`���AUI�͂��̌��ʂ�\������B�I�����C��/�I�t���C���\����L�����Z���͕s�v�ŁA�r����~�����_�E�����[�h�� cleanup �܂��͍Ď��s�ŉ������B
- _default_sources() �� CC4/MIT/CC0 ��3����Ԃ��B
- TagSearchService �� core_api �Ăяo���� limit ���Œ肹���AUI/Presenter ���w�肵���l�����̂܂܎g���B

## Operation Rules

- DbInitWorker now calls runtime.init_user_db(cache_dir) when preparing the user database, uses cache_dir/base_dbs/<filename> for cache fallbacks, and the UI only reports whether a base DB set is ready (Cancel/online indicators removed; partial downloads are cleaned up or retried before signaling failure).
- DbInitializationService defaults to the CC4, MIT, and CC0 Hugging Face sources.
- TagSearchService no longer hardcodes limit=1000; it forwards the UI/Presenter-provided limit/offset to TagSearchRequest.

