"""BatchImportServiceのユニットテスト。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

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
    repo.get_model_by_litellm_id.return_value = model
    # タグID解決
    repo.batch_resolve_tag_ids.return_value = {
        "1girl": 10,
        "solo": 20,
        "blue hair": 30,
    }
    return repo


def _make_service(repository: MagicMock) -> BatchImportService:
    """Mock repository を split repo roles として明示注入する。"""
    return BatchImportService(
        repository,
        model_repository=repository,
        annotation_repository=repository,
    )


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
        service = _make_service(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.total_records == 2
        assert result.parsed_ok == 2
        assert result.parse_errors == 0
        assert result.matched == 2
        assert result.unmatched == 0
        assert result.saved == 2
        assert result.save_errors == 0
        assert result.model_name == "gpt-4-turbo-2024-04-09"
        mock_repository.save_annotations_batch.assert_called_once()
        assert len(mock_repository.save_annotations_batch.call_args[0][0]) == 2
        mock_repository.save_annotations.assert_not_called()

    def test_dry_run_no_save(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """dry-runモードではsave_annotationsが呼ばれない。"""
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl, solo\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = _make_service(mock_repository)

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
        service = _make_service(mock_repository)

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
        service = _make_service(mock_repository)

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
        service = _make_service(mock_repository)

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
        service = _make_service(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.total_records == 1  # 429はスキップされたので1件のみ
        assert result.parsed_ok == 1

    def test_save_error_counted(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """save_annotationsのエラーがカウントされる。"""
        mock_repository.save_annotations_batch.side_effect = Exception("batch DB error")
        mock_repository.save_annotations.side_effect = Exception("DB error")
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = _make_service(mock_repository)

        result = service.import_from_jsonl(jsonl_path)

        assert result.save_errors == 1
        assert result.saved == 0

    def test_auto_register_model(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """未登録モデルが自動登録される。

        ADR 0023 Phase 1.11 (Issue #238): bare 名 (`gpt-4-turbo-2024-04-09`) は
        `openai/<bare>` に正規化されて lookup・登録される。
        """
        mock_repository.get_model_by_litellm_id.return_value = None
        mock_repository.insert_model.return_value = 200
        records = [
            _make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: text"),
        ]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = _make_service(mock_repository)

        service.import_from_jsonl(jsonl_path)

        mock_repository.insert_model.assert_called_once_with(
            name="gpt-4-turbo-2024-04-09",
            provider="openai",
            model_types=["multimodal", "caption", "tags"],
            litellm_model_id="openai/gpt-4-turbo-2024-04-09",
            requires_api_key=True,
        )


class TestBatchImportServiceDirectory:
    """import_from_directory()のテスト。"""

    @pytest.mark.parametrize("image_count", [1, 500, 501, 1000, 10000])
    @pytest.mark.parametrize("file_count", [1, 3])
    @pytest.mark.parametrize("dry_run", [False, True])
    def test_stem_index_built_once_per_operation(
        self, tmp_path: Path, mock_repository: MagicMock, image_count: int, file_count: int, dry_run: bool
    ) -> None:
        """N画像/Fファイルでも全画像索引の走査はN件を1回だけ。"""
        scanned_rows = 0

        def build_index() -> dict[str, int]:
            nonlocal scanned_rows
            scanned_rows += image_count
            return {f"image-{i}": i + 1 for i in range(image_count)}

        mock_repository.get_all_image_filename_index.side_effect = build_index
        for number in range(file_count):
            record = _make_batch_record("image-0", "Tags: solo\n\nCaption: test")
            (tmp_path / f"batch-{number}.jsonl").write_text(json.dumps(record), encoding="utf-8")

        result = _make_service(mock_repository).import_from_directory(tmp_path, dry_run=dry_run)

        assert result.total_records == result.matched == file_count
        assert result.saved == (0 if dry_run else file_count)
        mock_repository.get_all_image_filename_index.assert_called_once()
        assert scanned_rows == image_count

    def test_phash_only_does_not_build_stem_index(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        mock_repository.find_image_ids_by_phash_long_edge.return_value = {("aaaaaaaaaaaaaaaa", 1024): [7]}
        for number in range(3):
            record = _make_batch_record("ph:aaaaaaaaaaaaaaaa:le:1024", "Tags: solo\n\nCaption: test")
            (tmp_path / f"batch-{number}.jsonl").write_text(json.dumps(record), encoding="utf-8")

        result = _make_service(mock_repository).import_from_directory(tmp_path, dry_run=True)

        assert result.matched == 3
        mock_repository.get_all_image_filename_index.assert_not_called()

    def test_new_alias_visible_next_operation_and_other_project(
        self, tmp_path: Path, mock_repository: MagicMock
    ) -> None:
        record = _make_batch_record("new-alias", "Tags: solo\n\nCaption: test")
        jsonl_path = _create_jsonl_file(tmp_path, [record])
        mock_repository.get_all_image_filename_index.side_effect = [{}, {"new-alias": 8}, {}]
        service = _make_service(mock_repository)

        assert service.import_from_directory(tmp_path, dry_run=True).unmatched == 1
        assert service.import_from_directory(tmp_path, dry_run=True).matched == 1
        assert service.import_from_jsonl(jsonl_path, dry_run=True).unmatched == 1
        assert mock_repository.get_all_image_filename_index.call_count == 3

        other_repository = MagicMock()
        other_repository.get_all_image_filename_index.return_value = {}
        assert _make_service(other_repository).import_from_directory(tmp_path, dry_run=True).unmatched == 1
        other_repository.get_all_image_filename_index.assert_called_once()

    def test_mixed_records_preserve_partial_parse_and_unmatched_results(
        self, tmp_path: Path, mock_repository: MagicMock
    ) -> None:
        mock_repository.find_image_ids_by_phash_long_edge.return_value = {
            ("aaaaaaaaaaaaaaaa", 1024): [7, 9]
        }
        records = [
            _make_batch_record("ph:aaaaaaaaaaaaaaaa:le:1024", "Tags: solo\n\nCaption: test"),
            _make_batch_record("0262_1227", "Tags: solo\n\nCaption: test"),
            _make_batch_record("unmatched", "Tags: solo\n\nCaption: test"),
            _make_batch_record("invalid", "Invalid content without tags"),
        ]
        for number in range(3):
            (tmp_path / f"batch-{number}.jsonl").write_text(
                "\n".join(json.dumps(record) for record in records), encoding="utf-8"
            )

        result = _make_service(mock_repository).import_from_directory(tmp_path, dry_run=True)

        assert (result.total_records, result.parsed_ok, result.parse_errors) == (12, 9, 3)
        assert (result.matched, result.unmatched, result.saved) == (6, 3, 0)
        assert result.unmatched_ids == ["unmatched"] * 3
        assert len(result.error_details) == 3
        mock_repository.get_all_image_filename_index.assert_called_once()

    def test_multiple_jsonl_files(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """複数JSONLファイルの結果が集約される。"""
        records1 = [_make_batch_record("0262_1227", "Tags: 1girl\n\nCaption: a")]
        records2 = [_make_batch_record("0263_1228", "Tags: solo\n\nCaption: b")]

        (tmp_path / "batch1.jsonl").write_text("\n".join(json.dumps(r) for r in records1), encoding="utf-8")
        (tmp_path / "batch2.jsonl").write_text("\n".join(json.dumps(r) for r in records2), encoding="utf-8")

        service = _make_service(mock_repository)
        result = service.import_from_directory(tmp_path)

        assert result.total_records == 2
        assert result.saved == 2

    def test_no_jsonl_files_raises_error(self, tmp_path: Path, mock_repository: MagicMock) -> None:
        """JSONLファイルなしでValueError。"""
        service = _make_service(mock_repository)
        with pytest.raises(ValueError, match="JSONLファイルが見つかりません"):
            service.import_from_directory(tmp_path)

    def test_nonexistent_directory_raises_error(self, mock_repository: MagicMock) -> None:
        """存在しないディレクトリでFileNotFoundError。"""
        service = _make_service(mock_repository)
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


class TestBatchImportTagResolutionKeys:
    """`batch_resolve_tag_ids` へ渡すキーの正規化 (#1275 / Codex P2)。"""

    def test_resolution_keys_are_clean_format_not_lowercased(
        self, tmp_path: Path, mock_repository: MagicMock
    ) -> None:
        """検索キーは clean_format + strip。小文字化しない。

        外部 tag_db の完全一致はキー側だけを畳むため (genai-tag-db-tools#142)、
        ここで小文字化すると `Xd` のような大文字混じり base タグに到達できず、
        user DB へ重複登録される。underscore を残すと下流の `clean_tag`
        (clean_format 済み) と噛み合わず cache が常に miss する。
        """
        records = [_make_batch_record("0262_1227", "Tags: Long_Hair, Xd\n\nCaption: x")]
        jsonl_path = _create_jsonl_file(tmp_path, records)
        service = _make_service(mock_repository)

        service.import_from_jsonl(jsonl_path)

        passed_keys = mock_repository.batch_resolve_tag_ids.call_args[0][0]
        assert passed_keys == {"Long Hair", "Xd"}
