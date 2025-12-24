# Plan: genai-tag-db-tools リファクタ計画（改訂版）

**Created**: 2025-12-21 15:05:00
**Source**: manual_sync
**Original File**: ethereal-painting-orbit.md
**Status**: planning

---

## 前提
- worktree: `C:\\LoRAIro\\worktrees\\genai-tag-db-tools-refactor`
- branch: `refactor/db-tools-hf`
- 既存計画の7つの問題点を解決する

## 現在の実装状況

### 実装済み
- ディレクトリ構造変更（`data/` → `db/`）
- HFダウンロード機能（`io/hf_downloader.py`）
- DBランタイム管理（`db/runtime.py`）
- Repository API拡張（deprecated, source_created_at, observed_atフィールド）
- サービス層骨格（`services/app_services.py`, `tag_search.py`, `tag_register.py`, `tag_statistics.py`）

### 未実装
- 統合ビュー機能
- ユーザーDB統合
- HFダウンロード例外処理詳細
- 移行ロジック
- キャッシュ管理
- テスト整備（現在3ファイルのみ）

### エンコーディング問題
- `services/app_services.py` が文字化け（Shift-JIS/CP932）
- `db/db_maintenance_tool.py` も文字化けの可能性

## 改訂内容（7項目の解決方針）

### 1. 統合ビュー実装の明確化

**実装方法:** 物理的な統合DBは作成せず、**複数DBを順次検索する仮想統合**を実装

**詳細:**
- `db/repository.py` に `MultiDBRepository` クラスを追加
- 優先順位: CC4 > MIT > CC0 > ユーザーDB
- 検索時は優先順位の高いDBから順に検索し、最初に見つかったものを返す
- 返り値に `source_db: str` フィールドを追加（どのDBから取得したか）
- `source_db` はデバッグ用途のみで表示は任意
- デデュープキー: `tag` 文字列（tag_id は使用しない）

**代替案（Phase 2で検討）:**
- 期間限定で「結合済みキャッシュDB」を生成（再生成可能）
- 初回は仮想統合で実装し、パフォーマンス問題があれば物理統合に移行

**修正対象ファイル:**
- `src/genai_tag_db_tools/db/repository.py`
- `src/genai_tag_db_tools/db/runtime.py`（複数DB管理）

### 2. HFダウンロード例外処理の実装

**方針:**
- 失敗時は「前回キャッシュにフォールバック」
- 初回ダウンロード失敗は「明示エラー（ユーザーに通知）」
- 途中失敗は「一時ファイル破棄 → 前回キャッシュに戻す」
- SHA不一致時は「再ダウンロード」
- ネットワークエラーは「リトライ3回 → フォールバック」

**詳細実装:**
```python
# io/hf_downloader.py に追加
def download_with_fallback(spec: HFDatasetSpec, dest_dir: Path, token: str | None = None) -> Path:
    cache_manifest = dest_dir / "manifest.json"
    previous_cache = _load_previous_cache(cache_manifest)

    try:
        downloaded = download_hf_dataset_file(spec, dest_dir=dest_dir, token=token)
        _save_manifest(cache_manifest, spec, downloaded)
        return downloaded
    except Exception as e:
        if previous_cache:
            logger.warning(f"ダウンロード失敗、前回キャッシュを使用: {e}")
            return previous_cache
        else:
            raise RuntimeError(f"初回ダウンロード失敗: {e}")
```

**修正対象ファイル:**
- `src/genai_tag_db_tools/io/hf_downloader.py`

### 3. テスト戦略の具体化

**テスト構成:**
```
tests/
├── unit/
│   ├── test_hf_downloader.py       # HFダウンロード機能
│   ├── test_multi_db_repository.py # 統合ビュー
│   ├── test_tag_register.py        # 登録機能
│   └── test_migration.py           # 移行ロジック
├── integration/
│   ├── test_download_init_search.py # 初回DL→起動→検索→登録
│   └── test_cache_fallback.py       # キャッシュフォールバック
└── gui/
    └── test_app_services_signals.py # 最低限の起動/シグナル
```

**モック戦略:**
- Unit: HFダウンロードは `hf_hub_download` をモック
- Integration: ローカルに小規模テストDBを配置
- GUI: `QSignalSpy` を使用してシグナル発火を検証

**カバレッジ目標:** 75%以上

**修正対象:**
- `tests/` ディレクトリ全体を再構築

### 4. ユーザーDB初期化の実装

**方針:**
- ユーザーDBは初回起動時に自動生成（空の状態）
- 移行ロジックは不要
- スキーマは HF配布DBと同一（`schema.py` のDDLをそのまま使用）

**実装:**
```python
# db/runtime.py に追加
def init_user_db(cache_dir: Path) -> Path:
    """ユーザーDBを初期化（存在しなければ作成）"""
    user_db_path = cache_dir / "user_db" / "user_tags.sqlite"
    if not user_db_path.exists():
        user_db_path.parent.mkdir(parents=True, exist_ok=True)
        # HF配布DBと同じスキーマでテーブル作成
        create_tables(user_db_path)
    return user_db_path
```

**修正対象ファイル:**
- `src/genai_tag_db_tools/db/runtime.py`
- `src/genai_tag_db_tools/db/schema.py`（テーブル作成関数）

### 5. キャッシュ管理の明確化

**キャッシュ構成:**
```
cache_dir/
├── base_dbs/
│   ├── cc4.sqlite
│   ├── mit.sqlite
│   └── cc0.sqlite
├── user_db/
│   └── user_tags.sqlite
└── metadata/
    ├── manifest_cc4.json
    ├── manifest_mit.json
    └── manifest_cc0.json
```

**対象repo/filenameは明記する**（CC0/MIT/CC4それぞれのrepo_idとfilenameを列挙する）

- CC4: repo_id=`NEXTAltair/genai-image-tag-db-CC4`, filename=`genai-image-tag-db-cc4.sqlite`
- MIT: repo_id=`NEXTAltair/genai-image-tag-db-mit`, filename=`genai-image-tag-db-mit.sqlite`
- CC0: repo_id=`NEXTAltair/genai-image-tag-db`, filename=`genai-image-tag-db-cc0.sqlite`
- デフォルトキャッシュは GUI側のフォールバック用途のみ

**API設計:**
```python
# services/app_services.py
def ensure_db_ready(repo_id: str, filename: str, cache_dir: Path, token: str | None = None) -> Path:
    """HF DBをダウンロード・初期化して使用可能にする"""
    spec = HFDatasetSpec(repo_id=repo_id, filename=filename)
    db_path = download_with_fallback(spec, dest_dir=cache_dir / "base_dbs", token=token)
    init_engine(db_path)
    return db_path
```

**修正対象ファイル:**
- `src/genai_tag_db_tools/services/app_services.py`
- `src/genai_tag_db_tools/io/hf_downloader.py`

## 実装順序（優先度順）

### Phase 1: 緊急修正
1. エンコーディング修正（`app_services.py`, `db_maintenance_tool.py`）

### Phase 2: コア機能
2. 保存先の統一（`cache_dir` 必須化）
3. HFダウンロード例外処理（フォールバック機能）
4. キャッシュ管理（manifest, 複数DB初期化）

### Phase 3: 統合機能
5. 統合ビュー実装（`MultiDBRepository`）
6. ユーザーDB統合（スキーマ定義、登録機能）

### Phase 4: GUI/CLI接続
7. `app_services.py` の `ensure_db_ready` 実装
8. GUI/CLI から `ensure_db_ready` を呼び出す

### Phase 5: テスト
9. Unit テスト実装
10. Integration テスト実装
11. GUI テスト実装

## クリティカルパス

1. エンコーディング修正（即時）
2. 保存先統一 → HF例外処理 → キャッシュ管理
3. 統合ビュー → ユーザーDB初期化
4. テスト整備

## 重要な制約

- エンコーディング修正は最優先（他の作業をブロック）
- 統合ビューは「仮想統合」から開始（物理統合は保留）
- ユーザーDBは空の状態から開始（移行は不要）
- API互換性は「旧API削除判定条件」（既存計画 6.1）を満たすまで保持

## 未決事項（実装中に決定）

- 統合ビューのパフォーマンスが問題になった場合の物理統合移行タイミング
- 診断CLIのチェック項目最終確定
