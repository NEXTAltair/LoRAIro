# genai-tag-db-tools GUI Refactor - Service Layer core_api Integration (2025-12-23)

## 実装完了サマリ

### 実装内容
Service Layer (TagSearchService, TagStatisticsService) を core_api と統合し、Pydantic models による型安全な API 使用を実現。

### アーキテクチャパターン

#### Service Layer Adapter Pattern
```
Widget → Service (core_api adapter) → core_api → Repository (MergedTagReader)
```

#### Lazy Initialization Pattern
- MergedTagReader を初回使用時に生成（テスト時の DB ファイル要求を回避）
- `_get_merged_reader()` メソッドによる遅延初期化

#### Fallback Strategy
- ValidationError または FileNotFoundError 発生時に legacy TagSearcher/TagStatistics へフォールバック
- WARNING ログ出力による透明性確保

### 実装ファイル

#### 新規作成

**converters.py** (63 lines)
- `search_result_to_dataframe()`: TagSearchResult → Polars DataFrame
- `statistics_result_to_dict()`: TagStatisticsResult → dict
- Pydantic models と GUI 表示層の変換を担当

**test_app_services_core_api_integration.py** (194 lines, 7 tests)
- Language/usage filter warning logs テスト
- 成功時の DataFrame/dict 返却テスト
- ValidationError/FileNotFoundError fallback テスト
- 全テスト PASS (7/7)

#### 修正

**app_services.py**
- TYPE_CHECKING imports 追加（F821 エラー回避）
- TagSearchService.search_tags() - core_api 統合
- TagStatisticsService.get_general_stats() - core_api 統合
- Lazy initialization メソッド追加

### テスト結果

```bash
112 tests passed (全テストスイート)
- 既存テスト: 105 tests
- 新規テスト: 7 tests (core_api integration)
```

**新規テストカバレッジ:**
- Language filter → WARNING ログ確認 ✅
- Usage filter → WARNING ログ確認 ✅
- 成功時の core_api 呼び出し → DataFrame 返却 ✅
- ValidationError → legacy fallback ✅
- FileNotFoundError → legacy fallback ✅
- 統計取得成功 → dict 返却 ✅
- 統計取得失敗 → legacy fallback ✅

### 設計決定

1. **Lazy Initialization の採用理由**
   - テスト時に DB ファイル不要（モック注入可能）
   - 初期化コストの遅延により起動高速化

2. **Fallback Strategy の採用理由**
   - 後方互換性維持
   - 段階的移行を可能に
   - core_api 障害時の可用性確保

3. **TYPE_CHECKING による循環 import 回避**
   - MergedTagReader, TagRegisterRequest, TagRegisterResult を TYPE_CHECKING ブロックで import
   - 実行時の import 遅延とエディタ補完の両立

### 未対応機能（将来実装予定）

1. **Language filtering in core_api**
   - 現状: WARNING ログのみ出力、フィルタリング未実施
   - 将来: core_api 側で言語フィルタリング実装後に対応

2. **Usage count filtering in core_api**
   - 現状: WARNING ログのみ出力、フィルタリング未実施
   - 将来: core_api 側で usage_count フィルタリング実装後に対応

### Widget Layer への影響（次フェーズ）

Widget 層は現在 Service Layer を経由して間接的に core_api を使用。
将来的に Widget 層から直接 Service Layer を呼び出す方式に統一予定。

### リファクタリング計画進捗

**完了した TODO 項目:**
1. ✅ Service Layer に core_api adapter 追加
2. ✅ DataFrame conversion helpers 作成
3. ✅ Pydantic ValidationError ハンドリング
4. ✅ Lazy initialization パターン適用
5. ✅ limit/offset パラメータ対応（固定値削除）

**残タスク（次フェーズ）:**
- Widget 層の Service Layer 直接使用への移行
- Language/usage filtering の core_api 側実装

### 2025-12-23 更新: limit/offset パラメータ対応

計画更新に従い、`TagSearchService.search_tags()` の `limit=1000` 固定を削除。

**変更内容:**
- `search_tags()` メソッドに `limit` (デフォルト1000) と `offset` (デフォルト0) パラメータ追加
- UI/リクエストから指定された値を直接 `TagSearchRequest` に渡すように修正
- 適切な docstring 追加（各パラメータの説明）

**テスト追加:**
- `test_search_tags_with_custom_limit_offset`: カスタム limit/offset が正しく core_api に渡されることを検証

**テスト結果:**
```
113 tests passed (既存 105 + 新規 8)
- limit/offset パラメータ渡し確認テスト ✅
```
