"""Kohya-ss 形式の学習データセットを、版・フォルダ・学習テキストとして取り込む service (Issue #1418)。

設計書: `docs/superpowers/specs/2026-11-05-kohya-dataset-roundtrip-design.md`。

- 画像は `ImageDatabaseManager.register_original_image` で登録するだけで、画像直下の `Tag` /
  `Caption` には書かない。学習テキストは `DatasetRepository` 側にフォルダごとに保存する。
- トリガーワードは計画 (`FolderImportPlan.trigger_word`) の値だけを保存する。スキャンの候補は
  確認なしに確定しない。
- 書き込みの前に計画を検証し、設定 json も正規化しておく。版の作成で衝突した場合は何も書かない。
- 設定 json の秘密の値は `normalize_kohya_gui_config` が取り除いたものだけを保存する。
"""

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from lorairo.database.db_manager import ImageDatabaseManager
from lorairo.database.repository.dataset import (
    DatasetConflictError,
    DatasetRepository,
    FolderImageSpec,
    FolderSpec,
    LearningTextSpec,
    TrainingConfigSpec,
)
from lorairo.filesystem import FileSystemManager
from lorairo.services.kohya_config_normalizer import (
    NormalizedConfig,
    NormalizedValue,
    normalize_kohya_gui_config,
)
from lorairo.services.kohya_scanner import (
    DEFAULT_DISCOVERY_MAX_DEPTH,
    DEFAULT_EXCLUDE_PATTERNS,
    ScannedFolder,
    discover_kohya_roots,
    has_kohya_folder,
    scan_kohya_directory,
)
from lorairo.utils.log import logger

CONFIG_SOURCE_KIND = "kohya_gui_json"


@dataclass(frozen=True)
class FolderScanSummary:
    """フォルダ 1 つ分のスキャン情報 (確認用。確定値ではない)。

    Attributes:
        image_count: フォルダ直下の画像数。
        images_without_text: 学習テキスト (`.txt` / `.caption`) が無い画像数。
        trigger_candidate: 先頭要素の共通性から出したトリガーワード候補。閾値未満なら None。
        trigger_match_rate: 最頻の先頭要素を先頭に持つ画像の割合 (0.0〜1.0)。
    """

    image_count: int
    images_without_text: int
    trigger_candidate: str | None
    trigger_match_rate: float


@dataclass(frozen=True)
class FolderImportPlan:
    """取り込むフォルダ 1 つ分の確定値。

    `scan` は確認用のスキャン情報で、取り込みには使わない。トリガーワード候補
    (`scan.trigger_candidate`) は確認なしに `trigger_word` へ入れない (ADR 0098)。
    """

    dir_name: str
    name: str
    num_repeats: int
    trigger_word: str | None
    include: bool
    scan: FolderScanSummary | None = None


@dataclass(frozen=True)
class DatasetImportPlan:
    """取り込みの計画 (ユーザーが確認・確定したもの)。"""

    dataset_name: str
    version_name: str
    parent_version_id: int | None
    folders: list[FolderImportPlan]
    config_files: list[Path]
    train_data_dir_hints: list[str] = field(default_factory=list)

    @property
    def included_folders(self) -> list[FolderImportPlan]:
        """取り込む (`include=True`) フォルダ。"""
        return [folder for folder in self.folders if folder.include]


@dataclass(frozen=True)
class FolderOverride:
    """ユーザーが確認画面で確定したフォルダ 1 つ分の値 (取捨・繰り返し回数・トリガーワード)。"""

    dir_name: str
    include: bool
    num_repeats: int
    trigger_word: str | None


def apply_folder_overrides(plan: DatasetImportPlan, overrides: list[FolderOverride]) -> DatasetImportPlan:
    """確定値を計画のフォルダに反映した新しい計画を返す。

    `overrides` は確認画面で確定したフォルダの全体とみなし、確定値の無いフォルダ (確認後に
    追加されたフォルダなど、ユーザーが確認していないもの) は取り込まない。
    トリガーワードの空文字は未設定 (`None`) とする。

    Args:
        plan: `propose_plan` で作った計画。
        overrides: フォルダごとの確定値。

    Returns:
        確定値を反映した計画。

    Raises:
        ValueError: 確定値のフォルダが計画に無い、同じフォルダが重複する、繰り返し回数が 1 未満の場合。
    """
    by_dir: dict[str, FolderOverride] = {}
    for override in overrides:
        if override.dir_name in by_dir:
            raise ValueError(f"同じフォルダの指定が重複しています: '{override.dir_name}'")
        if override.num_repeats < 1:
            raise ValueError(f"繰り返し回数は 1 以上にしてください: '{override.dir_name}'")
        by_dir[override.dir_name] = override
    known = {folder.dir_name for folder in plan.folders}
    unknown = sorted(set(by_dir) - known)
    if unknown:
        # 確認後にフォルダが消えた・改名された場合。黙って落とすと意図と違う版になる
        raise ValueError(f"取り込み対象のフォルダが見つかりません: {', '.join(unknown)}")

    folders: list[FolderImportPlan] = []
    for folder in plan.folders:
        confirmed = by_dir.get(folder.dir_name)
        if confirmed is None:
            # 確認していないフォルダを黙って取り込むと、確認画面の内容と違う版になる
            logger.debug(f"確認画面に無いフォルダは取り込みません: {folder.dir_name}")
            folders.append(replace(folder, include=False))
            continue
        trigger = confirmed.trigger_word.strip() if confirmed.trigger_word else ""
        folders.append(
            replace(
                folder,
                include=confirmed.include,
                num_repeats=confirmed.num_repeats,
                trigger_word=trigger or None,
            )
        )
    return replace(plan, folders=folders)


@dataclass(frozen=True)
class VersionCandidate:
    """親フォルダの配下で見つけた版の候補 1 つ分 (Issue #1648)。

    Attributes:
        version_name: 版名の候補。版を表す上位フォルダ名 (親フォルダ直下のフォルダ名)。
            同じ上位フォルダに候補が 2 つ以上ある場合は親フォルダからの相対パス。順番指定の識別子にも使う。
        root: 取り込みのルート (`<数字>_<名前>` フォルダを持つディレクトリ)。
        plan: この版の取り込み計画。`parent_version_id` は取り込み時に順番から決める。
    """

    version_name: str
    root: Path
    plan: DatasetImportPlan


_NATURAL_SPLIT = re.compile(r"(\d+)")


def _natural_key(name: str) -> tuple[tuple[int, int | str], ...]:
    """名前順の比較キー。数字の部分は数として比べる (`v2` < `v10`)。"""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in _NATURAL_SPLIT.split(name)
        if part
    )


def order_version_candidates(
    candidates: list[VersionCandidate], order: list[str]
) -> tuple[list[VersionCandidate], list[VersionCandidate]]:
    """利用者が指定した順番に版の候補を並べる。

    順番を指定しなければ候補の並び (名前順) のまま全部を取り込む。指定した場合は、指定した版だけを
    その順に取り込み、指定に無い版は取り込まない。最新版を自動では決めない (Issue #1648)。

    Args:
        candidates: 名前順に並んだ版の候補。
        order: 取り込む版名の候補を、古い版から順に並べたもの。空なら名前順。

    Returns:
        (取り込む版を順番に並べたもの, 取り込まない版)。

    Raises:
        ValueError: 候補に無い版名や、同じ版名の重複がある場合。
    """
    if not order:
        return list(candidates), []
    by_name = {candidate.version_name: candidate for candidate in candidates}
    duplicated = sorted({name for name in order if order.count(name) > 1})
    if duplicated:
        raise ValueError(f"順番の指定に同じ版が重複しています: {', '.join(duplicated)}")
    unknown = [name for name in order if name not in by_name]
    if unknown:
        raise ValueError(
            f"順番の指定にある版が見つかりません: {', '.join(unknown)} (候補: {', '.join(by_name)})"
        )
    ordered = [by_name[name] for name in order]
    skipped = [candidate for candidate in candidates if candidate.version_name not in order]
    return ordered, skipped


def _version_names(parent: Path, roots: list[Path]) -> list[str]:
    """ルート候補ごとに版名の候補を決める。

    親フォルダ直下のフォルダ名 (`raikou_v06ps/lora_train_data/train_dir` なら `raikou_v06ps`) を使う。
    同じ上位フォルダに候補が 2 つ以上あれば、区別できるよう親フォルダからの相対パスにする。
    """
    tops = [root.relative_to(parent).parts[0] for root in roots]
    return [
        top if tops.count(top) == 1 else root.relative_to(parent).as_posix()
        for top, root in zip(tops, roots, strict=True)
    ]


class EmptyDatasetImportError(ValueError):
    """取り込めるフォルダが 1 つも無い計画を拒否するときの例外。

    Attributes:
        train_data_dir_hints: 設定 json の `train_data_dir` (ルートの候補)。
    """

    def __init__(self, message: str, train_data_dir_hints: list[str]) -> None:
        super().__init__(message)
        self.train_data_dir_hints = train_data_dir_hints
        # CLI のエラー境界が details として表示する
        self.details: dict[str, object] = (
            {"train_data_dir_hints": train_data_dir_hints} if train_data_dir_hints else {}
        )


@dataclass(frozen=True)
class DatasetImportResult:
    """取り込み結果。

    Attributes:
        dataset_id: `datasets.id`。
        version_id: 作成した版の ID。
        folder_count: 取り込んだフォルダ数。
        image_count: フォルダへの所属を記録した画像数 (同じ画像が 2 フォルダにあれば 2 と数える)。
        skipped_images: 画像の登録に失敗し、所属を記録しなかった画像数。
        training_config_ids: 追加した学習設定の ID。
        images_without_text: 取り込んだ画像のうち、学習テキストが無い画像数 (取り込みはする)。
            登録に失敗した画像は数えない。
    """

    dataset_id: int
    version_id: int
    folder_count: int
    image_count: int
    skipped_images: int
    training_config_ids: list[int]
    images_without_text: int = 0


@dataclass(frozen=True)
class _PreparedConfig:
    """書き込み前に読み込み・正規化した設定 json。"""

    path: Path
    normalized: NormalizedConfig


def _read_config_text(path: Path) -> str:
    # Windows で保存された BOM 付き json も読めるようにする
    return path.read_text(encoding="utf-8-sig")


def _detect_configs(root: Path) -> list[_PreparedConfig]:
    """`root` 直下の設定 json を自動検出する。読めない json はスキップする。"""
    prepared: list[_PreparedConfig] = []
    # 設定 json でない json も置かれうるため、読めないものは黙ってスキップする
    for path in sorted(root.glob("*.json"), key=lambda p: p.name):
        if not path.is_file():
            continue
        try:
            normalized = normalize_kohya_gui_config(_read_config_text(path))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            # json.JSONDecodeError は ValueError の派生
            logger.debug(f"設定 json として読めないためスキップ: {path.name}: {type(e).__name__}")
            continue
        prepared.append(_PreparedConfig(path, normalized))
    return prepared


def _detect_configs_up_to(root: Path, version_dir: Path) -> list[_PreparedConfig]:
    """`root` から `version_dir` (版フォルダ) までの各ディレクトリ直下の設定 json を自動検出する。

    `raikou_v06ps/raikou_v06.json` のように、版フォルダ直下に置かれた設定 json も拾う (Issue #1648)。
    """
    directories = [root]
    current = root
    while current != version_dir and version_dir in current.parents:
        current = current.parent
        directories.append(current)
    prepared: list[_PreparedConfig] = []
    for directory in directories:
        prepared.extend(_detect_configs(directory))
    return prepared


def _load_explicit_configs(paths: list[Path]) -> list[_PreparedConfig]:
    """明示指定の設定 json を読む。1 つでも読めなければ拒否する。

    黙って落とすと設定を欠いた版がコミットされるため、自動検出と違いスキップしない。

    Raises:
        FileNotFoundError: 設定 json が存在しない場合。
        ValueError: 設定 json が不正 (json でない・最上位がオブジェクトでない・UTF-8 でない) な場合。
        OSError: 設定 json を読めない場合。
    """
    prepared: list[_PreparedConfig] = []
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"指定された設定 json が見つかりません: {path.name}")
        try:
            normalized = normalize_kohya_gui_config(_read_config_text(path))
        except UnicodeDecodeError as e:
            # UnicodeDecodeError は ValueError の派生だが、原因が分かるよう明示する
            raise ValueError(f"指定された設定 json を UTF-8 として読めません: {path.name}") from e
        except ValueError as e:
            raise ValueError(f"指定された設定 json が不正です: {path.name}") from e
        prepared.append(_PreparedConfig(path, normalized))
    return prepared


def _as_str(value: NormalizedValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _as_int(value: NormalizedValue | None) -> int | None:
    # bool は int の派生だが数値として扱わない
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _as_float(value: NormalizedValue | None) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _to_training_config_spec(prepared: _PreparedConfig) -> TrainingConfigSpec:
    """正規化結果を `TrainingConfigSpec` にする。主要な値は `normalized` から取り出す。"""
    config = prepared.normalized
    normalized = config.normalized
    return TrainingConfigSpec(
        source_kind=CONFIG_SOURCE_KIND,
        source_file_name=prepared.path.name,
        raw_content=config.raw_content,
        normalized_json=json.dumps(normalized, ensure_ascii=False),
        unmapped_json=json.dumps(config.unmapped, ensure_ascii=False),
        target_script=config.target_script,
        output_name=_as_str(normalized.get("output_name")),
        base_model=_as_str(normalized.get("pretrained_model_name_or_path")),
        resolution=_as_str(normalized.get("resolution")),
        network_dim=_as_int(normalized.get("network_dim")),
        network_alpha=_as_float(normalized.get("network_alpha")),
        learning_rate=_as_float(normalized.get("learning_rate")),
    )


def summarize_folder(folder: ScannedFolder) -> FolderScanSummary:
    """スキャン結果を確認用のスキャン情報にまとめる。

    Args:
        folder: スキャンしたフォルダ。

    Returns:
        画像数・学習テキストの無い画像数・トリガーワード候補。
    """
    return FolderScanSummary(
        image_count=len(folder.images),
        images_without_text=sum(1 for image in folder.images if not image.texts),
        trigger_candidate=folder.trigger_candidate,
        trigger_match_rate=folder.trigger_match_rate,
    )


def _train_data_dir_hints(root: Path, prepared: list[_PreparedConfig]) -> list[str]:
    """設定 json の `train_data_dir` のうち、`root` と異なるものを重複なしで返す。"""
    hints: list[str] = []
    for config in prepared:
        value = _as_str(config.normalized.normalized.get("train_data_dir"))
        if not value or value in hints:
            continue
        # 同じ場所を指す値は候補にしない (区切り文字の違いは吸収する)
        if Path(value).as_posix().rstrip("/") == root.as_posix().rstrip("/"):
            continue
        hints.append(value)
    return hints


def _empty_import_error(root: Path, hints: list[str]) -> EmptyDatasetImportError:
    message = f"取り込めるフォルダがありません (<数字>_<名前> のフォルダが無いか、すべて外されています): {root.name}"
    if hints:
        message += (
            f"。設定 json の train_data_dir をルートにすると取り込めるかもしれません: {', '.join(hints)}"
        )
    return EmptyDatasetImportError(message, hints)


def _validate_folders(
    plan: DatasetImportPlan, scanned_by_dir: dict[str, ScannedFolder]
) -> list[tuple[FolderImportPlan, ScannedFolder]]:
    """取り込むフォルダを検証し、計画とスキャン結果の組を計画順に返す。

    Raises:
        DatasetConflictError: 計画に同じフォルダが重複する、またはフォルダ内で `file_stem` が重複する場合。
        ValueError: 計画のフォルダがスキャン結果に無い (存在しない・除外対象) 場合。
    """
    targets: list[tuple[FolderImportPlan, ScannedFolder]] = []
    seen: set[str] = set()
    for folder_plan in plan.folders:
        if not folder_plan.include:
            continue
        if folder_plan.dir_name in seen:
            raise DatasetConflictError(f"計画に同じフォルダが重複しています: '{folder_plan.dir_name}'")
        seen.add(folder_plan.dir_name)
        scanned = scanned_by_dir.get(folder_plan.dir_name)
        if scanned is None:
            raise ValueError(f"取り込み対象のフォルダが見つかりません: '{folder_plan.dir_name}'")
        stems = [image.file_stem for image in scanned.images]
        if len(stems) != len(set(stems)):
            raise DatasetConflictError(
                f"フォルダ内に同じ名前 (拡張子違い) の画像があります: '{folder_plan.dir_name}'"
            )
        targets.append((folder_plan, scanned))
    return targets


def _build_plan(
    root: Path, dataset_name: str, version_name: str, prepared: list[_PreparedConfig]
) -> DatasetImportPlan:
    """スキャン結果と設定 json から取り込み計画を作る。トリガーワードは確定しない。"""
    folders = [
        FolderImportPlan(
            dir_name=folder.dir_name,
            name=folder.name,
            num_repeats=folder.num_repeats,
            trigger_word=None,
            include=True,
            scan=summarize_folder(folder),
        )
        for folder in scan_kohya_directory(root)
    ]
    return DatasetImportPlan(
        dataset_name=dataset_name,
        version_name=version_name,
        parent_version_id=None,
        folders=folders,
        config_files=[config.path for config in prepared],
        train_data_dir_hints=_train_data_dir_hints(root, prepared),
    )


class DatasetImportService:
    """Kohya 形式のディレクトリを、データセットの版として取り込む service (Qt-free)。"""

    def __init__(
        self,
        db_manager: ImageDatabaseManager,
        repository: DatasetRepository,
        fsm: FileSystemManager,
    ) -> None:
        """service を初期化する。

        Args:
            db_manager: 画像の登録に使う DB マネージャ。
            repository: データセットの Repository。
            fsm: 画像の保存先を管理する FileSystemManager (初期化済みであること)。
        """
        self._db_manager = db_manager
        self._repository = repository
        self._fsm = fsm

    def propose_plan(
        self,
        root: Path,
        dataset_name: str,
        version_name: str,
        explicit_config_files: list[Path] | None = None,
    ) -> DatasetImportPlan:
        """スキャン結果から取り込み計画の候補を作る。DB には何も書かない。

        トリガーワードはスキャンの候補を確定値にしないため `None` とし、候補は各フォルダの
        `scan` (画像数・学習テキストの無い画像数と合わせて) に載せる。版名は、
        `version_name` が空なら `root` 直下の設定 json の `output_name` を候補にし、
        それも無ければ `root` のフォルダ名を使う。

        Args:
            root: Kohya 形式のルートディレクトリ。
            dataset_name: データセット名。
            version_name: 版名。空文字なら候補を作る。
            explicit_config_files: 設定 json を明示する場合のパス。`None` なら `root` 直下を自動検出する。
                自動検出では読めない json をスキップするが、明示指定は 1 つでも読めなければ拒否する。

        Returns:
            確認前の取り込み計画。

        Raises:
            FileNotFoundError: 明示指定の設定 json が存在しない場合。
            ValueError: 明示指定の設定 json が不正 (json でない・UTF-8 でない等) な場合。
            OSError: 明示指定の設定 json を読めない場合。
        """
        prepared = (
            _detect_configs(root)
            if explicit_config_files is None
            else _load_explicit_configs(explicit_config_files)
        )
        output_names = [
            config.normalized.output_name for config in prepared if config.normalized.output_name
        ]

        proposed_version = version_name.strip()
        if not proposed_version:
            proposed_version = output_names[0] if output_names else root.name
        return _build_plan(root, dataset_name, proposed_version, prepared)

    def discover_versions(
        self,
        parent: Path,
        dataset_name: str,
        exclude_patterns: tuple[str, ...] = (),
        max_depth: int = DEFAULT_DISCOVERY_MAX_DEPTH,
    ) -> list[VersionCandidate]:
        """親フォルダの配下から版の候補を探し、版ごとの取り込み計画を作る。DB には何も書かない。

        版名の候補は版を表す上位フォルダ名から出し、名前順 (数字は数として比較) に並べる。
        名前順は初期値にすぎず、最新版や順番は自動で確定しない (Issue #1648)。

        Args:
            parent: 探索の起点 (版のフォルダを含む親フォルダ)。
            dataset_name: データセット名。
            exclude_patterns: 既定の除外に加えて、探索で潜らないフォルダ名の fnmatch パターン。
            max_depth: 探索する深さの上限。

        Returns:
            名前順に並べた版の候補。`parent` 自身が取り込みのルートなら空 (従来の取り込みを使う)。
        """
        # 親フォルダ自身が取り込みのルートなら、追加の除外に関係なく従来の取り込みとする
        if discover_kohya_roots(parent, DEFAULT_EXCLUDE_PATTERNS, max_depth=0):
            return []
        roots = discover_kohya_roots(parent, DEFAULT_EXCLUDE_PATTERNS + exclude_patterns, max_depth)
        # 学習フォルダがシンボリックリンクだけのルートは、版が見つからなければ従来の取り込みとする
        if not roots and has_kohya_folder(parent, DEFAULT_EXCLUDE_PATTERNS, include_symlinks=True):
            return []
        candidates: list[VersionCandidate] = []
        for root, name in zip(roots, _version_names(parent, roots), strict=True):
            version_dir = parent / root.relative_to(parent).parts[0]
            prepared = _detect_configs_up_to(root, version_dir)
            candidates.append(VersionCandidate(name, root, _build_plan(root, dataset_name, name, prepared)))
        candidates.sort(key=lambda candidate: _natural_key(candidate.version_name))
        logger.info(f"版の候補の探索: {len(candidates)}件 ({parent})")
        return candidates

    def import_versions(
        self, candidates: list[VersionCandidate], parent_version_id: int | None = None
    ) -> list[DatasetImportResult]:
        """版の候補を、並び順に 1 版ずつ取り込む。各版の親の版は 1 つ前の版にする。

        書き込みの前に、同じデータセットに同名の版が無いことと、各版に取り込むフォルダが
        あることを確かめる。

        Args:
            candidates: 取り込む順 (古い版から) に並べた版の候補。
            parent_version_id: 先頭の版の親の版 ID。

        Returns:
            版ごとの取り込み結果 (取り込んだ順)。

        Raises:
            DatasetConflictError: 同じデータセットに同名の版がある、または版名が重複する場合。
            EmptyDatasetImportError: 取り込むフォルダが 1 つも無い版がある場合 (何も書かない)。
        """
        names = [candidate.plan.version_name for candidate in candidates]
        if len(names) != len(set(names)):
            raise DatasetConflictError(f"取り込む版の名前が重複しています: {', '.join(names)}")
        for candidate in candidates:
            if not candidate.plan.included_folders:
                raise _empty_import_error(candidate.root, candidate.plan.train_data_dir_hints)
        dataset_names = {candidate.plan.dataset_name for candidate in candidates}
        existing = sorted(
            summary.version_name
            for summary in self._repository.list_versions()
            if summary.dataset_name in dataset_names and summary.version_name in names
        )
        if existing:
            raise DatasetConflictError(f"同じデータセットに同名の版が既にあります: {', '.join(existing)}")

        results: list[DatasetImportResult] = []
        previous = parent_version_id
        for candidate in candidates:
            result = self.import_directory(
                candidate.root, replace(candidate.plan, parent_version_id=previous)
            )
            results.append(result)
            previous = result.version_id
        logger.info(f"版の取り込み完了: {len(results)}版")
        return results

    def import_directory(self, root: Path, plan: DatasetImportPlan) -> DatasetImportResult:
        """計画に従ってディレクトリを取り込み、新しい版を作る。

        書き込み前に計画の検証と設定 json の正規化を済ませ、版の作成で衝突した場合は
        何も書かない。フォルダは 1 つずつ 1 トランザクションで追加する。

        Args:
            root: Kohya 形式のルートディレクトリ。
            plan: 確認済みの取り込み計画。

        Returns:
            取り込み結果。

        Raises:
            DatasetConflictError: 同じデータセットに同名の版がある、計画に同じフォルダが重複する、
                フォルダ内で画像名が重複する場合。
            EmptyDatasetImportError: 取り込むフォルダが 1 つも無い場合 (空の版は作らない)。
            ValueError: 計画のフォルダがスキャン結果に無い、または設定 json が読めない場合。
            OSError: 設定 json を読めない場合。
        """
        scanned_by_dir = {folder.dir_name: folder for folder in scan_kohya_directory(root)}
        targets = _validate_folders(plan, scanned_by_dir)
        prepared_configs = [
            _PreparedConfig(path, normalize_kohya_gui_config(_read_config_text(path)))
            for path in plan.config_files
        ]
        if not targets:
            raise _empty_import_error(root, _train_data_dir_hints(root, prepared_configs))

        logger.info(
            f"データセット取り込み開始: {root} (dataset='{plan.dataset_name}', "
            f"version='{plan.version_name}', folders={len(targets)})"
        )
        dataset_id = self._repository.ensure_dataset(plan.dataset_name)
        version_id = self._repository.create_version(dataset_id, plan.version_name, plan.parent_version_id)

        image_count = 0
        skipped_images = 0
        images_without_text = 0
        for position, (folder_plan, scanned) in enumerate(targets):
            images: list[FolderImageSpec] = []
            for scanned_image in scanned.images:
                registered = self._db_manager.register_original_image(scanned_image.path, self._fsm)
                if registered is None:
                    skipped_images += 1
                    logger.debug(f"画像を登録できないため所属を記録しません: {scanned_image.path}")
                    continue
                # 登録できた画像だけを数える (スキャン時の件数は計画の scan に載っている)
                if not scanned_image.texts:
                    images_without_text += 1
                images.append(
                    FolderImageSpec(
                        image_id=registered[0],
                        file_stem=scanned_image.file_stem,
                        texts=[
                            LearningTextSpec(text.extension, text.raw_text, list(text.elements))
                            for text in scanned_image.texts
                        ],
                    )
                )
            spec = FolderSpec(
                dir_name=folder_plan.dir_name,
                name=folder_plan.name,
                num_repeats=folder_plan.num_repeats,
                trigger_word=folder_plan.trigger_word,
                position=position,
            )
            self._repository.add_folder(version_id, spec, images)
            image_count += len(images)

        training_config_ids = [
            self._repository.add_training_config(dataset_id, version_id, _to_training_config_spec(prepared))
            for prepared in prepared_configs
        ]

        logger.info(
            f"データセット取り込み完了: version_id={version_id}, folders={len(targets)}, "
            f"images={image_count}, skipped={skipped_images}, without_text={images_without_text}, "
            f"configs={len(training_config_ids)}"
        )
        return DatasetImportResult(
            dataset_id=dataset_id,
            version_id=version_id,
            folder_count=len(targets),
            image_count=image_count,
            skipped_images=skipped_images,
            training_config_ids=training_config_ids,
            images_without_text=images_without_text,
        )
