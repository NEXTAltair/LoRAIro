"""
プロジェクトディレクトリ生成と管理の統合テスト
db_core.py の変更をテストする
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from lorairo.database.db_core import get_project_dir, sanitize_project_name


class TestProjectDirectoryIntegration:
    """プロジェクトディレクトリ管理の統合テスト"""

    def test_project_directory_creation_with_unicode_names(self):
        """Unicode対応プロジェクト名でのディレクトリ作成"""
        test_cases = [
            "main_dataset",
            "猫画像コレクション",
            "NSFW_データセット",
            "test_プロジェクト_123",
            "データ分析用",
        ]

        for project_name in test_cases:
            with tempfile.TemporaryDirectory() as tmp_dir:
                base_dir = Path(tmp_dir)

                # プロジェクトディレクトリ生成
                project_dir = get_project_dir(str(base_dir), project_name)

                # ディレクトリが作成されること
                assert project_dir.exists()
                assert project_dir.is_dir()

                # 親ディレクトリが正しいこと
                assert project_dir.parent == base_dir

                # ディレクトリ名が期待される形式であること（safe_name_YYYYMMDD_NNN）
                dir_name = project_dir.name
                parts = dir_name.split("_")
                assert len(parts) >= 3

                # 日付部分が今日の日付であること
                today = datetime.now().strftime("%Y%m%d")
                assert today in dir_name

                # 連番部分が3桁の数字であること
                assert parts[-1].isdigit()
                assert len(parts[-1]) == 3

    def test_project_directory_auto_increment(self):
        """同一日の連番自動生成テスト"""
        project_name = "test_project"

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)

            # 複数のプロジェクトディレクトリを作成
            dirs = []
            for i in range(3):
                project_dir = get_project_dir(str(base_dir), project_name)
                dirs.append(project_dir)

                # 各ディレクトリが作成されること
                assert project_dir.exists()

            # 連番が正しく増加すること
            dir_names = [d.name for d in dirs]
            today = datetime.now().strftime("%Y%m%d")

            expected_patterns = [
                f"test_project_{today}_001",
                f"test_project_{today}_002",
                f"test_project_{today}_003",
            ]

            for expected, actual in zip(expected_patterns, dir_names, strict=False):
                assert actual == expected

    def test_filesystem_safe_name_conversion(self):
        """ファイルシステム安全な名前変換テスト"""
        test_cases = [
            # (入力, 期待される結果の特徴)
            ("normal_name", "normal_name"),
            ("project<test>", "project_test_"),
            ("data/analysis", "data_analysis"),
            ("file:name", "file_name"),
            ('project"name', "project_name"),
            ("data\\backup", "data_backup"),
            ("project|test", "project_test"),
            ("file?name", "file_name"),
            ("data*set", "data_set"),
        ]

        for input_name, expected_safe in test_cases:
            result = sanitize_project_name(input_name)

            # 無効文字が除去されていること
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                assert char not in result

            # 空文字列にならないこと
            assert len(result) > 0

    def test_existing_directory_detection(self):
        """既存ディレクトリ検知と連番生成テスト"""
        project_name = "existing_test"

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            today = datetime.now().strftime("%Y%m%d")

            # 既存のプロジェクトディレクトリを手動作成
            existing_dirs = [
                base_dir / f"existing_test_{today}_001",
                base_dir / f"existing_test_{today}_003",  # 002をスキップ
                base_dir / f"existing_test_{today}_005",
            ]

            for existing_dir in existing_dirs:
                existing_dir.mkdir()

            # 新しいプロジェクトディレクトリを作成
            new_project_dir = get_project_dir(str(base_dir), project_name)

            # 最大番号+1の連番が使用されること
            expected_name = f"existing_test_{today}_006"
            assert new_project_dir.name == expected_name
            assert new_project_dir.exists()

    def test_project_directory_structure_integration(self):
        """プロジェクトディレクトリ構造と設定の統合テスト"""
        project_name = "structure_test"

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)

            # プロジェクトディレクトリ作成
            project_dir = get_project_dir(str(base_dir), project_name)

            # 期待されるサブディレクトリを作成
            image_dataset_dir = project_dir / "image_dataset"
            image_dataset_dir.mkdir()

            original_images_dir = image_dataset_dir / "original_images"
            original_images_dir.mkdir()

            # データベースファイルを作成
            db_file = project_dir / "image_database.db"
            db_file.touch()

            # 構造が正しいことを確認
            assert project_dir.exists()
            assert image_dataset_dir.exists()
            assert original_images_dir.exists()
            assert db_file.exists()

            # 相対パス解決のテスト
            relative_path = "image_dataset/original_images/test.jpg"
            absolute_path = project_dir / relative_path
            expected_parent = original_images_dir
            assert absolute_path.parent == expected_parent

    def test_cross_platform_directory_creation(self):
        """クロスプラットフォーム対応のディレクトリ作成テスト"""
        # Unicode文字とパス区切り文字を含むプロジェクト名
        problematic_names = [
            "データ/セット",  # Unix パス区切り
            "データ\\セット",  # Windows パス区切り
            "プロジェクト:テスト",  # Windowsで無効
            "ファイル<名前>",  # 角括弧
            'データ"テスト"',  # 引用符
        ]

        for project_name in problematic_names:
            with tempfile.TemporaryDirectory() as tmp_dir:
                base_dir = Path(tmp_dir)

                # ディレクトリ作成が成功すること
                project_dir = get_project_dir(str(base_dir), project_name)
                assert project_dir.exists()

                # 作成されたディレクトリ名が安全であること
                dir_name = project_dir.name
                invalid_chars = '<>:"/\\|?*'
                for char in invalid_chars:
                    assert char not in dir_name

    def test_long_project_name_handling(self):
        """長いプロジェクト名の処理テスト"""
        # 比較的長いプロジェクト名（ファイルシステム制限を考慮）
        long_name = "長いプロジェクト名_テスト用_データセット_分析用"  # 適度な長さ

        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)

            # 長い名前でもディレクトリ作成が成功すること
            project_dir = get_project_dir(str(base_dir), long_name)
            assert project_dir.exists()

            # ディレクトリ名が適切な長さに収まること（OSの制限内）
            dir_name = project_dir.name
            # 大部分のファイルシステムで255文字制限
            assert len(dir_name.encode("utf-8")) <= 255

            # 非常に長すぎる名前の場合はエラーが発生することを確認
            very_long_name = "非常に長いプロジェクト名" * 20  # 意図的に長すぎる名前
            try:
                get_project_dir(str(base_dir), very_long_name)
                # 上記でエラーが発生しなかった場合は失敗
                assert False, "非常に長い名前でエラーが発生しませんでした"
            except OSError:
                # ファイルシステム制限によるエラーは期待される動作
                pass

    def test_special_character_edge_cases(self):
        """特殊文字のエッジケースのテスト"""
        edge_cases = [
            "",  # 空文字列
            "   ",  # 空白のみ
            ".",  # ドット
            "..",  # 親ディレクトリ参照
            "CON",  # Windowsの予約語
            "PRN",  # Windowsの予約語
            "AUX",  # Windowsの予約語
        ]

        for project_name in edge_cases:
            with tempfile.TemporaryDirectory() as tmp_dir:
                base_dir = Path(tmp_dir)

                # エラーなくディレクトリが作成されること
                project_dir = get_project_dir(str(base_dir), project_name)
                assert project_dir.exists()

                # 有効なディレクトリ名になること
                dir_name = project_dir.name
                assert len(dir_name) > 0
                assert dir_name not in [".", ".."]
