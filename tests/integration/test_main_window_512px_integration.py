"""
統合テスト: MainWindowのディレクトリ処理時に512px画像が正常に作成されるかを検証

このテストは以下のフローを検証します:
1. MainWindowにディレクトリを設定
2. バッチ処理により画像をデータベースに登録
3. 編集画面表示時に512px画像が正常に作成される
4. 作成された512px画像のサイズと品質を検証
"""

import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from lorairo.database.db_core import DefaultSessionLocal
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.gui.window.main_window import MainWindow
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager


@pytest.fixture
def app():
    """QApplication fixture for GUI tests"""
    if not QApplication.instance():
        app = QApplication([])
    else:
        app = QApplication.instance()
    yield app
    if app:
        app.quit()


@pytest.fixture
def temp_test_directory():
    """テスト用の一時ディレクトリとテスト画像を作成"""
    temp_dir = Path(tempfile.mkdtemp())

    # テスト画像を作成 (実際のWebPファイル)
    test_image_1 = Image.new("RGB", (704, 992), color="red")
    test_image_2 = Image.new("RGB", (800, 600), color="blue")

    image_path_1 = temp_dir / "test_image_1.webp"
    image_path_2 = temp_dir / "test_image_2.webp"

    test_image_1.save(image_path_1, "WEBP")
    test_image_2.save(image_path_2, "WEBP")

    # テキストファイルも作成（タグとキャプション）
    (temp_dir / "test_image_1.txt").write_text("1girl, portrait, detailed")
    (temp_dir / "test_image_1.caption").write_text("A detailed portrait of a girl")
    (temp_dir / "test_image_2.txt").write_text("landscape, blue sky, nature")
    (temp_dir / "test_image_2.caption").write_text("A beautiful landscape with blue sky")

    yield temp_dir

    # クリーンアップ
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_database_directory():
    """テスト用のデータベースディレクトリを作成"""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_config(temp_database_directory):
    """テスト用の設定サービス"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        config_content = f'''
[directories]
database_base_dir = "{temp_database_directory}"
dataset = ""
export_dir = ""

[image_processing]
target_resolution = 1024
preferred_resolutions = [[512, 512], [768, 512], [1024, 1024]]

[log]
level = "DEBUG"
'''
        f.write(config_content)
        config_path = Path(f.name)

    config_service = ConfigurationService(config_path)
    yield config_service

    # クリーンアップ
    config_path.unlink(missing_ok=True)


class TestMainWindow512pxIntegration:
    """MainWindowの512px画像生成統合テスト"""

    def test_directory_processing_creates_512px_images(self, app, temp_test_directory, test_config):
        """
        ディレクトリ処理時に512px画像が正常に作成されることを検証
        """
        # MainWindowを初期化（設定を注入）
        with patch("lorairo.gui.window.main_window.ConfigurationService", return_value=test_config):
            main_window = MainWindow()

        try:
            # バッチ処理を実行（プログレスウィジェット無しでダイレクト実行）
            from lorairo.services.batch_processor import process_directory_batch

            # FileSystemManagerを初期化
            database_dir = test_config.get_database_directory()
            if not database_dir or database_dir == Path("database"):
                from datetime import datetime

                base_dir = Path(test_config.get_setting("directories", "database_base_dir", "lorairo_data"))
                project_name = f"test_project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                database_dir = base_dir / project_name
                test_config.update_setting("directories", "database_dir", str(database_dir))

            main_window.fsm.initialize(database_dir, 1024)

            # バッチ処理を直接実行
            result = process_directory_batch(
                temp_test_directory, test_config, main_window.fsm, main_window.idm
            )

            # 処理結果を確認
            assert result is not None, "バッチ処理が失敗しました"

            # データベースに画像が登録されていることを確認
            image_ids = main_window.idm.get_image_ids_from_directory(temp_test_directory)
            assert len(image_ids) > 0, "画像がデータベースに登録されていません"

            # 各画像について512px画像の生成をテスト
            for image_id in image_ids:
                self._verify_512px_image_creation(main_window, image_id)

        finally:
            main_window.close()

    def _verify_512px_image_creation(self, main_window, image_id):
        """指定された画像IDの512px画像生成を検証"""
        # 画像メタデータを取得
        metadata = main_window.idm.get_image_metadata(image_id)
        assert metadata is not None, f"画像メタデータが見つかりません: image_id={image_id}"

        # 512px画像生成を実行
        result_path = main_window.image_processing_service.ensure_512px_image(
            image_id, Path(metadata.file_path)
        )

        # 結果を検証
        assert result_path is not None, f"512px画像の生成に失敗しました: image_id={image_id}"
        assert result_path.exists(), f"512px画像ファイルが存在しません: {result_path}"

        # 画像のサイズと品質を検証
        with Image.open(result_path) as img:
            width, height = img.size

            # サイズが512px以下であることを確認
            assert max(width, height) <= 512, f"画像サイズが512pxを超えています: {width}x{height}"

            # 32の倍数であることを確認（SD向け最適化）
            assert width % 32 == 0, f"幅が32の倍数ではありません: {width}"
            assert height % 32 == 0, f"高さが32の倍数ではありません: {height}"

            # アスペクト比の妥当性を確認
            assert width > 0 and height > 0, f"無効な画像サイズ: {width}x{height}"

            # 画像形式の確認
            assert img.format in ["WEBP", "JPEG", "PNG"], f"予期しない画像形式: {img.format}"

    def test_512px_image_database_registration(self, app, temp_test_directory, test_config):
        """
        512px画像がデータベースに適切に登録されることを検証
        """
        with patch("lorairo.gui.window.main_window.ConfigurationService", return_value=test_config):
            main_window = MainWindow()

        try:
            # バッチ処理を実行
            main_window.dataset_dir_changed(str(temp_test_directory))

            # 処理完了を待機
            self._wait_for_batch_completion(main_window)

            # 画像IDを取得
            image_ids = main_window.idm.get_image_ids_from_directory(temp_test_directory)

            for image_id in image_ids:
                # 元画像のメタデータを取得
                metadata = main_window.idm.get_image_metadata(image_id)

                # 512px画像を生成
                result_path = main_window.image_processing_service.ensure_512px_image(
                    image_id, Path(metadata.file_path)
                )

                if result_path:
                    # データベースに512px画像が登録されているかチェック
                    processed_images = main_window.idm.get_processed_images_by_original_id(image_id)

                    # 512px解像度の画像が存在することを確認
                    has_512px = any(img.target_resolution == 512 for img in processed_images)
                    assert has_512px, f"512px画像がデータベースに登録されていません: image_id={image_id}"

        finally:
            main_window.close()

    def test_error_handling_in_512px_creation(self, app, temp_test_directory, test_config):
        """
        512px画像生成時のエラーハンドリングを検証
        """
        with patch("lorairo.gui.window.main_window.ConfigurationService", return_value=test_config):
            main_window = MainWindow()

        try:
            # バッチ処理を実行
            main_window.dataset_dir_changed(str(temp_test_directory))
            self._wait_for_batch_completion(main_window)

            image_ids = main_window.idm.get_image_ids_from_directory(temp_test_directory)

            if image_ids:
                image_id = image_ids[0]

                # 存在しないファイルパスで512px画像生成を試行
                non_existent_path = Path("/non/existent/path.webp")

                result_path = main_window.image_processing_service.ensure_512px_image(
                    image_id, non_existent_path
                )

                # エラー時はNoneが返されることを確認
                assert result_path is None, "存在しないファイルに対してパスが返されました"

        finally:
            main_window.close()

    def test_multiple_resolution_support(self, app, temp_test_directory, test_config):
        """
        複数解像度での画像生成をテスト
        """
        with patch("lorairo.gui.window.main_window.ConfigurationService", return_value=test_config):
            main_window = MainWindow()

        try:
            # バッチ処理を実行
            main_window.dataset_dir_changed(str(temp_test_directory))
            self._wait_for_batch_completion(main_window)

            image_ids = main_window.idm.get_image_ids_from_directory(temp_test_directory)

            if image_ids:
                image_id = image_ids[0]
                metadata = main_window.idm.get_image_metadata(image_id)

                # 異なる解像度での画像生成をテスト
                for target_resolution in [256, 512, 768]:
                    # 一時的な処理サービスを作成
                    temp_service = main_window.image_processing_service

                    # カスタム解像度での処理をテスト
                    processed_img = temp_service._process_single_image_for_resolution(
                        Path(metadata.file_path), metadata.has_alpha, metadata.mode, target_resolution
                    )

                    if processed_img:
                        # 解像度が期待値以下であることを確認
                        assert max(processed_img.width, processed_img.height) <= target_resolution

        finally:
            main_window.close()

    def _wait_for_batch_completion(self, main_window, timeout_ms=30000):
        """バッチ処理の完了を待機"""
        loop = QEventLoop()

        def on_completion():
            loop.quit()

        # プログレスコントローラーの完了を監視
        if hasattr(main_window.progress_controller, "worker") and main_window.progress_controller.worker:
            main_window.progress_controller.worker.finished.connect(on_completion)

        # タイムアウト設定
        timer = QTimer()
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)

        loop.exec()
        timer.stop()

    def test_image_quality_after_512px_conversion(self, app, temp_test_directory, test_config):
        """
        512px変換後の画像品質を検証
        """
        with patch("lorairo.gui.window.main_window.ConfigurationService", return_value=test_config):
            main_window = MainWindow()

        try:
            # バッチ処理を実行
            main_window.dataset_dir_changed(str(temp_test_directory))
            self._wait_for_batch_completion(main_window)

            image_ids = main_window.idm.get_image_ids_from_directory(temp_test_directory)

            for image_id in image_ids:
                metadata = main_window.idm.get_image_metadata(image_id)
                original_path = Path(metadata.file_path)

                # 元画像を読み込み
                with Image.open(original_path) as original_img:
                    original_width, original_height = original_img.size

                # 512px画像を生成
                result_path = main_window.image_processing_service.ensure_512px_image(
                    image_id, original_path
                )

                if result_path and result_path.exists():
                    with Image.open(result_path) as processed_img:
                        processed_width, processed_height = processed_img.size

                        # アスペクト比が保持されていることを確認
                        original_ratio = original_width / original_height
                        processed_ratio = processed_width / processed_height

                        # 小数点誤差を考慮して比較（5%以内の差異）
                        ratio_diff = abs(original_ratio - processed_ratio) / original_ratio
                        assert ratio_diff < 0.05, (
                            f"アスペクト比が大きく変化しています: "
                            f"元画像={original_ratio:.3f}, 処理後={processed_ratio:.3f}"
                        )

                        # 画像が適切にスケールダウンされていることを確認
                        scale_factor = max(
                            processed_width / original_width, processed_height / original_height
                        )
                        assert scale_factor <= 1.0, "画像がアップスケールされています"

        finally:
            main_window.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
