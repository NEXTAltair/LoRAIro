"""バッチ処理用のユーティリティ関数

OpenAI Batch APIで使用するJSONLファイルの生成等のヘルパー関数
"""

import base64
import json
import re
from pathlib import Path
from typing import Any

from lorairo.utils.log import logger


def create_batch_jsonl(
    image_paths: list[Path], prompt: str, model: str = "gpt-4o", output_path: Path | None = None
) -> Path:
    """
    OpenAI Batch API用のJSONLファイルを作成する。

    Args:
        image_paths (List[Path]): 処理する画像ファイルのパスリスト
        prompt (str): 画像に対するプロンプト
        model (str): 使用するOpenAIモデル(デフォルト: gpt-4o)
        output_path (Path | None): 出力ファイルパス(Noneの場合は自動生成)

    Returns:
        Path: 作成されたJSONLファイルのパス

    Raises:
        FileNotFoundError: 画像ファイルが見つからない場合
        ValueError: 無効な引数が指定された場合
    """
    if not image_paths:
        raise ValueError("image_pathsは空にできません")

    if not prompt.strip():
        raise ValueError("promptは空にできません")

    # 出力パスの決定
    if output_path is None:
        timestamp = str(int(Path().stat().st_mtime))
        output_path = Path(f"batch_request_{timestamp}.jsonl")

    logger.info(f"バッチJSONLファイルを作成中: {output_path}")

    with open(output_path, "w", encoding="utf-8") as f:
        for i, image_path in enumerate(image_paths):
            if not image_path.exists():
                logger.warning(f"画像ファイルが見つかりません: {image_path}")
                continue

            # 画像をbase64エンコード
            with open(image_path, "rb") as img_file:
                base64_image = base64.b64encode(img_file.read()).decode("utf-8")

            # バッチリクエストのJSONオブジェクト作成
            request_data = {
                "custom_id": f"request_{i}_{image_path.stem}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{image_path.suffix[1:]};base64,{base64_image}",
                                        "detail": "high",
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": 3000,
                },
            }

            # JSONLファイルに1行として追加
            f.write(json.dumps(request_data, ensure_ascii=False) + "\n")

    logger.info(f"バッチJSONLファイル作成完了: {output_path} ({len(image_paths)}件)")
    return output_path


def parse_batch_results(results_dict: dict[str, str]) -> dict[str, dict[str, Any]]:
    """
    バッチ処理結果を解析して構造化データに変換する。

    Args:
        results_dict (dict[str, str]): OpenAIBatchProcessor.get_batch_results()の結果

    Returns:
        dict[str, dict[str, Any]]: 画像名をキーとした解析結果辞書

    Example:
        {
            "image1.jpg": {
                "caption": "A beautiful sunset over the ocean",
                "tags": ["sunset", "ocean", "landscape"],
                "custom_id": "request_0_image1"
            }
        }
    """
    parsed_results = {}

    for custom_id, content in results_dict.items():
        try:
            # custom_idから画像名を抽出 (format: "request_{i}_{image_stem}")
            parts = custom_id.split("_")
            if len(parts) >= 3:
                image_name = "_".join(parts[2:])  # 画像名部分を結合
            else:
                image_name = custom_id

            # コンテンツを解析(フォーマットは用途に応じて調整)
            parsed_data = {
                "caption": content.strip(),
                "tags": _extract_tags_from_content(content),
                "custom_id": custom_id,
                "raw_content": content,
            }

            parsed_results[image_name] = parsed_data

        except Exception as e:
            logger.error(f"結果解析エラー for {custom_id}: {e}")
            continue

    logger.info(f"バッチ結果解析完了: {len(parsed_results)}件")
    return parsed_results


def _extract_tags_from_content(content: str) -> list[str]:
    """
    コンテンツからタグを抽出する簡単なヘルパー関数。

    実際の実装では、プロンプトの形式に応じて調整が必要。

    Args:
        content (str): AIからのレスポンステキスト

    Returns:
        List[str]: 抽出されたタグのリスト
    """
    # 簡単な実装例:カンマ区切りでタグが含まれている場合を想定
    tags = []

    # "Tags:" などの後にタグが列挙されている場合
    tag_match = re.search(r"\b(?:tags?|keywords?)\s*[:]\s*([^\n]+)", content, re.IGNORECASE)
    if tag_match:
        tag_text = tag_match.group(1)
        tags = [tag.strip() for tag in tag_text.split(",") if tag.strip()]

    return tags


def monitor_batch_progress(processor: Any, batch_id: str, check_interval: int = 60) -> str:
    """
    バッチ処理の進行状況を監視する。

    Args:
        processor: OpenAIBatchProcessorのインスタンス
        batch_id (str): 監視するバッチID
        check_interval (int): チェック間隔(秒)

    Returns:
        str: 最終的なバッチステータス

    Warning:
        この関数は同期的に実行されるため、長時間ブロックする可能性があります。
        GUIアプリケーションやワーカースレッド内で使用する場合は、非同期処理や
        バックグラウンドタスクの実装を強く推奨します。
        `check_interval` が大きい場合（60秒以上）、UIがフリーズする可能性があります。
    """
    import time

    logger.info(f"バッチ処理監視開始: {batch_id}")

    while True:
        try:
            status_info = processor.get_batch_status(batch_id)
            status = status_info.get("status", "unknown")

            logger.info(f"バッチステータス: {status}")

            if status in ["completed", "failed", "cancelled"]:
                logger.info(f"バッチ処理終了: {status}")
                return status

            elif status in ["validating", "in_progress", "finalizing"]:
                logger.info(f"処理中... 次回チェック: {check_interval}秒後")
                time.sleep(check_interval)

            else:
                logger.warning(f"不明なステータス: {status}")
                time.sleep(check_interval)

        except Exception as e:
            logger.error(f"ステータス確認エラー: {e}")
            time.sleep(check_interval)
