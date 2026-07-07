# tests/unit/gui/state/test_dataset_state.py

from pathlib import Path
from unittest.mock import Mock

import pytest

from lorairo.gui.state.dataset_state import DatasetStateManager


class TestDatasetStateManager:
    """DatasetStateManager のユニットテスト"""

    @pytest.fixture
    def state_manager(self):
        """テスト用のDatasetStateManagerを作成"""
        return DatasetStateManager()

    @pytest.fixture
    def sample_image_metadata(self):
        """サンプル画像メタデータ"""
        return [
            {"id": 1, "stored_image_path": str(Path("/test/image1.jpg")), "width": 1024, "height": 768},
            {"id": 2, "stored_image_path": str(Path("/test/image2.jpg")), "width": 800, "height": 600},
            {"id": 3, "stored_image_path": str(Path("/test/image3.jpg")), "width": 1200, "height": 900},
        ]

    def test_initialization(self, state_manager):
        """初期化テスト"""
        assert state_manager.dataset_path is None
        assert len(state_manager.all_images) == 0
        assert len(state_manager.filtered_images) == 0
        assert len(state_manager.selected_image_ids) == 0
        assert state_manager.current_image_id is None
        assert state_manager.thumbnail_size == 150
        assert state_manager.layout_mode == "grid"

    def test_set_dataset_path(self, state_manager):
        """データセットパス設定テスト"""
        test_path = Path("/test/dataset")

        # シグナル発行確認用のモック
        signal_mock = Mock()
        state_manager.dataset_changed.connect(signal_mock)

        state_manager.set_dataset_path(test_path)

        assert state_manager.dataset_path == test_path
        signal_mock.assert_called_once_with(str(test_path))

    def test_set_dataset_images(self, state_manager, sample_image_metadata):
        """データセット画像設定テスト"""
        # シグナル発行確認用のモック
        images_loaded_mock = Mock()
        images_filtered_mock = Mock()
        dataset_loaded_mock = Mock()

        state_manager.images_loaded.connect(images_loaded_mock)
        state_manager.images_filtered.connect(images_filtered_mock)
        state_manager.dataset_loaded.connect(dataset_loaded_mock)

        state_manager.set_dataset_images(sample_image_metadata)

        assert len(state_manager.all_images) == 3
        assert len(state_manager.filtered_images) == 3
        assert state_manager.selected_image_ids == []

        images_loaded_mock.assert_called_once()
        images_filtered_mock.assert_called_once()
        dataset_loaded_mock.assert_called_once_with(3)

    def test_selection_management(self, state_manager, sample_image_metadata):
        """選択管理テスト"""
        state_manager.set_dataset_images(sample_image_metadata)

        # 単一選択
        selection_mock = Mock()
        state_manager.selection_changed.connect(selection_mock)

        state_manager.set_selected_images([1])
        assert state_manager.selected_image_ids == [1]
        selection_mock.assert_called_with([1])

        # 複数選択
        state_manager.set_selected_images([1, 2])
        assert state_manager.selected_image_ids == [1, 2]

        # 選択追加
        state_manager.add_to_selection(3)
        assert state_manager.selected_image_ids == [1, 2, 3]

        # 選択削除
        state_manager.remove_from_selection(2)
        assert state_manager.selected_image_ids == [1, 3]

        # トグル選択
        state_manager.toggle_selection(2)  # 追加
        assert 2 in state_manager.selected_image_ids
        state_manager.toggle_selection(2)  # 削除
        assert 2 not in state_manager.selected_image_ids

    def test_current_image_management(self, state_manager):
        """現在画像管理テスト"""
        current_changed_mock = Mock()
        current_cleared_mock = Mock()

        state_manager.current_image_changed.connect(current_changed_mock)
        state_manager.current_image_cleared.connect(current_cleared_mock)

        # 現在画像設定
        state_manager.set_current_image(1)
        assert state_manager.current_image_id == 1
        current_changed_mock.assert_called_once_with(1)

        # 現在画像クリア
        state_manager.clear_current_image()
        assert state_manager.current_image_id is None
        current_cleared_mock.assert_called_once()

    def test_set_current_image_falls_back_to_db_when_uncached(self, state_manager):
        """キャッシュ未登録の画像でも DB から取得して空辞書でなく実データを emit する。

        登録完了サマリの「#N を表示」リンク等、現在の検索結果に含まれない画像を
        選択したときに preview/details が空にならないようにする (PR #762 Codex P2)。
        """
        data_changed_mock = Mock()
        state_manager.current_image_data_changed.connect(data_changed_mock)

        mock_db_manager = Mock()
        mock_repository = Mock()
        mock_db_manager.image_repo = mock_repository
        fetched = {"id": 4412, "stored_image_path": "/data/4412.webp", "width": 1024, "height": 1536}
        mock_repository.get_image_metadata.return_value = fetched
        state_manager._db_manager = mock_db_manager

        state_manager.set_current_image(4412)

        mock_repository.get_image_metadata.assert_called_once_with(4412)
        data_changed_mock.assert_called_once_with(fetched)

    def test_ui_state_management(self, state_manager):
        """UI状態管理テスト"""
        thumbnail_size_mock = Mock()
        layout_mode_mock = Mock()
        ui_state_mock = Mock()

        state_manager.thumbnail_size_changed.connect(thumbnail_size_mock)
        state_manager.layout_mode_changed.connect(layout_mode_mock)
        state_manager.ui_state_changed.connect(ui_state_mock)

        # サムネイルサイズ変更
        state_manager.set_thumbnail_size(200)
        assert state_manager.thumbnail_size == 200
        thumbnail_size_mock.assert_called_once_with(200)

        # レイアウトモード変更
        state_manager.set_layout_mode("list")
        assert state_manager.layout_mode == "list"
        layout_mode_mock.assert_called_once_with("list")

        # 任意UI状態
        state_manager.set_ui_state("test_key", "test_value")
        assert state_manager.get_ui_state("test_key") == "test_value"
        ui_state_mock.assert_called_once_with("test_key", "test_value")

    def test_utility_methods(self, state_manager, sample_image_metadata):
        """ユーティリティメソッドテスト"""
        state_manager.set_dataset_images(sample_image_metadata)

        # 画像検索
        image_data = state_manager.get_image_by_id(1)
        assert image_data["id"] == 1
        # Cross-platform path comparison using Path objects
        assert Path(image_data["stored_image_path"]) == Path("/test/image1.jpg")

        # 存在チェック
        assert state_manager.has_images() is True
        assert state_manager.has_filtered_images() is True

        # 選択状態チェック
        state_manager.set_selected_images([1, 2])
        assert state_manager.is_image_selected(1) is True
        assert state_manager.is_image_selected(3) is False

        # 現在画像データ取得
        state_manager.set_current_image(2)
        current_data = state_manager.get_current_image_data()
        assert current_data["id"] == 2

    def test_state_summary(self, state_manager, sample_image_metadata):
        """状態サマリーテスト"""
        test_path = Path("/test/dataset")
        state_manager.set_dataset_path(test_path)
        state_manager.set_dataset_images(sample_image_metadata)
        state_manager.set_selected_images([1, 2])
        state_manager.set_current_image(1)

        summary = state_manager.get_state_summary()

        # Cross-platform path comparison - compare the expected path string with actual path string
        assert summary["dataset_path"] == str(test_path)
        assert summary["total_images"] == 3
        assert summary["filtered_images"] == 3
        assert summary["selected_images"] == 2
        assert summary["current_image_id"] == 1
        assert summary["thumbnail_size"] == 150
        assert summary["layout_mode"] == "grid"

    def test_clear_dataset(self, state_manager, sample_image_metadata):
        """データセットクリアテスト"""
        # データ設定
        state_manager.set_dataset_path(Path("/test/dataset"))
        state_manager.set_dataset_images(sample_image_metadata)
        state_manager.set_selected_images([1])
        state_manager.set_current_image(1)

        # クリア実行 (set_current_image より後に接続し、clear_dataset の emit だけ捕捉する)
        filter_cleared_mock = Mock()
        state_manager.filter_cleared.connect(filter_cleared_mock)
        current_data_mock = Mock()
        state_manager.current_image_data_changed.connect(current_data_mock)

        state_manager.clear_dataset()

        # 状態確認
        assert state_manager.dataset_path is None
        assert len(state_manager.all_images) == 0
        assert len(state_manager.filtered_images) == 0
        assert state_manager.selected_image_ids == []
        assert state_manager.current_image_id is None

        filter_cleared_mock.assert_called_once()
        # 現在画像があったので詳細/プレビューへ空データ通知でクリアさせる (#1228 Codex P2)
        current_data_mock.assert_called_once_with({})

    def test_clear_dataset_without_current_image_skips_empty_notify(
        self, state_manager, sample_image_metadata
    ):
        """現在画像が無い状態の clear_dataset は空データ通知を出さない (#1228 Codex P2)。"""
        state_manager.set_dataset_images(sample_image_metadata)
        current_data_mock = Mock()
        state_manager.current_image_data_changed.connect(current_data_mock)

        state_manager.clear_dataset()

        current_data_mock.assert_not_called()

    def test_clear_current_image_emits_empty_data_notify(self, state_manager, sample_image_metadata):
        """clear_current_image は current_image_cleared と current_image_data_changed({}) を出す (#1228 Codex P2)。

        詳細パネルは current_image_data_changed を購読するため、現在画像クリア時に空データ通知を
        出さないと stale な表示が残る (current_image_cleared のみでは詳細パネルが購読していない)。
        ExportTab のタグ絞り込みで現在画像が表示集合から外れる経路等で顕在化する。
        """
        state_manager.set_dataset_images(sample_image_metadata)
        state_manager.set_current_image(1)
        cleared_mock = Mock()
        data_mock = Mock()
        state_manager.current_image_cleared.connect(cleared_mock)
        state_manager.current_image_data_changed.connect(data_mock)

        state_manager.clear_current_image()

        cleared_mock.assert_called_once()
        data_mock.assert_called_once_with({})

    def test_clear_current_image_noop_when_already_cleared(self, state_manager):
        """現在画像が無ければ clear_current_image は何も emit しない (#1228)。"""
        cleared_mock = Mock()
        data_mock = Mock()
        state_manager.current_image_cleared.connect(cleared_mock)
        state_manager.current_image_data_changed.connect(data_mock)

        state_manager.clear_current_image()

        cleared_mock.assert_not_called()
        data_mock.assert_not_called()

    def test_refresh_images_uses_batch_query(self, state_manager, sample_image_metadata):
        """refresh_images が get_images_metadata_batch を1回呼ぶこと"""
        state_manager.set_dataset_images(sample_image_metadata)

        mock_db_manager = Mock()
        mock_repository = Mock()
        mock_db_manager.image_repo = mock_repository
        mock_repository.get_images_metadata_batch.return_value = [
            {"id": 1, "stored_image_path": "/test/image1_updated.jpg", "width": 2048, "height": 1536},
            {"id": 2, "stored_image_path": "/test/image2_updated.jpg", "width": 1600, "height": 1200},
        ]
        state_manager._db_manager = mock_db_manager

        state_manager.refresh_images([1, 2])

        # バッチメソッドが1回だけ呼ばれること
        mock_repository.get_images_metadata_batch.assert_called_once_with([1, 2])
        # 個別メソッドは呼ばれないこと
        mock_repository.get_image_metadata.assert_not_called()

    def test_refresh_images_updates_cache(self, state_manager, sample_image_metadata):
        """refresh_images がキャッシュを更新すること"""
        state_manager.set_dataset_images(sample_image_metadata)

        mock_db_manager = Mock()
        mock_repository = Mock()
        mock_db_manager.image_repo = mock_repository
        updated_metadata = {"id": 1, "stored_image_path": "/updated.jpg", "width": 2048, "height": 1536}
        mock_repository.get_images_metadata_batch.return_value = [updated_metadata]
        state_manager._db_manager = mock_db_manager

        state_manager.refresh_images([1])

        # キャッシュが更新されていること
        image = state_manager.get_image_by_id(1)
        assert image["width"] == 2048

    def test_refresh_images_empty_list(self, state_manager):
        """空リストでは何も呼ばれない"""
        mock_db_manager = Mock()
        state_manager._db_manager = mock_db_manager

        state_manager.refresh_images([])
        mock_db_manager.image_repo.get_images_metadata_batch.assert_not_called()

    # === get_image_by_id インデックス (Issue #584 / D2) ===

    def test_get_image_by_id_returns_none_when_not_found(self, state_manager, sample_image_metadata):
        """未登録IDでは None を返す"""
        state_manager.set_dataset_images(sample_image_metadata)
        assert state_manager.get_image_by_id(999) is None

    def test_get_image_by_id_index_invalidated_on_search_results(
        self, state_manager, sample_image_metadata
    ):
        """update_from_search_results 後、旧IDは消え新IDが引けること（インデックス無効化）"""
        state_manager.set_dataset_images(sample_image_metadata)
        assert state_manager.get_image_by_id(1) is not None  # 初回でインデックス構築

        # 完全置換（id=1,2,3 → id=10,11）
        state_manager.update_from_search_results(
            [
                {"id": 10, "stored_image_path": "/test/new10.jpg", "width": 100, "height": 100},
                {"id": 11, "stored_image_path": "/test/new11.jpg", "width": 100, "height": 100},
            ]
        )

        assert state_manager.get_image_by_id(1) is None  # 旧IDは stale 参照されない
        assert state_manager.get_image_by_id(10)["stored_image_path"] == "/test/new10.jpg"

    def test_get_image_by_id_index_invalidated_on_metadata_update(
        self, state_manager, sample_image_metadata
    ):
        """update_image_metadata 後、インデックス経由で最新値が引けること"""
        state_manager.set_dataset_images(sample_image_metadata)
        assert state_manager.get_image_by_id(1)["width"] == 1024  # 初回でインデックス構築

        state_manager.update_image_metadata(
            1, {"id": 1, "stored_image_path": "/test/image1.jpg", "width": 4096, "height": 2160}
        )

        assert state_manager.get_image_by_id(1)["width"] == 4096

    def test_get_image_by_id_index_invalidated_on_clear(self, state_manager, sample_image_metadata):
        """clear_dataset 後はインデックスが空になり None を返すこと"""
        state_manager.set_dataset_images(sample_image_metadata)
        assert state_manager.get_image_by_id(1) is not None

        state_manager.clear_dataset()
        assert state_manager.get_image_by_id(1) is None

    # === Issue #965: アノテーション遅延取得 ===

    def test_set_current_image_lazy_loads_annotations(self, state_manager):
        """検索キャッシュ dict (アノテーション無し) 選択時に DB から遅延取得して merge する"""
        # 検索フェーズ相当: アノテーションキーを持たない dict
        state_manager.update_from_search_results(
            [{"id": 1, "stored_image_path": "/test/image1.jpg", "width": 1024, "height": 768}]
        )

        db_manager = Mock()
        db_manager.image_repo.get_image_annotation_metadata.return_value = {
            "tags": [{"tag": "cat"}],
            "tags_text": "cat",
            "captions": [],
            "caption_text": "",
            "scores": [],
            "score_value": 0.0,
            "score_labels": [],
            "ratings": [],
            "quality_summary": {},
        }
        state_manager.set_db_manager(db_manager)

        received = Mock()
        state_manager.current_image_data_changed.connect(received)

        state_manager.set_current_image(1)

        # 対象1件だけ遅延取得される
        db_manager.image_repo.get_image_annotation_metadata.assert_called_once_with(1)
        # 発行された dict にアノテーションが merge されている
        emitted = received.call_args[0][0]
        assert emitted["tags_text"] == "cat"
        assert emitted["stored_image_path"] == "/test/image1.jpg"
        # キャッシュ (live 参照) も更新され、再選択は DB 往復不要
        assert state_manager.get_image_by_id(1)["tags_text"] == "cat"

    def test_set_current_image_skips_lazy_load_when_annotations_present(self, state_manager):
        """既にアノテーション済みの dict は遅延取得しない"""
        state_manager.update_from_search_results(
            [
                {
                    "id": 1,
                    "stored_image_path": "/test/image1.jpg",
                    "tags": [],
                    "tags_text": "",
                }
            ]
        )

        db_manager = Mock()
        state_manager.set_db_manager(db_manager)

        state_manager.set_current_image(1)

        db_manager.image_repo.get_image_annotation_metadata.assert_not_called()

    def test_set_current_image_without_db_manager_does_not_crash(self, state_manager):
        """db_manager 未設定でも遅延取得をスキップして安全に動作する"""
        state_manager.update_from_search_results([{"id": 1, "stored_image_path": "/test/image1.jpg"}])

        received = Mock()
        state_manager.current_image_data_changed.connect(received)

        state_manager.set_current_image(1)

        # シグナルは発行され、アノテーション無しのまま (例外なし)
        emitted = received.call_args[0][0]
        assert emitted["id"] == 1
        assert "tags" not in emitted

    # === Issue #1171: アノテーションキャッシュの明示無効化 (ADR 0084) ===

    def test_invalidate_annotations_rearms_lazy_load_for_non_current_image(self, state_manager):
        """無効化後の再選択で DB を再照会し最新アノテーションが入る (Issue #1171)"""
        state_manager.update_from_search_results(
            [
                {"id": 1, "stored_image_path": "/test/image1.jpg"},
                {"id": 2, "stored_image_path": "/test/image2.jpg"},
            ]
        )
        db_manager = Mock()
        annotations_v1 = {
            "tags": [{"tag": "old_tag"}],
            "tags_text": "old_tag",
        }
        annotations_v2 = {
            "tags": [{"tag": "cli_added_tag"}],
            "tags_text": "cli_added_tag",
        }
        db_manager.image_repo.get_image_annotation_metadata.return_value = annotations_v1
        state_manager.set_db_manager(db_manager)

        # 1回目の選択で遅延ロード → 別画像へ移動 (画像1は非 current)
        state_manager.set_current_image(1)
        state_manager.set_current_image(2)
        assert state_manager.get_image_by_id(1)["tags_text"] == "old_tag"

        # CLI が DB を書き換えた想定で無効化 → キャッシュからアノテーションキーが落ちる
        db_manager.image_repo.get_image_annotation_metadata.return_value = annotations_v2
        state_manager.invalidate_annotations([1])
        assert "tags" not in state_manager.get_image_by_id(1)
        assert state_manager.get_image_by_id(1)["stored_image_path"] == "/test/image1.jpg"

        # 再選択で DB 再照会され最新値が入る
        state_manager.set_current_image(1)
        assert state_manager.get_image_by_id(1)["tags_text"] == "cli_added_tag"

    def test_invalidate_annotations_refreshes_current_image_immediately(self, state_manager):
        """現在表示中の画像は即時 DB 再取得 + current_image_data_changed 再発行 (Issue #1171)"""
        state_manager.update_from_search_results([{"id": 1, "stored_image_path": "/test/image1.jpg"}])
        db_manager = Mock()
        db_manager.image_repo.get_image_annotation_metadata.return_value = {
            "tags": [{"tag": "old_tag"}],
            "tags_text": "old_tag",
        }
        state_manager.set_db_manager(db_manager)
        state_manager.set_current_image(1)

        received = Mock()
        state_manager.current_image_data_changed.connect(received)
        db_manager.image_repo.get_image_annotation_metadata.return_value = {
            "tags": [{"tag": "cli_added_tag"}],
            "tags_text": "cli_added_tag",
        }

        state_manager.invalidate_annotations([1])

        emitted = received.call_args[0][0]
        assert emitted["tags_text"] == "cli_added_tag"
        assert emitted["stored_image_path"] == "/test/image1.jpg"

    def test_invalidate_annotations_ignores_uncached_and_empty(self, state_manager):
        """キャッシュ未登録 ID / 空リストは安全に無視する (Issue #1171)"""
        state_manager.update_from_search_results([{"id": 1, "stored_image_path": "/test/image1.jpg"}])
        db_manager = Mock()
        state_manager.set_db_manager(db_manager)

        state_manager.invalidate_annotations([])
        state_manager.invalidate_annotations([999])

        db_manager.image_repo.get_image_annotation_metadata.assert_not_called()

    # === Issue #967: 全件コピーを伴わない軽量アクセサ ===

    def test_count_accessors(self, state_manager, sample_image_metadata):
        """image_count / filtered_count が全件コピーなしで件数を返す

        Issue #969: 2 層統合後は両者は常に同値 (単一リスト)。
        """
        state_manager.set_dataset_images(sample_image_metadata)
        assert state_manager.image_count == 3
        assert state_manager.filtered_count == 3
        assert state_manager.filtered_count == state_manager.image_count

        # 検索結果で置換しても両者は同値
        state_manager.update_from_search_results(sample_image_metadata[:2])
        assert state_manager.image_count == 2
        assert state_manager.filtered_count == 2

    def test_get_filtered_image_ids_slice(self, state_manager):
        """指定ページ範囲のスライスから ID のみを抽出する"""
        images = [{"id": i, "stored_image_path": f"/test/{i}.jpg"} for i in range(1, 11)]
        state_manager.set_dataset_images(images)

        assert state_manager.get_filtered_image_ids_slice(0, 3) == [1, 2, 3]
        assert state_manager.get_filtered_image_ids_slice(3, 6) == [4, 5, 6]
        # 範囲外は空
        assert state_manager.get_filtered_image_ids_slice(100, 200) == []

    def test_get_filtered_image_ids_slice_skips_non_int_ids(self, state_manager):
        """id が int でない要素はスキップする (従来の get_page_image_ids と同じ挙動)"""
        state_manager.set_dataset_images(
            [
                {"id": 1},
                {"id": None},
                {"stored_image_path": "/no_id.jpg"},
                {"id": 4},
            ]
        )
        assert state_manager.get_filtered_image_ids_slice(0, 4) == [1, 4]
