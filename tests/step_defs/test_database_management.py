# tests/step_defs/test_database_management.py

import re  # 日付範囲のパース用
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from PIL import Image
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.db_repository import (
    AnnotationsDict,
    CaptionAnnotationData,
    RatingAnnotationData,
    ScoreAnnotationData,
    TagAnnotationData,
)
from lorairo.database.schema import Image as SchemaImage
from lorairo.database.schema import Tag
from lorairo.storage.file_system import FileSystemManager

# Use __file__ based path for pytest-bdd compatibility
_FEATURE_FILE = Path(__file__).parent.parent / "features" / "database_management.feature"
scenarios(str(_FEATURE_FILE))

# --- Search Context Class --- #


class SearchContext:
    """検索結果を保持するコンテキストオブジェクト"""

    def __init__(self):
        self.results: list[dict[str, Any]] = []
        self.count: int = 0


# --- ヘルパー関数 ---


def parse_bool(value: str | None) -> bool:
    """文字列をbool値に変換します。

    'true' (大文字小文字無視) なら True を返します。
    空文字列、None、またはそれ以外の文字列の場合は False を返します。
    """
    if value is None:
        return False
    val = value.strip().lower()
    return val == "true"


def parse_optional_float(value: str | None) -> float | None:
    """文字列をfloat値に変換 (空文字やNoneはNoneを返す)"""
    if value is None or value.strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        print(f"警告: 不正な float 値: {value}")
        return None


def parse_optional_int(value: str | None) -> int | None:
    """文字列をint値に変換 (空文字やNoneはNoneを返す)"""
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        print(f"警告: 不正な int 値: {value}")
        return None


# --- Fixtures --- #


@pytest.fixture
def search_context() -> SearchContext:
    """検索コンテキストを提供するフィクスチャ"""
    return SearchContext()


# ... (Other existing fixtures: test_db_manager, fs_manager, test_image_path, etc.) ...

# --- Step Definitions (Given) --- #


# Use the new test_db_manager fixture
@given("データベースが初期化されている")
def given_db_initialized(test_db_manager: ImageDatabaseManager):
    """新しい test_db_manager が利用可能であることを確認"""
    assert test_db_manager is not None
    # Migrated_engine fixture already ensures DB is created and migrated
    # We can add a check for table existence if needed, but Alembic handles it.
    # For example, check total images initially is 0
    assert test_db_manager.get_total_image_count() == 0


@given(parsers.parse("データベースマネージャが初期化されている"))
@given("the database manager is initialized")
def db_manager(test_db_manager: ImageDatabaseManager) -> ImageDatabaseManager:
    """テスト用の ImageDatabaseManager インスタンスを返す"""
    # test_db_manager フィクスチャがインスタンスを提供するので、ここではそのまま返す
    assert test_db_manager is not None
    return test_db_manager


@given("モデルが登録されている")  # Feature ファイルの Background に合わせる
def given_models_registered(test_db_manager: ImageDatabaseManager):
    """初期データとしてモデルが登録されていることを確認する"""
    all_models = test_db_manager.get_models()  # model_types を含む辞書のリストを返すはず
    assert all_models, "モデルがDBに登録されていません"
    # 正しいアサーション: 各タイプが存在するかチェック
    assert any("tagger" in m.get("model_types", []) for m in all_models), (
        "初期データに 'tagger' タイプが見つかりません"
    )
    assert any("score" in m.get("model_types", []) for m in all_models), (
        "初期データに 'score' タイプが見つかりません"
    )
    assert any("rating" in m.get("model_types", []) for m in all_models), (
        "初期データに 'rating' タイプが見つかりません"
    )
    assert any("captioner" in m.get("model_types", []) for m in all_models), (
        "初期データに 'captioner' タイプが見つかりません"
    )


@given(parsers.parse('テスト用の画像ファイル "{image_name}" が存在する'))
def given_test_image_exists(test_image_path):
    """テスト用の画像ファイルが存在することを確認"""
    assert test_image_path.exists()


# Use new fixtures and return only image_id as before
@given("オリジナル画像が登録されている", target_fixture="image_registered")
def given_image_registered(
    test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager, test_image_path
):
    """新しい test_db_manager を使用して画像を登録し、IDを返す"""
    result = test_db_manager.register_original_image(test_image_path, fs_manager)
    assert result is not None, f"前提条件の画像登録に失敗: {test_image_path}"
    # Return only the image_id as the fixture value
    return result[0]


@given(
    parsers.parse("以下の画像とアノテーションが登録されている:"),
    target_fixture="registered_images_with_annotations",
)
def given_images_with_annotations_registered(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    test_image_dir: Path,  # テスト画像ディレクトリのフィクスチャを使用
    datatable,
    request,  # request フィクスチャを追加してコンテキストを共有
):
    """データテーブルに基づいて複数の画像とアノテーションを登録する"""
    registered_data = {}
    # データテーブルを処理 (リスト形式で受け取る前提に修正)
    header = [h.strip() for h in datatable[0]]  # .headings ではなくインデックス0でヘッダー取得
    rows = datatable[1:]  # .rows ではなくスライスでデータ行取得

    # 登録済みモデルIDをキャッシュ(毎回取得しないように)
    model_cache = {m["name"]: m["id"] for m in test_db_manager.get_models()}
    # テスト用にダミーのモデルIDマッピング(もしDBになければ)
    dummy_model_id_map = {
        "tag_model": model_cache.get("wd-vit-large-tagger-v3", 1),
        "caption_model": model_cache.get("GPT-4o", 1),
        "score_model": model_cache.get("cafe_aesthetic", 1),
        "rating_model": model_cache.get("classification_ViT-L-14_openai", 1),
    }

    for row_values_tuple in rows:
        row_data = {header[i]: val for i, val in enumerate(row_values_tuple)}

        image_filename = row_data.get("image_file")
        if not image_filename:
            print(f"警告: image_file が指定されていません。スキップします: {row_data}")
            continue

        # テスト画像パスを作成 (tests/resources/img/1_img/ 内のファイル名を想定)
        current_image_path = test_image_dir / image_filename
        # ファイル存在チェック (テストリソースが存在することを前提とする)
        if not current_image_path.exists():
            pytest.fail(f"テストに必要な画像ファイルが見つかりません: {current_image_path}")

        # 1. 画像を登録
        register_result = test_db_manager.register_original_image(current_image_path, fs_manager)
        if not register_result:
            pytest.fail(f"テストデータの画像登録に失敗: {current_image_path}")
        image_id, _ = register_result
        registered_data[image_filename] = {"id": image_id, "annotations": {}}

        # 2. アノテーションを準備
        annotations_to_save: AnnotationsDict = {"tags": [], "captions": [], "scores": [], "ratings": []}

        # タグ処理
        tags_str = row_data.get("tags")
        if tags_str:
            tags = [t.strip() for t in tags_str.split(",")]
            # 簡略化のため、最初のタグモデルを使用
            tag_model_id = dummy_model_id_map["tag_model"]
            annotations_to_save["tags"] = [
                {
                    "tag": tag,
                    "model_id": tag_model_id,
                    "confidence_score": 0.9,
                    "existing": False,
                    "is_edited_manually": False,
                    "tag_id": None,
                }
                for tag in tags
            ]
            registered_data[image_filename]["annotations"]["tags"] = tags

        # キャプション処理
        caption_str = row_data.get("caption")
        if caption_str:
            # 簡略化のため、最初のキャプションモデルを使用
            caption_model_id = dummy_model_id_map["caption_model"]
            annotations_to_save["captions"] = [
                {
                    "caption": caption_str,
                    "model_id": caption_model_id,
                    "existing": False,
                    "is_edited_manually": False,
                }
            ]
            registered_data[image_filename]["annotations"]["caption"] = caption_str

        # スコア処理 (もしテーブルにあれば)
        score_str = row_data.get("score")
        if score_str:
            score_value = parse_optional_float(score_str)
            if score_value is not None:
                score_model_id = dummy_model_id_map["score_model"]
                annotations_to_save["scores"].append(
                    {"score": score_value, "model_id": score_model_id, "is_edited_manually": False}
                )
                registered_data[image_filename]["annotations"]["score"] = score_value

        # 3. アノテーションを保存
        if any(annotations_to_save.values()):
            try:
                test_db_manager.repository.save_annotations(image_id, annotations_to_save)
            except Exception as e:
                pytest.fail(f"画像ID {image_id} のアノテーション保存中にエラー: {e}")

        # 4. 手動編集フラグやレーティングの更新 (必要に応じて)
        manual_edit_target = row_data.get("manual_edit_target")
        if manual_edit_target and manual_edit_target != "none":
            try:
                edit_type, edit_identifier = (
                    manual_edit_target.split(":", 1)
                    if ":" in manual_edit_target
                    else (manual_edit_target, None)
                )
                # 対応するアノテーションIDを探して更新フラグを立てる (簡略化)
                # 実際のテストでは、より厳密なアノテーション特定が必要
                ann_data = test_db_manager.get_image_annotations(image_id)
                target_ann_id = None
                if edit_type == "tag" and edit_identifier:
                    for tag_ann in ann_data.get("tags", []):
                        if tag_ann.get("tag") == edit_identifier:
                            target_ann_id = tag_ann.get("id")
                            break
                    if target_ann_id:
                        # Assuming repository has the method now:
                        test_db_manager.repository.update_annotation_manual_edit_flag(
                            "tags", target_ann_id, True
                        )
                        # with test_db_manager.repository.session_factory() as session:
                        #     session.execute(
                        #         sa.update(Tag)
                        #         .where(Tag.id == target_ann_id)
                        #         .values(is_edited_manually=True)
                        #     )
                        #     session.commit()
                elif edit_type == "caption":
                    if ann_data.get("captions"):
                        target_ann_id = ann_data["captions"][0].get("id")
                    if target_ann_id:
                        test_db_manager.repository.update_annotation_manual_edit_flag(
                            "captions", target_ann_id, True
                        )
                        # with test_db_manager.repository.session_factory() as session:
                        #     session.execute(
                        #         sa.update(Caption)
                        #         .where(Caption.id == target_ann_id)
                        #         .values(is_edited_manually=True)
                        #     )
                        #     session.commit()
                elif edit_type == "score":
                    if ann_data.get("scores"):
                        target_ann_id = ann_data["scores"][0].get("id")
                    if target_ann_id:
                        test_db_manager.repository.update_annotation_manual_edit_flag(
                            "scores", target_ann_id, True
                        )
                        # with test_db_manager.repository.session_factory() as session:
                        #     session.execute(
                        #         sa.update(Score)
                        #         .where(Score.id == target_ann_id)
                        #         .values(is_edited_manually=True)
                        #     )
                        #     session.commit()
                print(
                    f"画像ID {image_id} の {manual_edit_target} (ID: {target_ann_id}) を手動編集済みに設定"
                )
            except Exception as e:
                pytest.fail(f"画像ID {image_id} の手動編集フラグ設定中にエラー: {e}")

        manual_rating = row_data.get("manual_rating")
        if manual_rating:
            try:
                test_db_manager.repository.update_manual_rating(image_id, manual_rating)
                # with test_db_manager.repository.session_factory() as session:
                #     session.execute(
                #         sa.update(SchemaImage)
                #         .where(SchemaImage.id == image_id)
                #         .values(manual_rating=manual_rating)
                #     )
                #     session.commit()
                print(f"画像ID {image_id} の manual_rating を {manual_rating} に設定")
            except Exception as e:
                pytest.fail(f"画像ID {image_id} の手動レーティング設定中にエラー: {e}")

        # ★★★ NSFWテストデータ用の手動レーティング設定を追加 ★★★
        # filenameとtagsで判定 (tags_str が None でないことも確認)
        if image_filename == "file02.webp" and tags_str and "nsfw" in tags_str.lower():
            try:
                nsfw_rating = "R"  # または 'X', 'XXX'
                test_db_manager.repository.update_manual_rating(image_id, nsfw_rating)
                # with test_db_manager.repository.session_factory() as session:
                #     session.execute(
                #         sa.update(SchemaImage)
                #         .where(SchemaImage.id == image_id)
                #         .values(manual_rating=nsfw_rating)
                #     )
                #     session.commit()
                print(
                    f"画像ID {image_id} ({image_filename}) の manual_rating を NSFWテスト用に '{nsfw_rating}' に設定"
                )
            except Exception as e:
                pytest.fail(f"画像ID {image_id} のNSFWテスト用レーティング設定中にエラー: {e}")
        # ★★★ 追加ここまで ★★★

        # 日付オフセット処理 (もしテーブルにあれば)
        offset_days_str = row_data.get("registration_offset_days")
        if offset_days_str:
            try:
                offset_days = int(offset_days_str)
                # わずかなオフセットを追加して境界値問題を回避
                # offset 0日は現在時刻、1日は24時間+1秒前、2日は48時間+1秒前とする
                if offset_days == 0:
                    target_time = datetime.now(UTC)
                else:
                    # timedelta に秒単位のずれを追加
                    target_time = datetime.now(UTC) - timedelta(days=offset_days, seconds=1)

                # created_at と updated_at を直接更新 (テスト目的)
                with test_db_manager.repository.session_factory() as session:
                    session.execute(
                        sa.update(SchemaImage)  # Use imported SchemaImage model
                        .where(SchemaImage.id == image_id)  # Use SchemaImage.id
                        .values(created_at=target_time, updated_at=target_time)
                    )
                    # アノテーションの日付も更新 (簡略化のためタグのみ)
                    if annotations_to_save["tags"]:
                        session.execute(
                            sa.update(Tag)  # Use imported Tag model
                            .where(Tag.image_id == image_id)
                            .values(created_at=target_time, updated_at=target_time)
                        )
                    session.commit()  # Commit within the session context
                print(
                    f"画像ID {image_id} の登録日時を 約{offset_days} 日前に設定 (微調整あり)"
                )  # ログメッセージ変更
            except Exception as e:
                pytest.fail(f"画像ID {image_id} の日付オフセット設定中にエラー: {e}")

    # 登録したIDなどを後続ステップで使えるようにコンテキストに保存
    # request.config.cache.set("registered_images_context", registered_data)
    return registered_data  # フィクスチャとして返す


# --- Step Definitions (When) --- #


# Use new fixtures and capture result structure (tuple[int, dict])
@when("画像を登録する", target_fixture="register_image_result")
def when_register_image(
    test_db_manager: ImageDatabaseManager, fs_manager: FileSystemManager, test_image_path
):
    """新しい test_db_manager を使用して画像を登録する"""
    result = test_db_manager.register_original_image(test_image_path, fs_manager)
    assert result is not None, f"画像登録に失敗: {test_image_path}"
    image_id, metadata = result
    assert isinstance(image_id, int)
    assert isinstance(metadata, dict)
    print(f"Registered image ID: {image_id}, Metadata keys: {metadata.keys()}")  # Debug print
    # Store both id and metadata for later steps
    return {"image_id": image_id, "metadata": metadata}


@when("処理済み画像を登録する", target_fixture="processed_image_id")
def when_register_processed_image(
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    image_registered: int,  # オリジナル画像のIDを受け取る
    test_image_path: Path,  # 元画像のパス情報 (ファイル名取得などに使う)
):
    """ダミーの処理済み画像を作成し、DBに登録する"""
    # ダミーの処理済み画像情報を作成
    processed_filename = f"{test_image_path.stem}_processed.webp"
    processed_path = fs_manager.resized_images_dir / processed_filename  # 属性名を修正
    dummy_info = {
        "width": 256,
        "height": 256,
        "mode": "RGB",
        "has_alpha": False,
        "filename": processed_filename,
        # 他のメタデータは省略 (必要なら追加)
    }

    # ダミーの画像ファイルを作成 (内容は問わない)
    dummy_image = Image.new("RGB", (cast(int, dummy_info["width"]), cast(int, dummy_info["height"])))
    dummy_image.save(processed_path, "WEBP")

    # DBに登録
    processed_id = test_db_manager.register_processed_image(
        image_id=image_registered, processed_path=processed_path, info=dummy_info
    )
    assert processed_id is not None, f"処理済み画像の登録に失敗: {processed_path}"
    print(f"Registered processed image ID: {processed_id} for original image ID: {image_registered}")
    return processed_id


@when("以下のアノテーションを保存する:", target_fixture="saved_annotations_data")
def when_save_annotations_with_datatable(
    test_db_manager: ImageDatabaseManager, image_registered: int, datatable
):
    """データテーブル形式のアノテーションを解析し、保存する"""
    annotations_dict: AnnotationsDict = {
        "tags": [],
        "captions": [],
        "scores": [],
        "ratings": [],
    }

    try:
        # データテーブルをリストとして処理するよう修正
        header = [h.strip() for h in datatable[0]]  # ヘッダー行を取得
        data_rows = datatable[1:]  # データ行を取得

        # Check for essential headers (can be adjusted)
        required_headers = {"type", "content", "model_id"}
        if not required_headers.issubset(set(header)):
            raise ValueError(f"データテーブルのヘッダーに必要なカラムが含まれていません: {header}")

        # ヘッダー名からインデックスへのマッピングを作成
        header_map = {name: idx for idx, name in enumerate(header)}

        for row_values_tuple in data_rows:
            # Ensure row_values is a list or tuple
            row_values = list(row_values_tuple) if isinstance(row_values_tuple, tuple) else row_values_tuple

            if len(row_values) != len(header):
                print(
                    f"警告 (行 {row_values_tuple}): データ行の値の数({len(row_values)})がヘッダー({len(header)})と一致しません: {row_values}。スキップします."
                )
                continue

            # ヘルパー関数で値を取得 (列が存在しない場合は None)
            def get_value(col_name):
                return (
                    row_values[header_map[col_name]].strip()
                    if col_name in header_map
                    and header_map[col_name] < len(row_values)
                    and row_values[header_map[col_name]] is not None
                    else None
                )

            # --- 各列の値をパース ---
            annotation_type = get_value("type")
            content = get_value("content")
            model_id_str = get_value("model_id")
            confidence_str = get_value("confidence_score")
            edited_str = get_value("is_edited_manually")
            existing_str = get_value("existing")
            tag_id_str = get_value("tag_id")

            if not annotation_type or not content or not model_id_str:
                print(
                    f"警告 (行 {row_values_tuple}): データテーブルの行が無効です (必須項目不足): type={annotation_type}, content={content}, model_id={model_id_str}。スキップします."
                )
                continue

            model_id = parse_optional_int(model_id_str)
            if model_id is None:
                print(f"警告 (行 {row_values_tuple}): 無効な model_id: {model_id_str}。スキップします.")
                continue  # 次の行へ

            confidence_score = parse_optional_float(confidence_str)
            is_edited = parse_bool(edited_str)
            existing = parse_bool(existing_str)
            tag_id = parse_optional_int(tag_id_str)

            # --- 型ごとに AnnotationsDict に追加 ---
            try:
                if annotation_type == "tag":
                    tag_data: TagAnnotationData = {
                        "tag": content,
                        "model_id": model_id,
                        "confidence_score": confidence_score,
                        "is_edited_manually": is_edited,
                        "existing": existing if existing is not None else False,
                        "tag_id": tag_id,
                    }
                    annotations_dict["tags"].append(tag_data)
                elif annotation_type == "caption":
                    caption_data: CaptionAnnotationData = {
                        "caption": content,
                        "model_id": model_id,
                        "existing": existing if existing is not None else False,
                        "is_edited_manually": is_edited,
                    }
                    annotations_dict["captions"].append(caption_data)
                elif annotation_type == "score":
                    score_value = parse_optional_float(content)
                    if score_value is None:
                        print(f"警告 (行 {row_values_tuple}): 無効な score 値: {content}。スキップします.")
                        continue  # 次の行へ
                    score_data: ScoreAnnotationData = {
                        "score": score_value,
                        "model_id": model_id,
                        "is_edited_manually": is_edited if is_edited is not None else False,
                    }
                    annotations_dict["scores"].append(score_data)
                elif annotation_type == "rating":
                    # rating の content は raw_rating_value とする
                    rating_data: RatingAnnotationData = {
                        "raw_rating_value": content,
                        "normalized_rating": content,  # テスト用に同じ値
                        "model_id": model_id,
                        "confidence_score": confidence_score,
                    }
                    annotations_dict["ratings"].append(rating_data)
                else:
                    print(
                        f"警告 (行 {row_values_tuple}): 未知のアノテーションタイプ: {annotation_type}。スキップします."
                    )

            except Exception as inner_e:  # 個々の行の処理エラーを捕捉
                print(
                    f"エラー (行 {row_values_tuple}): アノテーションデータの構造化中にエラー: {inner_e}, データ: {row_values}"
                )
                continue  # 次の行へ

    except Exception as e:
        print(f"エラー: データテーブルの処理中に予期せぬエラーが発生しました: {e}")
        import traceback

        traceback.print_exc()
        pytest.fail(f"データテーブル処理エラー: {e}")

    # --- 保存処理の実行 ---
    try:
        test_db_manager.repository.save_annotations(image_registered, annotations_dict)
        print(f"画像ID {image_registered} のアノテーションをDBに保存しました: {annotations_dict}")
    except Exception as save_e:
        print(f"エラー: 画像ID {image_registered} のアノテーション保存中にエラー: {save_e}")
        import traceback

        traceback.print_exc()
        pytest.fail(f"アノテーション保存エラー: {save_e}")

    # パースしたアノテーションデータを返す必要がある
    return annotations_dict


# --- 検索ステップ (`When`) ---


# タグ検索 (AND/OR)
# CONVERTER for TagSearchType
def TagSearchType(text: str) -> bool:
    """Parses 'AND' or 'OR' into a boolean for use_and."""
    if text.upper() == "AND":
        return True
    elif text.upper() == "OR":
        return False
    else:
        raise ValueError(f"Invalid tag search type: {text}. Must be 'AND' or 'OR'.")


@when(
    parsers.cfparse(
        'タグ "{tags_str}" {search_type:TagSearchType} で画像を検索する',
        extra_types={"TagSearchType": TagSearchType},
    )
)
def when_search_by_tags(
    test_db_manager: ImageDatabaseManager,
    registered_images_with_annotations: dict,  # データ確認用にフィクスチャを追加
    search_context: SearchContext,
    tags_str: str,
    search_type: bool,
):
    tags = [t.strip() for t in tags_str.split(",")]  # タグの分割ロジックは維持

    # # --- データ確認用コード --- #
    # try:
    #     # file01.webp の image_id を特定 (このテストケース固有)
    #     target_image_id = None
    #     for filename, data in registered_images_with_annotations.items():
    #         if filename == "file01.webp":
    #             target_image_id = data.get("id")
    #             break
    #     if target_image_id:
    #         print(
    #             f"--- DEBUG: Checking annotations for image_id {target_image_id} (file01.webp) before search ---"
    #         )
    #         db_annotations = test_db_manager.get_image_annotations(target_image_id)
    #         print(f"DEBUG: Tags found in DB: {db_annotations.get('tags')}")
    #         print(f"-----------------------------------------------------------------------------------")
    #     else:
    #         print("--- DEBUG: Could not find image_id for file01.webp in fixture data ---")
    # except Exception as e:
    #     print(f"--- DEBUG: Error fetching annotations for data check: {e} ---")
    # # --- データ確認用コードここまで --- #

    results, count = test_db_manager.get_images_by_filter(tags=tags, use_and=search_type)
    search_context.results = results
    search_context.count = count
    print(f"タグ検索実行: tags={tags}, use_and={search_type}, 結果件数={count}")


# キャプション検索 (部分/完全)
# CONVERTER for CaptionMatchType (simplified)
def CaptionMatchType(text: str) -> bool:
    """Parses '部分一致' or '完全一致' into a boolean for exact match."""
    if "部分一致" in text:
        return False
    elif "完全一致" in text:
        return True
    else:
        raise ValueError(f"Invalid caption match type: {text}")


@when(
    parsers.cfparse(
        "キャプション {caption_str} で{match_type:CaptionMatchType}検索する",
        extra_types={"CaptionMatchType": CaptionMatchType},  # 正しい引数 extra_types を使用
    )
)
def when_search_by_caption(
    test_db_manager: ImageDatabaseManager,
    search_context: SearchContext,
    caption_str: str,
    match_type: bool,
):
    # 完全一致の場合はクオートで囲む想定
    search_term = f'"{caption_str}"' if match_type else caption_str
    results, count = test_db_manager.get_images_by_filter(caption=search_term)
    search_context.results = results
    search_context.count = count
    print(f"キャプション検索実行: caption='{search_term}', 結果件数={count}")


# タグとキャプションの複合検索
@when(parsers.cfparse("タグ {tags_str} AND キャプション {caption_str} で検索する"))
def when_search_by_tag_and_caption(
    test_db_manager: ImageDatabaseManager, search_context: SearchContext, tags_str: str, caption_str: str
):
    tags = [t.strip() for t in tags_str.split("AND")]  # AND で分割
    results, count = test_db_manager.get_images_by_filter(tags=tags, caption=caption_str, use_and=True)
    search_context.results = results
    search_context.count = count
    print(f"複合検索実行: tags={tags}, caption='{caption_str}', 結果件数={count}")


# 日付検索 (相対時間)
@when(parsers.cfparse("過去{hours:d}時間以内のアノテーションで検索する"))
def when_search_by_relative_date(
    test_db_manager: ImageDatabaseManager, search_context: SearchContext, hours: int
):
    now = datetime.now(UTC)
    start_time = now - timedelta(hours=hours)
    start_date_str = start_time.isoformat()
    results, count = test_db_manager.get_images_by_filter(start_date=start_date_str)
    search_context.results = results
    search_context.count = count
    print(f"相対日付検索実行: start_date='{start_date_str}', 結果件数={count}")


# 日付検索 (特定範囲)
def _parse_date_offset(offset_str: str) -> datetime:
    """Parse offset string like '-2 days' or '-0.5 days' relative to now."""
    match = re.match(r"([-+]?\d*\.?\d+)\s*(days?|hours?|minutes?)", offset_str, re.IGNORECASE)
    if not match:
        raise ValueError(f"Invalid date offset format: {offset_str}")
    value = float(match.group(1))
    unit = match.group(2).lower()

    delta_args = {}
    if "day" in unit:
        delta_args["days"] = value
    elif "hour" in unit:
        delta_args["hours"] = value
    elif "minute" in unit:
        delta_args["minutes"] = value

    return datetime.now(UTC) + timedelta(**delta_args)


@when(parsers.cfparse('特定の日付範囲 ("{start_offset}", "{end_offset}") で検索する'))
def when_search_by_date_range(
    test_db_manager: ImageDatabaseManager,
    search_context: SearchContext,
    start_offset: str,
    end_offset: str,
):
    try:
        start_dt = _parse_date_offset(start_offset.strip())
        end_dt = _parse_date_offset(end_offset.strip())
        start_date_str = start_dt.isoformat()
        end_date_str = end_dt.isoformat()
        results, count = test_db_manager.get_images_by_filter(
            start_date=start_date_str, end_date=end_date_str
        )
        search_context.results = results
        search_context.count = count
        print(f"日付範囲検索実行: start='{start_date_str}', end='{end_date_str}', 結果件数={count}")
    except ValueError as e:
        pytest.fail(f"日付オフセットのパースエラー: {e}")


# NSFWフィルター検索
@when(parsers.cfparse("include_nsfw={include_nsfw_str} で検索する"))
def when_search_with_nsfw_filter(
    test_db_manager: ImageDatabaseManager, search_context: SearchContext, include_nsfw_str: str
):
    include_nsfw = parse_bool(include_nsfw_str)
    results, count = test_db_manager.get_images_by_filter(include_nsfw=include_nsfw)
    search_context.results = results
    search_context.count = count
    print(f"NSFWフィルター検索実行: include_nsfw={include_nsfw}, 結果件数={count}")


# 手動編集フラグフィルター検索
@when(parsers.cfparse("is_edited_manually={edited_flag_str} でフィルタリングする"))
def when_search_by_manual_edit_flag(
    test_db_manager: ImageDatabaseManager, search_context: SearchContext, edited_flag_str: str
):
    manual_edit_filter = parse_bool(edited_flag_str)
    results, count = test_db_manager.get_images_by_filter(manual_edit_filter=manual_edit_filter)
    search_context.results = results
    search_context.count = count
    print(f"手動編集フラグ検索実行: manual_edit_filter={manual_edit_filter}, 結果件数={count}")


# 手動レーティングフィルター検索
@when(parsers.cfparse('manual_rating="{rating}" でフィルタリングする'))
def when_search_by_manual_rating(
    test_db_manager: ImageDatabaseManager, search_context: SearchContext, rating: str
):
    results, count = test_db_manager.get_images_by_filter(manual_rating_filter=rating)
    search_context.results = results
    search_context.count = count
    print(f"手動レーティング検索実行: manual_rating_filter='{rating}', 結果件数={count}")


# --- Step Definitions (Then) --- #


# Use new fixture and get metadata from the new manager
@then("画像メタデータがデータベースに保存される")
def then_check_metadata_saved(test_db_manager: ImageDatabaseManager, register_image_result: dict[str, Any]):
    """新しい test_db_manager でメタデータが保存されたことを確認"""
    image_id = register_image_result["image_id"]
    # Fetch metadata again to ensure it's persisted
    db_metadata = test_db_manager.get_image_metadata(image_id)
    assert db_metadata is not None, f"画像 ID {image_id} のメタデータが取得できません"
    assert db_metadata["id"] == image_id
    # Check some essential fields extracted by fs_manager/repository
    assert "width" in db_metadata and db_metadata["width"] > 0
    assert "height" in db_metadata and db_metadata["height"] > 0
    assert "original_image_path" in db_metadata
    assert "stored_image_path" in db_metadata  # Path saved by fs_manager


# Check metadata from the registration result
@then("画像のUUIDが生成される")
def then_check_uuid_generated(register_image_result: dict[str, Any]):
    """登録結果のメタデータにUUIDが含まれることを確認"""
    metadata = register_image_result["metadata"]
    assert "uuid" in metadata, "メタデータに 'uuid' がありません"
    assert isinstance(metadata["uuid"], str) and len(metadata["uuid"]) > 0, "UUIDが無効です"


# Check metadata from the registration result
@then("画像のpHashが計算され保存される")
def then_check_phash_saved(register_image_result: dict[str, Any]):
    """登録結果のメタデータにpHashが含まれることを確認"""
    metadata = register_image_result["metadata"]
    assert "phash" in metadata, "メタデータに 'phash' がありません"
    assert isinstance(metadata["phash"], str) and len(metadata["phash"]) > 0, "pHashが無効です"


# New step definition
@then("manual_rating は NULL である")
def then_manual_rating_is_null(
    test_db_manager: ImageDatabaseManager, register_image_result: dict[str, Any]
):
    """登録された画像の manual_rating が NULL であることを確認"""
    image_id = register_image_result["image_id"]
    db_metadata = test_db_manager.get_image_metadata(image_id)
    assert db_metadata is not None, f"画像 ID {image_id} のメタデータが取得できません"
    assert "manual_rating" in db_metadata, "メタデータに 'manual_rating' がありません"
    assert db_metadata["manual_rating"] is None, (
        f"manual_rating が NULL ではありません: {db_metadata['manual_rating']}"
    )


# ... (then_check_processed_metadata_saved, then_check_processed_image_linked は変更なし) ...
@then(
    parsers.parse(
        '"{expected_count:d}"件のキャプションが"{image_name}"について取得されるべき'  # 日本語ステップ名
    )
)
def then_check_captions_retrieved(
    test_db_manager: ImageDatabaseManager,
    registered_images_with_annotations: dict,
    image_name: str,
    expected_count: int,
):
    """指定された画像のキャプション件数を検証する"""  # 日本語Docstring
    image_info = registered_images_with_annotations.get(image_name)
    assert image_info, f"前提条件で画像 '{image_name}' が登録されていません"
    image_id = image_info["id"]
    retrieved_annotations = test_db_manager.get_image_annotations(image_id)  # image_id を int に変換
    assert retrieved_annotations is not None, f"画像ID {image_id} のアノテーションが見つかりません"
    actual_count = len(retrieved_annotations.get("captions", []))
    assert actual_count == expected_count, (
        f"画像 '{image_name}' (ID: {image_id}) のキャプションの件数が一致しません。期待: {expected_count}, 実際: {actual_count}"
    )
    print(
        f"キャプション取得テスト成功: 画像 '{image_name}' (ID: {image_id}) のキャプション件数 {actual_count} (期待値: {expected_count})"
    )


@then(
    parsers.parse(
        '"{expected_count:d}"件のスコアが"{image_name}"について取得されるべき'  # 日本語ステップ名
    )
)
def then_check_scores_retrieved(
    test_db_manager: ImageDatabaseManager,
    registered_images_with_annotations: dict,
    image_name: str,
    expected_count: int,
):
    """指定された画像のスコア件数を検証する"""  # 日本語Docstring
    image_info = registered_images_with_annotations.get(image_name)
    assert image_info, f"前提条件で画像 '{image_name}' が登録されていません"
    image_id = image_info["id"]
    retrieved_annotations = test_db_manager.get_image_annotations(image_id)  # image_id を int に変換
    assert retrieved_annotations is not None, f"画像ID {image_id} のアノテーションが見つかりません"
    actual_count = len(retrieved_annotations.get("scores", []))
    assert actual_count == expected_count, (
        f"画像 '{image_name}' (ID: {image_id}) のスコアの件数が一致しません。期待: {expected_count}, 実際: {actual_count}"
    )
    print(
        f"スコア取得テスト成功: 画像 '{image_name}' (ID: {image_id}) のスコア件数 {actual_count} (期待値: {expected_count})"
    )


@then(
    parsers.parse(
        '"{expected_count:d}"件の評価が"{image_name}"について取得されるべき'  # 日本語ステップ名
    )
)
def then_check_ratings_retrieved(
    test_db_manager: ImageDatabaseManager,
    registered_images_with_annotations: dict,
    image_name: str,
    expected_count: int,
):
    """指定された画像の評価件数を検証する"""  # 日本語Docstring
    image_info = registered_images_with_annotations.get(image_name)
    assert image_info, f"前提条件で画像 '{image_name}' が登録されていません"
    image_id = image_info["id"]
    retrieved_annotations = test_db_manager.get_image_annotations(image_id)  # image_id を int に変換
    assert retrieved_annotations is not None, f"画像ID {image_id} のアノテーションが見つかりません"
    actual_count = len(retrieved_annotations.get("ratings", []))
    assert actual_count == expected_count, (
        f"画像 '{image_name}' (ID: {image_id}) の評価の件数が一致しません。期待: {expected_count}, 実際: {actual_count}"
    )
    print(
        f"評価取得テスト成功: 画像 '{image_name}' (ID: {image_id}) の評価件数 {actual_count} (期待値: {expected_count})"
    )


# ... (then_check_processed_metadata_saved, then_check_processed_image_linked は変更なし) ...

# --- 検索結果検証ステップ (`Then`) --- #


@then(parsers.parse("{expected_count:d}件の画像が返される"))
def then_check_search_result_count(search_context: SearchContext, expected_count: int):
    """検索結果の件数が期待通りか検証する"""
    actual_count = search_context.count
    assert actual_count == expected_count, (
        f"検索結果の件数が一致しません。期待: {expected_count}, 実際: {actual_count}\n"
        f"取得結果: {search_context.results}"  # デバッグ用に結果も表示
    )
    print(f"検索結果件数テスト成功: {actual_count}件 (期待値: {expected_count})")


# ... (then_check_tag_is_edited_with_model など詳細検証ステップは変更なし) ...


@then("アノテーションがデータベースに保存される")
@then("保存されたアノテーションが期待通りにDBに存在するか確認する")
def then_check_annotations_saved(
    test_db_manager: ImageDatabaseManager, image_registered: int, saved_annotations_data: AnnotationsDict
):
    """保存されたアノテーションがDBに存在し、値が一致するか検証する"""
    db_annotations = test_db_manager.get_image_annotations(image_registered)
    assert db_annotations is not None, (
        f"画像ID {image_registered} のアノテーションがDBから取得できませんでした"
    )
    # print(f"画像ID {image_registered} から取得したDBアノテーション: {db_annotations}") # デバッグ用

    for key in ["tags", "captions", "scores", "ratings"]:
        # saved_list にはパースされたデータ、db_list にはDBから取得したデータ
        saved_list = saved_annotations_data.get(key, [])
        db_list = db_annotations.get(key, [])
        # print(f"検証中: {key}, 保存試行件数: {len(saved_list)}, DB件数: {len(db_list)}") # デバッグ用

        assert len(saved_list) == len(db_list), (
            f"保存された {key} の件数が一致しません。期待: {len(saved_list)}, DB: {len(db_list)}"
        )

        # DBから取得したデータを検索しやすいように辞書に変換
        db_items_map: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for item in db_list:
            map_key = None
            try:
                if key == "tags":
                    map_key = (item.get("tag"), item.get("model_id"))
                elif key == "captions":
                    map_key = (item.get("caption"), item.get("model_id"))
                elif key == "scores":
                    map_key = (item.get("model_id"), item.get("score"))  # スコア値もキーに含める
                elif key == "ratings":
                    map_key = (item.get("normalized_rating"), item.get("model_id"))
            except Exception as e:
                print(f"警告: DBアイテムのキー作成中にエラー: {e}, item={item}")
                continue
            if map_key is not None:
                if map_key in db_items_map:
                    # 既にキーが存在する場合、リストに追加
                    db_items_map[map_key].append(item)
                    print(f"情報: DBデータでキー {map_key} が重複。リストに追加しました。")
                else:
                    # キーが初めて現れた場合、要素が1つのリストとして作成
                    db_items_map[map_key] = [item]

        # 保存試行したデータがDBに存在し、値が一致するか確認
        processed_lookup_keys = set()  # 重複検証用
        for saved_item in saved_list:
            lookup_key = None
            try:
                if key == "tags":
                    lookup_key = (saved_item.get("tag"), saved_item.get("model_id"))
                elif key == "captions":
                    lookup_key = (saved_item.get("caption"), saved_item.get("model_id"))
                elif key == "scores":
                    lookup_key = (saved_item.get("model_id"), saved_item.get("score"))
                elif key == "ratings":
                    lookup_key = (saved_item.get("normalized_rating"), saved_item.get("model_id"))
            except Exception as e:
                print(f"警告: 保存試行データのキー作成中にエラー: {e}, item={saved_item}")
                pytest.fail(f"テストデータエラー: {saved_item}")

            assert lookup_key is not None, f"ルックアップキーの生成に失敗しました: {saved_item}"
            assert lookup_key in db_items_map, (
                f"保存試行した {key[:-1]} がDBに見つかりません (キー: {lookup_key})。"
                f" DB Map Keys: {list(db_items_map.keys())}\n"  # 改行はエスケープ
                f"保存試行アイテム: {saved_item}"
            )

            # DB側のデータ取得(常にリストとして取得)
            db_data_list = db_items_map[lookup_key]
            db_item_to_compare = None

            # まだ比較されていないDBアイテムを探す
            found_match_in_list = False
            for _idx, db_item in enumerate(db_data_list):
                # 簡易的な識別子(例:全フィールドをタプル化)で比較済みかチェック
                item_identifier = tuple(sorted(db_item.items()))
                if (lookup_key, item_identifier) not in processed_lookup_keys:
                    db_item_to_compare = db_item
                    processed_lookup_keys.add((lookup_key, item_identifier))
                    found_match_in_list = True
                    break
            if not found_match_in_list:
                pytest.fail(
                    f"キー {lookup_key} に対応する未比較のDBアイテムが見つかりませんでした。DBリスト: {db_data_list}"
                )

            assert db_item_to_compare is not None, (
                f"比較対象のDBアイテムが見つかりませんでした (キー: {lookup_key})"
            )

            # print(f"比較中 ({key}):\n保存試行 -> {saved_item}\nDBデータ -> {db_item_to_compare}") # デバッグ用

            # 各フィールドを比較
            all_keys = set(saved_item.keys()) | set(db_item_to_compare.keys())
            # 比較不要なキーを除外 (DBから返される可能性のあるキーも考慮)
            # tag_id は外部DB由来で変動するため、比較から除外
            keys_to_compare = [
                k for k in all_keys if k not in ["id", "created_at", "updated_at", "image_id", "tag_id"]
            ]

            for field in keys_to_compare:
                saved_value = saved_item.get(field)
                db_value = db_item_to_compare.get(field)

                # --- 値の比較ロジック --- #
                # None の扱い: saved が None なら DB も None を期待 (逆も然り)
                if saved_value is None:
                    assert db_value is None, (
                        f"{key} '{lookup_key}' のフィールド '{field}' が一致しません。"
                        f"期待: None, DB: {db_value}"
                    )
                    continue
                elif db_value is None:
                    # 'tag_id' はDB側でのみ生成される場合があるので、 saved_value が None でなければエラー
                    if field == "tag_id" and saved_value is not None:
                        print(
                            f"情報: フィールド 'tag_id' はDB側で生成されるため、DB値が None でも許容される場合があります。saved={saved_value}"
                        )
                        # ここでテストを失敗させるか、許容するかは要件次第
                        # pytest.fail(f"{key} '{lookup_key}' のフィールド '{field}' がDBでNoneですが、保存側は {saved_value} です。")
                    elif field != "tag_id":  # tag_id 以外でDBが None は通常期待しない
                        assert saved_value is None, (
                            f"{key} '{lookup_key}' のフィールド '{field}' が一致しません。"
                            f"期待: {saved_value}, DB: None"
                        )
                    continue

                # 型を比較前に合わせる(特に bool と float)
                try:
                    # Bool 値の比較 (DBが 0/1 を返す可能性を考慮)
                    is_bool_field = isinstance(saved_value, bool) or field in [
                        "is_edited_manually",
                        "existing",
                    ]
                    if is_bool_field:
                        # 文字列 "true"/"false" と数値 0/1 を bool に統一
                        parsed_saved_bool = (
                            parse_bool(str(saved_value))
                            if not isinstance(saved_value, bool)
                            else saved_value
                        )
                        parsed_db_bool = (
                            parse_bool(str(db_value)) if not isinstance(db_value, bool) else db_value
                        )
                        assert parsed_saved_bool == parsed_db_bool, (
                            f"{key} '{lookup_key}' の bool フィールド '{field}' が一致しません。"
                            f"期待: {parsed_saved_bool} ({saved_value}), DB: {parsed_db_bool} ({db_value})"
                        )
                        continue

                    # Float 値の比較 (許容誤差)
                    is_float_field = isinstance(saved_value, float) or field in [
                        "confidence_score",
                        "score",
                    ]
                    if is_float_field:
                        assert abs(float(saved_value) - float(db_value)) < 1e-6, (
                            f"{key} '{lookup_key}' の float フィールド '{field}' が一致しません。"
                            f"期待: {saved_value}, DB: {db_value}"
                        )
                        continue

                    # Int 値の比較 (tag_id など)
                    # tag_id は DB側で自動生成される場合があるので、 saved_item に存在しない場合がある
                    is_int_field = isinstance(saved_value, int) or field in ["model_id", "tag_id"]
                    if is_int_field:
                        # saved_value が None でなく、かつ DB の値と比較する場合
                        if saved_value is not None:
                            assert int(saved_value) == int(db_value), (
                                f"{key} '{lookup_key}' の int フィールド '{field}' が一致しません。"
                                f"期待: {saved_value}, DB: {db_value}"
                            )
                        elif field == "tag_id":
                            # saved_value が None (tag_idが未指定) の場合、DB側は整数のはず
                            assert isinstance(db_value, int), (
                                f"{key} '{lookup_key}' のフィールド 'tag_id' はDB側で整数であるべきです。"
                                f"DB値: {db_value} (型: {type(db_value)})"
                            )
                            # ここで tag_id が期待通りに振られているかの追加検証も可能
                            print(
                                f"情報: フィールド 'tag_id' は保存時に指定されていませんが、DB側で値 ({db_value}) が設定されています。"
                            )
                        continue

                except (ValueError, TypeError) as e:
                    print(
                        f"警告: フィールド '{field}' の比較中に型変換エラー: {e} (saved={saved_value}, db={db_value})。 文字列比較を試みます。"
                    )
                    # 型変換エラー時は文字列比較にフォールバック
                    pass

                # その他の型 (主に文字列) の比較
                assert str(saved_value) == str(db_value), (
                    f"{key} '{lookup_key}' のフィールド '{field}' が一致しません。"
                    f"期待: {saved_value}, DB: {db_value}"
                )

            # print(f"アイテム比較OK: {saved_item}") # デバッグ用


@then("保存したアノテーションを取得できる")
def then_check_annotations_retrieved(
    test_db_manager: ImageDatabaseManager, image_registered: int, saved_annotations_data: AnnotationsDict
):
    """取得したアノテーションが保存しようとしたものと一致するか検証"""
    # then_check_annotations_saved で検証ロジックは実装済みなので再利用
    print("then_check_annotations_retrieved を呼び出し、then_check_annotations_saved で検証を実行します。")
    then_check_annotations_saved(test_db_manager, image_registered, saved_annotations_data)


# --- 詳細検証用ヘルパー --- #


def _get_annotation_detail(
    test_db_manager: ImageDatabaseManager,
    image_id: int,
    annotation_type: str,  # "tags", "captions", "scores", "ratings"
    identifier: Any,  # tag name, caption text, score value, rating value
    model_id: int | None,  # model_id も識別子の一部として追加
    detail_key: str,  # "is_edited_manually", "existing", "confidence_score", "tag_id"
) -> Any:
    """特定のアノテーションから指定された詳細情報を取得するヘルパー"""
    annotations = test_db_manager.get_image_annotations(image_id)
    items = annotations.get(annotation_type, [])
    found_item = None
    # print(f"_get_annotation_detail: 検索中 type={annotation_type}, identifier={identifier}, model_id={model_id}, key={detail_key}, items={items}") # デバッグ用
    for item in items:
        # model_id が指定されていれば、それも一致条件に加える
        model_match = (model_id is None) or (item.get("model_id") == model_id)
        if not model_match:
            continue

        match = False
        # 各アノテーションタイプに応じた識別子でアイテムを検索
        try:
            if annotation_type == "tags" and item.get("tag") == identifier:
                match = True
            elif annotation_type == "captions" and item.get("caption") == identifier:
                match = True
            elif (
                annotation_type == "scores"
                and abs(item.get("score", float("nan")) - float(identifier)) < 1e-6
            ):
                match = True
            elif annotation_type == "ratings" and item.get("normalized_rating") == identifier:
                match = True  # または raw_rating_value
        except (TypeError, ValueError):  # float変換エラーなどを考慮
            print(
                f"警告: _get_annotation_detail での識別子比較中にエラー (identifier={identifier}, item={item})"
            )
            continue
        if match:
            found_item = item
            # print(f"アイテム発見: {found_item}") # デバッグ用
            break  # 最初に見つかったアイテムを使用

    assert found_item is not None, (
        f"{annotation_type} で識別子 '{identifier}' (model_id: {model_id}) の項目が見つかりません。"
        f"(画像ID: {image_id}, 取得項目: {items})"
    )

    # Nullableなフィールドはキーが存在しなくてもエラーにしない
    # assert detail_key in found_item, f"項目 {found_item} に詳細キー '{detail_key}' が見つかりません。"
    # print(f"返す値: {found_item.get(detail_key)}") # デバッグ用
    return found_item.get(detail_key)  # キーが存在しない場合は None が返る


# --- 詳細検証ステップ --- #


# タグ検証用ヘルパー
def _check_tag_detail(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    tag_name: str,
    model_id: int | None,
    detail_key: str,
    expected_value: str,
):
    expected_bool = parse_bool(expected_value)
    actual_value = _get_annotation_detail(
        test_db_manager, image_registered, "tags", tag_name, model_id, detail_key
    )
    # DBから取得した値が 0/1 の可能性もあるため、bool として比較
    actual_bool = bool(actual_value) if actual_value is not None else None
    assert actual_bool == expected_bool, (
        f"タグ '{tag_name}' (model_id: {model_id}) の '{detail_key}' が期待値 '{expected_bool}' と異なります。"
        f"実際の値: '{actual_value}' (型: {type(actual_value)})"
    )


@then(
    parsers.parse(
        '取得したタグ "{tag_name}" (モデルID: {model_id:d}) の is_edited_manually は {expected_value} である'
    )
)
def then_check_tag_is_edited_with_model(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    tag_name: str,
    model_id: int,
    expected_value: str,
):
    _check_tag_detail(
        test_db_manager, image_registered, tag_name, model_id, "is_edited_manually", expected_value
    )


@then(
    parsers.parse(
        '取得したタグ "{tag_name}" (モデルID: {model_id:d}) の existing は {expected_value} である'
    )
)
def then_check_tag_existing_with_model(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    tag_name: str,
    model_id: int,
    expected_value: str,
):
    _check_tag_detail(test_db_manager, image_registered, tag_name, model_id, "existing", expected_value)


# --- モデルID指定なし(Optionalだが、最初のモデルにマッチするなど曖昧なため非推奨。互換性のために残す場合) ---
# @then(parsers.parse('取得したタグ "{tag_name}" の is_edited_manually は {expected_value} である'))
# def then_check_tag_is_edited(test_db_manager: ImageDatabaseManager, image_registered: int, tag_name: str, expected_value: str):
#     print("警告: モデルIDなしのタグ検証は曖昧さを含む可能性があります。モデルIDを指定するステップの使用を推奨します。")
#     _check_tag_detail(test_db_manager, image_registered, tag_name, None, "is_edited_manually", expected_value)

# @then(parsers.parse('取得したタグ "{tag_name}" の existing は {expected_value} である'))
# def then_check_tag_existing(test_db_manager: ImageDatabaseManager, image_registered: int, tag_name: str, expected_value: str):
#     print("警告: モデルIDなしのタグ検証は曖昧さを含む可能性があります。モデルIDを指定するステップの使用を推奨します。")
#     _check_tag_detail(test_db_manager, image_registered, tag_name, None, "existing", expected_value)


# キャプション検証用ヘルパー
def _check_caption_detail(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    caption_text: str,
    model_id: int | None,
    detail_key: str,
    expected_value: str,
):
    expected_bool = parse_bool(expected_value)
    actual_value = _get_annotation_detail(
        test_db_manager, image_registered, "captions", caption_text, model_id, detail_key
    )
    actual_bool = bool(actual_value) if actual_value is not None else None
    assert actual_bool == expected_bool, (
        f"キャプション '{caption_text[:20]}...' (model_id: {model_id}) の '{detail_key}' が期待値 '{expected_bool}' と異なります。"
        f"実際の値: '{actual_value}' (型: {type(actual_value)})"
    )


@then(
    parsers.parse(
        '取得したキャプション "{caption_text}" (モデルID: {model_id:d}) の is_edited_manually は {expected_value} である'
    )
)
def then_check_caption_is_edited_with_model(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    caption_text: str,
    model_id: int,
    expected_value: str,
):
    _check_caption_detail(
        test_db_manager, image_registered, caption_text, model_id, "is_edited_manually", expected_value
    )


# --- モデルID指定なし(非推奨) ---
# @then(parsers.parse('取得したキャプション "{caption_text}" の is_edited_manually は {expected_value} である'))
# def then_check_caption_is_edited(test_db_manager: ImageDatabaseManager, image_registered: int, caption_text: str, expected_value: str):
#     print("警告: モデルIDなしのキャプション検証は曖昧さを含む可能性があります。")
#     _check_caption_detail(test_db_manager, image_registered, caption_text, None, "is_edited_manually", expected_value)


# スコア検証用ヘルパー
def _check_score_detail(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    score_value: str,
    model_id: int | None,
    detail_key: str,
    expected_value: str,
):
    expected_bool = parse_bool(expected_value)
    # score_value は float として識別子に渡す
    actual_value = _get_annotation_detail(
        test_db_manager, image_registered, "scores", float(score_value), model_id, detail_key
    )
    actual_bool = bool(actual_value) if actual_value is not None else None
    assert actual_bool == expected_bool, (
        f"スコア '{score_value}' (model_id: {model_id}) の '{detail_key}' が期待値 '{expected_bool}' と異なります。"
        f"実際の値: '{actual_value}' (型: {type(actual_value)})"
    )


@then(
    parsers.parse(
        "取得したスコア {score_value} (モデルID: {model_id:d}) の is_edited_manually は {expected_value} である"
    )
)
def then_check_score_is_edited_with_model(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    score_value: str,
    model_id: int,
    expected_value: str,
):
    _check_score_detail(
        test_db_manager, image_registered, score_value, model_id, "is_edited_manually", expected_value
    )


# --- モデルID指定なし(非推奨) ---
# @then(parsers.parse("取得したスコア {score_value} の is_edited_manually は {expected_value} である"))
# def then_check_score_is_edited(test_db_manager: ImageDatabaseManager, image_registered: int, score_value: str, expected_value: str):
#     print("警告: モデルIDなしのスコア検証は曖昧さを含む可能性があります。")
#     _check_score_detail(test_db_manager, image_registered, score_value, None, "is_edited_manually", expected_value)


# レーティング検証ステップ
@then(
    parsers.parse(
        '取得したレーティング "{rating_value}" (モデルID: {model_id:d}) の confidence_score は {expected_value} である'
    )
)
def then_check_rating_confidence_with_model(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,
    rating_value: str,
    model_id: int,
    expected_value: str,
):
    """指定されたレーティングの confidence_score を検証します。"""
    try:
        expected_float = float(expected_value)
    except ValueError:
        pytest.fail(f"期待値の confidence_score が不正な float 値です: {expected_value}")

    actual_value = _get_annotation_detail(
        test_db_manager, image_registered, "ratings", rating_value, model_id, "confidence_score"
    )

    assert actual_value is not None, (
        f"レーティング '{rating_value}' (model_id: {model_id}) の confidence_score が DB で None でした。"
    )

    try:
        actual_float = float(actual_value)
    except (ValueError, TypeError):
        pytest.fail(
            f"DB から取得した confidence_score が float に変換できません: {actual_value} (型: {type(actual_value)})"
        )

    assert abs(actual_float - expected_float) < 1e-6, (
        f"レーティング '{rating_value}' (model_id: {model_id}) の confidence_score が期待値と異なります。"
        f"期待: {expected_float}, 実際: {actual_float}"
    )


@then(
    parsers.parse(
        '"{expected_count:d}"件のタグが"{image_name}"について取得されるべき'  # 日本語ステップ名
    )
)
def then_check_tags_retrieved(
    test_db_manager: ImageDatabaseManager,
    registered_images_with_annotations: dict,
    image_name: str,
    expected_count: int,
):
    """指定された画像のタグ件数を検証する"""  # 日本語Docstring
    image_info = registered_images_with_annotations.get(image_name)
    assert image_info, f"前提条件で画像 '{image_name}' が登録されていません"
    image_id = image_info["id"]
    retrieved_annotations = test_db_manager.get_image_annotations(image_id)  # image_id を int に変換
    assert retrieved_annotations is not None, f"画像ID {image_id} のアノテーションが見つかりません"
    actual_count = len(retrieved_annotations.get("tags", []))
    assert actual_count == expected_count, (
        f"画像 '{image_name}' (ID: {image_id}) のタグの件数が一致しません。期待: {expected_count}, 実際: {actual_count}"
    )
    print(
        f"タグ取得テスト成功: 画像 '{image_name}' (ID: {image_id}) のタグ件数 {actual_count} (期待値: {expected_count})"
    )


# --- 処理済み画像関連ステップ --- #


@then("処理済み画像のメタデータがデータベースに保存される")
def then_check_processed_metadata_saved(
    test_db_manager: ImageDatabaseManager,
    image_registered: int,  # オリジナル画像ID
    processed_image_id: int,  # 登録された処理済み画像ID
):
    """登録された処理済み画像のメタデータが存在し、基本的なキーが含まれるか確認する"""
    processed_list = test_db_manager.get_processed_metadata(image_registered)
    assert processed_list is not None, (
        f"画像ID {image_registered} の処理済みメタデータが取得できませんでした。"
    )

    found_metadata = None
    for meta in processed_list:
        if meta.get("id") == processed_image_id:
            found_metadata = meta
            break

    assert found_metadata is not None, (
        f"ID {processed_image_id} の処理済み画像メタデータが、元画像ID {image_registered} に関連付けられていません。"
    )

    # 基本的なキーの存在チェック
    assert "stored_image_path" in found_metadata
    assert "width" in found_metadata
    assert "height" in found_metadata
    print(f"処理済み画像メタデータ (ID: {processed_image_id}) の存在を確認しました。")


@then("オリジナル画像と処理済み画像が関連付けられる")
def then_check_processed_image_linked(
    test_db_manager: ImageDatabaseManager, image_registered: int, processed_image_id: int
):
    """オリジナル画像IDから処理済み画像のメタデータを取得し、IDが一致するか確認する"""
    processed_list = test_db_manager.get_processed_metadata(image_registered)
    assert processed_list is not None, (
        f"画像ID {image_registered} の処理済みメタデータが取得できませんでした。"
    )

    assert any(meta.get("id") == processed_image_id for meta in processed_list), (
        f"ID {processed_image_id} の処理済み画像が、元画像ID {image_registered} に関連付けられていません。"
    )
    print(
        f"オリジナル画像 (ID: {image_registered}) と処理済み画像 (ID: {processed_image_id}) の関連付けを確認しました。"
    )
