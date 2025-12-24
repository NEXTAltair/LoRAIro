# Dataset Builder Phase 7: Repository-Based Automation Plan

## 策定日
2025年12月17日

## 概要

**目的**: Builder を当初の目的である「リポジトリーから自動でデータソースを集めてデータベースを構築」に立ち戻らせる。ローカルに置かれた CSV/DB を前提にせず、**取得→ビルド検証までを自動化**して再現可能なビルドを実現する（アップロードは手動でよい）。

**前提条件**: Phase 6.5（CC4版ローカルビルド）の完了
- 新スキーマ（TAG_FORMATS拡張）がCC0/MIT/CC4全てに適用済み
- deepghs/site_tags 統合の実績あり
- 詳細: `dataset_builder_phase6_5_cc4_local_build_plan_2025_12_17.md`

**スコープ**: 
- 新しいワークツリー/ブランチでクリーンな実装
- データ取得と処理の完全分離
- GitHub Actions による**手動トリガー**の自動ビルド検証パイプライン
- HuggingFace へのアップロードは**手動**（ビルド成果物の確認後に実施）

---

## ultrathink: 設計思考プロセス

### 問題の本質

**現状の問題点**:
1. ローカルファイル前提のコード（tags_v4.db、CSV ファイルのパス指定）
2. データ修正・クリーンアップが builder.py に混在し肥大化
3. 再現性の欠如（ローカル環境に依存、データソースのバージョン管理が不明確）
4. 手動ビルドが必要（自動更新されない）

**根本原因**:
- Phase 0-6 の設計がローカルファイル操作を前提としていた
- データ取得層とビルド層が混在
- GitHub Actions の CI/CD はテスト・Lint のみで、データビルドは未対応

### 理想のアーキテクチャ

```
┌─────────────────────────────────────────────────────┐
│ GitHub Actions (Manual Trigger only)                │
├─────────────────────────────────────────────────────┤
│ Phase A: Data Fetching                              │
│  ├─ Base DB (HF: NEXTAltair/genai-image-tag-db)   │
│  ├─ CSV Sources (from GitHub Repos)                │
│  └─ HuggingFace Datasets (via datasets library)    │
├─────────────────────────────────────────────────────┤
│ Phase B: Data Processing & Build                    │
│  ├─ builder.py (clean, no data correction)         │
│  └─ adapters (pure data transformation)            │
├─────────────────────────────────────────────────────┤
│ Phase C: Output & Publish                           │
│  ├─ SQLite (.db)                                    │
│  ├─ Parquet (HF Dataset Viewer)                    │
│  └─ HuggingFace Upload (manual)                    │
└─────────────────────────────────────────────────────┘
```

**設計原則**:
1. **Separation of Concerns**: データ取得 / 処理 / 公開を完全分離
2. **Reproducibility**: 全データソースが URL/API から取得可能
3. **Automation**: GitHub Actions でビルド検証まで自動化（手動トリガー）
4. **Clean Architecture**: builder.py からデータ修正コードを除去

---

## 要件定義

### 機能要件

**FR-1: データソース自動取得**
- Base DB の自動取得（HuggingFace: NEXTAltair/genai-image-tag-db）
- GitHub リポジトリからの CSV ファイル自動取得
- HuggingFace データセットの自動取得（翻訳等）
- データソースバージョンの記録（再現性保証）
- **非対象**: 事前にローカルへ配置された CSV/DB の取り込み（Phase 0-6 の方式）は Phase 7 の範囲外
- **ライセンス自動解析の判定単位**: 原則「リポジトリ単位」でよい（当面、複数ライセンス混在 repo を想定しない）
- **取得方式**: 原則「リポジトリを丸ごとクローン→内容を読んで処理決定」でよい（意図しないファイル拾いは実害が出た時に対処）
- **日時（重要）**: ホスティングサイト/ソース由来で「確実な更新日時」が取得できる場合は、それを優先してDBへ入力する。\n+  - 例: `TAG_USAGE_COUNTS.created_at/updated_at` は「countの観測日時（ソース側の日時）」として運用する\n+  - 例: タグ追加日/更新日なども、ソース側で確実に取得できるならそれを優先\n+  - 取得できない場合のみ、ビルド側の日時（固定で `00:00:00` でも可）を利用する

**FR-2: クリーンなビルド処理**
- builder.py の肥大化を解消（責務分割・モジュール化）
- Adapter による純粋なデータ変換のみ
- 翻訳クリーンアップ等は専用の前処理層へ移行（※「クリーンアップ除去」は**データ修正を無くす**の意味ではなく、コードの責務整理の意味）

**FR-3: GitHub Actions 統合**
- 手動トリガー（workflow_dispatch）
- ビルド成果物の Artifacts 保存
- ビルド検証（pytest + DB health report + parquet 生成）までを自動化
- HuggingFace へのアップロードは**手動**（運用負荷と失敗時の後戻りを優先）

**FR-4: ライセンス別ビルド**
- CC0 版ビルド（既存実装を流用）
- MIT 版ビルド（**HF上のCC0版SQLiteをベースに差分追記**）
- CC-BY-4.0 等が来たら別リポジトリ（例: `NEXTAltair/genai-image-tag-db-cc4`）としてビルド対象を追加
- ライセンス情報の自動生成（HF/GitHub のメタデータからの自動抽出を基本とする）

### 非機能要件

**NFR-1: 再現性**
- 全データソースが URL/API で取得可能
- ビルドプロセスが完全自動化
- データソースバージョンの記録

**NFR-2: パフォーマンス**
- GitHub Actions の実行時間制限内（6時間以内）
- キャッシュ活用によるビルド時間短縮

**NFR-3: 保守性**
- データ取得・処理・公開の明確な分離
- 各層のテストが独立
- 設定ファイルによる柔軟な管理

---

## 現状分析

### 現在のアーキテクチャ

```
builder.py (1800+ lines)
  ├─ Phase 0: データベース作成
  ├─ Phase 1: Danbooru tags_v3.db 取り込み
  │   └─ 言語値正規化（normalize_language_value）
  ├─ Phase 2: CSV 取り込み
  │   ├─ 翻訳クリーンアップ（delete_ja_translations_by_value_list）
  │   ├─ ASCII翻訳削除（delete_translations_ascii_only_for_languages）
  │   └─ 必須文字種チェック（delete_translations_missing_required_script）
  ├─ Phase 2.5: HF Translation 取り込み
  ├─ Phase 3: SQLite 最適化
  └─ Phase 4: Parquet エクスポート
```

**問題点**:
- builder.py に 5つのクリーンアップ関数が混在（約300行）
- ローカルファイルパス前提（`--sources`, `--csv-dir`）
- データソースの取得方法が不明確（README に記載なし）
- GitHub Actions は CI/CD のみ（データビルドなし）
- Base DB (HuggingFace の genai-image-tag-db) を前提とした「repo取得→ビルド検証」の自動化が未整備

### 既存の CI/CD インフラ

**`.github/workflows/ci.yml`**:
- トリガー: push, PR, workflow_dispatch
- ジョブ: test, lint
- 機能: テスト実行、カバレッジ測定、Ruff/mypy

**`.github/workflows/build-and-publish.yml`**:
- トリガー: 手動（workflow_dispatch）
- 機能: HuggingFace へのアップロード

**不足している機能**:
- データソースの自動取得
- 手動トリガーでのビルド検証ワークフロー整備（取得→ビルド→検証→Artifacts）
- ビルド成果物の Artifacts 保存

---

## ギャップ分析

| 要件 | 現状 | ギャップ | 優先度 |
|------|------|----------|--------|
| データ自動取得 | ? ローカルファイル前提 | 取得層の実装が必要 | 高 |
| クリーンなビルド | ? データ修正が混在 | 前処理層への分離が必要 | 高 |
| スケジュール実行 | ? 手動実行のみ | **採用しない（不要）** | - |
| 再現性保証 | ?? 部分的（ソース不明） | データソース URL の記録 | 高 |
| ライセンス別ビルド | ? 実装済み | なし | - |
| HF 自動アップロード | ? 実装済み | **採用しない（手動アップロード）** | - |

---

## 解決策の検討

### アプローチ A: Builder 拡張アプローチ

**概要**: 既存 builder.py に Fetcher モジュールを追加

**アーキテクチャ**:
```
builder.py (拡張)
  ├─ fetch_data_sources() → データ取得
  ├─ preprocess_data() → 前処理（クリーンアップ）
  └─ build_database() → ビルド（既存）
```

**メリット**:
- 既存コードの大部分を流用
- 実装コストが低い
- 段階的移行が可能

**デメリット**:
- builder.py がさらに肥大化
- 責任分離が不十分
- テストが複雑化

**評価**: ❌ 長期的保守性に問題

### アプローチ B: 完全分離アーキテクチャ

**概要**: データ取得・前処理・ビルドを独立したモジュールに分離

**アーキテクチャ**:
```
src/genai_tag_db_dataset_builder/
  ├─ fetcher/
  │   ├─ base.py (BaseFetcher)
  │   ├─ tags_v4.py (Tags_v4_Fetcher)
  │   ├─ github_csv.py (GitHub_CSV_Fetcher)
  │   └─ huggingface.py (HF_Dataset_Fetcher)
  ├─ preprocessor/
  │   ├─ translation_cleaner.py
  │   └─ normalization.py
  └─ builder/
      ├─ builder.py (クリーン版)
      └─ adapters/ (既存)
```

**メリット**:
- 責任分離が明確
- テストが独立
- 長期的保守性が高い
- 新しいデータソース追加が容易

**デメリット**:
- 実装コストが高い
- 既存コードの大規模リファクタリングが必要
- 移行期間中の並行保守

**評価**: ✅ 推奨（長期的視点）

### アプローチ C: マイクロサービス風アーキテクチャ

**概要**: 各 Phase を独立した CLI ツールとして実装

**アーキテクチャ**:
```
genai-tag-db-dataset-builder/
  ├─ fetch (CLI)
  ├─ preprocess (CLI)
  ├─ build (CLI)
  └─ publish (CLI)
```

**メリット**:
- 各ステップが完全独立
- デバッグが容易
- CI/CD での並列実行可能

**デメリット**:
- 実装コストが非常に高い
- 中間データの管理が複雑
- オーバーエンジニアリングのリスク

**評価**: ⚠️ 現時点では過剰設計

---

## 推奨ソリューション: アプローチ B（完全分離アーキテクチャ）

### アーキテクチャ設計

#### 1. Fetcher Layer（データ取得層）

**責任**: 外部ソースからのデータ取得、キャッシュ管理

```python
# src/genai_tag_db_dataset_builder/fetcher/base.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class BaseFetcher(ABC):
    """データソース取得の基底クラス"""
    
    @abstractmethod
    def fetch(self, cache_dir: Path) -> Path:
        """データを取得し、キャッシュディレクトリに保存"""
        pass
    
    @abstractmethod
    def get_metadata(self) -> dict[str, Any]:
        """データソースのメタデータを取得（バージョン、URL等）"""
        pass

# src/genai_tag_db_dataset_builder/fetcher/huggingface_base.py

class HF_BaseDB_Fetcher(BaseFetcher):
    def __init__(self, repo_id: str = "NEXTAltair/genai-image-tag-db"):
        self.repo_id = repo_id
    
    def fetch(self, cache_dir: Path) -> Path:
        """HuggingFace から Base DB をダウンロード"""
        from huggingface_hub import hf_hub_download
        
        target = cache_dir / "base.db"
        if not target.exists():
            db_path = hf_hub_download(
                repo_id=self.repo_id,
                filename="genai-image-tag-db.sqlite",
                cache_dir=cache_dir
            )
            shutil.copy(db_path, target)
        return target
    
    def get_metadata(self) -> dict[str, Any]:
        return {
            "source": "huggingface_base_db",
            "repo_id": self.repo_id,
            "fetched_at": datetime.now().isoformat()
        }
```

**主要 Fetcher**:
- `HF_BaseDB_Fetcher`: Base DB (NEXTAltair/genai-image-tag-db) の取得
- `GitHub_CSV_Fetcher`: GitHub リポジトリから CSV ファイル取得（git clone または API）
- `HF_Dataset_Fetcher`: HuggingFace datasets ライブラリ経由で翻訳データ等を取得

#### 2. Preprocessor Layer（前処理層）

**責任**: データクリーンアップ、正規化（builder.py から分離）

```python
# src/genai_tag_db_dataset_builder/preprocessor/translation_cleaner.py

from pathlib import Path
import sqlite3

class TranslationCleaner:
    """翻訳データのクリーンアップ処理"""
    
    def clean_ja_contamination(
        self, 
        db_path: Path,
        exclude_values: list[str]
    ) -> int:
        """language='ja' の中国語・英単語混入を除去"""
        conn = sqlite3.connect(db_path)
        deleted = _delete_ja_translations_by_value_list(conn, exclude_values)
        conn.close()
        return deleted
    
    def clean_missing_required_script(
        self, 
        db_path: Path,
        language: str
    ) -> int:
        """必須文字種を含まない翻訳を除去"""
        conn = sqlite3.connect(db_path)
        deleted = _delete_translations_missing_required_script(conn, language)
        conn.close()
        return deleted
```

**主要 Preprocessor**:
- `TranslationCleaner`: 翻訳データクリーンアップ（既存実装を移行）
- `LanguageNormalizer`: 言語値正規化（japanese→ja等）
- `FullwidthNormalizer`: 全角記号正規化（既存実装を移行）

#### 3. Builder Layer（ビルド層）

**責任**: データベース構築のみ（クリーンアップなし）

```python
# src/genai_tag_db_dataset_builder/builder/builder.py

class DatabaseBuilder:
    """クリーンなデータベースビルダー（前処理済みデータを使用）"""
    
    def build(
        self,
        output_path: Path,
        tags_v4_path: Path,
        csv_sources: list[Path],
        hf_datasets: list[str],
        config: BuildConfig
    ) -> BuildResult:
        """
        前処理済みデータからデータベースを構築
        
        - データクリーンアップは preprocessor で完了済み前提
        - Adapter による純粋なデータ変換のみ実施
        """
        # Phase 0: Base DB をコピー（HuggingFace からの取得済みDB）
        shutil.copy(base_db_path, output_path)
        
        # Phase 1: CSV 取り込み（クリーンアップなし）
        for csv_path in csv_sources:
            self._import_csv(output_path, csv_path)
        
        # Phase 3: SQLite 最適化
        optimize_database(output_path)
        
        # Phase 4: Parquet エクスポート
        export_to_parquet(output_path, config.parquet_dir)
        
        return BuildResult(...)
```

#### 4. Orchestrator（統合層）

**責任**: Fetcher → Preprocessor → Builder の統合実行

```python
# src/genai_tag_db_dataset_builder/orchestrator.py

class BuildOrchestrator:
    """ビルドプロセス全体の統合管理"""
    
    def run(self, config: OrchestratorConfig) -> None:
        """
        1. Fetch: データソース取得
        2. Preprocess: 前処理・クリーンアップ
        3. Build: データベース構築
        4. Publish: 出力・アップロード
        """
        # Step 1: Fetch
        fetcher = FetcherRegistry.create(config.sources)
        data_paths = fetcher.fetch_all(config.cache_dir)
        
        # Step 2: Preprocess
        preprocessor = PreprocessorPipeline(config.preprocess_rules)
        preprocessor.run(data_paths)
        
        # Step 3: Build
        builder = DatabaseBuilder()
        result = builder.build(
            output_path=config.output_path,
            base_db_path=data_paths["base_db"],
            csv_sources=data_paths["csv"],
            hf_datasets=config.hf_datasets,
            config=config.build_config
        )
        
        # Step 4: Publish
        if config.publish:
            publisher = HuggingFacePublisher(config.hf_token)
            publisher.upload(result.output_path, config.hf_repo)
```

### GitHub Actions ワークフロー設計

**`.github/workflows/build-dataset.yml`**:

```yaml
name: Build Tag Database

on:
  workflow_dispatch:
    inputs:
      license_type:
        description: 'License type to build (cc0, mit, both)'
        required: true
        default: 'both'
        type: choice
        options:
          - cc0
          - mit
          - both

jobs:
  build-cc0:
    if: github.event.inputs.license_type == 'cc0' || github.event.inputs.license_type == 'both'
    runs-on: ubuntu-latest
    timeout-minutes: 360  # 6時間
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      
      - name: Install dependencies
        run: |
          cd local_packages/genai-tag-db-dataset-builder
          uv sync --dev
      
      - name: Cache data sources
        uses: actions/cache@v4
        with:
          path: |
            ~/.cache/genai-tag-db-builder/base.db
            ~/.cache/genai-tag-db-builder/csv_sources/
          key: data-sources-${{ hashFiles('**/data_sources_config.json') }}
      
      - name: Build CC0 Database
        run: |
          cd local_packages/genai-tag-db-dataset-builder
          uv run python -m genai_tag_db_dataset_builder.orchestrator \
            --config configs/cc0_build_config.json \
            --output out_db_cc0/genai-image-tag-db-cc0.sqlite \
            --parquet-dir out_db_cc0/parquet \
            --cache-dir ~/.cache/genai-tag-db-builder
      
      - name: Upload Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: cc0-database
          path: |
            local_packages/genai-tag-db-dataset-builder/out_db_cc0/*.sqlite
            local_packages/genai-tag-db-dataset-builder/out_db_cc0/*.tsv
            local_packages/genai-tag-db-dataset-builder/out_db_cc0/parquet/
      
      # Upload to HuggingFace は手動運用（Artifacts を確認してからアップロード）
  
  build-mit:
    # MIT版も同様の構成（差分ビルド戦略を使用）
    if: github.event.inputs.license_type == 'mit' || github.event.inputs.license_type == 'both'
    # ベースDB方針:
    # - CC0ビルド: HFのCC0版SQLiteをベースに差分追記
    # - MITビルド: HFのMIT版SQLiteをベースに差分追記（CC0ジョブへの依存は不要）
    # - CC-BY-4.0等: 当面はHFのCC0版SQLiteをベースに差分追記し、別リポジトリへ出す
    runs-on: ubuntu-latest
    timeout-minutes: 180  # 3時間（差分ビルドのため短縮）
    
    steps:
      # CC0版ビルドと同様の手順
      # --base-db オプションで CC0版を指定
```

**主要機能**:
1. **手動トリガー**: ライセンス種別を選択可能（cc0/mit/both）
2. **キャッシュ**: データソースをキャッシュして高速化
3. **Artifacts**: ビルド成果物を保存
4. **HuggingFace Upload（手動）**: ビルド成果物を確認してから手動でアップロード

### 設定ファイル設計

**`configs/data_sources_config.json`**:

```json
{
  "data_sources": [
    {
      "name": "base_db_cc0",
      "type": "huggingface_base",
      "repo_id": "NEXTAltair/genai-image-tag-db",
      "filename": "genai-image-tag-db-cc0.sqlite"
    },
    {
      "name": "base_db_mit",
      "type": "huggingface_base",
      "repo_id": "NEXTAltair/genai-image-tag-db-mit",
      "filename": "genai-image-tag-db-mit.sqlite"
    },
    {
      "name": "booru_japanese_tag",
      "type": "github_repo",
      "repo": "boorutan/booru-japanese-tag",
      "ref": "main"
    },
    {
      "name": "halfmai_gist_sources",
      "type": "github_gist",
      "gist_id": "HalfMAI/e20a974a8b87bbb63d8da8051442b6b2"
    },
    {
      "name": "tagtable",
      "type": "github_repo",
      "repo": "zcyzcy88/TagTable",
      "ref": "main"
    },
    {
      "name": "danbooru_ja_tag_pair_20241015",
      "type": "huggingface_dataset",
      "dataset_id": "p1atdev/danbooru-ja-tag-pair-20241015",
      "split": "train"
    },
    {
      "name": "e621_rising_v3_curated",
      "type": "huggingface_dataset",
      "dataset_id": "hearmeneigh/e621-rising-v3-curated",
      "split": "train"
    },
    {
      "name": "danbooru2023_metadata_database",
      "type": "huggingface_dataset",
      "dataset_id": "KBlueLeaf/danbooru2023-metadata-database",
      "split": "train"
    },
    {
      "name": "deepghs_site_tags",
      "type": "huggingface_dataset",
      "dataset_id": "deepghs/site_tags",
      "split": "train"
    }
  ]
}
```

> 注: Phase 7 では「ローカルに置いたCSVファイルそのものの取り込み」は扱わない（既にCC0/MITビルドに取り込み済みの前提）。\n+> 取得対象は上記のような「HF / GitHub（repo or gist）」のみに絞る。

**`configs/cc0_build_config.json`**:

```json
{
  "license": "cc0-1.0",
  "base_db": "NEXTAltair/genai-image-tag-db (genai-image-tag-db-cc0.sqlite)",
  "include_sources": [
    "danbooru_241016.csv",
    "Tags_zh_full.csv"
  ],
  "exclude_sources": [],
  "preprocessing": {
    "translation_cleaning": true,
    "language_normalization": true,
    "fullwidth_normalization": true
  },
  "build": {
    "skip_danbooru_snapshot_replace": false,
    "enable_parquet_export": true
  },
  "publish": {
    "huggingface_repo": "NEXTAltair/genai-image-tag-db-cc0",
    "auto_upload": true
  }
}
```

---

## 実装計画

### Phase 7.0: 準備・設計（Week 1、5日間）

**Day 1-2: 新ワークツリー作成・環境構築**

```bash
# 新ワークツリー作成
cd /workspaces
git worktree add LoRAIro-phase7-repo-automation feature/phase7-repository-automation

cd LoRAIro-phase7-repo-automation
uv sync --dev
```

**タスク**:
- [ ] 新ブランチ `feature/phase7-repository-automation` 作成
- [ ] ワークツリーでの環境構築
- [ ] 既存テストの実行確認（全125テスト PASS）

**Day 3-5: アーキテクチャ設計ドキュメント作成**

**タスク**:
- [ ] Serenaメモリ作成: `dataset_builder_phase7_fetcher_architecture`
- [ ] Serenaメモリ作成: `dataset_builder_phase7_preprocessor_architecture`
- [ ] Serenaメモリ作成: `dataset_builder_phase7_orchestrator_architecture`
- [ ] データソース URL の調査・リスト化

### Phase 7.1: Fetcher Layer 実装（Week 2-3、10日間）

**Day 1-3: BaseFetcher と HF_BaseDB_Fetcher**

**実装**:
```python
# src/genai_tag_db_dataset_builder/fetcher/base.py
# src/genai_tag_db_dataset_builder/fetcher/huggingface_base.py
# tests/unit/fetcher/test_huggingface_base_fetcher.py
```

**タスク**:
- [ ] BaseFetcher 実装（抽象クラス、メタデータ管理）
- [ ] HF_BaseDB_Fetcher 実装（HuggingFace Hub からダウンロード、キャッシュ）
- [ ] ユニットテスト（HuggingFace Hub モック）

**Day 4-7: GitHub_CSV_Fetcher**

**実装**:
```python
# src/genai_tag_db_dataset_builder/fetcher/github_csv.py
# tests/unit/fetcher/test_github_csv_fetcher.py
```

**タスク**:
- [ ] GitHub API 経由での CSV 取得実装
- [ ] git clone オプションの実装（大規模リポジトリ対応）
- [ ] ユニットテスト（GitHub API モック）

**Day 8-10: HF_Dataset_Fetcher**

**実装**:
```python
# src/genai_tag_db_dataset_builder/fetcher/huggingface.py
# tests/unit/fetcher/test_huggingface_fetcher.py
```

**タスク**:
- [ ] HuggingFace datasets ライブラリ統合
- [ ] Parquet ファイルへの変換処理
- [ ] ユニットテスト

### Phase 7.2: Preprocessor Layer 実装（Week 4、7日間）

**Day 1-4: TranslationCleaner 分離**

**実装**:
```python
# src/genai_tag_db_dataset_builder/preprocessor/translation_cleaner.py
# tests/unit/preprocessor/test_translation_cleaner.py
```

**タスク**:
- [ ] builder.py から既存クリーンアップ関数を移行
  - `_normalize_language_value`
  - `_delete_ja_translations_by_value_list`
  - `_delete_translations_ascii_only_for_languages`
  - `_delete_translations_missing_required_script`
- [ ] TranslationCleaner クラスとして再実装
- [ ] ユニットテスト（既存テストを移行）

**Day 5-7: FullwidthNormalizer 分離**

**実装**:
```python
# src/genai_tag_db_dataset_builder/preprocessor/normalization.py
# tests/unit/preprocessor/test_normalization.py
```

**タスク**:
- [ ] core/normalize.py の全角記号変換を抽出
- [ ] FullwidthNormalizer クラスとして再実装
- [ ] ユニットテスト

### Phase 7.3: Builder Layer リファクタリング（Week 5-6、10日間）

**Day 1-5: builder.py のクリーンアップ**

**タスク**:
- [ ] クリーンアップ関数の削除（約300行削減）
- [ ] Phase 1/2 からクリーンアップ呼び出しの削除
- [ ] DatabaseBuilder クラスへの再構成
- [ ] 既存テストの修正（preprocessor 前提に変更）

**Day 6-10: Integration Tests 追加**

**実装**:
```python
# tests/integration/test_fetcher_preprocessor_builder.py
```

**タスク**:
- [ ] Fetcher → Preprocessor → Builder の統合テスト
- [ ] ライセンス別ビルドの統合テスト（CC0/MIT）
- [ ] エンドツーエンドテスト（小規模データセット使用）

### Phase 7.4: Orchestrator 実装（Week 7、7日間）

**Day 1-4: BuildOrchestrator 実装**

**実装**:
```python
# src/genai_tag_db_dataset_builder/orchestrator.py
# tests/unit/test_orchestrator.py
```

**タスク**:
- [ ] FetcherRegistry 実装（設定ファイルから Fetcher 生成）
- [ ] PreprocessorPipeline 実装（順次実行）
- [ ] BuildOrchestrator 実装（全体統合）
- [ ] 設定ファイルスキーマ定義（JSON Schema）

**Day 5-7: CLI インターフェース実装**

**実装**:
```python
# src/genai_tag_db_dataset_builder/__main__.py
```

**タスク**:
- [ ] argparse による CLI 実装
- [ ] 設定ファイル読み込み
- [ ] ロギング設定
- [ ] エラーハンドリング

### Phase 7.5: GitHub Actions 統合（Week 8、7日間）

**Day 1-3: ワークフロー実装**

**実装**:
```yaml
# .github/workflows/build-dataset.yml
```

**タスク**:
- [ ] 手動トリガー設定（workflow_dispatch）
- [ ] キャッシュ設定（データソース、uv）
- [ ] Artifacts アップロード設定

**Day 4-5: CC0 版ビルドジョブ**

**タスク**:
- [ ] CC0 版ビルドジョブ実装
- [ ] テスト実行（手動トリガー）

**Day 6-7: MIT 版ビルドジョブ**

**タスク**:
- [ ] MIT 版ビルドジョブ実装（CC0 依存）
- [ ] 差分ビルド戦略の統合
- [ ] テスト実行（手動トリガー）

### Phase 7.6: ドキュメント整備（Week 9、5日間）

**Day 1-2: README 更新**

**タスク**:
- [ ] README.md にアーキテクチャ図追加
- [ ] データソース一覧の記載
- [ ] ビルド手順の記載（ローカル/CI）
- [ ] トラブルシューティング追加

**Day 3-4: Serenaメモリ作成**

**タスク**:
- [ ] `dataset_builder_phase7_completion_report`
- [ ] `dataset_builder_fetcher_guide`
- [ ] `dataset_builder_preprocessor_guide`
- [ ] `dataset_builder_orchestrator_guide`

**Day 5: 完了記録・引き継ぎ**

**タスク**:
- [ ] Phase 7 完了記録の作成
- [ ] Phase 8（将来）への引き継ぎ事項整理
- [ ] dataset_builder__index.md の更新

---

## テスト戦略

### ユニットテスト

**Fetcher Layer**:
- モックサーバーを使用した HTTP ダウンロードテスト
- GitHub API モックによる CSV 取得テスト
- HuggingFace datasets のモックテスト
- キャッシュ機能のテスト

**Preprocessor Layer**:
- 既存の translation_cleanup テストを移行
- 正規化処理のテスト
- SQLite 接続の分離（テストごとに独立したDB使用）

**Builder Layer**:
- 既存の builder テストを修正（preprocessor 前提に）
- クリーンアップなしでのビルドテスト

**Orchestrator**:
- 設定ファイル読み込みテスト
- 各層の統合テスト（モック使用）

### 統合テスト

**エンドツーエンドテスト**:
```python
# tests/integration/test_full_build_pipeline.py

def test_full_build_cc0(tmp_path):
    """CC0版のフルビルドをテスト（小規模データセット）"""
    config = OrchestratorConfig(
        sources=["tags_v4", "small_csv_sample"],
        output_path=tmp_path / "output.db",
        license="cc0"
    )
    orchestrator = BuildOrchestrator()
    result = orchestrator.run(config)
    
    # 検証
    assert result.output_path.exists()
    assert result.total_tags > 0
    assert result.build_time < 60  # 1分以内
```

### GitHub Actions テスト

**戦略**:
1. **小規模データセットでのテスト**: 手動トリガーで実行、5-10分で完了
2. **フルビルドテスト**: 手動トリガーで実データをビルド・検証
3. **Artifacts 確認**: ビルド成果物のダウンロード・検証

---

## リスク管理

### 高リスク

**R1: GitHub Actions 実行時間超過（6時間制限）**
- 発生確率: 中
- 影響度: 高
- 対策: 
  - キャッシュ活用によるビルド時間短縮
  - フルビルドを段階的に実行（CC0→MIT）
  - タイムアウト時の再実行戦略

**R2: データソース URL の変更・削除**
- 発生確率: 中
- 影響度: 高
- 対策:
  - 複数ミラーの準備
  - Fallback URL の設定
  - 定期的な URL 確認

### 中リスク

**R3: 既存テストの大規模修正**
- 発生確率: 高
- 影響度: 中
- 対策:
  - 段階的リファクタリング
  - 既存機能の保証（回帰テスト）
  - テスト優先での実装

**R4: HuggingFace アップロード失敗**
- 発生確率: 低
- 影響度: 中
- 対策:
  - Artifacts への保存（バックアップ）
  - リトライ機構の実装
  - 手動アップロードの手順書

### 低リスク

**R5: キャッシュ無効化によるビルド遅延**
- 発生確率: 低
- 影響度: 低
- 対策:
  - キャッシュキーの安定化
  - 部分キャッシュの活用

---

## 成功基準

### Phase 7.0-7.4（実装）

- [ ] 全 Fetcher の実装完了（HF_BaseDB, GitHub_CSV, HuggingFace）
- [ ] 全 Preprocessor の実装完了（TranslationCleaner, FullwidthNormalizer）
- [ ] builder.py からクリーンアップ処理を分離（責務整理、約300行削減）
- [ ] Orchestrator の実装完了
- [ ] ユニットテスト≥80% カバレッジ
- [ ] 統合テスト 5件以上

### Phase 7.5（GitHub Actions）

- [ ] 手動トリガー（workflow_dispatch）のワークフロー完成（スケジュール実行は無し）
- [ ] 手動トリガーでの CC0/MIT ビルド成功（取得→ビルド→検証→Artifacts）
- [ ] Artifacts 保存・ダウンロード確認

### Phase 7.6（ドキュメント）

- [ ] README.md にアーキテクチャ図追加
- [ ] データソース一覧完成
- [ ] Serenaメモリ 4件以上作成
- [ ] Phase 7 完了記録作成

### 全体

- [ ] ローカルビルドとGitHub Actionsビルドの結果が一致
- [ ] 再現性保証（データソースバージョン記録）
- [ ] ビルド時間≤6時間（GitHub Actions制限内）

---

## タイムライン

### Phase 7.0: 準備・設計（Week 1）
- Day 1-2: 新ワークツリー作成・環境構築
- Day 3-5: アーキテクチャ設計ドキュメント作成

### Phase 7.1: Fetcher Layer 実装（Week 2-3）
- Day 1-3: BaseFetcher と HF_BaseDB_Fetcher
- Day 4-7: GitHub_CSV_Fetcher
- Day 8-10: HF_Dataset_Fetcher

### Phase 7.2: Preprocessor Layer 実装（Week 4）
- Day 1-4: TranslationCleaner 分離
- Day 5-7: FullwidthNormalizer 分離

### Phase 7.3: Builder Layer リファクタリング（Week 5-6）
- Day 1-5: builder.py のクリーンアップ
- Day 6-10: Integration Tests 追加

### Phase 7.4: Orchestrator 実装（Week 7）
- Day 1-4: BuildOrchestrator 実装
- Day 5-7: CLI インターフェース実装

### Phase 7.5: GitHub Actions 統合（Week 8）
- Day 1-3: ワークフロー実装
- Day 4-5: CC0 版ビルドジョブ
- Day 6-7: MIT 版ビルドジョブ

### Phase 7.6: ドキュメント整備（Week 9）
- Day 1-2: README 更新
- Day 3-4: Serenaメモリ作成
- Day 5: 完了記録・引き継ぎ

**総所要時間**: 9週間（45営業日）

---

## 次のステップ

### Phase 6.5 を先に実施

**重要**: Phase 7 の前に Phase 6.5（CC4版ローカルビルド）を完了させる必要があります。

**Phase 6.5 の目的**:
1. CC0版のスキーマ変更（TAG_FORMATS拡張）
2. CC0版の新スキーマでの再ビルド
3. CC0版をベースにCC4版を差分追記（deepghs/site_tags統合）
4. MIT版も新スキーマで再ビルド

**詳細**: `dataset_builder_phase6_5_cc4_local_build_plan_2025_12_17.md`

**実装順序**:
1. Phase 6.5.1: スキーマ設計とマイグレーション（3日間）
2. Phase 6.5.2: CC0版再ビルド（4日間）
3. Phase 6.5.3: SiteTags_Adapter 実装（5日間）
4. Phase 6.5.4: CC4版ビルド（5日間）
5. Phase 6.5.5: MIT版再ビルド（3日間）
6. Phase 6.5.6: ドキュメント整備（2日間）

**総所要時間**: 4週間（22営業日）

---

## Phase 7 実装開始の前提条件

Phase 6.5 完了後、以下の状態になっていることを確認：
- [ ] CC0/MIT/CC4 全てが新スキーマで統一
- [ ] TAG_FORMATS テーブルに source_url/license/last_updated カラムが追加
- [ ] deepghs/site_tags の18サイトがCC4版に統合済み
- [ ] SiteTags_Adapter が実装・テスト済み

### Phase 7 開始時のタスク

1. **新ワークツリー作成**:
```bash
cd /workspaces
git worktree add LoRAIro-phase7-repo-automation feature/phase7-repository-automation
cd LoRAIro-phase7-repo-automation
uv sync --dev
uv run pytest local_packages/genai-tag-db-dataset-builder/tests/ -q
```

2. **BaseFetcher 実装開始**:
```bash
mkdir -p local_packages/genai-tag-db-dataset-builder/src/genai_tag_db_dataset_builder/fetcher
touch local_packages/genai-tag-db-dataset-builder/src/genai_tag_db_dataset_builder/fetcher/__init__.py
touch local_packages/genai-tag-db-dataset-builder/src/genai_tag_db_dataset_builder/fetcher/base.py
```

3. **データソース確認**:
- Base DB (NEXTAltair/genai-image-tag-db) の HuggingFace URL 確認
- TagDB_DataSource_CSV のリポジトリ URL 確認
- HuggingFace dataset IDs 確認

### /implement コマンド実行時の指示

```
Phase 7.0 から順次実装を開始してください。

優先度:
1. Phase 7.0: 環境構築（Day 1-2）
2. Phase 7.1: BaseFetcher と HF_BaseDB_Fetcher（Day 1-3）
3. Phase 7.2: TranslationCleaner 分離（Day 1-4）

各実装完了後、ユニットテストを追加し、全テストが PASS することを確認してください。
```

---

## 設計決定の記録

### 決定 D1: 完全分離アーキテクチャの採用

**決定**: Fetcher / Preprocessor / Builder を完全分離

**理由**:
- 責任分離が明確（Single Responsibility Principle）
- 長期的保守性の向上
- 新しいデータソース追加が容易

**トレードオフ**:
- 実装コストが高い（9週間）
- 既存コードの大規模リファクタリングが必要

**代替案**:
- アプローチ A（Builder 拡張）: 短期的には低コストだが長期的保守性に問題
- アプローチ C（マイクロサービス風）: 過剰設計のリスク

### 決定 D2: GitHub Actions による完全自動化

**決定**: `workflow_dispatch`（手動トリガー）のみで、取得→ビルド→検証→Artifacts までを自動化。HuggingFaceへのPushは手動とする。

**理由**:
- 失敗時の切り分けと後戻りが容易（まず「作れてるか」をCIで保証）
- データソース更新の頻度・タイミングが一定でない（スケジュール実行の価値が薄い）
- 事故防止（意図せず公開物を更新しない）

**トレードオフ**:
- 人が「更新が必要か」を判断してトリガーを押す運用が必要
- 自動公開の手間削減は後回しになる

---

## 追記: バージョニング戦略（現時点の推奨）

### 前提
- **スキーマ**は「手動で変更・移行（migrations）」でよい
- **データ**は「同一スキーマで、ソース更新に応じて作り直す」

### 推奨案（運用が単純で、後から拡張しやすい）
1. **Schema version**
   - SQLite内に `schema_version` を持ち、破壊的変更時のみインクリメント
   - 例: `schema_version = 1,2,3...`

2. **Data version（Build version）**
   - ビルド成果物に「日付（+必要ならリビジョン）」を持たせる
   - 例: `data_version = 2025-12-17` / `2025-12-17.1`

3. **ライセンス別リポジトリ命名**
   - CC0: `NEXTAltair/genai-image-tag-db`
   - MIT: `NEXTAltair/genai-image-tag-db-mit`
   - CC-BY-4.0: `NEXTAltair/genai-image-tag-db-cc4`（将来）

### 決定 D3: 設定ファイルベースの管理

**決定**: JSON 設定ファイルでデータソースとビルド設定を管理

**理由**:
- ハードコードされたパスの削除
- ライセンス別ビルドの柔軟な管理
- データソースバージョンの記録

**影響**:
- 設定ファイルスキーマの定義が必要
- バリデーション機構の実装が必要

### 決定 D5: 取得は「最新 + 取得したSHA/Revisionを記録」

**決定**: 取得は原則「最新」を取りに行き、ビルド成果物に **取得した commit SHA / HF revision（またはETag）を記録**する。

**理由**:
- 運用が軽い（更新のたびにshaを手で更新しなくてよい）
- 「いつ・何を取り込んだか」は記録で追える（再現性は“完全一致”ではなく“追跡可能”を優先）

**実装メモ**:
- GitHub repo/gist: 取得後に `git rev-parse HEAD` を記録
- HuggingFace: `huggingface_hub` の戻り値/metadataから revision を記録（取得物のETagでも可）

### 決定 D4: 新ワークツリーでの実装

**決定**: `feature/phase7-repository-automation` ブランチで新規実装

**理由**:
- 大規模リファクタリングのため、既存ブランチとの分離が必要
- 並行開発の可能性（Phase 5-6 の継続）
- レビュー・テストの独立性

**影響**:
- マージ時の競合リスク
- ドキュメント整備が重要

---

## 参照

- **前提フェーズ**:
  - `dataset_builder_design_plan_2025_12_13.md`: Phase 0-4 の設計
  - `dataset_builder_phase5_6_implementation_plan_2025_12_15.md`: Phase 5-6 の計画
  - `dataset_builder_dual_license_builds_implementation_2025_12_16.md`: ライセンス別ビルド
  - `dataset_builder_translation_cleanup_2025_12_17.md`: 翻訳クリーンアップ
  - `dataset_builder_source_effects_idempotent_upserts_2025_12_17.md`: 冪等UPSERT

- **関連ドキュメント**:
  - `CLAUDE.md`: LoRAIro 開発ガイドライン
  - `development_guidelines.md`: プロジェクト固有開発パターン
  - `.github/workflows/ci.yml`: 既存 CI/CD ワークフロー

---

**策定者**: Claude Sonnet 4.5
**策定日**: 2025年12月17日
