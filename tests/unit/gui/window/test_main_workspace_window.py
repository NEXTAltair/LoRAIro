"""MainWorkspaceWindow ユニットテスト

責任分離後のMainWorkspaceWindowのビジネスロジックをテスト
- 最適パス決定処理の責任
- データベースアクセスロジック
- エラーハンドリング

Note: これらのテストはGUIコンポーネントを実際に作成せず、
ビジネスロジックのみをテストします。
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


class TestMainWorkspaceWindowPathResolution:
    """MainWorkspaceWindow パス解決ロジック テスト"""

    def test_resolve_optimal_thumbnail_data_with_512px_image(self) -> None:
        """512px画像が利用可能な場合の最適パス決定"""
        # GUI初期化をスキップしてメソッドのみテスト
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        # メソッドを直接取得
        resolve_method = MainWorkspaceWindow._resolve_optimal_thumbnail_data

        # モックオブジェクト作成
        mock_self = Mock()
        mock_db = Mock()
        mock_self.db_manager = mock_db

        # テスト用画像メタデータ
        image_metadata = [
            {"id": 101, "stored_image_path": "/original/image1.jpg"},
            {"id": 102, "stored_image_path": "/original/image2.jpg"},
        ]

        # 512px画像が存在する場合のモック設定
        def mock_check_processed(image_id: int, size: int) -> dict[str, str] | None:
            if image_id == 101 and size == 512:
                return {"stored_image_path": "/processed/512/image1.jpg"}
            return None

        mock_db.check_processed_image_exists.side_effect = mock_check_processed

        # resolve_stored_pathのモック
        with patch("lorairo.database.db_core.resolve_stored_path") as mock_resolve:
            mock_resolve.side_effect = lambda path: Path(path)

            # Path.exists()のモック
            with patch.object(Path, "exists", return_value=True):
                result = resolve_method(mock_self, image_metadata)

        # 結果の検証
        assert len(result) == 2
        assert result[0] == (Path("/processed/512/image1.jpg"), 101)  # 512px画像を使用
        assert result[1] == (Path("/original/image2.jpg"), 102)  # 元画像を使用

    def test_resolve_optimal_thumbnail_data_fallback_to_original(self) -> None:
        """512px画像が存在しない場合の元画像フォールバック"""
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        resolve_method = MainWorkspaceWindow._resolve_optimal_thumbnail_data

        mock_self = Mock()
        mock_db = Mock()
        mock_self.db_manager = mock_db

        # テスト用画像メタデータ
        image_metadata = [{"id": 201, "stored_image_path": "/original/image1.jpg"}]

        # 512px画像が存在しない場合
        mock_db.check_processed_image_exists.return_value = None

        result = resolve_method(mock_self, image_metadata)

        # 元画像にフォールバックすることを確認
        assert len(result) == 1
        assert result[0] == (Path("/original/image1.jpg"), 201)

    def test_resolve_optimal_thumbnail_data_error_handling(self) -> None:
        """パス解決エラー時のハンドリング"""
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        resolve_method = MainWorkspaceWindow._resolve_optimal_thumbnail_data

        mock_self = Mock()
        mock_db = Mock()
        mock_self.db_manager = mock_db

        # テスト用画像メタデータ
        image_metadata = [{"id": 301, "stored_image_path": "/original/image1.jpg"}]

        # データベースアクセスでエラーが発生
        mock_db.check_processed_image_exists.side_effect = Exception("DB Error")

        result = resolve_method(mock_self, image_metadata)

        # エラーが発生しても元画像にフォールバックすること
        assert len(result) == 1
        assert result[0] == (Path("/original/image1.jpg"), 301)

    def test_resolve_optimal_thumbnail_data_empty_metadata(self) -> None:
        """空のメタデータの処理"""
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        resolve_method = MainWorkspaceWindow._resolve_optimal_thumbnail_data

        mock_self = Mock()
        mock_db = Mock()
        mock_self.db_manager = mock_db

        result = resolve_method(mock_self, [])

        assert result == []

    def test_resolve_optimal_thumbnail_data_no_database_manager(self) -> None:
        """データベースマネージャーがない場合の処理"""
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        resolve_method = MainWorkspaceWindow._resolve_optimal_thumbnail_data

        mock_self = Mock()
        mock_self.db_manager = None

        image_metadata = [{"id": 401, "stored_image_path": "/original/image1.jpg"}]

        result = resolve_method(mock_self, image_metadata)

        # データベースマネージャーがない場合は元画像を使用
        assert len(result) == 1
        assert result[0] == (Path("/original/image1.jpg"), 401)


class TestMainWorkspaceWindowResponsibilityBoundaries:
    """MainWorkspaceWindow 責任境界テスト"""

    def test_has_path_resolution_method(self) -> None:
        """パス解決メソッドが存在することを確認"""
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        # メソッドが存在することを確認
        assert hasattr(MainWorkspaceWindow, "_resolve_optimal_thumbnail_data")
        assert callable(MainWorkspaceWindow._resolve_optimal_thumbnail_data)

    def test_path_resolution_method_signature(self) -> None:
        """パス解決メソッドのシグネチャ確認"""
        import inspect

        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        method = MainWorkspaceWindow._resolve_optimal_thumbnail_data
        signature = inspect.signature(method)

        # 期待するパラメータが存在することを確認
        params = list(signature.parameters.keys())
        assert "self" in params
        assert "image_metadata" in params


class TestMainWorkspaceWindowBusinessLogic:
    """MainWorkspaceWindow ビジネスロジック テスト"""

    def test_optimal_path_selection_logic(self) -> None:
        """最適パス選択ロジックのテスト"""
        from lorairo.gui.window.main_workspace_window import MainWorkspaceWindow

        resolve_method = MainWorkspaceWindow._resolve_optimal_thumbnail_data

        mock_self = Mock()
        mock_db = Mock()
        mock_self.db_manager = mock_db

        # 複数の画像でそれぞれ異なる最適化が適用される場合
        image_metadata = [
            {"id": 1, "stored_image_path": "/original/image1.jpg"},  # 512px利用可能
            {"id": 2, "stored_image_path": "/original/image2.jpg"},  # 512px利用不可
            {"id": 3, "stored_image_path": "/original/image3.jpg"},  # 512px存在するがファイルなし
        ]

        def mock_check_processed(image_id: int, size: int) -> dict[str, str] | None:
            if image_id == 1 and size == 512:
                return {"stored_image_path": "/processed/512/image1.jpg"}
            elif image_id == 3 and size == 512:
                return {"stored_image_path": "/processed/512/image3.jpg"}
            return None

        mock_db.check_processed_image_exists.side_effect = mock_check_processed

        with patch("lorairo.database.db_core.resolve_stored_path") as mock_resolve:
            mock_resolve.side_effect = lambda path: Path(path)

            def mock_exists(self: Path) -> bool:
                # image1の512px版は存在、image3の512px版は存在しない
                return str(self) == "/processed/512/image1.jpg"

            with patch.object(Path, "exists", mock_exists):
                result = resolve_method(mock_self, image_metadata)

        # 結果の検証
        assert len(result) == 3
        assert result[0] == (Path("/processed/512/image1.jpg"), 1)  # 512px利用
        assert result[1] == (Path("/original/image2.jpg"), 2)  # 元画像利用
        assert result[2] == (Path("/original/image3.jpg"), 3)  # フォールバック


if __name__ == "__main__":
    pytest.main([__file__])
