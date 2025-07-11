"""
MainWindow ディレクトリ処理における 512px 画像生成の統合テスト

このテストは以下の流れを検証します:
1. MainWindow でディレクトリを指定
2. バッチ処理の開始
3. 512px 画像が正常に生成されること
4. データベースに正しく登録されること
5. ensure_512px_image() メソッドが動作すること
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from lorairo.database.db_core import DefaultSessionLocal
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.gui.window.main_window import MainWindow
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def temp_image_dir():
    """テスト用の一時ディレクトリと画像ファイルを作成"""
    temp_dir = Path(tempfile.mkdtemp())

    # テスト用画像を作成 (600x400 サイズ - 512px未満なのでアップスケールが必要)
    test_image_path = temp_dir / "test_image.jpg"
    image = Image.new("RGB", (600, 400), color="red")
    image.save(test_image_path, "JPEG")

    # 追加のテスト画像も作成
    test_image2_path = temp_dir / "test_image2.png"
    image2 = Image.new("RGB", (800, 600), color="blue")
    image2.save(test_image2_path, "PNG")

    yield temp_dir

    # クリーンアップ
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_database_dir():
    """テスト用のデータベースディレクトリを作成"""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_config_service(temp_database_dir):
    """テスト用の ConfigurationService"""
    with patch("lorairo.services.configuration_service.ConfigurationService") as mock_config:
        config_instance = mock_config.return_value

        # データベース関連の設定
        config_instance.get_database_directory.return_value = temp_database_dir
        config_instance.get_setting.side_effect = lambda section, key, default=None: {
            ("directories", "database_base_dir"): str(temp_database_dir.parent),
            ("directories", "dataset"): "",
        }.get((section, key), default)

        # 画像処理設定
        config_instance.get_image_processing_config.return_value = {"upscaler": "RealESRGAN_x4plus"}

        config_instance.update_setting = MagicMock()

        yield config_instance


class TestMainWindow512pxGeneration:
    """MainWindow の 512px 画像生成統合テスト"""

    @pytest.fixture(autouse=True)
    def setup_app(self, qapp):
        """各テストでアプリケーションをセットアップ"""
        self.app = qapp

    @patch("lorairo.services.batch_processor.process_directory_batch")
    @patch("lorairo.editor.image_processor.Upscaler.upscale_image")
    def test_directory_processing_with_512px_generation(
        self, mock_upscale, mock_batch_processor, temp_image_dir, temp_database_dir, test_config_service
    ):
        """ディレクトリ処理で512px画像が生成されることをテスト"""

        # Upscaler のモックを設定
        def mock_upscale_func(img, model_name):
            # 単純に2倍にリサイズして返す
            return img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)

        mock_upscale.side_effect = mock_upscale_func

        # バッチ処理のモック設定
        def mock_batch_process(directory_path, config_service, fsm, idm):
            """バッチ処理をシミュレート"""
            # 実際の画像処理を実行
            for image_file in fsm.get_image_files(directory_path):
                result = idm.register_original_image(image_file, fsm)
                assert result is not None, f"画像登録が失敗しました: {image_file}"

        mock_batch_processor.side_effect = mock_batch_process

        with patch.object(test_config_service, "get_database_directory", return_value=temp_database_dir):
            # MainWindow を作成
            main_window = MainWindow()
            main_window.config_service = test_config_service

            # FileSystemManager を初期化
            main_window.fsm.initialize(temp_database_dir)

            try:
                # プログレスウィジェットのモック
                with (
                    patch.object(main_window.progress_widget, "show"),
                    patch.object(main_window.progress_controller, "start_process") as mock_start,
                ):
                    # start_process が呼ばれた時に直接バッチ処理を実行
                    def execute_batch_immediately(*args, **kwargs):
                        if args and callable(args[0]):
                            batch_func = args[0]
                            batch_args = args[1:]
                            batch_func(*batch_args, **kwargs)
                            # 完了コールバックを呼び出し
                            main_window.on_batch_completed(temp_image_dir)

                    mock_start.side_effect = execute_batch_immediately

                    # ディレクトリ変更をトリガー
                    main_window.dataset_dir_changed(str(temp_image_dir))

                    # バッチ処理が呼ばれたことを確認
                    mock_batch_processor.assert_called_once()
                    mock_start.assert_called_once()

                    # データベースから画像が取得できることを確認
                    image_ids = main_window.idm.get_image_ids_from_directory(temp_image_dir)
                    assert len(image_ids) > 0, "バッチ処理後に画像IDが取得できませんでした"

                    # 各画像に対して512px画像が生成されていることを確認
                    for image_id in image_ids:
                        # 512px画像の存在チェック
                        processed_512px = main_window.idm.check_processed_image_exists(image_id, 512)
                        assert processed_512px is not None, f"画像ID {image_id} の512px画像が見つかりません"
                        assert processed_512px["width"] == 512 or processed_512px["height"] == 512, (
                            f"512px画像のサイズが正しくありません: {processed_512px['width']}x{processed_512px['height']}"
                        )

                        # 低解像度画像パスも取得できることを確認
                        low_res_path = main_window.idm.get_low_res_image_path(image_id)
                        assert low_res_path is not None, (
                            f"画像ID {image_id} の低解像度画像パスが取得できません"
                        )
                        assert Path(low_res_path).exists(), (
                            f"低解像度画像ファイルが存在しません: {low_res_path}"
                        )

            finally:
                main_window.close()

    def test_ensure_512px_image_method(self, temp_image_dir, temp_database_dir, test_config_service):
        """ImageProcessingService.ensure_512px_image() メソッドのテスト"""

        # Upscaler のモック設定
        def mock_upscale_func(img, model_name):
            return img.resize((img.width * 2, img.height * 2), Image.Resampling.LANCZOS)

        with patch("lorairo.editor.image_processor.Upscaler.upscale_image", side_effect=mock_upscale_func):
            with patch.object(
                test_config_service, "get_database_directory", return_value=temp_database_dir
            ):
                # 独立したコンポーネントでテスト
                fsm = FileSystemManager()
                fsm.initialize(temp_database_dir)

                image_repo = ImageRepository(session_factory=DefaultSessionLocal)
                idm = ImageDatabaseManager(image_repo, test_config_service, fsm)

                from lorairo.services.image_processing_service import ImageProcessingService

                image_processing_service = ImageProcessingService(test_config_service, fsm, idm)

                # 画像を登録（512px生成なしで）
                image_files = fsm.get_image_files(temp_image_dir)
                assert len(image_files) > 0, "テスト画像が見つかりません"

                # 最初の画像で512px生成をスキップして登録
                test_image = image_files[0]
                with patch.object(idm, "_generate_thumbnail_512px"):
                    result = idm.register_original_image(test_image, fsm)
                    assert result is not None, "画像登録が失敗しました"

                image_id, metadata = result

                # 512px画像が存在しないことを確認
                processed_512px = idm.check_processed_image_exists(image_id, 512)
                assert processed_512px is None, "512px画像が予期せず存在しています"

                # ensure_512px_image を実行
                result_path = image_processing_service.ensure_512px_image(image_id)

                # 512px画像が生成されたことを確認
                assert result_path is not None, f"ensure_512px_image が失敗しました: image_id={image_id}"
                assert Path(result_path).exists(), f"生成された512px画像が存在しません: {result_path}"

                # データベースにも登録されていることを確認
                processed_512px_after = idm.check_processed_image_exists(image_id, 512)
                assert processed_512px_after is not None, "512px画像がデータベースに登録されていません"

                # 再度呼び出しても既存画像が返されることを確認
                result_path_2 = image_processing_service.ensure_512px_image(image_id)
                assert result_path_2 == result_path, "2回目の呼び出しで異なるパスが返されました"

    def test_on_batch_completed_callback(self, temp_image_dir, temp_database_dir, test_config_service):
        """on_batch_completed コールバックのテスト"""

        with patch.object(test_config_service, "get_database_directory", return_value=temp_database_dir):
            main_window = MainWindow()
            main_window.config_service = test_config_service
            main_window.fsm.initialize(temp_database_dir)

            try:
                # モックで画像IDを設定
                mock_image_ids = [1, 2, 3]

                with patch.object(
                    main_window.idm, "get_image_ids_from_directory", return_value=mock_image_ids
                ):
                    # ステータスバーのモック
                    with patch.object(main_window, "statusbar") as mock_statusbar:
                        mock_statusbar.showMessage = MagicMock()

                        # on_batch_completed を実行
                        main_window.on_batch_completed(temp_image_dir)

                        # dataset_image_paths が更新されていることを確認
                        assert main_window.dataset_image_paths == mock_image_ids

                        # ステータスバーにメッセージが表示されることを確認
                        mock_statusbar.showMessage.assert_called_with(
                            f"バッチ処理完了: {len(mock_image_ids)} 件の画像を処理しました"
                        )

            finally:
                main_window.close()


@pytest.mark.integration
def test_integration_with_real_images():
    """実際の画像ファイルを使った統合テスト（独立した環境で）"""

    # 独立した一時ディレクトリを作成
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_image_dir = temp_dir / "images"
        temp_database_dir = temp_dir / "database"

        temp_image_dir.mkdir()
        temp_database_dir.mkdir()

        # より大きなテスト画像を作成（アップスケールが不要なサイズ）
        large_image_path = temp_image_dir / "large_test.jpg"
        large_image = Image.new("RGB", (1024, 768), color="green")
        large_image.save(large_image_path, "JPEG")

        # 小さな画像も作成（アップスケールが必要なサイズ）
        small_image_path = temp_image_dir / "small_test.png"
        small_image = Image.new("RGB", (300, 300), color="purple")
        small_image.save(small_image_path, "PNG")

        # 設定サービスをモック
        with patch("lorairo.services.configuration_service.ConfigurationService") as mock_config_class:
            config_instance = mock_config_class.return_value
            config_instance.get_database_directory.return_value = temp_database_dir
            config_instance.get_setting.side_effect = lambda section, key, default=None: {
                ("directories", "database_base_dir"): str(temp_database_dir.parent),
                ("directories", "dataset"): "",
            }.get((section, key), default)
            config_instance.get_image_processing_config.return_value = {"upscaler": "RealESRGAN_x4plus"}
            config_instance.update_setting = MagicMock()

            # アップスケーラーをモック
            with patch("lorairo.editor.image_processor.Upscaler.upscale_image") as mock_upscale:
                mock_upscale.side_effect = lambda img, model: img.resize(
                    (img.width * 2, img.height * 2), Image.Resampling.LANCZOS
                )

                # FileSystemManager とデータベース操作をテスト
                fsm = FileSystemManager()
                fsm.initialize(temp_database_dir)

                image_repo = ImageRepository(session_factory=DefaultSessionLocal)
                config_service = ConfigurationService()
                idm = ImageDatabaseManager(image_repo, config_service, fsm)

                # 画像を登録し、512px画像が生成されることを確認
                for image_file in [large_image_path, small_image_path]:
                    result = idm.register_original_image(image_file, fsm)
                    assert result is not None, f"画像登録が失敗: {image_file}"

                    image_id, metadata = result

                    # 512px画像の確認
                    processed_512px = idm.check_processed_image_exists(image_id, 512)
                    assert processed_512px is not None, f"512px画像が生成されていません: {image_file}"

                    # 実際のファイルが存在することを確認
                    stored_path = processed_512px["stored_image_path"]
                    assert Path(stored_path).exists(), f"512px画像ファイルが存在しません: {stored_path}"

                    # 画像サイズの確認
                    with Image.open(stored_path) as img:
                        assert max(img.width, img.height) == 512, (
                            f"512px画像のサイズが正しくありません: {img.width}x{img.height}"
                        )
