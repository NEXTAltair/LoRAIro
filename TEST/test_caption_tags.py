import pytest
from unittest.mock import MagicMock
from pathlib import Path
from caption_tags import ImageAnalyzer
from module.api_utils import APIClientFactory, APIError

@pytest.fixture
def mock_api_client():
    """
    モックされたAPIクライアントを提供するフィクスチャ。
    """
    mock_client = MagicMock()
    # generate_caption メソッドが呼ばれたときに、モックのレスポンスを返す
    mock_client.generate_caption.return_value = "tags: tag1, tag2, tag3\ncaption: A sample caption\nscore: 0.85"
    return mock_client

@pytest.fixture
def mock_api_client_factory(mock_api_client):
    """
    モックされたAPIClientFactoryを提供するフィクスチャ。
    """
    factory = MagicMock(spec=APIClientFactory)
    # get_api_client メソッドが呼ばれたときに、モックのAPIクライアントを返す
    factory.get_api_client.return_value = (mock_api_client, None)
    return factory

@pytest.fixture
def mock_models_config():
    """
    モックされたモデル設定を提供するフィクスチャ。
    """
    vision_models = {
        1: {'name': 'mock_model'}
    }
    return vision_models

def test_analyze_image(sample_images, mock_api_client_factory, mock_models_config):
    """
    ImageAnalyzer.analyze_image の正常系のテスト。
    """
    image_path = sample_images['rgb']

    # ImageAnalyzer のインスタンスを作成し、初期化
    analyzer = ImageAnalyzer()
    analyzer.initialize(mock_api_client_factory, mock_models_config)

    # analyze_image メソッドを呼び出し
    result = analyzer.analyze_image(image_path, model_id=1)

    # 期待される結果
    expected_tags = [{'tag': 'tag1', 'model_id': 1}, {'tag': 'tag2', 'model_id': 1}, {'tag': 'tag3', 'model_id': 1}]
    expected_captions = [{'caption': 'a sample caption', 'model_id': 1}]
    expected_score = {'score': 0.85, 'model_id': 1}

    # 結果の検証
    assert result['tags'] == expected_tags
    assert result['captions'] == expected_captions
    assert result['score'] == expected_score
    assert result['image_path'] == str(image_path)

    # モックされたAPIクライアントのメソッドが正しく呼び出されたか確認
    mock_api_client = mock_api_client_factory.get_api_client.return_value[0]
    mock_api_client.set_image_data.assert_called_with(image_path)
    mock_api_client.generate_caption.assert_called_with(image_path, 'mock_model')

def test_analyze_image_with_exception(sample_images, mock_api_client_factory, mock_models_config):
    """
    APIクライアントが例外を投げた場合の ImageAnalyzer.analyze_image のテスト。
    """
    image_path = sample_images['rgb']

    # generate_caption が APIError を投げるように設定
    mock_api_client = mock_api_client_factory.get_api_client.return_value[0]
    mock_api_client.generate_caption.side_effect = APIError("API error occurred")

    analyzer = ImageAnalyzer()
    analyzer.initialize(mock_api_client_factory, mock_models_config)

    result = analyzer.analyze_image(image_path, model_id=1)

    # エラーメッセージの検証
    assert 'error' in result
    assert result['error'] == 'API Error: API error occurred'
    assert result['image_path'] == str(image_path)

def test_get_existing_annotations(tmp_path):
    """
    ImageAnalyzer.get_existing_annotations のテスト。
    """
    # テスト用の画像ファイルを作成
    image_path = tmp_path / 'test_image.jpg'
    image_path.touch()  # 空のファイルを作成

    # タグとキャプションのファイルを作成
    tag_file = image_path.with_suffix('.txt')
    caption_file = image_path.with_suffix('.caption')

    with open(tag_file, 'w', encoding='utf-8') as f:
        f.write('tag1, tag2, tag3')

    with open(caption_file, 'w', encoding='utf-8') as f:
        f.write('A sample caption, another_caption')

    # アノテーションを取得
    annotations = ImageAnalyzer.get_existing_annotations(image_path)

    # 期待されるアノテーション
    expected_annotations = {
        'tags': ['tag1', ' tag2', ' tag3'],
        'captions': ['a sample caption', ' another caption']
    }

    # アノテーションの検証
    assert annotations == expected_annotations
    # test_imageのtextファイルを削除
    tag_file.unlink()
    caption_file.unlink()

def test_get_existing_annotations_no_files(tmp_path):
    """
    タグとキャプションファイルが存在しない場合の ImageAnalyzer.get_existing_annotations のテスト。
    """
    image_path = tmp_path / 'test_image.jpg'
    image_path.touch()

    annotations = ImageAnalyzer.get_existing_annotations(image_path)

    # アノテーションが存在しないことを確認
    assert annotations is None
