"""Offline release metadata and user-facing upgrade documentation checks."""

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
        cls.releases = re.findall(
            r"^## (\d+\.\d+\.\d+) - (\d{4}-\d{2}-\d{2})\n(.*?)(?=^## |\Z)",
            cls.changelog,
            flags=re.MULTILINE | re.DOTALL,
        )
        cls.docs = {
            name: " ".join(
                (REPO_ROOT / name).read_text(encoding="utf-8").replace("**", "").split()
            )
            for name in ("README.md", "INSTALLATION.md")
        }

    def test_manifest_version_matches_latest_dated_changelog(self) -> None:
        self.assertTrue(self.releases)
        version, released_on, _ = self.releases[0]
        self.assertEqual(self.manifest["version"], version)
        self.assertEqual(date.fromisoformat(released_on).isoformat(), released_on)

    def test_v151_documents_log_subscription_fix(self) -> None:
        self.assertEqual(self.manifest["version"], "1.5.1")
        self.assertEqual([version for version, _, _ in self.releases[:2]],
                         ["1.5.1", "1.5.0"])
        release = self.releases[0][2]
        for detail in (
            "### Fixes", "log subscriptions", "2N IP Uni",
            "Unsupported events", "doorbell ring detection", "#105",
        ):
            with self.subTest(detail=detail):
                self.assertIn(detail, release)

    def test_v150_has_user_facing_release_groups(self) -> None:
        releases = {version: body for version, _, body in self.releases}
        self.assertIn("1.5.0", releases)
        for heading in (
            "### Features", "### Fixes", "### Docs", "### Security - Breaking change",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, releases["1.5.0"])

    def test_v150_security_explains_breaking_change_and_upgrade(self) -> None:
        release = next(body for version, _, body in self.releases if version == "1.5.0")
        security = " ".join(release.split("### Features", 1)[0].split())
        for instruction in (
            "HTTPS with certificate verification enabled",
            "unverified or factory self-signed certificate is treated as insecure",
            "Existing installations using Basic over unverified HTTPS will stop connecting",
            "Digest",
            "certificate Home Assistant trusts",
            "Reconfigure > Allow insecure connection",
            "Initial setup has no insecure opt-in",
            "Repair issue",
            "Digest authentication is unchanged",
            'supersedes the 1.4.0 rule that "Basic stays enabled over HTTPS"',
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, security)

    def test_both_guides_cover_new_entities_options_and_service(self) -> None:
        for name, doc in self.docs.items():
            for feature in (
                "SSDP", "image.", "_last_ring", "event.", "_doorbell", "tamper",
                "firmwarePackage", "Firmware channel", "firmware_channel",
                "active_track", "lts", "beta", "grant_access_user",
                "2n_intercom.grant_access", "access_point", "access-control events",
                "System - Control", "Access Control - Control",
            ):
                with self.subTest(file=name, feature=feature):
                    self.assertIn(feature, doc)

    def test_both_guides_explain_direct_output_safety(self) -> None:
        for name, doc in self.docs.items():
            for warning in (
                "disabled by default", "latching", "unlocked until",
                "led_secured", "I/O - Control",
            ):
                with self.subTest(file=name, warning=warning):
                    self.assertIn(warning, doc)

    def test_both_guides_explain_doorbell_migration(self) -> None:
        for name, doc in self.docs.items():
            for instruction in (
                "binary sensor", "without a deprecation period", "blueprint inputs",
                "event_type: ring",
            ):
                with self.subTest(file=name, instruction=instruction):
                    self.assertIn(instruction, doc)
            self.assertNotIn("flip the binary sensor", doc)


if __name__ == "__main__":
    unittest.main()
