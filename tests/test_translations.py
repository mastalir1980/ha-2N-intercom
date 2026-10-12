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

    def test_last_ring_is_translated(self) -> None:
        for lang, data in self.languages.items():
            with self.subTest(lang=lang):
                self.assertIn("last_ring", data["entity"]["image"])

    def test_icons_cover_new_entities_and_services(self) -> None:
        icons = _load("icons.json")
        self.assertEqual(icons["entity"]["image"]["last_ring"]["default"], "mdi:doorbell-video")
        self.assertEqual(set(icons["services"]), set(self.strings["services"]))


if __name__ == "__main__":
    unittest.main()
