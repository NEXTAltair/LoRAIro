# src/lorairo/gui/state/dataset_state.py

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QObject, Qt, Signal, Slot

from ...utils.log import logger
from ..workers.annotation_refresh_worker import AnnotationRefreshLoadWorker, AnnotationRefreshLookupWorker
from ..workers.manager import WorkerManager
from ..workers.terminal import CancelReason, WorkerOutcome, WorkerTerminalEvent


@dataclass(frozen=True)
class _AnnotationLookupRequest:
    worker_id: str
    context_version: int
    edit_cutoffs: dict[str, int]


@dataclass(frozen=True)
class _AnnotationLoadRequest:
    worker_id: str
    context_version: int
    selection_version: int
    image_id: int
    annotation_version: int
    cached: dict[str, Any]


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

        # #1384: execution completion resolves IDs asynchronously, invalidates only
        # annotation fields, then fetches only the current image on demand.
        self._annotation_worker_manager: WorkerManager | None = None
        self._annotation_refresh_closed = False
        self._annotation_context_version = 0
        self._annotation_selection_version = 0
        self._annotation_worker_serial = 0
        self._annotation_edit_serial = 0
        self._annotation_edited_at: dict[int, int] = {}
        self._annotation_versions: dict[int, int] = {}
        self._annotation_invalidated_ids: set[int] = set()
        self._annotation_pending_phashes: dict[str, int] = {}
        # Cancellation invalidates the logical request immediately, but SQL may
        # still be running. Keep the physical slot until its terminal event.
        self._annotation_active_worker_id: str | None = None
        self._annotation_lookup_request: _AnnotationLookupRequest | None = None
        self._annotation_load_request: _AnnotationLoadRequest | None = None
        self._annotation_failed_load: _AnnotationLoadRequest | None = None

        logger.debug("DatasetStateManager initialized")

    def set_db_manager(self, db_manager: Any) -> None:
        """
        ImageDatabaseManager への参照を設定

        バッチ操作後のメタデータ再読み込みに使用します。

        Args:
            db_manager: ImageDatabaseManager インスタンス
        """
        if self._db_manager is not db_manager:
            self._reset_annotation_refresh_context()
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
            self._reset_annotation_refresh_context()
            self._dataset_path = dataset_path
            logger.info(f"データセットパス変更: {dataset_path}")
            self.dataset_changed.emit(str(dataset_path))

    def set_dataset_images(self, images: list[dict[str, Any]]) -> None:
        """データセットの全画像リストを設定"""
        self._reset_annotation_refresh_context()
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
        self._reset_annotation_refresh_context()
        self._dataset_path = None
        self._all_images = []
        self._filter_conditions = {}
        self._invalidate_image_index()

        self.clear_selection()
        # 現在画像のクリアは clear_current_image に一本化する (#1228 Codex P2)。
        # selection_changed([]) は詳細パネルの full clear を担当しなくなった (search_tab は
        # widget.current_image_id で表示中画像を保持するようになった) ため、current image を
        # None にする経路が詳細/プレビューへ空データ通知を出す責務を持つ。
        self.clear_current_image()
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
        self._reset_annotation_refresh_context()

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

    def add_image(self, metadata: dict[str, Any]) -> None:
        """一覧の画像集合の先頭へ 1 件だけ追加する (検索を介さない即時反映、#1346)。

        クロップ保存直後のように「検索条件とは無関係に、いま作った画像を一覧へ載せたい」
        経路で使う。フィルタ未指定だと検索自体がスキップされ再検索では反映されないため、
        検索状態に依存しない追加経路を分けている。

        末尾ではなく先頭へ挿入するのは、``images_filtered`` を受けたページネーションが
        1 ページ目へリセットされるため (Codex P2)。末尾に積むと 100 件超の一覧では
        最終ページへ入ってしまい、表示中の 1 ページ目に現れない。同じ ID が既にあれば
        その位置から取り除いたうえで先頭へ移す (重複させない)。

        Args:
            metadata: 追加する画像のメタデータ (``id`` キー必須)。

        Side Effects:
            - ``_all_images`` の先頭へ挿入し、``images_filtered`` を発行する
              (ページネーションが 1 ページ目へリセットされる)。
        """
        image_id = metadata.get("id")
        if image_id is None:
            logger.warning("id を持たないメタデータは一覧へ追加できません")
            return

        self._note_annotation_edit(image_id)

        for index, existing in enumerate(self._all_images):
            if existing.get("id") == image_id:
                del self._all_images[index]
                break
        self._all_images.insert(0, metadata)
        self._invalidate_image_index()

        logger.debug(f"一覧の先頭へ画像を追加: ID {image_id} (合計 {len(self._all_images)}件)")
        self.images_filtered.emit(self._all_images)

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
            self._annotation_selection_version += 1
            self._cancel_annotation_load()
            self._current_image_id = image_id

            # 後方互換性のためIDシグナルを維持
            self.current_image_changed.emit(image_id)

            # 新しいデータシグナルで完全な画像メタデータを送信
            image_data = self.get_image_by_id(image_id)
            if image_data:
                if image_id in self._annotation_invalidated_ids:
                    # Selection must show this image's basic/processed metadata
                    # immediately, including when annotation retrieval fails.
                    self.current_image_data_changed.emit(image_data)
                    self._start_current_annotation_load()
                    return
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
        """現在の画像選択をクリア。

        `_current_image_id` を None にする唯一の経路 (clear_dataset もここへ委譲する)。
        current_image_cleared に加えて current_image_data_changed({}) も emit し、
        current-image チャネルを購読する詳細パネル / プレビューを確実にクリアする
        (#1228 Codex P2)。current_image_cleared のみでは詳細パネルが購読しておらず
        stale な表示が残る。ExportTab は両シグナルを購読するが空クリアは冪等。
        """
        if self._current_image_id is not None:
            self._annotation_selection_version += 1
            self._cancel_annotation_load()
            self._current_image_id = None
            self.current_image_cleared.emit()
            self.current_image_data_changed.emit({})

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

        self._note_annotation_edit(image_id)

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

        self._note_annotation_edit(image_id)
        # live 参照を in-place 更新するためパス/processed フィールドは保持される
        cached.update(annotations)
        logger.debug(f"アノテーションキャッシュ更新: image_id={image_id}")

        if self._current_image_id == image_id:
            self.current_image_data_changed.emit(cached)

    # _ensure_annotations_loaded がキャッシュへ merge するアノテーションキー
    # (= get_image_annotation_metadata / _format_annotations_for_metadata の全キー)。
    # invalidate_annotations はこれらを落として "tags" センチネルを外し、遅延ロードを再武装する。
    # 派生値 (rating_value / ai_*_value / manual_*_value) も落とさないとサムネイル
    # オーバーレイ等が stale 値を描画し続ける (Codex P2 / PR #1184)。
    _ANNOTATION_CACHE_KEYS = (
        "tags",
        "tags_text",
        "captions",
        "caption_text",
        "scores",
        "score_value",
        "ai_score_value",
        "manual_score_value",
        "score_labels",
        "ratings",
        "rating_value",
        "ai_rating_value",
        "manual_rating_value",
        "quality_summary",
    )

    def invalidate_annotations(self, image_ids: list[int]) -> None:
        """指定画像のアノテーションキャッシュを無効化し、次回選択時に DB を再照会させる (Issue #1171)。

        外部プロセス (CLI) の DB 書き込みは GUI のメモリキャッシュへ自動反映されない
        (ADR 0067 §4: 手動リロード)。本 API はユーザーの明示的な再読込操作から呼ばれ、
        キャッシュ dict からアノテーションキーを落として ``"tags"`` センチネルを外し、
        ``_ensure_annotations_loaded`` の遅延ロード (#965) を再武装する。

        現在表示中の画像が対象に含まれる場合は ``refresh_image_annotations`` で即時
        DB 再取得し、``current_image_data_changed`` を再発行して表示を更新する。

        Args:
            image_ids: 無効化対象の画像 ID リスト (キャッシュ未登録 ID は無視)。
        """
        if not image_ids:
            return

        invalidated = 0
        for image_id in image_ids:
            cached = self.get_image_by_id(image_id)
            if cached is None:
                continue
            self._note_annotation_edit(image_id)
            for key in self._ANNOTATION_CACHE_KEYS:
                cached.pop(key, None)
            invalidated += 1

        logger.debug(f"アノテーションキャッシュ無効化: {invalidated}/{len(image_ids)} 件")

        # 現在表示中の画像は即時再取得して表示を最新化する
        # (refresh_image_annotations はキャッシュ未登録なら refresh_image へフォールバック)
        if self._current_image_id is not None and self._current_image_id in set(image_ids):
            self.refresh_image_annotations(self._current_image_id)

    def refresh_annotations_after_execution(self, phashes: set[str]) -> None:
        """完了した実行の注釈だけを非同期で無効化・必要時再取得する (#1384)。

        pHash に対応する全画像版の ID 解決は専用 worker で行う。検索キャッシュに
        存在する画像の注釈キーだけを外し、現在画像と後から選択する画像の注釈だけを
        worker で読み込む。検索結果外のメタデータや全件の注釈は取得しない。
        複数の完了通知は pending pHash をまとめ、取りこぼさず順次処理する。
        """
        if not phashes or self._annotation_refresh_closed:
            return
        if self._db_manager is None:
            logger.warning("DB Manager 未設定のため、実行後の注釈キャッシュ更新を開始できません")
            return

        # A new execution can have written newer annotations than an in-flight
        # read. Keep invalidated IDs, but do not apply that old read's result.
        self._cancel_annotation_load()
        for phash in phashes:
            self._annotation_pending_phashes[phash] = self._annotation_edit_serial
        self._start_annotation_lookup()

    def shutdown_annotation_refresh(self) -> None:
        """後続の取得・反映を抑止し、実行中の worker を待たずに退避する。

        repo 内の実行中 SQL を即座に中断できる保証はない。終了時は既存 manager の
        retirement に所有権を渡し、QThread の実行中破棄と GUI の終了待機を避ける。
        """
        if self._annotation_refresh_closed:
            return
        self._annotation_refresh_closed = True
        self._reset_annotation_refresh_context()
        if self._annotation_worker_manager is not None:
            self._annotation_worker_manager.cancel_all_workers(
                reason=CancelReason.SHUTDOWN, total_grace_ms=0
            )

    def _get_annotation_worker_manager(self) -> WorkerManager:
        if self._annotation_worker_manager is None:
            self._annotation_worker_manager = WorkerManager(self)
            # WorkerManager's terminal signal can originate in its worker signal
            # forwarding callback. The receiving QObject slot must run on GUI.
            self._annotation_worker_manager.worker_terminal.connect(
                self._on_annotation_refresh_terminal, Qt.ConnectionType.QueuedConnection
            )
            self._annotation_worker_manager.worker_thread_released.connect(
                self._on_annotation_refresh_thread_released, Qt.ConnectionType.QueuedConnection
            )
        return self._annotation_worker_manager

    def _next_annotation_worker_id(self, operation: str) -> str:
        self._annotation_worker_serial += 1
        return f"annotation_refresh_{operation}_{self._annotation_worker_serial}"

    def _reset_annotation_refresh_context(self) -> None:
        """検索結果・プロジェクト・DB の交換前の要求を無効にする。"""
        self._annotation_context_version += 1
        self._annotation_pending_phashes.clear()
        self._annotation_invalidated_ids.clear()
        self._annotation_versions.clear()
        self._annotation_edited_at.clear()
        self._annotation_failed_load = None
        self._cancel_annotation_load()
        request = self._annotation_lookup_request
        self._annotation_lookup_request = None
        if request is not None and self._annotation_worker_manager is not None:
            self._annotation_worker_manager.request_cancel_worker(
                request.worker_id, reason=CancelReason.SEARCH_REPLACED
            )

    def _cancel_annotation_load(self) -> None:
        request = self._annotation_load_request
        self._annotation_load_request = None
        if request is not None and self._annotation_worker_manager is not None:
            self._annotation_worker_manager.request_cancel_worker(
                request.worker_id, reason=CancelReason.SEARCH_REPLACED
            )

    def _note_annotation_edit(self, image_id: int) -> None:
        """手動編集/明示的再読込より前に開始した結果による上書きを防ぐ。"""
        self._annotation_edit_serial += 1
        self._annotation_edited_at[image_id] = self._annotation_edit_serial
        self._annotation_versions[image_id] = self._annotation_versions.get(image_id, 0) + 1
        self._annotation_invalidated_ids.discard(image_id)
        if self._annotation_load_request is not None and self._annotation_load_request.image_id == image_id:
            self._cancel_annotation_load()

    def _start_annotation_lookup(self) -> None:
        if (
            self._annotation_refresh_closed
            or self._annotation_active_worker_id is not None
            or self._annotation_lookup_request is not None
            or not self._annotation_pending_phashes
            or self._db_manager is None
        ):
            return
        cutoffs = self._annotation_pending_phashes.copy()
        self._annotation_pending_phashes.clear()
        worker_id = self._next_annotation_worker_id("lookup")
        self._annotation_lookup_request = _AnnotationLookupRequest(
            worker_id, self._annotation_context_version, cutoffs
        )
        worker = AnnotationRefreshLookupWorker(self._db_manager.image_repo, set(cutoffs))
        self._annotation_active_worker_id = worker_id
        if not self._get_annotation_worker_manager().start_worker(
            worker_id, worker, defer_thread_release=True
        ):
            self._annotation_active_worker_id = None
            self._annotation_lookup_request = None
            logger.error(f"注釈キャッシュ更新の ID 解決 worker を開始できません: pHash {len(cutoffs)}件")

    def _start_current_annotation_load(self) -> None:
        image_id = self._current_image_id
        if (
            self._annotation_refresh_closed
            or self._annotation_active_worker_id is not None
            or self._annotation_load_request is not None
            or self._annotation_lookup_request is not None
            or self._annotation_pending_phashes
            or self._db_manager is None
            or image_id is None
            or image_id not in self._annotation_invalidated_ids
        ):
            return
        cached = self._get_all_images_index().get(image_id)
        if cached is None:
            return
        failed = self._annotation_failed_load
        if (
            failed is not None
            and failed.context_version == self._annotation_context_version
            and failed.selection_version == self._annotation_selection_version
            and failed.image_id == image_id
            and failed.annotation_version == self._annotation_versions.get(image_id, 0)
        ):
            return
        worker_id = self._next_annotation_worker_id("load")
        self._annotation_load_request = _AnnotationLoadRequest(
            worker_id,
            self._annotation_context_version,
            self._annotation_selection_version,
            image_id,
            self._annotation_versions.get(image_id, 0),
            cached,
        )
        worker = AnnotationRefreshLoadWorker(self._db_manager.image_repo, image_id)
        self._annotation_active_worker_id = worker_id
        if not self._get_annotation_worker_manager().start_worker(
            worker_id, worker, defer_thread_release=True
        ):
            self._annotation_active_worker_id = None
            self._annotation_load_request = None
            logger.error(f"注釈再取得 worker を開始できません: image_id={image_id}")

    @Slot(object)
    def _on_annotation_refresh_terminal(self, event: WorkerTerminalEvent) -> None:
        """worker の取得結果だけを GUI スレッドの状態へ反映する。"""
        if self._annotation_refresh_closed:
            return
        if event.worker_id != self._annotation_active_worker_id:
            return
        lookup = self._annotation_lookup_request
        if lookup is not None and event.worker_id == lookup.worker_id:
            self._annotation_lookup_request = None
            if lookup.context_version != self._annotation_context_version:
                return
            if event.outcome is WorkerOutcome.SUCCEEDED:
                self._apply_annotation_lookup(lookup, cast(dict[str, list[int]], event.result))
            elif event.outcome is not WorkerOutcome.CANCELED:
                logger.error(
                    f"実行後の注釈キャッシュ ID 解決失敗: pHash {len(lookup.edit_cutoffs)}件: {event.error}"
                )

        load = self._annotation_load_request
        if load is not None and event.worker_id == load.worker_id:
            self._annotation_load_request = None
            if event.outcome is WorkerOutcome.SUCCEEDED:
                annotations = cast(dict[str, Any] | None, event.result)
                self._apply_annotation_load(load, annotations)
                self._annotation_failed_load = load if not annotations else None
            elif event.outcome is not WorkerOutcome.CANCELED:
                self._annotation_failed_load = load
                logger.error(f"注釈再取得失敗: image_id={load.image_id}: {event.error}")
            # A failed/missing read stays invalidated for a later selection or
            # execution notification; do not create an automatic retry loop.
            return

    @Slot(str)
    def _on_annotation_refresh_thread_released(self, worker_id: str) -> None:
        """旧 worker の QObject 破棄まで完了してから最新要求を開始する。"""
        if worker_id != self._annotation_active_worker_id:
            return
        self._annotation_active_worker_id = None
        if self._annotation_refresh_closed:
            return
        self._start_annotation_lookup()
        self._start_current_annotation_load()

    def _apply_annotation_lookup(
        self, request: _AnnotationLookupRequest, phash_to_ids: dict[str, list[int]]
    ) -> None:
        # Several pHashes can resolve the same ID. Invalidation counts must
        # describe unique cached images, including all versions of each pHash.
        cutoffs_by_id: dict[int, int] = {}
        for phash, ids in phash_to_ids.items():
            cutoff = request.edit_cutoffs.get(phash)
            if cutoff is not None:
                for image_id in ids:
                    cutoffs_by_id[image_id] = max(cutoffs_by_id.get(image_id, cutoff), cutoff)
        index = self._get_all_images_index()
        invalidated = 0
        edited = 0
        cached_count = 0
        for image_id, cutoff in cutoffs_by_id.items():
            cached = index.get(image_id)
            if cached is None:
                continue
            cached_count += 1
            if self._annotation_edited_at.get(image_id, 0) > cutoff:
                edited += 1
                continue
            for key in self._ANNOTATION_CACHE_KEYS:
                cached.pop(key, None)
            self._annotation_versions[image_id] = self._annotation_versions.get(image_id, 0) + 1
            self._annotation_invalidated_ids.add(image_id)
            invalidated += 1
        logger.info(
            f"実行後の注釈キャッシュ無効化: pHash {len(request.edit_cutoffs)}件、"
            f"ID 解決 {len(cutoffs_by_id)}件、検索キャッシュ {cached_count}件、"
            f"無効化 {invalidated}件、後続の編集優先 {edited}件"
        )

    def _apply_annotation_load(
        self, request: _AnnotationLoadRequest, annotations: dict[str, Any] | None
    ) -> None:
        if (
            request.context_version != self._annotation_context_version
            or request.selection_version != self._annotation_selection_version
            or request.image_id != self._current_image_id
            or request.annotation_version != self._annotation_versions.get(request.image_id, 0)
            or self._get_all_images_index().get(request.image_id) is not request.cached
        ):
            logger.debug(f"古い注釈再取得結果を破棄: image_id={request.image_id}、反映 0件")
            return
        if not annotations:
            logger.warning(f"注釈再取得: image_id={request.image_id}、取得 0件、反映 0件")
            return
        # Restrict the merge to annotation keys even if a repository substitute
        # supplies extra metadata. Processed resolution and paths stay intact.
        request.cached.update(
            {key: annotations[key] for key in self._ANNOTATION_CACHE_KEYS if key in annotations}
        )
        self._annotation_invalidated_ids.discard(request.image_id)
        self.current_image_data_changed.emit(request.cached)
        logger.info(f"注釈再取得: image_id={request.image_id}、取得 1件、反映 1件")

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
