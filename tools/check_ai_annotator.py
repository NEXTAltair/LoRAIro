# tools/check_ai_annotator.py
import json  # JSON出力を追加
from pathlib import Path
from pprint import pprint

# Import PHashAnnotationResults for type hinting
from image_annotator_lib import PHashAnnotationResults
from PIL import Image

from lorairo.annotations.ai_annotator import (
    AiAnnotatorError,
    call_annotate_library,
    get_available_annotator_models,
)
from lorairo.utils.log import logger
from lorairo.utils.tools import calculate_phash

PROJECT_ROOT = Path.cwd()
# 出力先ディレクトリを tools ディレクトリに設定
OUTPUT_DIR = PROJECT_ROOT / "tools"
OUTPUT_DIR.mkdir(exist_ok=True)  # Ensure the output directory exists

# 出力ファイル名定義
MODELS_OUTPUT_TXT = OUTPUT_DIR / "annotator_models.txt"
RESULTS_OUTPUT_JSON = OUTPUT_DIR / "annotator_results.json"
RESULTS_OUTPUT_TXT = OUTPUT_DIR / "annotator_results.txt"


def main() -> None:
    """AI アノテーターモジュールの動作確認と結果ファイル出力"""
    available_models: list[str] = []
    # Initialize results as None | PHashAnnotationResults
    results: PHashAnnotationResults | None = None
    test_image_path_str = str(PROJECT_ROOT / "tests/resources/img/1_img/file01.webp")
    phash = ""

    try:
        # --- 1. 利用可能なモデルを取得 ---
        available_models = get_available_annotator_models()
        logger.info("--- 利用可能なモデル --- ")
        pprint(available_models)

        # モデルリストをテキストファイルに出力
        try:
            with open(MODELS_OUTPUT_TXT, "w", encoding="utf-8") as f:
                f.write("--- 利用可能なモデル ---\n")
                pprint(available_models, stream=f)
            logger.info(f"利用可能なモデルリストを {MODELS_OUTPUT_TXT} に出力しました。")
        except OSError as e:
            logger.error(f"{MODELS_OUTPUT_TXT} への書き込み中にエラーが発生しました: {e}")

        if not available_models:
            logger.warning("利用可能なモデルがありません。アノテーションテストをスキップします。")
            # results は空のままになる
        else:
            # --- 2. テスト用画像でアノテーション実行 ---
            test_image_path = Path(test_image_path_str)
            try:
                image = Image.open(test_image_path)
                logger.info(f"--- テスト画像読み込み成功: {test_image_path} ---")
            except FileNotFoundError:
                logger.error(f"--- エラー: テスト画像が見つかりません: {test_image_path} ---")
                logger.error("アノテーションテストを続行できません。")
                # results は空のままになる
                return  # アノテーション実行前に終了

            # Use all available models for testing
            models_to_test = available_models  # すべてのモデルを使用する
            logger.info(f"--- アノテーション実行 ({models_to_test}) ---")
            phash = calculate_phash(test_image_path)
            logger.info(f"--- テスト画像の pHash: {phash} ---")
            # Assign result if annotation is successful
            results = call_annotate_library([image], models_to_test, [phash])

    except AiAnnotatorError as e:
        logger.error("--- AiAnnotatorError が発生しました --- ")
        logger.error(e)
    except ValueError as e:
        logger.error("--- ValueError が発生しました --- ")
        logger.error(e)
    except Exception:
        logger.exception("--- 予期しないエラーが発生しました --- ")
    finally:
        # --- 3. 結果をファイルに出力 ---

        # 3.1 JSON形式で出力
        output_data_json = {
            "available_models": available_models,
            "test_image_path": test_image_path_str,
            "test_image_phash": phash,
            # Use results if not None, otherwise provide a default (e.g., empty dict or None)
            "annotation_results": results if results is not None else {},
        }
        try:
            with open(RESULTS_OUTPUT_JSON, "w", encoding="utf-8") as f:
                # indent=2 で整形して出力, ensure_ascii=False で日本語をそのまま出力
                json.dump(output_data_json, f, indent=2, ensure_ascii=False)
            logger.info(f"アノテーション結果をJSON形式で {RESULTS_OUTPUT_JSON} に出力しました。")
        except OSError as e:
            logger.error(f"{RESULTS_OUTPUT_JSON} への書き込み中にエラーが発生しました: {e}")
        except TypeError as e:  # JSONシリアライズ不可能な型が含まれる場合
            logger.error(f"結果のJSONシリアライズ中にエラーが発生しました: {e}")
            logger.error("出力データを確認してください:", output_data_json)

        # 3.2 テキスト形式で出力
        try:
            with open(RESULTS_OUTPUT_TXT, "w", encoding="utf-8") as f:
                f.write("--- AI Annotator Check Results ---\n\n")
                f.write("--- 利用可能なモデル ---\n")
                pprint(available_models, stream=f)
                f.write("\n")

                # Check if annotation was attempted (models were available)
                if available_models:
                    f.write("--- テスト画像 ---\n")
                    f.write(f"Path: {test_image_path_str}\n")
                    f.write(f"pHash: {phash if phash else 'N/A (Annotation not run)'}\n\n")

                f.write("--- アノテーション結果 ---\n")
                # Check if results were successfully obtained
                if results is None:
                    f.write("結果は取得できませんでした（エラー発生またはモデルなし）。\n")
                elif not results:  # Check if results dict itself is empty (shouldn't happen if successful)
                    f.write("結果は空でした。\n")
                else:
                    for res_phash, model_results in results.items():
                        f.write(f"\n[画像 pHash: {res_phash}]\n")
                        for model_name, result_data in model_results.items():
                            f.write(f"  - モデル: {model_name}\n")
                            tags = result_data.get("tags")
                            output = result_data.get("formatted_output")
                            error = result_data.get("error")
                            f.write(f"    Tags: {tags if tags else 'N/A'}\n")
                            # formatted_outputが複雑なオブジェクトの場合、pprintを使うと見やすいかも
                            f.write(f"    Formatted Output: {output if output else 'N/A'}\n")
                            f.write(f"    Error: {error if error else 'None'}\n")
            logger.info(f"アノテーション結果をテキスト形式で {RESULTS_OUTPUT_TXT} に出力しました。")
        except OSError as e:
            logger.error(f"{RESULTS_OUTPUT_TXT} への書き込み中にエラーが発生しました: {e}")


if __name__ == "__main__":
    # ログ設定は lorairo.utils.log の初期化に依存
    main()
