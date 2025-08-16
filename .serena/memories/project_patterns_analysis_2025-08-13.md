# LoRAIro Project Patterns and Structure Analysis

## Directory Organization Patterns

### Root Level Structure
```
LoRAIro/
├── src/lorairo/              # Modern implementation (active)
├── local_packages/           # Local submodules
│   ├── genai-tag-db-tools/  # Tag database management  
│   └── image-annotator-lib/ # AI annotation providers
├── config/                   # Configuration files (.toml)
├── tests/                    # Test suite organization
├── docs/                     # Documentation
├── scripts/                  # Build and setup scripts
├── cipher/                   # MCP integration
└── tasks/                    # Development task management
```

### Source Code Organization Patterns

#### Layered Architecture Pattern
```
src/lorairo/
├── main.py                   # Application entry point
├── database/                 # Data layer
│   ├── schema.py            # SQLAlchemy models
│   ├── db_repository.py     # Repository pattern
│   ├── db_manager.py        # Transaction management
│   └── db_core.py           # Core database utilities
├── services/                 # Business logic layer
│   ├── service_container.py # Dependency injection
│   ├── configuration_service.py
│   ├── image_processing_service.py
│   └── annotation_service.py
├── gui/                      # Presentation layer
│   ├── window/              # Main application windows
│   ├── widgets/             # Reusable UI components
│   ├── services/            # GUI-specific services
│   ├── workers/             # Background processing
│   └── state/               # State management
├── storage/                  # File system abstraction
└── utils/                    # Shared utilities
```

#### GUI Architecture Patterns

**Widget Component Pattern:**
- Self-contained UI components in `gui/widgets/`
- Designer files (`.ui`) auto-generate base classes
- Implementation classes extend designer classes
- Signal/slot communication between components

**Worker Pattern for Asynchronous Operations:**
- QRunnable-based workers in `gui/workers/`
- Base worker class provides common functionality
- Progress reporting and cancellation support
- Thread pool management via WorkerService

**Service Layer Pattern in GUI:**
- GUI-specific services in `gui/services/`
- Separation of GUI logic from business logic
- Clean interfaces for complex operations

### Configuration Patterns

#### Multi-file Configuration System
```
config/
├── lorairo.toml              # Main application configuration
├── annotator_config.toml     # AI provider settings
└── available_api_models.toml # Model registry
```

#### Environment-Specific Setup
- Cross-platform virtual environment management
- `.venv_linux` for development/testing
- `.venv_windows` for GUI execution
- Platform-specific dependency handling

### Testing Patterns

#### Test Organization Structure
```
tests/
├── conftest.py              # Shared test fixtures
├── unit/                    # Unit tests by module
├── integration/             # Integration tests
├── gui/                     # GUI-specific tests
├── performance/             # Performance benchmarks
├── resources/              # Test data and fixtures
├── features/               # BDD feature files
└── step_defs/             # BDD step definitions
```

#### Cross-Platform Testing Support
- Headless GUI testing on Linux (QT_QPA_PLATFORM=offscreen)
- Native window testing on Windows
- Container-based CI/CD support

### Data Storage Patterns

#### Project Organization Pattern
```
lorairo_data/
└── project_name_YYYYMMDD_NNN/
    ├── image_database.db
    └── image_dataset/
        ├── original_images/
        │   └── YYYY/MM/DD/source_dir/
        ├── 1024/                # Resolution-specific dirs
        └── batch_request_jsonl/
```

#### Database Design Pattern
- One SQLite database per project
- Date-based directory organization
- Unicode project name support
- Isolation for data extraction workflows

### Integration Patterns

#### Local Package Integration
- Git submodules managed via `uv.sources`
- Editable installs during `uv sync`
- Direct Python imports for tight integration
- Independent versioning and development

#### AI Provider Abstraction
- Multi-provider support (OpenAI, Anthropic, Google, Local)
- Unified interface through `image-annotator-lib`
- Provider-specific configuration management
- Structured result format (`PHashAnnotationResults`)

### Development Workflow Patterns

#### Command-Based Development
```
/.claude/commands/
├── check-existing.md        # Analysis phase
├── plan.md                 # Planning phase  
├── implement.md            # Implementation phase
└── test.md                 # Validation phase
```

#### Agent-Based Task Automation
- Investigation agent for codebase analysis
- Solutions agent for multi-approach problem solving
- Code-formatter agent for quality assurance
- Library-research agent for technology integration

### Code Style and Quality Patterns

#### Consistent Code Standards
- Ruff formatting (line length: 108)
- Type hints required for all functions
- Modern Python types (list/dict over typing.List/Dict)
- Pathlib over os for path operations

#### Architecture Quality Patterns
- Repository pattern for data access
- Service layer for business logic
- Dependency injection via ServiceContainer
- Clean separation of concerns

## Key Insights from Pattern Analysis

### Strengths
1. **Clear layered architecture** with well-defined boundaries
2. **Consistent patterns** across similar components
3. **Platform-aware design** supporting Windows and Linux
4. **Modern Python practices** with type hints and pathlib
5. **Comprehensive testing strategy** with multiple test types
6. **Flexible configuration system** supporting multiple use cases

### Areas for Continued Attention
1. **Local package integration** requires careful dependency management
2. **Cross-platform GUI testing** needs specialized handling
3. **AI provider management** requires robust error handling
4. **Large dataset processing** needs memory-efficient patterns

### Pattern Recommendations for Future Development
1. Continue using repository pattern for new data access needs
2. Extend worker pattern for new background operations
3. Maintain service layer separation for complex business logic
4. Use widget component pattern for new GUI features
5. Follow existing configuration file patterns for new settings