# src/lorairo/gui/state/dataset_state.py

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from ...utils.log import logger


class DatasetStateManager(QObject):
    """
    全Widget間で共有される単一状態管理システム。
    データセット情報、画像リスト、選択状態などを一元管理。
    """

    # === コアデータセット状態シグナル ===
    dataset_changed = Signal(str)  # dataset_path
    dataset_loaded = Signal(int)  # total_image_count

    # === 画像リスト・フィルター状態シグナル ===
    images_filtered = Signal(list)  # List[Dict[str, Any]] - filtered image metadata
    images_loaded = Signal(list)  # List[Dict[str, Any]] - all image metadata
    filter_cleared = Signal()

    # === 選択状態シグナル ===
    selection_changed = Signal(list)  # List[int] - selected image IDs
    current_image_changed = Signal(int)  # current_image_id
    current_image_data_changed = Signal(dict)  # current_image_data (complete metadata)
    current_image_cleared = Signal()

    # === UI状態シグナル ===
    ui_state_changed = Signal(str, object)  # state_key, state_value
    thumbnail_size_changed = Signal(int)  # thumbnail_size
    layout_mode_changed = Signal(str)  # layout_mode

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # === プライベート状態 ===
        self._dataset_path: Path | None = None
        # Issue #969: 検索結果(全件)とフィルター済みの2層モデルは実 UX で
        # 分岐せず形骸化していたため _all_images の単一リストに統合した。
        # filtered_* 系アクセサ・signal は後方互換のため _all_images を参照する。
        self._all_images: list[dict[str, Any]] = []
        # _all_images の id→metadata 遅延インデックス (get_image_by_id を O(1) 化)。
        # _all_images の内容が変わる箇所で _invalidate_image_index() により無効化する。
        self._id_index: dict[int, dict[str, Any]] | None = None
        self._selected_image_ids: list[int] = []
        self._current_image_id: int | None = None
        self._filter_conditions: dict[str, Any] = {}

        # === UI状態 ===
        self._thumbnail_size: int = 150
        self._layout_mode: str = "grid"  # "grid" | "list"
        self._ui_state: dict[str, Any] = {}

        # === DB Manager 参照（バッチ操作後のリフレッシュに使用） ===
        self._db_manager: Any = None

        logger.debug("DatasetStateManager initialized")

    def set_db_manager(self, db_manager: Any) -> None:
        """
        ImageDatabaseManager への参照を設定

        バッチ操作後のメタデータ再読み込みに使用します。

        Args:
            db_manager: ImageDatabaseManager インスタンス
        """
        self._db_manager = db_manager
        logger.debug("ImageDatabaseManager reference set in DatasetStateManager")

    # === Public Properties (Read-Only) ===

    @property
    def dataset_path(self) -> Path | None:
        return self._dataset_path

    @property
    def all_images(self) -> list[dict[str, Any]]:
        return self._all_images.copy()

    @property
    def filtered_images(self) -> list[dict[str, Any]]:
        # Issue #969: 2層統合後は全件と同一。後方互換のため defensive copy を返す。
        return self._all_images.copy()

    @property
    def image_count(self) -> int:
        """全画像の件数 (Issue #967: 全件 .copy() を伴わない O(1) アクセサ)。"""
        return len(self._all_images)

    @property
    def filtered_count(self) -> int:
        """フィルター済み画像の件数 (Issue #967: 全件 .copy() を伴わない O(1) アクセサ)。

        ``len(self.filtered_images)`` は read-only 用途でも全件 shallow copy を伴うため、
        ページング (PaginationStateManager.total_items / total_pages) のような高頻度経路
        では件数取得にこのアクセサを使う。Issue #969 の 2 層統合後は image_count と同値。
        """
        return len(self._all_images)

    @property
    def selected_image_ids(self) -> list[int]:
        return self._selected_image_ids.copy()

    @property
    def current_image_id(self) -> int | None:
        return self._current_image_id

    @property
    def filter_conditions(self) -> dict[str, Any]:
        return self._filter_conditions.copy()

    @property
    def thumbnail_size(self) -> int:
        return self._thumbnail_size

    @property
    def layout_mode(self) -> str:
        return self._layout_mode

    # === Dataset Management ===

    def set_dataset_path(self, dataset_path: Path) -> None:
        """データセットパスを設定"""
        if self._dataset_path != dataset_path:
            self._dataset_path = dataset_path
            logger.info(f"データセットパス変更: {dataset_path}")
            self.dataset_changed.emit(str(dataset_path))

    def set_dataset_images(self, images: list[dict[str, Any]]) -> None:
        """データセットの全画像リストを設定"""
        self._all_images = images.copy()
        self._invalidate_image_index()

        logger.info(f"データセット画像読み込み: {len(images)}件")
        self.images_loaded.emit(self._all_images)
        self.images_filtered.emit(self._all_images)
        self.dataset_loaded.emit(len(images))

        # 選択状態をクリア
        self.clear_selection()

    def clear_dataset(self) -> None:
        """データセット状態をクリア"""
        self._dataset_path = None
        self._all_images = []
        self._filter_conditions = {}
        self._invalidate_image_index()

        self.clear_selection()
        self._current_image_id = None
        self.filter_cleared.emit()
        logger.info("データセット状態をクリアしました")

    # === Filter Management ===

    def update_from_search_results(self, search_results: list[dict[str, Any]]) -> None:
        """
        検索結果による完全データ更新（クリーンなデータフロー）

        検索結果でマスターデータ (_all_images) を完全置換し、単一データソース
        (Single Source of Truth) として扱う。Issue #969 で検索結果/フィルターの
        2 層を統合したため、ここで保持する 1 リストが全件かつ表示対象を兼ねる。

        Args:
            search_results: 検索結果の画像メタデータリスト
                各辞書は以下のキーを含む必要があります:
                - "id": 画像ID (int)
                - "stored_image_path": 画像ファイルパス (str)
                - その他の画像メタデータ (width, height, etc.)

        Side Effects:
            - _all_images を完全置換
            - images_loaded と images_filtered シグナルを発行
            - 現在選択中の画像が結果に含まれない場合、選択をクリア
        """
        logger.info(f"検索結果によるデータ完全更新: {len(search_results)}件")

        # 完全データ置換（Single Source of Truth）。Issue #969: 2 層統合により
        # コピーは 1 回のみ (呼び出し元が保持する list との別オブジェクト化のため必要)。
        self._all_images = search_results.copy()
        self._invalidate_image_index()

        # フィルター条件はクリア（検索結果が新しい基準）
        self._filter_conditions = {}

        # シグナル発行で UI コンポーネントに通知
        self.images_loaded.emit(self._all_images)
        self.images_filtered.emit(self._all_images)

        # 現在の選択状態を検証・クリア
        if self._current_image_id:
            current_valid = any(img.get("id") == self._current_image_id for img in self._all_images)
            if not current_valid:
                logger.debug(
                    f"現在の画像ID {self._current_image_id} が検索結果に含まれていないため選択をクリア"
                )
                self.clear_current_image()

        logger.debug(f"データ同期完了: all_images={len(self._all_images)}")

    # === Selection Management ===

    def set_selected_images(self, image_ids: list[int]) -> None:
        """選択画像IDリストを設定"""
        if self._selected_image_ids != image_ids:
            self._selected_image_ids = image_ids.copy()
            self.selection_changed.emit(self._selected_image_ids)
            logger.debug(f"画像選択変更: {len(image_ids)}件選択")

    def add_to_selection(self, image_id: int) -> None:
        """選択に画像IDを追加"""
        if image_id not in self._selected_image_ids:
            self._selected_image_ids.append(image_id)
            self.selection_changed.emit(self._selected_image_ids)

    def remove_from_selection(self, image_id: int) -> None:
        """選択から画像IDを削除"""
        if image_id in self._selected_image_ids:
            self._selected_image_ids.remove(image_id)
            self.selection_changed.emit(self._selected_image_ids)

    def toggle_selection(self, image_id: int) -> None:
        """画像IDの選択状態をトグル"""
        if image_id in self._selected_image_ids:
            self.remove_from_selection(image_id)
        else:
            self.add_to_selection(image_id)

    def clear_selection(self) -> None:
        """全選択をクリア"""
        if self._selected_image_ids:
            self._selected_image_ids = []
            self.selection_changed.emit(self._selected_image_ids)

    def set_current_image(self, image_id: int) -> None:
        """現在の画像IDを設定"""
        if self._current_image_id != image_id:
            self._current_image_id = image_id

            # 後方互換性のためIDシグナルを維持
            self.current_image_changed.emit(image_id)

            # 新しいデータシグナルで完全な画像メタデータを送信
            image_data = self.get_image_by_id(image_id)
            if image_data:
                self._ensure_annotations_loaded(image_data)
                self.current_image_data_changed.emit(image_data)
                logger.debug(f"画像選択成功: ID {image_id} - current_image_data_changed シグナル発行")
            else:
                # デバッグ情報を詳細化
                state_summary = self.get_state_summary()
                logger.warning(
                    f"画像データ取得失敗: ID {image_id} | all_images={state_summary['total_images']}"
                )

                # キャッシュ未登録 (登録直後 / 検索結果外) は DB から取得して空表示を防ぐ
                db_image_data = self._get_image_from_db(image_id)
                if db_image_data:
                    logger.debug(f"DB から画像取得: ID {image_id} - データを送信")
                    self.current_image_data_changed.emit(db_image_data)
                else:
                    # 取得できない場合のみ空データでシグナルの一貫性を保つ
                    self.current_image_data_changed.emit({})

    def clear_current_image(self) -> None:
        """現在の画像選択をクリア"""
        if self._current_image_id is not None:
            self._current_image_id = None
            self.current_image_cleared.emit()

    # === UI State Management ===

    def set_thumbnail_size(self, size: int) -> None:
        """サムネイルサイズを設定"""
        if self._thumbnail_size != size:
            self._thumbnail_size = size
            self.thumbnail_size_changed.emit(size)

    def set_layout_mode(self, mode: str) -> None:
        """レイアウトモードを設定"""
        if mode in ["grid", "list"] and self._layout_mode != mode:
            self._layout_mode = mode
            self.layout_mode_changed.emit(mode)

    def set_ui_state(self, key: str, value: Any) -> None:
        """任意のUI状態を設定"""
        if self._ui_state.get(key) != value:
            self._ui_state[key] = value
            self.ui_state_changed.emit(key, value)

    def get_ui_state(self, key: str, default: Any = None) -> Any:
        """UI状態を取得"""
        return self._ui_state.get(key, default)

    # === Utility Methods ===

    def _get_all_images_index(self) -> dict[int, dict[str, Any]]:
        """_all_images の id→metadata インデックスを返す（遅延構築・O(1) 検索用）。

        _all_images の内容が変わる箇所で ``_invalidate_image_index()`` を呼ぶことで、
        次回アクセス時に再構築される。サムネイル描画 (``_display_page``) が
        ページ内全件に対して ``get_image_by_id`` を呼ぶ経路を O(n^2)→O(n) にする。
        """
        if self._id_index is None:
            index: dict[int, dict[str, Any]] = {}
            for img in self._all_images:
                img_id = img.get("id")
                if img_id is not None:
                    index[img_id] = img
            self._id_index = index
        return self._id_index

    def _invalidate_image_index(self) -> None:
        """_all_images の内容変更時にインデックスを無効化する。"""
        self._id_index = None

    def get_filtered_image_ids_slice(self, start: int, end: int) -> list[int]:
        """[start:end] ページ分の画像IDだけを返す (Issue #967)。

        ``filtered_images`` プロパティ経由だと全件 shallow copy が発生するが、
        本メソッドは ``_all_images[start:end]`` のスライス (高々 page_size 件) のみ
        を走査して id を抽出するため、ページング経路のコピーコストを O(全件) から
        O(ページ) に下げる。

        Args:
            start: スライス開始インデックス (0 始まり)。
            end: スライス終了インデックス (排他)。

        Returns:
            ページ内画像IDのリスト (int の id を持つ要素のみ)。
        """
        return [
            image_id
            for image in self._all_images[start:end]
            if isinstance((image_id := image.get("id")), int)
        ]

    def get_image_by_id(self, image_id: int) -> dict[str, Any] | None:
        """
        IDで画像メタデータを取得（統一データソース: _all_images インデックス）

        Args:
            image_id: 検索する画像ID

        Returns:
            画像メタデータ辞書、見つからない場合はNone
        """
        # all_images インデックスから O(1) 検索（Issue #969: 2 層統合により単一ソース）
        img = self._get_all_images_index().get(image_id)
        if img is not None:
            return img

        # デバッグ情報の詳細ログ
        logger.debug(
            f"画像ID {image_id} が見つかりません。"
            f"all_images: {len(self._all_images)}件, "
            f"IDサンプル: {[img.get('id') for img in self._all_images[:3]]}..."
        )
        return None

    def update_image_metadata(self, image_id: int, new_metadata: dict[str, Any]) -> None:
        """単一画像のキャッシュメタデータを更新

        _all_images を更新し、現在選択中の画像ならシグナル発行。
        Issue #969: 2 層統合により更新対象は単一リストのみ。

        Args:
            image_id: 更新対象の画像ID
            new_metadata: 更新後のメタデータ辞書（"id"フィールド必須）

        Note:
            - DB書き込み後のキャッシュ整合性維持に使用
            - 現在選択中の画像なら current_image_data_changed シグナル発行
        """
        if "id" not in new_metadata or new_metadata["id"] != image_id:
            logger.warning(f"メタデータ検証失敗: {image_id}")
            return

        # _all_imagesを更新
        found_in_all = False
        for i, img in enumerate(self._all_images):
            if img.get("id") == image_id:
                self._all_images[i] = new_metadata
                found_in_all = True
                logger.debug(f"_all_images更新: image_id={image_id}")
                break

        if found_in_all:
            # 要素を差し替えたためインデックスの該当エントリが stale になる
            self._invalidate_image_index()
        else:
            logger.warning(f"画像ID {image_id} が_all_imagesに見つかりません")

        # 現在選択中ならシグナル発行
        if self._current_image_id == image_id:
            self.current_image_data_changed.emit(new_metadata)
            logger.debug(f"キャッシュ更新とシグナル発行完了: {image_id}")

    def refresh_image(self, image_id: int) -> None:
        """
        単一画像のメタデータをDBから再読み込み

        バッチ編集後などに呼び出し、キャッシュされたメタデータを最新状態に更新します。

        Args:
            image_id: 再読み込み対象の画像ID

        Side Effects:
            - DB から最新メタデータを取得
            - _all_images のキャッシュを更新
            - 現在選択中の画像なら current_image_data_changed シグナル発行

        Note:
            - _db_manager が未設定の場合は警告ログを出して何もしない
            - DB から取得できない場合は警告ログを出す
        """
        if not self._db_manager:
            logger.warning("DB Manager not set, cannot refresh image metadata")
            return

        try:
            # DB から最新メタデータを取得
            image_metadata = self._db_manager.image_repo.get_image_metadata(image_id)

            if not image_metadata:
                logger.warning(f"Failed to fetch metadata from DB for image_id {image_id}")
                return

            # キャッシュを更新（既存の update_image_metadata を利用）
            self.update_image_metadata(image_id, image_metadata)
            logger.debug(f"Successfully refreshed metadata for image_id {image_id}")

        except Exception as e:
            logger.opt(exception=True).error(
                f"Error refreshing image metadata for image_id {image_id}: {e}"
            )

    def refresh_image_annotations(self, image_id: int) -> None:
        """単一画像のアノテーションだけを DB から再取得しキャッシュへ merge する (#980)。

        ``refresh_image()`` と異なり ``stored_image_path`` 等の (processed 解像度を含む)
        パス/メタフィールドを保持し、tags / captions / scores / score_labels / ratings 等の
        アノテーションのみ最新化する。個別タグ編集 (soft-reject / 復活 / 手動追加) 後に
        processed 解像度のプレビューが元画像へ切り替わる回帰を防ぐ。

        Args:
            image_id: 再取得対象の画像 ID。

        Side Effects:
            - DB からアノテーションのみ取得 (``get_image_annotation_metadata``)
            - キャッシュ dict (live 参照) を in-place 更新 (パスフィールドは保持)
            - 現在選択中の画像なら current_image_data_changed シグナル発行

        Note:
            - キャッシュ未登録 (検索結果外) の画像は ``refresh_image`` に委譲する。
            - _db_manager 未設定時は警告ログを出して何もしない。
        """
        if not self._db_manager:
            logger.warning("DB Manager not set, cannot refresh image annotations")
            return

        cached = self.get_image_by_id(image_id)
        if cached is None:
            # キャッシュ未登録 (登録直後 / 検索結果外) は full fetch にフォールバック
            self.refresh_image(image_id)
            return

        try:
            annotations = self._db_manager.image_repo.get_image_annotation_metadata(image_id)
        except Exception as e:
            logger.opt(exception=True).error(f"アノテーション再取得失敗: ID {image_id}: {e}")
            return

        if not annotations:
            return

        # live 参照を in-place 更新するためパス/processed フィールドは保持される
        cached.update(annotations)
        logger.debug(f"アノテーションキャッシュ更新: image_id={image_id}")

        if self._current_image_id == image_id:
            self.current_image_data_changed.emit(cached)

    def refresh_images(self, image_ids: list[int]) -> None:
        """
        複数画像のメタデータをDBから再読み込み

        バッチタグ追加などのバッチ操作後に呼び出し、影響を受けた画像の
        キャッシュを一括で最新状態に更新します。

        Args:
            image_ids: 再読み込み対象の画像IDリスト

        Side Effects:
            - DB から最新メタデータを一括取得（1クエリ）
            - _all_images のキャッシュを更新
            - 現在選択中の画像が含まれれば current_image_data_changed シグナル発行

        Note:
            - 空リストの場合は何もせずリターン
            - _db_manager が未設定の場合は警告ログを出して何もしない
            - DB取得できなかったIDは警告ログを出す

        Example:
            >>> # バッチタグ追加後のリフレッシュ
            >>> success = image_db_write_service.add_tag_batch([1, 2, 3], "landscape")
            >>> if success:
            >>>     dataset_state_manager.refresh_images([1, 2, 3])
        """
        if not image_ids:
            logger.debug("refresh_images called with empty list, nothing to do")
            return

        if not self._db_manager:
            logger.warning("DB Manager not set, cannot refresh image metadata")
            return

        logger.info(f"Refreshing metadata for {len(image_ids)} images")

        try:
            # 一括取得（N+1回避: 1クエリで全画像取得）
            metadata_list = self._db_manager.image_repo.get_images_metadata_batch(image_ids)

            # image_id → metadata のマップ作成
            metadata_by_id: dict[int, dict[str, Any]] = {m["id"]: m for m in metadata_list}

            # キャッシュ一括更新
            success_count = 0
            for image_id in image_ids:
                new_metadata = metadata_by_id.get(image_id)
                if new_metadata:
                    self.update_image_metadata(image_id, new_metadata)
                    success_count += 1
                else:
                    logger.warning(f"Failed to fetch metadata from DB for image_id {image_id}")

            logger.info(f"Metadata refresh completed: {success_count}/{len(image_ids)} successful")

        except Exception as e:
            logger.opt(exception=True).error(f"Error during batch metadata refresh: {e}")

    def _ensure_annotations_loaded(self, image_data: dict[str, Any]) -> None:
        """検索フェーズで省略されたアノテーションを遅延取得して dict に merge する。

        Issue #965: 検索 (include_annotations=False) では tags/captions/scores 等を
        先読みしない。サムネ選択 → プレビュー表示の時点で対象 1 件だけ取得し、
        キャッシュ dict (live 参照) を in-place 更新することで、以降の同一画像選択は
        DB 往復なしで即時表示できる。

        Args:
            image_data: 更新対象のメタデータ辞書 (キャッシュの live 参照)。

        Note:
            アノテーション済み (検索以外の経路 / 取得済み) の dict は "tags" キーを
            持つため何もしない。検索フェーズの dict のみ遅延取得の対象になる。
        """
        if "tags" in image_data:
            return  # 既にアノテーション済み
        image_id = image_data.get("id")
        if image_id is None or not self._db_manager:
            return
        try:
            annotations = self._db_manager.image_repo.get_image_annotation_metadata(image_id)
        except Exception as e:
            logger.opt(exception=True).error(f"アノテーション遅延取得失敗: ID {image_id}: {e}")
            return
        if annotations:
            image_data.update(annotations)
            logger.debug(f"アノテーション遅延取得・merge 完了: ID {image_id}")

    def _get_image_from_db(self, image_id: int) -> dict[str, Any] | None:
        """DB から単一画像メタデータを取得する（キャッシュ未登録画像の選択用）。

        登録直後や現在の検索結果に含まれない画像を選択したときに、preview /
        details が空にならないよう DB を直接引く。
        """
        if not self._db_manager:
            return None
        try:
            metadata: dict[str, Any] | None = self._db_manager.image_repo.get_image_metadata(image_id)
            return metadata
        except Exception as e:
            logger.opt(exception=True).error(f"DB からの画像取得失敗: ID {image_id}: {e}")
            return None

    def get_current_image_data(self) -> dict[str, Any] | None:
        """現在選択中の画像データを取得"""
        if self._current_image_id:
            return self.get_image_by_id(self._current_image_id)
        return None

    def has_images(self) -> bool:
        """画像が読み込まれているかチェック"""
        return len(self._all_images) > 0

    def has_filtered_images(self) -> bool:
        """表示対象画像があるかチェック (Issue #969: 2 層統合後は has_images と同値)"""
        return len(self._all_images) > 0

    def is_image_selected(self, image_id: int) -> bool:
        """指定画像IDが選択されているかチェック"""
        return image_id in self._selected_image_ids

    # === Debug Methods ===

    def get_state_summary(self) -> dict[str, Any]:
        """状態サマリーを取得（デバッグ用）"""
        return {
            "dataset_path": str(self._dataset_path) if self._dataset_path else None,
            "total_images": len(self._all_images),
            "filtered_images": len(self._all_images),
            "selected_images": len(self._selected_image_ids),
            "current_image_id": self._current_image_id,
            "has_filter": bool(self._filter_conditions),
            "thumbnail_size": self._thumbnail_size,
            "layout_mode": self._layout_mode,
        }
