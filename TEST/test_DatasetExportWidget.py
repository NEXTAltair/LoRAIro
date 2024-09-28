import pytest
from pytestqt.qtbot import QtBot
from pathlib import Path
from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import Qt
from unittest.mock import MagicMock, patch
from DatasetExportWidget import DatasetExportWidget

def test_init_ui(qtbot, mock_config_manager, mock_file_system_manager, mock_image_database_manager):
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
    qtbot.addWidget(widget)

    widget.init_ui()
    widget.exportDirectoryPicker.set_label_text("Export Directory:")
    assert widget.exportDirectoryPicker.DirectoryPicker.labelPicker.text() == "Export Directory:"

def test_on_filter_applied(qtbot, mock_config_manager, mock_file_system_manager,
                           mock_image_database_manager, mocker):
    # テストケースを定義
    test_cases = [
        {
            'description': '検索結果がある場合',
            'filter_conditions': {
                'filter_type': 'tags',
                'filter_text': 'tag1, tag2',
                'resolution': 1024,
                'use_and': True,
            },
            'expected_tags': ['tag1', 'tag2'],
            'expected_caption': '',
            'expected_resolution': 1024,
            'expected_use_and': True,
            'filtered_image_metadata': [
                {
                    'id': 1,
                    'image_id': 1,
                    'stored_image_path': '/path/to/image1.jpg',
                    'width': 1024,
                    'height': 1024,
                    'mode': 'RGB',
                    'has_alpha': 0,
                    'filename': 'image1.jpg',
                    'color_space': 'RGB',
                    'icc_profile': 'Not present',
                    'created_at': '2024-09-26T20:21:08.451199',
                    'updated_at': '2024-09-26T20:21:08.451199'
                },
                {
                    'id': 2,
                    'image_id': 2,
                    'stored_image_path': '/path/to/image2.jpg',
                    'width': 1024,
                    'height': 1024,
                    'mode': 'RGB',
                    'has_alpha': 0,
                    'filename': 'image2.jpg',
                    'color_space': 'RGB',
                    'icc_profile': 'Not present',
                    'created_at': '2024-09-26T20:21:08.451199',
                    'updated_at': '2024-09-26T20:21:08.451199'
                }
            ],
            'list_count': 2,
            'expect_no_results': False
        },
        {
            'description': '検索結果がない場合',
            'filter_conditions': {
                'filter_type': 'tags',
                'filter_text': 'nonexistent_tag',
                'resolution': 1024,
                'use_and': True,
            },
            'expected_tags': ['nonexistent_tag'],
            'expected_caption': '',
            'expected_resolution': 1024,
            'expected_use_and': True,
            'filtered_image_metadata': [],
            'list_count': 0,
            'expect_no_results': True
        }
    ]

    for case in test_cases:
        # テストケースの説明を表示
        print(f"Testing case: {case['description']}")

        # ウィジェットのインスタンス化と初期化
        widget = DatasetExportWidget()
        widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
        qtbot.addWidget(widget)

        # get_images_by_filter の返り値を設定
        mock_image_database_manager.get_images_by_filter.return_value = (
            case['filtered_image_metadata'],
            case['list_count']
        )

        # update_thumbnail_selector をモック
        mock_update_thumbnail_selector = mocker.patch.object(widget, 'update_thumbnail_selector')

        # QMessageBox.critical をモック
        mock_critical = mocker.patch.object(QMessageBox, 'critical')

        # on_filter_applied を呼び出し
        widget.on_filter_applied(case['filter_conditions'])

        # get_images_by_filter が正しい引数で呼ばれたか確認
        mock_image_database_manager.get_images_by_filter.assert_called_with(
            tags=case['expected_tags'],
            caption=case['expected_caption'],
            resolution=case['expected_resolution'],
            use_and=case['expected_use_and']
        )

        if case['expect_no_results']:
            # 結果がない場合の検証
            assert widget.image_path_id_map == {}
            mock_update_thumbnail_selector.assert_not_called()
            mock_critical.assert_called_once_with(
                widget,
                "info",
                f"{case['filter_conditions']['filter_type']} に {case['filter_conditions']['filter_text']} を含む検索結果がありません"
            )
        else:
            # 結果がある場合の検証
            expected_image_path_id_map = {
                Path(item['stored_image_path']): item['id'] for item in case['filtered_image_metadata']
            }
            assert widget.image_path_id_map == expected_image_path_id_map

            # update_thumbnail_selector が正しく呼ばれたか確認
            mock_update_thumbnail_selector.assert_called_once_with(
                list(expected_image_path_id_map.keys()),
                case['list_count']
            )
            mock_critical.assert_not_called()

        # モックをリセット
        mock_image_database_manager.get_images_by_filter.reset_mock()
        mock_update_thumbnail_selector.reset_mock()
        mock_critical.reset_mock()

def test_on_exportButton_clicked_no_export_directory(qtbot, mock_config_manager, mock_file_system_manager, mock_image_database_manager, mocker):
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
    qtbot.addWidget(widget)

    # 出力ディレクトリを空に設定
    widget.exportDirectoryPicker.set_path("")

    with patch.object(QMessageBox, 'warning') as mock_warning:
        qtbot.mouseClick(widget.exportButton, Qt.LeftButton)
        mock_warning.assert_called_once()

def test_on_exportButton_clicked_no_export_formats(qtbot, mock_config_manager, mock_file_system_manager, mock_image_database_manager, mocker):
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
    qtbot.addWidget(widget)

    # 出力ディレクトリを設定
    widget.exportDirectoryPicker.set_path("/path/to/export")
    # 出力形式のチェックボックスをオフにする
    widget.checkBoxTxtCap.setChecked(False)
    widget.checkBoxJson.setChecked(False)

    with patch.object(QMessageBox, 'warning') as mock_warning:
        qtbot.mouseClick(widget.exportButton, Qt.LeftButton)
        mock_warning.assert_called_once()

@pytest.mark.parametrize(
    "selected_images, image_path_id_map, annotations_list, expect_warning, expect_critical, expect_information, expect_logger_warning",
    [
        # テストケース1: 正常なエクスポート
        (
            [Path('/path/to/image1.jpg'), Path('/path/to/image2.jpg')],
            {
                Path('/path/to/image1.jpg'): 1,
                Path('/path/to/image2.jpg'): 2
            },
            [
                {'tags': ['tag1', 'tag2'], 'captions': ['caption1']},
                {'tags': ['tag3', 'tag4'], 'captions': ['caption2']}
            ],
            False,  # expect_warning
            False,  # expect_critical
            True,   # expect_information
            False   # expect_logger_warning
        ),
        # テストケース2: image_path_id_map に存在しない画像パスがある
        (
            [Path('/path/to/image1.jpg'), Path('/path/to/image2.jpg')],
            {
                Path('/path/to/image1.jpg'): 1
                # image2.jpg のエントリーがない
            },
            [
                {'tags': ['tag1', 'tag2'], 'captions': ['caption1']}
                # annotations_list も1つだけ
            ],
            False,
            False,
            True,
            True  # image2.jpg のIDが見つからないので警告ログが出る
        ),
        # テストケース3: 選択された画像がない
        (
            [],
            {},
            [],
            True,   # expect_warning: 警告ダイアログが表示される
            False,
            False,
            False
        ),
        # テストケース4: エクスポート中に例外が発生
        (
            [Path('/path/to/image1.jpg')],
            {
                Path('/path/to/image1.jpg'): 1
            },
            Exception("Database error"),  # get_image_annotations が例外を投げる
            False,
            True,   # expect_critical: エラーダイアログが表示される
            False,
            False
        ),
    ]
)
def test_export_dataset(qtbot, mock_config_manager, mock_file_system_manager,
                        mock_image_database_manager, mocker,
                        selected_images, image_path_id_map, annotations_list,
                        expect_warning, expect_critical, expect_information, expect_logger_warning):
    # ウィジェットのインスタンス化と初期化
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
    qtbot.addWidget(widget)

    # GUI コンポーネントのモック設定
    widget.exportButton = mocker.Mock()
    widget.statusLabel = mocker.Mock()
    widget.exportProgressBar = mocker.Mock()
    widget.thumbnailSelector = mocker.Mock()

    # 選択された画像パスを設定
    widget.thumbnailSelector.get_selected_images.return_value = selected_images

    # image_path_id_map を設定
    widget.image_path_id_map = image_path_id_map

    # get_image_annotations の返り値を設定
    if isinstance(annotations_list, Exception):
        # 例外を発生させる
        mock_image_database_manager.get_image_annotations.side_effect = annotations_list
    else:
        mock_image_database_manager.get_image_annotations.side_effect = annotations_list

    # FileSystemManager のメソッドをモック
    mock_file_system_manager.export_dataset_to_txt = mocker.Mock()
    mock_file_system_manager.export_dataset_to_json = mocker.Mock()

    # QMessageBox のモック
    mock_warning = mocker.patch.object(QMessageBox, 'warning')
    mock_critical = mocker.patch.object(QMessageBox, 'critical')
    mock_information = mocker.patch.object(QMessageBox, 'information')

    # ロガーの警告をモック
    mock_logger_warning = mocker.patch.object(widget.logger, 'warning')

    # エクスポートディレクトリとフォーマットを設定
    export_dir = Path('/path/to/export')
    formats = ['txt_cap', 'json']

    # メソッドを実行
    widget.export_dataset(export_dir, formats)

    # 警告ダイアログの確認
    if expect_warning:
        mock_warning.assert_called_once_with(widget, "Warning", "出力する画像を選択してください")
    else:
        mock_warning.assert_not_called()

    # エラーダイアログの確認
    if expect_critical:
        mock_critical.assert_called_once()
    else:
        mock_critical.assert_not_called()

    # 情報ダイアログの確認
    if expect_information:
        mock_information.assert_called_once_with(widget, "Success", "Dataset export completed successfully.")
    else:
        mock_information.assert_not_called()

    # ロガーの警告の確認
    if expect_logger_warning:
        mock_logger_warning.assert_called()
    else:
        mock_logger_warning.assert_not_called()

    # エクスポートメソッドの呼び出し回数を確認
    if not expect_warning and not expect_critical:
        expected_call_count = len(image_path_id_map)
        assert mock_file_system_manager.export_dataset_to_txt.call_count == expected_call_count * (1 if 'txt_cap' in formats else 0)
        assert mock_file_system_manager.export_dataset_to_json.call_count == expected_call_count * (1 if 'json' in formats else 0)
    else:
        mock_file_system_manager.export_dataset_to_txt.assert_not_called()
        mock_file_system_manager.export_dataset_to_json.assert_not_called()

def test_on_exportButton_clicked_no_export_directory(qtbot, mock_config_manager, mock_file_system_manager, mock_image_database_manager, mocker):
    # ウィジェットのインスタンス化
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)

    # GUI コンポーネントのモック設定
    widget.exportDirectoryPicker = mocker.Mock()
    widget.exportDirectoryPicker.get_selected_path.return_value = ''

    # QMessageBox の警告をモック（コンテキストマネージャーを使用しない）
    mock_warning = mocker.patch.object(QMessageBox, 'warning')

    # エクスポートボタンのクリックをシミュレート
    widget.on_exportButton_clicked()

    # 警告ダイアログが表示されたか確認
    mock_warning.assert_called_once_with(widget, "Warning", "出力先ディレクトリを選択してください")

def test_update_thumbnail_selector(qtbot, mock_config_manager, mock_file_system_manager, mock_image_database_manager, mocker):
    # DatasetExportWidget のインスタンスを作成し、必要なマネージャーを初期化
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
    qtbot.addWidget(widget)

    # サムネイルセレクターとラベルをモック化
    widget.thumbnailSelector = mocker.Mock()
    widget.thumbnailSelector.load_images = mocker.Mock()
    widget.thumbnailSelector.get_selected_images.return_value = [Path("/path/to/image1.jpg"), Path("/path/to/image2.jpg")]
    widget.imageCountLabel = mocker.Mock()

    # get_total_image_count の戻り値を設定
    mock_image_database_manager.get_total_image_count.return_value = 100

    # テスト用の画像パスとリスト数を設定
    image_paths = [Path("/path/to/image1.jpg"), Path("/path/to/image2.jpg")]
    list_count = 2

    # update_thumbnail_selector メソッドを実行
    widget.update_thumbnail_selector(image_paths, list_count)

    # load_images メソッドが正しく呼び出されたか確認
    widget.thumbnailSelector.load_images.assert_called_once_with(image_paths)

    # サムネイルセレクターから選択された画像を取得し、正しい数か確認
    selected_images = widget.thumbnailSelector.get_selected_images()
    assert len(selected_images) == 2

    # 画像数のラベルが正しく更新されたか確認
    widget.imageCountLabel.setText.assert_called_once_with(f"Selected Images: {list_count} / Total Images: 100")

def test_update_image_count_label(qtbot, mock_config_manager, mock_file_system_manager, mock_image_database_manager):
    widget = DatasetExportWidget()
    widget.initialize(mock_config_manager, mock_file_system_manager, mock_image_database_manager)
    qtbot.addWidget(widget)

    count = 10
    total = 100

    mock_image_database_manager.get_total_image_count.return_value = total

    widget.update_image_count_label(count)

    assert widget.imageCountLabel.text() == f"Selected Images: {count} / Total Images: {total}"
