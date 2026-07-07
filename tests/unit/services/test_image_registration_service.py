"""ImageRegistrationService ユニットテスト。

Issue #368: BDD で扱われない Service 内部の境界条件・重複検出・pHash 計算等の
deterministic な振る舞いを検証する。外部ネットワーク・実モデルには依存しない。
"""

from pathlib import Path

import pytest
from PIL import Image

from lorairo.public_api.exceptions import ImageRegistrationError
from lorairo.public_api.types import RegistrationResult
from lorairo.services.image_registration_service import ImageRegistrationService

# ==================== ローカル fixture ====================


@pytest.fixture
def service() -> ImageRegistrationService:
    """テスト対象の ImageRegistrationService インスタンス。"""
    return ImageRegistrationService()


def _make_image(
    path: Path, color: tuple[int, int, int] = (255, 0, 0), size: tuple[int, int] = (8, 8)
) -> Path:
    """8x8 の小さな PNG 画像を ``path`` に作成する。

    pHash 計算は実物の imagehash ライブラリで行うため、各画像で色を変えて
    pHash の差が出るようにする。

    Args:
        path: 画像ファイルの保存先。
        color: RGB 値。pHash 差異を出すために呼び出し側で変える。
        size: 画像サイズ（ピクセル）。pHash は内部で 32x32 にリサイズするため
              8x8 でも十分。

    Returns:
        作成した画像ファイルのパス。
    """
    img = Image.new("RGB", size, color=color)
    img.save(path)
    return path


def _make_unique_images(directory: Path, count: int) -> list[Path]:
    """``directory`` に互いに pHash が異なる ``count`` 枚の画像を作成する。

    色を大きく変えることで pHash が必ず異なるようにする。
    """
    paths: list[Path] = []
    # pHash が確実に異なるようにグラデーション + ノイズ的に変化させる
    for i in range(count):
        # 各画像で全ピクセルのパターンが変わるよう、PNG を直接構築する
        img = Image.new("RGB", (16, 16))
        for x in range(16):
            for y in range(16):
                # 画像ごとに大きく異なるパターン
                r = (i * 47 + x * 11 + y * 5) % 256
                g = (i * 89 + x * 7 + y * 13) % 256
                b = (i * 31 + x * 17 + y * 3) % 256
                img.putpixel((x, y), (r, g, b))
        path = directory / f"image_{i:03d}.png"
        img.save(path)
        paths.append(path)
    return paths


# ==================== register_images: 通常系 ====================


@pytest.mark.unit
class TestRegisterImagesNormal:
    """register_images の通常系（重複なし）。"""

    def test_register_images_with_directory_of_unique_images_registers_all(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """重複のないディレクトリ内 N 枚 → 全て successful に集計される。"""
        paths = _make_unique_images(tmp_path, 3)

        result = service.register_images(tmp_path, skip_duplicates=True)

        assert isinstance(result, RegistrationResult)
        assert result.total == len(paths)
        assert result.successful == 3
        assert result.skipped == 0
        assert result.failed == 0
        assert result.error_details is None

    def test_register_images_with_directory_recurses_into_subdirectories(
        self, service: ImageRegistrationService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """親ディレクトリ指定でもサブディレクトリ内の画像を登録対象に含める (#1267)。"""
        root_image = _make_image(tmp_path / "root.png")
        char_a = tmp_path / "char_a"
        char_b = tmp_path / "char_b"
        char_a.mkdir()
        char_b.mkdir()
        nested_images = [
            _make_image(char_a / "a.png", color=(0, 255, 0)),
            _make_image(char_b / "b.jpg", color=(0, 0, 255)),
        ]
        monkeypatch.setattr(service, "_calculate_phash", lambda p: str(p.relative_to(tmp_path)))

        result = service.register_images(tmp_path, skip_duplicates=True)

        assert result.total == 1 + len(nested_images)
        assert result.successful == 1 + len(nested_images)
        assert result.failed == 0
        assert result.skipped == 0
        assert root_image in service.get_image_files(tmp_path)

    def test_register_images_with_empty_directory_returns_zero_counts(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """空ディレクトリ → 0 件登録。"""
        result = service.register_images(tmp_path)

        assert result.total == 0
        assert result.successful == 0
        assert result.skipped == 0
        assert result.failed == 0

    def test_register_images_with_unsupported_extensions_only_returns_zero_counts(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """非対応拡張子のみのディレクトリ → 0 件登録（拡張子フィルタで除外）。"""
        (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "data.csv").write_text("a,b,c", encoding="utf-8")
        (tmp_path / "readme.md").write_text("# title", encoding="utf-8")

        result = service.register_images(tmp_path)

        assert result.total == 0
        assert result.successful == 0
        assert result.skipped == 0
        assert result.failed == 0


# ==================== register_images: 重複処理 ====================


@pytest.mark.unit
class TestRegisterImagesDuplicates:
    """register_images の重複検出経路。"""

    def test_register_images_with_skip_duplicates_true_skips_duplicate_phash(
        self,
        service: ImageRegistrationService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """skip_duplicates=True かつ同一 pHash が複数 → 1 枚 successful、残り skipped。"""
        # 3 枚作成（実 pHash は異なる）してから _calculate_phash を固定値モックする
        _make_unique_images(tmp_path, 3)
        monkeypatch.setattr(service, "_calculate_phash", lambda p: "deadbeef")

        result = service.register_images(tmp_path, skip_duplicates=True)

        assert result.total == 3
        assert result.successful == 1
        assert result.skipped == 2
        assert result.failed == 0

    def test_register_images_with_skip_duplicates_false_registers_all_duplicates(
        self,
        service: ImageRegistrationService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """skip_duplicates=False かつ同一 pHash が複数 → 全て successful。"""
        _make_unique_images(tmp_path, 3)
        monkeypatch.setattr(service, "_calculate_phash", lambda p: "deadbeef")

        result = service.register_images(tmp_path, skip_duplicates=False)

        assert result.total == 3
        assert result.successful == 3
        assert result.skipped == 0
        assert result.failed == 0


# ==================== _build_dedup_signature: 属性取得失敗 ====================


@pytest.mark.unit
class TestBuildDedupSignature:
    """_build_dedup_signature の属性取得失敗フォールバック (#633, codex P2)。"""

    def test_get_image_info_broad_error_falls_back_to_none(
        self, service: ImageRegistrationService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_image_info が OSError/ValueError 以外 (ImageCms 等) を投げても None で畳む。"""
        from lorairo.filesystem import FileSystemManager

        image_path = tmp_path / "broken_icc.jpg"
        image_path.write_bytes(b"fake")

        def _raise_imagecms(_path: Path) -> dict:
            # ImageCms 由来の独自例外を模す (OSError/ValueError ではない)
            raise RuntimeError("PyCMSError: cannot build transform")

        monkeypatch.setattr(FileSystemManager, "get_image_info", staticmethod(_raise_imagecms))

        # broad に捕捉され None を返す (reject せず dedup 見送り)
        assert service._build_dedup_signature(image_path, "deadbeef") is None

    def test_broken_metadata_counted_not_as_failed(
        self, service: ImageRegistrationService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """属性取得が broad 例外でも、ハッシュ可能な画像は failed にならず登録される。"""
        from lorairo.filesystem import FileSystemManager

        _make_unique_images(tmp_path, 1)
        monkeypatch.setattr(service, "_calculate_phash", lambda p: "deadbeef")
        monkeypatch.setattr(
            FileSystemManager,
            "get_image_info",
            staticmethod(lambda _p: (_ for _ in ()).throw(RuntimeError("ICC error"))),
        )

        result = service.register_images(tmp_path, skip_duplicates=True)

        assert result.failed == 0
        assert result.successful == 1


# ==================== register_images: エラー系 ====================


@pytest.mark.unit
class TestRegisterImagesErrors:
    """register_images の例外パス。"""

    def test_register_images_with_nonexistent_path_raises_image_registration_error(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """存在しないパス → ImageRegistrationError。"""
        missing = tmp_path / "does_not_exist"

        with pytest.raises(ImageRegistrationError) as excinfo:
            service.register_images(missing)

        assert "パスが見つかりません" in str(excinfo.value)

    def test_register_images_with_unsupported_single_file_raises_image_registration_error(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """非対応拡張子の単一ファイル → ImageRegistrationError。"""
        unsupported = tmp_path / "data.txt"
        unsupported.write_text("not an image", encoding="utf-8")

        with pytest.raises(ImageRegistrationError) as excinfo:
            service.register_images(unsupported)

        assert "サポートされていない画像形式" in str(excinfo.value)

    def test_register_images_counts_failed_when_phash_returns_none(
        self,
        service: ImageRegistrationService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """pHash 計算が None を返したファイルは failed に集計され error_details に記録される。"""
        _make_unique_images(tmp_path, 2)
        monkeypatch.setattr(service, "_calculate_phash", lambda p: None)

        result = service.register_images(tmp_path)

        assert result.total == 2
        assert result.successful == 0
        assert result.failed == 2
        assert result.error_details is not None
        assert len(result.error_details) == 2
        assert all("pHash計算失敗" in detail for detail in result.error_details)


# ==================== register_images: project_dir コピー ====================


@pytest.mark.unit
class TestRegisterImagesProjectDir:
    """register_images の project_dir 指定時のファイルコピー挙動。"""

    def test_register_images_with_project_dir_copies_to_original_images(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """project_dir 指定時 → <project_dir>/image_dataset/original_images/ にコピーされる。"""
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        project_dir = tmp_path / "project"
        paths = _make_unique_images(source_dir, 2)

        result = service.register_images(source_dir, project_dir=project_dir)

        dest_dir = project_dir / "image_dataset" / "original_images"
        assert dest_dir.is_dir()
        for src_path in paths:
            assert (dest_dir / src_path.name).is_file()
        assert result.successful == 2

    def test_register_images_with_project_dir_preserves_nested_relative_paths_for_same_basename(
        self,
        service: ImageRegistrationService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """再帰登録時、別サブディレクトリの同名ファイルを上書き・欠落させない (#1267)。"""
        source_dir = tmp_path / "src"
        char_a = source_dir / "char_a"
        char_b = source_dir / "char_b"
        char_a.mkdir(parents=True)
        char_b.mkdir(parents=True)
        _make_image(char_a / "0001.png")
        _make_image(char_b / "0001.png", color=(0, 255, 0))
        project_dir = tmp_path / "project"
        monkeypatch.setattr(service, "_calculate_phash", lambda p: str(p.relative_to(source_dir)))

        result = service.register_images(source_dir, project_dir=project_dir)

        dest_dir = project_dir / "image_dataset" / "original_images"
        assert (dest_dir / "char_a" / "0001.png").is_file()
        assert (dest_dir / "char_b" / "0001.png").is_file()
        assert not (dest_dir / "0001.png").exists()
        assert result.total == 2
        assert result.successful == 2
        assert result.failed == 0

    def test_register_images_with_project_dir_does_not_overwrite_existing_destination(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """コピー先に同名ファイルが既に存在する場合は上書きしない（既存ファイル維持）。"""
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        paths = _make_unique_images(source_dir, 1)
        project_dir = tmp_path / "project"

        dest_dir = project_dir / "image_dataset" / "original_images"
        dest_dir.mkdir(parents=True)
        existing_dest = dest_dir / paths[0].name
        existing_dest.write_bytes(b"ORIGINAL_CONTENT")

        result = service.register_images(source_dir, project_dir=project_dir)

        # 既存ファイル内容は保持される
        assert existing_dest.read_bytes() == b"ORIGINAL_CONTENT"
        assert result.successful == 1


# ==================== detect_duplicate_images ====================


@pytest.mark.unit
class TestDetectDuplicateImages:
    """detect_duplicate_images の挙動。"""

    def test_detect_duplicate_images_when_all_unique_returns_empty_dict(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """重複なし → 空辞書。"""
        _make_unique_images(tmp_path, 3)

        duplicates = service.detect_duplicate_images(tmp_path)

        assert duplicates == {}

    def test_detect_duplicate_images_when_phash_collides_groups_files(
        self,
        service: ImageRegistrationService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """同一 pHash 画像が複数 → pHash → list[str] の dict が返る。"""
        paths = _make_unique_images(tmp_path, 3)
        monkeypatch.setattr(service, "_calculate_phash", lambda p: "deadbeef")

        duplicates = service.detect_duplicate_images(tmp_path)

        assert list(duplicates.keys()) == ["deadbeef"]
        assert sorted(duplicates["deadbeef"]) == sorted(str(p) for p in paths)

    def test_detect_duplicate_images_recurses_into_subdirectories(
        self,
        service: ImageRegistrationService,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """重複検出もサブディレクトリ内の画像を対象に含める (#1267)。"""
        root_path = _make_image(tmp_path / "root.png")
        nested_dir = tmp_path / "nested"
        nested_dir.mkdir()
        nested_path = _make_image(nested_dir / "nested.png", color=(0, 255, 0))
        monkeypatch.setattr(service, "_calculate_phash", lambda p: "deadbeef")

        duplicates = service.detect_duplicate_images(tmp_path)

        assert duplicates == {"deadbeef": sorted([str(root_path), str(nested_path)])}

    def test_detect_duplicate_images_with_nonexistent_path_raises_image_registration_error(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """存在しないディレクトリ → ImageRegistrationError。"""
        missing = tmp_path / "missing"

        with pytest.raises(ImageRegistrationError) as excinfo:
            service.detect_duplicate_images(missing)

        assert "ディレクトリが見つかりません" in str(excinfo.value)

    def test_detect_duplicate_images_with_file_instead_of_dir_raises_image_registration_error(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """ディレクトリではなくファイル指定 → ImageRegistrationError。"""
        file_path = tmp_path / "single.png"
        _make_image(file_path)

        with pytest.raises(ImageRegistrationError) as excinfo:
            service.detect_duplicate_images(file_path)

        assert "ディレクトリではありません" in str(excinfo.value)


# ==================== get_image_files ====================


@pytest.mark.unit
class TestGetImageFiles:
    """get_image_files の公開 API 挙動。"""

    def test_get_image_files_with_directory_returns_only_supported_extensions_sorted(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """ディレクトリ内の対応拡張子のみがソートされて返る。"""
        # 対応拡張子（大文字小文字混在）
        _make_image(tmp_path / "b.png")
        _make_image(tmp_path / "a.jpg")
        _make_image(tmp_path / "c.JPEG")
        # 非対応拡張子は除外される
        (tmp_path / "note.txt").write_text("ignored", encoding="utf-8")
        (tmp_path / "data.csv").write_text("ignored", encoding="utf-8")

        files = service.get_image_files(tmp_path)

        assert files == sorted(files)
        names = [p.name for p in files]
        assert "a.jpg" in names
        assert "b.png" in names
        assert "c.JPEG" in names
        assert "note.txt" not in names
        assert "data.csv" not in names
        assert len(files) == 3

    def test_get_image_files_with_directory_recurses_and_uses_gui_extensions(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """GUI と同じ再帰走査・拡張子定義で tif/tiff も返す (#1267)。"""
        nested = tmp_path / "nested"
        nested.mkdir()
        _make_image(tmp_path / "root.tif")
        _make_image(nested / "child.TIFF")
        _make_image(nested / "child.webp")
        (nested / "note.txt").write_text("ignored", encoding="utf-8")

        files = service.get_image_files(tmp_path)

        assert files == sorted(files)
        assert [p.relative_to(tmp_path) for p in files] == [
            Path("nested/child.TIFF"),
            Path("nested/child.webp"),
            Path("root.tif"),
        ]

    def test_get_image_files_with_supported_single_file_returns_one_element_list(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """対応拡張子の単一ファイル → 1 要素のリスト。"""
        file_path = tmp_path / "single.png"
        _make_image(file_path)

        files = service.get_image_files(file_path)

        assert files == [file_path]

    def test_get_image_files_with_unsupported_single_file_returns_empty_list(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """非対応拡張子の単一ファイル → 空リスト（例外は出さない、公開 API としての判定用）。"""
        file_path = tmp_path / "note.txt"
        file_path.write_text("not an image", encoding="utf-8")

        files = service.get_image_files(file_path)

        assert files == []

    def test_get_image_files_with_empty_directory_returns_empty_list(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """空ディレクトリ → 空リスト。"""
        files = service.get_image_files(tmp_path)

        assert files == []


# ==================== _calculate_phash ====================


@pytest.mark.unit
class TestCalculatePhash:
    """_calculate_phash の正常系と破損入力での None 返却。"""

    def test_calculate_phash_with_valid_image_returns_hex_string(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """有効な画像 → 16進数文字列の pHash を返す。"""
        image_path = tmp_path / "valid.png"
        _make_image(image_path)

        phash = service._calculate_phash(image_path)

        assert phash is not None
        assert isinstance(phash, str)
        # imagehash.phash の出力は 16 進文字列（デフォルト hash_size=8 で 16 文字）
        assert len(phash) > 0
        assert all(c in "0123456789abcdef" for c in phash)

    def test_calculate_phash_with_empty_file_returns_none(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """中身が空のファイル → None を返す（例外を吸収）。"""
        empty_path = tmp_path / "empty.png"
        empty_path.write_bytes(b"")

        phash = service._calculate_phash(empty_path)

        assert phash is None

    def test_calculate_phash_with_text_file_renamed_as_png_returns_none(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """テキストファイルを .png にリネームしただけのファイル → None を返す。"""
        fake_png = tmp_path / "fake.png"
        fake_png.write_text("this is plain text, not a PNG", encoding="utf-8")

        phash = service._calculate_phash(fake_png)

        assert phash is None

    def test_calculate_phash_returns_same_value_for_identical_images(
        self, service: ImageRegistrationService, tmp_path: Path
    ) -> None:
        """同じ内容の画像は同じ pHash を返す（deterministic 性）。"""
        path1 = tmp_path / "img1.png"
        path2 = tmp_path / "img2.png"
        _make_image(path1, color=(100, 150, 200))
        _make_image(path2, color=(100, 150, 200))

        phash1 = service._calculate_phash(path1)
        phash2 = service._calculate_phash(path2)

        assert phash1 is not None
        assert phash2 is not None
        assert phash1 == phash2
