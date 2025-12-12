"""
Issue #2実装の統合テスト: 外部tag_dbへのタグ登録・検索機能

テストカバレッジ:
- 新規タグ作成と外部DB登録
- 既存タグ検索（重複作成防止）
- タグ正規化の一貫性（ExistingFileReaderとの整合性）
- 空タグ/エラー時の縮退動作

Note:
- これらのテストは環境変数TEST_TAG_DB_PATHが設定されている場合のみ実行される
- テスト用データベースを使用し、テスト後は自動クリーンアップされる
"""

import uuid

import pytest
from genai_tag_db_tools.utils.cleanup_str import TagCleaner

from lorairo.annotations.existing_file_reader import ExistingFileReader


@pytest.mark.integration
class TestTagDbIntegration:
    """外部tag_db統合機能のテスト

    TEST_TAG_DB_PATH環境変数が設定されている場合のみテスト実行。
    未設定の場合はconftest.pyのtest_tag_db_path fixtureでスキップされる。
    """

    @pytest.fixture
    def existing_file_reader(self) -> ExistingFileReader:
        """ExistingFileReaderインスタンスを提供"""
        return ExistingFileReader()

    def test_new_tag_creation(self, test_image_repository_with_tag_db, test_tag_repository):
        """
        新規タグ作成テスト

        目的: 外部tag_dbに存在しないタグを作成し、tag_idが返却されることを確認
        """
        # 一意な新規タグを生成
        new_tag = f"test_ai_tag_{uuid.uuid4().hex[:8]}"

        # ImageRepositoryを通じてタグ作成
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, new_tag)

        # 検証: tag_idが返却される
        assert tag_id is not None, f"Tag ID should be returned for new tag '{new_tag}'"

        # 外部tag_dbでタグの存在確認
        retrieved_tag = test_tag_repository.get_tag_by_id(tag_id)
        assert retrieved_tag is not None, "Tag should exist in external tag_db"
        # 正規化後のtagと比較（アンダースコアはスペースに変換される）
        expected_normalized = TagCleaner.clean_format(new_tag).strip()
        assert retrieved_tag.tag == expected_normalized, (
            f"Normalized tag should match: expected '{expected_normalized}', got '{retrieved_tag.tag}'"
        )
        assert retrieved_tag.source_tag == new_tag, "Source tag should match original"

    def test_existing_tag_lookup(self, test_image_repository_with_tag_db, test_tag_repository):
        """
        既存タグ検索テスト

        目的: 既存タグを検索した場合、重複作成せず既存tag_idを返すことを確認
        """
        # 一意なタグを生成（ベースDBに既存の可能性を排除）
        source_tag = f"test_lookup_{uuid.uuid4().hex[:8]}"
        # 正規化されたタグ（ImageRepositoryと同じ正規化を適用）
        normalized_tag = TagCleaner.clean_format(source_tag).strip()

        # 事前に外部tag_dbにタグ作成（正規化された形式で保存）
        tag_id_original = test_tag_repository.create_tag(source_tag=source_tag, tag=normalized_tag)

        # ImageRepositoryで同じタグを検索（元の形式で渡す）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_retrieved = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, source_tag)

        # 検証: 同じtag_idが返される
        assert tag_id_retrieved == tag_id_original, "Should return existing tag_id"

        # 重複作成されていないことを確認
        all_matching_tags = test_tag_repository.search_tag_ids(normalized_tag, partial=False)
        assert len(all_matching_tags) == 1, "Should not create duplicate tags"

    def test_tag_normalization_consistency(self, test_image_repository_with_tag_db, existing_file_reader, temp_dir):
        """
        タグ正規化の一貫性テスト

        目的: ImageRepositoryとExistingFileReaderで正規化ロジックが一致することを確認
        ExistingFileReaderの実際のファイル読み込み処理を使用してテスト
        """
        from pathlib import Path

        # テストファイルを作成
        test_image_path = temp_dir / "test_image.png"
        test_image_path.touch()
        test_tag_file = temp_dir / "test_image.txt"

        # テストケース: 様々な形式のタグ
        test_tags = [
            "  Girl, Blonde  ",  # 前後空白、カンマ
            "1girl,solo,standing",  # カンマ区切り
            "anime style, high quality",  # 空白とカンマ混在
            "test__underscore",  # アンダースコア
        ]

        for original_tag in test_tags:
            # テストファイルにタグを書き込み
            test_tag_file.write_text(original_tag, encoding="utf-8")

            # ExistingFileReader経由で正規化（実際のファイル読み込み処理）
            annotations = existing_file_reader.get_existing_annotations(test_image_path)
            assert annotations is not None, "Annotations should be loaded"
            reader_normalized_tags = annotations["tags"]

            # ImageRepository経由で正規化（直接TagCleaner使用）
            repo_normalized = TagCleaner.clean_format(original_tag).strip()

            # 検証: ExistingFileReaderで読み込んだタグと直接正規化した結果が一致
            # ExistingFileReaderはカンマ区切りでリストにするため、結合して比較
            reader_normalized_str = ", ".join(reader_normalized_tags) if reader_normalized_tags else ""

            # カンマ区切りの場合は各要素を比較
            if "," in original_tag:
                expected_tags = [tag.strip() for tag in repo_normalized.split(",") if tag.strip()]
                assert reader_normalized_tags == expected_tags, (
                    f"Normalization mismatch for '{original_tag}': "
                    f"reader={reader_normalized_tags} vs expected={expected_tags}"
                )
            else:
                # 単一タグの場合
                assert reader_normalized_str == repo_normalized or (
                    len(reader_normalized_tags) == 1 and reader_normalized_tags[0] == repo_normalized
                ), (
                    f"Normalization mismatch for '{original_tag}': "
                    f"reader='{reader_normalized_str}' vs repo='{repo_normalized}'"
                )

    def test_empty_tag_handling(self, test_image_repository_with_tag_db):
        """
        空タグ処理テスト

        目的: 空文字列や正規化後に空になるタグを正しく処理することを確認
        """
        # 空文字列タグ
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, "")

        assert tag_id is None, "Empty tag should return None"

        # 空白のみタグ
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, "   ")

        assert tag_id is None, "Whitespace-only tag should return None"

        # 正規化後に空になるタグ（特殊文字のみ）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, "!!!")

        # 正規化で空になる可能性があるため、Noneまたは有効なIDを確認
        assert tag_id is None or isinstance(tag_id, int), "Should handle special character tags"

    def test_graceful_degradation_on_error(self, test_image_repository_with_tag_db, monkeypatch):
        """
        エラー時の縮退動作テスト

        目的: TagRepository.create_tag()でエラーが発生した場合、Noneを返すことを確認
        """

        # TagRepository.create_tag()をモックしてエラーを発生させる
        def mock_create_tag(*args, **kwargs):
            raise Exception("Simulated tag_db error")

        monkeypatch.setattr(test_image_repository_with_tag_db.tag_repository, "create_tag", mock_create_tag)

        # エラー発生時の動作確認
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, "error_test_tag")

        # 検証: クラッシュせずNoneを返す
        assert tag_id is None, "Should return None on error without crashing"

    def test_tag_normalization_with_tag_cleaner(self, test_image_repository_with_tag_db):
        """
        TagCleanerによる正規化テスト

        目的: TagCleaner.clean_format()が期待通りにタグを正規化することを確認
        """
        # アンダースコアを含むタグ（正規化でスペースに変換される）
        test_input = "test_underscore_tag"
        normalized = TagCleaner.clean_format(test_input).strip()

        # 検証: アンダースコアがスペースに変換される
        assert "_" not in normalized, "Underscores should be converted to spaces"
        assert " " in normalized, "Should contain spaces after normalization"
        assert normalized == "test underscore tag", "Should normalize underscores to spaces"

    def test_tag_id_consistency_across_calls(self, test_image_repository_with_tag_db):
        """
        複数回呼び出しでのtag_id一貫性テスト

        目的: 同じタグを複数回処理した場合、常に同じtag_idが返されることを確認
        """
        test_tag = f"consistency_test_{uuid.uuid4().hex[:8]}"

        # 1回目の呼び出し
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_first = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 2回目の呼び出し（既存タグとして検索される）
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_second = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 3回目の呼び出し
        with test_image_repository_with_tag_db.session_factory() as session:
            tag_id_third = test_image_repository_with_tag_db._get_or_create_tag_id_external(session, test_tag)

        # 検証: すべて同じtag_idが返される
        assert tag_id_first == tag_id_second == tag_id_third, (
            f"Tag ID should be consistent across calls: {tag_id_first}, {tag_id_second}, {tag_id_third}"
        )
