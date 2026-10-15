"""Hermetic bship regressions using local Git repos and a stubbed GitHub CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLEAN_DIAGNOSIS = "No duplicate IDs, self-referential dependencies, or dependency cycles found."
DUPLICATE_DIAGNOSIS = (
    "WARNING: 1 duplicate task ID group affects 2 files.\n"
    "Repair preview (no files changed):"
)
STUB = """\
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(os.environ["BSHIP_TEST_ROOT"])
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps([name, *args]) + "\\n")
if [name, *args[:2]] == json.loads(os.environ.get("BSHIP_TEST_FAIL", "[]")):
    sys.exit("fixture command failure")
git = os.environ["BSHIP_TEST_GIT"]
if name == "git":
    os.execv(git, [git, *args])
elif name == "backlog" and args == ["doctor"]:
    if os.environ.get("BSHIP_TEST_BACKLOG"):
        os.execv(os.environ["BSHIP_TEST_BACKLOG"], [os.environ["BSHIP_TEST_BACKLOG"], *args])
    print(os.environ["BSHIP_TEST_DIAGNOSIS"])
    sys.exit(int(os.environ.get("BSHIP_TEST_DOCTOR_EXIT", "0")))
elif name == "gh" and args[:2] == ["pr", "create"]:
    print("https://github.com/example/fixture/pull/1")
elif name == "gh" and args == ["pr", "merge", "--merge", "--delete-branch"]:
    branch = subprocess.check_output(
        [git, "branch", "--show-current"], text=True).strip()
    subprocess.run(
        [git, "--git-dir", str(root / "origin.git"), "update-ref",
         "refs/heads/main", "refs/heads/" + branch], check=True)
else:
    sys.exit("unexpected fixture command")
"""


class BshipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        git = shutil.which("git")
        zsh = shutil.which("zsh")
        if git is None or zsh is None:
            raise unittest.SkipTest("git and zsh are required for bship tests")
        cls.git = git
        cls.zsh = zsh
        cls.backlog = shutil.which("backlog")
        cls.node = shutil.which("node")

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ha2n-bship-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.repo = self.root / "checkout"
        self.origin = self.root / "origin.git"
        self.seed = self.root / "seed"
        self.env = {
            "PATH": f"{self.bin}{os.pathsep}{os.defpath}",
            "HOME": str(self.home),
            "LC_ALL": "C",
            "BSHIP_REPO": str(self.repo),
            "BSHIP_TEST_ROOT": str(self.root),
            "BSHIP_TEST_GIT": self.git,
            "BSHIP_TEST_DIAGNOSIS": CLEAN_DIAGNOSIS,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(self.home / ".gitconfig"),
            "GIT_ALLOW_PROTOCOL": "file",
            "GIT_TERMINAL_PROMPT": "0",
        }
        stub = self.bin / "stub"
        stub.write_text(f"#!{sys.executable}\n{STUB}", encoding="utf-8")
        stub.chmod(0o755)
        for name in ("git", "gh", "backlog"):
            (self.bin / name).symlink_to(stub)
        if self.node is not None:
            (self.bin / "node").symlink_to(self.node)
        self._git(self.root, "config", "--global", "user.name", "Bship Test")
        self._git(self.root, "config", "--global", "user.email", "bship@example.invalid")
        self._git(self.root, "config", "--global", "commit.gpgsign", "false")
        self._git(self.root, "init", "-q", "--bare", "--initial-branch=main", str(self.origin))
        self._git(self.root, "clone", "-q", str(self.origin), str(self.seed))
        (self.seed / "backlog/tasks").mkdir(parents=True)
        (self.seed / "docs").mkdir()
        (self.seed / "backlog/config.yml").write_text(
            'project_name: "bship-fixture"\nstatuses: ["To Do", "Done"]\n'
            'remote_operations: false\nauto_commit: false\n',
            encoding="utf-8",
        )
        (self.seed / "backlog/tasks/task-1 - First.md").write_text(
            "---\nid: TASK-1\ntitle: First\nstatus: To Do\n---\n",
            encoding="utf-8",
        )
        (self.seed / "docs/guide.md").write_text("Original guide\n", encoding="utf-8")
        (self.seed / "README.md").write_text("Original readme\n", encoding="utf-8")
        self._commit_seed("Initial fixture")
        self._git(self.root, "clone", "-q", str(self.origin), str(self.repo))
        self.head = self._git(self.repo, "rev-parse", "HEAD")

    def _git(self, cwd: Path, *args: str) -> str:
        result = subprocess.run(
            [self.git, *args], cwd=cwd, env=self.env, check=True,
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout.strip()

    def _commit_seed(self, message: str) -> None:
        self._git(self.seed, "add", "-A")
        self._git(self.seed, "commit", "-q", "-m", message)
        self._git(self.seed, "push", "-q", "origin", "main")

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        (self.root / "calls.jsonl").write_text("", encoding="utf-8")
        return subprocess.run(
            [self.zsh, "-f", "-c", 'source "$1"; shift; bship "$@"',
             "bship-test", str(ROOT / "tools/bship.zsh"), *args],
            cwd=self.root, env=self.env, capture_output=True, text=True, timeout=30,
        )

    def _calls(self) -> list[list[str]]:
        return [
            json.loads(line)
            for line in (self.root / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        ]

    def _assert_refused_without_commit(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._git(self.repo, "rev-parse", "HEAD"), self.head)
        self.assertFalse(any(call[:2] == ["git", "commit"] for call in self._calls()))
        self.assertFalse(any(call[0] == "gh" for call in self._calls()))
        self.assertNotIn("backlog-", self._git(self.repo, "branch", "--format=%(refname:short)"))

    def test_ships_after_pull_and_returns_to_updated_main(self) -> None:
        (self.seed / "upstream.txt").write_text("Upstream\n", encoding="utf-8")
        self._commit_seed("Upstream update")
        (self.repo / "docs/guide.md").write_text("Local update\n", encoding="utf-8")
        self._git(self.repo, "add", "docs/guide.md")
        (self.repo / "backlog/new.md").write_text("New backlog note\n", encoding="utf-8")

        result = self._run("Backlog fixture update")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._git(self.repo, "branch", "--show-current"), "main")
        self.assertEqual(self._git(self.repo, "status", "--porcelain"), "")
        self.assertEqual(
            self._git(self.repo, "rev-parse", "HEAD"),
            self._git(self.origin, "rev-parse", "main"),
        )
        self.assertEqual((self.repo / "upstream.txt").read_text(), "Upstream\n")
        self.assertEqual((self.repo / "docs/guide.md").read_text(), "Local update\n")
        self.assertEqual(
            set(self._git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()),
            {"backlog/new.md", "docs/guide.md"},
        )
        calls = self._calls()
        self.assertLess(calls.index(["git", "pull", "--ff-only"]), calls.index(["backlog", "doctor"]))
        branch_index = next(i for i, call in enumerate(calls) if call[:3] == ["git", "switch", "-c"])
        self.assertLess(calls.index(["backlog", "doctor"]), branch_index)
        self.assertIn(
            ["gh", "pr", "create", "--base", "main", "--title", "Backlog fixture update",
             "--body", "Backlog-only change."], calls,
        )
        self.assertIn(["gh", "pr", "merge", "--merge", "--delete-branch"], calls)
        self.assertEqual(
            [call for call in calls if call[:2] == ["git", "pull"]],
            [["git", "pull", "--ff-only"], ["git", "pull", "-q", "--ff-only"]],
        )

    def test_default_title_and_repository_location(self) -> None:
        default = self.home / "programing/ha-2n-intercom"
        default.parent.mkdir()
        self.repo.rename(default)
        self.repo = default
        del self.env["BSHIP_REPO"]
        (self.repo / "docs/guide.md").write_text("Default checkout update\n", encoding="utf-8")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self._git(self.repo, "log", "-1", "--format=%s"), "Backlog update")

    def test_refuses_non_main_branch(self) -> None:
        self._git(self.repo, "switch", "-q", "-c", "feature")
        result = self._run()
        self._assert_refused_without_commit(result)
        self.assertIn("must be on main", result.stderr)
        self.assertNotIn(["git", "pull", "--ff-only"], self._calls())

    def test_refuses_detached_head(self) -> None:
        self._git(self.repo, "switch", "-q", "--detach")
        self._assert_refused_without_commit(self._run())

    def test_refuses_outside_changes(self) -> None:
        for mode in ("unstaged", "staged", "untracked", "renamed"):
            with self.subTest(mode=mode):
                if mode == "untracked":
                    path = self.repo / "nested/new.txt"
                    path.parent.mkdir()
                    path.write_text("Outside\n", encoding="utf-8")
                elif mode == "renamed":
                    self._git(self.repo, "mv", "README.md", "docs/readme.md")
                else:
                    (self.repo / "README.md").write_text("Outside\n", encoding="utf-8")
                    if mode == "staged":
                        self._git(self.repo, "add", "README.md")
                before = self._git(self.repo, "status", "--porcelain")
                result = self._run()
                self._assert_refused_without_commit(result)
                self.assertIn("changes outside backlog/ and docs/", result.stderr)
                self.assertEqual(self._git(self.repo, "status", "--porcelain"), before)
                self.assertNotIn(["git", "pull", "--ff-only"], self._calls())
                if mode == "untracked":
                    path.unlink()
                    path.parent.rmdir()
                else:
                    self._git(self.repo, "restore", "--source=HEAD", "--staged", "--worktree", ".")

    def test_pull_conflict_preserves_local_changes_and_stops(self) -> None:
        (self.seed / "docs/guide.md").write_text("Remote change\n", encoding="utf-8")
        self._commit_seed("Conflicting update")
        (self.repo / "docs/guide.md").write_text("Local change\n", encoding="utf-8")
        result = self._run()
        self._assert_refused_without_commit(result)
        self.assertIn("pull failed", result.stderr)
        self.assertEqual((self.repo / "docs/guide.md").read_text(), "Local change\n")
        self.assertNotIn(["backlog", "doctor"], self._calls())

    def test_diverged_main_cannot_be_pulled(self) -> None:
        (self.repo / "docs/local.md").write_text("Local commit\n", encoding="utf-8")
        self._git(self.repo, "add", "docs/local.md")
        self._git(self.repo, "commit", "-q", "-m", "Local main commit")
        self.head = self._git(self.repo, "rev-parse", "HEAD")
        (self.seed / "docs/remote.md").write_text("Remote commit\n", encoding="utf-8")
        self._commit_seed("Remote main commit")
        result = self._run()
        self._assert_refused_without_commit(result)
        self.assertIn("pull failed", result.stderr)
        self.assertNotIn(["backlog", "doctor"], self._calls())

    def test_refuses_duplicate_diagnoses_even_with_zero_exit(self) -> None:
        for diagnosis in (
            DUPLICATE_DIAGNOSIS,
            "WARNING: 1 DuPlIcAtE task Id GrOuP affects 2 files.",
            "RePaIr PrEvIeW (no files changed):",
        ):
            with self.subTest(diagnosis=diagnosis):
                self.env["BSHIP_TEST_DIAGNOSIS"] = diagnosis
                result = self._run()
                self._assert_refused_without_commit(result)
                self.assertIn("backlog doctor --fix", result.stderr)
                self.assertEqual(
                    [call for call in self._calls() if call[0] == "backlog"],
                    [["backlog", "doctor"]],
                )

    def test_accepts_other_successful_diagnoses(self) -> None:
        for index, diagnosis in enumerate((
            "No duplicate task IDs found in active or completed tasks.",
            "Doctor check completed.",
            "",
        )):
            with self.subTest(diagnosis=diagnosis):
                self.env["BSHIP_TEST_DIAGNOSIS"] = diagnosis
                (self.repo / "docs/guide.md").write_text(f"Update {index}\n", encoding="utf-8")
                result = self._run()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                branch = next(
                    call[3] for call in self._calls()
                    if call[:3] == ["git", "switch", "-c"]
                )
                self._git(self.repo, "branch", "-D", branch)

    def test_stops_when_doctor_fails(self) -> None:
        self.env["BSHIP_TEST_DOCTOR_EXIT"] = "1"
        result = self._run()
        self._assert_refused_without_commit(result)
        self.assertIn("backlog doctor failed", result.stderr)

    def test_real_doctor_allows_clean_backlog(self) -> None:
        if self.backlog is None:
            self.skipTest("Backlog CLI is required for the real doctor regression")
        self.env["BSHIP_TEST_BACKLOG"] = self.backlog
        (self.repo / "docs/guide.md").write_text("Local update\n", encoding="utf-8")
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No duplicate", result.stdout)

    def test_real_doctor_refuses_duplicate_pulled_from_main(self) -> None:
        if self.backlog is None:
            self.skipTest("Backlog CLI is required for the real duplicate-ID regression")
        self.env["BSHIP_TEST_BACKLOG"] = self.backlog
        (self.seed / "backlog/tasks/task-1 - Duplicate.md").write_text(
            "---\nid: TASK-1\ntitle: Duplicate\nstatus: To Do\n---\n",
            encoding="utf-8",
        )
        self._commit_seed("Upstream duplicate fixture")
        self.head = self._git(self.seed, "rev-parse", "HEAD")
        (self.repo / "docs/local.md").write_text("Preserve local note\n", encoding="utf-8")
        result = self._run()
        self._assert_refused_without_commit(result)
        self.assertIn("TASK-1", result.stdout + result.stderr)
        self.assertIn("task-1 - Duplicate.md", result.stdout + result.stderr)
        self.assertIn("backlog doctor --fix", result.stderr)
        self.assertTrue((self.repo / "backlog/tasks/task-1 - Duplicate.md").exists())
        self.assertEqual((self.repo / "docs/local.md").read_text(), "Preserve local note\n")

    def test_shipping_failures_stop_before_returning_to_main(self) -> None:
        for command in (["git", "push", "-q"], ["gh", "pr", "create"], ["gh", "pr", "merge"]):
            with self.subTest(command=command):
                self.env["BSHIP_TEST_FAIL"] = json.dumps(command)
                (self.repo / "docs/guide.md").write_text(str(command), encoding="utf-8")
                result = self._run()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PR shipping failed", result.stderr)
                branch = self._git(self.repo, "branch", "--show-current")
                self.assertTrue(branch.startswith("backlog-"), branch)
                self.assertNotIn(["git", "switch", "-q", "main"], self._calls())
                self._git(self.repo, "switch", "-q", "main")
                self._git(self.repo, "branch", "-D", branch)

    def test_final_pull_failure_is_reported(self) -> None:
        self.env["BSHIP_TEST_FAIL"] = json.dumps(["git", "pull", "-q"])
        (self.repo / "docs/guide.md").write_text("Local update\n", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PR merged, but updating main failed", result.stderr)
        self.assertEqual(self._git(self.repo, "branch", "--show-current"), "main")


class E2EPathFilterTests(unittest.TestCase):
    def test_ordered_paths_keep_config_relevant_and_dispatch_unfiltered(self) -> None:
        source = (ROOT / ".github/workflows/e2e-pi.yml").read_text(encoding="utf-8")
        self.assertIn(
            "  pull_request_target:\n"
            "    types: [opened, synchronize, reopened]\n"
            "    paths:\n"
            "      - '**'\n"
            "      - '!backlog/**'\n"
            "      - '!docs/**/*.md'\n"
            "      - 'backlog/config.yml'\n"
            "  workflow_dispatch:\n"
            "    inputs:\n",
            source,
        )

    def test_hacs_and_hassfest_push_only_main_and_skip_backlog_only_prs(self) -> None:
        for name in ("hacs.yml", "hassfest.yml"):
            with self.subTest(workflow=name):
                source = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
                self.assertIn(
                    "on:\n"
                    "  push:\n"
                    "    branches: [main]\n"
                    "  pull_request:\n"
                    "    paths:\n"
                    "      - '**'\n"
                    "      - '!backlog/**'\n"
                    "      - '!docs/**/*.md'\n"
                    "      - 'backlog/config.yml'\n"
                    "  workflow_dispatch:\n",
                    source,
                )


if __name__ == "__main__":
    unittest.main()
