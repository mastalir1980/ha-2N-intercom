"""Offline release metadata and user documentation consistency checks."""

from __future__ import annotations

from datetime import date
import json
import re
import unittest

from _stubs import INTEGRATION_DIR, REPO_ROOT


class ReleaseDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (INTEGRATION_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        cls.changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        cls.docs = {
            name: (REPO_ROOT / name).read_text(encoding="utf-8")
            for name in ("README.md", "INSTALLATION.md")
        }

    def test_latest_changelog_version_matches_manifest(self) -> None:
        heading = next(
            line for line in self.changelog.splitlines() if line.startswith("## ")
        )
        match = re.fullmatch(r"## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})", heading)
        self.assertIsNotNone(match)
        if match is not None:
            self.assertEqual(match[1], self.manifest["version"])
            self.assertEqual(date.fromisoformat(match[2]).isoformat(), match[2])

    def test_1_5_0_changelog_groups_user_changes_and_explains_migration(self) -> None:
        section = self.changelog.split("## 1.5.0 - ", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(
            re.findall(r"^### (.+)$", section, re.MULTILINE),
            ["Features", "Fixes", "Docs"],
        )
        for topic in (
            "event.<intercom>_doorbell",
            "binary sensor",
            "blueprint inputs",
            "linked_doorbell_sensor",
            "event_type: ring",
            "SSDP",
            "Firmware channel",
            "image.<intercom>_last_ring",
            "2n_intercom.grant_access",
            "Access-control events",
            "IO input",
            "IO output",
            "unlocked",
        ):
            with self.subTest(topic=topic):
                self.assertIn(topic, section)

    def test_new_entities_options_and_services_are_in_both_user_guides(self) -> None:
        for name, source in self.docs.items():
            for topic in (
                "image.",
                "_last_ring",
                "event.",
                "_doorbell",
                "update.",
                "_firmware",
                "_input_modul1_input1",
                "_tamper_modul1_tamper",
                "_output_relay1",
                "firmware_channel",
                "active_track",
                "lts",
                "beta",
                "grant_access_user",
                "2n_intercom.grant_access",
                "access_point",
                "config_entry_id",
                "SSDP",
                "System - Control",
                "I/O - Control",
                "Access Control - Control",
            ):
                with self.subTest(document=name, topic=topic):
                    self.assertIn(topic, source)

    def test_both_user_guides_warn_about_migration_and_latching_outputs(self) -> None:
        for name, source in self.docs.items():
            with self.subTest(document=name):
                self.assertIn("without a deprecation period", source)
                self.assertIn("event_type: ring", source)
                self.assertIn("disabled by default", source)
                self.assertIn("unlocked until", source)
                self.assertIn("device web UI", source)
                self.assertIn("no Install button", source)


if __name__ == "__main__":
    unittest.main()
