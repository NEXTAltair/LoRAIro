"""Issue #939: overlay DB 対応後 LoRAIro E2E 動作検証テスト

genai-tag-db-tools overlay 再設計完了後、LoRAIro のタグ登録・検索・変換フローが
正しく動作することを検証する。

テストシナリオ:
- Scenario 2: user 独自 tag の登録 → tag_id が 1_000_000_000 以上
- Scenario 3: アノテーションパス登録タグが merged reader で可視
- Scenario 4: format_id=1000 の TagManagementService 操作
"""

import uuid

import pytest


@pytest.mark.integration
class TestOverlayTagE2E:
    """overlay DB 対応後の LoRAIro タグ操作 E2E テスト"""

    def test_user_scope_tag_id_is_offset(self, test_tag_db_path) -> None:
        """user scope で登録したタグの tag_id は 1_000_000_000 以上 (Scenario 2)"""
        from genai_tag_db_tools import create_tag_register_service
        from genai_tag_db_tools.db.schema import USER_TAG_ID_OFFSET
        from genai_tag_db_tools.models import TagRegisterRequest

        unique_tag = f"custom_{uuid.uuid4().hex[:8]}"

        svc = create_tag_register_service()
        req = TagRegisterRequest(
            tag=unique_tag,
            source_tag=unique_tag,
            format_name="Lorairo",
            type_name="unknown",
            scope="user",
        )
        result = svc.register_tag(req)

        assert result.tag_id >= USER_TAG_ID_OFFSET, (
            f"user scope tag_id {result.tag_id} should be >= {USER_TAG_ID_OFFSET}"
        )

    def test_user_scope_tag_searchable_via_merged_reader(self, test_tag_db_path) -> None:
        """user scope で登録したタグが get_tag_reader() (merged) で検索できる (Scenario 2 続き)"""
        from genai_tag_db_tools import create_tag_register_service, get_tag_reader, search_tags
        from genai_tag_db_tools.models import TagRegisterRequest, TagSearchRequest

        unique_tag = f"searchable_{uuid.uuid4().hex[:8]}"
        normalized = unique_tag.replace("_", " ")

        svc = create_tag_register_service()
        req = TagRegisterRequest(
            tag=normalized,
            source_tag=unique_tag,
            format_name="Lorairo",
            type_name="unknown",
            scope="user",
        )
        result = svc.register_tag(req)
        registered_id = result.tag_id

        reader = get_tag_reader()
        search_req = TagSearchRequest(
            query=normalized,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=False,
        )
        search_result = search_tags(reader, search_req)
        found_ids = [item.tag_id for item in search_result.items]

        assert registered_id in found_ids, (
            f"tag_id {registered_id} for '{normalized}' not found in merged reader results: {found_ids}"
        )

    def test_annotation_registered_tag_visible_via_merged_reader(
        self, test_annotation_repository_with_tag_db
    ) -> None:
        """アノテーションパス登録タグ (scope なし) が get_tag_reader() で可視 (Scenario 3)"""
        from genai_tag_db_tools import get_tag_reader, search_tags
        from genai_tag_db_tools.models import TagSearchRequest

        unique_tag = f"anno_{uuid.uuid4().hex[:8]}"

        with test_annotation_repository_with_tag_db.session_factory() as session:
            tag_id = test_annotation_repository_with_tag_db._get_or_create_tag_id_external(
                session, unique_tag
            )

        assert tag_id is not None, f"tag_id should be returned for '{unique_tag}'"

        normalized = unique_tag.replace("_", " ")
        reader = get_tag_reader()
        search_req = TagSearchRequest(
            query=normalized,
            partial=False,
            resolve_preferred=False,
            include_aliases=True,
            include_deprecated=False,
        )
        search_result = search_tags(reader, search_req)
        found_ids = [item.tag_id for item in search_result.items]

        assert tag_id in found_ids, (
            f"annotation-registered tag_id {tag_id} for '{normalized}' "
            f"should be visible via merged reader, got: {found_ids}"
        )

    def test_tag_management_service_get_unknown_tags_shows_user_tags(self, test_tag_db_path) -> None:
        """TagManagementService.get_unknown_tags() が user scope タグを返す (Scenario 4)"""
        from genai_tag_db_tools import create_tag_register_service
        from genai_tag_db_tools.models import TagRegisterRequest

        from lorairo.services.tag_management_service import TagManagementService

        unique_tag = f"mgmt_{uuid.uuid4().hex[:8]}"
        normalized = unique_tag.replace("_", " ")

        svc = create_tag_register_service()
        req = TagRegisterRequest(
            tag=normalized,
            source_tag=unique_tag,
            format_name="Lorairo",
            type_name="unknown",
            scope="user",
        )
        svc.register_tag(req)

        tms = TagManagementService()
        unknown_tags = tms.get_unknown_tags()
        tag_names = [t.tag for t in unknown_tags]

        assert normalized in tag_names, (
            f"'{normalized}' should appear in get_unknown_tags(), got: {tag_names}"
        )

    def test_tag_management_service_update_type_persists(self, test_tag_db_path) -> None:
        """TagManagementService.update_single_tag_type() が type 更新を永続化する (Scenario 4 続き)"""
        from genai_tag_db_tools import create_tag_register_service
        from genai_tag_db_tools.models import TagRegisterRequest

        from lorairo.services.tag_management_service import TagManagementService

        unique_tag = f"typed_{uuid.uuid4().hex[:8]}"
        normalized = unique_tag.replace("_", " ")

        svc = create_tag_register_service()
        req = TagRegisterRequest(
            tag=normalized,
            source_tag=unique_tag,
            format_name="Lorairo",
            type_name="unknown",
            scope="user",
        )
        result = svc.register_tag(req)
        tag_id = result.tag_id

        tms = TagManagementService()

        # タイプ更新前: unknown に含まれる
        before = [t.tag_id for t in tms.get_unknown_tags()]
        assert tag_id in before, f"tag_id {tag_id} should be in unknown tags before update"

        # タイプ更新
        tms.update_single_tag_type(tag_id=tag_id, type_name="character")

        # 更新後: unknown から消える
        after = [t.tag_id for t in tms.get_unknown_tags()]
        assert tag_id not in after, f"tag_id {tag_id} should not be in unknown tags after type update"
