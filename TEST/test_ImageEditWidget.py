import pytest
from pytestqt.qtbot import QtBot
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from pathlib import Path

from src.ImageEditWidget import ImageEditWidget

@pytest.fixture
def widget(qtbot, mocker):
    mock_cm = mocker.Mock()
    mock_fsm = mocker.Mock()
    mock_idm = mocker.Mock()
    mock_main_window = mocker.Mock()

    mock_cm.config = {
        'image_processing': {'target_resolution': 512},
        'preferred_resolutions': [512, 768, 1024]
    }
    mock_cm.upscaler_models = {
        '1': {'name': 'Lanczos', 'provider': '01'},
        '2': {'name': 'Bicubic', 'provider': '02'}
    }

    widget = ImageEditWidget()
    widget.initialize(mock_cm, mock_fsm, mock_idm, mock_main_window)
    qtbot.addWidget(widget)
    return widget

def test_initialization(widget):
    assert widget.target_resolution == 512
    assert widget.preferred_resolutions == [512, 768, 1024]
    assert widget.comboBoxUpscaler.count() == 4
    assert [widget.comboBoxUpscaler.itemText(i) for i in range(4)] == ['None', 'RealESRGAN_x4plus', 'Lanczos', 'Bicubic']

@pytest.mark.parametrize("test_images", [
    [Path('test_image1.png'), Path('test_image2.png')],
    [Path('test_image3.jpg')]
])
def test_load_images(widget, mocker, test_images):
    mock_load_image = mocker.patch.object(widget.ImagePreview, 'load_image')
    mock_pixmap = mocker.patch('src.ImageEditWidget.QPixmap')
    mock_stat = mocker.patch('pathlib.Path.stat')

    mock_pixmap.return_value = mocker.Mock()
    mock_stat.return_value.st_size = 1024

    widget.load_images(test_images)

    assert widget.directory_images == test_images
    assert widget.tableWidgetImageList.rowCount() == len(test_images)
    mock_load_image.assert_called_with(test_images[0])

def test_process_all_images(widget, mocker):
    test_image_paths = [Path('test_image1.png'), Path('test_image2.png')]
    widget.directory_images = test_image_paths
    widget.upscaler = 'Lanczos'
    widget.target_resolution = 512

    mock_get_existing_annotations = mocker.patch('src.ImageEditWidget.ImageAnalyzer.get_existing_annotations', return_value={'tags': [], 'captions': []})
    mock_process_image = mocker.patch.object(widget.ipm, 'process_image', return_value='processed_image_data')

    # idm のモックを明示的に設定
    widget.idm = mocker.Mock()
    widget.idm.get_image_id_by_name.return_value = None  # 画像IDが存在しないと仮定
    widget.idm.register_original_image.return_value = (1, {'has_alpha': False, 'mode': 'RGB'})

    progress_callback = mocker.Mock()
    status_callback = mocker.Mock()
    is_canceled = mocker.Mock(return_value=False)

    widget.process_all_images(progress_callback=progress_callback, status_callback=status_callback, is_canceled=is_canceled)

    assert widget.idm.register_original_image.call_count == len(test_image_paths)

def test_on_pushButtonStartProcess_clicked(widget, mocker):
    mock_initialize_processing = mocker.patch.object(widget, 'initialize_processing')
    mock_process_all_images = mocker.patch.object(widget, 'process_all_images')
    mock_some_long_process = mocker.patch.object(widget.main_window, 'some_long_process', side_effect=lambda func: func())

    widget.on_pushButtonStartProcess_clicked()

    mock_initialize_processing.assert_called_once()
    mock_process_all_images.assert_called_once()
    mock_some_long_process.assert_called_once()

def test_on_pushButtonStartProcess_clicked_error(widget, mocker):
    mocker.patch.object(widget, 'initialize_processing', side_effect=Exception("Test error"))
    mock_error_dialog = mocker.patch('PySide6.QtWidgets.QMessageBox.critical')

    widget.on_pushButtonStartProcess_clicked()

    mock_error_dialog.assert_called_once()