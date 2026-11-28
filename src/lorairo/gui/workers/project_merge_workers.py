"""プロジェクトの統合の計画と確定を背景で行う worker (Issue #1660, ADR 0113)。

GUI スレッドで統合元・統合先の DB を開いたり画像をコピーしたりしないよう、Qt 非依存の
`ProjectMergeService` を worker スレッドで呼ぶ。統合元は service が読み取り専用で開く。
新しいプロジェクトを統合先にする場合は、CLI の `project merge --create` と同じく確定の直前に
プロジェクトを作り、統合に失敗したら作ったプロジェクトを消す。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ...database.db_core import IMG_DB_FILENAME, create_project_session_factory
from ...public_api.exceptions import ProjectNotFoundError, ProjectOperationError
from ...public_api.types import ProjectInfo
from ...services.project_management_service import ProjectManagementService
from ...services.project_merge_service import MergeMapping, MergePlan, MergeResult, ProjectMergeService
from ...services.project_transfer_service import SourceProject
from ...utils.log import logger
from .base import LoRAIroWorkerBase


@dataclass(frozen=True)
class MergeTarget:
    """統合先。

    Attributes:
        name: 統合先のプロジェクト名。
        root: 既存のプロジェクトのディレクトリ。新しく作るプロジェクトなら None。
    """

    name: str
    root: Path | None

    @property
    def is_new(self) -> bool:
        """新しく作るプロジェクトなら True。"""
        return self.root is None


@dataclass(frozen=True)
class MergeApplyOutcome:
    """確定した統合の結果と、統合先のディレクトリ。"""

    result: MergeResult
    target_root: Path


def _open_target(root: Path) -> sessionmaker[Session]:
    """統合先の DB を書き込み可能で開く (schema は head まで上げる)。"""
    return create_project_session_factory(root / IMG_DB_FILENAME)


def _dispose(factory: sessionmaker[Session]) -> None:
    engine = factory.kw.get("bind")
    if isinstance(engine, Engine):
        engine.dispose()


class ProjectMergeListWorker(LoRAIroWorkerBase[list[ProjectInfo]]):
    """統合元・統合先の候補になるプロジェクトの一覧を取得する。"""

    _OPERATION_TYPE = "project_merge_list"

    def __init__(self, service: ProjectManagementService) -> None:
        """Worker を初期化する。

        Args:
            service: プロジェクト管理 service。
        """
        super().__init__()
        self._service = service

    def execute(self) -> list[ProjectInfo]:
        """プロジェクトの一覧を返す。"""
        return self._service.list_projects()


class ProjectMergePlanWorker(LoRAIroWorkerBase[MergePlan]):
    """統合の計画を作る。統合先・統合元のどちらにも書き込まない。"""

    _OPERATION_TYPE = "project_merge_plan"

    def __init__(
        self, sources: Sequence[SourceProject], mapping: MergeMapping, target: MergeTarget
    ) -> None:
        """Worker を初期化する。

        Args:
            sources: 統合元 (この順に統合する)。
            mapping: 名前の対応。
            target: 統合先。
        """
        super().__init__()
        self._sources = list(sources)
        self._mapping = mapping
        self._target = target

    def execute(self) -> MergePlan:
        """計画を返す。

        Raises:
            ValueError: 統合元が空・重複する、統合先と同じ、または名前の対応が不正な場合。
            ReadOnlyPreconditionError: 統合元の DB を開けない場合。
            FileNotFoundError: 統合元の画像ファイルが見つからない場合。
        """
        if self._target.root is None:
            return ProjectMergeService.plan_into_new_project(
                self._sources, self._mapping, self._target.name
            )
        factory = _open_target(self._target.root)
        try:
            service = ProjectMergeService(factory, self._target.root, self._target.name)
            return service.plan(self._sources, self._mapping)
        finally:
            _dispose(factory)


class ProjectMergeApplyWorker(LoRAIroWorkerBase[MergeApplyOutcome]):
    """計画どおりに統合を確定する。"""

    _OPERATION_TYPE = "project_merge_apply"

    def __init__(
        self,
        sources: Sequence[SourceProject],
        mapping: MergeMapping,
        target: MergeTarget,
        project_service: ProjectManagementService,
    ) -> None:
        """Worker を初期化する。

        Args:
            sources: 統合元 (この順に統合する)。
            mapping: 名前の対応。
            target: 統合先。新しく作る場合はここで作る。
            project_service: 新しい統合先の作成と、失敗時の削除に使う。
        """
        super().__init__()
        self._sources = list(sources)
        self._mapping = mapping
        self._target = target
        self._project_service = project_service

    def execute(self) -> MergeApplyOutcome:
        """統合を確定する。失敗したら統合先に何も残さない。

        Raises:
            UnresolvedMergeConflictError: 未解決の衝突がある場合。
            ProjectAlreadyExistsError: 新しい統合先と同じ名前のプロジェクトが既にある場合。
            ValueError / ReadOnlyPreconditionError / FileNotFoundError: 計画と同じ。
            SQLAlchemyError / OSError: 統合先への書き込みに失敗した場合。
        """
        if self._target.root is not None:
            return MergeApplyOutcome(self._apply(self._target.root), self._target.root)

        info = self._project_service.create_project(self._target.name)
        merged = False
        try:
            result = self._apply(info.path)
            merged = True
        finally:
            # 作った統合先は、統合が失敗したら消す (中途半端なプロジェクトを残さない。CLI と同じ)
            if not merged:
                self._delete_created_project(info.name)
        return MergeApplyOutcome(result, info.path)

    def _apply(self, root: Path) -> MergeResult:
        factory = _open_target(root)
        try:
            return ProjectMergeService(factory, root, self._target.name).apply(self._sources, self._mapping)
        finally:
            # 失敗時に作ったプロジェクトを消す前に engine を閉じる (Windows では開いたままだと rmtree が
            # 共有違反になる)
            _dispose(factory)

    def _delete_created_project(self, name: str) -> None:
        try:
            self._project_service.delete_project(name)
        except (ProjectNotFoundError, ProjectOperationError):
            # 元の失敗を利用者へ伝えることを優先し、消せなかったことはログに残す
            logger.opt(exception=True).error(f"統合に失敗した新しいプロジェクトを消せませんでした: {name}")

    def _should_cancel_completed_result(self) -> bool:
        # commit 済みの統合は取り消せないため、完了した結果は常に通知する
        return False
