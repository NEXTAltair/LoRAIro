# ストレージ管理仕様 (Storage Management Specification)

## 1. 概要

本ドキュメントは、LoRAiro プロジェクトにおけるファイルシステム操作およびデータストレージ管理機能の設計仕様を定義する。
現在の `FileSystemManager` クラスは責務が肥大化しているため、リファクタリングにより責務を分離し、保守性、テスト容易性を向上させることを目的とする。

## 2. 設計方針

-   **責務分離:** 各機能（低レベルファイル操作、プロジェクト構造管理、画像保存、バッチ処理、エクスポート、設定永続化）を独立したクラス/モジュールに分割する。
-   **依存性注入:** クラスが必要とする依存オブジェクト（パス設定、他のサービスなど）は、コンストラクタやメソッド引数を通じて外部から注入する。`initialize` のような明示的な初期化ステップを避ける。
-   **状態最小化:** クラス内の状態を極力減らし、メソッドが必要な情報を引数で受け取るように設計する。
-   **パス操作統一:** ファイルパス操作は `pathlib` モジュールに統一する。
-   **エラーハンドリング:** 各操作で発生しうるエラーを具体的に定義し、適切にハンドリングまたは上位に伝播させる。

## 3. コンポーネント設計

### 3.1. `FileSystemUtils` (モジュール: `lorairo.utils.filesystem`)

-   **責務:** 低レベルで汎用的なファイルシステム操作を提供する。特定のプロジェクト構造には依存しない。
-   **主要関数:**
    -   `create_directory(path: Path, parents: bool = True, exist_ok: bool = True) -> None`: ディレクトリを作成する。
    -   `copy_file(src: Path, dst: Path, buffer_size: int = 64 * 1024 * 1024) -> None`: ファイルをコピーする (タイムスタンプ維持)。
    -   `find_files_recursively(directory: Path, pattern: str) -> list[Path]`: 指定ディレクトリ以下を再帰的に検索し、パターンに一致するファイルリストを返す。
    -   `get_file_size(path: Path) -> int`: ファイルサイズを取得する。
    -   `path_exists(path: Path) -> bool`: パスが存在するか確認する。
    -   `ensure_unique_path(path: Path) -> Path`: 指定パスが既に存在する場合、連番 (`_1`, `_2`, ...) を付与して一意なパスを返す。

### 3.2. `ProjectStructure` (クラス: `lorairo.storage.structure.ProjectStructure`)

-   **責務:** プロジェクト固有のディレクトリ構造を定義し、関連するパスを生成する。
-   **コンストラクタ:**
    -   `__init__(self, output_dir: Path, target_resolution: int)`
-   **主要プロパティ/メソッド:**
    -   `output_dir: Path`
    -   `target_resolution: int`
    -   `image_dataset_dir() -> Path`: `output_dir / "image_dataset"`
    -   `original_images_base_dir() -> Path`: `image_dataset_dir / "original_images"`
    -   `resolution_base_dir() -> Path`: `image_dataset_dir / str(target_resolution)`
    -   `get_daily_subdir_path(base_dir: Path, date: datetime | None = None) -> Path`: 日付ベース (`YYYY/MM/DD`) のサブディレクトリパスを生成する。
    -   `original_images_dir(date: datetime | None = None) -> Path`: 特定日のオリジナル画像保存ディレクトリパス。
    -   `resized_images_dir(date: datetime | None = None) -> Path`: 特定日のリサイズ済み画像保存ディレクトリパス。
    -   `batch_request_dir() -> Path`: `output_dir / "batch_request_jsonl"`
    -   `get_next_sequence_number(directory: Path, prefix: str, extension: str) -> int`: ディレクトリ内のファイル命名規則に基づき、次の連番を取得する。

### 3.3. `ImageStorage` (クラス: `lorairo.storage.image.ImageStorage`)

-   **責務:** オリジナル画像および処理済み (リサイズ済み) 画像の保存と、画像情報の取得を行う。
-   **コンストラクタ:**
    -   `__init__(self, project_structure: ProjectStructure, fs_utils: FileSystemUtils)`
-   **主要メソッド:**
    -   `save_original_image(self, src_path: Path, date: datetime | None = None) -> Path`: 元画像を対応する日付ディレクトリにコピーして保存し、保存先パスを返す。ファイル名衝突時は `ensure_unique_path` を利用。
    -   `save_processed_image(self, image: Image.Image, original_path: Path, date: datetime | None = None) -> Path`: 処理済み画像を対応する日付ディレクトリに連番付き (`{parent_dir_name}_{seq:05d}.webp`) で保存し、保存先パスを返す。
    -   `get_image_info(self, image_path: Path) -> dict[str, Any]`: 画像ファイルからメタデータ (サイズ、フォーマット、モード、色空間など) を取得する。

### 3.4. `BatchRequestProcessor` (クラス: `lorairo.storage.batch.BatchRequestProcessor`)

-   **責務:** OpenAI バッチ API リクエスト用の JSONL ファイルの作成、データ追記、およびサイズに基づく分割を行う。
-   **コンストラクタ:**
    -   `__init__(self, project_structure: ProjectStructure, fs_utils: FileSystemUtils)`
-   **主要メソッド:**
    -   `create_batch_request_file(self) -> Path`: 新しいバッチリクエストファイル (`batch_request.jsonl`) のパスを生成・確保する。
    -   `append_request(self, file_path: Path, data: dict[str, Any]) -> None`: 指定された JSONL ファイルにデータを追記する。
    -   `split_if_needed(self, jsonl_path: Path, max_size_mb: int = 96) -> list[Path]`: JSONL ファイルが指定サイズを超えていれば、複数のファイルに分割し、分割後のファイルパスリストを返す。分割不要なら元のパスを含むリストを返す。

### 3.5. `DatasetExporter` (クラス: `lorairo.storage.export.DatasetExporter`)

-   **責務:** 処理済み画像とそのメタデータ (タグ、キャプション) を、学習に適した形式 (テキストファイル、JSON) でエクスポートする。
-   **コンストラクタ:**
    -   `__init__(self, fs_utils: FileSystemUtils)`
-   **主要メソッド:**
    -   `export_to_txt(self, image_data: dict, save_dir: Path, merge_caption: bool = False) -> None`: 画像データ (パス、タグ、キャプション) を受け取り、指定ディレクトリに画像ファイル本体と `.txt` (タグ), `.caption` ファイルを出力する。
    -   `export_to_json(self, image_data: dict, save_dir: Path, metadata_filename: str = "meta_data.json") -> None`: 画像データを受け取り、指定ディレクトリに画像ファイル本体をコピーし、`metadata_filename` に JSON 形式でメタデータを追記する。

### 3.6. `ConfigPersistence` (モジュール: `lorairo.config.persistence` など)

-   **責務:** アプリケーション設定を TOML ファイルに永続化・読み込みを行う。 (既存の仕組みがあればそれに統合)
-   **主要関数:**
    -   `save_toml_config(config: dict, filepath: Path) -> None`
    -   `load_toml_config(filepath: Path) -> dict`

## 4. 移行計画

1.  上記コンポーネント (`FileSystemUtils`, `ProjectStructure` から順に) を実装する。
2.  `FileSystemManager` の各メソッドに対応する新しいコンポーネントのメソッドを呼び出すように、`FileSystemManager` 内部を修正する (アダプターパターン的な一時対応)。
3.  `FileSystemManager` を利用している他のモジュールを、新しいコンポーネントを直接利用するように段階的に修正する。
4.  すべての依存関係が解消されたら `FileSystemManager` クラスを削除する。

## 5. 注意事項

-   エラーハンドリングの詳細は各コンポーネントの実装時に具体化する。
-   既存のログ機構 (`logger`) を適切に引き継ぐ。 