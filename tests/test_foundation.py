"""Sprint 00 foundation gate.

Verifies the engineering foundation is present and internally consistent. Written
with the stdlib ``unittest`` runner so it needs no third-party dependencies and can
run before the Python stack exists (Sprint 01). ``pytest`` also collects these
tests, so the gate keeps running in later sprints.

Run: ``python3 -m unittest discover -s tests -v``
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that must exist for the foundation to be considered established.
REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "CHANGELOG.md",
    ".gitignore",
    ".env.example",
    "docs/architecture/overview.md",
    "docs/decisions/ADR-001-modular-monolith.md",
    "docs/decisions/ADR-002-technology-stack.md",
    "docs/decisions/ADR-003-missing-data-representation.md",
    "docs/decisions/ADR-004-historical-observations-model.md",
    "docs/data/README.md",
    "docs/api/README.md",
    "docs/sprints/README.md",
    "docs/sprints/sprint-00-plan.md",
    "docs/sprints/sprint-00-report.md",
]

# Documentation directories that must exist (§41 structure).
REQUIRED_DIRS = [
    "docs/architecture",
    "docs/decisions",
    "docs/data",
    "docs/api",
    "docs/sprints",
    "tests",
]


class FoundationStructureTest(unittest.TestCase):
    def test_required_files_exist_and_non_empty(self) -> None:
        for rel in REQUIRED_FILES:
            path = REPO_ROOT / rel
            with self.subTest(file=rel):
                self.assertTrue(path.is_file(), f"missing required file: {rel}")
                self.assertGreater(
                    path.stat().st_size, 0, f"required file is empty: {rel}"
                )

    def test_required_directories_exist(self) -> None:
        for rel in REQUIRED_DIRS:
            path = REPO_ROOT / rel
            with self.subTest(directory=rel):
                self.assertTrue(path.is_dir(), f"missing required directory: {rel}")


class FoundationContentTest(unittest.TestCase):
    def test_env_example_contains_no_obvious_real_secret(self) -> None:
        """`.env.example` documents shape only; secrets must be blank/placeholder."""
        text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        secret_keys = [
            "COINGECKO_API_KEY",
            "DEFILLAMA_API_KEY",
            "TELEGRAM_BOT_TOKEN",
            "POSTGRES_PASSWORD",
        ]
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.split("#", 1)[0].strip()
            if key in secret_keys:
                with self.subTest(key=key):
                    self.assertIn(
                        value,
                        {"", "change_me"},
                        f"{key} in .env.example must be blank or a placeholder, "
                        f"not a real secret",
                    )

    def test_gitignore_excludes_dotenv(self) -> None:
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", text, ".gitignore must exclude .env")

    def test_changelog_has_semver_entry(self) -> None:
        text = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"\[\d+\.\d+\.\d+\]",
            "CHANGELOG.md must contain at least one semantic-version entry",
        )

    def test_every_adr_has_status_and_decision(self) -> None:
        adr_dir = REPO_ROOT / "docs" / "decisions"
        adrs = sorted(adr_dir.glob("ADR-*.md"))
        self.assertGreaterEqual(len(adrs), 4, "expected at least four ADRs")
        for adr in adrs:
            body = adr.read_text(encoding="utf-8")
            with self.subTest(adr=adr.name):
                self.assertRegex(
                    body, r"(?i)status", f"{adr.name} must record a Status"
                )
                self.assertRegex(
                    body,
                    r"(?im)^##\s+Decision",
                    f"{adr.name} must contain a Decision section",
                )

    def test_agents_md_declares_core_data_rules(self) -> None:
        """Data-integrity rules must be discoverable in AGENTS.md."""
        text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for marker in ("UNKNOWN", "NOT_AVAILABLE", "NOT_APPLICABLE"):
            with self.subTest(marker=marker):
                self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
