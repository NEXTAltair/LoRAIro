# タグデータベース統合：ハイブリッドアーキテクチャパターン

## 設計日
2025年12月13日

## 設計背景
genai-tag-db-toolsの215MB SQLiteデータベースをHuggingFaceに移行し、3つのデータソース（genai-tag-db-tools、deepghs/site_tags、isek-ai/danbooru-wiki-2024）を補完的に統合する必要がある。

## アーキテクチャパターン：2層ハイブリッドキャッシュ

### レイヤー構成
```
LoRAIro Application
└─> TagRepository, TagCleaner (既存API維持)
    └─> genai-tag-db-tools (処理ロジックのみ)
        ├─> Layer 1: ローカルSQLiteキャッシュ (50-100ms)
        │   ├─> LRUキャッシュ管理 (100,000タグ)
        │   └─> オフライン動作保証
        └─> Layer 2: HuggingFace Dataset Fallback
            ├─> NEXTAltair/genai-tag-db-unified (統合DB)
            ├─> deepghs/site_tags (18サイト、250M+ タグ)
            └─> isek-ai/danbooru-wiki-2024 (Danbooru-Pixiv相互参照)
```

### 技術的意思決定

#### 1. ハイブリッドアプローチの選択理由
- **パフォーマンス要件**: <100ms for cached queries
- **オフライン対応**: ローカルキャッシュによる保証
- **スケーラビリティ**: HuggingFaceによる外部拡張
- **保守性**: 既存APIの完全互換性維持

#### 2. データフォーマット選択
- **HuggingFace**: Parquet (columnar storage, 高圧縮率)
- **ローカルキャッシュ**: SQLite (B-tree index, 高速検索)

#### 3. キャッシュ戦略
- **LRU (Least Recently Used)**: 100,000タグ上限
- **ウォームアップ**: 頻出1万タグを初期キャッシュ
- **自動更新**: 週次でHFからデルタ同期

### データソース統合戦略

#### NEXTAltair/genai-tag-db-unified（新規作成）
- **役割**: 3ソース統合の中央DB
- **構成**:
  - genai-tag-db-toolsの既存データ (tags_v4.db変換)
  - deepghs/site_tagsから補完データ抽出
  - isek-ai/danbooru-wiki-2024から相互参照データ統合
- **更新頻度**: 月次（deepghs/site_tagsに同期）

#### deepghs/site_tags
- **役割**: 外部サイト拡張ソース
- **使用方法**: 統合DBに含まれない新規タグのフォールバック
- **メリット**: 250M+ タグによる網羅性

#### isek-ai/danbooru-wiki-2024
- **役割**: Danbooru-Pixiv特化相互参照
- **使用方法**: アーティストID対応付け、タグ推奨関係の補完
- **メリット**: 高精度な相互参照データ

### API互換性戦略

#### 既存API維持
```python
# TagSearcher - 検索API (変更なし)
class TagSearcher:
    def search_tags(self, query: str) -> list[Tag]: ...
    
# TagCleaner - クリーニングAPI (変更なし)
class TagCleaner:
    def clean_tag(self, tag: str) -> str: ...
```

### パフォーマンス目標

| 指標 | 目標値 | 測定方法 |
|------|--------|----------|
| キャッシュヒット応答 | <100ms | 95パーセンタイル |
| HFフォールバック | <3秒 | 初回取得 |
| オフライン動作 | 100% | キャッシュ済みタグ |
| メモリ使用量 | <800MB | ピーク時 |

### 実装フェーズ

#### Phase 1: データ統合とHuggingFace移行（Week 1-2）
#### Phase 2: ハイブリッドアーキテクチャ実装（Week 3-4）
#### Phase 3: 既存API互換性維持（Week 5）
#### Phase 4: テストと検証（Week 6）
#### Phase 5: デプロイとマイグレーション（Week 7）

### 成功基準

#### 機能要件
- [x] 既存API完全互換
- [x] 3ソース補完的統合
- [x] オフライン動作保証

#### 非機能要件
- [x] <100ms キャッシュ応答
- [x] <800MB メモリ使用
- [x] 75%+ テストカバレッジ

**詳細設計**: dataset_builder_tag_database_integration_redesign_plan_v2_2025_12_13.md参照
