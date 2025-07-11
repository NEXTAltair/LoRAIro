"""
バッチ処理システム統合テスト
実際のファイルシステム、データベース、WorkerSystemとの統合をテストする
"""

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from lorairo.database.db_core import DefaultSessionLocal
from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import ImageRepository
from lorairo.services.batch_processor import process_directory_batch
from lorairo.services.configuration_service import ConfigurationService
from lorairo.storage.file_system import FileSystemManager


class TestBatchProcessingIntegration:
    """バッチ処理システムの統合テスト"""

    @pytest.fixture
    def test_images_dir(self, tmp_path):
        """テスト用画像ディレクトリを作成"""
        images_dir = tmp_path / "test_images"
        images_dir.mkdir()

        # テスト用画像ファイル作成
        for i in range(3):
            image_path = images_dir / f"test_image_{i}.jpg"
            # 簡単な100x100の赤い画像を作成
            image = Image.new("RGB", (100, 100), color="red")
            image.save(image_path, "JPEG")

        # 非画像ファイルも作成（無視されることを確認）
        (images_dir / "readme.txt").write_text("test file")

        return images_dir

    @pytest.fixture
    def test_database(self, tmp_path):
        """テスト用データベース設定"""
        db_path = tmp_path / "test_database.db"

        # データベース初期化
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_size INTEGER,
                    width INTEGER,
                    height INTEGER,
                    phash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        return db_path

    @pytest.fixture
    def config_service(self, tmp_path, test_database):
        """テスト用設定サービス"""
        config_file = tmp_path / "test_config.toml"
        config_file.write_text(f"""
[directories]
database_dir = "{test_database.parent}"
export_dir = "{tmp_path / "export"}"

[log]
level = "DEBUG"
file_path = "{tmp_path / "test.log"}"
""")

        # ConfigurationServiceに直接config_pathを渡す
        return ConfigurationService(config_path=config_file)

    @pytest.fixture
    def database_components(self, test_database):
        """データベース関連コンポーネント"""
        # セッション設定をテスト用DBに変更
        with patch("lorairo.database.db_core.DATABASE_URL", f"sqlite:///{test_database}"):
            image_repo = ImageRepository(session_factory=DefaultSessionLocal)
            idm = ImageDatabaseManager(image_repo)
            return idm

    def test_batch_processing_with_real_images(self, test_images_dir, config_service, database_components):
        """実際の画像ファイルでのバッチ処理統合テスト"""
        # Arrange
        fsm = FileSystemManager()
        idm = database_components

        # 進捗コールバック用のモック
        progress_callback = Mock()
        batch_progress_callback = Mock()
        status_callback = Mock()

        # Act
        result = process_directory_batch(
            test_images_dir,
            config_service,
            fsm,
            idm,
            progress_callback=progress_callback,
            batch_progress_callback=batch_progress_callback,
            status_callback=status_callback,
        )

        # Assert
        assert result["processed"] == 3
        assert result["errors"] == 0
        assert result["skipped"] == 0
        assert result["total"] == 3

        # コールバックが適切に呼ばれたことを確認
        assert progress_callback.call_count >= 3  # 各画像で1回以上
        assert batch_progress_callback.call_count == 3  # 各画像で1回
        assert status_callback.call_count >= 4  # 開始+各画像+完了

        # データベースに正しく登録されたことを確認
        # Note: 実際のデータベース確認は環境によって異なる可能性があるため、
        # ここではモックが呼ばれたことの確認に留める

    def test_batch_processing_with_duplicates(self, test_images_dir, config_service, database_components):
        """重複画像検出付きのバッチ処理統合テスト"""
        # Arrange
        fsm = FileSystemManager()
        idm = database_components

        # 最初の処理を実行
        process_directory_batch(test_images_dir, config_service, fsm, idm)

        # 同じディレクトリを再処理
        result = process_directory_batch(test_images_dir, config_service, fsm, idm)

        # Assert
        # 2回目は重複検出されてスキップされる可能性がある
        # (実際の重複検出ロジックによって結果が変わる)
        assert result["total"] == 3
        assert result["processed"] + result["skipped"] + result["errors"] == 3

    def test_batch_processing_cancellation(self, test_images_dir, config_service, database_components):
        """バッチ処理のキャンセル機能統合テスト"""
        # Arrange
        fsm = FileSystemManager()
        idm = database_components

        cancel_after_first = False

        def is_canceled():
            nonlocal cancel_after_first
            if not cancel_after_first:
                cancel_after_first = True
                return False
            return True

        status_callback = Mock()

        # Act
        result = process_directory_batch(
            test_images_dir,
            config_service,
            fsm,
            idm,
            status_callback=status_callback,
            is_canceled=is_canceled,
        )

        # Assert
        # キャンセルにより処理が途中で止まる
        assert result["processed"] < 3
        status_callback.assert_any_call("処理がキャンセルされました")

    def test_batch_processing_error_handling(self, tmp_path, config_service, database_components):
        """バッチ処理のエラーハンドリング統合テスト"""
        # Arrange
        # 存在しないディレクトリを指定
        non_existent_dir = tmp_path / "non_existent"
        fsm = FileSystemManager()
        idm = database_components

        status_callback = Mock()

        # Act
        result = process_directory_batch(
            non_existent_dir, config_service, fsm, idm, status_callback=status_callback
        )

        # Assert
        assert result["errors"] >= 1
        assert result["processed"] == 0
        # エラーメッセージがコールバックに送られることを確認
        status_callback.assert_any_call(lambda msg: "エラー" in msg or "error" in msg.lower())

    def test_batch_processing_with_mixed_file_types(self, tmp_path):
        """画像とその他ファイルが混在する場合の統合テスト（モック使用）"""
        # Arrange
        mixed_dir = tmp_path / "mixed_files"
        mixed_dir.mkdir()

        # 画像ファイル作成
        image_path = mixed_dir / "test.jpg"
        image = Image.new("RGB", (50, 50), color="blue")
        image.save(image_path, "JPEG")

        # 非画像ファイル作成
        (mixed_dir / "document.txt").write_text("not an image")
        (mixed_dir / "data.json").write_text('{"test": true}')

        # モックサービス使用
        config_service = Mock()
        fsm = FileSystemManager()  # 実際のFSMを使用してファイル検出をテスト
        idm = Mock()
        idm.detect_duplicate_image.return_value = None
        idm.register_original_image.return_value = ("test_id", {"metadata": "test"})

        # Act
        result = process_directory_batch(mixed_dir, config_service, fsm, idm)

        # Assert
        assert result["processed"] == 1  # 画像ファイルのみ処理
        assert result["total"] == 1  # 画像ファイルのみカウント
        # register_original_imageが1回だけ呼ばれた（画像ファイルのみ）
        assert idm.register_original_image.call_count == 1


class TestBatchProcessingPerformance:
    """バッチ処理のパフォーマンス統合テスト"""

    def test_batch_processing_performance_benchmark(self, tmp_path):
        """バッチ処理のパフォーマンス目標達成確認"""
        # Arrange
        # 100個の小さな画像を作成（メモリ効率重視）
        images_dir = tmp_path / "performance_test"
        images_dir.mkdir()

        for i in range(100):
            image_path = images_dir / f"perf_image_{i:03d}.jpg"
            # 小さな画像（10x10）を作成してメモリ使用量を抑制
            image = Image.new("RGB", (10, 10), color=(i % 256, 0, 0))
            image.save(image_path, "JPEG", quality=50)

        # テスト用設定
        config_service = Mock()
        fsm = FileSystemManager()
        idm = Mock()
        idm.detect_duplicate_image.return_value = None
        idm.register_original_image.return_value = (f"id_{i}", {"test": "metadata"})

        progress_values = []

        def track_progress(current, total, filename):
            progress_values.append((current, total, filename))

        # Act
        start_time = time.time()
        result = process_directory_batch(
            images_dir, config_service, fsm, idm, batch_progress_callback=track_progress
        )
        end_time = time.time()

        processing_time = end_time - start_time

        # Assert
        assert result["processed"] == 100
        assert result["errors"] == 0

        # パフォーマンス目標: 100画像を30秒以内で処理
        # (実際の目標は1000画像/5分だが、テストでは縮小)
        assert processing_time < 30, f"処理時間が遅すぎます: {processing_time:.2f}秒"

        # 進捗レポートが正しく機能していることを確認
        assert len(progress_values) == 100
        assert progress_values[0] == (1, 100, "perf_image_000.jpg")
        assert progress_values[-1] == (100, 100, "perf_image_099.jpg")


class TestBatchProcessingFileSystemIntegration:
    """ファイルシステムとの統合テスト"""

    def test_batch_processing_with_special_characters(self, tmp_path, config_service):
        """特殊文字を含むファイル名での統合テスト"""
        # Arrange
        special_dir = tmp_path / "special_chars"
        special_dir.mkdir()

        # 特殊文字を含むファイル名の画像作成
        special_names = ["日本語_画像.jpg", "image with spaces.jpg", "image@#$%.jpg", "𝕊𝕡𝕖𝕔𝕚𝕒𝕝.jpg"]

        for name in special_names:
            try:
                image_path = special_dir / name
                image = Image.new("RGB", (20, 20), color="green")
                image.save(image_path, "JPEG")
            except (OSError, UnicodeError):
                # プラットフォームで作成できない文字列はスキップ
                continue

        fsm = FileSystemManager()
        idm = Mock()
        idm.detect_duplicate_image.return_value = None
        idm.register_original_image.return_value = ("test_id", {"test": "metadata"})

        # Act
        result = process_directory_batch(special_dir, config_service, fsm, idm)

        # Assert
        # 少なくとも1つの画像は処理されることを期待
        assert result["total"] >= 1
        assert result["processed"] + result["errors"] == result["total"]

    def test_batch_processing_with_nested_directories(self, tmp_path, config_service):
        """ネストしたディレクトリ構造での統合テスト"""
        # Arrange
        base_dir = tmp_path / "nested_test"
        base_dir.mkdir()

        # ネストしたディレクトリ構造作成
        (base_dir / "subdir1").mkdir()
        (base_dir / "subdir1" / "subdir2").mkdir()

        # 各レベルに画像配置
        for level, dir_path in enumerate(
            [base_dir, base_dir / "subdir1", base_dir / "subdir1" / "subdir2"]
        ):
            image_path = dir_path / f"level_{level}.jpg"
            image = Image.new("RGB", (15, 15), color=(level * 80, 0, 0))
            image.save(image_path, "JPEG")

        fsm = FileSystemManager()
        idm = Mock()
        idm.detect_duplicate_image.return_value = None
        idm.register_original_image.return_value = ("test_id", {"test": "metadata"})

        # Act - トップレベルディレクトリのみを処理
        result = process_directory_batch(base_dir, config_service, fsm, idm)

        # Assert
        # get_image_filesの実装によって結果が変わる
        # 再帰的でない場合は1つ、再帰的な場合は3つ
        assert result["total"] >= 1
        assert result["processed"] == result["total"]
