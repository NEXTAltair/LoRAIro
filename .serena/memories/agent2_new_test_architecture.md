# LoRAIro 新テストアーキテクチャ設計（Agent 2）

**完成日**: 2026-02-10
**設計者**: Agent 2（テストアーキテクチャ設計リード）
**入力データ**: Agent 1 分析結果 + pytest 実測値

---

## 設計方針

### 原則 1: CLAUDE.md 「Testing Rules」に完全準拠
- テストレイヤー: **unit / integration / gui / bdd** の 4層（ただし現状 gui は unit/gui に統合）
- pytest マーカー統一: `@pytest.mark.unit|integration|gui|bdd|slow`
- 最小カバレッジ: **75% 維持**

### 原則 2: 現状の Unit-first 戦略を尊重
Agent 1 の実測データから判明：
- **ユニットテスト主力**: 850+ テスト（68%）
  - GUI ウィジェット: 240 テスト（最大）
  - サービス: 167 テスト
  - GUI サービス: 98 テスト
- **統合テスト補助的**: 214 テスト（17%）
- **BDD テスト**: 未実装（.feature のみ）

⇒ 現状のディレクトリ構成（unit/ 充実）を尊重。無理な reorganization は避ける。

### 原則 3: 単一責任の原則
- 各層の conftest.py は「本当に共有されるもの」のみ
- ローカルフィクスチャは各テストモジュール内に定義
- フィクスチャ数を 34個から **15-20個/ファイル** に削減

### 原則 4: 実行性能
- 現在の実行時間 ~50秒 から **±20% 以内** に抑える
- 並列実行対応で実効時間 ~30秒を実現

### 原則 5: 保守性
- テストファイル: 300行以下（既に達成）
- 新規テスト追加時の判断基準: 明確

---

## 現状 → 新構造のマッピング

### 変更が不要な部分（既に最適化）
| ディレクトリ | テスト数 | 評価 | アクション |
|---|---|---|---|
| tests/unit/ | 850+ | ✅ 充実 | そのまま維持 |
| tests/unit/gui/widgets/ | 240 | ✅ 充実 | そのまま維持 |
| tests/unit/services/ | 167 | ✅ 充実 | そのまま維持 |
| tests/integration/ | 214 | ✅ 補助的（適正） | そのまま維持 |

### 変更が必要な部分
| ディレクトリ | 現状 | 新構造 | 理由 |
|---|---|---|---|
| tests/conftest.py | 1層（34フィクスチャ） | 2層（root + layer別） | 責務分割 |
| pytest.ini | マーカー定義なし | 定義あり | マーカー統一 |
| tests/bdd/ | features + step_defs バラバラ | 整理 | BDD準備 |

---

## 新ディレクトリ構成

```
tests/
├── conftest.py                    # 全層共通フィクスチャ（最小限）
├── pytest.ini                     # マーカー定義
│
├── unit/                          # ユニットテスト層（既存、維持）
│   ├── conftest.py               # ユニット用フィクスチャ（新規分割）
│   ├── gui/
│   │   ├── widgets/              # 240 テスト
│   │   ├── services/             # 98 テスト
│   │   ├── workers/              # 42 テスト
│   │   ├── state/                # 41 テスト
│   │   ├── controllers/          # 31 テスト
│   │   ├── window/               # 30 テスト
│   │   ├── cache/                # 21 テスト
│   │   └── conftest.py           # GUI 専用フィクスチャ
│   ├── services/                 # 167 テスト
│   ├── storage/                  # 58 テスト
│   ├── ...（その他）
│   │
│   # 新追加（必要に応じて）
│   └── conftest.py               # ユニット層共通フィクスチャ
│
├── integration/                   # 統合テスト層（既存、維持）
│   ├── conftest.py               # 統合テスト用フィクスチャ（新規分割）
│   ├── gui/                       # 105 テスト
│   ├── database/                 # 8 テスト
│   ├── services/                 # 9 テスト
│   └── ... （その他の統合テスト）
│
├── bdd/                          # BDD E2E テスト層（準備用）
│   ├── conftest.py               # BDD フィクスチャ
│   ├── features/                 # Gherkin シナリオ（.feature）
│   └── step_defs/                # ステップ定義
│
├── resources/                     # テストリソース（変更なし）
│   └── img/
│
└── manual/                        # 手動テスト（プレースホルダー）
```

---

## conftest.py の責務分割（詳細設計）

### tests/conftest.py（ルート - 最小限）

**責務**:
- genai-tag-db-tools モック（全テスト必須）
- Qt ヘッドレス環境設定（Linux）
- プロジェクトルート参照

**フィクスチャ数**: 4-5個

```python
# tests/conftest.py（60-80行）

import os
import sys
from pathlib import Path
import unittest.mock
import pytest

# === genai-tag-db-tools Mock (CRITICAL) ===
# モジュールレベルでパッチを開始（lorairo import前）
_mock_result_1 = unittest.mock.Mock()
_mock_result_1.db_path = "/tmp/test_tag_db_cc4.db"
# ... 他の DB モック

_runtime_patches = [
    unittest.mock.patch("genai_tag_db_tools.initialize_databases", ...),
    unittest.mock.patch("genai_tag_db_tools.db.runtime.get_user_session_factory", ...),
]

for _patch in _runtime_patches:
    _patch.start()

# === Qt Configuration ===
@pytest.fixture(scope="session", autouse=True)
def configure_qt_for_tests():
    """Qt環境を自動設定（全テスト）"""
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    yield
    for patch in _runtime_patches:
        patch.stop()

# === Common ===
@pytest.fixture(scope="session")
def project_root() -> Path:
    """プロジェクトルート"""
    return Path(__file__).parent.parent
```

### tests/unit/conftest.py（ユニットテスト用）

**責務**:
- モック実装（OpenAI, Google, その他外部API）
- ダミーデータ生成
- **ユニットテスト専用の軽量フィクスチャ**

**フィクスチャ数**: 10-15個

```python
# tests/unit/conftest.py（150-200行）

import pytest
from unittest.mock import Mock, patch
from PIL import Image
import numpy as np

# === External API Mocks ===
@pytest.fixture
def mock_openai():
    """OpenAI API モック"""
    with patch("openai.ChatCompletion.create") as mock:
        mock.return_value = Mock(choices=[Mock(message=Mock(content="test"))])
        yield mock

@pytest.fixture
def mock_google():
    """Google Vision API モック"""
    with patch("google.cloud.vision.ImageAnnotatorClient") as mock:
        yield mock

# === Dummy Data ===
@pytest.fixture
def dummy_image() -> Image.Image:
    """ダミー PIL Image（100x100 RGB）"""
    return Image.new("RGB", (100, 100), color="red")

@pytest.fixture
def dummy_image_array() -> np.ndarray:
    """ダミー numpy 配列"""
    return np.zeros((100, 100, 3), dtype=np.uint8)

# === Service Mocks ===
@pytest.fixture
def mock_config_service():
    """ConfigService モック"""
    return Mock()

@pytest.fixture
def mock_db_manager():
    """ImageDatabaseManager モック"""
    return Mock()
```

### tests/unit/gui/conftest.py（GUI ユニットテスト用）

**責務**:
- QApplication 初期化
- QMessageBox モック
- Qt ウィジェット用ダミーデータ

**フィクスチャ数**: 8-12個

```python
# tests/unit/gui/conftest.py（100-150行）

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from unittest.mock import Mock, patch

@pytest.fixture(scope="session")
def qapp():
    """QApplication インスタンス（session スコープ）"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture(autouse=True)
def mock_qmessagebox(monkeypatch):
    """QMessageBox の自動モック"""
    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.Yes
    )
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda *args, **kwargs: QMessageBox.Ok
    )

@pytest.fixture
def mock_config_for_gui():
    """GUI 用 ConfigService モック"""
    mock = Mock()
    mock.get_setting.return_value = None
    return mock
```

### tests/integration/conftest.py（統合テスト用）

**責務**:
- DB 初期化（test_engine_with_schema）
- ストレージ管理（fs_manager）
- リポジトリフィクスチャ
- クリーンアップ処理

**フィクスチャ数**: 12-15個

```python
# tests/integration/conftest.py（200-250行）

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from lorairo.database.schema import Base
from lorairo.database.db_repository import ImageRepository
from lorairo.storage.file_system import FileSystemManager
import tempfile
from pathlib import Path

@pytest.fixture(scope="function")
def test_db_url() -> str:
    """テストDB URL（インメモリ）"""
    return "sqlite:///:memory:"

@pytest.fixture(scope="function")
def test_engine_with_schema(test_db_url):
    """DB エンジン + スキーマ作成"""
    engine = create_engine(test_db_url, echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def test_session(test_engine_with_schema):
    """DB セッション"""
    Session = sessionmaker(bind=test_engine_with_schema)
    session = Session()
    yield session
    session.close()

@pytest.fixture(scope="function")
def temp_storage_dir():
    """テンポラリストレージディレクトリ"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)

@pytest.fixture(scope="function")
def fs_manager(temp_storage_dir):
    """FileSystemManager インスタンス"""
    manager = FileSystemManager()
    manager.initialize(temp_storage_dir)
    yield manager

@pytest.fixture(scope="function")
def test_repository(test_session):
    """ImageRepository インスタンス"""
    return ImageRepository(test_session)
```

### tests/bdd/conftest.py（BDD テスト用 - 将来拡張）

**責務**:
- BDD ステップコンテキスト管理
- Gherkin テストデータセットアップ

**フィクスチャ数**: 3-5個（将来用）

```python
# tests/bdd/conftest.py（50-100行）

import pytest

@pytest.fixture
def bdd_context():
    """BDD ステップコンテキスト"""
    context = {"fixtures": {}, "results": {}}
    yield context

@pytest.fixture
def bdd_test_data():
    """BDD テストデータ"""
    return {
        "sample_images": [],
        "test_project": None,
    }
```

---

## pytest.ini マーカー定義

```ini
# pytest.ini

[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

markers =
    unit: ユニットテスト（外部依存はモック）
    integration: 統合テスト（内部コンポーネント結合）
    gui: GUIテスト（pytest-qt 使用）
    bdd: BDD E2Eテスト（Gherkin シナリオ）
    slow: 遅いテスト（5秒以上）

# 並列実行設定
addopts =
    -v
    --tb=short
    --strict-markers
```

---

## テストマーカー適用ルール

### ユニットテスト（tests/unit/）
```python
@pytest.mark.unit
def test_image_loader_valid_file(mock_filesystem):
    """外部依存はモック"""
    ...
```

### 統合テスト（tests/integration/）
```python
@pytest.mark.integration
def test_database_save_and_retrieve(test_session, test_repository):
    """DB + リポジトリ結合"""
    ...
```

### GUI テスト（tests/unit/gui/ と tests/integration/gui/）
```python
@pytest.mark.gui
def test_widget_initialization(qtbot, qapp):
    """Qt ウィジェット動作"""
    ...

# waitSignal / waitUntil の使用を必須化
with qtbot.waitSignal(widget.signal_name, timeout=5000):
    widget.trigger_action()
```

### BDD テスト（tests/bdd/）
```python
@pytest.mark.bdd
def test_user_can_load_images():
    """Gherkin シナリオのステップ"""
    ...
```

### 遅いテスト（オプション）
```python
@pytest.mark.slow
@pytest.mark.integration
def test_large_batch_processing():
    """5秒以上かかるテスト"""
    ...
```

---

## 実行性能最適化

### 実行パターン

#### パターン 1: 全テスト実行
```bash
uv run pytest
# 出力: 1,255 テスト、実行時間 ~50秒
```

#### パターン 2: カテゴリ別実行
```bash
uv run pytest -m unit              # ~30秒（850 テスト）
uv run pytest -m integration       # ~15秒（214 テスト）
uv run pytest -m gui               # ~5秒（100+ GUI テスト）
uv run pytest -m bdd               # ~3秒（準備中）
```

#### パターン 3: 並列実行（CI/CD）
```bash
pytest -m "unit or integration or gui or bdd" -n auto
# pytest-xdist による並列実行で実効時間 ~25-30秒
```

### パフォーマンス見積り

| パターン | テスト数 | 時間 | 備考 |
|---|---|---|---|
| Unit のみ | 850 | ~30秒 | 最速 |
| Integration のみ | 214 | ~15秒 | 中速 |
| GUI のみ | 100+ | ~5秒 | 最速 |
| 全テスト（順次） | 1,255 | ~50秒 | 現状 |
| **全テスト（並列）** | 1,255 | **~25-30秒** | 推奨（CI/CD） |

**改善効果**: 並列実行で **40-50% 時間短縮** 可能

---

## 移行ロードマップ（5フェーズ）

### Phase 1: 準備（1-2日）
- [ ] tests/unit/conftest.py を作成（既存テストとの互換性確認）
- [ ] tests/unit/gui/conftest.py を作成
- [ ] tests/integration/conftest.py を分割作成
- [ ] tests/bdd/conftest.py を作成
- [ ] pytest.ini にマーカー定義を追加
- [ ] テスト実行確認（全成功）

### Phase 2: ユニットテスト最適化（2-3日）
- [ ] @pytest.mark.unit を全 unit/ テストに付与
- [ ] conftest 内フィクスチャ使用を統一
- [ ] 重複テスト削除（Agent 1 findings から）
- [ ] テスト実行確認（成功率 100%）

### Phase 3: 統合テスト整理（1-2日）
- [ ] @pytest.mark.integration を全 integration/ テストに付与
- [ ] DB初期化フロー最適化
- [ ] テスト実行確認

### Phase 4: GUI / BDD 標準化（1-2日）
- [ ] @pytest.mark.gui を全 GUI テストに付与
- [ ] pytest-qt ベストプラクティス適用（waitSignal/waitUntil）
- [ ] BDD テスト構造準備
- [ ] テスト実行確認

### Phase 5: 検証・クリーンアップ（1日）
- [ ] 全テスト実行（成功率 100%）
- [ ] カバレッジ測定（75%+ 確保）
- [ ] 実行時間測定（並列実行で ~30秒）
- [ ] ドキュメント更新
- [ ] 古い conftest 内容の最適化完了

**総所要時間**: 約 7-10日

---

## 重要な設計決定

### 決定 1: Unit-first 戦略を尊重
**根拠**: 実測値から、既に ユニットテスト 850+ が充実している
**アクション**: unit/ ディレクトリを維持、conftest 分割のみ

### 決定 2: Multi-layer conftest による責務分割
**根拠**: 現在の 34個フィクスチャが混在、保守が困難
**アクション**: root + unit/gui/integration/bdd に分割（計 5層）

### 決定 3: GUI テストの pytest-qt 標準化
**根拠**: GUI テストが 40% を占める、品質確保が重要
**アクション**: waitSignal/waitUntil の強制使用

### 決定 4: BDD テストは準備段階
**根拠**: .feature ファイルのみ、Python テスト関数なし
**アクション**: conftest を準備、本実装は将来フェーズ

### 決定 5: パフォーマンスと保守性のバランス
**根拠**: 現状 ~50秒は許容範囲、並列実行で ~30秒へ
**アクション**: pytest-xdist 導入推奨（CI/CD 用）

---

## 成功基準

- ✅ 全テスト成功（1,255テスト、成功率 100%）
- ✅ カバレッジ 75%+（現状 75-80%）
- ✅ 実行時間 ~50秒 → 並列時 ~30秒（40% 短縮）
- ✅ conftest 責務分割完成（34個 → 15-20個/ファイル）
- ✅ pytest マーカー統一適用（全テスト）
- ✅ ドキュメント更新（docs/testing.md）

---

## 次のステップ

**Agent 3（品質検査）** が以下を実行：
1. **3A**: ユニットテスト品質チェック（重複検出、命名規則）
2. **3B**: 統合テスト品質チェック（依存関係、テスト分離）
3. **3C**: BDD テスト品質チェック（シナリオ構造）

その後、**Agent 4（実装）** が Phase 1-5 を実行します。
