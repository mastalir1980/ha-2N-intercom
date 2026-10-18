"""Consistency checks for strings.json, translations and icons."""

from __future__ import annotations

import json
import re
import unittest

from _stubs import INTEGRATION_DIR


def _load(name: str) -> dict:
    return json.loads((INTEGRATION_DIR / name).read_text(encoding="utf-8"))


def _keys(node: object, prefix: str = "") -> set[str]:
    if not isinstance(node, dict):
        return {prefix}
    keys: set[str] = set()
    for key, value in node.items():
        keys |= _keys(value, f"{prefix}.{key}" if prefix else key)
    return keys


class TranslationConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.strings = _load("strings.json")
        cls.languages = {
            lang: _load(f"translations/{lang}.json") for lang in ("en", "de", "cs")
        }

    def test_english_translation_matches_strings(self) -> None:
        strings = json.loads(json.dumps(self.strings))
        strings["config"].pop("progress", None)
        self.assertEqual(self.languages["en"], strings)

    def test_all_languages_share_the_same_keys(self) -> None:
        expected = _keys(self.languages["en"])
        for lang, data in self.languages.items():
            with self.subTest(lang=lang):
                self.assertEqual(_keys(data), expected)

    def test_placeholders_match_across_languages(self) -> None:
        placeholder = re.compile(r"\{(\w+)\}")
        english = self.languages["en"]["exceptions"]
        for lang, data in self.languages.items():
            for key, value in data["exceptions"].items():
                with self.subTest(lang=lang, key=key):
                    self.assertEqual(
                        set(placeholder.findall(value["message"])),
                        set(placeholder.findall(english[key]["message"])),
                    )

    def test_grant_access_and_last_ring_are_translated(self) -> None:
        source = (INTEGRATION_DIR / "__init__.py").read_text(encoding="utf-8")
        used = set(re.findall(r'"(grant_access_[a-z_]+)"', source)) - {
            "grant_access_user"
        }
        self.assertEqual(
            used,
            {
                "grant_access_no_user",
                "grant_access_invalid_access_point",
                "grant_access_denied",
                "grant_access_unauthorized",
                "grant_access_ap_disabled",
                "grant_access_unsupported",
                "grant_access_failed",
            },
        )
        for lang, data in self.languages.items():
            with self.subTest(lang=lang):
                self.assertTrue(used <= set(data["exceptions"]))
                self.assertIn("grant_access", data["services"])
                self.assertEqual(
                    set(data["services"]["grant_access"]["fields"]),
                    {"config_entry_id", "access_point", "user"},
                )
                self.assertIn("last_ring", data["entity"]["image"])
                self.assertEqual(
                    set(data["selector"]["access_point"]["options"]), {"0", "1"}
                )
                self.assertIn(
                    "grant_access_user",
                    data["options"]["step"]["device"]["data"],
                )

    def test_icons_cover_new_entities_and_services(self) -> None:
        icons = _load("icons.json")
        self.assertEqual(icons["entity"]["image"]["last_ring"]["default"], "mdi:doorbell-video")
        self.assertEqual(icons["services"]["grant_access"], "mdi:door-open")
        self.assertEqual(set(icons["services"]), set(self.strings["services"]))

    def test_doorbell_event_translations_and_icon(self) -> None:
        for lang, data in {"strings": self.strings, **self.languages}.items():
            with self.subTest(lang=lang):
                self.assertNotIn("doorbell", data["entity"]["binary_sensor"])
                event = data["entity"]["event"]["doorbell"]
                self.assertTrue(event["name"])
                self.assertEqual(
                    set(event["state_attributes"]["event_type"]["state"]), {"ring"}
                )
                self.assertTrue(event["state_attributes"]["event_type"]["state"]["ring"])
        self.assertEqual(
            _load("icons.json")["entity"]["event"]["doorbell"]["default"], "mdi:doorbell"
        )
        self.assertNotIn("doorbell", _load("icons.json")["entity"]["binary_sensor"])

    def test_io_output_names_errors_and_icons(self) -> None:
        for lang, data in self.languages.items():
            with self.subTest(lang=lang):
                self.assertEqual(
                    set(re.findall(r"\{(\w+)\}", data["entity"]["switch"]["io_output"]["name"])),
                    {"port"},
                )
                self.assertIn("io_control_failed", data["exceptions"])
        self.assertEqual(
            _load("icons.json")["entity"]["switch"]["io_output"],
            {
                "default": "mdi:electric-switch",
                "state": {"on": "mdi:electric-switch-closed"},
            },
        )

    def test_io_input_names_placeholders_and_icons(self) -> None:
        names = {
            "en": ("Input {port}", "Tamper {port}"),
            "de": ("Eingang {port}", "Sabotage {port}"),
            "cs": ("Vstup {port}", "Sabotáž {port}"),
        }
        for lang, data in self.languages.items():
            for key, name in zip(("io_input", "io_tamper"), names[lang]):
                with self.subTest(lang=lang, key=key):
                    translated_name = data["entity"]["binary_sensor"][key]["name"]
                    self.assertEqual(translated_name, name)
                    self.assertEqual(set(re.findall(r"\{(\w+)\}", translated_name)), {"port"})
        icons = _load("icons.json")["entity"]["binary_sensor"]
        self.assertEqual(
            icons["io_input"],
            {"default": "mdi:import", "state": {"on": "mdi:electric-switch-closed"}},
        )
        self.assertEqual(
            icons["io_tamper"],
            {"default": "mdi:shield-check", "state": {"on": "mdi:shield-alert"}},
        )


if __name__ == "__main__":
    unittest.main()
