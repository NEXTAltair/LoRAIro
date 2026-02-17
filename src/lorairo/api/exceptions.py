"""LoRAIro API層のカスタム例外定義。

統一的なエラーハンドリングを提供し、CLI/GUI/API使用時に
一貫したエラー情報を返す。
"""


class LoRAIroException(Exception):
    """LoRAIro基底例外。

    全てのLoRAIro固有の例外は這のクラスから継承する。
    """

    pass


# プロジェクト関連例外
class ProjectError(LoRAIroException):
    """プロジェクト操作エラーの基底クラス。"""

    pass


class ProjectNotFoundError(ProjectError):
    """指定されたプロジェクトが見つからない場合に発生。

    Args:
        project_name: 見つからないプロジェクト名。
    """

    def __init__(self, project_name: str) -> None:
        self.project_name = project_name
        super().__init__(f"プロジェクト '{project_name}' が見つかりません")


class ProjectAlreadyExistsError(ProjectError):
    """同名のプロジェクトが既に存在する場合に発生。

    Args:
        project_name: 重複しているプロジェクト名。
    """

    def __init__(self, project_name: str) -> None:
        self.project_name = project_name
        super().__init__(f"プロジェクト '{project_name}' は既に存在します")


class ProjectOperationError(ProjectError):
    """プロジェクトの作成/削除/更新操作に失敗した場合に発生。

    Args:
        project_name: 操作対象のプロジェクト名。
        operation: 実行した操作（'作成', '削除' など）。
        reason: 失敗した理由。
    """

    def __init__(self, project_name: str, operation: str, reason: str) -> None:
        self.project_name = project_name
        self.operation = operation
        super().__init__(
            f"プロジェクト '{project_name}' の{operation}に失敗しました: {reason}"
        )


# 画像関連例外
class ImageError(LoRAIroException):
    """画像処理エラーの基底クラス。"""

    pass


class ImageNotFoundError(ImageError):
    """指定された画像が見つからない場合に発生。

    Args:
        image_id: 見つからない画像ID。
    """

    def __init__(self, image_id: int) -> None:
        self.image_id = image_id
        super().__init__(f"画像 ID={image_id} が見つかりません")


class DuplicateImageError(ImageError):
    """重複する画像が検出された場合に発生。

    Args:
        file_path: 新規画像ファイルパス。
        existing_id: 既存画像ID。
    """

    def __init__(self, file_path: str, existing_id: int) -> None:
        self.file_path = file_path
        self.existing_id = existing_id
        super().__init__(
            f"画像 '{file_path}' は既に登録されています (ID={existing_id})"
        )


class ImageRegistrationError(ImageError):
    """画像登録に失敗した場合に発生。

    Args:
        reason: 失敗した理由。
        failed_count: 失敗した画像枚数。
    """

    def __init__(self, reason: str, failed_count: int = 1) -> None:
        self.reason = reason
        self.failed_count = failed_count
        super().__init__(f"画像登録に失敗しました: {reason} ({failed_count}件)")


# アノテーション関連例外
class AnnotationError(LoRAIroException):
    """アノテーション処理エラーの基底クラス。"""

    pass


class AnnotationFailedError(AnnotationError):
    """アノテーション実行に失敗した場合に発生。

    Args:
        model_name: 使用したモデル名。
        image_count: アノテーション対象の画像枚数。
        reason: 失敗した理由。
    """

    def __init__(
        self, model_name: str, image_count: int, reason: str
    ) -> None:
        self.model_name = model_name
        self.image_count = image_count
        super().__init__(
            f"モデル '{model_name}' による{image_count}枚の"
            f"アノテーションに失敗しました: {reason}"
        )


class APIKeyNotConfiguredError(AnnotationError):
    """必要なAPIキーが設定されていない場合に発生。

    Args:
        provider: APIプロバイダー名（'openai', 'claude' など）。
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"プロバイダー '{provider}' のAPIキーが設定されていません")


# エクスポート関連例外
class ExportError(LoRAIroException):
    """データセットエクスポートエラーの基底クラス。"""

    pass


class ExportFailedError(ExportError):
    """エクスポート実行に失敗した場合に発生。

    Args:
        format_type: エクスポート形式（'txt', 'json' など）。
        reason: 失敗した理由。
    """

    def __init__(self, format_type: str, reason: str) -> None:
        self.format_type = format_type
        super().__init__(
            f"形式 '{format_type}' でのエクスポートに失敗しました: {reason}"
        )


class InvalidFormatError(ExportError):
    """サポートされていない形式が指定された場合に発生。

    Args:
        format_type: 指定された形式。
        supported_formats: サポートされている形式のリスト。
    """

    def __init__(self, format_type: str, supported_formats: list[str]) -> None:
        self.format_type = format_type
        self.supported_formats = supported_formats
        super().__init__(
            f"形式 '{format_type}' はサポートされていません。"
            f"サポート形式: {', '.join(supported_formats)}"
        )


# タグ関連例外
class TagError(LoRAIroException):
    """タグ管理エラーの基底クラス。"""

    pass


class TagNotFoundError(TagError):
    """指定されたタグが見つからない場合に発生。

    Args:
        tag_name: 見つからないタグ名。
    """

    def __init__(self, tag_name: str) -> None:
        self.tag_name = tag_name
        super().__init__(f"タグ '{tag_name}' が見つかりません")


class TagRegistrationError(TagError):
    """タグ登録に失敗した場合に発生。

    Args:
        tag_name: 登録を試みたタグ名。
        reason: 失敗した理由。
    """

    def __init__(self, tag_name: str, reason: str) -> None:
        self.tag_name = tag_name
        super().__init__(f"タグ '{tag_name}' の登録に失敗しました: {reason}")


# データベース関連例外
class DatabaseError(LoRAIroException):
    """データベース操作エラーの基底クラス。"""

    pass


class DatabaseConnectionError(DatabaseError):
    """データベース接続に失敗した場合に発生。

    Args:
        project_name: 対象プロジェクト名。
        reason: 接続失敗の理由。
    """

    def __init__(self, project_name: str, reason: str) -> None:
        self.project_name = project_name
        super().__init__(
            f"プロジェクト '{project_name}' のデータベース接続に失敗しました: {reason}"
        )


# 入力検証関連例外
class ValidationError(LoRAIroException):
    """入力値バリデーションエラーの基底クラス。"""

    pass


class InvalidInputError(ValidationError):
    """無効な入力値が指定された場合に発生。

    Args:
        field_name: バリデーション失敗したフィールド名。
        reason: 無効な理由。
    """

    def __init__(self, field_name: str, reason: str) -> None:
        self.field_name = field_name
        super().__init__(f"フィールド '{field_name}' は無効です: {reason}")


class InvalidPathError(ValidationError):
    """無効なパスが指定された場合に発生。

    Args:
        path: 無効なパス。
        reason: 無効な理由。
    """

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        super().__init__(f"パス '{path}' は無効です: {reason}")
