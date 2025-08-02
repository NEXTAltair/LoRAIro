# LoRAIro Task Completion Checklist

## Code Quality Requirements

### Before Submitting Code Changes
- [ ] **Format code**: `ruff format src/ tests/`
- [ ] **Fix linting**: `ruff check src/ tests/ --fix`
- [ ] **Type checking**: `mypy src/` (strict mode enabled)
- [ ] **Run tests**: `pytest` (all tests must pass)
- [ ] **Coverage check**: Minimum 75% test coverage required

### Code Standards Verification
- [ ] **Type hints**: All functions have proper type annotations
- [ ] **Modern Python**: Use `list[str]` instead of `typing.List[str]`
- [ ] **Error handling**: Appropriate exception handling and logging
- [ ] **Documentation**: Public methods have docstrings
- [ ] **Architecture patterns**: Follow repository/service/worker patterns

## Testing Requirements

### Test Categories to Run
- [ ] **Unit tests**: `pytest -m unit` (fast, isolated tests)
- [ ] **Integration tests**: `pytest -m integration` (database/service tests)
- [ ] **GUI tests**: `pytest -m gui` (interface component tests)
- [ ] **Coverage report**: `pytest --cov=src --cov-report=html`

### Test Quality Checks
- [ ] **New functionality**: Tests written for new features
- [ ] **Edge cases**: Boundary conditions tested
- [ ] **Error scenarios**: Exception paths verified
- [ ] **Mock usage**: External dependencies properly mocked

## Database Operations

### Migration Management
- [ ] **Schema changes**: Alembic migration created if needed
- [ ] **Migration tested**: `alembic upgrade head` works correctly
- [ ] **Data integrity**: Existing data preserved through migration
- [ ] **Rollback tested**: `alembic downgrade` functions properly

### Repository Pattern
- [ ] **Data access**: All database operations use repository pattern
- [ ] **Transactions**: Proper transaction boundaries maintained
- [ ] **Error handling**: Database errors handled gracefully
- [ ] **Type safety**: SQLAlchemy relationships properly typed

## GUI Development

### Qt Best Practices
- [ ] **Signal/slot pattern**: Proper Qt communication patterns used
- [ ] **Background threads**: Long operations use worker threads
- [ ] **Resource cleanup**: Proper disposal of Qt resources
- [ ] **Error feedback**: User-friendly error messages displayed

### State Management
- [ ] **Centralized state**: DatasetStateManager used for application state
- [ ] **Event propagation**: State changes properly broadcast
- [ ] **GUI updates**: Interface reflects current application state
- [ ] **Performance**: No GUI blocking during operations

## Documentation Updates

### Code Documentation
- [ ] **Docstrings**: Public APIs documented with examples
- [ ] **Comments**: Complex logic explained with comments
- [ ] **Type annotations**: Self-documenting code through types
- [ ] **Architecture**: Major structural changes documented

### User-Facing Documentation
- [ ] **Feature changes**: User-visible changes documented
- [ ] **Configuration**: New settings documented with examples
- [ ] **Workflow impact**: Changes to user workflows explained
- [ ] **Migration guide**: Breaking changes include migration instructions

## Performance and Security

### Performance Considerations
- [ ] **Memory usage**: Large datasets handled efficiently
- [ ] **Database queries**: Optimized for performance
- [ ] **GUI responsiveness**: No blocking operations in main thread
- [ ] **Resource management**: Proper cleanup of system resources

### Security Checks
- [ ] **API keys**: No secrets committed to repository
- [ ] **User input**: Proper validation and sanitization
- [ ] **File operations**: Safe handling of user-provided paths
- [ ] **Error messages**: No sensitive information leaked in errors

## Deployment Readiness

### Cross-Platform Compatibility
- [ ] **Linux support**: Code works in development containers
- [ ] **Windows support**: GUI functionality verified on Windows
- [ ] **Dependencies**: Platform-specific requirements documented
- [ ] **Environment**: Cross-platform environment setup tested

### Integration Testing
- [ ] **Local packages**: Changes compatible with submodules
- [ ] **AI services**: External API integrations function correctly
- [ ] **File system**: Storage operations work across platforms
- [ ] **Configuration**: Settings load and persist correctly

## Final Verification

### Pre-Commit Checklist
- [ ] **Git status clean**: No unintended files staged
- [ ] **Commit message**: Clear, descriptive commit message
- [ ] **Branch state**: Working on correct feature branch
- [ ] **Remote sync**: Local branch up to date with remote

### Quality Gate
- [ ] **All tests pass**: No failing tests in test suite
- [ ] **No linting errors**: Clean ruff and mypy output
- [ ] **Coverage maintained**: Test coverage at or above 75%
- [ ] **Documentation current**: All documentation reflects changes