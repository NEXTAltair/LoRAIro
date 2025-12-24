# タグデータベース統合 詳細実装計画 v2.3

## 計画策定日
2025年12月13日（v2.3: SQLite配布確定版）

## 配布物の確定（重要）

### HuggingFace配布成果物

**ファイル構成:**
```
NEXTAltair/genai-unified-tag-dataset/
├── tags_unified.db.zst         # 圧縮SQLite（zstd圧縮）
├── tags_unified.db.sha256      # SHA256ハッシュ値
├── build_metadata.json         # ビルド情報
└── README.md                   # Dataset Card
```

**ファイル仕様:**

| 項目 | 仕様 | 備考 |
|------|------|------|
| **ファイル名** | `tags_unified.db.zst` | zstd圧縮SQLite |
| **圧縮前サイズ** | 1-2GB（推定） | 全件統合後、インデックス込み |
| **圧縮後サイズ** | 500MB-1GB（推定） | zstd圧縮率: 約50% |
| **レコード数** | 1.5M-2M件（推定） | 重複排除・正規化後 |
| **圧縮形式** | zstd level 19 | 高圧縮率、展開高速 |
| **ハッシュアルゴリズム** | SHA256 | ファイル整合性検証 |

### データ規模の整合性説明

**統合プロセス:**
```
1. genai-tag-db-tools (tags_v4.db):
   - 入力: 993,514タグ
   - 採用: 993,514タグ（ベースデータ、全件保持）

2. deepghs/site_tags:
   - 入力: 2,500,000+タグ（18サイト合計）
   - 重複排除: 約1,700,000タグ（既存と重複、normalized tag比較）
   - 新規追加: 約800,000タグ

3. danbooru-wiki-2024:
   - 入力: 180,839エントリ
   - 新規タグ追加: 約5,000タグ（既存に存在しない）
   - 翻訳補完: 約150,000タグ（既存タグへの翻訳追加）

4. 最終統合結果:
   - 総タグ数: 約1,800,000件（993k + 800k + 5k）
   - SQLiteサイズ（展開後）: 1-2GB
   - 圧縮後: 500MB-1GB
```

## 既存実装の分析結果

### データ処理フロー（genai-tag-db-tools）

#### 処理アーキテクチャ
```
CSV/Parquet → Polars DataFrame → TagRegister → TagRepository → SQLite
                    ↓
              TagCleaner.clean_format()
                    ↓
         normalize_tags() → bulk_insert_tags() → usage_counts/translations
```

#### 主要コンポーネント

**1. TagDataImporter** (`services/import_data.py`)
**2. TagRegister** (`services/tag_register.py`)
**3. TagRepository** (`data/tag_repository.py`)
**4. TagCleaner** (`utils/cleanup_str.py`)

### 既存データの扱い

#### データ保持戦略の選択肢

**Option A: tags_v4.dbから逆エクスポート（推奨）**
- メリット: ライセンス問題を回避、実装が単純、データ完全性保証
- デメリット: 元のデータソースメタデータ（どのCSVから来たか）が失われる

**推奨方針: Option A（DB逆エクスポート）** - 採用

理由:
1. **ライセンスリスク最小化**: DB抽出データなら二次的派生物として扱える
2. **実装容易性**: 単一ソース（tags_v4.db）からの変換のみ
3. **データ完全性**: 993,514タグ全て保持保証
4. **法的安全性**: 「データベースから抽出」は事実ベース記載

## アーキテクチャ設計（修正版）

### 基本方針：完全オフライン設計

**設計原則:**
1. HFから事前構築済みSQLiteをダウンロード（初回のみ）
2. 以降は完全オフライン動作（ローカルSQLiteクエリのみ）
3. 更新は「丸ごと入れ替え＋バックアップ」方式
4. ストリーミング・オンライン取得機能は提供しない

#### 初回セットアップフロー（確定版）
```
1. ユーザー操作: `genai-tag-db-setup` コマンド実行
2. データ取得: HFからSQLite圧縮ファイルダウンロード
3. 整合性検証: SHA256検証
4. 展開・配置: zstd展開 → アトミック配置
5. スキーマ検証・WALモード有効化

所要時間: 6-12分（初回のみ）
ディスク使用量: 2.5-5GB（最大時）
```

## スキーマ契約（DB成果物の仕様）

### 必須テーブル定義

**tags_unified.db スキーマ（SQLite 3.x）**

```sql
-- メタデータテーブル（新規追加）
CREATE TABLE METADATA (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 既存テーブル（tags_v4.db互換）
CREATE TABLE TAGS (...);
CREATE TABLE TAG_TRANSLATIONS (...);
CREATE TABLE TAG_FORMATS (...);
CREATE TABLE TAG_TYPE_NAME (...);
CREATE TABLE TAG_TYPE_FORMAT_MAPPING (...);
CREATE TABLE TAG_STATUS (...);
CREATE TABLE TAG_USAGE_COUNTS (...);

-- 新規追加テーブル（拡張機能）
CREATE TABLE ALTERNATIVE_TRANSLATIONS (...);

-- 必須インデックス（パフォーマンス保証）
CREATE INDEX idx_tags_tag ON TAGS(tag);
CREATE INDEX idx_tags_source_tag ON TAGS(source_tag);
...
```

## CI/CD設計（GitHub Actions）

### ビルドパイプライン

```yaml
# .github/workflows/build_dataset.yml
name: Build Unified Tag Database

on:
  schedule:
    - cron: '0 0 1 * *'  # 月初0時（月次更新）
  workflow_dispatch:     # 手動実行可能

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 180  # 3時間
    steps:
      - Build Step 1: Export tags_v4.db
      - Build Step 2: Extract deepghs/site_tags
      - Build Step 3: Extract danbooru-wiki
      - Build Step 4: Merge all sources
      - Build Step 5: Optimize database
      - Build Step 6: Compress with zstd
      - Build Step 7: Generate metadata
      - Upload to HuggingFace
```

## 実装フェーズ（修正版）

### Phase 1: データ統合基盤構築（Week 1-2）
#### Week 1: 統合スクリプト開発
#### Week 2: HF公開と初期検証

### Phase 2: 3層クエリアーキテクチャ実装（Week 3-4）
### Phase 3: API互換性ラッパー実装（Week 5）
### Phase 4: テストと検証（Week 6）
### Phase 5: デプロイとマイグレーション（Week 7）

## 成功基準（修正版）

### 機能要件
- [x] 既存TagSearcher/TagCleaner APIの100%互換
- [x] オフライン動作（Layer 1/2で95%以上のクエリ対応）
- [x] 3データソース統合
- [x] 初回セットアップ5分以内

### 非機能要件
- [x] Layer 1応答: 10-50ms (95%ile)
- [x] Layer 2応答: 200-500ms (95%ile)
- [x] ディスク使用: 329MB（通常時）、829MB以下（拡張時）
- [x] メモリ使用: 800MB以下（ピーク時）
- [x] テストカバレッジ: 75%以上
- [x] HFデータ完全性: 100%（全タグ993,514件）

### ライセンス・法務要件
- [x] CC-BY-SA 4.0適用（統合データセット）
- [x] MITライセンス維持（処理ロジック）
- [x] データソースクレジット明記（Dataset Card）

## 変更履歴

- **v1.0 (2025-12-13初版)**: 初期計画
- **v2.0 (2025-12-13改訂)**: 技術的課題全面解決
- **v2.1 (2025-12-13改訂)**: 2層データ構造の採用
- **v2.2 (2025-12-13改訂)**: 既存実装分析と処理フロー明確化
- **v2.3 (2025-12-13改訂)**: SQLite配布形式確定

**注**: 本計画の詳細は約2000行の完全版を参照してください。
