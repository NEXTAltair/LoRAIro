"""batch_processor モジュールのユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from lorairo.services.batch_processor import _process_associated_files, process_directory_batch


class TestProcessDirectoryBatch:
    """process_directory_batch 関数のテスト"""

    def test_empty_directory(self):
        """空のディレクトリの処理テスト"""
        # Arrange
        directory_path = Path("/test/empty")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        # ファイルが見つからない場合
        mock_fsm.get_image_files.return_value = []

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 0, "errors": 0, "skipped": 0, "total": 0}
        mock_fsm.get_image_files.assert_called_once_with(directory_path)

    def test_file_scan_error(self):
        """ファイルスキャンエラーのテスト"""
        # Arrange
        directory_path = Path("/test/error")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        # ファイルスキャンでエラー
        mock_fsm.get_image_files.side_effect = PermissionError("Access denied")

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 0, "errors": 1, "skipped": 0, "total": 0}

    def test_successful_processing(self):
        """正常処理のテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        # ファイルリスト
        image_files = [
            Path("/test/images/image1.jpg"),
            Path("/test/images/image2.png"),
            Path("/test/images/image3.gif"),
        ]
        mock_fsm.get_image_files.return_value = image_files

        # 重複チェック（すべて新規）
        mock_idm.detect_duplicate_image.return_value = None

        # 登録処理（すべて成功）
        mock_idm.register_original_image.side_effect = [
            ("id1", {"metadata": "data1"}),
            ("id2", {"metadata": "data2"}),
            ("id3", {"metadata": "data3"}),
        ]

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 3, "errors": 0, "skipped": 0, "total": 3}
        assert mock_idm.detect_duplicate_image.call_count == 3
        assert mock_idm.register_original_image.call_count == 3

    def test_duplicate_images(self):
        """重複画像のスキップテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [
            Path("/test/images/image1.jpg"),
            Path("/test/images/image2.jpg"),  # 重複
        ]
        mock_fsm.get_image_files.return_value = image_files

        # 1つ目は新規、2つ目は重複
        mock_idm.detect_duplicate_image.side_effect = [None, "existing_id"]
        mock_idm.register_original_image.return_value = ("id1", {"metadata": "data1"})

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 1, "errors": 0, "skipped": 1, "total": 2}
        assert mock_idm.register_original_image.call_count == 1

    def test_registration_failures(self):
        """登録失敗のテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [Path("/test/images/image1.jpg"), Path("/test/images/image2.jpg")]
        mock_fsm.get_image_files.return_value = image_files

        # 重複チェック（すべて新規）
        mock_idm.detect_duplicate_image.return_value = None

        # 1つ目成功、2つ目失敗
        mock_idm.register_original_image.side_effect = [
            ("id1", {"metadata": "data1"}),
            None,  # 登録失敗
        ]

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 1, "errors": 1, "skipped": 0, "total": 2}

    def test_registration_exception(self):
        """登録中の例外処理テスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [Path("/test/images/image1.jpg")]
        mock_fsm.get_image_files.return_value = image_files

        # 重複チェックでエラー
        mock_idm.detect_duplicate_image.side_effect = RuntimeError("DB Error")

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 0, "errors": 1, "skipped": 0, "total": 1}

    def test_progress_callbacks(self):
        """進捗コールバックのテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [Path("/test/images/image1.jpg"), Path("/test/images/image2.jpg")]
        mock_fsm.get_image_files.return_value = image_files

        mock_idm.detect_duplicate_image.return_value = None
        mock_idm.register_original_image.return_value = ("id1", {"metadata": "data1"})

        # コールバックモック
        progress_callback = Mock()
        batch_progress_callback = Mock()
        status_callback = Mock()

        # Act
        result = process_directory_batch(
            directory_path,
            mock_config,
            mock_fsm,
            mock_idm,
            progress_callback=progress_callback,
            batch_progress_callback=batch_progress_callback,
            status_callback=status_callback,
        )

        # Assert
        assert result == {"processed": 2, "errors": 0, "skipped": 0, "total": 2}

        # 進捗コールバックの呼び出し確認
        assert progress_callback.call_count == 2  # 50%, 100%
        progress_callback.assert_any_call(50)
        progress_callback.assert_any_call(100)

        # バッチ進捗コールバックの呼び出し確認
        assert batch_progress_callback.call_count == 2
        batch_progress_callback.assert_any_call(1, 2, "image1.jpg")
        batch_progress_callback.assert_any_call(2, 2, "image2.jpg")

        # ステータスコールバックの呼び出し確認
        assert status_callback.call_count >= 4  # 最低4回は呼ばれる

    def test_cancellation(self):
        """キャンセル処理のテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [
            Path("/test/images/image1.jpg"),
            Path("/test/images/image2.jpg"),
            Path("/test/images/image3.jpg"),
        ]
        mock_fsm.get_image_files.return_value = image_files

        mock_idm.detect_duplicate_image.return_value = None
        mock_idm.register_original_image.return_value = ("id1", {"metadata": "data1"})

        # 2回目の処理でキャンセル
        is_canceled_calls = 0

        def is_canceled():
            nonlocal is_canceled_calls
            is_canceled_calls += 1
            return is_canceled_calls >= 2  # 2回目からキャンセル

        status_callback = Mock()

        # Act
        result = process_directory_batch(
            directory_path,
            mock_config,
            mock_fsm,
            mock_idm,
            status_callback=status_callback,
            is_canceled=is_canceled,
        )

        # Assert
        # 1つ目は処理され、2つ目以降はキャンセル
        assert result == {"processed": 1, "errors": 0, "skipped": 0, "total": 3}

        # キャンセルメッセージが呼ばれることを確認
        status_callback.assert_any_call("処理がキャンセルされました")

    def test_mixed_results(self):
        """成功・失敗・スキップが混在するテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [
            Path("/test/images/image1.jpg"),  # 成功
            Path("/test/images/image2.jpg"),  # 重複スキップ
            Path("/test/images/image3.jpg"),  # 登録失敗
            Path("/test/images/image4.jpg"),  # 例外エラー
        ]
        mock_fsm.get_image_files.return_value = image_files

        # 重複チェック結果
        mock_idm.detect_duplicate_image.side_effect = [
            None,  # 新規
            "existing_id",  # 重複
            None,  # 新規
            None,  # 新規
        ]

        # 登録処理結果
        def register_side_effect(image_file, fsm):
            if image_file.name == "image1.jpg":
                return ("id1", {"metadata": "data1"})
            elif image_file.name == "image3.jpg":
                return None  # 登録失敗
            elif image_file.name == "image4.jpg":
                raise RuntimeError("Unexpected error")

        mock_idm.register_original_image.side_effect = register_side_effect

        # Act
        result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

        # Assert
        assert result == {"processed": 1, "errors": 2, "skipped": 1, "total": 4}

    def test_callback_none_safety(self):
        """コールバックがNoneの場合の安全性テスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [Path("/test/images/image1.jpg")]
        mock_fsm.get_image_files.return_value = image_files

        mock_idm.detect_duplicate_image.return_value = None
        mock_idm.register_original_image.return_value = ("id1", {"metadata": "data1"})

        # Act - すべてのコールバックをNoneで実行
        result = process_directory_batch(
            directory_path,
            mock_config,
            mock_fsm,
            mock_idm,
            progress_callback=None,
            batch_progress_callback=None,
            status_callback=None,
            is_canceled=None,
        )

        # Assert - 例外が発生せず正常に処理される
        assert result == {"processed": 1, "errors": 0, "skipped": 0, "total": 1}


class TestProcessAssociatedFiles:
    """_process_associated_files 関数のテスト"""

    def test_process_tags_file(self, tmp_path):
        """タグファイル処理のテスト"""
        # Arrange
        image_file = tmp_path / "test_image.jpg"
        image_file.touch()

        # タグファイル作成
        txt_file = tmp_path / "test_image.txt"
        txt_file.write_text("tag1, tag2, tag3", encoding="utf-8")

        mock_idm = Mock()
        image_id = 123

        # Act
        _process_associated_files(image_file, image_id, mock_idm)

        # Assert
        mock_idm.save_tags.assert_called_once()
        call_args = mock_idm.save_tags.call_args
        assert call_args[0][0] == image_id  # image_id
        tags_data = call_args[0][1]  # tags_data
        assert len(tags_data) == 3
        assert tags_data[0]["tag"] == "tag1"
        assert tags_data[1]["tag"] == "tag2"
        assert tags_data[2]["tag"] == "tag3"
        for tag_data in tags_data:
            assert tag_data["tag_id"] is None
            assert tag_data["model_id"] is None
            assert tag_data["existing"] is True
            assert tag_data["is_edited_manually"] is False
            assert tag_data["confidence_score"] is None

    def test_process_caption_file(self, tmp_path):
        """キャプションファイル処理のテスト"""
        # Arrange
        image_file = tmp_path / "test_image.jpg"
        image_file.touch()

        # キャプションファイル作成
        caption_file = tmp_path / "test_image.caption"
        caption_content = "This is a test caption for the image."
        caption_file.write_text(caption_content, encoding="utf-8")

        mock_idm = Mock()
        image_id = 456

        # Act
        _process_associated_files(image_file, image_id, mock_idm)

        # Assert
        mock_idm.save_captions.assert_called_once()
        call_args = mock_idm.save_captions.call_args
        assert call_args[0][0] == image_id  # image_id
        captions_data = call_args[0][1]  # captions_data
        assert len(captions_data) == 1
        assert captions_data[0]["caption"] == caption_content
        assert captions_data[0]["model_id"] is None
        assert captions_data[0]["existing"] is True
        assert captions_data[0]["is_edited_manually"] is False

    def test_no_associated_files(self, tmp_path):
        """関連ファイルがない場合のテスト"""
        # Arrange
        image_file = tmp_path / "test_image.jpg"
        image_file.touch()

        mock_idm = Mock()
        image_id = 999

        # Act
        _process_associated_files(image_file, image_id, mock_idm)

        # Assert
        mock_idm.save_tags.assert_not_called()
        mock_idm.save_captions.assert_not_called()

    def test_duplicate_image_processes_associated_files(self):
        """重複画像でも関連ファイルを処理するテスト"""
        # Arrange
        directory_path = Path("/test/images")
        mock_config = Mock()
        mock_fsm = Mock()
        mock_idm = Mock()

        image_files = [Path("/test/images/existing_image.jpg")]
        mock_fsm.get_image_files.return_value = image_files

        # 重複検出で既存IDを返す
        existing_id = 999
        mock_idm.detect_duplicate_image.return_value = existing_id

        # _process_associated_filesをモック
        with patch("lorairo.services.batch_processor._process_associated_files") as mock_process_files:
            # Act
            result = process_directory_batch(directory_path, mock_config, mock_fsm, mock_idm)

            # Assert
            assert result == {"processed": 0, "errors": 0, "skipped": 1, "total": 1}
            # 重複画像でも関連ファイル処理が呼ばれることを確認
            mock_process_files.assert_called_once_with(image_files[0], existing_id, mock_idm)

            # 新規登録は呼ばれない
            mock_idm.register_original_image.assert_not_called()
