"""画像登録 Service。

画像ファイルのスキャン、pHash計算、重複検出、プロジェクトへのコピーを Service 化。
Qt 依存なし。
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from loguru import logger
from PIL import Image

from lorairo.public_api.exceptions import ImageRegistrationError
from lorairo.public_api.types import RegistrationResult


@dataclass
class _DirectRegistrationTally:
    """direct 登録経路の集計カウンタ (#633)。

    project 未指定 / ファイルコピーのみの direct 経路で、重複/別版/新規を
    分類属性込み署名で区別して集計するための作業用カウンタ。
    """

    registered: int = 0
    variant: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    signatures_seen: set[tuple[str, tuple[Any, ...]]] = field(default_factory=set)
    phashs_seen: set[str] = field(default_factory=set)


class ImageRegistrationService:
    """画像登録 Service。

    画像ファイルのスキャン、pHash計算、重複検出、プロジェクトへの登録を担当。
    """

    # サポートする画像形式
    SUPPORTED_EXTENSIONS: ClassVar[set[str]] = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".JPG",
        ".JPEG",
        ".PNG",
        ".GIF",
        ".BMP",
        ".WEBP",
    }

    def __init__(self) -> None:
        """初期化。"""
        logger.debug("ImageRegistrationService 初期化")

    def register_images(
        self,
        source: Path,
        skip_duplicates: bool = True,
        project_dir: Path | None = None,
    ) -> RegistrationResult:
        """ファイルまたはディレクトリから画像を登録。

        Args:
            source: 画像ファイルまたはソースディレクトリのパス。
            skip_duplicates: 重複画像をスキップするか。
            project_dir: プロジェクトディレクトリ。指定時は
                        image_dataset/original_images/ にコピー。

        Returns:
            RegistrationResult: 登録結果。

        Raises:
            ImageRegistrationError: パスが見つからない、または非対応形式の場合。
        """
        if not source.exists():
            raise ImageRegistrationError(f"パスが見つかりません: {source}", 0)
        if source.is_file() and source.suffix not in self.SUPPORTED_EXTENSIONS:
            raise ImageRegistrationError(f"サポートされていない画像形式: {source}", 0)

        image_files = self.get_image_files(source)

        # プロジェクトの画像格納先を準備
        dest_dir: Path | None = None
        if project_dir:
            dest_dir = project_dir / "image_dataset" / "original_images"
            dest_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"スキャン完了: {len(image_files)}個の画像ファイル")

        # 登録処理 (ADR 0061 §4 / #633: 分類属性込み署名で別版を区別して dedup)
        tally = _DirectRegistrationTally()
        for image_file in image_files:
            try:
                self._register_one_direct(image_file, skip_duplicates, dest_dir, tally)
            except Exception as e:
                tally.failed += 1
                error_msg = f"{image_file.name}: {e!s}"
                tally.errors.append(error_msg)
                logger.warning(f"登録エラー: {error_msg}")

        result = RegistrationResult(
            total=len(image_files),
            successful=tally.registered,
            failed=tally.failed,
            skipped=tally.skipped,
            variant=tally.variant,
            error_details=tally.errors if tally.errors else None,
        )

        logger.info(
            f"登録完了: 成功={result.successful}, 別版={result.variant}, "
            f"スキップ={result.skipped}, 失敗={result.failed}"
        )

        return result

    def _register_one_direct(
        self,
        image_file: Path,
        skip_duplicates: bool,
        dest_dir: Path | None,
        tally: "_DirectRegistrationTally",
    ) -> None:
        """direct 経路で 1 ファイルを分類・コピーし、tally を in-place 更新する (#633)。

        pHash + 分類属性込みの署名で重複/別版/新規を判定する。重複は skip、別版は
        variant、新規は registered に集計し、project 指定時はファイルをコピーする。

        Args:
            image_file: 処理対象の画像ファイル。
            skip_duplicates: 重複をスキップするか。
            dest_dir: コピー先ディレクトリ (None ならコピーしない)。
            tally: 集計カウンタ (in-place 更新)。
        """
        phash = self._calculate_phash(image_file)
        if not phash:
            tally.failed += 1
            tally.errors.append(f"{image_file.name}: pHash計算失敗")
            return

        # 分類属性込みの dedup 署名を構築 (取得失敗時は pHash 単独へフォールバック)
        signature = self._build_dedup_signature(image_file, phash)

        # 重複チェック (属性込み署名で別版を区別)
        if skip_duplicates and signature is not None and signature in tally.signatures_seen:
            tally.skipped += 1
            logger.debug(f"重複スキップ: {image_file.name} (pHash={phash})")
            return

        # プロジェクトディレクトリにコピー
        if dest_dir:
            dest_file = dest_dir / image_file.name
            if not dest_file.exists():
                shutil.copy2(image_file, dest_file)

        # 別版判定: 同一 pHash 既出 かつ 属性署名が未出 → variant 集計 (#633)。
        # 同一署名 (真の重複) を skip_duplicates=False で登録する場合は variant にせず
        # registered に集計する (属性まで同一なら別版ではない)。
        is_variant = (
            phash in tally.phashs_seen and signature is not None and signature not in tally.signatures_seen
        )
        if is_variant:
            tally.variant += 1
            logger.debug(f"別版登録 (同一pHash): {image_file.name} (pHash={phash})")
        else:
            tally.registered += 1
            logger.debug(f"登録: {image_file.name} (pHash={phash})")

        tally.phashs_seen.add(phash)
        if signature is not None:
            tally.signatures_seen.add(signature)

    def _build_dedup_signature(self, image_path: Path, phash: str) -> tuple[str, tuple[Any, ...]] | None:
        """pHash + 分類属性から dedup 署名を構築する (ADR 0061 §4, #633)。

        DB を持たない direct 登録経路で「同一 pHash でも属性差があれば別版」を判定する
        ため、``ImageRepository.classify_phash_candidate`` と同じ分類属性
        (width / height / has_alpha / is_grayscale_like) を署名に含める。

        属性取得に失敗した場合は None を返し、呼び出し元は pHash 単独 dedup を諦めて
        その画像を常に新規扱いにする (誤って別画像を skip しないための保守的挙動)。

        Args:
            image_path: 署名を構築する画像パス。
            phash: 計算済み pHash。

        Returns:
            ``(phash, (属性値, ...))`` の署名。属性取得失敗時は None。
        """
        from lorairo.database.repository.image import ImageRepository
        from lorairo.storage.file_system import FileSystemManager

        # get_image_info は OSError / ValueError に限らず、壊れた埋め込み ICC profile の
        # ImageCms エラー等 (broad re-raise) も投げ得る。本 helper の契約は「属性取得失敗は
        # 画像を reject せず dedup を見送る」なので broad に捕捉して None を返す (codex review
        # #648 P2)。捕捉できないと外側ループが当該画像を failed に誤計上する。
        try:
            info = FileSystemManager.get_image_info(image_path)
        except Exception as e:
            logger.warning(f"画像情報取得に失敗、pHash単独dedupを見送り: {image_path.name}, {e}")
            return None
        attrs = tuple(info.get(attr) for attr in ImageRepository.CLASSIFICATION_ATTRS)
        return (phash, attrs)

    def detect_duplicate_images(self, directory: Path) -> dict[str, list[str]]:
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
            raise ImageRegistrationError(f"ディレクトリが見つかりません: {directory}", 0)

        if not directory.is_dir():
            raise ImageRegistrationError(f"ディレクトリではありません: {directory}", 0)

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
                logger.warning(f"pHash計算失敗: {image_file.name} - {e}")

        # 重複（2個以上）のみを抽出
        duplicates = {phash: files for phash, files in phash_map.items() if len(files) > 1}

        if duplicates:
            logger.info(f"重複検出: {len(duplicates)}グループ")
            for phash, files in duplicates.items():
                logger.debug(f"  pHash={phash}: {len(files)}ファイル")

        return duplicates

    def get_image_files(self, source: Path) -> list[Path]:
        """ファイルまたはディレクトリから画像ファイルを取得（公開API）。

        Args:
            source: 画像ファイルまたは検索対象ディレクトリ。

        Returns:
            list[Path]: 画像ファイルパスのリスト（ソート済み）。
        """
        if source.is_file():
            if source.suffix in self.SUPPORTED_EXTENSIONS:
                return [source]
            return []
        return self._get_image_files(source)

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
            logger.debug(f"pHash計算失敗: {image_path.name} - {type(e).__name__}")
            return None
