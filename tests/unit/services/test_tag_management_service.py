"""TagManagementService の単体テスト"""

from unittest.mock import patch

import pytest
from genai_tag_db_tools.models import (
    RefinementReason,
    RefinementRecommendation,
    RefinementSuggestion,
    TagRecordPublic,
    TagSearchResult,
    TagTypeUpdate,
)
from sqlalchemy.exc import OperationalError

from lorairo.services.tag_management_service import TagManagementService


def _recommendation(
    tag: str,
    *,
    needs: bool = True,
    reason_codes: list[str] | None = None,
    suggestion_tag: str | None = None,
    score: float = 0.5,
) -> RefinementRecommendation:
    """テスト用 RefinementRecommendation を組み立てる。"""
    reasons = [
        RefinementReason(code=code, message=f"{code} message")  # type: ignore[arg-type]
        for code in (reason_codes or [])
    ]
    suggestions = (
        [RefinementSuggestion(kind="correction_candidate", tag=suggestion_tag)]
        if suggestion_tag is not None
        else []
    )
    return RefinementRecommendation(
        source_tag=tag,
        normalized_tag=tag,
        needs_refinement=needs,
        score=score,
        reasons=reasons,
        suggestions=suggestions,
        proposals=[],
    )


def _search_result_with_translations(tag: str, translations: dict[str, list[str]]) -> TagSearchResult:
    """指定タグ・翻訳を持つ TagSearchResult を組み立てる。"""
    return TagSearchResult(
        items=[
            TagRecordPublic(
                tag=tag,
                tag_id=1,
                source_tag=tag,
                type_name="general",
                format_name="Lorairo",
                translations=translations,
            )
        ],
        total=1,
    )


@pytest.mark.unit
class TestTagManagementService:
    """TagManagementService のテストクラス"""

    @pytest.fixture
    def service(self) -> TagManagementService:
        """TagManagementService インスタンスを提供"""
        with patch("lorairo.services.tag_management_service.get_tag_reader"):
            with patch("lorairo.services.tag_management_service.get_user_repository"):
                return TagManagementService()

    def test_lorairo_format_id_constant(self, service: TagManagementService) -> None:
        """LoRAIro format_id が 1000 であることを確認"""
        assert service.LORAIRO_FORMAT_ID == 1000

    def test_get_unknown_tags_success(self, service: TagManagementService) -> None:
        """unknown typeタグ取得成功"""
        mock_tags = [
            TagRecordPublic(
                tag="test_tag1",
                tag_id=1,
                source_tag="test_tag1",
                type_name="unknown",
                format_name="Lorairo",
            ),
            TagRecordPublic(
                tag="test_tag2",
                tag_id=2,
                source_tag="test_tag2",
                type_name="unknown",
                format_name="Lorairo",
            ),
        ]

        with patch("lorairo.services.tag_management_service.get_unknown_type_tags", return_value=mock_tags):
            result = service.get_unknown_tags()

            assert len(result) == 2
            assert result[0].tag_id == 1
            assert result[1].tag_id == 2
            assert all(tag.type_name == "unknown" for tag in result)

    def test_get_unknown_tags_empty(self, service: TagManagementService) -> None:
        """unknown typeタグが存在しない場合"""
        with patch("lorairo.services.tag_management_service.get_unknown_type_tags", return_value=[]):
            result = service.get_unknown_tags()
            assert result == []

    def test_get_unknown_tags_error(self, service: TagManagementService) -> None:
        """unknown typeタグ取得時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.get_unknown_type_tags",
            side_effect=Exception("DB error"),
        ):
            with pytest.raises(Exception, match="DB error"):
                service.get_unknown_tags()

    def test_get_all_available_types_success(self, service: TagManagementService) -> None:
        """全type_name取得成功"""
        mock_types = ["character", "general", "meta", "unknown"]

        with patch("lorairo.services.tag_management_service.get_all_type_names", return_value=mock_types):
            result = service.get_all_available_types()

            assert result == mock_types
            assert "unknown" in result
            assert "character" in result

    def test_get_all_available_types_error(self, service: TagManagementService) -> None:
        """全type_name取得時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.get_all_type_names",
            side_effect=Exception("API error"),
        ):
            with pytest.raises(Exception, match="API error"):
                service.get_all_available_types()

    def test_get_format_specific_types_success(self, service: TagManagementService) -> None:
        """format固有type_name取得成功"""
        mock_types = ["unknown", "character", "general"]

        with patch(
            "lorairo.services.tag_management_service.get_format_type_names", return_value=mock_types
        ):
            result = service.get_format_specific_types()

            assert result == mock_types
            assert len(result) == 3

    def test_get_format_specific_types_error(self, service: TagManagementService) -> None:
        """format固有type_name取得時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.get_format_type_names",
            side_effect=Exception("Format error"),
        ):
            with pytest.raises(Exception, match="Format error"):
                service.get_format_specific_types()

    def test_update_tag_types_success(self, service: TagManagementService) -> None:
        """タグtype一括更新成功"""
        updates = [
            TagTypeUpdate(tag_id=1, type_name="character"),
            TagTypeUpdate(tag_id=2, type_name="general"),
        ]

        with patch("lorairo.services.tag_management_service.update_tags_type_batch") as mock_update:
            service.update_tag_types(updates)

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[0][1] == updates  # updates リスト
            assert call_args[1]["format_id"] == 1000  # format_id

    def test_update_tag_types_empty_list(self, service: TagManagementService) -> None:
        """空のupdatesリストの処理"""
        with patch("lorairo.services.tag_management_service.update_tags_type_batch") as mock_update:
            service.update_tag_types([])

            # 空リストの場合は API 呼び出ししない
            mock_update.assert_not_called()

    def test_update_tag_types_value_error(self, service: TagManagementService) -> None:
        """無効なupdatesでValueError"""
        updates = [TagTypeUpdate(tag_id=999, type_name="invalid")]

        with patch(
            "lorairo.services.tag_management_service.update_tags_type_batch",
            side_effect=ValueError("Invalid format_id"),
        ):
            with pytest.raises(ValueError, match="Invalid format_id"):
                service.update_tag_types(updates)

    def test_update_tag_types_error(self, service: TagManagementService) -> None:
        """タグtype更新時のエラーハンドリング"""
        updates = [TagTypeUpdate(tag_id=1, type_name="character")]

        with patch(
            "lorairo.services.tag_management_service.update_tags_type_batch",
            side_effect=Exception("Update error"),
        ):
            with pytest.raises(Exception, match="Update error"):
                service.update_tag_types(updates)

    def test_update_single_tag_type_success(self, service: TagManagementService) -> None:
        """単一タグtype更新成功"""
        with patch("lorairo.services.tag_management_service.update_tags_type_batch") as mock_update:
            service.update_single_tag_type(tag_id=1, type_name="character")

            mock_update.assert_called_once()
            call_args = mock_update.call_args
            updates = call_args[0][1]
            assert len(updates) == 1
            assert updates[0].tag_id == 1
            assert updates[0].type_name == "character"
            assert call_args[1]["format_id"] == 1000

    def test_update_single_tag_type_error(self, service: TagManagementService) -> None:
        """単一タグtype更新時のエラーハンドリング"""
        with patch(
            "lorairo.services.tag_management_service.update_tags_type_batch",
            side_effect=ValueError("Invalid tag_id"),
        ):
            with pytest.raises(ValueError, match="Invalid tag_id"):
                service.update_single_tag_type(tag_id=999, type_name="invalid")


@pytest.mark.unit
class TestTranslationQualityIntegration:
    """recommend_with_translation_quality の統合ロジックのテスト (#976)。"""

    @pytest.fixture
    def service(self) -> TagManagementService:
        """TagManagementService インスタンスを提供"""
        with patch("lorairo.services.tag_management_service.get_tag_reader"):
            with patch("lorairo.services.tag_management_service.get_user_repository"):
                return TagManagementService()

    def test_merges_translation_reason_into_clean_manual(self, service: TagManagementService) -> None:
        """manual に問題が無くても ja 翻訳候補の問題を ⚠ 対象へ合流する。"""
        manual = _recommendation("blue_eyes", needs=False, score=0.0)
        translation = _recommendation("blue_eyes", reason_codes=["overlong_translation"], score=0.6)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("blue_eyes", {"ja": ["とても長い翻訳文"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=translation,
            ),
        ):
            result = service.recommend_with_translation_quality("blue_eyes")

        assert result.needs_refinement is True
        assert {r.code for r in result.reasons} == {"overlong_translation"}
        assert result.score == 0.6

    def test_combines_manual_and_translation_reasons(self, service: TagManagementService) -> None:
        """manual reason と (実データ経路の) 翻訳品質 reason を両方保持する。"""
        manual = _recommendation("blue__eyes", reason_codes=["normalization_changes_tag"], score=0.7)
        # 実在タグ (完全一致行) だが ja 翻訳が未登録 → 実 recommend_translation_quality で
        # missing_translation が発火する (モックせず実データ経路を検証)。
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("blue__eyes", {}),
            ),
        ):
            result = service.recommend_with_translation_quality("blue__eyes")

        assert {r.code for r in result.reasons} == {"normalization_changes_tag", "missing_translation"}
        assert result.score == 1.0  # missing_translation の weight 1.0 が最大

    def test_dedups_translation_reason_codes_across_candidates(self, service: TagManagementService) -> None:
        """複数 ja 候補が同じ reason を出しても tooltip 用 reason は1つに重複排除する。"""
        manual = _recommendation("tag", needs=False, score=0.0)
        flagged = _recommendation("tag", reason_codes=["overlong_translation"], score=0.6)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("tag", {"ja": ["候補A", "候補B"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=flagged,
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        codes = [r.code for r in result.reasons]
        assert codes == ["overlong_translation"]

    def test_evaluates_all_ja_candidates(self, service: TagManagementService) -> None:
        """ja の全候補を recommend_translation_quality に渡して評価する。"""
        manual = _recommendation("tag", needs=False, score=0.0)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("tag", {"ja": ["c1", "c2", "c3"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=_recommendation("tag", needs=False, score=0.0),
            ) as mock_eval,
        ):
            service.recommend_with_translation_quality("tag")

        evaluated = [call.kwargs["translation"] for call in mock_eval.call_args_list]
        assert evaluated == ["c1", "c2", "c3"]
        assert all(call.kwargs["language"] == "ja" for call in mock_eval.call_args_list)

    def test_clean_translation_returns_manual_unchanged(self, service: TagManagementService) -> None:
        """全 ja 候補が問題無しなら manual の結果をそのまま返す。"""
        manual = _recommendation("tag", needs=False, score=0.0)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("tag", {"ja": ["きれいな翻訳"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=_recommendation("tag", needs=False, score=0.0),
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result is manual

    def test_exact_match_without_ja_fires_missing(self, service: TagManagementService) -> None:
        """実在タグ (完全一致行あり) で ja 翻訳が未登録/空なら missing_translation を発火する。

        search_tags の projection は空翻訳を除外する
        (repository._build... の `if translation.language and translation.translation`) ため、
        ja キーが無い行でも実データ経路で missing が発火することを実
        recommend_translation_quality で検証する (モックで隠さない)。
        """
        manual = _recommendation("tag", needs=False, score=0.0)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("tag", {"en": ["tag"]}),
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result.needs_refinement is True
        assert {r.code for r in result.reasons} == {"missing_translation"}

    def test_non_exact_match_row_translations_not_borrowed(self, service: TagManagementService) -> None:
        """alias/翻訳経由で別タグの行がマッチしても、その翻訳を借用せず素通しする (#991 P2)。"""
        manual = _recommendation("input_tag", needs=False, score=0.0)
        # search_tags が item.tag != 要求タグ の行を返すケース (別タグの翻訳に一致した等)。
        foreign_row = TagSearchResult(
            items=[
                TagRecordPublic(
                    tag="other_tag",
                    tag_id=2,
                    source_tag="other_tag",
                    type_name="general",
                    format_name="Lorairo",
                    translations={"ja": ["別タグの翻訳"]},
                )
            ],
            total=1,
        )
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=foreign_row,
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("input_tag")

        assert result is manual
        mock_eval.assert_not_called()

    def test_translation_only_match_without_ja_does_not_fire_missing(
        self, service: TagManagementService
    ) -> None:
        """完全一致行が無い (translation-only マッチ) 場合は ja 未登録でも missing を出さない (#991)。

        実在タグの ja 未登録は missing を出すが、別タグの翻訳経由でヒットしただけの行には
        missing も出さない (偽陽性防止)。test_exact_match_without_ja_fires_missing と対で
        「exact match 行の有無」による分岐を区別して検証する。
        """
        manual = _recommendation("input_tag", needs=False, score=0.0)
        foreign_row = TagSearchResult(
            items=[
                TagRecordPublic(
                    tag="other_tag",
                    tag_id=5,
                    source_tag="other_tag",
                    type_name="general",
                    format_name="Lorairo",
                    translations={"en": ["other"]},
                )
            ],
            total=1,
        )
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=foreign_row,
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("input_tag")

        assert result is manual
        mock_eval.assert_not_called()

    def test_source_tag_match_row_is_evaluated(self, service: TagManagementService) -> None:
        """source_tag が入力タグに一致する行は翻訳品質評価の対象になる (#991 再 P2)。"""
        manual = _recommendation("input_tag", needs=False, score=0.0)
        translation = _recommendation("input_tag", reason_codes=["overlong_translation"], score=0.6)
        # tag は別の canonical だが source_tag が要求タグに一致する行 (手動保存 source tag 等)。
        source_match_row = TagSearchResult(
            items=[
                TagRecordPublic(
                    tag="canonical_form",
                    tag_id=3,
                    source_tag="input_tag",
                    type_name="general",
                    format_name="Lorairo",
                    translations={"ja": ["とても長い翻訳文"]},
                )
            ],
            total=1,
        )
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=source_match_row,
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=translation,
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("input_tag")

        assert result.needs_refinement is True
        assert {r.code for r in result.reasons} == {"overlong_translation"}
        mock_eval.assert_called_once()
        assert mock_eval.call_args.kwargs["translation"] == "とても長い翻訳文"

    def test_case_variant_tag_match_row_is_evaluated(self, service: TagManagementService) -> None:
        """大文字小文字のみ違う canonical 行も casefold 一致で評価対象になる (#991 再 P2)。"""
        manual = _recommendation("blue_eyes", needs=False, score=0.0)
        # 行の tag は "Blue_Eyes" (case 変種)。入力 "blue_eyes" と casefold 一致する。
        # ja 翻訳は未登録なので実 recommend_translation_quality で missing が発火する。
        case_variant_row = TagSearchResult(
            items=[
                TagRecordPublic(
                    tag="Blue_Eyes",
                    tag_id=4,
                    source_tag=None,
                    type_name="general",
                    format_name="Lorairo",
                    translations={},
                )
            ],
            total=1,
        )
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=case_variant_row,
            ),
        ):
            result = service.recommend_with_translation_quality("blue_eyes")

        assert result.needs_refinement is True
        assert {r.code for r in result.reasons} == {"missing_translation"}

    def test_japanese_full_name_key_is_evaluated_not_missing(self, service: TagManagementService) -> None:
        """日本語訳が "japanese" キーで格納された行も翻訳として認識し missing 誤判定しない (#991 P1)。

        tagdb は language を verbatim 格納し、LoRAIro/register GUI は "japanese" を使う。
        "ja" だけを見ると "japanese" キーの有効訳を missing と誤判定して大量偽陽性になるため、
        "japanese" 候補が translation=None ではなく候補値として評価されることを検証する。
        """
        manual = _recommendation("tag", needs=False, score=0.0)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("tag", {"japanese": ["長い髪"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=_recommendation("tag", needs=False, score=0.0),
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result is manual  # 候補は clean → manual 素通し (missing 誤判定なし)
        mock_eval.assert_called_once()
        assert mock_eval.call_args.kwargs["translation"] == "長い髪"  # None ではない
        assert mock_eval.call_args.kwargs["language"] == "ja"

    def test_japanese_full_name_key_flagged_translation_is_reported(
        self, service: TagManagementService
    ) -> None:
        """ "japanese" キーの問題ある訳も翻訳品質 reason として ⚠ 対象になる (#991 P1)。"""
        manual = _recommendation("tag", needs=False, score=0.0)
        flagged = _recommendation("tag", reason_codes=["overlong_translation"], score=0.6)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("tag", {"japanese": ["とても長い翻訳文"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=flagged,
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result.needs_refinement is True
        assert {r.code for r in result.reasons} == {"overlong_translation"}

    def test_format_name_filters_search(self, service: TagManagementService) -> None:
        """既知 format は search に format_names フィルタを通し別 format の翻訳を借用しない (#991 P2)。"""
        manual = _recommendation("cat", needs=False, score=0.0)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("cat", {"ja": ["猫"]}),
            ) as mock_search,
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=_recommendation("cat", needs=False, score=0.0),
            ),
        ):
            service.recommend_with_translation_quality("cat", format_name="danbooru")

        request = mock_search.call_args.args[1]
        assert request.format_names == ["danbooru"]

    def test_unknown_format_does_not_filter_search(self, service: TagManagementService) -> None:
        """format が "unknown" (判定不能) のときは format フィルタを掛けない (#991 P2)。"""
        manual = _recommendation("cat", needs=False, score=0.0)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("cat", {"ja": ["猫"]}),
            ) as mock_search,
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
                return_value=_recommendation("cat", needs=False, score=0.0),
            ),
        ):
            service.recommend_with_translation_quality("cat")  # format_name 既定 "unknown"

        request = mock_search.call_args.args[1]
        assert request.format_names is None

    def test_search_value_error_degrades_to_manual(self, service: TagManagementService) -> None:
        """search_tags が ValueError を投げても例外を漏らさず manual へ縮退する (#991 P2)。"""
        manual = _recommendation("tag", reason_codes=["broad_single_word"], score=0.5)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                side_effect=ValueError("bad query"),
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result is manual

    def test_search_runtime_error_degrades_to_manual(self, service: TagManagementService) -> None:
        """search_tags が RuntimeError を投げても例外を漏らさず manual へ縮退する (#991 P2)。"""
        manual = _recommendation("tag", reason_codes=["broad_single_word"], score=0.5)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                side_effect=RuntimeError("reader closed"),
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result is manual

    def test_translation_fetch_failure_degrades_to_manual(self, service: TagManagementService) -> None:
        """翻訳取得 (DB read) 失敗時は例外を伝播させず manual の結果を返す。"""
        manual = _recommendation("tag", reason_codes=["broad_single_word"], score=0.5)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                side_effect=OperationalError("stmt", {}, Exception("db down")),
            ),
        ):
            result = service.recommend_with_translation_quality("tag")

        assert result is manual
