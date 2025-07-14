# LoRAIro Active Development Context

## Current Focus (Updated: 2025/07/12)

### Primary Development Activities
- **Image Processor Refactoring Complete (2025/07/12)**: Successfully completed comprehensive refactoring of `src/lorairo/editor/image_processor.py` with dependency injection, CPU-fixed processing, and AutoCrop optimization
- **Claude Code Hooks Enhancement Complete (2025/07/12)**: Implemented automatic LoRAIro environment command transformation for pytest, ruff, mypy, python, and uv commands
- **DevContainer Update Required**: jq package added to Dockerfile for hooks functionality - container rebuild required
- **Testing Phase Ready**: Ready to resume comprehensive testing after DevContainer rebuild

### Recently Completed Tasks  
1. **Requirements Clarification Session (2025/07/06)**: Systematically resolved 6 major ambiguous requirements through structured user dialogue
2. **Performance Requirements Finalized**: DB registration (1000 images/5 minutes), batch processing (100-image units)
3. **AI Integration Strategy Defined**: Model name direct specification, error skip handling, no cost controls
4. **Security Architecture Specified**: Plain-text config files, API key masking, policy violation tracking
5. **Architecture Decision Documented**: Hybrid controlled batch processing with clear performance targets
6. **Configuration Optimization (2025/07/07)**: Implemented DI + shared config pattern for immediate cross-instance updates

## Recent Major Changes

### Upscaler Information Recording Implementation (2025-07-10)
- **Feature**: Implemented comprehensive upscaler information recording system
- **Database Extension**: Added `upscaler_used` column to ProcessedImage table with Alembic migration
- **Metadata Tracking**: Enhanced ImageProcessingManager to return processing metadata tuples
- **Service Integration**: Updated ImageProcessingService to record upscaler information and add upscaled tags
- **Dependency Injection**: Refactored ImageDatabaseManager to use explicit dependency injection
- **Configuration Fix**: Resolved hardcoded upscaler issue in automatic 512px generation
- **Testing**: Added comprehensive unit and integration tests (11 test cases)
- **Benefits**: 
  - Transparent upscaler tracking for all processed images
  - Consistent configuration usage across manual and automatic processing
  - Better separation of concerns with explicit dependencies
  - Complete audit trail of image processing operations

### ImageProcessingManager Architecture Fix (2025-07-09)
- **Problem**: ImageProcessingManager was cached with stale resolution, causing GUI resolution changes not to affect processing
- **Solution**: Removed persistent instance caching, implemented temporary instance creation with current GUI resolution
- **Changes Made**:
  - Modified `ImageProcessingService.create_processing_manager()` to create temporary instances
  - Updated `edit.py` to pass current resolution to processing service
  - Removed filename-based duplicate detection in favor of pHash-only approach
  - Implemented lazy directory creation in FileSystemManager
- **Impact**: GUI resolution changes now properly reflect in image processing pipeline
- **Performance**: pHash-only duplicate detection improves processing speed and accuracy

### Thumbnail Generation Strategy (2025-07-09)
- **Decision**: Use existing 512px directory for thumbnail purposes instead of creating new thumbnails directory
- **Approach**: Automatically generate 512px images during DB registration (`register_original_image`)
- **Benefits**: 
  - UI display acceleration using pre-generated 512px images
  - No additional directory structure needed
  - Consistent with existing resolution management
  - Cache effect for 512px resolution selection
- **Implementation Plan**: Add 512px image generation to `ImageDatabaseManager.register_original_image()`

### Batch Processing Design Decision (2025-07-08)
- **Decision**: Adopted simple implementation approach for batch processing optimization
- **Approach**: Minimal changes to existing Worker + new dedicated batch function
- **Impact**: 1 new file (`simple_batch_processor.py`), 3 file modifications (progress.py, main_window.py)
- **Benefits**: Half-day implementation, maintains existing stability, meets 1000 images/5min performance target
- **Alternative Considered**: Complex worker hierarchy, hybrid approaches - rejected for complexity
- **Implementation**: Enhanced progress reporting (current/total/filename), improved cancellation, batch statistics

### Requirements Clarification and Documentation Update (2025-07-06)
- **Updated**: product_requirement_docs.md with clarified NFR1, FR1, FR5, NFR5, US1.2 requirements
- **Enhanced**: architecture.md with hybrid controlled batch processing architecture 
- **Specified**: Performance targets (DB registration: 1000 images/5 minutes, 100-image batches)
- **Defined**: AI integration strategy (model name specification, skip error handling)
- **Established**: Security policies (encrypted config files, API key masking, policy violation tracking)
- **Documented**: All decisions with 2025/07/06 clarification timestamps

### Development Rules Implementation
- **Created**: .cursor/rules/ directory with comprehensive development guidelines
  - `rules.mdc`: Core development principles and workflow
  - `memory.mdc`: Project memory bank and context management
  - `plan.mdc`: Structured planning guidelines
  - `implement.mdc`: Implementation best practices
  - `debug.mdc`: Debugging procedures and troubleshooting
- **Created**: .roo/ symbolic links for cross-platform development tool support

### Project Structure Modernization
- **Standardized**: Directory structure following established patterns
- **Improved**: Local package integration through uv.sources configuration
- **Enhanced**: Development environment setup with proper dependency management

## Current Architecture State

### Core Components Status
- **Main Application**: Stable foundation with Qt-based GUI architecture
- **Service Layer**: Well-defined services for image processing, annotation, and configuration
- **Database Layer**: SQLAlchemy-based repository pattern with Alembic migrations
- **AI Integration**: Multi-provider support through image-annotator-lib

### Local Package Integration
- **genai-tag-db-tools**: Tag database management utilities
  - Status: Integrated via uv.sources
  - Entry point: `tag-db` command
  - Usage: Tag taxonomy and database operations
- **image-annotator-lib**: Core annotation functionality
  - Status: Integrated as Python library
  - Features: Multi-provider AI annotation, local ML models
  - Recent updates: Latest structure patterns adopted

### Technology Stack
- **Package Manager**: uv for fast dependency resolution and management
- **GUI Framework**: PySide6 with Qt Designer integration
- **Database**: SQLite with SQLAlchemy ORM and Alembic migrations
- **AI Providers**: OpenAI, Anthropic, Google through image-annotator-lib
- **Local Models**: CLIP, DeepDanbooru via image-annotator-lib integration

## Development Workflow

### Current Development Commands
```bash
# Environment setup
uv sync --dev

# Application execution
lorairo
python -m lorairo.main

# Testing
pytest
pytest -m unit
pytest -m integration
pytest -m gui

# Code quality
ruff check
ruff format
mypy src/

# Database operations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Configuration Management
- **Main Config**: `config/lorairo.toml` - Application settings and AI provider configuration
- **Environment Variables**: API keys and development flags
- **Local Package Config**: Managed through uv.sources in pyproject.toml

## Known Issues and Considerations

### Resolved Issues
- **Context Structure**: Successfully migrated to integrated .cursor/rules/ and structured docs/tasks approach
- **Development Rules**: Established comprehensive guidelines for AI-assisted development
- **Documentation Consistency**: Achieved alignment between main project and submodule documentation patterns

### Current Challenges
- **Documentation Consistency**: Maintain consistency across all documentation files
- **Testing Coverage**: Ensure all components maintain >75% test coverage
- **Configuration Validation**: Implement comprehensive configuration validation and error handling

### Future Considerations
- **Performance Optimization**: Monitor and optimize for large dataset processing
- **Plugin Architecture**: Consider extensible architecture for custom AI providers
- **Cloud Integration**: Potential cloud storage and processing capabilities

## Next Steps

### Immediate Actions (Current Session)
1. **Implement Simple Batch Processing**: Create `simple_batch_processor.py` and modify Worker components
2. **Enhanced Progress Reporting**: Add batch-specific progress signals (current/total/filename)
3. **Main Window Integration**: Update `dataset_dir_changed()` to use new batch processing
4. **Testing and Validation**: Verify 1000 images/5min performance target

### Short-term Goals (Next Few Sessions)
1. **Enhanced Testing**: Expand test coverage and add integration tests for local packages
2. **Performance Monitoring**: Implement performance tracking for large batch operations
3. **User Experience**: Improve GUI responsiveness and error handling
4. **Documentation Completion**: Finalize all documentation and ensure consistency

### Medium-term Objectives (Next Weeks)
1. **Feature Enhancement**: Add advanced filtering and search capabilities
2. **Export Functionality**: Implement comprehensive export formats for various ML frameworks
3. **Quality Metrics**: Enhance quality assessment and scoring capabilities
4. **Community Preparation**: Prepare for potential open-source release

## Development Environment Status

### Dependencies Status
- **Core Dependencies**: All packages properly managed through uv
- **Local Packages**: Both submodules integrated and functioning
- **Development Tools**: Ruff, mypy, pytest all configured and working

### Configuration Status
- **Application Config**: Well-structured TOML configuration
- **AI Provider Setup**: Ready for multiple provider integration
- **Database Config**: Alembic migrations and schema management ready

### Testing Status
- **Test Framework**: pytest with proper markers and coverage
- **Test Categories**: Unit, integration, and GUI tests defined
- **Coverage Target**: 75% minimum coverage maintained

## Historical Context

### Relevant Historical Information from Project Development

**Project Foundation (2025-04-14 to 2025-04-17)**
- AI annotation functionality delegated to `image-annotator-lib` for separation of concerns
- Database migration from SQLite to SQLAlchemy ORM completed with Alembic migrations
- Project structure reorganized to src/lorairo layout following Python standards
- Configuration management refactored from ConfigManager singleton to ConfigurationService with dependency injection
- GUI components refactored to separate business logic from presentation layer
- Documentation structure aligned with 3-tier architecture (interfaces, application, core)

**Key Architectural Decisions**
- Adopted uv as package manager for speed and usability
- Implemented service layer pattern with dependency injection
- Separated AI annotation concerns to external library (`image-annotator-lib`)
- Established SQLAlchemy-based database layer with proper migrations
- Implemented ConfigurationService to replace problematic singleton pattern

**Development Patterns Established**
- Code quality: PEP 8 compliance, modern type hints, pathlib usage
- Testing: pytest with BDD approach using pytest-bdd
- Documentation: Google-style docstrings, comprehensive module documentation
- Error handling: Specific exception catching with clear error messages
- Architecture: Single responsibility principle, proper encapsulation

This active context provides a comprehensive view of current development state and immediate priorities for the LoRAIro project.