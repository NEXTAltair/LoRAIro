# LoRAIro Active Development Context

## Current Focus

### Primary Development Activities
- **Project Structure Reorganization**: Standardizing documentation and configuration structure based on image-annotator-lib patterns
- **Configuration Management**: Implementing consistent TOML-based configuration across all components
- **Local Package Integration**: Optimizing integration with genai-tag-db-tools and image-annotator-lib submodules
- **Development Environment**: Ensuring smooth uv-based dependency management and development workflow

### Recently Completed Tasks  
1. **Documentation Structure Cleanup**: Successfully reorganized docs/ directory to match modern standards
2. **Context Structure Migration**: Successfully migrated to integrated .cursor/rules/ and structured docs/tasks approach
3. **Configuration Standardization**: Aligned configuration patterns with submodule best practices
4. **Development Rules Setup**: Established .cursor and .roo development rules for consistent AI assistance

## Recent Major Changes

### Documentation Reorganization (2025-06-21)
- **Removed**: Old Plan/ directory with outdated planning documents
- **Removed**: Obsolete genai_tag_db_tools_api_plan.md
- **Created**: Comprehensive architecture.md with detailed system design
- **Created**: Technical specification in technical.md
- **Created**: Product requirements document (product_requirement_docs.md)
- **Updated**: CLAUDE.md with latest development commands and project structure

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
1. **Complete Context Documentation**: Validate all context documentation is properly structured
2. **Validate Configuration**: Ensure all TOML configurations are properly structured and documented
3. **Test Development Workflow**: Verify all development commands work correctly
4. **Update Documentation**: Ensure all documentation reflects current structure and capabilities

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