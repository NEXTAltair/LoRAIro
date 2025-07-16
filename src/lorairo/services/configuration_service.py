"""アプリケーションの設定を管理するサービスモジュール。"""

from pathlib import Path
from typing import Any

from ..utils.config import DEFAULT_CONFIG, DEFAULT_CONFIG_PATH, get_config, write_config_file
from ..utils.log import logger


class ConfigurationService:
    """アプリケーションの設定読み込み、更新、保存を担当するサービスクラス。"""

    def __init__(
        self, config_path: Path | None = None, shared_config: dict[str, Any] | None = None
    ) -> None:
        """ConfigurationServiceを初期化します。

        Args:
            config_path (Optional[Path]): 設定ファイルのパス。Noneの場合、デフォルトパスを使用。
            shared_config (Optional[dict]): 共有設定オブジェクト。複数インスタンス間で設定を共有する場合に使用。
        """
        self._config_path = config_path or DEFAULT_CONFIG_PATH

        if shared_config is not None:
            # 共有設定オブジェクトを使用（参照渡し）
            self._config = shared_config
            logger.debug("共有設定オブジェクトを使用してConfigurationServiceを初期化しました")
        else:
            # 新規設定読み込みまたはデフォルト設定ファイル作成
            try:
                self._config: dict[str, Any] = get_config(self._config_path)
                logger.info("設定ファイルを読み込みました: %s", self._config_path)
            except FileNotFoundError:
                logger.warning(
                    "設定ファイルが見つかりません。デフォルト設定で新規作成します: %s", self._config_path
                )
                self._config = self._create_default_config_file()
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
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value
        # APIキーの場合はマスキングしてログ出力
        if section == "api" and "key" in key.lower():
            masked_value = self._mask_api_key(str(value))
            logger.debug("設定値を更新しました: [%s] %s = %s", section, key, masked_value)
        elif section == "huggingface" and key == "token":
            masked_value = self._mask_api_key(str(value))
            logger.debug("設定値を更新しました: [%s] %s = %s", section, key, masked_value)
        else:
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

    def get_preferred_resolutions(self) -> list[tuple[int, int]]:
        """preferred_resolutions の設定を取得します。"""
        return self._config.get("preferred_resolutions", [])

    def get_upscaler_models(self) -> list[dict[str, Any]]:
        """upscaler_models の設定を取得します。"""
        # 型安全のため、リスト内の要素が dict であることを期待する
        return self._config.get("upscaler_models", [])

    def get_upscaler_model_by_name(self, name: str) -> dict[str, Any] | None:
        """指定された名前のアップスケーラーモデル設定を取得します。"""
        models = self.get_upscaler_models()
        for model in models:
            if model.get("name") == name:
                return model
        return None

    def get_available_upscaler_names(self) -> list[str]:
        """利用可能なアップスケーラーモデル名のリストを取得します。"""
        return [model.get("name", "") for model in self.get_upscaler_models()]

    def get_default_upscaler_name(self) -> str:
        """デフォルトのアップスケーラー名を取得します。"""
        # image_processing.upscaler または最初のモデル名を返す
        default_name = self.get_setting("image_processing", "upscaler", "")
        if default_name:
            return default_name

        # フォールバック: 最初のモデル名
        models = self.get_upscaler_models()
        if models:
            return models[0].get("name", "")

        return "RealESRGAN_x4plus"  # 最終フォールバック

    def validate_upscaler_config(self) -> bool:
        """アップスケーラー設定の妥当性をチェックします。"""
        models = self.get_upscaler_models()
        if not models:
            logger.warning("upscaler_models が設定されていません")
            return False

        for model in models:
            if not all(key in model for key in ["name", "path", "scale"]):
                logger.warning(f"不正なアップスケーラーモデル設定: {model}")
                return False

        return True

    def get_export_directory(self) -> Path:
        """directories.export_dir の設定値を取得します。"""
        dir_str = self.get_setting("directories", "export_dir", "export")  # デフォルトを"export"に
        return Path(dir_str)

    def get_database_directory(self) -> Path:
        """directories.database_dir の設定値を取得します。"""
        dir_str = self.get_setting("directories", "database_dir", "database")
        # 空文字列の場合もデフォルト値を使用
        if not dir_str:
            dir_str = "database"
        return Path(dir_str).resolve()

    def get_batch_results_directory(self) -> Path:
        """directories.batch_results_dir の設定値を取得します。"""
        dir_str = self.get_setting("directories", "batch_results_dir", "batch_results")
        return Path(dir_str)

    def update_image_processing_setting(self, key: str, value: Any) -> None:
        """image_processing セクション内の設定値を更新します。"""
        # update_setting を利用して更新
        self.update_setting("image_processing", key, value)

    def _mask_api_key(self, key: str) -> str:
        """APIキーを***でマスキングします。"""
        if not key or len(key) < 8:
            return "***"
        return f"{key[:4]}***{key[-4:]}"

    def get_available_providers(self) -> list[str]:
        """APIキーが設定されているプロバイダーを返します。"""
        providers = []
        if self.get_setting("api", "openai_key"):
            providers.append("openai")
        if self.get_setting("api", "claude_key"):
            providers.append("anthropic")
        if self.get_setting("api", "google_key"):
            providers.append("google")
        return providers

    def is_provider_available(self, provider: str) -> bool:
        """指定されたプロバイダーが利用可能かチェックします。"""
        provider_key_map = {
            "openai": "openai_key",
            "anthropic": "claude_key",
            "google": "google_key",
        }
        key_name = provider_key_map.get(provider.lower())
        if not key_name:
            return False
        api_key = self.get_setting("api", key_name)
        return bool(api_key and api_key.strip())

    def _create_default_config_file(self) -> dict[str, Any]:
        """デフォルト設定ファイルを作成し、設定辞書を返します。"""
        try:
            # デフォルト設定のコピーを作成
            from copy import deepcopy

            default_config = deepcopy(DEFAULT_CONFIG)

            # デフォルト設定ファイルを作成
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            write_config_file(default_config, self._config_path)

            logger.info("デフォルト設定ファイルを作成しました: %s", self._config_path)
            return default_config

        except Exception as e:
            logger.error("デフォルト設定ファイルの作成に失敗しました: %s", e, exc_info=True)
            # 作成に失敗した場合はメモリ上のみでデフォルト設定を使用
            from copy import deepcopy

            return deepcopy(DEFAULT_CONFIG)

    def get_shared_config(self) -> dict[str, Any]:
        """共有設定オブジェクトを取得します。DI用途で使用。"""
        return self._config

    # --- 他のウィジェットが必要とするメソッドもここに追加していく ---
