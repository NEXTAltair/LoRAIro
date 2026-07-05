"""classify_manual_tag / register_user_tag のユニットテスト (Issue #1174)。

外部 tag_db (genai-tag-db-tools) はモジュール境界 (search_tags /
recommend_manual_refinement / TagRegisterService) でモックし、分類ロジックと
縮退挙動を検証する。
"""

from unittest.mock import MagicMock

import pytest
from genai_tag_db_tools.models import (
    RefinementReason,
    RefinementRecommendation,
    RefinementSuggestion,
    TagRecordPublic,
    TagSearchResult,
)

from lorairo.database.repository import annotation_record as ar_module
from lorairo.database.repository.annotation_record import AnnotationRepository


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> AnnotationRepository:
    repository = AnnotationRepository(session_factory=MagicMock())
    # 外部 tag_db reader は存在する体でモック (インスタンス属性 patch、クラス patch 不可)
    monkeypatch.setattr(repository, "_get_merged_reader", lambda: MagicMock())
    return repository


def _search_result(*items: TagRecordPublic) -> TagSearchResult:
    return TagSearchResult(items=list(items), total=len(items))


def _recommendation(code: str, suggestions: list[str]) -> RefinementRecommendation:
    return RefinementRecommendation(
        source_tag="input",
        normalized_tag="input",
        needs_refinement=True,
        score=1.0,
        reasons=[RefinementReason(code=code, message="test")],
        suggestions=[RefinementSuggestion(kind="correction_candidate", tag=s) for s in suggestions],
        proposals=[],
    )


@pytest.mark.unit
class TestClassifyManualTag:
    def test_exact_match_returns_tag_id(self, repo, monkeypatch):
        monkeypatch.setattr(
            ar_module,
            "search_tags",
            lambda reader, request: _search_result(TagRecordPublic(tag="cat", tag_id=10)),
        )
        result = repo.classify_manual_tag("cat")
        assert result.classification == "exact"
        assert result.canonical_tag == "cat"
        assert result.tag_id == 10

    def test_alias_resolves_to_preferred(self, repo, monkeypatch):
        # resolve_preferred=True の search は alias 入力に preferred 行を返す
        monkeypatch.setattr(
            ar_module,
            "search_tags",
            lambda reader, request: _search_result(TagRecordPublic(tag="preferred name", tag_id=42)),
        )
        result = repo.classify_manual_tag("old_alias")
        assert result.classification == "alias_resolved"
        assert result.canonical_tag == "preferred name"
        assert result.tag_id == 42

    def test_user_format_alias_resolved_after_danbooru_miss(self, repo, monkeypatch):
        """danbooru ミス後に Lorairo format で user 登録 alias を解決する (Codex P1 / #1173)。

        `tags alias` で user DB に確定した typo が、再実行時の分類で preferred へ
        解決されることを保証する (これが無いと alias 確定の導線が閉じない)。
        """

        def fake_search(reader, request):
            if request.format_names == ["danbooru"]:
                return _search_result()
            assert request.format_names == ["Lorairo"]
            return _search_result(TagRecordPublic(tag="european architecture", tag_id=88))

        monkeypatch.setattr(ar_module, "search_tags", fake_search)
        result = repo.classify_manual_tag("europian architecture")
        assert result.classification == "alias_resolved"
        assert result.canonical_tag == "european architecture"
        assert result.tag_id == 88

    def test_typo_candidate_surfaced_not_applied(self, repo, monkeypatch):
        monkeypatch.setattr(ar_module, "search_tags", lambda reader, request: _search_result())
        monkeypatch.setattr(
            ar_module,
            "recommend_manual_refinement",
            lambda tag, reader, format_name: _recommendation(
                "typo_alias_candidate", ["european architecture"]
            ),
        )
        result = repo.classify_manual_tag("europian architecture")
        assert result.classification == "typo_candidate"
        assert result.candidates == ["european architecture"]
        assert result.tag_id is None
        # 入力 verbatim を保存対象に維持 (自動置換しない)
        assert result.canonical_tag == "europian architecture"

    def test_ambiguous_candidates_surfaced(self, repo, monkeypatch):
        monkeypatch.setattr(ar_module, "search_tags", lambda reader, request: _search_result())
        monkeypatch.setattr(
            ar_module,
            "recommend_manual_refinement",
            lambda tag, reader, format_name: _recommendation(
                "ambiguous_alias_candidates", ["cand_a", "cand_b"]
            ),
        )
        result = repo.classify_manual_tag("ambig")
        assert result.classification == "ambiguous"
        assert result.candidates == ["cand_a", "cand_b"]

    def test_not_found_is_unregistered(self, repo, monkeypatch):
        monkeypatch.setattr(ar_module, "search_tags", lambda reader, request: _search_result())
        monkeypatch.setattr(
            ar_module,
            "recommend_manual_refinement",
            lambda tag, reader, format_name: None,
        )
        result = repo.classify_manual_tag("brand new tag")
        assert result.classification == "unregistered"
        assert result.tag_id is None

    def test_empty_normalization_is_invalid(self, repo):
        result = repo.classify_manual_tag("   ")
        assert result.classification == "invalid"
        assert result.normalized_tag == ""

    def test_reader_unavailable_degrades_to_unregistered(self, monkeypatch):
        repository = AnnotationRepository(session_factory=MagicMock())
        monkeypatch.setattr(repository, "_get_merged_reader", lambda: None)
        result = repository.classify_manual_tag("cat")
        assert result.classification == "unregistered"
        assert result.tag_id is None


@pytest.mark.unit
class TestRegisterUserTag:
    def test_registers_with_user_scope(self, repo):
        service = MagicMock()
        service.register_tag.return_value = MagicMock(tag_id=1234, created=True)
        repo.tag_register_service = service

        tag_id = repo.register_user_tag("brand_new_tag")

        assert tag_id == 1234
        request = service.register_tag.call_args[0][0]
        assert request.scope == "user"
        assert request.tag == "brand new tag"  # clean_format で underscore → space
        assert request.source_tag == "brand_new_tag"

    def test_empty_normalization_skips_registration(self, repo):
        service = MagicMock()
        repo.tag_register_service = service
        assert repo.register_user_tag("   ") is None
        service.register_tag.assert_not_called()

    def test_registration_failure_degrades_to_none(self, repo):
        service = MagicMock()
        service.register_tag.side_effect = ValueError("挿入後にタグ ID が見つかりませんでした。")
        repo.tag_register_service = service
        assert repo.register_user_tag("edge_tag") is None
