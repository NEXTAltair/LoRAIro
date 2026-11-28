"""複数プロジェクトを、画像・タグ・データセットの版履歴ごと 1 つのプロジェクトへ統合する service。

ADR 0113 (Issue #1660)。Qt 非依存。ADR 0112 (#1661) のコピー処理と由来の記録を再利用する。

- 統合元は読み取り専用で開き、一切変更しない。統合先が統合元のどれかと同じなら拒否する。
- 画像は `ProjectTransferService.stage_images` で統合先のセッションに足す。同じ画像 (ADR 0061 の
  DUPLICATE) は 1 枚にまとめ、タグ・アノテーションは和集合にする。各版はまとめた 1 枚を指す。
- データセット・版は統合元ごとに複製し、版の由来を `dataset_version_origins` に記録する。
  同名のデータセット・版、作業中の版が 2 つ以上になるデータセットは衝突として計画に示し、
  利用者が名前の対応 (`MergeMapping`) を指定して解消するまで確定しない。
- 同じデータセットの版を 1 つの履歴にまとめる指定 (join) では、前の要素の最新版を次の要素の
  最初の版の parent にする。
- 統合先には 1 セッション 1 commit で書く。ファイルは staging に置いてから最終パスへ移し、
  途中で失敗したら rollback して、置いたファイルと作ったディレクトリを消す。
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, selectinload

from lorairo.database.db_core import IMG_DB_FILENAME, create_project_session_factory
from lorairo.database.repository.dataset import DatasetRepository
from lorairo.database.schema import (
    TRANSFER_KIND_MERGE_PROJECT,
    Dataset,
    DatasetFolder,
    DatasetFolderImage,
    DatasetLearningText,
    DatasetVersion,
    DatasetVersionOrigin,
    Image,
    TrainingConfig,
)
from lorairo.services import project_transfer_service as transfer
from lorairo.services.project_transfer_service import (
    ImageTransferItem,
    ProjectTransferService,
    SourceProject,
    open_read_only_project,
)
from lorairo.utils.log import logger

__all__ = [
    "ConflictKind",
    "MergeConflict",
    "MergeMapping",
    "MergeMappingError",
    "MergePlan",
    "MergeResult",
    "MergedDuplicate",
    "PlannedParent",
    "PlannedVersion",
    "ProjectMergeService",
    "SourceDatasetRef",
    "SourceImageSummary",
    "SourceVersionRef",
    "UnresolvedMergeConflictError",
]

_STAGING_DIR_NAME = ".transfer_staging"
_TARGET_LABEL = "(target)"

ConflictKind = Literal["dataset_name", "dataset_exists", "version_name", "multiple_working_versions"]
"""衝突の種類。

- ``dataset_name``: 複数の統合元のデータセットが、履歴をまとめる指定なしに同じ名前になる
- ``dataset_exists``: 統合先に同じ名前のデータセットが既にある (履歴をまとめる指定がない)
- ``version_name``: 1 つのデータセットの中で、同じ名前の版が 2 つ以上になる
- ``multiple_working_versions``: 1 つのデータセットの中で、作業中の版が 2 つ以上になる
"""


class MergeMappingError(ValueError):
    """名前の対応の指定が不正 (存在しない統合元・データセット・版を指す、指定が矛盾する) な場合の例外。"""


@dataclass(frozen=True)
class SourceDatasetRef:
    """統合元のデータセット (プロジェクト名 + データセット名)。"""

    project: str
    dataset: str

    @property
    def label(self) -> str:
        """表示と CLI 指定に使う `プロジェクト:データセット`。"""
        return f"{self.project}:{self.dataset}"


@dataclass(frozen=True)
class SourceVersionRef:
    """統合元の版 (プロジェクト名 + データセット名 + 版の名前)。"""

    project: str
    dataset: str
    version: str

    @property
    def label(self) -> str:
        """表示と CLI 指定に使う `プロジェクト:データセット/版`。"""
        return f"{self.project}:{self.dataset}/{self.version}"


@dataclass(frozen=True)
class MergeMapping:
    """名前の対応の指定。

    Attributes:
        dataset_names: 統合元のデータセット → 統合先のデータセット名。指定が無ければ同じ名前。
        version_names: 統合元の版 → 統合先の版の名前。指定が無ければ同じ名前。
        joins: 統合先のデータセット名 → 1 つの履歴にまとめる統合元のデータセット (この順に連ねる)。
            統合先に同じ名前のデータセットが既にあれば、その履歴を先頭にする。
    """

    dataset_names: Mapping[SourceDatasetRef, str] = field(default_factory=dict)
    version_names: Mapping[SourceVersionRef, str] = field(default_factory=dict)
    joins: Mapping[str, Sequence[SourceDatasetRef]] = field(default_factory=dict)

    def updated(self, other: MergeMapping) -> MergeMapping:
        """`other` の指定で上書き・追加した対応を返す (CLI の指定を mapping ファイルより優先する)。"""
        return MergeMapping(
            dataset_names={**self.dataset_names, **other.dataset_names},
            version_names={**self.version_names, **other.version_names},
            joins={**self.joins, **other.joins},
        )

    @classmethod
    def from_json_dict(cls, data: object) -> MergeMapping:
        """`MergePlan.mapping_template()` と同じ形の dict から対応を作る。

        Args:
            data: `{"datasets": [...], "versions": [...], "joins": [...]}`。どのキーも省略できる。

        Returns:
            名前の対応。統合元と同じ名前を指す項目は指定なしと同じ。

        Raises:
            MergeMappingError: 形が不正な場合。
        """
        if not isinstance(data, dict):
            raise MergeMappingError("mapping はオブジェクト (datasets / versions / joins) にしてください")
        dataset_names: dict[SourceDatasetRef, str] = {}
        for entry in _entries(data, "datasets"):
            ref = SourceDatasetRef(_text(entry, "source_project"), _text(entry, "source_dataset"))
            dataset_names[ref] = _text(entry, "target_dataset")
        version_names: dict[SourceVersionRef, str] = {}
        for entry in _entries(data, "versions"):
            version_ref = SourceVersionRef(
                _text(entry, "source_project"),
                _text(entry, "source_dataset"),
                _text(entry, "source_version"),
            )
            version_names[version_ref] = _text(entry, "target_version")
        joins: dict[str, list[SourceDatasetRef]] = {}
        for entry in _entries(data, "joins"):
            sources = _entries(entry, "sources")
            if not sources:
                raise MergeMappingError("joins の sources は空でない配列にしてください")
            joins[_text(entry, "target_dataset")] = [
                SourceDatasetRef(_text(item, "source_project"), _text(item, "source_dataset"))
                for item in sources
            ]
        return cls(dataset_names=dataset_names, version_names=version_names, joins=joins)


def _entries(data: dict[object, object], key: str) -> list[dict[object, object]]:
    raw = data.get(key, [])
    if not isinstance(raw, list):
        raise MergeMappingError(f"mapping の {key} は配列にしてください")
    entries: list[dict[object, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise MergeMappingError(f"mapping の {key} の各項目はオブジェクトにしてください")
        entries.append(item)
    return entries


def _text(entry: dict[object, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MergeMappingError(f"mapping の {key} は空でない文字列にしてください")
    return value.strip()


@dataclass(frozen=True)
class MergeConflict:
    """未解決の衝突 1 件。

    Attributes:
        kind: 衝突の種類 (`ConflictKind`)。
        target_dataset: 衝突が起きる統合先のデータセット名。
        target_version: 版の衝突なら統合先の版の名前。データセットの衝突なら None。
        sources: 衝突している統合元 (`プロジェクト:データセット[/版]`)。統合先の既存のものは `(target)`。
        message: 衝突の説明と解消のしかた。
    """

    kind: ConflictKind
    target_dataset: str
    target_version: str | None
    sources: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class PlannedParent:
    """計画した版の parent。

    Attributes:
        source_project: parent の版がある統合元。統合先に既にある版なら None。
        dataset: parent の版のデータセット名 (統合元の名前、または統合先の名前)。
        version: parent の版の名前。
        version_id: 統合元の DB での版 ID (統合先に既にある版なら統合先の版 ID)。
    """

    source_project: str | None
    dataset: str
    version: str
    version_id: int


@dataclass(frozen=True)
class PlannedVersion:
    """統合する版 1 つの計画。

    Attributes:
        source: 統合元の版。
        source_version_id: 統合元の DB での版 ID。
        target_dataset: 統合先のデータセット名。
        target_version: 統合先の版の名前。
        is_working: 作業中の版か (統合元のまま引き継ぐ)。
        parent: 統合先での parent。無ければ None。
        joined_parent: parent が履歴をまとめる指定で付いたものなら True。
        image_count: 版のフォルダに属する画像の数 (フォルダごとの所属数の合計)。
    """

    source: SourceVersionRef
    source_version_id: int
    target_dataset: str
    target_version: str
    is_working: bool
    parent: PlannedParent | None
    joined_parent: bool
    image_count: int


@dataclass(frozen=True)
class SourceImageSummary:
    """統合元 1 つ分の画像の扱いの集計。"""

    source_project: str
    images: int
    copy: int
    link: int
    already_linked: int


@dataclass(frozen=True)
class MergedDuplicate:
    """ハッシュ一致で別の画像にまとめる画像 1 枚。

    Attributes:
        source_project: まとめられる画像の統合元。
        source_image_id: まとめられる画像の統合元での ID。
        source_uuid: まとめられる画像の uuid。
        merged_into_project: まとめ先の画像の統合元。統合先に既にある画像なら None。
        merged_into_image_id: まとめ先の画像 ID (統合元の ID、または統合先の ID)。
    """

    source_project: str
    source_image_id: int
    source_uuid: str
    merged_into_project: str | None
    merged_into_image_id: int


@dataclass(frozen=True)
class MergePlan:
    """統合の計画。

    Attributes:
        target_project: 統合先のプロジェクト名。
        source_projects: 統合元のプロジェクト名 (指定順)。
        images: 統合元ごとの画像の扱いの集計。
        duplicates: ハッシュ一致で 1 枚にまとめる画像。
        versions: 統合する版 (統合先のデータセットごと、履歴の順)。
        conflicts: 未解決の衝突。空なら確定できる。
        mapping: 計画に使った名前の対応。
    """

    target_project: str
    source_projects: tuple[str, ...]
    images: tuple[SourceImageSummary, ...]
    duplicates: tuple[MergedDuplicate, ...]
    versions: tuple[PlannedVersion, ...]
    conflicts: tuple[MergeConflict, ...]
    mapping: MergeMapping

    @property
    def is_resolved(self) -> bool:
        """未解決の衝突が無ければ True。"""
        return not self.conflicts

    @property
    def image_count(self) -> int:
        """統合元の画像の合計枚数。"""
        return sum(summary.images for summary in self.images)

    def mapping_template(self) -> dict[str, list[dict[str, object]]]:
        """名前の対応のひな形 (`MergeMapping.from_json_dict` が読む形) を返す。

        いまの計画の名前をそのまま埋める。衝突している名前を書き換えて mapping ファイルにする。
        """
        datasets: dict[SourceDatasetRef, str] = {}
        for version in self.versions:
            datasets.setdefault(
                SourceDatasetRef(version.source.project, version.source.dataset), version.target_dataset
            )
        return {
            "datasets": [
                {"source_project": ref.project, "source_dataset": ref.dataset, "target_dataset": name}
                for ref, name in datasets.items()
            ],
            "versions": [
                {
                    "source_project": version.source.project,
                    "source_dataset": version.source.dataset,
                    "source_version": version.source.version,
                    "target_version": version.target_version,
                }
                for version in self.versions
            ],
            "joins": [
                {
                    "target_dataset": name,
                    "sources": [
                        {"source_project": ref.project, "source_dataset": ref.dataset} for ref in refs
                    ],
                }
                for name, refs in self.mapping.joins.items()
            ],
        }


@dataclass(frozen=True)
class MergeResult:
    """確定した統合の結果。

    Attributes:
        plan: 確定した計画 (衝突なし)。
        transfer_run_ids: 統合元のプロジェクト名 → 記録した `project_transfer_runs.id`。
        version_ids: 統合元の版 → 統合先の版 ID。
        image_ids: (統合元のプロジェクト名, 統合元の画像 ID) → 統合先の画像 ID。
        tags_added: 版の取り込み後のタグ同期 (ADR 0104) で足した行数。
        tags_removed: 同じく消した行数。
    """

    plan: MergePlan
    transfer_run_ids: dict[str, int]
    version_ids: dict[SourceVersionRef, int]
    image_ids: dict[tuple[str, int], int]
    tags_added: int
    tags_removed: int


class UnresolvedMergeConflictError(ValueError):
    """衝突が未解決のまま確定しようとした場合の例外。`conflicts` と `details` に衝突を持つ。"""

    def __init__(self, conflicts: Sequence[MergeConflict]) -> None:
        self.conflicts = tuple(conflicts)
        self.details: dict[str, object] = {
            "conflicts": [
                {
                    "kind": conflict.kind,
                    "target_dataset": conflict.target_dataset,
                    "target_version": conflict.target_version,
                    "sources": list(conflict.sources),
                }
                for conflict in self.conflicts
            ]
        }
        super().__init__(
            f"未解決の衝突が {len(self.conflicts)} 件あるため統合を確定できません。"
            "計画 (--confirm なし) で衝突を確かめ、名前の対応を指定してください"
        )


# --- 統合元・統合先のデータセットの読み込み結果 (セッションに依存しない値) ---


@dataclass(frozen=True)
class _SourceText:
    extension: str
    raw_text: str
    elements_json: str
    is_edited: bool


@dataclass(frozen=True)
class _SourceFolderImage:
    image_id: int
    file_stem: str
    texts: tuple[_SourceText, ...]


@dataclass(frozen=True)
class _SourceFolder:
    dir_name: str
    name: str
    num_repeats: int
    trigger_word: str | None
    position: int
    images: tuple[_SourceFolderImage, ...]


@dataclass(frozen=True)
class _VersionNode:
    """版の親子関係の判定に使う値 (統合元・統合先の共通)。"""

    id: int
    name: str
    parent_version_id: int | None
    is_working: bool


@dataclass(frozen=True)
class _SourceVersion:
    node: _VersionNode
    folders: tuple[_SourceFolder, ...]

    @property
    def image_count(self) -> int:
        return sum(len(folder.images) for folder in self.folders)


@dataclass(frozen=True)
class _SourceConfig:
    version_id: int | None
    values: dict[str, str | int | float | None]


@dataclass(frozen=True)
class _SourceDataset:
    ref: SourceDatasetRef
    description: str | None
    versions: tuple[_SourceVersion, ...]
    configs: tuple[_SourceConfig, ...]


@dataclass(frozen=True)
class _TargetDataset:
    id: int
    name: str
    versions: tuple[_VersionNode, ...]


_CONFIG_COLUMNS = (
    "source_kind",
    "source_file_name",
    "raw_content",
    "normalized_json",
    "unmapped_json",
    "target_script",
    "output_name",
    "base_model",
    "resolution",
    "network_dim",
    "network_alpha",
    "learning_rate",
)


@dataclass
class _DatasetGroup:
    """統合先のデータセット 1 つにまとまる統合元のデータセット (履歴の順)。"""

    target_name: str
    elements: list[_SourceDataset]
    joined: bool
    existing: _TargetDataset | None


@dataclass
class _DatasetPlan:
    groups: list[_DatasetGroup]
    versions: list[PlannedVersion]
    conflicts: list[MergeConflict]


def _latest_version_id(nodes: Sequence[_VersionNode]) -> int | None:
    """`DatasetRepository._latest_version_ids` と同じ規則で、データセットの最新版の ID を返す。

    確定済みの版のうち、他の確定済みの版の parent に指されていない版で、ID が最大のもの。
    """
    finalized = {node.id for node in nodes if not node.is_working}
    referenced = {
        node.parent_version_id
        for node in nodes
        if not node.is_working and node.parent_version_id in finalized
    }
    leaves = [node_id for node_id in finalized if node_id not in referenced]
    return max(leaves) if leaves else None


def _first_root_id(nodes: Sequence[_VersionNode]) -> int | None:
    """データセットの最初の版 (同じデータセットに parent が無い版のうち ID が最小のもの) の ID。"""
    ids = {node.id for node in nodes}
    roots = [node.id for node in nodes if node.parent_version_id not in ids]
    return min(roots) if roots else None


class ProjectMergeService:
    """複数プロジェクト (統合元) を 1 つのプロジェクト (統合先) へ統合する service。"""

    def __init__(
        self,
        target_session_factory: Callable[[], Session],
        target_root: Path,
        target_project_name: str,
    ) -> None:
        """service を初期化する。

        Args:
            target_session_factory: 統合先の DB のセッションファクトリ (書き込み可)。
            target_root: 統合先のプロジェクトディレクトリ。
            target_project_name: 統合先のプロジェクト名。
        """
        self._target_session_factory = target_session_factory
        self._target_root = target_root.resolve()
        self._target_project_name = target_project_name
        self._transfer = ProjectTransferService(target_session_factory, target_root, target_project_name)
        self._datasets = DatasetRepository(session_factory=target_session_factory)

    @classmethod
    def plan_into_new_project(
        cls, sources: Sequence[SourceProject], mapping: MergeMapping, project_name: str
    ) -> MergePlan:
        """まだ無いプロジェクトへ統合する計画を作る。何も残さない。

        空のプロジェクト DB を一時ディレクトリに作って計画し、終わったら消す。

        Args:
            sources: 統合元のプロジェクト (この順に統合する)。
            mapping: 名前の対応。
            project_name: 作る予定の統合先のプロジェクト名。

        Returns:
            統合の計画。
        """
        with tempfile.TemporaryDirectory(prefix="lorairo_merge_plan_") as temp_dir:
            root = Path(temp_dir) / "project"
            factory = create_project_session_factory(root / IMG_DB_FILENAME)
            try:
                return cls(factory, root, project_name).plan(sources, mapping)
            finally:
                engine = factory.kw.get("bind")
                if isinstance(engine, Engine):
                    engine.dispose()

    def plan(self, sources: Sequence[SourceProject], mapping: MergeMapping | None = None) -> MergePlan:
        """統合の計画を作る。統合先のセッションで同じ判定を行ってから rollback し、何も書かない。

        Args:
            sources: 統合元のプロジェクト (この順に統合する。ハッシュ一致の画像は先の統合元にまとめる)。
            mapping: 名前の対応。省略時は指定なし。

        Returns:
            画像の扱い・ハッシュ一致でまとめる画像・版の対応・未解決の衝突。

        Raises:
            ValueError: 統合元が空・重複する、または統合先と同じ場合。
            MergeMappingError: 名前の対応が不正な場合。
            ReadOnlyPreconditionError: 統合元の DB を開けない (schema が head でない等) 場合。
            FileNotFoundError: 統合元の画像ファイルが見つからない場合。
        """
        plan, _ = self._run(sources, mapping or MergeMapping(), apply=False)
        return plan

    def apply(self, sources: Sequence[SourceProject], mapping: MergeMapping | None = None) -> MergeResult:
        """計画どおりに統合し、1 回だけ commit する。衝突が残っていれば何も書かずに拒否する。

        Args:
            sources: 統合元のプロジェクト。
            mapping: 名前の対応。

        Returns:
            確定した計画と、統合元の版・画像に対応する統合先の ID。

        Raises:
            UnresolvedMergeConflictError: 未解決の衝突がある場合 (何も書かない)。
            ValueError / MergeMappingError / ReadOnlyPreconditionError / FileNotFoundError: `plan` と同じ。
            SQLAlchemyError / OSError: 統合先への書き込みに失敗した場合 (何も残さない)。
        """
        _, result = self._run(sources, mapping or MergeMapping(), apply=True)
        if result is None:
            raise RuntimeError("統合の結果がありません")
        return result

    # --- 本体 ---

    def _validate_sources(self, sources: Sequence[SourceProject]) -> None:
        if not sources:
            raise ValueError("統合元のプロジェクトを 1 つ以上指定してください")
        names = [source.name for source in sources]
        if len(set(names)) != len(names):
            raise ValueError(f"統合元のプロジェクトが重複しています: {', '.join(names)}")
        roots = [source.root.resolve() for source in sources]
        if len(set(roots)) != len(roots):
            raise ValueError("同じディレクトリのプロジェクトが統合元に 2 回以上含まれています")
        for source, root in zip(sources, roots, strict=True):
            if root == self._target_root or source.name == self._target_project_name:
                raise ValueError(f"統合先と同じプロジェクトは統合元にできません: {source.name}")

    def _run(
        self, sources: Sequence[SourceProject], mapping: MergeMapping, *, apply: bool
    ) -> tuple[MergePlan, MergeResult | None]:
        self._validate_sources(sources)
        logger.info(
            f"プロジェクトの統合を開始: target='{self._target_project_name}', "
            f"sources={[source.name for source in sources]}, apply={apply}"
        )
        staging_root = self._target_root / "image_dataset" / _STAGING_DIR_NAME / uuid.uuid4().hex
        with ExitStack() as stack:
            source_sessions: dict[str, Session] = {}
            for source in sources:
                factory = stack.enter_context(open_read_only_project(source))
                source_sessions[source.name] = stack.enter_context(factory())
            source_datasets = [
                dataset
                for source in sources
                for dataset in _load_source_datasets(source_sessions[source.name], source.name)
            ]
            with self._target_session_factory() as session:
                dataset_plan = _plan_datasets(
                    source_datasets, mapping, _load_target_datasets(session), [s.name for s in sources]
                )
                if apply and dataset_plan.conflicts:
                    raise UnresolvedMergeConflictError(dataset_plan.conflicts)
                contexts, items = self._stage_all_images(session, sources, source_sessions, staging_root)
                plan = _build_plan(self._target_project_name, sources, items, dataset_plan, mapping)
                if not apply:
                    session.rollback()
                    logger.info(
                        f"プロジェクトの統合の計画: target='{self._target_project_name}', "
                        f"images={plan.image_count}, duplicates={len(plan.duplicates)}, "
                        f"versions={len(plan.versions)}, conflicts={len(plan.conflicts)}"
                    )
                    return plan, None
                version_ids, image_ids, tags_added, tags_removed = self._stage_datasets(
                    session, plan, dataset_plan, contexts, items
                )
                result = MergeResult(
                    plan=plan,
                    transfer_run_ids={name: context.run.id for name, context in contexts.items()},
                    version_ids=version_ids,
                    image_ids=image_ids,
                    tags_added=tags_added,
                    tags_removed=tags_removed,
                )
                _write_files_and_commit(session, list(contexts.values()), staging_root)
        logger.info(
            f"プロジェクトの統合が完了: target='{self._target_project_name}', images={plan.image_count}, "
            f"duplicates={len(plan.duplicates)}, versions={len(result.version_ids)}"
        )
        return plan, result

    def _stage_all_images(
        self,
        session: Session,
        sources: Sequence[SourceProject],
        source_sessions: dict[str, Session],
        staging_root: Path,
    ) -> tuple[dict[str, transfer._StageContext], dict[str, list[ImageTransferItem]]]:
        """統合元ごとに全画像を統合先のセッションへ足す (commit もファイル操作もしない)。"""
        contexts: dict[str, transfer._StageContext] = {}
        items: dict[str, list[ImageTransferItem]] = {}
        for index, source in enumerate(sources):
            source_session = source_sessions[source.name]
            image_ids = list(source_session.execute(select(Image.id).order_by(Image.id)).scalars())
            images = ProjectTransferService._load_source_images(source_session, image_ids)
            metadata = ProjectTransferService._load_generation_metadata(source_session, image_ids)
            context, staged = self._transfer.stage_images(
                session, source, images, metadata, staging_dir=staging_root / f"{index:03d}"
            )
            # 統合で取り込んだことを記録する (stage_images は画像のコピーとして記録を作る)
            context.run.kind = TRANSFER_KIND_MERGE_PROJECT
            contexts[source.name] = context
            items[source.name] = staged
        session.flush()
        return contexts, items

    def _stage_datasets(
        self,
        session: Session,
        plan: MergePlan,
        dataset_plan: _DatasetPlan,
        contexts: dict[str, transfer._StageContext],
        items: dict[str, list[ImageTransferItem]],
    ) -> tuple[dict[SourceVersionRef, int], dict[tuple[str, int], int], int, int]:
        """データセット・版・フォルダ・学習テキスト・学習設定・版の由来を統合先のセッションに足す。

        commit もファイル操作もしない。最後に、足したデータセットの `KOHYA_DATASET` のタグを
        最新版へ同期する (ADR 0104)。

        Returns:
            (統合元の版 → 統合先の版 ID, 統合元の画像 → 統合先の画像 ID, 足したタグ数, 消したタグ数)。
        """
        image_ids = {
            (project, item.source_image_id): item.target_image_id
            for project, project_items in items.items()
            for item in project_items
            if item.target_image_id is not None
        }
        planned = {
            (version.source.project, version.source_version_id): version for version in plan.versions
        }
        version_ids: dict[tuple[str, int], int] = {}
        new_versions: list[tuple[DatasetVersion, PlannedVersion]] = []
        dataset_ids: list[int] = []
        for group in dataset_plan.groups:
            dataset_id = self._ensure_dataset(session, group)
            dataset_ids.append(dataset_id)
            for element in group.elements:
                project = element.ref.project
                element_versions: list[tuple[DatasetVersion, PlannedVersion]] = []
                for source_version in element.versions:
                    planned_version = planned[(project, source_version.node.id)]
                    version = DatasetVersion(
                        dataset_id=dataset_id,
                        name=planned_version.target_version,
                        is_working=source_version.node.is_working,
                    )
                    version.folders = [
                        _copy_folder(folder, project, image_ids) for folder in source_version.folders
                    ]
                    session.add(version)
                    element_versions.append((version, planned_version))
                # 版の ID を確定させてから、parent・由来・学習設定を付ける
                session.flush()
                for version, planned_version in element_versions:
                    version_ids[(project, planned_version.source_version_id)] = version.id
                new_versions.extend(element_versions)
                for config in element.configs:
                    session.add(
                        TrainingConfig(
                            dataset_id=dataset_id,
                            version_id=(
                                version_ids.get((project, config.version_id))
                                if config.version_id is not None
                                else None
                            ),
                            **config.values,
                        )
                    )
        for version, planned_version in new_versions:
            version.parent_version_id = _resolve_parent(planned_version.parent, version_ids)
            session.add(
                DatasetVersionOrigin(
                    version_id=version.id,
                    transfer_run_id=contexts[planned_version.source.project].run.id,
                    source_project_name=planned_version.source.project,
                    source_dataset_name=planned_version.source.dataset,
                    source_version_id=planned_version.source_version_id,
                    source_version_name=planned_version.source.version,
                )
            )
        session.flush()
        tags_added = tags_removed = 0
        for dataset_id in dataset_ids:
            synced = self._datasets.sync_kohya_tags_in_session(session, dataset_id)
            tags_added += synced.tags_added
            tags_removed += synced.tags_removed
        by_source = {planned_version.source: version.id for version, planned_version in new_versions}
        return by_source, image_ids, tags_added, tags_removed

    @staticmethod
    def _ensure_dataset(session: Session, group: _DatasetGroup) -> int:
        if group.existing is not None:
            return group.existing.id
        first = group.elements[0]
        dataset = Dataset(name=group.target_name, description=first.description)
        session.add(dataset)
        session.flush()
        return dataset.id


def _resolve_parent(parent: PlannedParent | None, version_ids: dict[tuple[str, int], int]) -> int | None:
    if parent is None:
        return None
    if parent.source_project is None:
        return parent.version_id
    return version_ids.get((parent.source_project, parent.version_id))


def _copy_folder(
    folder: _SourceFolder, project: str, image_ids: dict[tuple[str, int], int]
) -> DatasetFolder:
    """統合元のフォルダを、画像 ID を統合先の ID に置き換えて複製する。"""
    copied = DatasetFolder(
        dir_name=folder.dir_name,
        name=folder.name,
        num_repeats=folder.num_repeats,
        trigger_word=folder.trigger_word,
        position=folder.position,
    )
    for image in folder.images:
        folder_image = DatasetFolderImage(
            image_id=image_ids[(project, image.image_id)], file_stem=image.file_stem
        )
        folder_image.learning_texts = [
            DatasetLearningText(
                extension=text.extension,
                raw_text=text.raw_text,
                elements_json=text.elements_json,
                is_edited=text.is_edited,
            )
            for text in image.texts
        ]
        copied.images.append(folder_image)
    return copied


def _load_source_datasets(session: Session, project: str) -> list[_SourceDataset]:
    """統合元のデータセット・版・フォルダ・学習テキスト・学習設定を、名前順・版 ID 順で読む。"""
    stmt = (
        select(Dataset)
        .order_by(Dataset.name)
        .options(
            selectinload(Dataset.versions)
            .selectinload(DatasetVersion.folders)
            .selectinload(DatasetFolder.images)
            .selectinload(DatasetFolderImage.learning_texts),
            selectinload(Dataset.training_configs),
        )
    )
    datasets: list[_SourceDataset] = []
    for dataset in session.execute(stmt).scalars():
        versions = tuple(
            _SourceVersion(
                node=_VersionNode(version.id, version.name, version.parent_version_id, version.is_working),
                folders=tuple(
                    _SourceFolder(
                        dir_name=folder.dir_name,
                        name=folder.name,
                        num_repeats=folder.num_repeats,
                        trigger_word=folder.trigger_word,
                        position=folder.position,
                        images=tuple(
                            _SourceFolderImage(
                                image_id=folder_image.image_id,
                                file_stem=folder_image.file_stem,
                                texts=tuple(
                                    _SourceText(t.extension, t.raw_text, t.elements_json, t.is_edited)
                                    for t in sorted(folder_image.learning_texts, key=lambda t: t.id)
                                ),
                            )
                            for folder_image in sorted(folder.images, key=lambda i: i.id)
                        ),
                    )
                    for folder in sorted(version.folders, key=lambda f: (f.position, f.id))
                ),
            )
            for version in sorted(dataset.versions, key=lambda v: v.id)
        )
        configs = tuple(
            _SourceConfig(
                version_id=config.version_id,
                values={column: getattr(config, column) for column in _CONFIG_COLUMNS},
            )
            for config in sorted(dataset.training_configs, key=lambda c: c.id)
        )
        datasets.append(
            _SourceDataset(SourceDatasetRef(project, dataset.name), dataset.description, versions, configs)
        )
    return datasets


def _load_target_datasets(session: Session) -> dict[str, _TargetDataset]:
    """統合先に既にあるデータセットと版を読む。"""
    stmt = select(Dataset).options(selectinload(Dataset.versions))
    return {
        dataset.name: _TargetDataset(
            id=dataset.id,
            name=dataset.name,
            versions=tuple(
                _VersionNode(version.id, version.name, version.parent_version_id, version.is_working)
                for version in sorted(dataset.versions, key=lambda v: v.id)
            ),
        )
        for dataset in session.execute(stmt).scalars()
    }


# --- 版の対応と衝突の判定 (DB に依存しない) ---


def _require_dataset(
    datasets: dict[SourceDatasetRef, _SourceDataset], ref: SourceDatasetRef
) -> _SourceDataset:
    dataset = datasets.get(ref)
    if dataset is None:
        raise MergeMappingError(f"統合元にデータセットがありません: {ref.label}")
    return dataset


def _validate_mapping(mapping: MergeMapping, datasets: dict[SourceDatasetRef, _SourceDataset]) -> None:
    """名前の対応が、存在する統合元のデータセット・版を指し、互いに矛盾しないことを確かめる。"""
    for ref in mapping.dataset_names:
        _require_dataset(datasets, ref)
    for version_ref in mapping.version_names:
        dataset = _require_dataset(datasets, SourceDatasetRef(version_ref.project, version_ref.dataset))
        if all(version.node.name != version_ref.version for version in dataset.versions):
            raise MergeMappingError(f"統合元に版がありません: {version_ref.label}")
    _validate_joins(mapping, datasets)


def _validate_joins(mapping: MergeMapping, datasets: dict[SourceDatasetRef, _SourceDataset]) -> None:
    joined: set[SourceDatasetRef] = set()
    for name, refs in mapping.joins.items():
        if not refs:
            raise MergeMappingError(f"履歴をまとめるデータセットがありません: {name}")
        for ref in refs:
            _require_dataset(datasets, ref)
            if ref in joined:
                raise MergeMappingError(
                    f"同じデータセットを 2 つの履歴にまとめようとしています: {ref.label}"
                )
            joined.add(ref)
            mapped = mapping.dataset_names.get(ref)
            if mapped is not None and mapped != name:
                raise MergeMappingError(
                    f"データセットの名前の対応と履歴をまとめる指定が食い違っています: "
                    f"{ref.label} -> '{mapped}' / '{name}'"
                )


def _plan_datasets(
    source_datasets: list[_SourceDataset],
    mapping: MergeMapping,
    target_datasets: dict[str, _TargetDataset],
    source_order: list[str],
) -> _DatasetPlan:
    """統合元のデータセットを統合先のデータセットへまとめ、版の対応と衝突を決める。"""
    by_ref = {dataset.ref: dataset for dataset in source_datasets}
    _validate_mapping(mapping, by_ref)
    joined_name = {ref: name for name, refs in mapping.joins.items() for ref in refs}

    groups: dict[str, _DatasetGroup] = {}
    for name, refs in mapping.joins.items():
        groups[name] = _DatasetGroup(name, [by_ref[ref] for ref in refs], True, target_datasets.get(name))
    loose: dict[str, list[_SourceDataset]] = {}
    for dataset in source_datasets:
        if dataset.ref in joined_name:
            continue
        name = mapping.dataset_names.get(dataset.ref, dataset.ref.dataset)
        loose.setdefault(name, []).append(dataset)

    conflicts: list[MergeConflict] = []
    for name, datasets in loose.items():
        labels = tuple(dataset.ref.label for dataset in datasets)
        if name in groups:
            group = groups[name]
            conflicts.append(
                _dataset_conflict("dataset_name", name, (*[d.ref.label for d in group.elements], *labels))
            )
            continue
        if len(datasets) > 1:
            conflicts.append(_dataset_conflict("dataset_name", name, labels))
        elif name in target_datasets:
            conflicts.append(_dataset_conflict("dataset_exists", name, (_TARGET_LABEL, *labels)))
        groups[name] = _DatasetGroup(name, datasets, False, None)

    ordered = sorted(
        groups.values(),
        key=lambda group: (
            min(source_order.index(element.ref.project) for element in group.elements),
            group.target_name,
        ),
    )
    versions: list[PlannedVersion] = []
    for group in ordered:
        group_versions = _plan_group_versions(group, mapping)
        versions.extend(group_versions)
        # データセットの名前が衝突している間は、版の名前の衝突は解消後に判定する
        if all(conflict.target_dataset != group.target_name for conflict in conflicts):
            conflicts.extend(_version_conflicts(group, group_versions))
    return _DatasetPlan(groups=ordered, versions=versions, conflicts=conflicts)


def _dataset_conflict(kind: ConflictKind, name: str, sources: tuple[str, ...]) -> MergeConflict:
    if kind == "dataset_exists":
        message = (
            f"統合先にデータセット '{name}' が既にあります。別の名前にする (--map-dataset) か、"
            f"既存の履歴に続けてまとめる (--join-dataset {name}=...) 指定をしてください"
        )
    else:
        message = (
            f"データセット '{name}' が複数の統合元にあります ({', '.join(sources)})。"
            "別の名前にする (--map-dataset) か、1 つの履歴にまとめる (--join-dataset) 指定をしてください"
        )
    return MergeConflict(kind, name, None, sources, message)


def _plan_group_versions(group: _DatasetGroup, mapping: MergeMapping) -> list[PlannedVersion]:
    """統合先のデータセット 1 つに入る版の計画を、履歴の順に作る。"""
    planned: list[PlannedVersion] = []
    previous: PlannedParent | None = None
    if group.existing is not None:
        latest = _latest_version_id(group.existing.versions)
        previous = next(
            (
                PlannedParent(None, group.existing.name, node.name, node.id)
                for node in group.existing.versions
                if node.id == latest
            ),
            None,
        )
    for element in group.elements:
        nodes = [version.node for version in element.versions]
        names = {node.id: node.name for node in nodes}
        root_id = _first_root_id(nodes) if group.joined else None
        for version in element.versions:
            node = version.node
            parent: PlannedParent | None = None
            joined_parent = False
            if node.id == root_id and previous is not None:
                parent, joined_parent = previous, True
            elif node.parent_version_id in names:
                parent = PlannedParent(
                    element.ref.project,
                    element.ref.dataset,
                    names[node.parent_version_id],
                    node.parent_version_id,
                )
            ref = SourceVersionRef(element.ref.project, element.ref.dataset, node.name)
            planned.append(
                PlannedVersion(
                    source=ref,
                    source_version_id=node.id,
                    target_dataset=group.target_name,
                    target_version=mapping.version_names.get(ref, node.name),
                    is_working=node.is_working,
                    parent=parent,
                    joined_parent=joined_parent,
                    image_count=version.image_count,
                )
            )
        latest = _latest_version_id(nodes)
        if latest is not None:
            previous = PlannedParent(element.ref.project, element.ref.dataset, names[latest], latest)
    return planned


def _version_conflicts(group: _DatasetGroup, versions: list[PlannedVersion]) -> list[MergeConflict]:
    """同じデータセットに入る版の名前の重複と、作業中の版が 2 つ以上になることを衝突として返す。"""
    conflicts: list[MergeConflict] = []
    by_name: dict[str, list[str]] = {}
    working: list[str] = []
    if group.existing is not None:
        for node in group.existing.versions:
            by_name.setdefault(node.name, []).append(f"{_TARGET_LABEL}:{group.existing.name}/{node.name}")
            if node.is_working:
                working.append(f"{_TARGET_LABEL}:{group.existing.name}/{node.name}")
    for version in versions:
        by_name.setdefault(version.target_version, []).append(version.source.label)
        if version.is_working:
            working.append(version.source.label)
    for name, labels in by_name.items():
        if len(labels) > 1:
            conflicts.append(
                MergeConflict(
                    "version_name",
                    group.target_name,
                    name,
                    tuple(labels),
                    f"データセット '{group.target_name}' に版 '{name}' が {len(labels)} つあります "
                    f"({', '.join(labels)})。--map-version で別の名前にしてください",
                )
            )
    if len(working) > 1:
        conflicts.append(
            MergeConflict(
                "multiple_working_versions",
                group.target_name,
                None,
                tuple(working),
                f"データセット '{group.target_name}' に作業中の版が {len(working)} つあります "
                f"({', '.join(working)})。作業中の版はデータセットごとに 1 つまでです。"
                "履歴をまとめずに別のデータセットにするか、統合元で作業中の版を確定・破棄してください",
            )
        )
    return conflicts


def _build_plan(
    target_project: str,
    sources: Sequence[SourceProject],
    items: dict[str, list[ImageTransferItem]],
    dataset_plan: _DatasetPlan,
    mapping: MergeMapping,
) -> MergePlan:
    """画像の扱い (stage の結果) と版の対応から計画を作る。"""
    summaries: list[SourceImageSummary] = []
    duplicates: list[MergedDuplicate] = []
    # 同じ実行で新しく複製した画像が、どの統合元の画像から作られたか
    produced: dict[int, tuple[str, int]] = {}
    for source in sources:
        source_items = items[source.name]
        for item in source_items:
            if item.target_image_id is None:
                continue
            if item.action == "copy":
                produced[item.target_image_id] = (source.name, item.source_image_id)
            elif item.action == "link":
                into = produced.get(item.target_image_id)
                duplicates.append(
                    MergedDuplicate(
                        source_project=source.name,
                        source_image_id=item.source_image_id,
                        source_uuid=item.source_uuid,
                        merged_into_project=into[0] if into else None,
                        merged_into_image_id=into[1] if into else item.target_image_id,
                    )
                )
        summaries.append(
            SourceImageSummary(
                source_project=source.name,
                images=len(source_items),
                copy=sum(1 for item in source_items if item.action == "copy"),
                link=sum(1 for item in source_items if item.action == "link"),
                already_linked=sum(1 for item in source_items if item.action == "already_linked"),
            )
        )
    return MergePlan(
        target_project=target_project,
        source_projects=tuple(source.name for source in sources),
        images=tuple(summaries),
        duplicates=tuple(duplicates),
        versions=tuple(dataset_plan.versions),
        conflicts=tuple(dataset_plan.conflicts),
        mapping=mapping,
    )


# --- ファイルの配置と commit ---


def _write_files_and_commit(
    session: Session, contexts: list[transfer._StageContext], staging_root: Path
) -> None:
    """全統合元のファイルを staging に置いて最終パスへ移し、commit する。失敗したら何も残さない。

    Raises:
        ValueError: 2 つの統合元のファイルが同じ最終パスになる場合 (何も書かない)。
        OSError: ファイルのコピー・移動に失敗した場合。
        SQLAlchemyError: commit に失敗した場合。
    """
    plans = [plan for context in contexts for plan in context.files]
    finals = [plan.final for plan in plans]
    if len(set(finals)) != len(finals):
        session.rollback()
        raise ValueError(
            "統合元の画像ファイルが統合先の同じパスになります。統合元のフォルダ名を確かめてください"
        )
    moved: list[Path] = []
    created_dirs: list[Path] = []
    committed = False
    try:
        for context in contexts:
            context.staging_dir.mkdir(parents=True, exist_ok=True)
        for plan in plans:
            transfer._copy_file(plan.source, plan.staged)
        for plan in plans:
            created_dirs.extend(transfer._make_parents(plan.final.parent))
            plan.staged.replace(plan.final)
            moved.append(plan.final)
        session.commit()
        committed = True
    finally:
        if not committed:
            session.rollback()
            for path in moved:
                path.unlink(missing_ok=True)
            for directory in reversed(created_dirs):
                transfer._remove_empty_dir(directory)
            logger.warning(
                f"プロジェクトの統合が失敗したため、統合先の変更を取り消しました: files={len(moved)}"
            )
        shutil.rmtree(staging_root, ignore_errors=True)
        transfer._remove_empty_dir(staging_root.parent)
