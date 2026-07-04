"""DBマネージャー (高レベルインターフェース)"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text
from sqlalchemy.engine import Result
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..filesystem import FileSystemManager
from ..utils.log import logger
from ..utils.tools import calculate_phash
from .filter_criteria import ImageFilterCriteria
from .repository.annotation_record import AnnotationRepository
from .repository.error_record import ErrorRecordRepository
from .repository.image import ImageRepository, PhashClassification
from .repository.model import ModelRepository
from .repository.project import ProjectRepository
from .repository.provider_batch import ProviderBatchRepository
from .schema import (
    REJECT_REASON_INCORRECT,
    AnnotationsDict,
    CaptionAnnotationData,
    RatingAnnotationData,
    ScoreAnnotationData,
    TagAnnotationData,
)

if TYPE_CHECKING:
    from ..services.configuration_service import ConfigurationService


class RegistrationOutcome(StrEnum):
    """画像登録の最終 outcome 分類 (ADR 0061 §4, #633)。

    pHash 分類結果 (`PhashClassification`) を全登録経路で同じ意味の統計値に
    マッピングするための outcome。GUI worker / API / direct のいずれも本 enum を
    起点に `registered` / `variant` / `skipped` / `failed` を集計する。

    - ``REGISTERED``: 新規画像 (候補なし) を新規行として登録した。
    - ``VARIANT``: 同一 pHash だが属性差のある別版を新規行として登録した。
    - ``DUPLICATE``: 既存画像と同一と判定し、既存行へ寄せた (新規行を作らない)。
    - ``FAILED``: 入力起因のスキップ (デコード失敗 / 保存失敗等) で登録できなかった。
    """

    REGISTERED = "registered"
    VARIANT = "variant"
    DUPLICATE = "duplicate"
    FAILED = "failed"


@dataclass(frozen=True)
class RegistrationSideEffectResult:
    """統一登録エントリの結果 (ADR 0061 §4, #633)。

    Attributes:
        outcome: 登録 outcome 分類。
        image_id: 関連付けられた画像 ID。失敗時は ``None``。
            duplicate は既存 ID、variant / registered は新規 ID。
        metadata: 画像メタデータ。失敗時は ``None``。
    """

    outcome: RegistrationOutcome
    image_id: int | None
    metadata: dict[str, Any] | None


class ImageDatabaseManager:
    """画像データベース操作の高レベルインターフェースを提供するクラス。

    ADR 0035 段階 6 (#423): legacy `db_repository.ImageRepository` god class を撤廃し、
    Aggregate 単位 Repository (`ImageRepository` / `AnnotationRepository` /
    `ModelRepository` / `ProjectRepository` / `ErrorRecordRepository` /
    `ProviderBatchRepository`) を composition で保持する設計に移行。
    """

    def __init__(
        self,
        config_service: "ConfigurationService",
        fsm: FileSystemManager | None = None,
        *,
        session_factory: Any | None = None,
        model_repo: ModelRepository | None = None,
        project_repo: ProjectRepository | None = None,
        error_record_repo: ErrorRecordRepository | None = None,
        image_repo: ImageRepository | None = None,
        annotation_repo: AnnotationRepository | None = None,
        provider_batch_repo: ProviderBatchRepository | None = None,
    ):
        """ImageDatabaseManagerのコンストラクタ。

        ADR 0035 段階 6 (#423): legacy facade (`db_repository.ImageRepository`) が
        撤廃されたため、`repository` 引数は廃止。Manager は Aggregate 単位の
        Repository を composition で保持し、内部呼び出しは `self.X_repo.method()`
        で行う。テスト時は各 Repo を Mock 注入することで独立性を保てる。

        Args:
            config_service: 設定サービスインスタンス。
            fsm: ファイルシステムマネージャー（オプション）。
            session_factory: SQLAlchemy セッションファクトリ。None の場合は
                `db_core.DefaultSessionLocal` を流用する。Repo を 1 つも指定しない
                場合に本値で全 Repo を生成する。Repo を個別に Mock 注入する場合は
                指定不要。
            model_repo: Model 関連の Repository (ADR 0035 段階 1)。
            project_repo: Project 関連の Repository (ADR 0035 段階 2)。
            error_record_repo: ErrorRecord 関連の Repository (ADR 0035 段階 3)。
            image_repo: Image / ProcessedImage / FilenameAlias の Repository
                (ADR 0035 段階 4)。
            annotation_repo: Annotation 書き込み + 外部 tag_db 統合の Repository
                (ADR 0035 段階 5)。
            provider_batch_repo: Provider Batch API job/item/artifact の Repository
                (ADR 0035 段階 6)。

        """
        self.config_service = config_service
        self.fsm = fsm
        if session_factory is None:
            for repo in (
                image_repo,
                model_repo,
                project_repo,
                error_record_repo,
                annotation_repo,
                provider_batch_repo,
            ):
                session_factory = getattr(repo, "session_factory", None)
                if session_factory is not None:
                    break
            else:
                from .db_core import DefaultSessionLocal

                session_factory = DefaultSessionLocal
        # ADR 0035 段階 1-6: Aggregate 単位 Repository を composition で保持。
        # None の場合は session_factory を共有して生成する。
        self.model_repo: ModelRepository = model_repo or ModelRepository(session_factory=session_factory)
        self.project_repo: ProjectRepository = project_repo or ProjectRepository(
            session_factory=session_factory
        )
        self.error_record_repo: ErrorRecordRepository = error_record_repo or ErrorRecordRepository(
            session_factory=session_factory
        )
        self.image_repo: ImageRepository = image_repo or ImageRepository(session_factory=session_factory)
        # AnnotationRepository は __init__ 内で MergedTagReader / TagRegisterService の
        # 遅延初期化を試みる (失敗時は warning ログ + None でグレースフルデグラデーション)。
        self.annotation_repo: AnnotationRepository = annotation_repo or AnnotationRepository(
            session_factory=session_factory
        )
        self.provider_batch_repo: ProviderBatchRepository = provider_batch_repo or ProviderBatchRepository(
            session_factory=session_factory
        )
        self._cached_project_id: int | None = None
        logger.info("ImageDatabaseManager initialized.")

    @classmethod
    def create_default(cls) -> "ImageDatabaseManager":
        """デフォルト設定でインスタンスを作成するファクトリメソッド"""
        from ..services.configuration_service import ConfigurationService

        config_service = ConfigurationService()
        return cls(config_service)

    # __enter__ と __exit__ はリポジトリがセッション管理するため、ここでは不要になることが多い
    # 必要であれば、リポジトリのセッションファクトリを使う処理を追加できる

    def _get_current_project_id(self) -> int | None:
        """現在接続中の DB のプロジェクト ID を取得してキャッシュする。

        .lorairo-project メタデータから logical name を読み、ensure_project() で
        projects テーブルに行を確保してからそのIDを返す。
        project root が解決できない場合や DB の論理的失敗 (SQLAlchemyError) は
        None を返し、project_id 未設定のまま挿入される。
        予期しない例外は呼び出し元に伝播する。
        """
        if self._cached_project_id is not None:
            return self._cached_project_id

        import json

        from .db_core import get_current_project_root

        try:
            project_root = get_current_project_root()
        except (RuntimeError, OSError, ValueError):
            # project root が未設定 / 解決不能の場合は project_id なしで挿入を続行
            logger.debug(
                "プロジェクト root 解決に失敗 — project_id は未設定のまま挿入します", exc_info=True
            )
            return None

        metadata_file = project_root / ".lorairo-project"
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            # JSON が dict でない場合 (list / string 等の malformed metadata) は AttributeError になる
            project_name = metadata.get("name") or project_root.name
        except (OSError, json.JSONDecodeError, ValueError, AttributeError):
            project_name = project_root.name

        try:
            # ADR 0035 段階 2 (#423): injected project_repo 経由で呼び出し DI contract を維持。
            self._cached_project_id = self.project_repo.ensure_project(project_name, project_root)
        except SQLAlchemyError:
            logger.error(
                f"ensure_project 失敗 (project_name={project_name}) — project_id 未設定で続行",
                exc_info=True,
            )
            return None

        return self._cached_project_id

    def _prepare_image_metadata(
        self,
        image_path: Path,
        fsm: FileSystemManager,
    ) -> tuple[dict[str, Any], str] | None:
        """画像メタデータの準備（メタデータ取得 + pHash計算 + 情報追加）。

        ADR 0061 §3: 保存 (`save_original_image`) は重複/別版分類後に行うため、
        本メソッドではストレージ保存を行わない。`stored_image_path` は分類後に
        `register_original_image` 側で追加する。

        Args:
            image_path: オリジナル画像のパス。
            fsm: ファイルシステム操作用マネージャー (画像情報取得に使用)。

        Returns:
            成功時は (prepared_metadata, phash)、失敗時は None。
            `prepared_metadata` には `stored_image_path` はまだ含まれない。

        Raises:
            ValueError: 画像情報が取得できない場合。
            FileNotFoundError: pHash計算に失敗した場合。

        """
        # 1. 画像情報を取得
        original_metadata = fsm.get_image_info(image_path)
        if not original_metadata:
            logger.error(f"画像情報の取得に失敗: {image_path}")
            raise ValueError(f"画像情報の取得に失敗: {image_path}")

        # 2. pHash を計算
        try:
            phash = calculate_phash(image_path)
        except (ValueError, FileNotFoundError) as e:
            logger.warning(f"画像をスキップ: {e}")
            raise

        # 3. メタデータに情報を追加 (保存は分類後: ADR 0061)
        image_uuid = str(uuid.uuid4())
        original_metadata.update(
            {
                "uuid": image_uuid,
                "phash": phash,
                "original_image_path": str(image_path),
            },
        )

        return original_metadata, phash

    def register_original_image(
        self,
        image_path: Path,
        fsm: FileSystemManager,
    ) -> tuple[int, dict[str, Any]] | None:
        """オリジナル画像をDBに登録する（オーケストレータ）。

        ADR 0061: pHash 完全一致を候補とし、追加属性 (width / height / has_alpha /
        is_grayscale_like) の比較で「重複 (duplicate)」「別版 (variant)」「新規 (new)」に
        分類する。保存 (`save_original_image`) は分類結果が別版/新規のときだけ行い、
        重複時はファイルコピーを残さない (#632)。

        Args:
            image_path: オリジナル画像のパス。
            fsm: ファイルシステム操作用マネージャー。

        Returns:
            登録成功時 (新規 / 別版) は (image_id, original_metadata)、
            重複時は (existing_image_id, existing_metadata)、
            入力起因の失敗 (ValueError / FileNotFoundError / OSError) 時は None。
            戻り値の公開契約 (image_id, metadata) は後方互換に保つ。分類結果は
            metadata 内の `phash_classification` キーで付加情報として伝える
            (副作用の全経路統一は #633 のスコープ)。
            OSError には PIL の UnidentifiedImageError や PermissionError 等の
            ファイル読み取り / デコード失敗が含まれる (1 ファイル不正で worker 全体を
            止めないための per-file tolerance)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元 (Worker boundary)
                に伝播させる。Worker 層で error_occurred シグナルに変換される。

        """
        try:
            # 1. メタデータを準備 (この時点では保存しない: ADR 0061 §3)
            prepare_result = self._prepare_image_metadata(image_path, fsm)
            if prepare_result is None:
                return None
            original_metadata, phash = prepare_result
        except (ValueError, FileNotFoundError, OSError):
            # 入力起因のスキップは正常系扱い (既にログ出力済み)
            return None

        # 2. pHash 候補を取得し、属性比較で重複/別版/新規に分類 (ADR 0061 §1-2)
        # 分類は DB アクセスを伴わない純粋ロジック (classmethod) なのでクラス経由で呼ぶ。
        candidates = self.image_repo.find_phash_candidates(phash)
        classification, existing_id = ImageRepository.classify_phash_candidate(
            original_metadata, candidates
        )

        # 3. 重複確定: 保存せず既存メタデータを返す (#632: ファイルコピーを残さない)
        if classification is PhashClassification.DUPLICATE and existing_id is not None:
            return self._handle_duplicate_image(existing_id, image_path, fsm)

        # 4. 新規 / 別版: 保存 + 挿入 + サムネイル生成を委譲する (ADR 0061 §3)
        return self._persist_new_or_variant(image_path, fsm, original_metadata, phash, classification)

    def register_image_with_side_effects(
        self,
        image_path: Path,
        fsm: FileSystemManager,
        *,
        associated_annotations: dict[str, Any] | None = None,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> RegistrationSideEffectResult:
        """画像を登録し、分類結果駆動の副作用を全経路統一ルールで適用する (ADR 0061 §4, #633)。

        重複 / 別版 / 新規それぞれの副作用 (関連 ``.txt`` / ``.caption`` の取り込み先・
        filename alias 登録・512px 生成) を本メソッド 1 箇所で定義する。GUI worker /
        API / direct のいずれの登録経路もこのエントリへ寄せることで、同一入力に対し
        同一の副作用と統計値が得られる。

        副作用ルール:
        - **新規 (registered)**: 新規行を作り、関連ファイルを新規 ID へ取り込む。
          512px はオリジナル登録時に生成済み。alias は登録しない。
        - **別版 (variant)**: 同一 pHash でも新規行を作り、関連ファイルは
          *別版レコード* (新規 ID) へ取り込む。alias は登録しない。
        - **重複 (duplicate)**: 既存行へ寄せ、関連ファイルは *既存レコード* へ
          取り込む。バッチインポート照合用に filename alias を登録する。
        - **失敗 (failed)**: 何も取り込まず outcome=FAILED を返す。

        Args:
            image_path: 登録対象の画像パス。
            fsm: ファイルシステム操作用マネージャー。
            associated_annotations: 事前読み込み済みの関連アノテーション
                (``SidecarAnnotationReader.get_existing_annotations`` の戻り値)。
                None の場合は本メソッド内で読み込む。
            tag_id_cache: 正規化済みタグ → tag_id のキャッシュ (N+1 回避用)。

        Returns:
            RegistrationSideEffectResult: outcome / image_id / metadata。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元 (Worker boundary) に
                伝播させる。

        """
        result = self.register_original_image(image_path, fsm)
        if result is None:
            logger.error(f"画像登録失敗: {image_path}")
            return RegistrationSideEffectResult(RegistrationOutcome.FAILED, None, None)

        image_id, metadata = result
        classification = metadata.get("phash_classification")
        outcome = self._classification_to_outcome(classification)

        # 関連 .txt / .caption を分類結果に従った image_id へ取り込む。
        # variant は新規 ID、duplicate は既存 ID。いずれも result の image_id がターゲット。
        self._import_associated_files(
            image_path,
            image_id,
            annotations=associated_annotations,
            tag_id_cache=tag_id_cache,
        )

        # filename alias は重複時のみ登録する (バッチインポートの custom_id 照合用)。
        # 別版 / 新規は自身の filename を持つため alias 不要。
        if outcome is RegistrationOutcome.DUPLICATE:
            self._register_filename_alias(image_id, image_path.stem)

        return RegistrationSideEffectResult(outcome, image_id, metadata)

    @staticmethod
    def _classification_to_outcome(classification: object) -> RegistrationOutcome:
        """pHash 分類結果文字列を登録 outcome へマッピングする (#633)。

        Args:
            classification: ``metadata["phash_classification"]`` の値
                (``"duplicate"`` / ``"variant"`` / ``"new"`` または欠落)。

        Returns:
            対応する RegistrationOutcome。未知 / 欠落は REGISTERED 扱い。

        """
        if classification == PhashClassification.DUPLICATE.value:
            return RegistrationOutcome.DUPLICATE
        if classification == PhashClassification.VARIANT.value:
            return RegistrationOutcome.VARIANT
        return RegistrationOutcome.REGISTERED

    def _register_filename_alias(self, image_id: int, stem: str) -> None:
        """filename alias を登録する。DB 未初期化等の失敗は握り潰す (#633)。

        重複スキップ画像の filename をバッチインポートの custom_id 照合に使えるよう
        登録する。失敗しても登録 outcome は変わらないため warning に落として続行する。

        Args:
            image_id: alias を紐付ける画像 ID。
            stem: 登録するファイル名 stem。

        """
        try:
            self.image_repo.add_filename_alias(image_id, stem)
        except SQLAlchemyError as e:
            logger.warning(f"エイリアス登録失敗 (登録 outcome は継続): {stem}, {e}")

    def _import_associated_files(
        self,
        image_path: Path,
        image_id: int,
        *,
        annotations: dict[str, Any] | None = None,
        tag_id_cache: dict[str, int | None] | None = None,
    ) -> None:
        """画像に関連する .txt / .caption を読み込み、指定 image_id へ保存する (#633)。

        分類結果駆動の副作用統一 (ADR 0061 §4) の取り込み実体。GUI worker /
        API / direct のいずれの経路もこの 1 箇所を通すことで取り込み先 (image_id) と
        挙動を揃える。

        Args:
            image_path: 関連ファイル探索の起点となる画像パス。
            image_id: 取り込み先の画像 ID (分類結果に従い caller が解決済み)。
            annotations: 事前読み込み済みアノテーション。None なら本メソッドで読む。
            tag_id_cache: 正規化済みタグ → tag_id のキャッシュ。

        """
        from ..annotation.sidecar_reader import SidecarAnnotationReader

        if annotations is None:
            annotations = SidecarAnnotationReader().get_existing_annotations(image_path)
        if not annotations:
            return

        from genai_tag_db_tools.utils.cleanup_str import TagCleaner

        raw_tags = annotations.get("tags", [])
        tags = [tag for tag in raw_tags if isinstance(tag, str)] if isinstance(raw_tags, list) else []
        if tags:
            tags_data: list[TagAnnotationData] = [
                {
                    "tag_id": (
                        tag_id_cache.get(TagCleaner.clean_format(tag).strip()) if tag_id_cache else None
                    ),
                    "model_id": None,
                    "tag": tag,
                    "confidence_score": None,
                    "existing": True,
                    "is_edited_manually": False,
                }
                for tag in tags
            ]
            self.save_tags(image_id, tags_data)
            logger.debug(f"関連タグを取り込み: {image_path.name} - {len(tags)}件 (ID={image_id})")

        raw_captions = annotations.get("captions", [])
        captions = [c for c in raw_captions if isinstance(c, str)] if isinstance(raw_captions, list) else []
        if captions:
            captions_data: list[CaptionAnnotationData] = [
                {
                    "model_id": None,
                    "caption": caption,
                    "existing": False,
                    "is_edited_manually": False,
                }
                for caption in captions
            ]
            self.save_captions(image_id, captions_data)
            logger.debug(f"関連キャプションを取り込み: {image_path.name} (ID={image_id})")

    def _persist_new_or_variant(
        self,
        image_path: Path,
        fsm: FileSystemManager,
        original_metadata: dict[str, Any],
        phash: str,
        classification: PhashClassification,
    ) -> tuple[int, dict[str, Any]] | None:
        """新規 / 別版分類された画像を保存・挿入し、サムネイルを生成する (ADR 0061 §3)。

        保存 → DB 挿入 (classification-aware 重複ガード込み) → 512px 生成の順で実行する。
        並行レースで挿入直前に重複が確定した場合は保存済みコピーを cleanup し、重複扱い
        (既存メタデータ返却) に切り替える。

        Args:
            image_path: 登録対象の画像パス。
            fsm: ファイルシステム操作用マネージャー。
            original_metadata: `_prepare_image_metadata` が組んだメタデータ (保存前)。
            phash: 計算済み pHash (ログ用)。
            classification: 事前分類結果 (NEW または VARIANT)。

        Returns:
            登録成功時は (image_id, metadata)、保存失敗時は None。
            レースで重複確定したときは既存 (existing_id, existing_metadata)。

        """
        # save_original_image は copy/storage 初期化失敗で OSError / FileNotFoundError /
        # RuntimeError 等を投げ得る。メタデータ読み取りと copy の間にソースが消える等の
        # 入力起因の失敗は per-file tolerance (None 返し) を維持する。
        try:
            db_stored_original_path = fsm.save_original_image(image_path)
        except (OSError, FileNotFoundError, ValueError, RuntimeError) as e:
            logger.warning(
                f"オリジナル画像のストレージ保存に失敗したためスキップ: {image_path}, Error: {e}"
            )
            return None
        if not db_stored_original_path:
            logger.error(f"オリジナル画像のストレージ保存に失敗: {image_path}")
            return None
        original_metadata["stored_image_path"] = str(db_stored_original_path)
        original_metadata["phash_classification"] = classification.value

        # project_id を付与して project-scoped filter を有効化
        project_id = self._get_current_project_id()
        if project_id is not None:
            original_metadata["project_id"] = project_id

        # add_original_image が挿入直前に classification-aware 重複ガードを実行する。
        # 並行登録レースで分類後・挿入前に同一の重複が割り込むと was_inserted=False で
        # 既存 ID が返る。その場合は保存済みファイルを孤児化しないよう cleanup し、
        # 重複扱い (既存メタデータ返却) に切り替える (ADR 0061 §3, PR #647 review)。
        try:
            image_id, was_inserted = self.image_repo.add_original_image(original_metadata)
        except SQLAlchemyError:
            # DB 挿入失敗が確定したら保存済みファイルを削除し孤児を残さない (ADR 0061 §3 cleanup 規約)
            self._cleanup_orphan_original(db_stored_original_path)
            raise

        if not was_inserted:
            # レースで重複確定: 保存した第 2 コピーを削除して既存メタデータを返す。
            logger.debug(f"並行登録レースで重複確定: 保存済みコピーを削除し既存IDを返します: ID={image_id}")
            self._cleanup_orphan_original(db_stored_original_path)
            return self._handle_duplicate_image(image_id, image_path, fsm)

        if classification is PhashClassification.VARIANT:
            logger.info(
                f"別版画像を新規登録しました (同一pHash): ID={image_id}, Path={image_path}, pHash={phash}"
            )
        else:
            logger.debug(f"オリジナル画像を登録しました: ID={image_id}, Path={image_path}")

        # 512px サムネイル画像の自動生成 (best-effort: 生成失敗で登録自体は失敗させない)
        try:
            self._generate_thumbnail_512px(image_id, db_stored_original_path, original_metadata, fsm)
        except (SQLAlchemyError, OSError, ValueError, RuntimeError) as e:
            logger.warning(
                f"512px サムネイル生成に失敗しましたが、処理を続行します: {image_path}, Error: {e}",
            )

        return image_id, original_metadata

    @staticmethod
    def _cleanup_orphan_original(stored_path: Path) -> None:
        """DB 未登録が確定した保存済みオリジナル画像を削除する (ADR 0061 §3)。

        保存は成功したが DB 挿入に失敗した場合、ストレージ上に孤児ファイルが
        残らないよう削除する。削除自体の失敗 (OSError) は best-effort で握り潰す
        (主たる例外を上書きしないため)。

        Args:
            stored_path: 削除対象の保存済みオリジナル画像パス。

        """
        try:
            stored_path.unlink(missing_ok=True)
            logger.debug(f"DB 登録失敗のため保存済みオリジナルを削除しました: {stored_path}")
        except OSError as e:
            logger.warning(f"孤児オリジナルファイルの削除に失敗 (処理続行): {stored_path}, Error: {e}")

    def _handle_duplicate_image(
        self,
        existing_id: int,
        image_path: Path,
        fsm: FileSystemManager,
    ) -> tuple[int, dict[str, Any]]:
        """重複検出時の処理。512pxサムネイル生成と既存メタデータ返却を行う。

        Args:
            existing_id: 既存画像のID。
            image_path: 重複元の画像パス。
            fsm: ファイルシステム操作用マネージャー。

        Returns:
            (existing_image_id, existing_metadata) のタプル。

        """
        logger.warning(f"重複画像を検出 (pHash): 既存ID={existing_id}, Path={image_path}")

        # 重複画像の 512px 画像生成は best-effort: 失敗しても既存メタデータ返却の主処理は止めない。
        # check_processed_image_exists / _generate_thumbnail_512px は SQLAlchemyError / OSError /
        # ValueError / RuntimeError を投げ得るので、これらに限って握りつぶし他は伝播させる。
        try:
            existing_512px = self.check_processed_image_exists(existing_id, 512)
            if not existing_512px:
                logger.info(f"重複画像に512px画像が存在しないため、生成を試行します: ID={existing_id}")
                existing_metadata = self.image_repo.get_image_metadata(existing_id)
                if existing_metadata:
                    stored_path = Path(existing_metadata["stored_image_path"])
                    self._generate_thumbnail_512px(existing_id, stored_path, existing_metadata, fsm)
            else:
                logger.debug(f"重複画像に512px画像が既に存在します: ID={existing_id}")
        except (SQLAlchemyError, OSError, ValueError, RuntimeError) as e:
            logger.warning(
                f"重複画像の512px生成チェック中にエラー (処理続行): ID={existing_id}, Error: {e}",
            )

        # 既存のメタデータを取得して返す
        existing_metadata = self.image_repo.get_image_metadata(existing_id)
        if existing_metadata is None:
            logger.warning(f"既存画像のメタデータが取得できませんでした: ID={existing_id}")
            existing_metadata = {}

        # 重複時も分類結果を metadata に付加する (#633: 副作用の分類結果駆動)。
        # 全経路の呼び出し元が phash_classification キーで outcome を判定できるようにする。
        existing_metadata["phash_classification"] = PhashClassification.DUPLICATE.value

        logger.debug(f"重複画像のメタデータを返します: ID={existing_id}")
        return existing_id, existing_metadata

    def _generate_thumbnail_512px(
        self,
        image_id: int,
        original_path: Path,
        original_metadata: dict[str, Any],
        fsm: FileSystemManager,
    ) -> None:
        """512px サムネイル画像を生成し、データベースに登録するオーケストレータ。

        Args:
            image_id (int): 元画像のID
            original_path (Path): 保存されたオリジナル画像のパス
            original_metadata (dict[str, Any]): 元画像のメタデータ
            fsm (FileSystemManager): ファイルシステムマネージャー

        """
        original_width = original_metadata.get("width", 0)
        original_height = original_metadata.get("height", 0)
        logger.debug(f"512px画像生成開始: ID={image_id}, 元サイズ={original_width}x{original_height}")

        try:
            # ステップ1: 画像処理と保存
            result = self._create_and_save_thumbnail(image_id, original_path, original_metadata, fsm)
            if result is None:
                # 画像処理に失敗（スキップ扱い）
                return

            processed_path, processing_metadata = result

            # ステップ2: DB登録
            processed_id = self._register_thumbnail_in_db(
                image_id, processed_path, processing_metadata, original_path, fsm
            )

            if processed_id:
                logger.debug(
                    f"512px サムネイル画像を生成・登録しました: 元画像ID={image_id}, "
                    f"処理済みID={processed_id}, Path={processed_path.name}",
                )
            else:
                logger.warning(
                    f"512px サムネイル画像の生成は成功しましたが、DB登録に失敗しました: 元画像ID={image_id}",
                )

        except (SQLAlchemyError, OSError, ValueError, RuntimeError) as e:
            logger.error(
                f"512px サムネイル生成中にエラーが発生しました: 元画像ID={image_id}, Error: {e}",
                exc_info=True,
            )
            raise

    def _create_and_save_thumbnail(
        self,
        image_id: int,
        original_path: Path,
        original_metadata: dict[str, Any],
        fsm: FileSystemManager,
    ) -> tuple[Path, dict[str, Any]] | None:
        """画像処理と保存を行う。

        ImageProcessingManager を使用して512px解像度で処理（アップスケール対応）し、
        処理済み画像をファイルシステムに保存します。

        Args:
            image_id (int): 元画像のID（ログ出力用）
            original_path (Path): 保存されたオリジナル画像のパス
            original_metadata (dict[str, Any]): 元画像のメタデータ
            fsm (FileSystemManager): ファイルシステムマネージャー

        Returns:
            tuple[Path, dict[str, Any]] | None: (処理済み画像パス, 処理メタデータ) の
            タプル。処理不可な場合は None。

        """
        from ..image_transforms.image_processor import ImageProcessingManager

        target_resolution = 512
        preferred_resolutions = [(512, 512)]

        # ImageProcessingManager を作成（ConfigurationService注入対応）
        ipm = ImageProcessingManager(fsm, target_resolution, preferred_resolutions, self.config_service)

        # アップスケーラー設定を取得
        image_processing_config = self.config_service.get_image_processing_config()
        upscaler = image_processing_config.get("upscaler", "RealESRGAN_x4plus")

        # 画像処理を実行
        has_alpha = original_metadata.get("has_alpha", False)
        mode = original_metadata.get("mode", "RGB")
        processed_image, processing_metadata = ipm.process_image(
            original_path,
            has_alpha,
            mode,
            upscaler=upscaler,
        )

        if not processed_image:
            # アップスケール後もサイズ不足等で処理できなかった場合
            logger.debug(
                f"512pxサムネイル生成をスキップ: 元画像ID={image_id} (画像が小さすぎるか処理不可)",
            )
            return None

        # 512px画像をファイルシステムに保存
        processed_path = fsm.save_processed_image(processed_image, original_path, target_resolution)

        return processed_path, processing_metadata

    def _register_thumbnail_in_db(
        self,
        image_id: int,
        processed_path: Path,
        processing_metadata: dict[str, Any],
        original_path: Path,
        fsm: FileSystemManager,
    ) -> int | None:
        """処理済み画像をデータベースに登録する。

        処理済み画像のメタデータを取得し、アップスケール情報を付加してから、
        register_processed_image を使用してDB登録します。

        Args:
            image_id (int): 元画像のID
            processed_path (Path): 処理済み画像の保存パス
            processing_metadata (dict[str, Any]): 画像処理メタデータ（アップスケール情報含む）
            original_path (Path): オリジナル画像パス（ログ出力用）
            fsm (FileSystemManager): ファイルシステムマネージャー

        Returns:
            int | None: 登録された処理済み画像ID。登録失敗時は None。

        """
        # 処理済み画像のメタデータを取得
        processed_metadata = fsm.get_image_info(processed_path)

        # アップスケール情報をメタデータに追加
        if processing_metadata.get("was_upscaled", False):
            processed_metadata["upscaler_used"] = processing_metadata.get("upscaler_used")
            logger.info(
                f"512px生成時にアップスケールを実行: {processing_metadata.get('upscaler_used')}",
            )

        # データベースに512px画像を登録
        processed_id = self.register_processed_image(image_id, processed_path, processed_metadata)

        return processed_id

    def register_processed_image(
        self,
        image_id: int,
        processed_path: Path,
        info: dict[str, Any],
    ) -> int | None:
        """処理済み画像を保存し、メタデータをデータベースに登録します。

        Args:
            image_id (int): 元画像のID。
            processed_path (Path): 処理済み画像の保存パス。
            info (dict[str, Any]): 処理済み画像のメタデータ (width, height などを含む)。

        Returns:
            int | None: 保存された処理済み画像のID。重複時も既存IDを返す。
                必須メタデータ不足時は None。

        Raises:
            SQLAlchemyError: DB 操作エラー時は呼び出し元に伝播させる。
            ValueError: Repository が無効な入力で raise した場合。

        """
        # メタデータに必須情報とパスを追加
        required_keys = ["width", "height", "has_alpha"]  # Repositoryでチェックされるが念のため
        if not all(key in info for key in required_keys):
            missing = [k for k in required_keys if k not in info]
            logger.error(f"処理済み画像の必須メタデータが不足: {missing}")
            return None

        info.update(
            {
                "image_id": image_id,
                "stored_image_path": str(processed_path),  # Path を文字列に
            },
        )

        # データベースに挿入 (Repository が重複チェックを行う)
        processed_image_id = self.image_repo.add_processed_image(info)
        if processed_image_id is not None:
            logger.debug(
                f"処理済み画像を登録/確認しました: ID={processed_image_id}, 元画像ID={image_id}",
            )
        # None が返るケースは Repository のエラーログで記録されるはず
        return processed_image_id

    def save_tags(self, image_id: int, tags_data: list[TagAnnotationData]) -> None:
        """指定された画像のタグ情報を保存・更新します。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
            ValueError: Repository が無効な入力で raise した場合。

        """
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": tags_data,
                "captions": [],
                "scores": [],
                "ratings": [],
            }
            self.annotation_repo.save_annotations(image_id, annotations_to_save)
            logger.debug(f"画像 ID {image_id} のタグ {len(tags_data)} 件を保存しました。")
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"画像 ID {image_id} のタグ保存中にエラー: {e}", exc_info=True)
            raise

    def save_captions(self, image_id: int, captions_data: list[CaptionAnnotationData]) -> None:
        """指定された画像のキャプション情報を保存・更新します。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
            ValueError: Repository が無効な入力で raise した場合。

        """
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": [],
                "captions": captions_data,
                "scores": [],
                "ratings": [],
            }
            self.annotation_repo.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のキャプション {len(captions_data)} 件を保存しました。")
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"画像 ID {image_id} のキャプション保存中にエラー: {e}", exc_info=True)
            raise

    def save_scores(self, image_id: int, scores_data: list[ScoreAnnotationData]) -> None:
        """指定された画像のスコア情報を保存・更新します。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
            ValueError: Repository が無効な入力で raise した場合。

        """
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": [],
                "captions": [],
                "scores": scores_data,
                "ratings": [],
            }
            self.annotation_repo.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のスコア {len(scores_data)} 件を保存しました。")
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"画像 ID {image_id} のスコア保存中にエラー: {e}", exc_info=True)
            raise

    def save_ratings(self, image_id: int, ratings_data: list[RatingAnnotationData]) -> None:
        """指定された画像のレーティング情報を保存・更新します。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
            ValueError: Repository が無効な入力で raise した場合。

        """
        try:
            annotations_to_save: AnnotationsDict = {
                "tags": [],
                "captions": [],
                "scores": [],
                "ratings": ratings_data,
            }
            self.annotation_repo.save_annotations(image_id, annotations_to_save)
            logger.info(f"画像 ID {image_id} のレーティング {len(ratings_data)} 件を保存しました。")
        except (SQLAlchemyError, ValueError) as e:
            logger.error(f"画像 ID {image_id} のレーティング保存中にエラー: {e}", exc_info=True)
            raise

    def register_prompt_tags(self, image_id: int, tags: list[str]) -> None:
        """プロンプトなど、元ファイル由来のタグを登録します。

        best-effort: タグ登録の失敗は呼び出し元 (画像登録パイプライン) を止めないため、
        DB エラー / 入力エラーは warning にしてフィルタアウトする。予期しない例外は伝播。

        """
        if not tags:
            return
        tags_data: list[TagAnnotationData] = [
            {
                "tag": tag,
                "model_id": None,
                "confidence_score": None,
                "existing": True,
                "is_edited_manually": False,
                "tag_id": None,
            }
            for tag in tags
        ]
        try:
            self.save_tags(image_id, tags_data)
            logger.info(f"画像 ID {image_id} のプロンプトタグ {len(tags)} 件を登録しました。")
        except (SQLAlchemyError, ValueError) as e:
            # save_tags 内でログが出るのでここでは再ログしないか、レベルを変える
            logger.warning(f"画像 ID {image_id} のプロンプトタグ登録に失敗: {e}")
            # raise はしない(上位処理を止めない場合)

    # 旧 save_score を save_scores を使うように変更
    def save_score(self, image_id: int, score_dict: dict[str, Any]) -> None:
        """単一のスコア情報を保存します (下位互換性のため)。

        best-effort: 単一スコアの保存失敗は呼び出し元を止めない。DB エラー / 入力エラーは
        warning に落として続行する。予期しない例外は伝播させる。

        """
        score_float = score_dict.get("score")
        model_id = score_dict.get("model_id")
        if score_float is None or model_id is None:
            logger.error(f"スコア情報が不正です: {score_dict}")
            return

        score_data: ScoreAnnotationData = {
            "score": score_float,
            "model_id": model_id,
            "is_edited_manually": False,
        }
        try:
            self.save_scores(image_id, [score_data])
            # logger info は save_scores 内で出力される
        except (SQLAlchemyError, ValueError) as e:
            logger.warning(f"画像 ID {image_id} のスコア保存に失敗: {e}")

    def get_low_res_image_path(self, image_id: int) -> str | None:
        """指定されたIDで最も解像度が低い処理済み画像のパスを取得します。

        Args:
            image_id (int): 取得する元画像のID。

        Returns:
            str | None: 最も解像度が低い処理済み画像のパス。見つからない場合はNone。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        # resolution=0 で最低解像度を取得 (見つからない場合は Repository が None / [] を返す正常系)
        metadata = self.image_repo.get_processed_image(image_id, resolution=0, all_data=False)
        if isinstance(metadata, dict):  # None でなく dict であることを確認
            path = metadata.get("stored_image_path")
            if isinstance(path, str) and path:
                logger.debug(f"画像ID {image_id} の低解像度画像パスを取得しました。")
                return path
            logger.warning(
                f"画像ID {image_id} の低解像度画像のパスが見つかりません。 Metadata: {metadata}",
            )
        else:
            logger.warning(f"画像ID {image_id} の低解像度画像メタデータが見つかりません。")
        return None

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """指定されたIDのオリジナル画像メタデータを取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            dict[str, Any] | None: 画像メタデータを含む辞書。画像が見つからない場合はNone。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            metadata = self.image_repo.get_image_metadata(image_id)
            if metadata is None:
                logger.info(f"ID {image_id} の画像メタデータが見つかりません。")
            return metadata
        except SQLAlchemyError as e:
            logger.error(f"画像メタデータ取得中にエラーが発生しました: {e}", exc_info=True)
            raise  # Repositoryでエラーが発生したら上に伝える

    def mark_image_reviewed(self, image_id: int, *, reviewed: bool = True) -> bool:
        """画像のレビュー完了状態 (reviewed_at) を設定/解除する。

        Wireframes v11 Frame 5 · Results の accept 永続化。

        Args:
            image_id: 対象画像 ID。
            reviewed: True なら accept (reviewed_at=now)、False なら undo (NULL)。

        Returns:
            更新できた場合 True、対象が未登録なら False。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
        """
        try:
            return self.image_repo.set_image_reviewed(image_id, reviewed=reviewed)
        except SQLAlchemyError as e:
            logger.error(f"画像レビュー状態の更新中にエラー (ID: {image_id}): {e}", exc_info=True)
            raise

    def get_processed_metadata(self, image_id: int) -> list[dict[str, Any]] | None:
        """指定された元画像IDに関連する全ての処理済み画像のメタデータを取得します。

        Args:
            image_id (int): 元画像のID。

        Returns:
            list[dict[str, Any]] | None: 処理済み画像のメタデータのリスト。見つからない場合は空リスト。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            # all_data=True でリストが返る
            metadata_list = self.image_repo.get_processed_image(image_id, all_data=True)
            if isinstance(metadata_list, list):
                if not metadata_list:
                    logger.info(f"ID {image_id} の元画像に関連する処理済み画像が見つかりません。")
                return metadata_list
            # Repository が予期せず None や dict を返した場合 (通常はないはず)
            logger.error(
                f"get_processed_image(all_data=True) がリストを返しませんでした: {type(metadata_list)}",
            )
            return []
        except SQLAlchemyError as e:
            logger.error(f"処理済み画像メタデータ取得中にエラーが発生しました: {e}", exc_info=True)
            raise

    def get_image_annotations(
        self,
        image_id: int,
        *,
        include_rejected: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        """指定された画像のアノテーション(タグ、キャプション、スコア、レーティング)を取得します。

        Args:
            image_id: 対象画像 ID。
            include_rejected: True の場合、soft-rejected Tag/Caption も返す。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元 (Worker boundary) に伝播させる。

        """
        try:
            return self.image_repo.get_image_annotations(image_id, include_rejected=include_rejected)
        except SQLAlchemyError as e:
            logger.error(f"画像ID {image_id} のアノテーション取得中にエラー: {e}", exc_info=True)
            raise

    def get_image_annotations_batch(
        self,
        image_ids: list[int],
        *,
        include_rejected: bool = False,
    ) -> dict[int, dict[str, Any]]:
        """複数画像のアノテーションを一括取得する (#1140 N+1 解消)。

        ``get_image_annotations`` と同じ 6-key dict を image_id ごとに返す。存在しない
        image_id は空スケルトンを返す。

        Args:
            image_ids: 対象画像 ID リスト。
            include_rejected: True の場合、soft-rejected Tag/Caption も返す。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
        """
        try:
            return self.image_repo.get_image_annotations_batch(image_ids, include_rejected=include_rejected)
        except SQLAlchemyError as e:
            logger.error(f"アノテーション一括取得中にエラー (count={len(image_ids)}): {e}", exc_info=True)
            raise

    def get_low_res_image_paths_batch(self, image_ids: list[int]) -> dict[int, str]:
        """複数画像の最低解像度処理済み画像パスを一括取得する (#1140 N+1 解消)。

        ``get_low_res_image_path`` と同じ「面積最小」選択を image_id ごとに行う。
        処理済み画像が無い image_id は結果に含めない。

        Args:
            image_ids: 対象画像 ID リスト。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
        """
        try:
            return self.image_repo.get_low_res_image_paths_batch(image_ids)
        except SQLAlchemyError as e:
            logger.error(f"最低解像度パス一括取得中にエラー (count={len(image_ids)}): {e}", exc_info=True)
            raise

    def get_images_metadata_batch(
        self, image_ids: list[int], *, include_annotations: bool = True
    ) -> list[dict[str, Any]]:
        """複数画像のオリジナルメタデータを一括取得する (#1140 N+1 解消)。

        ``get_image_metadata`` と同じ列集合の dict を返す (キーは images.id = ``id``)。
        見つからなかった ID は結果に含まれない。

        Args:
            image_ids: 対象画像 ID リスト。
            include_annotations: アノテーションを先読みするか。別経路で取得済みなら
                False にして二重フェッチを避ける (Issue #1140)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
        """
        try:
            return self.image_repo.get_images_metadata_batch(
                image_ids, include_annotations=include_annotations
            )
        except SQLAlchemyError as e:
            logger.error(f"メタデータ一括取得中にエラー (count={len(image_ids)}): {e}", exc_info=True)
            raise

    def get_models(self) -> list[dict[str, Any]]:
        """データベースに登録されている全てのモデル情報を取得します。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.model_repo.get_models()
        except SQLAlchemyError as e:
            logger.error(f"全モデル情報の取得中にエラー: {e}", exc_info=True)
            raise

    def get_tagger_models(self) -> list[dict[str, Any]]:
        """Tagger タイプのモデル情報を取得する (Issue #243: SSoT は `tags`)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.model_repo.get_models_by_type("tags")
        except SQLAlchemyError as e:
            logger.error(f"Taggerモデル情報の取得中にエラー: {e}", exc_info=True)
            raise

    def get_score_models(self) -> list[dict[str, Any]]:
        """Score タイプのモデル情報を取得する (Issue #243: SSoT は `scores`)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.model_repo.get_models_by_type("scores")
        except SQLAlchemyError as e:
            logger.error(f"Scoreモデル情報の取得中にエラー: {e}", exc_info=True)
            raise

    def get_captioner_models(self) -> list[dict[str, Any]]:
        """Captioner タイプのモデル情報を取得する (Issue #243: SSoT は `caption`)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.model_repo.get_models_by_type("caption")
        except SQLAlchemyError as e:
            logger.error(f"Captionerモデル情報の取得中にエラー: {e}", exc_info=True)
            raise

    def get_upscaler_models(self) -> list[dict[str, Any]]:
        """Upscaler タイプのモデル情報を取得する (SSoT は `upscaler` のまま)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.model_repo.get_models_by_type("upscaler")
        except SQLAlchemyError as e:
            logger.error(f"Upscalerモデル情報の取得中にエラー: {e}", exc_info=True)
            raise

    def get_llm_models(self) -> list[dict[str, Any]]:
        """LLM タイプのモデル情報を取得する (Issue #243: SSoT は `multimodal` に統合済み)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.model_repo.get_models_by_type("multimodal")
        except SQLAlchemyError as e:
            logger.error(f"LLMモデル情報の取得中にエラー: {e}", exc_info=True)
            raise

    def get_manual_edit_model_id(self) -> int:
        """手動編集用のモデルIDを取得します（キャッシュ機能付き）。

        MANUAL_EDITという名前のモデルが存在しない場合は新規作成します。
        初回呼び出し時にのみデータベースアクセスを行い、2回目以降はキャッシュされた値を返します。

        Returns:
            int: MANUAL_EDITモデルのID

        Raises:
            SQLAlchemyError: データベース操作中にエラーが発生した場合

        """
        if not hasattr(self, "_manual_edit_model_id"):
            with self.model_repo.session_factory() as session:
                # injected model_repo 経由で呼び出し DI contract を維持
                # (test double / subclass override / tenant-aware wrapper を尊重)
                self._manual_edit_model_id = self.model_repo._get_or_create_manual_edit_model(session)
                session.commit()
            logger.debug(f"MANUAL_EDITモデルIDをキャッシュ: {self._manual_edit_model_id}")
        return self._manual_edit_model_id

    # --- TagEdit soft-reject 導線 (Issue #792) ---

    def soft_reject_tag(self, image_id: int, tag: str, reason: str = REJECT_REASON_INCORRECT) -> bool:
        """画像の 1 タグを soft-reject する (rejected_at + reject_reason を記録、行は残す)。

        Args:
            image_id: 対象画像 ID。
            tag: soft-reject するタグ。
            reason: soft-reject 種別 (``'not_needed'`` 無効化 / ``'incorrect'`` 除外)。
                既定は ``'incorrect'`` (Issue #1003)。

        Returns:
            実際に reject された場合 True (既に無い場合 False)。
        """
        success, per_item = self.annotation_repo.remove_tag_from_images_batch(
            [image_id], tag, reason=reason
        )
        return success and any(status == "changed" for _, status in per_item)

    def soft_reject_tag_batch(
        self, image_ids: list[int], tag: str, reason: str = REJECT_REASON_INCORRECT
    ) -> int:
        """複数画像の 1 タグを一括 soft-reject し、実際に reject した件数を返す (#949)。

        エクスポート前タグ編集パネルの「✎ reject(DB)」(全 staged 画像へ永続 reject) で使う。

        Args:
            image_ids: 対象画像 ID のリスト。
            tag: soft-reject するタグ。
            reason: soft-reject 種別。既定は ``'incorrect'`` (Issue #1003)。

        Returns:
            実際に reject された画像数 (既に無い画像は数えない)。
        """
        if not image_ids:
            return 0
        success, per_item = self.annotation_repo.remove_tag_from_images_batch(image_ids, tag, reason=reason)
        if not success:
            return 0
        return sum(1 for _, status in per_item if status == "changed")

    def restore_tag(self, image_id: int, tag: str) -> bool:
        """soft-reject されたタグを復活する (rejected_at を NULL へ)。

        Args:
            image_id: 対象画像 ID。
            tag: 復活するタグ。

        Returns:
            実際に復活された場合 True。
        """
        success, per_item = self.annotation_repo.restore_tag_for_images_batch([image_id], tag)
        return success and any(status == "changed" for _, status in per_item)

    def replace_tag(self, image_id: int, from_tag: str, to_tag: str) -> bool:
        """画像の 1 タグを置換する (refinement 修正候補の適用、Issue #1007)。

        置換元は ``reject_reason='replaced'`` で soft-reject し (非表示)、置換先を手動タグ
        として追加する。原子的置換は ``replace_tag_for_images_batch`` (Issue #1003) に
        委譲する。

        Args:
            image_id: 対象画像 ID。
            from_tag: 置換元タグ (警告対象の canonical)。
            to_tag: 置換先タグ (修正候補)。

        Returns:
            実際に置換された場合 True (置換元タグが画像に無ければ False)。
        """
        success, per_item = self.annotation_repo.replace_tag_for_images_batch([image_id], from_tag, to_tag)
        return success and any(status == "changed" for _, status in per_item)

    def add_manual_tag(self, image_id: int, tag: str) -> bool:
        """画像に手動タグを追加する (is_edited_manually=True)。

        Args:
            image_id: 対象画像 ID。
            tag: 追加するタグ。

        Returns:
            実際に追加された場合 True (重複で skip された場合 False)。
        """
        model_id = self.get_manual_edit_model_id()
        success, added = self.annotation_repo.add_tag_to_images_batch([image_id], tag, model_id)
        return success and added > 0

    def get_rejected_tags(self, image_id: int) -> list[dict[str, Any]]:
        """画像の soft-reject 済みタグ一覧を返す (復活セクション表示用)。

        Args:
            image_id: 対象画像 ID。

        Returns:
            ``{"tag", "tag_id", "is_edited_manually", "reject_reason"}`` の dict リスト
            (reject_reason は表示種別の再構築に使う、Issue #1003)。
        """
        return self.annotation_repo.get_rejected_tags(image_id)

    def get_images_by_filter(
        self,
        criteria: ImageFilterCriteria | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """指定された条件に基づいて画像をフィルタリングし、メタデータと件数を返します。

        Args:
            criteria: ImageFilterCriteria形式のフィルター条件。None の場合は
                デフォルト条件 (全件) として扱う。

        Returns:
            tuple: (画像メタデータのリスト, 総数)
        """
        try:
            filter_criteria = criteria or ImageFilterCriteria()
            return self.image_repo.get_images_by_filter(filter_criteria)
        except SQLAlchemyError as e:
            logger.error(f"画像フィルタリング検索中にエラーが発生しました: {e}", exc_info=True)
            raise

    def detect_duplicate_image(self, image_path: Path) -> int | None:
        """画像の重複を検出し、重複が確定する場合はその画像のIDを返す。

        ADR 0061: pHash 完全一致を起点に、追加属性 (width / height / has_alpha /
        is_grayscale_like) の比較で「重複確定」のときだけ既存 ID を返す。同一 pHash でも
        属性差が重要な「別版」は重複とみなさず None を返し、呼び出し元が新規登録経路へ
        進めるようにする。

        Args:
            image_path (Path): 検査する画像ファイルのパス

        Returns:
            int | None: 重複が確定した場合はそのimage_id、それ以外 (別版 / 新規 /
                pHash 計算失敗) は None。pHash 計算失敗は `ValueError` /
                `FileNotFoundError` / `OSError` を None に畳む。OSError には
                PermissionError や PIL の UnidentifiedImageError 等が含まれる
                (1 ファイル不正で directory scan 全体を止めないための per-file tolerance)。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        image_name = image_path.name

        # pHash 計算失敗は重複なしとして扱う (正常系扱い)
        try:
            phash = calculate_phash(image_path)
        except (ValueError, FileNotFoundError, OSError) as e:
            logger.warning(f"画像をスキップ: {e}")
            return None

        # 分類には属性が要るため画像情報も取得する (取得失敗は重複なし扱い)
        # get_image_info は staticmethod のため fsm 未注入でも呼べる。
        try:
            image_info = FileSystemManager.get_image_info(image_path)
        except (OSError, ValueError) as e:
            logger.warning(f"画像情報取得に失敗したため重複なし扱い: {image_path}, Error: {e}")
            return None

        # DB 失敗は呼び出し元へ伝播させる
        candidates = self.image_repo.find_phash_candidates(phash)
        classification, existing_id = ImageRepository.classify_phash_candidate(image_info, candidates)
        if classification is PhashClassification.DUPLICATE and existing_id is not None:
            logger.debug(f"重複確定: pHash+属性一致 ID={existing_id}, Name={image_name}, pHash={phash}")
            return existing_id
        if classification is PhashClassification.VARIANT:
            logger.debug(f"別版検出 (重複ではない): Name={image_name}, pHash={phash}")
        else:
            logger.debug(f"重複なし: Name={image_name}, pHash={phash}")
        return None

    def get_images_count_only(
        self,
        criteria: ImageFilterCriteria | None = None,
    ) -> int:
        """指定条件に一致する画像件数のみを取得します。

        Args:
            criteria: ImageFilterCriteria形式のフィルター条件。None の場合は
                デフォルト条件 (全件) として扱う。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            filter_criteria = criteria or ImageFilterCriteria()
            return self.image_repo.get_images_count_only(filter_criteria)
        except SQLAlchemyError as e:
            logger.error(f"画像件数の取得中にエラーが発生しました: {e}", exc_info=True)
            raise

    def get_total_image_count(self) -> int:
        """データベース内に登録されたオリジナル画像の総数を取得します。

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            count = self.image_repo.get_total_image_count()
            return count
        except SQLAlchemyError as e:
            logger.error(f"総画像数の取得中にエラーが発生しました: {e}", exc_info=True)
            raise

    def get_image_ids_from_directory(self, directory_path: Path) -> list[int]:
        """指定されたディレクトリに含まれる画像のIDリストを取得します。

        Args:
            directory_path (Path): 検索対象のディレクトリパス

        Returns:
            list[int]: 該当する画像のIDリスト

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
            OSError: ディレクトリ走査に失敗した場合 (FileNotFoundError 等)。

        """
        try:
            # ディレクトリ内の画像ファイルを取得
            if not self.fsm:
                from ..filesystem import FileSystemManager

                temp_fsm = FileSystemManager()
                image_files = temp_fsm.get_image_files(directory_path)
            else:
                image_files = self.fsm.get_image_files(directory_path)
            image_ids = []

            for image_file in image_files:
                # pHashで重複検出（既存画像のID取得）
                image_id = self.detect_duplicate_image(image_file)
                if image_id:
                    image_ids.append(image_id)

            logger.info(f"ディレクトリ {directory_path} から {len(image_ids)} 件の画像IDを取得しました")
            return image_ids

        except (SQLAlchemyError, OSError) as e:
            logger.error(
                f"ディレクトリからの画像ID取得中にエラー: {directory_path}, Error: {e}",
                exc_info=True,
            )
            raise

    def get_dataset_status(self) -> dict[str, Any]:
        """データセット状態の取得（軽量な読み取り操作）

        DB 失敗時は status="error" を返す UI 向けステータス API。
        呼び出し元 (status バー等) が表示用に使うため、DB 例外は status へ畳む。

        Returns:
            dict: データセット状態情報 {"total_images": int, "status": str}
                ステータス値: "ready" | "empty" | "error"

        """
        try:
            total_count = self.get_total_image_count()
        except SQLAlchemyError as e:
            logger.error(f"データセット状態取得エラー: {e}", exc_info=True)
            return {"total_images": 0, "status": "error"}
        return {"total_images": total_count, "status": "ready" if total_count > 0 else "empty"}

    def get_annotation_status_counts(self) -> dict[str, int | float]:
        """アノテーション状態カウントを取得

        Returns:
            dict: アノテーション状態統計 {"total": int, "completed": int, "error": int, "completion_rate": float}

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            # 総画像数取得
            total_images = self.get_total_image_count()

            if total_images == 0:
                return {"total": 0, "completed": 0, "error": 0, "completion_rate": 0.0}

            # 完了画像数取得 (タグまたはキャプションが存在)
            session: Session = self.image_repo.get_session()
            with session:
                completed_query = text("""
                    SELECT COUNT(DISTINCT i.id) FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id AND t.rejected_at IS NULL
                    LEFT JOIN captions c ON i.id = c.image_id AND c.rejected_at IS NULL
                    WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                """)
                result: Result[Any] = session.execute(completed_query)
                completed_images: int = result.scalar() or 0

                # エラー画像数取得 (未解決のアノテーションエラーのみ)
                # ADR 0035 段階 3 (#423): injected error_record_repo 経由で呼び出し DI contract を維持。
                error_images = self.error_record_repo.get_error_count_unresolved(
                    operation_type="annotation"
                )

                completion_rate = (completed_images / total_images) * 100.0 if total_images > 0 else 0.0

                return {
                    "total": total_images,
                    "completed": completed_images,
                    "error": error_images,
                    "completion_rate": completion_rate,
                }

        except SQLAlchemyError as e:
            logger.error(f"アノテーション状態カウント取得エラー: {e}", exc_info=True)
            raise

    def filter_by_annotation_status(
        self,
        completed: bool = False,
        error: bool = False,
    ) -> list[dict[str, Any]]:
        """アノテーション状態でフィルタリング

        Args:
            completed: 完了画像のみ
            error: エラー画像のみ

        Returns:
            list: フィルター後の画像リスト

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            session: Session = self.image_repo.get_session()

            with session:
                if completed:
                    # 完了画像（タグまたはキャプション有り）
                    query = text("""
                        SELECT DISTINCT i.* FROM images i
                        LEFT JOIN tags t ON i.id = t.image_id AND t.rejected_at IS NULL
                        LEFT JOIN captions c ON i.id = c.image_id AND c.rejected_at IS NULL
                        WHERE t.id IS NOT NULL OR c.id IS NOT NULL
                    """)
                elif error:
                    # エラー画像（未解決のアノテーションエラーのみ）
                    # ADR 0035 段階 3 (#423): injected error_record_repo 経由で呼び出し DI contract を維持。
                    error_image_ids = self.error_record_repo.get_error_image_ids(
                        operation_type="annotation",
                        resolved=False,
                    )
                    if not error_image_ids:
                        return []
                    return self.image_repo.get_images_by_ids(error_image_ids)
                else:
                    # 全ての画像
                    query = text("SELECT * FROM images")

                result: Result[Any] = session.execute(query)
                return [dict(row._mapping) for row in result.fetchall()]

        except SQLAlchemyError as e:
            logger.error(f"アノテーション状態フィルタリングエラー: {e}", exc_info=True)
            raise

    def get_directory_images_metadata(self, directory_path: Path) -> list[dict[str, Any]]:
        """ディレクトリ内画像のメタデータ取得（軽量な読み取り操作）

        Args:
            directory_path: 検索対象ディレクトリのパス

        Returns:
            list: ディレクトリ内の画像メタデータリスト

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。
            OSError: ディレクトリ走査に失敗した場合 (FileNotFoundError 等)。

        """
        try:
            image_ids = self.get_image_ids_from_directory(directory_path)
            if not image_ids:
                return []

            # 画像IDリストからメタデータを取得
            images = []
            for image_id in image_ids:
                metadata = self.get_image_metadata(image_id)
                if metadata:
                    images.append(metadata)

            logger.info(
                f"ディレクトリ {directory_path} から {len(images)} 件の画像メタデータを取得しました",
            )
            return images

        except (SQLAlchemyError, OSError) as e:
            logger.error(f"ディレクトリ画像メタデータ取得エラー: {directory_path}, {e}", exc_info=True)
            raise

    def check_processed_image_exists(self, image_id: int, target_resolution: int) -> dict[str, Any] | None:
        """指定された画像IDと目標解像度に一致する処理済み画像が存在するかチェックします。

        Args:
            image_id (int): 元画像のID
            target_resolution (int): 目標解像度

        Returns:
            dict[str, Any] | None: 処理済み画像が存在する場合はそのメタデータ、存在しない場合はNone

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            # get_processed_image は resolution=0 以外の場合、dict | None を返す
            processed_image_metadata = self.image_repo.get_processed_image(
                image_id,
                resolution=target_resolution,
                all_data=False,
            )

            if isinstance(processed_image_metadata, dict):
                logger.debug(
                    f"解像度 {target_resolution} の処理済み画像が既に存在します: 元画像ID={image_id}, 処理済ID={processed_image_metadata.get('id')}",
                )
                return processed_image_metadata
            logger.info(
                f"解像度 {target_resolution} に一致する処理済み画像は見つかりませんでした: 元画像ID={image_id}",
            )
            return None
        except SQLAlchemyError as e:
            logger.error(
                f"処理済み画像の存在チェック中にエラーが発生しました: 元画像ID={image_id}, 解像度={target_resolution}, Error: {e}",
                exc_info=True,
            )
            raise

    def get_batch_available_resolutions(self, image_ids: list[int]) -> dict[int, list[int]]:
        """複数画像の利用可能な処理済み解像度を一括取得します。

        Args:
            image_ids: 画像IDリスト

        Returns:
            image_id -> 利用可能な解像度リスト のマッピング

        """
        return self.image_repo.get_batch_available_resolutions(image_ids)

    def filter_image_ids_with_tag_changes_since(self, image_ids: list[int], since: datetime) -> list[int]:
        """指定日時以降にタグ変更があった image_id に絞り込む (#614)。

        AI 実行 (model_id 付きタグの created_at) または手動編集
        (is_edited_manually のタグの updated_at) が since より後のものを残す。

        Args:
            image_ids: 絞り込み元の画像IDリスト。
            since: 変更ありとみなす閾値日時。

        Returns:
            since 以降にタグ変更があった image_id の一覧。
        """
        return self.image_repo.filter_image_ids_with_tag_changes_since(image_ids, since)

    def _parse_annotation_timestamp(self, update_time: datetime | str) -> datetime | None:
        """アノテーションのタイムスタンプをパースする。

        datetime オブジェクトまたは ISO 形式文字列からタイムスタンプを抽出し、
        タイムゾーン情報を付与します。naive datetime は UTC として扱います。

        Args:
            update_time: datetime オブジェクトまたは ISO 形式文字列。

        Returns:
            datetime | None: UTC タイムゾーン付きの datetime、またはパース失敗時は None。

        """
        if isinstance(update_time, datetime):
            dt = update_time
        elif isinstance(update_time, str):
            try:
                dt = datetime.fromisoformat(update_time.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"不正な updated_at 文字列: {update_time}")
                return None
        else:
            return None

        # naive datetime の場合、UTC と仮定
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt

    def _find_latest_annotation_timestamp(
        self,
        annotations: dict[str, list[dict[str, Any]]],
    ) -> datetime | None:
        """全アノテーションから最新の更新日時を検索する。

        タグ、キャプション、スコア、レーティング全体をスキャンして
        最新の更新タイムスタンプを取得します。有効なタイムスタンプが
        見つからない場合は None を返します。

        Args:
            annotations: 'tags', 'captions', 'scores', 'ratings' キーを持つ辞書。

        Returns:
            datetime | None: UTC タイムゾーン付きの最新更新日時、または見つからない場合は None。

        """
        all_updates: list[datetime] = []

        # スキャン: 全アノテーションから更新日時を抽出
        for key in annotations:
            for item in annotations[key]:
                if isinstance(item, dict) and "updated_at" in item:
                    parsed_dt = self._parse_annotation_timestamp(item["updated_at"])
                    if parsed_dt:
                        all_updates.append(parsed_dt)

        if not all_updates:
            logger.info("アノテーションに有効な更新日時が見つかりませんでした。")
            return None

        return max(all_updates)

    def filter_recent_annotations(
        self,
        annotations: dict[str, list[dict[str, Any]]],
        minutes_threshold: int = 5,
    ) -> dict[str, list[dict[str, Any]]]:
        """与えられたアノテーションデータから、指定時間内に更新されたものだけをフィルタリングします。
        'updated_at' フィールドが存在しないアノテーションは無視されます。

        Args:
            annotations (dict): 'tags', 'captions', 'scores', 'ratings' キーを持つ
                                アノテーション辞書。各値はアノテーション情報の辞書のリスト。
            minutes_threshold (int): 最新の更新時刻から遡る時間(分)。デフォルトは5分。

        Returns:
            dict: フィルタリングされたアノテーション辞書。

        """
        # 初期化
        filtered_annotations: dict[str, list[dict[str, Any]]] = {
            "tags": [],
            "captions": [],
            "scores": [],
            "ratings": [],
        }

        # 最新の更新日時を取得
        latest_update_dt = self._find_latest_annotation_timestamp(annotations)
        if latest_update_dt is None:
            return filtered_annotations

        # 閾値を計算
        time_threshold = latest_update_dt - timedelta(minutes=minutes_threshold)
        logger.debug(f"最新更新日時: {latest_update_dt}, 閾値: {time_threshold}")

        # フィルタリング処理
        for key in annotations:
            for item in annotations[key]:
                if isinstance(item, dict) and "updated_at" in item:
                    item_dt = self._parse_annotation_timestamp(item["updated_at"])
                    if item_dt and item_dt >= time_threshold:
                        filtered_annotations[key].append(item)

        logger.info(
            f"最近更新されたアノテーションをフィルタリングしました (閾値: {minutes_threshold}分)。",
        )
        return filtered_annotations

    def check_image_has_annotation(self, image_id: int) -> bool:
        """画像にアノテーション（タグまたはキャプション）が存在するかチェック

        Args:
            image_id: 画像ID

        Returns:
            bool: アノテーションが存在するかどうか

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            session = self.image_repo.get_session()
            with session:
                # タグまたはキャプションの存在確認
                query = """
                    SELECT 1 FROM images i
                    LEFT JOIN tags t ON i.id = t.image_id
                    LEFT JOIN captions c ON i.id = c.image_id
                    WHERE i.id = :image_id AND (t.id IS NOT NULL OR c.id IS NOT NULL)
                    LIMIT 1
                """
                result = session.execute(text(query), {"image_id": image_id})
                has_annotation = result.scalar() is not None

                logger.debug(
                    f"アノテーション存在確認: image_id={image_id}, has_annotation={has_annotation}",
                )
                return has_annotation

        except SQLAlchemyError as e:
            logger.error(f"アノテーション存在確認エラー: image_id={image_id}, error={e}", exc_info=True)
            raise

    def get_annotated_image_ids(self, image_ids: list[int]) -> set[int]:
        """指定IDリストからアノテーション済み画像IDを一括取得する。

        Args:
            image_ids: 検査対象の画像IDリスト。

        Returns:
            アノテーションが存在する画像IDのセット。

        """
        return self.image_repo.get_annotated_image_ids(image_ids)

    def save_error_record(
        self,
        operation_type: str,
        error_type: str,
        error_message: str,
        image_id: int | None = None,
        stack_trace: str | None = None,
        file_path: str | None = None,
        model_name: str | None = None,
    ) -> int:
        """エラーレコードを保存（Manager層Facade）

        Worker層から呼び出されるFacadeメソッド。
        **二次エラー防止 (sentinel return)**: エラー保存中の例外は呼び出し元
        (Worker の error handling 経路) を再 fail させない目的で、ここで
        sentinel `-1` に畳む。`except Exception` は本メソッドのこの用途で
        意図的に維持する (coding-style.md「Manager 層のエラーハンドリング方針」
        が許容する二次エラー防止パターン)。

        Args:
            operation_type: 操作種別 ("registration" | "annotation" | "processing")
            error_type: エラー種別（例: "FileNotFoundError", "APIError"）
            error_message: エラーメッセージ
            image_id: 画像ID (Optional)
            stack_trace: スタックトレース (Optional)
            file_path: ファイルパス (Optional)
            model_name: モデル名 (Optional)

        Returns:
            int: 作成された error_record_id。**二次エラー発生時は sentinel `-1`**
                (DB 保存失敗を呼び出し元の error handling 経路から隠す)。

        """
        try:
            # ADR 0035 段階 3 (#423): injected error_record_repo 経由で呼び出し DI contract を維持。
            error_id = self.error_record_repo.save_error_record(
                operation_type=operation_type,
                error_type=error_type,
                error_message=error_message,
                image_id=image_id,
                stack_trace=stack_trace,
                file_path=file_path,
                model_name=model_name,
            )
            logger.debug(
                f"エラーレコード保存完了: error_id={error_id}, "
                f"operation_type={operation_type}, error_type={error_type}",
            )
            return error_id

        except Exception as e:
            # 二次エラー防止 (sentinel return): ここで畳まないと error handling 経路が再失敗する。
            # 本メソッドの本来の責務がエラー保存なので、保存自体の失敗は致命的に扱わず
            # sentinel `-1` で返し、上位の error handling を止めない。
            logger.error(f"エラーレコード保存中にエラー（二次エラー）: {e}", exc_info=True)
            return -1

    def mark_errors_resolved_batch(self, error_ids: list[int]) -> tuple[bool, int]:
        """複数エラーを一括解決済みマーク（Manager層Facade）

        Args:
            error_ids: 対象エラーレコードのIDリスト

        Returns:
            (成功フラグ, 解決済みマーク件数)

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            # ADR 0035 段階 3 (#423): injected error_record_repo 経由で呼び出し DI contract を維持。
            return self.error_record_repo.mark_errors_resolved_batch(error_ids)
        except SQLAlchemyError as e:
            logger.error(f"一括解決マーク失敗（Manager）: {e}", exc_info=True)
            raise

    def get_image_id_by_filepath(self, filepath: str) -> int | None:
        """ファイルパスから画像IDを取得（Manager層Facade）

        Args:
            filepath: 画像ファイルパス

        Returns:
            int | None: 画像ID（見つからない場合は None）

        Raises:
            SQLAlchemyError: DB 操作に失敗した場合は呼び出し元に伝播させる。

        """
        try:
            return self.image_repo.get_image_id_by_filepath(filepath)
        except SQLAlchemyError as e:
            logger.error(f"ファイルパスからの画像ID取得エラー: {e}", exc_info=True)
            raise

    def get_created_at_histogram(self, bins: int = 20) -> list[tuple[datetime, datetime, int]]:
        """Image.created_at 分布ヒストグラムを取得する。

        Args:
            bins: ビン数（デフォルト 20）。

        Returns:
            list of (bin_start, bin_end, count)。空データの場合は空リスト。
        """
        return self.image_repo.get_created_at_histogram(bins=bins)

    def get_recently_used_model_ids(self, limit: int = 10) -> list[str]:
        """アノテーション実績があるモデルの litellm_model_id を返す。

        Args:
            limit: 最大件数（デフォルト 10）。

        Returns:
            litellm_model_id のリスト。
        """
        return self.image_repo.get_recently_used_model_ids(limit=limit)


# --- 初期化チェック ---
# try:
#     # 設定ファイル等からDBディレクトリパスを取得する想定
#     # db_dir = Path("path/to/your/database/directory")
#     manager = ImageDatabaseManager()
#     print("ImageDatabaseManager initialized successfully.")
# except Exception as e:
#     print(f"Failed to initialize ImageDatabaseManager: {e}")
#     traceback.print_exc()
