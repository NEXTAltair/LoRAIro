# Tech-debt inventory plan (pre-change)

## Goal
- Inventory/remove/refactor candidates with focus on readability, efficiency, testability (compatibility excluded)

## Scope
- Include: src/lorairo + local_packages
- Exclude: tests/, docs/, examples/, prototypes/, gui/designer/

## R/E/T definitions
- R (Readability): 0–3 based on long functions, deep nesting, mixed responsibilities, unclear naming
- E (Efficiency): 0–3 based on looped IO/DB, repeated heavy work, N+1, UI blocking sync ops
- T (Testability): 0–3 based on mixed UI/IO/DB, hard dependencies, global state, side effects
- U (Usage impact): High=1.5, Med=1.0, Low=0.5
- Priority = (R + E + T) * U

## Concrete plan (before code changes)
1) Freeze target list (top 3 by priority) and define desired outcomes per file
   - Example targets: src/lorairo/gui/workers/annotation_worker.py, src/lorairo/database/db_repository.py, local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory.py
   - For each target, record: current pain points, success criteria (e.g., function length <=60, I/O separation), and test scope
2) Create per-target task checklist
   - Split long functions into smaller units
   - Separate UI/IO/DB concerns
   - Add/adjust tests to protect behavior
3) Implement in order (highest priority first)
   - After each target: run focused tests, update R/E/T scores, record deviations
4) Remove or relocate __main__ harnesses and stubs (if not used)
   - Move to scripts/ or tests/ or delete if obsolete
5) Final validation
   - Run relevant pytest subset, ensure no behavior regressions

## Priority tiers (R/E/T/U scoring)

### High (>=10)
- local_packages/image-annotator-lib/src/image_annotator_lib/api.py — R/E/T=3/3/3, U=1.5, P=13.5
- local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory.py — 3/3/3, U=1.5, P=13.5
- local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory_adapters/webapi_helpers.py — 3/3/3, U=1.5, P=13.5
- local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/openai_api_chat.py — 3/3/3, U=1.5, P=13.5
- local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/anthropic_api.py — 3/3/3, U=1.5, P=13.5
- src/lorairo/database/db_repository.py — 3/2/3, U=1.5, P=12.0
- local_packages/genai-tag-db-tools/src/genai_tag_db_tools/db/repository.py — 3/2/3, U=1.5, P=12.0
- src/lorairo/gui/workers/annotation_worker.py — 3/2/3, U=1.5, P=12.0
- src/lorairo/gui/workers/database_worker.py — 3/2/3, U=1.5, P=12.0
- src/lorairo/services/batch_processor.py — 3/2/3, U=1.5, P=12.0
- local_packages/image-annotator-lib/src/image_annotator_lib/core/registry.py — 2/3/3, U=1.5, P=12.0
- local_packages/image-annotator-lib/src/image_annotator_lib/core/base/annotator.py — 2/3/3, U=1.5, P=12.0
- local_packages/image-annotator-lib/src/image_annotator_lib/core/base/onnx.py — 2/3/3, U=1.5, P=12.0
- local_packages/image-annotator-lib/src/image_annotator_lib/core/model_factory_adapters/adapters.py — 2/3/3, U=1.5, P=12.0
- local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/google_api.py — 2/3/3, U=1.5, P=12.0
- local_packages/image-annotator-lib/src/image_annotator_lib/model_class/annotator_webapi/openai_api_response.py — 2/3/3, U=1.5, P=12.0
- src/lorairo/database/db_manager.py — 2/2/3, U=1.5, P=10.5
- local_packages/image-annotator-lib/src/image_annotator_lib/core/provider_manager.py — 1/3/3, U=1.5, P=10.5

### Medium (6–9.5)
- src/lorairo/services/image_processing_service.py — 3/1/2, U=1.5, P=9.0
- local_packages/image-annotator-lib/src/image_annotator_lib/model_class/tagger_tensorflow.py — 1/2/3, U=1.5, P=9.0
- src/lorairo/services/dataset_export_service.py — 2/1/1, U=1.5, P=6.0
- src/lorairo/gui/window/main_window.py — 3/1/2, U=1.0, P=6.0
- src/lorairo/gui/widgets/filter_search_panel.py — 3/1/2, U=1.0, P=6.0

### Low (<6)
- src/lorairo/services/ui_responsive_conversion_service.py — 3/1/1, U=1.0, P=5.0 (if heavily used, bump U to 1.5 → P=7.5)
- src/lorairo/gui/widgets/thumbnail.py — 2/1/2, U=1.0, P=5.0
- src/lorairo/gui/widgets/selected_image_details_widget.py — 1/1/2, U=1.0, P=4.0
- src/lorairo/gui/widgets/annotation_results_widget.py — 1/1/2, U=1.0, P=4.0
- src/lorairo/gui/widgets/batch_tag_add_widget.py — 1/1/2, U=1.0, P=4.0
- src/lorairo/gui/widgets/image_preview.py — 1/1/2, U=1.0, P=4.0
- src/lorairo/gui/state/dataset_state.py — 1/1/1, U=1.0, P=3.0
- local_packages/genai-tag-db-tools/src/genai_tag_db_tools/gui/services/tag_search_service.py — 0/1/1, U=1.5, P=3.0
- local_packages/genai-tag-db-tools/src/genai_tag_db_tools/utils/messages.py — 0/1/1, U=1.0, P=2.0
- src/lorairo/gui/widgets/filter.py — 1/0/1, U=0.5, P=1.0 (stub)
- UI __main__ harness blocks (24 files) — 1/0/0, U=0.5, P=0.5 (move to scripts)

## Pending
- Confirm which files are in the first refactor batch
- Confirm testing scope (fast tests only vs full suite)
