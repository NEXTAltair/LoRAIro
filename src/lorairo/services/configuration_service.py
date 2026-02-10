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
            self._config = shared_config
            logger.debug("共有設定オブジェクトを使用してConfigurationServiceを初期化しました")
        else:
            self._config = {}  # Initialize _config here
            try:
                self._config = get_config(self._config_path)
                logger.info("設定ファイルを読み込みました: {}", self._config_path)
            except FileNotFoundError:
                logger.warning(
                    "設定ファイルが見つかりません。デフォルト設定で新規作成します: {}", self._config_path
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
            logger.debug("設定値を更新しました: [{}] {} = {}", section, key, masked_value)
        else:
            logger.debug("設定値を更新しました: [{}] {} = {}", section, key, value)

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
            logger.info("設定をファイルに保存しました: {}", save_path)
            return True
        except OSError:
            logger.error("設定ファイルの保存中にIOエラーが発生しました: {}", save_path, exc_info=True)
            return False
        except Exception:
            logger.error("設定ファイルの保存中に予期せぬエラーが発生しました。", exc_info=True)
            return False

    def get_image_processing_config(self) -> dict[str, Any]:
        """image_processing セクションの設定を取得します。"""
        config = self._config.get("image_processing", {})
        return config if isinstance(config, dict) else {}

    def get_preferred_resolutions(self) -> list[tuple[int, int]]:
        """preferred_resolutions の設定を取得します。"""
        resolutions = self._config.get("preferred_resolutions", [])
        return resolutions if isinstance(resolutions, list) else []

    def get_upscaler_models(self) -> list[dict[str, Any]]:
        """upscaler_models の設定を取得します。"""
        models = self._config.get("upscaler_models", [])
        return models if isinstance(models, list) else []

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
            return str(default_name)

        # フォールバック: 最初のモデル名
        models = self.get_upscaler_models()
        if models:
            return str(models[0].get("name", ""))

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

    def get_api_keys(self) -> dict[str, str]:
        """全APIキーを取得（空文字列は除外）

        Returns:
            dict[str, str]: プロバイダー名 → APIキーのマッピング
                           空文字列のキーは除外される
        """
        api_config = self._config.get("api", {})
        return {k: v for k, v in api_config.items() if v and v.strip()}

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

            logger.info("デフォルト設定ファイルを作成しました: {}", self._config_path)
            return default_config

        except Exception as e:
            logger.error("デフォルト設定ファイルの作成に失敗しました: {}", e, exc_info=True)
            # 作成に失敗した場合はメモリ上のみでデフォルト設定を使用
            from copy import deepcopy

            return deepcopy(DEFAULT_CONFIG)

    def get_shared_config(self) -> dict[str, Any]:
        """共有設定オブジェクトを取得します。DI用途で使用。"""
        return self._config

    def get_available_annotation_models(self) -> list[str]:
        """利用可能なアノテーションモデルリストを取得

        image-annotator-libから利用可能なモデルリストを動的に取得します。

        Returns:
            list[str]: 利用可能なモデル名のリスト
        """
        try:
            from image_annotator_lib import list_available_annotators

            return list_available_annotators()
        except ImportError as e:
            logger.error(f"image-annotator-libのインポートに失敗しました: {e}")
            return []
        except Exception as e:
            logger.error(f"モデルリスト取得中にエラーが発生しました: {e}", exc_info=True)
            return []

    def get_default_annotation_model(self) -> str | None:
        """デフォルトアノテーションモデルを取得

        ConfigurationServiceから設定値を取得し、設定がない場合は
        利用可能なAPIキーに基づいてデフォルトモデルを自動選択します。

        Returns:
            str | None: デフォルトモデル名、取得できない場合はNone
        """
        # 設定ファイルから明示的なデフォルト設定を取得
        configured_default = self.get_setting("annotation", "default_model")
        if configured_default:
            return str(configured_default)

        # APIキーに基づいた自動選択
        api_keys = self.get_api_keys()

        # プロバイダー優先順位に基づくデフォルトモデルマッピング
        provider_defaults = {
            "openai_key": "gpt-4o-mini",
            "claude_key": "claude-3-haiku-20240307",
            "google_key": "gemini-1.5-flash-latest",
        }

        for key_name, default_model in provider_defaults.items():
            if key_name in api_keys:
                logger.info(f"利用可能なAPIキーに基づいてデフォルトモデルを選択: {default_model}")
                return default_model

        # フォールバック: 最初の利用可能なモデル
        available_models = self.get_available_annotation_models()
        if available_models:
            return available_models[0]

        logger.warning("デフォルトモデルを特定できませんでした")
        return None

    # --- 他のウィジェットが必要とするメソッドもここに追加していく ---
