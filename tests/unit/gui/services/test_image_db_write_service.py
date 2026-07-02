# tests/unit/gui/services/test_image_db_write_service.py

from unittest.mock import Mock, patch

import pytest

from lorairo.gui.services.image_db_write_service import ImageDBWriteService


class TestImageDBWriteService:
    """ImageDBWriteService単体テスト（書き込み系のみ。

    旧 get_image_details / get_annotation_data は呼び出し元ゼロの dead code
    だったため Issue #1061 で削除した。読み取り (詳細パネル表示) の検証は
    tests/unit/database/test_db_repository_annotations.py (メタデータ投影) が担う。
    """

    @pytest.fixture
    def mock_db_manager(self):
        """テスト用モックImageDatabaseManager"""
        mock_db_manager = Mock()
        mock_db_manager.repository = Mock()
        return mock_db_manager

    @pytest.fixture
    def service(self, mock_db_manager):
        """テスト用ImageDBWriteService"""
        return ImageDBWriteService(db_manager=mock_db_manager)

    def test_constructor_with_db_manager(self, mock_db_manager):
        """コンストラクタ正常初期化（Phase 1-2パターン）"""
        service = ImageDBWriteService(db_manager=mock_db_manager)

        assert service.db_manager == mock_db_manager
        assert hasattr(service, "db_manager")

    def test_update_rating_success(self, service, mock_db_manager):
        """Rating更新機能正常動作（プレースホルダー実装）"""
        image_id = 100
        rating = "PG"

        result = service.update_rating(image_id, rating)

        # プレースホルダー実装では常にTrueを返す
        assert result is True

    def test_update_score_success(self, service, mock_db_manager):
        """Score更新機能正常動作"""
        image_id = 200
        score = 750  # 0-1000範囲

        result = service.update_score(image_id, score)

        assert result is True

        # save_annotations が display_score を含む ScoreAnnotationData で呼ばれることを確認
        mock_db_manager.annotation_repo.save_annotations.assert_called_once()
        call_kwargs = mock_db_manager.annotation_repo.save_annotations.call_args
        annotations = (
            call_kwargs.kwargs["annotations"] if call_kwargs.kwargs else call_kwargs[1]["annotations"]
        )
        score_data = annotations["scores"][0]
        assert "display_score" in score_data
        assert score_data["score"] == 7.5  # 750 / 100.0

    def test_update_rating_invalid_image_id(self, service, mock_db_manager):
        """不正なimage_id指定時の適切な処理（プレースホルダー実装）"""
        invalid_image_id = -1
        rating = "R"

        # プレースホルダー実装では常にTrueを返す
        result = service.update_rating(invalid_image_id, rating)

        assert result is True

    def test_update_score_invalid_range(self, service, mock_db_manager):
        """スコア範囲外の値の処理"""
        image_id = 300
        invalid_score = 1500  # 0-1000範囲外

        with patch("lorairo.gui.services.image_db_write_service.logger") as mock_logger:
            result = service.update_score(image_id, invalid_score)

            assert result is False
            mock_logger.warning.assert_called_with(
                f"Invalid score value: {invalid_score}. Must be between 0-1000"
            )

    def test_add_tag_batch_success(self, service, mock_db_manager):
        """バッチタグ追加成功ケース"""
        image_ids = [1, 2, 3]
        tag = "landscape"

        # 新しい原子的バッチ追加メソッドのモック設定
        mock_db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, 3)
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        # 実行
        result = service.add_tag_batch(image_ids, tag)

        # 検証
        assert result is True
        mock_db_manager.annotation_repo.add_tag_to_images_batch.assert_called_once_with(
            image_ids=image_ids, tag=tag, model_id=42
        )

    def test_add_tag_batch_duplicate_skip(self, service, mock_db_manager):
        """重複タグのスキップテスト"""
        image_ids = [1, 2]
        tag = "landscape"

        # 新しい原子的バッチ追加メソッドのモック設定（重複により0件追加）
        mock_db_manager.annotation_repo.add_tag_to_images_batch.return_value = (True, 0)
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        # 実行
        result = service.add_tag_batch(image_ids, tag)

        # 検証: 重複のため追加件数は0だが成功扱い
        assert result is True
        mock_db_manager.annotation_repo.add_tag_to_images_batch.assert_called_once_with(
            image_ids=image_ids, tag=tag, model_id=42
        )

    def test_add_tag_batch_empty_image_ids(self, service, mock_db_manager):
        """空の画像IDリストでの呼び出し"""
        result = service.add_tag_batch([], "landscape")

        # 検証: 早期リターンで False
        assert result is False
        mock_db_manager.annotation_repo.add_tag_to_images_batch.assert_not_called()

    def test_add_tag_batch_empty_tag(self, service, mock_db_manager):
        """空タグでの呼び出し"""
        result = service.add_tag_batch([1, 2], "")

        # 検証: 早期リターンで False
        assert result is False
        mock_db_manager.annotation_repo.add_tag_to_images_batch.assert_not_called()

    def test_add_tag_batch_db_error_returns_false(self, service, mock_db_manager):
        """DB エラー (SQLAlchemyError) 時は False を返す (#1062)"""
        from sqlalchemy.exc import SQLAlchemyError

        image_ids = [1, 2]
        tag = "landscape"

        mock_db_manager.annotation_repo.add_tag_to_images_batch.side_effect = SQLAlchemyError("DB Error")
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        result = service.add_tag_batch(image_ids, tag)

        assert result is False

    def test_add_tag_batch_unexpected_exception_propagates(self, service, mock_db_manager):
        """予期しない例外 (プログラミングエラー) は握りつぶさず伝播する (#1062)"""
        mock_db_manager.annotation_repo.add_tag_to_images_batch.side_effect = TypeError("bug")
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        with pytest.raises(TypeError):
            service.add_tag_batch([1, 2], "landscape")

    def test_update_rating_image_not_found_returns_false(self, service, mock_db_manager):
        """image_id 不存在 (ValueError) は期待されるケースとして False を返す (#1062)"""
        mock_db_manager.annotation_repo.save_annotations.side_effect = ValueError("image not found")
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        result = service.update_rating(999, "PG")

        assert result is False

    def test_update_caption_db_error_returns_false(self, service, mock_db_manager):
        """update_caption の DB エラーも False を返す (#1062)"""
        from sqlalchemy.exc import SQLAlchemyError

        mock_db_manager.annotation_repo.save_annotations.side_effect = SQLAlchemyError("locked")
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        result = service.update_caption(1, "a caption")

        assert result is False

    def test_update_score_unexpected_exception_propagates(self, service, mock_db_manager):
        """update_score の予期しない例外は伝播する (#1062)"""
        mock_db_manager.annotation_repo.save_annotations.side_effect = AttributeError("bug")
        mock_db_manager.get_manual_edit_model_id.return_value = 42

        with pytest.raises(AttributeError):
            service.update_score(1, 500)
