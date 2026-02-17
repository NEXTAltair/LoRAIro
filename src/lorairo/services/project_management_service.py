"""プロジェクト管理 Service。

プロジェクトのファイルシステム操作を Service 化し、
CLI/GUI双方から利用可能にする。Qt 依存なし。
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from lorairo.api.exceptions import (
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectOperationError,
)
from lorairo.api.types import ProjectInfo


class ProjectManagementService:
    """プロジェクト管理 Service。

    プロジェクトディレクトリの CRUD操作を担当。
    ~/.lorairo/projects/ 配下にプロジェクトディレクトリを管理する。
    """

    def __init__(self, projects_base_dir: Path | None = None) -> None:
        """初期化。

        Args:
            projects_base_dir: プロジェクトベースディレクトリ。
                              未指定時は ~/.lorairo/projects
        """
        self.projects_base_dir = projects_base_dir or (
            Path.home() / ".lorairo" / "projects"
        )
        logger.debug(
            f"ProjectManagementService 初期化: {self.projects_base_dir}"
        )

    def create_project(
        self, name: str, description: str = ""
    ) -> ProjectInfo:
        """プロジェクトを作成。

        ディレクトリ構造:
        ```
        ~/.lorairo/projects/
        └── project_name_20250216_142530/
            ├── .lorairo-project        (メタデータ)
            ├── image_database.db
            └── image_dataset/
                └── original_images/
        ```

        Args:
            name: プロジェクト名。
            description: プロジェクト説明。

        Returns:
            ProjectInfo: 作成されたプロジェクト情報。

        Raises:
            ProjectAlreadyExistsError: 同名プロジェクトが既に存在。
            ProjectOperationError: プロジェクト作成に失敗。
        """
        try:
            # 既存確認
            if self._project_exists(name):
                raise ProjectAlreadyExistsError(name)

            # ベースディレクトリ作成
            self.projects_base_dir.mkdir(parents=True, exist_ok=True)

            # プロジェクトディレクトリ名生成（名前_YYYYMMDD_HHMMSS）
            now = datetime.now()
            date_str = now.strftime("%Y%m%d_%H%M%S")
            project_dir = self.projects_base_dir / f"{name}_{date_str}"

            # 競合時のリトライ（極めて稀だが念のため）
            counter = 1
            while project_dir.exists():
                date_str = now.strftime(f"%Y%m%d_%H%M%S_{counter}")
                project_dir = self.projects_base_dir / f"{name}_{date_str}"
                counter += 1

            # ディレクトリ構造作成
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "image_dataset").mkdir(exist_ok=True)
            (project_dir / "image_dataset" / "original_images").mkdir(
                exist_ok=True
            )

            # メタデータファイル作成
            metadata = {
                "name": name,
                "created": date_str,
                "description": description,
            }
            metadata_file = project_dir / ".lorairo-project"
            metadata_file.write_text(
                json.dumps(metadata, indent=2, ensure_ascii=False)
            )

            # 初期データベースファイル作成（ダミー）
            # 実際のDB初期化は ImageDatabaseManager で行われる
            db_file = project_dir / "image_database.db"
            db_file.touch()

            logger.info(f"プロジェクト作成: {name} -> {project_dir}")

            return ProjectInfo(
                name=name,
                path=project_dir,
                created=now,
                description=description if description else None,
                image_count=0,
            )

        except ProjectAlreadyExistsError:
            raise
        except Exception as e:
            logger.error(f"プロジェクト作成失敗: {name}", exc_info=True)
            raise ProjectOperationError(name, "作成", str(e)) from e

    def list_projects(self) -> list[ProjectInfo]:
        """プロジェクト一覧を取得。

        Returns:
            list[ProjectInfo]: プロジェクト情報のリスト。存在しない場合は空リスト。
        """
        projects: list[ProjectInfo] = []

        if not self.projects_base_dir.exists():
            logger.debug(
                f"プロジェクトベースディレクトリが存在しません: "
                f"{self.projects_base_dir}"
            )
            return projects

        try:
            for proj_dir in sorted(self.projects_base_dir.iterdir()):
                if not proj_dir.is_dir():
                    continue

                project_info = self._read_project_info(proj_dir)
                if project_info:
                    projects.append(project_info)

            logger.debug(f"プロジェクト一覧取得: {len(projects)}件")
            return projects

        except Exception as e:
            logger.error("プロジェクト一覧取得失敗", exc_info=True)
            raise ProjectOperationError("", "一覧取得", str(e)) from e

    def get_project(self, name: str) -> ProjectInfo:
        """プロジェクト情報を取得。

        Args:
            name: プロジェクト名。

        Returns:
            ProjectInfo: プロジェクト情報。

        Raises:
            ProjectNotFoundError: プロジェクトが見つからない。
        """
        try:
            project_dir = self._find_project_directory(name)
            if not project_dir:
                raise ProjectNotFoundError(name)

            project_info = self._read_project_info(project_dir)
            if not project_info:
                raise ProjectNotFoundError(name)

            return project_info

        except ProjectNotFoundError:
            raise
        except Exception as e:
            logger.error(f"プロジェクト取得失敗: {name}", exc_info=True)
            raise ProjectOperationError(name, "取得", str(e)) from e

    def delete_project(self, name: str) -> None:
        """プロジェクトを削除。

        注意: このメソッドは完全にファイルシステムから削除します。
        復元不可能です。

        Args:
            name: プロジェクト名。

        Raises:
            ProjectNotFoundError: プロジェクトが見つからない。
            ProjectOperationError: 削除に失敗。
        """
        try:
            project_dir = self._find_project_directory(name)
            if not project_dir:
                raise ProjectNotFoundError(name)

            logger.debug(f"プロジェクト削除開始: {name} -> {project_dir}")
            shutil.rmtree(project_dir)
            logger.info(f"プロジェクト削除: {name}")

        except ProjectNotFoundError:
            raise
        except Exception as e:
            logger.error(f"プロジェクト削除失敗: {name}", exc_info=True)
            raise ProjectOperationError(name, "削除", str(e)) from e

    def update_project(
        self, name: str, description: str
    ) -> ProjectInfo:
        """プロジェクト情報を更新。

        現在は説明文の更新のみサポート。

        Args:
            name: プロジェクト名。
            description: 新しい説明文。

        Returns:
            ProjectInfo: 更新されたプロジェクト情報。

        Raises:
            ProjectNotFoundError: プロジェクトが見つからない。
            ProjectOperationError: 更新に失敗。
        """
        try:
            project_dir = self._find_project_directory(name)
            if not project_dir:
                raise ProjectNotFoundError(name)

            # メタデータファイルを更新
            metadata_file = project_dir / ".lorairo-project"
            if metadata_file.exists():
                metadata = json.loads(metadata_file.read_text())
                metadata["description"] = description
                metadata_file.write_text(
                    json.dumps(metadata, indent=2, ensure_ascii=False)
                )

            logger.info(f"プロジェクト更新: {name}")

            # 更新後の情報を取得して返す
            return self.get_project(name)

        except ProjectNotFoundError:
            raise
        except Exception as e:
            logger.error(f"プロジェクト更新失敗: {name}", exc_info=True)
            raise ProjectOperationError(name, "更新", str(e)) from e

    # ==================== プライベートメソッド ====================

    def _project_exists(self, name: str) -> bool:
        """プロジェクトが存在するか確認。

        Args:
            name: プロジェクト名。

        Returns:
            bool: 存在する場合 True。
        """
        return self._find_project_directory(name) is not None

    def _find_project_directory(self, name: str) -> Path | None:
        """プロジェクト名からディレクトリパスを検索。

        ディレクトリ名は「name_日付」形式なので、
        startswith で検索。

        Args:
            name: プロジェクト名。

        Returns:
            Optional[Path]: 見つかった場合はディレクトリパス、
                           見つからない場合は None。
        """
        if not self.projects_base_dir.exists():
            return None

        try:
            for proj_dir in self.projects_base_dir.iterdir():
                if proj_dir.is_dir() and proj_dir.name.startswith(
                    f"{name}_"
                ):
                    # メタデータファイルで確認
                    if (proj_dir / ".lorairo-project").exists():
                        return proj_dir
            return None

        except Exception:
            logger.warning(f"プロジェクト検索エラー: {name}", exc_info=True)
            return None

    def _read_project_info(
        self, project_dir: Path
    ) -> ProjectInfo | None:
        """プロジェクトディレクトリから情報を読み込み。

        Args:
            project_dir: プロジェクトディレクトリ。

        Returns:
            Optional[ProjectInfo]: プロジェクト情報。
                                  読み込み失敗時は None。
        """
        try:
            metadata_file = project_dir / ".lorairo-project"
            if not metadata_file.exists():
                logger.warning(
                    f"メタデータファイルが見つかりません: "
                    f"{metadata_file}"
                )
                return None

            metadata = json.loads(metadata_file.read_text())

            # 作成日時を datetime に変換
            created_str = metadata.get("created", "")
            try:
                created = datetime.strptime(created_str, "%Y%m%d_%H%M%S")
            except ValueError:
                # 新しいフォーマット対応（_NNNサフィックス対応）
                parts = created_str.rsplit("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    created = datetime.strptime(
                        parts[0], "%Y%m%d_%H%M%S"
                    )
                else:
                    created = datetime.now()

            # 画像数を取得（ダミー実装、実際はDB から取得）
            image_count = 0
            original_images_dir = (
                project_dir / "image_dataset" / "original_images"
            )
            if original_images_dir.exists():
                image_count = len(list(original_images_dir.glob("*")))

            return ProjectInfo(
                name=metadata.get("name", ""),
                path=project_dir,
                created=created,
                description=metadata.get("description"),
                image_count=image_count,
            )

        except Exception:
            logger.error(
                f"プロジェクト情報読み込み失敗: {project_dir}",
                exc_info=True,
            )
            return None
