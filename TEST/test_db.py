import pytest
from pathlib import Path
from module.db import SQLiteManager, ImageRepository, ImageDatabaseManager
from unittest.mock import MagicMock, patch
import uuid

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

def test_sqlite_fetch_one(sqlite_manager):
    """単一行のデータ取得の確認"""
    query = "SELECT * FROM models WHERE name = ?"
    params = ('test_model',)
    result = sqlite_manager.fetch_one(query, params)
    assert result is not None
    assert result['name'] == 'test_model'
    assert result['type'] == 'test_type'
    assert result['provider'] == 'test_provider'

def test_add_original_image(sqlite_manager, sample_image_info):
    """オリジナル画像の追加とメタデータの取得"""
    repo = ImageRepository(sqlite_manager)
    image_id = repo.add_original_image(sample_image_info)
    assert isinstance(image_id, int)

    metadata = repo.get_image_metadata(image_id)
    assert metadata is not None
    for key, value in sample_image_info.items():
        assert metadata[key] == value

def test_duplicate_image(sqlite_manager, sample_image_info):
    """重複画像の検出と同一IDの返却確認"""
    repo = ImageRepository(sqlite_manager)
    image_id1 = repo.add_original_image(sample_image_info)
    image_id2 = repo.add_original_image(sample_image_info)  # 重複画像を追加
    assert image_id1 == image_id2  # 同じIDが返される

@patch('module.db.calculate_phash', return_value='mocked_phash')
def test_register_original_image(mock_calculate_phash, sqlite_manager, mock_file_system_manager, tmp_path):
    """オリジナル画像の登録処理"""
    manager = ImageDatabaseManager()
    manager.db_manager = sqlite_manager
    manager.repository = ImageRepository(sqlite_manager)

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

def test_register_processed_image(sqlite_manager, sample_image_info, tmp_path):
    """処理済み画像の登録とメタデータの確認"""
    manager = ImageDatabaseManager()
    manager.db_manager = sqlite_manager
    manager.repository = ImageRepository(sqlite_manager)

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

def test_save_annotations(sqlite_manager, sample_image_info):
    """アノテーションの保存と取得の確認"""
    repo = ImageRepository(sqlite_manager)
    image_id = repo.add_original_image(sample_image_info)

    annotations = {
        'tags': [{'tag': 'test_tag', 'model_id': None}],
        'captions': [{'caption': 'test_caption', 'model_id': None}],
        'scores': [{'score': 0.95, 'model_id': 1}]
    }

    repo.save_annotations(image_id, annotations)

    retrieved_annotations = repo.get_image_annotations(image_id)
    assert 'tags' in retrieved_annotations
    assert 'captions' in retrieved_annotations
    assert 'scores' in retrieved_annotations

    assert len(retrieved_annotations['tags']) == 1
    assert retrieved_annotations['tags'][0]['tag'] == 'test_tag'

    assert len(retrieved_annotations['captions']) == 1
    assert retrieved_annotations['captions'][0]['caption'] == 'test_caption'

    assert len(retrieved_annotations['scores']) == 1
    assert retrieved_annotations['scores'][0]['score'] == 0.95

def test_get_images_by_tag(sqlite_manager, sample_image_info):
    """タグによる画像検索の確認"""
    repo = ImageRepository(sqlite_manager)
    image_id = repo.add_original_image(sample_image_info)
    repo.save_annotations(image_id, {'tags': [{'tag': 'test_tag', 'model_id': None}]})

    image_ids = repo.get_images_by_tag('test_tag')
    assert image_id in image_ids

def test_get_images_by_caption(sqlite_manager, sample_image_info):
    """キャプションによる画像検索の確認"""
    repo = ImageRepository(sqlite_manager)
    image_id = repo.add_original_image(sample_image_info)
    repo.save_annotations(image_id, {'captions': [{'caption': 'test_caption', 'model_id': None}]})

    image_ids = repo.get_images_by_caption('test_caption')
    assert image_id in image_ids

def test_update_image_metadata(sqlite_manager, sample_image_info):
    """画像メタデータの更新の確認"""
    repo = ImageRepository(sqlite_manager)
    image_id = repo.add_original_image(sample_image_info)

    updated_info = {'width': 1024, 'height': 768}
    repo.update_image_metadata(image_id, updated_info)

    metadata = repo.get_image_metadata(image_id)
    assert metadata['width'] == 1024
    assert metadata['height'] == 768
    assert metadata['updated_at'] is not None

def test_delete_image(sqlite_manager_function, sample_image_info):
    """画像の削除と関連データの確認"""
    repo = ImageRepository(sqlite_manager_function)
    image_id = repo.add_original_image(sample_image_info)
    repo.save_annotations(image_id, {
        'tags': [
            {'tag': 'test_tag1', 'model_id': None},
            {'tag': 'test_tag2', 'model_id': 1},
            {'tag': 'test_tag3', 'model_id': 2}
        ],
        'captions': [
            {'caption': 'test_caption1', 'model_id': None},
            {'caption': 'test_caption2', 'model_id': 1},
            {'caption': 'test_caption3', 'model_id': 2}
        ],
        'scores': [{'score': 0.95, 'model_id': 1}]
    })

    # 削除前にアノテーションが存在することを確認
    annotations_before = repo.get_image_annotations(image_id)
    assert len(annotations_before['tags']) == 3
    assert len(annotations_before['captions']) == 3
    assert len(annotations_before['scores']) == 1

    repo.delete_image(image_id)

    # 画像が削除されたことを確認
    metadata = repo.get_image_metadata(image_id)
    assert metadata is None

    # 削除後はアノテーションが空になることを確認
    annotations_after = repo.get_image_annotations(image_id)
    assert len(annotations_after['tags']) == 0
    assert len(annotations_after['captions']) == 0
    assert len(annotations_after['scores']) == 0

def test_get_total_image_count(sqlite_manager_function, sample_image_info):
    """総画像数の取得の確認"""
    repo = ImageRepository(sqlite_manager_function)
    initial_count = repo.get_total_image_count()

    repo.add_original_image(sample_image_info)
    new_count = repo.get_total_image_count()
    assert new_count == initial_count + 1

def test_get_models(sqlite_manager):
    """モデル情報の取得の確認"""
    manager = ImageDatabaseManager()
    manager.db_manager = sqlite_manager
    manager.repository = ImageRepository(sqlite_manager)

    vision_models, score_models, upscaler_models = manager.get_models()
    assert isinstance(vision_models, dict)
    assert isinstance(score_models, dict)
    assert isinstance(upscaler_models, dict)
    assert len(vision_models) > 0

def test_get_images_by_filter(sqlite_manager, sample_image_info):
    """フィルタによる画像検索の確認"""
    manager = ImageDatabaseManager()
    manager.db_manager = sqlite_manager
    manager.repository = ImageRepository(sqlite_manager)

    image_id = manager.repository.add_original_image(sample_image_info)
    manager.repository.save_annotations(image_id, {'tags': [{'tag': 'filter_tag', 'model_id': None}]})

    filtered_images, count = manager.get_images_by_filter(tags=['filter_tag'])
    assert count == 1
    assert filtered_images[0]['image_id'] == image_id

def test_create_tables(sqlite_manager):
    """テーブル作成のテスト"""
    sqlite_manager.create_tables()

    # images テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='images';"
    result = sqlite_manager.fetch_one(query)
    assert result is not None

    # processed_images テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='processed_images';"
    result = sqlite_manager.fetch_one(query)
    assert result is not None

    # models テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='models';"
    result = sqlite_manager.fetch_one(query)
    assert result is not None

    # tags テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='tags';"
    result = sqlite_manager.fetch_one(query)
    assert result is not None

    # captions テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='captions';"
    result = sqlite_manager.fetch_one(query)
    assert result is not None

    # scores テーブルの存在を確認
    query = "SELECT name FROM sqlite_master WHERE type='table' AND name='scores';"
    result = sqlite_manager.fetch_one(query)
    assert result is not None