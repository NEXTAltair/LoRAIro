"""バッチ処理用のユーティリティ関数

OpenAI Batch APIで使用するJSONLファイルの生成等のヘルパー関数
"""

import json
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
            import base64

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
    import re

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

    Note:
        この関数は同期的に実行されるため、長時間ブロックする可能性があります。
        実際の使用では非同期処理やバックグラウンドタスクの実装を推奨します。
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


# 使用例
def example_batch_workflow() -> dict[str, dict[str, Any]] | None:
    """
    OpenAIバッチ処理の使用例
    OpenAI SDKを使用したより信頼性の高い実装
    """
    from lorairo.services.openai_batch_processor import OpenAIBatchProcessor

    try:
        # 初期化
        processor = OpenAIBatchProcessor(api_key="your-openai-api-key")

        # 1. JSONLファイル作成
        image_paths = [Path("image1.jpg"), Path("image2.jpg")]
        prompt = "この画像を詳しく説明してください。"
        jsonl_path = create_batch_jsonl(image_paths, prompt)

        # 2. バッチ処理開始
        batch_id = processor.start_batch_processing(jsonl_path)

        # 3. 進行状況監視(実際にはバックグラウンドで実行)
        final_status = monitor_batch_progress(processor, batch_id)

        # 4. 結果取得
        if final_status == "completed":
            output_dir = Path("batch_results")
            processor.download_batch_results(batch_id, output_dir)

            # 5. 結果解析
            raw_results = processor.get_batch_results(output_dir)
            parsed_results = parse_batch_results(raw_results)

            logger.info(f"バッチ処理が正常に完了しました。結果: {len(parsed_results)}件")
            return parsed_results
        else:
            logger.error(f"バッチ処理が失敗しました: {final_status}")
            return None

    except Exception as e:
        logger.error(f"バッチ処理ワークフロー中にエラーが発生しました: {e}")
        return None
