# LoRAIro Active Development Context

## Current Focus (Updated: 2025/07/27 - API Compatibility + Unified Schema Complete)

### 🎯 Image-Annotator-Lib API Compatibility + Unified Validation Schema - 完了済み ✅

**実装期間**: 2025/07/26 - 2025/07/27

#### 🏆 主要成果

**1. Capability-based統一バリデーションスキーマ実装**
- `AnnotationResult`: 全モデルタイプ統合クラス
- `TaskCapability`: Tags/Captions/Scores能力定義
- 設定ファイルベースのcapability管理
- マルチモーダルLLM対応設計 (GPT-4o等)
- 生データ保持によるデバッグ性向上

**2. API互換性修正**
- パッチパス修正 (正しい__init__.py export使用)
- 破壊的変更による後方互換性排除
- image-annotator-lib統合レイヤー更新
- 実際のAPI構造との完全一致

**3. 型安全性とバリデーション強化**
- capability-basedフィールドバリデーション
- 実行時エラー防止機構
- 無効な組み合わせの事前検出
- 厳密な型チェックとPydantic活用

### Previous Development Activities  
- **Test Quality Improvement Complete (2025/07/23)**: Successfully implemented improved unit testing methodology, eliminated excessive mocking, added real bug detection capabilities
- **GUI Bug Fix Phase Complete (2025/07/22-23)**: Fixed all major GUI functionality issues including DB registration, search, thumbnail display, and file processing
- **Test Infrastructure Stabilization (2025/07/20)**: Fixed Qt GUI test fixtures, resolved generator object issues, improved test suite stability
- **PySide6 Worker System Complete (2025/07/19)**: Successfully completed comprehensive GUI redesign with MainWorkspaceWindow and Qt worker system

### Recently Completed Major Tasks (2025/07/23)
- **Test Quality Overhaul**: Rewritten unit tests following improved methodology - now catch real bugs instead of just passing
- **API Method Name Bug Fixes**: Fixed `register_image` → `register_original_image`, `get_image_by_id` → `get_image_metadata`
- **Import Path Bug Fixes**: Fixed `..database.db_core` → `...database.db_core` import errors
- **Search Functionality Restoration**: Fixed `include_untagged` logic that was causing search queries to be ignored
- **Auto-Registration Feature Restoration**: Restored missing auto-registration feature from old MainWindow
- **Thumbnail Loading Improvements**: Fixed import errors, increased loading threshold, improved display reliability
- **Tag/Caption File Processing**: Restored automatic .txt/.caption file registration functionality
- **Windows GUI Verification**: Confirmed dataset addition, image registration, and search functionality working correctly

### Previously Completed Major Tasks (2025/07/20-22)
- **Test Infrastructure Fix**: Fixed Qt GUI test fixtures (generator object issue in main_workspace_window_qt.py)
- **Legacy Test Cleanup**: Deleted 6 obsolete test files referencing removed MainWindow/Progress modules
- **Import Path Corrections**: Fixed 2 test files with incorrect import paths for relocated modules
- **Test Suite Stabilization**: Improved from ~41 failures to 352 passing tests (84% success rate)
- **Documentation Synchronization**: Updated memory.mdc, rules.mdc with current PySide6 worker architecture

### Previously Completed Major Tasks (2025/07/19)
- **MainWorkspaceWindow Implementation**: Workflow-centered 3-panel design with Qt auto-connection optimization
- **Worker System Relocation**: Moved worker system from services to gui directory for proper Qt dependency management
- **Legacy Component Removal**: Deleted 7 deprecated window files and cleaned up import dependencies
- **Architecture Documentation**: Comprehensive update of architecture.md, CLAUDE.md, technical.md

### Recently Completed Tasks  
1. **Requirements Clarification Session (2025/07/06)**: Systematically resolved 6 major ambiguous requirements through structured user dialogue
2. **Performance Requirements Finalized**: DB registration (1000 images/5 minutes), batch processing (100-image units)
3. **AI Integration Strategy Defined**: Model name direct specification, error skip handling, no cost controls
4. **Security Architecture Specified**: Plain-text config files, API key masking, policy violation tracking
5. **Architecture Decision Documented**: Hybrid controlled batch processing with clear performance targets
6. **Configuration Optimization (2025/07/07)**: Implemented DI + shared config pattern for immediate cross-instance updates

## Recent Major Changes

### Test Quality Methodology Improvement (2025-07-23)
- **Problem Identified**: User pointed out "テストは通るが実際の使用で問題が起きる" - tests were passing despite real bugs existing
- **Root Cause**: Excessive mocking of internal LoRAIro modules prevented tests from catching integration issues
- **Solution Implemented**: 
  - **Reduced Excessive Mocking**: Only mock external dependencies (filesystem, network, UI); use real objects for internal modules
  - **API Name Verification Tests**: Added tests that verify correct method names (`register_original_image` vs `register_image`)
  - **Import Path Verification Tests**: Added tests that catch import path errors (`...database.db_core` vs `..database.db_core`)
  - **Real Object Integration Tests**: Test actual module interactions instead of mocked behaviors
- **Files Created/Updated**:
  - `tests/unit/workers/test_database_worker.py`: Complete rewrite with improved methodology
  - `tests/unit/gui/window/test_main_workspace_window_improved.py`: New improved test suite
- **Impact**: Tests now catch real bugs that previously went undetected, significantly improving code reliability
- **Validation**: All improved tests pass and would have detected the actual bugs encountered during development

### GUI Functionality Bug Fix Phase (2025-07-22 to 2025-07-23)
- **Major Bugs Fixed**:
  - **DB Registration Not Working**: Fixed button visibility and auto-registration workflow
  - **API Method Name Errors**: Corrected `register_image` → `register_original_image`, `get_image_by_id` → `get_image_metadata`
  - **Import Path Errors**: Fixed `..database.db_core` → `...database.db_core` in database_worker.py
  - **Search Functionality Broken**: Fixed `include_untagged=True` logic that was ignoring search queries
  - **Missing Auto-Registration**: Restored auto-registration feature from old MainWindow using git history analysis
  - **Thumbnail Display Issues**: Fixed import errors and loading thresholds
  - **Tag/Caption Processing Missing**: Restored automatic .txt/.caption file registration
- **Resolution Process**: Systematic debugging with user feedback and log analysis
- **Windows Validation**: Confirmed all functionality working correctly in Windows GUI environment
- **Files Modified**: `main_workspace_window.py`, `database_worker.py`, `filter_search_panel.py`, `thumbnail_enhanced.py`

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

### Current Challenges (2025/07/20)
- **Worker System Integration**: Resolve 41 remaining test failures related to threading/async coordination
- **Database Integration**: Fix schema and migration issues affecting ~15 tests
- **GUI Component Initialization**: Address initialization errors in MainWorkspaceWindow integration
- **Japanese Text Processing**: Resolve BDD step definition failures with Japanese text handling
- **Test Coverage Optimization**: Maintain >75% coverage while fixing integration issues

### Future Considerations
- **Performance Optimization**: Monitor and optimize for large dataset processing
- **Plugin Architecture**: Consider extensible architecture for custom AI providers
- **Cloud Integration**: Potential cloud storage and processing capabilities

## Next Steps

### Immediate Actions (Current Session - 2025/07/20)
1. **Worker System Coordination Fix**: Resolve threading and async coordination issues in integration tests
2. **Database Integration Repair**: Fix schema and migration-related test failures
3. **GUI Initialization Debugging**: Address MainWorkspaceWindow initialization errors in tests
4. **Japanese Text Processing**: Resolve BDD step definition issues with database management tests

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

### Testing Status (Updated: 2025/07/20)
- **Test Framework**: pytest with proper markers and coverage
- **Test Categories**: Unit, integration, and GUI tests defined
- **Current Results**: 352 passing, 41 failing, 25 errors (~418 total tests)
- **Success Rate**: 84% (significant improvement from previous state)
- **Performance**: ~6.7 minutes runtime (acceptable for CI/CD)
- **Coverage Target**: 75% minimum coverage maintained
- **Key Fixes**: Qt GUI fixtures, import paths, legacy test removal
- **Remaining Issues**: Worker coordination, DB integration, GUI initialization

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