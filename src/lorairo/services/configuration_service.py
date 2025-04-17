"""アプリケーションの設定を管理するサービスモジュール。"""

from pathlib import Path
from typing import Any

from ..utils.config import DEFAULT_CONFIG_PATH, get_config, write_config_file
from ..utils.log import logger


class ConfigurationService:
    """アプリケーションの設定読み込み、更新、保存を担当するサービスクラス。"""

    def __init__(self, config_path: Path | None = None) -> None:
        """ConfigurationServiceを初期化します。

        Args:
            config_path (Optional[Path]): 設定ファイルのパス。Noneの場合、デフォルトパスを使用。
        """
        self._config_path = config_path or DEFAULT_CONFIG_PATH
        # TODO: ConfigManagerのシングルトン or DI に合わせて実装見直し
        try:
            self._config: dict[str, Any] = get_config(self._config_path)
            logger.info("設定ファイルを読み込みました: %s", self._config_path)
        except FileNotFoundError:
            logger.error("設定ファイルが見つかりません: %s", self._config_path, exc_info=True)
            # TODO: デフォルト設定で初期化するか、エラーをraiseするか検討
            self._config = {}
        except Exception:
            logger.error("設定ファイルの読み込み中に予期せぬエラーが発生しました。", exc_info=True)
            self._config = {}

    def get_setting(self, section: str, key: str, default: Any | None = None) -> Any:
        """指定されたセクションとキーの設定値を取得します。

        Args:
            section (str): 設定のセクション名。
            key (str): 設定のキー名。
            default (Optional[Any]): 設定値が見つからない場合に返すデフォルト値。

        Returns:
            Any: 設定値。見つからない場合は default。
        """
        # TODO: ネストしたキーに対応 (例: "api.openai_key")
        return self._config.get(section, {}).get(key, default)

    def get_all_settings(self) -> dict[str, Any]:
        """現在のすべての設定を取得します。

        Returns:
            dict[str, Any]: 設定全体の辞書。
        """
        # 注意: 内部状態の辞書を直接返すと外部から変更される可能性があるため、
        # 必要に応じてコピーを返すか、読み取り専用のインターフェースを提供する。
        # 現状は ConfigManager の挙動に合わせる。
        return self._config

    def update_setting(self, section: str, key: str, value: Any) -> None:
        """指定されたセクションとキーの設定値を更新します。

        Args:
            section (str): 設定のセクション名。
            key (str): 設定のキー名。
            value (Any): 新しい設定値。
        """
        # TODO: ネストしたキーに対応
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        logger.debug("設定値を更新しました: [%s] %s = %s", section, key, value)

    def save_settings(self, target_path: Path | None = None) -> bool:
        """現在の設定を指定されたファイルに保存します。

        Args:
            target_path (Optional[Path]): 保存先のファイルパス。Noneの場合、初期化時に使用したパスに上書き。

        Returns:
            bool: 保存に成功した場合は True、失敗した場合は False。
        """
        save_path = target_path or self._config_path
        if not save_path:
            logger.error("設定の保存先パスが決定できませんでした。")
            return False

        try:
            # FileSystemManager.save_toml_config(self._config, save_path) # FileSystemManager経由にするか検討
            write_config_file(self._config, save_path)
            logger.info("設定をファイルに保存しました: %s", save_path)
            return True
        except OSError:
            logger.error("設定ファイルの保存中にIOエラーが発生しました: %s", save_path, exc_info=True)
            return False
        except Exception:
            logger.error("設定ファイルの保存中に予期せぬエラーが発生しました。", exc_info=True)
            return False

    def get_image_processing_config(self) -> dict[str, Any]:
        """image_processing セクションの設定を取得します。"""
        return self._config.get("image_processing", {})

    def get_preferred_resolutions(self) -> list[int]:
        """preferred_resolutions の設定を取得します。"""
        # 型安全のため、リスト内の要素が int であることを期待する (バリデーションは別途検討)
        return self._config.get("preferred_resolutions", [])

    def get_upscaler_models(self) -> list[dict[str, Any]]:
        """upscaler_models の設定を取得します。"""
        # 型安全のため、リスト内の要素が dict であることを期待する
        return self._config.get("upscaler_models", [])

    def get_output_directory(self) -> Path:
        """directories.output の設定値を取得します。"""
        dir_str = self.get_setting("directories", "output", ".")  # デフォルトをカレントに
        return Path(dir_str)

    def update_image_processing_setting(self, key: str, value: Any) -> None:
        """image_processing セクション内の設定値を更新します。"""
        # update_setting を利用して更新
        self.update_setting("image_processing", key, value)

    # --- 他のウィジェットが必要とするメソッドもここに追加していく ---
