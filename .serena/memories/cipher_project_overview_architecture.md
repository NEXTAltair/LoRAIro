# LoRAIro Project Overview & Architecture (Cipher統合記録)

**移行元**: Cipher長期記憶 (2026-01-28にSerenaへ移行)

---

## Project Purpose
AI-powered LoRA image dataset preparation tool (Python/PySide6)

## Key Features
- Image processing automation (resize, format conversion, crop)
- Multi-provider AI annotation (GPT-4, Claude, Gemini, local models)
- SQLite metadata storage with search
- Batch processing, PySide6 GUI, systematic file organization

## Architecture

### Data Layer
- db_core.py: SQLite connection
- schema.py: SQLAlchemy ORM
- db_repository.py: Data access
- db_manager.py: High-level operations

### Service Layer
- Business: ImageProcessingService, ConfigurationService, AnnotatorLibraryAdapter
- GUI: WorkerService, SearchFilterService

### GUI Layer
- MainWorkspaceWindow: 688 lines (58.2% reduced)
- DatasetStateManager: Centralized state
- Workers: QRunnable-based background tasks

### Integration
- image-annotator-lib: annotate(), PHashAnnotationResults
- genai-tag-db-tools: search_tags(), tag normalization

## Database Design
- No UNIQUE constraints: history preservation
- tag_id: External reference (no FK constraint)
- Session: Context manager-based method-level
- SQLite WAL mode for concurrent access

## Data Storage Pattern
```
lorairo_data/project_name_YYYYMMDD_NNN/
├── image_database.db
└── image_dataset/
    ├── original_images/YYYY/MM/DD/
    └── 1024/
```
