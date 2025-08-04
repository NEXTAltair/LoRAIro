# Legacy Cleanup Plan: GUI-side AnnotatorLibAdapter Direct Usage Removal (Immediate Delete Policy)

Scope
- Target area: GUI widgets/services referencing AnnotatorLibAdapter directly
- Policy: No quarantine, immediate delete/refactor on branch feature/cleanup-legacy
- Out of scope for this phase: Core services under src/lorairo/services except mechanical signature alignment

Findings (evidence gathered via symbol search)
1) Direct deprecated usage path in widget
   - src/lorairo/gui/widgets/annotation_control_widget.py
     - from ...services.annotator_lib_adapter import AnnotatorLibAdapter (line ~22)
     - def set_annotator_adapter(self, adapter: AnnotatorLibAdapter)
     - In load_models():
       - elif self.annotator_adapter: logger.warning("Using AnnotatorLibAdapter directly (deprecated, use SearchFilterService)")
       - Direct call: self.annotator_adapter.get_available_models_with_metadata()
     - Conclusion: This fallback path is explicitly marked deprecated and should be removed. Widget must rely exclusively on SearchFilterService.

2) Widget exposing Optional AnnotatorLibAdapter
   - src/lorairo/gui/widgets/model_selection_widget.py
     - from ...services.annotator_lib_adapter import AnnotatorLibAdapter
     - __init__(..., annotator_adapter: AnnotatorLibAdapter | None = None)
     - load_models(): warns "AnnotatorLibAdapter not available" then early return
     - Conclusion: This widget still carries legacy dependency. Should be refactored to use SearchFilterService (or a dedicated provider service) and drop adapter references.

3) GUI services importing adapter
   - src/lorairo/gui/services/model_selection_service.py
     - from ...services.annotator_lib_adapter import AnnotatorLibAdapter
     - __init__(self, annotator_adapter: AnnotatorLibAdapter | None = None)
     - load_models(): warns and returns [] when adapter missing, logs summary on success
     - Conclusion: Service is adapter-aware; align to SearchFilterService as single source of truth or make adapter dependency injected via ModelSyncService facade; for GUI phase cleanup, plans prefer SearchFilterService centralization.

4) SearchFilterService also imports adapter
   - src/lorairo/gui/services/search_filter_service.py
     - from ...services.annotator_lib_adapter import AnnotatorLibAdapter
     - __init__(..., annotator_adapter: "AnnotatorLibAdapter | None" = None)
     - get model list path logs if adapter missing and calls adapter for metadata
     - Conclusion: This service is the designated migration hub; it tolerates adapter but unified GUI should only touch this service (no widget-level adapter usage). No delete here; keep as integration seam until core Phase 4 completes.

Non-GUI references (context only)
- src/lorairo/services/annotator_lib_adapter.py defines MockAnnotatorLibAdapter and AnnotatorLibAdapter, plus create_* factories
- src/lorairo/services/service_container.py provides integration path and fallback
- These are outside current phase; we do not delete core adapters now.

Risks
- If any UI currently sets annotator_adapter into widgets, removing parameters may break instantiation paths. Need to confirm widget constructors usage.
- Tests may rely on adapter-optional paths; we will scan tests for references and update accordingly.

Plan of Record (PoR) for Phase GUI-Adapter Cleanup
Branch: feature/cleanup-legacy

Step A: Remove widget-level adapter coupling
A1) annotation_control_widget.py
   - Remove import of AnnotatorLibAdapter
   - Remove __init__ parameter annotator_adapter and the field self.annotator_adapter
   - Remove set_annotator_adapter()
   - In load_models(), delete deprecated fallback branch using annotator_adapter. Enforce SearchFilterService presence; if absent, show empty list with info log.
   - Ensure set_search_filter_service() is the only injection path.
A2) model_selection_widget.py
   - Remove import of AnnotatorLibAdapter
   - Remove __init__ parameter annotator_adapter and any field usage
   - Refactor load_models() to use an injected service (preferred: SearchFilterService or a lightweight provider facade). If no service is currently wired, convert to pure-UI and delegate model-list to parent coordinator.

Step B: Align GUI services usage
B1) model_selection_service.py (short-term)
   - If only used by widgets, either: (Option 1) collapse into SearchFilterService calls, or (Option 2) keep as façade but remove hard dependency from widgets and have higher-level controller wire it.
   - Do not delete service yet; mark for consolidation with SearchFilterService in a later pass after widget decoupling.
B2) search_filter_service.py (no deletion)
   - Keep adapter-aware implementation as backend seam. Widgets must only call this service.

Step C: References and tests
C1) Repo-wide search for imports from ...services.annotator_lib_adapter in GUI paths; ensure no widget or GUI-layer consumers remain.
C2) Adjust any UI factory or window/controller that passed adapter to widgets. Replace with SearchFilterService injection.
C3) Update tests under tests/unit/gui/widgets/ and tests/integration/gui/ accordingly (constructor signature changes, interaction path via service).

Acceptance Criteria
- No widget under src/lorairo/gui/widgets imports or references AnnotatorLibAdapter.
- AnnotationControlWidget no longer contains the deprecated direct-call branch and builds/runs relying solely on SearchFilterService.
- ModelSelectionWidget no longer accepts/uses adapter; compiles and runs with a service or delegated data source.
- All tests referencing widget constructors are updated and green.

Rollback
- If breakage occurs due to missing service wiring, temporarily inject a thin adapter-backed service into SearchFilterService at controller level rather than reintroducing adapter into widgets.

Next Phase (out of current scope)
- Consolidate ModelSelectionService responsibilities into SearchFilterService or controller-level orchestration to reduce duplication.
- Review core adapter factory usage to ensure production/mock selection occurs only in service_container and not in GUI layer.
