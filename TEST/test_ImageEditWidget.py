import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.ImageEditWidget import ImageEditWidget
from module.file_sys import FileSystemManager
from module.db import ImageDatabaseManager
from gui_file.ImageEditWidget_ui import Ui_ImageEditWidget

def test_initialization(app, mock_config_manager, mock_file_system_manager,
                         image_database_manager, mock_main_window):
    widget = ImageEditWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, image_database_manager, mock_main_window)

    assert widget.cm == mock_config_manager
    assert widget.idm == image_database_manager
    assert widget.fsm == mock_file_system_manager
    assert widget.main_window == mock_main_window
    assert widget.target_resolution == 512
    assert widget.preferred_resolutions == [512, 768, 1024]
    assert widget.comboBoxUpscaler.count() == len(mock_config_manager.upscaler_models) + 2 # 2は QtDesignerで設定した NoneとRealESRGAN_x4plus
    assert widget.comboBoxUpscaler.itemText(0) == 'None'
    assert widget.comboBoxUpscaler.itemText(1) == 'RealESRGAN_x4plus'
    assert widget.comboBoxUpscaler.itemText(2) == 'Lanczos'
    assert widget.comboBoxUpscaler.itemText(3) == 'Bicubic'

def test_load_images(app, mock_config_manager, mock_file_system_manager, image_database_manager, 
                     mock_main_window, mock_image_analyzer, sample_images):
    test_image_paths = [sample_images["rgb"], sample_images["rgb512"]]
    mock_config_manager.dataset_image_paths = test_image_paths

    # `widget` を先に作成
    widget = ImageEditWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, image_database_manager, mock_main_window)

    # ここで `widget.ImagePreview.load_image` をモック化
    with patch('src.ImageEditWidget.QPixmap') as mock_pixmap, \
         patch.object(widget.ImagePreview, 'load_image') as mock_load_image, \
         patch('pathlib.Path.stat') as mock_stat:

        mock_pixmap.return_value = MagicMock()
        mock_stat.return_value.st_size = 1024  # ファイルサイズをモック

        widget.load_images(test_image_paths)

        assert widget.directory_images == test_image_paths
        assert widget.tableWidgetImageList.rowCount() == len(test_image_paths)
        # 画像プレビューが正しくロードされたか確認
        mock_load_image.assert_called_with(test_image_paths[0])

def test_process_all_images(app, mock_config_manager, mock_file_system_manager,
                            mock_main_window, mock_image_processing_manager):
    # テスト用の画像パス
    test_image_paths = [Path('test_image1.png'), Path('test_image2.png')]

    # ウィジェットを初期化
    widget = ImageEditWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, None, mock_main_window)
    widget.ipm = mock_image_processing_manager
    widget.directory_images = test_image_paths

    # 必要な属性を設定
    widget.upscaler = 'Lanczos'  # 適切な値を設定
    widget.target_resolution = 512  # 適切な値を設定

    # widget.idmをMagicMockに置き換える
    widget.idm = MagicMock()

    # widget.idm上で呼び出されるメソッドをモック化
    widget.idm.get_image_id_by_name.return_value = None  # 画像IDがまだ存在しないと仮定
    widget.idm.register_original_image.return_value = (1, {'has_alpha': False, 'mode': 'RGB'})
    widget.idm.get_image_metadata.return_value = {'has_alpha': False, 'mode': 'RGB'}
    widget.idm.check_processed_image_exists.return_value = False
    widget.idm.save_annotations.return_value = None  # 必要に応じて追加

    # ImageAnalyzerのモック化
    with patch('src.ImageEditWidget.ImageAnalyzer.get_existing_annotations') as mock_get_existing_annotations:
        mock_get_existing_annotations.return_value = {'tags': [], 'captions': []}

        # ImageProcessingManagerのメソッドをモック化
        widget.ipm.process_image.return_value = 'processed_image_data'

        # 進行状況とステータスのコールバックをモック化
        progress_callback = MagicMock()
        status_callback = MagicMock()
        is_canceled = MagicMock(return_value=False)

        # テスト対象のメソッドを呼び出す
        widget.process_all_images(progress_callback=progress_callback, status_callback=status_callback, is_canceled=is_canceled)

    # メソッドが期待通りに呼び出されたかをアサート
    assert widget.idm.register_original_image.call_count == len(test_image_paths)
    assert widget.ipm.process_image.call_count == len(test_image_paths)
    progress_callback.assert_called()
    status_callback.assert_called()


def test_on_pushButtonStartProcess_clicked(app, mock_config_manager, mock_file_system_manager, mock_image_database_manager, mock_main_window):
    widget = ImageEditWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager, mock_main_window)
    widget.initialize_processing = MagicMock()
    widget.process_all_images = MagicMock()
    widget.main_window.some_long_process = MagicMock()

    widget.on_pushButtonStartProcess_clicked()

    assert widget.initialize_processing.call_count == 1
    assert widget.process_all_images.call_count == 1
    assert widget.main_window.some_long_process.call_count == 1
