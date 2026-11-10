"""Kohya データセットの版の一覧・詳細・書き出しを背景で行う worker (Issue #1456)。

GUI スレッドで DB の照会やファイルの書き出しを行わないよう、`DatasetRepository` と
`KohyaDatasetExportService` (どちらも Qt-free) を worker スレッドで呼ぶ。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...database.repository.dataset import (
    DatasetRepository,
    TagCopyResult,
    TagRevokeResult,
    TrainingConfigSnapshot,
    VersionSnapshot,
    VersionSummary,
)
from ...services.kohya_dataset_export_service import KohyaDatasetExportService, KohyaExportResult
from .base import LoRAIroWorkerBase


@dataclass(frozen=True)
class KohyaVersionDetail:
    """版の中身と、そのデータセットの学習設定。"""

    version_id: int
    snapshot: VersionSnapshot
    training_configs: list[TrainingConfigSnapshot]


class KohyaVersionListWorker(LoRAIroWorkerBase[list[VersionSummary]]):
    """全データセットの版の一覧を取得する。"""

    _OPERATION_TYPE = "kohya_version_list"

    def __init__(self, repository: DatasetRepository) -> None:
        """Worker を初期化する。

        Args:
            repository: データセット Repository。
        """
        super().__init__()
        self._repository = repository

    def execute(self) -> list[VersionSummary]:
        """版の一覧を返す。"""
        return self._repository.list_versions()


class KohyaVersionDetailWorker(LoRAIroWorkerBase[KohyaVersionDetail]):
    """版のフォルダ一覧と、データセットの学習設定を取得する。"""

    _OPERATION_TYPE = "kohya_version_detail"

    def __init__(self, repository: DatasetRepository, version_id: int, dataset_id: int) -> None:
        """Worker を初期化する。

        Args:
            repository: データセット Repository。
            version_id: 版 ID。
            dataset_id: 版が属するデータセット ID (学習設定の取得に使う)。
        """
        super().__init__()
        self._repository = repository
        self._version_id = version_id
        self._dataset_id = dataset_id

    def execute(self) -> KohyaVersionDetail:
        """版の中身と学習設定を返す。

        Raises:
            LookupError: 版が存在しない場合。
        """
        snapshot = self._repository.get_version_snapshot(self._version_id)
        self._check_cancellation()
        configs = self._repository.list_training_configs(self._dataset_id)
        return KohyaVersionDetail(self._version_id, snapshot, configs)


class KohyaVersionExportWorker(LoRAIroWorkerBase[KohyaExportResult]):
    """版を Kohya-ss 形式で書き出す。"""

    _OPERATION_TYPE = "kohya_version_export"

    def __init__(
        self,
        repository: DatasetRepository,
        version_id: int,
        output_dir: Path,
        training_config_id: int | None,
    ) -> None:
        """Worker を初期化する。

        Args:
            repository: データセット Repository。
            version_id: 書き出す版 ID。
            output_dir: 出力先 (存在しないか空のディレクトリ)。
            training_config_id: 書き出す学習設定の ID。`None` なら学習設定を書き出さない。
        """
        super().__init__()
        self._repository = repository
        self._version_id = version_id
        self._output_dir = output_dir
        self._training_config_id = training_config_id

    def execute(self) -> KohyaExportResult:
        """書き出しを実行する。

        Raises:
            FileExistsError: 出力先が空でない場合。
            FileNotFoundError: 保存済み画像のファイルが無い場合。
            LookupError: 版・学習設定が存在しない場合。
            ValueError: 版にフォルダが無い、または学習テキストの拡張子が混在する場合。
        """
        return KohyaDatasetExportService(self._repository).export_version(
            self._version_id, self._output_dir, training_config_id=self._training_config_id
        )

    def _should_cancel_completed_result(self) -> bool:
        # 書き出し済みのファイルは取り消せないため、完了した結果は常に通知する
        return False


class KohyaVersionCopyTagsWorker(LoRAIroWorkerBase[TagCopyResult]):
    """版の学習テキストをライブラリの `Tag` (`KOHYA_DATASET`) へ写す (Issue #1490 / ADR 0104)。"""

    _OPERATION_TYPE = "kohya_version_copy_tags"

    def __init__(
        self,
        repository: DatasetRepository,
        version_id: int,
        *,
        dir_names: list[str] | None = None,
        extension: str = ".txt",
        dry_run: bool = False,
    ) -> None:
        """Worker を初期化する。

        Args:
            repository: データセット Repository。
            version_id: 版 ID。
            dir_names: 対象のフォルダ名 (`None` なら版の全フォルダ)。
            extension: 学習テキストの拡張子。
            dry_run: True なら件数だけ数えて書き込まない。
        """
        super().__init__()
        self._repository = repository
        self._version_id = version_id
        self._dir_names = dir_names
        self._extension = extension
        self._dry_run = dry_run

    def execute(self) -> TagCopyResult:
        """学習テキストのタグ反映 (または dry-run 集計) を実行する。"""
        return self._repository.copy_learning_texts_to_tags(
            self._version_id,
            dir_names=self._dir_names,
            extension=self._extension,
            dry_run=self._dry_run,
        )

    def _should_cancel_completed_result(self) -> bool:
        if not self._dry_run:
            return False
        return super()._should_cancel_completed_result()


class KohyaVersionRevokeTagsWorker(LoRAIroWorkerBase[TagRevokeResult]):
    """擬似モデル `KOHYA_DATASET` の `Tag` 行を一括削除する (Issue #1490 / ADR 0104)。"""

    _OPERATION_TYPE = "kohya_version_revoke_tags"

    def __init__(
        self,
        repository: DatasetRepository,
        version_id: int | None = None,
        *,
        dir_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> None:
        """Worker を初期化する。

        Args:
            repository: データセット Repository。
            version_id: 版 ID (`None` ならプロジェクト全体)。
            dir_names: 対象のフォルダ名 (`version_id` 指定時のみ有効、`None` なら全フォルダ)。
            dry_run: True なら件数だけ数えて削除しない。
        """
        super().__init__()
        self._repository = repository
        self._version_id = version_id
        self._dir_names = dir_names
        self._dry_run = dry_run

    def execute(self) -> TagRevokeResult:
        """`KOHYA_DATASET` タグの削除 (または dry-run 集計) を実行する。"""
        return self._repository.revoke_learning_texts_from_tags(
            version_id=self._version_id,
            dir_names=self._dir_names,
            dry_run=self._dry_run,
        )

    def _should_cancel_completed_result(self) -> bool:
        if not self._dry_run:
            return False
        return super()._should_cancel_completed_result()


class KohyaVersionCommitWorker(LoRAIroWorkerBase[int]):
    """作業版を確定版へ遷移させる (Issue #1564)。"""

    _OPERATION_TYPE = "kohya_version_commit"

    def __init__(self, repository: DatasetRepository, version_id: int) -> None:
        super().__init__()
        self._repository = repository
        self._version_id = version_id

    def execute(self) -> int:
        """作業版を確定し、対象 version_id を返す。"""
        self._repository.commit_working_version(self._version_id)
        return self._version_id

    def _should_cancel_completed_result(self) -> bool:
        return False


class KohyaVersionDiscardWorker(LoRAIroWorkerBase[int]):
    """作業版を破棄する (Issue #1564)。"""

    _OPERATION_TYPE = "kohya_version_discard"

    def __init__(self, repository: DatasetRepository, version_id: int) -> None:
        super().__init__()
        self._repository = repository
        self._version_id = version_id

    def execute(self) -> int:
        """作業版を削除し、対象 version_id を返す。"""
        self._repository.discard_working_version(self._version_id)
        return self._version_id

    def _should_cancel_completed_result(self) -> bool:
        return False
