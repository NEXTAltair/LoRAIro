# tests/bdd/conftest.py
"""
BDD テスト層の共有フィクスチャ

責務:
- BDD ステップコンテキスト管理
- Gherkin テストデータセットアップ
- シナリオ実行環境の初期化

このファイルは tests/conftest.py (ルート) に依存します。
"""

import pytest
from pathlib import Path


# ===== BDD Context Management =====

@pytest.fixture
def bdd_context():
    """
    BDD ステップコンテキスト

    各ステップ定義関数で共有される状態管理オブジェクト
    """
    context = {
        # 入力データ
        "inputs": {},

        # 実行中の状態
        "state": {},

        # 出力結果
        "results": {},

        # テスト用オブジェクト
        "fixtures": {},
    }
    return context


@pytest.fixture
def bdd_test_data():
    """BDD テスト用のサンプルデータ"""
    return {
        "projects": [],
        "images": [],
        "tags": [],
        "models": [],
    }


# ===== Scenario Setup =====

@pytest.fixture
def bdd_project_setup(bdd_context, bdd_test_data):
    """BDD シナリオ用のプロジェクトセットアップ"""
    project = {
        "name": "test_project",
        "directory": "/tmp/test_project",
        "images": [],
    }
    bdd_test_data["projects"].append(project)
    bdd_context["fixtures"]["project"] = project
    return project


@pytest.fixture
def bdd_image_setup(bdd_context, bdd_test_data):
    """BDD シナリオ用の画像セットアップ"""
    from PIL import Image
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        images = []
        for i in range(3):
            img = Image.new("RGB", (256, 256), color="red")
            img_path = Path(tmpdir) / f"image_{i}.png"
            img.save(img_path)
            images.append(str(img_path))

        bdd_test_data["images"] = images
        bdd_context["fixtures"]["images"] = images
        yield images


# ===== Step Execution Helpers =====

@pytest.fixture
def step_helper():
    """ステップ実行ヘルパー"""
    class StepHelper:
        def assert_result(self, context, key, expected):
            """結果を検証"""
            actual = context["results"].get(key)
            assert actual == expected, f"Expected {expected}, got {actual}"

        def set_input(self, context, key, value):
            """入力を設定"""
            context["inputs"][key] = value

        def get_output(self, context, key):
            """出力を取得"""
            return context["results"].get(key)

    return StepHelper()


# ===== BDD Environment =====

@pytest.fixture(scope="session")
def bdd_environment():
    """BDD テスト実行環境設定"""
    return {
        "timeout": 30,  # テストタイムアウト（秒）
        "retry_count": 3,  # リトライ回数
        "verbose": True,  # 詳細ログ
    }


# ===== Scenario Markers =====

def pytest_configure(config):
    """pytest マーカー設定"""
    config.addinivalue_line(
        "markers",
        "bdd: BDD E2E テスト（Gherkin シナリオ）"
    )


# ===== Test Cleanup =====

@pytest.fixture(autouse=True)
def bdd_cleanup(bdd_context):
    """BDD テスト後のクリーンアップ"""
    yield
    # コンテキストをリセット
    bdd_context.clear()


# ===== Automatic Marker Application =====

def pytest_collection_modifyitems(config, items):
    """tests/bdd 配下のテストに @pytest.mark.bdd を自動付与"""
    for item in items:
        if "tests/bdd" in str(item.fspath):
            item.add_marker(pytest.mark.bdd)
