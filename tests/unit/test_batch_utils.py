"""バッチ処理ユーティリティのユニットテスト"""

import base64
import json
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest

from lorairo.services.batch_utils import (
    _extract_tags_from_content,
    create_batch_jsonl,
    example_batch_workflow,
    monitor_batch_progress,
    parse_batch_results,
)


class TestCreateBatchJsonl:
    """create_batch_jsonl 関数のテスト"""

    def test_create_batch_jsonl_basic(self):
        """基本的なJSONL作成のテスト"""
        image_paths = [Path("image1.jpg"), Path("image2.jpg")]
        prompt = "Describe this image"

        # ファイル存在チェックとファイル読み込みをモック
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"fake_image_data")),
            patch("base64.b64encode", return_value=b"fake_base64_data"),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = 1234567890

            result_path = create_batch_jsonl(image_paths, prompt)

            assert result_path.name == "batch_request_1234567890.jsonl"

    def test_create_batch_jsonl_custom_output_path(self):
        """カスタム出力パスでのJSONL作成テスト"""
        image_paths = [Path("image1.jpg")]
        prompt = "Test prompt"
        custom_path = Path("custom_batch.jsonl")

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"fake_image_data")),
            patch("base64.b64encode", return_value=b"fake_base64_data"),
        ):
            result_path = create_batch_jsonl(image_paths, prompt, output_path=custom_path)

            assert result_path == custom_path

    def test_create_batch_jsonl_empty_images(self):
        """空の画像リストでのエラーテスト"""
        with pytest.raises(ValueError, match="image_pathsは空にできません"):
            create_batch_jsonl([], "prompt")

    def test_create_batch_jsonl_empty_prompt(self):
        """空のプロンプトでのエラーテスト"""
        image_paths = [Path("image1.jpg")]

        with pytest.raises(ValueError, match="promptは空にできません"):
            create_batch_jsonl(image_paths, "")

    def test_create_batch_jsonl_missing_image(self):
        """存在しない画像ファイルの処理テスト"""
        image_paths = [Path("missing.jpg"), Path("exists.jpg")]
        prompt = "Test prompt"

        # パスごとの存在チェック結果をマッピング
        path_exists_mapping = {str(Path("missing.jpg")): False, str(Path("exists.jpg")): True}

        def exists_side_effect(self):
            return path_exists_mapping.get(str(self), False)

        with (
            patch.object(Path, "exists", exists_side_effect),
            patch("builtins.open", mock_open(read_data=b"fake_image_data")),
            patch("base64.b64encode", return_value=b"fake_base64_data"),
            patch("pathlib.Path.stat") as mock_stat,
            patch("lorairo.services.batch_utils.logger") as mock_logger,
        ):
            mock_stat.return_value.st_mtime = 1234567890

            result_path = create_batch_jsonl(image_paths, prompt)

            # 存在しない画像について警告ログが出力されることを確認
            mock_logger.warning.assert_called_once()
            assert result_path is not None

    def test_create_batch_jsonl_custom_model(self):
        """カスタムモデル指定のテスト"""
        image_paths = [Path("image1.jpg")]
        prompt = "Test prompt"
        custom_model = "gpt-4o-mini"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"fake_image_data")) as mock_file,
            patch("base64.b64encode", return_value=b"fake_base64_data"),
            patch("pathlib.Path.stat") as mock_stat,
        ):
            mock_stat.return_value.st_mtime = 1234567890

            create_batch_jsonl(image_paths, prompt, model=custom_model)

            # ファイルに書き込まれた内容を確認
            written_content = mock_file.return_value.write.call_args[0][0]
            json_data = json.loads(written_content.strip())
            assert json_data["body"]["model"] == custom_model


class TestParseBatchResults:
    """parse_batch_results 関数のテスト"""

    def test_parse_batch_results_basic(self):
        """基本的な結果解析のテスト"""
        results_dict = {
            "request_0_image1": "A beautiful sunset over the ocean with tags: sunset, ocean, landscape",
            "request_1_image2": "A mountain view with tags: mountain, nature, sky",
        }

        result = parse_batch_results(results_dict)

        assert "image1" in result
        assert "image2" in result
        assert (
            result["image1"]["caption"]
            == "A beautiful sunset over the ocean with tags: sunset, ocean, landscape"
        )
        assert result["image1"]["custom_id"] == "request_0_image1"

    def test_parse_batch_results_with_underscore_in_name(self):
        """画像名にアンダースコアが含まれる場合のテスト"""
        results_dict = {"request_0_test_image_001": "Test content with tags: test, image"}

        result = parse_batch_results(results_dict)

        # アンダースコアを含む名前が正しく結合されることを確認
        assert "test_image_001" in result
        assert result["test_image_001"]["custom_id"] == "request_0_test_image_001"

    def test_parse_batch_results_malformed_custom_id(self):
        """不正なcustom_idの処理テスト"""
        results_dict = {"malformed_id": "Content without proper format"}

        result = parse_batch_results(results_dict)

        # 不正なIDでも適切に処理されることを確認
        assert "malformed_id" in result
        assert result["malformed_id"]["custom_id"] == "malformed_id"

    def test_parse_batch_results_with_exception(self):
        """例外処理のテスト"""
        results_dict = {
            "valid_id": "Valid content",
            "error_id": None,  # None は json.loads で例外を発生させる可能性
        }

        with patch("lorairo.services.batch_utils.logger") as mock_logger:
            result = parse_batch_results(results_dict)

        # エラーログが出力されることを確認
        assert len(result) <= len(results_dict)  # エラーのあるエントリは除外される可能性


class TestExtractTagsFromContent:
    """_extract_tags_from_content 関数のテスト"""

    def test_extract_tags_basic(self):
        """基本的なタグ抽出のテスト"""
        content = "This is a description. Tags: sunset, ocean, landscape, beautiful"

        result = _extract_tags_from_content(content)

        assert "sunset" in result
        assert "ocean" in result
        assert "landscape" in result
        assert "beautiful" in result

    def test_extract_tags_keywords_format(self):
        """Keywords形式のタグ抽出テスト"""
        content = "Description here. Keywords: mountain, nature, sky"

        result = _extract_tags_from_content(content)

        assert "mountain" in result
        assert "nature" in result
        assert "sky" in result

    def test_extract_tags_no_tags(self):
        """タグが見つからない場合のテスト"""
        content = "This is just a description without any tags section."

        result = _extract_tags_from_content(content)

        assert result == []

    def test_extract_tags_case_insensitive(self):
        """大文字小文字を無視したタグ抽出のテスト"""
        content = "Description. TAGS: item1, item2, item3"

        result = _extract_tags_from_content(content)

        assert len(result) == 3
        assert "item1" in result

    def test_extract_tags_whitespace_handling(self):
        """空白文字処理のテスト"""
        content = "Tags:  tag1  ,  tag2  ,  tag3  "

        result = _extract_tags_from_content(content)

        # 空白がトリムされていることを確認
        assert "tag1" in result
        assert "tag2" in result
        assert "tag3" in result
        assert " tag1 " not in result


class TestMonitorBatchProgress:
    """monitor_batch_progress 関数のテスト"""

    def test_monitor_batch_progress_completed(self):
        """バッチ処理完了の監視テスト"""
        mock_processor = Mock()
        mock_processor.get_batch_status.return_value = {"status": "completed"}

        with patch("time.sleep"):
            result = monitor_batch_progress(mock_processor, "batch_123", check_interval=1)

        assert result == "completed"
        mock_processor.get_batch_status.assert_called_with("batch_123")

    def test_monitor_batch_progress_in_progress_then_completed(self):
        """処理中から完了への遷移テスト"""
        mock_processor = Mock()
        # 最初は進行中、次に完了
        mock_processor.get_batch_status.side_effect = [{"status": "in_progress"}, {"status": "completed"}]

        with patch("time.sleep"):
            result = monitor_batch_progress(mock_processor, "batch_123", check_interval=1)

        assert result == "completed"
        assert mock_processor.get_batch_status.call_count == 2

    def test_monitor_batch_progress_failed(self):
        """バッチ処理失敗の監視テスト"""
        mock_processor = Mock()
        mock_processor.get_batch_status.return_value = {"status": "failed"}

        with patch("time.sleep"):
            result = monitor_batch_progress(mock_processor, "batch_123", check_interval=1)

        assert result == "failed"

    def test_monitor_batch_progress_exception_handling(self):
        """例外処理のテスト"""
        mock_processor = Mock()
        mock_processor.get_batch_status.side_effect = [Exception("Network error"), {"status": "completed"}]

        with patch("time.sleep"), patch("lorairo.services.batch_utils.logger") as mock_logger:
            result = monitor_batch_progress(mock_processor, "batch_123", check_interval=1)

        # エラーログが出力されることを確認
        mock_logger.error.assert_called()
        assert result == "completed"


class TestExampleBatchWorkflow:
    """example_batch_workflow 関数のテスト"""

    @patch("lorairo.services.batch_utils.create_batch_jsonl")
    @patch("lorairo.services.batch_utils.monitor_batch_progress")
    @patch("lorairo.services.batch_utils.parse_batch_results")
    def test_example_batch_workflow_success(self, mock_parse, mock_monitor, mock_create):
        """バッチワークフローの成功パスのテスト"""
        # Arrange
        mock_processor = Mock()
        mock_processor.start_batch_processing.return_value = "batch_123"
        mock_processor.download_batch_results.return_value = Path("results.jsonl")
        mock_processor.get_batch_results.return_value = {"image1": "result1"}

        mock_create.return_value = Path("batch.jsonl")
        mock_monitor.return_value = "completed"
        mock_parse.return_value = {"image1": {"tags": ["tag1"]}}

        with patch(
            "lorairo.services.openai_batch_processor.OpenAIBatchProcessor", return_value=mock_processor
        ):
            result = example_batch_workflow()

        # Assert
        assert result == {"image1": {"tags": ["tag1"]}}
        mock_create.assert_called_once()
        mock_monitor.assert_called_once()
        mock_parse.assert_called_once()

    @patch("lorairo.services.batch_utils.create_batch_jsonl")
    @patch("lorairo.services.batch_utils.monitor_batch_progress")
    def test_example_batch_workflow_failed(self, mock_monitor, mock_create):
        """バッチワークフローの失敗パスのテスト"""
        # Arrange
        mock_processor = Mock()
        mock_processor.start_batch_processing.return_value = "batch_123"

        mock_create.return_value = Path("batch.jsonl")
        mock_monitor.return_value = "failed"

        with (
            patch(
                "lorairo.services.openai_batch_processor.OpenAIBatchProcessor", return_value=mock_processor
            ),
            patch("lorairo.services.batch_utils.logger") as mock_logger,
        ):
            result = example_batch_workflow()

        # Assert
        assert result is None
        mock_logger.error.assert_called_once()
        assert "バッチ処理が失敗しました: failed" in str(mock_logger.error.call_args)
