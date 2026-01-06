#!/usr/bin/env python3
"""Documentation validation script.

Validates that documentation files (CLAUDE.md, docs/*.md) reference
valid file paths and that service counts match actual codebase structure.

Usage:
    python scripts/validate_docs.py                    # Full validation
    python scripts/validate_docs.py --check-services   # Service count only
    python scripts/validate_docs.py --check-paths      # File paths only
"""

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


class ValidationResult(NamedTuple):
    """Validation result."""

    passed: bool
    message: str
    details: list[str] | None = None


class DocValidator:
    """Documentation validator."""

    def __init__(self, project_root: Path):
        """Initialize validator.

        Args:
            project_root: Project root directory
        """
        self.project_root = project_root
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_all(self) -> bool:
        """Run all validation checks.

        Returns:
            True if all checks passed
        """
        results = [
            self.validate_file_paths(),
            self.validate_service_counts(),
            self.validate_integration_points(),
        ]

        return all(r.passed for r in results)

    def validate_file_paths(self) -> ValidationResult:
        """Validate all file paths referenced in documentation.

        Returns:
            ValidationResult with check status
        """
        print("Validating file paths...")

        doc_files = [
            self.project_root / "CLAUDE.md",
            self.project_root / "docs" / "services.md",
            self.project_root / "docs" / "integrations.md",
            self.project_root / "docs" / "testing.md",
        ]

        missing_paths = []
        total_paths = 0

        for doc_file in doc_files:
            if not doc_file.exists():
                missing_paths.append(f"Documentation file missing: {doc_file}")
                continue

            content = doc_file.read_text()

            # Extract file paths (pattern: src/lorairo/...)
            path_pattern = r'`(src/lorairo/[^`]+\.py)`'
            paths = re.findall(path_pattern, content)

            for path_str in paths:
                total_paths += 1
                full_path = self.project_root / path_str

                if not full_path.exists():
                    missing_paths.append(f"{doc_file.name}: {path_str} does not exist")

        if missing_paths:
            return ValidationResult(
                passed=False,
                message=f"Found {len(missing_paths)} missing file references",
                details=missing_paths,
            )

        return ValidationResult(
            passed=True, message=f"All {total_paths} file paths are valid"
        )

    def validate_service_counts(self) -> ValidationResult:
        """Validate service count matches actual files.

        Returns:
            ValidationResult with check status
        """
        print("Validating service counts...")

        # Count actual service files
        services_dir = self.project_root / "src" / "lorairo" / "services"
        gui_services_dir = self.project_root / "src" / "lorairo" / "gui" / "services"

        business_services = [
            f
            for f in services_dir.glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith("_")
        ]

        gui_services = [
            f
            for f in gui_services_dir.glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith("_")
        ]

        actual_count = len(business_services) + len(gui_services)

        # Expected count from CLAUDE.md
        expected_count = 29  # 22 business + 7 GUI

        if actual_count != expected_count:
            return ValidationResult(
                passed=False,
                message=f"Service count mismatch: expected {expected_count}, found {actual_count}",
                details=[
                    f"Business services: {len(business_services)} (expected 22)",
                    f"GUI services: {len(gui_services)} (expected 7)",
                ],
            )

        return ValidationResult(
            passed=True,
            message=f"Service count matches: {actual_count} services (22 business + 7 GUI)",
        )

    def validate_integration_points(self) -> ValidationResult:
        """Validate external package integration points.

        Returns:
            ValidationResult with check status
        """
        print("Validating integration points...")

        integration_files = [
            "src/lorairo/database/db_repository.py",
            "src/lorairo/services/tag_management_service.py",
            "src/lorairo/annotations/annotator_adapter.py",
            "src/lorairo/annotations/annotation_logic.py",
            "src/lorairo/services/annotator_library_adapter.py",
        ]

        missing_files = []

        for file_path_str in integration_files:
            full_path = self.project_root / file_path_str
            if not full_path.exists():
                missing_files.append(file_path_str)

        if missing_files:
            return ValidationResult(
                passed=False,
                message=f"Found {len(missing_files)} missing integration files",
                details=missing_files,
            )

        return ValidationResult(
            passed=True,
            message=f"All {len(integration_files)} integration points are valid",
        )


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    parser = argparse.ArgumentParser(description="Validate LoRAIro documentation")
    parser.add_argument(
        "--check-services",
        action="store_true",
        help="Check service counts only",
    )
    parser.add_argument(
        "--check-paths",
        action="store_true",
        help="Check file paths only",
    )
    parser.add_argument(
        "--check-integrations",
        action="store_true",
        help="Check integration points only",
    )

    args = parser.parse_args()

    # Determine project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    validator = DocValidator(project_root)

    # Run selected checks
    results = []

    if args.check_services:
        results.append(validator.validate_service_counts())
    elif args.check_paths:
        results.append(validator.validate_file_paths())
    elif args.check_integrations:
        results.append(validator.validate_integration_points())
    else:
        # Run all checks
        results = [
            validator.validate_file_paths(),
            validator.validate_service_counts(),
            validator.validate_integration_points(),
        ]

    # Print results
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)

    all_passed = True

    for result in results:
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"\n{status}: {result.message}")

        if result.details:
            for detail in result.details:
                print(f"  - {detail}")

        if not result.passed:
            all_passed = False

    print("\n" + "=" * 60)

    if all_passed:
        print("✅ All validation checks passed!")
        return 0
    else:
        print("❌ Some validation checks failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
