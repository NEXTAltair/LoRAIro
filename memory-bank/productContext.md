# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-04-14 03:12:05 - Log of updates made will be appended as footnotes to the end of this file.

* **Important:** When proceeding with the project, **always refer** to the specifications in `docs/specs/` and the plans in `docs/Plan/`.

## Project Overview

LoRAIro is a Python tool developed to address the developer's challenges in creating and managing image datasets for LoRA training (e.g., dataset scattering, cumbersome manual tasks like resizing and tagging). Since no existing tool with the necessary features was found, it aims to automate and streamline the entire dataset preparation process by integrating functionalities the developer needs: image processing, AI-powered automatic tagging and captioning, dataset management using SQLAlchemy (migrated from SQLite), and GUI operation via PySide6.

## Project Goal

* Automate and streamline the creation of image datasets for LoRA training.

## Key Features

* Image processing, AI tagging/captioning (via library), DB management, GUI

## Overall Architecture

* Python-based, PySide6 GUI, SQLAlchemy DB (SQLite target), external AI API integration (via library)

## Key Technologies

*   **Core:** Python (>=3.12)
*   **GUI:** PySide6, superqt
*   **Image Processing:** Pillow, OpenCV, NumPy, ImageHash, Spandrel
*   **AI Integration:** image-annotator-lib (handles various backends like Google Generative AI, Anthropic, OpenAI)
*   **Database:** SQLAlchemy, Alembic (Target: SQLite)
*   **ML/Parallel:** pytorch-lightning, joblib
*   **Configuration:** TOML, .env
*   **Custom Libraries:** genai-tag-db-tools
*   **Development Tools:** Git, uv, hatchling, Ruff, pytest

---
*Footnotes:*
*(Optional)[YYYY-MM-DD HH:MM:SS] - [Summary of Change]*
2025-04-14 03:12:05 - Initial population based on user input and pyproject.toml.
2025-04-16 13:11:44 - Added note emphasizing the importance of referring to docs/specs and docs/Plan. Updated Key Technologies and Architecture based on recent decisions (SQLAlchemy, Alembic, .env, library delegation).
2025-04-16 13:12:20 - Unified content language to English. Updated Project Overview and Key Features to reflect recent changes (SQLAlchemy migration, library delegation).
2025-04-17 17:26:09 - Updated documentation structure in `docs/` to align with the 3-tier architecture (interfaces, application, core). See `decisionLog.md` for details.