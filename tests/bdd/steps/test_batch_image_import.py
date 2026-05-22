"""バッチ画像インポート (BatchImportService) の BDD ステップ定義。

OpenAI Batch API の JSONL 結果取り込みフローを振る舞い仕様化する。
実 OpenAI Batch API は呼ばず、実 API レスポンス形式の JSONL fixture を
tmp_path に生成して検証する。
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.services.batch_import_service import BatchImportResult, BatchImportService
from lorairo.storage.file_system import FileSystemManager

_FEATURE_FILE = Path(__file__).parent.parent / "features" / "batch_image_import.feature"
scenarios(str(_FEATURE_FILE))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_batch_record(
    custom_id: str,
    content: str,
    model: str = "gpt-4-turbo-2024-04-09",
    status_code: int = 200,
) -> dict[str, Any]:
    """OpenAI Batch API レスポンス形式のレコードを作成する。"""
    return {
        "id": f"batch_req_{custom_id}",
        "custom_id": custom_id,
        "response": {
            "status_code": status_code,
            "body": {
                "id": f"chatcmpl-{custom_id}",
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            },
        },
        "error": None,
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> Path:
    """レコードリストを JSONL ファイルに書き出す。"""
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    return path


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class BatchImportContext:
    """ステップ間で受け渡すバッチインポートのコンテキスト。"""

    def __init__(self) -> None:
        self.repository: Any = None
        self.jsonl_path: Path | None = None
        self.result: BatchImportResult | None = None
        self.registered_image_id: int | None = None


@pytest.fixture
def batch_context() -> BatchImportContext:
    return BatchImportContext()


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------


@given(parsers.parse('データベースに画像 "{image_name}" が登録されている'))
def given_image_in_db(
    batch_context: BatchImportContext,
    test_db_manager: ImageDatabaseManager,
    fs_manager: FileSystemManager,
    test_image_dir: Path,
    image_name: str,
) -> None:
    """実テスト DB に画像を登録し、その repository を context に保持する。"""
    image_path = test_image_dir / image_name
    assert image_path.exists(), f"テスト画像が見つかりません: {image_path}"
    result = test_db_manager.register_original_image(image_path, fs_manager)
    assert result is not None, f"画像登録に失敗: {image_path}"
    batch_context.registered_image_id = result[0]
    batch_context.repository = test_db_manager.repository


@given("ファイル名インデックスが空のリポジトリがある")
def given_empty_index_repository(batch_context: BatchImportContext) -> None:
    """照合に失敗する Mock repository を用意する。"""
    repo = MagicMock()
    repo.get_all_image_filename_index.return_value = {}
    batch_context.repository = repo


@given(parsers.parse('ファイル名インデックスに "{stem}" を持つリポジトリがある'))
def given_index_repository_with_stem(batch_context: BatchImportContext, stem: str) -> None:
    """指定 stem で照合が成立する Mock repository を用意する。"""
    repo = MagicMock()
    repo.get_all_image_filename_index.return_value = {stem: 1}
    batch_context.repository = repo


@given(parsers.parse('"{custom_id}" の custom_id を持つ JSONL バッチ結果ファイルがある'))
def given_jsonl_with_custom_id(batch_context: BatchImportContext, tmp_path: Path, custom_id: str) -> None:
    """指定 custom_id を持つ JSONL fixture を tmp_path に生成する。"""
    records = [_make_batch_record(custom_id, "Tags: 1girl, solo\n\nCaption: A girl outside.")]
    batch_context.jsonl_path = _write_jsonl(tmp_path / "batch_result.jsonl", records)


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------


@when("JSONL バッチ結果を取り込む")
def when_import_jsonl(batch_context: BatchImportContext) -> None:
    assert batch_context.repository is not None
    assert batch_context.jsonl_path is not None
    service = BatchImportService(batch_context.repository)
    batch_context.result = service.import_from_jsonl(batch_context.jsonl_path)


@when("dry-run モードで JSONL バッチ結果を取り込む")
def when_import_jsonl_dry_run(batch_context: BatchImportContext) -> None:
    assert batch_context.repository is not None
    assert batch_context.jsonl_path is not None
    service = BatchImportService(batch_context.repository)
    batch_context.result = service.import_from_jsonl(batch_context.jsonl_path, dry_run=True)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------


@then(parsers.parse("取り込み結果の総レコード数は {count:d} 件である"))
def then_total_records(batch_context: BatchImportContext, count: int) -> None:
    assert batch_context.result is not None
    assert batch_context.result.total_records == count


@then(parsers.parse("取り込み結果のパース成功数は {count:d} 件である"))
def then_parsed_ok(batch_context: BatchImportContext, count: int) -> None:
    assert batch_context.result is not None
    assert batch_context.result.parsed_ok == count


@then(parsers.parse("取り込み結果の照合成功数は {count:d} 件である"))
def then_matched(batch_context: BatchImportContext, count: int) -> None:
    assert batch_context.result is not None
    assert batch_context.result.matched == count


@then(parsers.parse("取り込み結果の未照合数は {count:d} 件である"))
def then_unmatched(batch_context: BatchImportContext, count: int) -> None:
    assert batch_context.result is not None
    assert batch_context.result.unmatched == count


@then(parsers.parse("取り込み結果の保存数は {count:d} 件である"))
def then_saved(batch_context: BatchImportContext, count: int) -> None:
    assert batch_context.result is not None
    assert batch_context.result.saved == count


@then(parsers.parse('未照合 custom_id に "{custom_id}" が含まれる'))
def then_unmatched_ids_contains(batch_context: BatchImportContext, custom_id: str) -> None:
    assert batch_context.result is not None
    assert custom_id in batch_context.result.unmatched_ids


@then("登録済み画像にアノテーションが反映されている")
def then_annotations_reflected(
    batch_context: BatchImportContext, test_db_manager: ImageDatabaseManager
) -> None:
    """実テスト DB に取り込んだアノテーションが保存されていることを確認する。"""
    assert batch_context.registered_image_id is not None
    annotations = test_db_manager.get_image_annotations(batch_context.registered_image_id)
    assert annotations is not None
    tag_names = {t.get("tag") for t in annotations.get("tags", [])}
    assert "1girl" in tag_names, f"取り込んだタグが反映されていません: {tag_names}"
    captions = [c.get("caption") for c in annotations.get("captions", [])]
    assert any(c == "A girl outside." for c in captions), (
        f"取り込んだキャプションが反映されていません: {captions}"
    )


@then("アノテーションは保存されていない")
def then_no_annotations_saved(batch_context: BatchImportContext) -> None:
    """dry-run で repository.save_annotations が呼ばれていないことを確認する。"""
    repo = batch_context.repository
    assert isinstance(repo, MagicMock), "dry-run シナリオは Mock repository を前提とする"
    repo.save_annotations.assert_not_called()
