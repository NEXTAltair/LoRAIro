# 検索UX機能実装ステータス確認 2026-02-13

## 実装確認日時
- **実施日**: 2026-02-13
- **実施範囲**: 3つの検索UX機能（タグオートコンプリート、リアルタイム件数表示、除外検索）
- **確認対象ファイル**:
  - `src/lorairo/gui/widgets/filter_search_panel.py`
  - `src/lorairo/services/search_models.py`
  - `src/lorairo/database/db_repository.py`

---

## 機能別実装ステータス

### 1. タグオートコンプリート (Tag Autocompletion)

**実装状態**: **未実装**

**確認内容**:
- QCompleter関連コード: **なし**
- tag_suggestion_service.py: **存在しない**
- FilterSearchPanelに補完機能: **なし**

**計画の存在確認**:
- ✅ Plan記録あり: `plan_search_ux_01_tag_autocomplete_2026_02_05`
- 実装方針確定済み: QCompleter + genai-tag-db-tools search_tags()を活用
- 対象ファイル: FilterSearchPanel、TagSuggestionService（新規）

**実装必要性**:
- 新規サービス作成必須: `TagSuggestionService`
- FilterSearchPanel統合: `_setup_tag_completer()`, `_on_search_text_changed()` メソッド追加
- テスト: ユニット + GUI両方必要

---

### 2. リアルタイム件数表示 (Realtime Count Display)

**実装状態**: **未実装**

**確認内容**:
- FilterSearchPanelのカウント表示機能: **なし**
- デバウンスタイマー: **なし** (progress_barはあるが、別目的)
- `get_images_count_only()`メソッド: **db_repositoryに存在しない**
- db_managerのカウント専用メソッド: **なし**

**現在の状況**:
- FilterSearchPanelは進捗表示用progress_barを持つが、フィルター変更時のカウント表示はない
- db_repositoryのget_images_by_filter()は全メタデータを取得するため、カウント専用メソッドが必要

**計画の存在確認**:
- ✅ Plan記録あり: `plan_search_ux_02_realtime_count_2026_02_05`
- 実装方針確定済み: デバウンス500ms + COUNTクエリ専用メソッド
- 対象ファイル: SearchFilterService、ImageRepository、ImageDatabaseManager、FilterSearchPanel

**実装必要性**:
- db_repository: `get_images_count_only()` メソッド新規作成
- db_manager: 引数中継用メソッド追加
- FilterSearchPanel: デバウンスタイマー + 表示ロジック追加
- テスト: Repository/Manager層 + GUI層両方必要

---

### 3. 除外検索 (NOT Search / Exclude Tags)

**実装状態**: **未実装**

**確認内容**:
- SearchConditionsの`excluded_keywords`フィールド: **なし**
- db_repository._apply_tag_filter()のexcluded_tags引数: **なし**
- FilterSearchPanelのNOT検索サポート: **なし**
- NOT EXISTS SQLロジック: **実装されていない**

**現在の_apply_tag_filter()の状況** (line 1865-1911):
```python
def _apply_tag_filter(
    self,
    query: Select,
    tags: list[str] | None,
    use_and: bool,
    include_untagged: bool,
) -> Select:
    # シグネチャに excluded_tags パラメータがない
    # NOT EXISTS ロジックも実装されていない
```

**計画の存在確認**:
- ✅ Plan記録あり: `plan_search_ux_05_exclude_search_2026_02_05`
- 実装方針確定済み: プレフィックス方式 (`-tag`) + NOT EXISTS SQLロジック
- 対象ファイル: SearchConditions、SearchFilterService、ImageRepository、FilterSearchPanel

**実装必要性**:
- SearchConditions: `excluded_keywords`フィールド追加
- SearchFilterService: `parse_search_input()` 戻り値を tuple[list[str], list[str]] に変更
- ImageRepository: 
  - `_apply_tag_filter()` シグネチャ + NOT EXISTS ロジック追加
  - `_build_image_filter_query()` に excluded_tags引数追加
  - `get_images_by_filter()` に excluded_tags引数追加
- FilterSearchPanel: 除外キーワード解析 + UI更新
- テスト: Service層 + Repository層 + GUI層全て必要

---

## 実装の優先度と工数見積もり

| # | 機能 | 状態 | 工数 | 優先度 | 依存関係 |
|---|------|------|------|--------|---------|
| 1 | タグオートコンプリート | 未実装 | 中 | 中 | 独立 |
| 2 | リアルタイム件数表示 | 未実装 | 小 | 高 | 独立 |
| 3 | 除外検索 | 未実装 | 中 | 中 | 独立 |

**総工数**: 小～中程度

---

## 実装の推奨順序

### Phase 1 (優先度高)
1. **リアルタイム件数表示** (工数: 小)
   - DBクエリ層実装が簡潔
   - UI反応性向上で即座に効果が見える
   - 他の機能に依存しない

### Phase 2 (並列実装可)
2. **タグオートコンプリート** (工数: 中)
   - genai-tag-db-tools の search_tags() を活用
   - SearchFilterService と FilterSearchPanel を統合

3. **除外検索** (工数: 中)
   - FilterSearchPanel.parse_search_input() 拡張が必要
   - SQLロジック (NOT EXISTS) が複雑

---

## 実装上の注意点

### 1. SearchFilterService との整合性
- 現在: `parse_search_input()` は単純なリスト返却
- 追加時: tuple[list[str], list[str]] に変更
- 影響: FilterSearchPanel._on_search_requested()の更新が必須

### 2. SQLAlchemy NOT EXISTS パターン
```python
# 実装例
not_exists_subquery = (
    select(Tag.id)
    .where(Tag.image_id == Image.id, Tag.tag == excluded_pattern)
    .correlate(Image)
    .exists()
)
query = query.where(~not_exists_subquery)  # NOT演算子
```

### 3. デバウンス実装
- 既に FilterSearchPanel には QTimer があるが、progress_bar用
- リアルタイム件数表示用に独立したタイマーが必要
- 推奨: `_count_update_timer` (500ms)

### 4. パフォーマンス考慮
- `get_images_count_only()` は COUNT(*) のみ実行
- メタデータ取得の _fetch_filtered_metadata() は不要
- 大規模データセット対象時でも高速

---

## テスト計画の概要

### 1. タグオートコンプリート
- Unit: `tests/unit/services/test_tag_suggestion_service.py`
- GUI: `tests/unit/gui/widgets/test_filter_search_panel_autocomplete.py`
- Coverage: 75%+ 目標

### 2. リアルタイム件数表示
- Unit: `tests/unit/database/test_db_repository_count.py`
- Service: `tests/unit/gui/services/test_search_filter_service_count.py`
- GUI: 既存の FilterSearchPanel テスト拡張
- Coverage: 75%+ 目標

### 3. 除外検索
- Unit: `tests/unit/gui/services/test_search_filter_service_exclude.py`
- DB: `tests/unit/database/test_db_repository_exclude_tags.py`
- GUI: `tests/unit/gui/widgets/test_filter_search_panel_exclude.py`
- Coverage: 75%+ 目標

---

## 参照資料

### 計画ドキュメント
- `plan_search_ux_01_tag_autocomplete_2026_02_05` - タグオートコンプリート計画
- `plan_search_ux_02_realtime_count_2026_02_05` - リアルタイム件数表示計画
- `plan_search_ux_05_exclude_search_2026_02_05` - 除外検索計画

### コード参照ポイント
- FilterSearchPanel: `/workspaces/LoRAIro/src/lorairo/gui/widgets/filter_search_panel.py` (line 1-1316)
- SearchConditions: `/workspaces/LoRAIro/src/lorairo/services/search_models.py` (line 16-73)
- ImageRepository._apply_tag_filter(): line 1865-1911
- ImageRepository.get_images_by_filter(): line 2484-2569

---

## 実装開始時のチェックリスト

- [ ] 全3つの計画ドキュメントを確認
- [ ] 現在の FilterSearchPanel と SearchFilterService のAPI確認
- [ ] db_repository の既存フィルタリングロジック理解
- [ ] テスト構造 (conftest.py, fixtures) の把握
- [ ] 依存パッケージ (PySide6, SQLAlchemy, genai-tag-db-tools) のバージョン確認

