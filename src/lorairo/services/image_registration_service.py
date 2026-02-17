"""画像登録 Service。

画像ファイルのスキャン、pHash計算、重複検出を Service 化。
Qt 依存なし。
"""

from pathlib import Path
from typing import ClassVar

from loguru import logger
from PIL import Image

from lorairo.api.exceptions import ImageRegistrationError
from lorairo.api.types import DuplicateInfo, RegistrationResult


class ImageRegistrationService:
    """画像登録 Service。

    画像ファイルのスキャン、pHash計算、重複検出を担当。
    """

    # サポートする画像形式
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
        ".JPG", ".JPEG", ".PNG", ".GIF", ".BMP", ".WEBP"
    }

    def __init__(self) -> None:
        """初期化。"""
        logger.debug("ImageRegistrationService 初期化")

    def register_images(
        self,
        directory: Path,
        skip_duplicates: bool = True,
    ) -> RegistrationResult:
        """ディレクトリから画像を登録。

        Args:
            directory: 画像ファイルのディレクトリ。
            skip_duplicates: 重複画像をスキップするか。

        Returns:
            RegistrationResult: 登録結果。

        Raises:
            ImageRegistrationError: ディレクトリが見つからない場合。
        """
        if not directory.exists():
            raise ImageRegistrationError(
                f"ディレクトリが見つかりません: {directory}", 0
            )

        if not directory.is_dir():
            raise ImageRegistrationError(
                f"ディレクトリではありません: {directory}", 0
            )

        # 画像ファイルをスキャン
        image_files = self._get_image_files(directory)
        logger.info(f"スキャン完了: {len(image_files)}個の画像ファイル")

        # 登録処理
        registered = 0
        skipped = 0
        failed = 0
        errors: list[str] = []
        phashs_seen: set[str] = set()

        for image_file in image_files:
            try:
                # pHashを計算
                phash = self._calculate_phash(image_file)

                if not phash:
                    failed += 1
                    errors.append(f"{image_file.name}: pHash計算失敗")
                    continue

                # 重複チェック
                if skip_duplicates and phash in phashs_seen:
                    skipped += 1
                    logger.debug(
                        f"重複スキップ: {image_file.name} (pHash={phash})"
                    )
                    continue

                # 登録成功カウント
                registered += 1
                phashs_seen.add(phash)
                logger.debug(
                    f"登録: {image_file.name} (pHash={phash})"
                )

            except Exception as e:
                failed += 1
                error_msg = f"{image_file.name}: {e!s}"
                errors.append(error_msg)
                logger.warning(f"登録エラー: {error_msg}")

        result = RegistrationResult(
            total=len(image_files),
            successful=registered,
            failed=failed,
            skipped=skipped,
            error_details=errors if errors else None,
        )

        logger.info(
            f"登録完了: 成功={result.successful}, スキップ={result.skipped}, "
            f"失敗={result.failed}"
        )

        return result

    def detect_duplicate_images(
        self, directory: Path
    ) -> dict[str, list[str]]:
        """ディレクトリ内の重複画像を検出。

        同じpHashを持つ画像をグループ化して返す。

        Args:
            directory: 検索対象ディレクトリ。

        Returns:
            dict[str, list[str]]: pHash -> ファイルパスのリスト。
                                  重複なし（全て異なる）場合は空辞書。

        Raises:
            ImageRegistrationError: ディレクトリが見つからない場合。
        """
        if not directory.exists():
            raise ImageRegistrationError(
                f"ディレクトリが見つかりません: {directory}", 0
            )

        if not directory.is_dir():
            raise ImageRegistrationError(
                f"ディレクトリではありません: {directory}", 0
            )

        image_files = self._get_image_files(directory)
        logger.debug(f"重複検出対象: {len(image_files)}個の画像ファイル")

        # pHash -> ファイルパスのマッピング
        phash_map: dict[str, list[str]] = {}

        for image_file in image_files:
            try:
                phash = self._calculate_phash(image_file)
                if phash:
                    if phash not in phash_map:
                        phash_map[phash] = []
                    phash_map[phash].append(str(image_file))
            except Exception as e:
                logger.warning(
                    f"pHash計算失敗: {image_file.name} - {e}"
                )

        # 重複（2個以上）のみを抽出
        duplicates = {
            phash: files
            for phash, files in phash_map.items()
            if len(files) > 1
        }

        if duplicates:
            logger.info(f"重複検出: {len(duplicates)}グループ")
            for phash, files in duplicates.items():
                logger.debug(f"  pHash={phash}: {len(files)}ファイル")

        return duplicates

    # ==================== プライベートメソッド ====================

    def _get_image_files(self, directory: Path) -> list[Path]:
        """ディレクトリから画像ファイルを取得。

        Args:
            directory: 検索対象ディレクトリ。

        Returns:
            list[Path]: 画像ファイルパスのリスト（ソート済み）。
        """
        image_files: list[Path] = []

        for ext in self.SUPPORTED_EXTENSIONS:
            image_files.extend(directory.glob(f"*{ext}"))

        # 重複排除してソート
        return sorted(set(image_files))

    def _calculate_phash(self, image_path: Path) -> str | None:
        """画像のpHashを計算。

        Args:
            image_path: 画像ファイルパス。

        Returns:
            Optional[str]: pHash値（16進数文字列）。
                          計算失敗時は None。
        """
        try:
            import imagehash

            img = Image.open(image_path)
            phash = imagehash.phash(img)
            return str(phash)

        except Exception as e:
            logger.debug(
                f"pHash計算失敗: {image_path.name} - {type(e).__name__}"
            )
            return None
