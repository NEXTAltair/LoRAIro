import pytest
from pathlib import Path
from module.db import SQLiteManager, ImageRepository, ImageDatabaseManager
from unittest.mock import MagicMock, patch
from module.log import get_logger
import uuid
from datetime import datetime, timezone, timedelta
import time

@pytest.fixture
def test_db_paths(tmp_path):
    img_db = tmp_path / f"test_image_database_{uuid.uuid4()}.db"
    tag_db = Path("src/module/genai-tag-db-tools/tags_v3.db") #テストによる変更がないので実際のパスを使用
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

@pytest.fixture
def image_database_manager(sqlite_manager):
    # ハードコーディングされたパスをテスト用データベースに変更するためパッチ
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

def test_sqlite_fetch_one(sqlite_manager):
    """単一行のデータ取得の確認"""
    query = "SELECT * FROM models WHERE name = ?"
    params = ('gpt-4o',)
    result = sqlite_manager.fetch_one(query, params)
    # 確認するパラメーターはsrc.module.db.SQLiteManager.insert_modelsで追加されたもの
    assert result is not None
    assert result['name'] == 'gpt-4o'
    assert result['type'] == 'vision'
    assert result['provider'] == 'OpenAI'

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

def assert_annotations(retrieved, expected, model_id, case_index, repository):
    if 'tags' in expected:
        assert len(retrieved['tags']) >= len(expected['tags']), f"Case {case_index}: タグの数が一致しません"
        for tag in expected['tags']:
            matching_tags = [t for t in retrieved['tags'] if t['tag'] == tag]
            assert matching_tags, f"Case {case_index}: タグ '{tag}' が見つかりません"
            matching_tag = next((t for t in matching_tags if t['model_id'] == model_id), None)
            assert matching_tag is not None, f"Case {case_index}: タグ '{tag}' に期待される model_id が見つかりません"
            assert matching_tag['model_id'] == model_id, f"Case {case_index}: タグ '{tag}' のmodel_idが一致しません"
            expected_tag_id = repository.find_tag_id(tag)
            assert matching_tags[0]['tag_id'] == expected_tag_id, f"Case {case_index}: タグ '{tag}' のtag_idが一致しません"
            if tag == 'spiked collar':
                assert expected_tag_id == 1, f"Case {case_index}: 'spiked collar' のtag_idが1ではありません"
            
            # 新しい検証: updated_at が現在時刻に近いことを確認
            assert (datetime.now(timezone.utc) - datetime.fromisoformat(matching_tags[0]['updated_at']).replace(tzinfo=timezone.utc)) < timedelta(seconds=100), \
                f"Case {case_index}: タグ '{tag}' のupdated_atが最新ではありません"

    if 'captions' in expected:
        assert len(retrieved['captions']) >= len(expected['captions']), f"Case {case_index}: キャプションの数が一致しません"
        for caption in expected['captions']:
            matching_captions = [c for c in retrieved['captions'] if c['caption'] == caption]
            assert matching_captions, f"Case {case_index}: キャプション '{caption}' が見つかりません"
            assert matching_captions[0]['model_id'] == model_id, f"Case {case_index}: キャプション '{caption}' のmodel_idが一致しません"

    if 'score' in expected:
        matching_scores = [s for s in retrieved['scores'] if s['score'] == expected['score']]
        assert matching_scores, f"Case {case_index}: スコア {expected['score']} が見つかりません"
        assert matching_scores[0]['model_id'] == model_id, f"Case {case_index}: スコア {expected['score']} のmodel_idが一致しません"

def test_save_annotations(image_database_manager, sample_image_info):
    """アノテーションの保存、取得、更新の確認、欠損値のテストを含む"""
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)

    test_cases = [
        {
            'tags': ['spiked collar', 'tag1', 'tag2'],
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
        },
        {
            'tags': ['spiked collar'], #tags_v3に存在するidを登録
        }
    ]

    for index, case in enumerate(test_cases, start=1):
        manager.repository.save_annotations(image_id, case)

        retrieved = manager.repository.get_image_annotations(image_id)

        current_model_id = case.get('model_id')

        assert_annotations(retrieved, case, current_model_id, index, manager.repository)

    # タグの再登録のテスト
    time.sleep(1)  # updated_at の変更を確実に検出するため
    reregister_case = {
        'tags': ['spiked collar', 'tag1'],
        'model_id': 4
    }
    manager.repository.save_annotations(image_id, reregister_case)
    retrieved = manager.repository.get_image_annotations(image_id)

    # 再登録されたタグの検証
    for tag in reregister_case['tags']:
        matching_tags = [t for t in retrieved['tags'] if t['tag'] == tag]
        assert len(matching_tags) > 1, f"再登録: タグ '{tag}' の追加が行われませんでした"

        # 新しく追加されたタグの検証
        new_matching_tag = next((t for t in matching_tags if t['model_id'] == 4), None)
        assert new_matching_tag is not None, f"再登録: タグ '{tag}' に新しい model_id が見つかりません"
        assert (datetime.now(timezone.utc) - datetime.fromisoformat(new_matching_tag['updated_at']).replace(tzinfo=timezone.utc)) < timedelta(seconds=100), \
            f"再登録: タグ '{tag}' の updated_at が更新されていません"

    # 他のタグが影響を受けていないことを確認
    other_tags = [t for t in retrieved['tags'] if t['tag'] not in reregister_case['tags']]
    for tag in other_tags:
        assert tag['model_id'] != 4, f"再登録: 他のタグ '{tag['tag']}' のmodel_idが誤って更新されています"

def test_find_tag_id(image_database_manager, sample_image_info):
    """
    アタッチしたsrc.module.genai-tag-db-toolsのタグデータベースから登録されたタグIDを取得する
    """
    manager = image_database_manager
    image_id = manager.repository.add_original_image(sample_image_info)
    manager.repository.save_annotations(image_id, {'tags': ['spiked collar'], 'model_id': None})

    tag_id = manager.repository.find_tag_id('spiked collar')
    assert tag_id == 1

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

from datetime import datetime

@pytest.fixture
def setup_test_data(image_database_manager, sample_image_info, tmp_path):
    manager = image_database_manager

    # テスト用の画像データを作成
    image_data = [
        {"tags": ["cat", "cute"], "caption": "A cute cat playing"},
        {"tags": ["dog", "playful"], "caption": "A playful dog in the park"},
        {"tags": ["cat", "sleeping"], "caption": "A cat sleeping on a couch"},
        {"tags": ["bird", "flying"], "caption": "A bird flying in the sky"},
        {"tags": ["catfish", "swimming"], "caption": "A catfish swimming in a pond"}
    ]

    image_ids = []
    for idx, data in enumerate(image_data):
        # 直接SQLでオリジナル画像を追加（phashチェックを避けるため）
        query = """
        INSERT INTO images (uuid, stored_image_path, width, height, format, mode, has_alpha, filename,
                            extension, color_space, icc_profile, phash, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        created_at = datetime.now().isoformat()
        params = (
            str(uuid.uuid4()),  # uuid
            f"image_path_{idx}.jpg",  # stored_image_path
            256,  # width
            256,  # height
            "WEBP",  # format
            "RGB",  # mode
            False,  # has_alpha
            f'image_{idx}.jpg',  # filename
            'webp',  # extension
            'sRGB',  # color_space
            None,  # icc_profile
            f'unique_phash_{idx}',  # phash
            created_at,  # created_at
            created_at   # updated_at
        )
        cursor = manager.db_manager.execute(query, params)
        image_id = cursor.lastrowid
        image_ids.append(image_id)
        # 処理済み画像を登録
        processed_info = {
            'width': 256,
            'height': 256,
            'format': 'WEBP',
            'mode': 'RGB',
            'has_alpha': False,
            'filename': f'processed_{idx}.webp',
            'color_space': 'sRGB',
            'icc_profile': None
        }
        processed_path = tmp_path / f"processed_{idx}.webp"
        processed_path.touch()
        manager.register_processed_image(image_id, processed_path, processed_info)

        # アノテーションを保存
        manager.repository.save_annotations(image_id, {
            'tags': data['tags'],
            'captions': [data['caption']],
            'model_id': None
        })

    return manager, image_ids

test_cases = [
    # テストケース1: 完全一致タグ検索
    {
        "description": "完全一致タグ検索",
        "tags": ['"cat"'],
        "caption": None,
        "expected_count": 2,
        "expected_ids": lambda ids: {ids[0], ids[2]}
    },
    # テストケース1.1: 部分一致タグ検索
    {
        "description": "部分一致タグ検索",
        "tags": ['cat'],
        "caption": None,
        "expected_count": 3,
        "expected_ids": lambda ids: {ids[0], ids[2], ids[4]}
    },
    # テストケース2: ワイルドカードタグ検索
    {
        "description": "ワイルドカードタグ検索",
        "tags": ['cat*'],
        "caption": None,
        "expected_count": 3,
        "expected_ids": lambda ids: {ids[0], ids[2], ids[4]}
    },
    # テストケース3: AND検索
    {
        "description": "AND検索",
        "tags": ['cat', 'cute'],
        "caption": None,
        "use_and": True,
        "expected_count": 1,
        "expected_ids": lambda ids: {ids[0]}
    },
    # テストケース4: OR検索
    {
        "description": "OR検索",
        "tags": ['dog', 'bird'],
        "caption": None,
        "use_and": False,
        "expected_count": 2,
        "expected_ids": lambda ids: {ids[1], ids[3]}
    },
    # テストケース5: 部分一致キャプション検索
    {
        "description": "部分一致キャプション検索",
        "tags": None,
        "caption": 'sleeping',
        "expected_count": 1,
        "expected_ids": lambda ids: {ids[2]}
    },
    # テストケース6: ワイルドカードキャプション検索
    {
        "description": "ワイルドカードキャプション検索",
        "tags": None,
        "caption": '* in *',
        "expected_count": 3,
        "expected_ids": lambda ids: {ids[1], ids[3], ids[4]}
    },
    # テストケース7: タグとキャプションの組み合わせ検索
    {
        "description": "タグとキャプションの組み合わせ検索",
        "tags": ['cat*'],
        "caption": '*ing*',
        "expected_count": 3,
        "expected_ids": lambda ids: {ids[0], ids[2], ids[4]}
    },
    # テストケース8: 存在しないタグでの検索
    {
        "description": "存在しないタグでの検索",
        "tags": ['nonexistent'],
        "caption": None,
        "expected_count": 0,
        "expected_ids": lambda ids: set()
    },
    # テストケース9: 空のタグリストでの検索
    {
        "description": "空のタグリストでの検索",
        "tags": [],
        "caption": None,
        "expected_count": 0,
        "expected_ids": lambda ids: None
    },
    # テストケース10: 解像度フィルタ
    {
        "description": "解像度フィルタ",
        "tags": ['cat'],
        "caption": None,
        "resolution": 256,
        "expected_count": 3,
        "expected_ids": lambda ids: {ids[0], ids[2], ids[4]}
    },
    # エッジケース1: タグが存在しない
    {
        "description": "エッジケース - 存在しないタグ",
        "tags": ['nonexistent'],
        "caption": None,
        "expected_count": 0,
        "expected_ids": lambda ids: set()
    },
    # エッジケース2: タグと存在しないタグのAND検索
    {
        "description": "エッジケース - タグと存在しないタグのAND検索",
        "tags": ['cat', 'nonexistent'],
        "caption": None,
        "use_and": True,
        "expected_count": 0,
        "expected_ids": lambda ids: set()
    },
    # エッジケース3: 存在しないキャプション
    {
        "description": "エッジケース - 存在しないキャプション",
        "tags": None,
        "caption": 'nonexistent',
        "expected_count": 0,
        "expected_ids": lambda ids: set()
    },
    # エッジケース4: ワイルドカードタグ検索で全ての画像を取得
    {
        "description": "エッジケース - ワイルドカードタグ検索で全ての画像を取得",
        "tags": ['*'],
        "caption": None,
        "expected_count": 5,
        "expected_ids": lambda ids: set(ids)
    },
    # エッジケース5: ワイルドカードキャプション検索で全ての画像を取得
    {
        "description": "エッジケース - ワイルドカードキャプション検索で全ての画像を取得",
        "tags": None,
        "caption": '*',
        "expected_count": 5,
        "expected_ids": lambda ids: set(ids)
    },
]

@pytest.mark.parametrize("case", test_cases)
def test_get_images_by_filter_cases(setup_test_data, case):
    """フィルタリングのテストケース"""
    manager, image_ids = setup_test_data
    description = case.get("description")
    tags = case.get("tags")
    caption = case.get("caption")
    resolution = case.get("resolution", 0)
    use_and = case.get("use_and", True)
    expected_count = case.get("expected_count")
    expected_ids = case.get("expected_ids")(image_ids)

    filtered_images, count = manager.get_images_by_filter(
        tags=tags, caption=caption, resolution=resolution, use_and=use_and
    )

    assert count == expected_count, f"{description} - 期待される画像数と一致しません"
    # None が返ってくる場合に備える
    if filtered_images is None:
        assert expected_ids is None, f"{description} - 期待される画像IDと一致しません"
    else:
        actual_ids = set(img['image_id'] for img in filtered_images)
        assert actual_ids == expected_ids, f"{description} - 期待される画像IDと一致しません"

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

    # アノテーションを保存（タグの updated_at が更新される）
    manager.repository.save_annotations(image_id, {'tags': ['filter_tag'], 'model_id': None})

    # タグの updated_at を確認する
    rows = manager.db_manager.fetch_all(
        "SELECT created_at, updated_at FROM tags WHERE image_id = ?", [image_id]
    )
    for row in rows:
        print(f"Tag created_at: {row['created_at']}, updated_at: {row['updated_at']}")

    # 現在の日時をUTCで取得
    current_datetime = datetime.now(timezone.utc)

    # 日付範囲を設定
    start_date = (current_datetime - timedelta(seconds=10)).strftime('%Y-%m-%d %H:%M:%S')  # 10秒前
    end_date = (current_datetime + timedelta(seconds=10)).strftime('%Y-%m-%d %H:%M:%S')    # 10秒後

    filtered_images, count = manager.get_images_by_filter(
        tags=['filter_tag'],
        start_date=start_date,
        end_date=end_date
    )

    assert count == 1, f"Expected 1 image, but got {count}"
    assert filtered_images[0]['image_id'] == image_id

    # 時間範囲外の画像を検索（マッチしないはず）
    past_start_date = (current_datetime - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')  # 1日前
    past_end_date = (current_datetime - timedelta(hours=23)).strftime('%Y-%m-%d %H:%M:%S')   # 1日前+1時間

    filtered_images, count = manager.get_images_by_filter(
        tags=['filter_tag'],
        start_date=past_start_date,
        end_date=past_end_date
    )

    assert count == 0, f"Expected 0 images, but got {count}"
    assert len(filtered_images) == 0

def test_create_tables(image_database_manager):
    """テーブル作成のテストとカラムの存在確認"""
    manager = image_database_manager
    manager.db_manager.create_tables()

    # テーブルとそのカラムの定義
    table_definitions = {
        'images': [
            'id', 'uuid', 'phash', 'stored_image_path', 'width', 'height', 'format',
            'mode', 'has_alpha', 'filename', 'extension', 'color_space',
            'icc_profile', 'created_at', 'updated_at'
        ],
        'processed_images': [
            'id', 'image_id', 'stored_image_path', 'width', 'height', 'mode',
            'has_alpha', 'filename', 'color_space', 'icc_profile',
            'created_at', 'updated_at'
        ],
        'models': [
            'id', 'name', 'type', 'provider', 'created_at', 'updated_at'
        ],
        'tags': [
            'id', 'tag_id', 'image_id', 'model_id', 'tag', 'existing',
            'created_at', 'updated_at'
        ],
        'captions': [
            'id', 'image_id', 'model_id', 'caption', 'existing',
            'created_at', 'updated_at'
        ],
        'scores': [
            'id', 'image_id', 'model_id', 'score',
            'created_at', 'updated_at'
        ]
    }

    for table, expected_columns in table_definitions.items():
        # テーブルの存在を確認
        query = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';"
        result = manager.db_manager.fetch_one(query)
        assert result is not None, f"テーブル '{table}' が存在しません。"

        # テーブルのカラムを取得
        query = f"PRAGMA table_info({table});"
        columns_info = manager.db_manager.fetch_all(query)
        existing_columns = {col['name'] for col in columns_info}

        # 期待されるカラムがすべて存在するか確認
        for column in expected_columns:
            assert column in existing_columns, f"テーブル '{table}' にカラム '{column}' が存在しません。"
