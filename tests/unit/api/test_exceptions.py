"""api/exceptions.py のユニットテスト。"""

import pytest

from lorairo.api.exceptions import (
    AnnotationFailedError,
    APIKeyNotConfiguredError,
    BatchImportError,
    DatabaseConnectionError,
    DuplicateImageError,
    ExportFailedError,
    ImageNotFoundError,
    ImageRegistrationError,
    InvalidFormatError,
    InvalidInputError,
    InvalidPathError,
    LoRAIroException,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectOperationError,
    TagNotFoundError,
    TagRegistrationError,
)


class TestProjectExceptions:
    """プロジェクト関連例外のテスト。"""

    def test_project_not_found_error(self):
        err = ProjectNotFoundError("my_project")
        assert err.project_name == "my_project"
        assert "my_project" in str(err)

    def test_project_already_exists_error(self):
        err = ProjectAlreadyExistsError("dup_project")
        assert err.project_name == "dup_project"
        assert "dup_project" in str(err)

    def test_project_operation_error(self):
        err = ProjectOperationError("proj", "作成", "権限エラー")
        assert err.project_name == "proj"
        assert err.operation == "作成"
        assert "権限エラー" in str(err)

    def test_project_exceptions_inherit_base(self):
        assert isinstance(ProjectNotFoundError("x"), LoRAIroException)
        assert isinstance(ProjectAlreadyExistsError("x"), LoRAIroException)
        assert isinstance(ProjectOperationError("x", "op", "reason"), LoRAIroException)


class TestImageExceptions:
    """画像関連例外のテスト。"""

    def test_image_not_found_error(self):
        err = ImageNotFoundError(42)
        assert err.image_id == 42
        assert "42" in str(err)

    def test_duplicate_image_error(self):
        err = DuplicateImageError("/path/to/image.jpg", 10)
        assert err.file_path == "/path/to/image.jpg"
        assert err.existing_id == 10
        assert "/path/to/image.jpg" in str(err)
        assert "10" in str(err)

    def test_image_registration_error_default_count(self):
        err = ImageRegistrationError("ファイルが見つかりません")
        assert err.reason == "ファイルが見つかりません"
        assert err.failed_count == 1

    def test_image_registration_error_custom_count(self):
        err = ImageRegistrationError("バッチエラー", failed_count=5)
        assert err.failed_count == 5


class TestAnnotationExceptions:
    """アノテーション関連例外のテスト。"""

    def test_annotation_failed_error(self):
        err = AnnotationFailedError("gpt-4o", 10, "タイムアウト")
        assert err.model_name == "gpt-4o"
        assert err.image_count == 10
        assert "タイムアウト" in str(err)

    def test_batch_import_error_default(self):
        err = BatchImportError("パースエラー")
        assert err.processed == 0
        assert "パースエラー" in str(err)

    def test_batch_import_error_with_processed(self):
        err = BatchImportError("DBエラー", processed=3)
        assert err.processed == 3

    def test_api_key_not_configured_error(self):
        err = APIKeyNotConfiguredError("openai")
        assert err.provider == "openai"
        assert "openai" in str(err)


class TestExportExceptions:
    """エクスポート関連例外のテスト。"""

    def test_export_failed_error(self):
        err = ExportFailedError("json", "ディスクフル")
        assert err.format_type == "json"
        assert "ディスクフル" in str(err)

    def test_invalid_format_error(self):
        err = InvalidFormatError("xml", ["json", "txt", "csv"])
        assert err.format_type == "xml"
        assert err.supported_formats == ["json", "txt", "csv"]
        assert "json" in str(err)


class TestTagExceptions:
    """タグ関連例外のテスト。"""

    def test_tag_not_found_error(self):
        err = TagNotFoundError("unknown_tag")
        assert err.tag_name == "unknown_tag"
        assert "unknown_tag" in str(err)

    def test_tag_registration_error(self):
        err = TagRegistrationError("my_tag", "重複エラー")
        assert err.tag_name == "my_tag"
        assert "重複エラー" in str(err)


class TestDatabaseExceptions:
    """データベース関連例外のテスト。"""

    def test_database_connection_error(self):
        err = DatabaseConnectionError("my_project", "接続タイムアウト")
        assert err.project_name == "my_project"
        assert "接続タイムアウト" in str(err)


class TestValidationExceptions:
    """バリデーション関連例外のテスト。"""

    def test_invalid_input_error(self):
        err = InvalidInputError("email", "形式が不正")
        assert err.field_name == "email"
        assert "形式が不正" in str(err)

    def test_invalid_path_error(self):
        err = InvalidPathError("/bad/path", "存在しません")
        assert err.path == "/bad/path"
        assert "存在しません" in str(err)
