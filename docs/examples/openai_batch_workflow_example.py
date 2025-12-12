"""OpenAI Batch API 使用例

このファイルは OpenAI Batch API を使用したバッチ処理の実装例です。
実際のプロダクションコードでは、非同期処理やワーカースレッドを使用することを推奨します。

使用方法:
    from lorairo.services.openai_batch_processor import OpenAIBatchProcessor
    from lorairo.services.batch_utils import (
        create_batch_jsonl,
        monitor_batch_progress,
        parse_batch_results,
    )
    from pathlib import Path

    # 1. 初期化
    processor = OpenAIBatchProcessor(api_key="your-openai-api-key")

    # 2. JSONLファイル作成
    image_paths = [Path("image1.jpg"), Path("image2.jpg")]
    prompt = "この画像を詳しく説明してください。"
    jsonl_path = create_batch_jsonl(image_paths, prompt)

    # 3. バッチ処理開始
    batch_id = processor.start_batch_processing(jsonl_path)

    # 4. 進行状況監視（非同期推奨）
    # 注意: monitor_batch_progress() は同期的に実行されるため、
    # GUIアプリケーションではワーカースレッドで実行してください。
    final_status = monitor_batch_progress(processor, batch_id)

    # 5. 結果取得
    if final_status == "completed":
        output_dir = Path("batch_results")
        processor.download_batch_results(batch_id, output_dir)
        raw_results = processor.get_batch_results(output_dir)
        parsed_results = parse_batch_results(raw_results)
"""

from pathlib import Path
from typing import Any

from lorairo.services.batch_utils import (
    create_batch_jsonl,
    monitor_batch_progress,
    parse_batch_results,
)
from lorairo.services.openai_batch_processor import OpenAIBatchProcessor
from lorairo.utils.log import logger


def example_batch_workflow() -> dict[str, dict[str, Any]] | None:
    """
    OpenAIバッチ処理の使用例
    OpenAI SDKを使用したより信頼性の高い実装

    Warning:
        この関数は同期的に実行されるため、GUIアプリケーションでは
        ワーカースレッドで実行することを推奨します。
    """
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
        # 注意: この関数は同期的に実行されるため、GUIアプリケーションでは
        # ワーカースレッドで実行してください。
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

