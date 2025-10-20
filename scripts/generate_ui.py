#!/usr/bin/env python3
"""
Qt Designer UI to Python Code Generator
Converts all .ui files in the designer directory to corresponding *_ui.py files.

This script addresses the SearchFilterService connection issue that occurred when
Qt Designer UI files were not converted to Python code, causing MainWindow
to fail loading the filterSearchPanel widget.

Usage:
    uv run python scripts/generate_ui.py

Author: Claude Code (Anthropic)
Date: 2025-09-04
"""

import subprocess
import sys
from pathlib import Path
from typing import List

# Define project paths
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
UI_DESIGNER_DIR = PROJECT_ROOT / "src" / "lorairo" / "gui" / "designer"


def check_pyside6_uic() -> bool:
    """Check if pyside6-uic is available in the environment."""
    try:
        result = subprocess.run(
            ["UV_PROJECT_ENVIRONMENT=.venv_linux", "uv", "run", "which", "pyside6-uic"],
            capture_output=True,
            text=True,
            shell=True
        )
        return result.returncode == 0
    except Exception:
        return False


def find_ui_files() -> list[Path]:
    """Find all .ui files in the designer directory."""
    if not UI_DESIGNER_DIR.exists():
        print(f"❌ Designer directory not found: {UI_DESIGNER_DIR}")
        return []

    ui_files = list(UI_DESIGNER_DIR.glob("*.ui"))
    print(f"📋 Found {len(ui_files)} UI files to process")
    return ui_files


def generate_python_from_ui(ui_file: Path) -> bool:
    """Generate Python code from a UI file using pyside6-uic."""
    # Calculate output filename
    base_name = ui_file.stem
    py_file = ui_file.parent / f"{base_name}_ui.py"

    try:
        # Run pyside6-uic to convert .ui to .py
        cmd = [
            "UV_PROJECT_ENVIRONMENT=.venv_linux",
            "uv", "run", "pyside6-uic",
            str(ui_file),
            "-o", str(py_file)
        ]

        result = subprocess.run(
            " ".join(cmd),
            shell=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"✅ Generated {py_file.name} from {ui_file.name}")
            return True
        else:
            print(f"❌ Failed to generate {py_file.name}: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error generating {py_file.name}: {e}")
        return False


def main():
    """Main function to generate all UI Python files."""
    print("🔧 Qt Designer UI to Python Code Generator")
    print("=" * 50)

    # Check if pyside6-uic is available
    if not check_pyside6_uic():
        print("❌ pyside6-uic not found. Please install PySide6 tools:")
        print("   UV_PROJECT_ENVIRONMENT=.venv_linux uv add pyside6[tools]")
        sys.exit(1)

    print("✅ pyside6-uic is available")

    # Find all UI files
    ui_files = find_ui_files()
    if not ui_files:
        print("❌ No UI files found to process")
        sys.exit(1)

    # Generate Python files
    success_count = 0
    error_count = 0

    for ui_file in ui_files:
        if generate_python_from_ui(ui_file):
            success_count += 1
        else:
            error_count += 1

    # Summary
    print("\n" + "=" * 50)
    print("📊 Generation Summary:")
    print(f"   ✅ Success: {success_count} files")
    print(f"   ❌ Errors:  {error_count} files")

    if error_count == 0:
        print("\n🎉 All UI files generated successfully!")
        print("   MainWindow can now create filterSearchPanel widget")
        print("   SearchFilterService connection should work")
    else:
        print(f"\n⚠️  {error_count} files failed to generate")
        print("   Please check the error messages above")
        sys.exit(1)


if __name__ == "__main__":
    main()
