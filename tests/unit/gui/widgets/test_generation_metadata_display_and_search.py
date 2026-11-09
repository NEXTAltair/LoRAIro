"""生成メタデータの詳細表示・遅延 JSON ツリー・検索条件フィルターの単体テスト (Issue #1483)。"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QModelIndex, Qt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from lorairo.database.filter_criteria import ImageFilterCriteria
from lorairo.database.repository.generation_metadata import GenerationMetadataRepository
from lorairo.database.repository.image import ImageRepository
from lorairo.database.schema import Base, GenerationMetadata, GenerationMetadataSource, Image
from lorairo.domain.generation_metadata import (
    GenerationMetadataResult,
    GenerationMetadataStatus,
    GenerationParameters,
    LoraReference,
)
from lorairo.gui.services.search_filter_service import SearchFilterService
from lorairo.gui.widgets.filter_search_panel import FilterSearchPanel
from lorairo.gui.widgets.generation_metadata_display_widget import (
    GenerationMetadataDisplayWidget,
    LazyJsonTreeModel,
)
from lorairo.gui.widgets.selected_image_details_widget import SelectedImageDetailsWidget
from lorairo.services.search_criteria_processor import SearchCriteriaProcessor


@pytest.fixture
def in_memory_session_factory():
    """テスト用インメモリ SQLite セッションファクトリ。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _insert_test_image(session_factory, image_id: int, uuid_str: str) -> int:
    with session_factory() as session:
        img = Image(
            id=image_id,
            uuid=uuid_str,
            phash=f"phash_{image_id:04d}",
            original_image_path=f"/orig/{image_id}.png",
            stored_image_path=f"/stored/{image_id}.png",
            width=1024,
            height=1024,
            format="PNG",
            mode="RGB",
            has_alpha=False,
            filename=f"{image_id}.png",
            extension=".png",
        )
        session.add(img)
        session.commit()
    return image_id


class TestGenerationMetadataRepositorySearchFilters:
    """ImageRepository.get_images_by_filter の生成メタデータ検索条件テスト。"""

    @pytest.fixture
    def seeded_repos(self, in_memory_session_factory):
        image_repo = ImageRepository(session_factory=in_memory_session_factory)
        gen_repo = GenerationMetadataRepository(session_factory=in_memory_session_factory)

        # Image 1: 行なし (未解析 -> status="none" にマッチ)
        _insert_test_image(in_memory_session_factory, 1, "uuid-1")

        # Image 2: status="no_metadata" (-> status="none" にマッチ)
        _insert_test_image(in_memory_session_factory, 2, "uuid-2")
        gen_repo.save_result(
            2,
            GenerationMetadataResult(
                status=GenerationMetadataStatus.NO_METADATA,
                parser_name="test_parser",
            ),
        )

        # Image 3: A1111 (sd_webui), status="parsed"
        _insert_test_image(in_memory_session_factory, 3, "uuid-3")
        gen_repo.save_result(
            3,
            GenerationMetadataResult(
                status=GenerationMetadataStatus.PARSED,
                parser_name="test_parser",
                tool="sd_webui",
                parameters=GenerationParameters(
                    model_name="IllustriousXL_v10",
                    positive_prompt="1girl, masterpiece, cherry blossoms",
                    negative_prompt="lowres, bad anatomy",
                    seed="123456",
                    steps=28,
                    sampler="Euler a",
                    cfg_scale=7.0,
                    loras=(LoraReference(name="AnimeStyle_v2", weight="0.8"),),
                    extra={"Schedule type": "Karras", "Denoising strength": "0.55"},
                ),
            ),
        )

        # Image 4: ComfyUI, status="partial"
        _insert_test_image(in_memory_session_factory, 4, "uuid-4")
        gen_repo.save_result(
            4,
            GenerationMetadataResult(
                status=GenerationMetadataStatus.PARTIAL,
                parser_name="test_parser",
                tool="comfyui",
                parameters=GenerationParameters(
                    model_name=" ponyDiffusionV6XL.safetensors ",
                    positive_prompt="cyberpunk cityscape at night",
                    negative_prompt="blurry, watermark",
                    loras=(LoraReference(name="NeonGlowLoRA", weight="0.65"),),
                ),
            ),
        )

        # Image 5: status="unsupported", tool=None ("unknown" にマッチ)
        _insert_test_image(in_memory_session_factory, 5, "uuid-5")
        gen_repo.save_result(
            5,
            GenerationMetadataResult(
                status=GenerationMetadataStatus.UNSUPPORTED,
                parser_name="test_parser",
                tool=None,
            ),
        )

        # Image 6: status="failed", error_message="broken json"
        _insert_test_image(in_memory_session_factory, 6, "uuid-6")
        gen_repo.save_result(
            6,
            GenerationMetadataResult(
                status=GenerationMetadataStatus.FAILED,
                parser_name="test_parser",
                error_message="broken json",
            ),
        )

        return image_repo, gen_repo

    def test_filter_by_generation_status(self, seeded_repos):
        image_repo, _ = seeded_repos

        # "none" matches both no row (Image 1) and status="no_metadata" (Image 2)
        images_none, count_none = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_status="none", include_nsfw=True)
        )
        assert count_none == 2
        assert {img["id"] for img in images_none} == {1, 2}

        images_parsed, count_parsed = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_status="parsed", include_nsfw=True)
        )
        assert count_parsed == 1
        assert [img["id"] for img in images_parsed] == [3]

        images_partial, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_status="partial", include_nsfw=True)
        )
        assert [img["id"] for img in images_partial] == [4]

        images_unsupported, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_status="unsupported", include_nsfw=True)
        )
        assert [img["id"] for img in images_unsupported] == [5]

        images_failed, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_status="failed", include_nsfw=True)
        )
        assert [img["id"] for img in images_failed] == [6]

    def test_filter_by_generation_tool(self, seeded_repos):
        image_repo, _ = seeded_repos

        # "a1111" matches tool="sd_webui" or "a1111"
        images_a1111, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_tool="a1111", include_nsfw=True)
        )
        assert [img["id"] for img in images_a1111] == [3]

        images_comfy, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_tool="comfyui", include_nsfw=True)
        )
        assert [img["id"] for img in images_comfy] == [4]

        images_unknown, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_tool="unknown", include_nsfw=True)
        )
        assert {img["id"] for img in images_unknown} == {5, 6}

    def test_filter_by_model_lora_prompt_case_insensitive_substring(self, seeded_repos):
        image_repo, _ = seeded_repos

        # model_name substring (case-insensitive)
        images_model, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_model="illustriousxl", include_nsfw=True)
        )
        assert [img["id"] for img in images_model] == [3]

        # loras_json name substring (case-insensitive, does not match JSON keys/kind)
        images_lora, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_lora="neonglow", include_nsfw=True)
        )
        assert [img["id"] for img in images_lora] == [4]

        images_lora_key, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_lora="weight", include_nsfw=True)
        )
        assert images_lora_key == []

        # positive_prompt substring (case-insensitive)
        images_pos_prompt, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_prompt="CHERRY BLOSSOMS", include_nsfw=True)
        )
        assert [img["id"] for img in images_pos_prompt] == [3]

        # negative_prompt substring (case-insensitive)
        images_neg_prompt, _ = image_repo.get_images_by_filter(
            ImageFilterCriteria(generation_prompt="watermark", include_nsfw=True)
        )
        assert [img["id"] for img in images_neg_prompt] == [4]


class TestSearchServiceAndFilterPanelIntegration:
    """SearchConditions / SearchFilterService / FilterSearchPanel の統合テスト。"""

    def test_search_conditions_to_filter_criteria_and_preview(self):
        mock_db = Mock()
        service = SearchFilterService(db_manager=mock_db, model_selection_service=Mock())

        conditions = service.create_search_conditions(
            search_type="tags",
            keywords=[],
            generation_status="parsed",
            generation_tool="comfyui",
            generation_model="sdxl",
            generation_lora="detail_tweaker",
            generation_prompt="masterpiece",
        )
        criteria = conditions.to_filter_criteria()
        assert criteria.generation_status == "parsed"
        assert criteria.generation_tool == "comfyui"
        assert criteria.generation_model == "sdxl"
        assert criteria.generation_lora == "detail_tweaker"
        assert criteria.generation_prompt == "masterpiece"

        preview = service.create_search_preview(conditions)
        assert "生成状態: parsed" in preview
        assert "生成ツール: comfyui" in preview
        assert "生成モデル: sdxl" in preview
        assert "LoRA: detail_tweaker" in preview
        assert "プロンプト: masterpiece" in preview

        processor = SearchCriteriaProcessor(mock_db)
        gen_dict = processor.process_generation_metadata_filter(conditions)
        assert gen_dict == {
            "generation_status": "parsed",
            "generation_tool": "comfyui",
            "generation_model": "sdxl",
            "generation_lora": "detail_tweaker",
            "generation_prompt": "masterpiece",
        }

    def test_filter_search_panel_generation_controls_and_clear(self, qtbot):
        panel = FilterSearchPanel()
        qtbot.addWidget(panel)

        mock_db = Mock()
        mock_db.get_images_count_only.return_value = 0
        service = SearchFilterService(db_manager=mock_db, model_selection_service=Mock())
        panel.set_search_filter_service(service)

        panel.combo_generation_status.setCurrentText("parsed")
        panel.combo_generation_tool.setCurrentText("a1111")
        panel.line_edit_generation_model.setText("animagine")
        panel.line_edit_generation_lora.setText("lineart")
        panel.line_edit_generation_prompt.setText("1girl")

        cond_dict = panel.get_filter_conditions()
        assert cond_dict["generation_status"] == "parsed"
        assert cond_dict["generation_tool"] == "a1111"
        assert cond_dict["generation_model"] == "animagine"
        assert cond_dict["generation_lora"] == "lineart"
        assert cond_dict["generation_prompt"] == "1girl"

        # キーワード無しでも生成メタデータ条件のみで SearchConditions が構築できること
        built = panel._build_search_conditions_from_ui(show_status=False)
        assert built is not None
        assert built.generation_status == "parsed"
        assert built.generation_tool == "a1111"
        assert built.generation_model == "animagine"
        assert built.generation_lora == "lineart"
        assert built.generation_prompt == "1girl"

        # clear_filters() で全項目が初期値に戻ること
        panel.clear_filters()
        cleared = panel.get_filter_conditions()
        assert cleared["generation_status"] is None
        assert cleared["generation_tool"] is None
        assert cleared["generation_model"] is None
        assert cleared["generation_lora"] is None
        assert cleared["generation_prompt"] is None
        panel.shutdown()


class TestLazyJsonTreeModelAndDisplayWidget:
    """LazyJsonTreeModel の遅延展開と GenerationMetadataDisplayWidget の5状態テスト。"""

    def test_lazy_json_tree_model_populates_children_only_on_fetch_more(self):
        nested_workflow = json.dumps(
            {
                "nodes": [
                    {"id": 1, "type": "KSampler", "inputs": {"seed": 42, "steps": 20}},
                    {"id": 2, "type": "CLIPTextEncode", "inputs": {"text": "1girl"}},
                ],
                "links": [[1, 0, 2, 0]],
            }
        )
        model = LazyJsonTreeModel({"raw_workflow": nested_workflow})

        # ルート直下には "raw_workflow" の 1 ノードだけが存在し、その子ノードはまだ未生成
        assert model.rowCount(QModelIndex()) == 1
        workflow_idx = model.index(0, 0, QModelIndex())
        assert model.data(workflow_idx, Qt.ItemDataRole.DisplayRole) == "raw_workflow"
        assert model.hasChildren(workflow_idx) is True
        assert model.canFetchMore(workflow_idx) is True
        assert model.is_node_fetched(workflow_idx) is False
        assert model.rowCount(workflow_idx) == 0

        # 第1階層を展開 (fetchMore) -> "nodes", "links" のみ生成され、孫ノードは未生成
        model.fetchMore(workflow_idx)
        assert model.is_node_fetched(workflow_idx) is True
        assert model.canFetchMore(workflow_idx) is False
        assert model.rowCount(workflow_idx) == 2

        nodes_idx = model.index(0, 0, workflow_idx)
        assert model.data(nodes_idx, Qt.ItemDataRole.DisplayRole) == "nodes"
        assert model.hasChildren(nodes_idx) is True
        assert model.canFetchMore(nodes_idx) is True
        assert model.is_node_fetched(nodes_idx) is False
        assert model.rowCount(nodes_idx) == 0

        # 第2階層 ("nodes") を展開 -> [0], [1] が生成されるが、その中はまだ未生成
        model.fetchMore(nodes_idx)
        assert model.is_node_fetched(nodes_idx) is True
        assert model.rowCount(nodes_idx) == 2
        node0_idx = model.index(0, 0, nodes_idx)
        assert model.canFetchMore(node0_idx) is True
        assert model.rowCount(node0_idx) == 0

    def test_display_widget_distinguishes_all_five_states_and_fields(self, qtbot):
        widget = GenerationMetadataDisplayWidget()
        qtbot.addWidget(widget)

        # 1. none (初期状態 / None)
        assert widget.current_status == "none"
        assert widget.label_status.text() == "生成メタデータなし"
        assert widget.fields_container.isHidden() is True

        # 2. parsed (全抽出フィールド + raw_workflow 遅延ツリー)
        widget.set_generation_metadata(
            {
                "status": "parsed",
                "tool": "comfyui",
                "model_name": "juggernautXL_v9.safetensors",
                "loras": [{"name": "detail_slider", "weight": 0.75}],
                "positive_prompt": "masterpiece, best quality, 1girl",
                "negative_prompt": "worst quality, low quality",
                "seed": "987654321",
                "steps": 30,
                "sampler": "dpmpp_2m",
                "scheduler": "karras",
                "cfg": 6.5,
                "denoise": 0.45,
                "raw_workflow": '{"1": {"class_type": "KSampler"}}',
            }
        )
        assert widget.current_status == "parsed"
        assert widget.label_status.text() == "解析済み"
        assert "comfyui" in widget.label_tool.text().lower()
        assert widget.label_model_name.text() == "juggernautXL_v9.safetensors"
        assert widget.label_loras.text() == "detail_slider:0.75"
        assert widget.label_positive_prompt.text() == "masterpiece, best quality, 1girl"
        assert widget.label_negative_prompt.text() == "worst quality, low quality"
        assert widget.label_seed.text() == "987654321"
        assert widget.label_steps.text() == "30"
        assert widget.label_sampler.text() == "dpmpp_2m"
        assert widget.label_scheduler.text() == "karras"
        assert widget.label_cfg.text() == "6.5"
        assert widget.label_denoise.text() == "0.45"
        assert widget.raw_tree_model.rowCount(QModelIndex()) == 1

        # 3. partial
        widget.set_generation_metadata({"status": "partial", "tool": "a1111", "positive_prompt": "solo"})
        assert widget.current_status == "partial"
        assert widget.label_status.text() == "部分解析"

        # 4. unsupported
        widget.set_generation_metadata({"status": "unsupported"})
        assert widget.current_status == "unsupported"
        assert widget.label_status.text() == "未対応形式"

        # 5. failed + error_reason
        widget.set_generation_metadata({"status": "failed", "error_reason": "JSONDecodeError at line 1"})
        assert widget.current_status == "failed"
        assert "解析失敗" in widget.label_status.text()
        assert "JSONDecodeError at line 1" in widget.label_error_reason.text()
        assert widget.label_error_reason.isHidden() is False

    def test_selected_image_details_widget_loads_and_clears_generation_metadata(self, qtbot):
        details_widget = SelectedImageDetailsWidget()
        qtbot.addWidget(details_widget)

        mock_db = Mock()
        orm_meta = GenerationMetadata(
            id=1,
            image_id=42,
            status="parsed",
            tool="sd_webui",
            parser_name="builtin_generation_metadata",
            parser_version="1",
            positive_prompt="1girl, smile",
            negative_prompt="bad hands",
            model_name="anything_v5",
            seed="111",
            steps=20,
            sampler="Euler",
            cfg_scale=7.5,
            loras_json=json.dumps([{"name": "flat_color", "weight": 0.5, "kind": "lora"}]),
            extra_json=json.dumps({"Schedule type": "Automatic", "Denoising strength": "0.6"}),
        )
        orm_source = GenerationMetadataSource(
            id=1,
            image_id=42,
            source_kind="png_text",
            source_key="parameters",
            raw_text="1girl, smile\nNegative prompt: bad hands\nSteps: 20",
            sha256="abc",
        )
        mock_db.get_rejected_tags.return_value = []
        mock_db.get_generation_metadata.return_value = orm_meta
        mock_db.get_generation_metadata_sources.return_value = [orm_source]
        details_widget.set_db_manager(mock_db)

        details_widget._on_image_data_received(
            {
                "id": 42,
                "filename": "sample.png",
                "stored_image_path": "/stored/sample.png",
                "width": 512,
                "height": 512,
                "tags": [],
                "captions": [],
            }
        )

        gen_w = details_widget.generation_metadata_widget
        assert gen_w.current_status == "parsed"
        assert gen_w.label_model_name.text() == "anything_v5"
        assert gen_w.label_loras.text() == "flat_color:0.5"
        assert gen_w.label_scheduler.text() == "Automatic"
        assert gen_w.label_denoise.text() == "0.6"
        assert gen_w.raw_tree_model.rowCount(QModelIndex()) == 1

        # 空データ選択時はクリアされて "生成メタデータなし" に戻ること
        details_widget._on_image_data_received({})
        assert gen_w.current_status == "none"
        assert gen_w.label_status.text() == "生成メタデータなし"
