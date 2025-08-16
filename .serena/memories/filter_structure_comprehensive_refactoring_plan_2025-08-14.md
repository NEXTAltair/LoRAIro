# フィルター構造包括的リファクタリング計画

## 📋 プロジェクト概要

**作成日**: 2025-08-14
**対象ブランチ**: `refactor/search-filter-service-cleanup`
**目標**: フィルター関連コンポーネントの肥大化解消と設計品質向上

### 背景と課題
- `search_filter_service.py` (1,276行) の責任過多・肥大化
- GUI固有処理とビジネスロジックの不適切な混在
- 関連ウィジェットの分散構造 (filter.py + filter_search_panel.py)
- 既存ライブラリ機能の無意味な独自実装
- ImageDatabaseManagerへの適切な責任移譲が必要

## 🎯 リファクタリング戦略

### 修正された6段階アプローチ

#### **Stage 0: 無意味独自実装除去フェーズ (2日)**

**0.1 superqt完全活用によるCustomRangeSlider簡素化**
- 現状: 174行の独自ログスケール実装
- 目標: 50行の標準ライブラリ活用版

```python
# ❌ 現在の独自実装 (削除対象)
def scale_to_value(self, value: int) -> int:
    log_min = np.log1p(self.min_value)
    log_max = np.log1p(self.max_value)
    log_value = log_min + (log_max - log_min) * (value / 100)
    return int(np.expm1(log_value))

# ✅ 修正後 - superqt機能フル活用
from superqt import QDoubleRangeSlider
class DateTimeRangeWidget(QWidget):
    def __init__(self):
        self.slider = QDoubleRangeSlider()
        # superqtの最適化済み機能を直接利用
```

**0.2 標準ライブラリ活用による処理簡素化**
- 解像度処理: 正規表現による50行→10行削減
- フィルタリング: SQLAlchemy機能活用で200行→50行削減

```python
# ✅ 正規表現活用
import re
def parse_resolution(text: str) -> tuple[int, int] | None:
    match = re.match(r"(\d+)x(\d+)", text)
    return (int(match[1]), int(match[2])) if match else None

# ✅ SQLAlchemyフィルタリング活用
def filter_by_criteria(self, **filters):
    query = session.query(Image)
    if filters.get('aspect_ratio'):
        query = query.filter(Image.width / Image.height.between(0.95, 1.05))
    return query.all()
```

**0.3 PySide6モデル/ビューパターン導入**
- 独自リストフィルタリング → QSortFilterProxyModel活用

**期待効果**: 314行削減 + 信頼性向上

#### **Stage 1: データ層責任強化フェーズ (2日)**

**1.1 ImageDatabaseManager拡張**
- SearchFilterServiceからデータベース直接操作を移譲
- 適切な責任境界の確立

```python
# ImageDatabaseManagerに追加するメソッド
class ImageDatabaseManager:
    def get_dataset_status(self) -> dict[str, Any]:
        """データセット統計情報取得 - データ層の適切な責任"""
        
    def get_annotation_status_counts(self) -> dict[str, int]:
        """アノテーション状態カウント - データ層の適切な責任"""
        
    def execute_filtered_search(self, conditions: dict) -> tuple[list, int]:
        """フィルタリング検索実行 - データ層の適切な責任"""
        
    def check_image_has_annotation(self, image_id: int) -> bool:
        """アノテーション存在チェック - データ層の適切な責任"""
```

**移譲対象処理**:
- get_dataset_status() → db_manager.get_dataset_status()
- get_annotation_status_counts() → db_manager.get_annotation_status_counts()
- filter_by_annotation_status() → db_manager.filter_by_annotation_status()
- get_directory_images() → db_manager.get_directory_images_metadata()

**期待効果**: 責任境界明確化、データアクセス統合

#### **Stage 2: ビジネスロジック分離フェーズ (3日)**

**2.1 SearchCriteriaProcessor新規作成**
- 目標: 300行のビジネスロジック専用サービス

```python
# src/lorairo/services/search_criteria_processor.py
class SearchCriteriaProcessor:
    def __init__(self, db_manager: ImageDatabaseManager):
        self.db_manager = db_manager
    
    # 移行対象メソッド:
    def execute_search_with_filters(self, conditions) -> tuple[list, int]:
        # DB検索はdb_managerに委譲、フロントエンドフィルターのみここで処理
    def separate_search_and_filter_conditions(self, conditions) -> tuple
    def _convert_to_db_query_conditions(self, search_conditions) -> dict
    def _apply_frontend_filters(self, images, filters) -> list
    def process_resolution_filter(self, conditions) -> dict
    def process_date_filter(self, conditions) -> dict
    def apply_untagged_filter(self, conditions) -> dict
    def apply_tagged_filter_logic(self, conditions) -> dict
```

**2.2 ModelFilterService新規作成**
- 目標: 350行のモデル管理専用サービス

```python
# src/lorairo/services/model_filter_service.py
class ModelFilterService:
    def __init__(self, db_manager: ImageDatabaseManager, 
                 model_selection_service: ModelSelectionService):
        # モデル情報はModelSelectionServiceから
        # DB操作はImageDatabaseManagerに委譲
    
    # 移行対象メソッド:
    def get_annotation_models_list(self) -> list
    def filter_models_by_criteria(self, criteria) -> list
    def infer_model_capabilities(self, model_data) -> list
    def apply_advanced_model_filters(self, images, conditions) -> list
    def optimize_advanced_filtering_performance(self, images, conditions) -> list
    def validate_annotation_settings(self, settings) -> ValidationResult
```

**期待効果**: ビジネスロジックの明確な分離、単一責任原則達成

#### **Stage 3: GUI層純化フェーズ (2日)**

**3.1 SearchFilterService大幅縮小**
- 目標: 150行のGUI専用サービス

```python
# src/lorairo/gui/services/search_filter_service.py (縮小版)
class SearchFilterService:
    def __init__(self, 
                 criteria_processor: SearchCriteriaProcessor,
                 model_filter_service: ModelFilterService):
        # 純粋にGUI固有処理のみ
        self.criteria_processor = criteria_processor
        self.model_filter_service = model_filter_service
        
    # 残存メソッド (GUI専用):
    def create_search_conditions_from_ui(self, ui_params) -> SearchConditions
    def create_search_preview(self, conditions) -> str
    def get_available_resolutions(self) -> list[str]
    def get_available_aspect_ratios(self) -> list[str]
    def validate_ui_inputs(self, inputs) -> ValidationResult
```

**3.2 後方互換性確保**
- 既存呼び出し元への一時的ラッパーメソッド実装
- 段階的移行期間でのAPI互換性維持

**期待効果**: GUI固有処理への責任集約、他層への依存除去

#### **Stage 4: ウィジェット統合フェーズ (3日)**

**4.1 汎用コンポーネント独立**
```python
# src/lorairo/gui/widgets/custom_range_slider.py (新規独立)
class CustomRangeSlider(QWidget):
    """完全独立汎用範囲選択スライダー (50行目標)"""
    # superqt機能をフル活用した最小実装
    # プロジェクト全体で再利用可能
```

**4.2 フィルターパネル統合強化**
```python
# src/lorairo/gui/widgets/filter_search_panel.py (統合版・400行目標)
class FilterSearchPanel(QWidget):
    """統合検索・フィルターパネル"""
    def __init__(self):
        self.search_filter_service = SearchFilterService()
        self.setup_ui()  # CustomRangeSliderを直接統合
        
    # 統合内容:
    # - 既存のUI制御機能
    # - CustomRangeSliderの直接管理  
    # - 純化されたSearchFilterService利用
    # - filter.pyの削除に伴う機能吸収
```

**4.3 不要ファイル削除**
- `src/lorairo/gui/widgets/filter.py` 削除
- インポート文の全体更新
- 依存関係チェック・修正

**期待効果**: 関連コンポーネント統合、ファイル数削減

#### **Stage 5: 統合テスト・最適化フェーズ (3日)**

**5.1 包括的テスト実装**
```bash
# 新サービス単体テスト
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/unit/services/test_search_criteria_processor.py -v
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/unit/services/test_model_filter_service.py -v

# データ層拡張テスト
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/unit/database/test_image_database_manager_extended.py -v

# GUI統合テスト
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/integration/gui/test_filter_search_integration.py -v

# ウィジェット単体テスト
UV_PROJECT_ENVIRONMENT=.venv_linux uv run pytest tests/unit/gui/widgets/test_custom_range_slider.py -v
```

**5.2 パフォーマンス最適化**
- 大量画像処理時のメモリ使用量測定
- データベースクエリ効率化確認
- UI応答性テスト (100ms以下維持)
- superqt活用による処理速度改善測定

**5.3 品質指標達成確認**
- テストカバレッジ: 90%以上
- 既存機能の完全互換性
- パフォーマンス基準維持
- メモリリーク無し確認

**期待効果**: 品質保証完了、本番投入準備完了

#### **Stage 6: ドキュメント・完了フェーズ (1日)**

**6.1 設計文書更新**
- `docs/architecture.md` - 新サービス層構造追加
- `docs/technical.md` - 実装パターン更新
- API仕様書 - 新インターフェース文書化
- 設計決定記録 - リファクタリング理由と効果記録

**6.2 開発者ガイド更新**
- 新しいサービス利用方法
- ウィジェット統合パターン  
- テスト実行方法
- デバッグガイド

**期待効果**: 完全な文書化、知識継承

## 📊 修正された期待効果

### コード量最適化
```
既存: 1,276行 (SearchFilterService)
修正後総計:
- ImageDatabaseManager: +4メソッド追加
- SearchCriteriaProcessor: 300行 (新規)
- ModelFilterService: 350行 (新規)
- SearchFilterService: 150行 (大幅縮小)
- CustomRangeSlider: 50行 (簡素化)
- FilterSearchPanel: 400行 (統合)

実質削減: 614行削減 (1,276行 → 662行相当)
```

### アーキテクチャ品質向上
```
データ層 (ImageDatabaseManager)
├── データベース直接操作統合
├── 統計・状態取得機能
└── フィルタリング検索実行

ビジネスロジック層
├── SearchCriteriaProcessor (検索・フィルター処理)
└── ModelFilterService (モデル管理専用)

GUI層  
├── SearchFilterService (GUI専用・150行)
└── FilterSearchPanel + CustomRangeSlider (統合)
```

### 技術的改善
- **ライブラリ活用**: superqt, SQLAlchemy, 正規表現の完全活用
- **責任分離**: レイヤードアーキテクチャの確立
- **保守性**: 単一責任原則によるメンテナンス容易性
- **再利用性**: 汎用コンポーネントの独立
- **テスタビリティ**: モック対象明確化による単体テスト向上

## ⚠️ リスク管理

### 高リスク要因と対策

**1. 既存機能の破綻**
- リスク: 分離時の見落としによる機能不全
- 対策: 段階的移行、包括的テスト、バックアップブランチ保持

**2. パフォーマンス劣化**  
- リスク: サービス間通信オーバーヘッド
- 対策: パフォーマンステスト、プロファイリング、最適化

**3. 依存関係の複雑化**
- リスク: 循環依存の発生
- 対策: 依存関係図作成、インターフェース明確化

### 中リスク要因と対策

**1. ライブラリ変更の影響**
- リスク: superqt等の破壊的変更
- 対策: バージョン固定、互換性テスト

**2. 学習コスト**
- リスク: 新アーキテクチャの理解コスト
- 対策: 詳細ドキュメント、段階的導入

## 📅 詳細実装タイムライン

| Stage | 期間 | 主要成果物 | 成功指標 |
|-------|------|-----------|---------|
| Stage 0 | 2日 | ライブラリ活用版実装 | 314行削減達成 |
| Stage 1 | 2日 | 拡張ImageDatabaseManager | DB責任統合完了 |
| Stage 2 | 3日 | 新ビジネスロジック層 | サービス分離完了 |
| Stage 3 | 2日 | 純化SearchFilterService | GUI層純化完了 |
| Stage 4 | 3日 | ウィジェット統合完了 | 統合パネル・汎用スライダー |
| Stage 5 | 3日 | 品質保証完了 | 90%+テストカバレッジ |
| Stage 6 | 1日 | 文書化完了 | 設計記録・ガイド完成 |
| **合計** | **16日** | **完全リファクタリング** | **614行削減+品質向上** |

## 🚀 実装優先順位の根拠

### Stage 0が最優先の理由
- **即効性**: 無意味独自実装の除去で即座に効果
- **基盤整備**: 後続ステージの基盤となる標準化
- **リスク最小**: 既存ライブラリ活用で安定性確保

### Stage 1-2が次優先の理由
- **責任分離効果**: 最も重要なアーキテクチャ改善
- **並行開発可能**: 独立性が高く効率的実装可能
- **波及効果大**: 後続ステージへの影響最大

### Stage 3-6が最終段階の理由
- **統合検証必要**: 全体整合性の確認が不可欠
- **品質保証重要**: 本番投入前の厳格な検証
- **文書化完成**: 長期保守のための知識継承

## 📋 次ステップ

### 即座実行項目
1. **Stage 0開始**: superqt活用とライブラリ標準化
2. **依存関係確認**: 影響範囲の最終確認
3. **テスト環境準備**: CI/CDパイプライン整備

### 継続監視項目
1. **各Stageでの品質チェック**: 機能・性能・互換性
2. **進捗管理**: 16日間の詳細スケジュール管理
3. **ステークホルダー報告**: 定期的な進捗共有

## 🎯 成功指標

### 定量的指標
- **コード削減**: 614行削除達成
- **テストカバレッジ**: 90%以上
- **パフォーマンス**: 現状維持以上
- **期間**: 16日以内完了

### 定性的指標
- **責任境界明確化**: レイヤードアーキテクチャ確立
- **保守性向上**: 変更影響範囲の限定
- **再利用性向上**: 汎用コンポーネント独立
- **標準化達成**: ライブラリ機能の完全活用

---

**計画策定者**: Claude Code + Serena MCP
**承認待ち**: ユーザー確認・実装開始承認
**次フェーズ**: `/implement` による段階的実装開始