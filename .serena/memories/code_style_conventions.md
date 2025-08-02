# LoRAIro Code Style and Conventions

## Code Style Standards

### Formatting and Linting
- **Ruff** for linting and formatting (line-length: 108)
- **Quote style**: Double quotes (`"`)
- **Indent style**: Spaces (4 spaces)
- **Line ending**: Auto-detection

### Type Hints
- **Strict typing** enforced via mypy
- **Modern Python types** preferred: `list[str]` over `typing.List[str]`
- **Type hints required** for all functions and methods
- **Generic types** used appropriately for reusable components

### Import Organization
- **isort integration** via Ruff
- Standard library imports first
- Third-party imports second
- Local imports last
- Relative imports for same package

### Naming Conventions
- **Classes**: PascalCase (`ImageProcessor`)
- **Functions/Variables**: snake_case (`process_image`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_CONFIG`)
- **Private methods**: Leading underscore (`_internal_method`)
- **File names**: snake_case (`image_processor.py`)

### Documentation
- **Docstrings**: Required for public methods and classes
- **Type hints**: Serve as primary documentation
- **Comments**: Explain why, not what
- **Japanese comments**: Acceptable for domain-specific terms

### Architecture Patterns
- **Repository Pattern**: Database access abstraction
- **Service Layer**: Business logic separation
- **Dependency Injection**: Service composition
- **Worker Pattern**: Qt QRunnable/QThreadPool for async operations

### Error Handling
- **Custom exceptions** for domain-specific errors
- **Graceful degradation** with partial results
- **Comprehensive logging** with Loguru
- **Type-safe error propagation**

### File Organization
- **Module structure**: Logical grouping by functionality
- **Package hierarchy**: Clear separation of concerns
- **Resource files**: Centralized in dedicated directories
- **Generated code**: Excluded from linting (GUI designer files)

## Specific Patterns

### Database Operations
- Always use repository pattern
- Proper transaction management
- Type-safe SQLAlchemy relationships
- Handle connection failures gracefully

### GUI Components
- Qt signal/slot communication
- Background threads for long operations
- Proper resource cleanup
- User-friendly error messages

### Configuration
- TOML-based configuration files
- Environment variable overrides
- Type-safe configuration loading
- Default value fallbacks