from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from PySide6.QtCore import Qt

# テスト対象のモジュールをインポート
from lorairo.gui.window.edit import ImageEditWidget

# モック対象のクラス (実際のパスに合わせて調整が必要な場合あり)
# from lorairo.services.configuration_service import ConfigurationService
# from lorairo.services.image_processing_service import ImageProcessingService
# from lorairo.annotations.image_text_reader import ImageTextFileReader
# from lorairo.storage.file_system import FileSystemManager
# from lorairo.database.db_manager import ImageDatabaseManager
# from lorairo.gui.window.main_window import MainWindow


# --- Test Fixtures ---

# @pytest.fixture(scope="session")
# def qapp():
#     """PySide6 アプリケーションインスタンスを作成 (pytest-qt が自動で提供する場合が多い)"""
#     app = QApplication.instance()
#     if app is None:
#         app = QApplication(sys.argv)
#     return app


@pytest.fixture
def mock_services(mocker):
    """依存するサービスとマネージャのモックを作成"""
    mocks = {
        "config_service": mocker.MagicMock(name="ConfigurationService"),
        "fsm": mocker.MagicMock(name="FileSystemManager"),
        "idm": mocker.MagicMock(name="ImageDatabaseManager"),
        "image_processing_service": mocker.MagicMock(name="ImageProcessingService"),
        "image_text_reader": mocker.MagicMock(name="ImageTextFileReader"),
        "main_window": mocker.MagicMock(name="MainWindow"),
    }
    # メソッドのデフォルト戻り値を設定
    mocks["config_service"].get_image_processing_config.return_value = {
        "target_resolution": 512,
        "upscaler": "default_upscaler",
    }
    mocks["config_service"].get_preferred_resolutions.return_value = [512, 768]
    mocks["config_service"].get_upscaler_models.return_value = [
        {"name": "upscaler1"},
        {"name": "upscaler2"},
    ]
    mocks["config_service"].get_export_directory.return_value = Path("/fake/output")
    mocks["image_text_reader"].get_annotations_for_display.return_value = {
        "tags": ["tag1", "tag2"],
        "captions": ["caption1"],
    }
    mocks["main_window"].dataset_image_paths = []  # 初期は空リスト
    mocks["main_window"].some_long_process = mocker.MagicMock()  # some_long_process をモック

    # QPixmap と Path.stat のモック (ターゲットを edit モジュール内の QPixmap に変更)
    mock_qpixmap_class = mocker.patch("lorairo.gui.window.edit.QPixmap", autospec=True)
    mock_qpixmap_instance = mock_qpixmap_class.return_value
    mock_qpixmap_instance.height.return_value = 100
    mock_qpixmap_instance.width.return_value = 150
    mock_qpixmap_instance.scaled.return_value = mock_qpixmap_instance

    mocker.patch("pathlib.Path.stat", return_value=MagicMock(st_size=10240))

    return mocks


@pytest.fixture
def widget(qtbot, mock_services):
    """テスト対象の ImageEditWidget を初期化"""
    test_widget = ImageEditWidget()
    # initialize 前に ComboBox をクリアする
    test_widget.comboBoxUpscaler.clear()
    # モックを渡して初期化
    test_widget.initialize(
        config_service=mock_services["config_service"],
        file_system_manager=mock_services["fsm"],
        image_database_manager=mock_services["idm"],
        image_processing_service=mock_services["image_processing_service"],
        image_text_reader=mock_services["image_text_reader"],
        main_window=mock_services["main_window"],
    )
    qtbot.addWidget(test_widget)  # pytest-qt にウィジェットを登録
    return test_widget


# --- Test Cases ---


def test_initialize(widget, mock_services):
    """ウィジェットの初期化が正しく行われるかテスト"""
    # ConfigurationService から設定が読み込まれているか確認
    mock_services["config_service"].get_image_processing_config.assert_called_once()
    mock_services["config_service"].get_preferred_resolutions.assert_called_once()
    mock_services["config_service"].get_upscaler_models.assert_called_once()

    # comboBoxUpscaler にアイテムが追加されているか確認
    assert widget.comboBoxUpscaler.count() == 2
    assert widget.comboBoxUpscaler.itemText(0) == "upscaler1"
    assert widget.comboBoxUpscaler.itemText(1) == "upscaler2"

    # 初期値の確認
    assert widget.target_resolution == 512
    assert widget.preferred_resolutions == [512, 768]
    assert widget.upscaler is None


def test_load_images(widget, mock_services, mocker):
    """画像リストの読み込みとテーブル表示をテスト"""
    # モック画像パスリスト
    mock_image_paths = [Path("/fake/img1.png"), Path("/fake/img2.jpg"), Path("/fake/img3.webp")]
    widget.directory_images = mock_image_paths  # 直接セット (通常は MainWindow 経由)

    # _add_image_to_table と ImagePreview.load_image の呼び出しを追跡
    mock_load_preview = mocker.patch.object(widget.ImagePreview, "load_image", autospec=True)

    # load_images を実行
    widget.load_images(mock_image_paths)

    # テーブルがクリアされ、行数が設定されているか
    assert widget.tableWidgetImageList.rowCount() == len(mock_image_paths)
    # _add_image_to_table が各画像で呼び出されたか (これは内部実装なのでチェック不要かも)
    # assert mock_add_table.call_count == len(mock_image_paths)
    # assert mock_add_table.assert_has_calls([call(p) for p in mock_image_paths])
    # 最初の画像がプレビューにロードされたか (1回だけ)
    assert mock_load_preview.call_count == 1  # 修正
    mock_load_preview.assert_called_once_with(mock_image_paths[0])

    # comboBoxUpscaler にアイテムが追加されているか確認
    assert widget.comboBoxUpscaler.count() == 2
    assert widget.comboBoxUpscaler.itemText(0) == "upscaler1"
    assert widget.comboBoxUpscaler.itemText(1) == "upscaler2"


def test_add_image_to_table(widget, mock_services, mocker):
    """テーブルへの画像情報追加をテスト (_add_image_to_table)"""
    mock_path = Path("/fake/test.png")
    row_position = widget.tableWidgetImageList.rowCount()

    # QPixmap のモック設定はフィクスチャで行われる
    # QTableWidgetItem のモックは解除した

    # setItem をスパイする
    spy_set_item = mocker.spy(widget.tableWidgetImageList, "setItem")

    mock_services["image_text_reader"].get_annotations_for_display.return_value = {
        "tags": ["apple", "banana"],
        "captions": ["fruit basket"],
    }

    # _add_image_to_table を実行
    widget._add_image_to_table(mock_path)

    # 行が追加されたか
    assert widget.tableWidgetImageList.rowCount() == row_position + 1

    # 各セルの値を確認する代わりに setItem の呼び出しを確認
    # Thumbnail (Column 0) - QTableWidgetItem インスタンスが渡されることを確認
    # ファイル名 (Column 1)
    # パス (Column 2)
    # 解像度 (Column 3)
    # サイズ (Column 4)
    # タグ (Column 5)
    # キャプション (Column 6)
    expected_calls = [
        call(row_position, 0, mocker.ANY),  # Thumbnail: ANY で QTableWidgetItem インスタンスを期待
        call(row_position, 1, mocker.ANY),  # FileName
        call(row_position, 2, mocker.ANY),  # Path
        call(row_position, 3, mocker.ANY),  # Resolution
        call(row_position, 4, mocker.ANY),  # Size
        call(row_position, 5, mocker.ANY),  # Tags
        call(row_position, 6, mocker.ANY),  # Caption
    ]
    spy_set_item.assert_has_calls(expected_calls, any_order=False)

    # setItem の呼び出し回数も確認
    assert spy_set_item.call_count == 7

    # 必要であれば、特定の列の QTableWidgetItem のテキストを確認
    # 例: ファイル名
    item_filename = spy_set_item.call_args_list[1].args[2]  # 2番目の呼び出し(col 1)の第3引数
    assert item_filename.text() == "test.png"
    # 例: 解像度
    item_resolution = spy_set_item.call_args_list[3].args[2]  # 4番目の呼び出し(col 3)の第3引数
    assert item_resolution.text() == "100 x 150"
    # 例: タグ
    item_tags = spy_set_item.call_args_list[5].args[2]  # 6番目の呼び出し(col 5)の第3引数
    assert item_tags.text() == "apple, banana"
    # 例: キャプション
    item_caption = spy_set_item.call_args_list[6].args[2]  # 7番目の呼び出し(col 6)の第3引数
    assert item_caption.text() == "fruit basket"

    # AnnotationService が呼び出されたか確認
    mock_services["image_text_reader"].get_annotations_for_display.assert_called_once_with(mock_path)


def test_item_selection_changed(widget, qtbot, mocker):
    """テーブルアイテム選択時のプレビュー更新をテスト"""
    # ダミーデータをテーブルに追加
    mock_path1 = Path("/fake/select1.png")
    mock_path2 = Path("/fake/select2.png")
    widget.load_images([mock_path1, mock_path2])  # load_images を使うと _add_image_to_table が走る

    mock_load_preview = mocker.patch.object(widget.ImagePreview, "load_image", autospec=True)

    # 2行目を選択
    widget.tableWidgetImageList.setCurrentCell(1, 0)  # 2行目 (0-indexed) の最初の列を選択

    # シグナルが処理されるのを待つ (pytest-qt)
    # qtbot.waitSignals([widget.tableWidgetImageList.itemSelectionChanged]) # 直接シグナル待機は難しい場合がある

    # プレビューが更新されたか確認
    mock_load_preview.assert_called_with(mock_path2)  # 2行目のパス


def test_combobox_resize_option_changed(widget, qtbot, mock_services):
    """リサイズオプション変更時の動作をテスト"""
    # ダミーのアイテムを追加しておく (initialize で追加されていなければ)
    if widget.comboBoxResizeOption.count() == 0:
        widget.comboBoxResizeOption.addItems(["512x512", "768x768", "1024x1024"])

    # 2番目のアイテム (768x768) を選択
    qtbot.keyClicks(
        widget.comboBoxResizeOption, "768x768"
    )  # またはインデックスで設定 qtbot.selectItem(widget.comboBoxResizeOption, 1)

    # 値が更新されたか確認
    assert widget.target_resolution == 768
    # ConfigurationService が呼び出されたか確認
    mock_services["config_service"].update_image_processing_setting.assert_called_with(
        "target_resolution", 768
    )


def test_combobox_upscaler_changed(widget, qtbot, mock_services):
    """アップスケーラオプション変更時の動作をテスト"""
    # initialize でアイテムは追加済みのはず ("upscaler1", "upscaler2")

    # 2番目のアイテム ("upscaler2") を選択
    qtbot.keyClicks(
        widget.comboBoxUpscaler, "upscaler2"
    )  # またはインデックスで設定 qtbot.selectItem(widget.comboBoxUpscaler, 1)

    # 値が更新されたか確認
    assert widget.upscaler == "upscaler2"
    # ConfigurationService が呼び出されたか確認
    mock_services["config_service"].update_image_processing_setting.assert_called_with(
        "upscaler", "upscaler2"
    )


def test_start_processing_clicked_success(widget, qtbot, mock_services):
    """処理開始ボタンクリック時の正常系テスト"""
    # 処理対象の画像を設定
    mock_image_paths = [Path("/fake/process1.png")]
    widget.directory_images = mock_image_paths
    # アップスケーラを選択状態にする (setCurrentTextを使用)
    widget.comboBoxUpscaler.setCurrentText("upscaler1")

    # ボタンクリック
    qtbot.mouseClick(widget.pushButtonStartProcess, Qt.LeftButton)

    # MainWindow の some_long_process が呼び出されたか確認
    mock_services["main_window"].some_long_process.assert_called_once()
    # 呼び出し引数を確認
    args, kwargs = mock_services["main_window"].some_long_process.call_args
    assert args[0] == mock_services["image_processing_service"].process_images_in_list  # 第1引数は処理関数
    assert args[1] == mock_image_paths  # 第2引数は画像リスト
    assert kwargs.get("upscaler_override") == "upscaler1"  # kwargs でアップスケーラが渡されている


def test_start_processing_clicked_no_images(widget, qtbot, mock_services, mocker):
    """処理対象画像がない場合に警告が表示されるかテスト"""
    widget.directory_images = []  # 画像リストを空にする
    mock_messagebox = mocker.patch("PySide6.QtWidgets.QMessageBox.warning")

    qtbot.mouseClick(widget.pushButtonStartProcess, Qt.LeftButton)

    # 警告メッセージが表示されたか確認
    mock_messagebox.assert_called_once()
    # MainWindow の処理は呼ばれないはず
    mock_services["main_window"].some_long_process.assert_not_called()


# 他にエラーケース (Service未初期化、MainWindowなし) のテストも追加可能
