"""Image / ProcessedImage / FilenameAlias 永続化担当 Repository (ADR 0035 §1)。

`ImageRepository` god class 分割の段階 4 として、Image エンティティおよび
関連する ProcessedImage / FilenameAlias の CRUD・検索・フィルタ・メタデータ取得を
本 Repository に集約する。

管轄 entity:
  - `Image` (CRUD、pHash 重複検出、フィルタリング検索)
  - `ProcessedImage` (CRUD、解像度別 lookup、batch resolution map)
  - `ImageFilenameAlias` (重複スキップ画像の filename alias)

カバー領域:
  - 画像 CRUD: 登録 / 存在チェック / Processed 画像追加
  - 検索: pHash 一致 / annotated 画像 ID / filename index
  - メタデータ取得: 単体 / バッチ / 解像度別 (annotation 読み込み込み)
  - フィルタリング: タグ / キャプション / 評価 / NSFW / スコア / 日付 / project
  - File path 解決: 単体 / batch (N+1 回避)

段階 5 領域 (本 Repository には含めない):
  - Annotation 書き込み (`save_annotations`, `_save_*`, `update_*_batch`)
  - Tag DB 統合 (`MergedTagReader` / `TagRegisterService`)
  - genai-tag-db-tools 連携 (`batch_resolve_tag_ids`, `_register_*`)

段階 1 で確立した `BaseRepository` (`session_factory` + `BATCH_CHUNK_SIZE`) を継承する。
"""

from __future__ import annotations

import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from sqlalchemy import (
    Select,
    and_,
    exists,
    func,
    not_,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from ...domain.quality_tier import compute_quality_summary
from ...domain.score_scaler import calibrate_to_display
from ...utils.log import logger
from ..filter_criteria import ImageFilterCriteria
from ..schema import (
    MANUAL_EDIT_LITELLM_ID,
    MANUAL_EDIT_NAME,
    Caption,
    Image,
    ImageFilenameAlias,
    Model,
    ProcessedImage,
    Project,
    Rating,
    Score,
    ScoreLabel,
    Tag,
)
from .base import BaseRepository
from .model import ModelRepository


class PhashClassification(StrEnum):
    """pHash 完全一致候補の分類結果 (ADR 0061)。

    pHash 完全一致は「重複確定」ではなく候補にすぎない。追加属性比較を経て、
    既存画像と完全に同一なら ``DUPLICATE``、属性差が重要な別版なら ``VARIANT``、
    候補が一つも無ければ ``NEW`` に分類する。
    """

    DUPLICATE = "duplicate"
    VARIANT = "variant"
    NEW = "new"


class ImageRepository(BaseRepository):
    """Image / ProcessedImage / FilenameAlias の永続化を担当する Repository (ADR 0035 §1)。

    管轄 entity:
      - `Image` (CRUD・検索・フィルタ・メタデータ)
      - `ProcessedImage` (CRUD・解像度別 lookup)
      - `ImageFilenameAlias` (filename alias)
    """

    # exact-set selector (`image_ids`) の最大 ID 数 (ADR 0056)。
    # = StagingWidget.MAX_STAGING_IMAGES。エクスポート集合 (ステージング由来) の有界性を
    # リポジトリ層の契約として持たせる。Qt-free (ADR 0001) のため GUI 定数を import せず、
    # 値の drift は test で assert する。バインド安全 (BATCH_CHUNK_SIZE) は副次的に満たす。
    EXACT_SET_MAX_IDS: ClassVar[int] = 500

    # --- Filename Alias ---

    def get_all_image_filename_index(self) -> dict[str, int]:
        """全画像のfilename stem → image_id インデックスを構築する。

        バッチインポート時のcustom_id照合用。N+1クエリを回避するため
        1回のクエリで全画像のファイル名とIDを取得する。

        Returns:
            {filename_stem: image_id} の辞書。重複stem時は最新IDを優先。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                stmt = select(Image.id, Image.filename).where(Image.filename.isnot(None))
                results = session.execute(stmt).all()
                index: dict[str, int] = {}
                for image_id, filename in results:
                    stem = Path(filename).stem
                    index[stem] = image_id

                # エイリアス（重複スキップされた画像のファイル名）もインデックスに追加
                alias_stmt = select(ImageFilenameAlias.image_id, ImageFilenameAlias.stem)
                alias_results = session.execute(alias_stmt).all()
                for image_id, stem in alias_results:
                    if stem not in index:
                        index[stem] = image_id

                return index
            except SQLAlchemyError as e:
                logger.error(f"ファイル名インデックス構築エラー: {e}", exc_info=True)
                raise

    def add_filename_alias(self, image_id: int, stem: str) -> None:
        """重複スキップされた画像のファイル名エイリアスを登録する。

        Args:
            image_id: 重複元の画像ID。
            stem: スキップされた画像のファイル名stem。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        with self.session_factory() as session:
            try:
                alias = ImageFilenameAlias(image_id=image_id, stem=stem)
                session.add(alias)
                session.commit()
                logger.debug(f"ファイル名エイリアス登録: {stem} → image_id={image_id}")
            except IntegrityError:
                session.rollback()
                logger.debug(f"エイリアス既存のためスキップ: {stem}")
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(f"エイリアス登録エラー: {e}", exc_info=True)
                raise

    # --- Image CRUD ---

    def _image_exists(self, image_id: int) -> bool:
        """指定された画像IDが images テーブルに存在するかを確認します。

        Args:
            image_id (int): 確認する画像のID。

        Returns:
            bool: 画像が存在する場合はTrue、存在しない場合はFalse。

        """
        with self.session_factory() as session:
            try:
                stmt = select(Image.id).where(Image.id == image_id)
                # exists() など、より効率的な方法も検討できるが、まずはシンプルに
                result = session.execute(stmt).scalar_one_or_none()
                return result is not None
            except SQLAlchemyError as e:
                logger.error(
                    f"画像存在チェック中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def find_duplicate_image_by_phash(self, phash: str) -> int | None:
        """指定されたpHashに一致する画像をデータベースから検索し、Image IDを返します。
        pHashはNULL不可のため、完全一致で検索します。

        Args:
            phash (str): 検索するpHash。

        Returns:
            int | None: 重複する画像のID。見つからない場合はNone。

        """
        if not phash:  # pHashが空文字列やNoneの場合は検索しない
            return None
        with self.session_factory() as session:
            try:
                # ID を返す必要があるので、ID を SELECT するように修正
                stmt_id = select(Image.id).where(Image.phash == phash).limit(1)
                image_id = session.execute(stmt_id).scalar_one_or_none()
                if image_id:
                    logger.debug(f"pHashによる重複画像が見つかりました: ID {image_id}, pHash {phash}")
                return image_id
            except SQLAlchemyError as e:
                logger.error(f"pHashによる重複画像の検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    # 分類に用いる属性キー (ADR 0061 §2)。width / height / has_alpha /
    # is_grayscale_like が全て一致する候補のみを「重複確定」とみなす。
    # colorfulness_score は閾値調整・診断用の連続値で直接条件には用いない。
    CLASSIFICATION_ATTRS: ClassVar[tuple[str, ...]] = (
        "width",
        "height",
        "has_alpha",
        "is_grayscale_like",
    )

    def find_phash_candidates(self, phash: str) -> list[dict[str, Any]]:
        """指定 pHash に完全一致する候補画像の分類用属性を取得する (ADR 0061)。

        pHash 完全一致を「重複確定」とせず候補として扱うための検索。
        複数行が同一 pHash を共有し得る (別版が複数登録されている) ため、
        ``limit(1)`` せず全候補を返す。

        Args:
            phash: 検索する pHash。空文字列の場合は候補なし扱い。

        Returns:
            候補ごとの ``id`` と分類用属性 (``width`` / ``height`` /
            ``has_alpha`` / ``is_grayscale_like``) を含む辞書のリスト。
            一致が無い場合は空リスト。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not phash:
            return []
        with self.session_factory() as session:
            try:
                stmt = select(
                    Image.id,
                    Image.width,
                    Image.height,
                    Image.has_alpha,
                    Image.is_grayscale_like,
                ).where(Image.phash == phash)
                rows = session.execute(stmt).all()
                candidates = [
                    {
                        "id": row.id,
                        "width": row.width,
                        "height": row.height,
                        "has_alpha": row.has_alpha,
                        "is_grayscale_like": row.is_grayscale_like,
                    }
                    for row in rows
                ]
                logger.debug(f"pHash 候補検索: {len(candidates)}件 (pHash={phash})")
                return candidates
            except SQLAlchemyError as e:
                logger.error(f"pHash 候補検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    @classmethod
    def classify_phash_candidate(
        cls,
        new_attrs: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> tuple[PhashClassification, int | None]:
        """pHash 完全一致候補を属性比較で重複/別版/新規に分類する (ADR 0061 §2)。

        ``CLASSIFICATION_ATTRS`` (width / height / has_alpha / is_grayscale_like)
        が全て一致する候補が 1 件でもあれば「重複確定」とし、その既存 ID を返す。
        候補は存在するが属性が一致しない場合は「別版」、候補が無い場合は「新規」。

        ハミング距離による近似重複は導入せず、pHash 完全一致候補のみを起点とする。

        Args:
            new_attrs: 登録対象画像の属性辞書 (``width`` / ``height`` /
                ``has_alpha`` / ``is_grayscale_like`` を含む)。
            candidates: ``find_phash_candidates`` が返す候補リスト。

        Returns:
            ``(分類結果, 既存ID)`` のタプル。重複時のみ既存 ID を返し、
            別版 / 新規時は None。

        """
        if not candidates:
            return PhashClassification.NEW, None

        for candidate in candidates:
            if all(new_attrs.get(attr) == candidate.get(attr) for attr in cls.CLASSIFICATION_ATTRS):
                return PhashClassification.DUPLICATE, candidate["id"]

        return PhashClassification.VARIANT, None

    def find_image_ids_by_phashes(self, phashes: set[str]) -> dict[str, int]:
        """複数pHashに対応する画像IDを一括取得する。

        BATCH_CHUNK_SIZE を超える場合はチャンク分割してクエリを実行する。

        Args:
            phashes: 検索するpHashのセット。

        Returns:
            pHash → image_id のマッピング。見つからなかったpHashは含まれない。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not phashes:
            return {}

        phash_list = list(phashes)

        with self.session_factory() as session:
            try:
                phash_to_id: dict[str, int] = {}
                for i in range(0, len(phash_list), self.BATCH_CHUNK_SIZE):
                    chunk = phash_list[i : i + self.BATCH_CHUNK_SIZE]
                    stmt = select(Image.phash, Image.id).where(Image.phash.in_(chunk))
                    results = session.execute(stmt).all()
                    phash_to_id.update({row.phash: row.id for row in results})
                logger.debug(f"pHash一括検索: {len(phash_to_id)}/{len(phashes)}件見つかりました")
                return phash_to_id
            except SQLAlchemyError as e:
                logger.error(f"pHash一括検索中にエラー: {e}", exc_info=True)
                raise

    def get_annotated_image_ids(self, image_ids: list[int]) -> set[int]:
        """指定IDリストからアノテーション済み画像IDを一括取得する。

        タグまたはキャプションが存在する画像IDのセットを返す。
        BATCH_CHUNK_SIZE を超える場合はチャンク分割してクエリを実行する。

        Args:
            image_ids: 検査対象の画像IDリスト。

        Returns:
            アノテーションが存在する画像IDのセット。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not image_ids:
            return set()

        with self.session_factory() as session:
            try:
                annotated_ids: set[int] = set()
                for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                    # EXISTS サブクエリでタグまたはキャプションの存在を判定
                    stmt = (
                        select(Image.id)
                        .where(Image.id.in_(chunk))
                        .where(
                            or_(
                                exists().where(Tag.image_id == Image.id),
                                exists().where(Caption.image_id == Image.id),
                            ),
                        )
                    )
                    result = session.execute(stmt).scalars().all()
                    annotated_ids.update(result)
                logger.debug(
                    f"アノテーション存在一括チェック: "
                    f"{len(annotated_ids)}/{len(image_ids)}件にアノテーションあり",
                )
                return annotated_ids
            except SQLAlchemyError as e:
                logger.error(
                    f"アノテーション存在一括チェック中にエラー: {e}",
                    exc_info=True,
                )
                raise

    def add_original_image(self, info: dict[str, Any], *, allow_phash_duplicate: bool = False) -> int:
        """オリジナル画像のメタデータを images テーブルに追加します。
        pHash計算失敗時は例外を送出します。

        既定では pHash 完全一致を「重複確定」とみなし、既存 ID を返す後方互換
        挙動を維持します。ADR 0061 の別版分類で「別版 (variant)」と判定された
        画像を登録する場合は ``allow_phash_duplicate=True`` を指定し、同一 pHash の
        新規行として挿入します (分類は呼び出し元 Manager が済ませている前提)。

        Args:
            info (dict[str, Any]): 画像情報を含む辞書。
                                   `calculate_phash` が成功した前提で `phash` キーも含まれる想定。
                                   以下のキーが必須: uuid, phash, original_image_path,
                                   stored_image_path, width, height, format, extension。
                                   その他は Optional。
            allow_phash_duplicate: True の場合、pHash 完全一致の内部重複ガードを
                スキップして新規行を挿入する (ADR 0061 別版登録経路)。

        Returns:
            int: 挿入された画像のID、または (allow_phash_duplicate=False で)
                重複していた既存画像のID。

        Raises:
            ValueError: 必須情報が不足している場合、またはpHash計算済みでない場合。
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        required_keys = {
            "uuid",
            "phash",
            "original_image_path",
            "stored_image_path",
            "width",
            "height",
            "format",
            "extension",
        }
        if not required_keys.issubset(info.keys()):
            missing_keys = required_keys - info.keys()
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

        phash = info["phash"]

        # pHashで重複チェック (別版登録時はスキップ: ADR 0061)
        if not allow_phash_duplicate:
            existing_id = self.find_duplicate_image_by_phash(phash)
            if existing_id is not None:
                logger.warning(f"pHashが一致する画像が既に存在します: ID {existing_id} (pHash: {phash})")
                return existing_id

        # 新しい Image オブジェクトを作成
        new_image = Image(
            uuid=info["uuid"],
            phash=phash,
            original_image_path=str(info["original_image_path"]),  # Pathオブジェクトを文字列に
            stored_image_path=str(info["stored_image_path"]),  # Pathオブジェクトを文字列に
            width=info["width"],
            height=info["height"],
            format=info["format"],
            mode=info.get("mode"),
            has_alpha=info.get("has_alpha"),
            filename=info.get("filename"),
            extension=info["extension"],
            color_space=info.get("color_space"),
            icc_profile=info.get("icc_profile"),
            is_grayscale_like=info.get("is_grayscale_like"),
            colorfulness_score=info.get("colorfulness_score"),
            project_id=info.get("project_id"),
            # created_at, updated_at は server_default で設定される
        )

        with self.session_factory() as session:
            try:
                session.add(new_image)
                session.flush()  # ID を取得するために flush
                image_id = new_image.id
                session.commit()  # コミットは flush 後でもOK
                logger.debug(f"オリジナル画像をDBに追加しました: ID={image_id}, UUID={new_image.uuid}")
                return image_id
            except IntegrityError as e:
                # uuid の UNIQUE 制約違反など
                session.rollback()
                logger.error(f"オリジナル画像の追加中に整合性エラーが発生しました: {e}", exc_info=True)
                # uuid重複の場合、既存IDを探して返すか、あるいは単にエラーとするか?
                # ここではエラーを再発生させる
                raise
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"オリジナル画像の追加中にデータベースエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def _find_existing_processed_image_id(
        self,
        image_id: int,
        width: int,
        height: int,
        filename: str | None,
    ) -> int | None:
        """指定された条件に一致する既存の processed_image の ID を検索します。
        add_processed_image で IntegrityError が発生した場合に使用します。

        Args:
            image_id (int): 元画像の ID。
            width (int): 幅。
            height (int): 高さ。
            filename (Optional[str]): ファイル名。

        Returns:
            Optional[int]: 既存レコードの ID。見つからない場合は None。

        """
        with self.session_factory() as session:
            try:
                stmt = select(ProcessedImage.id).where(
                    ProcessedImage.image_id == image_id,
                    ProcessedImage.width == width,
                    ProcessedImage.height == height,
                    # filename が None の場合も考慮して比較
                    (ProcessedImage.filename == filename)
                    if filename is not None
                    else (ProcessedImage.filename.is_(None)),
                )
                existing_id = session.execute(stmt).scalar_one_or_none()
                return existing_id
            except SQLAlchemyError as e:
                logger.error(f"既存の処理済み画像ID検索中にエラー: {e}", exc_info=True)
                # この検索自体が失敗した場合は None を返すか、エラーを再発生させるか検討
                return None  # ここでは None を返す

    def add_processed_image(self, info: dict[str, Any]) -> int | None:
        """処理済み画像のメタデータを processed_images テーブルに追加します。
        重複する場合は既存の ID を返します。

        Args:
            info (dict[str, Any]): 処理済み画像情報を含む辞書。
                                   必須キー: image_id, stored_image_path, width, height, has_alpha。
                                   その他は Optional。

        Returns:
            int | None: 挿入された処理済み画像のID、または重複していた既存画像のID。
                        検索に失敗した場合は None を返す可能性あり。

        Raises:
            ValueError: 必須情報が不足している場合、または関連する Image が存在しない場合。
            SQLAlchemyError: 予期せぬデータベース操作でエラーが発生した場合 (IntegrityError 以外)。

        """
        required_keys = {"image_id", "stored_image_path", "width", "height", "has_alpha"}
        if not required_keys.issubset(info.keys()):
            missing_keys = required_keys - info.keys()
            raise ValueError(f"必須情報が不足しています: {', '.join(missing_keys)}")

        image_id = info["image_id"]
        width = info["width"]
        height = info["height"]
        filename = info.get("filename")  # filename は Optional

        # 関連する Image レコードが存在するか確認 (FK制約のため)
        if not self._image_exists(image_id):
            raise ValueError(f"関連するオリジナル画像が見つかりません: image_id={image_id}")

        # 新しい ProcessedImage オブジェクトを作成
        new_processed_image = ProcessedImage(
            image_id=image_id,
            stored_image_path=str(info["stored_image_path"]),  # Pathオブジェクトを文字列に
            width=width,
            height=height,
            mode=info.get("mode"),
            has_alpha=info["has_alpha"],
            filename=filename,
            color_space=info.get("color_space"),
            icc_profile=info.get("icc_profile"),
            upscaler_used=info.get("upscaler_used"),  # アップスケーラー情報を追加
            # created_at, updated_at は server_default で設定される
        )

        with self.session_factory() as session:
            try:
                session.add(new_processed_image)
                session.flush()  # ID を取得するために flush
                processed_image_id = new_processed_image.id
                session.commit()
                logger.debug(
                    f"処理済み画像をDBに追加しました: ID={processed_image_id}, 親画像ID={image_id}",
                )
                return processed_image_id
            except IntegrityError:
                # UNIQUE 制約違反 (image_id, width, height, filename)
                session.rollback()
                logger.warning(
                    f"処理済み画像の追加中に整合性エラーが発生しました。"
                    f" (おそらく重複: image_id={image_id}, width={width}, height={height}, filename={filename})."
                    f" 既存のIDを検索します。",
                )
                # 既存のIDを検索して返す
                existing_id = self._find_existing_processed_image_id(image_id, width, height, filename)
                if existing_id:
                    logger.debug(f"既存の処理済み画像IDが見つかりました: {existing_id}")
                else:
                    # 通常ここには来ないはずだが、もし検索でも見つからなければ警告
                    logger.error(
                        f"整合性エラー後、既存の処理済み画像が見つかりませんでした。"
                        f" 条件: image_id={image_id}, width={width}, height={height}, filename={filename}",
                    )
                return existing_id  # None の可能性もある
            except SQLAlchemyError as e:
                session.rollback()
                logger.error(
                    f"処理済み画像の追加中に予期せぬデータベースエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise  # IntegrityError 以外の DB エラーは再発生させる

    # --- Metadata ---

    def get_image_metadata(self, image_id: int) -> dict[str, Any] | None:
        """指定されたIDのオリジナル画像メタデータを辞書形式で取得します。

        Args:
            image_id (int): 取得する画像のID。

        Returns:
            Optional[dict[str, Any]]: 画像メタデータを含む辞書。画像が見つからない場合はNone。
                - rating_value: 最新のRating値（ratingsテーブルから取得）
                - score_value: 最新のScore値（scoresテーブルから取得）

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        with self.session_factory() as session:
            try:
                # 主キー検索には session.get が効率的
                # relationshipをeager loadingで取得（ratings, scores）
                stmt = (
                    select(Image)
                    .where(Image.id == image_id)
                    .options(
                        selectinload(Image.ratings).selectinload(Rating.model),
                        selectinload(Image.scores),
                    )
                )
                image: Image | None = session.execute(stmt).scalar_one_or_none()

                if image is None:
                    logger.warning(f"画像メタデータが見つかりません: image_id={image_id}")
                    return None

                # SQLAlchemy オブジェクトを辞書に変換
                metadata = {c.name: getattr(image, c.name) for c in image.__table__.columns}

                # Rating/Score情報を整形して追加（Issue #4対応）
                annotations = self._format_annotations_for_metadata(image)
                metadata.update(annotations)

                logger.debug(f"画像メタデータを取得しました: image_id={image_id}")
                return metadata

            except SQLAlchemyError as e:
                logger.error(
                    f"画像メタデータの取得中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def get_images_metadata_batch(self, image_ids: list[int]) -> list[dict[str, Any]]:
        """指定された複数IDのオリジナル画像メタデータを一括取得する。

        内部的に _fetch_filtered_metadata() を使用し、joinedloadで取得する。
        BATCH_CHUNK_SIZE を超える場合はチャンク分割してクエリを実行する。

        Args:
            image_ids: 取得する画像IDのリスト。

        Returns:
            画像メタデータ辞書のリスト。見つからなかったIDは結果に含まれない。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not image_ids:
            return []

        with self.session_factory() as session:
            try:
                # チャンク分割でSQLiteバインド変数上限を回避
                result: list[dict[str, Any]] = []
                for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                    result.extend(self._fetch_filtered_metadata(session, chunk, resolution=0))
                return result
            except SQLAlchemyError as e:
                logger.error(
                    f"画像メタデータの一括取得中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    def get_batch_available_resolutions(self, image_ids: list[int]) -> dict[int, list[int]]:
        """複数画像の利用可能な処理済み解像度を一括取得する。

        1クエリで全 ProcessedImage を取得し、Python側で解像度マッピングを構築する。
        N+1ループ（image_id × resolution の組み合わせ）の代替として使用する。

        Args:
            image_ids: 画像IDリスト

        Returns:
            image_id -> 利用可能な解像度リスト のマッピング。
            ProcessedImage が存在しない image_id は空リストになる。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        if not image_ids:
            return {}

        by_image: dict[int, list[dict[str, Any]]] = {image_id: [] for image_id in image_ids}
        with self.session_factory() as session:
            for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                rows = (
                    session.execute(select(ProcessedImage).where(ProcessedImage.image_id.in_(chunk)))
                    .scalars()
                    .all()
                )
                for row in rows:
                    metadata = {c.name: getattr(row, c.name) for c in row.__table__.columns}
                    if row.image_id in by_image:
                        by_image[row.image_id].append(metadata)

        target_resolutions = [512, 768, 1024, 1536]
        return {
            image_id: [
                target
                for target in target_resolutions
                if self._filter_by_resolution(by_image[image_id], target) is not None
            ]
            for image_id in image_ids
        }

    def get_processed_image(
        self,
        image_id: int,
        resolution: int = 0,
        all_data: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]] | None:  # 戻り値の型を調整
        """指定された image_id に関連する処理済み画像のメタデータを取得します。
        resolution に基づいてフィルタリングするか、all_data=True で全て取得します。

        Args:
            image_id (int): 元画像のID。
            resolution (int): フィルタリングの基準となる解像度 (長辺)。
                              0 の場合は最も解像度が低いものを返します。
            all_data (bool): True の場合はフィルタリングせず、関連する全ての
                             処理済み画像メタデータをリストで返します。

        Returns:
            Optional[Union[dict[str, Any], list[dict[str, Any]]]]:
                - all_data=True: 処理済み画像メタデータの辞書のリスト。見つからない場合は空リスト。
                - all_data=False: 条件に一致した処理済み画像メタデータの辞書。見つからない場合は None。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        with self.session_factory() as session:
            try:
                # image_id に紐づく全ての処理済み画像を取得
                stmt = select(ProcessedImage).where(ProcessedImage.image_id == image_id)
                results: list[ProcessedImage] = list(session.execute(stmt).scalars().all())

                if not results:
                    logger.warning(f"処理済み画像が見つかりません: image_id={image_id}")
                    return [] if all_data else None

                # モデルオブジェクトを辞書のリストに変換
                metadata_list = [
                    {c.name: getattr(img, c.name) for c in img.__table__.columns} for img in results
                ]

                if all_data:
                    logger.debug(
                        f"全 {len(metadata_list)} 件の処理済み画像メタデータを取得しました: image_id={image_id}",
                    )
                    return metadata_list

                # 解像度に基づいてフィルタリング
                selected_metadata: dict[str, Any] | None = None
                if resolution == 0:
                    # 最も解像度が低いもの (面積で比較)
                    selected_metadata = min(metadata_list, key=lambda x: x["width"] * x["height"])
                    logger.debug(
                        f"最低解像度の処理済み画像を選択しました: image_id={image_id}, id={selected_metadata['id']}",
                    )
                else:
                    # 指定解像度に最も近いものを選択
                    selected_metadata = self._filter_by_resolution(metadata_list, resolution)

                # all_data=False の場合、ここで選択されたメタデータ (またはNone) を返す
                if not all_data:
                    if selected_metadata:
                        logger.debug(
                            f"解像度 {resolution} に一致する処理済み画像を選択しました: image_id={image_id}, id={selected_metadata.get('id')}",
                        )
                    else:
                        logger.warning(
                            f"解像度 {resolution} に一致する処理済み画像が見つかりませんでした: image_id={image_id}",
                        )
                    return selected_metadata

            except SQLAlchemyError as e:
                logger.error(
                    f"処理済み画像の取得中にエラーが発生しました (ID: {image_id}): {e}",
                    exc_info=True,
                )
                raise

    def _filter_by_resolution(
        self,
        metadata_list: list[dict[str, Any]],
        resolution: int,
    ) -> dict[str, Any] | None:
        """解像度に基づいてメタデータをフィルタリングします。
        指定された解像度に最も近いもの (面積比で許容誤差20%以内) を返します。

        Args:
            metadata_list (list[dict[str, Any]]): ProcessedImageのメタデータの辞書のリスト。
            resolution (int): 目標解像度 (長辺)。

        Returns:
            dict[str, Any] | None: フィルタリングされたメタデータの辞書。見つからない場合はNone。

        """
        # 型安全性チェック: resolution が文字列の場合は int に変換
        if isinstance(resolution, str):
            try:
                resolution = int(resolution)
                logger.warning(
                    f"解像度パラメータが文字列として渡されました: '{resolution}' -> {resolution}",
                )
            except ValueError:
                logger.error(f"解像度パラメータの変換に失敗しました: '{resolution}'")
                return None

        best_match: dict[str, Any] | None = None
        min_error_ratio = float("inf")

        target_area = resolution * resolution  # Target area based on square of the long side

        for metadata in metadata_list:
            width = metadata.get("width", 0)
            height = metadata.get("height", 0)
            if not width or not height:
                continue

            # 1. Check for exact match on the longer side
            long_side = max(width, height)
            if long_side == resolution:
                logger.debug(f"Exact resolution match found: {metadata['id']}")
                return metadata  # Exact match found, return immediately

            # 2. Calculate area ratio difference if no exact match yet
            short_side = min(width, height)
            actual_area = long_side * short_side

            # Avoid division by zero if target_area is 0 (resolution is 0)
            # Though resolution=0 should be handled before calling this function
            if target_area == 0:
                error_ratio = float("inf")  # Or handle as a special case if needed
            else:
                error_ratio = abs(target_area - actual_area) / target_area

            # Check if within 20% tolerance and better than the current best match
            if error_ratio <= 0.2 and error_ratio < min_error_ratio:
                min_error_ratio = error_ratio
                best_match = metadata

        if best_match:
            logger.debug(
                f"Closest resolution match found (error: {min_error_ratio:.2f}): {best_match['id']}",
            )
        else:
            logger.debug(f"No suitable processed image found for resolution {resolution}")

        return best_match  # Return the best match found within tolerance, or None

    # --- Annotation Read Helpers (single image, per-item formatters) ---

    @staticmethod
    def _format_tag_annotation(tag: Any) -> dict[str, Any]:
        """タグアノテーションをdict形式にフォーマットする。

        Args:
            tag: タグORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
            "id": tag.id,
            "tag": tag.tag,
            "tag_id": tag.tag_id,
            "model_id": tag.model_id,
            "existing": tag.existing,
            "is_edited_manually": tag.is_edited_manually,
            "confidence_score": tag.confidence_score,
            "created_at": tag.created_at,
            "updated_at": tag.updated_at,
        }

    @staticmethod
    def _format_caption_annotation(caption: Any) -> dict[str, Any]:
        """キャプションアノテーションをdict形式にフォーマットする。

        Args:
            caption: キャプションORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
            "id": caption.id,
            "caption": caption.caption,
            "model_id": caption.model_id,
            "existing": caption.existing,
            "is_edited_manually": caption.is_edited_manually,
            "created_at": caption.created_at,
            "updated_at": caption.updated_at,
        }

    @staticmethod
    def _format_score_annotation(score: Any) -> dict[str, Any]:
        """スコアアノテーションをdict形式にフォーマットする。

        Args:
            score: スコアORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        return {
            "id": score.id,
            "score": score.score,
            "model_id": score.model_id,
            "is_edited_manually": score.is_edited_manually,
            "created_at": score.created_at,
            "updated_at": score.updated_at,
        }

    @staticmethod
    def _format_rating_annotation(rating: Any) -> dict[str, Any]:
        """レーティングアノテーションをdict形式にフォーマットする。

        Args:
            rating: レーティングORMオブジェクト。

        Returns:
            フォーマット済み辞書。

        """
        model_name = rating.model.name if rating.model else "Unknown"
        litellm_model_id = rating.model.litellm_model_id if rating.model else None
        is_manual = litellm_model_id == MANUAL_EDIT_LITELLM_ID or model_name == MANUAL_EDIT_NAME
        return {
            "id": rating.id,
            "raw_rating_value": rating.raw_rating_value,
            "normalized_rating": rating.normalized_rating,
            "model_id": rating.model_id,
            "model": model_name,
            "model_name": model_name,
            "source": "Manual" if is_manual else "AI",
            "confidence_score": rating.confidence_score,
            "created_at": rating.created_at,
            "updated_at": rating.updated_at,
        }

    @staticmethod
    def _format_score_label_annotation(sl: Any) -> dict[str, Any]:
        """スコアラベルアノテーション (ADR 0028) を dict 形式にフォーマットする。

        ADR 0028 で「常に model 名と組で保持」と決定したため、他 per-item helper と
        異なり ``model`` (model.name) を含める。``sl.model`` relationship が eager
        load されている前提 (``joinedload(ScoreLabel.model)`` 等)。

        Args:
            sl: ScoreLabel ORM オブジェクト。

        Returns:
            フォーマット済み辞書 (model 含む)。
        """
        return {
            "id": sl.id,
            "label": sl.label,
            "model_id": sl.model_id,
            "model": sl.model.name if sl.model else "Unknown",
            "is_edited_manually": sl.is_edited_manually,
            "created_at": sl.created_at,
            "updated_at": sl.updated_at,
        }

    def get_image_annotations(self, image_id: int) -> dict[str, Any]:
        """指定された画像IDのアノテーション(タグ、キャプション、スコア、スコアラベル、レーティング)を取得する。

        Eager Loadingを使用して関連データを効率的に取得する。

        Args:
            image_id: アノテーションを取得する画像のID。

        Returns:
            アノテーションデータを含む辞書。
            キー: 'tags', 'captions', 'scores', 'score_labels', 'ratings',
            'quality_summary' (ADR 0029、derived view)
            画像が存在しない場合は空のリストを持つ辞書を返す。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。

        """
        logger.debug(f"Getting annotations for image_id: {image_id}")
        annotations: dict[str, Any] = {
            "tags": [],
            "captions": [],
            "scores": [],
            "score_labels": [],
            "ratings": [],
            "quality_summary": {},
        }

        with self.session_factory() as session:
            try:
                stmt = (
                    select(Image)
                    .where(Image.id == image_id)
                    .options(
                        joinedload(Image.tags),
                        joinedload(Image.captions),
                        joinedload(Image.scores),
                        # ADR 0028: score_labels は model 名と組で返すため
                        # ScoreLabel.model も eager load する
                        joinedload(Image.score_labels).joinedload(ScoreLabel.model),
                        joinedload(Image.ratings).joinedload(Rating.model),
                        joinedload(Image.processed_images),
                    )
                )
                image = session.execute(stmt).unique().scalar_one_or_none()

                if image is None:
                    logger.warning(f"画像が見つかりません: image_id={image_id}")
                    return annotations

                if image.tags:
                    annotations["tags"] = [self._format_tag_annotation(t) for t in image.tags]
                if image.captions:
                    annotations["captions"] = [self._format_caption_annotation(c) for c in image.captions]
                if image.scores:
                    annotations["scores"] = [self._format_score_annotation(s) for s in image.scores]
                if image.score_labels:
                    annotations["score_labels"] = [
                        self._format_score_label_annotation(sl) for sl in image.score_labels
                    ]
                if image.ratings:
                    annotations["ratings"] = [self._format_rating_annotation(r) for r in image.ratings]

                # ADR 0029: derived view、永続化しない。raw annotation から毎回計算する。
                annotations["quality_summary"] = compute_quality_summary(
                    annotations["score_labels"], annotations["scores"]
                )

                logger.info(
                    f"取得したアノテーション数: tags={len(annotations['tags'])}, "
                    f"captions={len(annotations['captions'])}, scores={len(annotations['scores'])}, "
                    f"score_labels={len(annotations['score_labels'])}, "
                    f"ratings={len(annotations['ratings'])} for image_id={image_id}",
                )
                return annotations

            except SQLAlchemyError as e:
                logger.error(
                    f"画像ID {image_id} のアノテーション取得中にエラーが発生しました: {e}",
                    exc_info=True,
                )
                raise

    # --- Filter Helpers ---

    def _parse_datetime_str(self, date_str: str | None) -> datetime.datetime | None:
        """日付文字列を UTC timezone-aware datetime オブジェクトに変換。

        アプリケーション全体でUTC統一方針に従い、入力文字列をUTCとして解釈します。
        データベースは TIMESTAMP(timezone=True) でUTC保存されているため、
        フィルタリング時の比較もUTC基準で行います。

        Args:
            date_str: ISO 8601形式の日付文字列 (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS)

        Returns:
            datetime.datetime | None: UTC timezone-aware datetime オブジェクト、無効な場合は None

        """
        if not date_str:
            return None
        try:
            # ISO 8601形式 (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS) を想定
            # スペース区切りも考慮
            date_str = date_str.replace(" ", "T")
            # マイクロ秒以下を削除 (存在する場合)
            if "." in date_str:
                date_str = date_str.split(".")[0]

            # naive datetime としてパースしてからUTCタイムゾーンを設定
            # 入力文字列はUTC時刻として解釈する（アプリケーション統一方針）
            parsed_dt = datetime.datetime.fromisoformat(date_str)

            # タイムゾーン情報がない場合はUTCとして扱う
            if parsed_dt.tzinfo is None:
                from datetime import UTC

                parsed_dt = parsed_dt.replace(tzinfo=UTC)

            return parsed_dt
        except ValueError:
            logger.warning(f"無効な日付形式です: {date_str}。無視されます。")
            return None

    def _prepare_like_pattern(self, term: str) -> tuple[str, bool]:
        """検索語からLIKEパターンと完全一致フラグを準備します。"""
        is_exact = False
        pattern = term.strip()  # 前後の空白を除去

        if pattern.startswith('"') and pattern.endswith('"') and len(pattern) > 1:
            # ダブルクォートで囲まれている場合は完全一致
            is_exact = True
            pattern = pattern[1:-1]  # クォートを除去
            # クォート内のワイルドカードはリテラルとして扱う
            pattern = pattern.replace("%", "\\%").replace("_", "\\_").replace("*", "*")
        elif "*" in pattern:
            # アスタリスクがあれば LIKE 検索 (部分一致)
            # アスタリスクを SQL の % に置換
            pattern = pattern.replace("%", "\\%").replace("_", "\\_").replace("*", "%")
            is_exact = False
        else:
            # デフォルトは部分一致 (LIKE)
            is_exact = False
            # 前後に % を追加
            pattern = f"%{pattern.replace('%', '\\%').replace('_', '\\_')}%"

        # logger.debug(f"Prepared pattern: '{pattern}', is_exact: {is_exact} for term: '{term}'")
        return pattern, is_exact

    def _apply_date_filter(
        self,
        query: Select[Any],
        start_dt: datetime.datetime | None,
        end_dt: datetime.datetime | None,
    ) -> Select[Any]:
        """クエリに日付フィルタを適用します (画像またはアノテーションの更新日時)。"""
        if not start_dt and not end_dt:
            return query

        # 画像自体の作成/更新日時のみを考慮
        img_date_conds = []
        if start_dt:
            img_date_conds.append(Image.updated_at >= start_dt)
        if end_dt:
            img_date_conds.append(Image.updated_at <= end_dt)
        if img_date_conds:
            query = query.where(and_(*img_date_conds))

        return query

    def _apply_tag_filter(
        self,
        query: Select[Any],
        tags: list[str] | None,
        excluded_tags: list[str] | None,
        use_and: bool,
        include_untagged: bool,
    ) -> Select[Any]:
        """クエリにタグフィルタを適用します。"""
        if include_untagged:
            # タグが存在しない画像 (outerjoinしてTag.idがNULL)
            # 注: この条件は他のタグ/キャプション条件と併用されない前提 (Manager側で制御想定)
            query = query.outerjoin(Tag, Image.id == Tag.image_id).where(Tag.id.is_(None))
        elif tags:
            # use_and (AND検索) の場合、タグごとにJOIN条件を追加する
            if use_and:
                logger.debug(f"Applying AND tag filter (EXISTS) for tags: {tags}")
                for _i, tag_term in enumerate(tags):
                    pattern, is_exact = self._prepare_like_pattern(tag_term)
                    # is_exact フラグに基づいて条件を選択
                    subquery_condition = (Tag.tag == pattern) if is_exact else Tag.tag.like(pattern)
                    # EXISTS サブクエリを作成
                    exists_subquery = (
                        select(Tag.id)  # SELECT句は何でもよい (通常は 1 や PK)
                        .where(
                            Tag.image_id == Image.id,  # WHERE句に明示的な相関条件は残す
                            subquery_condition,
                        )
                        .correlate(Image)  # 明示的に相関させる
                        .exists()
                    )
                    # メインクエリに EXISTS 条件を追加
                    query = query.where(exists_subquery)
            else:
                # use_and=False (OR検索) の場合、単一のJOINとOR条件
                logger.debug(f"Applying OR tag filter for tags: {tags}")
                tag_criteria = []
                for t in tags:
                    pattern, is_exact = self._prepare_like_pattern(t)
                    if is_exact:
                        tag_criteria.append(Tag.tag == pattern)
                    else:
                        tag_criteria.append(Tag.tag.like(pattern))
                if tag_criteria:
                    query = query.join(Tag, Image.id == Tag.image_id).where(or_(*tag_criteria))
                    # logger.debug(f"Query after OR tag join: {query}") # クエリ確認用

        if excluded_tags and not include_untagged:
            logger.debug(f"Applying excluded tag filter (NOT EXISTS) for tags: {excluded_tags}")
            for excluded_tag in excluded_tags:
                pattern, is_exact = self._prepare_like_pattern(excluded_tag)
                excluded_condition = (Tag.tag == pattern) if is_exact else Tag.tag.like(pattern)
                not_exists_subquery = (
                    select(Tag.id)
                    .where(
                        Tag.image_id == Image.id,
                        excluded_condition,
                    )
                    .correlate(Image)
                    .exists()
                )
                query = query.where(not_(not_exists_subquery))

        return query

    def _apply_caption_filter(self, query: Select[Any], caption: str | None) -> Select[Any]:
        """クエリにキャプションフィルタを適用します (EXISTSを使用)。"""
        if caption:
            logger.debug(f"Applying caption filter (EXISTS) for caption: '{caption}'")
            pattern, is_exact = self._prepare_like_pattern(caption)

            caption_filter = (Caption.caption == pattern) if is_exact else (Caption.caption.like(pattern))

            # EXISTS サブクエリを作成
            exists_subquery = (
                select(Caption.id)
                .where(
                    Caption.image_id == Image.id,  # メインクエリの Image と相関させる
                    caption_filter,
                )
                .correlate(Image)  # 明示的に相関させる
                .exists()
            )
            # メインクエリに EXISTS 条件を追加
            query = query.where(exists_subquery)
        return query

    def _apply_ai_rating_filter(self, query: Select[Any], ai_rating_filter: str) -> Select[Any]:
        """クエリにAI評価レーティングフィルタを適用します (多数決ロジック)。

        1つの画像に複数のAIモデルによる異なる評価がある場合、
        50%以上のAI評価が指定されたレーティングと一致する画像のみを返します。

        Args:
            query (Select): 適用対象のクエリ
            ai_rating_filter (str): フィルタリングするレーティング値 (PG, PG-13, R, X, XXX, UNRATED)

        Returns:
            Select: AIレーティングフィルタが適用されたクエリ

        """
        logger.debug(f"Applying AI rating filter (majority vote) for rating: '{ai_rating_filter}'")

        # MANUAL_EDIT は AI フィルタから除外（AI 判定行のみを対象とする）
        ai_only = Rating.model_id.in_(select(Model.id).where(Model.name != "MANUAL_EDIT"))

        # UNRATED / RATED: AI レーティングの有無でフィルタ
        if ai_rating_filter in ("UNRATED", "RATED"):
            has_any_ai_rating = exists(
                select(Rating.id).where(Rating.image_id == Image.id, ai_only)
            ).correlate(Image)
            if ai_rating_filter == "UNRATED":
                query = query.where(not_(has_any_ai_rating))
                logger.debug("AI rating filter applied: UNRATED (no AI ratings)")
            else:
                query = query.where(has_any_ai_rating)
                logger.debug("AI rating filter applied: RATED (has any AI rating)")
            return query

        # 多数決ロジック: 画像ごとに総AI評価数とマッチング数を計算
        # マッチング数 >= 総評価数 / 2.0 の画像のみを返す

        # サブクエリ1: 画像ごとの総AI評価数（MANUAL_EDIT 除外）
        total_ratings_subquery = (
            select(Rating.image_id, func.count(Rating.id).label("total_count"))
            .where(ai_only)
            .group_by(Rating.image_id)
            .subquery()
        )

        # サブクエリ2: 画像ごとのマッチング評価数（MANUAL_EDIT 除外）
        matching_ratings_subquery = (
            select(Rating.image_id, func.count(Rating.id).label("matching_count"))
            .where(func.lower(Rating.normalized_rating) == ai_rating_filter.lower(), ai_only)
            .group_by(Rating.image_id)
            .subquery()
        )

        # EXISTS条件: マッチング数 >= 総評価数 / 2.0
        # COALESCE(matching_count, 0) で、マッチが0件の画像も処理
        majority_vote_condition = exists(
            select(1)
            .select_from(total_ratings_subquery)
            .outerjoin(
                matching_ratings_subquery,
                total_ratings_subquery.c.image_id == matching_ratings_subquery.c.image_id,
            )
            .where(
                total_ratings_subquery.c.image_id == Image.id,
                func.coalesce(matching_ratings_subquery.c.matching_count, 0)
                >= (total_ratings_subquery.c.total_count / 2.0),
            ),
        ).correlate(Image)

        query = query.where(majority_vote_condition)
        logger.debug("AI rating filter applied with majority vote logic")
        return query

    def _apply_unrated_filter(
        self,
        query: Select[Any],
        include_unrated: bool,
        only_unrated: bool = False,
    ) -> Select[Any]:
        """クエリに未評価画像フィルタを適用します (Either-based ロジック)。

        only_unrated=True の場合、Rating テーブルに行が無い画像のみを返します。
        include_unrated=False の場合、手動評価またはAI評価のいずれか1つ以上を持つ画像のみを返します。
        include_unrated=True の場合、フィルタリングを行いません。

        Args:
            query (Select): 適用対象のクエリ
            include_unrated (bool): 未評価画像を含めるかどうか
            only_unrated (bool): 未評価画像のみに絞るかどうか

        Returns:
            Select: 未評価フィルタが適用されたクエリ

        """
        has_any_rating = exists().where(Rating.image_id == Image.id).correlate(Image)
        if only_unrated:
            query = query.where(~has_any_rating)
            logger.debug("Unrated filter applied: images must have no ratings")
            return query

        if not include_unrated:
            # MANUAL_EDIT も含む Rating テーブルに行が存在する画像のみを返す
            # (manual rating も Rating テーブルに統一されたため OR は不要)
            query = query.where(has_any_rating)
            logger.debug("Unrated filter applied: images must have at least one rating")

        return query

    def _apply_missing_model_filter(
        self,
        query: Select[Any],
        missing_model_litellm_id: str | None,
    ) -> Select[Any]:
        """指定モデルの annotation が無い画像のみを返すフィルタを適用する。"""
        if not missing_model_litellm_id:
            return query

        model_id_subquery = select(Model.id).where(Model.litellm_model_id == missing_model_litellm_id)
        has_tag = (
            exists().where(Tag.image_id == Image.id, Tag.model_id.in_(model_id_subquery)).correlate(Image)
        )
        has_caption = (
            exists()
            .where(
                Caption.image_id == Image.id,
                Caption.model_id.in_(model_id_subquery),
            )
            .correlate(Image)
        )
        has_score = (
            exists()
            .where(
                Score.image_id == Image.id,
                Score.model_id.in_(model_id_subquery),
            )
            .correlate(Image)
        )
        has_score_label = (
            exists()
            .where(
                ScoreLabel.image_id == Image.id,
                ScoreLabel.model_id.in_(model_id_subquery),
            )
            .correlate(Image)
        )
        has_rating = (
            exists()
            .where(
                Rating.image_id == Image.id,
                Rating.model_id.in_(model_id_subquery),
            )
            .correlate(Image)
        )

        query = query.where(not_(or_(has_tag, has_caption, has_score, has_score_label, has_rating)))
        logger.debug(f"Missing model filter applied: litellm_model_id={missing_model_litellm_id}")
        return query

    def _apply_nsfw_filter(self, query: Select[Any], include_nsfw: bool, session: Session) -> Select[Any]:
        """クエリにNSFWフィルタを適用します。"""
        if not include_nsfw:
            # NSFWとみなすレーティング値 (小文字にして比較)
            nsfw_ratings = ["r", "x", "xxx"]

            # AIによるレーティングに基づく除外条件
            # Rating テーブルを LEFT JOIN する (なければ Rating.id is NULL)
            # query = query.outerjoin(Rating, Image.id == Rating.image_id)
            # 条件: Rating が存在し、かつ normalized_rating が NSFW リストに含まれる
            ai_nsfw_condition = (
                exists()
                .where(Rating.image_id == Image.id, func.lower(Rating.normalized_rating).in_(nsfw_ratings))
                .correlate(Image)
            )

            # 手動レーティングに基づく除外条件（ratingsテーブルから最新のMANUAL_EDIT ratingを参照）
            # ADR 0035 段階 4: MANUAL_EDIT model lookup は ModelRepository static helper を直接呼ぶ。
            manual_edit_model_id = ModelRepository._get_or_create_manual_edit_model(session)
            manual_nsfw_condition = (
                exists()
                .where(
                    Rating.image_id == Image.id,
                    Rating.model_id == manual_edit_model_id,
                    func.lower(Rating.normalized_rating).in_(nsfw_ratings),
                )
                .correlate(Image)
            )

            # タグベースのNSFW判定（"nsfw" / "explicit" タグが付いている画像を除外）
            tag_nsfw_condition = (
                exists()
                .where(Tag.image_id == Image.id, func.lower(Tag.tag).in_(["nsfw", "explicit"]))
                .correlate(Image)
            )

            # AIレーティング、手動レーティング、またはタグがNSFWである画像を除外
            query = query.where(not_(or_(ai_nsfw_condition, manual_nsfw_condition, tag_nsfw_condition)))
            # レーティング情報がない (NULL) 画像は除外しない
        return query

    def _apply_score_filter(
        self,
        query: Select[Any],
        score_min: float | None,
        score_max: float | None,
    ) -> Select[Any]:
        """クエリにスコア範囲フィルタを適用します。

        Args:
            query: 適用対象のクエリ
            score_min: 最小スコア値（0.0-10.0）
            score_max: 最大スコア値（0.0-10.0）

        Returns:
            フィルタ適用済みのクエリ

        """
        if score_min is None and score_max is None:
            return query

        # DB値（0.0-10.0）で直接比較
        db_min = score_min if score_min is not None else 0.0
        db_max = score_max if score_max is not None else 10.0

        # 指定範囲内のスコアを持つ画像のみを含める
        score_condition = (
            exists()
            .where(
                Score.image_id == Image.id,
                Score.score >= db_min,
                Score.score <= db_max,
            )
            .correlate(Image)
        )

        query = query.where(score_condition)
        logger.debug(
            f"Score filter applied: {db_min:.2f} - {db_max:.2f}",
        )

        return query

    def _apply_manual_filters(
        self,
        query: Select[Any],
        manual_rating_filter: str | None,
        manual_edit_filter: bool | None,
        session: Session,
    ) -> Select[Any]:
        """クエリに手動評価と手動編集フラグのフィルタを適用します。"""
        if manual_rating_filter:
            # ADR 0035 段階 4: MANUAL_EDIT model lookup は ModelRepository static helper を直接呼ぶ。
            manual_edit_model_id = ModelRepository._get_or_create_manual_edit_model(session)

            if manual_rating_filter in ("UNRATED", "RATED"):
                # 手動レーティングの有無でフィルタ
                has_manual_rating_subq = (
                    select(Rating.image_id).where(Rating.model_id == manual_edit_model_id).distinct()
                )
                if manual_rating_filter == "UNRATED":
                    query = query.where(Image.id.notin_(has_manual_rating_subq))
                else:
                    query = query.where(Image.id.in_(has_manual_rating_subq))
            else:
                # 特定の手動レーティングを持つ画像をフィルタ
                manual_rating_subq = (
                    select(Rating.image_id)
                    .where(Rating.normalized_rating == manual_rating_filter)
                    .where(Rating.model_id == manual_edit_model_id)
                    .distinct()
                )
                query = query.where(Image.id.in_(manual_rating_subq))

        if manual_edit_filter is not None:
            has_manual_edit = or_(
                exists().where(Tag.image_id == Image.id, Tag.is_edited_manually.is_(True)).correlate(Image),
                exists()
                .where(Caption.image_id == Image.id, Caption.is_edited_manually.is_(True))
                .correlate(Image),
                exists().where(Score.image_id == Image.id, Score.is_edited_manually).correlate(Image),
            )

            if manual_edit_filter:
                query = query.where(has_manual_edit)
            else:
                query = query.where(not_(has_manual_edit))

        return query

    # --- Annotation Format for Metadata (batch read helpers) ---

    def _format_tags(self, image: Image, annotations: dict[str, Any]) -> None:
        """タグアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.tags:
            annotations["tags"] = [
                {
                    "id": tag.id,
                    "tag": tag.tag,
                    "tag_id": tag.tag_id,
                    "model_id": tag.model_id,
                    "model_name": tag.model.name if tag.model else "Unknown",
                    "source": "Manual" if (tag.is_edited_manually or tag.existing) else "AI",
                    "existing": tag.existing,
                    "is_edited_manually": tag.is_edited_manually,
                    "confidence_score": tag.confidence_score,
                    "created_at": tag.created_at,
                    "updated_at": tag.updated_at,
                }
                for tag in image.tags
            ]
            annotations["tags_text"] = ", ".join([tag.tag for tag in image.tags])
        else:
            annotations["tags"] = []
            annotations["tags_text"] = ""

    def _format_captions(self, image: Image, annotations: dict[str, Any]) -> None:
        """キャプションアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.captions:
            annotations["captions"] = [
                {
                    "id": caption.id,
                    "caption": caption.caption,
                    "model_id": caption.model_id,
                    "model_name": caption.model.name if caption.model else "Unknown",
                    "existing": caption.existing,
                    "is_edited_manually": caption.is_edited_manually,
                    "created_at": caption.created_at,
                    "updated_at": caption.updated_at,
                }
                for caption in image.captions
            ]
            from datetime import datetime

            latest_caption = max(
                image.captions,
                key=lambda c: c.created_at if c.created_at else datetime.min,
            )
            annotations["caption_text"] = latest_caption.caption
        else:
            annotations["captions"] = []
            annotations["caption_text"] = ""

    def _format_scores(self, image: Image, annotations: dict[str, Any]) -> None:
        """スコアアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.scores:
            annotations["scores"] = [
                {
                    "id": score.id,
                    "score": score.score,
                    "model_id": score.model_id,
                    "model_name": score.model.name if score.model else "Unknown",
                    "is_edited_manually": score.is_edited_manually,
                    "created_at": score.created_at,
                    "updated_at": score.updated_at,
                }
                for score in image.scores
            ]
            annotations["score_value"] = self._derive_display_score(image)
        else:
            annotations["scores"] = []
            annotations["score_value"] = 0.0

    @staticmethod
    def _derive_display_score(image: Image) -> float:
        """Score 行から 0.0-10.0 の表示スコア (``score_value``) を導出する (Issue #626)。

        導出規約:

        - 手動行 (``is_edited_manually=True``) があれば、その最新の生値 (既に 0-10) を
          最優先で採用する。
        - 手動行が無ければ AI Score 行を model 単位で 1 値にまとめ、各 model の生値を
          ``calibrate_to_display`` で 0-10 化した平均を採用する。
        - Score 行が空 (呼び出し側で別途処理) の場合の保険として 0.0 を返す。

        新データは scorer 1 行/model だが、旧データ (Issue #626 以前) では同一 model に
        positive/complement 2 行が残り得る。その場合は best-effort で最新行を採用する。
        legacy 2 行データは近似値となり得るため、正確化には再アノテーションが必要。

        Args:
            image: scores リレーションを load 済みの Image。

        Returns:
            0.0-10.0 の表示スコア。
        """
        manual_scores = [s for s in image.scores if s.is_edited_manually]
        if manual_scores:
            latest_manual = max(manual_scores, key=lambda s: s.created_at)
            return float(latest_manual.score)

        ai_scores = [s for s in image.scores if not s.is_edited_manually]
        if not ai_scores:
            return 0.0

        # model 単位で最新行を 1 つに絞る (legacy 複数行データは近似)。
        # model_id は SET NULL で None になり得る (model 削除済み orphan 行)。
        latest_by_model: dict[int | None, Score] = {}
        for score_row in ai_scores:
            existing = latest_by_model.get(score_row.model_id)
            if existing is None or score_row.created_at > existing.created_at:
                latest_by_model[score_row.model_id] = score_row

        display_values: list[float] = []
        for score_row in latest_by_model.values():
            model_name = score_row.model.name if score_row.model else ""
            display_values.append(calibrate_to_display(model_name, float(score_row.score)))

        if not display_values:
            return 0.0
        return sum(display_values) / len(display_values)

    def _format_score_labels(self, image: Image, annotations: dict[str, Any]) -> None:
        """スコアラベル (canonical scorer の categorical 分類) をフォーマットする。

        ADR 0028 に基づき、各 entry は {model, label} ペアで保持し、scalar shorthand
        は持たない (multi-scorer の集約 / 多数決方式の前提)。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.score_labels:
            annotations["score_labels"] = [
                self._format_score_label_annotation(sl) for sl in image.score_labels
            ]
        else:
            annotations["score_labels"] = []

    def _format_ratings(self, image: Image, annotations: dict[str, Any]) -> None:
        """レーティングアノテーション情報をフォーマットする。

        Args:
            image: 画像オブジェクト。
            annotations: フォーマット結果を格納する辞書（直接更新される）。

        """
        if image.ratings:
            annotations["ratings"] = [self._format_rating_annotation(rating) for rating in image.ratings]
            latest_rating = max(image.ratings, key=lambda r: r.created_at)
            annotations["rating_value"] = latest_rating.normalized_rating
        else:
            annotations["ratings"] = []
            annotations["rating_value"] = ""

    def _format_annotations_for_metadata(self, image: Image) -> dict[str, Any]:
        """画像のアノテーション情報を辞書形式にフォーマット。

        Args:
            image: 画像オブジェクト。

        Returns:
            フォーマット済みアノテーション情報辞書。

        """
        annotations: dict[str, Any] = {}

        self._format_tags(image, annotations)
        self._format_captions(image, annotations)
        self._format_scores(image, annotations)
        self._format_score_labels(image, annotations)
        self._format_ratings(image, annotations)

        # ADR 0029: derived view。GUI のメタデータ経路 (SelectedImageDetailsWidget) も
        # quality_summary を受け取れるよう、get_image_annotations と同じく派生計算する。
        annotations["quality_summary"] = compute_quality_summary(
            annotations.get("score_labels", []), annotations.get("scores", [])
        )

        # per-image 整形詳細は firehose のため TRACE (通常デバッグでは抑制、ADR 0047)
        logger.trace(
            f"Formatted annotations: tags={len(annotations.get('tags', []))}, "
            f"captions={len(annotations.get('captions', []))}, "
            f"scores={len(annotations.get('scores', []))}, "
            f"score_labels={len(annotations.get('score_labels', []))}, "
            f"ratings={len(annotations.get('ratings', []))}",
        )

        return annotations

    # --- Metadata Fetchers (used by get_images_by_filter / get_images_metadata_batch) ---

    def _fetch_original_image_metadata(
        self,
        session: Session,
        image_ids: list[int],
    ) -> list[dict[str, Any]]:
        """オリジナル画像のメタデータをアノテーション付きで取得する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 画像IDリスト。

        Returns:
            メタデータ辞書のリスト。

        """
        orig_stmt = (
            select(Image)
            .where(Image.id.in_(image_ids))
            .options(
                selectinload(Image.tags).selectinload(Tag.model),
                selectinload(Image.captions).selectinload(Caption.model),
                selectinload(Image.scores).selectinload(Score.model),
                selectinload(Image.score_labels).selectinload(ScoreLabel.model),
                selectinload(Image.ratings).selectinload(Rating.model),
            )
        )
        orig_results: list[Image] = list(session.execute(orig_stmt).scalars().all())

        result = []
        for img in orig_results:
            metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
            metadata.update(self._format_annotations_for_metadata(img))
            result.append(metadata)
        return result

    def _fetch_processed_image_metadata(
        self,
        session: Session,
        image_ids: list[int],
        resolution: int,
    ) -> list[dict[str, Any]]:
        """処理済み画像のメタデータをアノテーション付きで取得する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 画像IDリスト。
            resolution: 対象解像度。

        Returns:
            メタデータ辞書のリスト。

        """
        proc_stmt = select(ProcessedImage).where(ProcessedImage.image_id.in_(image_ids))
        all_proc_images = session.execute(proc_stmt).scalars().all()

        # Original Imageのアノテーション情報を一括取得
        orig_annotations_stmt = (
            select(Image)
            .where(Image.id.in_(image_ids))
            .options(
                selectinload(Image.tags).selectinload(Tag.model),
                selectinload(Image.captions).selectinload(Caption.model),
                selectinload(Image.scores).selectinload(Score.model),
                selectinload(Image.score_labels).selectinload(ScoreLabel.model),
                selectinload(Image.ratings).selectinload(Rating.model),
            )
        )
        orig_images = session.execute(orig_annotations_stmt).scalars().all()
        annotations_by_image_id = {
            img.id: self._format_annotations_for_metadata(img) for img in orig_images
        }

        # image_id ごとにグループ化
        proc_images_by_id: dict[int, list[dict[str, Any]]] = {}
        for img in all_proc_images:
            if img.image_id not in proc_images_by_id:
                proc_images_by_id[img.image_id] = []
            proc_metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
            # idをimages.idに統一（GUI全体で「画像ID」として使われるため）
            # processed_images.idはprocessed_image_idとして保持
            proc_metadata["processed_image_id"] = proc_metadata["id"]
            proc_metadata["id"] = img.image_id
            if img.image_id in annotations_by_image_id:
                proc_metadata.update(annotations_by_image_id[img.image_id])
            proc_images_by_id[img.image_id].append(proc_metadata)

        result = []
        for image_id in image_ids:
            metadata_list = proc_images_by_id.get(image_id, [])
            if metadata_list:
                selected = self._filter_by_resolution(metadata_list, resolution)
                if selected:
                    result.append(selected)
        return result

    def _fetch_filtered_metadata(
        self,
        session: Session,
        image_ids: list[int],
        resolution: int,
    ) -> list[dict[str, Any]]:
        """フィルタリングされたIDリストに基づき、指定解像度のメタデータを取得する。

        Args:
            session: SQLAlchemyセッション。
            image_ids: 画像IDリスト。
            resolution: 対象解像度(0はオリジナル)。

        Returns:
            メタデータ辞書のリスト。

        """
        if not image_ids:
            return []

        if resolution == 0:
            return self._fetch_original_image_metadata(session, image_ids)
        return self._fetch_processed_image_metadata(session, image_ids, resolution)

    def _apply_processed_resolution_filter(
        self,
        query: Select[Any],
        resolution: int,
    ) -> Select[Any]:
        """処理済み画像の解像度候補が存在する画像だけに絞り込む。"""
        if resolution == 0:
            return query

        target_area = resolution * resolution
        exact_long_side = or_(
            and_(ProcessedImage.width >= ProcessedImage.height, ProcessedImage.width == resolution),
            and_(ProcessedImage.height > ProcessedImage.width, ProcessedImage.height == resolution),
        )
        within_area_tolerance = (
            func.abs(target_area - (ProcessedImage.width * ProcessedImage.height)) <= target_area * 0.2
        )

        return query.where(
            exists().where(
                ProcessedImage.image_id == Image.id,
                or_(exact_long_side, within_area_tolerance),
            )
        )

    def _apply_project_filter(
        self,
        query: Select[Any],
        project_name: str | None,
        project_id: int | None,
    ) -> Select[Any]:
        """プロジェクトフィルタを適用する。

        Args:
            query: 適用対象の SQLAlchemy Select クエリ。
            project_name: フィルタ対象プロジェクト名。
            project_id: フィルタ対象プロジェクトID（project_name より優先）。

        Returns:
            フィルタ適用済みクエリ。
        """
        if project_id is not None:
            query = query.where(Image.project_id == project_id)
            logger.debug(f"Project filter applied: project_id={project_id}")
        elif project_name is not None:
            project_id_subq = select(Project.id).where(Project.name == project_name).scalar_subquery()
            query = query.where(Image.project_id == project_id_subq)
            logger.debug(f"Project filter applied: project_name='{project_name}'")
        return query

    # --- Main Filter Method ---

    def _build_image_filter_query(
        self,
        session: Session,
        tags: list[str] | None,
        excluded_tags: list[str] | None,
        caption: str | None,
        use_and: bool,
        start_date: str | None,
        end_date: str | None,
        include_untagged: bool,
        include_nsfw: bool,
        include_unrated: bool,
        only_unrated: bool,
        missing_model_litellm_id: str | None,
        manual_rating_filter: str | None,
        ai_rating_filter: str | None,
        manual_edit_filter: bool | None,
        score_min: float | None = None,
        score_max: float | None = None,
        project_name: str | None = None,
        project_id: int | None = None,
    ) -> Select[Any]:
        """画像フィルタ条件を適用したクエリを構築する。

        Args:
            session: SQLAlchemyセッション。
            tags: 検索タグリスト。
            excluded_tags: 除外検索タグリスト。
            caption: 検索キャプション文字列。
            use_and: 複数タグのAND/OR指定。
            start_date: 検索開始日時(ISO 8601)。
            end_date: 検索終了日時(ISO 8601)。
            include_untagged: タグなし画像のみ対象とするか。
            include_nsfw: NSFWコンテンツを含むか。
            include_unrated: 未評価画像を含むか。
            only_unrated: 未評価画像のみを対象とするか。
            missing_model_litellm_id: 指定モデルの annotation が無い画像のみを対象とするか。
            manual_rating_filter: 手動レーティングフィルタ。
            ai_rating_filter: AI評価フィルタ。
            manual_edit_filter: 手動編集フラグフィルタ。
            score_min: 最小スコア値（0.0-10.0）。
            score_max: 最大スコア値（0.0-10.0）。
            project_name: プロジェクト名フィルタ（Phase C完了後に有効化）。
            project_id: プロジェクトIDフィルタ（Phase C完了後に有効化）。

        Returns:
            フィルタ適用済みのSelectクエリ。

        """
        query = select(Image.id)

        start_dt = self._parse_datetime_str(start_date)
        end_dt = self._parse_datetime_str(end_date)
        query = self._apply_date_filter(query, start_dt, end_dt)

        if include_untagged and (tags or caption):
            logger.warning("検索語句と include_untagged が同時に指定されたため、検索語句は無視されます。")

        query = self._apply_tag_filter(query, tags, excluded_tags, use_and, include_untagged)
        query = self._apply_caption_filter(query, caption)

        # Rating Filters: manual / AI を独立に AND 適用する (Issue #604)
        # 旧実装は manual と AI を排他 (if/elif) にしており、両方指定時に AI フィルタが
        # 無視されていた。manual_rating_filter=None のとき _apply_manual_filters は
        # manual_edit_filter のみ適用するため、無条件呼び出しで全組み合わせを網羅できる。
        query = self._apply_manual_filters(query, manual_rating_filter, manual_edit_filter, session)
        if ai_rating_filter:
            logger.debug("Applying AI rating filter")
            query = self._apply_ai_rating_filter(query, ai_rating_filter)

        # Unrated Filter
        query = self._apply_unrated_filter(query, include_unrated, only_unrated)

        # Missing Model Filter
        query = self._apply_missing_model_filter(query, missing_model_litellm_id)

        # NSFW Filter
        nsfw_values_to_exclude = {"r", "x", "xxx"}
        apply_nsfw_exclusion = not include_nsfw and (
            (manual_rating_filter is None or manual_rating_filter.lower() not in nsfw_values_to_exclude)
            and (ai_rating_filter is None or ai_rating_filter.lower() not in nsfw_values_to_exclude)
        )
        if apply_nsfw_exclusion:
            query = self._apply_nsfw_filter(query, include_nsfw=False, session=session)
        elif include_nsfw:
            query = self._apply_nsfw_filter(query, include_nsfw=True, session=session)

        # Score Filter
        query = self._apply_score_filter(query, score_min, score_max)

        # Project Filter (Phase C完了後に有効化)
        query = self._apply_project_filter(query, project_name, project_id)

        return query.distinct()

    def _fetch_images_by_exact_ids(
        self, image_ids: list[int], resolution: int, offset: int = 0, limit: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        """明示的な image_id リストをそのまま取得する exact-set selector (ADR 0055)。

        他のフィルタ次元 (tags / caption / include_nsfw / rating / score 等) を一切
        適用せず、DB に存在する指定 ID の metadata を返す。GUI がステージング集合を
        criteria 経由でエクスポートする際に、明示選択した NSFW 画像等がフィルタで
        黙って落ちるのを防ぐ。`offset` / `limit` は通常パスと同じくページングに用いる
        (総件数はページング前の存在件数を返す, Codex #623)。

        Args:
            image_ids: 取得対象の画像 ID リスト。
            resolution: metadata 取得時の解像度 (0 はオリジナル)。
            offset: ページング開始位置。
            limit: 取得件数上限。None は無制限。

        Returns:
            (metadata リスト, 総件数)。総件数は DB に存在する指定 ID 数 (ページング前)。
            DB に存在しない ID は除外される。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        # 呼び出し元の順序 (ステージング順など) を保持して dedup する (Codex #623)
        requested = list(dict.fromkeys(i for i in image_ids if i is not None))
        if not requested:
            return [], 0
        # exact-set はエクスポート集合 (ステージング由来) であり EXACT_SET_MAX_IDS で有界。
        # 上限超は曖昧な SQLite 例外ではなく契約違反として早期に弾く (ADR 0056)。
        if len(requested) > self.EXACT_SET_MAX_IDS:
            raise ValueError(
                f"image_ids exact-set は {self.EXACT_SET_MAX_IDS}件まで "
                f"(指定 {len(requested)}件)。ステージング上限と同値 (ADR 0056)。"
            )
        with self.session_factory() as session:
            try:
                # EXACT_SET_MAX_IDS (< BATCH_CHUNK_SIZE) で有界なため単一 IN で bind 安全 (ADR 0056)
                existing: set[int] = set(
                    session.execute(select(Image.id).where(Image.id.in_(requested))).scalars().all()
                )
                # 入力順を保持したまま存在する ID に絞る
                existing_ids = [i for i in requested if i in existing]

                # 解像度フィルタはページングより前に適用する。_fetch_filtered_metadata は
                # 指定解像度の処理済み版を持たない ID を落とすため、先に metadata を取得して
                # 解像度で絞り、入力順で並べ直してからページングする (Codex #623)。
                meta_by_id = {
                    m["id"]: m for m in self._fetch_filtered_metadata(session, existing_ids, resolution)
                }
                ordered = [meta_by_id[i] for i in existing_ids if i in meta_by_id]
                total_count = len(ordered)
                paged = ordered[offset:]
                if limit is not None:
                    paged = paged[:limit]
                logger.info(
                    f"image_ids exact-set: 指定 {len(requested)}件 → 存在 {len(existing_ids)}件 "
                    f"→ 解像度{resolution}該当 {total_count}件 → 取得 {len(paged)}件 (ADR 0055)"
                )
                return paged, total_count
            except SQLAlchemyError as e:
                logger.error(f"image_ids exact-set 取得エラー: {e}", exc_info=True)
                raise

    def get_images_by_filter(
        self,
        criteria: ImageFilterCriteria | None = None,
        **kwargs: Any,
    ) -> tuple[list[dict[str, Any]], int]:
        """指定された条件に基づいて画像をフィルタリングし、メタデータと件数を返す。

        Args:
            criteria: ImageFilterCriteria形式のフィルター条件（推奨）
            **kwargs: レガシー形式のキーワード引数（後方互換性用）

        Returns:
            条件にマッチした画像メタデータのリストとその総数。
        """
        # criteriaが指定されていればそれを使用、なければkwargsから生成
        filter_criteria = criteria if criteria else ImageFilterCriteria.from_kwargs(**kwargs)

        # 型安全性チェック: resolution が文字列の場合は int に変換
        if isinstance(filter_criteria.resolution, str):
            try:
                filter_criteria.resolution = int(filter_criteria.resolution)
                logger.warning(
                    f"解像度パラメータが文字列として渡されました: '{filter_criteria.resolution}' -> "
                    f"{filter_criteria.resolution}",
                )
            except ValueError:
                logger.error(f"解像度パラメータの変換に失敗しました: '{filter_criteria.resolution}'")
                return [], 0

        # ADR 0055: image_ids 指定時は exact-set selector として他フィルタを bypass する。
        if filter_criteria.image_ids is not None:
            return self._fetch_images_by_exact_ids(
                filter_criteria.image_ids,
                filter_criteria.resolution,
                offset=filter_criteria.offset,
                limit=filter_criteria.limit,
            )

        with self.session_factory() as session:
            try:
                query = self._build_image_filter_query(
                    session=session,
                    tags=filter_criteria.tags,
                    excluded_tags=filter_criteria.excluded_tags,
                    caption=filter_criteria.caption,
                    use_and=filter_criteria.use_and,
                    start_date=filter_criteria.start_date,
                    end_date=filter_criteria.end_date,
                    include_untagged=filter_criteria.include_untagged,
                    include_nsfw=filter_criteria.include_nsfw,
                    include_unrated=filter_criteria.include_unrated,
                    only_unrated=filter_criteria.only_unrated,
                    missing_model_litellm_id=filter_criteria.missing_model_litellm_id,
                    manual_rating_filter=filter_criteria.manual_rating_filter,
                    ai_rating_filter=filter_criteria.ai_rating_filter,
                    manual_edit_filter=filter_criteria.manual_edit_filter,
                    score_min=filter_criteria.score_min,
                    score_max=filter_criteria.score_max,
                    project_name=filter_criteria.project_name,
                    project_id=filter_criteria.project_id,
                )
                query = self._apply_processed_resolution_filter(query, filter_criteria.resolution)

                count_query = select(func.count()).select_from(query.subquery())
                total_count = session.execute(count_query).scalar_one()
                if total_count == 0:
                    logger.info("指定された条件に一致する画像が見つかりませんでした。")
                    return [], 0

                paged_query = query.order_by(Image.id)
                if filter_criteria.offset:
                    paged_query = paged_query.offset(filter_criteria.offset)
                if filter_criteria.limit is not None:
                    paged_query = paged_query.limit(filter_criteria.limit)

                filtered_image_ids: list[int] = list(session.execute(paged_query).scalars().all())
                logger.debug(f"フィルタリングで {len(filtered_image_ids)} 件の候補画像IDを取得しました。")

                final_metadata_list = self._fetch_filtered_metadata(
                    session, filtered_image_ids, filter_criteria.resolution
                )
                list_count = len(final_metadata_list)
                logger.info(f"最終的な検索結果: {list_count} 件 / 総件数: {total_count} 件")

                return final_metadata_list, total_count

            except SQLAlchemyError as e:
                logger.error(f"画像フィルタリング検索中にエラーが発生しました: {e}", exc_info=True)
                raise

    def get_images_count_only(
        self,
        criteria: ImageFilterCriteria | None = None,
        **kwargs: Any,
    ) -> int:
        """指定された条件に基づいて画像件数のみを取得する。

        フィルター式は ``get_images_by_filter`` と同一ロジックを使用し、
        メタデータ取得を行わない軽量な件数集計を実行する。

        Args:
            criteria: ImageFilterCriteria形式のフィルター条件（推奨）
            **kwargs: レガシー形式のキーワード引数（後方互換性用）

        Returns:
            条件に一致した画像件数。

        """
        filter_criteria = criteria if criteria else ImageFilterCriteria.from_kwargs(**kwargs)

        # ADR 0055: image_ids 指定時は exact-set として他フィルタを bypass する。
        # get_images_by_filter と総件数を一致させるため同一 helper の総件数を返す
        # (resolution 指定時は解像度該当のみ数える, Codex #623)。
        if filter_criteria.image_ids is not None:
            _, total_count = self._fetch_images_by_exact_ids(
                filter_criteria.image_ids, filter_criteria.resolution
            )
            return total_count

        with self.session_factory() as session:
            try:
                filtered_query = self._build_image_filter_query(
                    session=session,
                    tags=filter_criteria.tags,
                    excluded_tags=filter_criteria.excluded_tags,
                    caption=filter_criteria.caption,
                    use_and=filter_criteria.use_and,
                    start_date=filter_criteria.start_date,
                    end_date=filter_criteria.end_date,
                    include_untagged=filter_criteria.include_untagged,
                    include_nsfw=filter_criteria.include_nsfw,
                    include_unrated=filter_criteria.include_unrated,
                    only_unrated=filter_criteria.only_unrated,
                    missing_model_litellm_id=filter_criteria.missing_model_litellm_id,
                    manual_rating_filter=filter_criteria.manual_rating_filter,
                    ai_rating_filter=filter_criteria.ai_rating_filter,
                    manual_edit_filter=filter_criteria.manual_edit_filter,
                    score_min=filter_criteria.score_min,
                    score_max=filter_criteria.score_max,
                    project_name=filter_criteria.project_name,
                    project_id=filter_criteria.project_id,
                )
                filtered_query = self._apply_processed_resolution_filter(
                    filtered_query, filter_criteria.resolution
                )

                count_query = select(func.count()).select_from(filtered_query.subquery())
                count = session.execute(count_query).scalar_one()
                logger.debug(f"フィルター件数のみ取得: {count} 件")
                return count

            except SQLAlchemyError as e:
                logger.error(f"画像件数取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    # --- Count ---

    def get_total_image_count(self) -> int:
        """データベース内のオリジナル画像の総数を取得します。"""
        with self.session_factory() as session:
            try:
                stmt = select(func.count(Image.id))
                count = session.execute(stmt).scalar_one()
                return count
            except SQLAlchemyError as e:
                logger.error(f"総画像数の取得中にエラーが発生しました: {e}", exc_info=True)
                raise  # または、目的のエラー処理に応じて0を返します

    # --- By IDs (alternative entry, used by error workflow) ---

    def get_images_by_ids(self, image_ids: list[int]) -> list[dict[str, Any]]:
        """画像IDリストから画像メタデータを取得

        Args:
            image_ids: 画像IDリスト

        Returns:
            list[dict]: 画像メタデータリスト（既存フォーマット互換）

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合

        """
        if not image_ids:
            return []

        with self.session_factory() as session:
            try:
                # error workflow の未解決エラー全件など大量 ID で呼ばれ得る。exact-set (有界 500)
                # と異なり error 復旧集合は非有界なので、reject せず BATCH_CHUNK_SIZE で分割して
                # bind 上限超を回避する (ADR 0056 改訂 / Codex #625)。
                metadata_list = []
                for i in range(0, len(image_ids), self.BATCH_CHUNK_SIZE):
                    chunk = image_ids[i : i + self.BATCH_CHUNK_SIZE]
                    # アノテーション情報を含めて取得
                    stmt = (
                        select(Image)
                        .where(Image.id.in_(chunk))
                        .options(
                            joinedload(Image.tags).joinedload(Tag.model),
                            joinedload(Image.captions).joinedload(Caption.model),
                            joinedload(Image.scores).joinedload(Score.model),
                            joinedload(Image.ratings).joinedload(Rating.model),
                        )
                    )
                    images = session.execute(stmt).unique().scalars().all()

                    # 既存の get_images_by_filter と同じフォーマットで返す
                    for img in images:
                        metadata = {c.name: getattr(img, c.name) for c in img.__table__.columns}
                        # アノテーション情報を追加
                        metadata.update(self._format_annotations_for_metadata(img))
                        metadata_list.append(metadata)

                logger.debug(f"画像メタデータを取得: {len(metadata_list)}件")
                return metadata_list
            except SQLAlchemyError as e:
                logger.error(f"画像メタデータの取得中にエラーが発生しました: {e}", exc_info=True)
                raise

    # --- File Path Resolution ---

    def get_image_id_by_filepath(self, filepath: str) -> int | None:
        """ファイルパスから画像IDを取得

        Args:
            filepath: 画像ファイルの絶対パスまたは相対パス

        Returns:
            int | None: 画像ID（見つからない場合は None）

        """
        with self.session_factory() as session:
            try:
                from ..db_core import resolve_stored_path

                input_path = Path(filepath).resolve()
                filename = input_path.name

                # filenameで候補を検索
                stmt = select(Image).where(Image.filename == filename)
                results = session.execute(stmt).scalars().all()

                # 候補が見つかった場合、stored_image_pathを正規化して比較
                for image in results:
                    resolved_stored_path = resolve_stored_path(image.stored_image_path)
                    if resolved_stored_path.resolve() == input_path:
                        return image.id

                return None

            except Exception as e:
                logger.error(f"ファイルパスからの画像ID取得エラー: {filepath}, {e}")
                return None

    @staticmethod
    def _normalize_input_paths(filepaths: list[str]) -> tuple[dict[str, Path], set[str]]:
        """入力 path リストを resolve した dict と filename set に変換する helper。

        Args:
            filepaths: 解決対象の path リスト。

        Returns:
            (input_path -> resolved Path の dict, filename set)。
            resolve できなかった path は元 Path object のまま dict に入れ、
            filename set には含めない (DB 検索対象から除外)。
        """
        path_resolved: dict[str, Path] = {}
        filenames: set[str] = set()
        for raw in filepaths:
            try:
                resolved = Path(raw).resolve()
            except (OSError, RuntimeError, ValueError):
                path_resolved[raw] = Path(raw)
                continue
            path_resolved[raw] = resolved
            filenames.add(resolved.name)
        return path_resolved, filenames

    def _build_candidates_by_filename(
        self, candidates: list[Image]
    ) -> dict[str, list[tuple[Path, int, str]]]:
        """candidates を filename をキーとする dict に集約する helper。

        ADR 0023 Phase 1.5 (Codex P2 r3209511028): row-level resolve guard 経由で
        corrupted 行は skip し、健全な行のみ集約する。

        Args:
            candidates: filename IN 句で取得した Image ORM 行のリスト。

        Returns:
            filename -> [(resolved_abs Path, image_id, phash), ...] の dict。
            同じ filename で複数 image (別ディレクトリ) があり得るため list 値。
        """
        by_filename: dict[str, list[tuple[Path, int, str]]] = {}
        for img in candidates:
            if img.filename is None:
                continue
            resolved_abs = self._safe_resolve_stored_path(img.id, img.stored_image_path)
            if resolved_abs is None:
                continue
            by_filename.setdefault(img.filename, []).append((resolved_abs, img.id, img.phash))
        return by_filename

    @staticmethod
    def _safe_resolve_stored_path(image_id: int, stored_image_path: str) -> Path | None:
        """`stored_image_path` を絶対 Path に解決する row-level guard 付き helper。

        ADR 0023 Phase 1.5 (Codex P2 r3209511028): 1 行の corrupted path
        (シンボリックループ / 解決不能 path 等) で batch 全体を落とさないため、
        row-level で例外を吸収する。失敗時は warning + None を返す。

        Args:
            image_id: 対象画像 ID (logging 用)。
            stored_image_path: DB に保存された生 path。

        Returns:
            解決済みの絶対 Path、または resolve 失敗時 None。
        """
        from ..db_core import resolve_stored_path

        try:
            resolved_stored = resolve_stored_path(stored_image_path)
            return resolved_stored.resolve()
        except (OSError, ValueError, RuntimeError) as exc:
            logger.warning(
                f"バッチ画像 ID 解決: stored_image_path resolve 失敗を skip: "
                f"image_id={image_id}, path={stored_image_path!r}, error={exc}"
            )
            return None

    def get_image_ids_by_filepaths(self, filepaths: list[str]) -> dict[str, int | None]:
        """複数のファイルパスから画像 ID をバッチ解決する。

        ADR 0023 Phase 1.5 (Issue #42, Codex P2 r3209342204): N+1 クエリ回避。
        `get_image_id_by_filepath()` を N 回呼ぶ代わりに、filename を IN 句で
        一括取得して input path と stored_image_path の resolve 比較を Python 側
        で行う。GUI スレッドや Worker 内のループ内で大量パスを引く場合に使用。

        Args:
            filepaths: 解決対象の画像 path リスト (絶対 / 相対パス混在可)。

        Returns:
            dict[str, int | None]: 入力 path をキーに、対応する image_id (見つから
                なければ None) を値とする辞書。入力 path はそのまま辞書キーとして
                使われる (caller が input list との対応を辿りやすくするため)。
        """
        if not filepaths:
            return {}

        path_resolved, filenames = self._normalize_input_paths(filepaths)
        result: dict[str, int | None] = dict.fromkeys(filepaths)

        if not filenames:
            return result

        with self.session_factory() as session:
            try:
                # filename IN (...) で 1 クエリ取得 (重複 filename もまとめて)
                stmt = select(Image).where(Image.filename.in_(filenames))
                candidates = list(session.execute(stmt).scalars().all())
                by_filename = self._build_candidates_by_filename(candidates)

                # input path ごとに対応する image_id を resolve 比較で確定
                for raw, resolved_input in path_resolved.items():
                    matches = by_filename.get(resolved_input.name, [])
                    for stored_resolved, image_id, _phash in matches:
                        if stored_resolved == resolved_input:
                            result[raw] = image_id
                            break

                logger.debug(
                    f"バッチ画像 ID 解決: 入力 {len(filepaths)}件 → "
                    f"解決 {sum(1 for v in result.values() if v is not None)}件"
                )
                return result
            except Exception as e:
                logger.error(f"バッチ画像 ID 解決エラー: {e}", exc_info=True)
                return result

    def get_latest_normalized_ratings_by_image_ids(self, image_ids: list[int]) -> dict[int, str | None]:
        """画像 ID 一覧から最新 `normalized_rating` を 1 件ずつ取得する。

        `ratings` は複数モデル経由で複数行持つ前提を許容し、`created_at` が
        新しいものを採用する。`UNRATED` / `None` も値として保持し、
        prefilter 側で「送信可」として扱う。

        Args:
            image_ids: 対象画像 ID 一覧。

        Returns:
            `{image_id: normalized_rating}` の辞書。rating 未登録の image_id は辞書に含まれない。
        """
        if not image_ids:
            return {}

        requested_ids = list({image_id for image_id in image_ids if image_id is not None})
        if not requested_ids:
            return {}

        with self.session_factory() as session:
            try:
                stmt = (
                    select(Rating.image_id, Rating.normalized_rating)
                    .where(Rating.image_id.in_(requested_ids))
                    .order_by(Rating.image_id.asc(), Rating.created_at.desc(), Rating.id.desc())
                )
                results = session.execute(stmt).all()
                latest_ratings: dict[int, str | None] = {}
                for image_id, normalized_rating in results:
                    if image_id not in latest_ratings:
                        latest_ratings[image_id] = normalized_rating.upper() if normalized_rating else None

                logger.debug(
                    f"最新 rating 取得: 対象 {len(requested_ids)}件 → 解決 {len(latest_ratings)}件"
                )
                return latest_ratings
            except Exception as e:
                logger.error(f"最新 normalized_rating 取得エラー: {e}", exc_info=True)
                return {}

    def filter_image_ids_with_tag_changes_since(
        self, image_ids: list[int], since: datetime.datetime
    ) -> list[int]:
        """指定日時以降にタグ変更があった image_id に絞り込む (#614)。

        「変更」は以下のいずれか:
        - AI 実行: `model_id` 付きのタグ行で `updated_at > since`
        - 手動編集: `is_edited_manually = True` のタグ行で `updated_at > since`

        AI 再実行は既存タグ行を update する (created_at は据え置き・updated_at が更新される)
        ため、AI 側も `updated_at` を見ることで再実行を取りこぼさない (Codex #621)。
        元ファイル由来 (`existing = True`) のタグは AI でも手動編集でもないため
        自然に除外される。対象はタグのみ (caption/rating/score は対象外)。

        Args:
            image_ids: 絞り込み元の image_id 一覧。
            since: この日時より後の変更を「変更あり」とみなす閾値。

        Returns:
            since 以降にタグ変更があった image_id の一覧 (requested_ids の順序を保持)。

        Raises:
            SQLAlchemyError: データベース操作でエラーが発生した場合。
        """
        if not image_ids:
            return []
        requested_ids = list({image_id for image_id in image_ids if image_id is not None})
        if not requested_ids:
            return []

        with self.session_factory() as session:
            try:
                stmt = (
                    select(Tag.image_id)
                    .where(
                        Tag.image_id.in_(requested_ids),
                        or_(
                            and_(Tag.model_id.is_not(None), Tag.updated_at > since),
                            and_(Tag.is_edited_manually.is_(True), Tag.updated_at > since),
                        ),
                    )
                    .distinct()
                )
                changed_ids = {row[0] for row in session.execute(stmt).all()}
                logger.debug(
                    f"changed-since 絞り込み: 対象 {len(requested_ids)}件 → "
                    f"{len(changed_ids)}件 (since={since})"
                )
                return [image_id for image_id in requested_ids if image_id in changed_ids]
            except SQLAlchemyError as e:
                logger.error(f"changed-since 絞り込みエラー: {e}", exc_info=True)
                raise

    def get_phashes_by_filepaths(self, filepaths: list[str]) -> dict[str, str | None]:
        """複数のファイルパスから pHash をバッチ解決する。

        `get_image_ids_by_filepaths()` と同じ path resolve 規則で、登録済み画像の
        pHash を input path 順に引けるようにする。未登録または resolve 不能な path
        は None を返す。
        """
        if not filepaths:
            return {}

        path_resolved, filenames = self._normalize_input_paths(filepaths)
        result: dict[str, str | None] = dict.fromkeys(filepaths)

        if not filenames:
            return result

        with self.session_factory() as session:
            try:
                stmt = select(Image).where(Image.filename.in_(filenames))
                candidates = list(session.execute(stmt).scalars().all())
                by_filename = self._build_candidates_by_filename(candidates)

                for raw, resolved_input in path_resolved.items():
                    matches = by_filename.get(resolved_input.name, [])
                    for stored_resolved, _image_id, phash in matches:
                        if stored_resolved == resolved_input:
                            result[raw] = phash
                            break

                logger.debug(
                    f"バッチ pHash 解決: 入力 {len(filepaths)}件 → "
                    f"解決 {sum(1 for v in result.values() if v is not None)}件"
                )
                return result
            except Exception as e:
                logger.error(f"バッチ pHash 解決エラー: {e}", exc_info=True)
                return result
