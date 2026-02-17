# src/lorairo/services/favorite_filters_service.py
"""お気に入りフィルターの保存・読み込みを管理するサービスモジュール。"""

import json
from pathlib import Path
from typing import Any

from ..utils.log import logger


class FavoriteFiltersService:
    """お気に入りフィルターの永続化を管理するサービスクラス。

    JSON ファイルベースでフィルター条件を保存・読み込みします。
    設定ファイルは ~/.config/lorairo/favorite_filters.json に保存されます。
    """

    def __init__(self, organization: str = "LoRAIro", application: str = "LoRAIro") -> None:
        """FavoriteFiltersService を初期化します。

        Args:
            organization: 組織名（将来の拡張用に保持）
            application: アプリケーション名（将来の拡張用に保持）
        """
        # 設定ファイルパス
        self._config_dir = Path.home() / ".config" / "lorairo"
        self._filters_file = self._config_dir / "favorite_filters.json"

        # 設定ディレクトリを作成
        self._config_dir.mkdir(parents=True, exist_ok=True)

        logger.debug("FavoriteFiltersService initialized (config_dir={})", self._config_dir)

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
            # 既存のフィルターを読み込み
            filters = self._load_all_filters()

            # フィルターを追加
            filters[name] = filter_dict

            # JSON ファイルに保存
            self._filters_file.write_text(
                json.dumps(filters, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            logger.info("Saved favorite filter: {}", name)
            return True

        except (TypeError, ValueError) as e:
            logger.error("Failed to serialize filter '{}': {}", name, e, exc_info=True)
            return False
        except Exception as e:
            logger.error("Failed to save filter '{}': {}", name, e, exc_info=True)
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
            filters = self._load_all_filters()

            if name not in filters:
                logger.debug("Filter not found: {}", name)
                return None

            filter_dict = filters[name]

            if not isinstance(filter_dict, dict):
                logger.error("Invalid filter data for '{}': expected dict, got {}", name, type(filter_dict))
                return None

            logger.info("Loaded favorite filter: {}", name)
            return filter_dict

        except (TypeError, ValueError, json.JSONDecodeError) as e:
            logger.error("Failed to deserialize filter '{}': {}", name, e, exc_info=True)
            return None
        except Exception as e:
            logger.error("Failed to load filter '{}': {}", name, e, exc_info=True)
            return None

    def list_filters(self) -> list[str]:
        """保存されているフィルター名の一覧を取得します。

        Returns:
            list[str]: フィルター名のリスト（アルファベット順）
        """
        try:
            filters = self._load_all_filters()
            sorted_names = sorted(filters.keys())

            logger.debug("Listed {} favorite filters", len(sorted_names))
            return sorted_names

        except Exception as e:
            logger.error("Failed to list filters: {}", e, exc_info=True)
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
            filters = self._load_all_filters()

            # 存在確認
            if name not in filters:
                logger.warning("Filter not found for deletion: {}", name)
                return False

            # 削除
            del filters[name]

            # JSON ファイルに保存
            self._filters_file.write_text(
                json.dumps(filters, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            logger.info("Deleted favorite filter: {}", name)
            return True

        except Exception as e:
            logger.error("Failed to delete filter '{}': {}", name, e, exc_info=True)
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
            filters = self._load_all_filters()
            return name in filters
        except Exception as e:
            logger.error("Failed to check filter existence '{}': {}", name, e, exc_info=True)
            return False

    def clear_all_filters(self) -> bool:
        """すべてのフィルター条件を削除します（テスト用）。

        Returns:
            bool: 削除に成功した場合はTrue、失敗した場合はFalse
        """
        try:
            # 空の辞書を保存
            self._filters_file.write_text(
                json.dumps({}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            logger.info("Cleared all favorite filters")
            return True

        except Exception as e:
            logger.error("Failed to clear all filters: {}", e, exc_info=True)
            return False

    def _load_all_filters(self) -> dict[str, Any]:
        """すべてのフィルターを読み込みます。

        Returns:
            dict: フィルター辞書。ファイルが存在しない場合は空の辞書

        Raises:
            JSONDecodeError: JSON パースエラー
        """
        if not self._filters_file.exists():
            return {}

        try:
            content = self._filters_file.read_text(encoding="utf-8")
            return json.loads(content) if content else {}
        except json.JSONDecodeError as e:
            logger.error("Failed to parse filters file: {}", e, exc_info=True)
            raise
