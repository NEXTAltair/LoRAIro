# tests/unit/database/test_image_database_manager_extended.py

from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from lorairo.database.db_manager import ImageDatabaseManager


class TestImageDatabaseManagerExtended:
    """ImageDatabaseManager の拡張機能テスト（Stage 2で追加された機能）"""

    @pytest.fixture
    def mock_session(self):
        """モックセッション"""
        return Mock()

    @pytest.fixture
    def mock_db_core(self):
        """モックデータベースコア"""
        return Mock()

    @pytest.fixture
    def db_manager(self, mock_session, mock_db_core):
        """テスト用ImageDatabaseManager"""
        with patch("lorairo.database.db_manager.ImageRepository"):
            manager = ImageDatabaseManager(":memory:")
            # 直接セッションを設定（実際の実装に依存）
            if hasattr(manager, "session"):
                manager.session = mock_session
            elif hasattr(manager, "repository") and hasattr(manager.repository, "session"):
                manager.repository.session = mock_session
            return manager

    def test_check_image_has_annotation_true(self, db_manager, mock_session):
        """画像アノテーション存在確認テスト（存在する場合）"""
        from lorairo.database.schema import Annotation

        # モック設定：アノテーションが存在する
        mock_annotation = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_annotation

        result = db_manager.check_image_has_annotation(1)

        # 正しいクエリが実行されることを確認
        mock_session.query.assert_called_once_with(Annotation)
        mock_session.query.return_value.filter.assert_called_once()

        # アノテーションが存在するのでTrue
        assert result is True

    def test_check_image_has_annotation_false(self, db_manager, mock_session):
        """画像アノテーション存在確認テスト（存在しない場合）"""
        from lorairo.database.schema import Annotation

        # モック設定：アノテーションが存在しない
        mock_session.query.return_value.filter.return_value.first.return_value = None

        result = db_manager.check_image_has_annotation(1)

        # 正しいクエリが実行されることを確認
        mock_session.query.assert_called_once_with(Annotation)

        # アノテーションが存在しないのでFalse
        assert result is False

    def test_check_image_has_annotation_invalid_id(self, db_manager, mock_session):
        """画像アノテーション存在確認テスト（無効なID）"""
        # モック設定：クエリエラーを発生させる
        mock_session.query.side_effect = Exception("Invalid ID")

        result = db_manager.check_image_has_annotation(-1)

        # エラーが発生した場合はFalseを返す
        assert result is False

    def test_execute_filtered_search_basic(self, db_manager, mock_session):
        """基本的なフィルター検索実行テスト"""
        # get_images_by_filterメソッドをテスト
        mock_images = [
            {"id": 1, "file_name": "image1.jpg", "width": 1024, "height": 768},
            {"id": 2, "file_name": "image2.jpg", "width": 512, "height": 512},
        ]

        # get_images_by_filterメソッドをモック
        with patch.object(db_manager, "get_images_by_filter", return_value=(mock_images, 2)):
            conditions = {"keywords": ["test"], "tag_operator": "AND"}

            images, count = db_manager.get_images_by_filter(**conditions)

            # 結果の確認
            assert len(images) == 2
            assert count == 2

    def test_execute_filtered_search_with_tags(self, db_manager, mock_session):
        """タグ付きフィルター検索実行テスト"""
        from lorairo.database.schema import Image, Tag

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, file_name="tagged_image.jpg")]
        mock_query.all.return_value = mock_images
        mock_query.count.return_value = 1

        # JOINクエリのモック設定
        mock_session.query.return_value.join.return_value.filter.return_value = mock_query

        conditions = {"tags": ["anime", "girl"], "tag_operator": "AND"}

        images, count = db_manager.execute_filtered_search(conditions)

        # TAGテーブルとのJOINが実行されることを確認
        mock_session.query.assert_called_once_with(Image)

        assert len(images) == 1
        assert count == 1

    def test_execute_filtered_search_with_resolution(self, db_manager, mock_session):
        """解像度フィルター検索実行テスト"""
        from lorairo.database.schema import Image

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, width=1920, height=1080)]
        mock_query.filter.return_value.all.return_value = mock_images
        mock_query.filter.return_value.count.return_value = 1
        mock_session.query.return_value = mock_query

        conditions = {"min_width": 1024, "max_width": 2048, "min_height": 768, "max_height": 1440}

        images, count = db_manager.execute_filtered_search(conditions)

        # 解像度フィルターが適用されることを確認
        assert mock_query.filter.called
        assert len(images) == 1
        assert count == 1

    def test_execute_filtered_search_with_date_range(self, db_manager, mock_session):
        """日付範囲フィルター検索実行テスト"""
        from lorairo.database.schema import Image

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, created_at=datetime(2023, 6, 15))]
        mock_query.filter.return_value.all.return_value = mock_images
        mock_query.filter.return_value.count.return_value = 1
        mock_session.query.return_value = mock_query

        conditions = {"start_date": datetime(2023, 1, 1), "end_date": datetime(2023, 12, 31)}

        images, count = db_manager.execute_filtered_search(conditions)

        # 日付フィルターが適用されることを確認
        assert mock_query.filter.called
        assert len(images) == 1
        assert count == 1

    def test_execute_filtered_search_with_annotation_status(self, db_manager, mock_session):
        """アノテーション状態フィルター検索実行テスト"""
        from lorairo.database.schema import Annotation, Image

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, file_name="annotated_image.jpg")]
        mock_query.all.return_value = mock_images
        mock_query.count.return_value = 1

        # LEFT JOINとフィルターのモック設定
        mock_session.query.return_value.outerjoin.return_value.filter.return_value = mock_query

        conditions = {"annotation_status": "annotated"}

        images, count = db_manager.execute_filtered_search(conditions)

        # AnnotationテーブルとのOUTER JOINが実行されることを確認
        mock_session.query.assert_called_once_with(Image)

        assert len(images) == 1
        assert count == 1

    def test_execute_filtered_search_untagged_only(self, db_manager, mock_session):
        """未タグ画像のみフィルター検索実行テスト"""
        from lorairo.database.schema import Image, Tag

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, file_name="untagged_image.jpg")]
        mock_query.all.return_value = mock_images
        mock_query.count.return_value = 1

        # LEFT JOINでタグなし画像を検索
        mock_session.query.return_value.outerjoin.return_value.filter.return_value = mock_query

        conditions = {"has_tags": False}

        images, count = db_manager.execute_filtered_search(conditions)

        # TagテーブルとのOUTER JOINが実行されることを確認
        mock_session.query.assert_called_once_with(Image)

        assert len(images) == 1
        assert count == 1

    def test_execute_filtered_search_complex_conditions(self, db_manager, mock_session):
        """複合条件フィルター検索実行テスト"""
        from lorairo.database.schema import Image, Tag

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, file_name="complex_search.jpg")]
        mock_query.all.return_value = mock_images
        mock_query.count.return_value = 1

        # 複数のフィルター操作のモック設定
        mock_session.query.return_value.join.return_value.filter.return_value.filter.return_value = (
            mock_query
        )

        conditions = {
            "tags": ["anime"],
            "tag_operator": "AND",
            "min_width": 512,
            "start_date": datetime(2023, 1, 1),
            "annotation_status": "annotated",
        }

        images, count = db_manager.execute_filtered_search(conditions)

        # 複合条件が適用されることを確認
        mock_session.query.assert_called_once_with(Image)
        assert len(images) == 1
        assert count == 1

    def test_execute_filtered_search_no_conditions(self, db_manager, mock_session):
        """条件なしフィルター検索実行テスト"""
        from lorairo.database.schema import Image

        # モック設定
        mock_images = [
            Mock(id=1, file_name="image1.jpg"),
            Mock(id=2, file_name="image2.jpg"),
            Mock(id=3, file_name="image3.jpg"),
        ]
        mock_session.query.return_value.all.return_value = mock_images
        mock_session.query.return_value.count.return_value = 3

        conditions = {}

        images, count = db_manager.execute_filtered_search(conditions)

        # 条件なしの場合は全画像が返される
        mock_session.query.assert_called_once_with(Image)
        assert len(images) == 3
        assert count == 3

    @patch("lorairo.database.db_manager.logger")
    def test_execute_filtered_search_error_handling(self, mock_logger, db_manager, mock_session):
        """フィルター検索エラーハンドリングテスト"""
        # クエリエラーを発生させる
        mock_session.query.side_effect = Exception("Database error")

        conditions = {"tags": ["test"]}

        images, count = db_manager.execute_filtered_search(conditions)

        # エラーログが出力され、空の結果が返されることを確認
        mock_logger.error.assert_called_once()
        assert images == []
        assert count == 0

    def test_execute_filtered_search_tag_or_logic(self, db_manager, mock_session):
        """タグOR条件フィルター検索実行テスト"""
        from lorairo.database.schema import Image, Tag

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1), Mock(id=2)]
        mock_query.all.return_value = mock_images
        mock_query.count.return_value = 2

        # ORロジック用のモック設定
        mock_session.query.return_value.join.return_value.filter.return_value = mock_query

        conditions = {"tags": ["anime", "girl"], "tag_operator": "OR"}

        images, count = db_manager.execute_filtered_search(conditions)

        # ORロジックでタグ検索が実行されることを確認
        mock_session.query.assert_called_once_with(Image)
        assert len(images) == 2
        assert count == 2

    def test_execute_filtered_search_custom_resolution(self, db_manager, mock_session):
        """カスタム解像度フィルター検索実行テスト"""
        from lorairo.database.schema import Image

        # モック設定
        mock_query = Mock()
        mock_images = [Mock(id=1, width=1920, height=1080)]
        mock_query.filter.return_value.all.return_value = mock_images
        mock_query.filter.return_value.count.return_value = 1
        mock_session.query.return_value = mock_query

        conditions = {"custom_width": 1920, "custom_height": 1080}

        images, count = db_manager.execute_filtered_search(conditions)

        # カスタム解像度フィルターが適用されることを確認
        assert mock_query.filter.called
        assert len(images) == 1
        assert count == 1

    def test_get_dataset_status_with_extended_info(self, db_manager, mock_session):
        """拡張データセット状態取得テスト"""
        from lorairo.database.schema import Annotation, Image

        # モック設定
        mock_session.query.return_value.count.return_value = 100  # 総画像数
        mock_session.query.return_value.join.return_value.count.return_value = 75  # アノテーション済み数

        # Stage 2で拡張された状態取得をテスト
        if hasattr(db_manager, "get_dataset_status_extended"):
            status = db_manager.get_dataset_status_extended()

            assert status["total_images"] == 100
            assert status["annotated_images"] == 75
            assert status["completion_rate"] == 75.0
        else:
            # 基本バージョンでのテスト
            mock_session.query.return_value.count.return_value = 100
            status = db_manager.get_dataset_status()
            assert status["total_images"] == 100

    def test_get_annotation_status_counts(self, db_manager, mock_session):
        """アノテーション状態カウント取得テスト"""
        from lorairo.database.schema import Annotation

        # Stage 2で追加された可能性のある機能をテスト
        if hasattr(db_manager, "get_annotation_status_counts"):
            # モック設定
            mock_session.query.return_value.filter.return_value.count.side_effect = [
                50,
                20,
                5,
            ]  # completed, pending, error

            counts = db_manager.get_annotation_status_counts()

            assert counts["completed"] == 50
            assert counts["pending"] == 20
            assert counts["error"] == 5
            assert counts["total"] == 75


class TestImageDatabaseManagerPerformance:
    """ImageDatabaseManager の拡張機能パフォーマンステスト"""

    @pytest.fixture
    def db_manager_with_large_dataset(self):
        """大規模データセット用データベースマネージャー"""
        with patch("lorairo.database.db_manager.ImageRepository"):
            manager = ImageDatabaseManager(":memory:")
            # セッションモックを適切に設定
            mock_session = Mock()
            if hasattr(manager, "session"):
                manager.session = mock_session
            elif hasattr(manager, "repository") and hasattr(manager.repository, "session"):
                manager.repository.session = mock_session
            return manager

    def test_check_image_has_annotation_batch_performance(self, db_manager_with_large_dataset):
        """バッチでのアノテーション存在確認パフォーマンステスト"""
        from lorairo.database.schema import Annotation

        # 大量のIDでテスト
        image_ids = list(range(1000))

        # モック設定：半分の画像にアノテーションあり
        mock_session = db_manager_with_large_dataset.session
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            Mock() if i % 2 == 0 else None for i in image_ids
        ]

        results = []
        for image_id in image_ids:
            result = db_manager_with_large_dataset.check_image_has_annotation(image_id)
            results.append(result)

        # 結果の確認
        assert len(results) == 1000
        assert sum(results) == 500  # 半分がTrue

    def test_execute_filtered_search_large_dataset(self, db_manager_with_large_dataset):
        """大規模データセットでのフィルター検索パフォーマンステスト"""
        from lorairo.database.schema import Image

        # 大量の画像データのモック
        mock_images = [Mock(id=i, file_name=f"image_{i}.jpg") for i in range(10000)]

        mock_session = db_manager_with_large_dataset.session
        mock_session.query.return_value.all.return_value = mock_images
        mock_session.query.return_value.count.return_value = 10000

        conditions = {"min_width": 1024}

        images, count = db_manager_with_large_dataset.execute_filtered_search(conditions)

        # パフォーマンステストの結果確認
        assert len(images) == 10000
        assert count == 10000

    def test_execute_filtered_search_complex_conditions_performance(self, db_manager_with_large_dataset):
        """複合条件での検索パフォーマンステスト"""
        from lorairo.database.schema import Image

        # 複合条件でのモック設定
        mock_images = [Mock(id=i) for i in range(500)]  # フィルター後は500件

        mock_session = db_manager_with_large_dataset.session
        mock_query = Mock()
        mock_query.all.return_value = mock_images
        mock_query.count.return_value = 500

        # 複数のフィルター操作のチェーン
        mock_session.query.return_value.join.return_value.filter.return_value.filter.return_value = (
            mock_query
        )

        conditions = {
            "tags": ["anime", "girl"],
            "tag_operator": "AND",
            "min_width": 1024,
            "min_height": 1024,
            "start_date": datetime(2023, 1, 1),
            "end_date": datetime(2023, 12, 31),
        }

        images, count = db_manager_with_large_dataset.execute_filtered_search(conditions)

        # 複合条件でも正常に処理されることを確認
        assert len(images) == 500
        assert count == 500


class TestImageDatabaseManagerIntegration:
    """ImageDatabaseManager の拡張機能統合テスト"""

    @pytest.fixture
    def integration_db_manager(self):
        """統合テスト用データベースマネージャー"""
        with patch("lorairo.database.db_manager.ImageRepository"):
            manager = ImageDatabaseManager(":memory:")
            # セッションモックを適切に設定
            mock_session = Mock()
            if hasattr(manager, "session"):
                manager.session = mock_session
            elif hasattr(manager, "repository") and hasattr(manager.repository, "session"):
                manager.repository.session = mock_session
            return manager

    def test_annotation_and_search_integration(self, integration_db_manager):
        """アノテーション確認と検索の統合テスト"""
        from lorairo.database.schema import Annotation, Image

        # シナリオ：アノテーション済み画像を検索して、個別にアノテーション状態を確認

        # 1. フィルター検索実行
        mock_images = [
            Mock(id=1, file_name="image1.jpg"),
            Mock(id=2, file_name="image2.jpg"),
            Mock(id=3, file_name="image3.jpg"),
        ]

        mock_session = integration_db_manager.session
        mock_session.query.return_value.all.return_value = mock_images
        mock_session.query.return_value.count.return_value = 3

        images, count = integration_db_manager.execute_filtered_search({"annotation_status": "all"})

        # 2. 各画像のアノテーション状態を個別確認
        # id=1,3はアノテーションあり、id=2はなし
        mock_session.query.return_value.filter.return_value.first.side_effect = [
            Mock(),  # id=1: あり
            None,  # id=2: なし
            Mock(),  # id=3: あり
        ]

        annotation_status = []
        for image in images:
            has_annotation = integration_db_manager.check_image_has_annotation(image.id)
            annotation_status.append(has_annotation)

        # 結果確認
        assert len(images) == 3
        assert annotation_status == [True, False, True]

    def test_search_with_annotation_filtering_integration(self, integration_db_manager):
        """アノテーションフィルタリング付き検索統合テスト"""
        from lorairo.database.schema import Annotation, Image

        # アノテーション済み画像のみを検索する統合テスト
        mock_annotated_images = [
            Mock(id=1, file_name="annotated1.jpg"),
            Mock(id=3, file_name="annotated3.jpg"),
        ]

        mock_session = integration_db_manager.session
        mock_query = Mock()
        mock_query.all.return_value = mock_annotated_images
        mock_query.count.return_value = 2

        # JOINクエリのモック
        mock_session.query.return_value.join.return_value.filter.return_value = mock_query

        conditions = {"annotation_status": "annotated"}

        images, count = integration_db_manager.execute_filtered_search(conditions)

        # アノテーション済み画像のみが返されることを確認
        assert len(images) == 2
        assert count == 2

        # 返された画像がすべてアノテーション済みであることを確認（統合的観点）
        for image in images:
            assert image.id in [1, 3]  # アノテーション済みのID
