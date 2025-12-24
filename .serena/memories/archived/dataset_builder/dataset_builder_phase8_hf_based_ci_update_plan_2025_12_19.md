# Phase 8: HFベース差分追記 + CI更新ワークフロー（更新版 v2.0）

**最終更新**: 2025-12-20
**ステータス**: 実装完了・運用開始（CI/Publish動作確認済み）

## エグゼクティブサマリ

**Phase 8の本質**: 既存のbuilder.pyが持つ強力な差分追記機能を活用し、「ローカルCSV前提」から「HFベースDB + 外部ソース自動取得」へ移行するための**薄いオーケストレーションレイヤ**を追加する。

**実装状況**: コアロジックの80%は既に実装済み。必要なのは以下の3つのみ:
1. 外部ソースの定義・取得・リビジョン記録（sources.yml + fetcher）
2. ビルド統合スクリプト（builder_ci/orchestrator）
3. GitHub Actions ワークフロー（自動化）

## 1. 目的と戦略

### 1.1 目的
- **ローカルパス依存の排除**: CI環境で再現可能なビルドプロセスの実現
- **HFベースDB活用**: 既存のCC0データセットをベースに差分追記し、同run内でMIT/CC4はCC0成果物をbaseとして派生
- **外部ソース統合**: GitHub/HF datasets/gist等からの更新データを自動取得・統合
- **リビジョン追跡**: ビルド入力のcommit hash/revisionを完全に記録
- **自動検証**: db_health チェックによる品質保証

### 1.2 基本戦略（ライセンス別差分追記）

```
CC0更新: NEXTAltair/genai-image-tag-db (最新) → CC0ソースのみ追記 → CC0新版
MIT更新: CC0新版（同runで生成） → MITソースのみ追記 → MIT新版
CC4更新: CC0新版（同runで生成） → CC4ソースのみ追記 → CC4新版
```

**重要**:
- 初回作成は別手順で完了済みとし、Phase 8では「差分追記更新」のみを扱う。
- MIT/CC4はCC0ソースを再適用しない（CC0更新の成果物をベースに差分のみ）。
- CC0更新が無い場合はMIT/CC4は差分のみで更新する。

## 2. 実装状況サマリ

### 2.1 実装済み（活用する機能）✅

| 機能 | ファイル | 説明 |
|------|---------|------|
| **差分追記ビルド** | `builder.py:build_dataset()` (1860-3015行) | `base_db_path`でPhase 0/1スキップ、既存DBに追記 |
| **ソースフィルタ** | `builder.py:_load_source_filters()` (293-341行) | ワイルドカード対応のinclude/exclude |
| **HF翻訳取得** | `hf_translation_adapter.py:P1atdevDanbooruJaTagPairAdapter` | HF datasetsから直接翻訳データ取得 |
| **ライセンス別ビルド** | `build_dual_license.py` | CC0/MIT並列ビルド、フィルタ統合 |
| **健全性検証** | `report_db_health.py:run_health_checks()` | FK違反、orphan、統計サマリ |
| **Parquet出力** | `builder.py:_export_danbooru_parquet()` | Viewer用エクスポート |
| **HFアップロード** | `upload.py:upload_to_huggingface()` | huggingface_hubでのpush実装 |
| **Site Tags統合** | `adapters/site_tags_adapter.py` | 18サイトのSQLite統合（Phase 2.5完了）|

### 2.2 未実装（Phase 8で追加する機能）❌

| 機能 | 優先度 | 概要 |
|------|--------|------|
| **sources.yml** | 高 | 外部ソース定義（repo URL、license、paths_include） |
| **fetcher** | 高 | git clone / snapshot_download wrapper + manifest生成 |
| **orchestrator** | 高 | builder_ci/main.py（fetch → build → verify → publish統合） |
| **GitHub Actions** | 中 | .github/workflows/update-tag-dataset.yml |
| **HF base DB取得** | 中 | snapshot_downloadでbase DBを自動取得 |

## 3. 設計詳細

### 3.1 sources.yml フォーマット

**配置場所**: `local_packages/genai-tag-db-dataset-builder/builder_ci/sources.yml`

**フォーマット例**:
```yaml
sources:
  # CC0ソース
  - id: p1atdev-danbooru-ja-tag-pair
    kind: hf_dataset
    repo_id: p1atdev/danbooru-ja-tag-pair-20241015
    license: cc0-1.0
    applies_to: [cc0]  # CC0のみ（MIT/CC4へは再適用しない）
    data_type: translation_ja
    paths_include:
      - "data/train-*.parquet"
    hf_config:
      use_datasets_api: true  # datasets.load_dataset()で取得
      
  # MITソース
  - id: booru-japanese-tag
    kind: github
    url: https://github.com/boorutan/booru-japanese-tag
    license: mit
    applies_to: [mit]  # MIT版のみ
    data_type: translation_ja
    paths_include:
      - "danbooru-machine-jp.csv"
    revision_tracking: commit_hash
    
  # CC-BY-4.0ソース
  - id: deepghs-site-tags
    kind: hf_dataset
    repo_id: deepghs/site_tags
    url: https://huggingface.co/datasets/deepghs/site_tags
    license: cc-by-4.0
    applies_to: [cc4]
    data_type: site_tags_sqlite
    paths_include:
      - "*/tags.sqlite"  # 各サイトのSQLite
    revision_tracking: hf_revision
    
  # zh-CN翻訳（LICENSE要確認）
  - id: tag-autocomplete-zh
    kind: github
    url: https://github.com/sgmklp/tag-for-autocompletion-with-translation
    license: unspecified  # 要確認
    applies_to: [cc0]
    data_type: translation_zh_cn
    paths_include:
      - "Tags-zh-full.csv"
    enabled: false  # LICENSE確認後にtrue
```

**設計ポイント**:
- **id**: 一意識別子（ディレクトリ名、manifest記録用）
- **kind**: `github` / `hf_dataset` / `gist`
- **license**: ソースのライセンス（ビルド判定用）
- **applies_to**: どのビルド（cc0/mit/cc4）で使用可能か
- **data_type**: builder.pyへの入力種別（translation_ja, site_tags_sqlite, etc.）
- **paths_include**: 取得後に使用するファイルのglob（意図しないファイル拾い防止）
- **revision_tracking**: `commit_hash` / `hf_revision`

### 3.2 Fetcher実装

**配置場所**: `local_packages/genai-tag-db-dataset-builder/builder_ci/fetcher.py`

**責務**:
1. sources.ymlを読み込み
2. 各ソースを `external_sources/<id>/` に取得（git clone / snapshot_download）
3. commit hash / HF revisionを記録
4. build_manifest.jsonに記録

**実装方針**:
```python
from huggingface_hub import snapshot_download
import subprocess
from pathlib import Path
import json
from datetime import datetime, timezone

def fetch_github_repo(source: dict, dest: Path) -> dict:
    """git cloneしてcommit hashを記録"""
    url = source["url"]
    subprocess.run(["git", "clone", url, str(dest)], check=True)
    
    # commit hash取得
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True
    )
    commit_hash = result.stdout.strip()
    
    return {
        "id": source["id"],
        "kind": "github",
        "url": url,
        "commit_hash": commit_hash,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

def fetch_hf_dataset(source: dict, dest: Path) -> dict:
    """snapshot_downloadでHF datasetを取得"""
    repo_id = source["repo_id"]
    
    # HF datasets APIで取得する場合はスキップ（builder.pyが直接取得）
    if source.get("hf_config", {}).get("use_datasets_api"):
        return {
            "id": source["id"],
            "kind": "hf_dataset",
            "repo_id": repo_id,
            "fetch_method": "datasets_api",
            "note": "Fetched directly by builder.py via datasets.load_dataset()"
        }
    
    # snapshot_downloadで取得（SQLite等のバイナリファイル用）
    revision = snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=dest,
        allow_patterns=source.get("paths_include", ["*"]),
    )
    
    return {
        "id": source["id"],
        "kind": "hf_dataset",
        "repo_id": repo_id,
        "revision": revision,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
```

**Cache戦略**:
- GitHub Actions cacheで `external_sources/` をキャッシュ
- revisionが変わってない場合はスキップ（`--force`オプションで強制実行）

#### 3.2.1 Phase 8.1 実装の修正点（必須）

- HF（snapshot_download）のrevision記録/更新: `snapshot_download()` は「取得したrevision」を返さない（基本はローカルパス）。毎回 `HfApi().dataset_info(...).sha` でコミットSHAを解決し、そのSHAを `snapshot_download(..., revision=sha)` に渡して取得する。destが既にある場合も、SHAが変わっていたら再取得する（例: dest内に`.hf_sha`を保存して比較 / もしくは常にsnapshot_downloadしてキャッシュに任せる）。
- GitHub（cacheあり）の更新: destが存在する場合、cloneをスキップせず `git fetch --prune --tags` → `git reset --hard origin/HEAD`（必要なら `git clean -fdx`）で最新版に追従し、commit hashを再記録する。
- use_datasets_api=true のHFソース: ダウンロードはスキップでも、`HfApi().dataset_info(...).sha` をmanifestに記録する。さらに再現性のため、adapter側で **必ず** `datasets.load_dataset(..., revision=sha)` を使う（shaを渡せない設計ならPhase 8.2で引数/環境変数/設定ファイルで注入できるようにする）。
- テスト/一時出力: `test_output/` はCI/リポジトリには不要なので `.gitignore` に入れる（または生成しない）。

### 3.3 Orchestrator実装

**配置場所**: `local_packages/genai-tag-db-dataset-builder/builder_ci/main.py`

**フェーズ構成**:
```python
def orchestrate_build(
    target: str,  # "cc0" / "mit" / "cc4" / "all"
    base_hf_repos: dict[str, str],  # {"cc0": "NEXTAltair/genai-image-tag-db", ...}
    sources_yml: Path,
    work_dir: Path,
    force: bool = False,
) -> None:
    """
    Phase A: Fetch
      - HF base DBをダウンロード（snapshot_download）
      - sources.ymlに基づき外部ソースを取得
      - build_manifest.jsonに記録
      
    Phase B: Build
      - target別にinclude filterを生成（license判定）
      - builder.build_dataset()を呼び出し
        - base_db_path: ダウンロードしたHF DB
        - include_sources_path: 生成したfilter
        - hf_ja_translation_datasets: sources.ymlから抽出
        - parquet_output_dir: 指定
      
    Phase C: Verify
      - report_db_health.run_health_checks()
      - 失敗条件でexit 1（CIゲート）
      
    Phase D: Publish (optional)
      - upload.upload_to_huggingface()
      - または artifact出力
    """
    pass
```

**include filter生成ロジック**:
CIではローカルCSV（TagDB_DataSource_CSV）を使わず、`external_sources/` の成果物のみを対象にする。
```python
def generate_include_filter(target: str, sources: list[dict], work_dir: Path) -> Path:
    """targetに応じたinclude filterを生成"""
    filter_lines = []

    # targetに応じた外部ソース
    for src in sources:
        if target not in src["applies_to"]:
            continue
        if not src.get("enabled", True):
            continue
        if src.get("hf_config", {}).get("use_datasets_api"):
            # builder.py側でdatasets APIから直接取得するため除外
            continue
        
        # paths_includeをfilterに追加
        for pattern in src["paths_include"]:
            filter_lines.append(f"external_sources/{src['id']}/{pattern}")
    
    filter_path = work_dir / f"include_{target}_sources.generated.txt"
    filter_path.write_text("\n".join(filter_lines), encoding="utf-8")
    return filter_path
```

### 3.4 GitHub Actions Workflow

**配置場所**: `.github/workflows/update-tag-dataset.yml`

**トリガー**: `workflow_dispatch`（手動実行）

**入力パラメータ**:
- `target`: `cc0` / `mit` / `cc4` / `all`（`mit`/`cc4`/`all` は内部的に先に `cc0` を更新し、その成果物を base として使う）
- `publish`: `true` / `false`（HFへ自動push or artifact出力）
- `force`: `true` / `false`（リビジョン差分無しでも実行）

**環境変数（Secrets）**:
- `HF_TOKEN`: HuggingFace APIトークン

**ジョブ構成**:
```yaml
name: Update Tag Dataset

on:
  workflow_dispatch:
    inputs:
      target:
        description: 'Build target'
        required: true
        type: choice
        options:
          - cc0
          - mit
          - cc4
          - all
        default: 'cc0'
      publish:
        description: 'Publish to HuggingFace'
        required: true
        type: boolean
        default: false
      force:
        description: 'Force rebuild (ignore revision check)'
        required: true
        type: boolean
        default: false

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 360  # 6時間（大規模ビルド想定）
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          submodules: recursive
          
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          
      - name: Install uv
        uses: astral-sh/setup-uv@v1
        
      - name: Cache HuggingFace datasets
        uses: actions/cache@v4
        with:
          path: ~/.cache/huggingface
          key: hf-cache-${{ runner.os }}-${{ hashFiles('**/sources.yml') }}
          restore-keys: hf-cache-${{ runner.os }}-
          
      - name: Cache external sources
        uses: actions/cache@v4
        with:
          path: external_sources
          key: external-sources-${{ runner.os }}-${{ hashFiles('**/sources.yml') }}
          restore-keys: external-sources-${{ runner.os }}-
          
      - name: Install dependencies
        working-directory: local_packages/genai-tag-db-dataset-builder
        run: |
          uv sync --dev
          
      - name: Run orchestrator
        working-directory: local_packages/genai-tag-db-dataset-builder
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          uv run python -m builder_ci.main \
            --target ${{ inputs.target }} \
            --publish ${{ inputs.publish }} \
            --force ${{ inputs.force }}
            
      - name: Upload artifacts (if not published)
        if: ${{ !inputs.publish }}
        uses: actions/upload-artifact@v4
        with:
          name: tag-dataset-${{ inputs.target }}
          path: |
            local_packages/genai-tag-db-dataset-builder/out_db_${{ inputs.target }}/*.sqlite
            local_packages/genai-tag-db-dataset-builder/out_db_${{ inputs.target }}/parquet/
            local_packages/genai-tag-db-dataset-builder/out_db_${{ inputs.target }}/report/
            local_packages/genai-tag-db-dataset-builder/out_db_${{ inputs.target }}/build_manifest.json
          retention-days: 30
```

### 3.5 HF Base DB自動取得

**実装方針**:
```python
from huggingface_hub import snapshot_download

def download_base_db(repo_id: str, dest_dir: Path) -> Path:
    """HFからbase DBをダウンロード"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # 最新のsqliteファイルを取得
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        local_dir=dest_dir,
        allow_patterns=["*.sqlite"],
    )
    
    # ダウンロードされたsqliteファイルを検索
    sqlite_files = list(dest_dir.glob("**/*.sqlite"))
    if not sqlite_files:
        raise FileNotFoundError(f"No sqlite file found in {repo_id}")
    
    # 最新のファイルを返す（タイムスタンプでソート）
    return max(sqlite_files, key=lambda p: p.stat().st_mtime)
```

### 3.6 build_manifest.json生成

**フォーマット**:
```json
{
  "build_info": {
    "version": "v4.2.0",
    "target": "cc0",
    "built_at": "2025-12-19T12:34:56+00:00",
    "builder_version": "0.1.0",
    "base_db": {
      "repo_id": "NEXTAltair/genai-image-tag-db",
      "revision": "abc123def456",
      "downloaded_at": "2025-12-19T12:00:00+00:00"
    }
  },
  "sources": [
    {
      "id": "p1atdev-danbooru-ja-tag-pair",
      "kind": "hf_dataset",
      "repo_id": "p1atdev/danbooru-ja-tag-pair-20241015",
      "revision": "846b9a5",
      "fetched_at": "2025-12-19T12:10:00+00:00",
      "files_used": ["data/train-00000-of-00001.parquet"]
    },
    {
      "id": "booru-japanese-tag",
      "kind": "github",
      "url": "https://github.com/boorutan/booru-japanese-tag",
      "commit_hash": "035c0d63cbf70f6a3d8da4fbef31a122b48a9814",
      "fetched_at": "2025-12-19T12:15:00+00:00",
      "files_used": ["danbooru-machine-jp.csv"]
    }
  ],
  "statistics": {
    "total_sources": 2,
    "total_tags": 1234567,
    "total_translations": 234567
  },
  "health_checks": {
    "foreign_key_violations": 0,
    "orphan_tag_status": 0,
    "orphan_usage_counts": 0,
    "orphan_translations": 0,
    "duplicate_tags": 5,
    "status": "PASSED"
  }
}
```

## 4. 外部ソース取り込み戦略（統合版）

### 4.1 取り込むソース（確定）

| ID | License | 用途 | 取り込み方式 | paths_include |
|----|---------|------|-------------|---------------|
| **p1atdev-danbooru-ja-tag-pair** | CC0-1.0 | 日本語翻訳（CC0のみ） | `datasets.load_dataset()` | `data/train-*.parquet` |
| **booru-japanese-tag** | MIT | 日本語翻訳（MIT版） | git clone | `danbooru-machine-jp.csv` |
| **deepghs-site-tags** | CC-BY-4.0 | Site tags統合 | git clone | `*/tags.sqlite` |

### 4.2 取り込むソース（要確認）

| ID | License | 用途 | 取り込み方式 | 確認事項 |
|----|---------|------|-------------|----------|
| **tag-autocomplete-zh** | 要確認 | zh-CN翻訳（CC0のみ） | git clone | LICENSE確認後に`enabled: true` |

### 4.3 取り込まないソース（確定）

| ID | 理由 |
|----|------|
| **danbooru2023-metadata-database** | `popularity`=0で使用不可（`MAX(popularity)=0`を確認済み）、type補完のみ検討余地 |
| **e621-rising-v3-curated** | 学習データセット内集計であり、ホスティングサイト由来のusage countではない |
| **Z3D-E621-Convnext** | license: other（曖昧）、モデル重み主体でタグDBソースとして不適 |

### 4.4 paths_include設計原則

**事故防止のためのホワイトリスト方式**:
- リポジトリ全体を拾わず、必要な成果物のみ明示的に指定
- ワイルドカード使用時は慎重にテスト（初期は最小限）

**例**:
```yaml
# ✅ 良い例（成果物単位）
paths_include: ["danbooru-machine-jp.csv"]

# ⚠️ 注意が必要（ツール/画像も含む可能性）
paths_include: ["*.csv"]

# ❌ 避ける（repo全体）
paths_include: ["**/*"]
```

### 4.5 日時データの扱い

**原則**:
- **ソース日時優先**: データソース側に日時が含まれる場合、それを優先してDB側を更新
- **base DB値維持**: ソース側日時が取れない場合、base DBの値を維持（ビルド時刻で上書きしない）

**対象テーブル**:
- `TAG_USAGE_COUNTS.created_at/updated_at`: count値の観測日時（ソース日時）。ただしソース側日時が取れない場合は **`count` 変化時のみ** ビルド時刻を `updated_at` に入れる（`count` 不変なら日付は維持）
- `TAG_STATUS.source_created_at`: ホスティングサイト側での観測日時
- `TAG_STATUS.deprecated_at`: 取れない場合NULL許容

**実装上の注意**:
- ソース側に日時カラムがある場合、builder.py側で優先的に使用
- ソース側に日時がない場合、`INSERT OR IGNORE`で既存値を維持（`updated_at`を現在時刻で上書きしない）

## 5. 実装順序（段階的アプローチ）

### Phase 8.1: 基盤構築（1-2日）
1. `builder_ci/` ディレクトリ作成
2. `sources.yml` 初期版作成（軽量ソースのみ: p1atdev, booru-japanese-tag）
3. `fetcher.py` 実装（GitHub + HF dataset対応）
4. `build_manifest.json` 生成機能実装

**検証**: ローカルでfetch → manifest記録が正しいか確認

### Phase 8.2: Orchestrator実装（2-3日）
1. `main.py` 実装
   - HF base DB取得
   - include filter生成
   - builder.build_dataset()呼び出し
   - db_health検証
2. MIT版ビルドで動作確認（最も軽量）

**検証**: ローカルでMIT版の差分追記ビルド成功

### Phase 8.3: CI統合（1-2日）
1. `.github/workflows/update-tag-dataset.yml` 作成
2. GitHub Secrets設定（HF_TOKEN）
3. workflow_dispatch実行テスト（publish=false、artifact出力）

**検証**: CI上でMIT版ビルド → artifact取得

### Phase 8.4: 全ビルド対応（2-3日）
1. CC0/CC4を追加
2. `target=all` 対応
3. deepghs/site_tags統合（CC4）

**検証**: 全ライセンス版のビルド成功

### Phase 8.5: Publish機能（1日）
1. orchestratorにupload.py統合
2. publish=true でHF自動push

**検証**: HFへの自動アップロード成功

### Phase 8.6: 最適化（1-2日）
1. Cache戦略の調整
2. リビジョン差分チェック（force=falseで差分なしスキップ）
3. エラーハンドリング強化

## 6. テスト戦略

### 6.1 単体テスト
- `fetcher.py`: mock git/HF APIでfetch正常性
- `main.py`: 各フェーズの独立実行
- include filter生成ロジック

### 6.2 統合テスト
- ローカルでの完全ビルド（MIT版）
- db_health検証の失敗条件確認
- manifest生成の正確性

### 6.3 CI/CDテスト
- GitHub Actions dry-run
- cache動作確認
- artifact出力検証

## 7. リスクと対策

### 7.1 リスク

| リスク | 影響度 | 対策 |
|--------|--------|------|
| **意図しないファイル拾い** | 高 | paths_includeを狭く設定、初期は最小限 |
| **巨大repo取得（site_tags）** | 中 | cache活用、差分同期は後回し |
| **HF dataset revision変更頻度** | 低 | 常に最新取得＋revision記録でOK |
| **CI実行時間超過** | 中 | timeout-minutes: 360（6時間）設定 |
| **ディスク容量不足** | 中 | external_sourcesのcleanup、cache戦略 |

### 7.2 対策詳細

**paths_include事故防止**:
- 初期はホワイトリスト方式（明示的に列挙）
- ワイルドカード使用時は慎重にテスト

**巨大repo対策**:
- deepghs/site_tags: 差分同期はPhase 8.xで対応（初期はfull clone）
- cacheキー設計: `sources.yml`のhashでinvalidation

**リビジョン追跡**:
- build_manifest.jsonで完全記録
- 差分チェックは別PRで追加（force=trueで回避可能）

## 8. 次ステップ（implementフェーズへの引き継ぎ）

### 8.1 即座に実装可能な機能
- fetcher.py（GitHub + HF dataset fetch）
- sources.yml初期版（軽量ソースのみ）
- build_manifest.json生成

### 8.2 既存機能の活用
- `builder.build_dataset()`は変更不要
- `build_dual_license.py`はMIT版で参考
- `report_db_health.py`はCI gateで直接使用

### 8.3 実装時の注意点
- **日時データ**: ソース日時優先、base DB値維持（`TAG_USAGE_COUNTS` は `count` 変化時のみ `updated_at` を更新。`count` 不変なら日付は維持。ソース側日時が取れない場合はビルド時刻を `updated_at` に入れる）
- **License判定**: sources.ymlのlicense + applies_toで厳密に制御
- **HF datasets API**: `use_datasets_api: true`の場合、builder.pyが直接取得（fetch不要）

### 8.4 未解決の検討事項
- **tag-autocomplete-zh**: LICENSE確認後に`enabled: true`
- **danbooru2023-metadata-database**: type補完の必要性判断
- **差分同期最適化**: Phase 9以降で対応

### 8.5 成功基準

1. CI上でCC0/MIT/CC4の差分追記ビルドが成功
2. build_manifest.jsonに全ソースのrevision記録
3. db_health検証でforeign_key_violations=0
4. HFへの自動アップロード成功（成果物・README・report）

---

## 完了メモ（2025-12-20）

- CIワークフロー: publish前提で運用開始
- CC0/MIT/CC4: HFアップロード確認済み
- site_tags: CIでの取り込み動作確認済み（source_effectsに反映）
- TagDB_DataSource_CSV未配置警告: CI向けに抑制済み
