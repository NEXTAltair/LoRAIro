"""OpenAIBatchProcessor のユニットテスト"""

import json
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

import pytest
import requests

from lorairo.services.openai_batch_processor import APIError, OpenAIBatchProcessor


class TestAPIError:
    """APIError クラスのテスト"""

    def test_api_error_basic(self):
        """基本的なAPIError作成のテスト"""
        error = APIError("Test error", "TestAPI", "TEST001", 400)

        assert str(error) == "TestAPI API Error: Test error | Code: TEST001 | Status: 400"
        assert error.api_provider == "TestAPI"
        assert error.error_code == "TEST001"
        assert error.status_code == 400

    def test_api_error_minimal(self):
        """最小限のAPIError作成のテスト"""
        error = APIError("Simple error")

        assert str(error) == " API Error: Simple error"

    def test_check_response_success(self):
        """成功レスポンスのチェックテスト"""
        mock_response = Mock()
        mock_response.status_code = 200

        # 例外が発生しないことを確認
        APIError.check_response(mock_response, "TestAPI")

    def test_check_response_400_error(self):
        """400エラーレスポンスのチェックテスト"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"error": {"message": "Bad request"}}

        with pytest.raises(APIError) as exc_info:
            APIError.check_response(mock_response, "TestAPI")

        assert exc_info.value.api_provider == "TestAPI"
        assert exc_info.value.status_code == 400

    def test_check_response_401_error(self):
        """401認証エラーのチェックテスト"""
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.json.side_effect = json.JSONDecodeError("", "", 0)

        with pytest.raises(APIError) as exc_info:
            APIError.check_response(mock_response, "OpenAI")

        assert "APIキー認証エラー" in str(exc_info.value)

    def test_check_response_unknown_error(self):
        """未知のエラーコードのチェックテスト"""
        mock_response = Mock()
        mock_response.status_code = 999
        mock_response.json.side_effect = json.JSONDecodeError("", "", 0)

        with pytest.raises(APIError) as exc_info:
            APIError.check_response(mock_response, "TestAPI")

        assert "不明なHTTPエラー: 999" in str(exc_info.value)

    def test_to_dict(self):
        """辞書変換のテスト"""
        error = APIError("Test error", "TestAPI", "TEST001", 400)

        result = error.to_dict()

        assert result == {
            "message": "Test error",
            "api_provider": "TestAPI",
            "error_code": "TEST001",
            "status_code": 400,
        }


class TestOpenAIBatchProcessor:
    """OpenAIBatchProcessor クラスのテスト"""

    def test_init(self):
        """初期化テスト"""
        with patch("lorairo.services.openai_batch_processor.OpenAI") as mock_openai:
            processor = OpenAIBatchProcessor("test_api_key")

            assert processor.api_key == "test_api_key"
            assert processor.request_interval == 1.0
            assert processor.last_request_time == 0.0
            mock_openai.assert_called_once_with(api_key="test_api_key")

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_for_rate_limit(self, mock_sleep, mock_time):
        """レート制限待機のテスト"""
        processor = OpenAIBatchProcessor("test_key")
        processor.last_request_time = 10.0
        mock_time.return_value = 10.5  # 0.5秒経過

        processor._wait_for_rate_limit()

        # 0.5秒待機する必要があることを確認
        mock_sleep.assert_called_once_with(0.5)

    @patch("time.time")
    @patch("time.sleep")
    def test_wait_for_rate_limit_no_wait(self, mock_sleep, mock_time):
        """レート制限待機不要のテスト"""
        processor = OpenAIBatchProcessor("test_key")
        processor.last_request_time = 10.0
        mock_time.return_value = 12.0  # 2秒経過（十分）

        processor._wait_for_rate_limit()

        # 待機は不要
        mock_sleep.assert_not_called()

    @patch("pathlib.Path.exists")
    def test_start_batch_processing_success(self, mock_exists):
        """バッチ処理開始の成功テスト"""
        # モッククライアントを作成
        mock_client = Mock()
        mock_file = Mock()
        mock_file.id = "file_123"
        mock_batch = Mock()
        mock_batch.id = "batch_123"

        mock_client.files.create.return_value = mock_file
        mock_client.batches.create.return_value = mock_batch

        processor = OpenAIBatchProcessor("test_key", client=mock_client)
        jsonl_path = Path("test.jsonl")
        mock_exists.return_value = True

        with patch("builtins.open", mock_open(read_data=b"test data")):
            result = processor.start_batch_processing(jsonl_path)

        assert result == "batch_123"
        mock_client.files.create.assert_called_once()
        mock_client.batches.create.assert_called_once()

    @patch("pathlib.Path.exists")
    def test_start_batch_processing_file_not_found(self, mock_exists):
        """ファイルが見つからない場合のテスト"""
        processor = OpenAIBatchProcessor("test_key")
        jsonl_path = Path("missing.jsonl")
        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError):
            processor.start_batch_processing(jsonl_path)

    @patch("requests.post")
    @patch("pathlib.Path.exists")
    def test_start_batch_processing_upload_error(self, mock_exists, mock_post):
        """アップロードエラーのテスト"""
        processor = OpenAIBatchProcessor("test_key")
        jsonl_path = Path("test.jsonl")
        mock_exists.return_value = True

        # アップロードでエラーレスポンス
        error_response = Mock()
        error_response.status_code = 400
        error_response.json.return_value = {"error": {"message": "Upload failed"}}
        mock_post.return_value = error_response

        with (
            patch("builtins.open", mock_open(read_data=b"test data")),
            patch("time.time", return_value=100.0),
            pytest.raises(APIError),
        ):
            processor.start_batch_processing(jsonl_path)

    @patch("pathlib.Path.exists")
    def test_start_batch_processing_timeout(self, mock_exists):
        """タイムアウトエラーのテスト"""
        # モッククライアントを作成
        mock_client = Mock()
        mock_client.files.create.side_effect = requests.exceptions.Timeout("Request timeout")

        processor = OpenAIBatchProcessor("test_key", client=mock_client)
        jsonl_path = Path("test.jsonl")
        mock_exists.return_value = True

        with (
            patch("builtins.open", mock_open(read_data=b"test data")),
            pytest.raises(APIError, match="バッチ処理開始中にエラーが発生しました"),
        ):
            processor.start_batch_processing(jsonl_path)

    def test_get_batch_status_success(self):
        """バッチステータス取得の成功テスト"""
        # モッククライアントを作成
        mock_client = Mock()
        mock_batch = Mock()
        mock_batch.id = "batch_123"
        mock_batch.status = "completed"
        mock_batch.endpoint = "/v1/chat/completions"
        mock_batch.input_file_id = "file_123"
        mock_batch.output_file_id = "file_456"
        mock_batch.error_file_id = None
        mock_batch.created_at = 1234567890
        mock_batch.in_progress_at = 1234567891
        mock_batch.expires_at = 1234567999
        mock_batch.completed_at = 1234567895
        mock_batch.failed_at = None
        mock_batch.expired_at = None
        mock_batch.request_counts = {"total": 10, "completed": 10, "failed": 0}
        mock_batch.metadata = {}

        mock_client.batches.retrieve.return_value = mock_batch

        processor = OpenAIBatchProcessor("test_key", client=mock_client)
        result = processor.get_batch_status("batch_123")

        assert result["status"] == "completed"
        assert result["id"] == "batch_123"
        mock_client.batches.retrieve.assert_called_once_with("batch_123")

    @patch("requests.get")
    def test_get_batch_status_error(self, mock_get):
        """バッチステータス取得のエラーテスト"""
        processor = OpenAIBatchProcessor("test_key")

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": {"message": "Not found"}}
        mock_get.return_value = mock_response

        with patch("time.time", return_value=100.0), pytest.raises(APIError):
            processor.get_batch_status("batch_123")

    def test_get_batch_results_success(self, tmp_path):
        """バッチ結果取得の成功テスト"""
        processor = OpenAIBatchProcessor("test_key")

        # 実際のディレクトリとファイルを作成
        result_dir = tmp_path / "results"
        result_dir.mkdir()

        jsonl_file = result_dir / "batch_results.jsonl"
        jsonl_content = json.dumps(
            {
                "custom_id": "test_1",
                "response": {"body": {"choices": [{"message": {"content": "Test result"}}]}},
            }
        )
        jsonl_file.write_text(jsonl_content)

        result = processor.get_batch_results(result_dir)

        assert "test_1" in result
        assert result["test_1"] == "Test result"

    @patch("pathlib.Path.exists")
    def test_get_batch_results_directory_not_found(self, mock_exists):
        """結果ディレクトリが見つからない場合のテスト"""
        processor = OpenAIBatchProcessor("test_key")
        result_dir = Path("missing_results")
        mock_exists.return_value = False

        with pytest.raises(FileNotFoundError):
            processor.get_batch_results(result_dir)

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.glob")
    def test_get_batch_results_no_jsonl_files(self, mock_glob, mock_exists):
        """JSONLファイルが見つからない場合のテスト"""
        processor = OpenAIBatchProcessor("test_key")
        result_dir = Path("results")
        mock_exists.return_value = True
        mock_glob.return_value = []  # JSONLファイルなし

        with patch("lorairo.services.openai_batch_processor.logger") as mock_logger:
            result = processor.get_batch_results(result_dir)

        assert result == {}
        mock_logger.warning.assert_called_once()

    def test_download_batch_results_success(self):
        """バッチ結果ダウンロードの成功テスト"""
        # モッククライアントを作成
        mock_client = Mock()
        mock_batch = Mock()
        mock_batch.status = "completed"
        mock_batch.output_file_id = "file_456"

        mock_file_response = Mock()
        mock_file_response.content = b"downloaded content"

        mock_client.batches.retrieve.return_value = mock_batch
        mock_client.files.content.return_value = mock_file_response

        processor = OpenAIBatchProcessor("test_key", client=mock_client)
        output_dir = Path("output")

        with (
            patch("pathlib.Path.mkdir"),
            patch("builtins.open", mock_open()) as mock_file,
        ):
            result_path = processor.download_batch_results("batch_123", output_dir)

        assert result_path == output_dir / "batch_results_batch_123.jsonl"
        # ファイルに内容が書き込まれることを確認
        mock_file.return_value.write.assert_called_once_with(b"downloaded content")

    def test_download_batch_results_not_completed(self):
        """未完了のバッチ結果ダウンロードのテスト"""
        # モッククライアントを作成
        mock_client = Mock()
        mock_batch = Mock()
        mock_batch.status = "in_progress"

        mock_client.batches.retrieve.return_value = mock_batch

        processor = OpenAIBatchProcessor("test_key", client=mock_client)

        with pytest.raises(APIError, match="ダウンロード中にエラーが発生しました"):
            processor.download_batch_results("batch_123", Path("output"))

    def test_download_batch_results_no_output_file(self):
        """出力ファイルIDがない場合のテスト"""
        # モッククライアントを作成
        mock_client = Mock()
        mock_batch = Mock()
        mock_batch.status = "completed"
        mock_batch.output_file_id = None  # output_file_id なし

        mock_client.batches.retrieve.return_value = mock_batch

        processor = OpenAIBatchProcessor("test_key", client=mock_client)

        with pytest.raises(APIError, match="出力ファイルIDが見つかりません"):
            processor.download_batch_results("batch_123", Path("output"))


class TestIntegration:
    """統合テスト"""

    @patch("pathlib.Path.exists")
    def test_full_workflow_success(self, mock_exists):
        """完全なワークフローの成功テスト"""
        # モッククライアントを作成
        mock_client = Mock()

        # ファイルアップロード用のモック
        mock_file = Mock()
        mock_file.id = "file_123"
        mock_client.files.create.return_value = mock_file

        # バッチ作成用のモック
        mock_batch = Mock()
        mock_batch.id = "batch_123"
        mock_client.batches.create.return_value = mock_batch

        # ステータス確認用のモック
        mock_status_batch = Mock()
        mock_status_batch.id = "batch_123"
        mock_status_batch.status = "completed"
        mock_status_batch.endpoint = "/v1/chat/completions"
        mock_status_batch.input_file_id = "file_123"
        mock_status_batch.output_file_id = "file_456"
        mock_status_batch.error_file_id = None
        mock_status_batch.created_at = 1234567890
        mock_status_batch.in_progress_at = 1234567891
        mock_status_batch.expires_at = 1234567999
        mock_status_batch.completed_at = 1234567895
        mock_status_batch.failed_at = None
        mock_status_batch.expired_at = None
        mock_status_batch.request_counts = {"total": 10, "completed": 10, "failed": 0}
        mock_status_batch.metadata = {}

        # ダウンロード用のモック
        mock_file_response = Mock()
        mock_file_response.content = b"result content"
        mock_client.files.content.return_value = mock_file_response
        mock_client.batches.retrieve.return_value = mock_status_batch

        processor = OpenAIBatchProcessor("test_key", client=mock_client)
        jsonl_path = Path("test.jsonl")
        output_dir = Path("output")
        mock_exists.return_value = True

        with (
            patch("builtins.open", mock_open(read_data=b"test data")),
            patch("pathlib.Path.mkdir"),
        ):
            # バッチ処理開始
            batch_id = processor.start_batch_processing(jsonl_path)
            assert batch_id == "batch_123"

            # ステータス確認
            status = processor.get_batch_status(batch_id)
            assert status["status"] == "completed"

            # 結果ダウンロード
            result_path = processor.download_batch_results(batch_id, output_dir)
            assert result_path == output_dir / "batch_results_batch_123.jsonl"
