import pytest
from pathlib import Path
from ImageTaggerWidget import ImageTaggerWidget

def test_initialization(app, mock_config_manager, mock_image_database_manager, mocker):
    # ウィジェットのインスタンスを作成
    widget = ImageTaggerWidget()
    
    # 外部依存関係をモック化
    widget.DirectoryPickerSave = mocker.Mock()
    widget.ThumbnailSelector = mocker.Mock()
    widget.dbSearchWidget = mocker.Mock()
    
    # ウィジェットを初期化
    widget.initialize(mock_config_manager, mock_image_database_manager)
    
    # 属性が正しく設定されていることを確認
    assert widget.cm == mock_config_manager
    assert widget.idm == mock_image_database_manager

    # vision_providersが正しく設定されていることを確認
    expected_vision_providers = list(set(model['provider'] for model in mock_config_manager.vision_models.values()))
    assert widget.vision_providers == expected_vision_providers

    # comboBoxAPIに正しいアイテムが追加されていることを確認
    actual_api_items = [widget.comboBoxAPI.itemText(i) for i in range(widget.comboBoxAPI.count())]
    assert actual_api_items == expected_vision_providers

    # comboBoxTagFormatに正しいアイテムが追加されていることを確認
    expected_formats = ["danbooru", "e621", "derpibooru"]
    actual_formats = [widget.comboBoxTagFormat.itemText(i) for i in range(widget.comboBoxTagFormat.count())]
    assert actual_formats == expected_formats

    # プロンプトが正しく設定されていることを確認
    assert widget.textEditMainPrompt.toPlainText() == mock_config_manager.config['prompts']['main']
    assert widget.textEditAddPrompt.toPlainText() == mock_config_manager.config['prompts']['additional']

def test_load_images(app, mock_config_manager, mock_image_database_manager, mocker, tmp_path):
    # サンプルのwebp画像を作成
    image1 = tmp_path / 'image1.webp'
    image1.touch()
    image2 = tmp_path / 'image2.webp'
    image2.touch()
    image_files = [image1, image2]

    # ウィジェットのインスタンスを作成
    widget = ImageTaggerWidget()
    
    # 外部依存関係をモック化
    widget.DirectoryPickerSave = mocker.Mock()
    widget.ImagePreview = mocker.Mock()
    widget.ThumbnailSelector = mocker.Mock()
    widget.ThumbnailSelector.load_images = mocker.Mock()
    widget.ThumbnailSelector.select_first_image = mocker.Mock()
    widget.dbSearchWidget = mocker.Mock()
    
    # ウィジェットを初期化
    widget.initialize(mock_config_manager, mock_image_database_manager)
    
    # 画像をロード
    widget.load_images(image_files)
    
    # all_webp_filesが正しく設定されていることを確認
    assert widget.all_webp_files == image_files

    # ThumbnailSelectorのload_imagesが正しく呼び出されていることを確認
    widget.ThumbnailSelector.load_images.assert_called_with(image_files)

    # サムネイルの最初の画像が選択されていることを確認
    widget.ThumbnailSelector.select_first_image.assert_called_once()

def test_on_pushButtonGenerate_clicked(app, mock_config_manager, mock_image_database_manager, mocker, tmp_path):
    # サンプルのwebp画像を作成
    image = tmp_path / 'image.webp'
    image.touch()
    image_files = [image]

    # ウィジェットのインスタンスを作成
    widget = ImageTaggerWidget()
    
    # 外部依存関係をモック化
    widget.DirectoryPickerSave = mocker.Mock()
    widget.ImagePreview = mocker.Mock()
    widget.ThumbnailSelector = mocker.Mock()
    widget.ThumbnailSelector.load_images = mocker.Mock()
    widget.ThumbnailSelector.select_first_image = mocker.Mock()
    widget.dbSearchWidget = mocker.Mock()
    
    # ImageAnalyzerとAPIClientFactoryをモック化
    mock_image_analyzer = mocker.patch('ImageTaggerWidget.ImageAnalyzer')
    mock_api_client_factory = mocker.patch('ImageTaggerWidget.APIClientFactory')
    mock_image_analyzer_instance = mock_image_analyzer.return_value
    mock_image_analyzer_instance.analyze_image.return_value = {
        'image_path': str(image),
        'tags': [{'tag': 'sample_tag'}],
        'captions': [{'caption': 'sample_caption'}],
        'score': {'score': 0.85}
    }

    # ウィジェットを初期化
    widget.initialize(mock_config_manager, mock_image_database_manager)
    
    # 選択された画像を設定
    widget.selected_webp = image_files

    # ボタンクリックのメソッドを呼び出し
    widget.on_pushButtonGenerate_clicked()
    
    # タグとキャプションが正しく設定されていることを確認
    assert widget.all_tags == ['sample_tag']
    assert widget.all_captions == ['sample_caption']

    # テキストエディットに正しく表示されていることを確認
    assert widget.textEditTags.toPlainText() == 'sample_tag'
    assert widget.textEditCaption.toPlainText() == 'sample_caption'

def test_on_pushButtonSave_clicked(app, mock_config_manager, mock_image_database_manager, mocker, tmp_path):
    # サンプルのwebp画像を作成
    image = tmp_path / 'image.webp'
    image.touch()
    image_files = [image]

    # ウィジェットのインスタンスを作成
    widget = ImageTaggerWidget()
    
    # 外部依存関係をモック化
    widget.DirectoryPickerSave = mocker.Mock()
    widget.DirectoryPickerSave.get_selected_path.return_value = str(tmp_path)
    widget.ImagePreview = mocker.Mock()
    widget.ThumbnailSelector = mocker.Mock()
    widget.ThumbnailSelector.load_images = mocker.Mock()
    widget.ThumbnailSelector.select_first_image = mocker.Mock()
    widget.dbSearchWidget = mocker.Mock()
    
    # FileSystemManagerのメソッドをモック化
    mock_fsm = mocker.patch('ImageTaggerWidget.FileSystemManager')
    mock_fsm.export_dataset_to_txt = mocker.Mock()
    mock_fsm.export_dataset_to_json = mocker.Mock()

    # ウィジェットを初期化
    widget.initialize(mock_config_manager, mock_image_database_manager)
    
    # 選択された画像と生成されたタグ・キャプションを設定
    widget.selected_webp = image_files
    widget.all_tags = ['sample_tag']
    widget.all_captions = ['sample_caption']
    widget.all_results = [{
        'image_path': str(image),
        'tags': [{'tag': 'sample_tag'}],
        'captions': [{'caption': 'sample_caption'}],
        'score': {'score': 0.85}
    }]

    # 保存オプションを設定
    widget.checkBoxText.setChecked(True)
    widget.checkBoxJson.setChecked(True)
    widget.checkBoxDB.setChecked(True)
    
    # ボタンクリックのメソッドを呼び出し
    widget.on_pushButtonSave_clicked()
    
    # FileSystemManagerのメソッドが正しく呼び出されたことを確認
    mock_fsm.export_dataset_to_txt.assert_called()
    mock_fsm.export_dataset_to_json.assert_called()

    # データベースに保存するメソッドが呼び出されたことを確認
    mock_image_database_manager.save_annotations.assert_called()
    mock_image_database_manager.save_score.assert_called()

def test_on_comboBoxAPI_currentIndexChanged(app, mock_config_manager, mock_image_database_manager, mocker):
    widget = ImageTaggerWidget()
    
    # 外部依存関係をモック化
    widget.DirectoryPickerSave = mocker.Mock()
    widget.ThumbnailSelector = mocker.Mock()
    widget.dbSearchWidget = mocker.Mock()
    
    # ウィジェットを初期化
    widget.initialize(mock_config_manager, mock_image_database_manager)
    
    # comboBoxAPIにアイテムを追加
    widget.comboBoxAPI.addItems(['Provider A', 'Provider B'])
    
    # モデルリストを設定
    mock_config_manager.vision_models = {
        'model1': {'name': 'Model One', 'provider': 'Provider A'},
        'model2': {'name': 'Model Two', 'provider': 'Provider B'},
        'model3': {'name': 'Model Three', 'provider': 'Provider A'}
    }
    
    # メソッドを呼び出し
    widget.on_comboBoxAPI_currentIndexChanged(0)
    
    # comboBoxModelに正しいモデルが追加されていることを確認
    expected_models = ['Model One', 'Model Three']
    actual_models = [widget.comboBoxModel.itemText(i) for i in range(widget.comboBoxModel.count())]
    assert actual_models == expected_models
