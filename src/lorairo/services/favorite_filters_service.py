# src/lorairo/services/favorite_filters_service.py
"""お気に入りフィルターの保存・読み込みを管理するサービスモジュール。"""

import json
from typing import Any

from PySide6.QtCore import QSettings

from ..utils.log import logger


class FavoriteFiltersService:
    """お気に入りフィルターの永続化を管理するサービスクラス。

    QSettingsを使用してフィルター条件を保存・読み込みします。
    フィルター条件はJSON形式でシリアライズされます。
    """

    def __init__(self, organization: str = "LoRAIro", application: str = "LoRAIro") -> None:
        """FavoriteFiltersServiceを初期化します。

        Args:
            organization: 組織名（QSettings用）
            application: アプリケーション名（QSettings用）
        """
        self._settings = QSettings(organization, application)
        self._filters_group = "FavoriteFilters"
        logger.debug("FavoriteFiltersService initialized (org=%s, app=%s)", organization, application)

    def save_filter(self, name: str, filter_dict: dict[str, Any]) -> bool:
        """フィルター条件を保存します。

        Args:
            name: フィルター名（一意な識別子）
            filter_dict: フィルター条件の辞書

        Returns:
            bool: 保存に成功した場合はTrue、失敗した場合はFalse

        Raises:
            ValueError: フィルター名が空の場合
        """
        if not name or not name.strip():
            raise ValueError("Filter name cannot be empty")

        try:
            # JSON形式でシリアライズ
            filter_json = json.dumps(filter_dict, ensure_ascii=False)

            # QSettingsに保存
            self._settings.beginGroup(self._filters_group)
            self._settings.setValue(name, filter_json)
            self._settings.endGroup()
            self._settings.sync()

            logger.info("Saved favorite filter: %s", name)
            return True

        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize filter '%s': %s", name, e, exc_info=True)
            return False
        except Exception as e:
            logger.error("Failed to save filter '%s': %s", name, e, exc_info=True)
            return False

    def load_filter(self, name: str) -> dict[str, Any] | None:
        """フィルター条件を読み込みます。

        Args:
            name: フィルター名

        Returns:
            dict | None: フィルター条件の辞書、見つからない場合はNone
        """
        if not name or not name.strip():
            logger.warning("Cannot load filter: empty name")
            return None

        try:
            self._settings.beginGroup(self._filters_group)
            filter_json = self._settings.value(name)
            self._settings.endGroup()

            if filter_json is None:
                logger.debug("Filter not found: %s", name)
                return None

            # JSON形式でデシリアライズ
            filter_dict = json.loads(filter_json)

            if not isinstance(filter_dict, dict):
                logger.error("Invalid filter data for '%s': expected dict, got %s", name, type(filter_dict))
                return None

            logger.info("Loaded favorite filter: %s", name)
            return filter_dict

        except (TypeError, ValueError, json.JSONDecodeError) as e:
            logger.error("Failed to deserialize filter '%s': %s", name, e, exc_info=True)
            return None
        except Exception as e:
            logger.error("Failed to load filter '%s': %s", name, e, exc_info=True)
            return None

    def list_filters(self) -> list[str]:
        """保存されているフィルター名の一覧を取得します。

        Returns:
            list[str]: フィルター名のリスト（アルファベット順）
        """
        try:
            self._settings.beginGroup(self._filters_group)
            filter_names = self._settings.childKeys()
            self._settings.endGroup()

            # アルファベット順にソート
            sorted_names = sorted(filter_names)

            logger.debug("Listed %d favorite filters", len(sorted_names))
            return sorted_names

        except Exception as e:
            logger.error("Failed to list filters: %s", e, exc_info=True)
            return []

    def delete_filter(self, name: str) -> bool:
        """フィルター条件を削除します。

        Args:
            name: フィルター名

        Returns:
            bool: 削除に成功した場合はTrue、失敗した場合はFalse
        """
        if not name or not name.strip():
            logger.warning("Cannot delete filter: empty name")
            return False

        try:
            self._settings.beginGroup(self._filters_group)

            # 存在確認
            if not self._settings.contains(name):
                logger.warning("Filter not found for deletion: %s", name)
                self._settings.endGroup()
                return False

            # 削除
            self._settings.remove(name)
            self._settings.endGroup()
            self._settings.sync()

            logger.info("Deleted favorite filter: %s", name)
            return True

        except Exception as e:
            logger.error("Failed to delete filter '%s': %s", name, e, exc_info=True)
            return False

    def filter_exists(self, name: str) -> bool:
        """指定されたフィルター名が既に存在するか確認します。

        Args:
            name: フィルター名

        Returns:
            bool: 存在する場合はTrue、存在しない場合はFalse
        """
        if not name or not name.strip():
            return False

        try:
            self._settings.beginGroup(self._filters_group)
            exists = self._settings.contains(name)
            self._settings.endGroup()
            return exists
        except Exception as e:
            logger.error("Failed to check filter existence '%s': %s", name, e, exc_info=True)
            return False

    def clear_all_filters(self) -> bool:
        """すべてのフィルター条件を削除します（テスト用）。

        Returns:
            bool: 削除に成功した場合はTrue、失敗した場合はFalse
        """
        try:
            self._settings.beginGroup(self._filters_group)
            self._settings.remove("")  # Remove all keys in current group
            self._settings.endGroup()
            self._settings.sync()

            logger.info("Cleared all favorite filters")
            return True

        except Exception as e:
            logger.error("Failed to clear all filters: %s", e, exc_info=True)
            return False
