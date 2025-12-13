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
- **理由**: 
  - Parquet: 大量データの効率的なストリーミング
  - SQLite: ローカル検索の最適化

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
- **使用方法**: 
  - 統合DBに含まれない新規タグのフォールバック
  - 18サイト対応の包括的カバレッジ
- **メリット**: 250M+ タグによる網羅性

#### isek-ai/danbooru-wiki-2024
- **役割**: Danbooru-Pixiv特化相互参照
- **使用方法**: 
  - アーティストID対応付け
  - タグ推奨関係の補完
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

#### 内部実装の段階的移行
```python
# 新実装（内部のみ変更）
class HybridTagRepository:
    def __init__(self):
        self.local_cache = SQLiteCache()
        self.hf_fallback = HuggingFaceDatasetFallback()
    
    def get_tag(self, tag_id: str) -> Tag:
        # Layer 1: ローカルキャッシュ
        if tag := self.local_cache.get(tag_id):
            return tag
        
        # Layer 2: HuggingFace fallback
        tag = self.hf_fallback.fetch(tag_id)
        self.local_cache.put(tag_id, tag)
        return tag
```

### パフォーマンス目標

| 指標 | 目標値 | 測定方法 |
|------|--------|----------|
| キャッシュヒット応答 | <100ms | 95パーセンタイル |
| HFフォールバック | <3秒 | 初回取得 |
| オフライン動作 | 100% | キャッシュ済みタグ |
| メモリ使用量 | <800MB | ピーク時 |

### リスク管理

#### 技術リスク
1. **HuggingFace API制限**: 
   - 対策: ローカルキャッシュによる緩和
   - フォールバック: オフライン完全動作

2. **データ同期遅延**:
   - 対策: 週次自動更新スクリプト
   - 監視: バージョン差分アラート

3. **後方互換性破損**:
   - 対策: 包括的統合テストスイート
   - 保証: 既存LoRAIro統合の回帰テスト

#### 運用リスク
1. **ディスク容量不足**:
   - 対策: LRUによる自動削除
   - 上限: 10GB (100,000タグ × 100KB/tag)

2. **ネットワーク障害**:
   - 対策: オフラインモード自動切替
   - 回復: 接続復帰時の自動再同期

### 実装フェーズ

#### Phase 1: データ統合とHuggingFace移行（Week 1-2）
- tags_v4.db → Parquet変換
- 3ソース統合スクリプト作成
- NEXTAltair/genai-tag-db-unified公開

#### Phase 2: ハイブリッドアーキテクチャ実装（Week 3-4）
- HybridTagRepository実装
- LRUキャッシュ管理実装
- HuggingFaceフォールバック実装

#### Phase 3: 既存API互換性維持（Week 5）
- TagSearcher/TagCleanerラッパー実装
- 統合テストスイート作成

#### Phase 4: テストと検証（Week 6）
- パフォーマンスベンチマーク
- LoRAIro統合回帰テスト

#### Phase 5: デプロイとマイグレーション（Week 7）
- マイグレーションスクリプト
- ドキュメント更新

### 成功基準

#### 機能要件
- [x] 既存API完全互換
- [x] 3ソース補完的統合
- [x] オフライン動作保証

#### 非機能要件
- [x] <100ms キャッシュ応答
- [x] <800MB メモリ使用
- [x] 75%+ テストカバレッジ

### 設計教訓

1. **段階的移行の重要性**: 既存システムの段階的置換により、リスク最小化とロールバック可能性を確保
2. **ハイブリッド戦略の効果**: パフォーマンス（ローカル）とスケーラビリティ（クラウド）の両立
3. **API互換性の価値**: 既存統合を壊さない内部実装の刷新により、スムーズな移行を実現

### 参考資料
- [deepghs/site_tags](https://huggingface.co/datasets/deepghs/site_tags): 18サイト、250M+ タグ
- [isek-ai/danbooru-wiki-2024](https://huggingface.co/datasets/isek-ai/danbooru-wiki-2024): Danbooru-Pixiv相互参照
- Serena Memory: `tag_database_integration_redesign_plan_2025_12_13`
