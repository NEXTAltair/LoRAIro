"""画像管理API。

ImageRegistrationService をラップし、画像登録・管理機能を提供。
"""

from pathlib import Path
from typing import TYPE_CHECKING

from lorairo.api.exceptions import ImageRegistrationError, ProjectNotFoundError
from lorairo.api.types import RegistrationResult
from lorairo.database.db_manager import RegistrationOutcome
from lorairo.services.service_container import ServiceContainer

if TYPE_CHECKING:
    from lorairo.database.db_manager import ImageDatabaseManager
    from lorairo.storage.file_system import FileSystemManager


def register_images(
    directory: str | Path,
    skip_duplicates: bool = True,
    project_name: str | None = None,
) -> RegistrationResult:
    """ディレクトリから画像を登録。

    サポート形式: JPG, JPEG, PNG, GIF, BMP, WEBP

    Args:
        directory: 画像ファイルのディレクトリパス。
        skip_duplicates: 重複画像をスキップするか（デフォルト: True）。
        project_name: 登録先プロジェクト名。指定時は画像をプロジェクトにコピー。

    Returns:
        RegistrationResult: 登録結果（成功数、失敗数、スキップ数など）。

    Raises:
        ImageRegistrationError: ディレクトリが見つからない、
                               または登録処理に失敗した場合。
        ProjectNotFoundError: 指定プロジェクトが見つからない場合。

    使用例:
        >>> from pathlib import Path
        >>> from lorairo.api import register_images
        >>>
        >>> result = register_images(Path("/path/to/images"), project_name="my_project")
        >>> print(f"登録: {result.successful}件, スキップ: {result.skipped}件")
    """
    directory_path = Path(directory) if isinstance(directory, str) else directory

    container = ServiceContainer()

    if project_name:
        if not directory_path.exists():
            raise ImageRegistrationError(f"パスが見つかりません: {directory_path}", 0)
        if not directory_path.is_file() and not directory_path.is_dir():
            raise ImageRegistrationError(f"ファイルまたはディレクトリではありません: {directory_path}", 0)

        # プロジェクト指定時: プロジェクトを自己解決してから DB 登録を行う
        container.set_active_project(project_name)

        scan_service = container.image_registration_service
        image_files = scan_service.get_image_files(directory_path)

        if not image_files:
            if directory_path.is_file():
                raise ImageRegistrationError(f"サポートされていない画像形式: {directory_path}", 0)
            return RegistrationResult(total=0, successful=0, failed=0, skipped=0)

        return _register_into_db(
            container.db_manager,
            container.file_system_manager,
            image_files,
            skip_duplicates=skip_duplicates,
        )

    # プロジェクト未指定: ファイルコピーのみ（DB 登録なし）
    service = container.image_registration_service
    return service.register_images(directory_path, skip_duplicates, None)


def _register_into_db(
    db_manager: "ImageDatabaseManager",
    fsm: "FileSystemManager",
    image_files: list[Path],
    *,
    skip_duplicates: bool = True,
) -> RegistrationResult:
    """project-scoped な DB 登録を統一エントリ経由で行い、outcome を統計へ集計する (#633)。

    分類・保存・関連ファイル・alias の適用は ``register_image_with_side_effects`` が
    分類結果駆動で一元的に行う。本関数は outcome を ``RegistrationResult`` の統計値に
    マッピングするだけで、別版 (variant) を含む全経路統一の統計を返す。

    ADR 0061 では重複は新規行を作らず既存へ寄せるため、``skip_duplicates`` の値に依らず
    DB 行は増えない。ただし統計上の意味は ``skip_duplicates`` で切り替える:
    - ``skip_duplicates=True`` (既定): DUPLICATE は ``skipped`` に集計する。
    - ``skip_duplicates=False`` (``--include-duplicates``): DUPLICATE を既存画像参照の
      成功として ``successful`` に集計する (flag/docstring が約束する「重複を skip しない」
      挙動を満たす)。

    Args:
        db_manager: 画像 DB マネージャー。
        fsm: ファイルシステムマネージャー。
        image_files: 登録対象の画像ファイルリスト。
        skip_duplicates: 重複を skipped 扱いにするか。False なら successful に集計する。

    Returns:
        RegistrationResult: 登録結果 (successful / variant / skipped / failed)。
    """
    registered = 0
    variant = 0
    skipped = 0
    failed = 0
    errors: list[str] = []

    for image_file in image_files:
        try:
            side_effect_result = db_manager.register_image_with_side_effects(image_file, fsm)
            outcome = side_effect_result.outcome
            if outcome is RegistrationOutcome.REGISTERED:
                registered += 1
            elif outcome is RegistrationOutcome.VARIANT:
                variant += 1
            elif outcome is RegistrationOutcome.DUPLICATE:
                # include-duplicates 時は既存画像参照を成功として数える (#633, codex review)
                if skip_duplicates:
                    skipped += 1
                else:
                    registered += 1
            else:
                failed += 1
                errors.append(f"{image_file.name}: 登録失敗")
        except Exception as e:
            failed += 1
            errors.append(f"{image_file.name}: {e!s}")

    return RegistrationResult(
        total=len(image_files),
        successful=registered,
        failed=failed,
        skipped=skipped,
        variant=variant,
        error_details=errors or None,
    )


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
