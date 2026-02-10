# conftest.py 詳細分析

**ファイル**: `/workspaces/LoRAIro/tests/conftest.py`
**行数**: 600+ 行（推定）
**スコープ**: すべてのテストに適用（モジュールレベルのパッチを含む）

---

## 🔧 フィクスチャ一覧（34個）

### Session スコープ（全テスト共通）- autouse=True

| フィクスチャ名 | 用途 | 依存関係 |
|---|---|---|
| `mock_genai_tag_db_tools` | genai-tag-db-tools モック管理 | なし |
| `configure_qt_for_tests` | Qt 環境設定（ヘッドレス対応） | なし |
| `qapp_args` | Qt引数設定 | なし |
| `qapp` | QApplication インスタンス | qapp_args |

### Session スコープ（オンデマンド）

| フィクスチャ名 | 用途 |
|---|---|
| `project_root` | プロジェクトルートパス |

### Function スコープ（各テスト毎に実行）

**Qt/GUI関連**:
- `qt_main_window_mock_config` - MainWindow モック設定

**ストレージ関連**:
- `temp_dir` - 一時ディレクトリ
- `storage_dir` - ストレージディレクトリ（temp_dir 依存）
- `fs_manager` - FileSystemManager インスタンス（storage_dir 依存）

**データベース関連**:
- `test_db_url` - テストDB URL（in-memory SQLite）
- `test_engine_with_schema` - SQLAlchemy エンジン + スキーマ作成
- `db_session_factory` - SessionLocal ファクトリ
- `test_session` - DB セッション
- `test_repository` - ImageRepository インスタンス
- `temp_db_repository` - クリーンアップ対応の Repository
- `test_db_manager` - ImageDatabaseManager インスタンス
- `mock_config_service` - ConfigService モック

**テスト画像関連**:
- `test_image_dir` - テスト画像ディレクトリ
- `test_image_path` - テスト画像パス
- `test_image` - PIL Image オブジェクト
- `test_image_array` - numpy 配列（画像）
- `test_image_paths` - 複数画像パスリスト
- `test_images` - 複数 PIL Image
- `test_image_arrays` - 複数 numpy 配列

**サンプルデータ関連**:
- `sample_image_data` - ImageDict サンプル
- `sample_processed_image_data` - ProcessedImageDict サンプル
- `sample_annotations` - AnnotationsDict サンプル

**タイムスタンプ関連**:
- `current_timestamp` - 現在時刻
- `past_timestamp` - 過去時刻

**タグDB関連**:
- `test_tag_db_path` - テストタグDB パス
- `test_tag_repository` - TagRepository
- `test_image_repository_with_tag_db` - タグDB対応 ImageRepository

**その他**:
- `critical_failure_hooks` - エラーハンドリングテスト用

---

## 📊 フィクスチャ依存関係ツリー

```
mock_genai_tag_db_tools (session, autouse)
│
├─── qapp_args (session)
│    └─── qapp (session)
│         └─── [GUI テスト利用]
│
├─── configure_qt_for_tests (session, autouse)
│    └─── [Qt 環境設定]
│
├─── temp_dir (function)
│    ├─── storage_dir (function)
│    │    └─── fs_manager (function)
│    │         └─── [ファイルシステムテスト]
│    │
│    └─── test_tag_db_path (function)
│         └─── test_tag_repository (function)
│              └─── [タグDB テスト]
│
├─── test_db_url (function)
│    └─── test_engine_with_schema (function)
│         ├─── db_session_factory (function)
│         │    └─── test_session (function)
│         │         ├─── test_repository (function)
│         │         │    └─── [DB操作テスト]
│         │         │
│         │         └─── temp_db_repository (function)
│         │              └─── [DB テスト（クリーンアップ付き）]
│         │
│         └─── test_db_manager (function)
│              └─── [DB マネージャテスト]
│
├─── qt_main_window_mock_config (function)
│    └─── [GUI MainWindow テスト]
│
├─── mock_config_service (function)
│    └─── [ConfigService テスト]
│
├─── test_image_dir (function)
│    ├─── test_image_path (function)
│    │    ├─── test_image (function)
│    │    └─── test_image_array (function)
│    │
│    ├─── test_image_paths (function)
│    ├─── test_images (function)
│    └─── test_image_arrays (function)
│         └─── [画像処理テスト]
│
├─── sample_image_data (function)
├─── sample_processed_image_data (function)
├─── sample_annotations (function)
│    └─── [データスキーマテスト]
│
├─── current_timestamp (function)
├─── past_timestamp (function)
│    └─── [タイムスタンプテスト]
│
└─── test_image_repository_with_tag_db (function)
     └─── [統合テスト: タグDB × 画像リポジトリ]
```

---

## 🚨 フィクスチャ設計の問題点

### 1. **フィクスチャ数が多すぎる（34個）**
- **機能が混在**:
  - Qt (qapp) + DB (test_engine) + ストレージ (fs_manager) が同じ conftest に混在
  - 各テストカテゴリで必要なフィクスチャが異なるのに、全て1つの conftest に定義

### 2. **責務が明確でない**
- `mock_genai_tag_db_tools`: 外部依存モック
- `qapp_args`: Qt設定
- `temp_dir`: ストレージ管理
- `test_engine_with_schema`: DB初期化
- ...これらが全て同じレベルで定義されている

### 3. **Session-scope のモック戻しが不確実**
- `_runtime_patches` が モジュールレベルで開始
- 終了時の patch.stop() が正しく実行されるか不確実
- 複数テスト実行時の状態汚染リスク

### 4. **自動使用フィクスチャが多い（autouse=True）**
- `mock_genai_tag_db_tools`: 全テストに強制
- `configure_qt_for_tests`: 全テストに強制
- ⇒ 不要なテストでも実行される（性能低下）

### 5. **テストカテゴリ別の最適化なし**
- DB テスト: `test_engine_with_schema` が必要
- GUI テスト: `qapp` が必要
- ユニットテスト: ほぼ不要
- ⇒ 全テストが全フィクスチャを初期化している（無駄）

---

## ✅ Session-scope フィクスチャの活用状況

### 実際に使用されているもの
- `qapp` - GUI テストのみ
- `mock_genai_tag_db_tools` - 全テスト
- `configure_qt_for_tests` - 全テスト

### 使用効率
- **高**: genai_tag_db_tools モック（全テストで共通）
- **中**: Qt 設定（Linux ヘッドレス用）
- **低**: qapp（GUI テストのみ使用、他の 90% のテストでは不要）

---

## 📋 改善の必要な点

### Multi-layer conftest.py 実装のポイント

1. **tests/conftest.py（ルート）- 最小限のフィクスチャ**
   - `mock_genai_tag_db_tools` - 必須（全テスト）
   - `configure_qt_for_tests` - 必須（Linux ヘッドレス対応）
   - `project_root` - 共通

2. **tests/integration/conftest.py - DB + ストレージ**
   - `test_db_url` / `test_engine_with_schema`
   - `db_session_factory` / `test_session`
   - `test_repository` / `test_db_manager`
   - `fs_manager` / `storage_dir`

3. **tests/gui/conftest.py - Qt フィクスチャ**
   - `qapp` / `qapp_args`
   - `qt_main_window_mock_config`

4. **tests/bdd/conftest.py - BDD 専用**
   - ステップコンテキスト
   - テストデータセットアップ

---

## 🎯 推奨アクション（Agent 2 へ）

1. フィクスチャを 4つの conftest.py に分割
2. 各層の autouse を見直し（必要最小限に）
3. フィクスチャ間の依存関係を最適化
4. パフォーマンス測定（分割前後の実行時間比較）
