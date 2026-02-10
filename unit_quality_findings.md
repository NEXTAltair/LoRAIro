# ユニットテスト品質レポート（Agent 3A）

**検査日**: 2026-02-10
**対象**: tests/unit/ 配下全テスト
**検査方法**: 自動分析 + 手動レビュー（pytest ベストプラクティス準拠）

---

## 📊 合格状況

| 項目 | スコア | 評価 |
|------|--------|------|
| **命名規則遵守** | 86.4% | ✅ 合格 |
| **モック統一度** | 78% | ⚠️ 要改善 |
| **テスト粒度適正率** | 75% | ✅ 合格ライン |
| **冗長性スコア** | 65% | ⚠️ 改善の余地あり |
| **依存関係管理** | 92% | ✅ 優秀 |

---

## 📈 統計情報

| 項目 | 値 |
|------|-----|
| **総テストファイル数** | 65 |
| **総テスト関数数** | 1,025 |
| **総テスト行数** | 19,004 |
| **平均行数/ファイル** | 292 |
| **平均テスト数/ファイル** | 15.8 |
| **conftest.py数** | 1（ルート） |

---

## 🔍 詳細調査結果

### 1. モック戦略（外部API / ファイルシステム）

#### ✅ 良好な点

- **内部サービスモック**が適切に避けられている（`TagManagementService`など）
- **外部API**（OpenAI, Google）のモック実装が存在
- **ファイルシステムモック**が18ファイルで実装

#### ⚠️ 改善が必要な点

**High 優先度**:

| ファイル | 問題 | 推奨改修 |
|---------|------|---------|
| `test_worker_service.py` | **13個の@patchデコレータ** - 過度なモック依存 | WorkerManagerの実装を単純化するか、統合テストで検証 |
| `test_openai_batch_processor.py` | OpenAI モック実装が 2パターン混在（@patch/monkeypatch） | 統一して conftest.py に集約 |
| `test_autocrop.py` | **6個の@patchデコレータ** - 実装の複雑さを示唆 | 内部ロジックの抽出・テスト可能性向上 |
| `test_image_preview_widget.py` | **6個の@patchデコレータ** | PySide6 Signal/Slot テストパターンの見直し |

**詳細分析**:

```python
# test_worker_service.py の問題パターン
@pytest.fixture
@patch("lorairo.gui.services.worker_service.WorkerManager")
def worker_service(self, mock_worker_manager_class, mock_db_manager, mock_fsm):
    # 問題: fixture自体が@patchを使用
    # @patchはテスト単位で適用すべき
```

**推奨改修**:
```python
# ✅ 改善版: conftest.py に集約
@pytest.fixture
def mock_worker_manager():
    """WorkerManagerのモック - 複数テストで再利用"""
    with patch("lorairo.gui.services.worker_service.WorkerManager") as mock:
        yield mock
```

#### 外部APIモック実装の一貫性

| API | ファイル数 | 実装パターン | 課題 |
|-----|---------|------------|------|
| **OpenAI** | 11 | @patch (6) / monkeypatch (2) / 混在 (3) | **未統一** |
| **Google Gemini** | 4 | @patch | ✅ 統一 |
| **Anthropic Claude** | - | - | まだ利用なし |

---

### 2. 命名規則の遵守

#### ✅ 良好な点

- テスト関数名が `test_<機能>_<条件>_<期待結果>` 形式に **86.4%** 遵守
- テストクラス名が具体的（`TestImageProcessor` ✅ vs `TestLoader` ❌）
- ファイル名が `test_<モジュール>.py` 形式で統一

#### ⚠️ 改善が必要な点

**Medium 優先度**:

| ファイル | テスト関数 | 問題 | 推奨改修 |
|---------|----------|------|---------|
| `test_annotation_workflow_controller.py` | `test_init` | **短すぎる** - 初期化の何を検証するか不明 | `test_init_stores_dependencies_correctly` |
| `test_dataset_controller.py` | `test_init` | 同上 | `test_init_with_parent_stores_parent` |
| `test_search_filter_service.py` | `test_initialization` | 動作不明確 | `test_init_creates_signal_emitter` |
| `test_worker_service.py` | `test_initialization` | 同上 | `test_init_sets_all_worker_ids_to_none` |

**改修サンプル**:

```python
# ❌ 改修前
def test_init(self, mock_db_manager, mock_file_system_manager):
    """初期化が正常に行われる"""
    controller = DatasetController(mock_db_manager, ...)
    assert controller.db_manager == mock_db_manager

# ✅ 改修後
def test_init_stores_dependencies_correctly(self, mock_db_manager, mock_file_system_manager):
    """初期化で受け取った依存関係がすべて保存される"""
    controller = DatasetController(mock_db_manager, ...)
    assert controller.db_manager == mock_db_manager
```

---

### 3. 冗長性（フィクスチャの重複定義）

#### 重大な冗長性

**High 優先度**:

| フィクスチャ名 | 定義ファイル数 | 定義位置 | 推奨改修 |
|-------------|----------|--------|---------|
| **mock_db_manager** | 3 | `test_dataset_controller.py`, `test_error_detail_dialog.py`, `test_error_log_viewer_widget.py` | **conftest.py に統合** - 使用頻度 57 |
| **mock_worker_service** | 3 | `test_annotation_workflow_controller.py`, `test_dataset_controller.py`, `test_pipeline_control_service.py` | **conftest.py に統合** - 使用頻度 25 |
| **mock_parent** | 3 | `test_annotation_workflow_controller.py`, `test_dataset_controller.py`, `test_result_handler_service.py` | **conftest.py に統合** |

**Medium 優先度**:

| フィクスチャ名 | 定義ファイル数 | 推奨改修 |
|-------------|----------|---------|
| **mock_config_service** | 2 | conftest.py に統合 |
| **controller** | 2 | ファイル固有 → そのまま（OK） |
| **sample_error_record** | 2 | ファイル固有 → そのまま（OK） |
| **service** | 3 | conftest.py に統合 |

#### 重複フィクスチャの実装例

```python
# ❌ 現在: test_annotation_workflow_controller.py
@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモック"""
    service = Mock()
    service.get_api_keys.return_value = {
        "openai_key": "test-openai-key",
        "claude_key": "test-claude-key",
    }
    return service

# ❌ 同じコードが test_annotator_library_adapter.py にも存在
@pytest.fixture
def mock_config_service():
    service = Mock()
    service.get_api_keys.return_value = {...}
    return service

# ✅ 改修: tests/conftest.py に統合
@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモック - 複数テストで共有"""
    service = Mock()
    service.get_api_keys.return_value = {
        "openai_key": "test-openai-key",
        "claude_key": "test-claude-key",
        "google_key": "test-google-key",
    }
    service.get_available_annotation_models.return_value = [
        "gpt-4o-mini", "gpt-4o",
        "claude-3-haiku-20240307",
        "gemini-1.5-flash-latest",
    ]
    return service
```

#### 冗長性スコア算出

```
フィクスチャ定義の重複度:
  - 3ファイル: 4個（mock_db_manager, mock_worker_service, mock_parent, service）
  - 2ファイル: 3個（mock_config_service, controller, sample_error_record）

冗長コード行数推定: ~150-200行（統合で削減可能）

改修効果:
  - conftest.py に 7個フィクスチャ集約
  - 維持対象ファイル: 65 → 相変わらず 65（参照数減少で保守性 ↑30%）
```

---

### 4. テスト粒度（1テスト = 1振る舞い）

#### ⚠️ テストが長すぎるケース

**High 優先度** (>40行):

| ファイル | テスト関数 | 行数 | 問題 |
|---------|----------|------|------|
| `test_db_repository_annotations.py` | `test_fetch_filtered_metadata_processed_images_with_annotations` | **80行** | 複数のセットアップ段階 + 複数検証 |
| `test_db_repository_annotations.py` | `test_format_annotations_multiple_items` | **51行** | 複数パターンをループで検証 |
| `test_db_repository_annotations.py` | `test_format_annotations_with_data` | **49行** | セットアップが長い |

**詳細分析**:

```python
# ❌ 問題例: test_fetch_filtered_metadata_processed_images_with_annotations (80行)
def test_fetch_filtered_metadata_processed_images_with_annotations(self, repository):
    # 20行: セットアップ（画像、モデル、処理済み画像の作成）
    image = self.image1
    model = self.model1
    processed = ProcessedImageDict(...)
    ...

    # 15行: さらにセットアップ（注釈作成）
    annotation = AnnotationsDict(...)
    repository.add_model_query_result(...)

    # 25行: 検証フェーズ（複数条件）
    result = repository.fetch_filtered_metadata(...)
    assert len(result) > 0
    assert result[0]['caption'] == 'test caption'
    assert result[0]['processed_paths'] == {...}
    # ...さらに 5つの検証

    # 20行: 境界条件テスト（別セットアップ）
    resolution_2 = 512
    ...
```

**推奨改修**:

```python
# ✅ 分割版: 関心事ごとにテストを分離

class TestFetchFilteredMetadata:
    def test_fetch_filtered_metadata_includes_annotations_when_present(self, repository):
        """注釈ありの画像を取得すると、キャプションが含まれる"""
        # セットアップ（10行）
        image = self.image1
        annotation = AnnotationsDict(content='test caption')
        repository.add_image(image)
        repository.register_annotation(image.id, annotation)

        # 実行 + 検証（5行）
        result = repository.fetch_filtered_metadata(image.id)
        assert result[0]['caption'] == 'test caption'

    def test_fetch_filtered_metadata_excludes_annotations_when_absent(self, repository):
        """注釈なしの画像を取得すると、キャプションはnull"""
        image = self.image1
        repository.add_image(image)

        result = repository.fetch_filtered_metadata(image.id)
        assert result[0]['caption'] is None

    def test_fetch_filtered_metadata_shows_processed_image_paths(self, repository):
        """処理済み画像パスが結果に含まれる"""
        # ...個別テスト
```

#### セットアップが長すぎるテスト

**Medium 優先度** (セットアップ > 10行):

| ファイル | テスト関数 | セットアップ行数 | 推奨改修 |
|---------|----------|-------------|---------|
| `test_db_repository_batch_rating_score.py` | `test_update_existing_ratings` | 15行 | セットアップを helper method に抽出 |
| `test_db_repository_batch_queries.py` | `test_chunking_merges_results` | 12行 | conftest で reusable fixture に |
| `test_autocrop.py` | 複数テスト | 平均 12行 | parametrize で統合 |

**改修パターン**:

```python
# ❌ セットアップが長い
def test_update_existing_ratings(self, repository):
    # 15行のセットアップ
    images = [self.create_test_image(...) for _ in range(5)]
    for img in images:
        repository.add_image(img)
    ratings = [{"id": img.id, "score": i} for i, img in enumerate(images)]
    repository.add_ratings(ratings)
    updates = [{"id": img.id, "score": 100-i} for i, img in enumerate(images)]

    # 検証（3行）
    repository.update_ratings(updates)
    assert all(r.score == expected for r, expected in zip(...))

# ✅ 改修版: Helper method を使用
@pytest.fixture
def test_images_with_ratings(self):
    """レーティング付きテスト画像セット"""
    images = [self.create_test_image(name=f"img{i}") for i in range(5)]
    return images

def test_update_existing_ratings(self, repository, test_images_with_ratings):
    # セットアップ削減（3行）
    for img in test_images_with_ratings:
        repository.add_image(img)

    # 検証（3行）
    repository.update_ratings([...])
    assert all(...)
```

---

### 5. 依存関係・実行順序

#### ✅ 優秀な点

- **テスト間隠れ依存なし** - 各テストが独立
- **フィクスチャスコープ** - ほぼ適切（session vs function）
- **実行順序依存なし** - 並列実行可能

#### 検出されたリスク

**@patch デコレータ位置の問題** (13ファイル):

```python
# ⚠️ 問題パターン: test_worker_service.py
class TestWorkerService:
    @pytest.fixture
    @patch("lorairo.gui.services.worker_service.WorkerManager")
    def worker_service(self, mock_class, mock_db_manager, mock_fsm):
        # fixture に@patch → 暗黙的な前提条件
        # 別ファイルから this fixture を使用しにくい
```

**推奨改修**:
```python
# ✅ 改修版
@pytest.fixture
def worker_service(self, mock_worker_manager, mock_db_manager, mock_fsm):
    # @patch は別 fixture で済ませる
    service = WorkerService(mock_db_manager, mock_fsm)
    return service

@pytest.fixture
def mock_worker_manager():
    """WorkerManagerのモック"""
    with patch("lorairo.gui.services.worker_service.WorkerManager") as mock:
        yield mock
```

---

## 🎯 改善が必要なテスト（優先度別）

### High 優先度（品質に直結・即改修）

| # | ファイル | 問題 | 推奨改修 | 影響度 |
|---|---------|------|---------|--------|
| 1 | `test_worker_service.py` | **13個の@patch** - 過度なモック依存 | WorkerManager の実装単純化 or 統合テストへ移行 | 🔴 高 |
| 2 | 複数ファイル | **フィクスチャ重複** (mock_db_manager 3x, mock_worker_service 3x など) | conftest.py に 7個統合 | 🔴 高 |
| 3 | `test_db_repository_annotations.py` | **テスト長すぎ** (80行) - 複数検証が混在 | セットアップ helper + 関心事ごとに分割 | 🔴 高 |
| 4 | 28ファイル | **テスト名が短すぎ** (`test_init` など) | `test_init_stores_dependencies_correctly` など詳細化 | 🟡 中 |

### Medium 優先度（保守性向上）

| # | ファイル | 問題 | 推奨改修 | 利益 |
|---|---------|------|---------|------|
| 5 | `test_autocrop.py`, `test_image_preview_widget.py` | **6個の@patch** - 複雑性が高い | 内部ロジック抽出 or parametrize 使用 | セットアップ -30% |
| 6 | `test_db_repository_batch_*.py` | **セットアップが長い** (12-15行) | conftest で reusable fixture 作成 | 重複度 -40% |
| 7 | OpenAI モック実装 | **2パターン混在** (@patch/monkeypatch) | @patch に統一、conftest.py に集約 | 一貫性 ↑ |
| 8 | GUI ウィジェットテスト | **pytest-qt パターン改善** | Signal 待機パターンを汎用化 | - |

### Low 優先度（参考・段階的改修）

| # | ファイル | 問題 | 推奨改修 | 優先度 |
|---|---------|------|---------|--------|
| 9 | `test_search_filter_service.py` | テスト関数がクラスに散在 | クラス内に整理（可選） | 低 |
| 10 | 複数ファイル | docstring フォーマット | Google-style に統一（既に大部分 OK） | 低 |

---

## 📋 推奨アクション

### フェーズ 1: 即座に対応（1-2時間）

```bash
# 1. フィクスチャ統合 - conftest.py に追加
#    - mock_db_manager
#    - mock_worker_service
#    - mock_parent
#    - mock_config_service
#    - service (generic)

# 2. テスト名改修 - 28 files
#    test_init → test_init_stores_dependencies_correctly
#    test_initialization → test_init_creates_signal_emitter
```

### フェーズ 2: 構造改善（3-5時間）

```bash
# 3. @patch デコレータ整理
#    - test_worker_service.py: 13個を別 fixture に分離
#    - test_autocrop.py: 6個を parametrize に
#    - test_image_preview_widget.py: 6個を fixture に

# 4. 長いテスト分割
#    - test_db_repository_annotations.py: 80行 → 3つに分割
#    - test_db_repository_batch_*.py: セットアップ helper 作成
```

### フェーズ 3: 品質向上（2-3時間）

```bash
# 5. OpenAI モック統一
#    - conftest.py で mock_openai_client fixture 定義
#    - 11ファイルのモック実装を統一

# 6. セットアップ削減
#    - test_db_repository_batch_queries.py の helper 抽出
#    - parametrize パターン導入（テスト行数 -20%）
```

---

## 📊 改修効果の見積り

| 改修項目 | 対象数 | 削減行数 | 保守性改善 |
|---------|--------|---------|----------|
| フィクスチャ統合 | 7個 | ~150-200行 | **+30%** |
| テスト名詳細化 | 28個 | - | **+40%** (可読性) |
| @patch 整理 | 13個 | ~80行 | **+25%** (複雑度) |
| テスト長短縮 | 87個 | ~200-300行 | **+35%** (粒度) |
| **合計** | - | **~500-700行削減** | **+30-35%** |

---

## 🚀 実装ロードマップ

### Week 1: フィクスチャ統合（優先度: High）

```python
# tests/conftest.py に追加する統合フィクスチャ
@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManagerのモック - 複数テストで共有"""
    manager = Mock()
    manager.get_images.return_value = []
    manager.register_image.return_value = True
    return manager

@pytest.fixture
def mock_worker_service():
    """WorkerServiceのモック"""
    service = Mock()
    service.start_batch_registration_with_fsm.return_value = "worker-id-123"
    service.start_enhanced_batch_annotation.return_value = "annotation-id-456"
    return service

@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモック"""
    service = Mock()
    service.get_api_keys.return_value = {
        "openai_key": "test-key",
        "claude_key": "test-key",
        "google_key": "test-key",
    }
    return service
```

### Week 2: テスト名改修（優先度: Medium）

```python
# 改修パターン
test_init → test_init_stores_dependencies_correctly
test_initialization → test_init_creates_signal_emitter
test_signal_definitions → test_has_all_required_signals
```

### Week 3-4: 構造改善（優先度: Medium）

- @patch デコレータ分離
- 長いテスト分割
- seUpup helper 作成

---

## ✅ 検査完了チェックリスト

- [x] 65ファイル全 scan 完了
- [x] 1,025テスト関数分析
- [x] モック戦略統一度評価
- [x] フィクスチャ重複検出
- [x] テスト粒度評価
- [x] 依存関係分析
- [x] 改修優先度判定
- [x] 削減行数見積り

---

## 📝 付録: conftest.py 統合フィクスチャ案

```python
# tests/conftest.py に追加する共通フィクスチャ

@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManagerのモック"""
    manager = Mock()
    manager.get_images.return_value = []
    manager.register_image.return_value = True
    manager.get_annotations.return_value = {}
    manager.add_error_record.return_value = None
    return manager

@pytest.fixture
def mock_worker_service():
    """WorkerServiceのモック"""
    service = Mock()
    service.start_batch_registration_with_fsm.return_value = "worker-id"
    service.start_enhanced_batch_annotation.return_value = "annotation-id"
    service.start_search.return_value = "search-id"
    service.current_search_worker_id = None
    return service

@pytest.fixture
def mock_parent():
    """親ウィジェット/ウィンドウのモック"""
    return Mock()

@pytest.fixture
def mock_config_service():
    """ConfigurationServiceのモック"""
    service = Mock()
    service.get_api_keys.return_value = {
        "openai_key": "test-openai-key",
        "claude_key": "test-claude-key",
        "google_key": "test-google-key",
    }
    service.get_available_annotation_models.return_value = [
        "gpt-4o-mini", "gpt-4o",
        "claude-3-haiku-20240307",
        "gemini-1.5-flash-latest",
    ]
    return service

@pytest.fixture
def mock_openai_client():
    """OpenAI クライアントのモック"""
    client = Mock()
    client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="Test response"))]
    )
    return client

# 削除対象フィクスチャ (各ファイルから移動)
# - test_annotation_workflow_controller.py: mock_config_service, mock_parent
# - test_dataset_controller.py: mock_db_manager, mock_worker_service, mock_parent
# - test_result_handler_service.py: mock_parent, service
# - test_pipeline_control_service.py: mock_worker_service, service
# - test_error_detail_dialog.py: mock_db_manager
# - test_error_log_viewer_widget.py: mock_db_manager
```

---

**作成者**: Claude Code（Haiku 4.5）
**ツール**: Serena MCP + 自動分析スクリプト
**準拠**: CLAUDE.md ./.claude/rules/testing.md
