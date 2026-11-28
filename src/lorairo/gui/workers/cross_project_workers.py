"""プロジェクト横断の検索・画像コピー・版の作成を背景で行う worker (Issue #1661, ADR 0112)。

GUI スレッドで別プロジェクトの DB を開いたりファイルをコピーしたりしないよう、Qt 非依存の
`CrossProjectSearchService` / `ProjectTransferService` / `DatasetVersionBuildService` を worker
スレッドで呼ぶ。別プロジェクトの DB は service が読み取り専用で開く。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from sqlalchemy.exc import SQLAlchemyError

from ...database.filter_criteria import ImageFilterCriteria
from ...public_api.exceptions import ReadOnlyPreconditionError, ResultSetTooLargeError
from ...public_api.types import ProjectInfo
from ...services.dataset_version_build_service import (
    BuildVersionPlan,
    BuildVersionRequest,
    BuildVersionResult,
    DatasetVersionBuildService,
)
from ...services.project_management_service import ProjectManagementService
from ...services.project_transfer_service import (
    CrossProjectSearchService,
    ImageTransferResult,
    ProjectSearchResult,
    ProjectTransferService,
    SourceProject,
)
from ...utils.log import logger
from .base import LoRAIroWorkerBase

# 1 プロジェクトから取得する検索結果の上限 (CLI の `images search-projects` と同じ)
MAX_RESULTS_PER_PROJECT = 500
# 一致件数が上限を超えたプロジェクトの `unavailable_reason`
TOO_MANY_RESULTS_REASON = "too_many_results"


class ProjectListWorker(LoRAIroWorkerBase[list[ProjectInfo]]):
    """プロジェクトの一覧を取得する。"""

    _OPERATION_TYPE = "cross_project_list"

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


class CrossProjectSearchWorker(LoRAIroWorkerBase[list[ProjectSearchResult]]):
    """複数のプロジェクトを読み取り専用で検索する。

    開けないプロジェクト (schema が古い等) と、一致件数が上限を超えたプロジェクトは例外にせず、
    `unavailable_reason` 付きの空の結果にして残りを続ける。
    """

    _OPERATION_TYPE = "cross_project_search"

    def __init__(
        self,
        projects: Sequence[SourceProject],
        criteria_factory: Callable[[], ImageFilterCriteria],
        *,
        max_results_per_project: int = MAX_RESULTS_PER_PROJECT,
        service: CrossProjectSearchService | None = None,
    ) -> None:
        """Worker を初期化する。

        Args:
            projects: 検索するプロジェクト。
            criteria_factory: 検索条件を作る callable (タグ語の翻訳解決を含むので worker で呼ぶ)。
            max_results_per_project: 1 プロジェクトから取得してよい最大件数。
            service: 横断検索 service (テスト用の差し替え口)。
        """
        super().__init__()
        self._projects = list(projects)
        self._criteria_factory = criteria_factory
        self._max_results = max_results_per_project
        self._service = service or CrossProjectSearchService()

    def execute(self) -> list[ProjectSearchResult]:
        """プロジェクトごとの検索結果を、渡した順に返す。"""
        criteria = self._criteria_factory()
        results: list[ProjectSearchResult] = []
        for project in self._projects:
            self._check_cancellation()
            try:
                results.extend(
                    self._service.search(
                        [project],
                        criteria,
                        max_results_per_project=self._max_results,
                        skip_unavailable=True,
                    )
                )
            except ResultSetTooLargeError as e:
                logger.warning(
                    f"一致件数が上限を超えたため取得しませんでした: '{project.name}' "
                    f"(matched={e.matched}, limit={e.limit})"
                )
                results.append(
                    ProjectSearchResult(
                        project.name, e.matched, [], unavailable_reason=TOO_MANY_RESULTS_REASON
                    )
                )
        return results


@dataclass(frozen=True)
class CopyFailure:
    """コピー元 1 プロジェクト分の失敗。"""

    project_name: str
    message: str


@dataclass(frozen=True)
class CrossProjectCopyOutcome:
    """コピー元ごとの取り込み結果 (または計画) と失敗。

    Attributes:
        results: 成功したコピー元ごとの結果 (渡した順)。
        failures: 失敗したコピー元。コピー元ごとに 1 commit なので、失敗したもの以外は書き込み済み。
        dry_run: 計画だけで何も書いていない場合 True。
    """

    results: list[ImageTransferResult]
    failures: list[CopyFailure] = field(default_factory=list)
    dry_run: bool = False

    def count(self, action: str) -> int:
        """全コピー元を通した、指定した扱いの画像の数を返す。"""
        return sum(1 for result in self.results for item in result.items if item.action == action)

    def target_image_ids(self) -> list[int]:
        """取り込み先で追加・更新した画像 ID (計画では決まっている分だけ)。"""
        ids = [
            item.target_image_id
            for result in self.results
            for item in result.items
            if item.target_image_id is not None
        ]
        return list(dict.fromkeys(ids))


# コピー元 1 つの失敗として扱い、残りのコピー元を続ける例外 (service の Raises に対応)
_COPY_ERRORS = (ValueError, LookupError, OSError, ReadOnlyPreconditionError, SQLAlchemyError)


class CrossProjectCopyWorker(LoRAIroWorkerBase[CrossProjectCopyOutcome]):
    """選んだ画像をコピー元ごとに現在のプロジェクトへコピーする (または計画だけ作る)。"""

    _OPERATION_TYPE = "cross_project_copy"

    def __init__(
        self,
        service: ProjectTransferService,
        groups: Sequence[tuple[SourceProject, list[int]]],
        *,
        dry_run: bool,
    ) -> None:
        """Worker を初期化する。

        Args:
            service: 取り込み先を束縛したコピー service。
            groups: (コピー元, コピー元の画像 ID) の並び。
            dry_run: True なら計画だけを作り、何も書かない。
        """
        super().__init__()
        self._service = service
        self._groups = list(groups)
        self._dry_run = dry_run

    def execute(self) -> CrossProjectCopyOutcome:
        """コピー元ごとに `copy_images` を呼び、結果と失敗をまとめて返す。"""
        results: list[ImageTransferResult] = []
        failures: list[CopyFailure] = []
        for source, image_ids in self._groups:
            if self._dry_run:
                self._check_cancellation()
            try:
                results.append(self._service.copy_images(source, image_ids, dry_run=self._dry_run))
            except _COPY_ERRORS as e:
                logger.opt(exception=True).error(f"プロジェクトからのコピーに失敗しました: '{source.name}'")
                failures.append(CopyFailure(source.name, str(e)))
        return CrossProjectCopyOutcome(results, failures, dry_run=self._dry_run)

    def _should_cancel_completed_result(self) -> bool:
        # 書き込んだコピーは取り消せないため、実行した結果は常に通知する
        if not self._dry_run:
            return False
        return super()._should_cancel_completed_result()


class DatasetVersionProposeWorker(LoRAIroWorkerBase[BuildVersionPlan]):
    """選んだ画像から作る版の計画を作る (何も書かない)。"""

    _OPERATION_TYPE = "dataset_version_propose"

    def __init__(self, service: DatasetVersionBuildService, request: BuildVersionRequest) -> None:
        """Worker を初期化する。

        Args:
            service: 版の作成 service。
            request: 作る版の指定。
        """
        super().__init__()
        self._service = service
        self._request = request

    def execute(self) -> BuildVersionPlan:
        """計画を返す。

        Raises:
            ValueError: フォルダ名が不正、画像が無い等の場合。
            DatasetConflictError: 同じ名前の版が既にある場合。
        """
        return self._service.propose(self._request)


class DatasetVersionBuildWorker(LoRAIroWorkerBase[BuildVersionResult]):
    """選んだ画像から版を作る。"""

    _OPERATION_TYPE = "dataset_version_build"

    def __init__(self, service: DatasetVersionBuildService, request: BuildVersionRequest) -> None:
        """Worker を初期化する。

        Args:
            service: 版の作成 service。
            request: 作る版の指定。
        """
        super().__init__()
        self._service = service
        self._request = request

    def execute(self) -> BuildVersionResult:
        """版を作り、結果を返す。"""
        return self._service.build(self._request)

    def _should_cancel_completed_result(self) -> bool:
        # 作った版は取り消せないため、完了した結果は常に通知する
        return False
