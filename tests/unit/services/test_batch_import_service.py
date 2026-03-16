"""BatchImportServiceのユニットテスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lorairo.services.batch_import_service import BatchImportService


@pytest.fixture()
def mock_repository() -> MagicMock:
    """モックImageRepository。"""
    repo = MagicMock()
    # ファイル名インデックス
    repo.get_all_image_filename_index.return_value = {
        "0262_1227": 1,
        "0263_1228": 2,
        "0264_1229": 3,
    }
    # モデル検索
    model = MagicMock()
    model.id = 100
    repo.get_model_by_name.return_value = model
    # タグID解決
    repo.batch_resolve_tag_ids.return_value = {
        "1girl": 10,
        "solo": 20,
        "blue hair": 30,
    }
    return repo


def _create_jsonl_file(tmp_path: Path, records: list[dict]) -> Path:
    """テスト用JSONLファイルを作成する。"""
    jsonl_path = tmp_path / "test_batch.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    return jsonl_path


def _make_batch_record(
    custom_id: str,
    content: str,
    model: str = "gpt-4-turbo-2024-04-09",
    status_code: int = 200,
) -> dict:
    """OpenAI Batch APIレスポンス形式のレコードを作成する。"""
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
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                    }
                ],
            },
        },
        "error": None,
    }


class TestBatchImportServiceSingleFile:
    """import_from_jsonl()のテスト。"""

    def test_normal_import(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """正常インポート。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl, solo\n\nCaption: A girl."),
            _make_batch_record("0263_1228", "Tags: 1girl, blue hair\n\nCaption: Blue hair."),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.total_records == 2
        assert result.parsed_ok == 2
        assert result.parse_errors == 0
        assert result.matched == 2
        assert result.unmatched == 0
        assert result.saved == 2
        assert result.save_errors == 0
        assert result.model_name == "gpt-4-turbo-2024-04-09"
        assert mock_repository.save_annotations.call_count == 2

    def test_dry_run_no_save(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """dry-runモードではsave_annotationsが呼ばれない。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl, solo\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path, dry_run=True)

        assert result.matched == 1
        assert result.saved == 0
        mock_repository.save_annotations.assert_not_called()

    def test_model_name_override(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """model_name_overrideが結果に反映される。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path, model_name_override="custom-model")

        assert result.model_name == "custom-model"

    def test_parse_error_continues(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """パースエラーがあっても他のレコードは処理される。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: ok"),
            _make_batch_record("0263_1228", "Invalid content without tags"),
            _make_batch_record("0264_1229", "Tags: solo\n\nCaption: also ok"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.total_records == 3
        assert result.parsed_ok == 2
        assert result.parse_errors == 1
        assert result.matched == 2
        assert result.saved == 2
        assert len(result.error_details) == 1

    def test_unmatched_records(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """マッチ失敗レコードが正しくカウントされる。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: ok"),
            _make_batch_record("unknown_999", "Tags: solo\n\nCaption: unmatched"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.matched == 1
        assert result.unmatched == 1
        assert "unknown_999" in result.unmatched_ids

    def test_error_response_skipped(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """status_code != 200のレスポンスはスキップされる。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: ok"),
            _make_batch_record("0263_1228", "Tags: solo", status_code=429),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.total_records == 1  # 429はスキップされたので1件のみ
        assert result.parsed_ok == 1

    def test_save_error_counted(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """save_annotationsのエラーがカウントされる。"""
        mock_repository.save_annotations.side_effect = Exception("DB error")
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.save_errors == 1
        assert result.saved == 0

    def test_auto_register_model(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """未登録モデルが自動登録される。"""
        mock_repository.get_model_by_name.return_value = None
        mock_repository.insert_model.return_value = 200
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = BatchImportService(mock_repository)

        service.import_from_jsonl(jsonl_path)

        mock_repository.insert_model.assert_called_once_with(
            name="gpt-4-turbo-2024-04-09",
            provider="openai",
            model_types=["llm", "captioner"],
            api_model_id="gpt-4-turbo-2024-04-09",
            requires_api_key=True,
        )


class TestBatchImportServiceDirectory:
    """import_from_directory()のテスト。"""

    def test_multiple_jsonl_files(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """複数JSONLファイルの結果が集約される。"""
        records1 = [_make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: a")]
        records2 = [_make_batch_record("0263_1228", "Tags: solo\n\nCaption: b")]

        (tmp_path / "batch1.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records1), encoding="utf-8"
        )
        (tmp_path / "batch2.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records2), encoding="utf-8"
        )

        service = BatchImportService(mock_repository)
        result = service.import_from_directory(tmp_path)

        assert result.total_records == 2
        assert result.saved == 2

    def test_no_jsonl_files_raises_error(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """JSONLファイルなしでValueError。"""
        service = BatchImportService(mock_repository)
        with pytest.raises(ValueError, match="JSONLファイルが見つかりません"):
            service.import_from_directory(tmp_path)

    def test_nonexistent_directory_raises_error(self, mock_repository: MagicMock) -> None:
        """存在しないディレクトリでFileNotFoundError。"""
        service = BatchImportService(mock_repository)
        with pytest.raises(FileNotFoundError):
            service.import_from_directory(Path("/nonexistent/path"))


class TestBuildAnnotations:
    """_build_annotations()のテスト。"""

    def test_tags_and_caption(self) -> None:
        """タグとキャプションの変換。"""
        from lorairo.services.batch_content_parser import ParsedAnnotationContent

        content = ParsedAnnotationContent(tags=["1girl", "solo"], caption="A caption.")
        result = BatchImportService._build_annotations(content, model_id=100)

        assert len(result["tags"]) == 2
        assert result["tags"][0]["tag"] == "1girl"
        assert result["tags"][0]["model_id"] == 100
        assert result["tags"][0]["existing"] is False
        assert len(result["captions"]) == 1
        assert result["captions"][0]["caption"] == "A caption."
        assert result["scores"] == []
        assert result["ratings"] == []

    def test_no_caption(self) -> None:
        """キャプションなしの変換。"""
        from lorairo.services.batch_content_parser import ParsedAnnotationContent

        content = ParsedAnnotationContent(tags=["1girl"], caption=None)
        result = BatchImportService._build_annotations(content, model_id=100)

        assert len(result["tags"]) == 1
        assert result["captions"] == []
