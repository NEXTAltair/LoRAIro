import pytest
from pathlib import Path
from module.db import SQLiteManager, ImageRepository, ImageDatabaseManager
from unittest.mock import MagicMock, patch
from module.log import get_logger
import uuid

@pytest.fixture
def test_db_paths(tmp_path):
    img_db = tmp_path / f"test_image_database_{uuid.uuid4()}.db"
    tag_db = tmp_path / f"test_tag_database_{uuid.uuid4()}.db"
    return img_db, tag_db

@pytest.fixture
def sqlite_manager(test_db_paths):
    img_db, tag_db = test_db_paths
    sqlite_manager = SQLiteManager(img_db, tag_db)
    sqlite_manager.create_tables()
    sqlite_manager.insert_models()
    yield sqlite_manager
    sqlite_manager.close()
    img_db.unlink(missing_ok=True)
    tag_db.unlink(missing_ok=True)

@pytest.fixture
def image_database_manager(sqlite_manager):
    with patch.object(ImageDatabaseManager, '__init__', return_value=None):
        idm = ImageDatabaseManager()
        idm.logger = get_logger("ImageDatabaseManager")
        idm.db_manager = sqlite_manager
        idm.repository = ImageRepository(sqlite_manager)
        idm.logger.debug("初期化（テスト用パス使用）")
        yield idm

def test_sqlite_connect(sqlite_manager):
    """データベース接続とテーブル作成の確認"""
    conn = sqlite_manager.connect()
    assert conn is not None
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {table['name'] for table in cursor.fetchall()}
    expected_tables = {'images', 'processed_images', 'models', 'tags', 'captions', 'scores'}
    assert expected_tables.issubset(tables)

def test_sqlite_execute(sqlite_manager):
    """データベースへのクエリ実行の確認"""
    query = "INSERT INTO models (name, type, provider) VALUES (?, ?, ?)"
    params = ('test_model', 'test_type', 'test_provider')
    cursor = sqlite_manager.execute(query, params)
    assert cursor.lastrowid is not None

    """単一行のデータ取得の確認"""
    fetch_query = "SELECT * FROM models WHERE name = ?"
    fetch_params = ('test_model',)
    result = sqlite_manager.fetch_one(fetch_query, fetch_params)
    assert result is not None
    assert result['name'] == 'test_model'
    assert result['type'] == 'test_type'
    assert result['provider'] == 'test_provider'

def test_add_original_image(image_database_manager, sample_image_info):
    """オリジナル画像の追加とメタデータの取得"""
    image_id = image_database_manager.repository.add_original_image(sample_image_info)
    assert isinstance(image_id, int)

    metadata = image_database_manager.repository.get_image_metadata(image_id)
    assert metadata is not None
    for key, value in sample_image_info.items():
        assert metadata[key] == value

def test_duplicate_image(image_database_manager, sample_image_info):
    """重複画像の検出と同一IDの返却確認"""
    image_id1 = image_database_manager.repository.add_original_image(sample_image_info)
    image_id2 = image_database_manager.repository.add_original_image(sample_image_info)  # 重複画像を追加
    assert image_id1 == image_id2  # 同じIDが返される

@patch('module.db.calculate_phash', return_value='mocked_phash')
def test_register_original_image(mock_calculate_phash, image_database_manager, mock_file_system_manager, tmp_path):
    """オリジナル画像の登録処理"""
    manager = image_database_manager

    mock_file_system_manager.get_image_info.return_value = {
        'width': 800,
        'height': 600,
        'format': 'JPEG',
        'mode': 'RGB',
        'has_alpha': False,
        'filename': 'image.jpg',
        'extension': 'jpg',
        'color_space': 'sRGB',
        'icc_profile': None
    }
    mock_file_system_manager.save_original_image.return_value = tmp_path / "image.jpg"

    result = manager.register_original_image(Path("/fake/path/image.jpg"), mock_file_system_manager)
    assert result is not None
    image_id, metadata = result
    assert isinstance(image_id, int)
    assert metadata['width'] == 800
    assert metadata['height'] == 600

def test_register_processed_image(image_database_manager, sample_image_info, tmp_path):
    """処理済み画像の登録とメタデータの確認"""
    manager = image_database_manager

    image_id = manager.repository.add_original_image(sample_image_info)

    # processed_info に extension と phash は不要なため削除
    processed_info = {
        'width': 256,
        'height': 256,
        'format': 'WEBP',
        'mode': 'RGB',
        'has_alpha': False,
        'filename': 'processed.webp',
        'color_space': 'sRGB',
        'icc_profile': None
    }
    processed_path = tmp_path / "processed.webp"
    processed_path.touch()

    result = manager.register_processed_image(image_id, processed_path, processed_info)
    assert result is not None
    processed_image_id = result

    metadata = manager.repository.get_processed_image(image_id)
    assert metadata is not None
    assert len(metadata) > 0
    processed_metadata = metadata[0]
    assert processed_metadata['image_id'] == image_id
    assert processed_metadata['width'] == 256
    assert processed_metadata['height'] == 256

def assert_annotations(retrieved_data, expected_data, model_id, test_case_index):
    for key in ['tags', 'captions', 'scores']:
        if key in expected_data:
            expected = expected_data[key]
            if key == 'tags':
                filtered = [item['tag'] for item in retrieved_data['tags'] if item['model_id'] == model_id]
            elif key == 'captions':
                filtered = [item['caption'] for item in retrieved_data['captions'] if item['model_id'] == model_id]
            elif key == 'scores':
                filtered = [item['score'] for item in retrieved_data['scores'] if item['model_id'] == model_id]

            if key == 'scores':
                assert len(filtered) == 1, (
                    f"テストケース {test_case_index}: {key} の数が1ではありません。実際: {len(filtered)}"
                )
                assert filtered[0] == expected, (
                    f"テストケース {test_case_index}: {key} が一致しません。期待: {expected}, 実際: {filtered[0]}"
                )
            else:
                assert len(filtered) == len(expected), (
                    f"テストケース {test_case_index}: {key} の数が一致しません。期待: {len(expected)}, 実際: {len(filtered)}"
                )
                assert set(filtered) == set(expected), (
                    f"テストケース {test_case_index}: {key} の内容が一致しません。期待: {expected}, 実際: {filtered}"
                )

def test_save_annotations(image_database_manager, sample_image_info):
    """アノテーションの保存と取得の確認、欠損値のテストを含む"""
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)

    test_cases = [
        {
            'tags': ['tag1', 'tag2', 'tag3'],
            'captions': ['caption1', 'caption2'],
            'score': 0.95,
            'model_id': 1
        },
        {
            'tags': ['tag4', 'tag5'],
            'captions': ['caption3'],
            'model_id': 2
        },
        {
            'captions': ['caption4'],
            'score': 0.85,
            'model_id': 3
        },
        {
            'tags': ['tag6'],
            'score': 0.75,
            # 'model_id' がない場合
        }
    ]

    for index, case in enumerate(test_cases, start=1):
        manager.repository.save_annotations(image_id, case)

        retrieved = manager.repository.get_image_annotations(image_id)

        current_model_id = case.get('model_id')

        assert_annotations(retrieved, case, current_model_id, index)

def test_get_images_by_tag(image_database_manager, sample_image_info):
    """タグによる画像検索の確認"""
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)
    manager.repository.save_annotations(image_id, {'tags': ['test_tag'], 'model_id': None})

    image_ids = manager.repository.get_images_by_tag('test_tag')
    assert image_id in image_ids

def test_get_images_by_caption(image_database_manager, sample_image_info):
    """キャプションによる画像検索の確認"""
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)
    manager.repository.save_annotations(image_id, {'captions': ['test_caption'], 'model_id': None})

    image_ids = manager.repository.get_images_by_caption('test_caption')
    assert image_id in image_ids

def test_update_image_metadata(image_database_manager, sample_image_info):
    """画像メタデータの更新の確認"""
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)

    updated_info = {'width': 1024, 'height': 768}
    manager.repository.update_image_metadata(image_id, updated_info)

    metadata = manager.repository.get_image_metadata(image_id)
    assert metadata['width'] == 1024
    assert metadata['height'] == 768
    assert metadata['updated_at'] is not None

def test_delete_image(image_database_manager, sample_image_info):
    """画像の削除と関連データの確認"""
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)
    manager.repository.save_annotations(image_id, {
        'tags': ['test_tag1','test_tag2','test_tag3'],
        'captions': ['test_caption1','test_caption2','test_caption3'],
        'score': 0.95,
        'model_id': 1
    })

    # 削除前にアノテーションが存在することを確認
    annotations_before = manager.get_image_annotations(image_id)
    assert len(annotations_before['tags']) == 3
    assert len(annotations_before['captions']) == 3
    assert len(annotations_before['scores']) == 1

    manager.repository.delete_image(image_id)

    # 画像が削除されたことを確認
    metadata = manager.get_image_metadata(image_id)
    assert metadata is None

    # 削除後はアノテーションが空になることを確認
    annotations_after = manager.get_image_annotations(image_id)
    assert len(annotations_after['tags']) == 0
    assert len(annotations_after['captions']) == 0
    assert len(annotations_after['scores']) == 0

def test_get_total_image_count(image_database_manager, sample_image_info):
    """総画像数の取得の確認"""
    manager = image_database_manager
    initial_count = manager.repository.get_total_image_count()

    manager.repository.add_original_image(sample_image_info)
    new_count = manager.repository.get_total_image_count()
    assert new_count == initial_count + 1

def test_get_models(image_database_manager):
    """モデル情報の取得の確認"""
    manager = image_database_manager

    vision_models, score_models, upscaler_models = manager.get_models()
    assert isinstance(vision_models, dict)
    assert isinstance(score_models, dict)
    assert isinstance(upscaler_models, dict)
    assert len(vision_models) > 0

def test_get_images_by_filter(image_database_manager, sample_image_info, tmp_path):
    """フィルタによる画像検索の確認"""
    manager = image_database_manager

    # オリジナル画像を追加
    image_id = manager.repository.add_original_image(sample_image_info)

    # 処理済み画像を登録
    processed_info = {
        'width': 256,
        'height': 256,
        'format': 'WEBP',
        'mode': 'RGB',
        'has_alpha': False,
        'filename': 'processed.webp',
        'color_space': 'sRGB',
        'icc_profile': None
    }
    processed_path = tmp_path / "processed.webp"
    processed_path.touch()
    manager.register_processed_image(image_id, processed_path, processed_info)

    # アノテーションを保存
    manager.repository.save_annotations(image_id, {'tags': ['filter_tag'], 'model_id': None})

    # フィルタで画像を取得
    filtered_images, count = manager.get_images_by_filter(tags=['filter_tag'])
    assert count == 1
    assert filtered_images[0]['image_id'] == image_id


def test_create_tables(image_database_manager):
    """テーブル作成のテスト"""
    image_database_manager.db_manager.create_tables()

    # images テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='images';"
    result = image_database_manager.db_manager.fetch_one(query)
    assert result is not None

    # processed_images テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_images';"
    result = image_database_manager.db_manager.fetch_one(query)
    assert result is not None

    # models テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='models';"
    result = image_database_manager.db_manager.fetch_one(query)
    assert result is not None

    # tags テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='tags';"
    result = image_database_manager.db_manager.fetch_one(query)
    assert result is not None

    # captions テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='captions';"
    result = image_database_manager.db_manager.fetch_one(query)
    assert result is not None

    # scores テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores';"
    result = image_database_manager.db_manager.fetch_one(query)
    assert result is not None