# LoRAIro Technology Stack

## Programming Language
- **Python 3.12** (strict requirement, <3.13)

## Core Frameworks
- **PySide6 (>=6.8.0.2)** - Qt-based GUI framework
- **SQLAlchemy (>=2.0.40)** - Database ORM
- **Alembic (>=1.15.2)** - Database migrations
- **Loguru (>=0.7.2)** - Structured logging

## AI/ML Libraries
- **OpenAI (>=0.10.0)** - GPT models for annotation
- **torch** - PyTorch for ML models
- **Pillow** - Image processing
- **opencv-python** - Computer vision operations
- **numpy, scipy** - Numerical computing

## Image Processing
- **ImageHash** - Perceptual hashing
- **spandrel** - Image upscaling
- **rembg (>=2.0.67)** - Background removal

## GUI Components
- **superqt (>=0.6.7)** - Enhanced Qt widgets

## Development Tools
- **uv** - Package manager (replaces pip/poetry)
- **ruff** - Linting and formatting (line-length: 108)
- **mypy** - Type checking with strict mode
- **pytest** - Testing framework with coverage
- **pytest-qt** - GUI testing
- **pytest-bdd** - Behavior-driven development

## Local Dependencies
- **genai-tag-db-tools** - Tag database management (submodule)
- **image-annotator-lib** - Multi-provider AI annotation (submodule)

## Database
- **SQLite** - Local database storage
- **WAL mode** - Write-Ahead Logging for concurrency

## Configuration
- **TOML** - Configuration file format
- **Environment variables** - Runtime configuration