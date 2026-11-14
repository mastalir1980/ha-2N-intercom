"""Offline tests for the pipeline's unit-test requirements check."""

from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _stubs import REPO_ROOT, load_module


class UnitDepsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module(
            "e2e_unitdeps_test", REPO_ROOT / "e2e" / "e2elib" / "unitdeps.py"
        )

    def _requirements(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "requirements.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def _installed(self, *names: str):
        metadata = self.module.metadata

        def version(name: str) -> str:
            if name in names:
                return "1.0"
            raise metadata.PackageNotFoundError(name)

        return patch.object(metadata, "version", side_effect=version)

    def test_requirement_names_ignore_versions_comments_and_options(self) -> None:
        text = "# tools\nJinja2>=3.1\nPyYAML >= 6.0  # yaml\n\n-r other.txt\npkg[extra]==1; python_version>'3'\n"
        self.assertEqual(
            self.module.requirement_names(text), ["Jinja2", "PyYAML", "pkg"]
        )

    def test_missing_lists_only_absent_distributions(self) -> None:
        path = self._requirements("Jinja2>=3.1\nPyYAML>=6.0\n")
        with self._installed("PyYAML"):
            self.assertEqual(self.module.missing(path), ["Jinja2"])
        with self._installed("Jinja2", "PyYAML"):
            self.assertEqual(self.module.missing(path), [])

    def test_main_names_the_file_and_the_install_command(self) -> None:
        path = self._requirements("Jinja2>=3.1\nPyYAML>=6.0\n")
        out = io.StringIO()
        with self._installed("PyYAML"), contextlib.redirect_stdout(out):
            code = self.module.main(["unitdeps.py", str(path)])
        self.assertEqual(code, 1)
        message = out.getvalue()
        self.assertIn("Jinja2", message)
        self.assertNotIn("PyYAML", message)
        self.assertIn(str(path), message)
        self.assertIn(f"-m pip install -r {path}", message)

    def test_main_is_silent_when_everything_is_installed(self) -> None:
        path = self._requirements("Jinja2>=3.1\n")
        out = io.StringIO()
        with self._installed("Jinja2"), contextlib.redirect_stdout(out):
            self.assertEqual(self.module.main(["unitdeps.py", str(path)]), 0)
        self.assertEqual(out.getvalue(), "")

    def test_pipeline_runs_the_check_and_setup_installs_the_requirements(self) -> None:
        run_sh = (REPO_ROOT / "e2e" / "run.sh").read_text(encoding="utf-8")
        check = run_sh.index('e2elib/unitdeps.py" tests/requirements.txt')
        self.assertLess(check, run_sh.index("-m unittest discover"))
        setup = (REPO_ROOT / "e2e" / "e2e.sh").read_text(encoding="utf-8")
        self.assertIn(
            'install -q -r "$E2E/requirements.txt" -r "$REPO/tests/requirements.txt"',
            setup,
        )
        readme = (REPO_ROOT / "e2e" / "README.md").read_text(encoding="utf-8")
        self.assertIn("tests/requirements.txt", readme)


if __name__ == "__main__":
    unittest.main()
