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

    def test_get_format_specific_types_cached_on_second_call(self, service: TagManagementService) -> None:
        """2 回目の取得はキャッシュヒットで DB 走査 (get_format_type_names) をスキップする (#1257 原因C)。"""
        with patch(
            "lorairo.services.tag_management_service.get_format_type_names",
            return_value=["unknown", "character"],
        ) as mock_get:
            first = service.get_format_specific_types()
            second = service.get_format_specific_types()

            assert first == ["unknown", "character"]
            assert second == ["unknown", "character"]
            mock_get.assert_called_once()  # 2 回目はキャッシュ

    def test_get_format_specific_types_returns_copy(self, service: TagManagementService) -> None:
        """返り値を破壊してもキャッシュは汚染されない (防御的コピー、#1257 原因C)。"""
        with patch(
            "lorairo.services.tag_management_service.get_format_type_names",
            return_value=["unknown"],
        ):
            first = service.get_format_specific_types()
            first.append("mutated")
            second = service.get_format_specific_types()

            assert second == ["unknown"]

    def test_update_tag_types_invalidates_type_cache(self, service: TagManagementService) -> None:
        """自己書き込み (update_tag_types) 後は type 名キャッシュが再取得される (#1257 原因C)。"""
        with patch(
            "lorairo.services.tag_management_service.get_format_type_names",
            side_effect=[["unknown"], ["unknown", "character"]],
        ) as mock_get:
            assert service.get_format_specific_types() == ["unknown"]
            with patch("lorairo.services.tag_management_service.update_tags_type_batch"):
                service.update_tag_types([TagTypeUpdate(tag_id=1, type_name="character")])
            # 更新でキャッシュが捨てられ、再スキャンで新 type が現れる。
            assert service.get_format_specific_types() == ["unknown", "character"]
            assert mock_get.call_count == 2

    def test_invalidate_format_type_cache_forces_refetch(self, service: TagManagementService) -> None:
        """外部書き込み検知用の invalidate_format_type_cache で再取得が起きる (#1257 原因C)。"""
        with patch(
            "lorairo.services.tag_management_service.get_format_type_names",
            side_effect=[["unknown"], ["unknown", "meta"]],
        ) as mock_get:
            assert service.get_format_specific_types() == ["unknown"]
            service.invalidate_format_type_cache()
            assert service.get_format_specific_types() == ["unknown", "meta"]
            assert mock_get.call_count == 2

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

    def test_add_translation_delegates_to_public_api(self, service: TagManagementService) -> None:
        """add_translation が公開 API write_user_translation へ委譲する (#989)。"""
        with patch("lorairo.services.tag_management_service.write_user_translation") as mock_write:
            service.add_translation(tag_id=42, language="ja", translation="少女")

            mock_write.assert_called_once_with(service.repository, 42, "ja", "少女")

    def test_add_translation_propagates_error(self, service: TagManagementService) -> None:
        """書き込み失敗は呼び出し元へ伝播する (握りつぶさない)。"""
        with patch(
            "lorairo.services.tag_management_service.write_user_translation",
            side_effect=OperationalError("stmt", {}, Exception("db down")),
        ):
            with pytest.raises(OperationalError):
                service.add_translation(tag_id=42, language="ja", translation="少女")

    def test_add_translation_auto_sets_preferred(self, service: TagManagementService) -> None:
        """add_translation は追加後にその訳を主訳へ自動設定する (#1084)。"""
        with (
            patch("lorairo.services.tag_management_service.write_user_translation") as mock_write,
            patch("lorairo.services.tag_management_service.set_preferred_translation") as mock_pref,
        ):
            service.add_translation(tag_id=42, language="ja", translation="少女")

            mock_write.assert_called_once_with(service.repository, 42, "ja", "少女")
            mock_pref.assert_called_once_with(service.repository, 42, "ja", "少女")

    def test_list_translation_candidates_returns_candidates_and_preferred(
        self, service: TagManagementService
    ) -> None:
        """当該言語の候補訳 (エイリアス両表記) と現在の主訳を返す (#1084)。"""
        result = TagSearchResult(
            items=[
                TagRecordPublic(
                    tag="blue_eyes",
                    tag_id=5,
                    source_tag="blue_eyes",
                    translations={"japanese": ["青目", "青い目"], "en": ["blue eyes"]},
                )
            ]
        )
        with (
            patch("lorairo.services.tag_management_service.search_tags", return_value=result),
            patch(
                "lorairo.services.tag_management_service.get_preferred_translations_batch",
                return_value={5: {"ja": "青い目"}},
            ),
        ):
            candidates, current = service.list_translation_candidates("blue_eyes", "ja")

        assert candidates == ["青目", "青い目"]
        assert current == "青い目"

    def test_list_translation_candidates_unresolved_returns_empty(
        self, service: TagManagementService
    ) -> None:
        """完全一致行が無ければ ([], None) (#1084)。"""
        result = TagSearchResult(items=[TagRecordPublic(tag="other", tag_id=9, source_tag="other")])
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            assert service.list_translation_candidates("blue_eyes", "ja") == ([], None)

    def test_list_translation_candidates_preferred_failure_degrades(
        self, service: TagManagementService
    ) -> None:
        """主訳取得が失敗しても候補 + None へ縮退する (#1084)。"""
        result = TagSearchResult(
            items=[
                TagRecordPublic(
                    tag="blue_eyes",
                    tag_id=5,
                    source_tag="blue_eyes",
                    translations={"ja": ["青い目"]},
                )
            ]
        )
        with (
            patch("lorairo.services.tag_management_service.search_tags", return_value=result),
            patch(
                "lorairo.services.tag_management_service.get_preferred_translations_batch",
                side_effect=OperationalError("stmt", {}, Exception("db down")),
            ),
        ):
            candidates, current = service.list_translation_candidates("blue_eyes", "ja")

        assert candidates == ["青い目"]
        assert current is None

    def test_translation_status_batch_resolves_all_tags_in_two_queries(
        self, service: TagManagementService
    ) -> None:
        """複数タグの翻訳状況を search_tags_batch 1 回 + preferred batch 1 回で解決する (#1203)。"""
        batch = {
            "blue_eyes": TagSearchResult(
                items=[
                    TagRecordPublic(
                        tag="blue_eyes",
                        tag_id=5,
                        source_tag="blue_eyes",
                        translations={"japanese": ["青目", "青い目"], "en": ["blue eyes"]},
                    )
                ]
            ),
            "1girl": TagSearchResult(
                items=[
                    TagRecordPublic(
                        tag="1girl",
                        tag_id=10,
                        source_tag="1girl",
                        translations={"ja": ["少女"]},
                    )
                ]
            ),
        }
        with (
            patch(
                "lorairo.services.tag_management_service.search_tags_batch", return_value=batch
            ) as mock_batch,
            patch(
                "lorairo.services.tag_management_service.get_preferred_translations_batch",
                return_value={5: {"ja": "青い目"}},
            ) as mock_pref,
        ):
            statuses = service.translation_status_batch(["blue_eyes", "1girl", "missing_tag"])

        assert mock_batch.call_count == 1
        assert mock_pref.call_count == 1
        assert statuses["blue_eyes"].tag_id == 5
        assert statuses["blue_eyes"].by_language["ja"] == (["青目", "青い目"], "青い目")
        assert statuses["blue_eyes"].by_language["en"] == (["blue eyes"], None)
        assert statuses["1girl"].tag_id == 10
        assert statuses["1girl"].by_language["ja"] == (["少女"], None)
        assert statuses["missing_tag"].tag_id is None
        assert statuses["missing_tag"].by_language == {}

    def test_translation_status_batch_search_failure_degrades_to_unresolved(
        self, service: TagManagementService
    ) -> None:
        """batch 検索失敗は全タグ未解決 (tag_id=None) へ縮退する (#1203)。"""
        with patch(
            "lorairo.services.tag_management_service.search_tags_batch",
            side_effect=OperationalError("stmt", {}, Exception("db down")),
        ):
            statuses = service.translation_status_batch(["blue_eyes"])

        assert statuses["blue_eyes"].tag_id is None
        assert statuses["blue_eyes"].by_language == {}

    def test_translation_status_batch_preferred_failure_keeps_candidates(
        self, service: TagManagementService
    ) -> None:
        """主訳 batch 取得の失敗は候補のみ + preferred=None で続行する (#1203)。"""
        batch = {
            "blue_eyes": TagSearchResult(
                items=[
                    TagRecordPublic(
                        tag="blue_eyes",
                        tag_id=5,
                        source_tag="blue_eyes",
                        translations={"ja": ["青い目"]},
                    )
                ]
            )
        }
        with (
            patch("lorairo.services.tag_management_service.search_tags_batch", return_value=batch),
            patch(
                "lorairo.services.tag_management_service.get_preferred_translations_batch",
                side_effect=OperationalError("stmt", {}, Exception("db down")),
            ),
        ):
            statuses = service.translation_status_batch(["blue_eyes"])

        assert statuses["blue_eyes"].tag_id == 5
        assert statuses["blue_eyes"].by_language["ja"] == (["青い目"], None)

    def test_set_preferred_translation_success(self, service: TagManagementService) -> None:
        """canonical→tag_id 解決の上で主訳を設定し True を返す (#1084)。"""
        result = TagSearchResult(items=[TagRecordPublic(tag="1girl", tag_id=10, source_tag="1girl")])
        with (
            patch("lorairo.services.tag_management_service.search_tags", return_value=result),
            patch("lorairo.services.tag_management_service.set_preferred_translation") as mock_pref,
        ):
            assert service.set_preferred_translation("1girl", "ja", "少女") is True
            mock_pref.assert_called_once_with(service.repository, 10, "ja", "少女")

    def test_set_preferred_translation_unresolved_returns_false(
        self, service: TagManagementService
    ) -> None:
        """tag_id 未解決なら書き込まず False を返す (#1084)。"""
        result = TagSearchResult(items=[TagRecordPublic(tag="other", tag_id=9, source_tag="other")])
        with (
            patch("lorairo.services.tag_management_service.search_tags", return_value=result),
            patch("lorairo.services.tag_management_service.set_preferred_translation") as mock_pref,
        ):
            assert service.set_preferred_translation("1girl", "ja", "少女") is False
            mock_pref.assert_not_called()

    def test_resolve_tag_id_exact_match(self, service: TagManagementService) -> None:
        """canonical 完全一致行の tag_id を返す (#989)。"""
        result = TagSearchResult(
            items=[
                TagRecordPublic(tag="other", tag_id=99, source_tag="other"),
                TagRecordPublic(tag="1girl", tag_id=10, source_tag="1girl"),
            ]
        )
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            assert service.resolve_tag_id("1girl") == 10

    def test_resolve_tag_id_source_tag_match(self, service: TagManagementService) -> None:
        """source_tag 一致でも tag_id を解決する。"""
        result = TagSearchResult(items=[TagRecordPublic(tag="blue_eyes", tag_id=20, source_tag="aoi_me")])
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            assert service.resolve_tag_id("aoi_me") == 20

    def test_resolve_tag_id_no_exact_match_returns_none(self, service: TagManagementService) -> None:
        """完全一致が無ければ None (別タグの翻訳経由マッチを採用しない)。"""
        result = TagSearchResult(items=[TagRecordPublic(tag="unrelated", tag_id=5, source_tag="unrelated")])
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            assert service.resolve_tag_id("1girl") is None

    def test_resolve_tag_id_search_error_returns_none(self, service: TagManagementService) -> None:
        """検索失敗時は None で縮退する (非ブロッキング)。"""
        with patch(
            "lorairo.services.tag_management_service.search_tags",
            side_effect=OperationalError("stmt", {}, Exception("db down")),
        ):
            assert service.resolve_tag_id("1girl") is None

    def test_resolve_tag_id_search_is_unscoped(self, service: TagManagementService) -> None:
        """format を絞らず検索する (Lorairo/unknown 手動タグも解決、Codex #995 P2)。"""
        result = TagSearchResult(
            items=[TagRecordPublic(tag="my_oc", tag_id=1_000_000_001, source_tag="my_oc")]
        )
        with patch(
            "lorairo.services.tag_management_service.search_tags", return_value=result
        ) as mock_search:
            assert service.resolve_tag_id("my_oc") == 1_000_000_001
            request = mock_search.call_args[0][1]
            assert request.format_names is None  # danbooru に絞らない


@pytest.mark.unit
class TestTranslationQualityIntegration:
    """recommend_with_translation_quality の統合ロジックのテスト (#976)。"""

    @pytest.fixture(autouse=True)
    def _neutralize_tag_record(self):
        """tag-record refinement を無効化して翻訳品質統合を分離する (#1123)。

        本クラスは Mock reader を使うため recommend_tag_record_refinement が幻の signal を
        出しうる。翻訳品質統合の検証に集中するため no-op に固定する (実挙動は
        TestTagRecordRefinementIntegration で検証)。
        """
        with patch(
            "lorairo.services.tag_management_service.recommend_tag_record_refinement",
            return_value=_recommendation("_", needs=False, score=0.0),
        ):
            yield

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

    @pytest.mark.parametrize("format_name", ["danbooru", "unknown"])
    def test_translation_search_is_format_independent(
        self, service: TagManagementService, format_name: str
    ) -> None:
        """翻訳取得は format に依存しないため search を format で絞らない (#993、#991 P2 撤回)。

        tagdb の TAG_TRANSLATIONS は tag_id への FK だけを持ち format_id を持たない。照合キーの
        TAGS.tag は UNIQUE なので 1 タグ文字列 = 1 tag_id = 1 翻訳セット。format を渡しても返る翻訳は
        変わらない (CLI 実測で確認)。よって format_name の値に関わらず format_names は常に None。
        """
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
            service.recommend_with_translation_quality("cat", format_name=format_name)

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

    def test_alias_tag_skips_translation_evaluation(self, service: TagManagementService) -> None:
        """alias タグは manual が preferred へ誘導済みなので翻訳品質評価を skip する (#993)。

        alias 行は preferred タグが訳を持っていても自分は訳を持たないことが多く、評価すると
        無関係な missing_translation ⚠ が merge され、alias recommendation を ignore/fix した
        後も残る。manual reasons に alias_tag があれば翻訳取得・評価をどちらも行わない。
        """
        manual = _recommendation("aoi_me", reason_codes=["alias_tag"], score=0.9)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
            ) as mock_search,
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("aoi_me")

        assert result is manual
        mock_search.assert_not_called()
        mock_eval.assert_not_called()

    def test_non_preferred_tag_skips_translation_evaluation(self, service: TagManagementService) -> None:
        """非 preferred タグも翻訳品質評価を skip する (#993)。"""
        manual = _recommendation("cat", reason_codes=["non_preferred_tag"], score=0.9)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
            ) as mock_search,
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("cat")

        assert result is manual
        mock_search.assert_not_called()
        mock_eval.assert_not_called()

    def test_alias_with_other_reasons_still_skips_translation(self, service: TagManagementService) -> None:
        """alias_tag と他 reason が併存しても翻訳評価は skip する (alias 由来の偽陽性防止優先)。"""
        manual = _recommendation("aoi_me", reason_codes=["alias_tag", "broad_single_word"], score=0.9)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
            ) as mock_search,
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("aoi_me")

        assert result is manual
        mock_search.assert_not_called()
        mock_eval.assert_not_called()

    def test_missing_format_status_skips_translation_evaluation(
        self, service: TagManagementService
    ) -> None:
        """指定 format に status が無いタグは翻訳評価を skip する (Codex PR #999)。

        concrete format を渡す caller で、タグ行は存在するが当該 format に status が無いとき
        manual は missing_format_status を報告する。翻訳取得は format 非依存 (search を絞らない)
        ため、別 format 行を拾って無関係な missing_translation ⚠ を出しうる。manual signal で
        gate して評価をスキップする。
        """
        manual = _recommendation("e621_only_tag", reason_codes=["missing_format_status"], score=0.5)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
            ) as mock_search,
            patch(
                "lorairo.services.tag_management_service.recommend_translation_quality",
            ) as mock_eval,
        ):
            result = service.recommend_with_translation_quality("e621_only_tag", format_name="danbooru")

        assert result is manual
        mock_search.assert_not_called()
        mock_eval.assert_not_called()


@pytest.mark.unit
class TestTagRecordRefinementIntegration:
    """recommend_tag_record_refinement をタグ管理フローへ合流する (#1123)。"""

    @pytest.fixture(autouse=True)
    def _neutralize_translation(self):
        """翻訳品質評価を no-op に固定し、tag-record 合流のみを検証する。"""
        with patch(
            "lorairo.services.tag_management_service.recommend_translation_quality",
            return_value=_recommendation("_", needs=False, score=0.0),
        ):
            yield

    @pytest.fixture
    def service(self) -> TagManagementService:
        with patch("lorairo.services.tag_management_service.get_tag_reader"):
            with patch("lorairo.services.tag_management_service.get_user_repository"):
                return TagManagementService()

    def test_merges_tag_record_reason_into_clean_manual(self, service: TagManagementService) -> None:
        """manual が clean でも tag-record の status/type 問題を ⚠ 対象へ合流する。"""
        manual = _recommendation("dog", needs=False, score=0.0)
        record = _recommendation("dog", reason_codes=["deprecated_tag"], score=0.9)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("dog", {"ja": ["犬"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_tag_record_refinement",
                return_value=record,
            ),
        ):
            result = service.recommend_with_translation_quality("dog")

        assert result.needs_refinement is True
        assert "deprecated_tag" in {r.code for r in result.reasons}

    def test_allowlist_filters_non_display_codes(self, service: TagManagementService) -> None:
        """allowlist 外の tag-record reason (status_type_conflict) は ⚠ 表示しない (#993 の教訓)。"""
        manual = _recommendation("dog", needs=False, score=0.0)
        record = _recommendation("dog", reason_codes=["deprecated_tag", "status_type_conflict"], score=0.9)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=_search_result_with_translations("dog", {"ja": ["犬"]}),
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_tag_record_refinement",
                return_value=record,
            ),
        ):
            result = service.recommend_with_translation_quality("dog")

        codes = {r.code for r in result.reasons}
        assert "deprecated_tag" in codes
        assert "status_type_conflict" not in codes

    def test_skip_codes_short_circuit_tag_record(self, service: TagManagementService) -> None:
        """manual が alias/非preferred/missing-format を出したら tag-record 評価もスキップする。"""
        manual = _recommendation("dog", reason_codes=["alias_tag"], score=0.5)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch("lorairo.services.tag_management_service.recommend_tag_record_refinement") as mock_record,
        ):
            result = service.recommend_with_translation_quality("dog")

        assert result is manual
        mock_record.assert_not_called()

    def test_no_exact_row_skips_tag_record(self, service: TagManagementService) -> None:
        """完全一致行が無ければ tag-record を評価しない (row None)。"""
        manual = _recommendation("dog", needs=False, score=0.0)
        no_match = TagSearchResult(items=[TagRecordPublic(tag="other", tag_id=9, source_tag="other")])
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=no_match,
            ),
            patch("lorairo.services.tag_management_service.recommend_tag_record_refinement") as mock_record,
        ):
            result = service.recommend_with_translation_quality("dog")

        assert result is manual
        mock_record.assert_not_called()

    def test_prefers_user_overlay_row_for_record(self, service: TagManagementService) -> None:
        """base + user-overlay 完全一致行では overlay 行 (tag_id 高位) を record 評価に渡す (#1123 Codex P2)。"""
        manual = _recommendation("dog", needs=False, score=0.0)
        # base 行を先に、user overlay 行 (USER_TAG_ID_OFFSET=1e9 以上) を後に置く
        base_row = TagRecordPublic(
            tag="dog", tag_id=5, source_tag="dog", type_name="general", format_name="Lorairo"
        )
        overlay_row = TagRecordPublic(
            tag="dog",
            tag_id=1_000_000_005,
            source_tag="dog",
            type_name="general",
            format_name="Lorairo",
        )
        result_rows = TagSearchResult(items=[base_row, overlay_row], total=2)
        with (
            patch(
                "lorairo.services.tag_management_service.recommend_manual_refinement",
                return_value=manual,
            ),
            patch(
                "lorairo.services.tag_management_service.search_tags",
                return_value=result_rows,
            ),
            patch(
                "lorairo.services.tag_management_service.recommend_tag_record_refinement",
                return_value=_recommendation("_", needs=False, score=0.0),
            ) as mock_record,
        ):
            service.recommend_with_translation_quality("dog")

        # record 評価には base 行ではなく overlay 行 (tag_id 高位) が渡る
        assert mock_record.call_args.args[0].tag_id == 1_000_000_005


@pytest.mark.unit
class TestTranslationPrefetch:
    """prefetch_translations と _fetch_exact_match_translations のキャッシュ連携 (#998)。"""

    @pytest.fixture
    def service(self) -> TagManagementService:
        with patch("lorairo.services.tag_management_service.get_tag_reader"):
            with patch("lorairo.services.tag_management_service.get_user_repository"):
                return TagManagementService()

    def test_prefetch_populates_cache_and_avoids_search_tags(self, service: TagManagementService) -> None:
        """prefetch 後の完全一致取得はキャッシュから返し search_tags を呼ばない。"""
        batch = {"blue_eyes": _search_result_with_translations("blue_eyes", {"ja": ["青い目"]})}
        with patch(
            "lorairo.services.tag_management_service.search_tags_batch", return_value=batch
        ) as mock_batch:
            service.prefetch_translations(["blue_eyes", "missing"])

        mock_batch.assert_called_once()
        with patch("lorairo.services.tag_management_service.search_tags") as mock_search:
            hit = service._fetch_exact_match_translations("blue_eyes")
            miss = service._fetch_exact_match_translations("missing")

        assert hit == {"ja": ["青い目"]}
        # batch に無い query は「完全一致行なし」= None 扱い (呼び出し元は素通し)
        assert miss is None
        mock_search.assert_not_called()

    def test_prefetch_cache_consumed_once(self, service: TagManagementService) -> None:
        """キャッシュ命中は consume-once。2 回目は単発 search_tags fallback。"""
        batch = {"tag": _search_result_with_translations("tag", {"ja": ["訳"]})}
        with patch("lorairo.services.tag_management_service.search_tags_batch", return_value=batch):
            service.prefetch_translations(["tag"])

        with patch(
            "lorairo.services.tag_management_service.search_tags",
            return_value=_search_result_with_translations("tag", {"ja": ["再取得"]}),
        ) as mock_search:
            first = service._fetch_exact_match_translations("tag")
            second = service._fetch_exact_match_translations("tag")

        assert first == {"ja": ["訳"]}
        assert second == {"ja": ["再取得"]}
        mock_search.assert_called_once()

    def test_prefetch_batch_failure_falls_back_to_search_tags(self, service: TagManagementService) -> None:
        """batch 取得失敗は例外を伝播させず、per-tag fallback に委ねる。"""
        with patch(
            "lorairo.services.tag_management_service.search_tags_batch",
            side_effect=ValueError("boom"),
        ):
            service.prefetch_translations(["tag"])

        with patch(
            "lorairo.services.tag_management_service.search_tags",
            return_value=_search_result_with_translations("tag", {"ja": ["訳"]}),
        ) as mock_search:
            result = service._fetch_exact_match_translations("tag")

        assert result == {"ja": ["訳"]}
        mock_search.assert_called_once()

    def test_reprefetch_clears_stale_entries(self, service: TagManagementService) -> None:
        """再 prefetch は前回集合の stale entry を残さない。"""
        with patch(
            "lorairo.services.tag_management_service.search_tags_batch",
            return_value={"a": _search_result_with_translations("a", {"ja": ["A訳"]})},
        ):
            service.prefetch_translations(["a"])
        with patch(
            "lorairo.services.tag_management_service.search_tags_batch",
            return_value={"b": _search_result_with_translations("b", {"ja": ["B訳"]})},
        ):
            service.prefetch_translations(["b"])

        # "a" は再 prefetch でクリアされキャッシュに無い → fallback
        with patch(
            "lorairo.services.tag_management_service.search_tags",
            return_value=_search_result_with_translations("a", {"ja": ["A再"]}),
        ) as mock_search:
            result = service._fetch_exact_match_translations("a")

        assert result == {"ja": ["A再"]}
        mock_search.assert_called_once()

    def test_prefetch_empty_tags_noop(self, service: TagManagementService) -> None:
        """空入力は search_tags_batch を呼ばない。"""
        with patch("lorairo.services.tag_management_service.search_tags_batch") as mock_batch:
            service.prefetch_translations([])
        mock_batch.assert_not_called()


@pytest.mark.unit
class TestUserTranslationOverrides:
    """user overlay の修正値が base 誤訳候補を supersede する (#1054, PR #1086 Codex P2)。"""

    class _FakePatchRow:
        def __init__(self, translation_id: int, language: str, translation: str) -> None:
            self.translation_id = translation_id
            self.language = language
            self.translation = translation

    class _FakeUserRepo:
        def __init__(self, rows: list) -> None:
            self._rows = rows

        def get_translations(self, tag_id: int) -> list:
            return list(self._rows)

    class _FakeReaderWithUser:
        def __init__(self, user_repo) -> None:
            self.user_repo = user_repo

    @pytest.fixture
    def service(self) -> TagManagementService:
        with patch("lorairo.services.tag_management_service.get_tag_reader"):
            with patch("lorairo.services.tag_management_service.get_user_repository"):
                return TagManagementService()

    def _reader(self, rows: list):
        return self._FakeReaderWithUser(self._FakeUserRepo(rows))

    def test_fix_supersedes_bad_base_candidate(self, service: TagManagementService) -> None:
        """修正済み言語キーの base 誤訳候補は評価されず ⚠ が再発しない。"""
        # base の "japanese" に低品質訳 (記号のみ) が残っているが、user overlay が同一キーで
        # 修正済み → 評価は user 値のみになり警告ゼロ
        reader = self._reader([self._FakePatchRow(1, "japanese", "ドレス")])
        result = _search_result_with_translations("dress", {"japanese": ["???", "ドレス"]})
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            recs = service._evaluate_translation_quality("dress", repo=reader)

        assert recs == []

    def test_unfixed_language_key_still_warns(self, service: TagManagementService) -> None:
        """user 修正が無い言語キーの誤訳候補は従来どおり警告する (キー単位 supersede)。"""
        # "japanese" は修正済みだが "ja" キーに別の低品質訳が残っている
        reader = self._reader([self._FakePatchRow(1, "japanese", "ドレス")])
        result = _search_result_with_translations("dress", {"japanese": ["???"], "ja": ["!!!"]})
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            recs = service._evaluate_translation_quality("dress", repo=reader)

        assert len(recs) == 1

    def test_latest_user_patch_wins_per_language(self, service: TagManagementService) -> None:
        """同一言語キーに複数 patch がある場合は最新 (patch_id 最大) を採用する。"""
        # 1回目の修正も低品質、2回目で正しい値 → 最新のみ評価され警告ゼロ
        reader = self._reader(
            [
                self._FakePatchRow(2, "japanese", "ドレス"),
                self._FakePatchRow(1, "japanese", "???"),
            ]
        )
        result = _search_result_with_translations("dress", {"japanese": ["???"]})
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            recs = service._evaluate_translation_quality("dress", repo=reader)

        assert recs == []

    def test_no_user_repo_keeps_all_candidate_evaluation(self, service: TagManagementService) -> None:
        """user_repo を持たない reader では従来の全候補評価のまま (後方互換)。"""

        class _PlainReader:
            pass

        result = _search_result_with_translations("dress", {"japanese": ["???"]})
        with patch("lorairo.services.tag_management_service.search_tags", return_value=result):
            recs = service._evaluate_translation_quality("dress", repo=_PlainReader())

        assert len(recs) == 1


class TestPreferredTranslationCodexFollowups:
    """Codex P2 対応: 主訳設定の翻訳行保証 / provider の例外縮退 (#1084)。"""

    @pytest.fixture
    def service(self) -> TagManagementService:
        """TagManagementService インスタンスを提供"""
        with patch("lorairo.services.tag_management_service.get_tag_reader"):
            with patch("lorairo.services.tag_management_service.get_user_repository"):
                return TagManagementService()

    def test_set_preferred_also_writes_normalized_translation_row(
        self, service: TagManagementService
    ) -> None:
        """主訳設定時に正規化キーの翻訳行も書く (再起動後もセレクタに言語が現れる)。"""
        with (
            patch.object(service, "resolve_tag_id", return_value=42),
            patch("lorairo.services.tag_management_service.set_preferred_translation") as mock_pref,
            patch("lorairo.services.tag_management_service.write_user_translation") as mock_write,
        ):
            assert service.set_preferred_translation("blue eyes", "en", "blue eyes trans") is True
            mock_pref.assert_called_once_with(service.repository, 42, "en", "blue eyes trans")
            mock_write.assert_called_once_with(service.repository, 42, "en", "blue eyes trans")

    def test_candidates_degrade_when_preference_read_raises_value_error(
        self, service: TagManagementService
    ) -> None:
        """主訳読み取りの ValueError/RuntimeError でもダイアログ候補は返す (worker と同契約)。"""
        search_result = _search_result_with_translations("blue eyes", {"en": ["blue eyes trans"]})
        with (
            patch("lorairo.services.tag_management_service.search_tags", return_value=search_result),
            patch(
                "lorairo.services.tag_management_service.get_preferred_translations_batch",
                side_effect=ValueError("boom"),
            ),
        ):
            candidates, current = service.list_translation_candidates("blue eyes", "en")

        assert candidates == ["blue eyes trans"]
        assert current is None
