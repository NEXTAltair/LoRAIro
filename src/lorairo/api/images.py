"""画像管理API。

ImageRegistrationService をラップし、画像登録・管理機能を提供。
"""

from pathlib import Path

from lorairo.api.exceptions import ImageRegistrationError
from lorairo.api.types import RegistrationResult
from lorairo.services.service_container import ServiceContainer


def register_images(
    directory: str | Path,
    skip_duplicates: bool = True,
) -> RegistrationResult:
    """ディレクトリから画像を登録。

    サポート形式: JPG, JPEG, PNG, GIF, BMP, WEBP

    Args:
        directory: 画像ファイルのディレクトリパス。
        skip_duplicates: 重複画像をスキップするか（デフォルト: True）。

    Returns:
        RegistrationResult: 登録結果（成功数、失敗数、スキップ数など）。

    Raises:
        ImageRegistrationError: ディレクトリが見つからない、
                               または登録処理に失敗した場合。

    使用例:
        >>> from pathlib import Path
        >>> from lorairo.api import register_images
        >>>
        >>> result = register_images(Path("/path/to/images"))
        >>> print(f"登録: {result.successful}件, スキップ: {result.skipped}件")
    """
    directory_path = Path(directory) if isinstance(directory, str) else directory

    container = ServiceContainer()
    service = container.image_registration_service
    return service.register_images(directory_path, skip_duplicates)


def detect_duplicate_images(
    directory: str | Path,
) -> dict[str, list[str]]:
    """ディレクトリ内の重複画像を検出。

    同じ pHash を持つ画像をグループ化して返す。

    Args:
        directory: 検索対象ディレクトリ。

    Returns:
        dict[str, list[str]]: pHash -> ファイルパスのリスト。
                             重複なし（全て異なる）場合は空辞書。

    Raises:
        ImageRegistrationError: ディレクトリが見つからない場合。

    使用例:
        >>> from lorairo.api import detect_duplicate_images
        >>>
        >>> duplicates = detect_duplicate_images("/path/to/images")
        >>> for phash, files in duplicates.items():
        ...     print(f"pHash {phash}: {len(files)}個の重複")
    """
    directory_path = Path(directory) if isinstance(directory, str) else directory

    container = ServiceContainer()
    service = container.image_registration_service
    return service.detect_duplicate_images(directory_path)
