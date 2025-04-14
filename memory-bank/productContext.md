# Product Context

This file provides a high-level overview of the project and the expected product that will be created. Initially it is based upon projectBrief.md (if provided) and all other available project-related information in the working directory. This file is intended to be updated as the project evolves, and should be used to inform all other modes of the project's goals and context.
2025-04-14 03:12:05 - Log of updates made will be appended as footnotes to the end of this file.

*

## Project Overview

LoRAIroは、開発者自身のLoRA学習用画像データセット作成・管理における課題（データセットの散逸、リサイズやタグ付け等の手作業の煩雑さ）を解決するために開発されたPythonツールです。必要な機能を持つ既存ツールが見つからなかったため、画像処理、AIによる自動タグ付け・キャプション生成、SQLiteを用いたデータセット管理、そしてPySide6によるGUI操作といった、開発者が必要とする機能を統合的に提供し、データセット準備プロセス全体の自動化と効率化を目指します。

## Project Goal

* LoRA学習用データセット作成の自動化と効率化

## Key Features

* 画像処理、AIタグ・キャプション生成、DB管理、GUI

## Overall Architecture

* Pythonベース、PySide6 GUI、SQLite DB、外部AI API連携

## Key Technologies

*   **Core:** Python (>=3.12)
*   **GUI:** PySide6, superqt
*   **Image Processing:** Pillow, OpenCV, NumPy, ImageHash, Spandrel
*   **AI Integration:** Google Generative AI API, Anthropic API, OpenAI API
*   **Database:** SQLite
*   **ML/Parallel:** pytorch-lightning, joblib
*   **Configuration:** TOML
*   **Custom Libraries:** image-annotator-lib, genai-tag-db-tools
*   **Development Tools:** Git, uv, hatchling, Ruff, pytest

---
*Footnotes:*
*(Optional)[YYYY-MM-DD HH:MM:SS] - [Summary of Change]*
2025-04-14 03:12:05 - Initial population based on user input and pyproject.toml.