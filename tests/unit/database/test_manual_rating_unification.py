"""
Issue #119: manual_rating 格納先の Rating テーブル統一テスト

TDD RED フェーズ:
- update_manual_rating が Rating テーブルに書き込むことを確認
- _apply_manual_filters が正しくフィルタすることを確認
"""

import pytest
from sqlalchemy.orm import sessionmaker

from lorairo.database.db_repository import ImageRepository
from lorairo.database.schema import Image, Model, Rating


@pytest.fixture
def image_id(db_session_factory: sessionmaker) -> int:
    """テスト用 Image レコードを挿入して ID を返す。"""
    with db_session_factory() as session:
        image = Image(
            uuid="test-uuid-manual-rating",
            phash="deadbeef01234567",
            original_image_path="/tmp/test.webp",
            stored_image_path="/tmp/test.webp",
            width=100,
            height=100,
            format="WEBP",
            mode="RGB",
            has_alpha=False,
            filename="test.webp",
            extension=".webp",
        )
        session.add(image)
        session.commit()
        return image.id


class TestUpdateManualRatingWritesToRatingTable:
    """update_manual_rating が Rating テーブルに INSERT/DELETE することを確認。"""

    def test_set_rating_inserts_rating_record(
        self, test_repository: ImageRepository, db_session_factory: sessionmaker, image_id: int
    ) -> None:
        """PG を設定すると Rating テーブルに MANUAL_EDIT レコードが 1 件挿入される。"""
        result = test_repository.update_manual_rating(image_id, "PG")

        assert result is True
        with db_session_factory() as session:
            manual_model = session.query(Model).filter_by(name="MANUAL_EDIT").first()
            assert manual_model is not None, "MANUAL_EDIT モデルが作成されていない"
            ratings = session.query(Rating).filter_by(image_id=image_id, model_id=manual_model.id).all()
            assert len(ratings) == 1, f"Rating レコードが 1 件のはずが {len(ratings)} 件"
            assert ratings[0].normalized_rating == "PG"

    def test_set_rating_none_deletes_rating_records(
        self, test_repository: ImageRepository, db_session_factory: sessionmaker, image_id: int
    ) -> None:
        """rating=None で解除すると MANUAL_EDIT Rating が全て削除される。"""
        test_repository.update_manual_rating(image_id, "PG")
        result = test_repository.update_manual_rating(image_id, None)

        assert result is True
        with db_session_factory() as session:
            manual_model = session.query(Model).filter_by(name="MANUAL_EDIT").first()
            if manual_model is None:
                return  # モデルがなければレコードもない
            ratings = session.query(Rating).filter_by(image_id=image_id, model_id=manual_model.id).all()
            assert len(ratings) == 0, f"解除後に Rating レコードが残っている: {len(ratings)} 件"

    def test_set_rating_twice_keeps_history(
        self, test_repository: ImageRepository, db_session_factory: sessionmaker, image_id: int
    ) -> None:
        """PG → R と 2 回設定すると Rating テーブルに 2 件残る（履歴保持）。"""
        test_repository.update_manual_rating(image_id, "PG")
        test_repository.update_manual_rating(image_id, "R")

        with db_session_factory() as session:
            manual_model = session.query(Model).filter_by(name="MANUAL_EDIT").first()
            assert manual_model is not None
            ratings = session.query(Rating).filter_by(image_id=image_id, model_id=manual_model.id).all()
            assert len(ratings) == 2, f"履歴として 2 件のはずが {len(ratings)} 件"
            normalized_values = {r.normalized_rating for r in ratings}
            assert "PG" in normalized_values
            assert "R" in normalized_values

    def test_nonexistent_image_id_returns_false(self, test_repository: ImageRepository) -> None:
        """存在しない image_id では False を返し、例外は発生しない。"""
        result = test_repository.update_manual_rating(99999, "PG")
        assert result is False

    def test_does_not_write_to_image_manual_rating_column(
        self, test_repository: ImageRepository, db_session_factory: sessionmaker, image_id: int
    ) -> None:
        """Image テーブルの manual_rating カラムは変更されない（カラム削除後は属性なし）。"""
        test_repository.update_manual_rating(image_id, "PG")

        with db_session_factory() as session:
            image = session.get(Image, image_id)
            assert image is not None
            # manual_rating カラム削除後は属性が存在しない
            assert not hasattr(image, "manual_rating"), (
                "Image.manual_rating カラムは廃止されるため属性が存在してはいけない"
            )


class TestApplyManualFiltersWithRatingTable:
    """_apply_manual_filters が Rating テーブルを参照してフィルタすることを確認。"""

    @pytest.fixture
    def two_images(self, db_session_factory: sessionmaker) -> tuple[int, int]:
        """PG 設定済みと未設定の画像を 2 件作成して ID タプルを返す。"""
        with db_session_factory() as session:
            img1 = Image(
                uuid="filter-test-uuid-1",
                phash="filter01234567ab",
                original_image_path="/tmp/filter1.webp",
                stored_image_path="/tmp/filter1.webp",
                width=100,
                height=100,
                format="WEBP",
                mode="RGB",
                has_alpha=False,
                filename="filter1.webp",
                extension=".webp",
            )
            img2 = Image(
                uuid="filter-test-uuid-2",
                phash="filter89abcdef01",
                original_image_path="/tmp/filter2.webp",
                stored_image_path="/tmp/filter2.webp",
                width=100,
                height=100,
                format="WEBP",
                mode="RGB",
                has_alpha=False,
                filename="filter2.webp",
                extension=".webp",
            )
            session.add_all([img1, img2])
            session.commit()
            return img1.id, img2.id

    def test_filter_returns_only_matching_images(
        self,
        test_repository: ImageRepository,
        two_images: tuple[int, int],
    ) -> None:
        """manual_rating_filter='PG' で PG 設定済み画像のみが返される。"""
        img1_id, _img2_id = two_images
        test_repository.update_manual_rating(img1_id, "PG")

        results, count = test_repository.get_images_by_filter(manual_rating_filter="PG")

        assert count == 1, f"PG の画像は 1 件のはずが {count} 件"
        assert len(results) == 1
        assert results[0]["id"] == img1_id

    def test_filter_returns_zero_when_no_match(
        self,
        test_repository: ImageRepository,
        two_images: tuple[int, int],
    ) -> None:
        """存在しない rating 値でフィルタすると 0 件が返される。"""
        img1_id, _img2_id = two_images
        test_repository.update_manual_rating(img1_id, "PG")

        results, count = test_repository.get_images_by_filter(manual_rating_filter="X")

        assert count == 0
        assert len(results) == 0
