"""OpenAI Batch API専用プロセッサー

image-annotator-libがバッチ処理に対応するまで一時的に保持する
OpenAI Batch API機能の専用実装
"""

import json
import time
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI
from openai.types import Batch

from lorairo.utils.log import logger


class APIError(Exception):
    """API関連エラーの基底クラス"""

    def __init__(
        self,
        message: str,
        api_provider: str = "",
        error_code: str = "",
        status_code: int = 0,
    ):
        super().__init__(message)
        self.api_provider = api_provider
        self.error_code = error_code
        self.status_code = status_code

    def __str__(self):
        parts = [f"{self.api_provider} API Error: {self.args[0]}"]
        if self.error_code:
            parts.append(f"Code: {self.error_code}")
        if self.status_code:
            parts.append(f"Status: {self.status_code}")
        return " | ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """エラー情報を辞書形式で返す"""
        return {
            "message": self.args[0],
            "api_provider": self.api_provider,
            "error_code": self.error_code,
            "status_code": self.status_code,
        }

    @staticmethod
    def check_response(response: requests.Response, api_provider: str) -> None:
        """HTTPレスポンスをチェックしてエラーの場合は例外を発生させる"""
        if response.status_code == 200:
            return

        error_message = "Unknown error"
        try:
            error_data = response.json()
            if "error" in error_data and "message" in error_data["error"]:
                error_message = error_data["error"]["message"]
        except json.JSONDecodeError:
            pass

        if response.status_code == 401:
            error_message = "APIキー認証エラー"
        elif response.status_code == 400:
            if "error" not in locals():
                error_message = "Bad request"
        else:
            error_message = f"不明なHTTPエラー: {response.status_code}"

        raise APIError(error_message, api_provider, status_code=response.status_code)


class OpenAIBatchProcessor:
    """OpenAI Batch API専用プロセッサー

    image-annotator-libがバッチ処理に対応するまでの一時的な実装
    OpenAI SDKのライブラリ機能を最大限活用
    """

    def __init__(self, api_key: str, client: OpenAI | None = None) -> None:
        """OpenAIBatchProcessorを初期化

        Args:
            api_key (str): OpenAI APIキー
            client (OpenAI | None): テスト用のOpenAIクライアント（省略時は新規作成）
        """
        self.client = client or OpenAI(api_key=api_key)
        self.api_key = api_key
        self.request_interval = 1.0
        self.last_request_time = 0.0

    def _wait_for_rate_limit(self) -> None:
        """レート制限のための待機処理"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.request_interval:
            wait_time = self.request_interval - time_since_last_request
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def start_batch_processing(self, jsonl_path: Path) -> str:
        """
        JSONLファイルをアップロードしてバッチ処理を開始する。

        Args:
            jsonl_path (Path): アップロードするJSONLファイルのパス

        Returns:
            str: バッチ処理のID

        Raises:
            APIError: API呼び出しでエラーが発生した場合
            FileNotFoundError: JSONLファイルが見つからない場合
        """
        if not jsonl_path.exists():
            raise FileNotFoundError(f"JSONLファイルが見つかりません: {jsonl_path}")

        logger.info(f"OpenAIバッチ処理を開始します: {jsonl_path}")

        try:
            # 1. ファイルアップロード
            with open(jsonl_path, "rb") as file:
                batch_input_file = self.client.files.create(file=file, purpose="batch")

            logger.debug(f"ファイルアップロード完了: {batch_input_file.id}")

            # 2. バッチ処理を開始
            batch = self.client.batches.create(
                input_file_id=batch_input_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )

            logger.info(f"OpenAIバッチ処理が開始されました。ID: {batch.id}")
            return batch.id

        except Exception as e:
            raise APIError(f"バッチ処理開始中にエラーが発生しました: {e}", "OpenAI")

    def get_batch_status(self, batch_id: str) -> dict[str, Any]:
        """
        バッチ処理のステータスを取得する。

        Args:
            batch_id (str): バッチ処理のID

        Returns:
            dict[str, Any]: バッチ処理のステータス情報

        Raises:
            APIError: API呼び出しでエラーが発生した場合
        """
        try:
            batch = self.client.batches.retrieve(batch_id)
            # Batchオブジェクトを辞書に変換して返す
            return {
                "id": batch.id,
                "status": batch.status,
                "endpoint": batch.endpoint,
                "input_file_id": batch.input_file_id,
                "output_file_id": batch.output_file_id,
                "error_file_id": batch.error_file_id,
                "created_at": batch.created_at,
                "in_progress_at": batch.in_progress_at,
                "expires_at": batch.expires_at,
                "completed_at": batch.completed_at,
                "failed_at": batch.failed_at,
                "expired_at": batch.expired_at,
                "request_counts": batch.request_counts,
                "metadata": batch.metadata,
            }

        except Exception as e:
            raise APIError(f"バッチステータス取得中にエラーが発生しました: {e}", "OpenAI")

    def get_batch_results(self, batch_result_dir: Path) -> dict[str, str]:
        """
        OpenAI API のバッチ処理結果を読み込み、解析します。

        Args:
            batch_result_dir (Path): バッチ結果ファイルが格納されているディレクトリのパス。

        Returns:
            dict[str, str]: custom_idをキー、分析結果を値とする辞書。

        Raises:
            FileNotFoundError: 結果ディレクトリが見つからない場合
            json.JSONDecodeError: JSONLファイルの解析に失敗した場合
        """
        if not batch_result_dir.exists():
            raise FileNotFoundError(f"バッチ結果ディレクトリが見つかりません: {batch_result_dir}")

        logger.info(f"バッチ処理結果を読み込み中: {batch_result_dir}")
        results: dict[str, str] = {}

        jsonl_files = list(batch_result_dir.glob("*.jsonl"))
        if not jsonl_files:
            logger.warning(f"JSONLファイルが見つかりません: {batch_result_dir}")
            return results

        for jsonl_file in jsonl_files:
            logger.debug(f"処理中: {jsonl_file}")
            try:
                with open(jsonl_file, encoding="utf-8") as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                            if "custom_id" in data and "response" in data:
                                response_data = data["response"]
                                if "body" in response_data and "choices" in response_data["body"]:
                                    custom_id = data["custom_id"]
                                    choices = response_data["body"]["choices"]
                                    if (
                                        choices
                                        and "message" in choices[0]
                                        and "content" in choices[0]["message"]
                                    ):
                                        content = choices[0]["message"]["content"]
                                        results[custom_id] = content
                                    else:
                                        logger.warning(f"無効な応答構造 in {jsonl_file}:{line_num}")
                                else:
                                    logger.warning(f"レスポンスボディが不正 in {jsonl_file}:{line_num}")
                            else:
                                logger.warning(f"必須フィールドが不足 in {jsonl_file}:{line_num}")
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON解析エラー in {jsonl_file}:{line_num}: {e}")
                            continue

            except UnicodeDecodeError as e:
                logger.error(f"ファイル読み込みエラー {jsonl_file}: {e}")
                continue

        logger.info(f"バッチ処理結果読み込み完了: {len(results)}件")
        return results

    def download_batch_results(self, batch_id: str, output_dir: Path) -> Path:
        """
        完了したバッチ処理の結果をダウンロードする。

        Args:
            batch_id (str): バッチ処理のID
            output_dir (Path): 結果を保存するディレクトリ

        Returns:
            Path: ダウンロードしたファイルのパス

        Raises:
            APIError: API呼び出しでエラーが発生した場合
            ValueError: バッチ処理が完了していない場合
        """
        try:
            # バッチステータス確認
            batch = self.client.batches.retrieve(batch_id)

            if batch.status != "completed":
                raise ValueError(f"バッチ処理が完了していません。現在のステータス: {batch.status}")

            if not batch.output_file_id:
                raise APIError("出力ファイルIDが見つかりません", "OpenAI")

            # ファイルダウンロード
            file_response = self.client.files.content(batch.output_file_id)

            # 出力ディレクトリ作成
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / f"batch_results_{batch_id}.jsonl"

            with open(output_file, "wb") as f:
                f.write(file_response.content)

            logger.info(f"バッチ結果をダウンロードしました: {output_file}")
            return output_file

        except Exception as e:
            raise APIError(f"ダウンロード中にエラーが発生しました: {e}", "OpenAI")

    def list_batches(self, limit: int = 20) -> list[dict[str, Any]]:
        """
        バッチのリストを取得する。

        Args:
            limit (int): 取得するバッチ数の上限

        Returns:
            list[dict[str, Any]]: バッチ情報のリスト

        Raises:
            APIError: API呼び出しでエラーが発生した場合
        """
        try:
            batches = self.client.batches.list(limit=limit)
            return [
                {
                    "id": batch.id,
                    "status": batch.status,
                    "endpoint": batch.endpoint,
                    "created_at": batch.created_at,
                    "completed_at": batch.completed_at,
                    "request_counts": batch.request_counts,
                }
                for batch in batches.data
            ]

        except Exception as e:
            raise APIError(f"バッチリスト取得中にエラーが発生しました: {e}", "OpenAI")

    def cancel_batch(self, batch_id: str) -> dict[str, Any]:
        """
        バッチ処理をキャンセルする。

        Args:
            batch_id (str): キャンセルするバッチのID

        Returns:
            dict[str, Any]: キャンセル後のバッチ情報

        Raises:
            APIError: API呼び出しでエラーが発生した場合
        """
        try:
            batch = self.client.batches.cancel(batch_id)
            return {
                "id": batch.id,
                "status": batch.status,
                "cancelled_at": getattr(batch, "cancelled_at", None),
            }

        except Exception as e:
            raise APIError(f"バッチキャンセル中にエラーが発生しました: {e}", "OpenAI")
